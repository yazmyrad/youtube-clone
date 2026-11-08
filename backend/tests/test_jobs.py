import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.models import JobStatus, ProcessingJob, VideoStatus
from app.services import jobs
from app.services.jobs import ClaimedJob, JobError
from tests.job_helpers import MEDIA, enqueue, expire_lease, load_job, load_video, make_due
from tests.job_helpers import claim as claim_job


async def _db_now(session: AsyncSession) -> datetime:
    """The current time, unlike now(), which is fixed when the transaction starts."""
    now = await session.scalar(select(func.clock_timestamp()))
    assert now is not None
    return now


async def test_claim_marks_the_job_running(session: AsyncSession) -> None:
    queued = await enqueue(session)
    claim = await claim_job("w1")
    assert claim == ClaimedJob(id=queued.id, video_id=queued.video_id, attempt=1)

    job = await load_job(session, queued.id)
    assert job.status is JobStatus.running
    assert job.locked_by == "w1"
    assert job.locked_until is not None


async def test_claim_on_an_empty_queue(session: AsyncSession) -> None:
    assert await claim_job() is None


async def test_concurrent_claims_never_share_a_job(session: AsyncSession) -> None:
    """D18."""
    queued = [await enqueue(session) for _ in range(3)]
    claims = await asyncio.gather(*(claim_job(f"w{i}") for i in range(10)))
    won = [claim.id for claim in claims if claim is not None]
    assert len(won) == len(set(won))
    assert set(won) <= {job.id for job in queued}


async def test_concurrent_claims_on_one_job_have_one_winner(session: AsyncSession) -> None:
    """D18."""
    await enqueue(session)
    claims = await asyncio.gather(*(claim_job(f"w{i}") for i in range(10)))
    assert len([claim for claim in claims if claim is not None]) == 1


async def test_a_locked_row_is_skipped_without_waiting(session: AsyncSession) -> None:
    locked = await enqueue(session)
    other = await enqueue(session)
    await session.execute(
        select(ProcessingJob).where(ProcessingJob.id == locked.id).with_for_update()
    )

    claim = await asyncio.wait_for(claim_job(), timeout=5)

    assert claim is not None
    assert claim.id == other.id
    await session.rollback()


