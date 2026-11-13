import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.engagement import ReactionType
from app.models.video import VideoStatus, VideoVisibility
from app.schemas.auth import StrictModel

# Postgres text can't hold a NUL, so it has to be refused here rather than fail on insert.
_NO_NUL = r"^[^\x00]*$"
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=_NO_NUL)
]
Description = Annotated[str, StringConstraints(max_length=5000, pattern=_NO_NUL)]
CommentBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000, pattern=_NO_NUL)
]
SearchText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100, pattern=_NO_NUL)
]


class VideoCreateIn(StrictModel):
    title: Title
    description: Description = ""
    visibility: VideoVisibility = VideoVisibility.private


class VideoUpdateIn(StrictModel):
    title: Title | None = None
    description: Description | None = None
    visibility: VideoVisibility | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.title is None and self.description is None and self.visibility is None:
            raise ValueError("Set at least one of title, description, visibility")
        return self


class VideoOwnerOut(BaseModel):
    """What the owner sees about their own video, in any status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    visibility: VideoVisibility
    status: VideoStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class VideoOwnerPage(BaseModel):
    items: list[VideoOwnerOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class ChannelBriefOut(BaseModel):
    """The channel a video belongs to, as shown next to the video."""

    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str


class VideoDetailsOut(BaseModel):
    """What anyone allowed to view the video sees about it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    visibility: VideoVisibility
    status: VideoStatus
    duration_seconds: int | None
    published_at: datetime | None
    created_at: datetime
    channel: ChannelBriefOut
    views_count: int
    likes_count: int
    dislikes_count: int
    comments_count: int
    thumbnail_url: str | None = Field(description="Signed; null if not ready or hidden")
    my_reaction: ReactionType | None = Field(description="Null if none, or not logged in")


class VideoCardOut(BaseModel):
    """One video in a listing such as the home feed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    duration_seconds: int
    views_count: int
    published_at: datetime
    thumbnail_url: str = Field(description="Signed; request the list again after it expires")
    channel: ChannelBriefOut


class VideoCardPage(BaseModel):
    items: list[VideoCardOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class ReactionIn(StrictModel):
    reaction: ReactionType


class ReactionStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    my_reaction: ReactionType | None
    likes_count: int
    dislikes_count: int


class CommentIn(StrictModel):
    body: CommentBody


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    created_at: datetime
    author: ChannelBriefOut


class CommentPage(BaseModel):
    items: list[CommentOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class PresignedUploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str = Field(description="Send a multipart POST here")
    fields: dict[str, str] = Field(description="Form fields, to send before the `file` field")


class VideoCreatedOut(BaseModel):
    video: VideoOwnerOut
    upload: PresignedUploadOut


class PlaybackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str = Field(description="Relative URL of the HLS master playlist")
    expires_at: datetime = Field(description="Request a new URL before this time")


class VideoAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str
    granted_at: datetime


class VideoAccessPage(BaseModel):
    items: list[VideoAccessOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class ViewIn(StrictModel):
    watched_seconds: int = Field(
        ge=0, le=86_400, description="Seconds actually played since the page opened"
    )
    position_seconds: int = Field(ge=0, le=86_400, description="Where playback is now")


class ViewOut(BaseModel):
    counted: bool = Field(description="Whether this call counted a new view")
    views_count: int


class HistoryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video: VideoCardOut
    progress_seconds: int = Field(description="Where you left off")
    watched_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryEntryOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")
