#!/usr/bin/env bash
# Checks the running stack from the outside, through nginx, including playback protection
# (D40-D45) on real transcoded videos. Removes what it creates. Needs only bash, curl and Docker.
# Usage: scripts/smoke.sh [base_url] [compose command...]
set -uo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

base="${1:-http://127.0.0.1}"
[ $# -eq 0 ] || shift
[ $# -gt 0 ] || set -- docker compose
compose=("$@")

failures=0
work="$(mktemp -d)"
name="smoke$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
video_ids=()

# shellcheck disable=SC2016 # expanded inside the containers
cleanup() {
    rm -rf "$work"
    for id in "${video_ids[@]:-}"; do
        [ -n "$id" ] || continue
        "${compose[@]}" run --rm --no-deps -T --entrypoint sh storage-init -c '
            export MC_HOST_app="http://$MINIO_APP_ACCESS_KEY:$MINIO_APP_SECRET_KEY@minio:9000"
            mc rm -q --recursive --force "app/media/hls/$0/" >/dev/null 2>&1
            mc rm -q "app/media/thumbs/$0.jpg" >/dev/null 2>&1
            mc rm -q "app/uploads/raw/$0/source" >/dev/null 2>&1
            true' "$id" 2>/dev/null
    done
    "${compose[@]}" exec -T postgres sh -c \
        'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DELETE FROM videos WHERE owner_id IN (SELECT id FROM users WHERE username = '"'"'$0'"'"'); DELETE FROM users WHERE username = '"'"'$0'"'"'"' \
        "$name" >/dev/null 2>&1
}
trap cleanup EXIT

pass() { printf 'ok    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
die() { printf 'FAIL  %s\n' "$1"; exit 1; }

request() { # curl arguments; leaves the response in $work, prints the status
    curl -s -o "$work/body" -D "$work/headers" -w '%{http_code}' --max-time 20 --path-as-is "$@"
}

expect() { # description, expected status, path, extra curl arguments...
    local got
    got="$(request "${@:4}" "$base$3")"
    if [ "$got" = "$2" ]; then
        pass "$1"
    else
        fail "$1: expected $2, got $got"
    fi
}

is_object() { # Is the last response a playlist, a segment, a JPEG, or storage talking?
    local first
    first="$(head -c 1 "$work/body" | od -An -tx1 | tr -d ' \n')"
    [ "$first" = 47 ] || [ "$first" = ff ] && return 0
    head -c 7 "$work/body" | grep -qF '#EXTM3U' && return 0
    grep -aqE 'ListBucketResult|<Error>|AccessDenied' "$work/body"
}

no_object() { # description, path: whatever the status, no object or storage response comes back
    request "$base$2" >/dev/null
    if is_object; then
        fail "$1: returned an object"
    else
        pass "$1"
    fi
}

has_header() { grep -qiE "^$1" "$work/headers"; }
body_has() { grep -aqE "$1" "$work/body"; }

json() { # Python on the host isn't guaranteed; the API image always has it.
    "${compose[@]}" exec -T api python -c \
        'import json, sys; d = json.load(sys.stdin); print(eval(sys.argv[1]))' "$1"
}

sign() { # scope, video id, expiry: a valid signature, for what the API would never issue
    "${compose[@]}" exec -T api python -c \
        'import sys, uuid; from app.core.security import sign_media; print(sign_media(sys.argv[1], uuid.UUID(sys.argv[2]), int(sys.argv[3])))' \
        "$1" "$2" "$3"
}

# --- Routing ---------------------------------------------------------------

expect "health check passes through nginx" 200 /api/health
expect "Swagger UI is served"              200 /docs
expect "OpenAPI schema is served"          200 /openapi.json
expect "site root is served"               200 /
expect "unknown API route is 404"          404 /api/does-not-exist

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

# --- The site --------------------------------------------------------------

expect "a deep link is served by the SPA" 200 "/some/deep/link"
if body_has 'id="root"'; then pass "a deep link gets the SPA's page"; else fail "a deep link gets the SPA's page"; fi
expect "an API miss isn't answered by the SPA" 404 "/api/does-not-exist"
if body_has 'id="root"'; then fail "an API miss returned the SPA's page"; else pass "an API miss returned no page"; fi

expect "/redoc isn't answered by the SPA" 404 "/redoc"
expect "a path under /docs isn't answered by the SPA" 404 "/docs/x"

# The dev stack serves the site from Vite, which has no CSP and answers any path itself.
if [ -z "${SMOKE_DEV:-}" ]; then
    expect "D57 the SPA is served" 200 /
    if has_header "content-security-policy: default-src 'self'; script-src 'self';"; then
        pass "D57 the SPA serves a strict CSP"
    else
        fail "D57 the SPA serves a strict CSP"
    fi
    if has_header 'cache-control: no-cache'; then pass "index.html is revalidated"; else fail "index.html is revalidated"; fi
    if has_header 'x-content-type-options: nosniff'; then pass "index.html is nosniff"; else fail "index.html is nosniff"; fi
    # The page is only as good as the script it points at.
    script="$(grep -aoE '/assets/[^"]+\.js' "$work/body" | head -n 1)"
    if [ -n "$script" ]; then
        expect "the page's script is served" 200 "$script"
        if has_header 'content-type: (text|application)/javascript'; then pass "the script has a JavaScript type"; else fail "the script has a JavaScript type"; fi
        if has_header 'cache-control: public, max-age=31536000, immutable'; then pass "the script is cached for good"; else fail "the script is cached for good"; fi
    else
        fail "the page points at a built script"
    fi
    expect "the site icon is served" 200 "/favicon.svg"
    expect "/favicon.ico isn't answered by the SPA" 404 "/favicon.ico"
    expect "a missing asset is a real 404" 404 "/assets/does-not-exist.js"
    if body_has 'id="root"'; then fail "a missing asset returned the SPA's page"; else pass "a missing asset returned no page"; fi
fi

# --- Two real videos -------------------------------------------------------

register_body="{\"username\":\"$name\",\"email\":\"$name@example.com\",\"password\":\"correct horse battery\",\"display_name\":\"Smoke\"}"
login_body="{\"email\":\"$name@example.com\",\"password\":\"correct horse battery\"}"
curl -fsS --max-time 20 -o /dev/null -H 'Content-Type: application/json' -d "$register_body" \
    "$base/api/auth/register" || die "could not register a user"
curl -fsS --max-time 20 -o "$work/login" -H 'Content-Type: application/json' -d "$login_body" \
    "$base/api/auth/login" || die "could not log in"
access_token="$(json 'd["access_token"]' < "$work/login")"
auth=(-H "Authorization: Bearer $access_token")

# Through a file: written to a pipe, a container has no duration and the worker rejects it.
"${compose[@]}" exec -T worker sh -c '
    ffmpeg -nostdin -v error -y -f lavfi -i testsrc=duration=2:size=320x240:rate=10 \
        -c:v libx264 -preset ultrafast -pix_fmt yuv420p "/tmp/$0.mp4" \
        && cat "/tmp/$0.mp4"; status=$?; rm -f "/tmp/$0.mp4"; exit "$status"' "$name" \
    > "$work/clip.mp4" || die "could not generate a test clip"

upload_video() { # Sets video_id to a new private video whose file is uploaded and queued.
    local form=() line
    curl -fsS --max-time 20 "${auth[@]}" -H 'Content-Type: application/json' \
        -d '{"title":"Smoke check"}' "$base/api/videos" > "$work/created" \
        || die "could not create a video"
    video_id="$(json 'd["video"]["id"]' < "$work/created")"
    video_ids+=("$video_id")
    while IFS= read -r line; do
        form+=(--form-string "$line")
    done < <(json '"\n".join(f"{k}={v}" for k, v in d["upload"]["fields"].items())' < "$work/created")
    [ "$(request "${form[@]}" -F "file=@$work/clip.mp4" "$base/uploads/")" = 204 ] \
        || die "upload through nginx failed: $(cat "$work/body")"
    [ "$(request -X POST "${auth[@]}" "$base/api/videos/$video_id/upload/complete")" = 200 ] \
        || die "complete failed: $(cat "$work/body")"
}

wait_ready() { # video id; sets play_url once the video can be played
    local deadline=$((SECONDS + 180)) got
    while [ "$SECONDS" -lt "$deadline" ]; do
        got="$(request -X POST "${auth[@]}" "$base/api/videos/$1/playback")"
        if [ "$got" = 200 ]; then
            play_url="$(json 'd["url"]' < "$work/body")"
            return
        fi
        [ "$got" = 409 ] || die "/playback answered $got: $(cat "$work/body")"
        sleep 1
    done
    die "video $1 was not ready after 180 seconds"
}

upload_video; id_a="$video_id"
upload_video; id_b="$video_id"
wait_ready "$id_a"; url_a="$play_url"
wait_ready "$id_b"; url_b="$play_url"

# --- The main scenario (D02): like and comment on a video that plays ---------

json_type=(-H 'Content-Type: application/json')

expect "D02 the watch page is served" 200 "/watch?v=$id_a"
body_has 'id="root"' && pass "D02 the watch page is the SPA" || fail "D02 the watch page isn't the SPA"

expect "D02 like" 200 "/api/videos/$id_a/reaction" -X PUT "${auth[@]}" "${json_type[@]}" -d '{"reaction":"like"}'
expect "D02 comment" 201 "/api/videos/$id_a/comments" -X POST "${auth[@]}" "${json_type[@]}" -d '{"body":"Smoke comment"}'

expect "D02 the comment is listed" 200 "/api/videos/$id_a/comments" "${auth[@]}"
body_has 'Smoke comment' && pass "D02 the list has the comment" || fail "D02 the list lacks the comment"

expect "D02 details after like and comment" 200 "/api/videos/$id_a" "${auth[@]}"
counts="$(json '(d["likes_count"], d["comments_count"], d["my_reaction"])' < "$work/body")"
[ "$counts" = "(1, 1, 'like')" ] && pass "D02 the counters moved" || fail "D02 counters are $counts"

token="${url_a#/hls/}"; token="${token%%/*}"
exp="${token%%.*}"; sig="${token#*.}"
hls="/hls/$token/$id_a"

# --- D40: a valid token plays ----------------------------------------------

expect "D40 master playlist with a valid token" 200 "$hls/master.m3u8"
has_header 'content-type: application/vnd\.apple\.mpegurl' && pass "D40 master has its media type" \
    || fail "D40 master has the wrong media type"
body_has '^360p/index\.m3u8' && pass "D40 master uses relative paths" \
    || fail "D40 master doesn't list 360p/index.m3u8"
has_header 'x-amz-' && fail "D40 storage headers reach the client" \
    || pass "D40 storage headers are hidden"
has_header 'x-content-type-options: nosniff' && pass "D40 nosniff is set" || fail "D40 nosniff is missing"

expect "D40 media playlist with a valid token" 200 "$hls/360p/index.m3u8"
body_has '^seg_00000\.ts' && pass "D40 media playlist uses relative paths" \
    || fail "D40 media playlist doesn't list seg_00000.ts"

expect "D40 segment with a valid token" 200 "$hls/360p/seg_00000.ts"
has_header 'content-type: video/mp2t' && pass "D40 segment has its media type" \
    || fail "D40 segment has the wrong media type"
[ "$(head -c 1 "$work/body" | od -An -tx1 | tr -d ' \n')" = 47 ] && pass "D40 segment is MPEG-TS" \
    || fail "D40 segment isn't MPEG-TS"

expect "a query string is not passed on to storage" 200 "$hls/master.m3u8?acl"
body_has '^#EXTM3U' && pass "the query string got the playlist, not an S3 API" \
    || fail "a query string changed the response"

expect "POST with a valid token"   403 "$hls/master.m3u8" -X POST
expect "PUT with a valid token"    403 "$hls/master.m3u8" -X PUT --data-binary x
expect "DELETE with a valid token" 403 "$hls/master.m3u8" -X DELETE

expect "absent file with a valid token" 403 "$hls/720p/index.m3u8"
is_object && fail "absent file exposes storage's error" || pass "absent file shows no storage error"

# --- D41: forged, expired and missing tokens -------------------------------

case "$sig" in
    0*) forged_sig="1${sig#0}" ;;
    *) forged_sig="0${sig#?}" ;;
