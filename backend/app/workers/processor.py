"""Turns a claimed job into media files. Must be cancellable: a lost lease cancels it."""

import shutil
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services import jobs, media, storage
from app.services.jobs import ClaimedJob, JobError, MediaResult

SCRATCH_PREFIX = "job-"
CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".jpg": "image/jpeg",
}


class LeaseLost(Exception):
    """Another worker owns the job now, so this one must not publish."""


def clear_scratch() -> None:
    """Removes what a killed worker left behind. Only called at startup, with no job running."""
    for leftover in get_settings().worker_scratch_dir.glob(f"{SCRATCH_PREFIX}*"):
        shutil.rmtree(leftover, ignore_errors=True)


async def _upload(key: str, path: Path) -> None:
    await storage.upload_media(key, path, CONTENT_TYPES[path.suffix])


async def _publish(claim: ClaimedJob, result: media.Transcoded, prefix: str) -> None:
    """The master playlist goes last: it's what makes the video playable.

    Renewing first gives this worker a full lease, which outlasts the single PUT below,
    so a worker that has been replaced can't overwrite what the new one published.
    """
    async with get_sessionmaker()() as session:
        if not await jobs.heartbeat(session, claim):
            raise LeaseLost
    await _upload(f"{prefix}/{result.master.name}", result.master)


async def process(claim: ClaimedJob) -> MediaResult:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        raw_key = await jobs.source_key(session, claim.video_id)
    if raw_key is None:
        raise JobError("The uploaded file is missing")

    with tempfile.TemporaryDirectory(
        prefix=SCRATCH_PREFIX, dir=settings.worker_scratch_dir
    ) as scratch:
        source = Path(scratch) / "source"
        await storage.download(settings.uploads_bucket, raw_key, source)
        info = await media.probe(source)
        output = Path(scratch) / "output"
        output.mkdir()
        result = await media.transcode(source, info, output)

        prefix = storage.hls_prefix(claim.video_id)
        files = (p for p in result.hls_dir.rglob("*") if p.is_file() and p != result.master)
        # Segments before the playlists that name them.
        for path in sorted(files, key=lambda p: (p.suffix != ".ts", p)):
            await _upload(f"{prefix}/{path.relative_to(result.hls_dir)}", path)
        thumbnail = storage.thumbnail_key(claim.video_id)
        await _upload(thumbnail, result.thumbnail)
        await _publish(claim, result, prefix)

    return MediaResult(
        hls_prefix=prefix,
        thumbnail_key=thumbnail,
        duration_seconds=max(1, round(info.duration)),
    )
