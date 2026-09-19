"""Construct a reproducible weak-label landslide research dataset.

Samples are inside explicitly mapped low/medium/high KSDMA polygons. Labels
are historical map classes, NOT house suitability and NOT observed events.
Predictors are older terrain and rainfall; source class and coordinates never
enter the model. Polygon IDs are retained for group-separated evaluation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import ee
from kerala_land_lab.earth import initialize, feature_image, FEATURES, CATALOG

p = argparse.ArgumentParser()
p.add_argument("--per-class", type=int, default=240)
p.add_argument("--seed", type=int, default=42)
p.add_argument("--batch-size", type=int, default=60)
args = p.parse_args()
rng = np.random.default_rng(args.seed)
root = Path("data/processed")
hazards = gpd.read_file(root / "hazards.gpkg")
state = gpd.read_file(root / "kerala.geojson").geometry.iloc[0]
hazards = hazards[hazards.source.str.startswith("landslide/")].to_crs(32643)
labels = {"Low Hazard Zone": 0, "Medium Hazard Zone": 1, "High Hazard Zone": 2}
rows = []
for label, target in labels.items():
    group = hazards[hazards.source_label == label].copy()
    # Area-weighted selection avoids over-representing tiny polygon fragments.
    weights = group.geometry.area.to_numpy(copy=True); weights /= weights.sum()
    attempts = 0
    while sum(row["target"] == target for row in rows) < args.per_class:
        attempts += 1
        if attempts > args.per_class * 2000:
            raise RuntimeError(f"Unable to sample class {label}")
        polygon = group.iloc[rng.choice(len(group), p=weights)]
        x0, y0, x1, y1 = polygon.geometry.bounds
        point = Point(rng.uniform(x0, x1), rng.uniform(y0, y1))
        if not polygon.geometry.contains(point):
            continue
        geo = gpd.GeoSeries([point], crs=32643).to_crs(4326).iloc[0]
        if not state.covers(geo):
            continue
        rows.append({"sample_id": len(rows), "lon": geo.x, "lat": geo.y,
                     "target": target, "source_label": label,
                     "source_polygon_id": polygon.source_polygon_id,
                     "geometry": geo})
samples = gpd.GeoDataFrame(rows, crs=4326)
districts = gpd.read_file(root / "districts.geojson")[["name", "geometry"]]
samples = gpd.sjoin(samples, districts, how="left", predicate="within").rename(columns={"name": "district"}).drop(columns="index_right")
if samples.sample_id.duplicated().any() or samples.district.isna().any():
    raise RuntimeError("Every sample must belong to exactly one district")
samples.drop(columns="geometry").to_csv(root / "sample_plan.csv", index=False)
print(f"Sample plan: {len(samples)} locations, {samples.source_polygon_id.nunique()} source polygons",flush=True)
initialize()
image = feature_image()
cache = root / "feature_batches"
cache.mkdir(exist_ok=True)
signature = hashlib.sha256((root / "sample_plan.csv").read_bytes()).hexdigest()[:16]
records = []
for start in range(0, len(samples), args.batch_size):
    file = cache / f"{signature}-{start}.json"
    if file.exists():
        batch = json.loads(file.read_text())
    else:
        points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([row.lon, row.lat]), {"sample_id": int(row.sample_id)}) for row in samples.iloc[start:start+args.batch_size].itertuples()])
        # reduceRegions retains null values instead of silently dropping masked samples.
        result = image.reduceRegions(points, ee.Reducer.first(), scale=30, tileScale=4).getInfo()
        batch = [feature["properties"] for feature in result["features"]]
        file.write_text(json.dumps(batch))
    records.extend(batch)
    print(f"Earth Engine measurements: {len(records)}/{len(samples)}",flush=True)
frame = samples.drop(columns="geometry").merge(pd.DataFrame(records),on="sample_id",validate="one_to_one")
frame.to_csv(root / "landslide_dataset.csv",index=False)
card={"seed":args.seed,"rows":len(frame),"features":FEATURES,"feature_sources":CATALOG,"targets":labels,"sampling":"Class-balanced, polygon area weighted; not representative of Kerala prevalence", "purpose":"Reproduce historical mapped landslide susceptibility", "not_validated_for":"Construction suitability or future landslide probability", "source_polygons":int(frame.source_polygon_id.nunique()),"district_counts":frame.district.value_counts().to_dict(),"geographic_limitation":"The available KSDMA landslide polygons sampled here are concentrated in Wayanad; this pilot is not statewide evidence.","missing_by_feature":frame[FEATURES].isna().sum().to_dict()}
(root / "dataset-card.json").write_text(json.dumps(card,indent=2))
Path("docs").mkdir(exist_ok=True)
Path("docs/dataset-card.json").write_text(json.dumps(card,indent=2))
