import torch
from torch import nn


class FeatureTransformer(nn.Module):
    """Each continuous feature receives its own learned token projection."""
    def __init__(self,n_features,dimension=32):
        super().__init__()
        self.weight=nn.Parameter(torch.randn(n_features,dimension)*.02)
        self.bias=nn.Parameter(torch.randn(n_features,dimension)*.02)
        self.cls=nn.Parameter(torch.zeros(1,1,dimension))
        layer=nn.TransformerEncoderLayer(dimension,nhead=4,dim_feedforward=64,dropout=.15,batch_first=True,norm_first=True)
        self.encoder=nn.TransformerEncoder(layer,num_layers=2,enable_nested_tensor=False)
        self.head=nn.Sequential(nn.LayerNorm(dimension),nn.Linear(dimension,3))

    def forward(self,x):
        tokens=x.unsqueeze(-1)*self.weight+self.bias
        tokens=torch.cat([self.cls.expand(x.shape[0],-1,-1),tokens],dim=1)
        return self.head(self.encoder(tokens)[:,0])
