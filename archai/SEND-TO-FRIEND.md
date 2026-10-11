# ArchAI — start here

This is the complete Windows project with the current website code, local AI model files, setup scripts and example floor plans. You do not need Codex or any AI API key.

## First-time setup

1. Install Python 3.12 (64-bit) and Node.js 22 or newer. Select Add Python to PATH when installing Python. Restart Windows or your terminal after installation.
2. Extract this entire ZIP into a short path, such as C:\ArchAI. Do not run it from inside the ZIP.
3. Double-click 1-SETUP.cmd. Internet is required to install application dependencies. This can take several minutes. Keep the setup window open until it says Setup complete.
4. Double-click 2-START.cmd. Wait for the website to start, then open http://127.0.0.1:3000/projects in Chrome or Edge.
5. Register your own local account. Choose New project, then follow Plot → Floors → Rooms → Review → Generate 2D plan.
6. To stop both servers, double-click 3-STOP.cmd. Do this before starting them again.

If Windows shows a downloaded-file warning, inspect the scripts before running them. Setup does not require administrator access.

## What is included

- Next.js website and FastAPI backend.
- HouseGAN++ checkpoint for layout proposals.
- CubiCasa5K checkpoint for experimental floor-plan image recognition.
- Qwen2.5-1.5B-Instruct Q4_K_M checkpoint for local chat edits.
- Guided requirements, 2D plans, 3D viewer, walkthrough, exports and revision history.
- examples/ contains layout JSON that can be imported with Import 2D plan in a workspace.
- Upstream model/source licenses and research notes. Preserve them when sharing. CubiCasa has noncommercial license conditions.

This package excludes the sender's user accounts, passwords, sessions and personal project database. Your own database is created locally on first use. Example JSON contains floor-plan geometry only; importing it does not import accounts or chat history.

## Hardware and operation

8 GB RAM is tight: close memory-heavy programs. More RAM improves responsiveness. Local Qwen runs on CPU in this version and chat can take tens of seconds. A dedicated GPU is not required to start the backend; browser WebGL is required for the 3D viewer. After first-time dependency setup, model inference needs no hosted service. Some decorative web fonts or remote images may still need internet.

The setup script verifies the bundled Qwen file instead of redownloading it. The ZIP intentionally does not contain node_modules or a Python virtual environment, because those must be installed for your machine.

## Using it

Use the guided questions rather than a long description. Rectangle is the best-supported footprint. Review every floor before generation. In the workspace, use Edit requirements to change counts or attached bathrooms. For AI chat, request one change at a time and use room names from the plan.

In 3D choose Start walkthrough. Drag to look, use WASD/arrows to move, and press Escape to exit. Select another floor to visit it; continuous stair climbing and furniture collisions are not implemented.

The planner has limited support for arbitrary shapes and room combinations. Plans are conceptual, not construction drawings. See REQUIREMENTS-UX.md and START-HERE.md for the current capabilities and limits.

## Troubleshooting

- Python not found: install Python 3.12 and ensure it is on PATH; avoid using the Microsoft Store launcher placeholder.
- Wrong Python version: use Python 3.12 for these pinned dependencies.
- Node/npm not found: install Node.js 22+ and reopen the setup window.
- Setup fails: read the last error, fix the missing prerequisite, then rerun 1-SETUP.cmd.
- Ports 3000 or 8000 already in use: stop your earlier ArchAI run using 3-STOP.cmd. Other applications using those ports must be closed separately.
- Page not ready: give the first launch time to compile, then reload. Logs are in logs/api-error.log and logs/web-error.log.

This package was checked for archive integrity, required model/source files, and exclusion of databases/credentials. The app was tested on the sender's Windows laptop. A clean installation on a separate friend's machine has not been tested.
