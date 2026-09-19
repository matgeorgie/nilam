"""Build a district-balanced Kerala feature table from Earth Engine, KSDMA and OSM."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import STRtree

from kerala_land_lab.data import DISTRICTS
from kerala_land_lab.earth import initialize
from kerala_land_lab.statewide import balanced_district_points, hazard_reference_label, terrain_zone

EARTH_FEATURES = [
    "annual_rainfall", "aspect", "clay_content", "distance_to_water", "elevation",
    "flood_occurrence", "land_cover_class", "mean_humidity", "mean_temperature",
    "mean_wind_speed", "ndvi", "organic_carbon", "sand_content", "slope", "soil_ph",
    "terrain_ruggedness_index", "water_content",
]
DISTANCE_KINDS = ["hospital", "school", "quarry", "bus_stop", "railway_station", "pharmacy", "shop", "bank", "park", "waste_facility", "industrial"]


def earth_image() -> ee.Image:
    dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
    terrain = ee.Terrain.products(dem)
    rainfall = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                .filterDate("2000-01-01", "2025-01-01").sum().divide(25).rename("annual_rainfall"))
    # JRC masks locations where water was never detected. For the occurrence
    # band that has the defined value zero, distinct from missing source data.
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    distance_water = water.gt(0).fastDistanceTransform(2048).sqrt().multiply(30).rename("distance_to_water")
    land_cover = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate("2021-01-01", "2025-01-01")
                  .select("label").mode().rename("land_cover_class"))
    ndvi = (ee.ImageCollection("MODIS/061/MOD13Q1").filterDate("2019-01-01", "2025-01-01")
            .select("NDVI").mean().multiply(0.0001).rename("ndvi"))
    climate = (ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate("2015-01-01", "2025-01-01")
               .select(["temperature_2m", "dewpoint_temperature_2m", "u_component_of_wind_10m", "v_component_of_wind_10m"]).mean())
    temperature = climate.select("temperature_2m").subtract(273.15)
    dewpoint = climate.select("dewpoint_temperature_2m").subtract(273.15)
    humidity = (dewpoint.multiply(17.625).divide(dewpoint.add(243.04)).exp()
                .divide(temperature.multiply(17.625).divide(temperature.add(243.04)).exp())
                .multiply(100).clamp(0, 100).rename("mean_humidity"))
    wind = (climate.select("u_component_of_wind_10m").pow(2)
            .add(climate.select("v_component_of_wind_10m").pow(2)).sqrt().rename("mean_wind_speed"))
    clay = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b0").rename("clay_content")
    sand = ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b0").rename("sand_content")
    carbon = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select("b0").divide(5).rename("organic_carbon")
    ph = ee.Image("OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02").select("b0").divide(10).rename("soil_ph")
    soil_water = ee.Image("OpenLandMap/SOL/SOL_WATERCONTENT-33KPA_USDA-4B1C_M/v01").select("b0").rename("water_content")
    ruggedness = dem.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(1)).rename("terrain_ruggedness_index")
    return dem.addBands([
        terrain.select("slope"), terrain.select("aspect"), ruggedness, rainfall,
        water.rename("flood_occurrence"), distance_water, land_cover, ndvi,
        temperature.rename("mean_temperature"), humidity, wind, clay, sand, carbon, ph, soil_water,
    ]).select(EARTH_FEATURES).unmask(-9999, sameFootprint=False)


def sample_earth(points: gpd.GeoDataFrame, batch_size: int, checkpoint: Path) -> pd.DataFrame:
    image = earth_image()
    rows = pd.read_csv(checkpoint).to_dict("records") if checkpoint.exists() else []
    completed = {row["point_id"] for row in rows}
    pending = points.loc[~points.point_id.isin(completed)]
    for start in range(0, len(pending), batch_size):
        part = pending.iloc[start:start + batch_size]
        features = [ee.Feature(ee.Geometry.Point([r.lng, r.lat]), {"point_id": r.point_id}) for r in part.itertuples()]
        for attempt in range(1, 4):
            try:
                result = image.sampleRegions(collection=ee.FeatureCollection(features), scale=30, geometries=False, tileScale=4).getInfo()
                break
            except (TimeoutError, OSError):
                if attempt == 3:
                    raise
                print(f"Earth Engine transient failure; retry {attempt}/2", flush=True)
                time.sleep(2 * attempt)
        values = {feature["properties"]["point_id"]: feature["properties"] for feature in result["features"]}
        for point_id in part.point_id:
            row = {"point_id": point_id}
            row.update(values.get(point_id, {}))
            rows.append(row)
        pd.DataFrame(rows).to_csv(checkpoint, index=False)
        print(f"Earth Engine {len(rows)}/{len(points)}", flush=True)
    frame = pd.DataFrame(rows).set_index("point_id").loc[points.point_id].reset_index()
    return frame.replace(-9999, np.nan)


def nearest_distances(points: gpd.GeoDataFrame, geometries: gpd.GeoSeries) -> np.ndarray:
    targets = [g for g in geometries if g is not None and not g.is_empty]
    if not targets:
        return np.full(len(points), np.nan)
    tree = STRtree(targets)
    indices, distances = tree.query_nearest(points.geometry.to_numpy(), return_distance=True)
    # Multiple target geometries can tie for one point. Collapse ties instead
    # of returning one value per match, which can exceed the point count.
    result = np.full(len(points), np.nan)
    for source_index, distance in zip(indices[0], distances):
        if np.isnan(result[source_index]) or distance < result[source_index]:
            result[source_index] = distance
    return result


def attach_osm(frame: gpd.GeoDataFrame, processed: Path) -> gpd.GeoDataFrame:
    projected = frame.to_crs(32643)
    facilities = gpd.read_file(processed / "facilities.gpkg", layer="facilities").to_crs(32643)
    roads = gpd.read_file(processed / "roads.gpkg", layer="roads").to_crs(32643)
    power = gpd.read_file(processed / "power_lines.gpkg", layer="power_lines").to_crs(32643)
    projected["dist_nearest_road"] = nearest_distances(projected, roads.geometry)
    projected["dist_nearest_highway"] = nearest_distances(projected, roads.loc[roads.major.astype(bool), "geometry"])
    for kind in DISTANCE_KINDS:
        projected[f"dist_nearest_{kind}"] = nearest_distances(projected, facilities.loc[facilities.kind == kind, "geometry"])
    projected["dist_nearest_power_line"] = nearest_distances(projected, power.geometry)
    return projected.to_crs(4326)


def attach_hazards(points: gpd.GeoDataFrame, processed: Path) -> gpd.GeoDataFrame:
    hazards = gpd.read_file(processed / "hazards.gpkg", layer="hazards")
    joined = gpd.sjoin(points[["point_id", "geometry"]], hazards[["source", "source_label", "geometry"]], predicate="intersects", how="left")
    lookup = joined.groupby("point_id").apply(lambda g: list(zip(g.source.fillna(""), g.source_label.fillna(""))), include_groups=False).to_dict()
    flood_refs, landslide_refs, labels, scores, bases = [], [], [], [], []
    for point_id in points.point_id:
        hits = lookup.get(point_id, [])
        flood_values = {label for source, label in hits if source.startswith("flood/")}
        slide_values = {label for source, label in hits if source == "landslide/kerala"}
        flood = "Waterbody" if "Waterbody" in flood_values else "Flood plain" if "Flood plain" in flood_values else "Unmapped"
        slide = "High" if "High Hazard Zone" in slide_values else "Medium" if "Medium Hazard Zone" in slide_values else "Low" if "Low Hazard Zone" in slide_values else "Unknown"
        label, score, basis = hazard_reference_label(flood, slide)
        flood_refs.append(flood); landslide_refs.append(slide); labels.append(label); scores.append(score); bases.append(basis)
    points["flood_reference"] = flood_refs
    points["landslide_susceptibility"] = landslide_refs
    points["label"] = labels
    points["confidence_score"] = scores
    points["label_basis"] = bases
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points-per-district", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=70)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    processed = args.data_dir / "processed"
    initialize()
    districts = gpd.read_file(processed / "districts.geojson")
    missing = set(DISTRICTS) - set(districts.name)
    if missing:
        raise RuntimeError(f"Missing districts: {sorted(missing)}")
    points = balanced_district_points(districts, args.points_per_district, args.seed)
    checkpoint = processed / "statewide_earth_features.csv"
    if checkpoint.exists():
        candidate = pd.read_csv(checkpoint)
        earth = candidate if candidate.point_id.tolist() == points.point_id.tolist() else sample_earth(points, args.batch_size, checkpoint)
    else:
        earth = sample_earth(points, args.batch_size, checkpoint)
    earth = earth.replace(-9999, np.nan)
    earth.to_csv(checkpoint, index=False)
    points = points.merge(earth, on="point_id", how="left", validate="one_to_one")
    points["terrain_zone"] = points.elevation.apply(terrain_zone)
    points["seismic_zone"] = "III"
    points = attach_hazards(points, processed)
    points = attach_osm(points, processed)
    columns = [
        "point_id", "lat", "lng", "district", "terrain_zone", "annual_rainfall", "aspect",
        "clay_content", "distance_to_water", "elevation", "flood_occurrence", "flood_reference",
        "land_cover_class", "mean_humidity", "mean_temperature", "mean_wind_speed", "ndvi",
        "organic_carbon", "sand_content", "slope", "soil_ph", "terrain_ruggedness_index",
        "water_content", "seismic_zone", "landslide_susceptibility", "dist_nearest_road",
        "dist_nearest_highway", "dist_nearest_hospital", "dist_nearest_school", "dist_nearest_quarry",
        "dist_nearest_bus_stop", "dist_nearest_railway_station", "dist_nearest_pharmacy",
        "dist_nearest_shop", "dist_nearest_bank", "dist_nearest_park", "dist_nearest_power_line",
        "dist_nearest_waste_facility", "dist_nearest_industrial", "label", "confidence_score", "label_basis",
    ]
    output = processed / "kerala_statewide_features.csv"
    result = pd.DataFrame(points.drop(columns="geometry"))[columns]
    result.to_csv(output, index=False, float_format="%.6f")
    card = {
        "created_at": datetime.now(timezone.utc).isoformat(), "rows": len(result), "columns": columns,
        "seed": args.seed, "sampling": f"{args.points_per_district} random interior points in each of 14 district boundaries",
        "district_counts": result.district.value_counts().sort_index().to_dict(),
        "label_counts": result.label.value_counts().to_dict(), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "target_definition": "Evidence-only hazard reference; not a residential suitability or construction-safety label",
        "confidence_definition": "1.0 means a direct point/polygon intersection with a KSDMA/NCESS reference; 0.0 means unlabeled. It is not predictive confidence.",
        "feature_notes": {
            "flood_occurrence": "JRC Global Surface Water occurrence percentage; it is not historical flood-event frequency",
            "terrain_ruggedness_index": "3x3 SRTM elevation standard deviation proxy in metres",
            "soil": "OpenLandMap predicted surface values at 0 cm; organic carbon raw values divided by 5, pH divided by 10 per catalog scale",
            "terrain_zone": "Analytical elevation class: lowland <=20m, midland 20-300m, highland >300m; not an official Kerala physiographic classification",
            "distances": "Straight-line metres to the nearest mapped OSM geometry; completeness varies and legal/route access is not established",
            "seismic_zone": "Statewide Zone III generalization from KSDMA; site response and local geology are not represented",
        },
        "sources": {
            "terrain": "USGS/SRTMGL1_003", "rainfall": "UCSB-CHG/CHIRPS/DAILY, 2000-2024 annual mean",
            "water": "JRC/GSW1_4/GlobalSurfaceWater", "land_cover": "GOOGLE/DYNAMICWORLD/V1, 2021-2024 modal class",
            "vegetation": "MODIS/061/MOD13Q1, 2019-2024 mean NDVI", "climate": "ECMWF/ERA5_LAND/MONTHLY_AGGR, 2015-2024 mean",
            "soil": "OpenLandMap surface predictions, 250m", "hazards": "KSDMA/NCESS reference polygons",
            "infrastructure": "OpenStreetMap Southern Zone extract, ODbL 1.0",
        },
        "missing_by_feature": result.isna().sum().to_dict(),
        "limitations": ["Random sample points are not cadastral parcels", "No bearing-capacity test, title, zoning, permit, sewage, crime, price, noise, air-quality, or utility-service confirmation", "Unmapped means unknown, never safe", "Labels require expert review before supervised suitability training"],
    }
    Path("docs/statewide-dataset-card.json").write_text(json.dumps(card, indent=2) + "\n")
    print(json.dumps({"output": str(output), "rows": len(result), "districts": card["district_counts"], "labels": card["label_counts"], "sha256": card["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
