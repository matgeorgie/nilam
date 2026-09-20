"""Temporal satellite + tabular fusion model for Nilam research experiments."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import torch
from torch import nn

S2_BANDS = [
    "COASTAL_AEROSOL", "BLUE", "GREEN", "RED", "RED_EDGE_1", "RED_EDGE_2",
    "RED_EDGE_3", "NIR_BROAD", "NIR_NARROW", "WATER_VAPOR", "SWIR_1", "SWIR_2",
]
EE_S2_BANDS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12"]
S2_MEAN = torch.tensor([1390.458, 1503.317, 1718.197, 1853.910, 2199.100, 2779.975, 2987.011, 3083.234, 3132.220, 3162.988, 2424.884, 1857.648])
S2_STD = torch.tensor([2106.761, 2141.107, 2038.973, 2134.138, 2085.321, 1889.926, 1820.257, 1871.918, 1753.829, 1797.379, 1434.261, 1334.311])


class TabularTokenEncoder(nn.Module):
    def __init__(self, n_features: int, dimension: int):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(n_features, dimension) * 0.02)
        self.bias = nn.Parameter(torch.zeros(n_features, dimension))
        self.feature_identity = nn.Parameter(torch.randn(n_features, dimension) * 0.02)
        layer = nn.TransformerEncoderLayer(dimension, 4, dimension * 3, dropout=0.15, batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        tokens = values.unsqueeze(-1) * self.weight + self.bias + self.feature_identity
        return self.encoder(tokens)


class MultimodalFusionModel(nn.Module):
    """Two-season TerraMind tokens fused with public-data feature tokens."""
    def __init__(self, backbone: nn.Module, n_tabular: int, vision_dim: int, n_classes: int = 4, seasons: int = 2):
        super().__init__()
        self.backbone = backbone
        self.seasons = seasons
        self.season_embedding = nn.Parameter(torch.randn(1, seasons, vision_dim) * 0.02)
        temporal_layer = nn.TransformerEncoderLayer(vision_dim, 4, vision_dim * 3, dropout=0.15, batch_first=True, norm_first=True)
        self.temporal = nn.TransformerEncoder(temporal_layer, 2, enable_nested_tensor=False)
        self.tabular = TabularTokenEncoder(n_tabular, vision_dim)
        self.cross_attention = nn.MultiheadAttention(vision_dim, 4, dropout=0.1, batch_first=True)
        self.branch_gate = nn.Sequential(nn.Linear(vision_dim * 3, vision_dim), nn.GELU(), nn.Linear(vision_dim, 3), nn.Softmax(dim=-1))
        self.fusion_head = nn.Sequential(nn.LayerNorm(vision_dim), nn.Linear(vision_dim, vision_dim), nn.GELU(), nn.Dropout(0.25), nn.Linear(vision_dim, n_classes))
        self.vision_head = nn.Sequential(nn.LayerNorm(vision_dim), nn.Linear(vision_dim, n_classes))
        self.tabular_head = nn.Sequential(nn.LayerNorm(vision_dim), nn.Linear(vision_dim, n_classes))

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
        season_tokens = self._vision_tokens(chips)
        tabular_tokens = self.tabular(tabular)
        cross, _ = self.cross_attention(season_tokens, tabular_tokens, tabular_tokens, need_weights=False)
        vision_summary = season_tokens.mean(dim=1)
        tabular_summary = tabular_tokens.mean(dim=1)
        cross_summary = cross.mean(dim=1)
        weights = self.branch_gate(torch.cat([vision_summary, tabular_summary, cross_summary], dim=-1))
        fused = weights[:, 0:1] * vision_summary + weights[:, 1:2] * tabular_summary + weights[:, 2:3] * cross_summary
        return {
            "fusion": self.fusion_head(fused),
            "vision": self.vision_head(vision_summary),
            "tabular": self.tabular_head(tabular_summary),
            "gate": weights,
        }


def build_terramind_tiny(checkpoint: Path | None = None) -> tuple[nn.Module, int]:
    try:
        from terratorch.registry import BACKBONE_REGISTRY
    except ImportError as exc:
        raise RuntimeError("Install the multimodal environment from requirements-multimodal.txt") from exc
    kwargs = {
        "pretrained": checkpoint is None,
        "modalities": ["S2L2A"],
        "bands": {"S2L2A": S2_BANDS},
    }
    if checkpoint is not None:
        kwargs["ckpt_path"] = str(checkpoint)
    backbone = BACKBONE_REGISTRY.build("terramind_v1_tiny", **kwargs)
    dimension = int(getattr(backbone, "num_features", getattr(backbone, "embed_dim", 192)))
    return backbone, dimension


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


def load_chip(path: Path, augment: bool = False) -> torch.Tensor:
    with np.load(path) as archive:
        chips = archive["chips"].astype(np.float32)
    if chips.shape != (2, 12, 224, 224):
        raise ValueError(f"{path} has {chips.shape}; expected (2, 12, 224, 224)")
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
