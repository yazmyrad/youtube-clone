"""Seeds demo data: `python -m app.workers.seed`. Runs in the worker image, which has ffmpeg
for the title cards that stand in for videos `fetch_demo_media` couldn't download.

Prints the new accounts' credentials to stdout and nothing else, so the caller can save
them to a private file. Prints nothing when the demo data is already there.
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.services import seed
from app.services.media import render_title_card

logger = logging.getLogger(__name__)


def format_credentials(credentials: list[seed.Credential]) -> str:
    lines = [f"{'ROLE':<6}  {'USERNAME':<16}  {'EMAIL':<34}  PASSWORD"]
    lines += [f"{c.role:<6}  {c.username:<16}  {c.email:<34}  {c.password}" for c in credentials]
    return "\n".join(lines) + "\n"


async def main() -> int:
    settings = get_settings()
    try:
        with tempfile.TemporaryDirectory(dir=settings.worker_scratch_dir) as workdir:
            async with get_sessionmaker()() as session:
                credentials = await seed.seed(
                    session, render_title_card, Path(workdir), settings.demo_media_dir
                )
    except seed.PartiallySeeded as exc:
        logger.error("%s. Remove them, or start from an empty database.", exc)
        return 1
    finally:
        await get_engine().dispose()
    if credentials is None:
        logger.info("Demo data is already there; nothing to do")
        return 0
    sys.stdout.write(format_credentials(credentials))
    logger.info("Seeded %d accounts; the worker is processing the videos", len(credentials))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    sys.exit(asyncio.run(main()))
