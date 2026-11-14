#!/usr/bin/env bash
# Tests the path a clean machine takes: install.sh runs as root in a bare Ubuntu container with no
# Docker or curl, so it has to install them. Containers it starts run on the host's Docker daemon.
# Removes everything it creates. Usage: scripts/test-clean-install.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

if [ -n "$(docker ps -aq --filter label=com.docker.compose.project=youtube-clone)" ] \
    || [ -n "$(docker volume ls -q --filter name=youtube-clone_)" ]; then
    printf 'FAIL  remove the existing stack first: docker compose down -v\n' >&2
    exit 1
fi

tar --exclude=.git --exclude=.env --exclude=.env.dev --exclude='demo-credentials*.txt' --exclude=.venv --exclude=__pycache__ --exclude='*.egg-info' \
    --exclude=.pytest_cache --exclude=.ruff_cache --exclude=node_modules --exclude=dist -cf - . \
    | docker run --rm -i --network host -v /var/run/docker.sock:/var/run/docker.sock \
        -e HTTP_PORT=18081 ubuntu:24.04 bash -c '
    set -euo pipefail
    mkdir /repo && cd /repo && tar -xf -
    if command -v docker >/dev/null || command -v curl >/dev/null; then
        echo "FAIL  the image is not clean" >&2
        exit 1
    fi
    trap "docker compose down -v --remove-orphans >/dev/null 2>&1 || true" EXIT
    ./install.sh
    [ "$(stat -c %a .env)" = 600 ] || { echo "FAIL  .env is not mode 600" >&2; exit 1; }
    # Before smoke: its last check uses up the login rate limit (D58).
    scripts/test-demo-data.sh http://127.0.0.1:18081 demo-credentials.txt
    scripts/smoke.sh http://127.0.0.1:18081
'
printf 'clean install test passed\n'
