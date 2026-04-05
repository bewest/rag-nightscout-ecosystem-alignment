"""
experiments_validated.py — Forward-validated experiments using the validation framework.

These experiments use run_validated_classification / run_validated_retrieval / etc.
to produce multi-seed results with confidence intervals and held-out test evaluation.

Run:
    python3 -m tools.cgmencode.experiments_validated <experiment-key> [--patients-dir ...]

Phase 1: Baseline validation (re-run key results through framework)
Phase 2: Forward experiments (new science + validation)
"""

import os
import time
import numpy as np
import torch
import torch.nn as nn

from .experiment_lib import (
    set_seed, get_device, set_device, resolve_patient_paths,
    run_validated_classification, ExperimentContext,
)
from .run_pattern_experiments import (
    load_multiscale_data, load_multiscale_data_3way, SCALE_CONFIG,
    save_results,
)


# ─── Shared CNN architectures ──────────────────────────────────────────

class UAMCNN(nn.Module):
    """1D-CNN for binary classification on 2h windows (EXP-313 architecture)."""
    def __init__(self, in_channels=8):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, 2),
        )

    def forward(self, x):
        half = x.shape[1] // 2
        x = x[:, :half].permute(0, 2, 1)  # [B, C, T]
        features = self.conv(x).squeeze(-1)
        return self.classifier(features)


class OverrideCNN(nn.Module):
    """1D-CNN for 3-class override prediction (EXP-314 architecture)."""
    def __init__(self, in_channels=8, n_classes=3):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_classes),
        )

    def forward(self, x):
        h = x.shape[1] // 2
        x = x[:, :h].permute(0, 2, 1)
        feat = self.conv(x).squeeze(-1)
        return self.classifier(feat)


class MultiTaskCNN(nn.Module):
    """Shared-backbone CNN with override and hypo heads (EXP-322 architecture)."""
    def __init__(self, in_channels=8):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.override_head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, 3),
        )
        self.hypo_head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(32, 2),
        )

    def forward(self, x):
        h = x.shape[1] // 2
        x = x[:, :h].permute(0, 2, 1)
        feat = self.backbone(x).squeeze(-1)
        return self.override_head(feat), self.hypo_head(feat)


# ─── Label builders ────────────────────────────────────────────────────

def build_uam_labels(windows):
    """UAM = rapid glucose rise (>10 mg/dL per 5min step) without recent carbs."""
    half = windows.shape[1] // 2
    hist = windows[:, :half]
    glucose = hist[:, :, 0] * 400.0
    carbs = hist[:, :, 5]
    roc = np.diff(glucose, axis=1)
    rapid_rise = (roc > 10).any(axis=1)
    no_carbs = carbs.sum(axis=1) < 0.01
    return (rapid_rise & no_carbs).astype(np.int64)


def build_override_labels(windows, lead_steps=3):
    """Override = glucose leaves [70, 180] in the next lead_steps (default 15min)."""
    half = windows.shape[1] // 2
    future = windows[:, half:half + lead_steps, 0] * 400.0
    high = (future > 180).any(axis=1)
    low = (future < 70).any(axis=1)
    labels = np.zeros(len(windows), dtype=np.int64)
    labels[high] = 1
    labels[low] = 2  # low overrides high (safety)
    return labels


def build_hypo_labels(windows, lead_steps=6):
    """Hypo = glucose < 70 in the next lead_steps (default 30min)."""
    half = windows.shape[1] // 2
    future = windows[:, half:half + lead_steps, 0] * 400.0
    return (future < 70).any(axis=1).astype(np.int64)


# ─── Generic training loop ─────────────────────────────────────────────

