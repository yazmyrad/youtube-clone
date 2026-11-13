"""Cleanup. Each sweep is safe to repeat and to run from several workers.

A row and its objects can't change in one transaction, so objects go first: a failure
leaves the row in place and the next sweep finishes the work.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, exists, func, select, update

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import JobStatus, ProcessingJob, Video, VideoStatus, VideoView
from app.services import storage

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


async def delete_finished_raw_files() -> None:
    """The source is only needed until the video reaches a final state."""
    bucket = get_settings().uploads_bucket
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(Video.id, Video.raw_key)
                .where(
                    Video.raw_key.is_not(None),
                    Video.status.in_((VideoStatus.ready, VideoStatus.failed)),
                )
                .limit(BATCH_SIZE)
            )
        ).all()
        await session.rollback()  # No transaction stays open during the storage calls.
        for video_id, key in rows:
            try:
                await storage.delete_object(bucket, key)
            except Exception:
                logger.exception("Couldn't delete the raw file of video %s", video_id)
                continue
            await session.execute(
                update(Video)
                .where(Video.id == video_id, Video.raw_key == key)
                .values(raw_key=None)
                .execution_options(synchronize_session=False)
            )
            await session.commit()


async def retire_abandoned_uploads() -> None:
    """Soft-deletes them, which also makes `complete` refuse them from here on."""
    age = get_settings().abandoned_upload_age
    async with get_sessionmaker()() as session:
        await session.execute(
            update(Video)
            .where(
                Video.status == VideoStatus.uploading,
                Video.created_at < func.now() - age,
                Video.deleted_at.is_(None),
            )
            .values(deleted_at=func.now())
            .execution_options(synchronize_session=False)
        )
        await session.commit()


async def _delete_objects(video_id: uuid.UUID) -> None:
    settings = get_settings()
    await storage.delete_prefix(settings.media_bucket, f"{storage.hls_prefix(video_id)}/")
    await storage.delete_object(settings.media_bucket, storage.thumbnail_key(video_id))
    await storage.delete_object(settings.uploads_bucket, storage.raw_key(video_id))


async def purge_deleted_videos() -> None:
    """Removes objects, then the row, and child rows cascade.

    A video with an active job waits, so a running worker can't add objects after the purge.
    """
    active_job = exists().where(
        ProcessingJob.video_id == Video.id,
        ProcessingJob.status.in_((JobStatus.queued, JobStatus.running)),
    )
    async with get_sessionmaker()() as session:
        video_ids = (
            await session.scalars(
                select(Video.id)
                .where(Video.deleted_at.is_not(None), ~active_job)
                .order_by(Video.deleted_at)
                .limit(BATCH_SIZE)
            )
        ).all()
        await session.rollback()
        for video_id in video_ids:
            try:
                await _delete_objects(video_id)
            except Exception:
                logger.exception("Couldn't delete the objects of video %s", video_id)
                continue
            await session.execute(
                delete(Video)
                .where(Video.id == video_id, Video.deleted_at.is_not(None), ~active_job)
                .execution_options(synchronize_session=False)
            )
            await session.commit()


async def forget_old_views() -> None:
    """A view only needs remembering for the day it counted on (D52). Days are UTC, as in
    `views.record_view`."""
    today = datetime.now(UTC).date()
    async with get_sessionmaker()() as session:
        await session.execute(delete(VideoView).where(VideoView.day < today))
        await session.commit()


async def run_all() -> None:
    await delete_finished_raw_files()
    await retire_abandoned_uploads()
    await purge_deleted_videos()
    await forget_old_views()
