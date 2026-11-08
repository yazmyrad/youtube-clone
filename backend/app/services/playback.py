import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.permissions import ensure_can_play
from app.models import User, Video, VideoStatus


@dataclass(frozen=True)
class PlaybackGrant:
    url: str
    expires_at: datetime


async def issue_playback(
    session: AsyncSession, user: User | None, video_id: uuid.UUID
) -> PlaybackGrant:
    """The only place a playback URL comes from, and so where viewing rights are enforced."""
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found")
    ensure_can_play(user, video)
    if video.status != VideoStatus.ready:
        raise Conflict("The video isn't ready yet")

    exp = int(time.time() + get_settings().playback_ttl.total_seconds())
    sig = security.sign_media(security.MEDIA_SCOPE_HLS, video.id, exp)
    return PlaybackGrant(
        url=f"/hls/{exp}.{sig}/{video.id}/master.m3u8",
        expires_at=datetime.fromtimestamp(exp, UTC),
    )


def thumbnail_url(video_id: uuid.UUID) -> str:
    """A signed thumbnail URL. Callers include it only for users who may see the video.

    Expires at the next hour boundary plus one hour, so the URL stays the same for an hour
    and browsers can cache the image.
    """
    exp = (int(time.time()) // 3600 + 2) * 3600
    sig = security.sign_media(security.MEDIA_SCOPE_THUMB, video_id, exp)
    return f"/thumbs/{exp}.{sig}/{video_id}.jpg"


def authorize_media(scope: str, video_id: str, exp: str, sig: str) -> None:
    """Checks one media request. The permission check already happened when the URL was
    issued, so this is only the signature and expiry, with no database lookup per segment."""
    if not security.verify_media(scope, video_id, exp, sig):
        raise Forbidden("Invalid or expired playback token")
