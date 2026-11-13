"""Facts about the caller that come from the request rather than the account."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request


@dataclass(frozen=True)
class ClientInfo:
    ip: str
    user_agent: str


def get_client_info(request: Request) -> ClientInfo:
    """nginx sets X-Real-IP from the connection, overwriting anything the client sent, and
    the API is reachable only through nginx. Without it (tests), the socket's address."""
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
    return ClientInfo(ip=ip, user_agent=request.headers.get("user-agent", "")[:512])


ClientDep = Annotated[ClientInfo, Depends(get_client_info)]
