"""
uncertainty.py — Monte Carlo Dropout uncertainty quantification.

Estimates prediction uncertainty by running multiple forward passes
with dropout enabled. Produces prediction intervals and event
probability estimates (P(hypo), P(hyper)) needed for safety guards.

Usage:
    from tools.cgmencode.uncertainty import mc_predict, hypo_probability

    mean, std, samples = mc_predict(model, x, n_samples=50)
    p_hypo = hypo_probability(mean, std, threshold_mgdl=70)
"""

import math
from contextlib import contextmanager
from typing import Dict, Tuple

import torch
import torch.nn as nn

from .schema import NORMALIZATION_SCALES, IDX_GLUCOSE

GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']  # 400.0 mg/dL


# ---------------------------------------------------------------------------
# Gaussian CDF — scipy-free fallback using the error function from math
# ---------------------------------------------------------------------------

def _norm_cdf(x: torch.Tensor) -> torch.Tensor:
    """Standard normal CDF, element-wise.  Uses torch.erfc for numerical stability."""
    return 0.5 * torch.erfc(-x / math.sqrt(2.0))


# ---------------------------------------------------------------------------
# 1. MC-Dropout context manager
# ---------------------------------------------------------------------------

@contextmanager
def enable_mc_dropout(model: nn.Module):
    """Keep Dropout layers in training mode while the rest of the model is in eval.

    On exit the original ``training`` flag of every Dropout module is restored,
    so this is safe to nest and idempotent w.r.t. model state.
    """
    dropout_states: list = []
    for m in model.modules():
        if isinstance(m, nn.Dropout):
            dropout_states.append((m, m.training))
            m.training = True
    try:
        yield model
    finally:
        for m, was_training in dropout_states:
            m.training = was_training


# ---------------------------------------------------------------------------
# 2. MC forward-pass sampler
# ---------------------------------------------------------------------------

