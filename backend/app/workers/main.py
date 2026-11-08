"""The worker process: claims jobs one at a time and runs them under a renewed lease."""

import asyncio
import contextlib
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.services import jobs
from app.services.jobs import ClaimedJob, MediaResult
from app.workers.processor import process as default_process

logger = logging.getLogger(__name__)

Processor = Callable[[ClaimedJob], Awaitable[MediaResult]]


async def _renew_until_lost(claim: ClaimedJob) -> None:
    """Returns only when the lease is lost. A failed renewal is retried: if the database
    stays away the lease expires, and the fence stops this worker's late writes."""
    interval = get_settings().job_heartbeat_interval.total_seconds()
    while True:
        await asyncio.sleep(interval)
        try:
            async with get_sessionmaker()() as session:
                if not await jobs.heartbeat(session, claim):
                    return
        except Exception:
            logger.exception("Couldn't renew the lease on job %s", claim.id)


async def run_one(process: Processor, worker_id: str) -> bool:
    """Runs one job if any is available. No transaction stays open during the work."""
    async with get_sessionmaker()() as session:
        claim = await jobs.claim_next(session, worker_id)
    if claim is None:
        return False

    logger.info("Job %s: attempt %s on video %s", claim.id, claim.attempt, claim.video_id)
    work = asyncio.ensure_future(process(claim))
    lease = asyncio.ensure_future(_renew_until_lost(claim))
    try:
        await asyncio.wait({work, lease}, return_when=asyncio.FIRST_COMPLETED)
        lost = not work.done()
    finally:
        # Also runs on shutdown, when this task is cancelled. The lease then expires
        # and the job is picked up again.
        work.cancel()
        lease.cancel()
        await asyncio.gather(work, lease, return_exceptions=True)

    if lost:
        logger.warning("Job %s: lease lost, abandoning attempt %s", claim.id, claim.attempt)
        return True

    # Nothing outside cancelled it, so a stray cancellation inside the work is just a failure.
    error = RuntimeError("The work was cancelled") if work.cancelled() else work.exception()
    async with get_sessionmaker()() as session:
        if error is None:
            recorded = await jobs.complete(session, claim, work.result())
        else:
            logger.error("Job %s: attempt %s failed: %r", claim.id, claim.attempt, error)
            recorded = await jobs.fail(session, claim, error)
    if not recorded:
        logger.warning("Job %s: lease lost before attempt %s finished", claim.id, claim.attempt)
    return True


async def run_forever(process: Processor, worker_id: str) -> None:
    """Works until cancelled, and outlives database outages."""
    poll_interval = get_settings().job_poll_interval.total_seconds()
    while True:
        try:
            worked = await run_one(process, worker_id)
        except Exception:
            logger.exception("Worker loop error")
            worked = False
        if not worked:
            await asyncio.sleep(poll_interval)


async def _main() -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    task = asyncio.ensure_future(run_forever(default_process, worker_id))
    loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop_signal, task.cancel)
    logger.info("Worker %s started", worker_id)
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await get_engine().dispose()
    logger.info("Worker %s stopped", worker_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_main())
