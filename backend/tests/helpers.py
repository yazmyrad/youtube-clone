from collections.abc import Awaitable, Callable
from dataclasses import dataclass

PASSWORD = "correct horse battery"


@dataclass
class ApiUser:
    id: str
    username: str
    email: str
    access_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


CreateUser = Callable[..., Awaitable[ApiUser]]
