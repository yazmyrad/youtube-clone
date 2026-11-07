import socket
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest

from app.core import config
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.main import create_app


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


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
