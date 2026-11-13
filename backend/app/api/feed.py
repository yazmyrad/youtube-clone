from fastapi import APIRouter, status

from app.core.pagination import DEFAULT_VIDEO_PAGE, KeysetCursor, PageLimit
from app.core.permissions import CurrentUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.videos import VideoCardOut, VideoCardPage
from app.services import videos as videos_service

router = APIRouter(
    prefix="/feed",
    tags=["feed"],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut}},
)


@router.get(
    "/subscriptions",
    response_model=VideoCardPage,
    summary="Latest public videos from the channels you subscribe to",
)
async def list_subscription_feed(
    user: CurrentUser,
    session: SessionDep,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_VIDEO_PAGE,
) -> VideoCardPage:
    cards, next_cursor = await videos_service.list_subscription_feed(
        session, user, cursor=cursor, limit=limit
    )
    return VideoCardPage(
        items=[VideoCardOut.model_validate(card) for card in cards], next_cursor=next_cursor
    )
