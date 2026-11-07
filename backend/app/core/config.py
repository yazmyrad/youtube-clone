from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Optional backend/.env for running the API outside Docker (see .env.example).
# Real environment variables take precedence, so the compose deploy ignores it.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """In Docker, compose passes settings in from the .env that install.sh generates."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=30)
    # Off by default: the IP-only deploy serves plain HTTP. `--domain` mode turns it on.
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=ENV_FILE)
