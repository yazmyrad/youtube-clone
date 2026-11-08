#!/bin/sh
# One-shot storage setup, run by the storage-init service. Safe to run again.
# The only place that uses the MinIO root credentials; the app gets a scoped user.
set -eu

: "${MINIO_ROOT_USER:?}" "${MINIO_ROOT_PASSWORD:?}" "${MINIO_APP_ACCESS_KEY:?}" "${MINIO_APP_SECRET_KEY:?}"

here="$(dirname "$0")"
# Root credentials go through the environment, never into a config file or the process list.
# `mc admin user add` takes the app secret as an argument; accepted, since this one-shot
# container runs nothing else and is reachable only on the internal storage network.
export MC_HOST_root="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000"

mc mb --ignore-existing root/uploads root/media

# nginx can't sign S3 requests, so it reads HLS and thumbnails anonymously over the internal
# storage network. Only GetObject under hls/ and thumbs/: no listing, nothing in uploads.
mc anonymous set-json "$here/media-anonymous.json" root/media
mc anonymous set none root/uploads

# `policy create` replaces an existing policy, so edits to the file apply on the next run.
mc admin policy create root app "$here/app-policy.json"
# `user add` on an existing user updates its secret, so a changed .env takes effect.
mc admin user add root "$MINIO_APP_ACCESS_KEY" "$MINIO_APP_SECRET_KEY"
mc admin policy attach root app --user "$MINIO_APP_ACCESS_KEY"

echo "storage ready: buckets uploads, media; app user $MINIO_APP_ACCESS_KEY"
