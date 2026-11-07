import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User, UserRole
from tests.helpers import PASSWORD, ApiUser, CreateUser, SetRole

ORIGIN = {"Origin": "http://test"}


async def _admin(create_user: CreateUser, set_role: SetRole, name: str = "root") -> ApiUser:
    admin = await create_user(name)
    await set_role(admin, UserRole.admin)
    return admin


async def _stored(session: AsyncSession, user: ApiUser) -> User:
    stored = await session.scalar(
        select(User).where(User.id == user.id).execution_options(populate_existing=True)
    )
    assert stored is not None
    return stored


async def test_admin_lists_and_searches_users(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole
) -> None:
    admin = await _admin(create_user, set_role)
    for name in ("alice", "bob", "carol"):
        await create_user(name)

    everyone = await api.get("/api/admin/users", headers=admin.headers)
    found = await api.get("/api/admin/users", headers=admin.headers, params={"q": "BO"})
    literal = await api.get("/api/admin/users", headers=admin.headers, params={"q": "%"})

    assert [u["username"] for u in everyone.json()["items"]] == ["alice", "bob", "carol", "root"]
    assert [u["username"] for u in found.json()["items"]] == ["bob"]
    assert literal.json()["items"] == []  # `%` is matched literally, not as a wildcard


async def test_admin_user_list_paginates(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole
) -> None:
    admin = await _admin(create_user, set_role)
    for name in ("alice", "bob", "carol"):
        await create_user(name)

    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        page = (await api.get("/api/admin/users", headers=admin.headers, params=params)).json()
        seen += [u["username"] for u in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == ["alice", "bob", "carol", "root"]


async def test_admin_changes_role(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, set_role: SetRole
) -> None:
    admin = await _admin(create_user, set_role)
    alice = await create_user()

    response = await api.patch(
        f"/api/admin/users/{alice.id}", headers=admin.headers, json={"role": "moderator"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "moderator"
    assert (await _stored(session, alice)).role == UserRole.moderator


async def test_moderator_cant_change_roles(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, set_role: SetRole
) -> None:
    """D37: a moderator can't change roles, including their own."""
    moderator = await create_user("mod")
    await set_role(moderator, UserRole.moderator)
    alice = await create_user()

    for target in (alice, moderator):
        response = await api.patch(
            f"/api/admin/users/{target.id}", headers=moderator.headers, json={"role": "admin"}
        )
        assert response.status_code == 403
    assert (await _stored(session, alice)).role == UserRole.user
    assert (await _stored(session, moderator)).role == UserRole.moderator


@pytest.mark.parametrize(
    "body", [{"role": "user"}, {"role": "moderator"}, {"is_active": False}]
)
async def test_admin_cant_demote_or_disable_self(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    body: dict[str, object],
) -> None:
    """D37: an admin can't demote or disable themselves, so one admin always remains."""
    admin = await _admin(create_user, set_role)

    response = await api.patch(f"/api/admin/users/{admin.id}", headers=admin.headers, json=body)

    assert response.status_code == 403
    stored = await _stored(session, admin)
    assert (stored.role, stored.is_active) == (UserRole.admin, True)


async def test_admin_can_demote_another_admin(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole
) -> None:
    admin = await _admin(create_user, set_role)
    other = await _admin(create_user, set_role, "other")

    response = await api.patch(
        f"/api/admin/users/{other.id}", headers=admin.headers, json={"role": "user"}
    )

    assert response.status_code == 200


async def test_promotion_applies_on_next_request(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole
) -> None:
    """D38: the same, unexpired JWT gets the new role at once."""
    admin = await _admin(create_user, set_role)
    alice = await create_user()
    assert (await api.get("/api/admin/users", headers=alice.headers)).status_code == 403

    await api.patch(f"/api/admin/users/{alice.id}", headers=admin.headers, json={"role": "admin"})

    assert (await api.get("/api/admin/users", headers=alice.headers)).status_code == 200


async def test_demotion_applies_on_next_request(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole
) -> None:
    """D38: a demoted admin loses access with the JWT they already hold."""
    admin = await _admin(create_user, set_role)
    other = await _admin(create_user, set_role, "other")
    assert (await api.get("/api/admin/users", headers=other.headers)).status_code == 200

    await api.patch(f"/api/admin/users/{other.id}", headers=admin.headers, json={"role": "user"})

    assert (await api.get("/api/admin/users", headers=other.headers)).status_code == 403


async def test_disable_applies_on_next_request_and_ends_sessions(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, set_role: SetRole
) -> None:
    """D38: a disabled user is locked out with an unexpired JWT, their refresh tokens are
    revoked, and they can't log in again until re-enabled."""
    admin = await _admin(create_user, set_role)
    alice = await create_user()
    login = await api.post("/api/auth/login", json={"email": alice.email, "password": PASSWORD})
    refresh_token = login.cookies["refresh_token"]
    api.cookies.clear()

    response = await api.patch(
        f"/api/admin/users/{alice.id}", headers=admin.headers, json={"is_active": False}
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert (await api.get("/api/users/me", headers=alice.headers)).status_code == 401
    tokens = await session.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == alice.id)
        .execution_options(populate_existing=True)
    )
    assert all(token.revoked_at is not None for token in tokens)
    refreshed = await api.post(
        "/api/auth/refresh", headers=ORIGIN | {"Cookie": f"refresh_token={refresh_token}"}
    )
    assert refreshed.status_code == 401
    relogin = await api.post("/api/auth/login", json={"email": alice.email, "password": PASSWORD})
    assert relogin.status_code == 403

    await api.patch(
        f"/api/admin/users/{alice.id}", headers=admin.headers, json={"is_active": True}
    )
    relogin = await api.post("/api/auth/login", json={"email": alice.email, "password": PASSWORD})
    assert relogin.status_code == 200


async def test_update_unknown_user_is_404(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole
) -> None:
    admin = await _admin(create_user, set_role)
    response = await api.patch(
        "/api/admin/users/00000000-0000-4000-8000-000000000000",
        headers=admin.headers,
        json={"role": "moderator"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body", [{"role": "superuser"}, {"username": "mallory"}, {"password_hash": "x"}]
)
async def test_update_rejects_unknown_values(
    api: httpx.AsyncClient, create_user: CreateUser, set_role: SetRole, body: dict[str, str]
) -> None:
    admin = await _admin(create_user, set_role)
    alice = await create_user()
    response = await api.patch(f"/api/admin/users/{alice.id}", headers=admin.headers, json=body)
    assert response.status_code == 422
