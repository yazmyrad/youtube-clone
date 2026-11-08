# Development commands. Run `make` to list them.
# Deploying to a server is separate: ./install.sh

SHELL := /bin/bash
.DEFAULT_GOAL := help

DEV := docker compose -p youtube-clone-dev --env-file .env.dev -f compose.yaml -f compose.dev.yaml
BIN := .venv/bin
# Runs a command in backend/ with the dev connection settings loaded.
IN_BACKEND := cd backend && set -a && . ./.env && set +a &&

.PHONY: help setup env venv dev up down rebuild logs ps shell nginx-reload \
	require-db test-db db-shell db-reset migrate migration downgrade migrations \
	run-local test test-storage test-upload lint fix check

help: ## Show this list
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Setup -----------------------------------------------------------------

setup: env venv ## First-time setup: env files and the Python virtualenv

env: ## Create .env.dev and backend/.env (keeps existing secrets)
	@scripts/dev-env.sh

venv: ## Create backend/.venv and install pinned dependencies
	@test -d backend/.venv || python3 -m venv backend/.venv \
		|| { echo "Creating the virtualenv failed. On Ubuntu: sudo apt install python3-venv" >&2; exit 1; }
	@backend/$(BIN)/pip install -q --disable-pip-version-check -c backend/requirements.lock -e "backend[dev]"

# --- Dev stack -------------------------------------------------------------

dev: up ## Start the stack with hot reload, then follow API logs (Ctrl-C stops only the logs)
	@trap 'exit 0' INT; $(DEV) logs -f --tail=20 api

up: env ## Start the stack in the background
	$(DEV) up -d --build --wait
	@. ./.env.dev && printf '\n  Site:     http://localhost:%s\n  API docs: http://localhost:%s/docs\n  Postgres: 127.0.0.1:%s\n\n' "$$HTTP_PORT" "$$HTTP_PORT" "$$DEV_DB_PORT"

down: env ## Stop the stack (keeps data)
	$(DEV) down

rebuild: env ## Rebuild images, for dependency or Dockerfile changes
	$(DEV) up -d --build --wait --force-recreate

logs: env ## Follow logs of all services
	@trap 'exit 0' INT; $(DEV) logs -f --tail=50

ps: env ## Show service status
	$(DEV) ps -a

shell: env ## Open a shell in the API container
	$(DEV) exec api sh

nginx-reload: env ## Validate infra/nginx/*.conf, then apply it (a bad config changes nothing)
	$(DEV) exec nginx nginx -t
	$(DEV) exec nginx nginx -s reload

# --- Database --------------------------------------------------------------

require-db: env
	@$(DEV) exec -T postgres pg_isready -q 2>/dev/null \
		|| { echo "The dev database isn't running. Start it with: make up" >&2; exit 1; }

test-db: require-db ## Create the test database if it's missing
	@$(DEV) exec -T postgres sh /docker-entrypoint-initdb.d/create-test-db.sh

db-shell: require-db ## Open psql on the dev database
	$(DEV) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-reset: env ## Delete all dev data (the dev stack only), then start fresh
	@read -r -p "Delete all data in the dev database? [y/N] " answer && [ "$$answer" = y ] \
		|| { echo "Cancelled."; exit 1; }
	$(DEV) down -v
	$(MAKE) up

migrate: require-db ## Apply migrations to the dev database
	$(IN_BACKEND) $(BIN)/alembic upgrade head

# `m` is read from the environment ($$m), so quotes and $ in the message are safe.
migration: migrate ## Create a migration from model changes: make migration m="add users"
	@test -n "$$m" || { echo 'usage: make migration m="describe the change"' >&2; exit 1; }
	$(IN_BACKEND) $(BIN)/alembic revision --autogenerate -m "$$m"

downgrade: require-db ## Roll back the latest migration
	$(IN_BACKEND) $(BIN)/alembic downgrade -1

migrations: require-db ## Show migration history and the current revision
	$(IN_BACKEND) $(BIN)/alembic history --indicate-current

# --- Code ------------------------------------------------------------------

run-local: env ## Run the API on the host at :8000 with reload (uses the stack's Postgres)
	$(IN_BACKEND) $(BIN)/uvicorn app.main:app --reload --port 8000

# The app is pointed at the test database too, so no test can reach dev data.
test: test-db ## Run tests; database tests use the dev stack's test database
	$(IN_BACKEND) DATABASE_URL="$$TEST_DATABASE_URL" $(BIN)/pytest -q

test-storage: env ## Check MinIO buckets and permissions on the running dev stack
	@scripts/test-storage.sh $(DEV)

test-upload: env ## Check uploads through nginx on the running dev stack (LARGE=1 sends 2 GB)
	@LARGE="$(LARGE)" scripts/test-upload.sh $(DEV)

lint: ## Check code with ruff
	cd backend && $(BIN)/ruff check .

fix: ## Apply ruff's automatic fixes
	cd backend && $(BIN)/ruff check --fix .

check: lint test ## Lint and test, as required before every commit
