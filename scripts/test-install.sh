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
[ ! -e demo-credentials.txt ] || fail "remove demo-credentials.txt first, so seeding is tested"
if ./install.sh --no-such-flag >/dev/null 2>&1; then fail "install.sh accepted an unknown flag"; fi
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

# Before smoke: its last check uses up the login rate limit (D58).
scripts/test-demo-data.sh "http://127.0.0.1:${port}" demo-credentials.txt
scripts/smoke.sh "http://127.0.0.1:${port}" "${DOCKER[@]}" compose
scripts/test-storage.sh "${DOCKER[@]}" compose

secrets_before="$(sha256sum .env)"
demo_before="$(sha256sum demo-credentials.txt)"
marker="$(date +%s%N)"
psql "CREATE TABLE install_rerun_check (marker text); INSERT INTO install_rerun_check VALUES ('$marker');"
trap 'psql "DROP TABLE IF EXISTS install_rerun_check;" || true' EXIT

./install.sh

[ "$(sha256sum .env)" = "$secrets_before" ] || fail "install.sh changed .env on rerun"
[ "$(sha256sum demo-credentials.txt)" = "$demo_before" ] || fail "install.sh changed demo passwords on rerun"
[ "$(psql "SELECT count(*) FROM users WHERE email LIKE '%@demo.example.com';")" = 7 ] \
    || fail "install.sh seeded the demo accounts twice"
[ "$(psql 'SELECT marker FROM install_rerun_check;')" = "$marker" ] || fail "database data was lost on rerun"
printf 'ok    rerun kept secrets and data\n'

scripts/smoke.sh "http://127.0.0.1:${port}" "${DOCKER[@]}" compose
printf 'install test passed\n'
