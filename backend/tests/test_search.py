"""GET /search/videos: D59, and D33 for search."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import NOT_LISTED, ApiUser, CreateUser, collect_pages, create_ready_video

SEARCH = "/api/search/videos"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def _titled(
    api: httpx.AsyncClient, session: AsyncSession, owner: ApiUser, title: str, **values: object
) -> str:
    return await create_ready_video(api, session, owner, title=title, **values)


async def _found(api: httpx.AsyncClient, q: str) -> list[str]:
    response = await api.get(SEARCH, params={"q": q})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


@pytest.mark.parametrize("q", ["Cooking", "cook", "OOKIN", "pasta at", "  pasta  "])
async def test_finds_a_part_of_the_title_ignoring_case(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, q: str
) -> None:
    """D59."""
    owner = await create_user()
    match = await _titled(api, session, owner, "Cooking pasta at home")
    await _titled(api, session, owner, "Garden tour")

    assert await _found(api, q) == [match]


@pytest.mark.parametrize(
    ("q", "title", "other"),
    [("0%", "Save 50% today", "Save 500 today"), ("a_b", "a_b notes", "axb notes")],
    ids=["percent", "underscore"],
)
async def test_wildcards_are_literal(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    q: str,
    title: str,
    other: str,
) -> None:
    """D59: without escaping, `0%` and `a_b` would also match the other title."""
    owner = await create_user()
    match = await _titled(api, session, owner, title)
    await _titled(api, session, owner, other)

    assert await _found(api, q) == [match]


async def test_the_escape_character_is_literal(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    match = await _titled(api, session, owner, "either/or")
    await _titled(api, session, owner, "either or")

    assert await _found(api, "r/o") == [match]


@pytest.mark.parametrize("state", NOT_LISTED)
@pytest.mark.parametrize("as_owner", [True, False], ids=["owner", "anonymous"])
async def test_only_listed_videos_are_found(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    state: str,
    as_owner: bool,
) -> None:
    """D33."""
    owner = await create_user()
    listed = await _titled(api, session, owner, "Secret plans")
    absent = await _titled(api, session, owner, "Secret plans", **NOT_LISTED[state])

    response = await api.get(
        SEARCH, params={"q": "secret"}, headers=owner.headers if as_owner else {}
    )

    assert [item["id"] for item in response.json()["items"]] == [listed]
    assert absent not in response.text


async def test_pages_newest_first_within_the_matches(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    ids = [
        await _titled(api, session, owner, "Match", published_at=T0 + timedelta(minutes=i))
        for i in range(3)
    ]
    await _titled(api, session, owner, "Other", published_at=T0 + timedelta(minutes=9))

    assert await collect_pages(api, SEARCH, q="match", limit=2) == [[ids[2], ids[1]], [ids[0]]]


@pytest.mark.parametrize(
    "params",
    [{}, {"q": "a"}, {"q": "    "}, {"q": " a "}, {"q": "x" * 101}, {"q": "ab\x00"}],
    ids=["missing", "one-char", "only-spaces", "one-char-padded", "too-long", "nul"],
)
async def test_bad_queries_are_rejected(
    api: httpx.AsyncClient, params: dict[str, str]
) -> None:
    assert (await api.get(SEARCH, params=params)).status_code == 422


async def test_bad_cursor_is_rejected(api: httpx.AsyncClient) -> None:
    response = await api.get(SEARCH, params={"q": "clip", "cursor": "nonsense"})

    assert response.status_code == 422
