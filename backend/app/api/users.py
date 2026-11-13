import uuid

from fastapi import APIRouter, status

from app.core.pagination import (
    DEFAULT_SUBSCRIPTION_PAGE,
    DEFAULT_VIDEO_PAGE,
    KeysetCursor,
    PageLimit,
)
from app.core.permissions import CurrentUser, SessionDep
from app.schemas.channels import SubscribedChannelOut, SubscribedChannelPage
from app.schemas.errors import ErrorOut
from app.schemas.playlists import OwnPlaylistOut, OwnPlaylistPage
from app.schemas.users import MeOut, MeUpdateIn
from app.schemas.videos import VideoOwnerOut, VideoOwnerPage
from app.services import channels as channels_service
from app.services import playlists as playlists_service
from app.services import users as users_service
from app.services import videos as videos_service

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut}},
)


@router.get("/me", response_model=MeOut, summary="Current user")
async def get_me(user: CurrentUser) -> MeOut:
    return MeOut.model_validate(user)


@router.patch("/me", response_model=MeOut, summary="Edit display name and description")
async def update_me(data: MeUpdateIn, user: CurrentUser, session: SessionDep) -> MeOut:
    return MeOut.model_validate(await users_service.update_me(session, user, data))


@router.get(
    "/me/videos",
    response_model=VideoOwnerPage,
    summary="List your own videos in any status, newest first",
)
async def list_my_videos(
    user: CurrentUser,
    session: SessionDep,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_VIDEO_PAGE,
) -> VideoOwnerPage:
    videos, next_cursor = await videos_service.list_my_videos(
        session, user, cursor=cursor, limit=limit
    )
    return VideoOwnerPage(
        items=[VideoOwnerOut.model_validate(video) for video in videos], next_cursor=next_cursor
    )


@router.get(
    "/me/subscriptions",
    response_model=SubscribedChannelPage,
    summary="Channels you subscribe to, most recently subscribed first",
)
async def list_my_subscriptions(
    user: CurrentUser,
    session: SessionDep,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_SUBSCRIPTION_PAGE,
) -> SubscribedChannelPage:
    channels, next_cursor = await channels_service.list_my_subscriptions(
        session, user, cursor=cursor, limit=limit
    )
    return SubscribedChannelPage(
        items=[SubscribedChannelOut.model_validate(channel) for channel in channels],
        next_cursor=next_cursor,
    )


@router.get(
    "/me/playlists",
    response_model=OwnPlaylistPage,
    summary="Your playlists, newest first, each saying whether it holds `video_id`",
)
async def list_my_playlists(
    user: CurrentUser,
    session: SessionDep,
    video_id: uuid.UUID | None = None,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_SUBSCRIPTION_PAGE,
) -> OwnPlaylistPage:
    playlists, next_cursor = await playlists_service.list_my_playlists(
        session, user, video_id=video_id, cursor=cursor, limit=limit
    )
    return OwnPlaylistPage(
        items=[OwnPlaylistOut.model_validate(p) for p in playlists], next_cursor=next_cursor
    )
