"""The demo video download: only verified files are kept, and nothing stops the install."""

import email.message
import hashlib
import io
import urllib.error
from pathlib import Path

import pytest

from app.services.seed import DemoSource
from app.workers import fetch_demo_media

# urllib's HTTPError wraps a temporary-file closer that warns when collected, even after
# close(), on some Python versions: an artifact of building the errors by hand here.
pytestmark = pytest.mark.filterwarnings(
    "ignore::ResourceWarning", "ignore::pytest.PytestUnraisableExceptionWarning"
)

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
    monkeypatch.setattr(fetch_demo_media.time, "sleep", lambda _: None)
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


def _busy(code: int = 429, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(SOURCE.url, code, "busy", headers, io.BytesIO(b""))


def test_waits_and_retries_when_the_host_is_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: list[object] = [_busy(retry_after="3"), _busy(503), _Response(BODY)]
    waits: list[float] = []

    def urlopen(request: object, timeout: float) -> _Response:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer  # type: ignore[return-value]

    monkeypatch.setattr(fetch_demo_media.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fetch_demo_media.time, "sleep", waits.append)

    assert fetch_demo_media.fetch(SOURCE, tmp_path)
    assert waits == [3.0, 4.0]
    assert (tmp_path / "clip.mp4").read_bytes() == BODY


def test_gives_up_on_a_file_after_a_few_tries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def urlopen(request: object, timeout: float) -> None:
        calls.append(1)
        raise _busy()

    monkeypatch.setattr(fetch_demo_media.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fetch_demo_media.time, "sleep", lambda _: None)

    assert not fetch_demo_media.fetch(SOURCE, tmp_path)
    assert len(calls) == fetch_demo_media.ATTEMPTS
    assert list(tmp_path.iterdir()) == []


def test_a_missing_file_isnt_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def urlopen(request: object, timeout: float) -> None:
        calls.append(1)
        raise _busy(404)

    monkeypatch.setattr(fetch_demo_media.urllib.request, "urlopen", urlopen)

    assert not fetch_demo_media.fetch(SOURCE, tmp_path)
    assert len(calls) == 1


def test_a_long_retry_after_is_capped() -> None:
    assert (
        fetch_demo_media.retry_after(_busy(retry_after="3600"), 0)
        == fetch_demo_media.MAX_WAIT_SECONDS
    )


def test_names_itself_and_adds_a_contact_only_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_FETCH_CONTACT", raising=False)
    assert fetch_demo_media.user_agent() == (
        "YouTubeCloneDemoFetch/1.0 (self-hosted demo data) Python-urllib"
    )

    monkeypatch.setenv("DEMO_FETCH_CONTACT", "ops@example.org")
    assert "(self-hosted demo data; ops@example.org)" in fetch_demo_media.user_agent()


def test_paces_requests_to_the_same_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    same_host = [
        DemoSource(f"{i}.mp4", f"https://videos.example.com/{i}.mp4", SOURCE.sha256, "")
        for i in range(3)
    ]
    waits: list[float] = []
    monkeypatch.setattr(fetch_demo_media, "sources", lambda: same_host)
    monkeypatch.setattr(fetch_demo_media, "fetch", lambda source, directory: True)
    monkeypatch.setattr(fetch_demo_media.time, "sleep", waits.append)
    monkeypatch.setenv("DEMO_MEDIA_DIR", str(tmp_path))

    assert fetch_demo_media.main() == 0
    assert waits == [fetch_demo_media.PACE_SECONDS] * 2
