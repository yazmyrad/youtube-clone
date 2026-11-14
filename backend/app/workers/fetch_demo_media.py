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
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from app.services.seed import CHANNELS, DemoSource, sha256_of

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path("/var/lib/demo-media")
# The largest demo file is about 17 MB; this only stops a runaway download.
MAX_BYTES = 64 * 1024 * 1024
TIMEOUT_SECONDS = 60
# Wikimedia asks automated clients for a descriptive name and a way to reach whoever runs
# them (https://w.wiki/4wJS). Nothing about the operator is sent unless they set
# DEMO_FETCH_CONTACT (a URL or an email address) themselves.
USER_AGENT = "YouTubeCloneDemoFetch/1.0 (self-hosted demo data{contact}) Python-urllib"
# Busy hosts answer 429 or 503: wait as they ask, a few times, then give up on that file.
ATTEMPTS = 4
RETRY_STATUSES = {429, 503}
MAX_WAIT_SECONDS = 30.0
# A pause between requests to the same host, as rate-limited hosts expect.
PACE_SECONDS = 1.0


def user_agent() -> str:
    contact = os.environ.get("DEMO_FETCH_CONTACT", "").strip()
    return USER_AGENT.format(contact=f"; {contact}" if contact else "")


def retry_after(error: urllib.error.HTTPError, attempt: int) -> float:
    """The host's Retry-After in seconds if it gives one, else doubling from two seconds."""
    header = error.headers.get("Retry-After") if error.headers else None
    if header and header.strip().isdigit():
        return min(float(header.strip()), MAX_WAIT_SECONDS)
    return min(2.0 * 2**attempt, MAX_WAIT_SECONDS)


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
    request = urllib.request.Request(source.url, headers={"User-Agent": user_agent()})  # noqa: S310 - https only, checked above
    try:
        for attempt in range(ATTEMPTS):
            try:
                with (
                    urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response,  # noqa: S310
                    partial.open("wb") as out,
                ):
                    digest, size = hashlib.sha256(), 0
                    while chunk := response.read(1 << 20):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError(f"larger than {MAX_BYTES} bytes")
                        digest.update(chunk)
                        out.write(chunk)
                break
            except urllib.error.HTTPError as error:
                error.close()  # Its body is an open response.
                if error.code not in RETRY_STATUSES or attempt == ATTEMPTS - 1:
                    raise
                wait = retry_after(error, attempt)
                logger.info(
                    "%s: the host is busy (%s); trying again in %.0fs",
                    source.file,
                    error.code,
                    wait,
                )
                time.sleep(wait)
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
    ready = 0
    last_host = None
    for source in wanted:
        host = urlsplit(source.url).hostname
        already = (directory / source.file).is_file()
        if host == last_host and not already:
            time.sleep(PACE_SECONDS)
        ready += fetch(source, directory)
        last_host = host
    logger.info("Demo videos ready: %d of %d", ready, len(wanted))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    sys.exit(main())
