import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.client import ClientDep
from app.core.pagination import DEFAULT_VIDEO_PAGE, KeysetCursor, PageLimit
from app.core.permissions import CurrentUser, OptionalUser, SessionDep
from app.models.user import USERNAME_PATTERN
from app.schemas.errors import ErrorOut
from app.schemas.videos import (
    PlaybackOut,
    PresignedUploadOut,
    VideoAccessOut,
    VideoAccessPage,
    VideoCardOut,
    VideoCardPage,
    VideoCreatedOut,
    VideoCreateIn,
    VideoDetailsOut,
    VideoOwnerOut,
    VideoUpdateIn,
    ViewIn,
    ViewOut,
)
from app.services import playback as playback_service
from app.services import videos as videos_service
from app.services import views as views_service

Username = Annotated[str, Path(pattern=USERNAME_PATTERN)]

router = APIRouter(
    prefix="/videos",
    tags=["videos"],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut}},
)


@router.post(
    "",
    response_model=VideoCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a video and get a presigned upload form",
    responses={status.HTTP_409_CONFLICT: {"model": ErrorOut}},
)
async def create_video(
    data: VideoCreateIn, user: CurrentUser, session: SessionDep
) -> VideoCreatedOut:
    video, upload = await videos_service.create_video(session, user, data)
    return VideoCreatedOut(
        video=VideoOwnerOut.model_validate(video),
        upload=PresignedUploadOut.model_validate(upload),
    )


@router.get("", response_model=VideoCardPage, summary="List public videos, newest first")
async def list_feed(
    session: SessionDep, cursor: KeysetCursor = None, limit: PageLimit = DEFAULT_VIDEO_PAGE
) -> VideoCardPage:
    cards, next_cursor = await videos_service.list_feed(session, cursor=cursor, limit=limit)
    return VideoCardPage(
        items=[VideoCardOut.model_validate(card) for card in cards], next_cursor=next_cursor
    )


@router.get(
    "/{video_id}",
    response_model=VideoDetailsOut,
    summary="Get a video's details",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)
async def get_video(
    video_id: uuid.UUID, user: OptionalUser, session: SessionDep
) -> VideoDetailsOut:
    return VideoDetailsOut.model_validate(await videos_service.get_video(session, user, video_id))


@router.post(
    "/{video_id}/upload/complete",
    response_model=VideoOwnerOut,
    summary="Confirm the upload and start processing (safe to repeat)",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
        status.HTTP_409_CONFLICT: {"model": ErrorOut},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorOut},
    },
)
async def complete_upload(
    video_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> VideoOwnerOut:
    return VideoOwnerOut.model_validate(
        await videos_service.complete_upload(session, user, video_id)
    )


@router.patch(
    "/{video_id}",
    response_model=VideoOwnerOut,
    summary="Edit title, description or visibility",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)
async def update_video(
    video_id: uuid.UUID, data: VideoUpdateIn, user: CurrentUser, session: SessionDep
) -> VideoOwnerOut:
    return VideoOwnerOut.model_validate(
        await videos_service.update_video(session, user, video_id, data)
    )


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your video",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)
async def delete_video(video_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await videos_service.delete_video(session, user, video_id)


@router.post(
    "/{video_id}/playback",
    response_model=PlaybackOut,
    summary="Get a short-lived signed URL for the HLS master playlist",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
        status.HTTP_409_CONFLICT: {"model": ErrorOut},
    },
)
async def start_playback(
    video_id: uuid.UUID, user: OptionalUser, session: SessionDep
) -> PlaybackOut:
    return PlaybackOut.model_validate(
        await playback_service.issue_playback(session, user, video_id)
    )


@router.post(
    "/{video_id}/view",
    response_model=ViewOut,
    summary="Playback heartbeat: counts a view after 30 s or half the video, once a day",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
        status.HTTP_409_CONFLICT: {"model": ErrorOut},
    },
)
async def record_view(
    video_id: uuid.UUID,
    data: ViewIn,
    viewer: OptionalUser,
    client: ClientDep,
    session: SessionDep,
) -> ViewOut:
    return ViewOut.model_validate(
        await views_service.record_view(
            session,
            viewer,
            video_id,
            client,
            watched_seconds=data.watched_seconds,
            position_seconds=data.position_seconds,
        ),
        from_attributes=True,
    )


@router.get(
    "/{video_id}/access",
    response_model=VideoAccessPage,
    summary="List who may watch this private video",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)
async def list_access(
    video_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    cursor: Annotated[str | None, Query(pattern=USERNAME_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> VideoAccessPage:
    rows, next_cursor = await videos_service.list_access(
        session, user, video_id, cursor=cursor, limit=limit
    )
    return VideoAccessPage(
        items=[VideoAccessOut.model_validate(row) for row in rows], next_cursor=next_cursor
    )


@router.put(
    "/{video_id}/access/{username}",
    response_model=VideoAccessOut,
    summary="Let a user watch this private video (safe to repeat)",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
        status.HTTP_409_CONFLICT: {"model": ErrorOut},
    },
)
async def grant_access(
    video_id: uuid.UUID, username: Username, user: CurrentUser, session: SessionDep
) -> VideoAccessOut:
    return VideoAccessOut.model_validate(
        await videos_service.grant_access(session, user, video_id, username)
    )


@router.delete(
    "/{video_id}/access/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop a user from watching this private video (safe to repeat)",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)
async def revoke_access(
    video_id: uuid.UUID, username: Username, user: CurrentUser, session: SessionDep
) -> None:
    await videos_service.revoke_access(session, user, video_id, username)
