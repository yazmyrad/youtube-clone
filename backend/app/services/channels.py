"""Channels. A channel is a user, addressed by username."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.pagination import decode_cursor, encode_cursor
from app.core.permissions import ensure_can_subscribe
from app.models import Subscription, User
from app.services import videos
from app.services.videos import VideoCard


@dataclass(frozen=True)
class ChannelDetails:
    username: str
    display_name: str
    description: str
    subscribers_count: int
    created_at: datetime
    is_subscribed: bool


@dataclass(frozen=True)
class SubscriptionState:
    is_subscribed: bool
    subscribers_count: int


@dataclass(frozen=True)
class SubscribedChannel:
    username: str
    display_name: str
    subscribed_at: datetime


async def get_channel_user(session: AsyncSession, username: str) -> User:
    channel = await session.scalar(select(User).where(User.username == username))
    if channel is None:
        raise NotFound("Channel not found")
    return channel


async def get_channel(session: AsyncSession, viewer: User | None, username: str) -> ChannelDetails:
    channel = await get_channel_user(session, username)
    subscribed = viewer is not None and (
        await session.get(Subscription, (viewer.id, channel.id)) is not None
    )
    return ChannelDetails(
        username=channel.username,
        display_name=channel.display_name,
        description=channel.description,
        subscribers_count=channel.subscribers_count,
        created_at=channel.created_at,
        is_subscribed=subscribed,
    )


async def list_channel_videos(
    session: AsyncSession, viewer: User | None, username: str, *, cursor: str | None, limit: int
) -> tuple[list[VideoCard], str | None]:
    channel = await get_channel_user(session, username)
    return await videos.list_channel_videos(session, viewer, channel, cursor=cursor, limit=limit)


async def _adjust_subscribers(session: AsyncSession, channel_id: uuid.UUID, delta: int) -> int:
    """Atomic, in the caller's transaction. Keeps `updated_at`: a new subscriber isn't an
    edit of the profile."""
    count = await session.scalar(
        update(User)
        .where(User.id == channel_id)
        .values(subscribers_count=User.subscribers_count + delta, updated_at=User.updated_at)
        .returning(User.subscribers_count)
        .execution_options(synchronize_session=False)
    )
    return count or 0


async def _current_count(session: AsyncSession, channel_id: uuid.UUID) -> int:
    count = await session.scalar(select(User.subscribers_count).where(User.id == channel_id))
    return count or 0


async def subscribe(session: AsyncSession, user: User, username: str) -> SubscriptionState:
    """Safe to repeat, also concurrently: only the call that inserts the row counts it (D53)."""
    channel = await get_channel_user(session, username)
    ensure_can_subscribe(user, channel)
    inserted = await session.scalar(
        insert(Subscription)
        .values(subscriber_id=user.id, channel_id=channel.id)
        .on_conflict_do_nothing()
        .returning(Subscription.channel_id)
    )
    if inserted is not None:
        count = await _adjust_subscribers(session, channel.id, 1)
    else:
        count = await _current_count(session, channel.id)
    await session.commit()
    return SubscriptionState(is_subscribed=True, subscribers_count=count)


async def unsubscribe(session: AsyncSession, user: User, username: str) -> SubscriptionState:
    """Safe to repeat, also concurrently: only the call that deletes the row counts it."""
    channel = await get_channel_user(session, username)
    deleted = await session.scalar(
        delete(Subscription)
        .where(Subscription.subscriber_id == user.id, Subscription.channel_id == channel.id)
        .returning(Subscription.channel_id)
    )
    if deleted is not None:
        count = await _adjust_subscribers(session, channel.id, -1)
    else:
        count = await _current_count(session, channel.id)
    await session.commit()
    return SubscriptionState(is_subscribed=False, subscribers_count=count)


async def list_my_subscriptions(
    session: AsyncSession, user: User, *, cursor: str | None, limit: int
) -> tuple[list[SubscribedChannel], str | None]:
    """The channels `user` subscribes to, most recently subscribed first."""
    query = (
        select(User.username, User.display_name, User.id, Subscription.created_at)
        .join(Subscription, Subscription.channel_id == User.id)
        .where(Subscription.subscriber_id == user.id)
        .order_by(Subscription.created_at.desc(), User.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        query = query.where(tuple_(Subscription.created_at, User.id) < decode_cursor(cursor))
    rows = (await session.execute(query)).all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return [
        SubscribedChannel(
            username=r.username, display_name=r.display_name, subscribed_at=r.created_at
        )
        for r in page
    ], next_cursor
