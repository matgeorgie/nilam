import torch
import torch.nn as nn
import torch.nn.functional as F

class GraphConvolution(nn.Module):
    """Simple GCN layer for scaffolding."""
    def __init__(self, in_features, out_features):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)
        
    def forward(self, x, adj):
        # x: (B, N, F), adj: (B, N, N)
        out = torch.bmm(adj, x)
        return self.linear(out)

class GeneratorGNN(nn.Module):
    """
    Scaffolding for a Graph-Conditioned Generator (like HouseGAN).
    Inputs:
        - node_features: Room types (one-hot) + noise vector (for diversity)
        - adjacency_matrix: Room connectivity graph
    Outputs:
        - predicted_boxes: (x, y, w, h) for each room
    """
    def __init__(self, node_in_dim, hidden_dim, out_dim=4):
        super().__init__()
        self.gcn1 = GraphConvolution(node_in_dim, hidden_dim)
        self.gcn2 = GraphConvolution(hidden_dim, hidden_dim)
        self.fc = nn.Linear(hidden_dim, out_dim)
        
    def forward(self, node_features, adj):
        x = F.relu(self.gcn1(node_features, adj))
        x = F.relu(self.gcn2(x, adj))
        boxes = torch.sigmoid(self.fc(x)) # Bound boxes to [0, 1]
        return boxes

class DiscriminatorGNN(nn.Module):
    """
    Scaffolding for the Discriminator.
    Evaluates whether the given layout graph + bounding boxes are 'real' or 'fake'.
    """
    def __init__(self, node_in_dim, hidden_dim):
        super().__init__()
        # node_in_dim includes the room type + the 4 bbox coordinates
        self.gcn1 = GraphConvolution(node_in_dim, hidden_dim)
        self.gcn2 = GraphConvolution(hidden_dim, hidden_dim)
        self.fc = nn.Linear(hidden_dim, 1)
        
    def forward(self, node_features, boxes, adj):
        # Concatenate features and spatial boxes
        x = torch.cat([node_features, boxes], dim=-1)
        x = F.relu(self.gcn1(x, adj))
        x = F.relu(self.gcn2(x, adj))
        
        # Pool across nodes to get a single score per graph
        pooled = torch.mean(x, dim=1) 
        validity = torch.sigmoid(self.fc(pooled))
        return validity
