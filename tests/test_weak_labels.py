from kerala_land_lab.weak_labels import weak_label


def base_row():
    return {"land_cover_class": 6, "flood_reference": "Unmapped", "gsi_landslide_susceptibility": "Not mapped", "slope": 2, "terrain_ruggedness_index": 1, "annual_rainfall": 2500, "distance_to_water": 1000, "dist_nearest_quarry": 5000, "dist_nearest_waste_facility": 5000, "dist_nearest_industrial": 5000, "dist_nearest_power_line": 500, "dist_nearest_road": 50, "dist_nearest_hospital": 1000, "dist_nearest_school": 500, "dist_nearest_bus_stop": 200, "clay_content": 30, "elevation": 50, "mean_humidity": 80, "ndvi": .5, "soil_ph": 5.5, **{f"flood_level_{period}yr_m": 0 for period in (10, 25, 50, 100, 200, 500)}}


def test_low_concern_evidence_gets_higher_screening_label():
    result = weak_label(base_row())
    assert result["label"] == 3
    assert result["suitability_score"] == 100


def test_water_and_frequent_flood_screen_out():
    row = base_row(); row["land_cover_class"] = 0; row["flood_level_10yr_m"] = 2
    result = weak_label(row)
    assert result["label"] == 0
    assert result["penalty_hazard"] >= 95


def test_official_landslide_and_terrain_reduce_score():
    row = base_row(); row["gsi_landslide_susceptibility"] = "High"; row["slope"] = 35
    result = weak_label(row)
    assert result["suitability_score"] == 30
    assert result["label"] == 1
