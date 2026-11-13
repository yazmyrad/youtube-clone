from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Video, VideoView, WatchHistory


@pytest.fixture
async def user(session: AsyncSession) -> User:
    user = User(username="alice", email="alice@example.com", password_hash="x", display_name="A")
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
async def video(session: AsyncSession, user: User) -> Video:
    video = Video(owner_id=user.id, title="Clip")
    session.add(video)
    await session.commit()
    return video


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_one_history_row_per_user_and_video(
    session: AsyncSession, user: User, video: Video
) -> None:
    session.add(WatchHistory(user_id=user.id, video_id=video.id))
    await session.commit()
    session.expunge_all()

    session.add(WatchHistory(user_id=user.id, video_id=video.id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_progress_cant_be_negative(session: AsyncSession, user: User, video: Video) -> None:
    session.add(WatchHistory(user_id=user.id, video_id=video.id, progress_seconds=-1))

    with pytest.raises(IntegrityError, match="ck_watch_history_progress_non_negative"):
        await session.commit()
    await session.rollback()


async def test_one_view_per_viewer_video_and_day(session: AsyncSession, video: Video) -> None:
    """D52, in the schema."""
    session.add(VideoView(video_id=video.id, viewer_key=b"k", day=date(2026, 1, 1)))
    await session.commit()
    session.add(VideoView(video_id=video.id, viewer_key=b"k", day=date(2026, 1, 2)))
    session.add(VideoView(video_id=video.id, viewer_key=b"other", day=date(2026, 1, 1)))
    await session.commit()
    session.expunge_all()

    session.add(VideoView(video_id=video.id, viewer_key=b"k", day=date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_rows_go_with_their_video(session: AsyncSession, user: User, video: Video) -> None:
    session.add(WatchHistory(user_id=user.id, video_id=video.id))
    session.add(VideoView(video_id=video.id, viewer_key=b"k", day=date(2026, 1, 1)))
    await session.commit()

    await session.execute(delete(Video).where(Video.id == video.id))
    await session.commit()

    assert await _count(session, WatchHistory) == await _count(session, VideoView) == 0


async def test_history_goes_with_its_user(session: AsyncSession, user: User) -> None:
    other = User(username="bob", email="bob@example.com", password_hash="x", display_name="B")
    session.add(other)
    await session.commit()
    video = Video(owner_id=other.id, title="Clip")
    session.add(video)
    await session.commit()
    session.add(WatchHistory(user_id=user.id, video_id=video.id))
    await session.commit()

    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()

    assert await _count(session, WatchHistory) == 0
