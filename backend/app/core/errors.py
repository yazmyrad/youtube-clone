"""Domain errors raised by services. One handler turns them into HTTP responses,
so services stay free of FastAPI and routers stay free of error mapping."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    headers: dict[str, str] | None = None

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012 - read-only class constant


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT


class ServiceUnavailable(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


async def _handle(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - registered for AppError only
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle)
