"""D30: the action matrix from architecture.md section 4, one parametrized case per cell.

Only rows whose endpoints exist so far are here; each later feature adds its rows.
"Owner" isn't a column: these rows are about someone else's video, and test_videos.py
covers what the owner can do.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
import pytest

from app.models import UserRole
from tests.helpers import PASSWORD, ApiUser, CreateUser, SetRole

ANON = "anonymous"
ACTORS = (ANON, UserRole.user, UserRole.moderator, UserRole.admin)

# Expected outcome per cell: yes = allowed, or the status code the actor gets.
YES = "yes"
NO_LOGIN = 401
NO = 403
HIDDEN = 404  # Denied, without revealing that the video exists.


@dataclass(frozen=True)
class Ctx:
    api: httpx.AsyncClient
    actor: ApiUser | None
    other: ApiUser  # some other user, as a target

    @property
    def headers(self) -> dict[str, str]:
        return self.actor.headers if self.actor else {}


Action = Callable[[Ctx], Awaitable[httpx.Response]]


async def _register(ctx: Ctx) -> httpx.Response:
    body = {"username": "newbie", "email": "newbie@example.com", "password": PASSWORD,
            "display_name": "Newbie"}  # fmt: skip
    return await ctx.api.post("/api/auth/register", json=body)


async def _log_in(ctx: Ctx) -> httpx.Response:
    body = {"email": ctx.other.email, "password": PASSWORD}
    return await ctx.api.post("/api/auth/login", json=body)


async def _get_me(ctx: Ctx) -> httpx.Response:
    return await ctx.api.get("/api/users/me", headers=ctx.headers)


async def _edit_me(ctx: Ctx) -> httpx.Response:
    return await ctx.api.patch("/api/users/me", headers=ctx.headers, json={"description": "hi"})


async def _create_video(ctx: Ctx) -> httpx.Response:
    return await ctx.api.post("/api/videos", headers=ctx.headers, json={"title": "Clip"})


async def _others_video(ctx: Ctx) -> str:
    created = await ctx.api.post("/api/videos", headers=ctx.other.headers, json={"title": "Theirs"})
    return created.json()["video"]["id"]


async def _complete_others_upload(ctx: Ctx) -> httpx.Response:
    url = f"/api/videos/{await _others_video(ctx)}/upload/complete"
    return await ctx.api.post(url, headers=ctx.headers)


async def _edit_others_video(ctx: Ctx) -> httpx.Response:
    url = f"/api/videos/{await _others_video(ctx)}"
    return await ctx.api.patch(url, headers=ctx.headers, json={"title": "Mine now"})


async def _list_others_access(ctx: Ctx) -> httpx.Response:
    url = f"/api/videos/{await _others_video(ctx)}/access"
    return await ctx.api.get(url, headers=ctx.headers)


async def _grant_access_to_others_video(ctx: Ctx) -> httpx.Response:
    url = f"/api/videos/{await _others_video(ctx)}/access/{ctx.other.username}"
    return await ctx.api.put(url, headers=ctx.headers)


async def _revoke_access_to_others_video(ctx: Ctx) -> httpx.Response:
    url = f"/api/videos/{await _others_video(ctx)}/access/{ctx.other.username}"
    return await ctx.api.delete(url, headers=ctx.headers)


async def _list_users(ctx: Ctx) -> httpx.Response:
    return await ctx.api.get("/api/admin/users", headers=ctx.headers)


async def _change_role(ctx: Ctx) -> httpx.Response:
    url = f"/api/admin/users/{ctx.other.id}"
    return await ctx.api.patch(url, headers=ctx.headers, json={"role": "moderator"})


async def _disable_user(ctx: Ctx) -> httpx.Response:
    url = f"/api/admin/users/{ctx.other.id}"
    return await ctx.api.patch(url, headers=ctx.headers, json={"is_active": False})


# Columns follow ACTORS: anonymous, user, moderator, admin.
MATRIX: dict[str, tuple[Action, tuple[str | int, ...]]] = {
    # "Register, log in" is n/a for logged-in roles in the doc; the API simply allows it.
    "register": (_register, (YES, YES, YES, YES)),
    "log in": (_log_in, (YES, YES, YES, YES)),
    "view own profile": (_get_me, (NO_LOGIN, YES, YES, YES)),
    "edit own profile": (_edit_me, (NO_LOGIN, YES, YES, YES)),
    "upload video": (_create_video, (NO_LOGIN, YES, YES, YES)),
    "confirm someone else's upload": (_complete_others_upload, (NO_LOGIN, HIDDEN, HIDDEN, HIDDEN)),
    "edit someone else's video": (_edit_others_video, (NO_LOGIN, HIDDEN, HIDDEN, HIDDEN)),
    "list allowlist of someone else's video": (
        _list_others_access, (NO_LOGIN, HIDDEN, HIDDEN, HIDDEN)
    ),
    "grant access to someone else's video": (
        _grant_access_to_others_video, (NO_LOGIN, HIDDEN, HIDDEN, HIDDEN)
    ),
    "revoke access to someone else's video": (
        _revoke_access_to_others_video, (NO_LOGIN, HIDDEN, HIDDEN, HIDDEN)
    ),
    "list users": (_list_users, (NO_LOGIN, NO, NO, YES)),
    "change roles": (_change_role, (NO_LOGIN, NO, NO, YES)),
    "disable users": (_disable_user, (NO_LOGIN, NO, NO, YES)),
}

CELLS = [
    pytest.param(name, actor, expected, id=f"{name}-{actor}")
    for name, (_, row) in MATRIX.items()
    for actor, expected in zip(ACTORS, row, strict=True)
]


async def _actor(create_user: CreateUser, set_role: SetRole, actor: str) -> ApiUser | None:
    if actor == ANON:
        return None
    user = await create_user("actor")
    if actor != UserRole.user:
        await set_role(user, UserRole(actor))
    return user


@pytest.mark.parametrize(("name", "actor", "expected"), CELLS)
async def test_action_matrix(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    set_role: SetRole,
    name: str,
    actor: str,
    expected: str | int,
) -> None:
    ctx = Ctx(api, await _actor(create_user, set_role, actor), await create_user("other"))

    response = await MATRIX[name][0](ctx)

    if expected == YES:
        assert response.is_success, response.text
    else:
        assert response.status_code == expected, response.text


@pytest.mark.parametrize("name", [n for n, (_, row) in MATRIX.items() if row[0] == NO_LOGIN])
async def test_disabled_user_is_treated_as_logged_out(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole, name: str
) -> None:
    """A disabled account's still-valid JWT opens nothing that needs a login (D38)."""
    admin = await create_user("root")
    await set_role(admin, UserRole.admin)
    actor = await create_user("actor")
    await api.patch(f"/api/admin/users/{actor.id}", headers=admin.headers,
                    json={"is_active": False})  # fmt: skip

    response = await MATRIX[name][0](Ctx(api, actor, admin))

    assert response.status_code == 401
