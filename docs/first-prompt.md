You are the architect and lead developer. We are building a YouTube clone as a take-home assignment (text below).
AI writes all the code; I set the tasks and review, so we work in small steps with tests and meaningful commits.

Technologies (fixed by the assignment): Python + FastAPI, PostgreSQL, Swagger /docs, deployment on a clean Ubuntu machine with one command.
My choices: SQLAlchemy 2 async + Alembic; MinIO (S3) for video with presigned uploads; a worker with ffmpeg (HLS 360p/720p, thumbnails),
a PostgreSQL-based queue (SKIP LOCKED), no Redis; nginx; docker compose + install.sh; frontend with Vite + React + TypeScript + Tailwind + hls.js;
pytest + httpx; ruff.

The agent tooling is already in .claude/: agents architect, reviewer, security-auditor, test-writer; skills add-endpoint, db-migration,
deploy-check; commands /feature, /review, /commit. CLAUDE.md contains the rules. Use them where appropriate.

The task for now is design only; do not write code. Create docs/architecture.md:
1. Goals and scope (what we are building, what we are deliberately NOT building).
2. Components and data flows: upload, processing, delivery, private videos (exactly how HLS segments are protected).
3. Database schema: tables, fields, relationships, indexes, constraints, enums.
4. Roles and permission matrix (user/moderator/admin × actions, public/unlisted/private).
5. API: list of endpoints by screen.
6. Security: threats and mitigations.
7. "Definition of done": verifiable criteria for "works correctly" for critical behavior.
8. A plan of ~25 steps, each step = one commit, organized by day (I have 9 days), prioritizing the scenario
   "sign-up → upload → watch → like and comment" after a single deploy command.
Ask questions if anything is ambiguous. Then wait for my approval.

--- ASSIGNMENT TEXT LINK -> docs/assignment.md