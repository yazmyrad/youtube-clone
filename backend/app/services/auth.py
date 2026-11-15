import uuid
from collections.abc import Iterable
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


async def login(session: AsyncSession, data: LoginIn, held: tuple[str, ...] = ()) -> IssuedTokens:
    """`held`: the refresh tokens this browser already has. Signing in again to one of those
    accounts ends its old session; a new account beyond MAX_ACCOUNTS live ones is refused."""
    user = await session.scalar(select(User).where(User.email == data.email))
    # Always runs argon2, even for an unknown email, so timing doesn't reveal accounts.
    if not await security.verify_password(user.password_hash if user else None, data.password):
        raise Unauthorized(INVALID_CREDENTIALS)
    assert user is not None  # noqa: S101 - verify_password fails without a hash
    if not user.is_active:
        raise Forbidden("This account is disabled")
    rows = await _token_rows(session, held)
    now = datetime.now(UTC)
    live = {row.user_id for row in rows if row.revoked_at is None and row.expires_at > now}
    if user.id not in live and len(live) >= MAX_ACCOUNTS:
        raise Conflict(
            f"You're signed in to {MAX_ACCOUNTS} accounts in this browser. "
            "Sign out of one to add another."
        )
    # Its cookie is about to be replaced: the session it held mustn't outlive it.
    for family_id in {row.family_id for row in rows if row.user_id == user.id}:
        await _revoke_family(session, family_id, now)
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


async def _token_rows(session: AsyncSession, tokens: Iterable[str | None]) -> list[RefreshToken]:
    hashes = [security.hash_refresh_token(token) for token in tokens if token]
    if not hashes:
        return []
    return list(
        await session.scalars(select(RefreshToken).where(RefreshToken.token_hash.in_(hashes)))
    )


async def logout(
    session: AsyncSession, *refresh_tokens: str | None, user_id: uuid.UUID | None = None
) -> set[str]:
    """Revokes each token's whole family; with `user_id`, only tokens of that account, so
    signing out of one can't end another. Returns the tokens it revoked. Unknown or missing
    tokens are ignored, so logging out is always safe to repeat."""
    rows = await _token_rows(session, refresh_tokens)
    if user_id is not None:
        rows = [row for row in rows if row.user_id == user_id]
    now = datetime.now(UTC)
    for family_id in {row.family_id for row in rows}:
        await _revoke_family(session, family_id, now)
    await session.commit()
    revoked = {row.token_hash for row in rows}
    return {t for t in refresh_tokens if t and security.hash_refresh_token(t) in revoked}


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
