"""The single place for authentication and permission checks (architecture.md, section 4).

Routers depend on these; nothing re-implements them inline.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.db import get_session
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.models import User, UserRole, Video

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


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """A dependency that lets through only callers with one of `roles` (else 403)."""

    async def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise Forbidden("You don't have permission to do this")
        return user

    return dependency


ModeratorUser = Annotated[User, Depends(require_role(UserRole.moderator, UserRole.admin))]
AdminUser = Annotated[User, Depends(require_role(UserRole.admin))]


def ensure_video_owner(user: User, video: Video) -> None:
    """Only the owner may manage a video, moderators and admins included in the refusal.
    404 and not 403, so the response doesn't reveal that a private video exists."""
    if video.deleted_at is not None or video.owner_id != user.id:
        raise NotFound("Video not found")


def ensure_can_manage_user(
    actor: User, target: User, *, role: UserRole | None, is_active: bool | None
) -> None:
    """Changing roles and enabling or disabling users is admin-only (D37). An admin can't
    demote or disable themselves, so at least one admin always remains.

    `actor` and `target` must be freshly loaded and locked by the caller, so two admins
    can't demote each other concurrently and leave none."""
    if not actor.is_active or actor.role != UserRole.admin:
        raise Forbidden("You don't have permission to do this")
    if actor.id == target.id and (
        (role is not None and role != UserRole.admin) or is_active is False
    ):
        raise Forbidden("Admins can't demote or disable themselves")
