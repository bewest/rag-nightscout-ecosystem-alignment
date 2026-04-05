"""
clinical_loss.py — Clinically-weighted loss functions for glucose forecasting.

Implements asymmetric zone and slope costs inspired by GluPredKit's
weighted_ridge.py (Wolff et al., JOSS 2024, DOI:10.21105/joss.06904).

The core insight: MSE treats "off by 20 at BG=300" the same as "off by 20
at BG=50."  In clinical practice, hypo errors are life-threatening (minutes)
while hyper errors cause chronic damage (days). This module provides loss
functions that encode that asymmetry.

Usage in experiments:
    from .clinical_loss import ClinicalZoneLoss, train_forecast_clinical

    loss_fn = ClinicalZoneLoss(left_weight=19.0, target_mg=105.0)
    best, epochs = train_forecast_clinical(
        model, train_ds, val_ds, save_path, label,
        loss_fn=loss_fn, scale=400.0,
    )
"""

import math
import torch
import torch.nn as nn


class ClinicalZoneLoss(nn.Module):
    """Asymmetric zone + slope weighted MSE for glucose forecasting.

    Computes per-sample weights based on:
      1. Zone cost: log-scale distance from target, with hypo weighted
         ``left_weight`` times more than hyper (default 19:1).
      2. Slope cost: penalizes rapid glucose changes, especially drops
         toward hypoglycemia.

    The final loss is:  weighted_MSE + alpha * L1

    All computations work on *denormalized* mg/dL values internally but
    accept normalized tensors as input (scaled by ``scale`` factor).

    Args:
        left_weight: Penalty multiplier for BG < target (hypo side).
        right_weight: Penalty multiplier for BG >= target (hyper side).
        target_mg: Target glucose in mg/dL (zone cost center).
        constant: Scaling constant for zone cost (Clarke-grid derived).
        alpha: Weight for L1 regularization term.
        scale: Normalization factor (glucose_mg = normalized * scale).
    """

    def __init__(
        self,
        left_weight: float = 19.0,
        right_weight: float = 1.0,
        target_mg: float = 105.0,
        constant: float = 32.917,
        alpha: float = 0.1,
        scale: float = 400.0,
    ):
        super().__init__()
        self.left_weight = left_weight
        self.right_weight = right_weight
        self.target_mg = target_mg
        self.constant = constant
        self.alpha = alpha
        self.scale = scale
        # Pre-compute log(target) for zone cost
        self.log_target = math.log(max(target_mg, 1.0))
        # Conversion factor mg/dL → mmol/L for slope cost
        self.k_mmol = 18.0182

    def zone_cost(self, bg_mg: torch.Tensor) -> torch.Tensor:
        """Asymmetric log-scale zone cost in mg/dL space.

        Returns per-element cost tensor (same shape as input).
        """
        bg_clamped = bg_mg.clamp(1.0, 600.0)
        log_diff_sq = (torch.log(bg_clamped) - self.log_target) ** 2

        weight = torch.where(
            bg_clamped < self.target_mg,
            torch.tensor(self.left_weight, device=bg_mg.device, dtype=bg_mg.dtype),
            torch.tensor(self.right_weight, device=bg_mg.device, dtype=bg_mg.dtype),
        )
        return self.constant * weight * log_diff_sq

    def slope_cost(self, bg_mg: torch.Tensor, delta_mg: torch.Tensor) -> torch.Tensor:
        """Velocity-dependent cost penalizing rapid glucose changes.

        Operates in mmol/L space per GluPredKit convention.
        Penalizes rapid drops more heavily near hypo range.
        """
        bg_mmol = bg_mg / self.k_mmol
        delta_mmol = delta_mg / self.k_mmol

        a = bg_mmol.clamp(max=15.0)  # rising cost factor
        b = (15.0 - bg_mmol).clamp(min=0.0)  # falling cost factor (higher near hypo)

        delta_sq = delta_mmol ** 2
        sign = torch.sign(delta_mmol)

        # Rising: a * delta^2;  Falling: 2*b * delta^2
        cost = ((sign + 1) / 2) * a * delta_sq + ((-sign + 1) / 2) * 2 * b * delta_sq
        return cost

    def forward(
        self,
        pred_norm: torch.Tensor,
        target_norm: torch.Tensor,
    ) -> torch.Tensor:
        """Compute clinical zone loss.

        Args:
            pred_norm: Predicted glucose, normalized (B, T, 1) or (B, T).
            target_norm: Target glucose, normalized (same shape).

        Returns:
            Scalar loss value.
        """
        # Denormalize to mg/dL for clinical weight computation
        target_mg = target_norm * self.scale
        pred_mg = pred_norm * self.scale

        # Zone cost from true glucose (weights error by clinical danger zone)
        zone_w = self.zone_cost(target_mg)

        # Slope cost from consecutive glucose differences in target
        if target_mg.dim() >= 2 and target_mg.shape[-2] > 1:
            # Compute delta along time dimension (dim=-2)
            delta = torch.zeros_like(target_mg)
            delta[..., 1:, :] = target_mg[..., 1:, :] - target_mg[..., :-1, :]
            slope_w = self.slope_cost(target_mg, delta)
        else:
            slope_w = torch.zeros_like(zone_w)

        # Combined weight: zone + slope + 1 (ensure minimum weight of 1)
        weights = zone_w + slope_w + 1.0
        # Normalize weights to mean=1 to keep gradient scale comparable to MSE
        weights = weights / (weights.mean() + 1e-8)

        # Weighted MSE + alpha * L1
        sq_err = (pred_norm - target_norm) ** 2
        weighted_mse = (weights * sq_err).mean()
        l1 = torch.abs(pred_norm - target_norm).mean()

        return weighted_mse + self.alpha * l1


def train_forecast_clinical(
    model, train_ds, val_ds, save_path, label,
    loss_fn=None, lr=1e-3, epochs=50, batch=32, patience=15,
    weight_decay=1e-5, lr_patience=5, forecast_steps=None,
    scale=400.0,
):
    """Forecast training with pluggable loss function.

    Drop-in replacement for ``train_forecast()`` that accepts a custom
    loss function.  If ``loss_fn`` is None, falls back to standard MSE
    (identical behavior to ``train_forecast``).

    The custom loss receives (pred_norm, target_norm) — both normalized
    tensors of shape (B, T_future, 1).

    Returns (best_val_loss, epochs_run).
    """
    import os
    from torch.utils.data import DataLoader
    from .experiment_lib import (
        get_device, batch_to_device, mask_future_channels, load_checkpoint,
    )

    device = get_device()
    model.to(device)
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)

    # Default to MSE if no clinical loss provided
    if loss_fn is None:
        crit = nn.MSELoss()
        use_clinical = False
    else:
        crit = loss_fn
        use_clinical = True

    best = float('inf')
    stale = 0

    def _forecast_step(batch_data, backward=False):
        x = batch_to_device(batch_data[0], device)
        half = x.shape[1] - forecast_steps if forecast_steps else x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        pred = model(x_in, causal=True)
        # Extract future glucose: (B, T_future, 1)
        pred_future = pred[:, half:, :1]
        target_future = x[:, half:, :1]
        loss = crit(pred_future, target_future)
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    loss_name = type(crit).__name__
    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _forecast_step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _forecast_step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label, 'loss_fn': loss_name,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e} ({loss_name}){mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        load_checkpoint(model, save_path)
    return best, ep + 1
