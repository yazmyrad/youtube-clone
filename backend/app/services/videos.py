import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound
from app.core.permissions import ensure_video_owner
from app.models import ProcessingJob, User, Video, VideoStatus
from app.schemas.videos import VideoCreateIn
from app.services import storage
from app.services.storage import PresignedUpload

MAX_ACTIVE_UPLOADS = 3


async def create_video(
    session: AsyncSession, owner: User, data: VideoCreateIn
) -> tuple[Video, PresignedUpload]:
    # Serializes one user's requests, so concurrent ones can't all pass the count below.
    # NO KEY UPDATE, the weaker lock, doesn't block inserts that reference this user.
    await session.execute(
        select(User.id).where(User.id == owner.id).with_for_update(key_share=True)
    )
    active = await session.scalar(
        select(func.count())
        .select_from(Video)
        .where(
            Video.owner_id == owner.id,
            Video.status == VideoStatus.uploading,
            Video.deleted_at.is_(None),
        )
    )
    if active is not None and active >= MAX_ACTIVE_UPLOADS:
        raise Conflict(f"You can have at most {MAX_ACTIVE_UPLOADS} uploads in progress")

    video_id = uuid.uuid4()
    key = storage.raw_key(video_id)
    upload = storage.presign_upload(key)
    video = Video(
        id=video_id,
        owner_id=owner.id,
        title=data.title,
        description=data.description,
        visibility=data.visibility,
        raw_key=key,
    )
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return video, upload


async def _get_owned_for_update(session: AsyncSession, user: User, video_id: uuid.UUID) -> Video:
    video = await session.scalar(
        select(Video).where(Video.id == video_id).with_for_update(key_share=True)
    )
    if video is None:
        raise NotFound("Video not found")
    ensure_video_owner(user, video)
    return video


async def complete_upload(session: AsyncSession, user: User, video_id: uuid.UUID) -> Video:
    """Confirms the file reached storage and enqueues processing. Safe to repeat: the row
    lock makes concurrent calls take turns, and later ones find the status already moved."""
    video = await _get_owned_for_update(session, user, video_id)
    if video.status != VideoStatus.uploading:
        return video

    size = await storage.uploaded_size(storage.raw_key(video.id))
    if size is None:
        raise Conflict("The file hasn't been uploaded yet")
    if size > get_settings().max_upload_bytes:
        raise Conflict("The uploaded file is too large")

    video.status = VideoStatus.processing
    video.source_size_bytes = size
    session.add(ProcessingJob(video_id=video.id))
    await session.commit()
    await session.refresh(video)
    return video
