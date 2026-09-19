"""Statewide sampling and evidence-label helpers.

The generated target is a hazard-reference label. It is deliberately not a
claim that a parcel is suitable or unsuitable for construction.
"""
from __future__ import annotations

import numpy as np
import geopandas as gpd
from shapely.geometry import Point


def balanced_district_points(districts: gpd.GeoDataFrame, per_district: int, seed: int) -> gpd.GeoDataFrame:
    """Draw the same number of reproducible points within every district."""
    rng = np.random.default_rng(seed)
    projected = districts.to_crs(32643)
    rows = []
    for district in sorted(projected.name.unique()):
        geometry = projected.loc[projected.name == district].geometry.union_all()
        minx, miny, maxx, maxy = geometry.bounds
        accepted = 0
        attempts = 0
        while accepted < per_district:
            attempts += 1
            if attempts > per_district * 1000:
                raise RuntimeError(f"Could not sample {per_district} points in {district}")
            point = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
            if geometry.contains(point):
                rows.append({"district": district, "geometry": point})
                accepted += 1
    points = gpd.GeoDataFrame(rows, crs=32643).to_crs(4326)
    points.insert(0, "point_id", [f"KL-{i:05d}" for i in range(1, len(points) + 1)])
    points["lat"] = points.geometry.y
    points["lng"] = points.geometry.x
    return points


def hazard_reference_label(flood_reference: str, landslide_susceptibility: str) -> tuple[str, float, str]:
    """Return an evidence label, evidence strength, and human-readable basis."""
    flood = flood_reference in {"Flood plain", "Waterbody"}
    if landslide_susceptibility == "High" or flood_reference == "Waterbody":
        return "high_hazard_reference", 1.0, "Direct intersection with an official high-hazard or waterbody polygon"
    if landslide_susceptibility == "Medium" or flood:
        return "hazard_review_reference", 1.0, "Direct intersection with an official medium-hazard or flood-plain polygon"
    if landslide_susceptibility == "Low":
        return "low_landslide_reference", 1.0, "Direct intersection with an official low-susceptibility polygon; other hazards remain unknown"
    return "unlabeled", 0.0, "No official reference polygon intersects the point; absence is not evidence of safety"


def terrain_zone(elevation: float | None) -> str:
    """Transparent analytical elevation class, not an official physiographic map."""
    if elevation is None or np.isnan(elevation):
        return "unknown"
    if elevation <= 20:
        return "lowland_0_20m"
    if elevation <= 300:
        return "midland_20_300m"
    return "highland_above_300m"
