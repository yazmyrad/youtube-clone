import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_refresh_token
from app.models import RefreshToken, User
from tests.helpers import PASSWORD, CreateUser

ORIGIN = {"Origin": "http://test"}  # the test client's base URL


async def _login(api: httpx.AsyncClient, email: str) -> str:
    response = await api.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    api.cookies.clear()  # Tests pass the cookie explicitly, so it's clear which one is used.
    return response.cookies["refresh_token"]


async def _refresh(
    api: httpx.AsyncClient, token: str | None, headers: dict[str, str] = ORIGIN
) -> httpx.Response:
    cookie = {"Cookie": f"refresh_token={token}"} if token else {}
    response = await api.post("/api/auth/refresh", headers=headers | cookie)
    api.cookies.clear()
    return response


async def _token_row(session: AsyncSession, token: str) -> RefreshToken:
    row = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(token))
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def _active_tokens(session: AsyncSession) -> int:
    count = await session.scalar(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )
    return count or 0


@pytest.fixture
async def refresh_token(api: httpx.AsyncClient, create_user: CreateUser) -> str:
    user = await create_user()
    return await _login(api, user.email)


async def test_refresh_rotates_the_token(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    response = await _refresh(api, refresh_token)

    assert response.status_code == 200
    new_token = response.cookies["refresh_token"]
    assert new_token != refresh_token
    me = await api.get(
        "/api/users/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.status_code == 200
    old, new = await _token_row(session, refresh_token), await _token_row(session, new_token)
    assert old.revoked_at is not None
    assert new.revoked_at is None
    assert new.family_id == old.family_id


async def test_reusing_a_rotated_token_revokes_the_family(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    """D54: a stolen, already rotated token kills the session for everyone holding it."""
    rotated = (await _refresh(api, refresh_token)).cookies["refresh_token"]

    reuse = await _refresh(api, refresh_token)

    assert reuse.status_code == 401
    assert (await _token_row(session, rotated)).revoked_at is not None
    assert (await _refresh(api, rotated)).status_code == 401


async def test_reuse_leaves_other_sessions_alone(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()
    phone, laptop = await _login(api, user.email), await _login(api, user.email)
    await _refresh(api, phone)

    await _refresh(api, phone)  # reuse on the phone session

    assert (await _refresh(api, laptop)).status_code == 200


async def test_concurrent_refreshes_with_one_token_rotate_once(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    responses = await asyncio.gather(*(_refresh(api, refresh_token) for _ in range(2)))

    assert sorted(r.status_code for r in responses) == [200, 401]
    # The loser is treated as reuse, so the whole family ends up revoked.
    assert await _active_tokens(session) == 1  # only the session from create_user


async def test_expired_token_is_rejected(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await session.commit()

    assert (await _refresh(api, refresh_token)).status_code == 401


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
async def test_missing_or_unknown_token_is_rejected(
    api: httpx.AsyncClient, token: str | None
) -> None:
    response = await _refresh(api, token)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired refresh token"}


async def test_disabled_user_cannot_refresh(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    await session.execute(update(User).values(is_active=False))
    await session.commit()

    assert (await _refresh(api, refresh_token)).status_code == 401
    assert (await _token_row(session, refresh_token)).revoked_at is not None


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null"},
        {"Origin": "http://evil.example"},
        {"Origin": "https://test"},
        {"Origin": "http://test:8080"},
    ],
)
async def test_refresh_requires_same_origin(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str, headers: dict[str, str]
) -> None:
    response = await _refresh(api, refresh_token, headers=headers)

    assert response.status_code == 403
    assert (await _token_row(session, refresh_token)).revoked_at is None


async def test_logout_revokes_the_family_and_clears_the_cookie(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    rotated = (await _refresh(api, refresh_token)).cookies["refresh_token"]

    response = await api.post(
        "/api/auth/logout", headers=ORIGIN | {"Cookie": f"refresh_token={rotated}"}
    )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith('refresh_token=""') and "max-age=0" in cookie
    assert "path=/api/auth" in cookie
    assert (await _refresh(api, rotated)).status_code == 401
    assert await _active_tokens(session) == 1  # only the session from create_user


async def test_logout_without_a_cookie_succeeds(api: httpx.AsyncClient) -> None:
    response = await api.post("/api/auth/logout", headers=ORIGIN)
    assert response.status_code == 204


async def test_logout_requires_same_origin(
    api: httpx.AsyncClient, session: AsyncSession, refresh_token: str
) -> None:
    response = await api.post(
        "/api/auth/logout",
        headers={"Origin": "http://evil.example", "Cookie": f"refresh_token={refresh_token}"},
    )

    assert response.status_code == 403
    assert (await _token_row(session, refresh_token)).revoked_at is None


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        ("https://videos.example.com", True),
        ("http://test", False),  # The request's own scheme and host no longer count.
        ("http://videos.example.com", False),
        ("https://evil.example", False),
    ],
)
async def test_behind_tls_the_public_origin_is_the_one_allowed(
    api: httpx.AsyncClient,
    refresh_token: str,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    allowed: bool,
) -> None:
    """`--domain` mode: TLS ends in front of nginx, so the request itself says http."""
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://videos.example.com")
    get_settings.cache_clear()
    token = refresh_token

    response = await api.post(
        "/api/auth/logout",
        headers={"Origin": origin, "Cookie": f"refresh_token={token}"},
    )

    assert (response.status_code != 403) is allowed, response.text
    get_settings.cache_clear()
