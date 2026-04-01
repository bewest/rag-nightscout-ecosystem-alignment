import torch
import torch.nn as nn
import math
from typing import Optional


def generate_causal_mask(seq_len: int, device: torch.device) -> torch.Tensor:
    """Generate upper-triangular causal attention mask."""
    return torch.triu(
        torch.ones(seq_len, seq_len, device=device) * float('-inf'),
        diagonal=1,
    )


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

    def forward(self, x, mask=None, causal=False):
        """
        Args:
            x: (Batch, SeqLen, Features=8)
            mask: Optional attention mask (SeqLen, SeqLen)
            causal: If True, apply causal (autoregressive) attention mask.
                    Use for forecast tasks where the model should not attend
                    to future positions.
        """
        # Project to latent space
        z = self.input_projection(x)
        
        # Add temporal context
        z = self.pos_encoder(z)
        
        # Build attention mask
        if causal and mask is None:
            mask = generate_causal_mask(x.size(1), x.device)
        
        # Attention across time and features
        encoded = self.transformer_encoder(z, mask=mask)
        
        # Project back to original feature space
        reconstructed = self.output_projection(encoded)
        
        return reconstructed


class CGMGroupedEncoder(nn.Module):
    """
    Feature-grouped Masked Sequence Encoder for CGM/Insulin time-series.

    Encodes domain structure by projecting State (glucose/IOB/COB),
    Action (basal/bolus/carbs), and Temporal (sin/cos) feature groups
    through separate linear layers before concatenation. This provides
    an inductive bias about which features are physiological state vs.
    control inputs vs. temporal context.

    Architecture:
      state_proj(3 → d_model//2) | action_proj(3 → d_model//4) | time_proj(2 → d_model//4)
      → concatenate → d_model → PositionalEncoding → TransformerEncoder → output heads

    Maintains the same external interface as CGMTransformerAE (input_dim=8, output_dim=8)
    so it's a drop-in replacement in MODEL_REGISTRY.
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 2, dim_feedforward: int = 128, dropout: float = 0.1):
        super().__init__()
        assert d_model % 4 == 0, "d_model must be divisible by 4 for feature grouping"

        # Feature-grouped projections
        d_state = d_model // 2    # 50% capacity for physiological state
        d_action = d_model // 4   # 25% capacity for control inputs
        d_time = d_model - d_state - d_action  # remaining for temporal

        self.state_proj = nn.Linear(3, d_state)    # glucose, IOB, COB
        self.action_proj = nn.Linear(3, d_action)   # net_basal, bolus, carbs
        self.time_proj = nn.Linear(2, d_time)       # time_sin, time_cos

        self.pos_encoder = PositionalEncoding(d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Reconstruction head (back to all 8 features)
        self.output_projection = nn.Linear(d_model, input_dim)

    def forward(self, x, mask=None, causal=False):
        """
        Args:
            x: (Batch, SeqLen, 8) — standard 8-feature cgmencode vector
            mask: Optional attention mask (SeqLen, SeqLen)
            causal: If True, apply causal attention mask for autoregressive tasks.
        """
        # Split by semantic group and project
        state = self.state_proj(x[..., :3])      # glucose, IOB, COB
        action = self.action_proj(x[..., 3:6])    # net_basal, bolus, carbs
        time = self.time_proj(x[..., 6:8])        # time_sin, time_cos

        z = torch.cat([state, action, time], dim=-1)
        z = self.pos_encoder(z)

        if causal and mask is None:
            mask = generate_causal_mask(x.size(1), x.device)

        encoded = self.transformer_encoder(z, mask=mask)
        return self.output_projection(encoded)


# ── Training helpers ─────────────────────────────────────────────
# Minimal functions for use in scripts and experiments.

def train_one_epoch(model, loader, optimizer, criterion):
    """Train for one epoch, return average loss."""
    model.train()
    device = next(model.parameters()).device
    total = 0.0
    n = 0
    for x, y in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        optimizer.zero_grad()
        loss = criterion(model(x), y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += loss.item() * x.size(0)
        n += x.size(0)
    return total / n if n > 0 else float('inf')


def eval_loss(model, loader, criterion):
    """Evaluate model on a DataLoader, return average loss."""
    model.eval()
    device = next(model.parameters()).device
    total = 0.0
    n = 0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            total += criterion(model(x), y).item() * x.size(0)
            n += x.size(0)
    return total / n if n > 0 else float('inf')


if __name__ == "__main__":
    # Quick smoke test: verify model can forward-pass
    model = CGMTransformerAE(input_dim=8, d_model=32, nhead=2, num_layers=1)
    x = torch.randn(2, 12, 8)
    y = model(x)
    print(f"Input: {x.shape} → Output: {y.shape}")
    y_causal = model(x, causal=True)
    print(f"Causal: {x.shape} → Output: {y_causal.shape}")
    params = sum(p.numel() for p in model.parameters())
    print(f"Parameters: {params:,}")
