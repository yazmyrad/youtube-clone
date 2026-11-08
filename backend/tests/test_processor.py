import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobStatus, ProcessingJob, VideoStatus
from app.services import storage
from app.workers import main as worker
from app.workers import processor
from tests.conftest import TEST_BUCKET, TEST_MEDIA_BUCKET
from tests.job_helpers import claim, enqueue, expire_lease, load_job, load_video
from tests.media_helpers import make_clip, require_ffmpeg


@pytest.fixture(autouse=True)
def _ffmpeg() -> None:
    require_ffmpeg()


def _scratch_dirs(root: Path) -> list[Path]:
    return list(root.glob(f"{processor.SCRATCH_PREFIX}*"))


def _media_keys() -> set[str]:
    listing = storage.get_client().list_objects_v2(Bucket=TEST_MEDIA_BUCKET)
    return {item["Key"] for item in listing.get("Contents", [])}


async def _enqueue_file(
    session: AsyncSession, content: bytes, **job_fields: object
) -> ProcessingJob:
    key = f"raw/{uuid.uuid4()}/source"
    storage.get_client().put_object(Bucket=TEST_BUCKET, Key=key, Body=content)
    return await enqueue(session, raw_key=key, **job_fields)


async def test_a_valid_clip_becomes_a_ready_video(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    """D16, through the worker and real storage."""
    clip = make_clip(tmp_path / "clip.mp4", size="1280x720", seconds=2)
    queued = await _enqueue_file(session, clip.read_bytes())

    assert await worker.run_one(processor.process, "w1") is True

    job = await load_job(session, queued.id)
    assert job.status is JobStatus.done, job.last_error
    video = await load_video(session, queued.video_id)
    assert video.status is VideoStatus.ready
    assert video.duration_seconds == 2
    assert video.hls_prefix == f"hls/{queued.video_id}"
    assert video.thumbnail_key == f"thumbs/{queued.video_id}.jpg"
    keys = _media_keys()
    for name in ("master.m3u8", "360p/index.m3u8", "360p/seg_00000.ts", "720p/index.m3u8"):
        assert f"{video.hls_prefix}/{name}" in keys
    assert video.thumbnail_key in keys
    head = storage.get_client().head_object(
        Bucket=TEST_MEDIA_BUCKET, Key=f"{video.hls_prefix}/master.m3u8"
    )
    assert head["ContentType"] == "application/vnd.apple.mpegurl"


async def test_a_text_file_fails_with_a_readable_reason(
    session: AsyncSession, minio: str
) -> None:
    """D14, through the worker and real storage."""
    queued = await _enqueue_file(session, b"not a video at all\n", max_attempts=1)

    await worker.run_one(processor.process, "w1")

    video = await load_video(session, queued.video_id)
    assert (video.status, video.failure_reason) == (
        VideoStatus.failed,
        "This file isn't a supported video",
    )
    assert _media_keys() == set()


async def test_a_replaced_worker_does_not_publish_the_master_playlist(
    session: AsyncSession, minio: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = make_clip(tmp_path / "clip.mp4", seconds=1)
    queued = await _enqueue_file(session, clip.read_bytes())
    real_upload = storage.upload_media
    taken_over = False

    async def lose_the_lease_midway(key: str, source: Path, content_type: str) -> None:
        nonlocal taken_over
        await real_upload(key, source, content_type)
        if not taken_over:
            taken_over = True
            await expire_lease(session, queued.id)
            assert await claim("new") is not None

    monkeypatch.setattr(storage, "upload_media", lose_the_lease_midway)

    assert await worker.run_one(processor.process, "old") is True

    assert not any(key.endswith("master.m3u8") for key in _media_keys())
    job = await load_job(session, queued.id)
    assert (job.status, job.locked_by, job.attempts) == (JobStatus.running, "new", 2)
    assert (await load_video(session, queued.video_id)).status is VideoStatus.processing


async def test_a_missing_upload_is_a_readable_failure(session: AsyncSession) -> None:
    queued = await enqueue(session, max_attempts=1)

    await worker.run_one(processor.process, "w1")

    video = await load_video(session, queued.video_id)
    assert video.failure_reason == "The uploaded file is missing"


async def test_scratch_is_empty_after_a_job(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    clip = make_clip(tmp_path / "clip.mp4")
    await _enqueue_file(session, clip.read_bytes())

    await worker.run_one(processor.process, "w1")

    assert _scratch_dirs(tmp_path) == []


def test_clear_scratch_only_removes_job_directories(tmp_path: Path) -> None:
    leftover = tmp_path / f"{processor.SCRATCH_PREFIX}abc"
    leftover.mkdir()
    (leftover / "source").write_text("x")
    other = tmp_path / "unrelated"
    other.mkdir()

    processor.clear_scratch()

    assert not leftover.exists()
    assert other.exists()
