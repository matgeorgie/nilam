"""Transparent public-data weak labels for an experimental screening model.

These rules produce a research target, not expert ground truth, a building
permit decision, or a statement that a parcel is safe.
"""
from __future__ import annotations

import math
from typing import Mapping

LABEL_NAMES = {
    0: "screen_out_public_data",
    1: "low_public_data_suitability",
    2: "moderate_public_data_suitability",
    3: "higher_public_data_suitability",
}
VERSION = "public_screening_v1"
CORE_COMPLETENESS = [
    "annual_rainfall", "clay_content", "elevation", "mean_humidity", "ndvi", "slope", "soil_ph",
    "gsi_landslide_susceptibility", "flood_level_100yr_m", "dist_nearest_road", "dist_nearest_hospital",
]


def _number(row: Mapping, name: str, default: float = math.nan) -> float:
    try:
        value = float(row[name])
        return value if math.isfinite(value) else default
    except (KeyError, TypeError, ValueError):
        return default


def weak_label(row: Mapping) -> dict:
    components = {"hazard": 0.0, "terrain": 0.0, "environmental_conflict": 0.0, "access": 0.0, "amenities": 0.0}
    reasons = []

    def add(component: str, penalty: float, reason: str) -> None:
        components[component] += penalty
        reasons.append({"component": component, "penalty": penalty, "reason": reason})

    if _number(row, "land_cover_class") == 0 or row.get("flood_reference") == "Waterbody":
        add("hazard", 95, "Mapped water land cover or official waterbody reference")

    periods = (10, 25, 50, 100, 200, 500)
    flood_levels = {period: _number(row, f"flood_level_{period}yr_m", 0) for period in periods}
    first_period = next((period for period in periods if flood_levels[period] > 0), None)
    if first_period is not None:
        base = {10: 50, 25: 42, 50: 35, 100: 28, 200: 18, 500: 10}[first_period]
        level_penalty = min(15, max(flood_levels.values()) * 1.5)
        add("hazard", base + level_penalty, f"Modeled historical flood extent begins at the {first_period}-year return period")

    susceptibility = row.get("gsi_landslide_susceptibility")
    landslide_penalty = {"High": 45, "Moderate": 28, "Low": 10}.get(susceptibility, 0)
    if landslide_penalty:
        add("hazard", landslide_penalty, f"GSI 2022 {str(susceptibility).lower()} landslide susceptibility")
    if row.get("flood_reference") == "Flood plain" and first_period is None:
        add("hazard", 12, "Older KSDMA flood-plain reference intersects the point")

    slope = _number(row, "slope", 0)
    if slope >= 45:
        add("terrain", 35, "Slope is at least 45 degrees")
    elif slope >= 30:
        add("terrain", 25, "Slope is 30 to 45 degrees")
    elif slope >= 20:
        add("terrain", 15, "Slope is 20 to 30 degrees")
    elif slope >= 10:
        add("terrain", 7, "Slope is 10 to 20 degrees")
    ruggedness = _number(row, "terrain_ruggedness_index", 0)
    if ruggedness >= 20:
        add("terrain", 12, "High 3x3 elevation variability")
    elif ruggedness >= 10:
        add("terrain", 7, "Moderate 3x3 elevation variability")
    if _number(row, "annual_rainfall", 0) > 3500 and slope >= 20:
        add("terrain", 5, "High annual rainfall combined with a steep slope")

    water_distance = _number(row, "distance_to_water", math.inf)
    if water_distance < 30:
        add("environmental_conflict", 12, "Within 30 metres of mapped surface water")
    elif water_distance < 100:
        add("environmental_conflict", 7, "Within 100 metres of mapped surface water")
    elif water_distance < 250:
        add("environmental_conflict", 3, "Within 250 metres of mapped surface water")
    conflict_rules = {
        "dist_nearest_quarry": ((500, 15), (1000, 8)),
        "dist_nearest_waste_facility": ((500, 10), (1000, 5)),
        "dist_nearest_industrial": ((250, 10), (500, 5)),
        "dist_nearest_power_line": ((50, 15), (100, 8)),
    }
    for feature, thresholds in conflict_rules.items():
        distance = _number(row, feature, math.inf)
        for threshold, penalty in thresholds:
            if distance < threshold:
                add("environmental_conflict", penalty, f"Mapped {feature.removeprefix('dist_nearest_').replace('_', ' ')} within {threshold} metres")
                break

    road = _number(row, "dist_nearest_road", 0)
    if road > 2000:
        add("access", 15, "Nearest mapped road is over 2 kilometres away")
    elif road > 1000:
        add("access", 10, "Nearest mapped road is over 1 kilometre away")
    elif road > 500:
        add("access", 5, "Nearest mapped road is over 500 metres away")
    hospital = _number(row, "dist_nearest_hospital", 0)
    if hospital > 20000:
        add("amenities", 5, "Nearest mapped hospital is over 20 kilometres away")
    elif hospital > 10000:
        add("amenities", 3, "Nearest mapped hospital is over 10 kilometres away")
    if _number(row, "dist_nearest_school", 0) > 10000:
        add("amenities", 3, "Nearest mapped school is over 10 kilometres away")
    if _number(row, "dist_nearest_bus_stop", 0) > 5000:
        add("amenities", 2, "Nearest mapped bus stop is over 5 kilometres away")

    total_penalty = min(100.0, sum(components.values()))
    score = round(100 - total_penalty, 3)
    target = 0 if score < 25 else 1 if score < 50 else 2 if score < 70 else 3
    available = sum(not math.isnan(_number(row, feature)) for feature in CORE_COMPLETENESS)
    completeness = available / len(CORE_COMPLETENESS)
    official_evidence = first_period is not None or susceptibility in {"Low", "Moderate", "High"} or row.get("flood_reference") in {"Flood plain", "Waterbody"}
    confidence = 0.45 + 0.25 * completeness + (0.15 if official_evidence else 0)
    boundary_distance = min(abs(score - boundary) for boundary in (25, 50, 70))
    if boundary_distance < 3:
        confidence -= 0.08
    confidence = round(max(0.35, min(0.9, confidence)), 3)
    return {
        "label": target, "label_name": LABEL_NAMES[target], "suitability_score": score,
        "confidence_score": confidence, "weak_label_version": VERSION,
        **{f"penalty_{key}": round(value, 3) for key, value in components.items()},
        "label_basis": reasons,
    }
