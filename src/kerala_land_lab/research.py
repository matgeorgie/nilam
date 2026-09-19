"""Utilities that make spatial model evaluation reproducible and auditable."""
from __future__ import annotations

import numpy as np
import pandas as pd


def grouped_stratified_split(
    frame: pd.DataFrame,
    *,
    target: str = "target",
    group: str = "source_polygon_id",
    seed: int = 42,
    proportions: tuple[float, float, float] = (0.6, 0.2, 0.2),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split whole source polygons while balancing row counts within each class.

    The target is expected to be constant within each source polygon. Groups are
    assigned greedily to the split with the largest remaining class-specific
    row deficit. Random tie-breaking is deterministic from ``seed``.
    """
    if not np.isclose(sum(proportions), 1):
        raise ValueError("Split proportions must sum to one")
    purity = frame.groupby(group)[target].nunique()
    if (purity != 1).any():
        raise ValueError("Each source polygon must have exactly one target class")
    rng = np.random.default_rng(seed)
    assignments: dict[object, int] = {}
    for class_value, subset in frame.groupby(target):
        counts = subset.groupby(group).size().rename("rows").reset_index()
        counts["tie"] = rng.random(len(counts))
        counts = counts.sort_values(["rows", "tie"], ascending=[False, True])
        desired = np.asarray(proportions) * len(subset)
        current = np.zeros(3, dtype=float)
        for row in counts.itertuples(index=False):
            deficits = desired - current
            split = int(np.argmax(deficits / np.asarray(proportions)))
            assignments[getattr(row, group)] = split
            current[split] += row.rows
    membership = frame[group].map(assignments).to_numpy()
    result = tuple(np.flatnonzero(membership == split) for split in range(3))
    if any(len(indices) == 0 for indices in result):
        raise ValueError("Grouped split produced an empty partition")
    return result
