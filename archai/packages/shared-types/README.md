# Shared API types

The web client uses strict TypeScript contracts in `apps/web/lib/types.ts`. The authoritative validation boundary is Pydantic in `apps/api/app/schemas.py`. Generate JSON Schema with `python scripts/export-schema.py`; future clients can generate bindings from these files or `/openapi.json`.
