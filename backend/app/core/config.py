from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Read from the environment only: install.sh generates .env and compose passes it in."""

    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
