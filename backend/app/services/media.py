"""ffprobe and ffmpeg. The input is hostile: its extension and declared type mean nothing."""

import asyncio
import json
import logging
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.jobs import JobError

logger = logging.getLogger(__name__)

# The demuxer names ffprobe reports, mapped to the format forced on ffmpeg's input. Anything
# else never gets demuxed, including HLS playlists, which would open the files they reference.
FORMATS = {"mov,mp4,m4a,3gp,3g2,mj2": "mov", "matroska,webm": "matroska", "avi": "avi"}
FORMAT_WHITELIST = ",".join(FORMATS)
MAX_DURATION_SECONDS = 2 * 60 * 60
PROBE_TIMEOUT_SECONDS = 60
STDERR_TAIL_BYTES = 2000

UNSUPPORTED = "This file isn't a supported video"


class ToolFailed(Exception):
    """ffprobe or ffmpeg exited with an error. The text is internal."""


@dataclass(frozen=True)
class SourceInfo:
    input_format: str
    duration: float
    # As displayed, so with any rotation applied.
    width: int
    height: int
    has_audio: bool


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
                "format=format_name,duration:stream=codec_type,width,height"
                ":stream_side_data=rotation",
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
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None or not video.get("width") or not video.get("height"):
        raise JobError("This file has no video in it")

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
        duration=duration,
        width=width,
        height=height,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )
