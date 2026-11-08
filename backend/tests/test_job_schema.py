import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobStatus, ProcessingJob, User, Video


@pytest.fixture
async def video(session: AsyncSession) -> Video:
    user = User(username="alice", email="alice@example.com", password_hash="x", display_name="A")
    session.add(user)
    await session.flush()
    clip = Video(owner_id=user.id, title="Clip")
    session.add(clip)
    await session.commit()
    return clip


async def test_defaults(session: AsyncSession, video: Video) -> None:
    job = ProcessingJob(video_id=video.id)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    assert job.status is JobStatus.queued
    assert (job.attempts, job.max_attempts) == (0, 3)
    assert job.run_after is not None
    assert job.locked_until is None


@pytest.mark.parametrize("active", [JobStatus.queued, JobStatus.running])
async def test_second_active_job_is_rejected(
    session: AsyncSession, video: Video, active: JobStatus
) -> None:
    session.add(ProcessingJob(video_id=video.id, status=active))
    await session.commit()
    session.add(ProcessingJob(video_id=video.id))
    with pytest.raises(IntegrityError, match="uq_processing_jobs_active_video"):
        await session.commit()


@pytest.mark.parametrize("finished", [JobStatus.done, JobStatus.failed])
async def test_finished_jobs_allow_a_new_one(
    session: AsyncSession, video: Video, finished: JobStatus
) -> None:
    session.add(ProcessingJob(video_id=video.id, status=finished))
    await session.commit()
    session.add(ProcessingJob(video_id=video.id))
    await session.commit()


async def test_jobs_are_deleted_with_their_video(session: AsyncSession, video: Video) -> None:
    session.add(ProcessingJob(video_id=video.id))
    await session.commit()
    await session.execute(delete(Video).where(Video.id == video.id))
    await session.commit()
    assert list(await session.scalars(select(ProcessingJob))) == []
