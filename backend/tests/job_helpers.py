import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.models import ProcessingJob, User, Video, VideoStatus
from app.services import jobs
from app.services.jobs import ClaimedJob, MediaResult

MEDIA = MediaResult(hls_prefix="hls/x", thumbnail_key="thumbs/x.jpg", duration_seconds=5)


async def make_video(session: AsyncSession, **fields: object) -> Video:
    name = f"user_{uuid.uuid4().hex[:12]}"
    user = User(username=name, email=f"{name}@example.com", password_hash="x", display_name="A")
    session.add(user)
    await session.flush()
    video = Video(owner_id=user.id, title="Clip", **fields)
    session.add(video)
    await session.commit()
    return video


async def enqueue(
    session: AsyncSession, raw_key: str | None = None, **job_fields: object
) -> ProcessingJob:
    video = await make_video(session, status=VideoStatus.processing, raw_key=raw_key)
    job = ProcessingJob(video_id=video.id, **job_fields)
    session.add(job)
    await session.commit()
    return job


async def claim(worker: str = "w1") -> ClaimedJob | None:
    async with get_sessionmaker()() as session:
        return await jobs.claim_next(session, worker)


async def expire_lease(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(locked_until=func.now() - timedelta(minutes=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def make_due(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(run_after=func.now() - timedelta(minutes=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def load_job(session: AsyncSession, job_id: int) -> ProcessingJob:
    job = await session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .execution_options(populate_existing=True)
    )
    assert job is not None
    return job


async def load_video(session: AsyncSession, video_id: uuid.UUID) -> Video:
    video = await session.scalar(
        select(Video).where(Video.id == video_id).execution_options(populate_existing=True)
    )
    assert video is not None
    return video
