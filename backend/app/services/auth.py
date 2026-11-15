import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, Unauthorized
from app.models import RefreshToken, User
from app.schemas.auth import LoginIn, RegisterIn

INVALID_CREDENTIALS = "Invalid email or password"
INVALID_REFRESH = "Invalid or expired refresh token"
# Accounts signed in at once in one browser, as YouTube allows a handful.
MAX_ACCOUNTS = 5


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user_id: uuid.UUID


async def register(session: AsyncSession, data: RegisterIn) -> User:
    # The role is never taken from input: new accounts always get the column default.
    user = User(
        username=data.username,
        email=data.email,
        password_hash=await security.hash_password(data.password),
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


async def login(
    session: AsyncSession, data: LoginIn, signed_in: frozenset[uuid.UUID] = frozenset()
) -> IssuedTokens:
    """`signed_in`: the accounts this browser already holds. Signing in again to one of them
    is fine; a new one beyond MAX_ACCOUNTS is refused."""
    user = await session.scalar(select(User).where(User.email == data.email))
    # Always runs argon2, even for an unknown email, so timing doesn't reveal accounts.
    if not await security.verify_password(user.password_hash if user else None, data.password):
        raise Unauthorized(INVALID_CREDENTIALS)
    assert user is not None  # noqa: S101 - verify_password fails without a hash
    if not user.is_active:
        raise Forbidden("This account is disabled")
    if user.id not in signed_in and len(signed_in) >= MAX_ACCOUNTS:
        raise Conflict(
            f"You're signed in to {MAX_ACCOUNTS} accounts in this browser. "
            "Sign out of one to add another."
        )
    tokens = await _issue_tokens(session, user.id, family_id=uuid.uuid4())
    await session.commit()
    return tokens


async def refresh(
    session: AsyncSession, refresh_token: str | None, user_id: uuid.UUID | None = None
) -> IssuedTokens:
    """Rotates a refresh token: the presented one is revoked and a new one is issued in the
    same family. Presenting an already revoked token means it was copied, so the whole
    family is revoked and both the thief and the victim must log in again (D54). With
    `user_id`, the token must be that account's: a cookie can't stand in for another one."""
    if not refresh_token:
        raise Unauthorized(INVALID_REFRESH)
    now = datetime.now(UTC)
    # The row lock makes concurrent refreshes with one token run one after another, so
    # only the first can rotate it and the second is treated as reuse.
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == security.hash_refresh_token(refresh_token))
        .with_for_update()
    )
    if token is None:
        raise Unauthorized(INVALID_REFRESH)
    if token.revoked_at is not None:
        await _revoke_family(session, token.family_id, now)
        await session.commit()  # Before raising, so the revocation isn't rolled back.
        raise Unauthorized(INVALID_REFRESH)
    if token.expires_at <= now or (user_id is not None and token.user_id != user_id):
        raise Unauthorized(INVALID_REFRESH)
    user = await session.get(User, token.user_id)
    if user is None or not user.is_active:
        await _revoke_family(session, token.family_id, now)
        await session.commit()
        raise Unauthorized(INVALID_REFRESH)

    token.revoked_at = now
    tokens = await _issue_tokens(session, user.id, family_id=token.family_id)
    await session.commit()
    return tokens


async def signed_in_accounts(session: AsyncSession, refresh_tokens: list[str]) -> list[User]:
    """The accounts these tokens still sign in, by name. Nothing is rotated: this is for the
    account switcher, which only shows who's there."""
    if not refresh_tokens:
        return []
    hashes = [security.hash_refresh_token(token) for token in refresh_tokens]
    users = await session.scalars(
        select(User)
        .join(RefreshToken, RefreshToken.user_id == User.id)
        .where(
            RefreshToken.token_hash.in_(hashes),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
        .order_by(User.display_name, User.username)
    )
    return list(users.unique())


async def logout(session: AsyncSession, *refresh_tokens: str | None) -> None:
    """Revokes each token's whole family. Unknown or missing tokens are ignored, so
    logging out is always safe to repeat."""
    hashes = [security.hash_refresh_token(token) for token in refresh_tokens if token]
    if not hashes:
        return
    families = await session.scalars(
        select(RefreshToken.family_id).where(RefreshToken.token_hash.in_(hashes))
    )
    now = datetime.now(UTC)
    for family_id in set(families):
        await _revoke_family(session, family_id, now)
    await session.commit()


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


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
    return IssuedTokens(access_token, expires_in, refresh_token, user_id)
