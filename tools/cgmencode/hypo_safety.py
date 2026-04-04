"""
hypo_safety.py — Hypoglycemia safety module for CGM glucose forecasting.

Provides asymmetric loss functions, 2-stage classifier+forecaster pipeline,
and safety-focused evaluation metrics. Built on findings from:
  - EXP-136: 2-stage prototype (classifier F1=0.745, forecast MAE=12.3 in hypo)
  - EXP-248: Per-patient FT + hypo weight=3 achieves 7.8 hypo MAE

Clinical motivation: Hypo range (< 70 mg/dL) MAE is 39.8 — 2.54× worse than
overall 10.59. Missed hypos are safety-critical; false alarms are tolerable.
"""

import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from .schema import NORMALIZATION_SCALES, FUTURE_UNKNOWN_CHANNELS
from .experiment_lib import (
    create_model, mask_future_channels, get_device, batch_to_device,
    set_seed, load_checkpoint,
)


GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']  # 400.0
HYPO_THRESHOLD_MGDL = 70.0
HYPO_THRESHOLD_NORM = HYPO_THRESHOLD_MGDL / GLUCOSE_SCALE


class AsymmetricHypoLoss(nn.Module):
    """Weighted MSE that penalizes missed hypos more than false alarms.

    When true glucose is below `threshold`, prediction errors are weighted
    by `miss_weight`. When true glucose is above threshold, errors are
    weighted by `false_alarm_weight`.

    Compatible with train_forecast() loss interface (accepts pred, target tensors).
    """

    def __init__(self, threshold=HYPO_THRESHOLD_NORM,
                 miss_weight=5.0, false_alarm_weight=1.0):
        super().__init__()
        self.threshold = threshold
        self.miss_weight = miss_weight
        self.false_alarm_weight = false_alarm_weight

    def forward(self, pred, target):
        """
        Args:
            pred: (B, T, 1) predicted glucose (normalized)
            target: (B, T, 1) true glucose (normalized)
        Returns:
            Scalar weighted MSE loss
        """
        sq_err = (pred - target) ** 2
        weights = torch.where(
            target < self.threshold,
            torch.tensor(self.miss_weight, device=pred.device),
            torch.tensor(self.false_alarm_weight, device=pred.device),
        )
        return (weights * sq_err).mean()


def train_hypo_classifier(model, train_ds, val_ds, save_path,
                          horizon_steps=6, threshold_mgdl=HYPO_THRESHOLD_MGDL,
                          label='hypo-clf', lr=1e-3, epochs=50,
                          patience=15, batch_size=32):
    """Train a binary classifier: "will glucose go below threshold in next horizon?"

    Uses the forecast model's glucose predictions to derive a binary label.
    Optimized for high sensitivity (≥ 95%) by threshold tuning on validation set.

    Args:
        model: CGMGroupedEncoder instance
        train_ds: TensorDataset with (x,) windows
        val_ds: TensorDataset with (x,) windows
        save_path: Where to save best checkpoint
        horizon_steps: How many future steps to check (6 = 30 min at 5-min intervals)
        threshold_mgdl: Hypo threshold in mg/dL
        label: Training log label
        lr, epochs, patience, batch_size: Training hyperparams

    Returns:
        dict with best_sensitivity, best_specificity, optimal_threshold, val_auc
    """
    device = get_device()
    model.to(device)
    threshold_norm = threshold_mgdl / GLUCOSE_SCALE

    # Derive binary labels from glucose in future window
    def _get_labels(x, half):
        future_glucose = x[:, half:half + horizon_steps, 0]  # channel 0 = glucose
        return (future_glucose.min(dim=1).values < threshold_norm).float()

    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    bce = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([5.0], device=device))
    best_val, stale = float('inf'), 0

    for ep in range(epochs):
        model.train()
        for b in DataLoader(train_ds, batch_size=batch_size, shuffle=True):
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            labels = _get_labels(x, half)

            x_in = x.clone()
            mask_future_channels(x_in, half)
            pred = model(x_in, causal=True)
            if isinstance(pred, dict):
                pred = pred['forecast']
            # Use mean of predicted future glucose as logit proxy
            pred_future_mean = pred[:, half:half + horizon_steps, 0].mean(dim=1)
            # Invert: lower predicted glucose → higher hypo probability
            logits = -pred_future_mean * 10.0

            loss = bce(logits, labels)
            opt.zero_grad()
            loss.backward()
            opt.step()

        # Validation
        model.eval()
        all_logits, all_labels = [], []
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in DataLoader(val_ds, batch_size=64):
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                labels = _get_labels(x, half)
                x_in = x.clone()
                mask_future_channels(x_in, half)
                pred = model(x_in, causal=True)
                if isinstance(pred, dict):
                    pred = pred['forecast']
                pred_future_mean = pred[:, half:half + horizon_steps, 0].mean(dim=1)
                logits = -pred_future_mean * 10.0
                loss = bce(logits, labels)
                vtl += loss.item() * x.size(0)
                vn += x.size(0)
                all_logits.append(logits.cpu())
                all_labels.append(labels.cpu())

        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best_val:
            best_val, stale = vl, 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({'model_state': model.state_dict(), 'epoch': ep,
                         'val_loss': vl, 'label': label}, save_path)
        else:
            stale += 1
        if patience > 0 and stale >= patience:
            break

    if os.path.exists(save_path):
        load_checkpoint(model, save_path)

    # Find optimal threshold for ≥ 95% sensitivity
    all_logits = torch.cat(all_logits)
    all_labels = torch.cat(all_labels)
    probs = torch.sigmoid(all_logits)

    best_sens, best_spec, best_thresh = 0.0, 0.0, 0.5
    for thresh in np.arange(0.05, 0.96, 0.05):
        preds = (probs >= thresh).float()
        pos = all_labels == 1
        neg = all_labels == 0
        sens = preds[pos].mean().item() if pos.any() else 0.0
        spec = (1.0 - preds[neg].mean().item()) if neg.any() else 0.0
        if sens >= 0.95 and spec > best_spec:
            best_sens, best_spec, best_thresh = sens, spec, float(thresh)
        elif sens >= best_sens and best_sens < 0.95:
            best_sens, best_spec, best_thresh = sens, spec, float(thresh)

    return {
        'best_sensitivity': round(best_sens, 4),
        'best_specificity': round(best_spec, 4),
        'optimal_threshold': round(best_thresh, 3),
        'val_loss': round(best_val, 6),
    }


