from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, users
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # Fail at startup, not on the first request, if configuration is missing.
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube clone API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    for module in (health, auth, users):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
