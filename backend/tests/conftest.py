import os
import socket
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.main import create_app
from app.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _clear_caches() -> None:
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep cached settings and engines from leaking between tests and event loops.

    Also ignores any developer backend/.env, so it can't change test results.
    """
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
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
