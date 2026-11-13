import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.video import VideoVisibility

if TYPE_CHECKING:
    from app.models.user import User


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="title_not_blank"),
        # A channel's playlists, newest first.
        Index("ix_playlists_owner_created", "owner_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000), server_default="")
    # The videos' type: the same three levels mean the same thing here.
    visibility: Mapped[VideoVisibility] = mapped_column(
        Enum(VideoVisibility, name="video_visibility", create_type=False),
        server_default=VideoVisibility.public.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Loaded only on request, so N+1s fail loudly.
    owner: Mapped["User"] = relationship(lazy="raise")


class PlaylistItem(Base):
    """Being in a playlist grants no access: reads filter items through `can_view`."""

    __tablename__ = "playlist_items"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        # Checked at commit, so a reorder can pass through duplicates within one transaction.
        UniqueConstraint("playlist_id", "position", deferrable=True, initially="DEFERRED"),
    )

    playlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
