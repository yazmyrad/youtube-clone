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

    minio_endpoint: str = "http://minio:9000"
    # The scoped app user from infra/minio/init.sh, never the root account.
    minio_app_access_key: str
    minio_app_secret_key: SecretStr
    uploads_bucket: str = "uploads"
    # Enforced by storage through the presigned POST policy.
    max_upload_bytes: int = 2 * 1024**3
    upload_url_ttl: timedelta = timedelta(hours=1)

    # A worker that stops renewing its lease for this long is presumed dead.
    job_lease: timedelta = timedelta(seconds=60)
    job_heartbeat_interval: timedelta = timedelta(seconds=20)
    job_poll_interval: timedelta = timedelta(seconds=2)
    # Doubles after each failed attempt.
    job_retry_backoff: timedelta = timedelta(seconds=30)

    ffmpeg_timeout: timedelta = timedelta(hours=6)
    ffmpeg_threads: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=ENV_FILE)
