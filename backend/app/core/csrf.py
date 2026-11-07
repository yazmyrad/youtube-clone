from fastapi import Request

from app.core.errors import Forbidden


async def require_same_origin(request: Request) -> None:
    """CSRF guard for endpoints authenticated by cookie (refresh, logout).

    The refresh cookie is already SameSite=Strict; this also rejects requests whose Origin
    isn't this site. Browsers always send Origin on cross-site and same-site POSTs, so a
    missing one is refused too. The scheme comes from X-Forwarded-Proto (set by nginx).
    """
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin or not host or origin != f"{request.url.scheme}://{host}":
        raise Forbidden("Origin not allowed")
