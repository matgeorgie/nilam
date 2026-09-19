"""Add transparent, trainable public-data weak labels to the statewide table."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from kerala_land_lab.weak_labels import LABEL_NAMES, VERSION, weak_label

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data", type=Path, default=Path("data/processed/kerala_statewide_features.csv"))
parser.add_argument("--card", type=Path, default=Path("docs/statewide-dataset-card.json"))
args = parser.parse_args()

frame = pd.read_csv(args.data)
labels = pd.DataFrame([weak_label(row) for row in frame.to_dict("records")])
labels["label_basis"] = labels.label_basis.apply(json.dumps)
for column in labels:
    frame[column] = labels[column]
frame.to_csv(args.data, index=False, float_format="%.6f")

card = json.loads(args.card.read_text())
card.update({
    "rows": len(frame), "columns": frame.columns.tolist(), "sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
    "target_definition": "Four-class experimental public-data suitability screening target derived from the documented weak-label rules",
    "confidence_definition": "Evidence/completeness strength for the weak label; not a calibrated probability of safety",
    "hazard_reference_definition": "Separate direct-intersection label and confidence from the older KSDMA/NCESS polygons, retained for provenance",
    "training_target": "label", "training_target_names": LABEL_NAMES,
    "weak_label_version": VERSION, "weak_label_counts": frame.label_name.value_counts().to_dict(),
    "weak_label_warning": "Rule-derived public-data screening target; not expert ground truth, a permit decision, or proof that a site is safe",
    "weak_label_components": ["hazard", "terrain", "environmental_conflict", "access", "amenities"],
    "weak_label_rule_summary": {
        "hazard": "Largest weight: GSI 2022 susceptibility, modeled flood return period and water level, mapped water, and older flood reference",
        "terrain": "Slope, local elevation variability, and a high-rainfall/steep-slope interaction",
        "environmental_conflict": "Proximity to surface water, quarries, waste facilities, industrial land, and mapped power lines",
        "access": "Straight-line distance to the nearest mapped road",
        "amenities": "Straight-line distance to mapped hospitals, schools, and bus stops",
        "excluded_from_scoring": "Surface soil predictions are retained as model inputs but do not claim bearing capacity; legal title, parcel zoning, CRZ, sewage, crime, price, noise, air quality, and verified utility service remain unavailable",
    },
    "missing_by_feature": frame.isna().sum().to_dict(),
    "limitations": ["Random sample points are not cadastral parcels", "Weak labels reproduce documented public-data assumptions rather than observed building outcomes", "No bearing-capacity test, title, zoning, permit, CRZ decision, sewage, crime, price, noise, air-quality, or verified utility service", "Not mapped means unknown, never safe", "Expert review is required before interpreting the target as construction suitability"],
})
args.card.write_text(json.dumps(card, indent=2) + "\n")
print(json.dumps({"data": str(args.data), "rows": len(frame), "classes": card["weak_label_counts"], "sha256": card["sha256"]}, indent=2))
