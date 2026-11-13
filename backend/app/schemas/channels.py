from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import VideoVisibility
from app.schemas.videos import VideoCardOut


class ChannelOut(BaseModel):
    """A channel's page header. A channel is a user, addressed by username."""

    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str
    description: str
    subscribers_count: int
    created_at: datetime
    is_subscribed: bool = Field(description="Whether the caller subscribes; false if anonymous")


class ChannelVideoOut(VideoCardOut):
    visibility: VideoVisibility = Field(
        description="Others only ever see public videos; the owner also sees the rest"
    )


class ChannelVideoPage(BaseModel):
    items: list[ChannelVideoOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class SubscriptionStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_subscribed: bool
    subscribers_count: int


class SubscribedChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str
    subscribed_at: datetime


class SubscribedChannelPage(BaseModel):
    items: list[SubscribedChannelOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")
