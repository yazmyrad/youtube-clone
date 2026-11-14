"""The demo video download: only verified files are kept, and nothing stops the install."""

import hashlib
import io
from pathlib import Path

import pytest

from app.services.seed import DemoSource
from app.workers import fetch_demo_media

BODY = b"a demo video"
SOURCE = DemoSource(
    file="clip.mp4",
    url="https://videos.example.com/clip.mp4",
    sha256=hashlib.sha256(BODY).hexdigest(),
    credit="Public domain",
)


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serves BODY for any URL, and records the URLs asked for."""
    asked: list[str] = []

    def urlopen(request: object, timeout: float) -> _Response:
        asked.append(request.full_url)  # type: ignore[attr-defined]
        assert timeout == fetch_demo_media.TIMEOUT_SECONDS
        return _Response(BODY)

    monkeypatch.setattr(fetch_demo_media.urllib.request, "urlopen", urlopen)
    return asked


def test_downloads_and_keeps_a_verified_file(tmp_path: Path, served: list[str]) -> None:
    assert fetch_demo_media.fetch(SOURCE, tmp_path)

    assert (tmp_path / "clip.mp4").read_bytes() == BODY
    assert served == [SOURCE.url]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clip.mp4"]


def test_an_intact_file_is_not_downloaded_again(tmp_path: Path, served: list[str]) -> None:
    (tmp_path / "clip.mp4").write_bytes(BODY)

    assert fetch_demo_media.fetch(SOURCE, tmp_path)
    assert served == []


def test_a_damaged_file_is_downloaded_again(tmp_path: Path, served: list[str]) -> None:
    (tmp_path / "clip.mp4").write_bytes(b"truncated")

    assert fetch_demo_media.fetch(SOURCE, tmp_path)
    assert (tmp_path / "clip.mp4").read_bytes() == BODY


def test_a_wrong_checksum_keeps_nothing(tmp_path: Path, served: list[str]) -> None:
    wrong = DemoSource(SOURCE.file, SOURCE.url, "0" * 64, SOURCE.credit)

    assert not fetch_demo_media.fetch(wrong, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_an_oversized_download_is_dropped(
    tmp_path: Path, served: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_demo_media, "MAX_BYTES", len(BODY) - 1)

    assert not fetch_demo_media.fetch(SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_only_https(tmp_path: Path, served: list[str]) -> None:
    plain = DemoSource(SOURCE.file, "http://videos.example.com/clip.mp4", SOURCE.sha256, "")

    assert not fetch_demo_media.fetch(plain, tmp_path)
    assert served == []


def test_a_network_failure_is_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(*_: object, **__: object) -> None:
        raise OSError("network is unreachable")

    monkeypatch.setattr(fetch_demo_media.urllib.request, "urlopen", unreachable)
    monkeypatch.setenv("DEMO_MEDIA_DIR", str(tmp_path))

    assert not fetch_demo_media.fetch(SOURCE, tmp_path)
    assert fetch_demo_media.main() == 0
    assert list(tmp_path.iterdir()) == []


def test_a_missing_directory_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MEDIA_DIR", str(tmp_path / "absent"))

    assert fetch_demo_media.main() == 1


def test_fetches_every_catalog_video() -> None:
    from app.services.seed import CHANNELS

    expected = [v.source for c in CHANNELS for v in c.videos if v.source]
    assert fetch_demo_media.sources() == expected