def train_hypo_forecaster(model, train_ds, val_ds, save_path,
                          label='hypo-forecaster', miss_weight=5.0,
                          lr=1e-3, epochs=50, patience=15, batch_size=32):
    """Train a specialized forecaster optimized for hypo-range accuracy.

    Uses AsymmetricHypoLoss to penalize missed hypos more heavily.

    Args:
        model: CGMGroupedEncoder instance
        train_ds, val_ds: TensorDatasets
        save_path: Checkpoint path
        miss_weight: Penalty multiplier for hypo-range errors
        label, lr, epochs, patience, batch_size: Training params

    Returns:
        (best_val_loss, epochs_run)
    """
    device = get_device()
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    loss_fn = AsymmetricHypoLoss(miss_weight=miss_weight)
    best_val, stale = float('inf'), 0

    for ep in range(epochs):
        model.train()
        for b in DataLoader(train_ds, batch_size=batch_size, shuffle=True):
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            x_in = x.clone()
            mask_future_channels(x_in, half)
            pred = model(x_in, causal=True)
            if isinstance(pred, dict):
                pred = pred['forecast']
            loss = loss_fn(pred[:, half:, :1], x[:, half:, :1])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in DataLoader(val_ds, batch_size=64):
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                x_in = x.clone()
                mask_future_channels(x_in, half)
                pred = model(x_in, causal=True)
                if isinstance(pred, dict):
                    pred = pred['forecast']
                vtl += loss_fn(pred[:, half:, :1],
                               x[:, half:, :1]).item() * x.size(0)
                vn += x.size(0)
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best_val:
            best_val, stale = vl, 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({'model_state': model.state_dict(), 'epoch': ep,
                         'val_loss': vl, 'label': label}, save_path)
        else:
            stale += 1
        if patience > 0 and stale >= patience:
            break

    if os.path.exists(save_path):
        load_checkpoint(model, save_path)
    return best_val, ep + 1


class HypoSafetyEnsemble(nn.Module):
    """2-stage hypo safety pipeline: classifier gates → forecaster refines.

    Stage 1: Classifier predicts hypo probability.
    Stage 2: If probability exceeds threshold, forecaster ensemble provides
             refined glucose prediction for the hypo range.

    This follows the EXP-136 architecture with EXP-248 weighting improvements.
    """

    def __init__(self, classifier, forecaster_ensemble, clf_threshold=0.5):
        """
        Args:
            classifier: Model used for hypo probability estimation
            forecaster_ensemble: List of models trained with AsymmetricHypoLoss
            clf_threshold: Probability threshold for triggering forecaster
        """
        super().__init__()
        self.classifier = classifier
        self.forecasters = nn.ModuleList(forecaster_ensemble)
        self.clf_threshold = clf_threshold

    def predict(self, x, horizon_steps=6):
        """
        Args:
            x: (B, T, C) input window (already masked)
            horizon_steps: Steps to check for hypo

        Returns:
            dict with:
                hypo_probability: (B,) probability of hypo in horizon
                predicted_glucose: (B, T, 1) ensemble mean forecast
                is_hypo_alert: (B,) bool — whether classifier triggers
        """
        half = x.shape[1] // 2
        # Stage 1: Classify
        self.classifier.eval()
        with torch.no_grad():
            clf_pred = self.classifier(x, causal=True)
            if isinstance(clf_pred, dict):
                clf_pred = clf_pred['forecast']
            future_mean = clf_pred[:, half:half + horizon_steps, 0].mean(dim=1)
            hypo_prob = torch.sigmoid(-future_mean * 10.0)

        is_alert = hypo_prob >= self.clf_threshold

        # Stage 2: Ensemble forecast (always computed for simplicity)
        forecasts = []
        for m in self.forecasters:
            m.eval()
            with torch.no_grad():
                pred = m(x, causal=True)
                if isinstance(pred, dict):
                    pred = pred['forecast']
                forecasts.append(pred[:, :, :1])

        ensemble_pred = torch.stack(forecasts, dim=0).mean(dim=0)

        return {
            'hypo_probability': hypo_prob,
            'predicted_glucose': ensemble_pred,
            'is_hypo_alert': is_alert,
        }


