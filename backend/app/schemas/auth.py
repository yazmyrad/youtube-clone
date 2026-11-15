import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.user import USERNAME_PATTERN

# argon2 hashes any length, but an upper bound keeps hashing cost bounded per request.
Password = Annotated[str, Field(min_length=8, max_length=128)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class StrictModel(BaseModel):
    # Unknown fields are an error, so a client can't slip in `role` or `is_active` (D36).
    model_config = ConfigDict(extra="forbid")


class RegisterIn(StrictModel):
    username: Annotated[str, Field(pattern=USERNAME_PATTERN)]
    email: EmailStr
    password: Password
    display_name: DisplayName


class LoginIn(StrictModel):
    email: EmailStr
    password: Annotated[str, Field(max_length=128)]


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - a token type, not a secret
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshIn(StrictModel):
    user_id: uuid.UUID | None = Field(
        default=None, description="Which signed-in account; optional when there's only one"
    )


class LogoutIn(StrictModel):
    user_id: uuid.UUID | None = Field(
        default=None, description="Sign out of this account only; without it, of all of them"
    )


class AccountOut(BaseModel):
    """An account signed in in this browser, as the switcher shows it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None


class AccountsOut(BaseModel):
    items: list[AccountOut]
