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

    Architecture (core, input_dim=8):
      state_proj(3 → d_model//2) | action_proj(3 → d_model//4) | time_proj(2 → d_model//4)
      → concatenate → d_model → PositionalEncoding → TransformerEncoder → output heads

    Architecture (extended, input_dim=16):
      state_proj(3) | action_proj(3) | time_proj(2) | context_proj(8 → d_context)
      → concatenate → d_model + d_context → LayerNorm → d_model (via fusion)
      → PositionalEncoding → TransformerEncoder → output heads

    Maintains the same external interface as CGMTransformerAE so it's a
    drop-in replacement in MODEL_REGISTRY. When input_dim=8 (default),
    behaves identically to the original — no context group is created,
    existing checkpoints load without modification.
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 2, dim_feedforward: int = 128, dropout: float = 0.1):
        super().__init__()
        assert d_model % 4 == 0, "d_model must be divisible by 4 for feature grouping"

        self.input_dim = input_dim
        self.d_model = d_model

        # Feature-grouped projections (core — always present)
        d_state = d_model // 2    # 50% capacity for physiological state
        d_action = d_model // 4   # 25% capacity for control inputs
        d_time = d_model - d_state - d_action  # remaining for temporal

        self.state_proj = nn.Linear(3, d_state)    # glucose, IOB, COB
        self.action_proj = nn.Linear(3, d_action)   # net_basal, bolus, carbs
        self.time_proj = nn.Linear(2, d_time)       # time_sin, time_cos

        # Context group (extended schema only — agentic features)
        self._has_context = input_dim > 8
        if self._has_context:
            n_context = input_dim - 8
            d_context = max(d_model // 8, 8)  # ~12.5% capacity for context
            self.context_proj = nn.Linear(n_context, d_context)
            # Fusion layer: (d_model + d_context) → d_model
            self.fusion = nn.Linear(d_model + d_context, d_model)
            self.fusion_norm = nn.LayerNorm(d_model)

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

        # Reconstruction head (back to all input features)
        self.output_projection = nn.Linear(d_model, input_dim)

    def forward(self, x, mask=None, causal=False):
        """
        Args:
            x: (Batch, SeqLen, input_dim) — 8 or 16 feature cgmencode vector
            mask: Optional attention mask (SeqLen, SeqLen)
            causal: If True, apply causal attention mask for autoregressive tasks.
        """
        # Split by semantic group and project
        state = self.state_proj(x[..., :3])      # glucose, IOB, COB
        action = self.action_proj(x[..., 3:6])    # net_basal, bolus, carbs
        time = self.time_proj(x[..., 6:8])        # time_sin, time_cos

        z = torch.cat([state, action, time], dim=-1)

        if self._has_context and x.size(-1) > 8:
            ctx = self.context_proj(x[..., 8:])
            z = self.fusion_norm(self.fusion(torch.cat([z, ctx], dim=-1)))

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

    # Extended GroupedEncoder (16 features)
    model_ext = CGMGroupedEncoder(input_dim=16, d_model=64, nhead=4, num_layers=2)
    x_ext = torch.randn(2, 12, 16)
    y_ext = model_ext(x_ext)
    print(f"\nExtended Input: {x_ext.shape} → Output: {y_ext.shape}")
    params_ext = sum(p.numel() for p in model_ext.parameters())
    print(f"Extended Parameters: {params_ext:,}")

    # Core GroupedEncoder (8 features) — backward compat
    model_core = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=2)
    y_core = model_core(x)
    print(f"\nCore Input: {x.shape} → Output: {y_core.shape}")
    params_core = sum(p.numel() for p in model_core.parameters())
    print(f"Core Parameters: {params_core:,}")
