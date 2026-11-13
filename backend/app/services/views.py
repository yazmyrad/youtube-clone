"""View counting (D52) and watch history."""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.client import ClientInfo
from app.core.errors import NotFound
from app.core.permissions import ensure_can_engage
from app.models import User, Video, VideoView, WatchHistory
from app.services.videos import adjust_counters

# A view counts once this much has been watched, or half of a shorter video.
VIEW_AFTER_SECONDS = 30


@dataclass(frozen=True)
class ViewResult:
    counted: bool
    views_count: int


def seconds_to_count(duration_seconds: int) -> int:
    return max(1, min(VIEW_AFTER_SECONDS, math.ceil(duration_seconds / 2)))


async def record_view(
    session: AsyncSession,
    viewer: User | None,
    video_id: uuid.UUID,
    client: ClientInfo,
    *,
    watched_seconds: int,
    position_seconds: int,
) -> ViewResult:
    """A heartbeat from the player. Counts a view once enough has been watched, at most once
    per viewer, video and day, and keeps a signed-in viewer's place in their history."""
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found")
    await ensure_can_engage(session, viewer, video)
    duration = video.duration_seconds or 0

    counted = False
    # As on YouTube, a channel watching its own video adds no view.
    own = viewer is not None and viewer.id == video.owner_id
    if not own and min(watched_seconds, duration) >= seconds_to_count(duration):
        key = security.viewer_key(viewer.id if viewer else None, client.ip, client.user_agent)
        inserted = await session.scalar(
            insert(VideoView)
            .values(video_id=video.id, viewer_key=key, day=datetime.now(UTC).date())
            .on_conflict_do_nothing()
            .returning(VideoView.video_id)
        )
        if inserted is not None:
            await adjust_counters(session, video.id, views_count=1)
            counted = True

    if viewer is not None:
        progress = min(position_seconds, duration)
        await session.execute(
            insert(WatchHistory)
            .values(user_id=viewer.id, video_id=video.id, progress_seconds=progress)
            .on_conflict_do_update(
                index_elements=[WatchHistory.user_id, WatchHistory.video_id],
                set_={"progress_seconds": progress, "last_watched_at": func.now()},
            )
        )
    await session.commit()
    views = await session.scalar(select(Video.views_count).where(Video.id == video.id))
    return ViewResult(counted=counted, views_count=views or 0)
