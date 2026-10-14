import numpy as np
import pytest

from kerala_land_lab import preference_learning as learning


def candidate(lat, lon, flat, hospital_m, overall=75):
    return {
        "point_id": f"site-{lat}-{lon}", "lat": lat, "lon": lon,
        "district": "Thrissur", "rank": 1,
        "suitability_percent": 70, "overall_fit_percent": overall,
        "flat_land_percent": flat, "open_land_percent": 80,
        "evidence": {"hospital_distance_m": hospital_m, "school_distance_m": 2500,
                     "road_distance_m": 350, "park_distance_m": 2000,
                     "shop_distance_m": 1000, "industrial_distance_m": 4000,
                     "quarry_distance_m": 4000, "ndvi": 0.5},
    }


def test_real_pair_votes_update_only_the_preference_adjustment(tmp_path, monkeypatch):
    store = learning.PreferenceStore(tmp_path / "feedback.sqlite3")
    left = candidate(10.5, 76.2, 90, 500)
    right = candidate(10.6, 76.3, 35, 7500, overall=74)
    search_id, initial = store.save_search([left, right], 2)
    assert [item["point_id"] for item in initial] == [left["point_id"], right["point_id"]]
    assert all(item["preference_adjustment_points"] == 0 for item in initial)
    monkeypatch.setattr(learning, "_holdout", lambda _: False)
    pair = store.create_pair(search_id, "browser-123456789")
    assert pair and {pair["left"]["point_id"], pair["right"]["point_id"]} == {left["point_id"], right["point_id"]}
    choice = "left" if pair["left"]["point_id"] == left["point_id"] else "right"
    result = store.vote(pair["pair_id"], "browser-123456789", choice)
    assert result["community_votes"] == 1
    preferred = next(item for item in result["candidates"] if item["point_id"] == left["point_id"])
    other = next(item for item in result["candidates"] if item["point_id"] == right["point_id"])
    assert preferred["preference_adjustment_points"] > other["preference_adjustment_points"]
    assert preferred["original_suitability_percent"] == 70
    assert all(abs(item["preference_adjustment_points"]) <= 10 for item in result["candidates"])
    assert learning.PreferenceStore(store.path).status()["votes"] == 1
    with pytest.raises(ValueError, match="already answered"):
        store.vote(pair["pair_id"], "browser-123456789", choice)
    assert store.create_pair(search_id, "browser-123456789") is None


def test_heldout_vote_updates_live_model_but_not_evaluation_training(tmp_path, monkeypatch):
    store = learning.PreferenceStore(tmp_path / "feedback.sqlite3")
    sites = [candidate(10.5, 76.2, 90, 500), candidate(10.6, 76.3, 35, 7500)]
    search_id, _ = store.save_search(sites, 2)
    monkeypatch.setattr(learning, "_holdout", lambda _: True)
    pair = store.create_pair(search_id, "browser-123456789")
    result = store.vote(pair["pair_id"], "browser-123456789", "tie")
    assert result["community_votes"] == 1
    assert result["evaluation"]["training_votes"] == 0
    assert result["evaluation"]["holdout_votes"] == 1
    assert np.isfinite(result["evaluation"]["static_ranking"]["log_loss"])


def test_skipping_logs_exposure_without_changing_weights(tmp_path):
    store = learning.PreferenceStore(tmp_path / "feedback.sqlite3")
    search_id, _ = store.save_search([candidate(10.5, 76.2, 90, 500), candidate(10.6, 76.3, 35, 7500)], 2)
    pair = store.create_pair(search_id, "browser-123456789")
    result = store.vote(pair["pair_id"], "browser-123456789", "skip")
    assert result["community_votes"] == 0
    assert all(item["suitability_percent"] == 70 for item in result["candidates"])


def test_pair_prefers_competitive_screened_sites(tmp_path):
    store = learning.PreferenceStore(tmp_path / "feedback.sqlite3")
    stronger = candidate(10.5, 76.2, 90, 500, overall=82)
    similar = candidate(10.6, 76.3, 75, 900, overall=76)
    weak = candidate(10.7, 76.4, 20, 7500, overall=40)
    weak["suitability_percent"] = 30
    search_id, _ = store.save_search([stronger, similar, weak], 3)
    pair = store.create_pair(search_id, "browser-123456789")
    assert {pair["left"]["point_id"], pair["right"]["point_id"]} == {
        stronger["point_id"], similar["point_id"]
    }


def test_repeated_geographic_pair_keeps_same_evaluation_split(tmp_path):
    store = learning.PreferenceStore(tmp_path / "feedback.sqlite3")
    search_id, _ = store.save_search([candidate(10.5, 76.2, 90, 500), candidate(10.6, 76.3, 35, 7500)], 2)
    first = store.create_pair(search_id, "browser-first-123456")
    second = store.create_pair(search_id, "browser-second-123456")
    with store._connect() as db:
        rows = db.execute("SELECT split FROM exposures WHERE id IN (?,?)", (first["pair_id"], second["pair_id"])).fetchall()
    assert len({row["split"] for row in rows}) == 1
