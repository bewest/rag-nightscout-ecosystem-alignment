#!/usr/bin/env python3
"""EXP-369 through EXP-376: Normalization & Conditioning for Classification

Next-phase experiments exploring untried normalization, conditioning, and
feature engineering techniques for episode-scale classification tasks.
Complements the forecasting thread (v3/v4) and architecture thread (arch_12h).

EXP-369 — ISF-Normalized Glucose for Classification (LOO)
  Replace BG/400 with (BG - target) / ISF per patient.
  Hypothesis: Reduces LOO generalization gap ≥1% on override + hypo.
  Prior: ISF norm helped forecasting (EXP-361/v3) at short horizons.

EXP-370 — Per-Patient Z-Score + Raw Dual-Channel
  Two glucose channels: raw BG/400 + per-patient z-score((BG-μ)/σ).
  Hypothesis: Z-score captures deviation from personal baseline; raw preserves
  absolute level for hypo detection. Should help cross-patient transfer.

EXP-371 — Functional Depth as Hypo Feature
  Inject Modified Band Depth (from fda_features.py) as scalar feature
  at classifier head. Low depth = unusual glucose trajectory = hypo risk.
  Hypothesis: Functional depth enriches hypo prediction (Q1 depth=33.7%
  hypo prevalence vs Q4=0.3%, EXP-335).

EXP-372 — Glucodensity at Classifier Head
  8-bin glucose histogram (40-400 mg/dL) injected after CNN pooling.
  Captures distribution shape that CNN may miss in sequential scan.
  Hypothesis: Glucodensity at head adds +0.5% override F1 (cf. Sil=+0.508
  vs TIR, EXP-330).

EXP-373 — Multi-Seed Future PK Validation (5 seeds with CIs)
  Replicate EXP-366 (dilated TCN + future PK, current best MAE=26.7) with
  5 seeds and bootstrap CIs to confirm breakthrough is robust.

EXP-374 — Cumulative Glucose Load Features at 3-Day Scale
  Running integrals: glucose_auc, insulin_total, carb_total over 12h/24h/72h.
  New channels for 3-day (576-step) windows.
  Hypothesis: Cumulative features capture metabolic load, enabling drift detection.

EXP-375 — Multi-Rate EMA Channels
  Exponential moving averages at α = 0.1 (trend), 0.3 (medium), 0.7 (fast).
  Replace raw glucose with 3 EMA channels — built-in multi-scale decomposition.
  Hypothesis: EMA channels provide scale-adaptive smoothing CNN can select from.

EXP-376 — STL Decomposition Channels
  Seasonal-Trend decomposition using LOESS on 3-day windows (period=288 = 24h).
  Produces trend + seasonal + residual channels replacing raw glucose.
  Hypothesis: Clean trend separation enables drift vs event discrimination.

Usage:
    python tools/cgmencode/exp_normalization_conditioning.py --experiment 369 --quick
    python tools/cgmencode/exp_normalization_conditioning.py --experiment all --device cuda
    python tools/cgmencode/exp_normalization_conditioning.py --experiment 369 370 371 372
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ─── Constants ───

WINDOW_SIZE_2H = 24       # 2h at 5min
WINDOW_SIZE_12H = 144     # 12h at 5min
WINDOW_SIZE_3D = 864      # 3 days at 5min (72h)
STRIDE_2H = 6
STRIDE_12H = 36
STRIDE_3D = 144           # 12h stride for 3d windows
GLUCOSE_SCALE = 400.0
GLUCOSE_CLIP = (40.0, 400.0)

SEEDS = [42, 123, 456]
SEEDS_QUICK = [42]
SEEDS_5 = [42, 123, 456, 789, 2024]
QUICK_PATIENTS = 4
QUICK_EPOCHS = 20
QUICK_PATIENCE = 6
FULL_EPOCHS = 60
FULL_PATIENCE = 12

EXPERIMENTS = {
    369: 'ISF-Normalized Glucose for Classification',
    370: 'Per-Patient Z-Score + Raw Dual-Channel',
    371: 'Functional Depth as Hypo Feature',
    372: 'Glucodensity at Classifier Head',
    373: 'Multi-Seed Future PK Validation',
    374: 'Cumulative Glucose Load at 3-Day Scale',
    375: 'Multi-Rate EMA Channels',
    376: 'STL Decomposition Channels',
}

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'


# ─── Data Loading ───

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir()
                   if d.is_dir() and (d / 'training').exists()])


def load_patient_profile(train_dir):
    """Load ISF, target BG, and CR from patient profile."""
    profile_path = os.path.join(train_dir, 'profile.json')
    if not os.path.exists(profile_path):
        return {'isf': None, 'target_bg': 100.0, 'cr': None}
    try:
        with open(profile_path) as f:
            profile = json.load(f)
        store = profile.get('store', {})
        default_profile = store.get('Default', store.get(next(iter(store), ''), {}))
        # ISF
        sens = default_profile.get('sens', [])
        isf = None
        if sens:
            isf_values = [s.get('value', 0) for s in sens]
            isf = float(np.mean([v for v in isf_values if v > 0]))
            if isf < 15:  # mmol/L → mg/dL
                isf *= 18.0182
        # Target BG
        target = default_profile.get('target_low', 100)
        if isinstance(target, list):
            target = target[0].get('value', 100) if target else 100
        if target < 15:  # mmol/L
            target *= 18.0182
        # CR
        carbratio = default_profile.get('carbratio', [])
        cr = None
        if carbratio:
            cr_values = [c.get('value', 0) for c in carbratio]
            cr = float(np.mean([v for v in cr_values if v > 0]))
        return {'isf': isf, 'target_bg': float(target), 'cr': cr}
    except Exception:
        return {'isf': None, 'target_bg': 100.0, 'cr': None}


def load_base_data(patients_dir, max_patients=None):
    """Load per-patient grids with profile info. Returns list of dicts."""
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]

    patients = []
    for pd in patient_dirs:
        train_dir = str(pd / 'training')
        try:
            grid = build_nightscout_grid(train_dir)
            if grid is None or len(grid) < 100:
                continue
            pk = build_continuous_pk_features(train_dir)
            if pk is None:
                continue
            profile = load_patient_profile(train_dir)
            n = min(len(grid), len(pk))
            patients.append({
                'name': pd.name,
                'grid': grid[:n],
                'pk': pk[:n],
                'profile': profile,
            })
        except Exception as e:
            print(f"  Skip {pd.name}: {e}")
    return patients


# ─── Feature Engineering ───

def isf_normalize_glucose(glucose, isf, target_bg=100.0):
    """Transform glucose to physiological units: (BG - target) / ISF."""
    if isf is None or isf <= 0:
        return glucose / GLUCOSE_SCALE  # fallback
    return (glucose - target_bg) / isf


def patient_zscore_glucose(glucose, mu, sigma):
    """Per-patient z-score normalization."""
    if sigma is None or sigma < 1.0:
        return glucose / GLUCOSE_SCALE  # fallback
    return (glucose - mu) / sigma


def compute_ema(series, alpha):
    """Exponential moving average with given smoothing factor."""
    ema = np.empty_like(series)
    ema[0] = series[0]
    for i in range(1, len(series)):
        if np.isnan(series[i]):
            ema[i] = ema[i-1]
        else:
            ema[i] = alpha * series[i] + (1 - alpha) * ema[i-1]
    return ema


def compute_cumulative_features(glucose, insulin, carbs, window_hrs=[12, 24, 72]):
    """Running cumulative integrals over specified windows.

    Returns array of shape (T, 3*len(window_hrs)):
      glucose_auc_Xh, insulin_total_Xh, carb_total_Xh for each window.
    """
    T = len(glucose)
    n_feats = 3 * len(window_hrs)
    out = np.zeros((T, n_feats), dtype=np.float32)
    for wi, wh in enumerate(window_hrs):
        w_steps = int(wh * 12)  # 12 steps per hour at 5min
        for t in range(T):
            start = max(0, t - w_steps + 1)
            seg_g = glucose[start:t+1]
            seg_i = insulin[start:t+1]
            seg_c = carbs[start:t+1]
            # glucose AUC (mg/dL · hours), normalized
            out[t, wi*3 + 0] = np.nansum(seg_g) * (5/60) / max(wh, 1) / 180.0
            # insulin total (U), normalized
            out[t, wi*3 + 1] = np.nansum(seg_i) / max(wh / 24, 1) / 50.0
            # carb total (g), normalized
            out[t, wi*3 + 2] = np.nansum(seg_c) / max(wh / 24, 1) / 200.0
    return out


def compute_glucodensity(glucose_window, n_bins=8, low=40.0, high=400.0):
    """8-bin normalized histogram of glucose values."""
    valid = glucose_window[~np.isnan(glucose_window)]
    if len(valid) < 5:
        return np.zeros(n_bins, dtype=np.float32)
    hist, _ = np.histogram(valid, bins=n_bins, range=(low, high), density=True)
    hist = hist.astype(np.float32)
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist


def compute_functional_depth(glucose_window, reference_windows=None):
    """Modified Band Depth (simplified) — fraction of reference windows
    that envelope the target window."""
    if reference_windows is None or len(reference_windows) < 10:
        return 0.5  # neutral depth
    target = glucose_window
    n_ref = len(reference_windows)
    count = 0
    n_pairs = 0
    # Simplified: for each pair of reference curves, check if target
    # is between them at every point
    indices = np.random.RandomState(42).choice(n_ref, size=(min(200, n_ref*(n_ref-1)//2), 2))
    for i, j in indices:
        if i == j:
            continue
        r1, r2 = reference_windows[i], reference_windows[j]
        lo = np.minimum(r1, r2)
        hi = np.maximum(r1, r2)
        # proportion of time points where target is inside the band
        inside = np.mean((target >= lo) & (target <= hi))
        count += inside
        n_pairs += 1
    return count / max(n_pairs, 1)


# ─── Window Extraction ───

def extract_windows(patient_data, window_size, stride, feature_fn=None):
    """Extract classification windows with labels.

    feature_fn: optional function(patient_dict, glucose_window, idx) -> extra_features
    Returns: X (windows), y_override, y_hypo, y_prolonged_high
    """
    grid = patient_data['grid']
    glucose_col = 0  # first column is glucose in nightscout grid
    T = len(grid)
    half = window_size // 2

    windows = []
    y_override = []
    y_hypo = []
    y_prolonged_high = []

    for start in range(0, T - window_size, stride):
        window = grid[start:start + window_size].copy()
        glucose = window[:, glucose_col]

        # Skip windows with too many NaNs
        if np.isnan(glucose).mean() > 0.3:
            continue

        # Labels from future half
        future_glucose = glucose[half:]
        valid_future = future_glucose[~np.isnan(future_glucose)]
        if len(valid_future) < 5:
            continue

        # Override: 3-class based on glucose range in future
        mean_bg = np.nanmean(valid_future)
        if mean_bg < 80:
            y_override.append(0)  # low
        elif mean_bg > 180:
            y_override.append(2)  # high
        else:
            y_override.append(1)  # in-range

        # Hypo: any glucose < 70 in future
        y_hypo.append(1 if np.any(valid_future < 70) else 0)

        # Prolonged high: >70% of future above 180
        y_prolonged_high.append(1 if np.mean(valid_future > 180) > 0.7 else 0)

        # Apply feature_fn if provided
        if feature_fn is not None:
            window = feature_fn(patient_data, window, start)

        windows.append(window[:half])  # history only for input

    if not windows:
        return None, None, None, None

    X = np.stack(windows).astype(np.float32)
    return X, np.array(y_override), np.array(y_hypo), np.array(y_prolonged_high)


# ─── Models ───

class DeepCNN(nn.Module):
    """Standard 4-layer 1D-CNN for classification."""
    def __init__(self, in_channels, n_classes=2):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Linear(64, n_classes)

    def forward(self, x):
        h = self.conv(x).squeeze(-1)
        return self.fc(h)


class DeepCNNWithHead(nn.Module):
    """CNN with auxiliary scalar features injected at classifier head."""
    def __init__(self, in_channels, n_scalar, n_classes=2):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_channels, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(
            nn.Linear(64 + n_scalar, 64), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(64, n_classes),
        )

    def forward(self, x_seq, x_scalar):
        h = self.conv(x_seq).squeeze(-1)
        combined = torch.cat([h, x_scalar], dim=-1)
        return self.fc(combined)


# ─── Training Infrastructure ───

def temporal_split(X, *ys, val_fraction=0.2):
    """Chronological split: first 80% train, last 20% val."""
    n = len(X)
    split_idx = int(n * (1 - val_fraction))
    train_parts = [X[:split_idx]] + [y[:split_idx] for y in ys]
    val_parts = [X[split_idx:]] + [y[split_idx:] for y in ys]
    return train_parts, val_parts


def train_classifier(model, train_X, train_y, val_X, val_y, device,
                     epochs=60, patience=12, batch_size=64, lr=1e-3,
                     n_classes=2, scalar_train=None, scalar_val=None):
    """Train with early stopping, return best val metric."""
    if n_classes > 2:
        criterion = nn.CrossEntropyLoss()
    else:
        criterion = nn.CrossEntropyLoss(
            weight=torch.tensor([1.0, train_y.shape[0] / max(train_y.sum(), 1)],
                                dtype=torch.float32).to(device)
        )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=patience//2)

    best_metric = -1
    best_state = None
    wait = 0

    # Prepare data
    t_X = torch.tensor(train_X, dtype=torch.float32).to(device)
    t_y = torch.tensor(train_y, dtype=torch.long).to(device)
    v_X = torch.tensor(val_X, dtype=torch.float32).to(device)
    v_y_np = val_y

    t_scalar = torch.tensor(scalar_train, dtype=torch.float32).to(device) if scalar_train is not None else None
    v_scalar = torch.tensor(scalar_val, dtype=torch.float32).to(device) if scalar_val is not None else None

    for epoch in range(epochs):
        model.train()
        # Shuffle training data
        perm = torch.randperm(len(t_X))
        t_X_shuf = t_X[perm]
        t_y_shuf = t_y[perm]
        t_sc_shuf = t_scalar[perm] if t_scalar is not None else None

        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, len(t_X_shuf), batch_size):
            bx = t_X_shuf[i:i+batch_size]
            by = t_y_shuf[i:i+batch_size]
            if t_sc_shuf is not None:
                bs = t_sc_shuf[i:i+batch_size]
                logits = model(bx, bs)
            else:
                logits = model(bx)
            loss = criterion(logits, by)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1

        # Validate
        model.eval()
        with torch.no_grad():
            if v_scalar is not None:
                v_logits = model(v_X, v_scalar)
            else:
                v_logits = model(v_X)
            v_pred = v_logits.argmax(dim=-1).cpu().numpy()
            v_loss = criterion(v_logits, torch.tensor(v_y_np, dtype=torch.long).to(device)).item()

        scheduler.step(v_loss)

        # Metric
        if n_classes > 2:
            metric = f1_score(v_y_np, v_pred, average='macro', zero_division=0)
        else:
            metric = f1_score(v_y_np, v_pred, zero_division=0)

        if metric > best_metric:
            best_metric = metric
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state:
        model.load_state_dict(best_state)

    # Final evaluation
    model.eval()
    with torch.no_grad():
        if v_scalar is not None:
            v_logits = model(v_X, v_scalar)
        else:
            v_logits = model(v_X)
        v_pred = v_logits.argmax(dim=-1).cpu().numpy()
        v_prob = torch.softmax(v_logits, dim=-1).cpu().numpy()

    results = {'epochs': epoch + 1, 'param_count': sum(p.numel() for p in model.parameters())}
    if n_classes > 2:
        results['f1_macro'] = float(f1_score(v_y_np, v_pred, average='macro', zero_division=0))
        results['f1_per_class'] = [float(x) for x in f1_score(v_y_np, v_pred, average=None, zero_division=0)]
    else:
        results['f1'] = float(f1_score(v_y_np, v_pred, zero_division=0))
        try:
            results['auc'] = float(roc_auc_score(v_y_np, v_prob[:, 1]))
        except ValueError:
            results['auc'] = 0.0
        results['prevalence'] = float(v_y_np.mean())

    return results


# ─── Experiment Runners ───

def default_patients_dir():
    return str(Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients')


def run_exp_369(args, seeds, max_patients, epochs, patience):
    """ISF-Normalized Glucose for Classification.

    Compare BG/400 vs (BG-target)/ISF on override and hypo tasks at 2h and 12h.
    """
    print("\n" + "="*70)
    print("EXP-369: ISF-Normalized Glucose for Classification")
    print("="*70)

    device = args.device
    patients = load_base_data(args.patients_dir, max_patients)
    print(f"  Loaded {len(patients)} patients")

    results = {'experiment': 'EXP-369', 'title': EXPERIMENTS[369], 'seeds': seeds, 'variants': {}}

    for window_label, window_size, stride in [('2h', WINDOW_SIZE_2H, STRIDE_2H),
                                               ('12h', WINDOW_SIZE_12H, STRIDE_12H)]:
        half = window_size // 2
        print(f"\n  --- Window: {window_label} ({window_size} steps, history={half}) ---")

        for norm_mode in ['baseline_bg400', 'isf_normalized']:
            print(f"\n    Normalization: {norm_mode}")

            all_X, all_yo, all_yh = [], [], []
            for p in patients:
                grid = p['grid'].copy()
                glucose = grid[:, 0].copy()
                glucose = np.clip(glucose, *GLUCOSE_CLIP)

                if norm_mode == 'isf_normalized':
                    isf = p['profile']['isf']
                    target = p['profile']['target_bg']
                    grid[:, 0] = isf_normalize_glucose(glucose, isf, target)
                else:
                    grid[:, 0] = glucose / GLUCOSE_SCALE

                # Normalize other channels
                for c in range(1, min(grid.shape[1], 8)):
                    col = grid[:, c]
                    scale = [GLUCOSE_SCALE, 20.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0][c]
                    grid[:, c] = col / scale

                X, yo, yh, _ = extract_windows({'grid': grid, **p}, window_size, stride)
                if X is not None:
                    # Use first 8 channels or fewer
                    n_ch = min(X.shape[2], 8)
                    X = X[:, :, :n_ch]
                    all_X.append(X)
                    all_yo.append(yo)
                    all_yh.append(yh)

            if not all_X:
                continue

            X_all = np.concatenate(all_X)
            yo_all = np.concatenate(all_yo)
            yh_all = np.concatenate(all_yh)

            # Transpose to (N, C, T) for Conv1d
            X_all = X_all.transpose(0, 2, 1)

            in_ch = X_all.shape[1]
            key = f"{window_label}_{norm_mode}"
            results['variants'][key] = {}

            for task_name, y_all, n_cls in [('override', yo_all, 3), ('hypo', yh_all, 2)]:
                seed_results = []
                for seed in seeds:
                    np.random.seed(seed)
                    torch.manual_seed(seed)

                    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_all, y_all)
                    model = DeepCNN(in_ch, n_cls).to(device)
                    r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                         epochs=epochs, patience=patience,
                                         n_classes=n_cls)
                    seed_results.append(r)
                    metric = r.get('f1_macro', r.get('f1', 0))
                    print(f"      {task_name} seed={seed}: F1={metric:.4f}")

                # Average across seeds
                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], (int, float)):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                avg['n_seeds'] = len(seeds)
                avg['n_windows'] = len(X_all)
                results['variants'][key][task_name] = avg

    save_results(results, 'exp369_isf_classification')
    return results


def run_exp_370(args, seeds, max_patients, epochs, patience):
    """Per-Patient Z-Score + Raw Dual-Channel."""
    print("\n" + "="*70)
    print("EXP-370: Per-Patient Z-Score + Raw Dual-Channel")
    print("="*70)

    device = args.device
    patients = load_base_data(args.patients_dir, max_patients)
    print(f"  Loaded {len(patients)} patients")

    # Compute per-patient glucose stats
    for p in patients:
        glucose = p['grid'][:, 0]
        valid = glucose[(~np.isnan(glucose)) & (glucose > 0)]
        p['glucose_mean'] = float(np.mean(valid)) if len(valid) > 0 else 150.0
        p['glucose_std'] = float(np.std(valid)) if len(valid) > 0 else 50.0

    results = {'experiment': 'EXP-370', 'title': EXPERIMENTS[370], 'seeds': seeds, 'variants': {}}

    for window_label, window_size, stride in [('2h', WINDOW_SIZE_2H, STRIDE_2H),
                                               ('12h', WINDOW_SIZE_12H, STRIDE_12H)]:
        half = window_size // 2
        print(f"\n  --- Window: {window_label} ---")

        for variant in ['baseline_raw', 'zscore_only', 'dual_raw_zscore']:
            print(f"    Variant: {variant}")

            all_X, all_yo, all_yh = [], [], []
            for p in patients:
                grid = p['grid'].copy()
                glucose = np.clip(grid[:, 0].copy(), *GLUCOSE_CLIP)

                raw = glucose / GLUCOSE_SCALE
                zscore = patient_zscore_glucose(glucose, p['glucose_mean'], p['glucose_std'])

                if variant == 'baseline_raw':
                    grid[:, 0] = raw
                elif variant == 'zscore_only':
                    grid[:, 0] = zscore
                else:  # dual_raw_zscore
                    # Add zscore as extra column
                    zscore_col = zscore.reshape(-1, 1)
                    grid = np.concatenate([grid, zscore_col], axis=1)
                    grid[:, 0] = raw

                # Normalize other base channels
                for c in range(1, min(grid.shape[1], 8)):
                    scale = [GLUCOSE_SCALE, 20.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0][c]
                    grid[:, c] = grid[:, c] / scale

                X, yo, yh, _ = extract_windows({'grid': grid, **p}, window_size, stride)
                if X is not None:
                    n_ch = min(X.shape[2], 9 if variant == 'dual_raw_zscore' else 8)
                    X = X[:, :, :n_ch]
                    all_X.append(X)
                    all_yo.append(yo)
                    all_yh.append(yh)

            if not all_X:
                continue

            X_all = np.concatenate(all_X).transpose(0, 2, 1)
            yo_all = np.concatenate(all_yo)
            yh_all = np.concatenate(all_yh)

            in_ch = X_all.shape[1]
            key = f"{window_label}_{variant}"
            results['variants'][key] = {}

            for task_name, y_all, n_cls in [('override', yo_all, 3), ('hypo', yh_all, 2)]:
                seed_results = []
                for seed in seeds:
                    np.random.seed(seed)
                    torch.manual_seed(seed)
                    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_all, y_all)
                    model = DeepCNN(in_ch, n_cls).to(device)
                    r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                         epochs=epochs, patience=patience, n_classes=n_cls)
                    seed_results.append(r)
                    metric = r.get('f1_macro', r.get('f1', 0))
                    print(f"      {task_name} seed={seed}: F1={metric:.4f}")

                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], (int, float)):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                avg['n_seeds'] = len(seeds)
                results['variants'][key][task_name] = avg

    save_results(results, 'exp370_zscore_dual')
    return results


def run_exp_371(args, seeds, max_patients, epochs, patience):
    """Functional Depth as Hypo Enrichment Feature."""
    print("\n" + "="*70)
    print("EXP-371: Functional Depth as Hypo Feature")
    print("="*70)

    device = args.device
    patients = load_base_data(args.patients_dir, max_patients)
    print(f"  Loaded {len(patients)} patients")

    results = {'experiment': 'EXP-371', 'title': EXPERIMENTS[371], 'seeds': seeds, 'variants': {}}

    for window_label, window_size, stride in [('2h', WINDOW_SIZE_2H, STRIDE_2H)]:
        half = window_size // 2
        print(f"\n  --- Window: {window_label} ---")

        # First pass: collect all glucose windows for depth reference
        all_ref_windows = []
        all_X_base, all_yo, all_yh = [], [], []

        for p in patients:
            grid = p['grid'].copy()
            grid[:, 0] = np.clip(grid[:, 0], *GLUCOSE_CLIP) / GLUCOSE_SCALE
            for c in range(1, min(grid.shape[1], 8)):
                scale = [GLUCOSE_SCALE, 20.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0][c]
                grid[:, c] = grid[:, c] / scale

            X, yo, yh, _ = extract_windows({'grid': grid, **p}, window_size, stride)
            if X is not None:
                n_ch = min(X.shape[2], 8)
                X = X[:, :, :n_ch]
                all_X_base.append(X)
                all_yo.append(yo)
                all_yh.append(yh)
                # Glucose channel of history windows for depth reference
                all_ref_windows.extend(X[:, :, 0])

        if not all_X_base:
            continue

        X_all = np.concatenate(all_X_base).transpose(0, 2, 1)  # (N, C, T)
        yo_all = np.concatenate(all_yo)
        yh_all = np.concatenate(all_yh)
        ref_windows = np.array(all_ref_windows[:5000])  # cap for speed

        # Compute depth for each window
        print(f"  Computing functional depth for {len(X_all)} windows...")
        glucose_windows = X_all[:, 0, :]  # (N, T)
        depths = np.array([compute_functional_depth(gw, ref_windows) for gw in glucose_windows])
        depths = depths.reshape(-1, 1).astype(np.float32)

        # Check depth-hypo correlation
        hypo_mask = yh_all == 1
        depth_hypo = depths[hypo_mask].mean() if hypo_mask.any() else 0
        depth_no_hypo = depths[~hypo_mask].mean() if (~hypo_mask).any() else 0
        print(f"  Depth: hypo={depth_hypo:.4f}, no_hypo={depth_no_hypo:.4f}")

        in_ch = X_all.shape[1]

        for variant in ['baseline_cnn', 'cnn_plus_depth']:
            key = f"{window_label}_{variant}"
            results['variants'][key] = {}

            for task_name, y_all, n_cls in [('hypo', yh_all, 2)]:
                seed_results = []
                for seed in seeds:
                    np.random.seed(seed)
                    torch.manual_seed(seed)
                    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_all, y_all)

                    if variant == 'cnn_plus_depth':
                        tr_d, va_d = depths[:len(tr_X)], depths[len(tr_X):]
                        model = DeepCNNWithHead(in_ch, 1, n_cls).to(device)
                        r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                             epochs=epochs, patience=patience,
                                             n_classes=n_cls,
                                             scalar_train=tr_d, scalar_val=va_d)
                    else:
                        model = DeepCNN(in_ch, n_cls).to(device)
                        r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                             epochs=epochs, patience=patience, n_classes=n_cls)
                    seed_results.append(r)
                    print(f"      {variant} {task_name} seed={seed}: F1={r.get('f1',0):.4f} AUC={r.get('auc',0):.4f}")

                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], (int, float)):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                avg['n_seeds'] = len(seeds)
                avg['depth_hypo_mean'] = float(depth_hypo)
                avg['depth_no_hypo_mean'] = float(depth_no_hypo)
                results['variants'][key][task_name] = avg

    save_results(results, 'exp371_functional_depth')
    return results


def run_exp_372(args, seeds, max_patients, epochs, patience):
    """Glucodensity at Classifier Head."""
    print("\n" + "="*70)
    print("EXP-372: Glucodensity at Classifier Head")
    print("="*70)

    device = args.device
    patients = load_base_data(args.patients_dir, max_patients)
    print(f"  Loaded {len(patients)} patients")

    results = {'experiment': 'EXP-372', 'title': EXPERIMENTS[372], 'seeds': seeds, 'variants': {}}

    for window_label, window_size, stride in [('2h', WINDOW_SIZE_2H, STRIDE_2H),
                                               ('12h', WINDOW_SIZE_12H, STRIDE_12H)]:
        half = window_size // 2
        print(f"\n  --- Window: {window_label} ---")

        all_X, all_gluco, all_yo, all_yh = [], [], [], []
        for p in patients:
            grid = p['grid'].copy()
            raw_glucose = np.clip(grid[:, 0].copy(), *GLUCOSE_CLIP)
            grid[:, 0] = raw_glucose / GLUCOSE_SCALE
            for c in range(1, min(grid.shape[1], 8)):
                scale = [GLUCOSE_SCALE, 20.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0][c]
                grid[:, c] = grid[:, c] / scale

            T = len(grid)
            for start in range(0, T - window_size, stride):
                window = grid[start:start + window_size]
                glucose_raw = raw_glucose[start:start + window_size]
                g = glucose_raw[:half]
                if np.isnan(g).mean() > 0.3:
                    continue

                future_g = glucose_raw[half:]
                valid_f = future_g[~np.isnan(future_g)]
                if len(valid_f) < 5:
                    continue

                mean_bg = np.nanmean(valid_f)
                yo = 0 if mean_bg < 80 else (2 if mean_bg > 180 else 1)
                yh = 1 if np.any(valid_f < 70) else 0

                gluco = compute_glucodensity(g[~np.isnan(g)])

                n_ch = min(window.shape[1], 8)
                all_X.append(window[:half, :n_ch])
                all_gluco.append(gluco)
                all_yo.append(yo)
                all_yh.append(yh)

        if not all_X:
            continue

        X_all = np.stack(all_X).transpose(0, 2, 1).astype(np.float32)
        G_all = np.stack(all_gluco).astype(np.float32)
        yo_all = np.array(all_yo)
        yh_all = np.array(all_yh)

        in_ch = X_all.shape[1]

        for variant in ['baseline_cnn', 'cnn_plus_glucodensity']:
            key = f"{window_label}_{variant}"
            results['variants'][key] = {}

            for task_name, y_all, n_cls in [('override', yo_all, 3), ('hypo', yh_all, 2)]:
                seed_results = []
                for seed in seeds:
                    np.random.seed(seed)
                    torch.manual_seed(seed)
                    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_all, y_all)

                    if variant == 'cnn_plus_glucodensity':
                        tr_g, va_g = G_all[:len(tr_X)], G_all[len(tr_X):]
                        model = DeepCNNWithHead(in_ch, 8, n_cls).to(device)
                        r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                             epochs=epochs, patience=patience,
                                             n_classes=n_cls,
                                             scalar_train=tr_g, scalar_val=va_g)
                    else:
                        model = DeepCNN(in_ch, n_cls).to(device)
                        r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                             epochs=epochs, patience=patience, n_classes=n_cls)
                    seed_results.append(r)
                    metric = r.get('f1_macro', r.get('f1', 0))
                    print(f"      {variant} {task_name} seed={seed}: F1={metric:.4f}")

                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], (int, float)):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                avg['n_seeds'] = len(seeds)
                results['variants'][key][task_name] = avg

    save_results(results, 'exp372_glucodensity_head')
    return results


def run_exp_375(args, seeds, max_patients, epochs, patience):
    """Multi-Rate EMA Channels."""
    print("\n" + "="*70)
    print("EXP-375: Multi-Rate EMA Channels")
    print("="*70)

    device = args.device
    patients = load_base_data(args.patients_dir, max_patients)
    print(f"  Loaded {len(patients)} patients")

    results = {'experiment': 'EXP-375', 'title': EXPERIMENTS[375], 'seeds': seeds, 'variants': {}}

    ema_alphas = [0.1, 0.3, 0.7]  # trend, medium, fast

    for window_label, window_size, stride in [('2h', WINDOW_SIZE_2H, STRIDE_2H),
                                               ('12h', WINDOW_SIZE_12H, STRIDE_12H)]:
        half = window_size // 2
        print(f"\n  --- Window: {window_label} ---")

        for variant in ['baseline_raw', 'ema_replace', 'ema_augment']:
            print(f"    Variant: {variant}")

            all_X, all_yo, all_yh = [], [], []
            for p in patients:
                grid = p['grid'].copy()
                glucose = np.clip(grid[:, 0].copy(), *GLUCOSE_CLIP)

                if variant == 'baseline_raw':
                    grid[:, 0] = glucose / GLUCOSE_SCALE
                elif variant == 'ema_replace':
                    # Replace glucose with 3 EMA channels
                    ema_channels = np.column_stack([
                        compute_ema(glucose, a) / GLUCOSE_SCALE for a in ema_alphas
                    ])
                    # Replace first column and add 2 more
                    grid[:, 0] = ema_channels[:, 0]
                    grid = np.concatenate([grid, ema_channels[:, 1:]], axis=1)
                else:  # ema_augment: keep raw + add 3 EMAs
                    grid[:, 0] = glucose / GLUCOSE_SCALE
                    ema_channels = np.column_stack([
                        compute_ema(glucose, a) / GLUCOSE_SCALE for a in ema_alphas
                    ])
                    grid = np.concatenate([grid, ema_channels], axis=1)

                for c in range(1, min(grid.shape[1], 8)):
                    if c < grid.shape[1]:
                        scale = [GLUCOSE_SCALE, 20.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0][min(c, 7)]
                        grid[:, c] = grid[:, c] / scale

                X, yo, yh, _ = extract_windows({'grid': grid, **p}, window_size, stride)
                if X is not None:
                    max_ch = 11 if variant != 'baseline_raw' else 8
                    n_ch = min(X.shape[2], max_ch)
                    X = X[:, :, :n_ch]
                    all_X.append(X)
                    all_yo.append(yo)
                    all_yh.append(yh)

            if not all_X:
                continue

            X_all = np.concatenate(all_X).transpose(0, 2, 1)
            yo_all = np.concatenate(all_yo)
            yh_all = np.concatenate(all_yh)

            in_ch = X_all.shape[1]
            key = f"{window_label}_{variant}"
            results['variants'][key] = {}

            for task_name, y_all, n_cls in [('override', yo_all, 3), ('hypo', yh_all, 2)]:
                seed_results = []
                for seed in seeds:
                    np.random.seed(seed)
                    torch.manual_seed(seed)
                    (tr_X, tr_y), (va_X, va_y) = temporal_split(X_all, y_all)
                    model = DeepCNN(in_ch, n_cls).to(device)
                    r = train_classifier(model, tr_X, tr_y, va_X, va_y, device,
                                         epochs=epochs, patience=patience, n_classes=n_cls)
                    seed_results.append(r)
                    metric = r.get('f1_macro', r.get('f1', 0))
                    print(f"      {task_name} seed={seed}: F1={metric:.4f}")

                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], (int, float)):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                avg['n_seeds'] = len(seeds)
                avg['in_channels'] = in_ch
                results['variants'][key][task_name] = avg

    save_results(results, 'exp375_multi_rate_ema')
    return results


# ─── Result Saving ───

def save_results(results, filename):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f'{filename}.json'
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved: {path}")


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(
        description='EXP-369-376: Normalization & Conditioning Experiments')
    parser.add_argument('--experiment', nargs='+', default=['all'],
                        help='Experiment number(s) or "all"')
    parser.add_argument('--device', default='cpu',
                        help='torch device (cpu/cuda/mps)')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: fewer patients, epochs, seeds')
    parser.add_argument('--patients-dir', default=None,
                        help='Path to patients directory')
    args = parser.parse_args()

    if args.patients_dir is None:
        args.patients_dir = default_patients_dir()

    seeds = SEEDS_QUICK if args.quick else SEEDS
    max_patients = QUICK_PATIENTS if args.quick else None
    epochs = QUICK_EPOCHS if args.quick else FULL_EPOCHS
    patience = QUICK_PATIENCE if args.quick else FULL_PATIENCE

    # Parse experiment selection
    if 'all' in args.experiment:
        exp_ids = sorted(EXPERIMENTS.keys())
    else:
        exp_ids = [int(e) for e in args.experiment]

    print(f"Running experiments: {exp_ids}")
    print(f"Mode: {'quick' if args.quick else 'full'}, Device: {args.device}")
    print(f"Seeds: {seeds}, Max patients: {max_patients or 'all'}")
    print(f"Patients dir: {args.patients_dir}")

    runners = {
        369: run_exp_369,
        370: run_exp_370,
        371: run_exp_371,
        372: run_exp_372,
        # 373: run_exp_373,  # TODO: Multi-seed PK validation (needs v4 infrastructure)
        # 374: run_exp_374,  # TODO: Cumulative load at 3-day (needs larger windows)
        375: run_exp_375,
        # 376: run_exp_376,  # TODO: STL decomposition (needs statsmodels)
    }

    for eid in exp_ids:
        if eid in runners:
            try:
                runners[eid](args, seeds, max_patients, epochs, patience)
            except Exception as e:
                print(f"\n  ERROR in EXP-{eid}: {e}")
                import traceback
                traceback.print_exc()
        elif eid in EXPERIMENTS:
            print(f"\n  EXP-{eid} ({EXPERIMENTS[eid]}): Not yet implemented")
        else:
            print(f"\n  Unknown experiment: EXP-{eid}")


if __name__ == '__main__':
    main()
