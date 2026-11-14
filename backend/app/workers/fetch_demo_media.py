"""Downloads the demo videos: `python -m app.workers.fetch_demo_media`.

Runs in its own container, the only backend one with internet access, before the seed. It
needs nothing else: no database, no storage. Each file is checked against the SHA-256 in the
seed's catalog and kept only if it matches; one already there and intact isn't fetched
again. A video that can't be had is left out, and the seed gives it a title card, so this
always exits 0 unless the directory itself is unusable.
"""

import hashlib
import logging
import os
import sys
import urllib.request
from pathlib import Path

from app.services.seed import CHANNELS, DemoSource, sha256_of

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path("/var/lib/demo-media")
# The largest demo file is about 17 MB; this only stops a runaway download.
MAX_BYTES = 64 * 1024 * 1024
TIMEOUT_SECONDS = 60
# A plain name: nothing about who runs this goes to the video hosts.
USER_AGENT = "youtube-clone-demo-fetch/1.0"


def sources() -> list[DemoSource]:
    return [
        video.source for channel in CHANNELS for video in channel.videos if video.source is not None
    ]


def fetch(source: DemoSource, directory: Path) -> bool:
    """Makes sure `directory` holds the verified file. Returns whether it does."""
    target = directory / source.file
    if target.is_file() and sha256_of(target) == source.sha256:
        return True
    partial = directory / f".{source.file}.part"
    digest = hashlib.sha256()
    size = 0
    if not source.url.startswith("https://"):
        logger.warning("%s: not an https URL; a title card will stand in", source.file)
        return False
    request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - https only, checked above
    try:
        with (
            urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response,  # noqa: S310
            partial.open("wb") as out,
        ):
            while chunk := response.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(f"larger than {MAX_BYTES} bytes")
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != source.sha256:
            raise ValueError("checksum mismatch")
    except (OSError, ValueError) as exc:
        partial.unlink(missing_ok=True)
        logger.warning("%s: not downloaded (%s); a title card will stand in", source.file, exc)
        return False
    os.replace(partial, target)
    logger.info("%s: downloaded, %d KB", source.file, size // 1024)
    return True


def main() -> int:
    directory = Path(os.environ.get("DEMO_MEDIA_DIR", DEFAULT_DIR))
    if not directory.is_dir():
        logger.error("%s is not a directory", directory)
        return 1
    wanted = sources()
    ready = sum(fetch(source, directory) for source in wanted)
    logger.info("Demo videos ready: %d of %d", ready, len(wanted))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    sys.exit(main())
