import torch
import torch.nn as nn
import torch.nn.functional as F
from .model import PositionalEncoding, CGMTransformerAE

# =============================================================================
# 1. VARIATIONAL AUTOENCODER (VAE)
# =============================================================================
class CGMTransformerVAE(nn.Module):
    """
    VAE for generative scenario exploration.

    Improved architecture vs original:
    - Separate encoder/decoder transformer layers (no weight sharing)
    - Per-timestep latent variables instead of mean-pooling bottleneck
    - Larger latent_dim default (64 vs 32) to preserve temporal information

    The encoder maps each timestep to (mu, logvar), reparameterization samples
    per-timestep latent vectors, and the decoder reconstructs from these.
    This preserves temporal structure that mean-pooling destroyed.
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, latent_dim: int = 64, nhead: int = 4):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        # Separate encoder and decoder (no weight sharing)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, batch_first=True, norm_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(enc_layer, num_layers=2)
        
        # Per-timestep latent distribution
        self.fc_mu = nn.Linear(d_model, latent_dim)
        self.fc_var = nn.Linear(d_model, latent_dim)
        
        # Decoder (separate layers)
        self.decoder_input = nn.Linear(latent_dim, d_model)
        dec_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, batch_first=True, norm_first=True,
        )
        self.transformer_decoder = nn.TransformerEncoder(dec_layer, num_layers=2)
        self.output_projection = nn.Linear(d_model, input_dim)

    def encode(self, x):
        z = self.pos_encoder(self.input_projection(x))
        encoded = self.transformer_encoder(z)  # (B, T, d_model)
        # Per-timestep latent distribution (preserves temporal structure)
        return self.fc_mu(encoded), self.fc_var(encoded)

    def reparameterize(self, mu, logvar):
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z, seq_len: int = None):
        # z is already (B, T, latent_dim) — per-timestep
        z = self.decoder_input(z)
        z = self.pos_encoder(z)
        decoded = self.transformer_decoder(z)
        return self.output_projection(decoded)

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z), mu, logvar

def vae_loss_function(recon_x, x, mu, logvar, beta=0.01):
    recon_loss = F.mse_loss(recon_x, x)
    # KL Divergence: mean over all dimensions (batch, time, latent)
    # to keep KL magnitude stable regardless of sequence length or latent_dim
    kld_loss = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
    return recon_loss + beta * kld_loss

# =============================================================================
# 2. ACTION-CONDITIONED PREDICTOR
# =============================================================================
class ConditionedTransformer(nn.Module):
    """
    Digital Twin / Dosing Counselor.
    Predicts Future Glucose based on (History + Proposed Action).
    """
    def __init__(self, history_dim: int = 8, action_dim: int = 3, d_model: int = 64,
                 dropout: float = 0.2):
        super().__init__()
        self.history_proj = nn.Linear(history_dim, d_model)
        self.action_proj = nn.Linear(action_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        self.input_dropout = nn.Dropout(dropout)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=4, batch_first=True,
            dropout=dropout,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=3)
        
        self.output_head = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, 1),
        )

    def forward(self, history, future_actions):
        """
        history: (Batch, SeqH, 8)
        future_actions: (Batch, SeqF, 3)
        """
        # Project both to same latent dimension
        h_z = self.history_proj(history)
        a_z = self.action_proj(future_actions)
        
        # Combine across time: [History... FutureActions]
        combined = torch.cat([h_z, a_z], dim=1)
        combined = self.pos_encoder(combined)
        combined = self.input_dropout(combined)
        
        encoded = self.transformer(combined)
        
        # We only care about predicting glucose for the "future" part of the sequence
        future_part = encoded[:, history.size(1):, :]
        return self.output_head(future_part).squeeze(-1)

# =============================================================================
# 3. CONTRASTIVE REPRESENTATION LEARNING
# =============================================================================
class ContrastiveLoss(nn.Module):
    """
    Encourages two augmented versions of the same sample to have similar embeddings.
    """
    def __init__(self, temperature=0.07):
        super().__init__()
        self.temperature = temperature

    def forward(self, z_i, z_j):
        """z_i and z_j are latent embeddings from two augmented views."""
        # Normalize
        z_i = F.normalize(z_i, dim=1)
        z_j = F.normalize(z_j, dim=1)
        
        # Cosine similarity
        logits = torch.matmul(z_i, z_j.T) / self.temperature
        
        # Target: Diagonal (i and j are matched)
        labels = torch.arange(z_i.size(0)).to(z_i.device)
        return F.cross_entropy(logits, labels)

# =============================================================================
# 4. DENOISING DIFFUSION (DDPM-style for 1D)
# =============================================================================

def linear_beta_schedule(timesteps: int = 1000, beta_start: float = 1e-4, beta_end: float = 0.02):
    """Linear β-schedule as in Ho et al. (2020)."""
    return torch.linspace(beta_start, beta_end, timesteps)


def precompute_diffusion_constants(betas: torch.Tensor):
    """Precompute αbar, sqrt(αbar), sqrt(1-αbar) for efficient forward/reverse."""
    alphas = 1.0 - betas
    alphas_cumprod = torch.cumprod(alphas, dim=0)
    return {
        'betas': betas,
        'alphas_cumprod': alphas_cumprod,
        'sqrt_alphas_cumprod': torch.sqrt(alphas_cumprod),
        'sqrt_one_minus_alphas_cumprod': torch.sqrt(1.0 - alphas_cumprod),
    }


class CGMDenoisingDiffusion(nn.Module):
    """
    A 1D Diffusion model for stochastic scenario generation.
    Uses proper DDPM β-schedule: x_t = sqrt(αbar_t) * x_0 + sqrt(1-αbar_t) * ε
    Predicts the noise ε given (x_t, t).
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4,
                 timesteps: int = 1000):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, d_model)
        self.step_embedding = nn.Embedding(timesteps, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=3)
        self.output_projection = nn.Linear(d_model, input_dim)

        # Precompute diffusion constants (registered as buffers so they move with .to())
        betas = linear_beta_schedule(timesteps)
        consts = precompute_diffusion_constants(betas)
        self.register_buffer('sqrt_alphas_cumprod', consts['sqrt_alphas_cumprod'])
        self.register_buffer('sqrt_one_minus_alphas_cumprod', consts['sqrt_one_minus_alphas_cumprod'])
        self.timesteps = timesteps

    def q_sample(self, x_0, t, noise=None):
        """Forward diffusion: q(x_t | x_0) = N(sqrt(αbar_t)*x_0, (1-αbar_t)*I)."""
        if noise is None:
            noise = torch.randn_like(x_0)
        sqrt_ab = self.sqrt_alphas_cumprod[t]            # (B,)
        sqrt_1_ab = self.sqrt_one_minus_alphas_cumprod[t] # (B,)
        # Reshape for broadcasting: (B,) → (B, 1, 1)
        while sqrt_ab.dim() < x_0.dim():
            sqrt_ab = sqrt_ab.unsqueeze(-1)
            sqrt_1_ab = sqrt_1_ab.unsqueeze(-1)
        return sqrt_ab * x_0 + sqrt_1_ab * noise

    def forward(self, x_t, t_indices):
        """
        x_t: (Batch, SeqLen, 8) — the sequence at noise level t
        t_indices: (Batch,) — the current diffusion steps [0, timesteps-1]
        """
        z = self.input_projection(x_t)
        t_embed = self.step_embedding(t_indices).unsqueeze(1)
        z = z + t_embed
        z = self.pos_encoder(z)
        out = self.transformer(z)
        return self.output_projection(out)  # Predict the noise ε