esac
past=$(( $(date +%s) - 60 ))
expired="$past.$(sign hls "$id_a" "$past")"

for file in master.m3u8 360p/index.m3u8 360p/seg_00000.ts; do
    expect "D41 forged signature: $file"     403 "/hls/$exp.$forged_sig/$id_a/$file"
    expect "D41 extended expiry: $file"      403 "/hls/$((exp + 600)).$sig/$id_a/$file"
    expect "D41 expired token: $file"        403 "/hls/$expired/$id_a/$file"
    expect "D41 missing token: $file"        403 "/hls/$id_a/$file"
    expect "D41 malformed token: $file"      403 "/hls/not-a-token/$id_a/$file"
done

# --- D42: a token opens only its own video ---------------------------------

expect "D42 video B plays with its own token" 200 "$url_b"
expect "D42 video A's token on B's playlist" 403 "/hls/$token/$id_b/master.m3u8"
expect "D42 video A's token on B's segment"  403 "/hls/$token/$id_b/360p/seg_00000.ts"

# --- D43: storage has no way in from outside -------------------------------

host="${base#*://}"; host="${host%%[:/]*}"
for port in 9000 9001; do
    if curl -s -o /dev/null -D "$work/headers" --connect-timeout 3 --max-time 5 \
        "http://$host:$port/minio/health/live" && has_header '(server: minio|x-amz-|x-minio-)'; then
        fail "D43 MinIO answers on port $port"
    else
        pass "D43 MinIO doesn't answer on port $port"
    fi
