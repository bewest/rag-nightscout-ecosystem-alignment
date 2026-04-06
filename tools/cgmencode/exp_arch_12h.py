#!/usr/bin/env python3
"""EXP-361: Architecture Search at 12h Episode Scale

Tests whether the DeepCNN's limited receptive field (RF=9 steps = 45min,
only 6.2% of 144-step 12h window) is the bottleneck preventing feature
variants from beating baseline at 12h.

Hypothesis: At 12h, the CNN's receptive field is too small to learn
long-range temporal dependencies. Features like PK channels and FDA
derivatives encode distant temporal relationships but the CNN can't
exploit them because it only "sees" 45 minutes at a time.

Architecture variants tested:
  deep_cnn       : Current DeepCNN (control). RF=9 steps.
  dilated_cnn    : Dilated convolutions d=[1,2,4,8,16]. RF=63 steps (43.8%).
  transformer    : 2-layer TransformerEncoder, d=64, 4 heads. Global attention.
  cnn_downsample : Input downsampled 2x (72 steps at 10min). RF=9/72=12.5%.
  large_kernel   : Conv1d k=7 (4 layers). RF=25 steps (17.4%).
  se_cnn         : DeepCNN + Squeeze-and-Excitation channel attention.

Runs with baseline_8ch AND pk_no_time_6ch (the two best 12h features from
prior experiments) to test if better architecture unlocks PK benefit.

Usage:
    python tools/cgmencode/exp_arch_12h.py [--device cuda] [--seeds 42 123 456]
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

WINDOW_SIZE = 144  # 12h at 5min
STRIDE = 36
HALF = WINDOW_SIZE // 2  # 72 steps = 6h history


# ── Data loading (reused from EXP-360) ───────────────────────────────────

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


def window_and_split(patients, window_size=WINDOW_SIZE, stride=STRIDE):
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

FEATURE_VARIANTS = {
    'baseline_8ch': {
        'desc': 'Standard 8ch (control)',
        'build': lambda b, p, f: b,
    },
    'pk_no_time_6ch': {
        'desc': 'EXP-350 12h override winner',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # glucose
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 2:3],     # pk basal_ratio
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 4:5],     # pk carb_accel
        ], axis=2),
    },
}
FEATURE_ORDER = list(FEATURE_VARIANTS.keys())


# ── Labels ────────────────────────────────────────────────────────────────

def build_override_labels(bw):
    fg = bw[:, HALF:, 0] * 400.0
    hi = (fg > 180).any(axis=1)
    lo = (fg < 70).any(axis=1)
    labels = np.zeros(len(bw), dtype=np.int64)
    labels[hi] = 1; labels[lo] = 2
    return labels

def build_hypo_labels(bw):
    return ((bw[:, HALF:, 0] * 400.0 < 70).any(axis=1)).astype(np.int64)

def build_prolonged_high_labels(bw):
    fg = bw[:, HALF:, 0] * 400.0
    return ((fg > 180).mean(axis=1) > 0.5).astype(np.int64)


TASKS = {
    'override':       {'fn': build_override_labels,       'nc': 3, 'pm': 'f1_macro'},
    'hypo':           {'fn': build_hypo_labels,           'nc': 2, 'pm': 'auc'},
    'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1'},
}


# ── Architecture variants ────────────────────────────────────────────────

class DeepCNN(nn.Module):
    """Control: current 4-layer CNN. RF=9 steps."""
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


class DilatedCNN(nn.Module):
    """Dilated convolutions for exponential receptive field growth.
    5 layers with dilations [1, 2, 4, 8, 16], k=3: RF = 63 steps (43.8%)."""
    def __init__(self, in_ch, nc):
        super().__init__()
        layers = []
        ch = [in_ch, 32, 64, 64, 128, 128]
        dilations = [1, 2, 4, 8, 16]
        for i, d in enumerate(dilations):
            layers.extend([
                nn.Conv1d(ch[i], ch[i + 1], 3, padding=d, dilation=d),
                nn.ReLU(),
                nn.BatchNorm1d(ch[i + 1]),
            ])
        layers.append(nn.AdaptiveAvgPool1d(1))
        self.conv = nn.Sequential(*layers)
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
    """Transformer encoder with global attention. Sees entire sequence."""
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
        # x: (B, T, C)
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.encoder(h)
        h = h.mean(dim=1)  # global average pooling over time
        return self.fc(h)


class LargeKernelCNN(nn.Module):
    """CNN with k=7 kernels. 4 layers: RF = 25 steps (17.4%).
    Also uses stride-2 at first layer for 2x downsampling."""
    def __init__(self, in_ch, nc):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 7, padding=3, stride=2), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 7, padding=3), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, 7, padding=3), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 7, padding=3), nn.ReLU(), nn.BatchNorm1d(128),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        return self.fc(self.conv(x.permute(0, 2, 1)).squeeze(-1))


class SEBlock(nn.Module):
    """Squeeze-and-Excitation: learns per-channel attention weights."""
    def __init__(self, channels, reduction=4):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(channels, max(channels // reduction, 4)),
            nn.ReLU(),
            nn.Linear(max(channels // reduction, 4), channels),
            nn.Sigmoid(),
        )

    def forward(self, x):
        # x: (B, C, T)
        w = x.mean(dim=2)  # squeeze: (B, C)
        w = self.fc(w).unsqueeze(2)  # excite: (B, C, 1)
        return x * w


class SE_CNN(nn.Module):
    """DeepCNN + Squeeze-and-Excitation channel attention.
    SE blocks after conv layers 2 and 4 let model learn which channels matter."""
    def __init__(self, in_ch, nc):
        super().__init__()
        self.block1 = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
        )
        self.se1 = SEBlock(64)
        self.pool = nn.MaxPool1d(2)
        self.block2 = nn.Sequential(
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(128),
        )
        self.se2 = SEBlock(128)
        self.gap = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        h = x.permute(0, 2, 1)
        h = self.se1(self.block1(h))
        h = self.pool(h)
        h = self.se2(self.block2(h))
        h = self.gap(h).squeeze(-1)
        return self.fc(h)


ARCH_VARIANTS = {
    'deep_cnn': {
        'desc': 'Control: 4-layer CNN, RF=9 (6.2%)',
        'cls': DeepCNN,
        'downsample': False,
    },
    'dilated_cnn': {
        'desc': 'Dilated d=[1,2,4,8,16], RF=63 (43.8%)',
        'cls': DilatedCNN,
        'downsample': False,
    },
    'transformer': {
        'desc': 'TransformerEncoder 2L/4H/d64, global attention',
        'cls': TransformerClassifier,
        'downsample': False,
    },
    'cnn_downsample': {
        'desc': 'DeepCNN on 2x downsampled input (72 steps at 10min)',
        'cls': DeepCNN,
        'downsample': True,  # 144 → 72 steps
    },
    'large_kernel': {
        'desc': 'k=7 CNN with stride-2 first layer, RF≈49',
        'cls': LargeKernelCNN,
        'downsample': False,
    },
    'se_cnn': {
        'desc': 'DeepCNN + SE channel attention',
        'cls': SE_CNN,
        'downsample': False,
    },
}
ARCH_ORDER = list(ARCH_VARIANTS.keys())


# ── Training ─────────────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, arch_name, epochs=60, bs=256, patience=12):
    """Train architecture variant and evaluate."""
    arch = ARCH_VARIANTS[arch_name]
    in_ch = tx.shape[2]
    half = HALF

    # History only
    th = tx[:, :half].copy()
    vh = vx[:, :half].copy()

    # Downsample if needed (average consecutive pairs: 5min → 10min)
    if arch['downsample']:
        th = (th[:, 0::2] + th[:, 1::2]) / 2.0
        vh = (vh[:, 0::2] + vh[:, 1::2]) / 2.0
        half = half // 2

    model = arch['cls'](in_ch, nc).to(device)
    w = compute_class_weights(ty, nc).to(device)
    crit = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)

    th_t = torch.from_numpy(th).float()
    vh_t = torch.from_numpy(vh).float()
    ds = TensorDataset(th_t, torch.from_numpy(ty).long())
    dl = DataLoader(ds, batch_size=bs, shuffle=True, pin_memory=(device.type == 'cuda'))

    best_m, best_p, best_pr, wait = -1, None, None, 0
    for ep in range(epochs):
        model.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(); crit(model(xb), yb).backward(); opt.step()
        model.eval()
        with torch.no_grad():
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
    r = {'epochs': ep + 1, 'in_channels': in_ch, 'history_steps': half,
         'param_count': nparams, 'architecture': arch_name}
    if nc == 2:
        r['f1'] = float(f1_score(vy, best_p, average='binary', zero_division=0))
        try: r['auc'] = float(roc_auc_score(vy, best_pr[:, 1]))
        except: r['auc'] = 0.0
        r['prevalence'] = float(vy.mean())
    else:
        r['f1_macro'] = float(f1_score(vy, best_p, average='macro', zero_division=0))
        r['f1_per_class'] = [float(x) for x in f1_score(vy, best_p, average=None, zero_division=0)]
    return r


def run_experiment(patients, device, seeds):
    """Run all arch × feature × task × seed combinations."""
    bt, bv, pt, pv, ft, fv = window_and_split(patients)
    print(f"  {len(bt)} train, {len(bv)} val")

    # Build labels from baseline windows
    lab = {}
    for tname, tdef in TASKS.items():
        ty = tdef['fn'](bt)
        vy = tdef['fn'](bv)
        lab[tname] = (ty, vy)
        if tdef['nc'] == 2:
            print(f"  {tname}: prev={vy.mean():.3f}")
        else:
            from collections import Counter
            print(f"  {tname}: dist={sorted(Counter(ty).items())}")

    results = {}
    for feat_name in FEATURE_ORDER:
        fdef = FEATURE_VARIANTS[feat_name]
        tx = fdef['build'](bt, pt, ft)
        vx = fdef['build'](bv, pv, fv)
        results[feat_name] = {}

        for arch_name in ARCH_ORDER:
            results[feat_name][arch_name] = {}
            print(f"\n{'='*60}")
            print(f"[{feat_name}] {arch_name} — {ARCH_VARIANTS[arch_name]['desc']}")
            print(f"{'='*60}")
            print(f"  {tx.shape[2]}ch, shape: {tx.shape}")

            for tname, tdef in TASKS.items():
                ty, vy = lab[tname]
                nc, pm = tdef['nc'], tdef['pm']

                seed_results = []
                for s in seeds:
                    torch.manual_seed(s)
                    np.random.seed(s)
                    r = train_and_eval(tx, ty, vx, vy, nc, device, arch_name)
                    seed_results.append(r)

                # Average metric across seeds
                avg = {}
                for k in seed_results[0]:
                    if isinstance(seed_results[0][k], float):
                        avg[k] = float(np.mean([sr[k] for sr in seed_results]))
                    elif isinstance(seed_results[0][k], list):
                        avg[k] = [float(np.mean([sr[k][i] for sr in seed_results]))
                                  for i in range(len(seed_results[0][k]))]
                    else:
                        avg[k] = seed_results[0][k]

                results[feat_name][arch_name][tname] = avg
                val = avg.get(pm, avg.get('f1_macro', avg.get('auc', 0)))
                print(f"  {tname}: {pm}={val:.4f} (params={avg.get('param_count', '?')})")

    return results


def print_summary(results):
    """Print comparison tables for each task."""
    for tname, tdef in TASKS.items():
        pm = tdef['pm']
        print(f"\n{'='*70}")
        print(f"  {tname.upper()} — {pm}")
        print(f"{'='*70}")

        # Header
        header = f"  {'arch':<20}"
        for feat in FEATURE_ORDER:
            header += f" {feat:<18}"
        print(header)
        print("  " + "-" * (20 + 18 * len(FEATURE_ORDER)))

        # Get baseline (deep_cnn + baseline_8ch) for delta
        base_val = results.get('baseline_8ch', {}).get('deep_cnn', {}).get(tname, {}).get(pm, 0)

        for arch in ARCH_ORDER:
            row = f"  {arch:<20}"
            for feat in FEATURE_ORDER:
                val = results.get(feat, {}).get(arch, {}).get(tname, {}).get(pm, 0)
                delta = val - base_val
                row += f" {val:.4f} ({delta:+.4f})"
            print(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"EXP-361: Architecture Search at 12h")
    print(f"Device: {device}, Seeds: {args.seeds}")
    print(f"Architectures: {ARCH_ORDER}")
    print(f"Features: {FEATURE_ORDER}")
    print(f"Window: {WINDOW_SIZE} steps (12h), history: {HALF} steps (6h)")

    t0 = time.time()
    patients = load_patient_features(args.patients_dir)
    results = run_experiment(patients, device, args.seeds)
    elapsed = time.time() - t0

    print(f"\n{'#'*70}")
    print(f"# EXP-361 RESULTS SUMMARY")
    print(f"{'#'*70}")
    print_summary(results)

    # Find best overall per task
    print(f"\n{'='*70}")
    print(f"  BEST PER TASK")
    print(f"{'='*70}")
    for tname, tdef in TASKS.items():
        pm = tdef['pm']
        best_val, best_feat, best_arch = -1, '', ''
        for feat in FEATURE_ORDER:
            for arch in ARCH_ORDER:
                val = results.get(feat, {}).get(arch, {}).get(tname, {}).get(pm, 0)
                if val > best_val:
                    best_val, best_feat, best_arch = val, feat, arch
        base_val = results.get('baseline_8ch', {}).get('deep_cnn', {}).get(tname, {}).get(pm, 0)
        print(f"  {tname}: {best_arch} + {best_feat} = {best_val:.4f} (Δ={best_val-base_val:+.4f} vs control)")

    print(f"\nTotal: {elapsed:.0f}s")

    out = {
        'experiment': 'EXP-361',
        'title': 'Architecture Search at 12h Episode Scale',
        'window_steps': WINDOW_SIZE,
        'history_steps': HALF,
        'seeds': args.seeds,
        'architectures': {k: v['desc'] for k, v in ARCH_VARIANTS.items()},
        'features': {k: v['desc'] for k, v in FEATURE_VARIANTS.items()},
        'results': results,
        'elapsed_seconds': elapsed,
    }
    outpath = 'externals/experiments/exp361_arch_12h.json'
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved: {outpath}")


if __name__ == '__main__':
    main()
