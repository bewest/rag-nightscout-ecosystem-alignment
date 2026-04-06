#!/usr/bin/env python3
"""EXP-362: Transformer + Feature Variants at Episode Scales (6h, 12h)

Combines the two best findings from prior experiments:
- EXP-361: Transformer is the best architecture at 12h (+0.4% override, +1.0% prolonged_high)
- EXP-360: Hybrid raw+FDA+PK features help at 6h (+0.7-2.3%)

Hypothesis: Transformer's global attention can better exploit hybrid features
than DeepCNN at both 6h and 12h. The CNN's limited receptive field may have
masked feature benefits — transformer's full-sequence attention should let
PK/FDA channels contribute across the entire history window.

Tests transformer vs deep_cnn with the best feature variants from EXP-360:
  baseline_8ch       : Standard control
  raw_plus_fda_8ch   : Best 6h override in EXP-360
  raw_fda_pk_8ch     : Best 6h prolonged_high in EXP-360
  kitchen_sink_10ch  : Most channels (tests if transformer handles more dims)

─── Cross-thread coordination ───

  EXPERIMENT ID REGISTRY: This file owns EXP-362. Forecasting thread owns
  EXP-360–368. Normalization runner (exp_normalization_conditioning.py) owns
  EXP-369–376. Next available for this thread: EXP-385+.

  DIRECTIONS THAT STAY IN YOUR LANE (transformer × features, won't conflict):
  1. Attention head specialization: Do different heads attend to different
     feature channels? Visualize per-head attention to understand if the
     transformer self-organizes into glucose-head, PK-head, FDA-head, etc.
  2. Feature dropout ablation: Systematically drop one feature variant at a
     time from kitchen_sink_10ch to find minimal effective feature set for
     transformer. Unlike CNN, transformer may be robust to more channels.
  3. Cross-scale transfer: Pre-train transformer on 12h windows (more data),
     then fine-tune on 6h. Tests if long-context pre-training helps the
     scale where features struggle most.
  4. Positional encoding ablation: Remove sinusoidal positional encoding at
     12h (time-translation invariance was proven at ≤12h, EXP-349). Transformer
     without position encoding = pure set function on timestep features.

  NOTE: ISF normalization, z-score, EMA, glucodensity, depth features are
  being developed in exp_normalization_conditioning.py (EXP-369+). Once
  validated, they become new feature variants to test here with transformer.

Usage:
    python tools/cgmencode/exp_transformer_features.py [--scales 6h 12h]
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

SCALE_CONFIGS = {
    '6h':  {'window_size': 72,  'stride': 36, 'label': '3h history → 3h prediction'},
    '12h': {'window_size': 144, 'stride': 36, 'label': '6h history → 6h prediction'},
}


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


# ── Feature variants ─────────────────────────────────────────────────────

VARIANT_DEFS = {
    'baseline_8ch': {
        'desc': 'Standard 8ch (control)',
        'build': lambda b, p, f: b,
    },
    'raw_plus_fda_8ch': {
        'desc': 'Raw glucose + FDA derivatives + treatment (no time)',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:6],     # iob, cob, net_basal, bolus, carbs
        ], axis=2),
    },
    'raw_fda_pk_8ch': {
        'desc': 'Raw glucose + FDA d1 + PK state + treatment core',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:2],     # glucose_d1
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 2:3],     # pk basal_ratio
            b[:, :, 1:2],     # iob
            b[:, :, 3:4],     # net_basal
        ], axis=2),
    },
    'kitchen_sink_10ch': {
        'desc': 'Raw + FDA deriv + PK state (10ch)',
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
}
VARIANT_ORDER = list(VARIANT_DEFS.keys())


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


TASKS = {
    'override':       {'fn': build_override_labels,       'nc': 3, 'pm': 'f1_macro'},
    'hypo':           {'fn': build_hypo_labels,           'nc': 2, 'pm': 'auc'},
    'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1'},
}


# ── Architectures ─────────────────────────────────────────────────────────

class DeepCNN(nn.Module):
    """Control: 4-layer CNN, RF=9."""
    def __init__(self, in_ch, nc):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(128),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        return self.fc(self.conv(x.permute(0, 2, 1)).squeeze(-1))


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
    """Transformer encoder with global attention."""
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


ARCH_DEFS = {
    'deep_cnn': {'desc': 'DeepCNN control (RF=9)', 'cls': DeepCNN},
    'transformer': {'desc': 'Transformer 2L/4H/d64 (global)', 'cls': TransformerClassifier},
}
ARCH_ORDER = list(ARCH_DEFS.keys())


# ── Training ─────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, arch_cls, half, epochs=60, bs=256, patience=12):
    in_ch = tx.shape[2]
    model = arch_cls(in_ch, nc).to(device)
    w = compute_class_weights(ty, nc).to(device)
    crit = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)

    th = torch.from_numpy(tx[:, :half].copy()).float()
    vh = torch.from_numpy(vx[:, :half].copy()).float()
    ds = TensorDataset(th, torch.from_numpy(ty).long())
    dl = DataLoader(ds, batch_size=bs, shuffle=True, pin_memory=(device.type == 'cuda'))

    best_m, best_p, best_pr, wait = -1, None, None, 0
    for ep in range(epochs):
        model.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(); crit(model(xb), yb).backward(); opt.step()
        model.eval()
        with torch.no_grad():
            logits = model(vh.to(device))
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
            if wait >= patience: break

    nparams = sum(p.numel() for p in model.parameters())
    r = {'epochs': ep + 1, 'in_channels': in_ch, 'history_steps': half, 'param_count': nparams}
    if nc == 2:
        r['f1'] = float(f1_score(vy, best_p, average='binary', zero_division=0))
        try: r['auc'] = float(roc_auc_score(vy, best_pr[:, 1]))
        except: r['auc'] = 0.0
        r['prevalence'] = float(vy.mean())
    else:
        r['f1_macro'] = float(f1_score(vy, best_p, average='macro', zero_division=0))
        r['f1_per_class'] = [float(x) for x in f1_score(vy, best_p, average=None, zero_division=0)]
    return r


def run_scale(scale_name, patients, device, seeds):
    cfg = SCALE_CONFIGS[scale_name]
    ws = cfg['window_size']
    half = ws // 2
    print(f"\n{'#'*70}")
    print(f"# SCALE: {scale_name} — {cfg['label']}")
    print(f"{'#'*70}")

    bt, bv, pt, pv, ft, fv = window_and_split(patients, ws, cfg['stride'])
    print(f"  {len(bt)} train, {len(bv)} val")

    lab = {}
    for tname, tdef in TASKS.items():
        ty = tdef['fn'](bt, half)
        vy = tdef['fn'](bv, half)
        lab[tname] = (ty, vy)
        if tdef['nc'] == 2:
            print(f"  {tname}: prev={vy.mean():.3f}")
        else:
            from collections import Counter
            print(f"  {tname}: dist={sorted(Counter(ty).items())}")

    results = {}
    for arch_name in ARCH_ORDER:
        arch_cls = ARCH_DEFS[arch_name]['cls']
        results[arch_name] = {}

        for feat_name in VARIANT_ORDER:
            fdef = VARIANT_DEFS[feat_name]
            tx = fdef['build'](bt, pt, ft)
            vx = fdef['build'](bv, pv, fv)

            print(f"\n{'='*60}")
            print(f"[{scale_name}] {arch_name} + {feat_name}")
            print(f"{'='*60}")
            print(f"  {tx.shape[2]}ch, shape: {tx.shape}")

            results[arch_name][feat_name] = {}
            for tname, tdef in TASKS.items():
                ty, vy = lab[tname]
                nc, pm = tdef['nc'], tdef['pm']

                seed_results = []
                for s in seeds:
                    torch.manual_seed(s)
                    np.random.seed(s)
                    r = train_and_eval(tx, ty, vx, vy, nc, device, arch_cls, half)
                    seed_results.append(r)

                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], float):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                    elif isinstance(seed_results[0][k], list):
                        avg[k] = [float(np.mean([sr[k][i] for sr in seed_results]))
                                  for i in range(len(seed_results[0][k]))]
                    else:
                        avg[k] = seed_results[0][k]

                results[arch_name][feat_name][tname] = avg
                val = avg.get(pm, avg.get('f1_macro', avg.get('auc', 0)))
                print(f"  {tname}: {pm}={val:.4f}")

    # Summary table
    print(f"\n{'='*70}")
    print(f"[{scale_name}] SUMMARY")
    print(f"{'='*70}")
    ctrl = results.get('deep_cnn', {}).get('baseline_8ch', {})
    for tname, tdef in TASKS.items():
        pm = tdef['pm']
        ctrl_val = ctrl.get(tname, {}).get(pm, 0)
        print(f"\n  {tname} ({pm}):")
        best_val, best_combo = -1, ''
        for arch in ARCH_ORDER:
            for feat in VARIANT_ORDER:
                val = results.get(arch, {}).get(feat, {}).get(tname, {}).get(pm, 0)
                delta = val - ctrl_val
                tag = ' ★' if val > best_val else ''
                if val > best_val:
                    best_val, best_combo = val, f"{arch}+{feat}"
                print(f"    {arch:15s} + {feat:20s}: {val:.4f} (Δ={delta:+.4f}){tag}")
        print(f"    → BEST: {best_combo} = {best_val:.4f} (Δ={best_val-ctrl_val:+.4f})")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    parser.add_argument('--scales', nargs='+', default=['6h', '12h'])
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"EXP-362: Transformer + Feature Variants at Episode Scales")
    print(f"Device: {device}, Seeds: {args.seeds}, Scales: {args.scales}")

    t0 = time.time()
    patients = load_patient_features(args.patients_dir)

    all_results = {}
    for scale in args.scales:
        all_results[scale] = run_scale(scale, patients, device, args.seeds)

    elapsed = time.time() - t0

    # Cross-scale summary
    print(f"\n{'#'*70}")
    print(f"# CROSS-SCALE: Transformer vs DeepCNN interaction with features")
    print(f"{'#'*70}")
    for tname, tdef in TASKS.items():
        pm = tdef['pm']
        print(f"\n  {tname} ({pm}):")
        for scale in args.scales:
            sr = all_results.get(scale, {})
            ctrl = sr.get('deep_cnn', {}).get('baseline_8ch', {}).get(tname, {}).get(pm, 0)
            best_val, best_combo = ctrl, 'deep_cnn+baseline_8ch'
            for arch in ARCH_ORDER:
                for feat in VARIANT_ORDER:
                    val = sr.get(arch, {}).get(feat, {}).get(tname, {}).get(pm, 0)
                    if val > best_val:
                        best_val, best_combo = val, f"{arch}+{feat}"
            print(f"    {scale}: best={best_combo:40s} val={best_val:.4f} (Δ={best_val-ctrl:+.4f})")

    print(f"\nTotal: {elapsed:.0f}s")

    out = {
        'experiment': 'EXP-362',
        'title': 'Transformer + Feature Variants at Episode Scales',
        'seeds': args.seeds,
        'scales': args.scales,
        'architectures': {k: v['desc'] for k, v in ARCH_DEFS.items()},
        'features': {k: v['desc'] for k, v in VARIANT_DEFS.items()},
        'results': all_results,
        'elapsed_seconds': elapsed,
    }
    outpath = 'externals/experiments/exp362_transformer_features.json'
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved: {outpath}")


if __name__ == '__main__':
    main()
