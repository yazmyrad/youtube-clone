#!/usr/bin/env bash
# Tests D01 and D03: install.sh brings up a healthy stack, and running it again keeps data and secrets.
# Needs a clean checkout with no existing stack, and leaves the stack running.
# Usage: HTTP_PORT=18080 scripts/test-install.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

fail() { printf 'FAIL  %s\n' "$*" >&2; exit 1; }

DOCKER=(docker)
docker info >/dev/null 2>&1 || DOCKER=(sudo docker)

[ ! -e .env ] || fail "remove .env first, so secret generation is tested"
[ -z "$("${DOCKER[@]}" volume ls -q --filter name=youtube-clone_)" ] \
    || fail "remove the existing stack first: docker compose down -v"

psql() {
    "${DOCKER[@]}" compose exec -T postgres \
        sh -c 'psql -v ON_ERROR_STOP=1 -qtA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' -- "$1"
}

./install.sh
port="$(sed -n 's/^HTTP_PORT=//p' .env)"

[ "$(stat -c '%a' .env)" = 600 ] || fail ".env is not mode 600"
git check-ignore -q .env || fail ".env is not git-ignored"
printf 'ok    .env is private and git-ignored\n'

published="$("${DOCKER[@]}" ps --filter label=com.docker.compose.project=youtube-clone \
    --format '{{.Label "com.docker.compose.service"}} {{.Ports}}' \
    | { grep -e '->' || true; } | cut -d' ' -f1 | sort -u)"
[ "$published" = nginx ] || fail "published services should be only nginx, got: '$published'"
printf 'ok    only nginx publishes a port\n'

scripts/smoke.sh "http://127.0.0.1:${port}"
scripts/test-storage.sh "${DOCKER[@]}" compose

secrets_before="$(sha256sum .env)"
marker="$(date +%s%N)"
psql "CREATE TABLE install_rerun_check (marker text); INSERT INTO install_rerun_check VALUES ('$marker');"
trap 'psql "DROP TABLE IF EXISTS install_rerun_check;" || true' EXIT

./install.sh

[ "$(sha256sum .env)" = "$secrets_before" ] || fail "install.sh changed .env on rerun"
[ "$(psql 'SELECT marker FROM install_rerun_check;')" = "$marker" ] || fail "database data was lost on rerun"
printf 'ok    rerun kept secrets and data\n'

scripts/smoke.sh "http://127.0.0.1:${port}"
printf 'install test passed\n'
