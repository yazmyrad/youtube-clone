import asyncio
import os
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core import config
from app.core.config import get_settings
from app.core.db import get_engine, get_session
from app.main import create_app, lifespan
from app.services import health as health_service

OK_BODY = {"status": "ok", "database": "ok"}
UNAVAILABLE_BODY = {"status": "unavailable", "database": "unavailable"}


@pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="needs a real Postgres: set TEST_DATABASE_URL (CI does)",
)
async def test_health_ok_with_real_database(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])

    response = await client.get("/api/health")
    await get_engine().dispose()

    assert response.status_code == 200
    assert response.json() == OK_BODY


async def test_health_ok_when_query_succeeds() -> None:
    class WorkingSession:
        async def execute(self, _statement: object) -> None:
            return None

    app = create_app()
    app.dependency_overrides[get_session] = lambda: WorkingSession()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == OK_BODY


async def test_health_503_when_database_refuses_connections(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, closed_port: int
) -> None:
    password = "do-not-leak-this"
    monkeypatch.setenv(
        "DATABASE_URL", f"postgresql+asyncpg://app:{password}@127.0.0.1:{closed_port}/app"
    )

    response = await client.get("/api/health")
    await get_engine().dispose()

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY
    assert password not in response.text


async def test_health_503_when_database_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingSession:
        async def execute(self, _statement: object) -> None:
            await asyncio.Event().wait()

    monkeypatch.setattr(health_service, "DB_CHECK_TIMEOUT_SECONDS", 0.01)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: HangingSession()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY


async def test_startup_fails_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        async with lifespan(create_app()):
            pass


async def test_app_starts_with_database_url_from_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Running uvicorn outside Docker: DATABASE_URL comes only from backend/.env."""
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql+asyncpg://app:pw@127.0.0.1:1/app\n")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = create_app()
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            docs = await http_client.get("/docs")

    assert docs.status_code == 200


def test_environment_overrides_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql+asyncpg://from-file/app\n")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://from-env/app")

    assert get_settings().database_url == "postgresql+asyncpg://from-env/app"


async def test_health_is_documented_in_swagger(client: httpx.AsyncClient) -> None:
    docs = await client.get("/docs")
    schema = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    responses = schema.json()["paths"]["/api/health"]["get"]["responses"]
    assert {"200", "503"} <= responses.keys()
