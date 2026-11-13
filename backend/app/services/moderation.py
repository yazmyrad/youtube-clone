"""The moderators' work: the report queue, and hiding and restoring videos. Every decision
writes a row to the audit log in the same transaction."""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import Conflict, NotFound
from app.core.pagination import decode_cursor, encode_cursor
from app.core.permissions import can_show_thumbnail, ensure_can_view
from app.models import (
    ModerationAction,
    ModerationActionType,
    Report,
    ReportReason,
    ReportStatus,
    User,
    Video,
)
from app.services import playback

# How many of a video's open reports the queue shows in full.
REPORTS_SHOWN = 5


@dataclass(frozen=True)
class QueuedReport:
    id: uuid.UUID
    reason: ReportReason
    details: str
    reporter: User
    created_at: datetime


@dataclass(frozen=True)
class QueueEntry:
    """A video with open reports, as the moderators' queue shows it."""

    video: Video
    thumbnail_url: str | None
    open_reports: int
    reasons: dict[ReportReason, int]
    first_reported_at: datetime
    reports: list[QueuedReport]


async def list_queue(
    session: AsyncSession, *, cursor: str | None, limit: int
) -> tuple[list[QueueEntry], str | None]:
    """Videos with open reports, the longest-waiting first, with keyset pagination."""
    first = func.min(Report.created_at).label("first_reported_at")
    grouped = (
        select(Report.video_id, first, func.count().label("open_reports"))
        .where(Report.status == ReportStatus.open)
        .group_by(Report.video_id)
        .subquery()
    )
    query = (
        select(Video, grouped.c.first_reported_at, grouped.c.open_reports)
        .join(grouped, grouped.c.video_id == Video.id)
        .options(joinedload(Video.owner, innerjoin=True))
        .where(Video.deleted_at.is_(None))
        .order_by(grouped.c.first_reported_at, Video.id)
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(tuple_(grouped.c.first_reported_at, Video.id) > decode_cursor(cursor))
    rows = (await session.execute(query)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(rows[-1].first_reported_at, rows[-1].Video.id)

    video_ids = [row.Video.id for row in rows]
    reports = (
        await session.scalars(
            select(Report)
            .where(Report.video_id.in_(video_ids), Report.status == ReportStatus.open)
            .order_by(Report.created_at.desc())
        )
    ).all()
    reporters = {
        user.id: user
        for user in await session.scalars(
            select(User).where(User.id.in_({report.reporter_id for report in reports}))
        )
    }
    by_video: dict[uuid.UUID, list[Report]] = {}
    for report in reports:
        by_video.setdefault(report.video_id, []).append(report)

    entries = []
    for row in rows:
        open_reports = by_video.get(row.Video.id, [])
        entries.append(
            QueueEntry(
                video=row.Video,
                thumbnail_url=(
                    playback.thumbnail_url(row.Video.id) if can_show_thumbnail(row.Video) else None
                ),
                open_reports=row.open_reports,
                reasons=dict(Counter(report.reason for report in open_reports)),
                first_reported_at=row.first_reported_at,
                reports=[
                    QueuedReport(
                        id=report.id,
                        reason=report.reason,
                        details=report.details,
                        reporter=reporters[report.reporter_id],
                        created_at=report.created_at,
                    )
                    for report in open_reports[:REPORTS_SHOWN]
                ],
            )
        )
    return entries, next_cursor


async def _close_reports(
    session: AsyncSession,
    moderator: User,
    video_id: uuid.UUID,
    status: ReportStatus,
    reason: str,
) -> int:
    """Closes every open report on the video, each with its own audit row. Returns how many."""
    closed = list(
        await session.scalars(
            update(Report)
            .where(Report.video_id == video_id, Report.status == ReportStatus.open)
            .values(status=status, resolved_by=moderator.id, resolved_at=func.now())
            .returning(Report.id)
        )
    )
    action = (
        ModerationActionType.resolve_report
        if status == ReportStatus.resolved
        else ModerationActionType.dismiss_report
    )
    session.add_all(
        ModerationAction(
            actor_id=moderator.id,
            action=action,
            target_video_id=video_id,
            report_id=report_id,
            reason=reason,
        )
        for report_id in closed
    )
    return len(closed)


async def close_report(
    session: AsyncSession,
    moderator: User,
    report_id: uuid.UUID,
    status: ReportStatus,
    reason: str,
) -> int:
    """Resolves or dismisses a report, and with it the other open reports on its video: the
    queue shows them together, so the decision covers them all."""
    report = await session.get(Report, report_id)
    if report is None:
        raise NotFound("Report not found")
    if report.status != ReportStatus.open:
        raise Conflict("This report is already closed")
    # Serializes decisions on one video, so two moderators can't both close its reports.
    await session.execute(select(Video.id).where(Video.id == report.video_id).with_for_update())
    closed = await _close_reports(session, moderator, report.video_id, status, reason)
    if closed == 0:
        await session.rollback()
        raise Conflict("This report is already closed")
    await session.commit()
    return closed


async def _video_for_update(session: AsyncSession, moderator: User, video_id: uuid.UUID) -> Video:
    video = await session.scalar(select(Video).where(Video.id == video_id).with_for_update())
    if video is None:
        raise NotFound("Video not found")
    # A moderator acts only on what they may see: a private video needs an open report (D35).
    await ensure_can_view(session, moderator, video)
    return video


async def hide_video(
    session: AsyncSession, moderator: User, video_id: uuid.UUID, reason: str
) -> int:
    """Takes the video off everywhere at once (D46) and resolves its open reports. Returns how
    many reports it resolved."""
    video = await _video_for_update(session, moderator, video_id)
    if video.hidden_at is not None:
        raise Conflict("The video is already hidden")
    video.hidden_at = func.now()
    session.add(
        ModerationAction(
            actor_id=moderator.id,
            action=ModerationActionType.hide_video,
            target_video_id=video.id,
            target_user_id=video.owner_id,
            reason=reason,
        )
    )
    resolved = await _close_reports(session, moderator, video.id, ReportStatus.resolved, reason)
    await session.commit()
    return resolved


async def restore_video(
    session: AsyncSession, moderator: User, video_id: uuid.UUID, reason: str
) -> None:
    video = await _video_for_update(session, moderator, video_id)
    if video.hidden_at is None:
        raise Conflict("The video isn't hidden")
    video.hidden_at = None
    session.add(
        ModerationAction(
            actor_id=moderator.id,
            action=ModerationActionType.restore_video,
            target_video_id=video.id,
            target_user_id=video.owner_id,
            reason=reason,
        )
    )
    await session.commit()


async def hidden_reason(session: AsyncSession, video_id: uuid.UUID) -> str | None:
    """Why the video was last hidden, for its owner and moderators."""
    return await session.scalar(
        select(ModerationAction.reason)
        .where(
            ModerationAction.target_video_id == video_id,
            ModerationAction.action == ModerationActionType.hide_video,
        )
        .order_by(ModerationAction.created_at.desc(), ModerationAction.id.desc())
        .limit(1)
    )
