import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import JobStatus, ProcessingJob, Video, VideoStatus, VideoView
from app.services import storage
from app.workers import main as worker
from app.workers import sweeps
from tests.conftest import TEST_BUCKET, TEST_MEDIA_BUCKET
from tests.helpers import CreateUser
from tests.job_helpers import make_video

LONG_AGO = datetime.now(UTC) - timedelta(days=2)
READY = {
    "status": VideoStatus.ready,
    "hls_prefix": "hls/x",
    "thumbnail_key": "thumbs/x.jpg",
    "duration_seconds": 5,
    "published_at": LONG_AGO,
}


async def _new_video(session: AsyncSession, **fields: object) -> uuid.UUID:
    """The id alone: the rollbacks below expire the object, and async can't lazy-load it."""
    return (await make_video(session, **fields)).id


def _put(bucket: str, key: str) -> None:
    storage.get_client().put_object(Bucket=bucket, Key=key, Body=b"x")


def _keys(bucket: str) -> set[str]:
    listing = storage.get_client().list_objects_v2(Bucket=bucket)
    return {item["Key"] for item in listing.get("Contents", [])}


async def _exists(session: AsyncSession, video_id: uuid.UUID) -> bool:
    await session.rollback()
    return await session.scalar(select(Video.id).where(Video.id == video_id)) is not None


async def _raw_key(session: AsyncSession, video_id: uuid.UUID) -> str | None:
    await session.rollback()
    return await session.scalar(select(Video.raw_key).where(Video.id == video_id))


async def _deleted_at(session: AsyncSession, video_id: uuid.UUID) -> datetime | None:
    await session.rollback()
    return await session.scalar(select(Video.deleted_at).where(Video.id == video_id))


@pytest.mark.parametrize(
    ("fields", "removed"),
    [
        (READY, True),
        ({"status": VideoStatus.failed}, True),
        ({"status": VideoStatus.processing}, False),
        ({"status": VideoStatus.uploading}, False),
    ],
)
async def test_raw_files_go_only_in_a_final_state(
    session: AsyncSession, minio: str, fields: dict, removed: bool
) -> None:
    key = f"raw/{uuid.uuid4()}/source"
    _put(TEST_BUCKET, key)
    video = await _new_video(session, raw_key=key, **fields)

    await sweeps.delete_finished_raw_files()

    assert (key not in _keys(TEST_BUCKET)) is removed
    assert (await _raw_key(session, video) is None) is removed


async def test_a_storage_failure_keeps_the_key_for_the_next_sweep(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = await _new_video(session, raw_key="raw/a/source", status=VideoStatus.failed)

    async def broken(*_: object) -> None:
        raise ConnectionError("storage is away")

    monkeypatch.setattr(storage, "delete_object", broken)

    await sweeps.delete_finished_raw_files()

    assert await _raw_key(session, video) == "raw/a/source"


async def test_only_old_uploads_are_retired(session: AsyncSession) -> None:
    old = await _new_video(session, status=VideoStatus.uploading, created_at=LONG_AGO)
    fresh = await _new_video(session, status=VideoStatus.uploading)
    old_processing = await _new_video(session, status=VideoStatus.processing, created_at=LONG_AGO)

    await sweeps.retire_abandoned_uploads()

    assert await _deleted_at(session, old) is not None
    assert await _deleted_at(session, fresh) is None
    assert await _deleted_at(session, old_processing) is None


async def test_a_retired_upload_cannot_be_completed(
    api: httpx.AsyncClient, create_user: CreateUser, session: AsyncSession
) -> None:
    user = await create_user()
    created = await api.post("/api/videos", headers=user.headers, json={"title": "Clip"})
    video_id = created.json()["video"]["id"]
    await session.execute(update(Video).values(created_at=LONG_AGO))
    await session.commit()

    await sweeps.retire_abandoned_uploads()

    response = await api.post(f"/api/videos/{video_id}/upload/complete", headers=user.headers)
    assert response.status_code == 404


async def test_purge_removes_objects_then_the_row(session: AsyncSession, minio: str) -> None:
    gone = await _new_video(session, deleted_at=LONG_AGO)
    kept = await _new_video(session)
    for video_id in (gone, kept):
        _put(TEST_MEDIA_BUCKET, f"hls/{video_id}/master.m3u8")
        _put(TEST_MEDIA_BUCKET, f"hls/{video_id}/360p/seg_00000.ts")
        _put(TEST_MEDIA_BUCKET, f"thumbs/{video_id}.jpg")
        _put(TEST_BUCKET, f"raw/{video_id}/source")

    await sweeps.purge_deleted_videos()

    assert not await _exists(session, gone)
    assert await _exists(session, kept)
    media = _keys(TEST_MEDIA_BUCKET)
    assert not any(str(gone) in key for key in media)
    assert sum(str(kept) in key for key in media) == 3
    assert _keys(TEST_BUCKET) == {f"raw/{kept}/source"}


@pytest.mark.parametrize(
    ("job_status", "purged"),
    [
        (JobStatus.queued, False),
        (JobStatus.running, False),
        (JobStatus.done, True),
        (JobStatus.failed, True),
    ],
)
async def test_purge_waits_for_an_active_job(
    session: AsyncSession, minio: str, job_status: JobStatus, purged: bool
) -> None:
    video = await _new_video(session, deleted_at=LONG_AGO, status=VideoStatus.processing)
    session.add(ProcessingJob(video_id=video, status=job_status))
    await session.commit()

    await sweeps.purge_deleted_videos()

    assert (not await _exists(session, video)) is purged


async def test_purge_keeps_the_row_if_storage_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = await _new_video(session, deleted_at=LONG_AGO)

    async def broken(*_: object) -> None:
        raise ConnectionError("storage is away")

    monkeypatch.setattr(storage, "delete_prefix", broken)

    await sweeps.purge_deleted_videos()

    assert await _exists(session, video)


async def test_the_sweep_loop_outlives_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWEEP_INTERVAL", "PT0.01S")
    get_settings.cache_clear()
    second_call = asyncio.Event()
    calls = 0

    async def broken() -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            second_call.set()
        raise ConnectionError("database is away")

    monkeypatch.setattr(sweeps, "run_all", broken)
    loop = asyncio.ensure_future(worker.sweep_forever())
    await asyncio.wait_for(second_call.wait(), timeout=5)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop


async def test_forgets_views_from_before_today(session: AsyncSession) -> None:
    video_id = await _new_video(session)
    today = datetime.now(UTC).date()
    for day in (today - timedelta(days=2), today - timedelta(days=1), today):
        session.add(VideoView(video_id=video_id, viewer_key=b"k", day=day))
    await session.commit()

    await sweeps.forget_old_views()

    days = list(await session.scalars(select(VideoView.day)))
    assert days == [today]
