#!/usr/bin/env python3
"""EXP-379: Per-Patient Fine-Tuning + FDA-Augment Combo at 12h

Research hints from docs indicate two high-impact untested ideas:

EXP-379a: Per-Patient Fine-Tuning (2h + 6h)
  EXP-326 showed 3-4% LOO generalization gap. Per-patient fine-tuning of best
  global model may recover this. Strategy: train global model on all patients,
  then fine-tune last layers on each patient's training data separately,
  evaluate on that patient's validation data.

  Tests: Transformer + baseline_plus_fda_10ch (universally best from EXP-377)
  at 2h and 6h scales with per-patient adaptation.

EXP-379b: FDA + Augmentation Combined at 12h
  EXP-377 showed FDA helps +1.4% at 12h. EXP-378 showed time_warp/mixup help
  +0.2-0.3%. Can we stack these gains? Test baseline_plus_fda_10ch + time_warp
  and baseline_plus_fda_10ch + mixup at 12h.

EXP-380: Multivariate FDA — Cross-Covariance Glucose-Insulin
  From FDA experiment proposals: compute cross-covariance eigenvalues between
  glucose and IOB functional representations. This captures interaction dynamics
  that separate derivatives miss. Hypothesis: the interaction structure between
  glucose trajectory and insulin state encodes physiological response patterns.

Usage:
    python tools/cgmencode/exp_per_patient_fda_combo.py
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse, math, copy
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score
from scipy.interpolate import UnivariateSpline, CubicSpline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features


# ── Shared data utilities ─────────────────────────────────────────────────

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
            raw_glucose = df['glucose'].values
            g_smooth, g_d1, g_d2 = smooth_glucose_series(raw_glucose)
            fda_3ch = np.column_stack([
                g_smooth / 400.0, g_d1 / 10.0, g_d2 / 5.0,
            ]).astype(np.float32)
            ml = min(len(base_8ch), len(fda_3ch))
            base_8ch = base_8ch[:ml].astype(np.float32)
            fda_3ch = fda_3ch[:ml]
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(fda_3ch, copy=False)

            # Build baseline_plus_fda_10ch per patient
            fda_10ch = np.concatenate([
                base_8ch[:, 0:1],   # glucose
                fda_3ch[:, 1:3],    # d1, d2
                base_8ch[:, 1:8],   # iob, cob, net_basal, bolus, carbs, time_sin, time_cos
            ], axis=1).astype(np.float32)

            # Also build cross-covariance features for EXP-380
            iob_smooth = base_8ch[:, 1]  # IOB already continuous
            # Cross-covariance: glucose_d1 * iob (interaction term)
            cross_gi = (g_d1 / 10.0) * (iob_smooth / np.maximum(np.abs(iob_smooth).max(), 1e-6))
            cross_gi = cross_gi.astype(np.float32)

            patients.append({
                'pid': pid,
                'base_8ch': base_8ch,
                'fda_10ch': fda_10ch,
                'cross_gi': cross_gi,
                'length': ml,
            })
            print(f"  {pid}: {ml} timesteps")
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")
    return patients


def window_patient(data, window_size, stride, feature_key='fda_10ch'):
    """Window a single patient's data, returning (windows, n_total)."""
    arr = data[feature_key] if isinstance(data, dict) else data
    ml = len(arr)
    windows = []
    for i in range(0, ml - window_size + 1, stride):
        windows.append(arr[i:i + window_size])
    if len(windows) < 5:
        return None
    return np.array(windows, dtype=np.float32)


def window_and_split_all(patients, window_size, stride, feature_key='fda_10ch'):
    """Window all patients, chronological split, return (train, val) + per-patient data."""
    all_train, all_val = [], []
    per_patient = {}
    for p in patients:
        w = window_patient(p, window_size, stride, feature_key)
        if w is None:
            continue
        n = len(w)
        s = int(n * 0.8)
        train, val = w[:s], w[s:]
        all_train.append(train)
        all_val.append(val)
        per_patient[p['pid']] = {'train': train, 'val': val}

    train = np.concatenate(all_train)
    val = np.concatenate(all_val)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(train))
    train = train[idx]
    return train, val, per_patient


