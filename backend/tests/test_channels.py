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


# --- Sort chips, totals and the channel's search box --------------------------------------


@pytest.mark.parametrize("path", ["videos", "shorts"])
async def test_sorted_latest_popular_and_oldest_across_pages(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, path: str
) -> None:
    alice = await create_user("alice")
    shape = {"width": 1080, "height": 1920} if path == "shorts" else {}
    # Ties on views, so the id has to break them for paging to be exact.
    views = [5, 50, 5, 500, 0]
    made = [
        await create_ready_video(
            api,
            session,
            alice,
            published_at=T0 + timedelta(minutes=i),
            views_count=count,
            **shape,
        )
        for i, count in enumerate(views)
    ]
    url = f"/api/channels/alice/{path}"

    def flat(pages: list[list[str]]) -> list[str]:
        return [video for page in pages for video in page]

    latest = flat(await collect_pages(api, url, limit=2))
    oldest = flat(await collect_pages(api, url, limit=2, sort="oldest"))
    popular = flat(await collect_pages(api, url, limit=2, sort="popular"))

    assert latest == made[::-1]
    assert oldest == made
    by_views = sorted(zip(views, made, strict=True), key=lambda v: (v[0], v[1]), reverse=True)
    assert popular == [video for _, video in by_views]


async def test_an_unknown_sort_is_refused(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")

    response = await api.get("/api/channels/alice/videos", params={"sort": "random"})

    assert response.status_code == 422


async def test_totals_count_only_public_videos(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    await create_ready_video(api, session, alice, views_count=10)
    await create_ready_video(api, session, alice, views_count=5, width=1080, height=1920)
    for hidden in NOT_LISTED.values():
        await create_ready_video(api, session, alice, views_count=1000, **hidden)

    # The owner sees the same numbers as everyone: the About box is public.
    for headers in ({}, alice.headers):
        body = (await api.get("/api/channels/alice", headers=headers)).json()
        assert (body["videos_count"], body["views_count"]) == (2, 15)


async def test_a_new_channel_has_no_videos_or_views(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    await create_user("alice")

    body = (await api.get("/api/channels/alice")).json()

    assert (body["videos_count"], body["views_count"]) == (0, 0)


async def test_search_finds_the_channels_videos_and_shorts_only(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    bob = await create_user("bob")
    video = await create_ready_video(api, session, alice, title="Rust in 100 seconds")
    short = await create_ready_video(
        api, session, alice, title="RUST tips", width=1080, height=1920, published_at=T0
    )
    await create_ready_video(api, session, alice, title="Go in 100 seconds")
    await create_ready_video(api, session, bob, title="Rust by Bob")

    found = _ids(await api.get("/api/channels/alice/search", params={"q": "rust"}))

    assert found == [video, short]


@pytest.mark.parametrize("hidden", NOT_LISTED.values(), ids=NOT_LISTED.keys())
async def test_search_shows_others_only_listed_videos(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    hidden: dict[str, object],
) -> None:
    alice = await create_user("alice")
    bob = await create_user("bob")
    await create_ready_video(api, session, alice, title="Secret plans", **hidden)

    for headers in ({}, bob.headers):
        found = _ids(
            await api.get("/api/channels/alice/search", params={"q": "secret"}, headers=headers)
        )
        assert found == []


async def test_search_shows_the_owner_their_private_videos(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    private = await create_ready_video(
        api, session, alice, title="Secret plans", **NOT_LISTED["private"]
    )

    found = _ids(
        await api.get("/api/channels/alice/search", params={"q": "secret"}, headers=alice.headers)
    )

    assert found == [private]


@pytest.mark.parametrize("q", ["", "x", "a" * 101])
async def test_search_needs_a_sensible_query(
    api: httpx.AsyncClient, create_user: CreateUser, q: str
) -> None:
    await create_user("alice")

    response = await api.get("/api/channels/alice/search", params={"q": q})

    assert response.status_code == 422


async def test_search_of_an_unknown_channel_is_404(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/channels/nobody/search", params={"q": "rust"})

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("cursor_from", "used_with"),
    [("popular", "latest"), ("latest", "popular"), ("popular", "oldest")],
)
async def test_a_cursor_only_works_in_its_own_order(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    cursor_from: str,
    used_with: str,
) -> None:
    alice = await create_user("alice")
    for i in range(3):
        await create_ready_video(api, session, alice, published_at=T0 + timedelta(minutes=i))
    first = await api.get("/api/channels/alice/videos", params={"limit": 1, "sort": cursor_from})
    cursor = first.json()["next_cursor"]

    response = await api.get(
        "/api/channels/alice/videos", params={"limit": 1, "sort": used_with, "cursor": cursor}
    )

    assert response.status_code == 400


async def test_a_popular_cursor_elsewhere_is_refused_not_a_crash(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    cursor = "p5_00000000-0000-0000-0000-000000000000"

    response = await api.get(
        "/api/users/me/history", params={"cursor": cursor}, headers=alice.headers
    )

    assert response.status_code == 400
