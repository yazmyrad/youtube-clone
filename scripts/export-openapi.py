#!/usr/bin/env python3
"""Writes the API's OpenAPI document to frontend/openapi.json, the source of the generated
TypeScript types. Needs the backend's settings, but no running stack. Run: make api-types"""

import json
from pathlib import Path

from app.main import app

OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"

OUTPUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
