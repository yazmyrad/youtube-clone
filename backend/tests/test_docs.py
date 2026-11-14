"""D61: /docs lists the API and needs no internet access."""

import re

import httpx


async def test_docs_use_only_local_files(api: httpx.AsyncClient) -> None:
    response = await api.get("/docs")

    assert response.status_code == 200
    urls = re.findall(r"""(?:src|href|url)\s*[:=]\s*['"]([^'"]+)['"]""", response.text)
    assert urls, response.text
    assert all(url.startswith("/") for url in urls), urls
    assert "/openapi.json" in urls


async def test_the_local_files_are_served(api: httpx.AsyncClient) -> None:
    for name, kind in (("swagger-ui-bundle.js", "javascript"), ("swagger-ui.css", "css")):
        response = await api.get(f"/api/docs-assets/{name}")
        assert response.status_code == 200, name
        assert kind in response.headers["content-type"]
        assert len(response.content) > 10_000


async def test_the_schema_lists_every_api_route(api: httpx.AsyncClient) -> None:
    paths = (await api.get("/openapi.json")).json()["paths"]

    assert all(path.startswith("/api/") for path in paths)
    for expected in ("/api/videos", "/api/playlists", "/api/moderation/reports"):
        assert expected in paths
    assert not any("docs-assets" in path or path.startswith("/internal") for path in paths)


async def test_redoc_is_off(api: httpx.AsyncClient) -> None:
    assert (await api.get("/redoc")).status_code == 404
