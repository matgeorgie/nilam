"""Earth Engine measurements. Predictions are never substituted for observations."""
import os
from pathlib import Path
import ee
import httplib2
import google.oauth2.credentials
import socket

_getaddrinfo = socket.getaddrinfo

FEATURES = ["elevation", "slope", "northness", "eastness", "relief_300m", "rainfall_annual"]
CATALOG = {
    "elevation": {"unit": "m", "source": "USGS/SRTMGL1_003", "resolution_m": 30, "vintage": "2000"},
    "slope": {"unit": "degrees", "source": "SRTM-derived slope", "resolution_m": 30, "vintage": "2000"},
    "northness": {"unit": "cos(aspect)", "source": "SRTM-derived aspect", "resolution_m": 30, "vintage": "2000"},
    "eastness": {"unit": "sin(aspect)", "source": "SRTM-derived aspect", "resolution_m": 30, "vintage": "2000"},
    "relief_300m": {"unit": "m", "source": "SRTM focal elevation standard deviation within 300m", "resolution_m": 30, "vintage": "2000"},
    "rainfall_annual": {"unit": "mm/year", "source": "UCSB-CHG/CHIRPS/DAILY", "resolution_m": 5566, "vintage": "2000–2009 mean annual total"},
}
STATEWIDE_FEATURES = [
    "annual_rainfall", "aspect", "clay_content", "distance_to_water", "elevation",
    "flood_occurrence", "land_cover_class", "mean_humidity", "mean_temperature",
    "mean_wind_speed", "ndvi", "organic_carbon", "sand_content", "slope", "soil_ph",
    "terrain_ruggedness_index", "water_content",
]
STATEWIDE_CATALOG = {
    "annual_rainfall": {"unit": "mm/year", "source": "CHIRPS", "resolution_m": 5566, "vintage": "2000–2024 mean"},
    "aspect": {"unit": "degrees", "source": "SRTM-derived", "resolution_m": 30, "vintage": "2000"},
    "clay_content": {"unit": "%", "source": "OpenLandMap surface prediction", "resolution_m": 250, "vintage": "1950–2018 model"},
    "distance_to_water": {"unit": "m", "source": "JRC Global Surface Water", "resolution_m": 30, "vintage": "1984–2021"},
    "elevation": {"unit": "m", "source": "SRTM", "resolution_m": 30, "vintage": "2000"},
    "flood_occurrence": {"unit": "%", "source": "JRC surface-water occurrence", "resolution_m": 30, "vintage": "1984–2021"},
    "land_cover_class": {"unit": "class 0–8", "source": "Dynamic World modal class", "resolution_m": 10, "vintage": "2021–2024"},
    "mean_humidity": {"unit": "%", "source": "ERA5-Land derived", "resolution_m": 11132, "vintage": "2015–2024 mean"},
    "mean_temperature": {"unit": "°C", "source": "ERA5-Land", "resolution_m": 11132, "vintage": "2015–2024 mean"},
    "mean_wind_speed": {"unit": "m/s", "source": "ERA5-Land derived", "resolution_m": 11132, "vintage": "2015–2024 mean"},
    "ndvi": {"unit": "index", "source": "MODIS MOD13Q1", "resolution_m": 250, "vintage": "2019–2024 mean"},
    "organic_carbon": {"unit": "g/kg", "source": "OpenLandMap surface prediction", "resolution_m": 250, "vintage": "1950–2018 model"},
    "sand_content": {"unit": "%", "source": "OpenLandMap surface prediction", "resolution_m": 250, "vintage": "1950–2018 model"},
    "slope": {"unit": "degrees", "source": "SRTM-derived", "resolution_m": 30, "vintage": "2000"},
    "soil_ph": {"unit": "pH", "source": "OpenLandMap surface prediction", "resolution_m": 250, "vintage": "1950–2018 model"},
    "terrain_ruggedness_index": {"unit": "m std. dev.", "source": "SRTM 3×3 proxy", "resolution_m": 30, "vintage": "2000"},
    "water_content": {"unit": "volumetric %", "source": "OpenLandMap at 33kPa", "resolution_m": 250, "vintage": "1950–2018 model"},
}


def load_env():
    path = Path(__file__).resolve().parents[2] / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)


