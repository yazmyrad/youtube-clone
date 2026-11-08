#!/usr/bin/env bash
# Checks MinIO buckets and permissions on a running stack: the scoped app user is limited to
# objects, and anonymous access is GetObject on media/hls/ and media/thumbs/ only.
# Usage: scripts/test-storage.sh [compose command...]   (default: docker compose)
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

[ $# -gt 0 ] || set -- docker compose

# storage-init's container has the app credentials and the storage network; root is unused.
"$@" run --rm --no-deps -T --entrypoint sh storage-init /init/checks.sh
