from fastapi import APIRouter, status

from app.core.pagination import DEFAULT_VIDEO_PAGE, KeysetCursor, PageLimit
from app.core.permissions import OptionalUser, SessionDep
from app.schemas.channels import ChannelOut, ChannelVideoOut, ChannelVideoPage
from app.schemas.errors import ErrorOut
from app.services import channels as channels_service

router = APIRouter(
    prefix="/channels",
    tags=["channels"],
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)


@router.get("/{username}", response_model=ChannelOut, summary="Channel details")
async def get_channel(username: str, session: SessionDep, viewer: OptionalUser) -> ChannelOut:
    details = await channels_service.get_channel(session, viewer, username)
    return ChannelOut.model_validate(details)


@router.get(
    "/{username}/videos",
    response_model=ChannelVideoPage,
    summary="A channel's videos, newest first; the owner also sees private and unlisted ones",
)
async def list_channel_videos(
    username: str,
    session: SessionDep,
    viewer: OptionalUser,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_VIDEO_PAGE,
) -> ChannelVideoPage:
    cards, next_cursor = await channels_service.list_channel_videos(
        session, viewer, username, cursor=cursor, limit=limit
    )
    return ChannelVideoPage(
        items=[ChannelVideoOut.model_validate(card) for card in cards], next_cursor=next_cursor
    )
