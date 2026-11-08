"""Managing the private allowlist. test_permission_matrix.py covers who else may try."""

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Video, VideoAccess
from tests.helpers import ApiUser, CreateUser


@pytest.fixture
async def owner(create_user: CreateUser) -> ApiUser:
    return await create_user("alice")


@pytest.fixture
async def friend(create_user: CreateUser) -> ApiUser:
    return await create_user("bobby")


@pytest.fixture
async def video_id(api: httpx.AsyncClient, owner: ApiUser) -> str:
    created = await api.post("/api/videos", headers=owner.headers, json={"title": "Clip"})
    assert created.status_code == 201, created.text
    return created.json()["video"]["id"]


def _url(video_id: str, username: str | None = None) -> str:
    return f"/api/videos/{video_id}/access" + (f"/{username}" if username else "")


async def _usernames(api: httpx.AsyncClient, owner: ApiUser, video_id: str) -> list[str]:
    response = await api.get(_url(video_id), headers=owner.headers)
    assert response.status_code == 200, response.text
    return [item["username"] for item in response.json()["items"]]


async def test_a_new_video_has_an_empty_allowlist(
    api: httpx.AsyncClient, owner: ApiUser, video_id: str
) -> None:
    response = await api.get(_url(video_id), headers=owner.headers)

    assert response.json() == {"items": [], "next_cursor": None}


async def test_grant_returns_the_entry_and_lists_it(
    api: httpx.AsyncClient, owner: ApiUser, friend: ApiUser, video_id: str
) -> None:
    response = await api.put(_url(video_id, friend.username), headers=owner.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == friend.username
    assert body["display_name"] == "Bobby"
    assert datetime.fromisoformat(body["granted_at"])
    assert set(body) == {"username", "display_name", "granted_at"}
    assert await _usernames(api, owner, video_id) == [friend.username]


async def test_granting_twice_keeps_one_entry(
    api: httpx.AsyncClient, owner: ApiUser, friend: ApiUser, video_id: str
) -> None:
    url = _url(video_id, friend.username)

    first = await api.put(url, headers=owner.headers)
    second = await api.put(url, headers=owner.headers)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert await _usernames(api, owner, video_id) == [friend.username]


async def test_concurrent_grants_keep_one_entry(
    api: httpx.AsyncClient,
    session: AsyncSession,
    owner: ApiUser,
    friend: ApiUser,
    video_id: str,
) -> None:
    url = _url(video_id, friend.username)

    responses = await asyncio.gather(*(api.put(url, headers=owner.headers) for _ in range(5)))

    assert [r.status_code for r in responses] == [200] * 5
    assert await session.scalar(select(func.count()).select_from(VideoAccess)) == 1


async def test_username_is_case_insensitive(
    api: httpx.AsyncClient, owner: ApiUser, friend: ApiUser, video_id: str
) -> None:
    granted = await api.put(_url(video_id, "BOBBY"), headers=owner.headers)
    assert granted.json()["username"] == friend.username

    assert (await api.delete(_url(video_id, "BoBbY"), headers=owner.headers)).status_code == 204
    assert await _usernames(api, owner, video_id) == []


async def test_grant_to_an_unknown_user_is_404(
    api: httpx.AsyncClient, owner: ApiUser, video_id: str
) -> None:
    response = await api.put(_url(video_id, "nobody"), headers=owner.headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


async def test_owner_cannot_grant_to_themselves(
    api: httpx.AsyncClient, owner: ApiUser, video_id: str
) -> None:
    response = await api.put(_url(video_id, owner.username), headers=owner.headers)

    assert response.status_code == 409
    assert await _usernames(api, owner, video_id) == []


@pytest.mark.parametrize("username", ["ab", "has space", "a" * 31, "semi;colon"])
async def test_invalid_usernames_are_rejected(
    api: httpx.AsyncClient, owner: ApiUser, video_id: str, username: str
) -> None:
    response = await api.put(_url(video_id, username), headers=owner.headers)

    assert response.status_code == 422


async def test_revoke_removes_only_that_user(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    owner: ApiUser,
    friend: ApiUser,
    video_id: str,
) -> None:
    other = await create_user("carol")
    await api.put(_url(video_id, friend.username), headers=owner.headers)
    await api.put(_url(video_id, other.username), headers=owner.headers)

    response = await api.delete(_url(video_id, friend.username), headers=owner.headers)

    assert response.status_code == 204
    assert await _usernames(api, owner, video_id) == [other.username]


@pytest.mark.parametrize("username", ["bobby", "nobody"])
async def test_revoking_when_not_listed_is_still_204(
    api: httpx.AsyncClient, owner: ApiUser, friend: ApiUser, video_id: str, username: str
) -> None:
    """Includes an unknown username: the answer doesn't reveal which ones exist."""
    assert friend.username == "bobby"

    response = await api.delete(_url(video_id, username), headers=owner.headers)

    assert response.status_code == 204


async def test_list_is_paginated_by_username(
    api: httpx.AsyncClient, create_user: CreateUser, owner: ApiUser, video_id: str
) -> None:
    for name in ("delta", "alpha", "charlie", "bravo", "echo"):
        await api.put(_url(video_id, (await create_user(name)).username), headers=owner.headers)

    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = (await api.get(_url(video_id), headers=owner.headers, params=params)).json()
        seen += [item["username"] for item in page["items"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == ["alpha", "bravo", "charlie", "delta", "echo"]
    assert pages == 3


async def test_entries_belong_to_one_video(
    api: httpx.AsyncClient, owner: ApiUser, friend: ApiUser, video_id: str
) -> None:
    created = await api.post("/api/videos", headers=owner.headers, json={"title": "Another"})
    await api.put(_url(video_id, friend.username), headers=owner.headers)

    assert await _usernames(api, owner, created.json()["video"]["id"]) == []


@pytest.mark.parametrize(("method", "with_user"), [("GET", False), ("PUT", True), ("DELETE", True)])
async def test_a_deleted_video_is_gone(
    api: httpx.AsyncClient,
    session: AsyncSession,
    owner: ApiUser,
    friend: ApiUser,
    video_id: str,
    method: str,
    with_user: bool,
) -> None:
    await session.execute(
        update(Video).where(Video.id == uuid.UUID(video_id)).values(deleted_at=datetime.now(UTC))
    )
    await session.commit()
    url = _url(video_id, friend.username if with_user else None)

    assert (await api.request(method, url, headers=owner.headers)).status_code == 404


@pytest.mark.parametrize(("method", "with_user"), [("GET", False), ("PUT", True), ("DELETE", True)])
async def test_an_unknown_video_is_404(
    api: httpx.AsyncClient, owner: ApiUser, friend: ApiUser, method: str, with_user: bool
) -> None:
    url = _url(str(uuid.uuid4()), friend.username if with_user else None)

    assert (await api.request(method, url, headers=owner.headers)).status_code == 404
