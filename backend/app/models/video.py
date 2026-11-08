import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VideoVisibility(enum.StrEnum):
    public = "public"
    unlisted = "unlisted"
    private = "private"


class VideoStatus(enum.StrEnum):
    uploading = "uploading"
    processing = "processing"
    ready = "ready"
    failed = "failed"


# Shared by the feed and search indexes: what anyone may see in a listing.
LISTED = text(
    "visibility = 'public' AND status = 'ready' AND hidden_at IS NULL AND deleted_at IS NULL"
)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="title_not_blank"),
        CheckConstraint("duration_seconds > 0", name="duration_positive"),
        CheckConstraint("source_size_bytes >= 0", name="source_size_non_negative"),
        CheckConstraint("views_count >= 0", name="views_count_non_negative"),
        CheckConstraint("likes_count >= 0", name="likes_count_non_negative"),
        CheckConstraint("dislikes_count >= 0", name="dislikes_count_non_negative"),
        CheckConstraint("comments_count >= 0", name="comments_count_non_negative"),
        # A video can't be ready without its files.
        CheckConstraint(
            "status <> 'ready' OR (hls_prefix IS NOT NULL AND thumbnail_key IS NOT NULL"
            " AND duration_seconds IS NOT NULL AND published_at IS NOT NULL)",
            name="ready_has_media",
        ),
        # Home feed, keyset pagination.
        Index(
            "ix_videos_feed",
            text("published_at DESC"),
            text("id DESC"),
            postgresql_where=LISTED,
        ),
        # Search by title, tolerant of partial matches.
        Index(
            "ix_videos_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
            postgresql_where=LISTED,
        ),
        # Channel page and subscriptions feed.
        Index(
            "ix_videos_channel",
            "owner_id",
            text("published_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'ready' AND deleted_at IS NULL"),
        ),
        # The owner's own video list.
        Index(
            "ix_videos_owner_created",
            "owner_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Abandoned upload sweep.
        Index(
            "ix_videos_uploading_created",
            "created_at",
            postgresql_where=text("status = 'uploading'"),
        ),
        # Object deletion sweep.
        Index(
            "ix_videos_deleted",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(5000), server_default="")
    visibility: Mapped[VideoVisibility] = mapped_column(
        Enum(VideoVisibility, name="video_visibility"),
        server_default=VideoVisibility.private.value,
    )
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status"), server_default=VideoStatus.uploading.value
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_key: Mapped[str | None] = mapped_column(Text)  # Cleared when the raw file is deleted.
    hls_prefix: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    source_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    views_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    likes_count: Mapped[int] = mapped_column(Integer, server_default="0")
    dislikes_count: Mapped[int] = mapped_column(Integer, server_default="0")
    comments_count: Mapped[int] = mapped_column(Integer, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
