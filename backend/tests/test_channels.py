"""GET /channels/{username} and its videos, and D33 for channel pages."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription
from app.models.user import UserRole
from tests.helpers import NOT_LISTED, CreateUser, SetRole, collect_pages, create_ready_video

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def test_channel_details(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    alice = await create_user("alice")
    await api.patch("/api/users/me", headers=alice.headers, json={"description": "Hi there"})

    response = await api.get("/api/channels/alice")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["description"] == "Hi there"
    assert body["subscribers_count"] == 0
    assert body["is_subscribed"] is False
    assert "email" not in body
    assert "role" not in body


async def test_username_is_case_insensitive(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    await create_user("alice")

    assert (await api.get("/api/channels/ALICE")).json()["username"] == "alice"


async def test_is_subscribed_reflects_the_caller(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob, carol = (
        await create_user("alice"),
        await create_user("bob"),
        await create_user("carol"),
    )
    session.add(Subscription(subscriber_id=bob.id, channel_id=alice.id))
    await session.commit()

    as_bob = await api.get("/api/channels/alice", headers=bob.headers)
    as_carol = await api.get("/api/channels/alice", headers=carol.headers)

    assert as_bob.json()["is_subscribed"] is True
    assert as_carol.json()["is_subscribed"] is False


@pytest.mark.parametrize("path", ["", "/videos"])
async def test_unknown_channel_is_404(api: httpx.AsyncClient, path: str) -> None:
    response = await api.get(f"/api/channels/nobody{path}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Channel not found"


async def test_lists_only_that_channels_videos_newest_first(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    old = await create_ready_video(api, session, alice, published_at=T0)
    new = await create_ready_video(api, session, alice, published_at=T0 + timedelta(days=1))
    await create_ready_video(api, session, bob)

    response = await api.get("/api/channels/alice/videos")

    assert _ids(response) == [new, old]
    item = response.json()["items"][0]
    assert item["channel"]["username"] == "alice"
    assert item["visibility"] == "public"
    assert item["thumbnail_url"].startswith("/thumbs/")


@pytest.mark.parametrize("state", NOT_LISTED)
@pytest.mark.parametrize("viewer", ["anonymous", "other user", "moderator", "admin"])
async def test_others_see_only_listed_videos(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    state: str,
    viewer: str,
) -> None:
    """D33: a channel page shows others exactly what the feed would."""
    alice = await create_user("alice")
    listed = await create_ready_video(api, session, alice)
    absent = await create_ready_video(api, session, alice, **NOT_LISTED[state])
    headers = {}
    if viewer != "anonymous":
        other = await create_user("bob")
        if viewer in ("moderator", "admin"):
            await set_role(other, UserRole(viewer))
        headers = other.headers

    response = await api.get("/api/channels/alice/videos", headers=headers)

    assert _ids(response) == [listed]
    assert absent not in response.text


@pytest.mark.parametrize(
    ("state", "shown"),
    [
        ("unlisted", True),
        ("private", True),
        ("hidden", False),
        ("processing", False),
        ("deleted", False),
    ],
)
async def test_the_owner_also_sees_their_private_and_unlisted_videos(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    state: str,
    shown: bool,
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice, **NOT_LISTED[state])

    response = await api.get("/api/channels/alice/videos", headers=alice.headers)

    assert _ids(response) == ([video] if shown else [])
    if shown:
        assert response.json()["items"][0]["visibility"] == state


async def test_pages_cover_every_video_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    made = [
        await create_ready_video(api, session, alice, published_at=T0 + timedelta(minutes=i))
        for i in range(5)
    ]

    pages = await collect_pages(api, "/api/channels/alice/videos", limit=2)

    assert [len(page) for page in pages] == [2, 2, 1]
    assert [video for page in pages for video in page] == made[::-1]
