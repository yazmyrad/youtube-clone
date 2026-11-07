import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.user import UserRole
from app.schemas.auth import StrictModel


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page")


class AdminUserUpdateIn(StrictModel):
    role: UserRole | None = None
    is_active: bool | None = Field(
        default=None, description="false disables the account and ends all its sessions"
    )

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.role is None and self.is_active is None:
            raise ValueError("Set at least one of role, is_active")
        return self
