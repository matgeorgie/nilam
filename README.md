# Nilam

Nilam is a local-first Kerala residential land-screening research project. It has two workflows:

1. **Assess a site** by searching, clicking a point, or drawing a polygon on Google Maps.
2. **Find matching land** by choosing a centre and radius, then optionally describing a preferred home location in text or English speech.

Nilam is a research screening tool. Its score is not construction clearance, a legal opinion, a property listing, proof that land is vacant, or the probability that a house is safe. Soil bearing capacity, title, zoning, wetland/CRZ status, drainage, utilities, legal access, and price still require primary records and professional inspection.

## Product model

The application exposes one model: **TerraMind Base + TabPFN 3.5 adaptive late fusion**.

- **TabPFN** reads 38 terrain, climate, soil, water, hazard, access, utility, and amenity features. It is the dominant expert because it performed best on held-out districts.
- **TerraMind** reads two 224 × 224 × 12 Sentinel-2 L2A composites: dry season (January–March) and monsoon season (June–September). The final two TerraMind blocks were fine-tuned during the multimodal experiment.
- Both experts output probabilities for four weak-label suitability classes. A validation-calibrated geometric pool converts them into one probability distribution. The selected TerraMind weight is 8%; TabPFN retains 92% influence.
- The displayed percentage is the probability-weighted ordinal index using class anchors 8%, 34%, 64%, and 90%. It is an experimental comparative score, not a calibrated safety probability.
- Conditional permutation SHAP perturbs TabPFN features while holding TerraMind evidence fixed, so the final report can explain mapped feature effects without repeatedly running the satellite backbone.

Calibration uses Ernakulam and Wayanad. Alappuzha, Idukki, and Kasaragod remain untouched test districts. The fused model obtained 0.847 macro-F1 and TabPFN alone obtained 0.850 on the 300-point test set. The gate accepts fusion only within a narrow performance tolerance and therefore limits TerraMind to 8%. Full metrics are tracked in [`docs/terramind-tabpfn-evaluation.json`](docs/terramind-tabpfn-evaluation.json).

## Statewide dataset

`data/processed/kerala_statewide_features.csv` contains 1,400 study rows: 100 spatially balanced points from each of Kerala’s 14 districts. It is generated locally and intentionally ignored by Git because the source geospatial assets are not redistributed.

The table combines:

- SRTM terrain: elevation, slope, aspect, and terrain ruggedness;
- CHIRPS/ERA5-Land climate: rainfall, humidity, temperature, and wind;
- OpenLandMap soils: clay, sand, pH, organic carbon, and water content;
- Dynamic World, MODIS, and JRC surface evidence: land cover, NDVI, water occurrence, and distance to water;
- GSI 2022 landslide susceptibility and KSDMA/UNEP flood depths for 10–500-year return periods;
- OpenStreetMap distances to roads, transport, hospitals, schools, pharmacies, shops, banks, parks, quarries, industry, waste facilities, and power lines.

`scripts/label_statewide_dataset.py` adds a transparent four-class weak target and rule trace. These labels represent public-data screening rules, not observed building outcomes or expert ground truth. See [`docs/statewide-dataset-card.json`](docs/statewide-dataset-card.json).

The 1,400 points remain the controlled academic training/evaluation cohort. They are not the search catalogue. Every land search creates roughly 900 fresh cells inside the selected circle, checks nearly three million mapped OSM building centres, and sends the 240 most promising and exploratory cells to Earth Engine. Dynamic World tests both the exact pixel and its 45 m neighbourhood for recent built-up and open-land signals before TabPFN ranks the surviving cells. Slow-changing soil and climate fields are interpolated from the statewide cohort. This keeps model training, geographic evaluation, and interactive search candidates separate.

## Local semantic and voice tools

- **Laya** is the local System 1 intent router. The finder shows when it is reading a request and which needs it understood; exact numeric requirements are extracted deterministically.
- **GLiNER2.5-Decide** is an optional experimental comparison enabled with `NILAM_ENABLE_GLINER=1`. It is not on the critical prediction path.
- **Distil-Whisper small.en** transcribes English requests locally. Its weights download on first voice use.
- Candidate search keeps safety constraints separate from preferences. It will not trade a mapped high flood or high landslide condition for a shorter commute.

Google Maps provides the basemap, address search, and Street View from both workflows. Open-land evidence comes from Dynamic World built probability, recent land cover, and the local OSM building index.

