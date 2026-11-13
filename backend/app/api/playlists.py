import uuid

from fastapi import APIRouter, status

from app.core.permissions import CurrentUser, OptionalUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.playlists import (
    PlaylistCreateIn,
    PlaylistItemIn,
    PlaylistOrderIn,
    PlaylistOut,
    PlaylistUpdateIn,
)
from app.services import playlists as playlists_service

router = APIRouter(
    prefix="/playlists",
    tags=["playlists"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
    },
)


@router.post(
    "",
    response_model=PlaylistOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a playlist (private unless you say otherwise)",
)
async def create_playlist(
    data: PlaylistCreateIn, user: CurrentUser, session: SessionDep
) -> PlaylistOut:
    return PlaylistOut.model_validate(await playlists_service.create_playlist(session, user, data))


@router.get(
    "/{playlist_id}",
    response_model=PlaylistOut,
    summary="A playlist with the videos you may watch; private ones only for the owner",
)
async def get_playlist(
    playlist_id: uuid.UUID, viewer: OptionalUser, session: SessionDep
) -> PlaylistOut:
    return PlaylistOut.model_validate(
        await playlists_service.get_playlist(session, viewer, playlist_id)
    )


@router.patch(
    "/{playlist_id}",
    response_model=PlaylistOut,
    summary="Edit your playlist's title, description or visibility",
)
async def update_playlist(
    playlist_id: uuid.UUID, data: PlaylistUpdateIn, user: CurrentUser, session: SessionDep
) -> PlaylistOut:
    return PlaylistOut.model_validate(
        await playlists_service.update_playlist(session, user, playlist_id, data)
    )


@router.delete(
    "/{playlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your playlist; its videos stay",
)
async def delete_playlist(playlist_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await playlists_service.delete_playlist(session, user, playlist_id)


@router.post(
    "/{playlist_id}/items",
    response_model=PlaylistOut,
    summary="Add a video you may watch to the end of your playlist (safe to repeat)",
    responses={status.HTTP_409_CONFLICT: {"model": ErrorOut}},
)
async def add_item(
    playlist_id: uuid.UUID, data: PlaylistItemIn, user: CurrentUser, session: SessionDep
) -> PlaylistOut:
    return PlaylistOut.model_validate(
        await playlists_service.add_item(session, user, playlist_id, data.video_id)
    )


@router.delete(
    "/{playlist_id}/items/{video_id}",
    response_model=PlaylistOut,
    summary="Remove a video from your playlist (safe to repeat)",
)
async def remove_item(
    playlist_id: uuid.UUID, video_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PlaylistOut:
    return PlaylistOut.model_validate(
        await playlists_service.remove_item(session, user, playlist_id, video_id)
    )


@router.put(
    "/{playlist_id}/items/order",
    response_model=PlaylistOut,
    summary="Reorder your playlist",
    responses={status.HTTP_409_CONFLICT: {"model": ErrorOut}},
)
async def reorder_items(
    playlist_id: uuid.UUID, data: PlaylistOrderIn, user: CurrentUser, session: SessionDep
) -> PlaylistOut:
    return PlaylistOut.model_validate(
        await playlists_service.reorder_items(session, user, playlist_id, data.video_ids)
    )
