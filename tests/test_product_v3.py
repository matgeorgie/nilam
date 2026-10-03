import numpy as np
import pandas as pd

from kerala_land_lab.fusion import FusionConfig, combine_probabilities
from kerala_land_lab.search import rank_candidates
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
