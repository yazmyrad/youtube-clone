from pathlib import Path

import pytest

from app.services import media
from app.services.jobs import JobError
from tests.media_helpers import make_clip, require_ffmpeg, run_ffmpeg


@pytest.fixture(autouse=True)
def _ffmpeg() -> None:
    require_ffmpeg()


@pytest.mark.parametrize(
    ("name", "codecs", "expected"),
    [
        ("a.mp4", ("-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac"), "mov"),
        ("a.mkv", ("-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac"), "matroska"),
        ("a.webm", ("-c:v", "libvpx", "-c:a", "libvorbis"), "matroska"),
        ("a.avi", ("-c:v", "mpeg4", "-c:a", "libmp3lame"), "avi"),
    ],
)
async def test_allowed_containers(
    tmp_path: Path, name: str, codecs: tuple[str, ...], expected: str
) -> None:
    info = await media.probe(make_clip(tmp_path / name, codecs=codecs))

    assert info.input_format == expected
    assert (info.width, info.height, info.has_audio) == (320, 240, True)
    assert info.duration == pytest.approx(1, abs=0.2)


async def test_the_extension_is_ignored(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "a.mp4")
    renamed = clip.rename(tmp_path / "source")

    assert (await media.probe(renamed)).input_format == "mov"


async def test_text_named_mp4_is_rejected(tmp_path: Path) -> None:
    """D14."""
    fake = tmp_path / "video.mp4"
    fake.write_text("just some text\n")

    with pytest.raises(JobError, match="supported video"):
        await media.probe(fake)


async def test_hls_playlist_is_rejected_before_its_references_are_opened(tmp_path: Path) -> None:
    """D15. Without the whitelist this playlist is accepted and its segment is opened."""
    clip = make_clip(tmp_path / "a.mp4")
    segment = tmp_path / "seg.ts"
    run_ffmpeg("-i", str(clip), "-c", "copy", "-f", "mpegts", str(segment))
    playlist = tmp_path / "evil.m3u8"
    playlist.write_text(
        f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:1,\n{segment}\n#EXT-X-ENDLIST\n"
    )

    with pytest.raises(JobError, match="supported video"):
        await media.probe(playlist)


async def test_a_container_off_the_allowlist_is_rejected(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "a.ts")

    with pytest.raises(JobError, match="supported video"):
        await media.probe(clip)


async def test_audio_only_is_rejected(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "a.mp4", video=False, codecs=("-c:a", "aac"))

    with pytest.raises(JobError, match="no video"):
        await media.probe(clip)


async def test_too_long_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clip = make_clip(tmp_path / "a.mp4", seconds=2)
    monkeypatch.setattr(media, "MAX_DURATION_SECONDS", 1)

    with pytest.raises(JobError, match="at most"):
        await media.probe(clip)


async def test_no_audio_is_reported(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "a.mp4", audio=False, codecs=("-c:v", "libx264"))

    assert (await media.probe(clip)).has_audio is False


async def test_rotation_swaps_the_displayed_size(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "a.mp4")
    rotated = tmp_path / "rotated.mp4"
    run_ffmpeg("-display_rotation", "90", "-i", str(clip), "-c", "copy", str(rotated))

    info = await media.probe(rotated)

    assert (info.width, info.height) == (240, 320)
