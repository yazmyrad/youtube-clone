"""Turns a claimed job into media files. Must be cancellable: a lost lease cancels it."""

from app.services.jobs import ClaimedJob, JobError, MediaResult


async def process(claim: ClaimedJob) -> MediaResult:
    raise JobError("Video processing isn't available yet")
