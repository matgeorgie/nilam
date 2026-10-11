# ArchAI implementation plan and contracts

## Delivery sequence
1. Runnable Next.js + FastAPI monorepo with durable SQLAlchemy storage.
2. Strict requirement extraction, provider interface, clarification and provenance.
3. Shapely-backed plot/buildable/footprint geometry and polygonal room contracts.
4. Multi-family candidate generation with backtracking allocation and connected circulation.
5. Hard validation, formal soft scoring, retained alternatives and immutable selection revisions.
6. SVG workspace, synchronized procedural Three.js model and vector/model exports.
7. Dataset adapter/evaluation boundary for a future learned vector proposer.

## Data model
User owns Projects. A Project has Messages and immutable Revisions. Each revision stores a validated HouseSpecification, semantic relationship graph, selected HouseLayout, retained Candidate Plans, validation checks and LayoutScore. JSON uses PostgreSQL JSONB (SQLite JSON for local development). Plot, buildable area, footprint (including courtyard holes), polygonal RoomGeometry, Wall, Door, Window and Stair records live inside the versioned layout, avoiding geometry split across independently updated tables. Generated exports are derived from a revision rather than stored redundantly.

All geometry is in feet internally; meter inputs and minimum/preferred areas are normalized once. Floors are zero-indexed. Room IDs are stable across regeneration. Wall openings have wall IDs, offset and width. The same wall segments, openings, rooms and stairs drive both renderers and exports.

## API
All project endpoints require a bearer session and ownership. `/api/auth/register`, `/login`, `/logout`, `/me` manage sessions; `/forgot-password` provides a non-enumerating response (email integration required for actual delivery).

`POST /api/projects {name, specification?}` → Project. `GET /api/projects` → ProjectSummary[]. `GET/PATCH/DELETE /api/projects/{id}` → project CRUD. `POST /duplicate` → copied project.

`POST /chat {message}` → {project, reply, missing_fields}. Extraction merges validated requirements without coordinates; incomplete specs produce clarification. Complete specs generate a validated revision atomically. `/requirements {specification}` replaces requirements. `/generate` generates. `/modify {message}` uses typed operations. `/layout` returns current layout. `/validate` returns validation. `/candidates/{candidate_id}/select` promotes a retained candidate and creates a new revision.

`GET /revisions` returns immutable history; `POST /revisions/{revision_id}/restore` creates a new revision from the selected snapshot. `/undo` and `/redo` move the current history cursor; a new edit after undo starts a new branch while retaining old snapshots. `/export/2d?format=svg|pdf|png` returns a file; `/export/3d?format=gltf|glb` returns a semantic-model-derived scene. Invalid layouts cannot export.

Errors use FastAPI JSON `detail` with a human-readable explanation; 401/403/404/422/503 distinguish authentication, ownership, missing records, impossible/invalid input and unavailable providers.

## Frontend
App Router routes: landing `/`, auth `/login`, projects `/projects`, workspace `/workspace/[id]`. Typed API boundary; React state for workspace and revision cursor, SVG pan/zoom/selection, lazy-loaded React Three Fiber canvas. Shared geometry adapter cuts openings in walls for 2D and 3D. Server remains authoritative; saves and revisions survive refresh. Mobile panels become tabs.

## Generation boundary

The LLM is limited to producing a schema-validated House Specification or typed edit operation. `DeterministicLayoutEngine` constructs and clips footprint polygons, allocates rooms with bounded backtracking, reconstructs walls/openings, rejects hard failures, and ranks valid plans. `auto` searches across seven concrete footprint families; a locked shape searches ordering variants within that family. Alternatives are retained as complete structured geometry rather than images.

The experimental HouseGAN++ adapter uses pre-trained single-floor room masks only as a small preference when ranking already valid deterministic candidates. It does not propose accepted room loops or wall geometry. A future learned geometry proposer would still need reconstruction and the same validation gate before persistence or export.

## Constraints and honest limitations

The optimizer supports polygonal plots, declared setbacks, and orthogonal polygonal building/room geometry. It rejects unsupported exact geometry and infeasible packing. Custom freehand building footprints and non-Manhattan wall reconstruction are not implemented. Adjacency is measured and explicitly reported, never asserted blindly. Scores are computed heuristics, not professional approval or code compliance. A research-only HouseGAN++ checkpoint is present, but it is not a source of accepted layout geometry. Offline extraction is an explicitly labeled rule-based development provider; configured LLM failures never silently fall back to mock responses. See `floorplan-generation-assessment.md`, `dataset-research.md`, and ADR 0001.
