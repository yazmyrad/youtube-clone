#!/usr/bin/env bash
# Checks the running stack from the outside, through nginx.
# Usage: scripts/smoke.sh [base_url]
set -uo pipefail

base="${1:-http://127.0.0.1}"
failures=0

pass() { printf 'ok    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

expect() { # description, expected status, path
    local got
    got="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 --path-as-is "$base$3")"
    if [ "$got" = "$2" ]; then
        pass "$1"
    else
        fail "$1: expected $2, got $got"
    fi
}

expect "health check passes through nginx" 200 /api/health
expect "Swagger UI is served"              200 /docs
expect "OpenAPI schema is served"          200 /openapi.json
expect "site root is served"               200 /
expect "unknown API route is 404"          404 /api/does-not-exist

# The API's /internal/ routes must have no public route. The placeholder page answers any other
# path, so the proof is getting that page rather than checking the status alone.
marker='<title>YouTube clone</title>'
if body="$(curl -fsS --max-time 10 --path-as-is "$base/internal/playback-auth")" \
    && printf '%s' "$body" | grep -qF "$marker"; then
    pass "/internal/ does not reach the API"
else
    fail "/internal/ did not return the site page"
fi

if headers="$(curl -fsSI --max-time 10 "$base/")"; then
    server="$(printf '%s' "$headers" | grep -i '^server:' || true)"
    if printf '%s' "$server" | grep -qE '[0-9]+\.[0-9]+'; then
        fail "nginx version is exposed: $server"
    else
        pass "nginx version is hidden"
    fi
else
    fail "could not read response headers"
fi

[ "$failures" -eq 0 ] || { printf '%d check(s) failed\n' "$failures"; exit 1; }
printf 'all checks passed\n'
