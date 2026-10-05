"""Deterministic candidate filtering and preference ranking."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


OPEN_LAND_CLASSES = {2, 4, 5, 7}
NON_BUILDABLE_COVER_CLASSES = {0, 3, 6, 8}
PREFERENCE_KEYS = {
    "max_hospital_km", "max_school_km", "max_road_km", "max_transit_km",
    "prefer_hospital", "prefer_school", "prefer_road", "prefer_transit",
    "prefer_quiet", "prefer_green", "prefer_park", "prefer_shops",
}


def _haversine_km(lat: np.ndarray, lon: np.ndarray, center_lat: float, center_lon: float) -> np.ndarray:
    phi1 = np.radians(lat)
    phi2 = np.radians(center_lat)
    dphi = np.radians(lat - center_lat)
    dlambda = np.radians(lon - center_lon)
    value = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(value), np.sqrt(1 - value))


def candidate_grid(center_lat: float, center_lon: float, radius_km: float, max_points: int = 900) -> pd.DataFrame:
    """Create a fresh, deterministic search grid inside a user-selected circle."""

    radius_m = float(radius_km) * 1000
    spacing_m = max(60.0, radius_m * np.sqrt(np.pi / max_points))
    lat_step = spacing_m / 111_320
    lon_step = spacing_m / (111_320 * max(np.cos(np.radians(center_lat)), 0.2))
    lat_extent = radius_m / 111_320
    lon_extent = radius_m / (111_320 * max(np.cos(np.radians(center_lat)), 0.2))
    rows = []
    for lat in np.arange(center_lat - lat_extent, center_lat + lat_extent + lat_step / 2, lat_step):
        for lon in np.arange(center_lon - lon_extent, center_lon + lon_extent + lon_step / 2, lon_step):
            distance = float(_haversine_km(np.array([lat]), np.array([lon]), center_lat, center_lon)[0])
            if distance <= radius_km:
                rows.append({
                    "point_id": f"search-{lat:.6f}-{lon:.6f}", "lat": float(lat), "lng": float(lon),
                    "search_distance_km": distance, "cell_size_m": round(spacing_m),
                })
    return pd.DataFrame(rows).sort_values("search_distance_km").reset_index(drop=True)


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
    if requirements.get("prefer_open_land", True):
        hard &= ~work.land_cover_class.fillna(-1).isin(NON_BUILDABLE_COVER_CLASSES).to_numpy()
        cover_open=work.land_cover_class.isin(OPEN_LAND_CLASSES).to_numpy()
        if "open_probability_45m" in work:
            open_probability=work.open_probability_45m.fillna(0).to_numpy(dtype=float)
            hard &= open_probability>=.12
            hard &= cover_open|(open_probability>=.18)
        else:
            hard &= cover_open
        if "built_probability" in work:
            hard &= work.built_probability.fillna(1).to_numpy(dtype=float) <= .35
        if "built_probability_45m" in work:
            hard &= work.built_probability_45m.fillna(1).to_numpy(dtype=float) <= .30
        if "building_distance_m" in work and work.building_distance_m.notna().any():
            hard &= work.building_distance_m.fillna(0).to_numpy(dtype=float) >= 30
    exact_limits = {
        "max_hospital_km": "dist_nearest_hospital", "max_school_km": "dist_nearest_school",
        "max_road_km": "dist_nearest_road", "max_transit_km": "dist_nearest_bus_stop",
    }
    for key, column in exact_limits.items():
        if requirements.get(key) is not None:
            hard &= work[column].fillna(np.inf).to_numpy(dtype=float) <= float(requirements[key]) * 1000
    work = work.loc[hard].copy()
    if work.empty:
        return []
    scores = []
    weights = []

    def add(values, weight):
        scores.append(np.asarray(values, dtype=float)); weights.append(weight)

    preference_requested = any(requirements.get(key) not in (None, False) for key in PREFERENCE_KEYS)
    add(_closer_score(work.dist_nearest_hospital, requirements.get("max_hospital_km"), 8), 1.5 if requirements.get("prefer_hospital") or requirements.get("max_hospital_km") else .45)
    add(_closer_score(work.dist_nearest_school, requirements.get("max_school_km"), 5), 1.4 if requirements.get("prefer_school") or requirements.get("max_school_km") else .4)
    add(_closer_score(work.dist_nearest_road, requirements.get("max_road_km"), 1.5), 1.5 if requirements.get("prefer_road") or requirements.get("max_road_km") else .6)
    if requirements.get("prefer_transit") or requirements.get("max_transit_km"):
        add(_closer_score(work.dist_nearest_bus_stop, requirements.get("max_transit_km"), 3), 1.0)
    if requirements.get("prefer_quiet"):
        industrial = np.clip(work.dist_nearest_industrial.fillna(0).to_numpy(dtype=float) / 3000, 0, 1)
        quarry = np.clip(work.dist_nearest_quarry.fillna(0).to_numpy(dtype=float) / 3000, 0, 1)
        add((industrial + quarry) / 2, 1.1)
    if requirements.get("prefer_green"):
        add(np.clip((work.ndvi.fillna(.5).to_numpy(dtype=float) - .25) / .55, 0, 1), .8)
    if requirements.get("prefer_park"):
        add(_closer_score(work.dist_nearest_park, None, 3), 1.1)
    if requirements.get("prefer_shops"):
        add(_closer_score(work.dist_nearest_shop, None, 3), 1.0)
    matrix = np.stack(scores, axis=1)
    preference_fit = np.average(matrix, axis=1, weights=np.asarray(weights)) * 100
    work["preference_fit"] = preference_fit
    built_column = "built_probability_45m" if "built_probability_45m" in work else "built_probability"
    if built_column in work:
        built_score = (1 - work[built_column].fillna(1).to_numpy(dtype=float)) * 100
    else:
        built_score = work.land_cover_class.isin(OPEN_LAND_CLASSES).to_numpy(dtype=float) * 100
    cover_score = np.where(work.land_cover_class.isin(OPEN_LAND_CLASSES), 100.0, 55.0)
    if "building_distance_m" in work and work.building_distance_m.notna().any():
        distance_score = np.clip(work.building_distance_m.fillna(0).to_numpy(dtype=float) / 120, 0, 1) * 100
        open_signal = np.clip(work.get("open_probability_45m", work.get("open_probability", pd.Series(0,index=work.index))).fillna(0).to_numpy(dtype=float),0,1)*100
        open_land_score = .40 * built_score + .30 * distance_score + .15 * cover_score + .15 * open_signal
    else:
        open_land_score = .75 * built_score + .25 * cover_score
    work["open_land_score"] = open_land_score
    if preference_requested:
        work["overall_fit"] = .52 * work.model_suitability + .20 * open_land_score + .28 * preference_fit
    else:
        work["overall_fit"] = .62 * work.model_suitability + .23 * open_land_score + .15 * preference_fit
    work = work.sort_values(["overall_fit", "model_suitability"], ascending=False).head(limit)
    candidates = []
    def optional_number(value, digits=1):
        return None if pd.isna(value) else round(float(value), digits)
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
            "open_land_percent": round(float(row.open_land_score), 1),
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
                "park_distance_m": optional_number(getattr(row, "dist_nearest_park", np.nan), 0),
                "building_distance_m": optional_number(getattr(row, "building_distance_m", np.nan)),
                "built_probability": optional_number(float(getattr(row, "built_probability", np.nan)) * 100),
                "nearby_built_probability": optional_number(float(getattr(row, "built_probability_45m", np.nan)) * 100),
                "satellite_open_probability": optional_number(float(getattr(row, "open_probability_45m", np.nan)) * 100),
                "cell_size_m": int(getattr(row, "cell_size_m", 0)),
            },
        })
    return candidates
