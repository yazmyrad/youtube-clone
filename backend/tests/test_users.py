import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from tests.helpers import CreateUser


async def test_update_me_changes_profile(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    user = await create_user()

    response = await api.patch(
        "/api/users/me",
        headers=user.headers,
        json={"display_name": "  Alice A.  ", "description": "<script>x</script>"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Alice A."
    assert response.json()["description"] == "<script>x</script>"  # stored as plain text
    me = await api.get("/api/users/me", headers=user.headers)
    assert me.json()["display_name"] == "Alice A."


async def test_update_me_keeps_unsent_fields(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()

    response = await api.patch("/api/users/me", headers=user.headers, json={"description": "hi"})

    assert response.json()["display_name"] == "Alice"


@pytest.mark.parametrize(
    "body",
    [
        {"role": "admin"},
        {"display_name": "Alice", "role": "admin"},
        {"is_active": True},
        {"username": "mallory"},
        {"email": "mallory@example.com"},
    ],
)
async def test_update_me_rejects_other_fields(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, body: dict[str, str]
) -> None:
    """D36: a user can't set their own role (or other protected fields) via profile update."""
    user = await create_user()

    response = await api.patch("/api/users/me", headers=user.headers, json=body)

    assert response.status_code == 422
    stored = await session.scalar(select(User))
    assert stored is not None
    assert (stored.role, stored.username, stored.display_name) == (UserRole.user, "alice", "Alice")


@pytest.mark.parametrize("body", [{"display_name": ""}, {"description": "x" * 1001}])
async def test_update_me_validates_lengths(
    api: httpx.AsyncClient, create_user: CreateUser, body: dict[str, str]
) -> None:
    user = await create_user()
    response = await api.patch("/api/users/me", headers=user.headers, json=body)
    assert response.status_code == 422


async def test_update_me_requires_login(api: httpx.AsyncClient) -> None:
    response = await api.patch("/api/users/me", json={"description": "hi"})
    assert response.status_code == 401
