"""Local pairwise learning for candidate preference, after Nilam's hard site screens.

The learned adjustment describes aggregate taste. It never changes the eligibility
mask or the unadjusted public-data model score.
"""
from __future__ import annotations

from itertools import combinations
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
import hashlib
import json
import math
import secrets
import sqlite3
import time
import uuid

import numpy as np


FEATURES = (
    "flat_ground", "open_ground", "hospital_access", "school_access",
    "road_access", "park_access", "shop_access", "greenery", "quiet_surroundings",
)
MAX_ADJUSTMENT_POINTS = 10.0
HOLDOUT_FRACTION = 0.2


def _fraction(value: object, fallback: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return float(np.clip(number, 0.0, 1.0)) if math.isfinite(number) else fallback


def _percent(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return float(np.clip(number / 100, 0, 1)) if math.isfinite(number) else 0.5


def _near(distance: object, radius_m: float) -> float:
    try:
        number = float(distance)
    except (TypeError, ValueError):
        return 0.5
    return float(np.clip(1 - number / radius_m, 0, 1)) if math.isfinite(number) else 0.5


def candidate_features(candidate: dict) -> np.ndarray:
    """Stable, bounded site attributes available in every saved search snapshot."""
    evidence = candidate.get("evidence") or {}
    quiet = (_fraction_distance(evidence.get("industrial_distance_m"), 4000)
             + _fraction_distance(evidence.get("quarry_distance_m"), 4000)) / 2
    return np.asarray([
        _percent(candidate.get("flat_land_percent")),
        _percent(candidate.get("open_land_percent")),
        _near(evidence.get("hospital_distance_m"), 8000),
        _near(evidence.get("school_distance_m"), 6000),
        _near(evidence.get("road_distance_m"), 1800),
        _near(evidence.get("park_distance_m"), 5000),
        _near(evidence.get("shop_distance_m"), 4000),
        _fraction(evidence.get("ndvi")),
        quiet,
    ], dtype=np.float64)


def _fraction_distance(distance: object, radius_m: float) -> float:
    try:
        number = float(distance)
    except (TypeError, ValueError):
        return 0.5
    return float(np.clip(number / radius_m, 0, 1)) if math.isfinite(number) else 0.5


def win_probability(left: dict, right: dict, weights: np.ndarray) -> float:
    margin = float(np.dot(weights, candidate_features(left) - candidate_features(right)))
    return 1 / (1 + math.exp(-float(np.clip(margin, -30, 30))))


def update_weights(weights: np.ndarray, left: dict, right: dict, choice: str, vote_count: int) -> np.ndarray:
    if choice not in {"left", "right", "tie"}:
        return weights.copy()
    target = {"left": 1.0, "right": 0.0, "tie": 0.5}[choice]
    delta = candidate_features(left) - candidate_features(right)
    probability = win_probability(left, right, weights)
    rate = 0.8 / math.sqrt(1 + vote_count / 25)
    return np.clip(weights + rate * ((target - probability) * delta - 0.01 * weights), -3, 3)


def preference_adjustment(candidate: dict, weights: np.ndarray) -> float:
    centered = candidate_features(candidate) - 0.5
    margin = float(np.dot(weights, centered))
    preference = 1 / (1 + math.exp(-float(np.clip(margin, -30, 30))))
    return MAX_ADJUSTMENT_POINTS * (2 * preference - 1)


def rerank_candidates(candidates: list[dict], weights: np.ndarray, vote_count: int, limit: int) -> list[dict]:
    ranked = []
    for source in candidates:
        item = dict(source)
        base = float(item.get("original_suitability_percent", item["suitability_percent"]))
        static_fit = float(item.get("static_overall_fit_percent", item["overall_fit_percent"]))
        adjustment = preference_adjustment(item, weights) if vote_count else 0.0
        item["original_suitability_percent"] = round(base, 1)
        item["static_overall_fit_percent"] = round(static_fit, 1)
        item["preference_adjustment_points"] = round(adjustment, 1)
        item["community_preference_percent"] = round(50 + adjustment * 5, 1)
        item["community_votes"] = vote_count
        item["suitability_percent"] = round(float(np.clip(base + adjustment, 0, 100)), 1)
        item["overall_fit_percent"] = round(float(np.clip(static_fit + adjustment, 0, 100)), 1)
        ranked.append(item)
    if vote_count:
        ranked.sort(key=lambda item: (item["overall_fit_percent"], item["original_suitability_percent"]), reverse=True)
    for rank, item in enumerate(ranked[:limit], 1):
        item["rank"] = rank
    return ranked[:limit]


def _site_key(candidate: dict) -> str:
    return f"{float(candidate['lat']):.4f},{float(candidate['lon']):.4f}"


def _pair_key(left: dict, right: dict) -> str:
    return "|".join(sorted((_site_key(left), _site_key(right))))


def _holdout(pair_key: str) -> bool:
    # Keep repeat exposures of the same geographic pair in one evaluation split.
    return int(hashlib.sha256(pair_key.encode()).hexdigest()[:8], 16) / 16**8 < HOLDOUT_FRACTION


class PreferenceStore:
    """SQLite feedback log plus online Bradley-Terry style shared weights."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS model_state (
                    name TEXT PRIMARY KEY, weights_json TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0, votes INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS searches (
                    id TEXT PRIMARY KEY, created_at REAL NOT NULL,
                    candidates_json TEXT NOT NULL, result_limit INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exposures (
                    id TEXT PRIMARY KEY, search_id TEXT NOT NULL, browser_id TEXT NOT NULL,
                    pair_key TEXT NOT NULL, left_json TEXT NOT NULL, right_json TEXT NOT NULL,
                    model_version INTEGER NOT NULL, propensity REAL NOT NULL,
                    left_order_propensity REAL NOT NULL, created_at REAL NOT NULL,
                    split TEXT NOT NULL, choice TEXT, chosen_at REAL
                );
                CREATE INDEX IF NOT EXISTS exposures_browser_pair ON exposures(browser_id,pair_key);
                CREATE INDEX IF NOT EXISTS exposures_split ON exposures(split,choice);
            """)
            for name in ("live", "evaluation_train"):
                db.execute("INSERT OR IGNORE INTO model_state VALUES(?,?,0,0)",
                           (name, json.dumps([0.0] * len(FEATURES))))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _state(db: sqlite3.Connection, name: str = "live") -> tuple[np.ndarray, int, int]:
        row = db.execute("SELECT weights_json,version,votes FROM model_state WHERE name=?", (name,)).fetchone()
        return np.asarray(json.loads(row["weights_json"]), dtype=np.float64), row["version"], row["votes"]

    def status(self) -> dict:
        with self.lock, self._connect() as db:
            _, version, votes = self._state(db)
            return {"model_version": version, "votes": votes, "features": list(FEATURES),
                    "max_adjustment_points": MAX_ADJUSTMENT_POINTS}

    def save_search(self, candidates: list[dict], result_limit: int) -> tuple[str, list[dict]]:
        search_id = uuid.uuid4().hex
        with self.lock, self._connect() as db:
            db.execute("INSERT INTO searches VALUES(?,?,?,?)",
                       (search_id, time.time(), json.dumps(candidates, allow_nan=False), result_limit))
            weights, _, votes = self._state(db)
        return search_id, rerank_candidates(candidates, weights, votes, result_limit)

    def _search(self, db: sqlite3.Connection, search_id: str) -> tuple[list[dict], int] | None:
        row = db.execute("SELECT candidates_json,result_limit FROM searches WHERE id=?", (search_id,)).fetchone()
        return (json.loads(row["candidates_json"]), row["result_limit"]) if row else None

    def create_pair(self, search_id: str, browser_id: str) -> dict | None:
        with self.lock, self._connect() as db:
            saved = self._search(db, search_id)
            if saved is None:
                raise KeyError("Search expired or was not found")
            candidates, _ = saved
            weights, version, votes = self._state(db)
            pool = rerank_candidates(candidates, weights, votes, min(12, len(candidates)))
            competitive = [site for site in pool if site["original_suitability_percent"] >= 50]
            if len(competitive) >= 2:
                pool = competitive
            seen = {row[0] for row in db.execute("SELECT pair_key FROM exposures WHERE browser_id=?", (browser_id,))}
            pairs = [(a, b) for a, b in combinations(pool, 2) if _pair_key(a, b) not in seen]
            if not pairs:
                return None
            close_pairs = [(a, b) for a, b in pairs if abs(a["static_overall_fit_percent"] - b["static_overall_fit_percent"]) <= 20]
            if close_pairs:
                pairs = close_pairs
            desirability = []
            for left, right in pairs:
                uncertainty = 1 - 2 * abs(win_probability(left, right, weights) - 0.5)
                contrast = min(float(np.linalg.norm(candidate_features(left) - candidate_features(right))), 1)
                desirability.append(0.2 + uncertainty * (0.3 + contrast))
            probabilities = np.asarray(desirability) / sum(desirability)
            index = secrets.SystemRandom().choices(range(len(pairs)), weights=probabilities, k=1)[0]
            left, right = pairs[index]
            if secrets.randbelow(2):
                left, right = right, left
            pair_id = uuid.uuid4().hex
            split = "holdout" if _holdout(_pair_key(left, right)) else "train"
            db.execute("""INSERT INTO exposures
                (id,search_id,browser_id,pair_key,left_json,right_json,model_version,
                 propensity,left_order_propensity,created_at,split)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (pair_id, search_id, browser_id, _pair_key(left, right), json.dumps(left),
                 json.dumps(right), version, float(probabilities[index]), 0.5, time.time(), split))
            return {"pair_id": pair_id, "left": left, "right": right,
                    "model_version": version, "community_votes": votes}

    def vote(self, pair_id: str, browser_id: str, choice: str) -> dict:
        if choice not in {"left", "right", "tie", "skip"}:
            raise ValueError("Choice must be left, right, tie or skip")
        with self.lock, self._connect() as db:
            exposure = db.execute("SELECT * FROM exposures WHERE id=?", (pair_id,)).fetchone()
            if exposure is None or exposure["browser_id"] != browser_id:
                raise KeyError("Comparison not found for this browser")
            if exposure["choice"] is not None:
                raise ValueError("This comparison was already answered")
            left, right = json.loads(exposure["left_json"]), json.loads(exposure["right_json"])
            db.execute("UPDATE exposures SET choice=?,chosen_at=? WHERE id=?", (choice, time.time(), pair_id))
            if choice != "skip":
                names = ["live"] + (["evaluation_train"] if exposure["split"] == "train" else [])
                for name in names:
                    weights, version, votes = self._state(db, name)
                    updated = update_weights(weights, left, right, choice, votes)
                    db.execute("UPDATE model_state SET weights_json=?,version=?,votes=? WHERE name=?",
                               (json.dumps(updated.tolist()), version + 1, votes + 1, name))
            saved = self._search(db, exposure["search_id"])
            weights, version, votes = self._state(db)
            candidates = rerank_candidates(saved[0], weights, votes, saved[1]) if saved else []
            return {"choice": choice, "model_version": version, "community_votes": votes,
                    "candidates": candidates, "evaluation": self._evaluate(db)}

    def evaluation(self) -> dict:
        with self.lock, self._connect() as db:
            return self._evaluate(db)

    def _evaluate(self, db: sqlite3.Connection) -> dict:
        weights, version, train_votes = self._state(db, "evaluation_train")
        rows = db.execute("SELECT left_json,right_json,choice FROM exposures WHERE split='holdout' AND choice IN ('left','right','tie')").fetchall()
        outcomes, learned, static = [], [], []
        for row in rows:
            left, right = json.loads(row["left_json"]), json.loads(row["right_json"])
            outcomes.append({"left": 1.0, "right": 0.0, "tie": 0.5}[row["choice"]])
            learned.append(win_probability(left, right, weights))
            delta = (float(left["static_overall_fit_percent"]) - float(right["static_overall_fit_percent"])) / 15
            static.append(1 / (1 + math.exp(-float(np.clip(delta, -30, 30)))))
        total = db.execute("SELECT COUNT(*) FROM exposures WHERE choice IN ('left','right','tie')").fetchone()[0]
        strict = [i for i, outcome in enumerate(outcomes) if outcome != 0.5]
        def metrics(predicted: list[float]) -> dict:
            if not outcomes:
                return {"pairwise_accuracy": None, "log_loss": None, "brier": None}
            actual = np.asarray(outcomes)
            probability = np.clip(np.asarray(predicted), 1e-7, 1 - 1e-7)
            return {
                "pairwise_accuracy": round(float(np.mean((probability[strict] > 0.5) == (actual[strict] > 0.5))), 3) if strict else None,
                "log_loss": round(float(np.mean(-actual * np.log(probability) - (1 - actual) * np.log(1 - probability))), 3),
                "brier": round(float(np.mean((probability - actual) ** 2)), 3),
            }
        return {"human_votes": total, "training_votes": train_votes, "holdout_votes": len(rows),
                "heldout_strict_choices": len(strict), "evaluation_model_version": version,
                "learned": metrics(learned), "static_ranking": metrics(static),
                "meaning": "Held-out pair choices are excluded from the evaluation model, while the live shared model learns from every vote. Compare only after enough real votes."}
