import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Row, Select, delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound
from app.core.pagination import decode_cursor, encode_cursor
from app.core.permissions import (
    can_show_thumbnail,
    ensure_can_engage,
    ensure_can_view,
    ensure_video_owner,
    listed_videos,
)
from app.models import (
    ProcessingJob,
    ReactionType,
    User,
    Video,
    VideoAccess,
    VideoReaction,
    VideoStatus,
    VideoVisibility,
)
from app.schemas.videos import VideoCreateIn, VideoUpdateIn
from app.services import playback, storage
from app.services.storage import PresignedUpload

MAX_ACTIVE_UPLOADS = 3


@dataclass(frozen=True)
class VideoDetails:
    id: uuid.UUID
    title: str
    description: str
    visibility: VideoVisibility
    status: VideoStatus
    duration_seconds: int | None
    published_at: datetime | None
    created_at: datetime
    channel: User
    views_count: int
    likes_count: int
    dislikes_count: int
    comments_count: int
    thumbnail_url: str | None
    my_reaction: ReactionType | None


@dataclass(frozen=True)
class VideoCard:
    id: uuid.UUID
    title: str
    duration_seconds: int
    views_count: int
    published_at: datetime
    thumbnail_url: str
    channel: User


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


async def get_video(
    session: AsyncSession, user: User | None, video_id: uuid.UUID
) -> VideoDetails:
    video = await session.get(Video, video_id, options=[joinedload(Video.owner, innerjoin=True)])
    if video is None:
        raise NotFound("Video not found")
    await ensure_can_view(session, user, video)
    reaction = await session.get(VideoReaction, (user.id, video.id)) if user else None
    return VideoDetails(
        id=video.id,
        title=video.title,
        description=video.description,
        visibility=video.visibility,
        status=video.status,
        duration_seconds=video.duration_seconds,
        published_at=video.published_at,
        created_at=video.created_at,
        channel=video.owner,
        views_count=video.views_count,
        likes_count=video.likes_count,
        dislikes_count=video.dislikes_count,
        comments_count=video.comments_count,
        thumbnail_url=playback.thumbnail_url(video.id) if can_show_thumbnail(video) else None,
        my_reaction=reaction.reaction if reaction else None,
    )


async def get_engageable_for_update(
    session: AsyncSession, user: User, video_id: uuid.UUID
) -> Video:
    """A video the user may like or comment on, row locked. Counter updates need that lock
    anyway, and holding it from the start means the check can't race a moderator's hide."""
    video = await session.scalar(
        select(Video).where(Video.id == video_id).with_for_update(key_share=True)
    )
    if video is None:
        raise NotFound("Video not found")
    await ensure_can_engage(session, user, video)
    return video


async def adjust_counters(session: AsyncSession, video_id: uuid.UUID, **deltas: int) -> None:
    """Atomically changes denormalized counters, in the caller's transaction. Keeps
    `updated_at` as it is: a like isn't an edit of the video."""
    values = {name: getattr(Video, name) + delta for name, delta in deltas.items()}
    await session.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(updated_at=Video.updated_at, **values)
        .execution_options(synchronize_session=False)
    )


async def _listed_page(
    session: AsyncSession, *criteria: ColumnElement[bool], cursor: str | None, limit: int
) -> tuple[list[VideoCard], str | None]:
    """Listed videos matching `criteria`, newest first, with keyset pagination."""
    query = (
        select(Video)
        .options(joinedload(Video.owner, innerjoin=True))
        .where(listed_videos(), *criteria)
        .order_by(Video.published_at.desc(), Video.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(tuple_(Video.published_at, Video.id) < decode_cursor(cursor))
    videos = list(await session.scalars(query))
    next_cursor = None
    if len(videos) > limit:
        videos = videos[:limit]
        next_cursor = encode_cursor(videos[-1].published_at, videos[-1].id)
    cards = [
        VideoCard(
            id=video.id,
            title=video.title,
            duration_seconds=video.duration_seconds,
            views_count=video.views_count,
            published_at=video.published_at,
            thumbnail_url=playback.thumbnail_url(video.id),
            channel=video.owner,
        )
        for video in videos
    ]
    return cards, next_cursor


async def list_feed(
    session: AsyncSession, *, cursor: str | None, limit: int
) -> tuple[list[VideoCard], str | None]:
    return await _listed_page(session, cursor=cursor, limit=limit)


async def search_videos(
    session: AsyncSession, *, q: str, cursor: str | None, limit: int
) -> tuple[list[VideoCard], str | None]:
    """Listed videos with `q` anywhere in the title, ignoring case. `%` and `_` are literal."""
    return await _listed_page(
        session, Video.title.icontains(q, autoescape=True), cursor=cursor, limit=limit
    )


async def update_video(
    session: AsyncSession, user: User, video_id: uuid.UUID, data: VideoUpdateIn
) -> Video:
    video = await _get_owned_for_update(session, user, video_id)
    if data.title is not None:
        video.title = data.title
    if data.description is not None:
        video.description = data.description
    if data.visibility is not None:
        video.visibility = data.visibility
    await session.commit()
    await session.refresh(video)
    return video


def _access_entries(video_id: uuid.UUID) -> Select:
    return (
        select(User.username, User.display_name, VideoAccess.created_at.label("granted_at"))
        .join(VideoAccess, VideoAccess.user_id == User.id)
        .where(VideoAccess.video_id == video_id)
    )


async def list_access(
    session: AsyncSession, user: User, video_id: uuid.UUID, *, cursor: str | None, limit: int
) -> tuple[list[Row], str | None]:
    """The allowlist ordered by username, with keyset pagination on it."""
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found")
    ensure_video_owner(user, video)

    query = _access_entries(video_id).order_by(User.username).limit(limit + 1)
    if cursor:
        query = query.where(User.username > cursor)
    rows = list(await session.execute(query))
    if len(rows) > limit:
        return rows[:limit], rows[limit - 1].username
    return rows, None


async def grant_access(
    session: AsyncSession, user: User, video_id: uuid.UUID, username: str
) -> Row:
    """Safe to repeat. Allowed at any visibility, so a list can be ready before going private."""
    video = await _get_owned_for_update(session, user, video_id)
    target_id = await session.scalar(select(User.id).where(User.username == username))
    if target_id is None:
        raise NotFound("User not found")
    if target_id == video.owner_id:
        raise Conflict("You already have access to your own video")

    await session.execute(
        insert(VideoAccess).values(video_id=video_id, user_id=target_id).on_conflict_do_nothing()
    )
    # Read before committing: the row is a plain result, and can't be revoked in between.
    entry = (await session.execute(_access_entries(video_id).where(User.id == target_id))).one()
    await session.commit()
    return entry


async def revoke_access(
    session: AsyncSession, user: User, video_id: uuid.UUID, username: str
) -> None:
    """Safe to repeat, and says nothing about whether the username exists."""
    await _get_owned_for_update(session, user, video_id)
    await session.execute(
        delete(VideoAccess)
        .where(
            VideoAccess.video_id == video_id,
            VideoAccess.user_id.in_(select(User.id).where(User.username == username)),
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
