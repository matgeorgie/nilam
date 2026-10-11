# ArchAI

ArchAI 2 is the home-design extension included in Nilam. Start both apps with `bash scripts/run_integrated.sh` from the parent Nilam directory, then open `http://127.0.0.1:8000/`. Nilam serves this design studio at `/design/`; selecting **Design a home here** carries the chosen Kerala point and screening score into the plot brief. This is a site reference, not a measured parcel. The local studio opens directly without login and is intended only for loopback access.

New project now uses **Plot → Floors → Rooms → Review**. Select room counts and individual attached bathrooms without writing a description. Advanced site constraints are optional. The existing local AI chat remains available for edits after generation. See REQUIREMENTS-UX.md for the research, implementation and limits.

Turn your ideas into intelligent 2D & 3D house plans.

ArchAI is a runnable academic architecture application with a Next.js interface, FastAPI services, durable project storage, provider-independent language interpretation, a deterministic layout engine, vector plans, procedural 3D, revision history and exports.

**Generated plans are conceptual designs and should be reviewed and approved by a qualified architect/engineer before construction.** They are not construction drawings or building-code certifications.

For first-time setup, local startup, health checks, and troubleshooting, see [RUNNING.md](RUNNING.md).

## Run with Nilam

The integrated local launcher is the supported startup path. Follow [RUNNING.md](RUNNING.md), then open [Nilam](http://127.0.0.1:8000/). The home-design studio opens directly at `/design` without an account step. Saved projects persist in the local SQLite database across restarts. The plot wizard collects real plot dimensions and can generate several footprint families; Nilam's selected map point remains a reference attached to the design.

The former standalone Docker and account-based deployment paths are not part of this local Nilam integration. Do not expose the account-free API beyond loopback.

## Environment

See `.env.example`. Shell environment values are read by the backend. To load a file for a standalone API process, use `uvicorn --env-file ../../.env app.main:app`. Next.js reads frontend settings from `apps/web/.env.local` at build time.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL; local SQLite fallback if absent |
| `ARCHAI_MODEL_PATH` | Optional path to a local Qwen GGUF; default checkpoint under apps/api/app/ml/language |
| `NEXT_PUBLIC_API_URL` | Browser API origin, default `http://127.0.0.1:8001` |
| `CORS_ORIGINS` | Comma-separated local frontend origins; Nilam at port 8000 is included by default |

The local API uses one device-level project owner and rejects non-loopback project requests. Account registration, login and logout routes are removed. This is a local academic tool, not a security-audited hosted service.

## Architecture

```text
Next.js workspace
  → REST / chat
  → AIProvider → validated Pydantic requirements or operation
  → HouseSpecification + room relationships
  → LayoutEngine → deterministic feasible candidates
  → independent geometry validation + computed scores
  → immutable revision
  → SVG / React Three Fiber / exports
```

See `docs/architecture.md` for data model, API contracts and frontend structure. FastAPI exposes complete generated request/response documentation at `/docs` and `/openapi.json`.

### Language interpretation

Production language inference uses LocalModelProvider in apps/api/app/ai/local_model.py with a pinned official Qwen2.5-1.5B-Instruct Q4_K_M checkpoint and llama-cpp-python. It runs directly in the Python process without an HTTP inference endpoint. The old development parser is retained only for legacy fixtures and is never selected by get_provider(). Hosted language providers were removed.

Site settings from the form are authoritative. The local model reads per-floor room lists and cannot overwrite the plot, shape, road or floor count. The form exposes the extracted requirements for review. Typed JSON validation and room-reference checks reject malformed output and guessed room instances. Chat supports typed edits and validated position swaps; infeasible edits preserve the current revision. The general layout generator remains bounded and cannot handle every program or footprint.

See START-HERE.md and LOCAL-AI-UPGRADE.md for installation, controls, tested scope and limitations.

### Layout engine

`LayoutEngine` is the replaceable interface. `DeterministicLayoutEngine` expands counts, normalizes meters into feet, constructs a Shapely/GEOS buildable polygon from the plot and setbacks, allocates each room to exactly one floor, and uses bounded backtracking to partition shape-specific wings around connected circulation. It keeps attached bathrooms with their bedrooms, constructs walls and semantic openings, validates every candidate, and selects the highest-scoring feasible plan.

The seven concrete footprint families are generated inside the buildable plot polygon. Rectangle uses the full envelope; L, T, U, C and Stepped create orthogonal wings and intentional recesses; Courtyard uses a true polygon hole. `auto` searches across families and retains up to five shape-distinct valid alternatives with their checks, rationale, and scores. The workspace candidate selector promotes an alternative into an immutable revision. The same polygons drive validation, 2D drawing, exports, and 3D placement. Users can also request a shape in chat—for example, “Change the house shape to courtyard.”

Valid topology, plot containment, declared setbacks, minimum sizes, room counts, selected-footprint boundaries, floor indices, room overlap, valid openings, exterior windows, aligned stairs, reachability, road access, and prohibited bathroom-to-kitchen access are hard checks. Infeasible layouts are rejected atomically with a shape-specific explanation. Requirement coverage, relationships, preferred areas, circulation, usable efficiency, daylight, privacy, ventilation, structural simplicity, and plot utilization contribute to the formal score. Unmet soft preferences appear as warnings. The score is a comparison heuristic, not professional approval.

The specification accepts rectangular or polygonal plots, per-side setbacks, road side/width, and north angle. For irregular plots, the footprint template is intersected with the setback buildable polygon and rejected if clipping destroys too much usable area. Non-rectangular footprints have less usable area than a full rectangle, so a specification may need a larger plot, more floors, or fewer rooms. Exact-width requests that cannot fit a selected wing are rejected. Custom freehand building footprints, non-Manhattan wall reconstruction, jurisdiction-specific setback lookup, and road-specific gate/driveway routing are not yet implemented.

### 2D and 3D

The SVG renderer uses room polygons, deduplicated wall segments, semantic doors with swing arcs, exterior windows, furniture symbols, stairs, labels, dimensions and a compass. Select a room with a mouse or keyboard. Zoom controls, background drag pan and double-click reset are available.

The React Three Fiber viewer uses the same room and wall coordinates. Wall spans are split around doors and windows. Floor plates omit staircase openings; aligned steps connect levels. Neutral materials, basic furniture, daylight and orbit/pan/zoom support concept review. Floor selection and an optional roof control visibility. A rendering boundary preserves the 2D workflow on WebGL failure. First-person navigation is not implemented.

SVG, PNG and PDF export from the stored geometry. GLB and self-contained glTF export from a procedural scene built from the same rooms, walls and stair records. Export validates the saved revision again. SVG is the most detailed drawing export; the initial PDF/PNG exporter has simpler annotations/furniture than the interactive view. DXF and Blender pipelines are not implemented.

### Editing and history

Supported engine edits include room addition/removal, area resizing, exact dimensions when feasible, preferred-floor movement, relationship changes, floor count, style and plot dimensions, and regeneration. Individual door/window insertion/removal and arbitrary free-coordinate movement are explicitly rejected pending a wall-specific editor. Semantic operations are implemented without empty handlers or silently discarding a request.

Every successful major edit creates a revision. Failed edits do not overwrite the current design. History supports preview, restore, undo and redo. A new edit after undo preserves previous snapshots but starts a new current branch. Restoring creates another revision rather than deleting history.

## Testing

```powershell
cd apps/api
..\..\.venv\Scripts\python.exe -m pytest -q
cd ../..
npm run typecheck
npm run build
```

Run the required 100-plan geometry-diversity evaluation:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate-shape-diversity.py --count 100 --output docs\examples\shape-diversity-report.json
```

Browser tests expect both servers running:

```powershell
cd apps/web
npx playwright install chromium
npm run test:e2e
```

Tests cover acceptance extraction, footprint families, candidate retention, geometry validation, revisions, exports, and the account-free Nilam site-reference handoff. Some older browser fixtures still describe the former sign-in flow and need migration before running the complete legacy browser suite.

## Dataset and future ML integration

`apps/api/app/research/datasets.py` defines a normalized import format and checks room rectangles. It does not download datasets or pretend to contain a trained model. Dataset-specific CubiCasa5K SVG/segmentation and RPLAN raster annotation adapters can normalize their labels into this interface, subject to the original licenses. Keep training artifacts and raw datasets outside source control.

An experimental local HouseGAN++ checkpoint is bundled under `apps/api/app/ml/houseganpp` for research use. For eligible single-floor briefs without parking or attached bathrooms, its room-mask centres supply a small ranking bonus to otherwise valid deterministic candidates. Its masks do **not** become room coordinates, walls, openings, or a construction-ready plan; multi-floor plans still use the deterministic engine. The upstream HouseGAN++ code states research-only use under GPL-3.0, so review its terms and the RPLAN data provenance before redistribution or commercial use. No quality improvement claim has been established against a held-out architectural benchmark.

A future learned engine can implement `LayoutEngine.generate(specification)`. Its outputs must pass the independent validation layer before save/export. Compare requirement coverage, adjacency, area fidelity, circulation, efficiency and daylight heuristics against the deterministic baseline. Add dataset splits and reproducible evaluation before claiming learned performance.

## Academic limitations

Structural engineering, local codes, egress compliance, plumbing/HVAC routing, accessibility standards, exact setbacks, structural loads and construction documents are outside this prototype. The browser and exports are conceptual. Configured external LLM calls and PostgreSQL/Docker deployment need credentials/services and should be verified in the intended deployment environment. No external account or cloud deployment is bundled.
