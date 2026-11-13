import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import VideoVisibility
from app.schemas.auth import StrictModel
from app.schemas.videos import ChannelBriefOut, Title, VideoCardOut

PlaylistDescription = Annotated[str, StringConstraints(max_length=1000, pattern=r"^[^\x00]*$")]


class PlaylistCreateIn(StrictModel):
    title: Title
    description: PlaylistDescription = ""
    visibility: VideoVisibility = VideoVisibility.private


class PlaylistUpdateIn(StrictModel):
    title: Title | None = None
    description: PlaylistDescription | None = None
    visibility: VideoVisibility | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.title is None and self.description is None and self.visibility is None:
            raise ValueError("Set at least one of title, description, visibility")
        return self


class PlaylistSummaryOut(BaseModel):
    """A playlist as listed. Counts and the thumbnail cover only the videos the caller may
    watch."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    visibility: VideoVisibility
    channel: ChannelBriefOut
    video_count: int = Field(description="Videos the caller may watch")
    thumbnail_url: str | None = Field(description="The first such video's; null if none")
    updated_at: datetime


class PlaylistOut(PlaylistSummaryOut):
    description: str
    created_at: datetime
    items: list[VideoCardOut] = Field(
        description="In playlist order; only what the caller may watch"
    )


class PlaylistPage(BaseModel):
    items: list[PlaylistSummaryOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class PlaylistItemIn(StrictModel):
    video_id: uuid.UUID


class PlaylistOrderIn(StrictModel):
    video_ids: list[uuid.UUID] = Field(
        max_length=500,
        description="The new order of exactly the videos the playlist shows you",
    )