def initialize():
    load_env()
    if os.environ.get("NILAM_IPV4") == "1":
        # Process-local workaround for this host's stalled IPv6 connections.
        # TLS certificate verification and all authentication remain enabled.
        socket.getaddrinfo = lambda host, port, family=0, type=0, proto=0, flags=0: _getaddrinfo(host, port, socket.AF_INET if family == socket.AF_UNSPEC else family, type, proto, flags)
    project = os.environ.get("PROJECT_ID")
    if not project:
        raise RuntimeError("Set PROJECT_ID in .env")
    # Avoid the extra implicit validation refresh in get_persistent_credentials.
    credentials = google.oauth2.credentials.Credentials(None, **ee.oauth.get_credentials_arguments())
    ee.Initialize(credentials=credentials, project=project, http_transport=httplib2.Http(timeout=25))
    ee.data.setDeadline(60000)


def feature_image():
    dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
    terrain = ee.Terrain.products(dem)
    aspect = terrain.select("aspect").multiply(3.141592653589793 / 180)
    relief = dem.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.circle(300, "meters")).rename("relief_300m")
    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterDate("2000-01-01", "2010-01-01").sum().divide(10).rename("rainfall_annual"))
    return dem.addBands([terrain.select("slope"), aspect.cos().rename("northness"),
                         aspect.sin().rename("eastness"), relief, rain]).select(FEATURES)


def point_features(lon, lat):
    values = feature_image().reduceRegion(ee.Reducer.first(), ee.Geometry.Point([lon, lat]), scale=30, maxPixels=1000).getInfo()
    return {name: values.get(name) for name in FEATURES}


def statewide_feature_image():
    dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
    terrain = ee.Terrain.products(dem)
    rainfall = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate("2000-01-01", "2025-01-01").sum().divide(25).rename("annual_rainfall")
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    distance_water = water.gt(0).fastDistanceTransform(2048).sqrt().multiply(30).rename("distance_to_water")
    land_cover = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate("2021-01-01", "2025-01-01").select("label").mode().rename("land_cover_class")
    ndvi = ee.ImageCollection("MODIS/061/MOD13Q1").filterDate("2019-01-01", "2025-01-01").select("NDVI").mean().multiply(.0001).rename("ndvi")
    climate = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate("2015-01-01", "2025-01-01").select(["temperature_2m", "dewpoint_temperature_2m", "u_component_of_wind_10m", "v_component_of_wind_10m"]).mean()
    temperature = climate.select("temperature_2m").subtract(273.15)
    dewpoint = climate.select("dewpoint_temperature_2m").subtract(273.15)
    humidity = dewpoint.multiply(17.625).divide(dewpoint.add(243.04)).exp().divide(temperature.multiply(17.625).divide(temperature.add(243.04)).exp()).multiply(100).clamp(0, 100).rename("mean_humidity")
    wind = climate.select("u_component_of_wind_10m").pow(2).add(climate.select("v_component_of_wind_10m").pow(2)).sqrt().rename("mean_wind_speed")
    images = [
        terrain.select("slope"), terrain.select("aspect"), dem.reduceNeighborhood(ee.Reducer.stdDev(), ee.Kernel.square(1)).rename("terrain_ruggedness_index"), rainfall,
        water.rename("flood_occurrence"), distance_water, land_cover, ndvi, temperature.rename("mean_temperature"), humidity, wind,
        ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b0").rename("clay_content"),
        ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b0").rename("sand_content"),
        ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select("b0").divide(5).rename("organic_carbon"),
        ee.Image("OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02").select("b0").divide(10).rename("soil_ph"),
        ee.Image("OpenLandMap/SOL/SOL_WATERCONTENT-33KPA_USDA-4B1C_M/v01").select("b0").rename("water_content"),
    ]
    return dem.addBands(images).select(STATEWIDE_FEATURES).unmask(-9999, sameFootprint=False)


def statewide_point_features(lon, lat):
    values = statewide_feature_image().reduceRegion(ee.Reducer.first(), ee.Geometry.Point([lon, lat]), scale=30, maxPixels=1000).getInfo()
    return {name: None if values.get(name) == -9999 else values.get(name) for name in STATEWIDE_FEATURES}


def statewide_points_features(points):
    """Fetch Earth Engine features for several points in one server request."""
    features = [
        ee.Feature(ee.Geometry.Point([lon, lat]), {"sample_id": index})
        for index, (lon, lat) in enumerate(points)
    ]
    result = statewide_feature_image().reduceRegions(
        collection=ee.FeatureCollection(features),
        reducer=ee.Reducer.first(),
        scale=30,
    ).getInfo()
    rows = [None] * len(points)
    for feature in result.get("features", []):
        properties = feature.get("properties", {})
        index = int(properties["sample_id"])
        rows[index] = {
            name: None if properties.get(name) == -9999 else properties.get(name)
            for name in STATEWIDE_FEATURES
        }
    return [row or {name: None for name in STATEWIDE_FEATURES} for row in rows]
