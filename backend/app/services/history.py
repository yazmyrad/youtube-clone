"""A user's watch history. Only theirs, and only what they may still watch."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.pagination import decode_cursor, encode_cursor
from app.core.permissions import playable_videos
from app.models import User, Video, WatchHistory
from app.services.videos import VideoCard, to_card


@dataclass(frozen=True)
class HistoryEntry:
    video: VideoCard
    progress_seconds: int
    watched_at: datetime


async def list_history(
    session: AsyncSession, user: User, *, cursor: str | None, limit: int
) -> tuple[list[HistoryEntry], str | None]:
    """Most recently watched first. A video since made private, hidden or deleted drops out,
    and returns if it becomes watchable again."""
    query = (
        select(Video, WatchHistory.progress_seconds, WatchHistory.last_watched_at)
        .join(WatchHistory, WatchHistory.video_id == Video.id)
        .options(joinedload(Video.owner, innerjoin=True))
        .where(WatchHistory.user_id == user.id, playable_videos(user))
        .order_by(WatchHistory.last_watched_at.desc(), WatchHistory.video_id.desc())
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(
            tuple_(WatchHistory.last_watched_at, WatchHistory.video_id) < decode_cursor(cursor)
        )
    rows = (await session.execute(query)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.last_watched_at, last.Video.id)
    return [
        HistoryEntry(to_card(row.Video), row.progress_seconds, row.last_watched_at) for row in rows
    ], next_cursor


async def remove_entry(session: AsyncSession, user: User, video_id: uuid.UUID) -> None:
    """Safe to repeat."""
    await session.execute(
        delete(WatchHistory).where(
            WatchHistory.user_id == user.id, WatchHistory.video_id == video_id
        )
    )
    await session.commit()


async def clear(session: AsyncSession, user: User) -> None:
    await session.execute(delete(WatchHistory).where(WatchHistory.user_id == user.id))
    await session.commit()
