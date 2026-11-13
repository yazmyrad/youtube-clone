import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import ReportReason, ReportStatus
from app.schemas.auth import StrictModel

ReportDetails = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=1000, pattern=r"^[^\x00]*$")
]


class ReportIn(StrictModel):
    reason: ReportReason
    details: ReportDetails = ""


class ReportOut(BaseModel):
    """What the reporter sees of their own report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    video_id: uuid.UUID
    reason: ReportReason
    details: str
    status: ReportStatus
    created_at: datetime