def evaluate_hypo_safety(models, val_ds, thresholds_steps=None,
                         hypo_mgdl=HYPO_THRESHOLD_MGDL, batch_size=64):
    """Compute hypo-specific safety metrics for a set of forecast models.

    Args:
        models: List of forecast models (will be ensembled)
        val_ds: Validation TensorDataset
        thresholds_steps: List of horizon steps to evaluate (default: [6, 12] = 30/60 min)
        hypo_mgdl: Hypo threshold in mg/dL
        batch_size: Eval batch size

    Returns:
        dict with per-horizon metrics:
            hypo_mae: MAE in mg/dL for samples where true glucose < threshold
            sensitivity: fraction of true hypos correctly predicted below threshold
            specificity: fraction of non-hypos correctly predicted above threshold
            lead_time_steps: mean steps before hypo where prediction first drops below threshold
            n_hypo_samples: number of hypo samples evaluated
    """
    if thresholds_steps is None:
        thresholds_steps = [6, 12]  # 30 and 60 min at 5-min intervals

    device = get_device()
    hypo_norm = hypo_mgdl / GLUCOSE_SCALE

    for m in models:
        m.eval()
        m.to(device)

    results = {}
    for hz in thresholds_steps:
        all_pred_g, all_true_g = [], []
        for b in DataLoader(val_ds, batch_size=batch_size):
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2

            # Ensemble prediction
            preds = []
            for m in models:
                x_in = x.clone()
                mask_future_channels(x_in, half)
                with torch.no_grad():
                    p = m(x_in, causal=True)
                    if isinstance(p, dict):
                        p = p['forecast']
                    preds.append(p[:, half:half + hz, 0])
            ens_pred = torch.stack(preds, dim=0).mean(dim=0)  # (B, hz)
            true_g = x[:, half:half + hz, 0]  # (B, hz)
            all_pred_g.append(ens_pred.cpu())
            all_true_g.append(true_g.cpu())

        all_pred = torch.cat(all_pred_g, dim=0)  # (N, hz)
        all_true = torch.cat(all_true_g, dim=0)

        # Per-sample: true minimum glucose in horizon
        true_min = all_true.min(dim=1).values  # (N,)
        pred_min = all_pred.min(dim=1).values

        is_hypo = true_min < hypo_norm
        n_hypo = is_hypo.sum().item()

        if n_hypo > 0:
            # MAE in mg/dL for hypo samples
            hypo_mae = ((pred_min[is_hypo] - true_min[is_hypo]).abs()
                        * GLUCOSE_SCALE).mean().item()
            # Sensitivity: does predicted min also go below threshold?
            sens = (pred_min[is_hypo] < hypo_norm).float().mean().item()
        else:
            hypo_mae = float('nan')
            sens = float('nan')

        not_hypo = ~is_hypo
        if not_hypo.any():
            spec = (pred_min[not_hypo] >= hypo_norm).float().mean().item()
        else:
            spec = float('nan')

        # Lead time: for true hypos, how many steps before the actual hypo
        # does the prediction first go below threshold?
        lead_times = []
        if n_hypo > 0:
            hypo_indices = torch.where(is_hypo)[0]
            for idx in hypo_indices:
                pred_below = all_pred[idx] < hypo_norm
                true_below = all_true[idx] < hypo_norm
                if pred_below.any() and true_below.any():
                    first_pred = pred_below.nonzero(as_tuple=True)[0][0].item()
                    first_true = true_below.nonzero(as_tuple=True)[0][0].item()
                    lead_times.append(first_true - first_pred)

        results[f'{hz * 5}min'] = {
            'hypo_mae_mgdl': round(hypo_mae, 2) if not np.isnan(hypo_mae) else None,
            'sensitivity': round(sens, 4) if not np.isnan(sens) else None,
            'specificity': round(spec, 4) if not np.isnan(spec) else None,
            'lead_time_steps': round(float(np.mean(lead_times)), 1) if lead_times else None,
            'n_hypo_samples': n_hypo,
            'n_total_samples': len(all_pred),
        }

    return results
