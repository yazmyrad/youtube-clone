#!/usr/bin/env bash
# Seeds demo data into the running stack and saves the demo passwords to a file only the
# current user can read. Safe to run again: existing demo data and that file are kept.
# The worker processes the demo videos afterwards, which takes a minute or two.
# Usage: scripts/seed.sh <credentials file> [compose command...]
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

[ $# -ge 1 ] || { echo "usage: $0 <credentials file> [compose command...]" >&2; exit 2; }
out="$1"
shift
[ $# -gt 0 ] || set -- docker compose

# Next to the target, so the final rename is atomic; mktemp creates it with mode 600.
tmp="$(mktemp "$out.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

# --build: the seed image isn't built by `compose up`, and must match the current code.
# Quiet progress: compose writes build output to stdout, which holds only the passwords.
"$@" --progress quiet run --rm -T --build seed > "$tmp" \
    || { echo "ERROR: seeding demo data failed" >&2; exit 1; }

pending() { # demo videos the worker hasn't finished
    # shellcheck disable=SC2016 # expanded inside the container
    "$@" exec -T postgres sh -c 'psql -qtA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
        SELECT count(*) FROM videos v JOIN users u ON u.id = v.owner_id
        WHERE u.email LIKE '"'"'%@demo.example.com'"'"' AND v.status IN ('"'"'uploading'"'"', '"'"'processing'"'"')"'
}

if [ -s "$tmp" ]; then
    chmod 600 "$tmp"
    mv "$tmp" "$out"
    echo "==> Demo accounts and passwords saved to $out (readable only by you)"
    # So the site is complete on the first visit, and a first upload isn't queued behind these.
    echo "==> Processing the demo videos (about two minutes)"
    deadline=$((SECONDS + 600))
    while left="$(pending "$@")" && [ "${left:-1}" != 0 ]; do
        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "WARNING: $left demo videos are still processing; they will appear when done" >&2
            break
        fi
        sleep 5
    done
elif [ -f "$out" ]; then
    echo "==> Demo data is already there; its accounts are in $out"
else
    echo "==> Demo data is already there; its passwords were shown when it was created"
fi
