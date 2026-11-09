import uuid

from fastapi import APIRouter, status

from app.core.permissions import CurrentUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.videos import ReactionIn, ReactionStateOut
from app.services import reactions as reactions_service

router = APIRouter(
    prefix="/videos",
    tags=["reactions"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
        status.HTTP_409_CONFLICT: {"model": ErrorOut},
    },
)


@router.put(
    "/{video_id}/reaction",
    response_model=ReactionStateOut,
    summary="Like or dislike a video (safe to repeat)",
)
async def set_reaction(
    video_id: uuid.UUID, data: ReactionIn, user: CurrentUser, session: SessionDep
) -> ReactionStateOut:
    return ReactionStateOut.model_validate(
        await reactions_service.set_reaction(session, user, video_id, data.reaction)
    )


@router.delete(
    "/{video_id}/reaction",
    response_model=ReactionStateOut,
    summary="Remove your like or dislike (safe to repeat)",
)
async def remove_reaction(
    video_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ReactionStateOut:
    return ReactionStateOut.model_validate(
        await reactions_service.remove_reaction(session, user, video_id)
    )
