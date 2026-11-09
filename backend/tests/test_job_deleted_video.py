from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobStatus, ProcessingJob, Video
from app.services.jobs import VIDEO_DELETED
from tests.job_helpers import claim, enqueue, expire_lease, load_job


async def _delete_video(session: AsyncSession, job: ProcessingJob) -> None:
    await session.execute(
        update(Video).where(Video.id == job.video_id).values(deleted_at=datetime.now(UTC))
    )
    await session.commit()


async def test_a_deleted_videos_job_is_closed_not_claimed(session: AsyncSession) -> None:
    job = await enqueue(session)
    await _delete_video(session, job)

    assert await claim() is None

    closed = await load_job(session, job.id)
    assert closed.status == JobStatus.failed
    assert closed.last_error == VIDEO_DELETED
    assert closed.finished_at is not None
    assert (closed.locked_by, closed.locked_until) == (None, None)


async def test_the_next_job_is_claimed_instead(session: AsyncSession) -> None:
    gone = await enqueue(session)
    await _delete_video(session, gone)
    live = await enqueue(session)

    claimed = await claim()

    assert claimed is not None
    assert claimed.id == live.id


async def test_a_dead_workers_job_is_closed_if_the_video_was_deleted(
    session: AsyncSession,
) -> None:
    job = await enqueue(session)
    assert await claim() is not None
    await _delete_video(session, job)
    await expire_lease(session, job.id)

    assert await claim() is None

    assert (await load_job(session, job.id)).status == JobStatus.failed
