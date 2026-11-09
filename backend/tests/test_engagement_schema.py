import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReactionType, User, Video, VideoReaction


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


async def _react(session: AsyncSession, user: User, video: Video) -> None:
    session.add(VideoReaction(user_id=user.id, video_id=video.id, reaction=ReactionType.like))
    await session.commit()


async def test_one_reaction_per_user_and_video(
    session: AsyncSession, user: User, video: Video
) -> None:
    await _react(session, user, video)
    session.expunge_all()

    with pytest.raises(IntegrityError):
        await _react(session, user, video)
    await session.rollback()


async def test_reactions_go_with_the_video(
    session: AsyncSession, user: User, video: Video
) -> None:
    await _react(session, user, video)

    await session.execute(delete(Video).where(Video.id == video.id))
    await session.commit()

    assert await _count(session, VideoReaction) == 0


async def test_reactions_go_with_the_user(session: AsyncSession, user: User, video: Video) -> None:
    other = User(username="bobby", email="bobby@example.com", password_hash="x", display_name="B")
    session.add(other)
    await session.commit()
    await _react(session, other, video)

    await session.execute(delete(User).where(User.id == other.id))
    await session.commit()

    assert await _count(session, VideoReaction) == 0
