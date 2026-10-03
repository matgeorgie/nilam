"""Quality-gated late fusion for TerraMind and TabPFN predictions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class FusionConfig:
    """Small, auditable calibration artifact for the two model experts."""

    agree_vision_weight: float = 0.08
    disagree_vision_weight: float = 0.02
    quality_gate_passed: bool = False
    validation_macro_f1: float | None = None
    test_macro_f1: float | None = None
    tabpfn_test_macro_f1: float | None = None
    version: str = "terramind_tabpfn_v1"

    @classmethod
    def load(cls, path: Path) -> "FusionConfig":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        accepted = {name: raw[name] for name in cls.__dataclass_fields__ if name in raw}
        return cls(**accepted)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")


def _normalize(probabilities: np.ndarray) -> np.ndarray:
    values = np.asarray(probabilities, dtype=np.float64)
    values = np.clip(values, 1e-7, None)
    return values / values.sum(axis=-1, keepdims=True)


def combine_probabilities(
    tabpfn: np.ndarray,
    terramind: np.ndarray,
    config: FusionConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Geometrically pool experts with a conservative, agreement-aware vision weight."""

    tabular = _normalize(tabpfn)
    vision = _normalize(terramind)
    if tabular.shape != vision.shape:
        raise ValueError(f"Expert probability shapes differ: {tabular.shape} vs {vision.shape}")
    agreement = tabular.argmax(axis=-1) == vision.argmax(axis=-1)
    weight = np.where(agreement, config.agree_vision_weight, config.disagree_vision_weight)
    fused_log = (1 - weight[:, None]) * np.log(tabular) + weight[:, None] * np.log(vision)
    fused_log -= fused_log.max(axis=-1, keepdims=True)
    fused = np.exp(fused_log)
    fused /= fused.sum(axis=-1, keepdims=True)
    return fused.astype(np.float32), weight.astype(np.float32)

