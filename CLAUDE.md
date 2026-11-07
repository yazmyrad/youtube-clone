# YouTube clone — project rules

Test assignment: YouTube copy. Judged on: scope, similarity to YouTube, one-command deploy on clean Ubuntu,
architecture, DB design, AI setup, security, git history. Source of truth for design: docs/architecture.md.

## Stack (fixed)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async) + Alembic, PostgreSQL. Swagger at /docs.
- Storage: MinIO (S3 API) via presigned URLs. Video is processed by a worker (ffmpeg -> HLS 360p/720p + thumbnail).
- Queue: PostgreSQL table + `SELECT ... FOR UPDATE SKIP LOCKED` (no Redis).
- Frontend: Vite + React + TypeScript, Tailwind, React Router, TanStack Query, hls.js. API types generated from OpenAPI.
- Infra: docker compose (nginx, api, worker, postgres, minio), `./install.sh` does everything on clean Ubuntu.
- Tests: pytest + httpx; lint: ruff.

## Layout
backend/app/{api,core,models,schemas,services,workers}  backend/tests  backend/alembic
frontend/src/{pages,components,api,hooks}  infra/  docs/  scripts/seed.py  install.sh  README.md

## Rules
1. Work in small steps. One feature = migration + code + test + commit. Never batch unrelated changes.
2. Layering: router (thin) -> service (logic, permissions) -> models. No SQL in routers.
3. Roles (user/moderator/admin) and video visibility (public/unlisted/private) are checked ONLY through
   shared dependencies/services in app/core/permissions.py. Never re-implement checks inline.
4. Private video files are never public: playback only via short-lived signed URLs after a permission check.
5. No secrets in git. install.sh generates .env. Passwords: argon2. Validate uploads (size, ffprobe type).
6. Every critical behavior has a test (see docs/architecture.md "definition of done").
7. Before commit: `ruff check`, `pytest`. Commit messages: Conventional Commits (feat/fix/test/docs/chore).
8. Ask me before changing anything in docs/architecture.md or the DB schema.
9. Keep replies short. Don't paste big files back; reference paths.

## Commands
Development goes through the Makefile (`make` lists all targets). It runs a separate dev stack with hot reload.
- First time: `make setup`   Run: `make dev` (site and /docs at http://localhost:8080)   Stop: `make down`
- Before commit: `make check` (ruff + pytest; database tests need the dev stack running)
- Migrations: `make migration m="..."`, review the file, then `make migrate`. The stack also applies them on start.
- Deploy (clean Ubuntu): `./install.sh`   Deploy tests: `scripts/test-install.sh`, `scripts/test-clean-install.sh`