done
no_object "D43 bucket path, master"   "/media/hls/$id_a/master.m3u8"
no_object "D43 bucket path, segment"  "/media/hls/$id_a/360p/seg_00000.ts"
no_object "D43 bucket path, listing"  "/media/"
no_object "D43 MinIO's own API"       "/minio/health/live"
expect    "D43 object path without a token" 403 "/hls/$id_a/master.m3u8"

# --- D44: upload reads and the internal route ------------------------------

expect "D44 GET on the upload path"   403 "/uploads/"
expect "D44 GET on an uploaded key"   403 "/uploads/raw/$id_a/source"
expect "D44 /internal/ from outside"  404 "/internal/playback-auth"
expect "D44 /internal/ with a valid signature's headers" 404 "/internal/playback-auth" \
    -H "X-Media-Scope: hls" -H "X-Media-Id: $id_a" -H "X-Media-Exp: $exp" -H "X-Media-Sig: $sig"
expect "D44 /internal/ through /api/" 404 "/api/..%2finternal/playback-auth"
expect "D44 nginx's auth location"    404 "/_playback_auth"

# --- Thumbnails: same check, separate signing scope ------------------------

thumb_exp=$(( $(date +%s) + 3600 ))
thumb="$thumb_exp.$(sign thumb "$id_a" "$thumb_exp")"