def mc_predict(
    model: nn.Module,
    x: torch.Tensor,
    n_samples: int = 50,
    causal: bool = False,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Run *n_samples* stochastic forward passes with dropout active.

    Parameters
    ----------
    model : nn.Module
        A cgmencode model (CGMTransformerAE or CGMGroupedEncoder).
    x : Tensor, shape (B, SeqLen, Features)
        Normalised input batch.
    n_samples : int
        Number of MC samples (default 50).
    causal : bool
        Pass through to ``model.forward(..., causal=causal)``.

    Returns
    -------
    mean : Tensor (B, S, F)
    std  : Tensor (B, S, F)
    samples : Tensor (n_samples, B, S, F)
    """
    model.eval()
    samples = []
    with enable_mc_dropout(model):
        for _ in range(n_samples):
            out = model(x, causal=causal)
            samples.append(out.detach())

    # (n_samples, B, S, F)
    samples_t = torch.stack(samples, dim=0)
    mean = samples_t.mean(dim=0)
    std = samples_t.std(dim=0)
    return mean, std, samples_t


# ---------------------------------------------------------------------------
# 3. Hypo / hyper probability helpers
# ---------------------------------------------------------------------------

def hypo_probability(
    mean_glucose_mgdl: torch.Tensor,
    std_glucose_mgdl: torch.Tensor,
    threshold_mgdl: float = 70.0,
) -> torch.Tensor:
    """P(glucose < threshold) assuming Gaussian per timestep.

    Parameters
    ----------
    mean_glucose_mgdl : Tensor (B, SeqLen) or (B, SeqLen, 1)
        Mean predicted glucose in **mg/dL**.
    std_glucose_mgdl : Tensor, same shape
        Standard deviation in mg/dL.
    threshold_mgdl : float
        Hypoglycaemia threshold (default 70 mg/dL).

    Returns
    -------
    Tensor of probabilities, same leading shape squeezed to (B, SeqLen).
    """
    mean = mean_glucose_mgdl.squeeze(-1) if mean_glucose_mgdl.dim() == 3 else mean_glucose_mgdl
    std = std_glucose_mgdl.squeeze(-1) if std_glucose_mgdl.dim() == 3 else std_glucose_mgdl
    # Clamp std to avoid division by zero
    std = std.clamp(min=1e-6)
    z = (threshold_mgdl - mean) / std
    return _norm_cdf(z)


def hyper_probability(
    mean_glucose_mgdl: torch.Tensor,
    std_glucose_mgdl: torch.Tensor,
    threshold_mgdl: float = 180.0,
) -> torch.Tensor:
    """P(glucose > threshold) assuming Gaussian per timestep.

    Returns Tensor of shape (B, SeqLen).
    """
    mean = mean_glucose_mgdl.squeeze(-1) if mean_glucose_mgdl.dim() == 3 else mean_glucose_mgdl
    std = std_glucose_mgdl.squeeze(-1) if std_glucose_mgdl.dim() == 3 else std_glucose_mgdl
    std = std.clamp(min=1e-6)
    z = (threshold_mgdl - mean) / std
    return 1.0 - _norm_cdf(z)


# ---------------------------------------------------------------------------
# 4. Prediction intervals
# ---------------------------------------------------------------------------

def prediction_interval(
    mean: torch.Tensor,
    std: torch.Tensor,
    confidence: float = 0.95,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Symmetric Gaussian prediction interval.

    Returns (lower, upper) tensors with same shape as *mean*.
    """
    # Two-tailed z for the given confidence level
    alpha = 1.0 - confidence
    # Inverse CDF via the relationship: z = sqrt(2) * erfinv(1 - alpha)
    z = math.sqrt(2.0) * torch.erfinv(torch.tensor(1.0 - alpha)).item()
    lower = mean - z * std
    upper = mean + z * std
    return lower, upper


# ---------------------------------------------------------------------------
# 5. High-level safety forecast
# ---------------------------------------------------------------------------

@torch.no_grad()
def mc_forecast_with_safety(
    model: nn.Module,
    x: torch.Tensor,
    n_samples: int = 50,
    hypo_thresh: float = 70.0,
    hyper_thresh: float = 180.0,
    causal: bool = True,
    confidence: float = 0.95,
    safety_p_hypo_limit: float = 0.05,
) -> Dict[str, torch.Tensor]:
    """Full MC-Dropout forecast with safety annotations.

    Returns a dict with keys:

    * ``mean_glucose_mgdl``  (B, SeqLen)
    * ``std_glucose_mgdl``   (B, SeqLen)
    * ``p_hypo``             (B, SeqLen)
    * ``p_hyper``            (B, SeqLen)
    * ``ci_lower``           (B, SeqLen)
    * ``ci_upper``           (B, SeqLen)
    * ``is_safe``            (B,) — True when **all** timesteps have P(hypo) < limit
    """
    mean_norm, std_norm, _ = mc_predict(model, x, n_samples=n_samples, causal=causal)

    # Extract glucose channel and denormalize to mg/dL
    mean_g = mean_norm[..., IDX_GLUCOSE] * GLUCOSE_SCALE
    std_g = std_norm[..., IDX_GLUCOSE] * GLUCOSE_SCALE

    p_hypo = hypo_probability(mean_g, std_g, threshold_mgdl=hypo_thresh)
    p_hyper = hyper_probability(mean_g, std_g, threshold_mgdl=hyper_thresh)
    ci_lo, ci_hi = prediction_interval(mean_g, std_g, confidence=confidence)

    # Safe iff no timestep exceeds the hypo probability limit
    is_safe = (p_hypo < safety_p_hypo_limit).all(dim=-1)  # (B,)

    return {
        'mean_glucose_mgdl': mean_g,
        'std_glucose_mgdl': std_g,
        'p_hypo': p_hypo,
        'p_hyper': p_hyper,
        'ci_lower': ci_lo,
        'ci_upper': ci_hi,
        'is_safe': is_safe,
    }
