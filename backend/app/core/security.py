"""Password hashing, access tokens (JWT) and refresh token values. No database access here."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"

_hasher = PasswordHasher()
# Verified against when the user doesn't exist, so an unknown email takes as long as a
# wrong password and the response time doesn't reveal which emails are registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Returns the token and its lifetime in seconds."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + settings.access_token_ttl}
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, int(settings.access_token_ttl.total_seconds())


def decode_access_token(token: str) -> uuid.UUID | None:
    """The user ID from a valid, unexpired token, or None. Only HS256 is accepted."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()
