import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.video import VideoStatus, VideoVisibility
from app.schemas.auth import StrictModel

# Postgres text can't hold a NUL, so it has to be refused here rather than fail on insert.
_NO_NUL = r"^[^\x00]*$"
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=_NO_NUL)
]
Description = Annotated[str, StringConstraints(max_length=5000, pattern=_NO_NUL)]


class VideoCreateIn(StrictModel):
    title: Title
    description: Description = ""
    visibility: VideoVisibility = VideoVisibility.private


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


class PresignedUploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str = Field(description="Send a multipart POST here")
    fields: dict[str, str] = Field(description="Form fields, to send before the `file` field")


class VideoCreatedOut(BaseModel):
    video: VideoOwnerOut
    upload: PresignedUploadOut
