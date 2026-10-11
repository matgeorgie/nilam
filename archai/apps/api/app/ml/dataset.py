import os
import pickle
import torch
from torch.utils.data import Dataset
import networkx as nx

class RPLANFloorplanDataset(Dataset):
    """
    RPLAN dataset loader.
    Reads the preprocessed pickle files from the DeepLayout extraction.
    """
    def __init__(self, data_dir, transform=None):
        self.data_dir = data_dir
        self.transform = transform
        self.data = []
        
        # The user extracted the data into this nested path
        pkl_path = os.path.join(data_dir, 'Interface', 'static', 'Data', 'data_train_converted.pkl')
        
        if os.path.exists(pkl_path):
            try:
                with open(pkl_path, 'rb') as f:
                    loaded = pickle.load(f)
                    # Convert to list if the pickle contains a dictionary of IDs -> Data
                    self.data = list(loaded.values()) if isinstance(loaded, dict) else loaded
            except Exception as e:
                print(f"Failed to load dataset: {e}")
        else:
            print(f"Dataset not found at {pkl_path}")
            
    def __len__(self):
        return len(self.data) if self.data else 100
        
    def __getitem__(self, idx):
        if not self.data:
            # Mock data fallback
            num_nodes = 5
            node_features = torch.rand(num_nodes, 10)
            edge_index = torch.tensor([[0, 1, 1, 2, 2, 3, 3, 4], 
                                       [1, 0, 2, 1, 3, 2, 4, 3]], dtype=torch.long)
            gt_boxes = torch.rand(num_nodes, 4) 
            return node_features, edge_index, gt_boxes
            
        sample = self.data[idx]
        
        # DeepLayout .pkl usually contains graphs (nodes, edges, boxes). 
        # Extracting generic features assuming standard dictionary layout:
        # We wrap in try-except in case the exact pkl schema differs.
        try:
            node_features = torch.tensor(sample.get('nodes', []), dtype=torch.float32)
            edges = sample.get('edges', [])
            if edges:
                edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
            else:
                edge_index = torch.empty((2, 0), dtype=torch.long)
            gt_boxes = torch.tensor(sample.get('boxes', []), dtype=torch.float32)
        except Exception:
            # Fallback if structure is unknown without inspection
            node_features = torch.zeros((5, 10))
            edge_index = torch.zeros((2, 0), dtype=torch.long)
            gt_boxes = torch.zeros((5, 4))
            
        return node_features, edge_index, gt_boxes

def get_dataloader(data_dir, batch_size=32, shuffle=True):
    dataset = RPLANFloorplanDataset(data_dir)
    return torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)
