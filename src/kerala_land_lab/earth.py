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
