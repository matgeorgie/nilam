# Running Nilam with ArchAI 2

ArchAI 2 is the home-design studio inside Nilam. Its source lives in this `archai` directory. All three servers bind to `127.0.0.1`; Nilam presents the studio at the same browser origin under `/design`.

## First-time setup

Install the Nilam environment and build its data/models as described in the [Nilam README](../README.md). For ArchAI 2, use Node.js 22+ and Python 3.12:

```sh
cd "/Users/mathewbijugeorge/Documents/Codex Project/kerala-land-lab/archai"
python3.12 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.txt
CMAKE_ARGS="-DGGML_METAL=OFF -DGGML_OPENMP=OFF" .venv/bin/python -m pip install --no-cache-dir --no-binary=llama-cpp-python llama-cpp-python==0.3.36
.venv/bin/python scripts/download-language-model.py
npm install
```

The Qwen checkpoint powers free-text design edits. The plot-to-plan wizard still works when language inference is unavailable. Without `DATABASE_URL`, ArchAI stores designs in `apps/api/archai.db` on this device.

## Start the combined app

```sh
cd "/Users/mathewbijugeorge/Documents/Codex Project/kerala-land-lab"
bash scripts/run_integrated.sh
```

Open [Nilam](http://127.0.0.1:8000/). Assess a point or select a candidate in Find suitable land, then choose **Design a home here**. The plot wizard opens immediately at `/design` with that point’s coordinates, district and screening score. Enter real parcel dimensions, road side and rooms before generating a conceptual 2D/3D design. Saved designs are available at [Designs](http://127.0.0.1:8000/design/projects).

The launcher builds both frontends, starts Nilam on port 8000, the ArchAI API on 8001, and Next.js on 3000, then keeps them running until **Ctrl+C**. Ports 8000, 8001 and 3000 must be free. The ArchAI API health endpoint is [http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health). Existing dependencies, model weights and local designs in the former sibling `ArchAI 2` directory are reused when available; fresh setups can install directly in this directory.

The design API has no sign-in in this local edition. Keep it on loopback; project routes also reject non-loopback clients. Nilam’s point is a map reference, not a surveyed parcel, ownership record, or plot boundary.
