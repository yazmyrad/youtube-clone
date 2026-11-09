"""D51: denormalized counters match a recount from source rows."""

import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment, ReactionType, Video, VideoReaction
from tests.helpers import ApiUser, CreateUser, create_ready_video


async def _assert_counters_match(session: AsyncSession, video_id: str) -> None:
    vid = uuid.UUID(video_id)

    async def reactions(kind: ReactionType) -> int | None:
        return await session.scalar(
            select(func.count())
            .select_from(VideoReaction)
            .where(VideoReaction.video_id == vid, VideoReaction.reaction == kind)
        )

    comments = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.video_id == vid)
    )
    stored = (
        await session.execute(
            select(Video.likes_count, Video.dislikes_count, Video.comments_count).where(
                Video.id == vid
            )
        )
    ).one()

    assert tuple(stored) == (
        await reactions(ReactionType.like),
        await reactions(ReactionType.dislike),
        comments,
    )


async def test_counters_match_a_recount_after_mixed_actions(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user("owner"))
    other_video = await create_ready_video(api, session, await create_user("other"))
    ana, ben, cyd = [await create_user(name) for name in ("anaaa", "benny", "cydia")]
    reaction_url = f"/api/videos/{video_id}/reaction"
    comments_url = f"/api/videos/{video_id}/comments"

    async def react(user: ApiUser, kind: str, url: str = reaction_url) -> None:
        response = await api.put(url, headers=user.headers, json={"reaction": kind})
        assert response.status_code == 200, response.text

    async def comment(user: ApiUser, url: str = comments_url) -> str:
        response = await api.post(url, headers=user.headers, json={"body": "Hi"})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    await react(ana, "like")
    await react(ben, "like")
    await react(cyd, "dislike")
    await react(ana, "like")  # A repeat.
    await react(ben, "dislike")  # A switch.
    await api.delete(reaction_url, headers=cyd.headers)  # A removal.
    await api.delete(reaction_url, headers=cyd.headers)  # A repeated removal.
    await react(ana, "dislike", f"/api/videos/{other_video}/reaction")  # Elsewhere.
    first = await comment(ana)
    await comment(ben)
    await comment(cyd)
    await comment(ana, f"/api/videos/{other_video}/comments")  # Elsewhere.
    await api.delete(f"/api/comments/{first}", headers=ana.headers)
    await api.delete(f"/api/comments/{first}", headers=ana.headers)  # A repeat.

    await _assert_counters_match(session, video_id)
    await _assert_counters_match(session, other_video)
    body = (await api.get(f"/api/videos/{video_id}")).json()
    assert (body["likes_count"], body["dislikes_count"], body["comments_count"]) == (1, 1, 2)
