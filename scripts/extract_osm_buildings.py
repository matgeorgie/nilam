"""Build a compact local index of mapped OpenStreetMap building centres."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import osmium
from pyproj import Transformer
from shapely import wkb, make_valid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("pbf", type=Path)
parser.add_argument("--out", type=Path, default=Path("data/processed/osm_building_centres.npz"))
args = parser.parse_args()
args.out.parent.mkdir(parents=True, exist_ok=True)
factory = osmium.geom.WKBFactory()
longitudes, latitudes = [], []
processor = (osmium.FileProcessor(str(args.pbf)).with_locations().with_areas()
             .with_filter(osmium.filter.KeyFilter("building")))
for obj in processor:
    if not obj.is_area() or not obj.tags.get("building"):
        continue
    try:
        geometry = make_valid(wkb.loads(factory.create_multipolygon(obj), hex=True))
        point = geometry.representative_point()
        if 74.75 <= point.x <= 77.55 and 8.05 <= point.y <= 12.95:
            longitudes.append(point.x)
            latitudes.append(point.y)
    except (RuntimeError, ValueError):
        continue
    if len(longitudes) and len(longitudes) % 100_000 == 0:
        print(f"Mapped building centres: {len(longitudes):,}", flush=True)
transformer = Transformer.from_crs(4326, 32643, always_xy=True)
eastings, northings = transformer.transform(np.asarray(longitudes), np.asarray(latitudes))
np.savez_compressed(args.out, x=np.asarray(eastings, dtype=np.float32), y=np.asarray(northings, dtype=np.float32))
print(f"Saved {len(longitudes):,} building centres to {args.out}", flush=True)

