"""Channels. A channel is a user, addressed by username."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
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
