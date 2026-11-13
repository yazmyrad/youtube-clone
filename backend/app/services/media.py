"""ffprobe and ffmpeg. The input is hostile: its extension and declared type mean nothing."""

import asyncio
import json
import logging
import math
import os
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.jobs import JobError

logger = logging.getLogger(__name__)

# The demuxer names ffprobe reports, mapped to the format forced on ffmpeg's input. Anything
# else never gets demuxed, including HLS playlists, which would open the files they reference.
FORMATS = {"mov,mp4,m4a,3gp,3g2,mj2": "mov", "matroska,webm": "matroska", "avi": "avi"}
FORMAT_WHITELIST = ",".join(FORMATS)
MAX_DURATION_SECONDS = 2 * 60 * 60
# 4K. A huge declared frame would otherwise get the worker killed for memory.
MAX_FRAME_PIXELS = 4096 * 2160
PROBE_TIMEOUT_SECONDS = 60
STDERR_TAIL_BYTES = 2000

UNSUPPORTED = "This file isn't a supported video"
TRANSCODE_FAILED = "This video couldn't be converted"

SEGMENT_SECONDS = 6
MAX_FPS = "30"
# Rendition name (also the object path), height and video bitrate cap.
LADDER = (("360p", 360, "1000k"), ("720p", 720, "3000k"))
# The header's duration is a claim. Output stops just past it, so a file holding far more than
# it declares can't run for hours or fill the disk.
DURATION_MARGIN_SECONDS = 1
# Container overhead and bitrate peaks on top of the measured average, for the master playlist.
BANDWIDTH_MARGIN = 1.2


class ToolFailed(Exception):
    """ffprobe or ffmpeg exited with an error. The text is internal."""


@dataclass(frozen=True)
class SourceInfo:
    input_format: str
    video_stream: int
    duration: float
    # As displayed, so with any rotation applied.
    width: int
    height: int
    has_audio: bool


@dataclass(frozen=True)
class Rendition:
    name: str
    width: int
    height: int
    max_rate: str


@dataclass(frozen=True)
class Transcoded:
    hls_dir: Path
    master: Path
    thumbnail: Path


async def _run(args: list[str], limit_seconds: float) -> bytes:
    """Runs a tool and returns its stdout. The process never outlives this call."""
    with tempfile.TemporaryFile() as stderr:
        process = await asyncio.create_subprocess_exec(
            *args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), limit_seconds)
        except TimeoutError as exc:
            raise JobError("Processing this video took too long") from exc
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode != 0:
            stderr.seek(max(0, os.fstat(stderr.fileno()).st_size - STDERR_TAIL_BYTES))
            tail = stderr.read().decode(errors="replace")
            raise ToolFailed(f"{Path(args[0]).name} exited with {process.returncode}: {tail}")
    return output


def _rotation(stream: dict[str, Any]) -> int:
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            return int(side_data["rotation"])
    return 0