expect "thumbnail with a valid token" 200 "/thumbs/$thumb/$id_a.jpg"
has_header 'content-type: image/jpeg' && pass "thumbnail has its media type" \
    || fail "thumbnail has the wrong media type"
[ "$(head -c 1 "$work/body" | od -An -tx1 | tr -d ' \n')" = ff ] && pass "thumbnail is a JPEG" \
    || fail "thumbnail isn't a JPEG"
expect "thumbnail with a forged signature"   403 "/thumbs/$thumb_exp.$forged_sig/$id_a.jpg"
expect "thumbnail with another video's token" 403 "/thumbs/$thumb/$id_b.jpg"
expect "thumbnail with an HLS token"         403 "/thumbs/$token/$id_a.jpg"
expect "HLS playlist with a thumbnail token" 403 "/hls/$thumb/$id_a/master.m3u8"
expect "thumbnail without a token"           403 "/thumbs/$id_a.jpg"
no_object "thumbnail by its bucket path"     "/media/thumbs/$id_a.jpg"
no_object "traversal out of /thumbs/"        "/thumbs/$thumb/../../media/thumbs/$id_a.jpg"

# --- D45: path traversal ---------------------------------------------------

traversals=(
    "$hls/../$id_b/master.m3u8"
    "$hls/%2e%2e/$id_b/master.m3u8"
    "$hls/..%2f$id_b/master.m3u8"
    "$hls/%2e%2e%2f$id_b/master.m3u8"
    "$hls/%252e%252e/$id_b/master.m3u8"
    "$hls/..%252f$id_b/master.m3u8"
    "/hls/$token//$id_b/master.m3u8"
    "$hls/master.m3u8%00.ts"
    "$hls/master.m3u8%2500.ts"
    "$hls/..%5c$id_b%5cmaster.m3u8"
    "$hls/360p/../../../../uploads/raw/$id_a/source"
    "$hls/360p/%2e%2e/%2e%2e/%2e%2e/%2e%2e/uploads/raw/$id_a/source"
    "$hls/../../../media/hls/$id_a/master.m3u8"
    "$hls/../../../minio/health/live"
    "$hls/360p/"
    "$hls/"
    "$hls/source"
    "$hls/.minio.sys/config"
    "/hls/$token/../$token/../../media/hls/$id_a/master.m3u8"
)
for path in "${traversals[@]}"; do
    no_object "D45 ${path#"$hls"}" "$path"
done

[ "$failures" -eq 0 ] || { printf '%d check(s) failed\n' "$failures"; exit 1; }
printf 'all checks passed\n'
