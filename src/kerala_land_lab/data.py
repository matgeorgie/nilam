"""Download and normalize official reference layers without inventing labels.

These maps describe historical susceptibility. They are not construction permits,
observed landslide events, or labels of safe/unsafe residential land.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import requests
from defusedxml import ElementTree as ET
from shapely import make_valid
from shapely.geometry import Point, Polygon

SOURCES = {
    "ksdma_flood.zip": "https://sdma.kerala.gov.in/wp-content/uploads/2018/10/Flood_KML.zip",
    "ksdma_landslide.rar": "https://sdma.kerala.gov.in/wp-content/uploads/2020/08/Landslide-1.rar",
}
DISTRICTS = ["Kasaragod", "Kannur", "Wayanad", "Kozhikode", "Malappuram", "Palakkad", "Thrissur", "Ernakulam", "Idukki", "Kottayam", "Alappuzha", "Pathanamthitta", "Kollam", "Thiruvananthapuram"]


def download(root: Path) -> None:
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, url in SOURCES.items():
        path = raw / name
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".part")
            try:
                with requests.get(url, stream=True, timeout=(15, 120)) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        manifest.append({
            "file": name, "url": url, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "license": "Not established; retain locally, do not redistribute",
            "source_page": "https://sdma.kerala.gov.in/maps/",
            "source_vintage": "NCESS 2010 according to KSDMA source page",
            "purpose": "Historical susceptibility reference, not suitability ground truth",
        })
    (root / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n")


def coordinates(text: str) -> list[tuple[float, float]]:
    result = []
    for token in text.split():
        lon, lat, *_ = token.split(",")
        x, y = float(lon), float(lat)
        if not (-180 <= x <= 180 and -90 <= y <= 90):
            raise ValueError("KML coordinate outside geographic bounds")
        result.append((x, y))
    return result


def parse_kml(content: bytes, source: str, district: str | None) -> list[dict]:
    """Preserve polygon holes and explicit classes; fail on missing geometry."""
    root = ET.fromstring(content)
    rows = []
    for index, placemark in enumerate(root.findall(".//{*}Placemark")):
        label = placemark.findtext("{*}name")
        if not label:
            raise ValueError(f"Unlabeled placemark in {source}")
        polygons = placemark.findall(".//{*}Polygon")
        if not polygons:
            raise ValueError(f"Placemark without polygon: {source}:{index}")
        for part, polygon in enumerate(polygons):
            outer = polygon.findtext("{*}outerBoundaryIs/{*}LinearRing/{*}coordinates")
            if not outer:
                raise ValueError(f"Missing exterior ring: {source}:{index}")
            holes = [coordinates(r.text or "") for r in polygon.findall("{*}innerBoundaryIs/{*}LinearRing/{*}coordinates")]
            original = Polygon(coordinates(outer), holes)
            geometry = make_valid(original)
            if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError(f"Invalid polygon after repair: {source}:{index}:{part}")
            rows.append({"source": source, "source_polygon_id": f"{source}:{index}",
                         "part": part, "district": district, "source_label": label,
                         "geometry_repaired": not original.is_valid, "geometry": geometry})
    return rows


def prepare(root: Path) -> dict:
    rows = []
    districts = set()
    with zipfile.ZipFile(root / "raw/ksdma_flood.zip") as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith(".kmz"):
                continue
            district = Path(name).stem.title().replace("Kasargod", "Kasaragod")
            districts.add(district)
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as kmz:
                kml_names = [n for n in kmz.namelist() if n.lower().endswith(".kml")]
                if len(kml_names) != 1:
                    raise ValueError(f"Expected exactly one KML inside {name}")
                rows.extend(parse_kml(kmz.read(kml_names[0]), f"flood/{district}", district))
    if districts != set(DISTRICTS):
        raise ValueError(f"Unexpected district coverage: {districts}")
    # macOS bsdtar supports this RAR; only one named member goes to stdout.
    result = subprocess.run(["tar", "-xOf", str(root / "raw/ksdma_landslide.rar"), "doc.kml"],
                            check=True, capture_output=True, timeout=120)
    rows.extend(parse_kml(result.stdout, "landslide/kerala", None))
    frame = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    out = root / "processed"
    out.mkdir(parents=True, exist_ok=True)
    frame.to_file(out / "hazards.gpkg", layer="hazards", driver="GPKG")
    summary = {"polygon_parts": len(frame), "source_placemarks": frame.source_polygon_id.nunique(),
               "districts_with_flood_layers": sorted(districts),
               "classes": frame.groupby(["source", "source_label"]).size().rename("parts").reset_index().to_dict("records"),
               "repaired_parts": int(frame.geometry_repaired.sum()),
               "warning": "No intersection means unmapped/unknown, never safe. Landslide districts have not been spatially joined."}
    (root / "inventory.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def lookup(path: Path, lon: float, lat: float) -> dict:
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("Invalid coordinates")
    frame = gpd.read_file(path, layer="hazards", bbox=(lon, lat, lon, lat))
    point = Point(lon, lat)
    hits = frame[frame.geometry.intersects(point)]
    records = hits.drop(columns="geometry").to_dict("records")
    return {"longitude": lon, "latitude": lat, "mapped_evidence": records,
            "assessment": "Historical mapped hazard present" if records else "Unknown: no mapped polygon at this point",
            "construction_suitability": None,
            "kerala_boundary_verified": False,
            "limitations": ["Historical reference layers only", "No parcel boundary, soil bearing test, or legal assessment", "Absence from hazard polygons is not evidence of safety"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["download", "prepare", "lookup"])
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--lon", type=float)
    parser.add_argument("--lat", type=float)
    args = parser.parse_args()
    if args.command == "download":
        download(args.data_dir)
    elif args.command == "prepare":
        print(json.dumps(prepare(args.data_dir), indent=2))
    else:
        if args.lon is None or args.lat is None:
            parser.error("lookup requires --lon and --lat")
        print(json.dumps(lookup(args.data_dir / "processed/hazards.gpkg", args.lon, args.lat), indent=2))


if __name__ == "__main__":
    main()
