"""A channel's avatar and banner: checked, cropped and re-encoded here, then stored as WebP.

Re-encoding means what's served is only ever pixels this code wrote: no metadata (location
in a photo's EXIF), no trailing bytes, no second format hiding in the file.
"""

import asyncio
import io
import logging
import secrets
import warnings
from dataclasses import dataclass
from enum import StrEnum

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    BadRequest,
    PayloadTooLarge,
    ServiceUnavailable,
    UnsupportedMediaType,
)
from app.models import User
from app.services import storage

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 6 * 1024 * 1024
# A small file can still decode to a huge picture ("decompression bomb"): refused before
# decoding, by the size in its header.
MAX_PIXELS = 25_000_000
ACCEPTED_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
CHANNEL_PREFIX = "channels/"
# Images decode in threads; this bounds the memory they take at once.
_decoding = asyncio.Semaphore(2)


class ImageKind(StrEnum):
    avatar = "avatar"
    banner = "banner"


@dataclass(frozen=True)
class Shape:
    size: tuple[int, int]
    min_size: tuple[int, int]


# YouTube's own: a square avatar, and a wide banner of which every screen shows the middle.
SHAPES = {
    ImageKind.avatar: Shape(size=(256, 256), min_size=(98, 98)),
    ImageKind.banner: Shape(size=(2048, 340), min_size=(1024, 170)),
}


def process(data: bytes, content_type: str, kind: ImageKind) -> bytes:
    """The image as WebP in `kind`'s shape, cropped to the middle. Raises BadRequest."""
    fmt = ACCEPTED_TYPES.get(content_type)
    if fmt is None:
        raise UnsupportedMediaType("Upload a JPEG, PNG or WebP image")
    shape = SHAPES[kind]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # `formats` stops Pillow from trying every decoder it has on the bytes.
            with Image.open(io.BytesIO(data), formats=[fmt]) as image:
                width, height = image.size
                if width * height > MAX_PIXELS:
                    raise BadRequest("The image is too large: at most 25 megapixels")
                image.seek(0)  # An animated image: its first frame.
                # As the camera was held: a photo taken sideways is checked and cropped upright.
                upright = ImageOps.exif_transpose(image)
                if upright.width < shape.min_size[0] or upright.height < shape.min_size[1]:
                    raise BadRequest(
                        f"The image is too small: at least {shape.min_size[0]}"
                        f"x{shape.min_size[1]} pixels"
                    )
                alpha = "A" in upright.getbands() or "transparency" in upright.info
                mode = "RGBA" if alpha else "RGB"
                fitted = ImageOps.fit(
                    upright.convert(mode), shape.size, method=Image.Resampling.LANCZOS
                )
    except (BadRequest, UnsupportedMediaType):
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        # Pillow reports a broken file in several ways; all mean the same to the uploader.
        raise BadRequest("This file isn't a valid image") from exc
    out = io.BytesIO()
    fitted.save(out, format="WEBP", quality=85, method=4)
    return out.getvalue()


def new_key(user: User, kind: ImageKind) -> str:
    """A new name for each upload, so a URL's content never changes and caches can keep it."""
    return f"{user.id}/{kind}-{secrets.token_hex(16)}.webp"


async def set_image(
    session: AsyncSession, user: User, kind: ImageKind, data: bytes, content_type: str
) -> User:
    if len(data) > MAX_IMAGE_BYTES:
        raise PayloadTooLarge("The image is too large: at most 6 MB")
    async with _decoding:
        webp = await asyncio.to_thread(process, data, content_type, kind)
    key = new_key(user, kind)
    try:
        await storage.put_media_bytes(CHANNEL_PREFIX + key, webp, "image/webp")
    except Exception as exc:
        logger.exception("Couldn't store a channel image")
        raise ServiceUnavailable("Storage is unavailable, try again") from exc
    old = _swap(user, kind, key)
    await session.commit()
    await session.refresh(user)
    await _forget(old)
    return user


async def remove_image(session: AsyncSession, user: User, kind: ImageKind) -> User:
    old = _swap(user, kind, None)
    await session.commit()
    await session.refresh(user)
    await _forget(old)
    return user


def _swap(user: User, kind: ImageKind, key: str | None) -> str | None:
    column = f"{kind}_key"
    old: str | None = getattr(user, column)
    setattr(user, column, key)
    return old


async def _forget(key: str | None) -> None:
    """After the commit: a leftover object costs a little space, a missing one a broken page."""
    if key is None:
        return
    try:
        await storage.delete_object(get_settings().media_bucket, CHANNEL_PREFIX + key)
    except Exception:
        logger.warning("Couldn't delete an old channel image", exc_info=True)
