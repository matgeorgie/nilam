"""Report Nilam's local human-vote preference evaluation as JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kerala_land_lab.preference_learning import PreferenceStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/processed/preference_feedback.sqlite3")
    args = parser.parse_args()
    if not args.database.exists():
        parser.error(f"No human comparison log exists at {args.database}. Compare sites in Nilam first.")
    print(json.dumps(PreferenceStore(args.database).evaluation(), indent=2))


if __name__ == "__main__":
    main()
