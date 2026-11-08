"""Password hashing, access tokens (JWT) and refresh token values. No database access here."""

import asyncio
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
MEDIA_SCOPE_HLS = "hls"
MEDIA_SCOPE_THUMB = "thumb"
_MEDIA_SCOPES = {MEDIA_SCOPE_HLS, MEDIA_SCOPE_THUMB}

_hasher = PasswordHasher()
# Verified against when the user doesn't exist, so an unknown email takes as long as a
# wrong password and the response time doesn't reveal which emails are registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


# argon2 is CPU-heavy on purpose; it runs in a thread so it doesn't stall the event loop.
async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    return await asyncio.to_thread(_verify, password_hash, password)


def _verify(password_hash: str | None, password: str) -> bool:
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


def _media_signature(scope: str, video_id: str, exp: str) -> bytes:
    secret = get_settings().playback_secret.get_secret_value().encode()
    message = f"{scope}:{video_id}:{exp}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest().encode()


def sign_media(scope: str, video_id: uuid.UUID, exp: int) -> str:
    """The signature for a media URL. It covers the scope, so an HLS token can't open a
    thumbnail, and the video, so it can't be replayed against another one."""
    return _media_signature(scope, str(video_id), str(exp)).decode()


def verify_media(scope: str, video_id: str, exp: str, sig: str) -> bool:
    """Checks untrusted strings from a media request. Needs no database, so it's cheap
    enough to run per segment. Anything malformed is simply invalid."""
    try:
        if scope not in _MEDIA_SCOPES or str(uuid.UUID(video_id)) != video_id:
            return False
        if not (exp.isascii() and exp.isdecimal()) or int(exp) <= time.time():
            return False
        return hmac.compare_digest(_media_signature(scope, video_id, exp), sig.encode())
    except ValueError:
        return False
