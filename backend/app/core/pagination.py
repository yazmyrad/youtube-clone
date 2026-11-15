"""Keyset pagination, newest first: the cursor is the last item's (timestamp, id) sort key."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Query

from app.core.errors import BadRequest

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# At most 16 digits is always a valid datetime (up to the year 2286), so decoding can't fail.
# A "p" marks a cursor of a list sorted by a count, so it can't be mistaken for a time.
_CURSOR_PATTERN = r"^p?\d{1,16}_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

KeysetCursor = Annotated[str | None, Query(pattern=_CURSOR_PATTERN)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
DEFAULT_VIDEO_PAGE = 24
DEFAULT_COMMENT_PAGE = 20
DEFAULT_SUBSCRIPTION_PAGE = 50


def encode_cursor(timestamp: datetime, item_id: uuid.UUID) -> str:
    """Whole microseconds, so the timestamp survives the round trip exactly."""
    return f"{(timestamp - _EPOCH) // _MICROSECOND}_{item_id}"


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """`cursor` has already passed `KeysetCursor`'s pattern."""
    if is_count_cursor(cursor):
        raise BadRequest("This cursor belongs to a list in another order")
    microseconds, item_id = cursor.split("_")
    return _EPOCH + int(microseconds) * _MICROSECOND, uuid.UUID(item_id)


def is_count_cursor(cursor: str) -> bool:
    return cursor.startswith("p")


def encode_count_cursor(count: int, item_id: uuid.UUID) -> str:
    """For lists sorted by a count, such as the most viewed."""
    return f"p{count}_{item_id}"


def decode_count_cursor(cursor: str) -> tuple[int, uuid.UUID]:
    count, item_id = cursor.removeprefix("p").split("_")
    return int(count), uuid.UUID(item_id)
