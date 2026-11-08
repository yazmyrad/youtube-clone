from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Video, VideoStatus, VideoVisibility


@pytest.fixture
async def owner(session: AsyncSession) -> User:
    user = User(username="alice", email="alice@example.com", password_hash="x", display_name="A")
    session.add(user)
    await session.commit()
    return user


def _video(owner: User, **fields: Any) -> Video:
    return Video(owner_id=owner.id, **{"title": "Clip", **fields})


READY_MEDIA = {
    "hls_prefix": "hls/x",
    "thumbnail_key": "thumbs/x.jpg",
    "duration_seconds": 10,
    "published_at": datetime(2026, 1, 1, tzinfo=UTC),
}


async def test_defaults(session: AsyncSession, owner: User) -> None:
    video = _video(owner)
    session.add(video)
    await session.commit()
    await session.refresh(video)
    assert video.visibility is VideoVisibility.private
    assert video.status is VideoStatus.uploading
    assert video.description == ""
    counters = (video.views_count, video.likes_count, video.dislikes_count, video.comments_count)
    assert counters == (0, 0, 0, 0)


@pytest.mark.parametrize("title", ["", "   "])
async def test_blank_title_is_rejected(session: AsyncSession, owner: User, title: str) -> None:
    session.add(_video(owner, title=title))
    with pytest.raises(IntegrityError, match="ck_videos_title_not_blank"):
        await session.commit()


@pytest.mark.parametrize("missing", sorted(READY_MEDIA))
async def test_ready_requires_media(session: AsyncSession, owner: User, missing: str) -> None:
    media = {k: v for k, v in READY_MEDIA.items() if k != missing}
    session.add(_video(owner, status=VideoStatus.ready, **media))
    with pytest.raises(IntegrityError, match="ck_videos_ready_has_media"):
        await session.commit()


@pytest.mark.parametrize("status", [VideoStatus.processing, VideoStatus.failed])
async def test_not_ready_may_lack_media(
    session: AsyncSession, owner: User, status: VideoStatus
) -> None:
    session.add(_video(owner, status=status))
    await session.commit()


async def test_ready_with_media_is_accepted(session: AsyncSession, owner: User) -> None:
    session.add(_video(owner, status=VideoStatus.ready, **READY_MEDIA))
    await session.commit()


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("views_count", -1, "views_count_non_negative"),
        ("likes_count", -1, "likes_count_non_negative"),
        ("dislikes_count", -1, "dislikes_count_non_negative"),
        ("comments_count", -1, "comments_count_non_negative"),
        ("source_size_bytes", -1, "source_size_non_negative"),
        ("duration_seconds", 0, "duration_positive"),
    ],
)
async def test_invalid_numbers_are_rejected(
    session: AsyncSession, owner: User, field: str, value: int, constraint: str
) -> None:
    session.add(_video(owner, **{field: value}))
    with pytest.raises(IntegrityError, match=f"ck_videos_{constraint}"):
        await session.commit()


async def test_owner_with_videos_cannot_be_deleted(session: AsyncSession, owner: User) -> None:
    session.add(_video(owner))
    await session.commit()
    with pytest.raises(IntegrityError, match="fk_videos_owner_id_users"):
        await session.execute(delete(User).where(User.id == owner.id))