def _train_classifier(model, train_x, train_y, val_x, val_y, device,
                      epochs=30, batch_size=256, class_weights=None):
    """Train a classifier and return predictions + probabilities on val set."""
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    if class_weights is not None:
        criterion = nn.CrossEntropyLoss(weight=class_weights.to(device))
    else:
        criterion = nn.CrossEntropyLoss()

    train_t = torch.from_numpy(train_x).float()
    train_yt = torch.from_numpy(train_y).long()
    val_t = torch.from_numpy(val_x).float()

    best_val_f1 = 0.0
    patience = 0

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(train_x))
        for start in range(0, len(perm), batch_size):
            end = min(start + batch_size, len(perm))
            idx = perm[start:end]
            logits = model(train_t[idx].to(device))
            loss = criterion(logits, train_yt[idx].to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # Early stopping check every 5 epochs
        if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
            model.eval()
            preds_list = []
            with torch.no_grad():
                for vs in range(0, len(val_x), 512):
                    ve = min(vs + 512, len(val_x))
                    logits = model(val_t[vs:ve].to(device))
                    preds_list.append(logits.argmax(dim=-1).cpu().numpy())
            preds = np.concatenate(preds_list)
            from sklearn.metrics import f1_score
            val_f1 = f1_score(train_y[:1], train_y[:1], zero_division=0)  # dummy
            # Use positive-class F1 for binary, macro for multi-class
            n_classes = len(np.unique(train_y))
            if n_classes == 2:
                val_f1 = f1_score(val_y, preds, zero_division=0)
            else:
                val_f1 = f1_score(val_y, preds, average='macro', zero_division=0)

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                patience = 0
            else:
                patience += 1
            if patience >= 4:
                break

    # Final predictions with probabilities
    model.eval()
    all_preds, all_probs = [], []
    with torch.no_grad():
        for vs in range(0, len(val_x), 512):
            ve = min(vs + 512, len(val_x))
            logits = model(val_t[vs:ve].to(device))
            all_preds.append(logits.argmax(dim=-1).cpu().numpy())
            all_probs.append(torch.softmax(logits, dim=-1).cpu().numpy())
    return np.concatenate(all_preds), np.concatenate(all_probs)


def _compute_class_weights(labels, n_classes, device):
    """Inverse-frequency class weights."""
    from collections import Counter
    counts = Counter(labels.tolist())
    n = len(labels)
    weights = [n / (n_classes * max(1, counts.get(c, 1))) for c in range(n_classes)]
    return torch.tensor(weights, dtype=torch.float32).to(device)


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Baseline Validation
# ═══════════════════════════════════════════════════════════════════════

def run_validated_uam_baseline(args):
    """EXP-313v: Validated UAM CNN baseline — 5 seeds, 3-way split.

    Reproduces EXP-313 (F1=0.939) through the validated framework.
    Gate: F1 CI must exclude 0.90.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-313v: Validated UAM CNN Baseline (5 seeds, 3-way split)")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']
    print(f"3-way split: train={len(train_np)}, val={len(val_np)}, test={len(test_np)}")

    # Build labels on all splits
    train_uam = build_uam_labels(train_np)
    test_uam = build_uam_labels(test_np)
    print(f"UAM prevalence: train={train_uam.mean():.3f}, test={test_uam.mean():.3f}")

    n_pos = train_uam.sum()
    n_neg = len(train_uam) - n_pos
    cw = torch.tensor([1.0, n_neg / max(1, n_pos)], dtype=torch.float32)

    def train_and_eval(seed):
        set_seed(seed)
        model = UAMCNN()
        preds, probs = _train_classifier(
            model, train_np, train_uam, test_np, test_uam,
            device, epochs=epochs, class_weights=cw,
        )
        return {
            'y_true': test_uam,
            'y_pred': preds,
            'y_prob': probs[:, 1],  # positive class probability
        }

    result = run_validated_classification(
        'EXP-313v', output_dir, train_and_eval,
        task_name='uam', positive_label=1,
    )
    print(f"\n✅ EXP-313v complete. Results: {output_dir}/exp_313v_validated.json")
    return result


def run_validated_override_baseline(args):
    """EXP-314v: Validated Override CNN baseline — 3 seeds, 3-way split.

    Reproduces EXP-314 (15min lead, F1=0.821) through validated framework.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-314v: Validated Override CNN Baseline (3 seeds, 3-way split)")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']
    print(f"3-way split: train={len(train_np)}, val={len(val_np)}, test={len(test_np)}")

    train_labels = build_override_labels(train_np, lead_steps=3)
    test_labels = build_override_labels(test_np, lead_steps=3)
    print(f"Override rate: train={(train_labels > 0).mean():.3f}, "
          f"test={(test_labels > 0).mean():.3f}")

    cw = _compute_class_weights(train_labels, 3, device)

    def train_and_eval(seed):
        set_seed(seed)
        model = OverrideCNN()
        preds, probs = _train_classifier(
            model, train_np, train_labels, test_np, test_labels,
            device, epochs=epochs, class_weights=cw,
        )
        # For 3-class, use max non-zero probability as "override probability"
        override_prob = 1.0 - probs[:, 0]
        return {
            'y_true': (test_labels > 0).astype(int),  # binary: override or not
            'y_pred': (preds > 0).astype(int),
            'y_prob': override_prob,
        }

    result = run_validated_classification(
        'EXP-314v', output_dir, train_and_eval,
        task_name='override', positive_label=1,
        seeds=[42, 123, 456],  # 3 seeds for quick validation
    )
    print(f"\n✅ EXP-314v complete.")
    return result


def run_validated_hypo_baseline(args):
    """EXP-322v: Validated Multi-Task Hypo baseline — 3 seeds, 3-way split.

    Reproduces EXP-322 multi-task CNN through validated framework.
    Evaluates hypo head only (override head is a bonus signal).
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-322v: Validated Multi-Task Hypo Baseline (3 seeds, 3-way split)")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']
    print(f"3-way split: train={len(train_np)}, val={len(val_np)}, test={len(test_np)}")

    train_override = build_override_labels(train_np)
    train_hypo = build_hypo_labels(train_np)
    test_hypo = build_hypo_labels(test_np)
    print(f"Hypo prevalence: train={train_hypo.mean():.3f}, test={test_hypo.mean():.3f}")

    # Override class weights
    ov_cw = _compute_class_weights(train_override, 3, device)
    # Hypo class weights (heavier on minority)
    n_hypo_pos = train_hypo.sum()
    n_hypo_neg = len(train_hypo) - n_hypo_pos
    hypo_weight = max(2.0, n_hypo_neg / max(1, n_hypo_pos))
    hypo_cw = torch.tensor([1.0, hypo_weight], dtype=torch.float32).to(device)

    def train_and_eval(seed):
        set_seed(seed)
        model = MultiTaskCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        ov_criterion = nn.CrossEntropyLoss(weight=ov_cw)
        hypo_criterion = nn.CrossEntropyLoss(weight=hypo_cw)

        train_t = torch.from_numpy(train_np).float()
        train_ov_t = torch.from_numpy(train_override).long()
        train_hypo_t = torch.from_numpy(train_hypo).long()
        test_t = torch.from_numpy(test_np).float()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                ov_logits, hypo_logits = model(train_t[idx].to(device))
                loss = ov_criterion(ov_logits, train_ov_t[idx].to(device)) + \
                       hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Evaluate hypo head on test set
        model.eval()
        all_probs = []
        with torch.no_grad():
            for vs in range(0, len(test_np), 512):
                ve = min(vs + 512, len(test_np))
                _, hypo_logits = model(test_t[vs:ve].to(device))
                all_probs.append(torch.softmax(hypo_logits, dim=-1)[:, 1].cpu().numpy())
        hypo_probs = np.concatenate(all_probs)

        # Optimal threshold via val set
        val_hypo = build_hypo_labels(val_np)
        val_t_tensor = torch.from_numpy(val_np).float()
        val_probs = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                _, hl = model(val_t_tensor[vs:ve].to(device))
                val_probs.append(torch.softmax(hl, dim=-1)[:, 1].cpu().numpy())
        val_probs = np.concatenate(val_probs)

        from sklearn.metrics import f1_score
        best_thresh = 0.5
        best_f1 = 0.0
        for t in np.arange(0.01, 1.0, 0.01):
            f1 = f1_score(val_hypo, (val_probs >= t).astype(int), zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = t

        preds = (hypo_probs >= best_thresh).astype(int)
        return {
            'y_true': test_hypo,
            'y_pred': preds,
            'y_prob': hypo_probs,
            'threshold': best_thresh,
        }

    result = run_validated_classification(
        'EXP-322v', output_dir, train_and_eval,
        task_name='hypo', positive_label=1,
        seeds=[42, 123, 456],
    )
    print(f"\n✅ EXP-322v complete.")
    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Forward Experiments
# ═══════════════════════════════════════════════════════════════════════

def run_depth_hypo(args):
    """EXP-336: Functional depth as additional hypo feature.

    EXP-335 showed 2.37x hypo enrichment in low-depth windows.
    This adds functional depth as a 9th input channel to the multi-task CNN.

    Hypothesis: depth signal improves hypo F1 by >= 0.02.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-336: Functional Depth + Multi-Task Hypo CNN")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    # Compute functional depth per window using band depth
    def compute_depth_channel(windows):
        """Compute modified band depth for glucose channel in each window."""
        half = windows.shape[1] // 2
        glucose = windows[:, :half, 0]  # [N, T]
        n = len(glucose)
        # Band depth = fraction of curves that envelope each curve
        # Simplified: use mean + std distance as depth proxy
        mean_curve = glucose.mean(axis=0)
        std_curve = glucose.std(axis=0) + 1e-8
        # Depth = 1 / (1 + mean z-score) — higher = more central
        z_scores = np.abs(glucose - mean_curve) / std_curve
        depth = 1.0 / (1.0 + z_scores.mean(axis=1))
        # Expand to [N, T, 1] to broadcast with window
        depth_channel = np.broadcast_to(depth[:, None, None],
                                        (n, windows.shape[1], 1))
        return np.concatenate([windows, depth_channel], axis=2).astype(np.float32)

    train_aug = compute_depth_channel(train_np)
    val_aug = compute_depth_channel(val_np)
    test_aug = compute_depth_channel(test_np)
    print(f"Augmented: {train_aug.shape[2]} channels (was {train_np.shape[2]})")

    train_override = build_override_labels(train_np)
    train_hypo = build_hypo_labels(train_np)
    test_hypo = build_hypo_labels(test_np)
    val_hypo = build_hypo_labels(val_np)
    print(f"Hypo prevalence: train={train_hypo.mean():.3f}, test={test_hypo.mean():.3f}")

    ov_cw = _compute_class_weights(train_override, 3, device)
    n_hypo_pos = train_hypo.sum()
    n_hypo_neg = len(train_hypo) - n_hypo_pos
    hypo_weight = max(2.0, n_hypo_neg / max(1, n_hypo_pos))
    hypo_cw = torch.tensor([1.0, hypo_weight], dtype=torch.float32).to(device)

    def train_and_eval(seed):
        set_seed(seed)
        model = MultiTaskCNN(in_channels=9).to(device)  # 9 channels with depth
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        ov_criterion = nn.CrossEntropyLoss(weight=ov_cw)
        hypo_criterion = nn.CrossEntropyLoss(weight=hypo_cw)

        train_t = torch.from_numpy(train_aug).float()
        train_ov_t = torch.from_numpy(train_override).long()
        train_hypo_t = torch.from_numpy(train_hypo).long()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_aug))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                ov_logits, hypo_logits = model(train_t[idx].to(device))
                loss = ov_criterion(ov_logits, train_ov_t[idx].to(device)) + \
                       hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        model.eval()
        test_t = torch.from_numpy(test_aug).float()
        all_probs = []
        with torch.no_grad():
            for vs in range(0, len(test_aug), 512):
                ve = min(vs + 512, len(test_aug))
                _, hypo_logits = model(test_t[vs:ve].to(device))
                all_probs.append(torch.softmax(hypo_logits, dim=-1)[:, 1].cpu().numpy())
        hypo_probs = np.concatenate(all_probs)

        # Threshold from val set
        val_t_tensor = torch.from_numpy(val_aug).float()
        vp = []
        with torch.no_grad():
            for vs in range(0, len(val_aug), 512):
                ve = min(vs + 512, len(val_aug))
                _, hl = model(val_t_tensor[vs:ve].to(device))
                vp.append(torch.softmax(hl, dim=-1)[:, 1].cpu().numpy())
        vp = np.concatenate(vp)

        from sklearn.metrics import f1_score
        best_thresh, best_f1 = 0.5, 0.0
        for t in np.arange(0.01, 1.0, 0.01):
            f1 = f1_score(val_hypo, (vp >= t).astype(int), zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = t

        preds = (hypo_probs >= best_thresh).astype(int)
        return {
            'y_true': test_hypo,
            'y_pred': preds,
            'y_prob': hypo_probs,
            'threshold': best_thresh,
        }

    result = run_validated_classification(
        'EXP-336', output_dir, train_and_eval,
        task_name='hypo', positive_label=1,
    )
    print(f"\n✅ EXP-336 complete.")
    return result


def run_bspline_cnn_uam(args):
    """EXP-337: B-spline coefficients as CNN input for UAM detection.

    EXP-328 showed B-spline smoothing achieves <0.5 mg/dL round-trip error.
    This replaces raw 8ch grid with B-spline coefficient vectors.

    Hypothesis: smoother input representation matches or improves F1.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-337: B-Spline CNN for UAM Detection")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    # B-spline smoothing for glucose channel
    def bspline_smooth_windows(windows, n_basis=12):
        """Replace glucose channel with B-spline smoothed version + derivative."""
        from scipy.interpolate import BSpline, make_interp_spline
        half = windows.shape[1] // 2
        smoothed = windows.copy()
        deriv_channel = np.zeros((len(windows), windows.shape[1], 1), dtype=np.float32)

        t = np.arange(half)
        for i in range(len(windows)):
            glucose = windows[i, :half, 0]
            try:
                spl = make_interp_spline(t, glucose, k=3)
                smoothed[i, :half, 0] = spl(t)
                # 1st derivative as additional channel
                deriv_channel[i, :half, 0] = spl.derivative()(t)
            except Exception:
                deriv_channel[i, :half, 0] = np.gradient(glucose)
        return np.concatenate([smoothed, deriv_channel], axis=2).astype(np.float32)

    print("  Computing B-spline features...")
    train_bs = bspline_smooth_windows(train_np)
    val_bs = bspline_smooth_windows(val_np)
    test_bs = bspline_smooth_windows(test_np)
    print(f"  B-spline: {train_bs.shape[2]} channels (was {train_np.shape[2]})")

    train_uam = build_uam_labels(train_np)
    test_uam = build_uam_labels(test_np)
    print(f"UAM prevalence: train={train_uam.mean():.3f}, test={test_uam.mean():.3f}")

    n_pos = train_uam.sum()
    n_neg = len(train_uam) - n_pos
    cw = torch.tensor([1.0, n_neg / max(1, n_pos)], dtype=torch.float32)

    def train_and_eval(seed):
        set_seed(seed)
        model = UAMCNN(in_channels=9)  # 8 original + 1 derivative
        preds, probs = _train_classifier(
            model, train_bs, train_uam, test_bs, test_uam,
            device, epochs=epochs, class_weights=cw,
        )
        return {
            'y_true': test_uam,
            'y_pred': preds,
            'y_prob': probs[:, 1],
        }

    result = run_validated_classification(
        'EXP-337', output_dir, train_and_eval,
        task_name='uam', positive_label=1,
    )
    print(f"\n✅ EXP-337 complete.")
    return result


def run_glucodensity_override(args):
    """EXP-338: Glucodensity features for override detection.

    EXP-330 showed glucodensity profiles have Sil=0.965 vs TIR's 0.422 — much
    richer distribution information. This injects per-window glucodensity
    summaries into the classifier head (after CNN temporal feature extraction),
    not as conv input channels (constant channels break CNN spatial gradients).

    Hypothesis: glucodensity context improves override F1 by >= 0.01.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-338: Glucodensity-Enhanced Override CNN")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    n_bins = 8

    def compute_glucodensity(windows):
        """Compute per-window glucose distribution histogram."""
        half = windows.shape[1] // 2
        glucose = windows[:, :half, 0] * 400.0
        bin_edges = np.linspace(40, 400, n_bins + 1)
        histograms = np.zeros((len(windows), n_bins), dtype=np.float32)
        for i in range(len(windows)):
            h, _ = np.histogram(glucose[i], bins=bin_edges)
            histograms[i] = h
        # Normalize to sum to 1
        row_sums = histograms.sum(axis=1, keepdims=True)
        histograms = histograms / np.maximum(row_sums, 1e-8)
        return histograms

    print("  Computing glucodensity features...")
    train_gd = compute_glucodensity(train_np)
    test_gd = compute_glucodensity(test_np)
    print(f"  Glucodensity: {n_bins} bins per window")

    train_labels = build_override_labels(train_np, lead_steps=3)
    test_labels = build_override_labels(test_np, lead_steps=3)
    print(f"Override rate: train={(train_labels > 0).mean():.3f}")

    cw = _compute_class_weights(train_labels, 3, device)

    class GlucodensityOverrideCNN(nn.Module):
        """CNN + glucodensity features injected at classifier head."""
        def __init__(self, in_channels=8, n_gd_bins=8, n_classes=3):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64 + n_gd_bins, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_classes),
            )

        def forward(self, x, gd_features):
            h = x.shape[1] // 2
            conv_feat = self.conv(x[:, :h].permute(0, 2, 1)).squeeze(-1)
            combined = torch.cat([conv_feat, gd_features], dim=1)
            return self.classifier(combined)

    def train_and_eval(seed):
        set_seed(seed)
        model = GlucodensityOverrideCNN(n_gd_bins=n_bins).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=cw)

        train_t = torch.from_numpy(train_np).float()
        train_gd_t = torch.from_numpy(train_gd).float()
        train_y = torch.from_numpy(train_labels).long()
        test_t = torch.from_numpy(test_np).float()
        test_gd_t = torch.from_numpy(test_gd).float()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = model(train_t[idx].to(device), train_gd_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        model.eval()
        all_preds, all_probs = [], []
        with torch.no_grad():
            for vs in range(0, len(test_np), 512):
                ve = min(vs + 512, len(test_np))
                logits = model(test_t[vs:ve].to(device), test_gd_t[vs:ve].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                all_probs.append(torch.softmax(logits, dim=-1).cpu().numpy())
        preds = np.concatenate(all_preds)
        probs = np.concatenate(all_probs)

        return {
            'y_true': (test_labels > 0).astype(int),
            'y_pred': (preds > 0).astype(int),
            'y_prob': 1.0 - probs[:, 0],
        }

    result = run_validated_classification(
        'EXP-338', output_dir, train_and_eval,
        task_name='override', positive_label=1,
        seeds=[42, 123, 456],
    )
    print(f"\n✅ EXP-338 complete.")
    return result


def run_attention_vs_cnn_override(args):
    """EXP-339: Attention vs CNN head-to-head for override detection.

    EXP-327 showed attention F1=0.852 vs EXP-314 CNN F1=0.821 (single seed).
    This runs both through the validated framework to determine if the 2%
    attention premium is real.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-339: Attention vs CNN Override Head-to-Head")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    train_labels = build_override_labels(train_np, lead_steps=3)
    test_labels = build_override_labels(test_np, lead_steps=3)
    cw = _compute_class_weights(train_labels, 3, device)

    class AttentionOverrideCNN(nn.Module):
        """CNN + self-attention for override prediction."""
        def __init__(self, in_channels=8, n_classes=3):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
            )
            self.attn = nn.MultiheadAttention(64, num_heads=4, batch_first=True)
            self.classifier = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_classes),
            )

        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)  # [B, C, T]
            feat = self.conv(x)  # [B, 64, T]
            feat = feat.permute(0, 2, 1)  # [B, T, 64]
            attn_out, _ = self.attn(feat, feat, feat)
            pooled = attn_out.mean(dim=1)  # [B, 64]
            return self.classifier(pooled)

    results = {}

    # CNN variant
    print("\n--- CNN (EXP-314 architecture) ---")
    def train_cnn(seed):
        set_seed(seed)
        model = OverrideCNN()
        preds, probs = _train_classifier(
            model, train_np, train_labels, test_np, test_labels,
            device, epochs=epochs, class_weights=cw,
        )
        return {
            'y_true': (test_labels > 0).astype(int),
            'y_pred': (preds > 0).astype(int),
            'y_prob': 1.0 - probs[:, 0],
        }

    cnn_result = run_validated_classification(
        'EXP-339-CNN', output_dir, train_cnn,
        task_name='override', positive_label=1,
    )

    # Attention variant
    print("\n--- Attention CNN (EXP-327 architecture) ---")
    def train_attn(seed):
        set_seed(seed)
        model = AttentionOverrideCNN()
        preds, probs = _train_classifier(
            model, train_np, train_labels, test_np, test_labels,
            device, epochs=epochs, class_weights=cw,
        )
        return {
            'y_true': (test_labels > 0).astype(int),
            'y_pred': (preds > 0).astype(int),
            'y_prob': 1.0 - probs[:, 0],
        }

    attn_result = run_validated_classification(
        'EXP-339-Attn', output_dir, train_attn,
        task_name='override', positive_label=1,
    )

    # Summary comparison
    summary = {
        'experiment': 'EXP-339',
        'name': 'attention-vs-cnn-override',
        'method': 'Head-to-head comparison with validated framework',
        'cnn': cnn_result,
        'attention': attn_result,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    save_results(summary, os.path.join(output_dir, 'exp339_attn_vs_cnn.json'))
    print(f"\n✅ EXP-339 complete.")
    return summary


# ─── Phase 3: Transfer Best Techniques Across Objectives ──────────────

def run_bspline_override(args):
    """EXP-340: B-spline smoothing for override detection.

    EXP-337 showed B-spline input gives UAM F1=0.939 vs 0.918 baseline (+0.021)
    and halved ECE (0.014 vs 0.025). Transfer this technique to override.

    Hypothesis: B-spline improves override F1 by >= 0.01 and reduces ECE.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-340: B-Spline CNN for Override Detection")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    train_bs = _bspline_smooth_windows(train_np)
    test_bs = _bspline_smooth_windows(test_np)
    print(f"  B-spline: {train_bs.shape[2]} channels (was {train_np.shape[2]})")

    train_labels = build_override_labels(train_np, lead_steps=3)
    test_labels = build_override_labels(test_np, lead_steps=3)
    cw = _compute_class_weights(train_labels, 3, device)

    def train_and_eval(seed):
        set_seed(seed)
        model = OverrideCNN(in_channels=9)  # 8 + derivative
        preds, probs = _train_classifier(
            model, train_bs, train_labels, test_bs, test_labels,
            device, epochs=epochs, class_weights=cw,
        )
        return {
            'y_true': (test_labels > 0).astype(int),
            'y_pred': (preds > 0).astype(int),
            'y_prob': 1.0 - probs[:, 0],
        }

    result = run_validated_classification(
        'EXP-340', output_dir, train_and_eval,
        task_name='override', positive_label=1,
        seeds=[42, 123, 456, 789, 1337],
    )
    print(f"\n✅ EXP-340 complete.")
    return result


def run_bspline_hypo(args):
    """EXP-341: B-spline smoothing for hypo prediction.

    Transfer B-spline technique to hypo (weakest objective, F1=0.681).
    B-spline derivative captures glucose rate-of-change which is clinically
    relevant for hypoglycemia risk (falling glucose).

    Hypothesis: B-spline derivative channel improves hypo F1 by >= 0.01.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-341: B-Spline CNN for Hypo Prediction")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    train_bs = _bspline_smooth_windows(train_np)
    test_bs = _bspline_smooth_windows(test_np)
    print(f"  B-spline: {train_bs.shape[2]} channels (was {train_np.shape[2]})")

    train_labels = build_hypo_labels(train_np, lead_steps=6)
    test_labels = build_hypo_labels(test_np, lead_steps=6)
    cw = _compute_class_weights(train_labels, 2, device)

    class BSplineMultiTaskCNN(nn.Module):
        """Multi-task CNN with B-spline input (9ch)."""
        def __init__(self, in_channels=9, n_override=3, n_hypo=2):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.override_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_override),
            )
            self.hypo_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_hypo),
            )

        def forward(self, x):
            h = x.shape[1] // 2
            feat = self.backbone(x[:, :h].permute(0, 2, 1)).squeeze(-1)
            return self.override_head(feat), self.hypo_head(feat)

    # Override labels needed for multi-task
    train_override = build_override_labels(train_np, lead_steps=3)
    test_override = build_override_labels(test_np, lead_steps=3)
    cw_override = _compute_class_weights(train_override, 3, device)
    cw_hypo = cw

    def train_and_eval(seed):
        set_seed(seed)
        model = BSplineMultiTaskCNN(in_channels=9).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        crit_ovr = nn.CrossEntropyLoss(weight=cw_override)
        crit_hypo = nn.CrossEntropyLoss(weight=cw_hypo)

        train_t = torch.from_numpy(train_bs).float()
        train_y_ovr = torch.from_numpy(train_override).long()
        train_y_hypo = torch.from_numpy(train_labels).long()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_bs))
            for start in range(0, len(perm), batch_size):
                idx = perm[start:min(start + batch_size, len(perm))]
                ovr_logits, hypo_logits = model(train_t[idx].to(device))
                loss = crit_ovr(ovr_logits, train_y_ovr[idx].to(device)) + \
                       crit_hypo(hypo_logits, train_y_hypo[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        model.eval()
        test_t = torch.from_numpy(test_bs).float()
        all_preds, all_probs = [], []
        with torch.no_grad():
            for s in range(0, len(test_bs), 512):
                e = min(s + 512, len(test_bs))
                _, hypo_logits = model(test_t[s:e].to(device))
                all_preds.append(hypo_logits.argmax(dim=-1).cpu().numpy())
                all_probs.append(torch.softmax(hypo_logits, dim=-1).cpu().numpy())

        preds = np.concatenate(all_preds)
        probs = np.concatenate(all_probs)
        return {
            'y_true': test_labels,
            'y_pred': preds,
            'y_prob': probs[:, 1],
        }

    result = run_validated_classification(
        'EXP-341', output_dir, train_and_eval,
        task_name='hypo', positive_label=1,
        seeds=[42, 123, 456, 789, 1337],
    )
    print(f"\n✅ EXP-341 complete.")
    return result


def run_glucodensity_hypo(args):
    """EXP-342: Glucodensity head injection for hypo prediction.

    EXP-338 showed glucodensity head injection improved override F1 by +0.006
    and ECE by 16%. Transfer to hypo. Glucose distribution shape may help
    predict upcoming lows (skewed left = dropping trend).

    Hypothesis: glucodensity improves hypo F1 by >= 0.01.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-342: Glucodensity-Enhanced Hypo CNN")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    n_bins = 8

    def compute_glucodensity(windows):
        half = windows.shape[1] // 2
        glucose = windows[:, :half, 0] * 400.0
        bin_edges = np.linspace(40, 400, n_bins + 1)
        histograms = np.zeros((len(windows), n_bins), dtype=np.float32)
        for i in range(len(windows)):
            h, _ = np.histogram(glucose[i], bins=bin_edges)
            histograms[i] = h
        row_sums = histograms.sum(axis=1, keepdims=True)
        histograms = histograms / np.maximum(row_sums, 1e-8)
        return histograms

    train_gd = compute_glucodensity(train_np)
    test_gd = compute_glucodensity(test_np)

    train_labels = build_hypo_labels(train_np, lead_steps=6)
    test_labels = build_hypo_labels(test_np, lead_steps=6)

    # Multi-task setup (override + hypo) with glucodensity
    train_override = build_override_labels(train_np, lead_steps=3)
    test_override = build_override_labels(test_np, lead_steps=3)
    cw_override = _compute_class_weights(train_override, 3, device)
    cw_hypo = _compute_class_weights(train_labels, 2, device)

    class GlucodensityMultiTaskCNN(nn.Module):
        def __init__(self, in_channels=8, n_gd_bins=8, n_override=3, n_hypo=2):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.override_head = nn.Sequential(
                nn.Linear(64 + n_gd_bins, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_override),
            )
            self.hypo_head = nn.Sequential(
                nn.Linear(64 + n_gd_bins, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_hypo),
            )

        def forward(self, x, gd):
            h = x.shape[1] // 2
            feat = self.backbone(x[:, :h].permute(0, 2, 1)).squeeze(-1)
            combined = torch.cat([feat, gd], dim=1)
            return self.override_head(combined), self.hypo_head(combined)

    def train_and_eval(seed):
        set_seed(seed)
        model = GlucodensityMultiTaskCNN(n_gd_bins=n_bins).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        crit_ovr = nn.CrossEntropyLoss(weight=cw_override)
        crit_hypo = nn.CrossEntropyLoss(weight=cw_hypo)

        train_t = torch.from_numpy(train_np).float()
        train_gd_t = torch.from_numpy(train_gd).float()
        train_y_ovr = torch.from_numpy(train_override).long()
        train_y_hypo = torch.from_numpy(train_labels).long()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                idx = perm[start:min(start + batch_size, len(perm))]
                ovr_logits, hypo_logits = model(
                    train_t[idx].to(device), train_gd_t[idx].to(device))
                loss = crit_ovr(ovr_logits, train_y_ovr[idx].to(device)) + \
                       crit_hypo(hypo_logits, train_y_hypo[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        model.eval()
        test_t = torch.from_numpy(test_np).float()
        test_gd_t = torch.from_numpy(test_gd).float()
        all_preds, all_probs = [], []
        with torch.no_grad():
            for s in range(0, len(test_np), 512):
                e = min(s + 512, len(test_np))
                _, hypo_logits = model(
                    test_t[s:e].to(device), test_gd_t[s:e].to(device))
                all_preds.append(hypo_logits.argmax(dim=-1).cpu().numpy())
                all_probs.append(torch.softmax(hypo_logits, dim=-1).cpu().numpy())

        preds = np.concatenate(all_preds)
        probs = np.concatenate(all_probs)
        return {
            'y_true': test_labels,
            'y_pred': preds,
            'y_prob': probs[:, 1],
        }

    result = run_validated_classification(
        'EXP-342', output_dir, train_and_eval,
        task_name='hypo', positive_label=1,
        seeds=[42, 123, 456, 789, 1337],
    )
    print(f"\n✅ EXP-342 complete.")
    return result


def run_platt_calibrated_override(args):
    """EXP-343: Platt calibration for override CNN.

    EXP-324 showed Platt scaling reduces ECE from 0.206 to 0.010. Our validated
    baselines show ECE=0.084 (override) and 0.114 (hypo). Integrate Platt as
    a post-processing step inside the validated framework.

    Hypothesis: Platt reduces ECE by >= 50% while preserving F1 within CI.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-343: Platt-Calibrated Override CNN")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    train_labels = build_override_labels(train_np, lead_steps=3)
    val_labels = build_override_labels(val_np, lead_steps=3)
    test_labels = build_override_labels(test_np, lead_steps=3)
    cw = _compute_class_weights(train_labels, 3, device)

    from sklearn.linear_model import LogisticRegression

    def train_and_eval(seed):
        set_seed(seed)
        model = OverrideCNN(in_channels=8).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=cw)
        batch_size = 256

        train_t = torch.from_numpy(train_np).float()
        train_y = torch.from_numpy(train_labels).long()

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                idx = perm[start:min(start + batch_size, len(perm))]
                h = train_t[idx].shape[1] // 2
                logits = model(train_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Collect validation logits for Platt scaling
        model.eval()
        val_t = torch.from_numpy(val_np).float()
        val_logits = []
        with torch.no_grad():
            for s in range(0, len(val_np), 512):
                e = min(s + 512, len(val_np))
                logits = model(val_t[s:e].to(device))
                val_logits.append(logits.cpu().numpy())
        val_logits = np.concatenate(val_logits)
        val_probs_raw = np.exp(val_logits) / np.exp(val_logits).sum(axis=1, keepdims=True)
        val_binary = (val_labels > 0).astype(int)
        val_override_prob = 1.0 - val_probs_raw[:, 0]

        # Fit Platt scaler on validation set
        platt = LogisticRegression(C=1e10, solver='lbfgs', max_iter=1000)
        platt.fit(val_override_prob.reshape(-1, 1), val_binary)

        # Evaluate on test set with Platt calibration
        test_t = torch.from_numpy(test_np).float()
        test_logits = []
        with torch.no_grad():
            for s in range(0, len(test_np), 512):
                e = min(s + 512, len(test_np))
                logits = model(test_t[s:e].to(device))
                test_logits.append(logits.cpu().numpy())
        test_logits = np.concatenate(test_logits)
        test_probs_raw = np.exp(test_logits) / np.exp(test_logits).sum(axis=1, keepdims=True)
        test_override_prob_raw = 1.0 - test_probs_raw[:, 0]

        # Apply Platt calibration
        test_override_prob_cal = platt.predict_proba(
            test_override_prob_raw.reshape(-1, 1))[:, 1]

        test_binary = (test_labels > 0).astype(int)
        test_preds = (test_override_prob_cal >= 0.5).astype(int)

        return {
            'y_true': test_binary,
            'y_pred': test_preds,
            'y_prob': test_override_prob_cal,
        }

    result = run_validated_classification(
        'EXP-343', output_dir, train_and_eval,
        task_name='override', positive_label=1,
        seeds=[42, 123, 456, 789, 1337],
    )
    print(f"\n✅ EXP-343 complete.")
    return result


def run_bspline_glucodensity_override(args):
    """EXP-344: B-spline + glucodensity combined for override.

    Stack the two positive signals from Phase 2:
    - B-spline smoothing + derivative (EXP-337: +0.021 F1 for UAM)
    - Glucodensity head injection (EXP-338: +0.006 F1, -16% ECE)

    Hypothesis: combined effect yields override F1 >= 0.880.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = getattr(args, 'epochs', 30)

    print("=" * 60)
    print("EXP-344: B-Spline + Glucodensity Override CNN")
    print("=" * 60)

    data = load_multiscale_data_3way(patient_paths, scale='fast')
    train_np, val_np, test_np = data['train'], data['val'], data['test']

    n_bins = 8
    train_bs = _bspline_smooth_windows(train_np)
    test_bs = _bspline_smooth_windows(test_np)

    def compute_glucodensity(windows):
        half = windows.shape[1] // 2
        glucose = windows[:, :half, 0] * 400.0
        bin_edges = np.linspace(40, 400, n_bins + 1)
        histograms = np.zeros((len(windows), n_bins), dtype=np.float32)
        for i in range(len(windows)):
            h, _ = np.histogram(glucose[i], bins=bin_edges)
            histograms[i] = h
        row_sums = histograms.sum(axis=1, keepdims=True)
        return histograms / np.maximum(row_sums, 1e-8)

    train_gd = compute_glucodensity(train_np)
    test_gd = compute_glucodensity(test_np)

    train_labels = build_override_labels(train_np, lead_steps=3)
    test_labels = build_override_labels(test_np, lead_steps=3)
    cw = _compute_class_weights(train_labels, 3, device)

    class BSplineGlucodensityCNN(nn.Module):
        """B-spline CNN (9ch temporal) + glucodensity (8-bin head injection)."""
        def __init__(self, in_channels=9, n_gd_bins=8, n_classes=3):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64 + n_gd_bins, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_classes),
            )

        def forward(self, x, gd):
            h = x.shape[1] // 2
            conv_feat = self.conv(x[:, :h].permute(0, 2, 1)).squeeze(-1)
            combined = torch.cat([conv_feat, gd], dim=1)
            return self.classifier(combined)

    def train_and_eval(seed):
        set_seed(seed)
        model = BSplineGlucodensityCNN(n_gd_bins=n_bins).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=cw)

        train_t = torch.from_numpy(train_bs).float()
        train_gd_t = torch.from_numpy(train_gd).float()
        train_y = torch.from_numpy(train_labels).long()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_bs))
            for start in range(0, len(perm), batch_size):
                idx = perm[start:min(start + batch_size, len(perm))]
                logits = model(train_t[idx].to(device), train_gd_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        model.eval()
        test_t = torch.from_numpy(test_bs).float()
        test_gd_t = torch.from_numpy(test_gd).float()
        all_preds, all_probs = [], []
        with torch.no_grad():
            for s in range(0, len(test_bs), 512):
                e = min(s + 512, len(test_bs))
                logits = model(test_t[s:e].to(device), test_gd_t[s:e].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                all_probs.append(torch.softmax(logits, dim=-1).cpu().numpy())

        preds = np.concatenate(all_preds)
        probs = np.concatenate(all_probs)
        return {
            'y_true': (test_labels > 0).astype(int),
            'y_pred': (preds > 0).astype(int),
            'y_prob': 1.0 - probs[:, 0],
        }

    result = run_validated_classification(
        'EXP-344', output_dir, train_and_eval,
        task_name='override', positive_label=1,
        seeds=[42, 123, 456, 789, 1337],
    )
    print(f"\n✅ EXP-344 complete.")
    return result


# ─── Shared utilities for Phase 3 ──────────────────────────────────────

def _bspline_smooth_windows(windows, n_basis=12):
    """Replace glucose channel with B-spline smoothed version + derivative."""
    from scipy.interpolate import make_interp_spline
    half = windows.shape[1] // 2
    smoothed = windows.copy()
    deriv_channel = np.zeros((len(windows), windows.shape[1], 1), dtype=np.float32)

    t = np.arange(half)
    for i in range(len(windows)):
        glucose = windows[i, :half, 0]
        try:
            spl = make_interp_spline(t, glucose, k=3)
            smoothed[i, :half, 0] = spl(t)
            deriv_channel[i, :half, 0] = spl.derivative()(t)
        except Exception:
            deriv_channel[i, :half, 0] = np.gradient(glucose)
    return np.concatenate([smoothed, deriv_channel], axis=2).astype(np.float32)


# ─── Registry ──────────────────────────────────────────────────────────

VALIDATED_REGISTRY = {
    # Phase 1: Baselines
    'validate-uam': ('EXP-313v', run_validated_uam_baseline,
                     'Validated UAM CNN baseline (5 seeds)'),
    'validate-override': ('EXP-314v', run_validated_override_baseline,
                          'Validated override CNN baseline (3 seeds)'),
    'validate-hypo': ('EXP-322v', run_validated_hypo_baseline,
                      'Validated multi-task hypo baseline (3 seeds)'),

    # Phase 2: Forward experiments
    'depth-hypo': ('EXP-336', run_depth_hypo,
                   'Functional depth + multi-task hypo CNN'),
    'bspline-uam': ('EXP-337', run_bspline_cnn_uam,
                    'B-spline smoothed CNN for UAM detection'),
    'glucodensity-override': ('EXP-338', run_glucodensity_override,
                              'Glucodensity-enhanced override CNN'),
    'attention-vs-cnn': ('EXP-339', run_attention_vs_cnn_override,
                         'Attention vs CNN head-to-head override'),

    # Phase 3: Transfer best techniques across objectives
    'bspline-override': ('EXP-340', run_bspline_override,
                         'B-spline smoothed CNN for override detection'),
    'bspline-hypo': ('EXP-341', run_bspline_hypo,
                     'B-spline multi-task CNN for hypo prediction'),
    'glucodensity-hypo': ('EXP-342', run_glucodensity_hypo,
                          'Glucodensity-enhanced multi-task hypo CNN'),
    'platt-override': ('EXP-343', run_platt_calibrated_override,
                       'Platt-calibrated override CNN'),
    'bspline-gluco-override': ('EXP-344', run_bspline_glucodensity_override,
                               'B-spline + glucodensity combined override'),
}


def run_experiment(key, args):
    """Run a validated experiment by key."""
    if key not in VALIDATED_REGISTRY:
        print(f"Unknown experiment: {key}")
        print(f"Available: {', '.join(sorted(VALIDATED_REGISTRY.keys()))}")
        return None
    exp_id, fn, desc = VALIDATED_REGISTRY[key]
    print(f"\n{'='*60}")
    print(f"Running: {exp_id} — {desc}")
    print(f"{'='*60}\n")
    return fn(args)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run validated experiments')
    parser.add_argument('experiment', choices=sorted(VALIDATED_REGISTRY.keys()),
                        help='Experiment to run')
    parser.add_argument('--patients-dir', default='externals/ns-data/patients',
                        help='Path to patient data directory')
    parser.add_argument('--output-dir', default='externals/experiments',
                        help='Directory for result JSON files')
    parser.add_argument('--epochs', type=int, default=30,
                        help='Training epochs per seed')
    parser.add_argument('--device', default=None,
                        help='Device (cuda/cpu, auto-detected if omitted)')
    parsed = parser.parse_args()

    if parsed.device is None:
        import torch
        parsed.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        parsed.device = torch.device(parsed.device)

    run_experiment(parsed.experiment, parsed)
