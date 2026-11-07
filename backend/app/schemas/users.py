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
    created_at: datetime


class MeUpdateIn(StrictModel):
    """Only these fields are editable by the user; role and status are admin-only."""

    display_name: DisplayName | None = None
    description: Annotated[str, Field(max_length=1000)] | None = None
