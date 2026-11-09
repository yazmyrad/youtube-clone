import json
from pathlib import Path

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def test_frontend_openapi_snapshot_is_current() -> None:
    """The frontend's API types are generated from this file. If this fails: make api-types."""
    assert json.loads(SNAPSHOT.read_text()) == json.loads(json.dumps(app.openapi()))
