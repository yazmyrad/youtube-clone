import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ,
    reason="needs a real Postgres: set TEST_DATABASE_URL (make test and CI do)",
)

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def alembic_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    url = os.environ["TEST_DATABASE_URL"]
    database = make_url(url).database or ""
    if not database.endswith("test"):
        # This test downgrades to an empty schema, so never point it at real data.
        pytest.fail(f"TEST_DATABASE_URL must name a test database, got {database!r}")
    monkeypatch.setenv("DATABASE_URL", url)
    return Config(str(ALEMBIC_INI))


def test_migrations_match_models_and_are_reversible(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)  # Fails if models have changes with no migration.
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_migrations_render_as_sql(alembic_config: Config) -> None:
    """Offline mode, for reviewing the SQL a deploy will run."""
    command.upgrade(alembic_config, "head", sql=True)
