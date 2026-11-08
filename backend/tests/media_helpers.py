import os
import shutil
import subprocess
from pathlib import Path

import pytest


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    if os.environ.get("CI"):
        pytest.fail("CI must install ffmpeg")
    pytest.skip("needs ffmpeg on the host: sudo apt install ffmpeg")


def run_ffmpeg(*args: str) -> None:
    command = ["ffmpeg", "-v", "error", "-y", *args]
    subprocess.run(command, check=True)  # noqa: S603 - fixed tool, arguments from the test itself


def make_clip(
    path: Path,
    *,
    size: str = "320x240",
    seconds: float = 1,
    audio: bool = True,
    video: bool = True,
    codecs: tuple[str, ...] = ("-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac"),
) -> Path:
    """A tiny generated clip, so no binaries live in git."""
    args: list[str] = []
    if video:
        args += ["-f", "lavfi", "-i", f"testsrc=d={seconds}:s={size}:r=24"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=d={seconds}"]
    run_ffmpeg(*args, *codecs, str(path))
    return path
