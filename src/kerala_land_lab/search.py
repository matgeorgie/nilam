"""Deterministic candidate filtering and preference ranking."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape


OPEN_LAND_CLASSES = {2, 4, 5, 7}


@dataclass(frozen=True)
class SearchArea:
    district: str | None = None
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float | None = None
    geometry: dict[str, Any] | None = None


def _haversine_km(lat: np.ndarray, lon: np.ndarray, center_lat: float, center_lon: float) -> np.ndarray:
    phi1 = np.radians(lat)
    phi2 = np.radians(center_lat)
    dphi = np.radians(lat - center_lat)
    dlambda = np.radians(lon - center_lon)
    value = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(value), np.sqrt(1 - value))


def select_area(frame: pd.DataFrame, area: SearchArea) -> pd.DataFrame:
    selected = frame.copy()
    if area.district:
        selected = selected[selected.district == area.district]
    if area.geometry:
        polygon = shape(area.geometry)
        selected = selected[[polygon.covers(Point(row.lng, row.lat)) for row in selected.itertuples()]]
    if area.center_lat is not None and area.center_lon is not None and area.radius_km:
        distances = _haversine_km(selected.lat.to_numpy(), selected.lng.to_numpy(), area.center_lat, area.center_lon)
        selected = selected.assign(search_distance_km=distances)
        selected = selected[selected.search_distance_km <= area.radius_km]
    return selected.reset_index(drop=True)


def _closer_score(values: pd.Series, preferred_km: float | None, fallback_km: float) -> np.ndarray:
    target = max(preferred_km or fallback_km, 0.1) * 1000
    return np.clip(1 - values.fillna(values.median()).to_numpy(dtype=float) / (target * 2), 0, 1)


def rank_candidates(
    frame: pd.DataFrame,
    suitability: np.ndarray,
    requirements: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    if len(frame) != len(suitability):
        raise ValueError("Candidate rows and suitability scores must align")
    work = frame.copy()
    work["model_suitability"] = np.asarray(suitability, dtype=float)
    hard = np.ones(len(work), dtype=bool)
    hard &= work.land_cover_class.fillna(-1).to_numpy() != 0
    hard &= work.slope.fillna(90).to_numpy() <= float(requirements.get("max_slope", 30))
    if requirements.get("avoid_high_flood", True):
        hard &= work.flood_level_100yr_m.fillna(0).to_numpy() <= 1.5
    if requirements.get("avoid_high_landslide", True):
        hard &= work.gsi_landslide_susceptibility.fillna("Not mapped").to_numpy() != "High"
    if requirements.get("prefer_open_land"):
        hard &= work.land_cover_class.isin(OPEN_LAND_CLASSES).to_numpy()
    work = work.loc[hard].copy()
    if work.empty:
        return []
    scores = []
    weights = []

    def add(values, weight):
        scores.append(np.asarray(values, dtype=float)); weights.append(weight)

    add(_closer_score(work.dist_nearest_hospital, requirements.get("max_hospital_km"), 8), 1.2)
    add(_closer_score(work.dist_nearest_school, requirements.get("max_school_km"), 5), 1.0)
    add(_closer_score(work.dist_nearest_road, requirements.get("max_road_km"), 1.5), 1.1)
    if requirements.get("prefer_transit") or requirements.get("max_transit_km"):
        add(_closer_score(work.dist_nearest_bus_stop, requirements.get("max_transit_km"), 3), 1.0)
    if requirements.get("prefer_quiet"):
        industrial = np.clip(work.dist_nearest_industrial.fillna(0).to_numpy(dtype=float) / 3000, 0, 1)
        quarry = np.clip(work.dist_nearest_quarry.fillna(0).to_numpy(dtype=float) / 3000, 0, 1)
        add((industrial + quarry) / 2, 1.1)
    if requirements.get("prefer_green"):
        add(np.clip((work.ndvi.fillna(.5).to_numpy(dtype=float) - .25) / .55, 0, 1), .8)
    matrix = np.stack(scores, axis=1)
    preference_fit = np.average(matrix, axis=1, weights=np.asarray(weights)) * 100
    work["preference_fit"] = preference_fit
    work["overall_fit"] = .76 * work.model_suitability + .24 * preference_fit
    work = work.sort_values(["overall_fit", "model_suitability"], ascending=False).head(limit)
    candidates = []
    for rank, row in enumerate(work.itertuples(), 1):
        advantages = []
        constraints = []
        if row.slope <= 10: advantages.append("gentle mapped slope")
        elif row.slope >= 20: constraints.append("steeper terrain")
        if row.flood_level_100yr_m <= 0: advantages.append("outside mapped 100-year flood depth")
        elif row.flood_level_100yr_m > .5: constraints.append("mapped flood-depth evidence")
        if row.dist_nearest_road <= 1000: advantages.append("mapped road nearby")
        if row.dist_nearest_hospital <= 5000: advantages.append("hospital within 5 km")
        if row.gsi_landslide_susceptibility in {"Moderate", "High"}: constraints.append(f"{row.gsi_landslide_susceptibility.lower()} mapped landslide class")
        candidates.append({
            "rank": rank,
            "point_id": row.point_id,
            "lat": round(float(row.lat), 6),
            "lon": round(float(row.lng), 6),
            "district": row.district,
            "suitability_percent": round(float(row.model_suitability), 1),
            "preference_fit_percent": round(float(row.preference_fit), 1),
            "overall_fit_percent": round(float(row.overall_fit), 1),
            "apparently_open": int(row.land_cover_class) in OPEN_LAND_CLASSES,
            "advantages": advantages[:3],
            "constraints": constraints[:3],
            "evidence": {
                "slope": round(float(row.slope), 1),
                "flood_level_100yr_m": round(float(row.flood_level_100yr_m), 2),
                "landslide": row.gsi_landslide_susceptibility,
                "road_distance_m": round(float(row.dist_nearest_road)),
                "hospital_distance_m": round(float(row.dist_nearest_hospital)),
                "school_distance_m": round(float(row.dist_nearest_school)),
            },
        })
    return candidates
