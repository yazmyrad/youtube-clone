"""Shorts: which videos are Shorts, where they're listed, and where they aren't."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.helpers import NOT_LISTED, ApiUser, CreateUser, create_ready_video

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
VERTICAL = {"width": 1080, "height": 1920, "duration_seconds": 30}
WIDE = {"width": 1920, "height": 1080, "duration_seconds": 30}


async def _ids(api: httpx.AsyncClient, url: str, user: ApiUser | None = None) -> list[str]:
    response = await api.get(url, headers=user.headers if user else {})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


@pytest.mark.parametrize(
    ("size", "short"),
    [
        (VERTICAL, True),
        ({"width": 720, "height": 1280, "duration_seconds": 180}, True),
        ({"width": 720, "height": 1280, "duration_seconds": 181}, False),
        ({"width": 1080, "height": 1080, "duration_seconds": 30}, False),
        (WIDE, False),
        ({"width": None, "height": None, "duration_seconds": 30}, False),
    ],
)
async def test_a_short_is_vertical_and_at_most_three_minutes(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    size: dict[str, int | None],
    short: bool,
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"), **size)

    details = (await api.get(f"/api/videos/{video}")).json()
    shorts = await _ids(api, "/api/videos/shorts")
    home = await _ids(api, "/api/videos")

    assert details["is_short"] is short
    assert (video in shorts, video in home) == (short, not short)


async def test_details_carry_the_size(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"), **VERTICAL)

    details = (await api.get(f"/api/videos/{video}")).json()

    assert (details["width"], details["height"]) == (1080, 1920)


async def test_shorts_newest_first_with_pages(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    made = [
        await create_ready_video(
            api, session, alice, published_at=T0 + timedelta(minutes=i), **VERTICAL
        )
        for i in range(3)
    ]

    first = (await api.get("/api/videos/shorts", params={"limit": 2})).json()
    second = (
        await api.get("/api/videos/shorts", params={"limit": 2, "cursor": first["next_cursor"]})
    ).json()

    assert [v["id"] for v in first["items"] + second["items"]] == made[::-1]
    assert second["next_cursor"] is None
    assert all(item["is_short"] for item in first["items"])


@pytest.mark.parametrize("state", NOT_LISTED)
async def test_the_shorts_feed_shows_only_listed_shorts(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    """D33, for Shorts."""
    alice = await create_user("alice")
    listed = await create_ready_video(api, session, alice, **VERTICAL)
    other = await create_ready_video(api, session, alice, **{**VERTICAL, **NOT_LISTED[state]})

    assert await _ids(api, "/api/videos/shorts") == [listed]
    assert other not in await _ids(api, "/api/videos/shorts")


async def test_a_disabled_users_shorts_leave_the_feed(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    await create_ready_video(api, session, alice, **VERTICAL)

    await session.execute(
        update(User).where(User.id == uuid.UUID(alice.id)).values(is_active=False)
    )
    await session.commit()

    assert await _ids(api, "/api/videos/shorts") == []


async def test_a_channel_lists_shorts_apart_from_videos(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    short = await create_ready_video(api, session, alice, **VERTICAL)
    wide = await create_ready_video(api, session, alice, **WIDE)
    private_short = await create_ready_video(
        api, session, alice, **{**VERTICAL, "visibility": "private"}
    )

    assert await _ids(api, "/api/channels/alice/videos") == [wide]
    assert await _ids(api, "/api/channels/alice/shorts", bob) == [short]
    assert set(await _ids(api, "/api/channels/alice/shorts", alice)) == {short, private_short}


async def test_the_subscriptions_feed_leaves_shorts_out(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await create_ready_video(api, session, alice, **VERTICAL)
    wide = await create_ready_video(api, session, alice, **WIDE)
    await api.put("/api/channels/alice/subscription", headers=bob.headers)

    assert await _ids(api, "/api/feed/subscriptions", bob) == [wide]


async def test_search_finds_shorts_and_says_so(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    short = await create_ready_video(api, session, alice, **VERTICAL)
    await api.patch(f"/api/videos/{short}", headers=alice.headers, json={"title": "Waterfall"})

    items = (await api.get("/api/search/videos", params={"q": "waterfall"})).json()["items"]

    assert [(item["id"], item["is_short"]) for item in items] == [(short, True)]
