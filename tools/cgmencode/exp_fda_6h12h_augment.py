#!/usr/bin/env python3
"""EXP-377: baseline_plus_fda at 6h/12h + Data Augmentation at 12h

Two questions to answer:
  Q1: Does the 2h-optimal feature set (baseline_plus_fda_10ch) also improve 6h/12h?
      EXP-375 showed FDA derivatives are THE key ingredient at 2h. Kitchen_sink
      works at 6h but we never tested baseline+FDA there.
  Q2: Can data augmentation help at 12h where all other approaches fail?
      Since architecture and features don't improve 12h, the bottleneck may be
      data quantity. Augmentation increases effective training data.

EXP-377a: Feature comparison at 6h (Transformer)
  1. baseline_8ch                (control)
  2. kitchen_sink_10ch           (current 6h best)
  3. baseline_plus_fda_10ch      (2h best, never tested at 6h)
  4. base_notime_fda_8ch         (compact FDA variant)

EXP-377b: Feature comparison at 12h (Transformer)
  5-8. Same 4 variants at 12h

EXP-378: Data Augmentation at 12h (Transformer + baseline_8ch)
  9.  no_augment                 (control)
  10. jitter (σ=0.02)            (Gaussian noise on all channels)
  11. scaling (σ=0.1)            (random per-channel multiplicative scaling)
  12. time_warp (σ=0.05)         (random temporal warping via cubic spline)
  13. mixup (α=0.3)              (interpolation between samples)
  14. combined (jitter+scaling)   (best augmentation combo)

Usage:
    python tools/cgmencode/exp_fda_6h12h_augment.py
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse, math
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score
from scipy.interpolate import UnivariateSpline
from scipy.interpolate import CubicSpline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features


# ── Data loading (same as EXP-375) ───────────────────────────────────────

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


def window_and_split(patients, window_size, stride):
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


# ── Feature variants ─────────────────────────────────────────────────────

VARIANT_DEFS = {
    'baseline_8ch': {
        'desc': 'Standard 8ch (control)',
        'build': lambda b, p, f: b,
    },
    'kitchen_sink_10ch': {
        'desc': 'glucose + FDA deriv + treatment + PK state (10ch)',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1], f[:, :, 1:3], b[:, :, 1:4],
            p[:, :, 6:7], p[:, :, 0:1], p[:, :, 3:4], p[:, :, 2:3],
        ], axis=2),
    },
    'baseline_plus_fda_10ch': {
        'desc': 'baseline + FDA deriv (2h best)',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1], f[:, :, 1:3], b[:, :, 1:8],
        ], axis=2),
    },
    'base_notime_fda_8ch': {
        'desc': 'baseline -time +FDA deriv (compact)',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1], f[:, :, 1:3], b[:, :, 1:6],
        ], axis=2),
    },
}


# ── Labels ────────────────────────────────────────────────────────────────

def build_override_labels(bw, half):
    fg = bw[:, half:, 0] * 400.0
    hi, lo = (fg > 180).any(axis=1), (fg < 70).any(axis=1)
    labels = np.zeros(len(bw), dtype=np.int64)
    labels[hi] = 1; labels[lo] = 2
    return labels

def build_hypo_labels(bw, half):
    return ((bw[:, half:, 0] * 400.0 < 70).any(axis=1)).astype(np.int64)

def build_prolonged_high_labels(bw, half):
    fg = bw[:, half:, 0] * 400.0
    return ((fg > 180).mean(axis=1) > 0.5).astype(np.int64)


# ── Architectures ─────────────────────────────────────────────────────────

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
        self.fc = nn.Sequential(nn.Linear(d_model, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.encoder(h)
        h = h.mean(dim=1)
        return self.fc(h)


# ── Data Augmentation ─────────────────────────────────────────────────────

def augment_jitter(x, sigma=0.02):
    """Add Gaussian noise to all channels."""
    return x + np.random.randn(*x.shape).astype(np.float32) * sigma


def augment_scaling(x, sigma=0.1):
    """Random per-channel multiplicative scaling."""
    scales = np.random.randn(x.shape[0], 1, x.shape[2]).astype(np.float32) * sigma + 1.0
    return x * scales


def augment_time_warp(x, sigma=0.05, n_knots=4):
    """Random temporal warping via cubic spline."""
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


def augment_mixup(x, y, alpha=0.3):
    """Mixup: interpolate between random pairs."""
    B = len(x)
    lam = np.random.beta(alpha, alpha, size=(B, 1, 1)).astype(np.float32)
    idx = np.random.permutation(B)
    x_mixed = lam * x + (1 - lam) * x[idx]
    # For classification, use the dominant label
    y_mixed = np.where(lam.squeeze() > 0.5, y, y[idx])
    return x_mixed, y_mixed


# ── Training ─────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, in_ch,
                   epochs=60, bs=256, patience=12, augment_fn=None):
    wt = compute_class_weights(ty, nc).to(device)
    val_ds = TensorDataset(torch.FloatTensor(vx), torch.LongTensor(vy))
    val_dl = DataLoader(val_ds, batch_size=bs * 2)

    model = TransformerClassifier(in_ch, nc).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit = nn.CrossEntropyLoss(weight=wt)

    best_val, best_state, wait = -1, None, 0
    for ep in range(epochs):
        # Apply augmentation at the start of each epoch
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
                xb = xb.to(device)
                out = model(xb)
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
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    return best_val


def run_feature_experiment(name, scale, variant_key, bt, bv, pt, pv, ft, fv,
                           half, device, seeds, tasks):
    """Run one feature variant across tasks and seeds."""
    vdef = VARIANT_DEFS[variant_key]
    tx_full = vdef['build'](bt, pt, ft)
    vx_full = vdef['build'](bv, pv, fv)
    nch = tx_full.shape[2]

    print(f"\n{'='*60}")
    print(f"[{scale}] {name}: {variant_key} ({nch}ch)")
    print(f"{'='*60}")

    results = {}
    for tname, (label_fn, nc, metric_name) in tasks.items():
        ty = label_fn(bt, half)
        vy = label_fn(bv, half)
        tx = tx_full[:, :half, :]
        vx = vx_full[:, :half, :]

        seed_results = []
        for seed in seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            val = train_and_eval(tx, ty, vx, vy, nc, device, nch)
            seed_results.append(val)

        mean_val = float(np.mean(seed_results))
        results[tname] = mean_val
        print(f"  {tname}: {mean_val:.4f}")

    return results


def run_augment_experiment(name, aug_fn, bt, bv, pt, pv, ft, fv,
                           half, device, seeds, tasks):
    """Run one augmentation variant at 12h with baseline_8ch."""
    # Use baseline_8ch for augmentation experiments
    tx_full = bt
    vx_full = bv
    nch = tx_full.shape[2]

    print(f"\n{'='*60}")
    print(f"[12h] AUGMENT {name}: baseline_8ch ({nch}ch)")
    print(f"{'='*60}")

    results = {}
    for tname, (label_fn, nc, metric_name) in tasks.items():
        ty = label_fn(bt, half)
        vy = label_fn(bv, half)
        tx = tx_full[:, :half, :]
        vx = vx_full[:, :half, :]

        seed_results = []
        for seed in seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            val = train_and_eval(tx, ty, vx, vy, nc, device, nch,
                                 epochs=80, patience=15, augment_fn=aug_fn)
            seed_results.append(val)

        mean_val = float(np.mean(seed_results))
        results[tname] = mean_val
        print(f"  {tname}: {mean_val:.4f}")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    parser.add_argument('--skip-6h', action='store_true')
    parser.add_argument('--skip-12h-features', action='store_true')
    parser.add_argument('--skip-augment', action='store_true')
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"EXP-377/378: FDA at 6h/12h + Augmentation at 12h")
    print(f"Device: {device}, Seeds: {args.seeds}")

    patients = load_patient_features(args.patients_dir)

    all_results = {}
    t0 = time.time()

    # ── EXP-377a: Feature comparison at 6h ────────────────────────────────

    if not args.skip_6h:
        print("\n" + "#" * 70)
        print("# EXP-377a: Feature Comparison at 6h (Transformer)")
        print("#" * 70)

        bt6, bv6, pt6, pv6, ft6, fv6 = window_and_split(patients, 72, 36)
        half6 = 36
        print(f"  {len(bt6)} train, {len(bv6)} val")

        tasks_6h = {
            'override': (build_override_labels, 3, 'f1_macro'),
            'hypo': (build_hypo_labels, 2, 'auc'),
            'prolonged_high': (build_prolonged_high_labels, 2, 'f1'),
        }

        for vkey in ['baseline_8ch', 'kitchen_sink_10ch', 'baseline_plus_fda_10ch', 'base_notime_fda_8ch']:
            res = run_feature_experiment(
                f"377a_{vkey}", '6h', vkey,
                bt6, bv6, pt6, pv6, ft6, fv6,
                half6, device, args.seeds, tasks_6h,
            )
            all_results[f"EXP377a_6h_{vkey}"] = res

        # 6h Summary
        print("\n" + "=" * 70)
        print("EXP-377a 6h SUMMARY")
        print("=" * 70)
        base_6h = all_results.get('EXP377a_6h_baseline_8ch', {})
        for tname in ['override', 'hypo', 'prolonged_high']:
            print(f"\n  {tname}:")
            ref = base_6h.get(tname, 0)
            for vkey in ['baseline_8ch', 'kitchen_sink_10ch', 'baseline_plus_fda_10ch', 'base_notime_fda_8ch']:
                val = all_results.get(f'EXP377a_6h_{vkey}', {}).get(tname, 0)
                delta = val - ref
                marker = " ★" if val > ref + 0.001 else (" ▼" if val < ref - 0.001 else "")
                print(f"    {vkey:30s}: {val:.4f} (Δ={delta:+.4f}){marker}")

    # ── EXP-377b: Feature comparison at 12h ───────────────────────────────

    if not args.skip_12h_features:
        print("\n" + "#" * 70)
        print("# EXP-377b: Feature Comparison at 12h (Transformer)")
        print("#" * 70)

        bt12, bv12, pt12, pv12, ft12, fv12 = window_and_split(patients, 144, 36)
        half12 = 72
        print(f"  {len(bt12)} train, {len(bv12)} val")

        tasks_12h = {
            'override': (build_override_labels, 3, 'f1_macro'),
            'hypo': (build_hypo_labels, 2, 'auc'),
            'prolonged_high': (build_prolonged_high_labels, 2, 'f1'),
        }

        for vkey in ['baseline_8ch', 'kitchen_sink_10ch', 'baseline_plus_fda_10ch', 'base_notime_fda_8ch']:
            res = run_feature_experiment(
                f"377b_{vkey}", '12h', vkey,
                bt12, bv12, pt12, pv12, ft12, fv12,
                half12, device, args.seeds, tasks_12h,
            )
            all_results[f"EXP377b_12h_{vkey}"] = res

        # 12h Summary
        print("\n" + "=" * 70)
        print("EXP-377b 12h SUMMARY")
        print("=" * 70)
        base_12h = all_results.get('EXP377b_12h_baseline_8ch', {})
        for tname in ['override', 'hypo', 'prolonged_high']:
            print(f"\n  {tname}:")
            ref = base_12h.get(tname, 0)
            for vkey in ['baseline_8ch', 'kitchen_sink_10ch', 'baseline_plus_fda_10ch', 'base_notime_fda_8ch']:
                val = all_results.get(f'EXP377b_12h_{vkey}', {}).get(tname, 0)
                delta = val - ref
                marker = " ★" if val > ref + 0.001 else (" ▼" if val < ref - 0.001 else "")
                print(f"    {vkey:30s}: {val:.4f} (Δ={delta:+.4f}){marker}")

    # ── EXP-378: Data Augmentation at 12h ─────────────────────────────────

    if not args.skip_augment:
        print("\n" + "#" * 70)
        print("# EXP-378: Data Augmentation at 12h (Transformer + baseline_8ch)")
        print("#" * 70)

        try:
            _ = bt12
        except NameError:
            bt12, bv12, pt12, pv12, ft12, fv12 = window_and_split(patients, 144, 36)
        half12 = 72
        print(f"  {len(bt12)} train, {len(bv12)} val")

        tasks_12h = {
            'override': (build_override_labels, 3, 'f1_macro'),
            'hypo': (build_hypo_labels, 2, 'auc'),
            'prolonged_high': (build_prolonged_high_labels, 2, 'f1'),
        }

        augment_configs = {
            'no_augment': None,
            'jitter_002': lambda x, y: (augment_jitter(x, sigma=0.02), y),
            'scaling_01': lambda x, y: (augment_scaling(x, sigma=0.1), y),
            'time_warp_005': lambda x, y: (augment_time_warp(x, sigma=0.05), y),
            'mixup_03': lambda x, y: augment_mixup(x, y, alpha=0.3),
            'jitter_scaling': lambda x, y: (augment_scaling(augment_jitter(x, 0.02), 0.1), y),
        }

        for aug_name, aug_fn in augment_configs.items():
            res = run_augment_experiment(
                aug_name, aug_fn,
                bt12, bv12, pt12, pv12, ft12, fv12,
                half12, device, args.seeds, tasks_12h,
            )
            all_results[f"EXP378_augment_{aug_name}"] = res

        # Augmentation Summary
        print("\n" + "=" * 70)
        print("EXP-378 AUGMENTATION SUMMARY (12h)")
        print("=" * 70)
        base_aug = all_results.get('EXP378_augment_no_augment', {})
        for tname in ['override', 'hypo', 'prolonged_high']:
            print(f"\n  {tname}:")
            ref = base_aug.get(tname, 0)
            for aug_name in augment_configs:
                val = all_results.get(f'EXP378_augment_{aug_name}', {}).get(tname, 0)
                delta = val - ref
                marker = " ★" if val > ref + 0.001 else (" ▼" if val < ref - 0.001 else "")
                print(f"    {aug_name:20s}: {val:.4f} (Δ={delta:+.4f}){marker}")

    elapsed = time.time() - t0
    print(f"\nTotal: {elapsed:.0f}s")

    # Save results
    out = {
        'experiment': 'EXP-377/378',
        'description': 'FDA at 6h/12h + augmentation at 12h',
        'device': str(device),
        'seeds': args.seeds,
        'elapsed_s': elapsed,
        'results': all_results,
    }
    os.makedirs('externals/experiments', exist_ok=True)
    with open('externals/experiments/exp377_fda_6h12h_augment.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved: externals/experiments/exp377_fda_6h12h_augment.json")


if __name__ == '__main__':
    main()
