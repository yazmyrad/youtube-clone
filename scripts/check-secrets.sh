#!/usr/bin/env bash
# D62: no secrets in git. Fails if an env or credentials file is tracked, or if a tracked
# file holds a private key, a cloud or GitHub token, or a long literal assigned to a
# secret-looking name. Example files ship empty values on purpose.
set -euo pipefail
cd "$(dirname "$0")/.."

failures=0
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

tracked="$(git ls-files | grep -E '(^|/)\.env(\.[a-z]+)?$|demo-credentials|\.pem$|(^|/)id_(rsa|ed25519)' \
    | grep -vE '\.example$' || true)"
[ -z "$tracked" ] || fail "tracked secret files: $tracked"

for check in \
    "private key|BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY" \
    "AWS access key|AKIA[0-9A-Z]{16}" \
    "GitHub token|gh[pousr]_[A-Za-z0-9]{30,}" \
    "Slack token|xox[abposr]-[A-Za-z0-9-]{10,}" \
    "literal secret|(SECRET|PASSWORD|PASSWD|ACCESS_KEY|SECRET_KEY|API_KEY|TOKEN)[A-Z_]*[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9/+_-]{24,}"; do
    name="${check%%|*}"
    pattern="${check#*|}"
    # CI's own values are labelled throwaway: the test services they unlock live for one run.
    found="$(git grep -nIE "$pattern" -- ':!*.lock' ':!*package-lock.json' ':!scripts/check-secrets.sh' \
        | grep -v 'throwaway' || true)"
    [ -z "$found" ] || fail "$name in: $(printf '%s\n' "$found" | cut -d: -f1,2 | tr '\n' ' ')"
done

git check-ignore -q .env || fail ".env isn't git-ignored"
git check-ignore -q backend/.env || fail "backend/.env isn't git-ignored"

[ "$failures" -eq 0 ] || exit 1
printf 'ok    no secrets tracked (D62)\n'
