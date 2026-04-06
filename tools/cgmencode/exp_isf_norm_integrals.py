#!/usr/bin/env python3
"""EXP-381: ISF-Normalized Glucose + Cumulative Integral Features

★★★★★ PRIORITY from evidence synthesis: ISF normalization is the most
principled way to reduce cross-patient variability. Instead of glucose/400,
use (glucose - target) / ISF to express glucose in "insulin-equivalent" units.

EXP-381a: ISF-Normalized Glucose at 2h, 6h, 12h
  Replace glucose/400 with (glucose - target) / ISF per patient.
  Expected: reduce cross-patient variance, improve generalization.
  Control: baseline_plus_fda_10ch (current universal best).

EXP-381b: Cumulative Integral Features at 12h
  Add rolling integral features: glucose_load (area above 180),
  hypo_load (area below 70), insulin_cumul (rolling IOB integral).
  These are naturally smooth at long horizons and encode clinically
  meaningful summaries. Expected to help 12h where raw channels fail.

EXP-381c: Combined ISF-norm + cumulative integrals + FDA at 12h+mixup
  Stack all promising ingredients for maximum 12h performance.

Usage:
    PYTHONUNBUFFERED=1 python tools/cgmencode/exp_isf_norm_integrals.py
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, math
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score
from scipy.interpolate import UnivariateSpline, CubicSpline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid


# ── Shared utilities ──────────────────────────────────────────────────────

def smooth_glucose_series(glucose, smoothing_factor=None):
    x = np.arange(len(glucose), dtype=float)
    valid = ~np.isnan(glucose) & (glucose > 0)
    if valid.sum() < 20:
        d1 = np.gradient(glucose)
        d2 = np.gradient(d1)
        return glucose.copy(), d1, d2
    if smoothing_factor is None:
        smoothing_factor = valid.sum() * 1.0
    try:
        spl = UnivariateSpline(x[valid], glucose[valid], s=smoothing_factor, k=4)
        smooth = spl(x)
        d1 = spl.derivative(1)(x)
        d2 = spl.derivative(2)(x)
        smooth = np.clip(smooth, 30, 500)
    except Exception:
        smooth = glucose.copy()
        d1 = np.gradient(glucose)
        d2 = np.gradient(d1)
    return smooth.astype(np.float32), d1.astype(np.float32), d2.astype(np.float32)


def find_patient_dirs(d):
    dirs = sorted(glob.glob(os.path.join(d, '*/training')))
    if not dirs:
        dirs = sorted(glob.glob(os.path.join(d, '*')))
    return [x for x in dirs if os.path.isdir(x)]


def load_isf_from_profile(patient_dir):
    """Load ISF and target from patient profile.json."""
    import json as _json
    profile_path = os.path.join(patient_dir, 'profile.json')
    if not os.path.exists(profile_path):
        # Walk up to find profile
        parent = os.path.dirname(patient_dir)
        profile_path = os.path.join(parent, 'profile.json')
    if not os.path.exists(profile_path):
        return None, None

    with open(profile_path) as f:
        profiles = _json.load(f)

    # Nightscout profile format
    if isinstance(profiles, list):
        profile = profiles[0] if profiles else {}
    else:
        profile = profiles

    store = profile.get('store', profile)
    if isinstance(store, dict):
        # Get first profile
        for key in store:
            if isinstance(store[key], dict):
                store = store[key]
                break

    # Extract ISF schedule
    sens = store.get('sens', store.get('sensitivity', []))
    if isinstance(sens, list) and len(sens) > 0:
        isf_values = [s.get('value', s.get('sensitivity', 0)) for s in sens]
        mean_isf = float(np.mean([v for v in isf_values if v > 0])) if isf_values else None
    else:
        mean_isf = None

    # Extract target BG
    target_low = store.get('target_low', store.get('targetLow', []))
    target_high = store.get('target_high', store.get('targetHigh', []))
    if isinstance(target_low, list) and len(target_low) > 0:
        tl = [t.get('value', 0) for t in target_low]
        th = [t.get('value', 0) for t in target_high] if isinstance(target_high, list) else tl
        target = float(np.mean([(l + h) / 2 for l, h in zip(tl, th) if l > 0 and h > 0]))
    else:
        target = None

    return mean_isf, target


def compute_cumulative_integrals(glucose_raw, iob, dt_min=5):
    """Compute rolling cumulative integral features.

    Returns:
        glucose_load: cumulative area above 180 mg/dL (in mg*min/dL)
        hypo_load: cumulative area below 70 mg/dL (in mg*min/dL)
        insulin_cumul: cumulative IOB integral (in U*min)

    All normalized by rolling window to prevent unbounded growth.
    """
    n = len(glucose_raw)
    # Use rolling 2h (24 step) window for cumulative features
    window = 24

    glucose_load = np.zeros(n, dtype=np.float32)
    hypo_load = np.zeros(n, dtype=np.float32)
    insulin_cumul = np.zeros(n, dtype=np.float32)

    for i in range(n):
        start = max(0, i - window + 1)
        g_window = glucose_raw[start:i + 1]
        iob_window = iob[start:i + 1]

        # Area above 180 (hyperglycemia burden)
        above = np.maximum(g_window - 180, 0)
        glucose_load[i] = above.sum() * dt_min / 1000.0  # scale down

        # Area below 70 (hypoglycemia burden)
        below = np.maximum(70 - g_window, 0)
        hypo_load[i] = below.sum() * dt_min / 100.0  # scale down

        # Cumulative insulin
        insulin_cumul[i] = iob_window.sum() * dt_min / 100.0

    return glucose_load, hypo_load, insulin_cumul


def load_patients(patients_dir):
    """Load all patients with ISF normalization and integral features."""
    patient_dirs = find_patient_dirs(patients_dir)
    print(f"Loading {len(patient_dirs)} patients")
    patients = []
    for pdir in patient_dirs:
        pid = Path(pdir).parent.name
        try:
            df, base_8ch = build_nightscout_grid(pdir)
            raw_glucose = df['glucose'].values
            g_smooth, g_d1, g_d2 = smooth_glucose_series(raw_glucose)
            ml = min(len(base_8ch), len(g_smooth))
            base_8ch = base_8ch[:ml].astype(np.float32)
            g_smooth = g_smooth[:ml]
            g_d1 = g_d1[:ml]
            g_d2 = g_d2[:ml]
            raw_glucose = raw_glucose[:ml]
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(g_smooth, copy=False)

            # Load ISF and target from profile
            isf, target = load_isf_from_profile(pdir)
            if isf is None or isf <= 0:
                isf = 50.0  # default mg/dL per U (will note which patients use default)
                isf_source = 'default'
            else:
                isf_source = 'profile'
            if target is None or target <= 0:
                target = 100.0  # default target mg/dL
                target_source = 'default'
            else:
                target_source = 'profile'

            # Detect mmol/L vs mg/dL: if ISF < 5, likely mmol/L
            if isf < 5.0:
                isf = isf * 18.0  # convert to mg/dL per U
                target = target * 18.0 if target < 15 else target
                print(f"  {pid}: ISF converted from mmol/L: {isf/18:.1f}→{isf:.0f} mg/dL/U")

            print(f"  {pid}: ISF={isf:.1f} mg/dL/U ({isf_source}), "
                  f"target={target:.0f} mg/dL ({target_source}), {ml} steps")

            # ISF-normalized glucose: (glucose - target) / ISF
            # This transforms glucose into "insulin-equivalent" units
            # A value of 1.0 means "one unit of insulin correction away from target"
            isf_norm_glucose = (raw_glucose.astype(np.float32) - target) / isf

            # Cumulative integrals
            iob = base_8ch[:, 1]  # IOB channel
            g_load, h_load, i_cumul = compute_cumulative_integrals(raw_glucose, iob)

            # Build feature variants:
            # 1. baseline_plus_fda_10ch (control - current best)
            fda_10ch = np.column_stack([
                base_8ch[:, 0:1],   # glucose/400
                g_d1[:, np.newaxis] / 10.0,
                g_d2[:, np.newaxis] / 5.0,
                base_8ch[:, 1:8],   # iob, cob, net_basal, bolus, carbs, time_sin, time_cos
            ]).astype(np.float32)

            # 2. ISF-normalized: replace glucose/400 with ISF-norm glucose
            isf_norm_10ch = np.column_stack([
                isf_norm_glucose[:, np.newaxis],  # ISF-normalized glucose
                g_d1[:, np.newaxis] / 10.0,
                g_d2[:, np.newaxis] / 5.0,
                base_8ch[:, 1:8],
            ]).astype(np.float32)

            # 3. ISF-norm + cumulative integrals (13ch)
            isf_integ_13ch = np.column_stack([
                isf_norm_glucose[:, np.newaxis],
                g_d1[:, np.newaxis] / 10.0,
                g_d2[:, np.newaxis] / 5.0,
                base_8ch[:, 1:8],
                g_load[:, np.newaxis],
                h_load[:, np.newaxis],
                i_cumul[:, np.newaxis],
            ]).astype(np.float32)

            np.nan_to_num(fda_10ch, copy=False)
            np.nan_to_num(isf_norm_10ch, copy=False)
            np.nan_to_num(isf_integ_13ch, copy=False)

            patients.append({
                'pid': pid, 'length': ml,
                'fda_10ch': fda_10ch,
                'isf_norm_10ch': isf_norm_10ch,
                'isf_integ_13ch': isf_integ_13ch,
                'isf': isf, 'target': target,
            })
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")
    return patients


# ── Windowing & splitting ─────────────────────────────────────────────────

def window_and_split_all(patients, window_size, stride, feature_key):
    all_train, all_val = [], []
    for p in patients:
        arr = p[feature_key]
        n = len(arr)
        windows = []
        for i in range(0, n - window_size + 1, stride):
            windows.append(arr[i:i + window_size])
        if len(windows) < 5:
            continue
        w = np.array(windows, dtype=np.float32)
        s = int(len(w) * 0.8)
        all_train.append(w[:s])
        all_val.append(w[s:])
    train = np.concatenate(all_train)
    val = np.concatenate(all_val)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(train))
    train = train[idx]
    return train, val


# ── Labels ────────────────────────────────────────────────────────────────

def build_override_labels(windows, glucose_idx=0, scale_factor=400.0):
    # For ISF-norm: glucose is in ISF units, not 0-1 scaled
    # Need to reconstruct approximate mg/dL for label purposes
    # Use the fact that high/low thresholds are universal in mg/dL
    fg = windows[:, :, glucose_idx]
    # If values are small (ISF-norm range ~-1 to +5), it's ISF-normalized
    if np.abs(fg).max() < 20:
        # ISF-norm: a value of ~(180-100)/50 = 1.6 is "high", ~(70-100)/50 = -0.6 is "low"
        # Use approximate thresholds
        half = windows.shape[1] // 2
        fg_future = fg[:, half:]
        hi = (fg_future > 1.5).any(axis=1)   # ~180 mg/dL above target
        lo = (fg_future < -0.5).any(axis=1)   # ~70 mg/dL below target
    else:
        half = windows.shape[1] // 2
        fg_future = fg[:, half:] * scale_factor
        hi = (fg_future > 180).any(axis=1)
        lo = (fg_future < 70).any(axis=1)
    labels = np.zeros(len(windows), dtype=np.int64)
    labels[hi] = 1
    labels[lo] = 2
    return labels


def build_hypo_labels(windows, glucose_idx=0, scale_factor=400.0):
    fg = windows[:, :, glucose_idx]
    half = windows.shape[1] // 2
    if np.abs(fg).max() < 20:
        return ((fg[:, half:] < -0.5).any(axis=1)).astype(np.int64)
    return ((fg[:, half:] * scale_factor < 70).any(axis=1)).astype(np.int64)


def build_prolonged_high_labels(windows, glucose_idx=0, scale_factor=400.0):
    fg = windows[:, :, glucose_idx]
    half = windows.shape[1] // 2
    if np.abs(fg).max() < 20:
        return ((fg[:, half:] > 1.5).mean(axis=1) > 0.5).astype(np.int64)
    return ((fg[:, half:] * scale_factor > 180).mean(axis=1) > 0.5).astype(np.int64)


# ── Model ─────────────────────────────────────────────────────────────────

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=200):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term[:d_model // 2])
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


class TransformerClassifier(nn.Module):
    def __init__(self, in_ch, nc, d_model=64, nhead=4, nlayers=2, dropout=0.1):
        super().__init__()
        self.input_proj = nn.Linear(in_ch, d_model)
        self.pos_enc = PositionalEncoding(d_model, max_len=200)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=128,
            dropout=dropout, batch_first=True, activation='gelu',
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=nlayers)
        self.fc = nn.Sequential(
            nn.Linear(d_model, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc)
        )

    def forward(self, x):
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.encoder(h)
        h = h.mean(dim=1)
        return self.fc(h)


# ── Augmentation ──────────────────────────────────────────────────────────

def augment_mixup(x, y, alpha=0.3):
    B = len(x)
    lam = np.random.beta(alpha, alpha, size=(B, 1, 1)).astype(np.float32)
    idx = np.random.permutation(B)
    x_mixed = lam * x + (1 - lam) * x[idx]
    y_mixed = np.where(lam.squeeze() > 0.5, y, y[idx])
    return x_mixed, y_mixed


def augment_time_warp(x, sigma=0.05, n_knots=4):
    B, T, C = x.shape
    orig = np.linspace(0, 1, T)
    result = np.empty_like(x)
    for i in range(B):
        knot_positions = np.linspace(0, 1, n_knots + 2)
        knot_values = knot_positions + np.random.randn(n_knots + 2).astype(np.float32) * sigma
        knot_values[0] = 0.0
        knot_values[-1] = 1.0
        knot_values = np.sort(knot_values)
        cs = CubicSpline(knot_positions, knot_values)
        warped = cs(orig)
        warped = np.clip(warped, 0, 1) * (T - 1)
        for c in range(C):
            result[i, :, c] = np.interp(warped, np.arange(T), x[i, :, c])
    return result


# ── Training ──────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, in_ch,
                   epochs=60, bs=256, patience=12, augment_fn=None, lr=1e-3):
    wt = compute_class_weights(ty, nc).to(device)
    val_ds = TensorDataset(torch.FloatTensor(vx), torch.LongTensor(vy))
    val_dl = DataLoader(val_ds, batch_size=bs * 2)

    model = TransformerClassifier(in_ch, nc).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit = nn.CrossEntropyLoss(weight=wt)

    best_val, wait = -1, 0
    for ep in range(epochs):
        if augment_fn is not None:
            aug_tx, aug_ty = augment_fn(tx.copy(), ty.copy())
        else:
            aug_tx, aug_ty = tx, ty

        train_ds = TensorDataset(torch.FloatTensor(aug_tx), torch.LongTensor(aug_ty))
        train_dl = DataLoader(train_ds, batch_size=bs, shuffle=True, drop_last=True)

        model.train()
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            crit(model(xb), yb).backward()
            opt.step()
        sched.step()

        model.eval()
        preds, probs, ytrue = [], [], []
        with torch.no_grad():
            for xb, yb in val_dl:
                out = model(xb.to(device))
                preds.append(out.argmax(1).cpu().numpy())
                probs.append(F.softmax(out, dim=1).cpu().numpy())
                ytrue.append(yb.numpy())
        preds = np.concatenate(preds)
        probs = np.concatenate(probs)
        ytrue = np.concatenate(ytrue)

        if nc == 2:
            try:
                metric = roc_auc_score(ytrue, probs[:, 1])
            except:
                metric = f1_score(ytrue, preds, average='binary')
        else:
            metric = f1_score(ytrue, preds, average='macro')

        if metric > best_val:
            best_val = metric
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_val


def run_variant(name, train, val, tasks, half, device, seeds,
                augment_fn=None, epochs=60):
    """Run a feature variant across all tasks and seeds."""
    nch = train.shape[2]
    results = {}
    for tname, (label_fn, nc, _) in tasks.items():
        ty = label_fn(train, half)
        vy = label_fn(val, half)
        tx = train[:, :half, :]
        vx = val[:, :half, :]

        scores = []
        for seed in seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            val_metric = train_and_eval(
                tx, ty, vx, vy, nc, device, nch,
                epochs=epochs, augment_fn=augment_fn)
            scores.append(val_metric)

        mean_val = float(np.mean(scores))
        results[tname] = mean_val
        print(f"    [{name}] {tname}: {mean_val:.4f}")
    return results


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    seeds = [42, 123, 456]
    patients_dir = 'externals/ns-data/patients'

    print(f"EXP-381: ISF-Normalized Glucose + Cumulative Integrals")
    print(f"Device: {device}, Seeds: {seeds}")

    patients = load_patients(patients_dir)
    all_results = {}
    t0 = time.time()

    tasks = {
        'override': (lambda w, h: build_override_labels(w), 3, 'f1_macro'),
        'hypo': (lambda w, h: build_hypo_labels(w), 2, 'auc'),
    }

    # ── EXP-381a: ISF-normalized glucose across scales ────────────────────

    for scale, (ws, stride) in [('2h', (24, 12)), ('6h', (72, 36)), ('12h', (144, 36))]:
        half = ws // 2
        print(f"\n{'#' * 70}")
        print(f"# EXP-381a: ISF-Normalized Glucose at {scale}")
        print(f"{'#' * 70}")

        # Control: baseline_plus_fda_10ch
        train_ctrl, val_ctrl = window_and_split_all(patients, ws, stride, 'fda_10ch')
        print(f"  Control (fda_10ch): {len(train_ctrl)} train, {len(val_ctrl)} val")
        r_ctrl = run_variant('fda_10ch', train_ctrl, val_ctrl, tasks, half, device, seeds)
        for k, v in r_ctrl.items():
            all_results[f'EXP381a_{scale}_fda_10ch_{k}'] = v

        # Test: ISF-normalized 10ch
        train_isf, val_isf = window_and_split_all(patients, ws, stride, 'isf_norm_10ch')
        print(f"  ISF-norm (isf_norm_10ch): {len(train_isf)} train, {len(val_isf)} val")
        r_isf = run_variant('isf_norm_10ch', train_isf, val_isf, tasks, half, device, seeds)
        for k, v in r_isf.items():
            all_results[f'EXP381a_{scale}_isf_norm_10ch_{k}'] = v

        # Summary
        print(f"\n  {scale} SUMMARY:")
        for tname in tasks:
            ctrl = r_ctrl[tname]
            isf = r_isf[tname]
            delta = isf - ctrl
            marker = " ★" if delta > 0.001 else (" ▼" if delta < -0.001 else "")
            print(f"    {tname}: control={ctrl:.4f}, ISF-norm={isf:.4f} (Δ={delta:+.4f}){marker}")

    # ── EXP-381b: Cumulative integrals at 12h ─────────────────────────────

    print(f"\n{'#' * 70}")
    print(f"# EXP-381b: Cumulative Integral Features at 12h")
    print(f"{'#' * 70}")

    ws, stride, half = 144, 36, 72

    # ISF-norm + integrals (13ch)
    train_integ, val_integ = window_and_split_all(patients, ws, stride, 'isf_integ_13ch')
    print(f"  ISF+integrals (13ch): {len(train_integ)} train, {len(val_integ)} val")
    r_integ = run_variant('isf_integ_13ch', train_integ, val_integ, tasks, half, device, seeds)
    for k, v in r_integ.items():
        all_results[f'EXP381b_12h_isf_integ_13ch_{k}'] = v

    # Summary vs 12h controls
    print(f"\n  12h SUMMARY (all variants):")
    for tname in tasks:
        ctrl = all_results.get(f'EXP381a_12h_fda_10ch_{tname}', 0)
        isf = all_results.get(f'EXP381a_12h_isf_norm_10ch_{tname}', 0)
        integ = all_results.get(f'EXP381b_12h_isf_integ_13ch_{tname}', 0)
        print(f"    {tname}: fda={ctrl:.4f}, isf_norm={isf:.4f}, isf+integ={integ:.4f}")

    # ── EXP-381c: Best 12h combo (ISF+integ+mixup) ───────────────────────

    print(f"\n{'#' * 70}")
    print(f"# EXP-381c: Best 12h Combo (ISF+integ+mixup)")
    print(f"{'#' * 70}")

    aug_fn = lambda x, y: augment_mixup(x, y, alpha=0.3)
    r_combo = run_variant('isf_integ_13ch+mixup', train_integ, val_integ,
                          tasks, half, device, seeds, augment_fn=aug_fn, epochs=80)
    for k, v in r_combo.items():
        all_results[f'EXP381c_12h_isf_integ_mixup_{k}'] = v

    # Also test with time_warp (best for hypo from EXP-379b)
    aug_fn_tw = lambda x, y: (augment_time_warp(x, sigma=0.05), y)
    r_combo_tw = run_variant('isf_integ_13ch+time_warp', train_integ, val_integ,
                             tasks, half, device, seeds, augment_fn=aug_fn_tw, epochs=80)
    for k, v in r_combo_tw.items():
        all_results[f'EXP381c_12h_isf_integ_twarp_{k}'] = v

    # Final summary
    elapsed = time.time() - t0
    print(f"\n{'=' * 70}")
    print(f"FINAL RESULTS SUMMARY")
    print(f"{'=' * 70}")
    for scale in ['2h', '6h', '12h']:
        print(f"\n  {scale}:")
        for tname in tasks:
            ctrl = all_results.get(f'EXP381a_{scale}_fda_10ch_{tname}', 0)
            isf = all_results.get(f'EXP381a_{scale}_isf_norm_10ch_{tname}', 0)
            delta = isf - ctrl
            marker = " ★" if delta > 0.001 else (" ▼" if delta < -0.001 else "")
            print(f"    {tname}: fda={ctrl:.4f} → isf_norm={isf:.4f} (Δ={delta:+.4f}){marker}")

    print(f"\n  12h combos:")
    for tname in tasks:
        ctrl = all_results.get(f'EXP381a_12h_fda_10ch_{tname}', 0)
        vals = [
            ('isf_norm', all_results.get(f'EXP381a_12h_isf_norm_10ch_{tname}', 0)),
            ('isf+integ', all_results.get(f'EXP381b_12h_isf_integ_13ch_{tname}', 0)),
            ('isf+integ+mixup', all_results.get(f'EXP381c_12h_isf_integ_mixup_{tname}', 0)),
            ('isf+integ+twarp', all_results.get(f'EXP381c_12h_isf_integ_twarp_{tname}', 0)),
        ]
        print(f"    {tname} (baseline fda={ctrl:.4f}):")
        for name, val in vals:
            delta = val - ctrl
            marker = " ★" if delta > 0.001 else (" ▼" if delta < -0.001 else "")
            print(f"      {name:25s}: {val:.4f} (Δ={delta:+.4f}){marker}")

    print(f"\nTotal: {elapsed:.0f}s")

    out = {
        'experiment': 'EXP-381',
        'description': 'ISF-normalized glucose + cumulative integral features',
        'device': str(device),
        'seeds': seeds,
        'elapsed_s': elapsed,
        'results': all_results,
    }
    os.makedirs('externals/experiments', exist_ok=True)
    with open('externals/experiments/exp381_isf_norm_integrals.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved: externals/experiments/exp381_isf_norm_integrals.json")


if __name__ == '__main__':
    main()