# =============================================================================
# CLI / EXPLORATION HARNESS
# =============================================================================
def train_toolbox_model(model, loader, optimizer, mode='vae', epochs=5):
    """Generic training harness for toolbox models."""
    print(f"Starting {mode.upper()} training for {epochs} epochs...")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for batch in loader:
            optimizer.zero_grad()
            if mode == 'vae':
                x, _ = batch
                recon, mu, logvar = model(x)
                loss = vae_loss_function(recon, x, mu, logvar)
            elif mode == 'conditioned':
                (hist, actions), target = batch
                pred = model(hist, actions)
                loss = F.mse_loss(pred, target)
            elif mode == 'diffusion':
                x, _ = batch
                t = torch.randint(0, model.timesteps, (x.size(0),))
                noise = torch.randn_like(x)
                x_t = model.q_sample(x, t, noise=noise)
                predicted_noise = model(x_t, t)
                loss = F.mse_loss(predicted_noise, noise)
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
        
        avg_loss = total_loss / len(loader)
        print(f"Epoch {epoch:02d} | Avg Loss: {avg_loss:.6f}")

if __name__ == "__main__":
    from .encoder import load_fixtures_to_dataset
    from torch.utils.data import DataLoader
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else 'vae'
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    if mode == 'stats':
        train_ds, _ = load_fixtures_to_dataset(['fixtures/algorithm-replays', 'fixtures/scenarios'], window_size=72)
        print(f"--- Data Statistics ---")
        if train_ds:
            # We add 20% back because load_fixtures_to_dataset splits them
            total = int(len(train_ds) / 0.8)
            print(f"Total usable vectors (6h window): {total}")
            print(f"Total training samples: {len(train_ds)}")
            print(f"Feature shape: {train_ds[0][0].shape}")
        else:
            print("No usable data found.")
        sys.exit(0)

    print(f"--- Running Toolbox Experiment: {mode.upper()} ---")

    if mode == 'vae':
        train_ds, val_ds = load_fixtures_to_dataset(['fixtures/algorithm-replays', 'fixtures/scenarios'], task='reconstruct', window_size=12)
        if not train_ds: print("No data."); sys.exit(1)
        loader = DataLoader(train_ds, batch_size=16, shuffle=True)
        model = CGMTransformerVAE(input_dim=8)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        train_toolbox_model(model, loader, optimizer, 'vae', epochs)

    elif mode == 'conditioned':
        train_ds, val_ds = load_fixtures_to_dataset(['fixtures/algorithm-replays', 'fixtures/scenarios'], conditioned=True, window_size=12)
        if not train_ds: print("No data."); sys.exit(1)
        loader = DataLoader(train_ds, batch_size=16, shuffle=True)
        model = ConditionedTransformer()
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        train_toolbox_model(model, loader, optimizer, 'conditioned', epochs)
    
    elif mode == 'diffusion':
        train_ds, val_ds = load_fixtures_to_dataset(['fixtures/algorithm-replays', 'fixtures/scenarios'], task='reconstruct', window_size=12)
        if not train_ds: print("No data."); sys.exit(1)
        loader = DataLoader(train_ds, batch_size=16, shuffle=True)
        model = CGMDenoisingDiffusion(input_dim=8)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        train_toolbox_model(model, loader, optimizer, 'diffusion', epochs)

    else:
        print("Unknown mode. Use 'stats', 'vae', 'conditioned', or 'diffusion'.")
