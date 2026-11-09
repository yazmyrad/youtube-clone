import uuid

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import NotFound
from app.core.pagination import decode_cursor, encode_cursor
from app.core.permissions import ensure_can_delete_comment, ensure_can_view
from app.models import Comment, User, Video
from app.services.videos import adjust_counters, get_engageable_for_update


async def list_comments(
    session: AsyncSession, user: User | None, video_id: uuid.UUID, *, cursor: str | None, limit: int
) -> tuple[list[Comment], str | None]:
    """A video's comments, newest first, with keyset pagination."""
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found")
    await ensure_can_view(session, user, video)

    query = (
        select(Comment)
        .options(joinedload(Comment.author, innerjoin=True))
        .where(Comment.video_id == video_id)
        .order_by(Comment.created_at.desc(), Comment.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(tuple_(Comment.created_at, Comment.id) < decode_cursor(cursor))
    comments = list(await session.scalars(query))
    if len(comments) > limit:
        comments = comments[:limit]
        return comments, encode_cursor(comments[-1].created_at, comments[-1].id)
    return comments, None


async def add_comment(
    session: AsyncSession, user: User, video_id: uuid.UUID, body: str
) -> Comment:
    video = await get_engageable_for_update(session, user, video_id)
    comment = Comment(video_id=video.id, author=user, body=body)
    session.add(comment)
    await adjust_counters(session, video.id, comments_count=1)
    await session.commit()
    # Only this column: a full refresh would also unload `author`.
    await session.refresh(comment, ["created_at"])
    return comment


async def delete_comment(session: AsyncSession, user: User, comment_id: uuid.UUID) -> None:
    comment = await session.get(Comment, comment_id)
    if comment is None:
        raise NotFound("Comment not found")
    # Concurrent deletes take turns here, so only the one that removes the row counts it.
    video = await session.scalar(
        select(Video).where(Video.id == comment.video_id).with_for_update(key_share=True)
    )
    if video is None:
        raise NotFound("Comment not found")
    await ensure_can_delete_comment(session, user, comment, video)

    result = await session.execute(
        delete(Comment)
        .where(Comment.id == comment_id)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount:
        await adjust_counters(session, video.id, comments_count=-1)
    await session.commit()
