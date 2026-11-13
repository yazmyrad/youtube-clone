"""POST /videos/{id}/view: counting views (D52) and keeping watch history."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import Video, VideoView, WatchHistory
from app.services.views import seconds_to_count
from tests.helpers import NOT_LISTED, ApiUser, CreateUser, create_ready_video

ANON = {"X-Real-IP": "203.0.113.7", "User-Agent": "Firefox"}


async def _view(
    api: httpx.AsyncClient,
    video_id: str,
    user: ApiUser | None = None,
    *,
    watched: int = 60,
    position: int = 10,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await api.post(
        f"/api/videos/{video_id}/view",
        headers={**ANON, **(headers or {}), **(user.headers if user else {})},
        json={"watched_seconds": watched, "position_seconds": position},
    )


async def _views(session: AsyncSession, video_id: str) -> tuple[int, int]:
    """The stored count and a recount of the rows behind it."""
    session.expire_all()
    vid = uuid.UUID(video_id)
    stored = await session.scalar(select(Video.views_count).where(Video.id == vid))
    rows = await session.scalar(
        select(func.count()).select_from(VideoView).where(VideoView.video_id == vid)
    )
    return stored or 0, rows or 0


@pytest.mark.parametrize(("duration", "needed"), [(100, 30), (40, 20), (5, 3), (1, 1)])
def test_a_view_needs_30_seconds_or_half_the_video(duration: int, needed: int) -> None:
    assert seconds_to_count(duration) == needed


async def test_counts_a_view_once_enough_is_watched(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"), duration_seconds=100)

    early = await _view(api, video, watched=29)
    enough = await _view(api, video, watched=30)

    assert early.status_code == 200, early.text
    assert early.json() == {"counted": False, "views_count": 0}
    assert enough.json() == {"counted": True, "views_count": 1}
    assert await _views(session, video) == (1, 1)


async def test_repeat_views_on_one_day_count_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D52, for a signed-in viewer, whatever address they come from."""
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)

    first = await _view(api, video, bob)
    again = await _view(api, video, bob, headers={"X-Real-IP": "198.51.100.1"})

    assert (first.json()["counted"], again.json()["counted"]) == (True, False)
    assert await _views(session, video) == (1, 1)


async def test_anonymous_viewers_are_told_apart_by_address_and_browser(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))

    results = [
        (await _view(api, video, headers=headers)).json()["counted"]
        for headers in (
            {},
            {},  # The same visitor again.
            {"X-Real-IP": "198.51.100.1"},
            {"User-Agent": "Safari"},
        )
    ]

    assert results == [True, False, True, True]
    assert await _views(session, video) == (3, 3)


async def test_signed_in_and_anonymous_count_apart(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice)

    await _view(api, video)
    await _view(api, video, await create_user("bob"))

    assert await _views(session, video) == (2, 2)


async def test_a_new_day_counts_again(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    session.add(
        VideoView(
            video_id=uuid.UUID(video),
            viewer_key=security.viewer_key(uuid.UUID(bob.id), "", ""),
            day=yesterday,
        )
    )
    await session.commit()

    assert (await _view(api, video, bob)).json()["counted"] is True


async def test_concurrent_heartbeats_count_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)

    responses = await asyncio.gather(*(_view(api, video, bob) for _ in range(5)))

    assert sorted(r.json()["counted"] for r in responses) == [False] * 4 + [True]
    assert await _views(session, video) == (1, 1)


async def test_the_raw_address_is_never_stored(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))

    await _view(api, video)

    key = await session.scalar(select(VideoView.viewer_key))
    assert key is not None
    assert len(key) == 32
    assert ANON["X-Real-IP"].encode() not in key


async def test_keeps_a_signed_in_viewers_place(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice, duration_seconds=100)

    await _view(api, video, bob, watched=5, position=5)
    first = await session.scalar(select(WatchHistory.last_watched_at))
    await _view(api, video, bob, watched=40, position=250)

    session.expire_all()
    row = await session.scalar(select(WatchHistory))
    assert row is not None
    assert (str(row.user_id), str(row.video_id)) == (bob.id, video)
    assert row.progress_seconds == 100  # Never past the end.
    assert first is not None
    assert row.last_watched_at > first


async def test_anonymous_viewers_have_no_history(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))

    await _view(api, video)

    assert await session.scalar(select(func.count()).select_from(WatchHistory)) == 0


@pytest.mark.parametrize("state", ["private", "hidden", "deleted"])
async def test_a_video_you_cant_watch_gets_no_view(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice, **NOT_LISTED[state])

    response = await _view(api, video, bob)

    assert response.status_code == 404
    assert await _views(session, video) == (0, 0)
    assert await session.scalar(select(func.count()).select_from(WatchHistory)) == 0


async def test_an_unready_video_gets_no_view(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice, **NOT_LISTED["processing"])

    assert (await _view(api, video, alice)).status_code == 409


async def test_a_shared_private_video_counts(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice, visibility="private")
    await api.put(f"/api/videos/{video}/access/bob", headers=alice.headers)

    assert (await _view(api, video, bob)).json()["counted"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"watched_seconds": -1, "position_seconds": 0},
        {"watched_seconds": 0, "position_seconds": 86_401},
        {"watched_seconds": 1},
        {"watched_seconds": 1, "position_seconds": 1, "views": 100},
    ],
)
async def test_validates_the_heartbeat(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    body: dict[str, int],
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))

    response = await api.post(f"/api/videos/{video}/view", json=body)

    assert response.status_code == 422


async def test_watching_your_own_video_adds_no_view(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice)

    response = await _view(api, video, alice)

    assert response.json() == {"counted": False, "views_count": 0}
    assert await _views(session, video) == (0, 0)
    assert await session.scalar(select(func.count()).select_from(WatchHistory)) == 1
