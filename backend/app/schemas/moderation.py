import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import ReportReason, VideoStatus, VideoVisibility
from app.schemas.auth import StrictModel
from app.schemas.videos import ChannelBriefOut

Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=1000, pattern=r"^[^\x00]*$")
]
RequiredReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000, pattern=r"^[^\x00]*$"),
]


class DecisionIn(StrictModel):
    reason: Reason = ""


class HideIn(StrictModel):
    reason: RequiredReason = Field(description="Shown to the video's owner")


class ReporterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str


class QueuedReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reason: ReportReason
    details: str
    reporter: ReporterOut
    created_at: datetime


class ReportedVideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    visibility: VideoVisibility
    status: VideoStatus
    hidden_at: datetime | None
    channel: ChannelBriefOut = Field(validation_alias="owner")


class QueueEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video: ReportedVideoOut
    thumbnail_url: str | None
    open_reports: int
    reasons: dict[ReportReason, int]
    first_reported_at: datetime
    reports: list[QueuedReportOut] = Field(description="The latest few, newest first")


class QueuePage(BaseModel):
    items: list[QueueEntryOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class DecisionOut(BaseModel):
    reports_closed: int = Field(description="Open reports on the video that this closed")
