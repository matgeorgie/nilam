"""Current official Kerala hazard layers used by the statewide table."""
from __future__ import annotations

import hashlib
import json
import zipfile
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
import requests

GSI_DISTRICTS = {
    "Thiruvananthapuram": "TVM", "Kollam": "Kollam", "Pathanamthitta": "Pathanamthitta",
    "Kottayam": "Kottayam", "Idukki": "Idukki", "Ernakulam": "Ernakulam",
    "Thrissur": "Thrissur", "Palakkad": "Palakkad", "Malappuram": "Malappuram",
    "Kozhikode": "Kozhikode", "Wayanad": "Wayanad", "Kannur": "Kannur", "Kasaragod": "Kasaragod",
}
BASE = "https://sdma.kerala.gov.in/wp-content/uploads"
GSI_URLS = {district: f"{BASE}/2025/08/{slug}.zip" for district, slug in GSI_DISTRICTS.items()}
FLOOD_URLS = {
    "10_25_50": f"{BASE}/2026/06/1.-Flood-Return-Probability-Historical-10-25-50-years.zip",
    "100_200_500": f"{BASE}/2026/06/2.Flood-Return-Probability-Historical-100-200-500-years.zip",
}
RETURN_PERIODS = (10, 25, 50, 100, 200, 500)


def _download(url: str, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=(20, 180)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_current_hazards(data_dir: Path) -> dict:
    gsi_dir = data_dir / "raw/ksdma_gsi_2022"
    flood_dir = data_dir / "raw/ksdma_flood_probability"
    manifest = []
    for district, url in GSI_URLS.items():
        path = gsi_dir / f"gsi_2022_{GSI_DISTRICTS[district]}.zip"
        _download(url, path)
        manifest.append({"kind": "gsi_landslide", "district": district, "url": url, "file": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    for group, url in FLOOD_URLS.items():
        path = flood_dir / f"flood_probability_{group}.zip"
        _download(url, path)
        manifest.append({"kind": "flood_probability", "return_periods": group, "url": url, "file": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {"source_page": "https://sdma.kerala.gov.in/hazard-maps/", "files": manifest}
    (data_dir / "current-hazard-sources.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def _zip_layer(path: Path) -> gpd.GeoDataFrame:
    with zipfile.ZipFile(path) as archive:
        shapefiles = [name for name in archive.namelist() if name.lower().endswith(".shp")]
        if len(shapefiles) != 1:
            raise ValueError(f"Expected one shapefile in {path}, found {shapefiles}")
        layer = shapefiles[0]
    return gpd.read_file(f"zip://{path.resolve()}!{layer}")


@lru_cache(maxsize=2)
def gsi_layer(data_dir: Path) -> gpd.GeoDataFrame:
    layers = []
    for district, slug in GSI_DISTRICTS.items():
        layer = _zip_layer(data_dir / f"raw/ksdma_gsi_2022/gsi_2022_{slug}.zip").to_crs(4326)
        layer["district_source"] = district
        layers.append(layer[["Susceptibi", "district_source", "geometry"]])
    return gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), crs=4326)


def attach_gsi_landslide(points: gpd.GeoDataFrame, data_dir: Path) -> gpd.GeoDataFrame:
    susceptibility = gsi_layer(data_dir)
    joined = gpd.sjoin(points[["point_id", "geometry"]], susceptibility, predicate="intersects", how="left")
    priority = {"High": 3, "Moderate": 2, "Low": 1}
    values = {}
    for point_id, rows in joined.groupby("point_id"):
        candidates = list(rows.Susceptibi.dropna())
        values[point_id] = max(candidates, key=lambda value: priority[value]) if candidates else "Not mapped"
    result = points.copy()
    result["gsi_landslide_susceptibility"] = result.point_id.map(values)
    return result


def _raster_member(path: Path, period: int) -> str:
    with zipfile.ZipFile(path) as archive:
        matches = [name for name in archive.namelist() if name.endswith(f"_{period}_yr_Historical.tif")]
    if len(matches) != 1:
        raise ValueError(f"Expected one {period}-year raster in {path}, found {matches}")
    return matches[0]


def attach_flood_levels(points: gpd.GeoDataFrame, data_dir: Path) -> gpd.GeoDataFrame:
    """Attach modeled flood water level in metres; zero means outside the modeled extent."""
    result = points.copy()
    coordinates = list(zip(result.geometry.x, result.geometry.y))
    for period in RETURN_PERIODS:
        group = "10_25_50" if period <= 50 else "100_200_500"
        path = data_dir / f"raw/ksdma_flood_probability/flood_probability_{group}.zip"
        member = _raster_member(path, period)
        with rasterio.open(f"zip://{path.resolve()}!{member}") as source:
            raw = list(source.sample(coordinates, masked=True))
        # Official maps label this variable Flood Water Level (m). The TIFF
        # stores centimetre-scale values: 400 corresponds to 4 metres.
        result[f"flood_level_{period}yr_m"] = [0.0 if value.mask[0] else float(value[0]) / 100 for value in raw]
    return result
