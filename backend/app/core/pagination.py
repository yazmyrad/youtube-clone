"""Keyset pagination over videos, newest first: the cursor is the last item's sort key."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Query

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# At most 16 digits is always a valid datetime (up to the year 2286), so decoding can't fail.
_CURSOR_PATTERN = r"^\d{1,16}_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

VideoCursor = Annotated[str | None, Query(pattern=_CURSOR_PATTERN)]
VideoPageLimit = Annotated[int, Query(ge=1, le=100)]
DEFAULT_VIDEO_PAGE = 24


def encode_video_cursor(published_at: datetime, video_id: uuid.UUID) -> str:
    """Whole microseconds, so the timestamp survives the round trip exactly."""
    return f"{(published_at - _EPOCH) // _MICROSECOND}_{video_id}"


def decode_video_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """`cursor` has already passed `VideoCursor`'s pattern."""
    microseconds, video_id = cursor.split("_")
    return _EPOCH + int(microseconds) * _MICROSECOND, uuid.UUID(video_id)
