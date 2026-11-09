import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Video, VideoStatus
from tests.helpers import ApiUser, CreateUser, create_ready_video

URL = "/api/users/me/videos"


async def _list(api: httpx.AsyncClient, user: ApiUser, **params: Any) -> dict[str, Any]:
    response = await api.get(URL, headers=user.headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _uploading(api: httpx.AsyncClient, user: ApiUser) -> str:
    created = await api.post("/api/videos", headers=user.headers, json={"title": "New"})
    assert created.status_code == 201, created.text
    return created.json()["video"]["id"]


async def _set(session: AsyncSession, video_id: str, **values: Any) -> None:
    await session.execute(update(Video).where(Video.id == uuid.UUID(video_id)).values(**values))
    await session.commit()


async def test_requires_login(api: httpx.AsyncClient) -> None:
    assert (await api.get(URL)).status_code == 401


async def test_lists_every_status_and_visibility(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    ready = await create_ready_video(api, session, user)
    processing = await _uploading(api, user)
    await _set(session, processing, status=VideoStatus.processing)
    failed = await _uploading(api, user)
    await _set(session, failed, status=VideoStatus.failed, failure_reason="Not a video")
    uploading = await _uploading(api, user)

    items = (await _list(api, user))["items"]

    assert [(item["id"], item["status"]) for item in items] == [
        (uploading, "uploading"),
        (failed, "failed"),
        (processing, "processing"),
        (ready, "ready"),
    ]
    assert items[1]["failure_reason"] == "Not a video"
    assert "raw_key" not in items[0]


async def test_shows_only_your_own(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    bob = await create_user("bob")
    await create_ready_video(api, session, bob)
    await _uploading(api, bob)

    assert (await _list(api, alice))["items"] == []


async def test_leaves_out_deleted(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    kept = await create_ready_video(api, session, user)
    await create_ready_video(api, session, user, deleted_at=datetime.now(UTC))

    assert [item["id"] for item in (await _list(api, user))["items"]] == [kept]


async def test_pages_cover_everything_once_when_timestamps_tie(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    same_moment = datetime(2026, 1, 1, tzinfo=UTC)
    ids = [await create_ready_video(api, session, user) for _ in range(5)]
    for video_id in ids:
        await _set(session, video_id, created_at=same_moment)

    first = await _list(api, user, limit=2)
    second = await _list(api, user, limit=2, cursor=first["next_cursor"])
    third = await _list(api, user, limit=2, cursor=second["next_cursor"])

    seen = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert seen == sorted(ids, key=uuid.UUID, reverse=True)
    assert third["next_cursor"] is None


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"cursor": "nonsense"}])
async def test_bad_paging_is_refused(
    api: httpx.AsyncClient, create_user: CreateUser, params: dict[str, Any]
) -> None:
    user = await create_user()
    response = await api.get(URL, headers=user.headers, params=params)
    assert response.status_code == 422
