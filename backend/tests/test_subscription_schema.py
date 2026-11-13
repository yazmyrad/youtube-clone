import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, User


async def _user(session: AsyncSession, name: str) -> User:
    user = User(username=name, email=f"{name}@example.com", password_hash="x", display_name=name)
    session.add(user)
    await session.commit()
    return user


async def _subscribe(session: AsyncSession, subscriber: User, channel: User) -> None:
    session.add(Subscription(subscriber_id=subscriber.id, channel_id=channel.id))
    await session.commit()


async def _count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Subscription)) or 0


async def test_one_subscription_per_user_and_channel(session: AsyncSession) -> None:
    alice, bob = await _user(session, "alice"), await _user(session, "bob")
    await _subscribe(session, alice, bob)
    session.expunge_all()

    with pytest.raises(IntegrityError):
        await _subscribe(session, alice, bob)
    await session.rollback()


async def test_nobody_subscribes_to_themselves(session: AsyncSession) -> None:
    alice = await _user(session, "alice")

    with pytest.raises(IntegrityError, match="ck_subscriptions_not_self"):
        await _subscribe(session, alice, alice)
    await session.rollback()


@pytest.mark.parametrize("deleted", ["subscriber", "channel"])
async def test_subscriptions_go_with_either_user(session: AsyncSession, deleted: str) -> None:
    alice, bob = await _user(session, "alice"), await _user(session, "bob")
    await _subscribe(session, alice, bob)
    gone = alice if deleted == "subscriber" else bob

    await session.execute(delete(User).where(User.id == gone.id))
    await session.commit()

    assert await _count(session) == 0
