import uuid

from fastapi import APIRouter, status

from app.core.permissions import CurrentUser, OptionalUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.playlists import PlaylistCreateIn, PlaylistOut, PlaylistUpdateIn
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
