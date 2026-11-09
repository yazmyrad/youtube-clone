import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReactionType, User, Video, VideoReaction
from app.services.videos import adjust_counters, get_engageable_for_update

_COUNTER = {ReactionType.like: "likes_count", ReactionType.dislike: "dislikes_count"}


@dataclass(frozen=True)
class ReactionState:
    my_reaction: ReactionType | None
    likes_count: int
    dislikes_count: int


async def _finish(
    session: AsyncSession, video: Video, my_reaction: ReactionType | None
) -> ReactionState:
    await session.commit()
    await session.refresh(video)
    return ReactionState(my_reaction, video.likes_count, video.dislikes_count)


async def set_reaction(
    session: AsyncSession, user: User, video_id: uuid.UUID, reaction: ReactionType
) -> ReactionState:
    """Safe to repeat. The video's row lock makes one user's concurrent calls take turns, so
    each sees what the last one left and the counters stay right."""
    video = await get_engageable_for_update(session, user, video_id)
    existing = await session.get(VideoReaction, (user.id, video.id))
    if existing is None:
        session.add(VideoReaction(user_id=user.id, video_id=video.id, reaction=reaction))
        await adjust_counters(session, video.id, **{_COUNTER[reaction]: 1})
    elif existing.reaction != reaction:
        await adjust_counters(
            session, video.id, **{_COUNTER[existing.reaction]: -1, _COUNTER[reaction]: 1}
        )
        existing.reaction = reaction
    return await _finish(session, video, reaction)


async def remove_reaction(
    session: AsyncSession, user: User, video_id: uuid.UUID
) -> ReactionState:
    """Safe to repeat."""
    video = await get_engageable_for_update(session, user, video_id)
    existing = await session.get(VideoReaction, (user.id, video.id))
    if existing is not None:
        await session.delete(existing)
        await adjust_counters(session, video.id, **{_COUNTER[existing.reaction]: -1})
    return await _finish(session, video, None)
