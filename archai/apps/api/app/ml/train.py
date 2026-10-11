import os
import torch
import torch.optim as optim
import torch.nn as nn
from .dataset import get_dataloader
from .model import GeneratorGNN, DiscriminatorGNN

def train_epoch(generator, discriminator, dataloader, opt_G, opt_D, criterion, device):
    """
    Scaffolding for a GAN training loop on graph floor plans.
    """
    generator.train()
    discriminator.train()
    
    total_g_loss = 0
    total_d_loss = 0
    
    for batch_idx, (node_features, edge_index, gt_boxes) in enumerate(dataloader):
        # In a real setup with PyTorch Geometric, edge_index would be converted to an adjacency matrix for our simple GCN, 
        # or we'd use PyG layers directly.
        # For scaffolding, let's assume we construct a dense adj matrix.
        B, N, _ = node_features.shape
        adj = torch.ones(B, N, N).to(device) # Mock adjacency
        
        node_features = node_features.to(device)
        gt_boxes = gt_boxes.to(device)
        
        # ---------------------
        #  Train Discriminator
        # ---------------------
        opt_D.zero_grad()
        
        # Real loss
        real_validity = discriminator(node_features, gt_boxes, adj)
        real_loss = criterion(real_validity, torch.ones_like(real_validity))
        
        # Fake loss
        noise = torch.randn(B, N, 16).to(device) # Noise for diversity
        gen_input = torch.cat([node_features, noise], dim=-1)
        fake_boxes = generator(gen_input, adj)
        fake_validity = discriminator(node_features, fake_boxes.detach(), adj)
        fake_loss = criterion(fake_validity, torch.zeros_like(fake_validity))
        
        d_loss = (real_loss + fake_loss) / 2
        d_loss.backward()
        opt_D.step()
        
        # -----------------
        #  Train Generator
        # -----------------
        opt_G.zero_grad()
        
        # G wants Discriminator to classify fakes as real
        fake_validity = discriminator(node_features, fake_boxes, adj)
        g_loss = criterion(fake_validity, torch.ones_like(fake_validity))
        
        # Additional geometric/architectural losses would go here (e.g. overlap penalties)
        
        g_loss.backward()
        opt_G.step()
        
        total_g_loss += g_loss.item()
        total_d_loss += d_loss.item()
        
    return total_g_loss / len(dataloader), total_d_loss / len(dataloader)

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on {device}")
    
    # Hyperparameters
    NODE_DIM = 10 # 10 room types
    NOISE_DIM = 16
    HIDDEN_DIM = 64
    EPOCHS = 100
    
    dataloader = get_dataloader(data_dir='./data/rplan', batch_size=32)
    
    generator = GeneratorGNN(NODE_DIM + NOISE_DIM, HIDDEN_DIM, out_dim=4).to(device)
    discriminator = DiscriminatorGNN(NODE_DIM + 4, HIDDEN_DIM).to(device)
    
    opt_G = optim.Adam(generator.parameters(), lr=0.0002, betas=(0.5, 0.999))
    opt_D = optim.Adam(discriminator.parameters(), lr=0.0002, betas=(0.5, 0.999))
    criterion = nn.BCELoss()
    
    for epoch in range(EPOCHS):
        g_loss, d_loss = train_epoch(generator, discriminator, dataloader, opt_G, opt_D, criterion, device)
        print(f"Epoch {epoch}/{EPOCHS} | D Loss: {d_loss:.4f} | G Loss: {g_loss:.4f}")
        
        if epoch % 10 == 0:
            torch.save(generator.state_dict(), f"generator_epoch_{epoch}.pth")

if __name__ == '__main__':
    main()
