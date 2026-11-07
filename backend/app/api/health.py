from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.health import HealthOut
from app.services import health as health_service

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Liveness and database check",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthOut}},
)
async def health(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthOut:
    result = await health_service.get_health(session)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
