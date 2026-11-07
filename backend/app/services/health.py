import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import HealthOut

logger = logging.getLogger(__name__)

DB_CHECK_TIMEOUT_SECONDS = 2.0


async def get_health(session: AsyncSession) -> HealthOut:
    if await _database_is_up(session):
        return HealthOut(status="ok", database="ok")
    return HealthOut(status="unavailable", database="unavailable")


async def _database_is_up(session: AsyncSession) -> bool:
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
    # Broad on purpose: asyncpg raises OSError and its own errors on connect, not only
    # SQLAlchemy errors, and any failure here must become a 503 rather than a 500.
    except Exception:
        logger.exception("Database health check failed")
        return False
    return True
