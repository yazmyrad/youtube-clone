from typing import Annotated

from fastapi import APIRouter, Query

from app.core.pagination import DEFAULT_VIDEO_PAGE, KeysetCursor, PageLimit
from app.core.permissions import SessionDep
from app.schemas.videos import SearchText, VideoCardOut, VideoCardPage
from app.services import videos as videos_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/videos", response_model=VideoCardPage, summary="Find public videos by title")
async def search_videos(
    session: SessionDep,
    q: Annotated[SearchText, Query(description="Part of the title, at least 2 characters")],
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_VIDEO_PAGE,
) -> VideoCardPage:
    cards, next_cursor = await videos_service.search_videos(
        session, q=q, cursor=cursor, limit=limit
    )
    return VideoCardPage(
        items=[VideoCardOut.model_validate(card) for card in cards], next_cursor=next_cursor
    )
