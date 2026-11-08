from fastapi import APIRouter, status

from app.core.permissions import CurrentUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.videos import PresignedUploadOut, VideoCreatedOut, VideoCreateIn, VideoOwnerOut
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