# ── Labels ────────────────────────────────────────────────────────────────

def build_override_labels(windows, half):
    fg = windows[:, half:, 0] * 400.0
    hi = (fg > 180).any(axis=1)
    lo = (fg < 70).any(axis=1)
    labels = np.zeros(len(windows), dtype=np.int64)
    labels[hi] = 1
    labels[lo] = 2
    return labels

def build_hypo_labels(windows, half):
    return ((windows[:, half:, 0] * 400.0 < 70).any(axis=1)).astype(np.int64)

def build_prolonged_high_labels(windows, half):
    fg = windows[:, half:, 0] * 400.0
    return ((fg > 180).mean(axis=1) > 0.5).astype(np.int64)


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


def augment_mixup(x, y, alpha=0.3):
    B = len(x)
    lam = np.random.beta(alpha, alpha, size=(B, 1, 1)).astype(np.float32)
    idx = np.random.permutation(B)
    x_mixed = lam * x + (1 - lam) * x[idx]
    y_mixed = np.where(lam.squeeze() > 0.5, y, y[idx])
    return x_mixed, y_mixed


# ── Training ──────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_model(tx, ty, vx, vy, nc, device, in_ch,
                epochs=60, bs=256, patience=12, augment_fn=None, lr=1e-3):
    """Train global model, return (best_metric, best_state_dict)."""
    wt = compute_class_weights(ty, nc).to(device)
    val_ds = TensorDataset(torch.FloatTensor(vx), torch.LongTensor(vy))
    val_dl = DataLoader(val_ds, batch_size=bs * 2)

    model = TransformerClassifier(in_ch, nc).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit = nn.CrossEntropyLoss(weight=wt)

    best_val, best_state, wait = -1, None, 0
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
        metric = evaluate_model(model, val_dl, nc, device)

        if metric > best_val:
            best_val = metric
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    return best_val, best_state


def evaluate_model(model, val_dl, nc, device):
    """Evaluate a model on validation data."""
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
            return roc_auc_score(ytrue, probs[:, 1])
        except:
            return f1_score(ytrue, preds, average='binary')
    else:
        return f1_score(ytrue, preds, average='macro')


