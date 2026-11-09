import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole, Video, VideoStatus, VideoVisibility

PASSWORD = "correct horse battery"

# Column values that keep a video out of every public listing (D33).
NOT_LISTED: dict[str, dict[str, Any]] = {
    "unlisted": {"visibility": VideoVisibility.unlisted},
    "private": {"visibility": VideoVisibility.private},
    "hidden": {"hidden_at": datetime.now(UTC)},
    "processing": {"status": VideoStatus.processing, "published_at": None},
    "deleted": {"deleted_at": datetime.now(UTC)},
}


@dataclass
class ApiUser:
    id: str
    username: str
    email: str
    access_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


CreateUser = Callable[..., Awaitable[ApiUser]]
SetRole = Callable[[ApiUser, UserRole], Awaitable[None]]


async def create_ready_video(
    api: httpx.AsyncClient, session: AsyncSession, owner: ApiUser, **values: Any
) -> str:
    """A public video of `owner`, ready to play unless `values` say otherwise."""
    created = await api.post("/api/videos", headers=owner.headers, json={"title": "Clip"})
    assert created.status_code == 201, created.text
    video_id = created.json()["video"]["id"]
    ready = {
        "status": VideoStatus.ready,
        "hls_prefix": f"hls/{video_id}",
        "thumbnail_key": f"thumbs/{video_id}.jpg",
        "duration_seconds": 5,
        "published_at": datetime.now(UTC),
        "visibility": VideoVisibility.public,
    }
    await session.execute(
        update(Video).where(Video.id == uuid.UUID(video_id)).values({**ready, **values})
    )
    await session.commit()
    return video_id


async def collect_pages(api: httpx.AsyncClient, url: str, **params: Any) -> list[list[str]]:
    """Follows `next_cursor` to the end; returns the video ids on each page."""
    pages: list[list[str]] = []
    cursor = None
    for _ in range(50):
        query = params | ({"cursor": cursor} if cursor else {})
        response = await api.get(url, params=query)
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append([item["id"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages
    raise AssertionError("pagination never ended")
