"""Local preference interpretation and decision routing for Nilam.

Laya is the production semantic decision engine. GLiNER2.5-Decide is an
optional research comparator. Exact quantities are always parsed and confirmed
deterministically rather than delegated to either classifier.
"""
from __future__ import annotations

from functools import lru_cache
import os
import re
from typing import Any


INTENTS = {
    "find_land": "find promising land matching stated requirements",
    "check_site": "assess one selected location",
    "compare_candidates": "compare two or more candidate locations",
    "explain_result": "explain an existing suitability result",
    "expert_help": "identify which professional review is needed",
}


def _distance_km(text: str, words: tuple[str, ...]) -> float | None:
    targets = "|".join(re.escape(word) for word in words)
    patterns = [
        rf"(?:within|under|less than|max(?:imum)?|no more than)\s+(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|m|met(?:er|re)s?)?\s+(?:of|from)?\s*(?:a|the)?\s*(?:{targets})",
        rf"(?:{targets})\s+(?:must\s+be\s+|should\s+be\s+)?(?:within|under|less than|max(?:imum)?|no more than)\s+(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|m|met(?:er|re)s?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            value = float(match.group(1))
            unit = (match.group(2) or "km").lower()
            is_metres = unit == "m" or unit.startswith("met")
            return round(value / 1000 if is_metres else value, 3)
    return None


def deterministic_preferences(text: str) -> dict[str, Any]:
    """Extract explicit, reviewable values without inventing unstated limits."""

    lower = text.lower()
    slope = re.search(r"(?:slope|gradient)[^\d]{0,18}(\d+(?:\.\d+)?)\s*(?:°|degrees?)", lower)
    requirements: dict[str, Any] = {
        "avoid_high_flood": any(term in lower for term in ("low flood", "avoid flood", "flood safe", "no flooding")),
        "avoid_high_landslide": any(term in lower for term in ("avoid landslide", "low landslide", "stable slope")),
        "prefer_quiet": any(term in lower for term in ("quiet", "peaceful", "away from industry", "low noise")),
        "prefer_green": any(term in lower for term in ("green", "vegetation", "nature", "trees")),
        "prefer_transit": any(term in lower for term in ("public transport", "bus", "railway", "train")),
        "prefer_open_land": any(term in lower for term in ("open land", "clear land", "vacant", "empty plot")),
    }
    if slope:
        requirements["max_slope"] = float(slope.group(1))
    distance_terms = {
        "max_hospital_km": ("hospital", "clinic"),
        "max_school_km": ("school", "college"),
        "max_road_km": ("road", "highway"),
        "max_transit_km": ("bus stop", "railway", "train station", "public transport"),
    }
    for key, terms in distance_terms.items():
        value = _distance_km(lower, terms)
        if value is not None:
            requirements[key] = value
    return requirements


@lru_cache(maxsize=1)
def _laya_router():
    if os.environ.get("NILAM_ENABLE_LAYA", "1") != "1":
        return None
    try:
        from laya import Router
    except ImportError:
        return None
    return Router(preload=False, max_loaded=1)


@lru_cache(maxsize=1)
def _gliner_model():
    if os.environ.get("NILAM_ENABLE_GLINER", "0") != "1":
        return None
    try:
        from gliner2 import GLiNER2
    except ImportError:
        return None
    return GLiNER2.from_pretrained("fastino/GLiNER2.5-Decide")


def interpret_request(text: str) -> dict[str, Any]:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return {"text": "", "requirements": {}, "semantic": {"engine": "deterministic", "needs_confirmation": True}}
    requirements = deterministic_preferences(cleaned)
    semantic: dict[str, Any] = {
        "engine": "deterministic",
        "intent": "find_land",
        "risk_tolerance": "safety_first",
        "needs_confirmation": True,
    }
    router = _laya_router()
    if router is not None:
        questions = {
            "intent": {"type": "choice", "instructions": "What Nilam workflow does this request need?", "criteria": INTENTS},
            "risk_tolerance": {"type": "choice", "instructions": "How should environmental uncertainty be treated?", "criteria": {
                "safety_first": "reject strong hazards and preserve conservative safeguards",
                "balanced": "balance access preferences after safety safeguards",
                "unclear": "the request does not state a usable risk preference",
            }},
            "needs_expert": {"type": "noul", "instructions": "Does this request explicitly need engineering, legal, flood, or geotechnical review?"},
        }
        try:
            result = router.predict({"request": cleaned}, questions, model="typed-decisions")
            answers = result.get("answers", {})
            semantic.update({
                "engine": "laya",
                "intent": answers.get("intent", {}).get("choice", "find_land"),
                "risk_tolerance": answers.get("risk_tolerance", {}).get("choice", "safety_first"),
                "needs_expert": answers.get("needs_expert", {}).get("noul", 0),
                "confidence": min((answer.get("confidence", 0) for answer in answers.values()), default=0),
                "routing": result.get("routing", {}),
            })
        except Exception as exc:
            semantic["fallback_reason"] = type(exc).__name__
    comparator = _gliner_model()
    if comparator is not None:
        try:
            semantic["gliner_comparison"] = comparator.classify_text(cleaned, {"intent": list(INTENTS)})
        except Exception as exc:
            semantic["gliner_error"] = type(exc).__name__
    return {"text": cleaned, "requirements": requirements, "semantic": semantic}


def semantic_status() -> dict[str, Any]:
    import importlib.util

    return {
        "laya_installed": importlib.util.find_spec("laya") is not None,
        "laya_enabled": os.environ.get("NILAM_ENABLE_LAYA", "1") == "1",
        "gliner_installed": importlib.util.find_spec("gliner2") is not None,
        "gliner_enabled": os.environ.get("NILAM_ENABLE_GLINER", "0") == "1",
        "voice_model": "distil-whisper/distil-small.en",
    }
