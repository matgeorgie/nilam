"""Temporal satellite + tabular fusion model for Nilam research experiments."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import torch
from torch import nn

from kerala_land_lab.model import FeatureTransformer

S2_BANDS = [
    "COASTAL_AEROSOL", "BLUE", "GREEN", "RED", "RED_EDGE_1", "RED_EDGE_2",
    "RED_EDGE_3", "NIR_BROAD", "NIR_NARROW", "WATER_VAPOR", "SWIR_1", "SWIR_2",
]
EE_S2_BANDS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12"]
S2_MEAN = torch.tensor([1390.458, 1503.317, 1718.197, 1853.910, 2199.100, 2779.975, 2987.011, 3083.234, 3132.220, 3162.988, 2424.884, 1857.648])
S2_STD = torch.tensor([2106.761, 2141.107, 2038.973, 2134.138, 2085.321, 1889.926, 1820.257, 1871.918, 1753.829, 1797.379, 1434.261, 1334.311])


class MultimodalFusionModel(nn.Module):
    """Two-season TerraMind tokens fused with public-data feature tokens."""
    def __init__(self, backbone: nn.Module, n_tabular: int, vision_dim: int, n_classes: int = 4, seasons: int = 2, tabular_expert: FeatureTransformer | None = None):
        super().__init__()
        self.backbone = backbone
        self.seasons = seasons
        self.season_embedding = nn.Parameter(torch.randn(1, seasons, vision_dim) * 0.02)
        temporal_layer = nn.TransformerEncoderLayer(vision_dim, 4, vision_dim * 3, dropout=0.15, batch_first=True, norm_first=True)
        self.temporal = nn.TransformerEncoder(temporal_layer, 2, enable_nested_tensor=False)
        self.tabular = tabular_expert or FeatureTransformer(n_tabular, dimension=32, n_classes=n_classes)
        tabular_dim = self.tabular.dimension
        self.tabular_projection = nn.Sequential(nn.Linear(tabular_dim, vision_dim), nn.LayerNorm(vision_dim))
        self.vision_norm = nn.LayerNorm(vision_dim)
        self.cross_norm = nn.LayerNorm(vision_dim)
        self.cross_attention = nn.MultiheadAttention(vision_dim, 4, dropout=0.1, batch_first=True)
        self.branch_gate = nn.Sequential(nn.Linear(vision_dim * 3, vision_dim // 2), nn.GELU(), nn.Linear(vision_dim // 2, 3))
        nn.init.zeros_(self.branch_gate[-1].weight)
        with torch.no_grad():
            self.branch_gate[-1].bias.copy_(torch.tensor([0.0, 6.0, 0.0]))
        self.fusion_residual = nn.Sequential(nn.LayerNorm(vision_dim * 3), nn.Linear(vision_dim * 3, vision_dim), nn.GELU(), nn.Dropout(0.25), nn.Linear(vision_dim, n_classes))
        nn.init.zeros_(self.fusion_residual[-1].weight)
        nn.init.zeros_(self.fusion_residual[-1].bias)
        self.vision_head = nn.Sequential(nn.LayerNorm(vision_dim), nn.Linear(vision_dim, n_classes))
        self.cross_head = nn.Sequential(nn.LayerNorm(vision_dim), nn.Linear(vision_dim, n_classes))

    def _vision_tokens(self, chips: torch.Tensor) -> torch.Tensor:
        batch, seasons, channels, height, width = chips.shape
        flat = chips.reshape(batch * seasons, channels, height, width)
        output = self.backbone({"S2L2A": flat})
        if isinstance(output, dict):
            output = output.get("S2L2A", next(iter(output.values())))
        if isinstance(output, (list, tuple)):
            output = output[-1]
        if output.ndim == 4:
            output = output.flatten(2).transpose(1, 2)
        pooled = output.mean(dim=1).reshape(batch, seasons, -1)
        return self.temporal(pooled + self.season_embedding[:, :seasons])

    def forward(self, chips: torch.Tensor, tabular: torch.Tensor) -> dict[str, torch.Tensor]:
        season_tokens = self.vision_norm(self._vision_tokens(chips))
        compact_tabular_tokens = self.tabular.encode_tokens(tabular)
        tabular_logits = self.tabular.head(compact_tabular_tokens[:, 0])
        tabular_tokens = self.tabular_projection(compact_tabular_tokens)
        cross, _ = self.cross_attention(season_tokens, tabular_tokens, tabular_tokens, need_weights=False)
        vision_summary = season_tokens.mean(dim=1)
        tabular_summary = tabular_tokens[:, 0]
        cross_summary = self.cross_norm(cross.mean(dim=1))
        summaries = torch.cat([vision_summary, tabular_summary, cross_summary], dim=-1)
        gate_probability = torch.softmax(self.branch_gate(summaries) / 2.0, dim=-1)
        weights = 0.94 * gate_probability + 0.02
        vision_logits = self.vision_head(vision_summary)
        cross_logits = self.cross_head(cross_summary)
        experts = torch.stack([vision_logits, tabular_logits, cross_logits], dim=1)
        fused_logits = (weights.unsqueeze(-1) * experts).sum(dim=1) + 0.1 * self.fusion_residual(summaries)
        return {
            "fusion": fused_logits,
            "vision": vision_logits,
            "tabular": tabular_logits,
            "cross": cross_logits,
            "gate": weights,
        }


def build_terramind(checkpoint: Path | None = None, variant: str = "base", pretrained: bool = True) -> tuple[nn.Module, int]:
    try:
        from terratorch.registry import BACKBONE_REGISTRY
    except ImportError as exc:
        raise RuntimeError("Install the multimodal environment from requirements-multimodal.txt") from exc
    kwargs = {
        "pretrained": checkpoint is None and pretrained,
        "modalities": ["S2L2A"],
        "bands": {"S2L2A": S2_BANDS},
    }
    if checkpoint is not None:
        kwargs["ckpt_path"] = str(checkpoint)
    if variant not in {"tiny", "base"}:
        raise ValueError("variant must be 'tiny' or 'base'")
    backbone = BACKBONE_REGISTRY.build(f"terramind_v1_{variant}", **kwargs)
    if hasattr(backbone, "encoder_norm"):
        dimension = int(backbone.encoder_norm.normalized_shape[0])
    else:
        dimension = 192 if variant == "tiny" else 768
    return backbone, dimension


def build_terramind_tiny(checkpoint: Path | None = None) -> tuple[nn.Module, int]:
    """Backward-compatible tiny builder used by lightweight tests and experiments."""
    return build_terramind(checkpoint, variant="tiny")


def set_backbone_trainable(backbone: nn.Module, last_blocks: int = 0) -> list[str]:
    """Freeze the GeoFM or unfreeze only its final encoder blocks and norm."""
    for parameter in backbone.parameters():
        parameter.requires_grad = False
    if last_blocks <= 0:
        return []
    block_indices = []
    for name, _ in backbone.named_parameters():
        match = re.search(r"(?:encoder|blocks)\.(\d+)\.", name)
        if match:
            block_indices.append(int(match.group(1)))
    if not block_indices:
        raise RuntimeError("Could not locate TerraMind encoder blocks; inspect the installed TerraTorch version")
    selected = set(sorted(set(block_indices))[-last_blocks:])
    trainable = []
    for name, parameter in backbone.named_parameters():
        match = re.search(r"(?:encoder|blocks)\.(\d+)\.", name)
        if (match and int(match.group(1)) in selected) or "encoder_norm" in name:
            parameter.requires_grad = True
            trainable.append(name)
    return trainable


@dataclass(frozen=True)
class ChipRecord:
    point_id: str
    path: Path
    valid_fraction: float


def normalize_chip(chips: np.ndarray, augment: bool = False) -> torch.Tensor:
    chips = chips.astype(np.float32, copy=False)
    if chips.shape != (2, 12, 224, 224):
        raise ValueError(f"Chip has {chips.shape}; expected (2, 12, 224, 224)")
    tensor = torch.from_numpy(chips)
    tensor = (tensor - S2_MEAN.view(1, -1, 1, 1)) / S2_STD.view(1, -1, 1, 1)
    if augment:
        if torch.rand(()) < 0.5:
            tensor = tensor.flip(-1)
        if torch.rand(()) < 0.5:
            tensor = tensor.flip(-2)
        rotations = int(torch.randint(0, 4, ()).item())
        tensor = torch.rot90(tensor, rotations, (-2, -1))
    return tensor


def load_chip(path: Path, augment: bool = False) -> torch.Tensor:
    with np.load(path) as archive:
        chips = archive["chips"]
    return normalize_chip(chips, augment)
