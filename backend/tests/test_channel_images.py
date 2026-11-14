import io
import re

import httpx
import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.errors import BadRequest, UnsupportedMediaType
from app.services import storage
from app.services.channel_images import CHANNEL_PREFIX, MAX_IMAGE_BYTES, ImageKind, process
from tests.helpers import CreateUser

URL = re.compile(
    r"^/channel-images/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"/(avatar|banner)-[0-9a-f]{32}\.webp$"
)


def _image(
    size: tuple[int, int] = (640, 480),
    fmt: str = "JPEG",
    mode: str = "RGB",
    color: str | tuple[int, ...] = "teal",
    **save: object,
) -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, format=fmt, **save)
    return out.getvalue()


def _open(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


# --- What's made of the file -------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "size"), [(ImageKind.avatar, (256, 256)), (ImageKind.banner, (2048, 340))]
)
def test_an_image_is_cropped_to_its_shape_as_webp(kind: ImageKind, size: tuple[int, int]) -> None:
    out = _open(process(_image((2400, 1600)), "image/jpeg", kind))

    assert (out.format, out.size) == ("WEBP", size)


def test_metadata_is_dropped() -> None:
    exif = Image.Exif()
    exif[0x010F] = "Camera maker"  # Make
    exif[0x8825] = {2: (51, 30, 0)}  # GPS latitude
    out = _open(process(_image(exif=exif.tobytes()), "image/jpeg", ImageKind.avatar))

    assert not out.getexif()
    assert "exif" not in out.info


def test_transparency_is_kept() -> None:
    out = _open(
        process(
            _image(fmt="PNG", mode="RGBA", color=(0, 128, 128, 0)), "image/png", ImageKind.avatar
        )
    )

    assert out.mode == "RGBA"


def test_a_photo_taken_sideways_is_turned_upright() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotated 90° clockwise
    # 400 wide and 1200 tall once upright: too narrow for a banner only if it was turned.
    sideways = _image((1200, 400), exif=exif.tobytes())

    with pytest.raises(BadRequest, match="too small"):
        process(sideways, "image/jpeg", ImageKind.banner)


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"not an image at all", "image/png"),
        (_image(fmt="PNG"), "image/jpeg"),  # Not what it says it is.
        (_image()[:200], "image/jpeg"),  # Cut short.
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/webp"),
    ],
)
def test_a_file_that_isnt_that_image_is_refused(data: bytes, content_type: str) -> None:
    with pytest.raises(BadRequest, match="isn't a valid image"):
        process(data, content_type, ImageKind.avatar)


@pytest.mark.parametrize("content_type", ["image/gif", "image/svg+xml", "text/html", ""])
def test_other_types_are_refused(content_type: str) -> None:
    with pytest.raises(UnsupportedMediaType):
        process(_image(), content_type, ImageKind.avatar)


def test_a_huge_picture_is_refused_before_decoding() -> None:
    # 30 megapixels in a file of a few kilobytes.
    bomb = _image((6000, 5000), fmt="PNG", mode="1")
    assert len(bomb) < 100_000

    with pytest.raises(BadRequest, match="too large"):
        process(bomb, "image/png", ImageKind.banner)


def test_a_tiny_picture_is_refused() -> None:
    with pytest.raises(BadRequest, match="too small"):
        process(_image((50, 50)), "image/jpeg", ImageKind.avatar)


# --- Through the API ---------------------------------------------------------------------


def _stored(url: str) -> bytes | None:
    key = CHANNEL_PREFIX + url.removeprefix("/channel-images/")
    client = storage.get_client()
    try:
        return client.get_object(Bucket=get_settings().media_bucket, Key=key)["Body"].read()
    except client.exceptions.NoSuchKey:
        return None


async def _put(
    api: httpx.AsyncClient,
    headers: dict[str, str],
    kind: str,
    data: bytes,
    content_type: str = "image/jpeg",
) -> httpx.Response:
    return await api.put(
        f"/api/users/me/images/{kind}",
        headers={**headers, "Content-Type": content_type},
        content=data,
    )


@pytest.mark.parametrize("kind", ["avatar", "banner"])
async def test_owner_sets_an_image_shown_on_the_channel(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str, kind: str
) -> None:
    alice = await create_user("alice")

    response = await _put(api, alice.headers, kind, _image((2400, 1600)))

    assert response.status_code == 200, response.text
    url = response.json()[f"{kind}_url"]
    assert URL.match(url)
    assert _open(_stored(url) or b"").format == "WEBP"
    channel = (await api.get("/api/channels/alice")).json()
    assert channel[f"{kind}_url"] == url


async def test_a_new_image_replaces_the_old_one(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    alice = await create_user("alice")
    first = (await _put(api, alice.headers, "avatar", _image())).json()["avatar_url"]

    second = (await _put(api, alice.headers, "avatar", _image())).json()["avatar_url"]

    assert second != first  # A new URL, so caches never show the old picture.
    assert _stored(first) is None
    assert _stored(second) is not None


async def test_owner_removes_an_image(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    alice = await create_user("alice")
    url = (await _put(api, alice.headers, "avatar", _image())).json()["avatar_url"]

    response = await api.delete("/api/users/me/images/avatar", headers=alice.headers)
    again = await api.delete("/api/users/me/images/avatar", headers=alice.headers)

    assert (response.status_code, again.status_code) == (200, 200)
    assert response.json()["avatar_url"] is None
    assert _stored(url) is None
    assert (await api.get("/api/channels/alice")).json()["avatar_url"] is None


async def test_the_avatar_follows_the_channel_around(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    alice = await create_user("alice")
    bob = await create_user("bob")
    url = (await _put(api, alice.headers, "avatar", _image())).json()["avatar_url"]
    await api.put("/api/channels/alice/subscription", headers=bob.headers)

    subscriptions = (await api.get("/api/users/me/subscriptions", headers=bob.headers)).json()

    assert subscriptions["items"][0]["avatar_url"] == url


async def test_images_need_a_login(api: httpx.AsyncClient) -> None:
    put = await _put(api, {}, "avatar", _image())
    delete = await api.delete("/api/users/me/images/avatar")

    assert (put.status_code, delete.status_code) == (401, 401)


async def test_only_avatar_and_banner(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    alice = await create_user("alice")

    response = await _put(api, alice.headers, "history", _image())

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("data", "content_type", "status"),
    [
        (_image(), "image/gif", 415),
        (_image(), "application/octet-stream", 415),
        (b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg", 413),
        (b"not an image", "image/jpeg", 400),
    ],
)
async def test_bad_uploads_are_refused_and_change_nothing(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    data: bytes,
    content_type: str,
    status: int,
) -> None:
    alice = await create_user("alice")

    response = await _put(api, alice.headers, "avatar", data, content_type)

    assert response.status_code == status, response.text
    assert (await api.get("/api/users/me", headers=alice.headers)).json()["avatar_url"] is None


async def test_storage_down_keeps_the_old_image(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice = await create_user("alice")  # Storage is unreachable without the minio fixture.

    response = await _put(api, alice.headers, "avatar", _image())

    assert response.status_code == 503
    assert (await api.get("/api/users/me", headers=alice.headers)).json()["avatar_url"] is None
