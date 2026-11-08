import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.core.config import get_settings
from tests.helpers import ApiUser, CreateUser


async def _create(api: httpx.AsyncClient, user: ApiUser, **fields: Any) -> httpx.Response:
    return await api.post("/api/videos", headers=user.headers, json={"title": "Clip", **fields})


async def _post_form(bucket_url: str, upload: dict[str, Any], content: bytes) -> httpx.Response:
    """What the browser does; here straight to storage, nginx has its own check."""
    async with httpx.AsyncClient() as http:
        return await http.post(bucket_url, data=upload["fields"], files={"file": content})


def _policy(upload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(base64.b64decode(upload["fields"]["policy"]))


async def test_create_returns_video_and_upload_form(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()

    response = await _create(api, user, description="Hi", visibility="unlisted")

    assert response.status_code == 201, response.text
    body = response.json()
    video = body["video"]
    assert (video["title"], video["description"]) == ("Clip", "Hi")
    assert (video["visibility"], video["status"]) == ("unlisted", "uploading")
    assert "raw_key" not in video
    assert body["upload"]["url"] == "/uploads/"
    assert body["upload"]["fields"]["key"] == f"raw/{video['id']}/source"


async def test_visibility_defaults_to_private(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    response = await _create(api, await create_user())
    assert response.json()["video"]["visibility"] == "private"


async def test_policy_pins_key_size_and_expiry(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    body = (await _create(api, await create_user())).json()

    policy = _policy(body["upload"])

    assert {"key": f"raw/{body['video']['id']}/source"} in policy["conditions"]
    assert ["content-length-range", 1, 2 * 1024**3] in policy["conditions"]
    expires = datetime.fromisoformat(policy["expiration"])
    assert timedelta(minutes=59) < expires - datetime.now(UTC) <= timedelta(hours=1)


@pytest.mark.parametrize(
    "fields",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 101},
        {"title": "a\x00b"},
        {"description": "x" * 5001},
        {"description": "a\x00b"},
        {"visibility": "secret"},
        {"status": "ready"},
        {"owner_id": "00000000-0000-0000-0000-000000000000"},
        {"raw_key": "raw/other/source"},
    ],
)
async def test_invalid_input_is_rejected(
    api: httpx.AsyncClient, create_user: CreateUser, fields: dict[str, str]
) -> None:
    response = await _create(api, await create_user(), **fields)
    assert response.status_code == 422, response.text


async def test_limit_on_uploads_in_progress(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    for _ in range(3):
        assert (await _create(api, alice)).status_code == 201

    assert (await _create(api, alice)).status_code == 409
    assert (await _create(api, bob)).status_code == 201


async def test_limit_holds_under_concurrent_requests(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice = await create_user()

    responses = await asyncio.gather(*(_create(api, alice) for _ in range(8)))

    assert sorted(r.status_code for r in responses) == [201] * 3 + [409] * 5


async def test_upload_form_works_against_storage(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    body = (await _create(api, await create_user())).json()

    response = await _post_form(minio, body["upload"], b"video bytes")

    assert response.status_code == 204, response.text


async def test_upload_form_cannot_write_another_key(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    upload = (await _create(api, await create_user())).json()["upload"]
    upload["fields"]["key"] = "raw/someone-else/source"

    response = await _post_form(minio, upload, b"video bytes")

    assert response.status_code == 403, response.text


async def test_file_over_the_limit_is_rejected_by_storage(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    minio: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D10. The limit is lowered, so the test needn't send 2 GB; the mechanism is the same."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    get_settings.cache_clear()
    upload = (await _create(api, await create_user())).json()["upload"]

    too_big = await _post_form(minio, upload, b"x" * 2048)
    fits = await _post_form(minio, upload, b"x" * 1024)

    assert too_big.status_code == 400, too_big.text
    assert "EntityTooLarge" in too_big.text
    assert fits.status_code == 204, fits.text


async def test_empty_file_is_rejected_by_storage(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    upload = (await _create(api, await create_user())).json()["upload"]

    response = await _post_form(minio, upload, b"")

    assert response.status_code == 400, response.text
