from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core.config import get_settings
from app.core.csrf import require_same_origin
from app.core.permissions import SessionDep
from app.schemas.auth import LoginIn, RegisterIn, TokenOut
from app.schemas.errors import ErrorOut
from app.schemas.users import MeOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# The browser sends the refresh cookie only to auth endpoints, never to the rest of the API.
REFRESH_COOKIE_PATH = "/api/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE, include_in_schema=False)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(settings.refresh_token_ttl.total_seconds()),
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


@router.post(
    "/register",
    response_model=MeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    responses={status.HTTP_409_CONFLICT: {"model": ErrorOut}},
)
async def register(data: RegisterIn, session: SessionDep) -> MeOut:
    user = await auth_service.register(session, data)
    return MeOut.model_validate(user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Log in: returns an access token and sets the refresh cookie",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_403_FORBIDDEN: {"model": ErrorOut},
    },
)
async def login(data: LoginIn, session: SessionDep, response: Response) -> TokenOut:
    tokens = await auth_service.login(session, data)
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post(
    "/refresh",
    response_model=TokenOut,
    summary="Rotate the refresh cookie and get a new access token",
    description="Reusing a refresh token that was already rotated revokes the whole session.",
    dependencies=[Depends(require_same_origin)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_403_FORBIDDEN: {"model": ErrorOut, "description": "Origin check failed"},
    },
)
async def refresh(
    session: SessionDep, response: Response, refresh_token: RefreshCookie = None
) -> TokenOut:
    tokens = await auth_service.refresh(session, refresh_token)
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the session and clear the refresh cookie",
    dependencies=[Depends(require_same_origin)],
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorOut, "description": "Origin check failed"}
    },
)
async def logout(session: SessionDep, refresh_token: RefreshCookie = None) -> Response:
    await auth_service.logout(session, refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    return response
