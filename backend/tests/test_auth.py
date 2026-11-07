from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import JWT_ALGORITHM
from app.models import RefreshToken, User, UserRole
from tests.helpers import PASSWORD, CreateUser


def _register_body(**overrides: object) -> dict[str, object]:
    body = {
        "username": "alice",
        "email": "alice@example.com",
        "password": PASSWORD,
        "display_name": "Alice",
    }
    return body | overrides


async def test_register_creates_a_regular_user(api: httpx.AsyncClient) -> None:
    response = await api.post("/api/auth/register", json=_register_body())

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["role"] == "user"
    assert "password" not in str(body)


async def test_password_is_stored_as_argon2(api: httpx.AsyncClient, session: AsyncSession) -> None:
    await api.post("/api/auth/register", json=_register_body())

    stored = await session.scalar(select(User.password_hash))
    assert stored is not None and stored.startswith("$argon2id$")


@pytest.mark.parametrize(
    "extra",
    [{"role": "admin"}, {"role": "moderator"}, {"is_active": False}, {"subscribers_count": 9}],
)
async def test_register_rejects_privileged_fields(
    api: httpx.AsyncClient, session: AsyncSession, extra: dict[str, object]
) -> None:
    """D36: a user can't set their own role through registration."""
    response = await api.post("/api/auth/register", json=_register_body(**extra))

    assert response.status_code == 422
    assert await session.scalar(select(User.id)) is None


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"username": "ALICE", "email": "other@example.com"}, "Username is already taken"),
        ({"username": "alice2", "email": "Alice@Example.com"}, "Email is already registered"),
    ],
)
async def test_register_rejects_duplicates_ignoring_case(
    api: httpx.AsyncClient, overrides: dict[str, str], detail: str
) -> None:
    await api.post("/api/auth/register", json=_register_body())

    response = await api.post("/api/auth/register", json=_register_body(**overrides))

    assert response.status_code == 409
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    "overrides",
    [
        {"username": "a b"},
        {"username": "ab"},
        {"email": "not-an-email"},
        {"password": "short"},
        {"password": "x" * 129},
        {"display_name": "   "},
        {"display_name": "x" * 51},
    ],
)
async def test_register_validates_input(api: httpx.AsyncClient, overrides: dict[str, str]) -> None:
    response = await api.post("/api/auth/register", json=_register_body(**overrides))
    assert response.status_code == 422


async def test_login_returns_access_token_and_refresh_cookie(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()

    response = await api.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("refresh_token=")
    for attribute in ("httponly", "samesite=strict", "path=/api/auth"):
        assert attribute in cookie


async def test_login_email_is_case_insensitive(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    await create_user()
    response = await api.post(
        "/api/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200


async def test_login_stores_only_a_hash_of_the_refresh_token(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    response = await api.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})

    cookie_value = response.cookies["refresh_token"]
    hashes = (await session.scalars(select(RefreshToken.token_hash))).all()
    assert len(hashes) == 2  # one from create_user, one from this login
    assert all(cookie_value.encode() not in h for h in hashes)


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": "alice@example.com", "password": "wrong password"},
        {"email": "nobody@example.com", "password": PASSWORD},
    ],
)
async def test_login_failures_look_the_same(
    api: httpx.AsyncClient, create_user: CreateUser, credentials: dict[str, str]
) -> None:
    await create_user()

    response = await api.post("/api/auth/login", json=credentials)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    assert "set-cookie" not in response.headers


async def test_disabled_user_cannot_log_in(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await session.execute(update(User).values(is_active=False))
    await session.commit()

    response = await api.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 403


async def test_access_token_works_for_me(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    user = await create_user()

    response = await api.get("/api/users/me", headers=user.headers)

    assert response.status_code == 200
    assert response.json()["id"] == user.id


def _forged(sub: str, secret: str, algorithm: str = JWT_ALGORITHM, **claims: object) -> str:
    now = datetime.now(UTC)
    payload = {"sub": sub, "iat": now, "exp": now + timedelta(minutes=5)} | claims
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.mark.parametrize("case", ["missing", "garbage", "wrong_secret", "expired", "alg_none"])
async def test_me_rejects_bad_tokens(
    api: httpx.AsyncClient, create_user: CreateUser, case: str
) -> None:
    user = await create_user()
    secret = "test-secret-" + "x" * 32
    tokens = {
        "garbage": "not.a.jwt",
        "wrong_secret": _forged(user.id, "another-secret-" + "y" * 32),
        "expired": _forged(user.id, secret, exp=datetime.now(UTC) - timedelta(seconds=1)),
        "alg_none": _forged(user.id, "", algorithm="none"),
    }
    headers = {"Authorization": f"Bearer {tokens[case]}"} if case in tokens else {}

    response = await api.get("/api/users/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_disabled_user_is_rejected_with_a_valid_token(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await session.execute(update(User).values(is_active=False))
    await session.commit()

    response = await api.get("/api/users/me", headers=user.headers)

    assert response.status_code == 401


async def test_role_comes_from_the_database_not_the_token(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await session.execute(update(User).values(role=UserRole.moderator))
    await session.commit()

    response = await api.get("/api/users/me", headers=user.headers)

    assert response.json()["role"] == "moderator"
