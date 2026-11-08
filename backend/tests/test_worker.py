import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import JobStatus, VideoStatus
from app.services import jobs
from app.services.jobs import ClaimedJob, JobError, MediaResult
from app.workers import main as worker
from tests.job_helpers import MEDIA, claim, enqueue, expire_lease, load_job, load_video, make_due


async def _succeed(_: ClaimedJob) -> MediaResult:
    return MEDIA


@pytest.fixture
def fast_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_HEARTBEAT_INTERVAL", "PT0.02S")
    monkeypatch.setenv("JOB_POLL_INTERVAL", "PT0.01S")
    get_settings.cache_clear()


async def test_nothing_to_do(session: AsyncSession) -> None:
    assert await worker.run_one(_succeed, "w1") is False


async def test_success_makes_the_video_ready(session: AsyncSession) -> None:
    queued = await enqueue(session)

    assert await worker.run_one(_succeed, "w1") is True

    assert (await load_job(session, queued.id)).status is JobStatus.done
    assert (await load_video(session, queued.video_id)).status is VideoStatus.ready


async def test_job_of_a_dead_worker_is_finished_by_another(session: AsyncSession) -> None:
    """D19."""
    queued = await enqueue(session)
    assert await claim("dead") is not None
    await expire_lease(session, queued.id)

    assert await worker.run_one(_succeed, "alive") is True

    job = await load_job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.done, 2)
    assert (await load_video(session, queued.video_id)).status is VideoStatus.ready


async def test_a_failing_job_stops_after_three_attempts(session: AsyncSession) -> None:
    """D21."""
    queued = await enqueue(session)
    runs = 0

    async def always_fail(_: ClaimedJob) -> MediaResult:
        nonlocal runs
        runs += 1
        raise JobError("Not a video file")

    for _ in range(5):
        await worker.run_one(always_fail, "w1")
        await make_due(session, queued.id)

    assert runs == 3
    job = await load_job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.failed, 3)
    video = await load_video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (VideoStatus.failed, "Not a video file")


async def test_a_retry_can_succeed(session: AsyncSession) -> None:
    queued = await enqueue(session)
    results: list[Exception | MediaResult] = [RuntimeError("flaky"), MEDIA]

    async def flaky(_: ClaimedJob) -> MediaResult:
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    await worker.run_one(flaky, "w1")
    await make_due(session, queued.id)
    await worker.run_one(flaky, "w1")

    job = await load_job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.done, 2)
    assert (await load_video(session, queued.video_id)).status is VideoStatus.ready


async def test_unexpected_error_text_stays_internal(session: AsyncSession) -> None:
    queued = await enqueue(session, max_attempts=1)

    async def crash(_: ClaimedJob) -> MediaResult:
        raise RuntimeError("/srv/secret/path")

    await worker.run_one(crash, "w1")

    video = await load_video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (VideoStatus.failed, jobs.GENERIC_FAILURE)


async def test_work_that_cancels_itself_counts_as_a_failure(session: AsyncSession) -> None:
    queued = await enqueue(session)

    async def cancels_itself(_: ClaimedJob) -> MediaResult:
        raise asyncio.CancelledError

    assert await worker.run_one(cancels_itself, "w1") is True

    job = await load_job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.queued, 1)
    assert "cancelled" in (job.last_error or "")


async def test_heartbeat_renews_the_lease_during_slow_work(
    session: AsyncSession, fast_timers: None
) -> None:
    queued = await enqueue(session)
    seen = []

    async def slow(_: ClaimedJob) -> MediaResult:
        async with get_sessionmaker()() as other:
            seen.append((await load_job(other, queued.id)).locked_until)
            await asyncio.sleep(0.2)
            await other.rollback()
            seen.append((await load_job(other, queued.id)).locked_until)
        return MEDIA

    await worker.run_one(slow, "w1")

    assert seen[1] > seen[0]


async def test_a_lost_lease_cancels_the_work_and_writes_nothing(
    session: AsyncSession, fast_timers: None
) -> None:
    queued = await enqueue(session)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang(_: ClaimedJob) -> MediaResult:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return MEDIA

    running = asyncio.ensure_future(worker.run_one(hang, "old"))
    await asyncio.wait_for(started.wait(), timeout=5)
    await expire_lease(session, queued.id)
    assert await claim("new") is not None

    assert await asyncio.wait_for(running, timeout=5) is True

    assert cancelled.is_set()
    job = await load_job(session, queued.id)
    assert (job.status, job.attempts, job.locked_by) == (JobStatus.running, 2, "new")
    assert job.last_error is None
    assert (await load_video(session, queued.video_id)).status is VideoStatus.processing


async def test_shutdown_stops_the_work_and_leaves_the_job_to_its_lease(
    session: AsyncSession,
) -> None:
    queued = await enqueue(session)
    started = asyncio.Event()

    async def hang(_: ClaimedJob) -> MediaResult:
        started.set()
        await asyncio.Event().wait()
        return MEDIA

    running = asyncio.ensure_future(worker.run_one(hang, "w1"))
    await asyncio.wait_for(started.wait(), timeout=5)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    job = await load_job(session, queued.id)
    assert (job.status, job.last_error) == (JobStatus.running, None)


async def test_the_loop_outlives_errors(
    session: AsyncSession, fast_timers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    second_call = asyncio.Event()
    calls = 0

    async def broken(*_: object) -> bool:
        nonlocal calls
        calls += 1
        if calls >= 2:
            second_call.set()
        raise ConnectionError("database is away")

    monkeypatch.setattr(worker, "run_one", broken)
    loop = asyncio.ensure_future(worker.run_forever(_succeed, "w1"))
    await asyncio.wait_for(second_call.wait(), timeout=5)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