async def probe(path: Path) -> SourceInfo:
    """Validates the file by its actual contents. Raises JobError if it can't be used."""
    try:
        output = await _run(
            [
                "ffprobe",
                "-v", "error",
                "-protocol_whitelist", "file",
                "-format_whitelist", FORMAT_WHITELIST,
                "-show_entries",
                "format=format_name,duration:stream=index,codec_type,width,height"
                ":stream_disposition=attached_pic:stream_side_data=rotation",
                "-of", "json",
                str(path),
            ],
            PROBE_TIMEOUT_SECONDS,
        )  # fmt: skip
    except ToolFailed as exc:
        logger.info("Rejected by ffprobe: %s", exc)
        raise JobError(UNSUPPORTED) from exc

    info = json.loads(output)
    input_format = FORMATS.get(info.get("format", {}).get("format_name", ""))
    if input_format is None:
        raise JobError(UNSUPPORTED)

    streams = info.get("streams", [])
    # Cover art is stored as a video stream, and can come before the real one.
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if video is None or not video.get("width") or not video.get("height"):
        raise JobError("This file has no video in it")

    if video["width"] * video["height"] > MAX_FRAME_PIXELS:
        raise JobError("Videos can be at most 4K")

    try:
        duration = float(info["format"]["duration"])
    except (KeyError, ValueError) as exc:
        raise JobError("Couldn't read this video's length") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise JobError("Couldn't read this video's length")
    if duration > MAX_DURATION_SECONDS:
        raise JobError("Videos can be at most 2 hours long")

    width, height = video["width"], video["height"]
    if _rotation(video) % 180 != 0:
        width, height = height, width
    return SourceInfo(
        input_format=input_format,
        video_stream=video["index"],
        duration=duration,
        width=width,
        height=height,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def _even(value: float) -> int:
    return max(2, round(value / 2) * 2)


def renditions_for(info: SourceInfo) -> list[Rendition]:
    """360p, or the source's own height if lower, plus 720p for tall enough sources."""
    result = []
    for name, target, max_rate in LADDER:
        if target > 360 and info.height < target:
            continue
        height = _even(min(target, info.height))
        result.append(Rendition(name, _even(info.width * height / info.height), height, max_rate))
    return result


def _input_args(source: Path, info: SourceInfo) -> list[str]:
    """The format is forced to the probed one, and only local files can be opened."""
    return [
        "-protocol_whitelist", "file",
        "-max_pixels", str(MAX_FRAME_PIXELS),  # The probe saw one frame; a stream can change size.
        "-f", info.input_format,
        "-i", str(source),
    ]  # fmt: skip


def _output_args(rendition: Rendition, label: str, directory: Path, duration: float) -> list[str]:
    settings = get_settings()
    return [
        "-map", f"[{label}]",
        "-map", "0:a:0?",  # The question mark: a source without audio is fine.
        "-sn", "-dn",
        "-t", str(duration + DURATION_MARGIN_SECONDS),
        "-threads", str(settings.ffmpeg_threads),
        "-fpsmax", MAX_FPS,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-profile:v", "main",
        "-pix_fmt", "yuv420p",
        "-maxrate", rendition.max_rate,
        "-bufsize", rendition.max_rate,
        # Keyframes at fixed times line the renditions up, so players can switch between them.
        "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SECONDS})",
        "-sc_threshold", "0",
        "-c:a", "aac",
        "-b:a", "96k",
        "-ac", "2",
        "-ar", "48000",
        "-f", "hls",
        "-hls_time", str(SEGMENT_SECONDS),
        "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", str(directory / "seg_%05d.ts"),
        str(directory / "index.m3u8"),
    ]  # fmt: skip


async def _encode(args: list[str]) -> None:
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", *args]
    try:
        await _run(command, get_settings().ffmpeg_timeout.total_seconds())
    except ToolFailed as exc:
        logger.warning("ffmpeg failed: %s", exc)
        raise JobError(TRANSCODE_FAILED) from exc


def _write_master(hls_dir: Path, renditions: list[Rendition], duration: float) -> Path:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for rendition in renditions:
        size = sum(f.stat().st_size for f in (hls_dir / rendition.name).glob("seg_*.ts"))
        bandwidth = max(1, round(size * 8 / duration * BANDWIDTH_MARGIN))
        lines.append(
            f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},"
            f"RESOLUTION={rendition.width}x{rendition.height}"
        )
        lines.append(f"{rendition.name}/index.m3u8")
    master = hls_dir / "master.m3u8"
    master.write_text("\n".join(lines) + "\n")
    return master


