"""The single place for authentication and permission checks (architecture.md, section 4).

Routers depend on these; nothing re-implements them inline.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.db import get_session
from app.core.errors import Unauthorized
from app.models import User

_bearer = HTTPBearer(auto_error=False, description="Access token from /api/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The caller, loaded from the database on every request, so a role change or
    disabling applies at once even while the JWT is still valid."""
    if credentials is None:
        raise Unauthorized("Not authenticated")
    user_id = security.decode_access_token(credentials.credentials)
    user = await session.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise Unauthorized("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