def fine_tune_model(base_state, tx, ty, vx, vy, nc, device, in_ch,
                    epochs=20, bs=64, lr=3e-4):
    """Fine-tune a pre-trained model on patient-specific data.
    Freeze encoder, only train fc head."""
    wt = compute_class_weights(ty, nc).to(device)
    model = TransformerClassifier(in_ch, nc).to(device)
    model.load_state_dict({k: v.to(device) for k, v in base_state.items()})

    # Freeze encoder layers, only fine-tune classification head
    for name, param in model.named_parameters():
        if 'fc' not in name:
            param.requires_grad = False

    val_ds = TensorDataset(torch.FloatTensor(vx), torch.LongTensor(vy))
    val_dl = DataLoader(val_ds, batch_size=bs * 2)
    train_ds = TensorDataset(torch.FloatTensor(tx), torch.LongTensor(ty))
    train_dl = DataLoader(train_ds, batch_size=min(bs, len(tx) // 2 + 1),
                          shuffle=True, drop_last=len(tx) > bs)

    opt = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()),
                            lr=lr, weight_decay=1e-4)
    crit = nn.CrossEntropyLoss(weight=wt)

    best_val, wait = -1, 0
    for ep in range(epochs):
        model.train()
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            crit(model(xb), yb).backward()
            opt.step()

        metric = evaluate_model(model, val_dl, nc, device)
        if metric > best_val:
            best_val = metric
            wait = 0
        else:
            wait += 1
            if wait >= 8:
                break
    return best_val


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    parser.add_argument('--skip-finetune', action='store_true')
    parser.add_argument('--skip-12h-combo', action='store_true')
    parser.add_argument('--skip-cross-cov', action='store_true')
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"EXP-379/380: Per-Patient Fine-Tuning + FDA-Augment Combo + Cross-Cov")
    print(f"Device: {device}, Seeds: {args.seeds}")

    patients = load_patient_features(args.patients_dir)
    all_results = {}
    t0 = time.time()

    tasks = {
        'override': (build_override_labels, 3, 'f1_macro'),
        'hypo': (build_hypo_labels, 2, 'auc'),
    }

    # ── EXP-379a: Per-Patient Fine-Tuning at 2h and 6h ───────────────────

    if not args.skip_finetune:
        for scale, (ws, stride, half) in [('2h', (24, 12, 12)), ('6h', (72, 36, 36))]:
            print(f"\n{'#' * 70}")
            print(f"# EXP-379a: Per-Patient Fine-Tuning at {scale}")
            print(f"{'#' * 70}")

            train_all, val_all, per_patient = window_and_split_all(
                patients, ws, stride, 'fda_10ch')
            nch = train_all.shape[2]
            print(f"  Global: {len(train_all)} train, {len(val_all)} val, {nch}ch")

            for tname, (label_fn, nc, metric_name) in tasks.items():
                print(f"\n  --- {tname} at {scale} ---")

                # Global labels
                ty_all = label_fn(train_all, half)
                vy_all = label_fn(val_all, half)
                tx_all = train_all[:, :half, :]
                vx_all = val_all[:, :half, :]

                global_scores = []
                ft_scores = []

                for seed in args.seeds:
                    torch.manual_seed(seed)
                    np.random.seed(seed)

                    # Train global model
                    global_metric, global_state = train_model(
                        tx_all, ty_all, vx_all, vy_all, nc, device, nch)
                    global_scores.append(global_metric)

                    # Per-patient fine-tuning
                    patient_ft_metrics = []
                    for pid, pdata in per_patient.items():
                        ptx = pdata['train'][:, :half, :]
                        pvx = pdata['val'][:, :half, :]
                        pty = label_fn(pdata['train'], half)
                        pvy = label_fn(pdata['val'], half)

                        if len(pvx) < 5 or len(np.unique(pvy)) < 2:
                            continue

                        ft_metric = fine_tune_model(
                            global_state, ptx, pty, pvx, pvy,
                            nc, device, nch)
                        patient_ft_metrics.append(ft_metric)

                    if patient_ft_metrics:
                        ft_scores.append(np.mean(patient_ft_metrics))

                global_mean = float(np.mean(global_scores))
                ft_mean = float(np.mean(ft_scores)) if ft_scores else global_mean
                delta = ft_mean - global_mean

                all_results[f"EXP379a_{scale}_{tname}_global"] = global_mean
                all_results[f"EXP379a_{scale}_{tname}_finetuned"] = ft_mean
                all_results[f"EXP379a_{scale}_{tname}_delta"] = delta

                print(f"    Global:     {global_mean:.4f}")
                print(f"    Fine-tuned: {ft_mean:.4f} (Δ={delta:+.4f})")

    # ── EXP-379b: FDA + Augmentation Combined at 12h ─────────────────────

    if not args.skip_12h_combo:
        print(f"\n{'#' * 70}")
        print(f"# EXP-379b: FDA + Augmentation Combined at 12h")
        print(f"{'#' * 70}")

        train_12, val_12, _ = window_and_split_all(patients, 144, 36, 'fda_10ch')
        half12 = 72
        nch = train_12.shape[2]
        print(f"  {len(train_12)} train, {len(val_12)} val, {nch}ch")

        combos = {
            'fda_only': None,
            'fda_time_warp': lambda x, y: (augment_time_warp(x, sigma=0.05), y),
            'fda_mixup': lambda x, y: augment_mixup(x, y, alpha=0.3),
        }

        for combo_name, aug_fn in combos.items():
            for tname, (label_fn, nc, metric_name) in tasks.items():
                ty = label_fn(train_12, half12)
                vy = label_fn(val_12, half12)
                tx = train_12[:, :half12, :]
                vx = val_12[:, :half12, :]

                scores = []
                for seed in args.seeds:
                    torch.manual_seed(seed)
                    np.random.seed(seed)
                    val, _ = train_model(tx, ty, vx, vy, nc, device, nch,
                                         epochs=80, patience=15, augment_fn=aug_fn)
                    scores.append(val)

                mean_val = float(np.mean(scores))
                all_results[f"EXP379b_12h_{combo_name}_{tname}"] = mean_val
                print(f"  [{combo_name}] {tname}: {mean_val:.4f}")

        # Summary
        print(f"\n{'=' * 60}")
        print("EXP-379b 12h FDA+Augment SUMMARY")
        print(f"{'=' * 60}")
        for tname in tasks:
            base = all_results.get(f'EXP379b_12h_fda_only_{tname}', 0)
            print(f"\n  {tname} (FDA baseline: {base:.4f}):")
            for combo_name in combos:
                val = all_results.get(f'EXP379b_12h_{combo_name}_{tname}', 0)
                delta = val - base
                marker = " ★" if delta > 0.001 else (" ▼" if delta < -0.001 else "")
                print(f"    {combo_name:20s}: {val:.4f} (Δ={delta:+.4f}){marker}")

    # ── EXP-380: Cross-Covariance Features ────────────────────────────────

    if not args.skip_cross_cov:
        print(f"\n{'#' * 70}")
        print(f"# EXP-380: Cross-Covariance Glucose-Insulin Features at 2h")
        print(f"{'#' * 70}")

        # Build cross-covariance augmented features (11ch)
        for p in patients:
            cross = p['cross_gi']
            ml = min(len(p['fda_10ch']), len(cross))
            p['fda_cross_11ch'] = np.concatenate([
                p['fda_10ch'][:ml],
                cross[:ml, np.newaxis],
            ], axis=1).astype(np.float32)

        train_cc, val_cc, _ = window_and_split_all(patients, 24, 12, 'fda_cross_11ch')
        train_base, val_base, _ = window_and_split_all(patients, 24, 12, 'fda_10ch')
        half2 = 12
        nch_cc = train_cc.shape[2]
        nch_base = train_base.shape[2]
        print(f"  Cross-cov 11ch: {len(train_cc)} train, {len(val_cc)} val")
        print(f"  FDA 10ch (control): {len(train_base)} train, {len(val_base)} val")

        for tname, (label_fn, nc, metric_name) in tasks.items():
            print(f"\n  --- {tname} ---")

            # Control: FDA 10ch
            ty = label_fn(train_base, half2)
            vy = label_fn(val_base, half2)
            tx = train_base[:, :half2, :]
            vx = val_base[:, :half2, :]

            scores_base = []
            for seed in args.seeds:
                torch.manual_seed(seed)
                np.random.seed(seed)
                val, _ = train_model(tx, ty, vx, vy, nc, device, nch_base)
                scores_base.append(val)

            # Cross-cov: FDA 11ch
            ty_cc = label_fn(train_cc, half2)
            vy_cc = label_fn(val_cc, half2)
            tx_cc = train_cc[:, :half2, :]
            vx_cc = val_cc[:, :half2, :]

            scores_cc = []
            for seed in args.seeds:
                torch.manual_seed(seed)
                np.random.seed(seed)
                val, _ = train_model(tx_cc, ty_cc, vx_cc, vy_cc, nc, device, nch_cc)
                scores_cc.append(val)

            base_mean = float(np.mean(scores_base))
            cc_mean = float(np.mean(scores_cc))
            delta = cc_mean - base_mean

            all_results[f"EXP380_2h_fda_10ch_{tname}"] = base_mean
            all_results[f"EXP380_2h_fda_cross_11ch_{tname}"] = cc_mean

            marker = " ★" if delta > 0.001 else (" ▼" if delta < -0.001 else "")
            print(f"    FDA 10ch (control): {base_mean:.4f}")
            print(f"    FDA+cross_cov 11ch: {cc_mean:.4f} (Δ={delta:+.4f}){marker}")

    elapsed = time.time() - t0
    print(f"\nTotal: {elapsed:.0f}s")

    out = {
        'experiment': 'EXP-379/380',
        'description': 'Per-patient fine-tuning + FDA-augment combo + cross-covariance',
        'device': str(device),
        'seeds': args.seeds,
        'elapsed_s': elapsed,
        'results': all_results,
    }
    os.makedirs('externals/experiments', exist_ok=True)
    with open('externals/experiments/exp379_per_patient_fda_combo.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved: externals/experiments/exp379_per_patient_fda_combo.json")


if __name__ == '__main__':
    main()
