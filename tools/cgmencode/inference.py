import torch
import numpy as np
from pathlib import Path
from .model import CGMTransformerAE
from .toolbox import CGMTransformerVAE, CGMDenoisingDiffusion, ConditionedTransformer

class T1PalPredictor:
    """High-level wrapper for model inference and 'Digital Twin' simulations."""
    
    def __init__(self, model_type='transformer', model_path=None, device='cpu'):
        self.device = torch.device(device)
        self.model_type = model_type
        
        # In a real app, these parameters would be loaded from a config file
        if model_type == 'transformer':
            self.model = CGMTransformerAE(input_dim=8).to(self.device)
        elif model_type == 'vae':
            self.model = CGMTransformerVAE(input_dim=8).to(self.device)
        elif model_type == 'diffusion':
            self.model = CGMDenoisingDiffusion(input_dim=8).to(self.device)
        elif model_type == 'conditioned':
            self.model = ConditionedTransformer().to(self.device)
            
        if model_path and Path(model_path).exists():
            self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        
        self.model.eval()

    @torch.no_grad()
    def predict_cloud(self, x, num_samples=50):
        """Generates a stochastic cloud of possible futures."""
        if self.model_type != 'diffusion':
            # For non-stochastic models, just return the single prediction repeated
            pred = self.model(x.to(self.device))
            return pred.unsqueeze(0).repeat(num_samples, 1, 1, 1)
        
        # Simplified Diffusion reverse sampling for demonstration
        results = []
        for _ in range(num_samples):
            # In a real DDPM, this would be a multi-step loop
            noise = torch.randn_like(x)
            results.append(self.model(x + noise, torch.zeros(x.size(0), dtype=torch.long)))
        return torch.stack(results)

    @torch.no_grad()
    def evaluate_dose(self, history, proposed_bolus):
        """Action-Conditioned simulation: What happens if I take this dose?"""
        if self.model_type != 'conditioned':
            raise ValueError("evaluate_dose requires a 'conditioned' model type.")
            
        # history: (1, SeqH, 8), proposed_bolus: float
        # Create a future action vector (e.g., 1 hour of zero basal + one-time bolus)
        future_actions = torch.zeros((1, 12, 3)) 
        future_actions[0, 0, 1] = proposed_bolus / 10.0 # Normalized bolus
        
        prediction = self.model(history.to(self.device), future_actions.to(self.device))
        return prediction * 400.0 # Denormalize to mg/dL
