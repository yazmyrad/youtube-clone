#!/usr/bin/env bash
# Checks the upload path through nginx on a running stack: form POST, complete, and that
# nothing else gets through /uploads/. LARGE=1 also sends a 2 GB file and one just over it.
# Removes what it creates. Usage: scripts/test-upload.sh [compose command...]
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

[ $# -gt 0 ] || set -- docker compose
compose=("$@")

base="http://$("${compose[@]}" port nginx 8080)"
work="$(mktemp -d)"
name="uploadcheck$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
video_ids=()
failures=0

# shellcheck disable=SC2016 # expanded inside the containers
cleanup() {
    rm -rf "$work"
    for id in "${video_ids[@]:-}"; do
        [ -n "$id" ] || continue
        "${compose[@]}" run --rm --no-deps -T --entrypoint sh storage-init -c \
            'MC_HOST_app="http://$MINIO_APP_ACCESS_KEY:$MINIO_APP_SECRET_KEY@minio:9000" mc rm -q "app/uploads/raw/$0/source" >/dev/null 2>&1 || true' "$id" 2>/dev/null
    done
    "${compose[@]}" exec -T postgres sh -c \
        'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DELETE FROM videos WHERE owner_id IN (SELECT id FROM users WHERE username = '"'"'$0'"'"'); DELETE FROM users WHERE username = '"'"'$0'"'"'"' \
        "$name" >/dev/null
}
trap cleanup EXIT

expect() { # expect <description> <wanted status> <actual status>
    if [ "$2" = "$3" ]; then
        echo "ok    $1 ($3)"
    else
        echo "FAIL  $1: wanted $2, got $3" >&2
        failures=$((failures + 1))
    fi
}

json() { python3 -c "import json, sys; d = json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }

status() { curl -s -o "$work/body" -w '%{http_code}' "$@"; }

register_body="{\"username\":\"$name\",\"email\":\"$name@example.com\",\"password\":\"correct horse battery\",\"display_name\":\"Check\"}"
login_body="{\"email\":\"$name@example.com\",\"password\":\"correct horse battery\"}"
curl -fsS -o /dev/null -H 'Content-Type: application/json' -d "$register_body" "$base/api/auth/register"
token="$(curl -fsS -H 'Content-Type: application/json' -d "$login_body" "$base/api/auth/login" | json 'd["access_token"]')"
auth=(-H "Authorization: Bearer $token")

new_video() { # Sets video_id, and form to the curl arguments for the upload form.
    curl -fsS "${auth[@]}" -H 'Content-Type: application/json' -d '{"title":"Upload check"}' \
        "$base/api/videos" > "$work/created"
    video_id="$(json 'd["video"]["id"]' < "$work/created")"
    video_ids+=("$video_id")
    form=()
    while IFS= read -r line; do
        form+=(--form-string "$line")
    done < <(json '"\n".join(f"{k}={v}" for k, v in d["upload"]["fields"].items())' < "$work/created")
}

complete() { status -X POST "${auth[@]}" "$base/api/videos/$video_id/upload/complete"; }

new_video
expect "complete before the upload" 409 "$(complete)"

printf 'video bytes' > "$work/small"
expect "form POST through nginx" 204 "$(status "${form[@]}" -F "file=@$work/small" "$base/uploads/")"
expect "complete after the upload" 200 "$(complete)"
expect "complete again" 200 "$(complete)"

expect "GET on the upload path" 403 "$(status "$base/uploads/")"
expect "GET on an object" 403 "$(status "$base/uploads/raw/$video_id/source")"
expect "PUT on an object" 403 "$(status -X PUT --data-binary x "$base/uploads/raw/$video_id/source")"
expect "PUT on the upload path" 403 "$(status -X PUT --data-binary x "$base/uploads/")"
expect "DELETE on the upload path" 403 "$(status -X DELETE "$base/uploads/")"
expect "POST with a query string" 400 "$(status -X POST "$base/uploads/?delete")"

truncate -s 3G "$work/too-big"
expect "body over the nginx limit" 413 "$(status "${form[@]}" -F "file=@$work/too-big" "$base/uploads/")"
rm -f "$work/too-big"

if [ -n "${LARGE:-}" ]; then
    new_video
    truncate -s 2G "$work/limit"
    expect "2 GB file, exactly the limit" 204 "$(status "${form[@]}" -F "file=@$work/limit" "$base/uploads/")"
    rm -f "$work/limit"
    expect "complete the 2 GB file" 200 "$(complete)"

    new_video
    truncate -s 2147483649 "$work/over"
    expect "one byte over 2 GB" 400 "$(status "${form[@]}" -F "file=@$work/over" "$base/uploads/")"
    grep -q EntityTooLarge "$work/body" || { echo "FAIL  no EntityTooLarge in the answer" >&2; failures=$((failures + 1)); }
    rm -f "$work/over"
    expect "complete after the refused upload" 409 "$(complete)"
fi

[ "$failures" -eq 0 ] || { echo "$failures check(s) failed" >&2; exit 1; }
echo "upload path: all checks passed"
