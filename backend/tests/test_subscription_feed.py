"""GET /feed/subscriptions, and D33 for it."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import NOT_LISTED, ApiUser, CreateUser, create_ready_video

FEED = "/api/feed/subscriptions"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _subscribe(api: httpx.AsyncClient, user: ApiUser, channel: str) -> None:
    response = await api.put(f"/api/channels/{channel}/subscription", headers=user.headers)
    assert response.status_code == 200, response.text


async def _ids(api: httpx.AsyncClient, user: ApiUser, **params: object) -> list[str]:
    response = await api.get(FEED, headers=user.headers, params=params)
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def test_only_subscribed_channels_newest_first(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, carol, dave = (
        await create_user("alice"),
        await create_user("carol"),
        await create_user("dave"),
    )
    bob = await create_user("bob")
    a = await create_ready_video(api, session, alice, published_at=T0)
    c = await create_ready_video(api, session, carol, published_at=T0 + timedelta(hours=1))
    await create_ready_video(api, session, dave)
    await create_ready_video(api, session, bob)  # Their own.
    await _subscribe(api, bob, "alice")
    await _subscribe(api, bob, "carol")
    await _subscribe(api, await create_user("erin"), "dave")  # Someone else's.

    assert await _ids(api, bob) == [c, a]


async def test_empty_without_subscriptions(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_ready_video(api, session, await create_user("alice"))

    assert await _ids(api, await create_user("bob")) == []


async def test_unsubscribing_drops_the_channel(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await create_ready_video(api, session, alice)
    await _subscribe(api, bob, "alice")

    await api.delete("/api/channels/alice/subscription", headers=bob.headers)

    assert await _ids(api, bob) == []


@pytest.mark.parametrize("state", NOT_LISTED)
async def test_subscribing_gives_no_extra_access(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    """D33: only what the home feed would show, even from a subscribed channel."""
    alice, bob = await create_user("alice"), await create_user("bob")
    listed = await create_ready_video(api, session, alice)
    await create_ready_video(api, session, alice, **NOT_LISTED[state])
    await _subscribe(api, bob, "alice")

    assert await _ids(api, bob) == [listed]


async def test_pages_cover_every_video_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    made = [
        await create_ready_video(api, session, alice, published_at=T0 + timedelta(minutes=i))
        for i in range(5)
    ]
    await _subscribe(api, bob, "alice")

    seen: list[list[str]] = []
    cursor = None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        body = (await api.get(FEED, headers=bob.headers, params=params)).json()
        seen.append([item["id"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert [len(page) for page in seen] == [2, 2, 1]
    assert [video for page in seen for video in page] == made[::-1]


async def test_needs_sign_in(api: httpx.AsyncClient) -> None:
    assert (await api.get(FEED)).status_code == 401
