# compose.yaml passes the same pinned image; the default keeps BuildKit from warning, and a
# test keeps the two equal.
ARG MINIO_IMAGE=pgsty/minio:RELEASE.2026-08-04T00-00-00Z@sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372
FROM ${MINIO_IMAGE}

COPY init.sh checks.sh app-policy.json media-anonymous.json /init/
