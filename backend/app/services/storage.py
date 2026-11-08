"""Object storage: MinIO through the S3 API. Layout is in architecture.md, section 2."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable

if TYPE_CHECKING:
    from botocore.client import BaseClient

logger = logging.getLogger(__name__)

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


def hls_prefix(video_id: uuid.UUID) -> str:
    return f"hls/{video_id}"


def thumbnail_key(video_id: uuid.UUID) -> str:
    return f"thumbs/{video_id}.jpg"


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


async def uploaded_size(key: str) -> int | None:
    """The size of an uploaded object, or None if it doesn't exist."""
    client = get_client()
    bucket = get_settings().uploads_bucket
    try:
        head = await asyncio.to_thread(client.head_object, Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return None
        logger.exception("Storage refused a HEAD request")
        raise ServiceUnavailable("Storage is unavailable, try again") from exc
    except BotoCoreError as exc:
        logger.exception("Storage is unreachable")
        raise ServiceUnavailable("Storage is unavailable, try again") from exc
    return head["ContentLength"]


async def download(bucket: str, key: str, destination: Path) -> None:
    """One stream is plenty on the internal network, and it's simpler to stop."""
    await asyncio.to_thread(
        get_client().download_file,
        bucket,
        key,
        str(destination),
        Config=TransferConfig(use_threads=False),
    )


def _put(bucket: str, key: str, source: Path, content_type: str) -> None:
    with source.open("rb") as body:
        get_client().put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


async def upload_media(key: str, source: Path, content_type: str) -> None:
    """A single PUT: it replaces the object atomically, and client timeouts bound it."""
    await asyncio.to_thread(_put, get_settings().media_bucket, key, source, content_type)
