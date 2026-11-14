#!/usr/bin/env bash
# One-command deploy for a clean Ubuntu machine. Safe to run again: data and secrets are kept.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage="usage: ./install.sh [--no-seed] [--domain example.com | --no-domain]"
SEED=1
DOMAIN_ARG=""
NO_DOMAIN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --no-seed) SEED=0 ;;
        --domain)
            [ $# -ge 2 ] || die "--domain needs a name ($usage)"
            DOMAIN_ARG="$2"
            shift
            ;;
        --domain=*) DOMAIN_ARG="${1#--domain=}" ;;
        --no-domain) NO_DOMAIN=1 ;;
        -h | --help) echo "$usage"; exit 0 ;;
        *) die "unknown argument: $1 ($usage)" ;;
    esac
    shift
done
[ -z "$DOMAIN_ARG" ] || [ "$NO_DOMAIN" = 0 ] || die "--domain and --no-domain together ($usage)"
if [ -n "$DOMAIN_ARG" ]; then
    # A host name with a dot, as certificates need (or localhost, for testing): no scheme,
    # port, path or IP address. Lowercase, as browsers send it.
    DOMAIN_ARG="$(printf '%s' "$DOMAIN_ARG" | tr '[:upper:]' '[:lower:]')"
    label='[a-z0-9]([a-z0-9-]*[a-z0-9])?'
    { [ "$DOMAIN_ARG" = localhost ] || {
        [ "${#DOMAIN_ARG}" -le 253 ] \
            && printf '%s' "$DOMAIN_ARG" | grep -qE "^$label(\.$label)+\$" \
            && ! printf '%s' "$DOMAIN_ARG" | grep -qE '^[0-9.]+$'
    }; } || die "--domain takes a domain name such as videos.example.com, not an IP address, URL or path"
fi

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

# Secrets added by later versions are appended, so an upgrade keeps the existing ones.
# Each purpose gets its own random secret.
add_secret() {
    grep -q "^$1=" .env || { echo "$1=$(random_hex)" >> .env; log "Added $1 to .env"; }
}
add_secret JWT_SECRET
add_secret PLAYBACK_SECRET
add_secret MINIO_ROOT_PASSWORD
add_secret MINIO_APP_SECRET_KEY
# Fixed names, not secrets; set the same way so an older .env gains them.
grep -q '^MINIO_ROOT_USER=' .env || echo "MINIO_ROOT_USER=minio-root" >> .env
grep -q '^MINIO_APP_ACCESS_KEY=' .env || echo "MINIO_APP_ACCESS_KEY=app" >> .env

# `--domain`: HTTPS through Caddy (compose.domain.yaml). Recorded in .env, so a plain rerun
# and every `docker compose` command keep it; remove these lines from .env to go back.
if [ -n "$DOMAIN_ARG" ] || [ "$NO_DOMAIN" = 1 ]; then
    sed -i '/^DOMAIN=/d; /^COMPOSE_FILE=/d' .env
fi
if [ -n "$DOMAIN_ARG" ]; then
    printf 'DOMAIN=%s\nCOMPOSE_FILE=compose.yaml:compose.domain.yaml\n' "$DOMAIN_ARG" >> .env
    log "HTTPS for $DOMAIN_ARG: it must point at this machine, with ports 80, 443 and 443/udp open"
elif [ "$NO_DOMAIN" = 1 ]; then
    log "Back to plain HTTP on port ${HTTP_PORT:-80}"
fi
domain="$(sed -n 's/^DOMAIN=//p' .env)"
compose_file="$(sed -n 's/^COMPOSE_FILE=//p' .env)"
[ -z "$domain" ] || [ -n "$compose_file" ] \
    || die ".env has DOMAIN but no COMPOSE_FILE; rerun with --domain $domain or --no-domain"
# Compose prefers the shell's variables over .env: make .env the only source of these.
if [ -n "$domain" ]; then
    export DOMAIN="$domain" COMPOSE_FILE="$compose_file"
else
    unset DOMAIN COMPOSE_FILE
fi

# Compose prefers a shell variable over .env, so make .env the single source of the port.
port="$(sed -n 's/^HTTP_PORT=//p' .env)"
export HTTP_PORT="$port"

log "Building and starting services (the first run takes a few minutes)"
# --remove-orphans: after --no-domain, Caddy would otherwise keep ports 80 and 443.
"${DOCKER[@]}" compose up -d --build --remove-orphans --wait --wait-timeout 300 \
    || { "${DOCKER[@]}" compose ps -a; "${DOCKER[@]}" compose logs --tail=30; die "services did not become healthy"; }

if [ -z "$domain" ]; then
    curl -fsS --max-time 10 "http://127.0.0.1:${port}/api/health" >/dev/null \
        || die "services started, but /api/health failed through nginx"
else
    # nginx publishes no port here; check it from Caddy's side, then HTTPS itself.
    "${DOCKER[@]}" compose exec -T caddy wget -q -O /dev/null http://nginx:8080/api/health \
        || die "services started, but /api/health failed through nginx"
    # The first certificate can take a minute; Caddy keeps trying, so this only warns.
    # `localhost` (for testing) gets Caddy's own CA, which nothing trusts: check it served TLS.
    trust=()
    [ "$domain" != localhost ] || trust=(--insecure)
    ok=""
    for _ in $(seq 1 30); do
        if curl -fsS --max-time 10 "${trust[@]}" --resolve "$domain:443:127.0.0.1" \
            "https://$domain/api/health" >/dev/null 2>&1; then ok=1; break; fi
        sleep 2
    done
    [ -n "$ok" ] || log "WARNING: https://$domain/ has no trusted certificate yet. Check that $domain points here and ports 80 and 443 are open: docker compose logs caddy"
fi

CREDENTIALS=demo-credentials.txt
if [ "$SEED" = 1 ]; then
    log "Adding demo data (skip with --no-seed)"
    scripts/seed.sh "$CREDENTIALS" "${DOCKER[@]}" compose || die "could not add demo data"
fi

if [ -n "$domain" ]; then
    url="https://$domain"
else
    host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    url="http://${host_ip:-localhost}"
    [ "$port" = 80 ] || url="${url}:${port}"
fi

log "Ready"
printf '    Site:     %s/\n    API docs: %s/docs\n' "$url" "$url"
if [ -f "$CREDENTIALS" ]; then
    printf '    Demo:     accounts and passwords in %s/%s\n' "$PWD" "$CREDENTIALS"
fi
