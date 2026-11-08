"""The viewing matrix from architecture.md section 4, as it applies to /playback.

The row for a moderator's open report comes with that feature (step 22).
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
from tests.helpers import ApiUser, CreateUser, SetRole, create_ready_video

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
    video_id = await create_ready_video(api, session, owner, **values)

    response = await _play(api, video_id, await _actor(create_user, set_role, actor, owner))

    assert response.status_code == expected, response.text


async def test_returns_a_signed_url_for_this_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

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
    video_id = await create_ready_video(api, session, owner, status=status, published_at=None)

    assert (await _play(api, video_id, owner)).status_code == 409


async def test_a_video_that_is_not_ready_is_hidden_from_everyone_else(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, set_role: SetRole
) -> None:
    video_id = await create_ready_video(
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
    video_id = await create_ready_video(
        api, session, await create_user(), visibility=VideoVisibility.private
    )
    stranger = await create_user("bob")

    private = await _play(api, video_id, stranger)
    missing = await _play(api, str(uuid.uuid4()), stranger)

    assert private.status_code == missing.status_code == 404
    assert private.json() == missing.json()


async def test_a_deleted_video_is_gone_even_for_its_owner(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner, deleted_at=datetime.now(UTC))

    assert (await _play(api, video_id, owner)).status_code == 404


async def test_a_bad_token_is_not_treated_as_anonymous(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

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
    video_id = await create_ready_video(api, session, owner)
    await api.patch(
        f"/api/admin/users/{owner.id}", headers=admin.headers, json={"is_active": False}
    )

    assert (await _play(api, video_id, owner)).status_code == 401


async def _grant(api: httpx.AsyncClient, owner: ApiUser, video_id: str, username: str) -> None:
    response = await api.put(f"/api/videos/{video_id}/access/{username}", headers=owner.headers)
    assert response.status_code == 200, response.text


async def _private_video(
    api: httpx.AsyncClient, session: AsyncSession, owner: ApiUser, **values: Any
) -> str:
    return await create_ready_video(
        api, session, owner, visibility=VideoVisibility.private, **values
    )


async def test_allowlisted_user_plays_until_revoked(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D32, step by step: nothing before the grant, and nothing after the revocation."""
    owner = await create_user()
    friend = await create_user("bobby")
    video_id = await _private_video(api, session, owner)

    assert (await _play(api, video_id, friend)).status_code == 404

    await _grant(api, owner, video_id, friend.username)
    assert (await _play(api, video_id, friend)).status_code == 200

    revoked = await api.delete(
        f"/api/videos/{video_id}/access/{friend.username}", headers=owner.headers
    )
    assert revoked.status_code == 204
    assert (await _play(api, video_id, friend)).status_code == 404


@pytest.mark.parametrize("role", [UserRole.moderator, UserRole.admin])
async def test_allowlist_applies_to_staff_like_anyone(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    role: UserRole,
) -> None:
    owner = await create_user()
    staff = await create_user("staff")
    await set_role(staff, role)
    video_id = await _private_video(api, session, owner)

    await _grant(api, owner, video_id, staff.username)

    assert (await _play(api, video_id, staff)).status_code == 200


async def test_an_entry_opens_only_its_own_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    shared = await _private_video(api, session, owner)
    other = await _private_video(api, session, owner)

    await _grant(api, owner, shared, friend.username)

    assert (await _play(api, other, friend)).status_code == 404


async def test_an_entry_does_not_help_anyone_else(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    video_id = await _private_video(api, session, owner)

    await _grant(api, owner, video_id, friend.username)

    assert (await _play(api, video_id)).status_code == 404
    assert (await _play(api, video_id, await create_user("carol"))).status_code == 404


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        pytest.param({"hidden_at": datetime.now(UTC)}, 404, id="hidden"),
        pytest.param({"deleted_at": datetime.now(UTC)}, 404, id="deleted"),
        pytest.param({"status": VideoStatus.processing, "published_at": None}, 404, id="not-ready"),
    ],
)
async def test_an_entry_does_not_override_other_rules(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    values: dict[str, Any],
    expected: int,
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    video_id = await _private_video(api, session, owner)
    await _grant(api, owner, video_id, friend.username)
    assert (await _play(api, video_id, friend)).status_code == 200

    await session.execute(update(Video).where(Video.id == uuid.UUID(video_id)).values(values))
    await session.commit()

    assert (await _play(api, video_id, friend)).status_code == expected


async def test_making_a_video_private_uses_a_list_prepared_earlier(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    stranger = await create_user("carol")
    video_id = await create_ready_video(api, session, owner)
    await _grant(api, owner, video_id, friend.username)

    edited = await api.patch(
        f"/api/videos/{video_id}", headers=owner.headers, json={"visibility": "private"}
    )

    assert edited.status_code == 200
    assert (await _play(api, video_id, friend)).status_code == 200
    assert (await _play(api, video_id, stranger)).status_code == 404
