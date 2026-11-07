import asyncio
import os

import httpx
import pytest
from pydantic import ValidationError

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


async def test_health_is_documented_in_swagger(client: httpx.AsyncClient) -> None:
    docs = await client.get("/docs")
    schema = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    responses = schema.json()["paths"]["/api/health"]["get"]["responses"]
    assert {"200", "503"} <= responses.keys()
