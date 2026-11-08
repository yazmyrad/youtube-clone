"""The endpoint behind nginx's auth_request. No database: it runs for every segment."""

import time
import uuid
from collections.abc import Callable

import httpx
import pytest

from app.core.security import MEDIA_SCOPE_HLS, MEDIA_SCOPE_THUMB, sign_media

URL = "/internal/playback-auth"
VIDEO = uuid.uuid4()


def _headers(
    scope: str = MEDIA_SCOPE_HLS,
    signed_scope: str = MEDIA_SCOPE_HLS,
    video: uuid.UUID = VIDEO,
    signed_video: uuid.UUID = VIDEO,
    exp: int | None = None,
) -> dict[str, str]:
    exp = int(time.time()) + 600 if exp is None else exp
    return {
        "X-Media-Scope": scope,
        "X-Media-Id": str(video),
        "X-Media-Exp": str(exp),
        "X-Media-Sig": sign_media(signed_scope, signed_video, exp),
    }


@pytest.mark.parametrize("scope", [MEDIA_SCOPE_HLS, MEDIA_SCOPE_THUMB])
async def test_valid_token_is_accepted(client: httpx.AsyncClient, scope: str) -> None:
    response = await client.get(URL, headers=_headers(scope=scope, signed_scope=scope))

    assert response.status_code == 204


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(lambda: _headers() | {"X-Media-Sig": "0" * 64}, id="forged"),
        pytest.param(lambda: _headers(exp=int(time.time()) - 1), id="expired"),
        pytest.param(lambda: _headers(video=uuid.uuid4()), id="another-video"),
        pytest.param(lambda: _headers(scope=MEDIA_SCOPE_THUMB), id="another-scope"),
        pytest.param(dict, id="no-headers"),
        pytest.param(
            lambda: {k: v for k, v in _headers().items() if k != "X-Media-Sig"}, id="no-signature"
        ),
        pytest.param(lambda: _headers() | {"X-Media-Exp": "soon"}, id="garbage-expiry"),
        pytest.param(lambda: _headers() | {"X-Media-Id": "x"}, id="garbage-id"),
    ],
)
async def test_anything_else_is_a_403(
    client: httpx.AsyncClient, headers: Callable[[], dict[str, str]]
) -> None:
    """Only 403: auth_request would turn a 422 or 400 into a 500."""
    assert (await client.get(URL, headers=headers())).status_code == 403


async def test_internal_routes_are_not_in_the_api_docs(client: httpx.AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]

    assert not [path for path in paths if path.startswith("/internal")]


async def test_not_reachable_under_the_public_prefix(client: httpx.AsyncClient) -> None:
    """nginx proxies only /api/, so the route must not exist there."""
    assert (await client.get("/api/internal/playback-auth")).status_code == 404
