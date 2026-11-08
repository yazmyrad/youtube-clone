"""The processing queue: a Postgres table claimed with FOR UPDATE SKIP LOCKED.

A claim is a lease. `attempts` doubles as the fencing value: every write below is conditional
on the claim's attempt, so a worker that lost its lease changes nothing. Times come from the
database clock, so workers can't disagree about when a lease expires.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import JobStatus, ProcessingJob, Video, VideoStatus

GENERIC_FAILURE = "Processing failed"
CRASH_FAILURE = "Processing kept stopping unexpectedly"
MAX_ERROR_LENGTH = 2000


class JobError(Exception):
    """A processing failure whose message is safe to show to the video's owner."""


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    video_id: uuid.UUID
    attempt: int


@dataclass(frozen=True)
class MediaResult:
    hls_prefix: str
    thumbnail_key: str
    duration_seconds: int


def _fence(claim: ClaimedJob) -> tuple[ColumnElement[bool], ...]:
    return (
        ProcessingJob.id == claim.id,
        ProcessingJob.status == JobStatus.running,
        ProcessingJob.attempts == claim.attempt,
    )


async def _update_video(session: AsyncSession, video_id: uuid.UUID, **values: Any) -> None:
    """Only a video still in `processing` moves, so a final status is never overwritten."""
    await session.execute(
        update(Video)
        .where(Video.id == video_id, Video.status == VideoStatus.processing)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def _fail_permanently(
    session: AsyncSession, job: ProcessingJob, reason: str, detail: str
) -> None:
    job.status = JobStatus.failed
    job.locked_by = None
    job.locked_until = None
    job.last_error = detail
    job.finished_at = func.now()
    await _update_video(session, job.video_id, status=VideoStatus.failed, failure_reason=reason)


async def source_key(session: AsyncSession, video_id: uuid.UUID) -> str | None:
    """Where the job's uploaded file is. None if it's gone."""
    return await session.scalar(select(Video.raw_key).where(Video.id == video_id))


async def claim_next(session: AsyncSession, worker_id: str) -> ClaimedJob | None:
    """Takes the oldest job that is due, or whose worker stopped renewing its lease."""
    settings = get_settings()
    claimable = or_(
        and_(ProcessingJob.status == JobStatus.queued, ProcessingJob.run_after <= func.now()),
        and_(ProcessingJob.status == JobStatus.running, ProcessingJob.locked_until < func.now()),
    )
    while True:
        job = await session.scalar(
            select(ProcessingJob)
            .where(claimable)
            .order_by(ProcessingJob.run_after, ProcessingJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if job is None:
            await session.rollback()
            return None

        if job.attempts >= job.max_attempts:
            # The worker died on the last attempt. Running it again would let a file
            # that crashes the worker loop forever.
            await _fail_permanently(
                session, job, CRASH_FAILURE, job.last_error or "Lease expired on the last attempt"
            )
            await session.commit()
            continue

        job.status = JobStatus.running
        job.attempts += 1
        job.locked_by = worker_id
        job.locked_until = func.now() + settings.job_lease
        claim = ClaimedJob(id=job.id, video_id=job.video_id, attempt=job.attempts)
        await session.commit()
        return claim


async def heartbeat(session: AsyncSession, claim: ClaimedJob) -> bool:
    """Extends the lease. False means it was lost and the work should stop."""
    result = await session.execute(
        update(ProcessingJob)
        .where(*_fence(claim))
        .values(locked_until=func.now() + get_settings().job_lease)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount == 1


async def release(session: AsyncSession, claim: ClaimedJob) -> bool:
    """Hands the job back on a clean shutdown, without using up an attempt.

    Raises the budget rather than lowering `attempts`, which has to stay unique as the fence.
    False means the lease was already lost.
    """
    result = await session.execute(
        update(ProcessingJob)
        .where(*_fence(claim))
        .values(
            status=JobStatus.queued,
            max_attempts=ProcessingJob.max_attempts + 1,
            run_after=func.now(),
            locked_by=None,
            locked_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount == 1


async def complete(session: AsyncSession, claim: ClaimedJob, media: MediaResult) -> bool:
    """Marks the job done and the video ready together. False means the lease was lost."""
    result = await session.execute(
        update(ProcessingJob)
        .where(*_fence(claim))
        .values(
            status=JobStatus.done,
            locked_by=None,
            locked_until=None,
            last_error=None,
            finished_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        return False
    await _update_video(
        session,
        claim.video_id,
        status=VideoStatus.ready,
        hls_prefix=media.hls_prefix,
        thumbnail_key=media.thumbnail_key,
        duration_seconds=media.duration_seconds,
        published_at=func.coalesce(Video.published_at, func.now()),
        failure_reason=None,
    )
    await session.commit()
    return True


async def fail(session: AsyncSession, claim: ClaimedJob, error: Exception) -> bool:
    """Schedules a retry with backoff, or gives up once attempts run out.

    False means the lease was lost. Only a JobError's text can reach the video's owner.
    """
    job = await session.scalar(
        select(ProcessingJob)
        .where(*_fence(claim))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        await session.rollback()
        return False

    detail = repr(error)[:MAX_ERROR_LENGTH]
    if claim.attempt >= job.max_attempts:
        reason = str(error) if isinstance(error, JobError) else GENERIC_FAILURE
        await _fail_permanently(session, job, reason, detail)
    else:
        job.status = JobStatus.queued
        job.locked_by = None
        job.locked_until = None
        job.last_error = detail
        job.run_after = func.now() + get_settings().job_retry_backoff * 2 ** (claim.attempt - 1)
    await session.commit()
    return True
