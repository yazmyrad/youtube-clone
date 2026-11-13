from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    admin,
    auth,
    channels,
    comments,
    feed,
    health,
    internal,
    playlists,
    reactions,
    search,
    users,
    videos,
)
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.services import storage


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # Fail at startup, not on the first request, if configuration is missing.
    storage.get_client()  # Building it is slow and blocking, so don't do that on a request.
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube clone API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    for module in (
        health,
        auth,
        users,
        admin,
        videos,
        reactions,
        comments,
        search,
        channels,
        feed,
        playlists,
    ):
        app.include_router(module.router, prefix="/api")
    # Outside /api on purpose: nginx proxies only /api/, so this has no public route.
    app.include_router(internal.router)
    return app


app = create_app()
