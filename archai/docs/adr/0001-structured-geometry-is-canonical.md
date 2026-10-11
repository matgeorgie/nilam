# Structured geometry is the canonical plan

ArchAI stores editable polygonal rooms, footprints, walls and openings as the source of truth; SVG, raster, PDF and 3D outputs are projections of that geometry. An LLM may interpret language into a House Specification, and a learned model may later propose candidate geometry, but neither an image nor unconstrained model output can bypass deterministic topology and architectural validation. This makes rendering and ML components replaceable at the cost of maintaining a stricter geometry schema and reconstruction boundary.
