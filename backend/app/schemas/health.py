from typing import Literal

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]
