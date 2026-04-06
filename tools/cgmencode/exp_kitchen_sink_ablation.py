#!/usr/bin/env python3
"""EXP-375: Kitchen Sink Channel Ablation at 2h
   EXP-376: Positional Encoding Ablation at 2h

EXP-374 showed Transformer+kitchen_sink_10ch achieves override F1=0.866 (+2.3%).
kitchen_sink_10ch = [glucose, glucose_d1, glucose_d2, iob, cob, net_basal,
                     pk_net_balance, pk_insulin_total, pk_carb_rate, pk_basal_ratio]

vs baseline_8ch = [glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos]

The +2.3% could come from:
  - Adding FDA derivatives (d1, d2)
  - Adding PK channels (net_balance, insulin_total, carb_rate, basal_ratio)
  - Removing time features (time_sin, time_cos)
  - Removing raw bolus/carbs (replaced by PK equivalents)

EXP-375 ablations (all Transformer at 2h):
  1. kitchen_sink_10ch           (control, best from EXP-374)
  2. kitchen_no_fda_8ch          (remove glucose_d1, d2 → PK contribution only)
  3. kitchen_no_pk_6ch           (remove PK channels → FDA contribution only)
  4. baseline_plus_fda_10ch      (add FDA to baseline, keep time/bolus/carbs)
  5. baseline_no_time_plus_fda_8ch  (baseline -time +FDA deriv)
  6. baseline_plus_pk_12ch       (add PK to baseline, keep everything)
  7. kitchen_plus_time_12ch      (add time back to kitchen_sink)
  8. minimal_override_5ch        (glucose, glucose_d1, iob, pk_net_balance, pk_basal_ratio)

EXP-376: PE ablation (Transformer at 2h, kitchen_sink_10ch):
  9. tfm_no_pe + kitchen_sink    (remove sinusoidal PE entirely)

Usage:
    python tools/cgmencode/exp_kitchen_sink_ablation.py
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features


# ── Data loading ─────────────────────────────────────────────────────────

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


# ── Feature variants for ablation ────────────────────────────────────────

# base channels: [0:glucose, 1:iob, 2:cob, 3:net_basal, 4:bolus, 5:carbs, 6:time_sin, 7:time_cos]
# pk channels:   [0:insulin_total, 1:insulin_effect, 2:basal_ratio, 3:carb_rate,
#                  4:carb_effect, 5:carb_total, 6:net_balance, 7:net_effect]
# fda channels:  [0:smooth_glucose, 1:glucose_d1, 2:glucose_d2]

VARIANT_DEFS = {
    # Control: kitchen_sink_10ch (EXP-374 best)
    'kitchen_sink_10ch': {
        'desc': '[glucose, d1, d2, iob, cob, net_basal, pk_net_bal, pk_ins_total, pk_carb_rate, pk_basal_ratio]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:4],     # iob, cob, net_basal
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 2:3],     # pk basal_ratio
        ], axis=2),
    },
    # Ablation 1: Remove FDA derivatives → isolate PK contribution
    'kitchen_no_fda_8ch': {
        'desc': '[glucose, iob, cob, net_basal, pk_net_bal, pk_ins_total, pk_carb_rate, pk_basal_ratio]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            b[:, :, 1:4],     # iob, cob, net_basal
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 2:3],     # pk basal_ratio
        ], axis=2),
    },
    # Ablation 2: Remove PK channels → isolate FDA contribution
    'kitchen_no_pk_6ch': {
        'desc': '[glucose, d1, d2, iob, cob, net_basal]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:4],     # iob, cob, net_basal
        ], axis=2),
    },
    # Ablation 3: Add FDA to baseline (keep time, bolus, carbs)
    'baseline_plus_fda_10ch': {
        'desc': '[glucose, d1, d2, iob, cob, net_basal, bolus, carbs, time_sin, time_cos]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:8],     # iob, cob, net_basal, bolus, carbs, time_sin, time_cos
        ], axis=2),
    },
    # Ablation 4: Baseline no_time + FDA derivatives
    'base_notime_fda_8ch': {
        'desc': '[glucose, d1, d2, iob, cob, net_basal, bolus, carbs]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:6],     # iob, cob, net_basal, bolus, carbs
        ], axis=2),
    },
    # Ablation 5: Baseline + PK (keep everything + add PK)
    'baseline_plus_pk_12ch': {
        'desc': '[baseline_8ch + pk_net_bal, pk_ins_total, pk_carb_rate, pk_basal_ratio]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, :8],      # full baseline
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 2:3],     # pk basal_ratio
        ], axis=2),
    },
    # Ablation 6: Kitchen sink + time features (test if time hurts kitchen)
    'kitchen_plus_time_12ch': {
        'desc': '[kitchen_sink_10ch + time_sin, time_cos]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:4],     # iob, cob, net_basal
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 2:3],     # pk basal_ratio
            b[:, :, 6:8],     # time_sin, time_cos
        ], axis=2),
    },
    # Ablation 7: Minimal override-focused set
    'minimal_override_5ch': {
        'desc': '[glucose, d1, iob, pk_net_bal, pk_basal_ratio]',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:2],     # glucose_d1
            b[:, :, 1:2],     # iob
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 2:3],     # pk basal_ratio
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

def build_uam_labels(bw, half):
    fg = bw[:, half:, 0] * 400.0
    rising = (np.diff(fg, axis=1) > 2.0).any(axis=1)
    carbs_present = (bw[:, :half, 5] > 0).any(axis=1)
    return (rising & ~carbs_present).astype(np.int64)


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
    def __init__(self, in_ch, nc, d_model=64, nhead=4, nlayers=2, dropout=0.1, use_pe=True):
        super().__init__()
        self.input_proj = nn.Linear(in_ch, d_model)
        self.use_pe = use_pe
        if use_pe:
            self.pos_enc = PositionalEncoding(d_model, max_len=200)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=128,
            dropout=dropout, batch_first=True, activation='gelu',
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=nlayers)
        self.fc = nn.Sequential(nn.Linear(d_model, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        h = self.input_proj(x)
        if self.use_pe:
            h = self.pos_enc(h)
        h = self.encoder(h)
        h = h.mean(dim=1)
        return self.fc(h)


# ── Training ─────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, make_model_fn,
                   epochs=60, bs=256, patience=12):
    """Train a model and return the eval metric."""
    wt = compute_class_weights(ty, nc).to(device)
    train_ds = TensorDataset(torch.FloatTensor(tx), torch.LongTensor(ty))
    val_ds = TensorDataset(torch.FloatTensor(vx), torch.LongTensor(vy))
    train_dl = DataLoader(train_ds, batch_size=bs, shuffle=True, drop_last=True)
    val_dl = DataLoader(val_ds, batch_size=bs * 2)

    model = make_model_fn().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit = nn.CrossEntropyLoss(weight=wt)

    best_val, best_state, wait = -1, None, 0
    for ep in range(epochs):
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


def run_config(name, variant_key, task_name, build_fn, base_t, base_v, pk_t, pk_v,
               fda_t, fda_v, half, device, seeds, use_pe=True):
    """Run one config across seeds, return mean metric."""
    vdef = VARIANT_DEFS[variant_key]
    tx_full = vdef['build'](base_t, pk_t, fda_t)
    vx_full = vdef['build'](base_v, pk_v, fda_v)
    nch = tx_full.shape[2]

    # Build labels from baseline (glucose in ch0 for all variants)
    if task_name == 'uam':
        ty = build_uam_labels(base_t, half)
        vy = build_uam_labels(base_v, half)
        nc = 2
    elif task_name == 'override':
        ty = build_override_labels(base_t, half)
        vy = build_override_labels(base_v, half)
        nc = 3
    elif task_name == 'hypo':
        ty = build_hypo_labels(base_t, half)
        vy = build_hypo_labels(base_v, half)
        nc = 2

    # Mask future values: only first half is input
    tx = tx_full[:, :half, :]
    vx = vx_full[:, :half, :]

    results = []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        def make_model():
            return TransformerClassifier(nch, nc, use_pe=use_pe)
        val = train_and_eval(tx, ty, vx, vy, nc, device, make_model)
        results.append(val)

    mean_val = float(np.mean(results))
    return mean_val


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"EXP-375/376: Kitchen Sink Ablation + PE Ablation at 2h")
    print(f"Device: {device}, Seeds: {args.seeds}")

    patients = load_patient_features(args.patients_dir)
    window_size = 24
    stride = 12
    half = window_size // 2

    bt, bv, pt, pv, ft, fv = window_and_split(patients, window_size, stride)
    print(f"  {len(bt)} train, {len(bv)} val")

    # Show label distributions
    ov_t = build_override_labels(bt, half)
    hy_t = build_hypo_labels(bt, half)
    uam_t = build_uam_labels(bt, half)
    print(f"  override: dist={sorted(zip(*np.unique(ov_t, return_counts=True)))}")
    print(f"  hypo: train_prev={hy_t.mean():.3f}")
    print(f"  uam: train_prev={uam_t.mean():.3f}")

    results = {}
    t0 = time.time()

    # ── EXP-375: Feature ablation (all with Transformer + PE) ────────────

    print("\n" + "#" * 70)
    print("# EXP-375: Kitchen Sink Channel Ablation at 2h (Transformer)")
    print("#" * 70)

    ablation_variants = [
        'kitchen_sink_10ch',       # control
        'kitchen_no_fda_8ch',      # remove FDA → PK only
        'kitchen_no_pk_6ch',       # remove PK → FDA only
        'baseline_plus_fda_10ch',  # add FDA to baseline (keep time/bolus/carbs)
        'base_notime_fda_8ch',     # baseline -time +FDA
        'baseline_plus_pk_12ch',   # add PK to baseline (keep everything)
        'kitchen_plus_time_12ch',  # add time back to kitchen
        'minimal_override_5ch',    # minimal feature set
    ]

    tasks_2h = {
        'uam': ('uam', 'f1'),
        'override': ('override', 'f1_macro'),
        'hypo': ('hypo', 'auc'),
    }

    for vkey in ablation_variants:
        vdef = VARIANT_DEFS[vkey]
        test_arr = vdef['build'](bt[:1], pt[:1], ft[:1])
        nch = test_arr.shape[2]
        print(f"\n{'='*60}")
        print(f"[2h] {vkey}: {nch}ch — {vdef['desc']}")
        print(f"{'='*60}")

        for tname, (task_key, metric_type) in tasks_2h.items():
            val = run_config(
                f"ablation_{vkey}_{tname}", vkey, task_key,
                lambda: None, bt, bv, pt, pv, ft, fv, half, device,
                args.seeds, use_pe=True,
            )
            rkey = f"EXP375_ablation_{vkey}_{tname}"
            results[rkey] = val
            print(f"  {tname}: {val:.4f}")

    # ── EXP-376: PE ablation (Transformer without positional encoding) ──

    print("\n" + "#" * 70)
    print("# EXP-376: Positional Encoding Ablation at 2h")
    print("#" * 70)

    pe_variants = ['kitchen_sink_10ch', 'kitchen_no_pk_6ch']
    for vkey in pe_variants:
        vdef = VARIANT_DEFS[vkey]
        test_arr = vdef['build'](bt[:1], pt[:1], ft[:1])
        nch = test_arr.shape[2]
        print(f"\n{'='*60}")
        print(f"[2h] NO_PE + {vkey}: {nch}ch — {vdef['desc']}")
        print(f"{'='*60}")

        for tname, (task_key, metric_type) in tasks_2h.items():
            val = run_config(
                f"no_pe_{vkey}_{tname}", vkey, task_key,
                lambda: None, bt, bv, pt, pv, ft, fv, half, device,
                args.seeds, use_pe=False,
            )
            rkey = f"EXP376_no_pe_{vkey}_{tname}"
            results[rkey] = val
            print(f"  {tname}: {val:.4f}")

    elapsed = time.time() - t0

    # ── Summary ──────────────────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("EXP-375 ABLATION SUMMARY (Transformer at 2h)")
    print("=" * 70)

    # Get baseline reference from EXP-374
    base_ref = {
        'uam': results.get('EXP375_ablation_kitchen_sink_10ch_uam', 0),
        'override': results.get('EXP375_ablation_kitchen_sink_10ch_override', 0),
        'hypo': results.get('EXP375_ablation_kitchen_sink_10ch_hypo', 0),
    }

    for tname in ['uam', 'override', 'hypo']:
        print(f"\n  {tname}:")
        ref = base_ref[tname]
        task_results = []
        for vkey in ablation_variants:
            rkey = f"EXP375_ablation_{vkey}_{tname}"
            val = results.get(rkey, 0)
            delta = val - ref
            marker = " ★" if val > ref + 0.001 else (" ▼" if val < ref - 0.001 else "")
            task_results.append((vkey, val, delta))
            nch = VARIANT_DEFS[vkey]['build'](bt[:1], pt[:1], ft[:1]).shape[2]
            print(f"    {vkey:30s} ({nch:2d}ch): {val:.4f} (Δ={delta:+.4f}){marker}")
        # Best
        best = max(task_results, key=lambda x: x[1])
        print(f"    → BEST: {best[0]} = {best[1]:.4f}")

    print("\n" + "=" * 70)
    print("EXP-376 PE ABLATION SUMMARY")
    print("=" * 70)

    for vkey in pe_variants:
        print(f"\n  {vkey}:")
        for tname in ['uam', 'override', 'hypo']:
            with_pe = results.get(f"EXP375_ablation_{vkey}_{tname}", 0)
            without_pe = results.get(f"EXP376_no_pe_{vkey}_{tname}", 0)
            delta = without_pe - with_pe
            marker = " ★" if delta > 0.001 else (" ▼" if delta < -0.001 else "")
            print(f"    {tname:10s}: PE={with_pe:.4f}, no_PE={without_pe:.4f} (Δ={delta:+.4f}){marker}")

    print(f"\nTotal: {elapsed:.0f}s")

    # ── Channel contribution analysis ─────────────────────────────────────

    print("\n" + "=" * 70)
    print("CHANNEL CONTRIBUTION ANALYSIS (Override F1)")
    print("=" * 70)
    ks = results.get('EXP375_ablation_kitchen_sink_10ch_override', 0)
    no_fda = results.get('EXP375_ablation_kitchen_no_fda_8ch_override', 0)
    no_pk = results.get('EXP375_ablation_kitchen_no_pk_6ch_override', 0)
    print(f"  kitchen_sink_10ch (full):     {ks:.4f}")
    print(f"  - FDA derivatives removed:    {no_fda:.4f} (Δ={no_fda-ks:+.4f}) → FDA contributes {ks-no_fda:+.4f}")
    print(f"  - PK channels removed:        {no_pk:.4f} (Δ={no_pk-ks:+.4f}) → PK contributes {ks-no_pk:+.4f}")
    print(f"  Interaction term: {ks - no_fda - no_pk + ks:.4f} (non-additive if ≠ {ks:.4f})")

    # Save results
    out = {
        'experiment': 'EXP-375/376',
        'description': 'Kitchen sink ablation + PE ablation at 2h',
        'device': str(device),
        'seeds': args.seeds,
        'window_size': window_size,
        'stride': stride,
        'n_train': len(bt),
        'n_val': len(bv),
        'elapsed_s': elapsed,
        'results': results,
        'variants': {k: v['desc'] for k, v in VARIANT_DEFS.items()},
    }
    os.makedirs('externals/experiments', exist_ok=True)
    with open('externals/experiments/exp375_kitchen_ablation.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved: externals/experiments/exp375_kitchen_ablation.json")


if __name__ == '__main__':
    main()
