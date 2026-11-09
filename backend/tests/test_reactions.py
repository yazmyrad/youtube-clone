"""PUT and DELETE /videos/{id}/reaction: D50, and who may react."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole, Video, VideoStatus, VideoVisibility
from tests.helpers import ApiUser, CreateUser, SetRole, create_ready_video


async def _react(
    api: httpx.AsyncClient, video_id: str, user: ApiUser, reaction: str = "like"
) -> httpx.Response:
    return await api.put(
        f"/api/videos/{video_id}/reaction", headers=user.headers, json={"reaction": reaction}
    )


async def _unreact(api: httpx.AsyncClient, video_id: str, user: ApiUser) -> httpx.Response:
    return await api.delete(f"/api/videos/{video_id}/reaction", headers=user.headers)


async def _counts(api: httpx.AsyncClient, video_id: str) -> tuple[int, int]:
    body = (await api.get(f"/api/videos/{video_id}")).json()
    return body["likes_count"], body["dislikes_count"]


async def test_liking_returns_the_new_state(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")

    response = await _react(api, video_id, fan)

    assert response.status_code == 200, response.text
    assert response.json() == {"my_reaction": "like", "likes_count": 1, "dislikes_count": 0}


async def test_liking_twice_counts_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D50."""
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")

    await _react(api, video_id, fan)
    await _react(api, video_id, fan)

    assert await _counts(api, video_id) == (1, 0)


async def test_switching_moves_the_count(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D50."""
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")

    await _react(api, video_id, fan, "like")
    response = await _react(api, video_id, fan, "dislike")

    assert response.json() == {"my_reaction": "dislike", "likes_count": 0, "dislikes_count": 1}
    assert await _counts(api, video_id) == (0, 1)


async def test_removing_is_safe_to_repeat(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")
    await _react(api, video_id, fan)

    first = await _unreact(api, video_id, fan)
    second = await _unreact(api, video_id, fan)

    expected = {"my_reaction": None, "likes_count": 0, "dislikes_count": 0}
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == expected


async def test_removing_a_reaction_never_made_changes_nothing(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())
    await _react(api, video_id, await create_user("bobby"))

    await _unreact(api, video_id, await create_user("carol"))

    assert await _counts(api, video_id) == (1, 0)


async def test_concurrent_likes_by_many_users(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D50."""
    video_id = await create_ready_video(api, session, await create_user())
    fans = [await create_user(f"fan{i}") for i in range(6)]

    responses = await asyncio.gather(*(_react(api, video_id, fan) for fan in fans))

    assert [r.status_code for r in responses] == [200] * 6
    assert await _counts(api, video_id) == (6, 0)


async def test_concurrent_repeats_by_one_user(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D50: racing like and dislike leaves exactly one reaction, whichever came last."""
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")
    reactions = ["like", "dislike"] * 4

    responses = await asyncio.gather(*(_react(api, video_id, fan, r) for r in reactions))

    assert [r.status_code for r in responses] == [200] * 8
    assert sum(await _counts(api, video_id)) == 1


async def test_unknown_reaction_is_rejected(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

    response = await _react(api, video_id, await create_user("bobby"), "love")

    assert response.status_code == 422


async def test_missing_video_is_404(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    assert (await _react(api, str(uuid.uuid4()), await create_user())).status_code == 404


async def test_stranger_cant_react_to_a_private_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(
        api, session, await create_user(), visibility=VideoVisibility.private
    )

    assert (await _react(api, video_id, await create_user("bobby"))).status_code == 404


async def test_allowlisted_user_can_react_to_a_private_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    video_id = await create_ready_video(api, session, owner, visibility=VideoVisibility.private)
    await api.put(f"/api/videos/{video_id}/access/{friend.username}", headers=owner.headers)

    assert (await _react(api, video_id, friend)).status_code == 200


@pytest.mark.parametrize("actor", ["owner", "moderator", "admin"])
async def test_nobody_reacts_to_a_hidden_video(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    actor: str,
) -> None:
    owner = await create_user("owner")
    video_id = await create_ready_video(api, session, owner, hidden_at=datetime.now(UTC))
    caller = owner
    if actor != "owner":
        caller = await create_user("staff")
        await set_role(caller, UserRole(actor))

    assert (await _react(api, video_id, caller)).status_code == 404
    assert (await _unreact(api, video_id, caller)).status_code == 404


async def test_owner_cant_react_before_the_video_is_ready(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    values: dict[str, Any] = {"status": VideoStatus.processing, "published_at": None}
    video_id = await create_ready_video(api, session, owner, **values)

    assert (await _react(api, video_id, owner)).status_code == 409


async def test_a_reaction_isnt_an_edit_of_the_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())
    updated_at = select(Video.updated_at).where(Video.id == uuid.UUID(video_id))
    before = await session.scalar(updated_at)
    await session.commit()

    await _react(api, video_id, await create_user("bobby"))

    assert await session.scalar(updated_at) == before


async def test_details_show_the_callers_own_reaction(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")
    other = await create_user("carol")
    await _react(api, video_id, fan, "dislike")

    async def seen(user: ApiUser | None) -> str | None:
        headers = user.headers if user else {}
        return (await api.get(f"/api/videos/{video_id}", headers=headers)).json()["my_reaction"]

    assert await seen(fan) == "dislike"
    assert await seen(other) is None
    assert await seen(None) is None
