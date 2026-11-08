import uuid

from fastapi import APIRouter, status

from app.core.permissions import CurrentUser, OptionalUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.videos import (
    PlaybackOut,
    PresignedUploadOut,
    VideoCreatedOut,
    VideoCreateIn,
    VideoOwnerOut,
    VideoUpdateIn,
)
from app.services import playback as playback_service
from app.services import videos as videos_service

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
