import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WatchHistory(Base):
    """One row per user and video, moved to the top each time they watch it."""

    __tablename__ = "watch_history"
    __table_args__ = (
        CheckConstraint("progress_seconds >= 0", name="progress_non_negative"),
        # The history page, newest first.
        Index("ix_watch_history_user_watched", "user_id", text("last_watched_at DESC")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    progress_seconds: Mapped[int] = mapped_column(Integer, server_default="0")
    last_watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VideoView(Base):
    """One counted view per viewer, video and day (D52). Short-lived: a daily sweep removes
    old days. `viewer_key` is an HMAC, so the raw IP is never stored."""

    __tablename__ = "video_views"

    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    viewer_key: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
