import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole
from app.schemas.auth import DisplayName, StrictModel


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    display_name: str
    description: str
    role: UserRole
    subscribers_count: int
    avatar_url: str | None = Field(description="Square WebP; null for the letter avatar")
    banner_url: str | None = Field(description="Wide WebP; null for none")
    created_at: datetime


class MeUpdateIn(StrictModel):
    """Only these fields are editable by the user; role and status are admin-only."""

    display_name: DisplayName | None = None
    description: Annotated[str, Field(max_length=1000)] | None = None
