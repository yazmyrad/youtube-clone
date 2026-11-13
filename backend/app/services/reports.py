"""Reporting videos. Moderators work the reports in services/moderation.py."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.permissions import ensure_can_report
from app.models import Report, User, Video
from app.schemas.reports import ReportIn


async def file_report(
    session: AsyncSession, user: User, video_id: uuid.UUID, data: ReportIn
) -> Report:
    # A share lock: a concurrent hide holds the row exclusively, so this waits for it and then
    # sees the video hidden, instead of leaving an open report on a hidden video.
    video = await session.scalar(
        select(Video)
        .where(Video.id == video_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if video is None:
        raise NotFound("Video not found")
    await ensure_can_report(session, user, video)
    report = Report(
        video_id=video.id, reporter_id=user.id, reason=data.reason, details=data.details
    )
    session.add(report)
    try:
        await session.commit()
    except IntegrityError as error:
        # The partial unique index: one open report per user and video (D56).
        await session.rollback()
        raise Conflict("You've already reported this video") from error
    await session.refresh(report)
    return report
