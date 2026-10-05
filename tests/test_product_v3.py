import numpy as np
import pandas as pd

from kerala_land_lab.fusion import FusionConfig, combine_probabilities
from kerala_land_lab.search import candidate_grid, rank_candidates
from kerala_land_lab.semantic import deterministic_preferences


def test_fusion_is_normalized_and_respects_calibrated_weight():
    tabpfn = np.array([[0.05, 0.10, 0.25, 0.60]], dtype=np.float32)
    terramind = np.array([[0.60, 0.20, 0.15, 0.05]], dtype=np.float32)
    fused, weights = combine_probabilities(
        tabpfn,
        terramind,
        FusionConfig(agree_vision_weight=0.08, disagree_vision_weight=0.08),
    )
    assert np.allclose(fused.sum(axis=1), 1)
    assert np.allclose(weights, [0.08])
    assert np.argmax(fused[0]) == 3


def test_semantic_parser_preserves_explicit_metric_distances():
    result = deterministic_preferences(
        "Find quiet green land with a hospital within 2500 metres and school under 4 km."
    )
    assert result["max_hospital_km"] == 2.5
    assert result["max_school_km"] == 4
    assert result["prefer_quiet"] is True
    assert result["prefer_green"] is True
    assert result["prefer_hospital"] is True
    assert result["prefer_school"] is True


def test_unstated_preferences_do_not_disable_default_safety_screens():
    result = deterministic_preferences("Near a hospital")
    assert result == {"prefer_hospital": True}


def test_candidate_grid_is_fresh_and_stays_inside_the_selected_circle():
    first = candidate_grid(10.5, 76.2, 3, max_points=180)
    second = candidate_grid(10.7, 76.4, 3, max_points=180)
    assert 150 <= len(first) <= 190
    assert first.search_distance_km.max() <= 3
    assert not np.allclose(first[["lat", "lng"]], second[["lat", "lng"]])
    assert first.cell_size_m.nunique() == 1


def test_candidate_ranking_never_relaxes_safety_filters():
    rows = pd.DataFrame(
        [
            {
                "point_id": "safe",
                "lat": 10.0,
                "lng": 76.0,
                "district": "Thrissur",
                "land_cover_class": 5,
                "slope": 5,
                "flood_level_100yr_m": 0,
                "gsi_landslide_susceptibility": "Low",
                "dist_nearest_hospital": 2000,
                "dist_nearest_school": 1000,
                "dist_nearest_road": 300,
                "dist_nearest_bus_stop": 700,
                "dist_nearest_industrial": 5000,
                "dist_nearest_quarry": 5000,
                "ndvi": 0.6,
            },
            {
                "point_id": "flooded",
                "lat": 10.1,
                "lng": 76.1,
                "district": "Thrissur",
                "land_cover_class": 5,
                "slope": 2,
                "flood_level_100yr_m": 2.2,
                "gsi_landslide_susceptibility": "Low",
                "dist_nearest_hospital": 100,
                "dist_nearest_school": 100,
                "dist_nearest_road": 100,
                "dist_nearest_bus_stop": 100,
                "dist_nearest_industrial": 5000,
                "dist_nearest_quarry": 5000,
                "ndvi": 0.8,
            },
        ]
    )
    candidates = rank_candidates(rows, np.array([72, 98]), {}, limit=10)
    assert [candidate["point_id"] for candidate in candidates] == ["safe"]


def test_open_land_request_is_a_filter_not_a_tradeoff():
    rows = pd.DataFrame(
        [
            {"point_id": "open", "lat": 10.0, "lng": 76.0, "district": "Thrissur", "land_cover_class": 5, "slope": 5, "flood_level_100yr_m": 0, "gsi_landslide_susceptibility": "Low", "dist_nearest_hospital": 2000, "dist_nearest_school": 1000, "dist_nearest_road": 300, "dist_nearest_bus_stop": 700, "dist_nearest_industrial": 5000, "dist_nearest_quarry": 5000, "ndvi": 0.5},
            {"point_id": "built", "lat": 10.1, "lng": 76.1, "district": "Thrissur", "land_cover_class": 6, "slope": 3, "flood_level_100yr_m": 0, "gsi_landslide_susceptibility": "Low", "dist_nearest_hospital": 100, "dist_nearest_school": 100, "dist_nearest_road": 100, "dist_nearest_bus_stop": 100, "dist_nearest_industrial": 5000, "dist_nearest_quarry": 5000, "ndvi": 0.2},
        ]
    )
    candidates = rank_candidates(rows, np.array([70, 99]), {"prefer_open_land": True})
    assert [candidate["point_id"] for candidate in candidates] == ["open"]


