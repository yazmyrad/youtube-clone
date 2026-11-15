"""Sign-in. A browser may hold several accounts at once, as on YouTube: each has its own
refresh cookie, `refresh_<user id>`, and the page says which one it means."""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, Response, status

from app.core.config import get_settings
from app.core.csrf import require_same_origin
from app.core.errors import BadRequest
from app.core.permissions import SessionDep
from app.schemas.auth import (
    AccountOut,
    AccountsOut,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
)
from app.schemas.errors import ErrorOut
from app.schemas.users import MeOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# Before accounts could be switched, one cookie by this name held the only session. It still
# works, and moves to its account's own cookie on the next refresh.
LEGACY_COOKIE = "refresh_token"
ACCOUNT_COOKIE = re.compile(r"^refresh_([0-9a-f]{32})$")
# The browser sends the refresh cookies only to auth endpoints, never to the rest of the API.
REFRESH_COOKIE_PATH = "/api/auth"

_ORIGIN_ERROR = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorOut, "description": "Origin check failed"}
}


def account_cookie(user_id: uuid.UUID) -> str:
    return f"refresh_{user_id.hex}"


def _account_tokens(request: Request) -> dict[uuid.UUID, str]:
    """The browser's accounts, by the user each cookie is named for. The server still checks
    that each token is that user's: the name is only a label."""
    tokens: dict[uuid.UUID, str] = {}
    for name, value in request.cookies.items():
        match = ACCOUNT_COOKIE.match(name)
        if match and value:
            tokens[uuid.UUID(hex=match.group(1))] = value
    return tokens


def _set_refresh_cookie(response: Response, user_id: uuid.UUID, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        account_cookie(user_id),
        token,
        max_age=int(settings.refresh_token_ttl.total_seconds()),
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        name,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=get_settings().cookie_secure,
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
    summary="Log in: returns an access token and adds the account's refresh cookie",
    description="Up to 5 accounts can be signed in at once in one browser.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_403_FORBIDDEN: {"model": ErrorOut},
        status.HTTP_409_CONFLICT: {"model": ErrorOut, "description": "Too many accounts"},
    },
)
async def login(
    data: LoginIn, session: SessionDep, request: Request, response: Response
) -> TokenOut:
    signed_in = frozenset(_account_tokens(request))
    tokens = await auth_service.login(session, data, signed_in)
    _set_refresh_cookie(response, tokens.user_id, tokens.refresh_token)
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.get(
    "/accounts",
    response_model=AccountsOut,
    summary="The accounts signed in in this browser, for the account switcher",
    description="Rotates nothing. Cookies that no longer sign anyone in are cleared.",
)
async def list_accounts(session: SessionDep, request: Request, response: Response) -> AccountsOut:
    tokens = _account_tokens(request)
    legacy = request.cookies.get(LEGACY_COOKIE)
    users = await auth_service.signed_in_accounts(
        session, [*tokens.values(), *([legacy] if legacy else [])]
    )
    live = {user.id for user in users}
    for user_id in tokens.keys() - live:
        _clear_cookie(response, account_cookie(user_id))
    return AccountsOut(items=[AccountOut.model_validate(user) for user in users])


@router.post(
    "/refresh",
    response_model=TokenOut,
    summary="Rotate an account's refresh cookie and get a new access token",
    description=(
        "`user_id` says which of the browser's accounts; it may be left out when there's "
        "only one. Reusing a refresh token that was already rotated revokes that session."
    ),
    dependencies=[Depends(require_same_origin)],
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorOut, "description": "Which account?"},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        **_ORIGIN_ERROR,
    },
)
async def refresh(
    session: SessionDep,
    request: Request,
    response: Response,
    data: Annotated[RefreshIn | None, Body()] = None,
) -> TokenOut:
    tokens = _account_tokens(request)
    legacy = request.cookies.get(LEGACY_COOKIE)
    user_id = data.user_id if data else None
    if user_id is not None:
        token = tokens.get(user_id) or legacy
    else:
        candidates = [*tokens.values(), *([legacy] if legacy else [])]
        if len(candidates) > 1:
            raise BadRequest("Several accounts are signed in: say which one")
        token = candidates[0] if candidates else None
    issued = await auth_service.refresh(session, token, user_id)
    _set_refresh_cookie(response, issued.user_id, issued.refresh_token)
    if legacy is not None and token == legacy:
        _clear_cookie(response, LEGACY_COOKIE)
    return TokenOut(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out of one account, or of all of them",
    description="With `user_id`, that account only; without, every account in this browser.",
    dependencies=[Depends(require_same_origin)],
    responses=_ORIGIN_ERROR,
)
async def logout(
    session: SessionDep,
    request: Request,
    data: Annotated[LogoutIn | None, Body()] = None,
) -> Response:
    tokens = _account_tokens(request)
    legacy = request.cookies.get(LEGACY_COOKIE)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    user_id = data.user_id if data else None
    if user_id is not None:
        await auth_service.logout(session, tokens.get(user_id))
        _clear_cookie(response, account_cookie(user_id))
        return response
    await auth_service.logout(session, *tokens.values(), legacy)
    for each in tokens:
        _clear_cookie(response, account_cookie(each))
    _clear_cookie(response, LEGACY_COOKIE)
    return response
