"""Swagger UI from files in the image, so /docs works without internet access (D61)."""

from fastapi import APIRouter, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from swagger_ui_bundle import swagger_ui_path

# Under /api, which nginx already proxies; the files are Swagger UI's own, pinned with the
# package version.
ASSETS = "/api/docs-assets"

router = APIRouter()


@router.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="YouTube clone API",
        swagger_js_url=f"{ASSETS}/swagger-ui-bundle.js",
        swagger_css_url=f"{ASSETS}/swagger-ui.css",
        swagger_favicon_url=f"{ASSETS}/favicon-32x32.png",
    )


def install_docs(app: FastAPI) -> None:
    app.mount(ASSETS, StaticFiles(directory=swagger_ui_path), name="docs-assets")
    app.include_router(router)
