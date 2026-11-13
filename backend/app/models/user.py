import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

USERNAME_PATTERN = r"^[a-zA-Z0-9_-]{3,30}$"


class UserRole(enum.StrEnum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"username ~ '{USERNAME_PATTERN}'", name="username_format"),
        CheckConstraint("subscribers_count >= 0", name="subscribers_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(CITEXT, unique=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(1000), server_default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), server_default=UserRole.user.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    subscribers_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Shared by every token rotated from one login, so reuse can revoke them all.
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)  # SHA-256
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    """A user following a channel. A channel is a user, so both sides are users."""

    __tablename__ = "subscriptions"
    __table_args__ = (CheckConstraint("subscriber_id <> channel_id", name="not_self"),)

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # For a channel's subscriber count and for deleting a channel's subscriptions.
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
