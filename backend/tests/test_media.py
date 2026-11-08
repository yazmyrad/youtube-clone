import asyncio
import os
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


async def _transcode(tmp_path: Path, **clip: object) -> media.Transcoded:
    source = make_clip(tmp_path / "a.mp4", **clip)  # type: ignore[arg-type]
    output = tmp_path / "out"
    output.mkdir()
    return await media.transcode(source, await media.probe(source), output)


def _variants(result: media.Transcoded) -> list[str]:
    return [line for line in result.master.read_text().splitlines() if line.endswith(".m3u8")]


async def test_small_source_gives_360p_only_and_a_thumbnail(tmp_path: Path) -> None:
    """D16."""
    result = await _transcode(tmp_path, size="640x480")

    assert _variants(result) == ["360p/index.m3u8"]
    assert "RESOLUTION=480x360" in result.master.read_text()
    assert list((result.hls_dir / "360p").glob("seg_*.ts"))
    assert not (result.hls_dir / "720p").exists()
    assert result.thumbnail.read_bytes().startswith(b"\xff\xd8")


async def test_720p_source_gives_both_renditions(tmp_path: Path) -> None:
    """D16."""
    result = await _transcode(tmp_path, size="1280x720")

    assert _variants(result) == ["360p/index.m3u8", "720p/index.m3u8"]
    assert "RESOLUTION=1280x720" in result.master.read_text()
    assert list((result.hls_dir / "720p").glob("seg_*.ts"))


async def test_never_upscales(tmp_path: Path) -> None:
    result = await _transcode(tmp_path, size="320x240")

    assert "RESOLUTION=320x240" in result.master.read_text()


async def test_no_audio_still_transcodes(tmp_path: Path) -> None:
    """D17."""
    result = await _transcode(tmp_path, audio=False, codecs=("-c:v", "libx264"))

    assert list((result.hls_dir / "360p").glob("seg_*.ts"))


async def test_segments_are_six_seconds_and_relative(tmp_path: Path) -> None:
    result = await _transcode(tmp_path, size="320x240", seconds=8)

    playlist = (result.hls_dir / "360p" / "index.m3u8").read_text().splitlines()
    durations = [float(line[8:].rstrip(",")) for line in playlist if line.startswith("#EXTINF:")]
    assert len(durations) == 2
    assert durations[0] == pytest.approx(6, abs=0.1)
    assert "seg_00000.ts" in playlist
    assert "#EXT-X-ENDLIST" in playlist


async def test_a_rotated_source_uses_its_displayed_height(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "a.mp4", size="1280x720")
    rotated = tmp_path / "rotated.mp4"
    run_ffmpeg("-display_rotation", "90", "-i", str(clip), "-c", "copy", str(rotated))
    output = tmp_path / "out"
    output.mkdir()

    result = await media.transcode(rotated, await media.probe(rotated), output)

    assert _variants(result) == ["360p/index.m3u8", "720p/index.m3u8"]
    text = result.master.read_text()
    assert "RESOLUTION=202x360" in text or "RESOLUTION=204x360" in text
    assert "RESOLUTION=404x720" in text or "RESOLUTION=406x720" in text


async def test_a_broken_source_gives_a_readable_error(tmp_path: Path) -> None:
    source = make_clip(tmp_path / "a.mp4")
    info = await media.probe(source)
    source.write_text("gone bad after the probe")
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(JobError, match="converted"):
        await media.transcode(source, info, output)


async def test_a_timeout_stops_the_tool() -> None:
    with pytest.raises(JobError, match="too long"):
        await media._run(["sleep", "30"], 0.05)


async def test_cancelling_kills_the_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    command = ["sh", "-c", f'echo $$ > "{pid_file}"; exec sleep 30']
    running = asyncio.ensure_future(media._run(command, 60))
    async with asyncio.timeout(5):
        while not pid_file.exists() or not pid_file.read_text().strip():  # noqa: ASYNC110 - another process writes it
            await asyncio.sleep(0.01)

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


async def test_an_oversized_frame_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = make_clip(tmp_path / "a.mp4", size="320x240")
    monkeypatch.setattr(media, "MAX_FRAME_PIXELS", 320 * 240 - 1)

    with pytest.raises(JobError, match="4K"):
        await media.probe(clip)


async def test_a_frame_at_the_limit_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = make_clip(tmp_path / "a.mp4", size="320x240")
    monkeypatch.setattr(media, "MAX_FRAME_PIXELS", 320 * 240)

    assert (await media.probe(clip)).height == 240


async def test_the_decoder_refuses_frames_the_probe_did_not_see(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_clip(tmp_path / "a.mp4", size="320x240")
    info = await media.probe(source)
    output = tmp_path / "out"
    output.mkdir()
    monkeypatch.setattr(media, "MAX_FRAME_PIXELS", 320 * 240 - 1)

    with pytest.raises(JobError, match="converted"):
        await media.transcode(source, info, output)
