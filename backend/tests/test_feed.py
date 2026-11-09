"""GET /videos: the home feed, and D33 for it."""

import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from tests.helpers import NOT_LISTED, CreateUser, collect_pages, create_ready_video

FEED = "/api/videos"
T0 = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)


async def test_empty_feed(api: httpx.AsyncClient) -> None:
    response = await api.get(FEED)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def test_card_fields(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(
        api, session, await create_user(), published_at=T0, views_count=7
    )

    card = (await api.get(FEED)).json()["items"][0]

    url = card.pop("thumbnail_url")
    match = re.fullmatch(rf"/thumbs/(\d+)\.([0-9a-f]{{64}})/{video_id}\.jpg", url)
    assert match is not None, url
    assert security.verify_media(
        security.MEDIA_SCOPE_THUMB, video_id, match.group(1), match.group(2)
    )
    assert card == {
        "id": video_id,
        "title": "Clip",
        "duration_seconds": 5,
        "views_count": 7,
        "published_at": "2026-01-01T12:00:00.123456Z",
        "channel": {"username": "alice", "display_name": "Alice"},
    }


@pytest.mark.parametrize("state", NOT_LISTED)
@pytest.mark.parametrize("as_owner", [True, False], ids=["owner", "anonymous"])
async def test_only_listed_videos_appear(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    state: str,
    as_owner: bool,
) -> None:
    """D33: not even for the owner, whose other videos live on their channel page."""
    owner = await create_user()
    listed = await create_ready_video(api, session, owner)
    absent = await create_ready_video(api, session, owner, **NOT_LISTED[state])

    response = await api.get(FEED, headers=owner.headers if as_owner else {})

    assert [item["id"] for item in response.json()["items"]] == [listed]
    assert absent not in response.text


async def test_newest_first(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    old = await create_ready_video(api, session, owner, published_at=T0)
    new = await create_ready_video(api, session, owner, published_at=T0 + timedelta(hours=1))
    mid = await create_ready_video(api, session, owner, published_at=T0 + timedelta(minutes=1))

    assert await collect_pages(api, FEED) == [[new, mid, old]]


async def test_pages_have_no_gaps_or_duplicates(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """Some share a timestamp, so only the id tie-break keeps them in order. Microseconds
    are distinct too: rounding them in the cursor would skip or repeat a video."""
    owner = await create_user()
    times = [T0, T0, T0, T0 + timedelta(microseconds=1), T0 + timedelta(microseconds=2)]
    ids = [await create_ready_video(api, session, owner, published_at=at) for at in times]

    pages = await collect_pages(api, FEED, limit=2)

    assert [len(page) for page in pages] == [2, 2, 1]
    walked = [video_id for page in pages for video_id in page]
    assert len(set(walked)) == len(walked)
    assert set(walked) == set(ids)
    assert walked == [video_id for page in await collect_pages(api, FEED) for video_id in page]


async def test_exact_limit_has_no_next_page(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    await create_ready_video(api, session, owner)
    await create_ready_video(api, session, owner)

    body = (await api.get(FEED, params={"limit": 2})).json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "nonsense"},
        {"cursor": "123_not-a-uuid"},
        {"cursor": "99999999999999999_00000000-0000-0000-0000-000000000000"},
        {"limit": 0},
        {"limit": 101},
    ],
    ids=["garbage", "bad-uuid", "huge-timestamp", "limit-zero", "limit-too-big"],
)
async def test_bad_paging_params_are_rejected(
    api: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    assert (await api.get(FEED, params=params)).status_code == 422
