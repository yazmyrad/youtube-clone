import uuid

from fastapi import APIRouter, Request, status

from app.core.errors import PayloadTooLarge, UnsupportedMediaType
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
from app.schemas.videos import HistoryEntryOut, HistoryPage, VideoOwnerOut, VideoOwnerPage
from app.services import channel_images
from app.services import channels as channels_service
from app.services import history as history_service
from app.services import playlists as playlists_service
from app.services import users as users_service
from app.services import videos as videos_service
from app.services.channel_images import ImageKind

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


@router.get(
    "/me/history",
    response_model=HistoryPage,
    summary="Your watch history, most recent first; only videos you may still watch",
)
async def list_history(
    user: CurrentUser,
    session: SessionDep,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_VIDEO_PAGE,
) -> HistoryPage:
    entries, next_cursor = await history_service.list_history(
        session, user, cursor=cursor, limit=limit
    )
    return HistoryPage(
        items=[HistoryEntryOut.model_validate(entry) for entry in entries],
        next_cursor=next_cursor,
    )


@router.delete(
    "/me/history",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear your watch history",
)
async def clear_history(user: CurrentUser, session: SessionDep) -> None:
    await history_service.clear(session, user)


@router.delete(
    "/me/history/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one video from your watch history (safe to repeat)",
)
async def remove_history_entry(video_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await history_service.remove_entry(session, user, video_id)


_IMAGE_BODY = {
    "requestBody": {
        "required": True,
        "description": "The image file itself as the body: JPEG, PNG or WebP, up to 6 MB",
        "content": {
            content_type: {"schema": {"type": "string", "format": "binary"}}
            for content_type in channel_images.ACCEPTED_TYPES
        },
    }
}
# Described here, not by Python: its name for 413 differs between versions, and the schema
# must be the same wherever it's generated.
_IMAGE_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ErrorOut,
        "description": "Not a valid image, or too small or too large in pixels",
    },
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorOut, "description": "Larger than 6 MB"},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
        "model": ErrorOut,
        "description": "Not JPEG, PNG or WebP",
    },
}


async def _image_body(request: Request) -> bytes:
    """At most one byte over the limit is read, so a huge body costs nothing to refuse."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > channel_images.MAX_IMAGE_BYTES:
            raise PayloadTooLarge("The image is too large: at most 6 MB")
    return bytes(data)


def _content_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


@router.put(
    "/me/images/{kind}",
    response_model=MeOut,
    responses=_IMAGE_ERRORS,
    openapi_extra=_IMAGE_BODY,
    summary="Set your channel's avatar or banner, cropped to its shape",
)
async def set_channel_image(
    kind: ImageKind, request: Request, user: CurrentUser, session: SessionDep
) -> MeOut:
    content_type = _content_type(request)
    if content_type not in channel_images.ACCEPTED_TYPES:
        raise UnsupportedMediaType("Upload a JPEG, PNG or WebP image")
    data = await _image_body(request)
    return MeOut.model_validate(
        await channel_images.set_image(session, user, kind, data, content_type)
    )


@router.delete(
    "/me/images/{kind}",
    response_model=MeOut,
    summary="Remove your channel's avatar or banner (safe to repeat)",
)
async def remove_channel_image(kind: ImageKind, user: CurrentUser, session: SessionDep) -> MeOut:
    return MeOut.model_validate(await channel_images.remove_image(session, user, kind))
