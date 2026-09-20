import numpy as np
import torch
from torch import nn

from kerala_land_lab.multimodal import MultimodalFusionModel, load_chip, set_backbone_trainable


class FakeBackbone(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder=nn.ModuleList([nn.Linear(12,16),nn.Linear(16,16),nn.Linear(16,16)])
        self.encoder_norm=nn.LayerNorm(16)
    def forward(self,inputs):
        values=inputs["S2L2A"].mean(dim=(-1,-2))
        outputs=[]
        for layer in self.encoder:
            values=layer(values);outputs.append(values.unsqueeze(1).expand(-1,4,-1))
        return outputs


def test_multimodal_fusion_outputs_all_ablation_heads():
    model=MultimodalFusionModel(FakeBackbone(),n_tabular=5,vision_dim=16)
    result=model(torch.randn(2,2,12,8,8),torch.randn(2,5))
    assert result["fusion"].shape==(2,4)
    assert result["vision"].shape==(2,4)
    assert result["tabular"].shape==(2,4)
    assert torch.allclose(result["gate"].sum(1),torch.ones(2),atol=1e-5)


def test_only_last_backbone_block_is_unfrozen():
    backbone=FakeBackbone();names=set_backbone_trainable(backbone,last_blocks=1)
    assert names
    assert not backbone.encoder[0].weight.requires_grad
    assert backbone.encoder[2].weight.requires_grad


def test_chip_loader_normalizes_and_preserves_shape(tmp_path):
    path=tmp_path/"chip.npz";np.savez_compressed(path,chips=np.full((2,12,224,224),2000,dtype=np.uint16))
    tensor=load_chip(path)
    assert tensor.shape==(2,12,224,224)
    assert torch.isfinite(tensor).all()