def test_preferences_change_the_ranking_inside_the_same_search_area():
    common = {
        "district": "Thrissur", "land_cover_class": 5, "slope": 5,
        "flood_level_100yr_m": 0, "gsi_landslide_susceptibility": "Low",
        "dist_nearest_school": 1500, "dist_nearest_road": 300,
        "dist_nearest_bus_stop": 700, "dist_nearest_quarry": 5000,
        "ndvi": .5, "built_probability": .05, "building_distance_m": 100,
    }
    rows = pd.DataFrame([
        {**common, "point_id": "hospital", "lat": 10.0, "lng": 76.0,
         "dist_nearest_hospital": 200, "dist_nearest_industrial": 1000},
        {**common, "point_id": "quiet", "lat": 10.1, "lng": 76.1,
         "dist_nearest_hospital": 7000, "dist_nearest_industrial": 8000},
    ])
    suitability = np.array([75, 75])
    hospital_first = rank_candidates(rows, suitability, {"prefer_hospital": True})
    quiet_first = rank_candidates(rows, suitability, {"prefer_quiet": True})
    assert hospital_first[0]["point_id"] == "hospital"
    assert quiet_first[0]["point_id"] == "quiet"


def test_tree_cover_needs_a_neighbourhood_open_land_signal():
    rows = pd.DataFrame([{
        "point_id": "tree-covered", "lat": 10.0, "lng": 76.0, "district": "Thrissur",
        "land_cover_class": 1, "slope": 5, "flood_level_100yr_m": 0,
        "gsi_landslide_susceptibility": "Low", "dist_nearest_hospital": 2000,
        "dist_nearest_school": 1000, "dist_nearest_road": 300,
        "dist_nearest_bus_stop": 700, "dist_nearest_industrial": 5000,
        "dist_nearest_quarry": 5000, "ndvi": .7, "built_probability": .05,
        "building_distance_m": 80, "open_probability_45m": .25,
    }])
    candidates = rank_candidates(rows, np.array([75]), {"prefer_open_land": True})
    assert candidates[0]["point_id"] == "tree-covered"
    assert candidates[0]["apparently_open"] is False


def test_dense_tree_cover_is_not_reported_as_open_land():
    rows = pd.DataFrame([{
        "point_id": "dense-tree", "lat": 10.0, "lng": 76.0, "district": "Thrissur",
        "land_cover_class": 1, "slope": 5, "flood_level_100yr_m": 0,
        "gsi_landslide_susceptibility": "Low", "dist_nearest_hospital": 2000,
        "dist_nearest_school": 1000, "dist_nearest_road": 300,
        "dist_nearest_bus_stop": 700, "dist_nearest_industrial": 5000,
        "dist_nearest_quarry": 5000, "ndvi": .8, "built_probability": .02,
        "built_probability_45m": .02, "open_probability_45m": .04,
        "building_distance_m": 500,
    }])
    assert rank_candidates(rows, np.array([90]), {"prefer_open_land": True}) == []


def test_flat_point_is_rejected_when_the_surrounding_cell_is_steep():
    common = {
        "lat": 10.0, "lng": 76.0, "district": "Thrissur", "land_cover_class": 5,
        "slope": 3, "flood_level_100yr_m": 0, "gsi_landslide_susceptibility": "Low",
        "dist_nearest_hospital": 2000, "dist_nearest_school": 1000,
        "dist_nearest_road": 300, "dist_nearest_bus_stop": 700,
        "dist_nearest_industrial": 5000, "dist_nearest_quarry": 5000,
        "ndvi": .5, "built_probability": .03, "built_probability_45m": .04,
        "open_probability_45m": .35, "building_distance_m": 100,
    }
    rows = pd.DataFrame([
        # One steep edge pixel is tolerated when 90% of the sampled cell is flat.
        {**common, "point_id": "flat", "slope_mean_45m": 3, "slope_max_45m": 16, "slope_p90_45m": 6, "elevation_stddev_45m": 1.2},
        {**common, "point_id": "uneven", "lng": 76.01, "slope_mean_45m": 6, "slope_max_45m": 18, "slope_p90_45m": 14, "elevation_stddev_45m": 7},
    ])
    candidates = rank_candidates(rows, np.array([75, 95]), {"prefer_open_land": True})
    assert [candidate["point_id"] for candidate in candidates] == ["flat"]
    assert candidates[0]["flat_land_percent"] > 50
