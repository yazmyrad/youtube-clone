import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReportReason(enum.StrEnum):
    spam = "spam"
    violence = "violence"
    sexual = "sexual"
    copyright = "copyright"
    other = "other"


class ReportStatus(enum.StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class ModerationActionType(enum.StrEnum):
    hide_video = "hide_video"
    restore_video = "restore_video"
    resolve_report = "resolve_report"
    dismiss_report = "dismiss_report"
    change_role = "change_role"
    disable_user = "disable_user"
    enable_user = "enable_user"


# Literal SQL, so Postgres can match queries to the partial indexes below.
OPEN = text("status = 'open'")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        # One open report per user and video (D56). Also answers "has an open report" (D35).
        Index(
            "uq_reports_open_video_reporter",
            "video_id",
            "reporter_id",
            unique=True,
            postgresql_where=OPEN,
        ),
        # The moderators' queue.
        Index("ix_reports_open_created", "created_at", postgresql_where=OPEN),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reason: Mapped[ReportReason] = mapped_column(Enum(ReportReason, name="report_reason"))
    details: Mapped[str] = mapped_column(String(1000), server_default="")
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), server_default=ReportStatus.open.value
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModerationAction(Base):
    """Append-only audit log: rows are inserted, never changed."""

    __tablename__ = "moderation_actions"
    __table_args__ = (
        Index("ix_moderation_actions_video_created", "target_video_id", text("created_at DESC")),
        Index("ix_moderation_actions_created", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[ModerationActionType] = mapped_column(
        Enum(ModerationActionType, name="moderation_action_type")
    )
    target_video_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL")
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(1000), server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
