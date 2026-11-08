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
