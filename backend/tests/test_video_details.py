"""GET /videos/{id}: the viewing matrix from architecture.md section 4, and D31."""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import UserRole, VideoStatus, VideoVisibility
from tests.helpers import ApiUser, CreateUser, SetRole, create_ready_video

ANON = "anonymous"
STRANGER = "user"
OWNER = "owner"
MODERATOR = "moderator"
ADMIN = "admin"

SEEN = 200
DENIED = 404

# Columns: anonymous, user, owner, moderator, admin. The moderator's open report comes in step 22.
ACTORS = (ANON, STRANGER, OWNER, MODERATOR, ADMIN)
MATRIX: dict[str, tuple[int, ...]] = {
    "public": (SEEN, SEEN, SEEN, SEEN, SEEN),
    "unlisted": (SEEN, SEEN, SEEN, SEEN, SEEN),
    "private": (DENIED, DENIED, SEEN, DENIED, DENIED),
    "hidden": (DENIED, DENIED, SEEN, SEEN, SEEN),
    "processing": (DENIED, DENIED, SEEN, DENIED, DENIED),
    "deleted": (DENIED, DENIED, DENIED, DENIED, DENIED),
}
STATES: dict[str, dict[str, Any]] = {
    "public": {},
    "unlisted": {"visibility": VideoVisibility.unlisted},
    "private": {"visibility": VideoVisibility.private},
    "hidden": {"hidden_at": datetime.now(UTC)},
    "processing": {"status": VideoStatus.processing, "published_at": None},
    "deleted": {"deleted_at": datetime.now(UTC)},
}
CELLS = [
    pytest.param(state, actor, expected, id=f"{state}-{actor}")
    for state, row in MATRIX.items()
    for actor, expected in zip(ACTORS, row, strict=True)
]


async def _get(
    api: httpx.AsyncClient, video_id: str, user: ApiUser | None = None
) -> httpx.Response:
    return await api.get(f"/api/videos/{video_id}", headers=user.headers if user else {})


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
    video_id = await create_ready_video(api, session, owner, **STATES[state])

    response = await _get(api, video_id, await _actor(create_user, set_role, actor, owner))

    assert response.status_code == expected, response.text


async def test_returns_only_the_public_fields(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

    body = (await _get(api, video_id)).json()

    assert body["id"] == video_id
    assert body["status"] == "ready"
    assert body["duration_seconds"] == 5
    assert set(body) == {
        "id",
        "title",
        "description",
        "visibility",
        "status",
        "duration_seconds",
        "published_at",
        "created_at",
        "channel",
        "views_count",
        "likes_count",
        "dislikes_count",
        "comments_count",
        "thumbnail_url",
    }
    assert body["channel"] == {"username": "alice", "display_name": "Alice"}
    assert body["views_count"] == 0
    assert body["likes_count"] == body["dislikes_count"] == body["comments_count"] == 0


async def test_ready_video_has_a_signed_thumbnail(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

    url = (await _get(api, video_id)).json()["thumbnail_url"]

    match = re.fullmatch(rf"/thumbs/(\d+)\.([0-9a-f]{{64}})/{video_id}\.jpg", url)
    assert match is not None, url
    assert security.verify_media(
        security.MEDIA_SCOPE_THUMB, video_id, match.group(1), match.group(2)
    )


async def test_no_thumbnail_while_processing(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner, **STATES["processing"])

    body = (await _get(api, video_id, owner)).json()

    assert body["status"] == "processing"
    assert body["thumbnail_url"] is None


@pytest.mark.parametrize("actor", [OWNER, MODERATOR, ADMIN])
async def test_no_thumbnail_on_a_hidden_video(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    actor: str,
) -> None:
    owner = await create_user("owner")
    video_id = await create_ready_video(api, session, owner, **STATES["hidden"])

    response = await _get(api, video_id, await _actor(create_user, set_role, actor, owner))

    assert response.status_code == 200, response.text
    assert response.json()["thumbnail_url"] is None


@pytest.mark.parametrize("logged_in", [True, False], ids=["stranger", "anonymous"])
async def test_a_private_video_looks_exactly_like_a_missing_one(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, logged_in: bool
) -> None:
    """D31, on details and on /playback."""
    video_id = await create_ready_video(
        api, session, await create_user(), visibility=VideoVisibility.private
    )
    missing_id = str(uuid.uuid4())
    caller = await create_user("bobby") if logged_in else None
    headers = caller.headers if caller else {}

    details = await _get(api, video_id, caller)
    missing_details = await _get(api, missing_id, caller)
    playback = await api.post(f"/api/videos/{video_id}/playback", headers=headers)
    missing_playback = await api.post(f"/api/videos/{missing_id}/playback", headers=headers)

    assert details.status_code == missing_details.status_code == 404
    assert details.json() == missing_details.json()
    assert playback.status_code == missing_playback.status_code == 404
    assert playback.json() == missing_playback.json()


async def test_allowlisted_user_sees_details_until_revoked(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    video_id = await create_ready_video(api, session, owner, visibility=VideoVisibility.private)
    access = f"/api/videos/{video_id}/access/{friend.username}"

    assert (await _get(api, video_id, friend)).status_code == 404

    await api.put(access, headers=owner.headers)
    assert (await _get(api, video_id, friend)).status_code == 200

    await api.delete(access, headers=owner.headers)
    assert (await _get(api, video_id, friend)).status_code == 404


async def test_a_bad_token_is_not_treated_as_anonymous(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

    response = await api.get(
        f"/api/videos/{video_id}", headers={"Authorization": "Bearer nonsense"}
    )

    assert response.status_code == 401