The first Laya interpretation downloads its local checkpoint (about 846 MB)
from Hugging Face. Later requests use the local cache. GLiNER and Distil-Whisper
also download only when their optional paths are used.

## Run locally

Requirements: macOS/Linux, Python 3.11, Node.js, completed Earth Engine authentication, local model artifacts, the prepared data files, and a Google Maps browser key with Maps JavaScript API, Places API (New), and Street View enabled.

Copy `.env.example` to `.env` and set:

```dotenv
PROJECT_ID=your-google-cloud-project-id
GOOGLE_MAPS_API_KEY=your-restricted-browser-key
OSM_PBF_PATH=../southern-zone-260916.osm.pbf
NILAM_ENABLE_LAYA=1
NILAM_ENABLE_GLINER=0
```

Restrict the Google key to `http://127.0.0.1:*` and the required browser APIs. Do not commit `.env`.

Install and build:

```bash
cd "/Users/mathewbijugeorge/Documents/Codex Project/kerala-land-lab"

uv venv --python /opt/homebrew/bin/python3.11 .venv-multimodal
uv pip install --python .venv-multimodal/bin/python -r requirements-multimodal.txt

cd web
npm install
npm run build
cd ..
```

Start the complete built application:

```bash
cd "/Users/mathewbijugeorge/Documents/Codex Project/kerala-land-lab"

PROJECT_ID=land-suitability-508903 \
PYTORCH_ENABLE_MPS_FALLBACK=1 \
.venv-multimodal/bin/python -m uvicorn kerala_land_lab.api:app \
  --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). For frontend development, run `npm run dev` in `web` and open port 5173; Vite proxies `/api` to port 8000.

## Reproduce data and models

Prepare base geospatial assets and the 1,400-row study:

```bash
.venv-multimodal/bin/python -m kerala_land_lab.data download
.venv-multimodal/bin/python -m kerala_land_lab.data prepare
.venv-multimodal/bin/python scripts/extract_osm.py ../southern-zone-260916.osm.pbf
PROJECT_ID=land-suitability-508903 .venv-multimodal/bin/python scripts/build_statewide_dataset.py --points-per-district 100
.venv-multimodal/bin/python scripts/label_statewide_dataset.py
```

Download seasonal chips with one worker on macOS, then train TerraMind multimodal v2:

```bash
PROJECT_ID=land-suitability-508903 \
.venv-multimodal/bin/python scripts/download_satellite_chips.py --workers 1

PYTORCH_ENABLE_MPS_FALLBACK=1 \
.venv-multimodal/bin/python scripts/train_multimodal.py \
  --variant base \
  --checkpoint "$HOME/models/terramind-v1-base/TerraMind_v1_base.pt" \
  --device mps --epochs 30 --batch-size 1 --accumulate 16
```

Fit/calibrate the product fusion from the trained TerraMind vision head and fitted TabPFN artifact:

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 \
.venv-multimodal/bin/python scripts/calibrate_terramind_tabpfn.py --batch-size 1
```

Build the local OSM building-centre index used by the radius search. The generated NPZ is ignored by Git:

```bash
.venv-multimodal/bin/python scripts/extract_osm_buildings.py \
  ../southern-zone-260916.osm.pbf
```

## Core files

- `src/kerala_land_lab/api.py` — API, progressive assessment, caching, search, voice, and model serving.
- `src/kerala_land_lab/fusion.py` — audited TerraMind/TabPFN probability fusion.
- `src/kerala_land_lab/search.py` — geographic filtering, non-negotiable safety rules, and preference ranking.
- `src/kerala_land_lab/semantic.py` — deterministic requirements plus Laya and optional GLiNER routing.
- `src/kerala_land_lab/satellite.py` — Earth Engine Sentinel-2 seasonal chips and persistent cache.
- `scripts/build_statewide_dataset.py` — 1,400-row Earth Engine/OSM dataset pipeline.
- `scripts/download_satellite_chips.py` — resumable dry/monsoon chip downloader.
- `scripts/train_multimodal.py` — TerraMind fine-tuning and multimodal ablation training.
- `scripts/calibrate_terramind_tabpfn.py` — product fusion calibration and district holdout evaluation.
- `scripts/extract_osm_buildings.py` — local index of mapped building centres for open-land screening.
- `web/src/main.jsx` and `web/src/style.css` — Google Maps product interface.

TabPFN weights have their own research/non-commercial terms. Review the installed model license before any deployment.
