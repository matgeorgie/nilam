"""Build a reusable coarse Kerala candidate-search index.

The default one-kilometre grid is a first-stage search surface. TerraMind is
run only after the user shortlists a candidate, avoiding a statewide satellite
chip download.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from kerala_land_lab.current_hazards import attach_flood_levels, attach_gsi_landslide, download_current_hazards
from kerala_land_lab.earth import initialize
from kerala_land_lab.statewide import terrain_zone
from build_statewide_dataset import attach_hazards, attach_osm, sample_earth


def grid_points(districts: gpd.GeoDataFrame, spacing_m: int) -> gpd.GeoDataFrame:
    projected = districts.to_crs(32643)
    rows = []
    point_number = 0
    for district in projected.itertuples():
        minx, miny, maxx, maxy = district.geometry.bounds
        for x in np.arange(minx + spacing_m / 2, maxx, spacing_m):
            for y in np.arange(miny + spacing_m / 2, maxy, spacing_m):
                point = Point(float(x), float(y))
                if district.geometry.covers(point):
                    rows.append({"point_id": f"SEARCH-{point_number:06d}", "district": district.name, "geometry": point})
                    point_number += 1
    result = gpd.GeoDataFrame(rows, crs=32643).to_crs(4326)
    result["lat"] = result.geometry.y
    result["lng"] = result.geometry.x
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacing-m", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=70)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    if args.spacing_m < 250:
        raise ValueError("Use at least 250 m for the coarse statewide index")
    processed = args.data_dir / "processed"
    points = grid_points(gpd.read_file(processed / "districts.geojson"), args.spacing_m)
    print(f"Candidate grid: {len(points):,} points", flush=True)
    initialize()
    earth = sample_earth(points, args.batch_size, processed / "search_earth_features.csv")
    points = points.merge(earth, on="point_id", how="left", validate="one_to_one")
    points["terrain_zone"] = points.elevation.apply(terrain_zone)
    points["seismic_zone"] = "III"
    points = attach_hazards(points, processed)
    download_current_hazards(args.data_dir)
    points = attach_gsi_landslide(points, args.data_dir)
    points = attach_flood_levels(points, args.data_dir)
    points = attach_osm(points, processed)
    output = processed / "kerala_search_index.csv"
    pd.DataFrame(points.drop(columns="geometry")).to_csv(output, index=False, float_format="%.6f")
    print(f"Saved {len(points):,} candidates to {output}")


if __name__ == "__main__":
    main()
