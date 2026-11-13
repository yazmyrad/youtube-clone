import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, Unauthorized
from app.core.permissions import ensure_can_manage_user
from app.models import ModerationAction, ModerationActionType, RefreshToken, User
from app.schemas.admin import AdminUserUpdateIn


async def list_users(
    session: AsyncSession, *, q: str | None, cursor: str | None, limit: int
) -> tuple[list[User], str | None]:
    """Users ordered by username, with keyset pagination on it (usernames are unique).
    `q` matches a part of the username or email; `%` and `_` in it are literal."""
    query = select(User).order_by(User.username).limit(limit + 1)
    if q:
        query = query.where(
            or_(
                User.username.contains(q, autoescape=True),
                User.email.contains(q, autoescape=True),
            )
        )
    if cursor:
        query = query.where(User.username > cursor)
    users = list(await session.scalars(query))
    if len(users) > limit:
        return users[:limit], users[limit - 1].username
    return users, None


async def update_user(
    session: AsyncSession, actor: User, user_id: uuid.UUID, data: AdminUserUpdateIn
) -> User:
    # Lock both rows in a fixed order (no deadlocks) and reload them, so the check below
    # sees the actor's current role even if another admin changed it a moment ago.
    rows = await session.scalars(
        select(User)
        .where(User.id.in_({actor.id, user_id}))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    by_id = {user.id: user for user in rows}
    current_actor, target = by_id.get(actor.id), by_id.get(user_id)
    if current_actor is None:
        raise Unauthorized("Invalid or expired token")
    if target is None:
        raise NotFound("User not found")
    ensure_can_manage_user(current_actor, target, role=data.role, is_active=data.is_active)

    def audit(action: ModerationActionType, reason: str = "") -> None:
        session.add(
            ModerationAction(
                actor_id=current_actor.id, action=action, target_user_id=target.id, reason=reason
            )
        )

    if data.role is not None and data.role != target.role:
        audit(ModerationActionType.change_role, f"{target.role.value} -> {data.role.value}")
        target.role = data.role
    if data.is_active is not None and data.is_active != target.is_active:
        audit(
            ModerationActionType.enable_user
            if data.is_active
            else ModerationActionType.disable_user
        )
        target.is_active = data.is_active
        if not data.is_active:
            # Access tokens stop working at once because the user is reloaded on every
            # request; revoking refresh tokens ends the sessions for good.
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
    await session.commit()
    await session.refresh(target)
    return target
