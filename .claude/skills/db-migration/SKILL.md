---
name: db-migration
description: Change the database schema safely with Alembic. Use whenever models change.
---
1. Edit models in app/models. Add indexes for filters/joins and unique constraints (e.g. likes: user_id+video_id).
2. `alembic revision --autogenerate -m "<msg>"`; read the generated file and fix it (enums, defaults, downgrade).
3. `alembic upgrade head` on a fresh DB, then `alembic downgrade -1` and up again.
4. Update docs/architecture.md schema section. Commit migration + models together.