async def transcode(source: Path, info: SourceInfo, output: Path) -> Transcoded:
    """Writes `hls/` and `thumbnail.jpg` under `output`. Cancelling kills ffmpeg."""
    renditions = renditions_for(info)
    hls_dir = output / "hls"
    outputs: list[str] = []
    splits = "".join(f"[s{i}]" for i in range(len(renditions)))
    filters = [f"[0:{info.video_stream}]split={len(renditions)}{splits}"]
    for i, rendition in enumerate(renditions):
        directory = hls_dir / rendition.name
        directory.mkdir(parents=True)
        filters.append(f"[s{i}]scale={rendition.width}:{rendition.height}[o{i}]")
        outputs += _output_args(rendition, f"o{i}", directory, info.duration)
    await _encode([*_input_args(source, info), "-filter_complex", ";".join(filters), *outputs])

    thumbnail = output / "thumbnail.jpg"
    smallest = renditions[0]
    await _encode(
        [
            "-ss", str(min(1.0, info.duration / 2)),
            *_input_args(source, info),
            "-map", f"0:{info.video_stream}",
            "-frames:v", "1",
            "-vf", f"scale={smallest.width}:{smallest.height}",
            "-q:v", "3",
            "-update", "1",
            str(thumbnail),
        ]
    )  # fmt: skip
    if not thumbnail.exists():
        raise JobError(TRANSCODE_FAILED)

    master = _write_master(hls_dir, renditions, info.duration)
    return Transcoded(hls_dir=hls_dir, master=master, thumbnail=thumbnail)


# Demo clips. Installed with ffmpeg on Debian and Ubuntu, through fontconfig's dependencies.
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
TITLE_CARD_TIMEOUT_SECONDS = 120
# DejaVu Sans Bold at 72 px averages about 45 px a character; 1280 px less the margins.
TITLE_LINE_CHARS = 24
TITLE_LINE_HEIGHT = 92


@dataclass(frozen=True)
class TitleCard:
    title: str
    channel: str
    tag: str
    color: str  # RRGGBB
    tone_hz: int
    seconds: int


def _title_lines(title: str) -> list[str]:
    """Breaks a title so each line fits the frame at the title's font size."""
    return textwrap.wrap(title, TITLE_LINE_CHARS) or [""]


async def render_title_card(card: TitleCard, path: Path) -> None:
    """Writes a 720p H.264/AAC clip: the title on a solid color, the channel and a topic tag.

    Text goes through files with expansion off, so no title can break out of the filter
    syntax or run drawtext's %{...} functions."""
    lines = _title_lines(card.title)
    texts = {f"title{i}": line for i, line in enumerate(lines)}
    texts |= {"channel": card.channel, "tag": card.tag}
    bold, regular, mono = (
        FONT_DIR / f"DejaVu{face}.ttf" for face in ("Sans-Bold", "Sans", "SansMono-Bold")
    )

    def text(name: str, font: Path, style: str) -> str:
        file = path.with_suffix(f".{name}.txt")
        return f"drawtext=fontfile={font}:textfile={file}:expansion=none:{style}"

    # One drawtext per line, each centered: this ffmpeg can't center lines within a block.
    top = (720 - len(lines) * TITLE_LINE_HEIGHT) // 2
    titles = [
        text(name, bold, f"fontcolor=white:fontsize=72:x=(w-tw)/2:y={top + i * TITLE_LINE_HEIGHT}")
        for i, name in enumerate(n for n in texts if n.startswith("title"))
    ]
    video = ",".join(
        (
            *titles,
            text("channel", regular, "fontcolor=white@0.85:fontsize=36:x=64:y=h-100"),
            text("tag", mono, "fontcolor=white@0.7:fontsize=32:x=64:y=64"),
        )
    )
    seconds = str(card.seconds)
    try:
        for name, value in texts.items():
            path.with_suffix(f".{name}.txt").write_text(value, encoding="utf-8")
        await _run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-y",
                "-f", "lavfi", "-i", f"color=c=0x{card.color}:s=1280x720:r=24:d={seconds}",
                "-f", "lavfi", "-i", f"sine=f={card.tone_hz}:d={seconds}",
                "-vf", video, "-af", "volume=0.2",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(path),
            ],
            TITLE_CARD_TIMEOUT_SECONDS,
        )  # fmt: skip
    finally:
        for name in texts:
            path.with_suffix(f".{name}.txt").unlink(missing_ok=True)
