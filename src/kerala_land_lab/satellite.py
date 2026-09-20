"""Sentinel-2 seasonal chip retrieval shared by training and live inference."""
from __future__ import annotations

from functools import lru_cache
import io
import zipfile

import ee
import numpy as np
import rasterio
import requests

from kerala_land_lab.multimodal import EE_S2_BANDS


def mask_s2(image):
    scl = image.select("SCL")
    clear = scl.neq(0).And(scl.neq(1)).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return image.updateMask(clear).select(EE_S2_BANDS)


def seasonal_composite(start_month: int, end_month: int, region):
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region)
            .filterDate("2023-01-01", "2026-01-01")
            .filter(ee.Filter.calendarRange(start_month, end_month, "month"))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 65))
            .map(mask_s2)
            .median())


def source_image(region):
    dry = seasonal_composite(1, 3, region).rename([f"dry_{band}" for band in EE_S2_BANDS])
    monsoon = seasonal_composite(6, 9, region).rename([f"monsoon_{band}" for band in EE_S2_BANDS])
    return dry.addBands(monsoon).unmask(0).clamp(0, 10000).toUint16()


def geotiff_array(content: bytes) -> np.ndarray:
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
            if len(names) != 1:
                raise ValueError(f"Expected one GeoTIFF, found {names}")
            content = archive.read(names[0])
    with rasterio.MemoryFile(content) as memory:
        with memory.open() as dataset:
            return dataset.read()


@lru_cache(maxsize=128)
def sentinel2_chip(lon: float, lat: float, patch_m: int = 2240) -> np.ndarray:
    """Fetch one immutable two-season chip; rounded coordinates provide request caching."""
    region = ee.Geometry.Point([float(lon), float(lat)]).buffer(patch_m / 2).bounds()
    image = source_image(region)
    url = image.getDownloadURL({"name": "nilam-live", "region": region, "dimensions": "224x224", "crs": "EPSG:32643", "format": "GEO_TIFF"})
    with requests.get(url, timeout=180, headers={"Connection": "close"}) as response:
        response.raise_for_status()
        content = response.content
    array = geotiff_array(content)
    if array.shape != (24, 224, 224):
        raise ValueError(f"Unexpected Sentinel-2 export shape {array.shape}")
    chip = array.reshape(2, 12, 224, 224).astype(np.uint16)
    if float(np.any(chip > 0, axis=(0, 1)).mean()) < 0.70:
        raise ValueError("Sentinel-2 composite has insufficient clear pixels")
    chip.flags.writeable = False
    return chip
