import uuid
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole, Video
from app.services.videos import MAX_ACTIVE_UPLOADS
from tests.helpers import ApiUser, CreateUser, SetRole, create_ready_video


async def _delete(api: httpx.AsyncClient, user: ApiUser, video_id: str) -> httpx.Response:
    return await api.delete(f"/api/videos/{video_id}", headers=user.headers)


async def _deleted_at(session: AsyncSession, video_id: str) -> datetime | None:
    session.expire_all()
    return await session.scalar(select(Video.deleted_at).where(Video.id == uuid.UUID(video_id)))


async def test_requires_login(api: httpx.AsyncClient) -> None:
    assert (await api.delete(f"/api/videos/{uuid.uuid4()}")).status_code == 401


async def test_owner_deletes_and_video_is_gone_at_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)

    response = await _delete(api, owner, video_id)

    assert response.status_code == 204, response.text
    assert await _deleted_at(session, video_id) is not None
    details = await api.get(f"/api/videos/{video_id}", headers=owner.headers)
    assert details.status_code == 404
    assert (await api.get("/api/videos")).json()["items"] == []
    mine = await api.get("/api/users/me/videos", headers=owner.headers)
    assert mine.json()["items"] == []


async def test_only_the_owner_may_delete(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
) -> None:
    owner = await create_user("alice")
    video_id = await create_ready_video(api, session, owner)
    stranger = await create_user("bob")
    moderator = await create_user("carol")
    await set_role(moderator, UserRole.moderator)

    for user in (stranger, moderator):
        assert (await _delete(api, user, video_id)).status_code == 404

    assert await _deleted_at(session, video_id) is None


async def test_deleting_twice_is_not_found(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    assert (await _delete(api, owner, video_id)).status_code == 204

    assert (await _delete(api, owner, video_id)).status_code == 404


async def test_unknown_video_is_not_found(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    owner = await create_user()
    assert (await _delete(api, owner, str(uuid.uuid4()))).status_code == 404


async def test_deleting_an_unfinished_upload_frees_its_slot(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    owner = await create_user()

    async def create() -> httpx.Response:
        return await api.post("/api/videos", headers=owner.headers, json={"title": "Clip"})

    uploads = [await create() for _ in range(MAX_ACTIVE_UPLOADS)]
    assert (await create()).status_code == 409

    assert (await _delete(api, owner, uploads[0].json()["video"]["id"])).status_code == 204

    assert (await create()).status_code == 201
