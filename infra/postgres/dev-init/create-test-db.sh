#!/bin/sh
# Creates the test database, so tests never touch dev data. Safe to run again.
# Runs automatically when the dev volume is first created, and from `make test`.
set -eu

db="${POSTGRES_DB}_test"

exists="$(psql -qtA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v db="$db" <<'SQL'
SELECT 1 FROM pg_database WHERE datname = :'db';
SQL
)"

if [ "$exists" != 1 ]; then
    psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -v db="$db" -v owner="$POSTGRES_USER" <<'SQL'
CREATE DATABASE :"db" OWNER :"owner";
SQL
    echo "Created database $db"
fi
