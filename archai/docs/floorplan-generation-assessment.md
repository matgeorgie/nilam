# Floor-plan generation assessment

## Existing system

ArchAI is a small monorepo with a Next.js/React workspace, FastAPI service, SQLAlchemy persistence (SQLite locally and PostgreSQL JSONB in deployment), Pydantic contracts, an OpenAI-compatible requirement provider, SVG/React Three Fiber rendering, immutable revisions, and SVG/PNG/PDF/glTF/GLB exports. The database stores the complete specification and generated layout in each revision. Tests exercise parsing, geometry, validation, exports, authentication, revisions, and browser flows.

The pre-upgrade generator was not a learned graph model. It expanded room counts, assigned each room to a floor, chose one of a few hand-authored orthogonal footprint decompositions, and greedily stacked axis-aligned room rectangles along fixed four-foot corridors. Four “candidates” changed room ordering but shared the same footprint and packing grammar. Only the highest-scoring layout was returned; alternatives were discarded.

## Why layouts collapsed into rectangles

1. `RoomGeometry` stored only `x`, `y`, `width`, and `height`; a non-rectangular room could not be represented.
2. The wall builder assumed four edges per room.
3. Candidate generation varied ordering, not topology, footprint family, or circulation graph.
4. A single vertical or horizontal corridor spine determined every partition.
5. The plot was always treated as an axis-aligned rectangle and setbacks were not passed into generation.
6. Scores covered requirements, adjacency, approximate area, reachability, efficiency, and daylight, but not privacy, ventilation, structural simplicity, or plot utilization.
7. The API persisted only the selected layout, so the frontend could not compare or promote another candidate.

## Implemented architecture

The current slice keeps the app runnable while replacing those constraints incrementally:

```text
language → validated House Specification
         → buildable polygon + candidate footprint families
         → backtracking room-to-wing allocation
         → polygonal rooms / walls / openings / circulation
         → GEOS topology + architectural hard checks
         → formal multi-factor score
         → ranked, retained Candidate Plans
         → selected immutable revision
         → SVG / PDF / raster / 3D projections
```

The canonical room model now supports arbitrary polygons while retaining bounding fields for compatibility. Footprints support rectangle, L, T, U, C, stepped, and enclosed-courtyard geometries, plus an `auto` search strategy. Plot polygons, per-side setbacks, road side, road width, and north angle are part of the specification. Shapely/GEOS performs polygon intersection, containment, area, distance, validity, and union operations. A bounded backtracking allocator replaces the previous greedy placement failure mode. The generator retains up to five shape-distinct valid alternatives with validation and scores; selecting one creates a revision.

Hard checks now include valid topology, plot containment, setbacks, footprint containment, non-overlap, room counts, minimum dimensions, opening placement, stair alignment, connected circulation, road entrance, and prohibited bathroom-to-kitchen access. Soft ranking includes requirement coverage, requested relationships, preferred areas, circulation, usable efficiency, daylight, privacy, ventilation, structural simplicity, and plot utilization.

## Deliberate limits

- The candidate proposer is procedural and deterministic today; no trained weights are bundled or falsely represented as AI.
- Generated room polygons are currently orthogonal. The schema and wall reconstruction support multi-vertex orthogonal polygons, but non-Manhattan wall reconstruction remains future work.
- Irregular input plots are clipped with robust geometry operations, but severe clipping is rejected instead of forcing an unsafe packing.
- Setbacks are user-declared design inputs, not jurisdiction-specific code validation.
- Furniture is representational and not yet included in collision constraints.
- Structural grids, wet-stack optimization, MEP, egress codes, accessibility codes, and local planning law require configurable professional rule packs.

## Recommended learned-model phase

Do not train an image generator. First normalize a legally usable polygon/graph corpus and establish the deterministic evaluator as the acceptance gate. The smallest maintainable learned component is a conditional polygon/adjacency proposer: a compact transformer or diffusion model predicts normalized room loops and door relations from the House Specification and footprint; geometric reconstruction snaps and repairs the proposal; the existing validator accepts or rejects it. Compare it against the procedural baseline before enabling it in production.
