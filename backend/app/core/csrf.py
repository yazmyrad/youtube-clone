from fastapi import Request

from app.core.config import get_settings
from app.core.errors import Forbidden


async def require_same_origin(request: Request) -> None:
    """CSRF guard for endpoints authenticated by cookie (refresh, logout).

    The refresh cookie is already SameSite=Strict; this also rejects requests whose Origin
    isn't this site. Browsers always send Origin on cross-site and same-site POSTs, so a
    missing one is refused too. The site's origin is PUBLIC_ORIGIN when set (`--domain`
    mode), else the scheme from X-Forwarded-Proto (set by nginx) with the Host.
    """
    origin = request.headers.get("origin")
    expected = get_settings().public_origin
    if expected is None:
        host = request.headers.get("host")
        expected = f"{request.url.scheme}://{host}" if host else None
    if not origin or origin != expected:
        raise Forbidden("Origin not allowed")
