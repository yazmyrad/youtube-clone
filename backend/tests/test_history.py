"""GET and DELETE /users/me/history."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Video, WatchHistory
from tests.helpers import NOT_LISTED, ApiUser, CreateUser, create_ready_video

HISTORY = "/api/users/me/history"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _watch(api: httpx.AsyncClient, user: ApiUser, video_id: str, position: int = 2) -> None:
    response = await api.post(
        f"/api/videos/{video_id}/view",
        headers=user.headers,
        json={"watched_seconds": 1, "position_seconds": position},
    )
    assert response.status_code == 200, response.text


async def _ids(api: httpx.AsyncClient, user: ApiUser) -> list[str]:
    response = await api.get(HISTORY, headers=user.headers)
    assert response.status_code == 200, response.text
    return [item["video"]["id"] for item in response.json()["items"]]


async def test_most_recently_watched_first(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    a = await create_ready_video(api, session, alice)
    b = await create_ready_video(api, session, alice)
    await _watch(api, bob, a, position=3)
    await _watch(api, bob, b)
    await _watch(api, bob, a, position=4)  # Watched again: back to the top.
    await _watch(api, alice, b)  # Someone else's history.

    response = await api.get(HISTORY, headers=bob.headers)

    assert [item["video"]["id"] for item in response.json()["items"]] == [a, b]
    first = response.json()["items"][0]
    assert first["progress_seconds"] == 4
    assert first["video"]["channel"]["username"] == "alice"
    assert first["video"]["thumbnail_url"].startswith("/thumbs/")


@pytest.mark.parametrize("state", ["private", "hidden", "deleted"])
async def test_a_video_you_can_no_longer_watch_drops_out(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)
    await _watch(api, bob, video)

    await session.execute(
        update(Video).where(Video.id == uuid.UUID(video)).values(NOT_LISTED[state])
    )
    await session.commit()

    response = await api.get(HISTORY, headers=bob.headers)
    assert video not in response.text


async def test_pages_cover_every_entry_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    videos = [await create_ready_video(api, session, alice) for _ in range(5)]
    for i, video in enumerate(videos):
        await _watch(api, bob, video)
        await session.execute(
            update(WatchHistory)
            .where(WatchHistory.video_id == uuid.UUID(video))
            .values(last_watched_at=T0 + timedelta(minutes=i))
        )
    await session.commit()

    seen: list[str] = []
    sizes = []
    cursor = None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        body = (await api.get(HISTORY, headers=bob.headers, params=params)).json()
        seen += [item["video"]["id"] for item in body["items"]]
        sizes.append(len(body["items"]))
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert sizes == [2, 2, 1]
    assert seen == videos[::-1]


async def test_remove_one_entry(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    a = await create_ready_video(api, session, alice)
    b = await create_ready_video(api, session, alice)
    await _watch(api, bob, a)
    await _watch(api, bob, b)

    removed = await api.delete(f"{HISTORY}/{a}", headers=bob.headers)
    again = await api.delete(f"{HISTORY}/{a}", headers=bob.headers)

    assert (removed.status_code, again.status_code) == (204, 204)
    assert await _ids(api, bob) == [b]


async def test_clear_only_your_own(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)
    await _watch(api, bob, video)
    await _watch(api, alice, video)

    response = await api.delete(HISTORY, headers=bob.headers)

    assert response.status_code == 204
    assert await _ids(api, bob) == []
    assert await _ids(api, alice) == [video]


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", ""), ("delete", ""), ("delete", f"/{uuid.uuid4()}")],
)
async def test_needs_sign_in(api: httpx.AsyncClient, method: str, path: str) -> None:
    assert (await api.request(method, f"{HISTORY}{path}")).status_code == 401
