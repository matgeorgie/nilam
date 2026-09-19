"""Extract OSM boundaries, facilities, roads, and power-line geometry.

OSM completeness is unknown. Distances are straight-line, not route distances.
Run from the repository root. The large PBF is never copied into Git.
"""
import argparse
import json
from pathlib import Path
import osmium
import geopandas as gpd
from shapely import wkb, make_valid
from shapely.geometry import Point
from kerala_land_lab.data import DISTRICTS

p = argparse.ArgumentParser()
p.add_argument("pbf", type=Path)
p.add_argument("--out", type=Path, default=Path("data/processed"))
args = p.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
factory = osmium.geom.WKBFactory()
boundaries, facilities, roads, power_lines = [], [], [], []
road_types = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"}
major_road_types = {"motorway", "trunk", "primary"}


def facility_kind(tags):
    amenity = tags.get("amenity")
    if amenity in {"hospital", "clinic", "doctors"}:
        return "hospital"
    if amenity in {"school", "college", "kindergarten"}:
        return "school"
    if amenity == "pharmacy":
        return "pharmacy"
    if amenity == "bank":
        return "bank"
    if amenity in {"waste_transfer_station", "waste_disposal", "recycling"}:
        return "waste_facility"
    if tags.get("shop"):
        return "shop"
    if tags.get("highway") == "bus_stop" or tags.get("public_transport") in {"platform", "station"}:
        return "bus_stop"
    if tags.get("railway") in {"station", "halt"}:
        return "railway_station"
    if tags.get("leisure") in {"park", "garden"}:
        return "park"
    if tags.get("landuse") == "quarry":
        return "quarry"
    if tags.get("landuse") == "industrial":
        return "industrial"
    if tags.get("landuse") == "landfill":
        return "waste_facility"
    return None


processor = (osmium.FileProcessor(str(args.pbf)).with_locations()
             .with_areas()
             .with_filter(osmium.filter.KeyFilter("boundary", "amenity", "highway", "shop", "landuse", "leisure", "power", "railway", "public_transport")))
skipped = 0
for obj in processor:
    tags = obj.tags
    if obj.is_area() and tags.get("boundary") == "administrative" and tags.get("admin_level") in {"4", "5"}:
        geometry = make_valid(wkb.loads(factory.create_multipolygon(obj), hex=True))
        boundaries.append({"name": tags.get("name:en", tags.get("name", "")), "level": tags.get("admin_level"), "osm_id": int(obj.orig_id()), "geometry": geometry})
    elif obj.is_area():
        kind = facility_kind(tags)
        if kind:
            try:
                geometry = make_valid(wkb.loads(factory.create_multipolygon(obj), hex=True))
                facilities.append({"kind": kind, "name": tags.get("name", "Unnamed mapped feature"), "osm_id": int(obj.orig_id()), "geometry": geometry})
            except (RuntimeError, ValueError):
                skipped += 1
    elif obj.is_node() and obj.location.valid():
        kind = facility_kind(tags)
        if kind and 74.8 <= obj.location.lon <= 77.5 and 8.1 <= obj.location.lat <= 12.9:
            facilities.append({"kind": kind, "name": tags.get("name", "Unnamed mapped feature"), "osm_id": int(obj.id), "geometry": Point(obj.location.lon, obj.location.lat)})
    elif obj.is_way() and tags.get("highway") in road_types:
        try:
            if not obj.nodes or not obj.nodes[0].location.valid():
                skipped += 1
                continue
            location = obj.nodes[0].location
            if not (74.8 <= location.lon <= 77.5 and 8.1 <= location.lat <= 12.9):
                continue
            geometry = wkb.loads(factory.create_linestring(obj), hex=True)
            kind = tags.get("highway")
            roads.append({"kind": kind, "major": kind in major_road_types, "access": tags.get("access", "unknown"), "osm_id": int(obj.id), "geometry": geometry})
        except (RuntimeError, ValueError):
            skipped += 1
    elif obj.is_way() and tags.get("power") in {"line", "minor_line"}:
        try:
            geometry = wkb.loads(factory.create_linestring(obj), hex=True)
            power_lines.append({"kind": tags.get("power"), "osm_id": int(obj.id), "geometry": geometry})
        except (RuntimeError, ValueError):
            skipped += 1
print("OSM parsed",len(boundaries),len(facilities),len(roads),len(power_lines),flush=True)
boundary = gpd.GeoDataFrame(boundaries, crs=4326)
state = boundary[(boundary.name == "Kerala") & (boundary.level == "4")]
if len(state) != 1:
    raise RuntimeError("Expected one complete Kerala state boundary")
region = state.geometry.iloc[0]
districts = boundary[(boundary.level == "5") & boundary.geometry.representative_point().within(region)].copy()
rejected_names = districts.loc[~districts.name.isin(DISTRICTS), "name"].tolist()
districts = districts[districts.name.isin(DISTRICTS)]
if len(districts) != 14:
    raise RuntimeError(f"Expected 14 Kerala districts, found {len(districts)}: {districts.name.tolist()}")
state.to_file(args.out / "kerala.geojson", driver="GeoJSON")
districts.to_file(args.out / "districts.geojson", driver="GeoJSON")
for name, rows in [("facilities", facilities), ("roads", roads), ("power_lines", power_lines)]:
    frame = gpd.GeoDataFrame(rows, crs=4326)
    frame = frame[frame.geometry.intersects(region)]
    frame.to_file(args.out / f"{name}.gpkg", layer=name, driver="GPKG")
    print(name,len(frame),flush=True)
# Preserve the API's narrower, backwards-compatible point-amenity layer.
amenities = gpd.GeoDataFrame(
    [row for row in facilities if row["kind"] in {"hospital", "pharmacy", "school", "shop", "bank"} and row["geometry"].geom_type == "Point"],
    crs=4326,
)
amenities = amenities[amenities.geometry.intersects(region)]
amenities.to_file(args.out / "amenities.gpkg", layer="amenities", driver="GPKG")
(args.out / "osm-metadata.json").write_text(json.dumps({"pbf": args.pbf.name, "bytes": args.pbf.stat().st_size, "districts": districts.name.tolist(), "rejected_district_level_names": rejected_names, "skipped_geometries": skipped, "license": "OpenStreetMap ODbL 1.0; attribution required", "facility_coverage": "Nodes and mapped polygons are included; OpenStreetMap completeness varies by category and district", "road_access": "Mapped geometry does not establish legal vehicle access"},indent=2))
