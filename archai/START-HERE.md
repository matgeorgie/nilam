# ArchAI upgraded - start here

Requires Windows, Python 3.12 and Node.js 22+. The setup scripts also detect the bundled Codex runtimes on this laptop. Extract into a short folder path. Close memory-heavy programs: your laptop has 8 GB RAM. Initial dependency setup requires internet; inference runs locally afterward.

Open PowerShell in the extracted archai folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/Setup-ArchAI.ps1
powershell -ExecutionPolicy Bypass -File scripts/Start-ArchAI.ps1
```

Open http://127.0.0.1:3000/projects. Register a local account. Logs are in logs/. Stop with scripts/Stop-ArchAI.ps1. The scripts bind only to localhost. HouseGAN and CubiCasa are bundled. Setup downloads the pinned Qwen GGUF once; no hosted AI API is used.

## Reliable one-day demonstration

1. Create a single-floor rectangular project with 2 bedrooms, kitchen, living and bathrooms. Generate and inspect the checks.
2. Open 3D. Try full-height/cutaway, garden, and furniture controls.
3. Export layout JSON. Import that same JSON using Import 2D plan: this preserves geometry exactly and constructs the 3D scene from it.
4. Export the furnished GLB from the 3D viewer.
5. Try an uploaded clean black-line PNG/JPEG using the bundled sample-floorplan.png. Enter the full image width in feet, including margins. The AI reconstruction is an experimental draft: review room detection, walls and openings.

Do not describe the imported image path as exact. CubiCasa identifies semantic regions; our contour conversion estimates geometry. The supplied synthetic image produces only 3 detected rooms, so it is a model demonstration, not a completeness benchmark.

## What AI actually does

HouseGAN++ proposes 2D room layouts locally. Failed geometric checks trigger the existing deterministic planner; the UI shows this honestly. CubiCasa5K performs actual local neural inference on uploaded plan images. Structured JSON is the authoritative bridge from 2D to 3D; mesh generation and furniture placement are procedural. Natural-language interpretation now uses Qwen2.5-1.5B-Instruct Q4_K_M through llama-cpp-python directly inside the Python process. No HTTP inference service or rule-parser fallback is used. New projects use confirmed structured questions. Local AI chat interprets design edits after generation.

The viewer now has photographic wood textures, shadows, detailed procedural furnishings and garden context. These are conceptual interactive visuals, not reference-level photorealism or construction drawings.

Optional Blender rendering, after installing Blender separately:

```powershell
blender --background --python scripts/render-house.py -- furnished-house.glb render.png
```

Export GLB from the viewer first. This script was NOT run or verified here because Blender was unavailable. Better furniture assets and render tuning are still needed to approach the references.

See RESEARCH-AND-CHANGES.md for sources, licensing and test results. Both bundled checkpoints have upstream license conditions; CubiCasa is CC BY-NC 4.0. No personal database or credentials are included.

## Guided requirements and walkthrough

Use New project → Plot → Floors → Rooms → Review. Choose the road side visually, pick a floor count, and select rooms one floor at a time. Assign attached bathrooms to individual bedrooms. Review the exact brief and use Change links before Generate 2D plan. No description or language extraction is required. Setbacks and other footprints are under optional advanced settings.

Existing projects have Edit requirements. For chat, name rooms exactly as shown in the plan: "Remove Bedroom 3", "Add one bedroom on the ground floor", or "Swap Bedroom 2 with Kitchen". Position swaps preserve other rooms and need valid private-room access. Adding/removing rooms regenerates the plan and may move other rooms. Failed edits preserve the saved revision; Undo restores successful changes.

In 3D choose Start walkthrough. Drag to look, WASD or arrows to move, Escape to exit. Walls block movement and door openings permit passage. Select a floor to visit another floor; continuous stair climbing and furniture collisions are not implemented. The garden gate and paths follow the actual road and entrance geometry.

Qwen runs on CPU on this laptop. Descriptions can take several minutes, especially with multiple floors. The guided form avoids language inference and remains the dependable input path. The model is pretrained, not trained from scratch for this project.

The layout generator still has limited footprint/room-program support; this update does not make every arbitrary shape and request feasible. Courtyard profiles now support 2–4 bedrooms with the tested service-room program and all road directions. Review validation before using a concept as a project demonstration.
