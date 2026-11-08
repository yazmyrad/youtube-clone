"""Object storage: MinIO through the S3 API. Layout is in architecture.md, section 2."""

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from app.core.config import get_settings

if TYPE_CHECKING:
    from botocore.client import BaseClient

# Same origin for the browser: nginx forwards this path to the bucket. A POST policy's
# signature covers the policy and not the host, so signing for the internal address is fine.
UPLOAD_URL = "/uploads/"


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    fields: dict[str, str]


@lru_cache
def get_client() -> "BaseClient":
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_app_access_key,
        aws_secret_access_key=settings.minio_app_secret_key.get_secret_value(),
        region_name="us-east-1",  # MinIO's default; part of the signature.
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=10,
            retries={"mode": "standard", "max_attempts": 2},
        ),
    )


def raw_key(video_id: uuid.UUID) -> str:
    """Generated on the server and never derived from anything the client sends."""
    return f"raw/{video_id}/source"


def presign_upload(key: str) -> PresignedUpload:
    """A form that can upload exactly `key`, up to the size limit, until it expires.
    Signing only computes an HMAC, so unlike the calls below it doesn't touch the network."""
    settings = get_settings()
    post = get_client().generate_presigned_post(
        settings.uploads_bucket,
        key,
        Conditions=[["content-length-range", 1, settings.max_upload_bytes]],
        ExpiresIn=int(settings.upload_url_ttl.total_seconds()),
    )
    return PresignedUpload(url=UPLOAD_URL, fields=post["fields"])
