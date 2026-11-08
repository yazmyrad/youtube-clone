from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_ci_env_provides_every_required_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI has no .env file, so a new required setting must also be added to the workflow."""
    ci_env = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]["backend"]["env"]
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    for name, value in ci_env.items():
        monkeypatch.setenv(name, value)
    # The database fixtures point DATABASE_URL at TEST_DATABASE_URL.
    monkeypatch.setenv("DATABASE_URL", ci_env["TEST_DATABASE_URL"])

    Settings(_env_file=None)
