#!/usr/bin/env bash
# Tests `./install.sh --domain`: HTTPS through Caddy, HTTP redirected, HSTS, Secure cookies,
# the Origin check behind TLS, nginx publishing no port, the client's address reaching
# nginx unforgeable, redirects staying on HTTPS, and `--no-domain` going back. `localhost`
# makes Caddy use its own CA, so no real domain is needed.
# Needs ports 80 and 443 free and no existing stack; removes everything it creates.
# Usage: scripts/test-domain.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

failures=0
pass() { printf 'ok    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
die() { printf 'FAIL  %s\n' "$1" >&2; exit 1; }

DOCKER=(docker)
docker info >/dev/null 2>&1 || DOCKER=(sudo docker)

[ ! -e .env ] || die "remove .env first"
[ -z "$("${DOCKER[@]}" volume ls -q --filter name=youtube-clone_)" ] \
    || die "remove the existing stack first: docker compose down -v"

work="$(mktemp -d)"
cleanup() {
    "${DOCKER[@]}" compose down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$work" .env
}
trap cleanup EXIT

for bad in 1.2.3.4 foo https://videos.example.com/; do
    if ./install.sh --no-seed --domain "$bad" >/dev/null 2>&1; then
        fail "--domain accepted $bad"
    fi
done
[ ! -e .env ] || fail "a rejected --domain still wrote .env"

./install.sh --no-seed --domain LocalHost

site=https://localhost
curl_tls() { curl -sk --max-time 10 "$@"; }

grep -qx 'DOMAIN=localhost' .env && pass "the domain is recorded, lowercased" \
    || fail ".env lacks DOMAIN=localhost"
grep -qx 'COMPOSE_FILE=compose.yaml:compose.domain.yaml' .env \
    && pass "compose commands use the HTTPS setup" || fail ".env lacks COMPOSE_FILE"

[ "$(curl_tls -o /dev/null -w '%{http_code}' "$site/api/health")" = 200 ] \
    && pass "the API answers over HTTPS" || fail "no HTTPS"
redirect="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' http://localhost/api/health)"
[ "$redirect" = "308 $site/api/health" ] && pass "plain HTTP is redirected to HTTPS" \
    || fail "HTTP answered: $redirect"
curl_tls -D "$work/headers" -o /dev/null "$site/"
grep -qi '^strict-transport-security: max-age=31536000' "$work/headers" && pass "HSTS is on" \
    || fail "no HSTS"
grep -qi '^x-frame-options: deny' "$work/headers" && pass "nginx's headers still arrive" \
    || fail "nginx's headers are lost"

# A trailing slash makes the API redirect; it must stay on https, or a POST would lose its
# Origin on the way.
location="$(curl_tls -o /dev/null -w '%{redirect_url}' "$site/api/videos/")"
case "$location" in
    http://*) fail "a redirect leaves HTTPS: $location" ;;
    *) pass "redirects stay on HTTPS (${location:-none})" ;;
esac

if "${DOCKER[@]}" compose port nginx 8080 >/dev/null 2>&1; then
    fail "nginx publishes a port"
else
    pass "only Caddy is published"
fi

json=(-H 'Content-Type: application/json')
curl_tls -o /dev/null "${json[@]}" "$site/api/auth/register" \
    -d '{"username":"tls_user","email":"tls@example.com","password":"correct horse battery","display_name":"TLS"}'
curl_tls -D "$work/login" -o /dev/null -c "$work/jar" "${json[@]}" "$site/api/auth/login" \
    -d '{"email":"tls@example.com","password":"correct horse battery"}'
grep -i '^set-cookie: refresh_token=' "$work/login" | grep -qi 'secure' \
    && pass "the refresh cookie is Secure" || fail "the refresh cookie isn't Secure"
refresh() { curl_tls -o /dev/null -w '%{http_code}' -b "$work/jar" -c "$work/jar" -X POST \
    -H "Origin: $1" "$site/api/auth/refresh"; }
[ "$(refresh http://localhost)" = 403 ] && pass "an http Origin is refused" \
    || fail "an http Origin was accepted"
[ "$(refresh "$site")" = 200 ] && pass "the site's https Origin may refresh" \
    || fail "refresh failed behind TLS"

curl_tls -o /dev/null -H 'X-Forwarded-For: 203.0.113.9' -H 'X-Real-IP: 203.0.113.9' \
    "$site/api/health?forged=1"
line="$("${DOCKER[@]}" compose logs nginx 2>/dev/null | grep 'forged=1' | tail -1)"
case "$line" in
    *203.0.113.9*) fail "a forged client address reached nginx: $line" ;;
    *10.213.67.2*) fail "nginx sees Caddy, not the client: $line" ;;
    "") fail "nginx logged no request" ;;
    *) pass "nginx sees the client's own address" ;;
esac

./install.sh --no-seed > "$work/rerun"
[ "$(curl_tls -o /dev/null -w '%{http_code}' "$site/api/health")" = 200 ] \
    && grep -q "https://localhost" "$work/rerun" && pass "a plain rerun keeps HTTPS" \
    || fail "a rerun dropped HTTPS"

./install.sh --no-seed --no-domain > "$work/back"
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost/api/health)" = 200 ] \
    && pass "--no-domain goes back to plain HTTP on port 80" || fail "--no-domain left no HTTP site"
[ -z "$("${DOCKER[@]}" ps -q --filter label=com.docker.compose.service=caddy)" ] \
    && pass "--no-domain removes Caddy" || fail "Caddy still runs after --no-domain"
grep -q '^DOMAIN=' .env && fail "--no-domain kept DOMAIN in .env" || pass "--no-domain clears .env"

[ "$failures" -eq 0 ] || { printf '%d check(s) failed\n' "$failures"; exit 1; }
printf 'all checks passed\n'
