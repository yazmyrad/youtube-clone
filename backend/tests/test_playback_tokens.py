import time
import uuid

import pytest

from app.core import security
from app.core.security import MEDIA_SCOPE_HLS, MEDIA_SCOPE_THUMB, sign_media, verify_media

VIDEO = uuid.uuid4()
OTHER_VIDEO = uuid.uuid4()


def _future() -> int:
    return int(time.time()) + 600


def _verify(scope: str, video_id: object, exp: object, sig: str) -> bool:
    return verify_media(scope, str(video_id), str(exp), sig)


def test_a_signed_url_verifies() -> None:
    exp = _future()

    assert _verify(MEDIA_SCOPE_HLS, VIDEO, exp, sign_media(MEDIA_SCOPE_HLS, VIDEO, exp))


def test_tampered_signature_is_rejected() -> None:
    exp = _future()
    sig = sign_media(MEDIA_SCOPE_HLS, VIDEO, exp)
    flipped = ("0" if sig[0] != "0" else "1") + sig[1:]

    assert not _verify(MEDIA_SCOPE_HLS, VIDEO, exp, flipped)


def test_extended_expiry_is_rejected() -> None:
    exp = _future()

    assert not _verify(MEDIA_SCOPE_HLS, VIDEO, exp + 1, sign_media(MEDIA_SCOPE_HLS, VIDEO, exp))


def test_token_for_another_video_is_rejected() -> None:
    exp = _future()

    assert not _verify(MEDIA_SCOPE_HLS, OTHER_VIDEO, exp, sign_media(MEDIA_SCOPE_HLS, VIDEO, exp))


def test_token_for_another_scope_is_rejected() -> None:
    exp = _future()

    assert not _verify(MEDIA_SCOPE_THUMB, VIDEO, exp, sign_media(MEDIA_SCOPE_HLS, VIDEO, exp))


def test_expired_token_is_rejected() -> None:
    exp = int(time.time()) - 1

    assert not _verify(MEDIA_SCOPE_HLS, VIDEO, exp, sign_media(MEDIA_SCOPE_HLS, VIDEO, exp))


def test_token_signed_with_another_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = _future()
    sig = sign_media(MEDIA_SCOPE_HLS, VIDEO, exp)
    monkeypatch.setenv("PLAYBACK_SECRET", "another-secret-" + "z" * 32)
    security.get_settings.cache_clear()

    assert not _verify(MEDIA_SCOPE_HLS, VIDEO, exp, sig)


@pytest.mark.parametrize(
    ("scope", "video_id", "exp", "sig"),
    [
        ("", "", "", ""),
        ("hls", "not-a-uuid", "9999999999", "ab"),
        ("hls", str(VIDEO).upper(), "9999999999", "ab"),
        ("hls", str(VIDEO), "soon", "ab"),
        ("hls", str(VIDEO), "-1", "ab"),
        ("hls", str(VIDEO), "٣٣٣", "ab"),
        ("hls", str(VIDEO), "9" * 5000, "ab"),
        ("hls", str(VIDEO), "9999999999", "é"),
        ("other", str(VIDEO), "9999999999", "ab"),
    ],
)
def test_malformed_input_is_invalid_and_never_raises(
    scope: str, video_id: str, exp: str, sig: str
) -> None:
    assert verify_media(scope, video_id, exp, sig) is False
