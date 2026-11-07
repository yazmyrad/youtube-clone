import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, Unauthorized
from app.models import RefreshToken, User
from app.schemas.auth import LoginIn, RegisterIn

INVALID_CREDENTIALS = "Invalid email or password"


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str


async def register(session: AsyncSession, data: RegisterIn) -> User:
    # The role is never taken from input: new accounts always get the column default.
    user = User(
        username=data.username,
        email=data.email,
        password_hash=security.hash_password(data.password),
        display_name=data.display_name,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        constraint = getattr(exc.orig, "constraint_name", None) or str(exc.orig)
        if "username" in constraint:
            raise Conflict("Username is already taken") from None
        if "email" in constraint:
            raise Conflict("Email is already registered") from None
        raise
    await session.refresh(user)
    return user


async def login(session: AsyncSession, data: LoginIn) -> IssuedTokens:
    user = await session.scalar(select(User).where(User.email == data.email))
    # Always runs argon2, even for an unknown email, so timing doesn't reveal accounts.
    if not security.verify_password(user.password_hash if user else None, data.password):
        raise Unauthorized(INVALID_CREDENTIALS)
    assert user is not None  # noqa: S101 - verify_password fails without a hash
    if not user.is_active:
        raise Forbidden("This account is disabled")
    tokens = await _issue_tokens(session, user.id, family_id=uuid.uuid4())
    await session.commit()
    return tokens


async def _issue_tokens(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID
) -> IssuedTokens:
    """Adds a refresh token row to the session; the caller commits."""
    refresh_token = security.new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=security.hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + get_settings().refresh_token_ttl,
        )
    )
    access_token, expires_in = security.create_access_token(user_id)
    return IssuedTokens(access_token, expires_in, refresh_token)
