import geopandas as gpd
from shapely.geometry import box

from kerala_land_lab.statewide import balanced_district_points, hazard_reference_label, terrain_zone


def test_balanced_district_sampling_is_exact_and_reproducible():
    districts = gpd.GeoDataFrame({"name": ["A", "B"]}, geometry=[box(76, 10, 76.1, 10.1), box(76.2, 10, 76.3, 10.1)], crs=4326)
    one = balanced_district_points(districts, 4, 7)
    two = balanced_district_points(districts, 4, 7)
    assert one.district.value_counts().to_dict() == {"A": 4, "B": 4}
    assert one[["lat", "lng"]].equals(two[["lat", "lng"]])


def test_unmapped_is_unlabeled_not_safe():
    label, confidence, basis = hazard_reference_label("Unmapped", "Unknown")
    assert label == "unlabeled"
    assert confidence == 0
    assert "not evidence of safety" in basis


def test_hazard_priority_and_terrain_zones():
    assert hazard_reference_label("Flood plain", "High")[0] == "high_hazard_reference"
    assert hazard_reference_label("Flood plain", "Unknown")[0] == "hazard_review_reference"
    assert [terrain_zone(v) for v in [10, 100, 500]] == ["lowland_0_20m", "midland_20_300m", "highland_above_300m"]
