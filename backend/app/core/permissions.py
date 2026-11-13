"""The single place for authentication and permission checks (architecture.md, section 4).

Routers depend on these; nothing re-implements them inline.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import ColumnElement, TextClause, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.db import get_session
from app.core.errors import Conflict, Forbidden, NotFound, Unauthorized
from app.models import Comment, User, UserRole, Video, VideoAccess, VideoStatus, VideoVisibility
from app.models.video import LISTED, PUBLISHED

_bearer = HTTPBearer(auto_error=False, description="Access token from /api/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def _load_user(session: AsyncSession, credentials: HTTPAuthorizationCredentials) -> User:
    """Loaded from the database on every request, so a role change or disabling applies
    at once even while the JWT is still valid."""
    user_id = security.decode_access_token(credentials.credentials)
    user = await session.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise Unauthorized("Invalid or expired token")
    return user


async def get_current_user(session: SessionDep, credentials: BearerDep) -> User:
    if credentials is None:
        raise Unauthorized("Not authenticated")
    return await _load_user(session, credentials)


async def get_optional_user(session: SessionDep, credentials: BearerDep) -> User | None:
    """None for an anonymous caller. A bad token is still a 401, so an expired session
    gets refreshed rather than quietly losing access to the caller's own videos."""
    return await _load_user(session, credentials) if credentials else None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


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


async def can_view(session: AsyncSession, user: User | None, video: Video) -> bool:
    """The viewing matrix (architecture.md, section 4). Fails closed for the row whose
    table doesn't exist yet: a moderator's open report. The allowlist applies to any role:
    it's the owner's own decision to share, not a moderator's power."""
    if video.deleted_at is not None:
        return False
    if user is not None and video.owner_id == user.id:
        return True
    if video.status != VideoStatus.ready:
        return False
    if video.hidden_at is not None:
        return user is not None and user.role in (UserRole.moderator, UserRole.admin)
    if video.visibility != VideoVisibility.private:
        return True
    if user is None:
        return False
    return await session.get(VideoAccess, (video.id, user.id)) is not None


async def ensure_can_view(session: AsyncSession, user: User | None, video: Video) -> None:
    """404 and not 403, so the response doesn't reveal that the video exists."""
    if not await can_view(session, user, video):
        raise NotFound("Video not found")


async def ensure_can_play(session: AsyncSession, user: User | None, video: Video) -> None:
    """Viewing rights, and nobody plays a hidden video: its owner sees only the details.
    404 and not 403, so the response doesn't reveal that the video exists."""
    if video.hidden_at is not None or not await can_view(session, user, video):
        raise NotFound("Video not found")


async def ensure_can_engage(session: AsyncSession, user: User | None, video: Video) -> None:
    """Liking and commenting. Unavailable on a hidden video even to those who may still open
    its details, and on a video that isn't ready, which only its owner can see."""
    await ensure_can_play(session, user, video)
    if video.status != VideoStatus.ready:
        raise Conflict("The video isn't ready yet")


async def ensure_can_delete_comment(
    session: AsyncSession, user: User, comment: Comment, video: Video
) -> None:
    """The author, the video's owner, moderators and admins, even on a hidden video so it
    can still be cleaned up. A caller who can't see the video gets the same 404 as for a
    comment that doesn't exist."""
    if video.deleted_at is not None:
        raise NotFound("Comment not found")
    if user.id in (comment.author_id, video.owner_id):
        return
    if user.role in (UserRole.moderator, UserRole.admin):
        return
    if not await can_view(session, user, video):
        raise NotFound("Comment not found")
    raise Forbidden("You can't delete this comment")


def listed_videos() -> TextClause:
    """Which videos the feed and search may show, to anyone at all. The same literal SQL as
    the partial indexes, because Postgres can't match bound parameters to their predicates."""
    return LISTED


def channel_videos(viewer: User | None, channel: User) -> ColumnElement[bool]:
    """Which of a channel's videos its page lists for `viewer`. Others see what the feed would
    show; the owner also sees their private and unlisted ones. Hidden videos stay off for
    everyone, as they have no thumbnail to show, and unfinished ones are on the upload page."""
    if viewer is not None and viewer.id == channel.id:
        return and_(Video.owner_id == channel.id, PUBLISHED, Video.hidden_at.is_(None))
    return and_(Video.owner_id == channel.id, LISTED)


def ensure_can_subscribe(user: User, channel: User) -> None:
    """Any signed-in user may subscribe to any channel but their own (D53)."""
    if user.id == channel.id:
        raise Forbidden("You can't subscribe to your own channel")


def can_show_thumbnail(video: Video) -> bool:
    """For a caller who already passed `can_view`. Follows playback: a hidden video shows
    nobody its picture, and one that isn't ready has none."""
    return video.status == VideoStatus.ready and video.hidden_at is None


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
