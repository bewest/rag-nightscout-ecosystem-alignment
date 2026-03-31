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
    Latent space is regularized to N(0, 1).
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, latent_dim: int = 32, nhead: int = 4):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
        
        # Mapping to latent distribution
        self.fc_mu = nn.Linear(d_model, latent_dim)
        self.fc_var = nn.Linear(d_model, latent_dim)
        
        # Decoding back
        self.decoder_input = nn.Linear(latent_dim, d_model)
        self.transformer_decoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.output_projection = nn.Linear(d_model, input_dim)

    def encode(self, x):
        z = self.pos_encoder(self.input_projection(x))
        # Use mean of all tokens as the latent summary
        encoded = self.transformer_encoder(z).mean(dim=1)
        return self.fc_mu(encoded), self.fc_var(encoded)

    def reparameterize(self, mu, logvar):
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z, seq_len: int):
        # Repeat latent vector across the time steps
        z = self.decoder_input(z).unsqueeze(1).repeat(1, seq_len, 1)
        z = self.pos_encoder(z)
        decoded = self.transformer_decoder(z)
        return self.output_projection(decoded)

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z, x.size(1)), mu, logvar

def vae_loss_function(recon_x, x, mu, logvar, beta=0.01):
    recon_loss = F.mse_loss(recon_x, x)
    # KL Divergence: pushes latent space to normal distribution
    kld_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
    return recon_loss + beta * kld_loss

# =============================================================================
# 2. ACTION-CONDITIONED PREDICTOR
# =============================================================================
class ConditionedTransformer(nn.Module):
    """
    Digital Twin / Dosing Counselor.
    Predicts Future Glucose based on (History + Proposed Action).
    """
    def __init__(self, history_dim: int = 8, action_dim: int = 3, d_model: int = 64):
        super().__init__()
        self.history_proj = nn.Linear(history_dim, d_model)
        self.action_proj = nn.Linear(action_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=4, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=3)
        
        # Output is single glucose value per future time step
        self.output_head = nn.Linear(d_model, 1)

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
class CGMDenoisingDiffusion(nn.Module):
    """
    A 1D Diffusion model for stochastic scenario generation.
    Predicts the 'noise' in a corrupted sequence.
    """
    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, d_model)
        # Time embedding to tell the model which diffusion step we're at
        self.step_embedding = nn.Embedding(1000, d_model) 
        self.pos_encoder = PositionalEncoding(d_model)
        
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=3)
        self.output_projection = nn.Linear(d_model, input_dim)

    def forward(self, x_t, t_indices):
        """
        x_t: (Batch, SeqLen, 8) - the sequence at noise level t
        t_indices: (Batch,) - the current diffusion steps [0-999]
        """
        z = self.input_projection(x_t)
        # Add time-step context
        t_embed = self.step_embedding(t_indices).unsqueeze(1)
        z = z + t_embed
        
        z = self.pos_encoder(z)
        out = self.transformer(z)
        return self.output_projection(out) # Predict the noise ε

# =============================================================================
# CLI / EXPLORATION HARNESS
# =============================================================================
def train_toolbox_model(model, loader, optimizer, mode='vae', epochs=5):
    """Generic training harness for toolbox models."""
    from .model import train_one_epoch
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
                t = torch.randint(0, 1000, (x.size(0),))
                noise = torch.randn_like(x)
                # Simplified forward diffusion
                x_t = x + noise 
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
