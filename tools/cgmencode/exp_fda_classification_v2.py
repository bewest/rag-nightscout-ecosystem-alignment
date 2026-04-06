#!/usr/bin/env python3
"""EXP-405/406: FDA Feature Engineering for Classification (v2)

Proven FDA features applied to classification at 2h and 12h scales, using
head injection (after CNN pooling) — the only approach that works for
scalar/global features (input channels give CNN zero gradient, EXP-338).

EXP-405: Glucodensity + Functional Depth Head Injection
  - 8-bin glucodensity histogram + Modified Band Depth injected at classifier
    head alongside CNN pooled features
  - Glucodensity Δ=+0.54 Silhouette vs TIR bins (EXP-330)
  - Depth Q1→33.7% hypo prevalence, 112× enrichment (EXP-335)
  - Tests 2h and 12h for override, hypo, prolonged_high tasks

EXP-406: Multi-Rate EMA Channels at 12h
  - Replaces single glucose channel with 3 EMA channels (α=0.7/0.3/0.1)
    plus raw glucose and derivative = 5ch glucose branch
  - Half-lives: 10min / 30min / 95min capture fast glucose spikes through
    slow baseline drift
  - Expected benefit at 12h where single-scale features fail
  - Also tests 2h as control (expect minimal benefit — 2h ≈ EMA smoothing)

Both experiments include ECE (Expected Calibration Error) for calibration
assessment. Results include F1, AUC-ROC, and ECE metrics.

── Cross-thread coordination ──────────────────────────────────────────────

  This runner is for the CLASSIFICATION researcher (Thread B).
  Imports shared utilities from feature_helpers.py.
  Does NOT conflict with:
    - Forecasting (Thread A): EXP-403/404 in exp_pk_forecast_v13.py
    - Architecture search: exp_arch_12h.py (EXP-361)
    - Multi-task transformer: exp_multitask_transformer.py (EXP-373/374)

  These experiments complement the existing direction by providing new
  features at the CLASSIFIER HEAD — architecture-agnostic and compatible
  with any underlying model (CNN, transformer, multi-task).

── Depends on ─────────────────────────────────────────────────────────────

  feature_helpers.py: multi_rate_ema_batch, glucodensity_head_features,
                      functional_depth_features, compute_head_features
  exp_arch_12h.py: load_patient_features, window_and_split, TASKS,
                   build_*_labels, smooth_glucose_series

── Usage ──────────────────────────────────────────────────────────────────

  python tools/cgmencode/exp_fda_classification_v2.py --experiment 405
  python tools/cgmencode/exp_fda_classification_v2.py --experiment 406
  python tools/cgmencode/exp_fda_classification_v2.py  # runs both

── Clinical Metrics ───────────────────────────────────────────────────────

  Classification experiments report ECE (Expected Calibration Error) via
  calibration_metrics() below. Platt scaling showed ECE 0.21→0.01 in
  EXP-324 — critical for clinical deployment. All results include:
    - F1 (binary or macro)
    - AUC-ROC (for binary tasks)
    - ECE (10-bin Expected Calibration Error)
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F_torch
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

from feature_helpers import (
    multi_rate_ema_batch,
    glucodensity_head_features,
    functional_depth_features,
    compute_head_features,
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
GLUCOSE_SCALE = 400.0


# ── Clinical Metrics ─────────────────────────────────────────────────────

def compute_ece(probs, labels, n_bins=10):
    """Expected Calibration Error — measures reliability of predicted probs.

    ECE < 0.05 is well-calibrated. ECE > 0.10 needs Platt/isotonic scaling.
    """
    if probs.ndim == 2:
        if probs.shape[1] == 2:
            confs = probs[:, 1]
            preds = (confs >= 0.5).astype(int)
        else:
            confs = probs.max(axis=1)
            preds = probs.argmax(axis=1)
    else:
        confs = probs
        preds = (confs >= 0.5).astype(int)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (confs > bin_boundaries[i]) & (confs <= bin_boundaries[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = (preds[mask] == labels[mask]).mean()
        bin_conf = confs[mask].mean()
        ece += mask.sum() / len(labels) * abs(bin_acc - bin_conf)
    return float(ece)


# ── Data Loading (reuse from exp_arch_12h) ───────────────────────────────

try:
    from exp_arch_12h import (
        load_patient_features,
        window_and_split,
        TASKS,
        WINDOW_SIZE,
        HALF,
        build_override_labels,
        build_hypo_labels,
        build_prolonged_high_labels,
        smooth_glucose_series,
        find_patient_dirs,
    )
except ImportError:
    print("WARNING: exp_arch_12h.py not importable, using inline definitions")
    # Inline fallbacks for standalone operation
    from scipy.interpolate import UnivariateSpline
    import glob as glob_mod

    WINDOW_SIZE = 144
    HALF = 72

    def smooth_glucose_series(glucose, smoothing_factor=None):
        x = np.arange(len(glucose), dtype=float)
        valid = ~np.isnan(glucose) & (glucose > 0)
        if valid.sum() < 20:
            d1 = np.gradient(glucose)
            return glucose.copy(), d1, np.gradient(d1)
        if smoothing_factor is None:
            smoothing_factor = valid.sum() * 1.0
        try:
            spl = UnivariateSpline(x[valid], glucose[valid], s=smoothing_factor, k=4)
            smooth = np.clip(spl(x), 30, 500)
            d1, d2 = spl.derivative(1)(x), spl.derivative(2)(x)
        except Exception:
            smooth = glucose.copy()
            d1 = np.gradient(glucose)
            d2 = np.gradient(d1)
        return smooth.astype(np.float32), d1.astype(np.float32), d2.astype(np.float32)

    def find_patient_dirs(d):
        dirs = sorted(glob_mod.glob(os.path.join(d, '*/training')))
        if not dirs:
            dirs = sorted(glob_mod.glob(os.path.join(d, '*')))
        return [x for x in dirs if os.path.isdir(x)]

    def load_patient_features(patients_dir):
        patient_dirs = find_patient_dirs(patients_dir)
        print(f"Loading {len(patient_dirs)} patients")
        patients = []
        for pdir in patient_dirs:
            pid = Path(pdir).parent.name
            try:
                df, base_8ch = build_nightscout_grid(pdir)
                pk_8ch = build_continuous_pk_features(df)
                raw_glucose = df['glucose'].values
                g_smooth, g_d1, g_d2 = smooth_glucose_series(raw_glucose)
                fda_3ch = np.column_stack([
                    g_smooth / 400.0, g_d1 / 10.0, g_d2 / 5.0,
                ]).astype(np.float32)
                ml = min(len(base_8ch), len(pk_8ch), len(fda_3ch))
                base_8ch = base_8ch[:ml].astype(np.float32)
                pk_8ch = pk_8ch[:ml].astype(np.float32)
                fda_3ch = fda_3ch[:ml]
                np.nan_to_num(base_8ch, copy=False)
                np.nan_to_num(pk_8ch, copy=False)
                np.nan_to_num(fda_3ch, copy=False)
                patients.append((pid, base_8ch, pk_8ch, fda_3ch))
                print(f"  {pid}: {ml} timesteps")
            except Exception as e:
                print(f"  {pid}: FAILED - {e}")
        return patients

    def window_and_split(patients, window_size=WINDOW_SIZE, stride=36):
        all_bt, all_bv, all_pt, all_pv, all_ft, all_fv = [], [], [], [], [], []
        for pid, base, pk, fda in patients:
            ml = len(base)
            bw, pw, fw = [], [], []
            for i in range(0, ml - window_size + 1, stride):
                bw.append(base[i:i + window_size])
                pw.append(pk[i:i + window_size])
                fw.append(fda[i:i + window_size])
            if len(bw) < 10:
                continue
            bw = np.array(bw, dtype=np.float32)
            pw = np.array(pw, dtype=np.float32)
            fw = np.array(fw, dtype=np.float32)
            n = len(bw)
            s = int(n * 0.8)
            all_bt.append(bw[:s]); all_bv.append(bw[s:])
            all_pt.append(pw[:s]); all_pv.append(pw[s:])
            all_ft.append(fw[:s]); all_fv.append(fw[s:])
        bt = np.concatenate(all_bt); bv = np.concatenate(all_bv)
        pt = np.concatenate(all_pt); pv = np.concatenate(all_pv)
        ft = np.concatenate(all_ft); fv = np.concatenate(all_fv)
        rng = np.random.RandomState(42)
        idx = rng.permutation(len(bt))
        bt, pt, ft = bt[idx], pt[idx], ft[idx]
        return bt, bv, pt, pv, ft, fv

    def build_override_labels(bw):
        fg = bw[:, HALF:, 0] * GLUCOSE_SCALE
        hi = (fg > 180).any(axis=1)
        lo = (fg < 70).any(axis=1)
        labels = np.zeros(len(bw), dtype=np.int64)
        labels[hi] = 1; labels[lo] = 2
        return labels

    def build_hypo_labels(bw):
        return ((bw[:, HALF:, 0] * GLUCOSE_SCALE < 70).any(axis=1)).astype(np.int64)

    def build_prolonged_high_labels(bw):
        fg = bw[:, HALF:, 0] * GLUCOSE_SCALE
        return ((fg > 180).mean(axis=1) > 0.5).astype(np.int64)

    TASKS = {
        'override':       {'fn': build_override_labels,       'nc': 3, 'pm': 'f1_macro'},
        'hypo':           {'fn': build_hypo_labels,           'nc': 2, 'pm': 'auc'},
        'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1'},
    }


# 2h windowing config
WINDOW_2H = 24   # 2h at 5min
HALF_2H = 12     # 1h history
STRIDE_2H = 6    # 30min stride


def window_and_split_2h(patients, window_size=WINDOW_2H, stride=STRIDE_2H):
    """Window at 2h scale for comparison."""
    all_bt, all_bv, all_pt, all_pv, all_ft, all_fv = [], [], [], [], [], []
    for pid, base, pk, fda in patients:
        ml = len(base)
        bw, pw, fw = [], [], []
        for i in range(0, ml - window_size + 1, stride):
            bw.append(base[i:i + window_size])
            pw.append(pk[i:i + window_size])
            fw.append(fda[i:i + window_size])
        if len(bw) < 10:
            continue
        bw = np.array(bw, dtype=np.float32)
        pw = np.array(pw, dtype=np.float32)
        fw = np.array(fw, dtype=np.float32)
        n = len(bw)
        s = int(n * 0.8)
        all_bt.append(bw[:s]); all_bv.append(bw[s:])
        all_pt.append(pw[:s]); all_pv.append(pw[s:])
        all_ft.append(fw[:s]); all_fv.append(fw[s:])
    bt = np.concatenate(all_bt); bv = np.concatenate(all_bv)
    pt = np.concatenate(all_pt); pv = np.concatenate(all_pv)
    ft = np.concatenate(all_ft); fv = np.concatenate(all_fv)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(bt))
    bt, pt, ft = bt[idx], pt[idx], ft[idx]
    return bt, bv, pt, pv, ft, fv


# ── Architecture: CNN with Head Injection ────────────────────────────────

class DeepCNNWithHead(nn.Module):
    """DeepCNN with extra scalar features injected at the classifier head.
    
    The CNN processes temporal channels → pool → 128-dim vector.
    Head features (glucodensity, depth, etc.) are concatenated to the
    pooled vector before the final classifier layers.
    
    This is the ONLY effective way to use scalar/global features with CNNs.
    Input-channel injection gives zero temporal gradient (EXP-338).
    """
    def __init__(self, in_ch, nc, head_dim=0):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(128),
            nn.AdaptiveAvgPool1d(1),
        )
        total = 128 + head_dim
        self.fc = nn.Sequential(
            nn.Linear(total, 64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, nc)
        )
        self.head_dim = head_dim

    def forward(self, x_temporal, x_head=None):
        # x_temporal: (B, T, C) → permute to (B, C, T)
        h = self.conv(x_temporal.permute(0, 2, 1)).squeeze(-1)
        if x_head is not None and self.head_dim > 0:
            h = torch.cat([h, x_head], dim=1)
        return self.fc(h)


class DilatedCNNWithHead(nn.Module):
    """Dilated CNN (RF=63) with head injection. Better for 12h windows."""
    def __init__(self, in_ch, nc, head_dim=0):
        super().__init__()
        layers = []
        ch_list = [in_ch, 32, 64, 64, 128, 128]
        dilations = [1, 2, 4, 8, 16]
        for i, d in enumerate(dilations):
            layers.extend([
                nn.Conv1d(ch_list[i], ch_list[i + 1], 3, padding=d, dilation=d),
                nn.ReLU(), nn.BatchNorm1d(ch_list[i + 1]),
            ])
        layers.append(nn.AdaptiveAvgPool1d(1))
        self.conv = nn.Sequential(*layers)
        total = 128 + head_dim
        self.fc = nn.Sequential(
            nn.Linear(total, 64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, nc)
        )
        self.head_dim = head_dim

    def forward(self, x_temporal, x_head=None):
        h = self.conv(x_temporal.permute(0, 2, 1)).squeeze(-1)
        if x_head is not None and self.head_dim > 0:
            h = torch.cat([h, x_head], dim=1)
        return self.fc(h)


# ── Training ─────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def build_2h_labels(bw, task_fn, half=HALF_2H):
    """Build labels for 2h windows using first-half history."""
    fg = bw[:, half:, 0] * GLUCOSE_SCALE
    if task_fn == build_hypo_labels:
        return ((fg < 70).any(axis=1)).astype(np.int64)
    elif task_fn == build_prolonged_high_labels:
        return ((fg > 180).mean(axis=1) > 0.5).astype(np.int64)
    else:
        hi = (fg > 180).any(axis=1)
        lo = (fg < 70).any(axis=1)
        labels = np.zeros(len(bw), dtype=np.int64)
        labels[hi] = 1; labels[lo] = 2
        return labels


def train_and_eval_with_head(tx, ty, vx, vy, nc, device,
                              head_train=None, head_val=None,
                              arch_cls=DeepCNNWithHead,
                              epochs=60, bs=256, patience=12, half=HALF):
    """Train model with optional head features and return metrics including ECE."""
    in_ch = tx.shape[2]
    th = tx[:, :half].copy()
    vh = vx[:, :half].copy()

    head_dim = 0 if head_train is None else head_train.shape[1]

    model = arch_cls(in_ch, nc, head_dim=head_dim).to(device)
    w = compute_class_weights(ty, nc).to(device)
    crit = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)

    th_t = torch.from_numpy(th).float()
    vh_t = torch.from_numpy(vh).float()

    if head_train is not None:
        ht_t = torch.from_numpy(head_train).float()
        hv_t = torch.from_numpy(head_val).float()
        ds = TensorDataset(th_t, ht_t, torch.from_numpy(ty).long())
    else:
        ds = TensorDataset(th_t, torch.from_numpy(ty).long())

    dl = DataLoader(ds, batch_size=bs, shuffle=True,
                    pin_memory=(device.type == 'cuda'))

    best_m, best_p, best_pr, wait = -1, None, None, 0
    for ep in range(epochs):
        model.train()
        for batch in dl:
            if head_train is not None:
                xb, hb, yb = batch[0].to(device), batch[1].to(device), batch[2].to(device)
                opt.zero_grad(); crit(model(xb, hb), yb).backward(); opt.step()
            else:
                xb, yb = batch[0].to(device), batch[1].to(device)
                opt.zero_grad(); crit(model(xb), yb).backward(); opt.step()

        model.eval()
        with torch.no_grad():
            if head_train is not None:
                logits = model(vh_t.to(device), hv_t.to(device))
            else:
                logits = model(vh_t.to(device))
            preds = logits.argmax(1).cpu().numpy()
            probs = torch.softmax(logits, 1).cpu().numpy()

        if nc == 2:
            try: metric = roc_auc_score(vy, probs[:, 1])
            except: metric = 0.0
        else:
            metric = f1_score(vy, preds, average='macro', zero_division=0)
        sched.step(1 - metric)

        if metric > best_m:
            best_m, best_p, best_pr, wait = metric, preds.copy(), probs.copy(), 0
        else:
            wait += 1
            if wait >= patience:
                break

    nparams = sum(p.numel() for p in model.parameters())
    r = {'epochs': ep + 1, 'in_channels': in_ch, 'head_dim': head_dim,
         'param_count': nparams, 'architecture': arch_cls.__name__}

    if nc == 2:
        r['f1'] = float(f1_score(vy, best_p, average='binary', zero_division=0))
        try: r['auc'] = float(roc_auc_score(vy, best_pr[:, 1]))
        except: r['auc'] = 0.0
        r['prevalence'] = float(vy.mean())
    else:
        r['f1_macro'] = float(f1_score(vy, best_p, average='macro', zero_division=0))
        r['f1_per_class'] = [float(x) for x in f1_score(
            vy, best_p, average=None, zero_division=0)]

    # ECE for calibration assessment
    r['ece'] = compute_ece(best_pr, vy)

    return r


# ── EXP-405: Glucodensity + Depth Head Injection ────────────────────────

def run_exp_405(patients, device, seeds):
    """Test glucodensity (8 bins) + functional depth injected at classifier head.
    
    Runs at both 2h and 12h scales for all three tasks.
    Control: same CNN without head features.
    """
    results = {'experiment': 'EXP-405', 'description': 'Glucodensity + depth head injection',
               'variants': {}}

    for scale_name, (wfn, half, stride) in [
        ('2h', (window_and_split_2h, HALF_2H, STRIDE_2H)),
        ('12h', (window_and_split, HALF, 36)),
    ]:
        print(f"\n═══ EXP-405 Scale: {scale_name} ═══")
        bt, bv, pt, pv, ft, fv = wfn(patients)
        print(f"  {len(bt)} train, {len(bv)} val windows")

        # Compute head features for train and val
        glucose_train = bt[:, :half, 0] * GLUCOSE_SCALE
        glucose_val = bv[:, :half, 0] * GLUCOSE_SCALE

        head_train = compute_head_features(glucose_train)
        head_val = compute_head_features(glucose_val)
        head_dim = head_train.shape[1] if head_train is not None else 0
        print(f"  Head features: {head_dim} dims")

        # Build labels
        for task_name, task_cfg in TASKS.items():
            nc = task_cfg['nc']
            if scale_name == '2h':
                ty = build_2h_labels(bt, task_cfg['fn'], half=half)
                vy = build_2h_labels(bv, task_cfg['fn'], half=half)
            else:
                ty = task_cfg['fn'](bt)
                vy = task_cfg['fn'](bv)

            pos_rate = vy.mean() if nc == 2 else None
            print(f"\n  Task: {task_name} ({scale_name})"
                  + (f" prevalence={pos_rate:.3f}" if pos_rate is not None else ""))

            for seed in seeds:
                np.random.seed(seed)
                torch.manual_seed(seed)

                # Control: no head features
                ctrl = train_and_eval_with_head(
                    bt, ty, bv, vy, nc, device,
                    head_train=None, head_val=None,
                    arch_cls=DeepCNNWithHead if scale_name == '2h' else DilatedCNNWithHead,
                    half=half)
                ctrl['variant'] = 'control'

                # Treatment: glucodensity + depth head
                treat = train_and_eval_with_head(
                    bt, ty, bv, vy, nc, device,
                    head_train=head_train, head_val=head_val,
                    arch_cls=DeepCNNWithHead if scale_name == '2h' else DilatedCNNWithHead,
                    half=half)
                treat['variant'] = 'glucodensity_depth_head'

                key = f"{scale_name}_{task_name}_s{seed}"
                results['variants'][key] = {
                    'scale': scale_name, 'task': task_name, 'seed': seed,
                    'control': ctrl, 'treatment': treat,
                    'head_dim': head_dim,
                }

                pm = task_cfg['pm']
                c_val = ctrl.get(pm, ctrl.get('f1_macro', 0))
                t_val = treat.get(pm, treat.get('f1_macro', 0))
                delta = t_val - c_val
                print(f"    seed={seed}: ctrl {pm}={c_val:.4f} "
                      f"treat={t_val:.4f} Δ={delta:+.4f} "
                      f"ECE ctrl={ctrl['ece']:.3f} treat={treat['ece']:.3f}")

    return results


# ── EXP-406: Multi-Rate EMA Channels ────────────────────────────────────

def build_ema_features(patients, window_size, stride, half):
    """Build 5-channel glucose branch: raw + 3 EMA + derivative."""
    all_train, all_val = [], []
    for pid, base, pk, fda in patients:
        glucose = base[:, 0]  # channel 0 is glucose/400
        ema_batch = np.expand_dims(glucose, 0)  # (1, T)
        ema_channels = multi_rate_ema_batch(
            ema_batch, alphas=[0.7, 0.3, 0.1])  # (1, T, 3)
        ema_channels = ema_channels[0]  # (T, 3)

        deriv = np.gradient(glucose)

        # 5ch: raw, ema_fast, ema_mid, ema_slow, derivative
        feat = np.column_stack([
            glucose, ema_channels, deriv / 10.0
        ]).astype(np.float32)
        np.nan_to_num(feat, copy=False)

        # Window
        ml = len(feat)
        windows = []
        for i in range(0, ml - window_size + 1, stride):
            windows.append(feat[i:i + window_size])
        if len(windows) < 10:
            continue
        arr = np.array(windows, dtype=np.float32)
        n = len(arr)
        s = int(n * 0.8)
        all_train.append(arr[:s])
        all_val.append(arr[s:])

    train = np.concatenate(all_train)
    val = np.concatenate(all_val)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(train))
    train = train[idx]
    return train, val


def run_exp_406(patients, device, seeds):
    """Test multi-rate EMA channels replacing single glucose channel.
    
    5ch glucose branch: raw + EMA(0.7) + EMA(0.3) + EMA(0.1) + derivative
    vs control 8ch baseline.
    Tests at 2h and 12h.
    """
    results = {'experiment': 'EXP-406', 'description': 'Multi-rate EMA channels',
               'variants': {}}

    for scale_name, (ws, half, stride) in [
        ('2h', (WINDOW_2H, HALF_2H, STRIDE_2H)),
        ('12h', (WINDOW_SIZE, HALF, 36)),
    ]:
        print(f"\n═══ EXP-406 Scale: {scale_name} ═══")

        # Control: standard 8ch
        bt, bv, pt, pv, ft, fv = (
            window_and_split_2h(patients) if scale_name == '2h'
            else window_and_split(patients)
        )
        print(f"  Control: {len(bt)} train, {len(bv)} val windows (8ch)")

        # Treatment: 5ch EMA
        ema_train, ema_val = build_ema_features(patients, ws, stride, half)
        print(f"  EMA: {len(ema_train)} train, {len(ema_val)} val windows (5ch)")

        for task_name, task_cfg in TASKS.items():
            nc = task_cfg['nc']
            if scale_name == '2h':
                ty = build_2h_labels(bt, task_cfg['fn'], half=half)
                vy = build_2h_labels(bv, task_cfg['fn'], half=half)
                # Also need labels for EMA windows (same windowing → same labels)
                ety = build_2h_labels(ema_train, task_cfg['fn'], half=half)
                evy = build_2h_labels(ema_val, task_cfg['fn'], half=half)
            else:
                ty = task_cfg['fn'](bt)
                vy = task_cfg['fn'](bv)
                ety = task_cfg['fn'](ema_train)
                evy = task_cfg['fn'](ema_val)

            print(f"\n  Task: {task_name} ({scale_name})")

            for seed in seeds:
                np.random.seed(seed)
                torch.manual_seed(seed)

                arch = DeepCNNWithHead if scale_name == '2h' else DilatedCNNWithHead

                # Control: standard 8ch
                ctrl = train_and_eval_with_head(
                    bt, ty, bv, vy, nc, device,
                    arch_cls=arch, half=half)
                ctrl['variant'] = 'baseline_8ch'

                # Treatment: 5ch EMA
                treat = train_and_eval_with_head(
                    ema_train, ety, ema_val, evy, nc, device,
                    arch_cls=arch, half=half)
                treat['variant'] = 'ema_5ch'

                key = f"{scale_name}_{task_name}_s{seed}"
                results['variants'][key] = {
                    'scale': scale_name, 'task': task_name, 'seed': seed,
                    'control': ctrl, 'treatment': treat,
                }

                pm = task_cfg['pm']
                c_val = ctrl.get(pm, ctrl.get('f1_macro', 0))
                t_val = treat.get(pm, treat.get('f1_macro', 0))
                delta = t_val - c_val
                print(f"    seed={seed}: ctrl {pm}={c_val:.4f} "
                      f"ema={t_val:.4f} Δ={delta:+.4f} "
                      f"ECE ctrl={ctrl['ece']:.3f} ema={treat['ece']:.3f}")

    return results


# ── Result Saving ────────────────────────────────────────────────────────

def save_results(results, exp_id):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"exp{exp_id}_fda_classification_v2.json"
    with open(path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-405/406: FDA Classification v2')
    parser.add_argument('--experiment', type=int, choices=[405, 406],
                        help='Run specific experiment (default: both)')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    parser.add_argument('--patients-dir', default=None,
                        help='Path to patients directory')
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"Device: {device}")

    pdir = args.patients_dir or str(
        Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients')
    print(f"Loading data from: {pdir}")
    patients = load_patient_features(pdir)

    if args.experiment is None or args.experiment == 405:
        r405 = run_exp_405(patients, device, args.seeds)
        save_results(r405, 405)

    if args.experiment is None or args.experiment == 406:
        r406 = run_exp_406(patients, device, args.seeds)
        save_results(r406, 406)

    print("\n✓ All experiments complete.")


if __name__ == '__main__':
    main()
