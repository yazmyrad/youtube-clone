---
name: add-endpoint
description: Add a new FastAPI endpoint following project layering (schema, service, router, permission, test). Use for any new API route.
---
1. Pydantic schemas in app/schemas/<area>.py (separate In/Out models, never return ORM objects).
2. Logic and permission check in app/services/<area>.py using app/core/permissions.py.
3. Thin router in app/api/<area>.py with response_model, status codes, tags for Swagger.
4. Tests in backend/tests/test_<area>.py: happy path, unauthenticated, forbidden, not found.
5. Run ruff + pytest, then commit.
