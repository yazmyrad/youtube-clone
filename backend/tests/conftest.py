import contextlib
import os
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.main import create_app
from app.models import Base, User, UserRole
from app.services import storage
from tests.helpers import PASSWORD, ApiUser

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
TEST_BUCKET = "uploads-test"


def _clear_caches() -> None:
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
    storage.get_client.cache_clear()


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep cached settings and engines from leaking between tests and event loops.

    Also ignores any developer backend/.env, so it can't change test results.
    """
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "x" * 32)
    # Storage is unreachable unless a test asks for it, and never holds dev objects.
    monkeypatch.setenv("MINIO_ENDPOINT", "http://storage.invalid:9000")
    monkeypatch.setenv("MINIO_APP_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("MINIO_APP_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("UPLOADS_BUCKET", TEST_BUCKET)
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def closed_port() -> int:
    """A local port with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("needs a real Postgres: set TEST_DATABASE_URL (make test and CI do)")
    if not (make_url(url).database or "").endswith("test"):
        # Tests truncate tables, so never point them at real data.
        pytest.fail("TEST_DATABASE_URL must name a database ending in 'test'")
    return url


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    """The test database, migrated to head once per run."""
    url = _test_database_url()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        command.upgrade(Config(str(ALEMBIC_INI)), "head")
        get_settings.cache_clear()
    return url


@pytest.fixture
async def db(migrated_database_url: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Points the app at the migrated test database and empties it after the test."""
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    yield
    engine = get_engine()
    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    # The pool belongs to this test's event loop; close it before the loop goes away.
    await engine.dispose()


@pytest.fixture
async def session(db: None) -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as db_session:
        yield db_session


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def api(db: None, client: httpx.AsyncClient) -> httpx.AsyncClient:
    """A client against the app with the test database behind it."""
    return client


@pytest.fixture
def minio(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Points the app at a real MinIO with an empty test bucket; yields the bucket's URL."""
    endpoint = os.environ.get("TEST_MINIO_ENDPOINT")
    if not endpoint:
        pytest.skip("needs a real MinIO: set TEST_MINIO_ENDPOINT (make test and CI do)")
    monkeypatch.setenv("MINIO_ENDPOINT", endpoint)
    # Root, because only root can create the test bucket; the app user can't touch it.
    monkeypatch.setenv("MINIO_APP_ACCESS_KEY", os.environ["TEST_MINIO_ACCESS_KEY"])
    monkeypatch.setenv("MINIO_APP_SECRET_KEY", os.environ["TEST_MINIO_SECRET_KEY"])
    get_settings.cache_clear()
    storage.get_client.cache_clear()
    client = storage.get_client()
    with contextlib.suppress(client.exceptions.BucketAlreadyOwnedByYou):
        client.create_bucket(Bucket=TEST_BUCKET)
    yield f"{endpoint}/{TEST_BUCKET}/"
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=TEST_BUCKET):
        for item in page.get("Contents", []):
            client.delete_object(Bucket=TEST_BUCKET, Key=item["Key"])


@pytest.fixture
def create_user(api: httpx.AsyncClient) -> Callable[..., Awaitable[ApiUser]]:
    """Registers and logs in a user through the API."""

    async def create(username: str = "alice") -> ApiUser:
        email = f"{username}@example.com"
        response = await api.post(
            "/api/auth/register",
            json={
                "username": username,
                "email": email,
                "password": PASSWORD,
                "display_name": username.title(),
            },
        )
        assert response.status_code == 201, response.text
        user_id = response.json()["id"]
        login = await api.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200, login.text
        api.cookies.clear()  # Each test opts into the refresh cookie explicitly.
        return ApiUser(user_id, username, email, login.json()["access_token"])

    return create


@pytest.fixture
def set_role(session: AsyncSession) -> Callable[[ApiUser, UserRole], Awaitable[None]]:
    """Gives a user a role directly in the database, the way install.sh seeds the admin."""

    async def set_(user: ApiUser, role: UserRole) -> None:
        await session.execute(update(User).where(User.id == user.id).values(role=role))
        await session.commit()

    return set_