async def test_a_job_that_is_not_due_is_not_claimed(session: AsyncSession) -> None:
    job = await enqueue(session)
    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job.id)
        .values(run_after=func.now() + timedelta(hours=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    assert await claim_job() is None


async def test_a_live_lease_is_not_taken(session: AsyncSession) -> None:
    await enqueue(session)
    assert await claim_job("w1") is not None
    assert await claim_job("w2") is None


async def test_an_expired_lease_is_reclaimed_with_a_new_attempt(session: AsyncSession) -> None:
    queued = await enqueue(session)
    assert await claim_job("w1") is not None
    await expire_lease(session, queued.id)

    claim = await claim_job("w2")

    assert claim is not None
    assert claim.attempt == 2
    assert (await load_job(session, queued.id)).locked_by == "w2"


async def test_heartbeat_extends_the_lease(session: AsyncSession) -> None:
    queued = await enqueue(session)
    claim = await claim_job()
    assert claim is not None
    await expire_lease(session, queued.id)

    async with get_sessionmaker()() as other:
        assert await jobs.heartbeat(other, claim) is True

    locked_until = (await load_job(session, queued.id)).locked_until
    assert locked_until is not None
    assert locked_until > await _db_now(session)


async def test_complete_makes_the_video_ready(session: AsyncSession) -> None:
    queued = await enqueue(session)
    claim = await claim_job()
    assert claim is not None

    async with get_sessionmaker()() as other:
        assert await jobs.complete(other, claim, MEDIA) is True

    job = await load_job(session, queued.id)
    assert job.status is JobStatus.done
    assert job.finished_at is not None
    assert job.locked_until is None
    video = await load_video(session, queued.video_id)
    assert video.status is VideoStatus.ready
    assert (video.hls_prefix, video.thumbnail_key, video.duration_seconds) == (
        MEDIA.hls_prefix,
        MEDIA.thumbnail_key,
        MEDIA.duration_seconds,
    )
    assert video.published_at is not None


async def test_stale_worker_changes_nothing(session: AsyncSession) -> None:
    """D20."""
    queued = await enqueue(session)
    stale = await claim_job("old")
    assert stale is not None
    await expire_lease(session, queued.id)
    current = await claim_job("new")
    assert current is not None
    before = await load_job(session, queued.id)
    locked_until = before.locked_until

    async with get_sessionmaker()() as other:
        assert await jobs.heartbeat(other, stale) is False
        assert await jobs.complete(other, stale, MEDIA) is False
        assert await jobs.fail(other, stale, RuntimeError("late")) is False

    job = await load_job(session, queued.id)
    assert (job.status, job.attempts, job.locked_by) == (JobStatus.running, 2, "new")
    assert job.locked_until == locked_until
    assert job.last_error is None
    assert (await load_video(session, queued.video_id)).status is VideoStatus.processing

    async with get_sessionmaker()() as other:
        assert await jobs.complete(other, current, MEDIA) is True
    assert (await load_video(session, queued.video_id)).status is VideoStatus.ready


async def test_failure_requeues_with_backoff(session: AsyncSession) -> None:
    queued = await enqueue(session)
    claim = await claim_job()
    assert claim is not None

    async with get_sessionmaker()() as other:
        assert await jobs.fail(other, claim, RuntimeError("boom")) is True

    job = await load_job(session, queued.id)
    assert (job.status, job.locked_by, job.locked_until) == (JobStatus.queued, None, None)
    assert "boom" in (job.last_error or "")
    assert job.run_after > await _db_now(session) + timedelta(seconds=20)
    assert (await load_video(session, queued.video_id)).status is VideoStatus.processing
    assert await claim_job() is None


async def test_backoff_doubles_each_attempt(session: AsyncSession) -> None:
    queued = await enqueue(session)
    for _ in range(2):
        claim = await claim_job()
        assert claim is not None
        async with get_sessionmaker()() as other:
            await jobs.fail(other, claim, RuntimeError("boom"))
        if claim.attempt == 1:
            await make_due(session, queued.id)

    job = await load_job(session, queued.id)
    assert job.run_after > await _db_now(session) + timedelta(seconds=50)


async def _fail_every_attempt(session: AsyncSession, job_id: int, error: Exception) -> None:
    for _ in range(3):
        claim = await claim_job()
        assert claim is not None
        async with get_sessionmaker()() as other:
            assert await jobs.fail(other, claim, error) is True
        await make_due(session, job_id)


async def test_last_failure_is_final_and_keeps_a_readable_reason(session: AsyncSession) -> None:
    """D21."""
    queued = await enqueue(session)
    await _fail_every_attempt(session, queued.id, JobError("Not a video file"))

    job = await load_job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.failed, 3)
    assert job.finished_at is not None
    video = await load_video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (VideoStatus.failed, "Not a video file")
    assert await claim_job() is None


async def test_unexpected_error_text_stays_internal(session: AsyncSession) -> None:
    queued = await enqueue(session)
    await _fail_every_attempt(session, queued.id, RuntimeError("/srv/secret/path"))

    job = await load_job(session, queued.id)
    assert "/srv/secret/path" in (job.last_error or "")
    video = await load_video(session, queued.video_id)
    assert video.failure_reason == jobs.GENERIC_FAILURE


async def test_worker_dying_on_the_last_attempt_ends_the_job(session: AsyncSession) -> None:
    """D21: a file that kills the worker must not be retried forever."""
    queued = await enqueue(session)
    other = await enqueue(session)
    for attempt in range(3):
        claim = await claim_job()
        assert claim is not None
        assert claim.id == queued.id
        assert claim.attempt == attempt + 1
        await expire_lease(session, queued.id)

    claim = await claim_job()

    assert claim is not None
    assert claim.id == other.id  # The exhausted job is closed and the next one is handed out.
    job = await load_job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.failed, 3)
    video = await load_video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (VideoStatus.failed, jobs.CRASH_FAILURE)


@pytest.mark.parametrize("final", [VideoStatus.ready, VideoStatus.failed])
async def test_a_final_video_status_is_not_overwritten(
    session: AsyncSession, final: VideoStatus
) -> None:
    queued = await enqueue(session)
    claim = await claim_job()
    assert claim is not None
    video = await load_video(session, queued.video_id)
    video.status = final
    if final is VideoStatus.ready:
        video.hls_prefix = "hls/old"
        video.thumbnail_key = "thumbs/old.jpg"
        video.duration_seconds = 1
        video.published_at = func.now()
    await session.commit()

    async with get_sessionmaker()() as other:
        await jobs.complete(other, claim, MEDIA)

    video = await load_video(session, queued.video_id)
    assert video.status is final
    assert video.hls_prefix == ("hls/old" if final is VideoStatus.ready else None)
