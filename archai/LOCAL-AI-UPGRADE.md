# ArchAI local AI, guided requirements and walkthrough upgrade

## Entrance and garden finding

The supplied project dc47d24c-c741-4386-83e9-37d145503f98 has road_edge from (0,0) to (50,0), a north-side pedestrian entrance and north-side vehicle gate. The old 3D garden always left its south edge open and placed its paving there. The viewer now derives the access side from road_edge, splits the garden fence at the actual entry/vehicle door positions, and connects paths to those doors. Trees avoid the approaches. Existing saved room geometry was preserved.

## Changes

- First-person perspective walkthrough: drag to look, WASD/arrows to move, Escape to exit. Eye height is 5.4 ft. Wall and garden fence collision checks respect actual door/gate openings. Ground-level navigation includes the garden and open courtyard; upper levels stay on their floor. Select a floor to visit it. Interior ceilings appear during walkthrough. Door leaves open into their room instead of obstructing the common hall.
- Per-floor guided requirements in New project and Edit requirements: bedroom counts, kitchens, living/dining, shared bathrooms, utility, office, sit-out, balconies, parking, and individual bedroom ensuite checkboxes. The review lists every floor's rooms. Closed/open kitchen preference is editable.
- Official Qwen2.5-1.5B-Instruct Q4_K_M is installed on this laptop and verified against its pinned SHA256. llama-cpp-python runs inference directly in the Python process. No hosted AI inference, local HTTP language server, API key, or production rule-parser fallback is used. The old parser remains solely for legacy fixture tests.
- Language chat translates requests into typed edits. Room-reference validation asks which bedroom instead of applying a guessed instance. Position swaps preserve other room geometry, maintain bedroom enclosure and hall access, reject detached ensuites, and validate before saving. Adding/removing rooms regenerates the plan, reported explicitly; Undo/Redo remains available.
- Courtyard profiles support 2–4 bedrooms with the tested service program, all four road directions, a true courtyard hole and a full-width rear hall. Each bedroom accesses circulation directly. Closed-kitchen wall suppression was corrected.
- Windows start/stop scripts now terminate verified owned processes using their actual runtime records, avoiding a PowerShell Stop-Process failure encountered during QA.

## Use

Open http://127.0.0.1:3000/projects. The current creation flow is Plot → Floors → Rooms → Review, with confirmed structured choices and no required description reading. Advanced site settings are optional. The old Read with local AI creation button has been removed. In an existing project click Edit requirements. For walkthrough open 3D view then Start walkthrough. See REQUIREMENTS-UX.md for the newer intake redesign.

Chat examples: "Swap Bedroom 2 with Kitchen", "Remove Bedroom 3", "Add one bedroom on the ground floor". Use the exact room names displayed on your plan. A kitchen becoming a bedroom must be enclosed and have hall access; otherwise the swap is rejected and the saved plan is preserved.

## Validation evidence

37 focused backend tests passed: duplex stairs/landings and four road directions; courtyard programs of 2/3/4 bedrooms and four roads; courtyard hole preservation; validated swaps and grouped-room removal; actual HouseGAN/CubiCasa inference and exports; local provider selection, JSON validation and missing-weight failure without parser fallback.

Browser checks passed for guided form → generation → requirements editor → 3D → walking movement → Escape exit, plus gate alignment, door passage and wall collision across different plans. TypeScript type checking passed. Screenshots were inspected. The old complete legacy suite was not certified green; older shape/API assumptions have known incompatibilities.

Real model inference was exercised, not replaced by fixture responses: an ambiguous bedroom edit produced clarification without changing the revision; a named kitchen/bedroom swap succeeded; bedroom removal succeeded. Adding one bedroom on the ground floor also succeeded and restored the courtyard program from two to three bedrooms. Simple description extraction has been exercised, but this is not a language accuracy benchmark.

## Practical limits

This is a usable prototype with bounded planning support. It is not a general architectural optimizer. Arbitrary footprint/program combinations can remain infeasible. The small local model misread dimensions, counts and ensuite assignments during longer-description trials; site settings are therefore authoritative and all extracted rooms are exposed for review. Malformed/unfinished reading asks for guided input. Each inference pass is bounded, and concurrent language requests report busy instead of queuing indefinitely. Named edit trials took roughly 16–67 seconds; descriptions can take longer. Do not present the model as reliably understanding every architectural instruction.

Continuous stair climbing, furniture collision, structural design, building-code approval and reference-level photorealistic rendering are not implemented. The 2D and 3D continue using the same saved geometry. Blender rendering remains unverified from the earlier upgrade.

## Moving to another computer

The source archive includes the existing HouseGAN and CubiCasa weights, but excludes the 1.12 GB Qwen GGUF to avoid duplicating a large download. Setup-ArchAI.ps1 invokes Install-LocalAI.ps1, which installs the local runtime, downloads the pinned official checkpoint once and verifies its checksum. Inference works offline afterward. No database, sessions, credentials, node_modules or virtual environment are in the archive.

Official weights: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
Runtime: https://github.com/abetlen/llama-cpp-python
See START-HERE.md and apps/api/app/ml/language/README.md.
