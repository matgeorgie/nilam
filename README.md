# Nilam

Nilam is an evidence-first Kerala residential land-screening research project. A user selects a location and sees historical hazard overlays, terrain and rainfall measurements, mapped access and facilities, an explainable model estimate, and a list of facts the available data cannot establish.

It is a research prototype. It does not issue construction clearance, replace a geotechnical investigation, establish legal access or title, or predict a landslide probability.

## Current research result

The first pilot dataset contains 540 class-balanced points sampled from KSDMA/NCESS historical landslide-susceptibility polygons. Earth Engine supplies six predictors: elevation, slope, two circular aspect components, local relief, and historical annual rainfall. Original source polygons are kept disjoint across train, validation, and test partitions.

The data is geographically narrow: 537 points are in Wayanad and three in Kozhikode. The experiment therefore measures a Wayanad-focused ability to reproduce the historical map. It is not evidence of Kerala-wide model performance or construction safety.

Four model experiments are defined:

- ExtraTrees, a supervised non-neural baseline.
- A feature-token Transformer trained from scratch with AdamW and validation early stopping.
- TabPFN 3.5 Fast used in its normal in-context mode.
- TabPFN 3.5 Fast with gradient fine-tuning and local checkpoints.
- TerraMind 1.0 Base with two-season Sentinel-2 imagery and gated cross-attention fusion.

The generated dataset stays local at `data/processed/landslide_dataset.csv`; KSDMA redistribution permission has not been established. `scripts/build_dataset.py` reproduces it from the source archives and Earth Engine. The tracked `docs/dataset-card.json` and `docs/evaluation.json` record its provenance and results without publishing the source geometries or generated rows.

A second, separate statewide table is generated at `data/processed/kerala_statewide_features.csv`. Its 1,400 rows comprise 100 points in each district and combine terrain, climate, vegetation, soil, surface-water, official hazard-reference, and OSM proximity fields. Current hazard enrichment uses GSI 2022 district landslide shapefiles and KSDMA/UNEP historical flood water-level rasters for 10, 25, 50, 100, 200, and 500-year return periods.

`scripts/label_statewide_dataset.py` adds a four-class experimental public-data screening target, a 0–100 score, component penalties, confidence, and a rule trace. These are transparent weak labels for model development, not observed construction outcomes or expert ground truth. See `docs/statewide-dataset-card.json` for rules, units, periods, sources, missingness, and limitations.

## Run locally

Requirements: Python 3.11+, Node.js, a local Earth Engine login, a Mapbox public token, and the Southern Zone OSM PBF.

```bash
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e '.[research,test]'
cd web && npm install && npm run build && cd ..
.venv/bin/python -m uvicorn kerala_land_lab.api:app --host 127.0.0.1 --port 8000
```

For frontend development, run `npm run dev` inside `web`; it proxies `/api` to port 8000.

Copy `.env.example` to `.env` and set local values. Never commit Earth Engine credentials or a Google Places key. Google Places is optional; when configured, Nilam queries it live, keeps its results separate from OSM, displays Google Maps attribution, and does not cache place content.

## Reproduce the research

```bash
.venv/bin/python -m kerala_land_lab.data download
.venv/bin/python -m kerala_land_lab.data prepare
.venv/bin/python scripts/extract_osm.py ../southern-zone-260916.osm.pbf
.venv/bin/python scripts/build_dataset.py
.venv/bin/python scripts/build_statewide_dataset.py --points-per-district 100
.venv/bin/python scripts/label_statewide_dataset.py
PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python scripts/train.py --tabpfn --finetune --device mps
PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python scripts/train_statewide.py --tabpfn --finetune --device mps
```

The multimodal experiment uses a separate Python 3.11 environment. It downloads two 12-band Sentinel-2 chips for every statewide point, fine-tunes the last TerraMind blocks, and evaluates vision-only, tabular-only, and fused heads on whole-district holdouts. See [the multimodal experiment protocol](docs/multimodal-fusion.md) for the exact commands and limitations.

The Apple Silicon device flag can be replaced with `cpu` or `cuda` as appropriate. TabPFN 3.5 weights carry Prior Labs' research/non-commercial license; review it before any deployment.

## Data sources

- Kerala State Disaster Management Authority historic flood references, current GSI 2022 landslide susceptibility, and UNEP/KSDMA historical flood-return water levels.
- NASA/USGS SRTM, CHIRPS, JRC Global Surface Water, Dynamic World, MODIS NDVI, ERA5-Land, and OpenLandMap through Google Earth Engine.
- OpenStreetMap contributors under ODbL 1.0.
- Optional Google Places Nearby Search, queried live when a server-side key is configured.

## Next validation milestone

Build a statewide flood-reference dataset across all 14 districts, evaluate by held-out districts, add independent event inventories, calibrate uncertainty, and collect expert-reviewed plot labels. Only the last step can turn the project from hazard screening toward validated residential suitability.

## Suitability map and SHAP

The web app supports point selection and editable polygon drawing on normal or satellite Mapbox basemaps. Polygon reports sample up to nine locations across the selected area and show the median model score plus its spatial range.

The displayed suitability percentage is an ordinal experimental index derived from the four model-class probabilities (8%, 34%, 64%, and 90% anchors). Permutation SHAP explains this exact scalar output. Each attribution is reported in percentage points, grouped by evidence family, and paired with the measured feature value. Positive SHAP values raise the displayed score; negative values lower it.

This score is not a probability of safe construction. See [docs/academic-roadmap.md](docs/academic-roadmap.md) for the expert-label, multimodal satellite, graph-learning, temporal-monsoon, and conformal-uncertainty research plan.
