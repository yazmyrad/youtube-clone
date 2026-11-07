#!/usr/bin/env bash
# One-command deploy for a clean Ubuntu machine. Safe to run again: data and secrets are kept.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ $# -eq 0 ] || die "unknown argument: $1 (usage: ./install.sh)"

SUDO=()
if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null || die "run as root, or install sudo"
    SUDO=(sudo)
fi

apt_get() {
    # A fresh VM often has unattended-upgrades holding the apt lock, so wait for it.
    "${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive \
        apt-get -o DPkg::Lock::Timeout=300 "$@"
}

install_docker() {
    [ -r /etc/os-release ] || die "cannot detect the OS; install Docker manually"
    # shellcheck disable=SC1091
    . /etc/os-release
    [ "${ID:-}" = ubuntu ] || die "automatic Docker install supports Ubuntu only; found ${ID:-unknown}"

    log "Installing Docker from Docker's apt repository"
    apt_get update -qq
    apt_get install -y -qq ca-certificates curl
    "${SUDO[@]}" install -m 0755 -d /etc/apt/keyrings
    "${SUDO[@]}" curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    "${SUDO[@]}" chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
        | "${SUDO[@]}" tee /etc/apt/sources.list.d/docker.list >/dev/null
    apt_get update -qq
    apt_get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
        "${SUDO[@]}" systemctl enable --now docker
    fi
}

if ! command -v docker >/dev/null; then
    install_docker
elif ! docker compose version >/dev/null 2>&1; then
    # Installing docker-ce here could replace a Docker setup the machine already relies on.
    die "Docker is installed without the Compose plugin; install it and run this again"
fi

if ! command -v curl >/dev/null; then
    apt_get update -qq
    apt_get install -y -qq curl
fi

# Don't assume the current user is in the docker group; a clean machine has nobody in it.
DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
    DOCKER=("${SUDO[@]}" docker)
    "${DOCKER[@]}" info >/dev/null 2>&1 || die "cannot reach the Docker daemon"
fi

random_hex() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

case "${HTTP_PORT:-80}" in
    *[!0-9]*) die "HTTP_PORT must be a number" ;;
esac

if [ ! -f .env ]; then
    log "Generating secrets in .env"
    (
        umask 077
        cat > .env <<EOF
HTTP_PORT=${HTTP_PORT:-80}
POSTGRES_USER=app
POSTGRES_DB=app
POSTGRES_PASSWORD=$(random_hex)
EOF
    )
else
    log "Keeping existing .env"
fi
chmod 600 .env

# Compose prefers a shell variable over .env, so make .env the single source of the port.
port="$(sed -n 's/^HTTP_PORT=//p' .env)"
export HTTP_PORT="$port"

log "Building and starting services (the first run takes a few minutes)"
"${DOCKER[@]}" compose up -d --build --wait --wait-timeout 300 \
    || { "${DOCKER[@]}" compose ps -a; "${DOCKER[@]}" compose logs --tail=30; die "services did not become healthy"; }

curl -fsS --max-time 10 "http://127.0.0.1:${port}/api/health" >/dev/null \
    || die "services started, but /api/health failed through nginx"

host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
url="http://${host_ip:-localhost}"
[ "$port" = 80 ] || url="${url}:${port}"

log "Ready"
printf '    Site:     %s/\n    API docs: %s/docs\n' "$url" "$url"
