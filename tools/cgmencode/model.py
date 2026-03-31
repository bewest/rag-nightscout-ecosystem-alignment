import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import Tuple, Optional

class PositionalEncoding(nn.Module):
    """Classic Sinusoidal Positional Encoding for time-series."""
    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]

class CGMTransformerAE(nn.Module):
    """
    Small Transformer-based Autoencoder for CGM/Insulin Time-Series.
    
    Architecture:
    1. Linear Projection: (Batch, SeqLen, InputDim) -> (Batch, SeqLen, d_model)
    2. Positional Encoding: Injects temporal order.
    3. Transformer Encoder: Multiple layers of Multi-Head Attention.
    4. Reconstruction Head: Linear projection back to (Batch, SeqLen, InputDim).
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4, 
                 num_layers: int = 2, dim_feedforward: int = 128, dropout: float = 0.1):
        super().__init__()
        
        # 1. Input Projection
        self.input_projection = nn.Linear(input_dim, d_model)
        
        # 2. Positional Encoding
        self.pos_encoder = PositionalEncoding(d_model)
        
        # 3. Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, 
            nhead=nhead, 
            dim_feedforward=dim_feedforward, 
            dropout=dropout,
            batch_first=True,
            norm_first=True # Modern practice: pre-norm
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # 4. Output Projection (Reconstruction)
        self.output_projection = nn.Linear(d_model, input_dim)
        
        self.init_weights()

    def init_weights(self):
        initrange = 0.1
        self.input_projection.weight.data.uniform_(-initrange, initrange)
        self.input_projection.bias.data.zero_()
        self.output_projection.weight.data.uniform_(-initrange, initrange)
        self.output_projection.bias.data.zero_()

    def forward(self, x, mask=None):
        """
        Args:
            x: (Batch, SeqLen, Features=8)
            mask: Optional attention mask (Batch, SeqLen, SeqLen)
        """
        # Project to latent space
        z = self.input_projection(x)
        
        # Add temporal context
        z = self.pos_encoder(z)
        
        # Attention across time and features
        encoded = self.transformer_encoder(z, mask=mask)
        
        # Project back to original feature space
        reconstructed = self.output_projection(encoded)
        
        return reconstructed

def train_one_epoch(model, loader, optimizer, criterion, clip_grad: float = 1.0):
    """Generic training step for a single epoch."""
    model.train()
    total_loss = 0
    for x_batch, y_batch in loader:
        optimizer.zero_grad()
        output = model(x_batch)
        loss = criterion(output, y_batch)
        loss.backward()
        
        # PRO-TIP: Gradient clipping for stability
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip_grad)
        
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)

def evaluate(model, loader, criterion):
    """Evaluation on validation set."""
    model.eval()
    total_loss = 0
    with torch.no_grad():
        for x_batch, y_batch in loader:
            output = model(x_batch)
            loss = criterion(output, y_batch)
            total_loss += loss.item()
    return total_loss / len(loader)

def experiment_decreasing_loss(epochs=10):
    """Verifies that loss decreases over a short training run with validation."""
    from .encoder import load_fixtures_to_dataset
    from torch.utils.data import DataLoader
    
    WINDOW = 12
    train_ds, val_ds = load_fixtures_to_dataset(
        ['fixtures/algorithm-replays', 'fixtures/scenarios'], 
        task='forecast', window_size=WINDOW
    )
    
    if not train_ds:
        print("Dataset creation failed.")
        return

    train_loader = DataLoader(train_ds, batch_size=16, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=16)

    # Updated input_dim=8 (6 original + 2 cyclical time)
    model = CGMTransformerAE(input_dim=8, d_model=32, nhead=2, num_layers=1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    criterion = nn.MSELoss()
    
    print(f"Starting experiment: {len(train_ds)} train, {len(val_ds)} val samples...")
    train_losses = []
    val_losses = []
    for epoch in range(epochs):
        t_loss = train_one_epoch(model, train_loader, optimizer, criterion)
        v_loss = evaluate(model, val_loader, criterion)
        train_losses.append(t_loss)
        val_losses.append(v_loss)
        
        if epoch % 2 == 0 or epoch == epochs - 1:
            print(f"Epoch {epoch:02d} | Train Loss: {t_loss:.6f} | Val Loss: {v_loss:.6f}")
            
    if train_losses[-1] < train_losses[0]:
        print(f"SUCCESS: Train loss decreased from {train_losses[0]:.6f} to {train_losses[-1]:.6f}")
        # SAVE MODEL
        torch.save(model.state_dict(), "transformer_model.pth")
        print("Model weights saved to 'transformer_model.pth'")
    else:
        print(f"FAILURE: Train loss did not decrease.")

if __name__ == "__main__":
    # Run the verification experiment
    experiment_decreasing_loss(epochs=10)
