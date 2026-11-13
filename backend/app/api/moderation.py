import uuid

from fastapi import APIRouter, status

from app.core.pagination import KeysetCursor, PageLimit
from app.core.permissions import ModeratorUser, SessionDep
from app.models import ReportStatus
from app.schemas.errors import ErrorOut
from app.schemas.moderation import DecisionIn, DecisionOut, HideIn, QueueEntryOut, QueuePage
from app.services import moderation as moderation_service

router = APIRouter(
    prefix="/moderation",
    tags=["moderation"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_403_FORBIDDEN: {"model": ErrorOut},
    },
)

_DECISION_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
    status.HTTP_409_CONFLICT: {"model": ErrorOut},
}


@router.get(
    "/reports",
    response_model=QueuePage,
    summary="Videos with open reports, the longest-waiting first",
)
async def list_queue(
    _moderator: ModeratorUser,
    session: SessionDep,
    cursor: KeysetCursor = None,
    limit: PageLimit = 20,
) -> QueuePage:
    entries, next_cursor = await moderation_service.list_queue(session, cursor=cursor, limit=limit)
    return QueuePage(
        items=[QueueEntryOut.model_validate(entry) for entry in entries],
        next_cursor=next_cursor,
    )


@router.post(
    "/reports/{report_id}/resolve",
    response_model=DecisionOut,
    summary="Mark the report, and the video's other open reports, resolved",
    responses=_DECISION_ERRORS,
)
async def resolve_report(
    report_id: uuid.UUID, data: DecisionIn, moderator: ModeratorUser, session: SessionDep
) -> DecisionOut:
    closed = await moderation_service.close_report(
        session, moderator, report_id, ReportStatus.resolved, data.reason
    )
    return DecisionOut(reports_closed=closed)


@router.post(
    "/reports/{report_id}/dismiss",
    response_model=DecisionOut,
    summary="Dismiss the report, and the video's other open reports",
    responses=_DECISION_ERRORS,
)
async def dismiss_report(
    report_id: uuid.UUID, data: DecisionIn, moderator: ModeratorUser, session: SessionDep
) -> DecisionOut:
    closed = await moderation_service.close_report(
        session, moderator, report_id, ReportStatus.dismissed, data.reason
    )
    return DecisionOut(reports_closed=closed)


@router.post(
    "/videos/{video_id}/hide",
    response_model=DecisionOut,
    summary="Hide a video everywhere, with a reason its owner sees; resolves its reports",
    responses=_DECISION_ERRORS,
)
async def hide_video(
    video_id: uuid.UUID, data: HideIn, moderator: ModeratorUser, session: SessionDep
) -> DecisionOut:
    resolved = await moderation_service.hide_video(session, moderator, video_id, data.reason)
    return DecisionOut(reports_closed=resolved)


@router.post(
    "/videos/{video_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restore a hidden video",
    responses=_DECISION_ERRORS,
)
async def restore_video(
    video_id: uuid.UUID, data: DecisionIn, moderator: ModeratorUser, session: SessionDep
) -> None:
    await moderation_service.restore_video(session, moderator, video_id, data.reason)
