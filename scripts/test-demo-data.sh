#!/usr/bin/env bash
# Tests D01's demo data through nginx: the credentials file is private, every demo account can
# log in, and the worker makes every demo video ready and listed on the home feed.
# Usage: scripts/test-demo-data.sh <base url> <credentials file>
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

base="$1"
credentials="$2"
fail() { printf 'FAIL  %s\n' "$*" >&2; exit 1; }
pass() { printf 'ok    %s\n' "$*"; }

[ -f "$credentials" ] || fail "$credentials is missing"
mode="$(stat -c '%a' "$credentials" 2>/dev/null || stat -f '%Lp' "$credentials")"
[ "$mode" = 600 ] || fail "$credentials is mode $mode, not 600"
git check-ignore -q "$credentials" 2>/dev/null || [ ! -d .git ] || fail "$credentials is not git-ignored"
pass "the demo credentials file is private"

# Rows are: role, username, email, password. Passwords are URL-safe, so they need no JSON escaping.
accounts=0
while read -r role username email password; do
    [ "$role" = ROLE ] && continue
    for _ in 1 2; do
        status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H 'Content-Type: application/json' \
            -d "{\"email\":\"$email\",\"password\":\"$password\"}" "$base/api/auth/login")"
        # Rate limited (D58): do as a client should, and wait the minute it asks for.
        [ "$status" = 429 ] || break
        sleep 61
    done
    [ "$status" = 200 ] || fail "demo account $username ($role) can't log in: $status"
    accounts=$((accounts + 1))
done < "$credentials"
[ "$accounts" -ge 7 ] || fail "expected at least 7 demo accounts, found $accounts"
pass "all $accounts demo accounts can log in"

# One small clip at a time on one CPU: allow a few minutes on a slow VM.
expected=12
deadline=$((SECONDS + 600))
while :; do
    listed="$(curl -fsS --max-time 20 "$base/api/videos?limit=50" | grep -oE '"username":"(codebytes|terminal_tales|pixel_pipeline)"' | wc -l | tr -d ' ')"
    [ "$listed" -ge "$expected" ] && break
    [ "$SECONDS" -lt "$deadline" ] || fail "only $listed of $expected demo videos are on home after 10 minutes"
    sleep 5
done
pass "all $expected demo videos are processed and on the home feed"

[ "$(curl -fsS --max-time 20 "$base/api/search/videos?q=in%20100%20Seconds" | grep -o '"id"' | wc -l | tr -d ' ')" -ge 2 ] \
    || fail "search doesn't find the demo videos"
pass "search finds the demo videos"
