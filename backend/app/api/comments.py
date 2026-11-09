import uuid

from fastapi import APIRouter, status

from app.core.pagination import DEFAULT_COMMENT_PAGE, KeysetCursor, PageLimit
from app.core.permissions import CurrentUser, OptionalUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.videos import CommentIn, CommentOut, CommentPage
from app.services import comments as comments_service

router = APIRouter(
    tags=["comments"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
    },
)


@router.get(
    "/videos/{video_id}/comments",
    response_model=CommentPage,
    summary="List a video's comments, newest first",
)
async def list_comments(
    video_id: uuid.UUID,
    user: OptionalUser,
    session: SessionDep,
    cursor: KeysetCursor = None,
    limit: PageLimit = DEFAULT_COMMENT_PAGE,
) -> CommentPage:
    comments, next_cursor = await comments_service.list_comments(
        session, user, video_id, cursor=cursor, limit=limit
    )
    return CommentPage(
        items=[CommentOut.model_validate(comment) for comment in comments],
        next_cursor=next_cursor,
    )


@router.post(
    "/videos/{video_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a video",
    responses={status.HTTP_409_CONFLICT: {"model": ErrorOut}},
)
async def add_comment(
    video_id: uuid.UUID, data: CommentIn, user: CurrentUser, session: SessionDep
) -> CommentOut:
    return CommentOut.model_validate(
        await comments_service.add_comment(session, user, video_id, data.body)
    )


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment (its author, the video's owner, or a moderator)",
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorOut}},
)
async def delete_comment(comment_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await comments_service.delete_comment(session, user, comment_id)
