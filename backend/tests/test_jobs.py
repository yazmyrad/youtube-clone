import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.models import JobStatus, ProcessingJob, User, Video, VideoStatus
from app.services import jobs
from app.services.jobs import ClaimedJob, JobError, MediaResult

MEDIA = MediaResult(hls_prefix="hls/x", thumbnail_key="thumbs/x.jpg", duration_seconds=5)


async def _enqueue(session: AsyncSession, **job_fields: object) -> ProcessingJob:
    name = f"user_{uuid.uuid4().hex[:12]}"
    user = User(username=name, email=f"{name}@example.com", password_hash="x", display_name="A")
    session.add(user)
    await session.flush()
    video = Video(owner_id=user.id, title="Clip", status=VideoStatus.processing)
    session.add(video)
    await session.flush()
    job = ProcessingJob(video_id=video.id, **job_fields)
    session.add(job)
    await session.commit()
    return job


async def _claim(worker: str = "w1") -> ClaimedJob | None:
    async with get_sessionmaker()() as session:
        return await jobs.claim_next(session, worker)


async def _expire_lease(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(locked_until=func.now() - timedelta(minutes=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def _make_due(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(run_after=func.now() - timedelta(minutes=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def _db_now(session: AsyncSession) -> datetime:
    """The current time, unlike now(), which is fixed when the transaction starts."""
    now = await session.scalar(select(func.clock_timestamp()))
    assert now is not None
    return now


async def _job(session: AsyncSession, job_id: int) -> ProcessingJob:
    job = await session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .execution_options(populate_existing=True)
    )
    assert job is not None
    return job


async def _video(session: AsyncSession, video_id: uuid.UUID) -> Video:
    video = await session.scalar(
        select(Video).where(Video.id == video_id).execution_options(populate_existing=True)
    )
    assert video is not None
    return video


async def test_claim_marks_the_job_running(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    claim = await _claim("w1")
    assert claim == ClaimedJob(id=queued.id, video_id=queued.video_id, attempt=1)

    job = await _job(session, queued.id)
    assert job.status is JobStatus.running
    assert job.locked_by == "w1"
    assert job.locked_until is not None


async def test_claim_on_an_empty_queue(session: AsyncSession) -> None:
    assert await _claim() is None


async def test_concurrent_claims_never_share_a_job(session: AsyncSession) -> None:
    """D18."""
    queued = [await _enqueue(session) for _ in range(3)]
    claims = await asyncio.gather(*(_claim(f"w{i}") for i in range(10)))
    won = [claim.id for claim in claims if claim is not None]
    assert len(won) == len(set(won))
    assert set(won) <= {job.id for job in queued}


async def test_concurrent_claims_on_one_job_have_one_winner(session: AsyncSession) -> None:
    """D18."""
    await _enqueue(session)
    claims = await asyncio.gather(*(_claim(f"w{i}") for i in range(10)))
    assert len([claim for claim in claims if claim is not None]) == 1


async def test_a_locked_row_is_skipped_without_waiting(session: AsyncSession) -> None:
    locked = await _enqueue(session)
    other = await _enqueue(session)
    await session.execute(
        select(ProcessingJob).where(ProcessingJob.id == locked.id).with_for_update()
    )

    claim = await asyncio.wait_for(_claim(), timeout=5)

    assert claim is not None
    assert claim.id == other.id
    await session.rollback()


async def test_a_job_that_is_not_due_is_not_claimed(session: AsyncSession) -> None:
    job = await _enqueue(session)
    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job.id)
        .values(run_after=func.now() + timedelta(hours=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    assert await _claim() is None


async def test_a_live_lease_is_not_taken(session: AsyncSession) -> None:
    await _enqueue(session)
    assert await _claim("w1") is not None
    assert await _claim("w2") is None


async def test_an_expired_lease_is_reclaimed_with_a_new_attempt(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    assert await _claim("w1") is not None
    await _expire_lease(session, queued.id)

    claim = await _claim("w2")

    assert claim is not None
    assert claim.attempt == 2
    assert (await _job(session, queued.id)).locked_by == "w2"


async def test_heartbeat_extends_the_lease(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    claim = await _claim()
    assert claim is not None
    await _expire_lease(session, queued.id)

    async with get_sessionmaker()() as other:
        assert await jobs.heartbeat(other, claim) is True

    locked_until = (await _job(session, queued.id)).locked_until
    assert locked_until is not None
    assert locked_until > await _db_now(session)


async def test_complete_makes_the_video_ready(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    claim = await _claim()
    assert claim is not None

    async with get_sessionmaker()() as other:
        assert await jobs.complete(other, claim, MEDIA) is True

    job = await _job(session, queued.id)
    assert job.status is JobStatus.done
    assert job.finished_at is not None
    assert job.locked_until is None
    video = await _video(session, queued.video_id)
    assert video.status is VideoStatus.ready
    assert (video.hls_prefix, video.thumbnail_key, video.duration_seconds) == (
        MEDIA.hls_prefix,
        MEDIA.thumbnail_key,
        MEDIA.duration_seconds,
    )
    assert video.published_at is not None


async def test_stale_worker_changes_nothing(session: AsyncSession) -> None:
    """D20."""
    queued = await _enqueue(session)
    stale = await _claim("old")
    assert stale is not None
    await _expire_lease(session, queued.id)
    current = await _claim("new")
    assert current is not None
    before = await _job(session, queued.id)
    locked_until = before.locked_until

    async with get_sessionmaker()() as other:
        assert await jobs.heartbeat(other, stale) is False
        assert await jobs.complete(other, stale, MEDIA) is False
        assert await jobs.fail(other, stale, RuntimeError("late")) is False

    job = await _job(session, queued.id)
    assert (job.status, job.attempts, job.locked_by) == (JobStatus.running, 2, "new")
    assert job.locked_until == locked_until
    assert job.last_error is None
    assert (await _video(session, queued.video_id)).status is VideoStatus.processing

    async with get_sessionmaker()() as other:
        assert await jobs.complete(other, current, MEDIA) is True
    assert (await _video(session, queued.video_id)).status is VideoStatus.ready


async def test_failure_requeues_with_backoff(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    claim = await _claim()
    assert claim is not None

    async with get_sessionmaker()() as other:
        assert await jobs.fail(other, claim, RuntimeError("boom")) is True

    job = await _job(session, queued.id)
    assert (job.status, job.locked_by, job.locked_until) == (JobStatus.queued, None, None)
    assert "boom" in (job.last_error or "")
    assert job.run_after > await _db_now(session) + timedelta(seconds=20)
    assert (await _video(session, queued.video_id)).status is VideoStatus.processing
    assert await _claim() is None


async def test_backoff_doubles_each_attempt(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    for _ in range(2):
        claim = await _claim()
        assert claim is not None
        async with get_sessionmaker()() as other:
            await jobs.fail(other, claim, RuntimeError("boom"))
        if claim.attempt == 1:
            await _make_due(session, queued.id)

    job = await _job(session, queued.id)
    assert job.run_after > await _db_now(session) + timedelta(seconds=50)


async def _fail_every_attempt(session: AsyncSession, job_id: int, error: Exception) -> None:
    for _ in range(3):
        claim = await _claim()
        assert claim is not None
        async with get_sessionmaker()() as other:
            assert await jobs.fail(other, claim, error) is True
        await _make_due(session, job_id)


async def test_last_failure_is_final_and_keeps_a_readable_reason(session: AsyncSession) -> None:
    """D21."""
    queued = await _enqueue(session)
    await _fail_every_attempt(session, queued.id, JobError("Not a video file"))

    job = await _job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.failed, 3)
    assert job.finished_at is not None
    video = await _video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (VideoStatus.failed, "Not a video file")
    assert await _claim() is None


async def test_unexpected_error_text_stays_internal(session: AsyncSession) -> None:
    queued = await _enqueue(session)
    await _fail_every_attempt(session, queued.id, RuntimeError("/srv/secret/path"))

    job = await _job(session, queued.id)
    assert "/srv/secret/path" in (job.last_error or "")
    video = await _video(session, queued.video_id)
    assert video.failure_reason == jobs.GENERIC_FAILURE


async def test_worker_dying_on_the_last_attempt_ends_the_job(session: AsyncSession) -> None:
    """D21: a file that kills the worker must not be retried forever."""
    queued = await _enqueue(session)
    other = await _enqueue(session)
    for attempt in range(3):
        claim = await _claim()
        assert claim is not None
        assert claim.id == queued.id
        assert claim.attempt == attempt + 1
        await _expire_lease(session, queued.id)

    claim = await _claim()

    assert claim is not None
    assert claim.id == other.id  # The exhausted job is closed and the next one is handed out.
    job = await _job(session, queued.id)
    assert (job.status, job.attempts) == (JobStatus.failed, 3)
    video = await _video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (VideoStatus.failed, jobs.CRASH_FAILURE)


@pytest.mark.parametrize("final", [VideoStatus.ready, VideoStatus.failed])
async def test_a_final_video_status_is_not_overwritten(
    session: AsyncSession, final: VideoStatus
) -> None:
    queued = await _enqueue(session)
    claim = await _claim()
    assert claim is not None
    video = await _video(session, queued.video_id)
    video.status = final
    if final is VideoStatus.ready:
        video.hls_prefix = "hls/old"
        video.thumbnail_key = "thumbs/old.jpg"
        video.duration_seconds = 1
        video.published_at = func.now()
    await session.commit()

    async with get_sessionmaker()() as other:
        await jobs.complete(other, claim, MEDIA)

    video = await _video(session, queued.video_id)
    assert video.status is final
    assert video.hls_prefix == ("hls/old" if final is VideoStatus.ready else None)
