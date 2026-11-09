import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReactionType(enum.StrEnum):
    like = "like"
    dislike = "dislike"


class VideoReaction(Base):
    """One like or dislike per user and video."""

    __tablename__ = "video_reactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    reaction: Mapped[ReactionType] = mapped_column(Enum(ReactionType, name="reaction_type"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
