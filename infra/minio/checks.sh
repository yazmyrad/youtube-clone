#!/bin/sh
# Storage permission checks, run inside the storage network by scripts/test-storage.sh.
# Uses only the scoped app user and anonymous requests, never the root account.
set -u

failures=0
pass() { printf 'ok    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
ok() { if "$@" >/dev/null 2>&1; then return 0; else return 1; fi; }

check() { # description, command...
    desc="$1"; shift
    if ok "$@"; then pass "$desc"; else fail "$desc"; fi
}
deny() { # description, command...
    desc="$1"; shift
    if ok "$@"; then fail "$desc"; else pass "$desc"; fi
}
anon() { # expected status, method, path
    got="$(curl -s -o /dev/null -w '%{http_code}' -X "$2" --path-as-is "http://minio:9000$3")"
    if [ "$got" = "$1" ]; then pass "anonymous $2 $3 is $1"; else fail "anonymous $2 $3: expected $1, got $got"; fi
}

export MC_HOST_app="http://${MINIO_APP_ACCESS_KEY}:${MINIO_APP_SECRET_KEY}@minio:9000"
id="check-$(date +%s)-$$"
cleanup() {
    mc rm -q "app/uploads/raw/$id/source" "app/media/hls/$id/master.m3u8" \
        "app/media/thumbs/$id.jpg" "app/media/other/$id" >/dev/null 2>&1 || true
}
trap cleanup EXIT

put() { printf 'x' | mc pipe -q "$1"; }

# The app user reads and writes objects in both buckets.
for key in "uploads/raw/$id/source" "media/hls/$id/master.m3u8" "media/thumbs/$id.jpg" "media/other/$id"; do
    check "app user can write $key" put "app/$key"
    check "app user can read $key" mc cat "app/$key"
done
check "app user can list uploads" mc ls "app/uploads/raw/$id/"
check "app user can delete objects" mc rm -q "app/media/other/$id"
put "app/media/other/$id" >/dev/null  # Restored for the anonymous check below.

# ...and nothing beyond objects.
deny "app user can't create buckets" mc mb "app/check-$id"
deny "app user can't change bucket policy" mc anonymous set public app/uploads
deny "app user can't use the admin API" mc admin user list app

# Anonymous: only GetObject under media/hls/ and media/thumbs/.
anon 200 GET "/media/hls/$id/master.m3u8"
anon 200 GET "/media/thumbs/$id.jpg"
anon 403 GET "/media/other/$id"
anon 403 GET "/media/"
anon 403 GET "/media/?list-type=2&prefix=hls/"
anon 403 GET "/uploads/raw/$id/source"
anon 403 GET "/uploads/"
anon 403 PUT "/media/hls/$id/evil.ts"
anon 403 DELETE "/media/hls/$id/master.m3u8"
anon 403 GET "/"

[ "$failures" -eq 0 ] || { printf '%d storage check(s) failed\n' "$failures"; exit 1; }
printf 'all storage checks passed\n'
