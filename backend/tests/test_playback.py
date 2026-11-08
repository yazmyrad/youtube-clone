"""The viewing matrix from architecture.md section 4, as it applies to /playback.

Rows for the private allowlist (step 11) and a moderator's open report (step 22) come with
those features; until then a private video is its owner's alone.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import MEDIA_SCOPE_HLS, verify_media
from app.models import UserRole, Video, VideoStatus, VideoVisibility
from tests.helpers import ApiUser, CreateUser, SetRole

ANON = "anonymous"
STRANGER = "user"
OWNER = "owner"
MODERATOR = "moderator"
ADMIN = "admin"

PLAYS = 200
DENIED = 404

# Columns: anonymous, user, owner, moderator, admin.
ACTORS = (ANON, STRANGER, OWNER, MODERATOR, ADMIN)
MATRIX: dict[str, tuple[int, ...]] = {
    "public": (PLAYS, PLAYS, PLAYS, PLAYS, PLAYS),
    "unlisted": (PLAYS, PLAYS, PLAYS, PLAYS, PLAYS),
    "private": (DENIED, DENIED, PLAYS, DENIED, DENIED),
    "hidden": (DENIED, DENIED, DENIED, DENIED, DENIED),
}
CELLS = [
    pytest.param(state, actor, expected, id=f"{state}-{actor}")
    for state, row in MATRIX.items()
    for actor, expected in zip(ACTORS, row, strict=True)
]


async def _video(
    api: httpx.AsyncClient, session: AsyncSession, owner: ApiUser, **values: Any
) -> str:
    """A video of `owner`, ready to play unless `values` say otherwise."""
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


async def _play(
    api: httpx.AsyncClient, video_id: str, user: ApiUser | None = None
) -> httpx.Response:
    headers = user.headers if user else {}
    return await api.post(f"/api/videos/{video_id}/playback", headers=headers)


async def _actor(
    create_user: CreateUser, set_role: SetRole, actor: str, owner: ApiUser
) -> ApiUser | None:
    if actor == ANON:
        return None
    if actor == OWNER:
        return owner
    user = await create_user("actor")
    if actor in (MODERATOR, ADMIN):
        await set_role(user, UserRole(actor))
    return user


@pytest.mark.parametrize(("state", "actor", "expected"), CELLS)
async def test_viewing_matrix(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    state: str,
    actor: str,
    expected: int,
) -> None:
    owner = await create_user("owner")
    values: dict[str, Any] = (
        {"hidden_at": datetime.now(UTC)}
        if state == "hidden"
        else {"visibility": VideoVisibility(state)}
    )
    video_id = await _video(api, session, owner, **values)

    response = await _play(api, video_id, await _actor(create_user, set_role, actor, owner))

    assert response.status_code == expected, response.text


async def test_returns_a_signed_url_for_this_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await _video(api, session, await create_user())

    response = await _play(api, video_id)

    body = response.json()
    match = re.fullmatch(rf"/hls/(\d+)\.([0-9a-f]{{64}})/{video_id}/master\.m3u8", body["url"])
    assert match
    exp, sig = match.groups()
    assert verify_media(MEDIA_SCOPE_HLS, video_id, exp, sig)
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert int(expires_at.timestamp()) == int(exp)
    remaining = expires_at - datetime.now(UTC)
    assert timedelta(minutes=9) < remaining <= timedelta(minutes=10)


@pytest.mark.parametrize("status", [VideoStatus.processing, VideoStatus.failed])
async def test_a_video_that_is_not_ready_is_a_conflict_for_its_owner(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, status: VideoStatus
) -> None:
    owner = await create_user()
    video_id = await _video(api, session, owner, status=status, published_at=None)

    assert (await _play(api, video_id, owner)).status_code == 409


async def test_a_video_that_is_not_ready_is_hidden_from_everyone_else(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, set_role: SetRole
) -> None:
    video_id = await _video(
        api, session, await create_user(), status=VideoStatus.processing, published_at=None
    )
    moderator = await create_user("mod")
    await set_role(moderator, UserRole.moderator)

    assert (await _play(api, video_id)).status_code == 404
    assert (await _play(api, video_id, await create_user("bob"))).status_code == 404
    assert (await _play(api, video_id, moderator)).status_code == 404


async def test_a_stranger_cannot_tell_a_private_video_from_a_missing_one(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D31, for /playback."""
    video_id = await _video(api, session, await create_user(), visibility=VideoVisibility.private)
    stranger = await create_user("bob")

    private = await _play(api, video_id, stranger)
    missing = await _play(api, str(uuid.uuid4()), stranger)

    assert private.status_code == missing.status_code == 404
    assert private.json() == missing.json()


async def test_a_deleted_video_is_gone_even_for_its_owner(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await _video(api, session, owner, deleted_at=datetime.now(UTC))

    assert (await _play(api, video_id, owner)).status_code == 404


async def test_a_bad_token_is_not_treated_as_anonymous(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await _video(api, session, await create_user())

    response = await api.post(
        f"/api/videos/{video_id}/playback", headers={"Authorization": "Bearer nonsense"}
    )

    assert response.status_code == 401


async def test_a_disabled_user_is_refused_on_the_next_request(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, set_role: SetRole
) -> None:
    """D38: the JWT is still valid, but the account no longer is."""
    admin = await create_user("root")
    await set_role(admin, UserRole.admin)
    owner = await create_user()
    video_id = await _video(api, session, owner)
    await api.patch(
        f"/api/admin/users/{owner.id}", headers=admin.headers, json={"is_active": False}
    )

    assert (await _play(api, video_id, owner)).status_code == 401
