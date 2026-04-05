#!/usr/bin/env python3
"""EXP-351: FDA-Enhanced Multi-Scale Classification

Tests whether B-spline smoothed glucose + analytic derivatives improve CNN
classification across three timescales (2h, 6h, 12h). Combines the FDA insight
(EXP-331: +15% SNR from B-spline derivatives) with the symmetry finding
(EXP-349: removing time helps at 2h) and PK finding (EXP-350: PK helps at 12h).

Scales:
  2h  : 24 steps, 1h history, 1h prediction — acute events (UAM, override, hypo)
  6h  : 72 steps, 3h history, 3h prediction — episode patterns (override, hypo, prolonged_high)
  12h : 144 steps, 6h history, 6h prediction — long episodes (override, hypo, prolonged_high)

Feature variants (per scale):
  baseline_8ch       : Standard 8ch (control)
  no_time_6ch        : Drop time_sin/cos (EXP-349 winner at 2h)
  fda_8ch            : [smooth_glucose, glucose_d1, glucose_d2, iob, cob, net_basal, bolus, carbs]
  fda_no_time_6ch    : [smooth_glucose, glucose_d1, glucose_d2, iob, cob, net_basal]
  fda_pk_no_time_6ch : [smooth_glucose, glucose_d1, pk_net_balance, pk_insulin_total, pk_carb_rate, pk_basal_ratio]

Architecture scales with sequence length:
  2h  : 3-layer CNN (32→64→64) + AdaptiveAvgPool
  6h  : 4-layer CNN (32→64→64→128) + MaxPool(2) + AdaptiveAvgPool
  12h : 4-layer CNN (32→64→64→128) + MaxPool(2) + AdaptiveAvgPool

Causality: B-spline smoothing on full series has local support (~4 points
= 20 min). Model receives ONLY history half. PK channels are strictly causal
(forward convolution from past doses only).

Usage:
    python tools/cgmencode/exp_fda_classification.py [--scales 2h 6h 12h]
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score
from scipy.interpolate import UnivariateSpline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ── Scale configurations ─────────────────────────────────────────────────
SCALE_CONFIGS = {
    '2h': {
        'window_size': 24,    # 2h = 24 × 5min
        'stride': 12,         # 50% overlap
        'history_label': '1h history → 1h prediction',
        'cnn_depth': 'shallow',
    },
    '6h': {
        'window_size': 72,    # 6h = 72 × 5min
        'stride': 36,         # 50% overlap
        'history_label': '3h history → 3h prediction',
        'cnn_depth': 'deep',
    },
    '12h': {
        'window_size': 144,   # 12h = 144 × 5min
        'stride': 36,         # 4.2% overlap (sparser, fewer windows)
        'history_label': '6h history → 6h prediction',
        'cnn_depth': 'deep',
    },
}


def smooth_glucose_series(glucose, smoothing_factor=None):
    """B-spline smooth full glucose series → (smooth, d1, d2).

    Uses scipy UnivariateSpline for analytic derivatives.
    Smoothing is mildly non-causal (B-spline support ~4 points = 20 min).
    """
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
    """Load per-timestep base + PK + FDA features for all patients.

    Returns list of (base_8ch, pk_8ch, fda_3ch) arrays — one per patient.
    Windowing happens later, per scale.
    """
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

            # Normalize: smooth/400, d1/10, d2/5
            fda_3ch = np.column_stack([
                g_smooth / 400.0,
                g_d1 / 10.0,
                g_d2 / 5.0,
            ]).astype(np.float32)

            ml = min(len(base_8ch), len(pk_8ch), len(fda_3ch))
            base_8ch = base_8ch[:ml].astype(np.float32)
            pk_8ch = pk_8ch[:ml].astype(np.float32)
            fda_3ch = fda_3ch[:ml]
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(pk_8ch, copy=False)
            np.nan_to_num(fda_3ch, copy=False)

            patients.append((pid, base_8ch, pk_8ch, fda_3ch))
            print(f"  {pid}: {ml} timesteps, smooth range [{g_smooth.min():.0f}, {g_smooth.max():.0f}]")
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")

    return patients


def window_and_split(patients, window_size, stride):
    """Window per-timestep features at given scale, chronological 80/20 split."""
    all_bt, all_bv = [], []
    all_pt, all_pv = [], []
    all_ft, all_fv = [], []

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


# ── Feature variant definitions ──────────────────────────────────────────

VARIANT_DEFS = {
    'baseline_8ch': {
        'desc': 'Standard 8ch (control)',
        'build': lambda b, p, f: b,
    },
    'no_time_6ch': {
        'desc': 'Drop time (EXP-349 winner at 2h)',
        'build': lambda b, p, f: b[:, :, :6],
    },
    'fda_8ch': {
        'desc': 'Smooth glucose + derivatives + treatment',
        'build': lambda b, p, f: np.concatenate([
            f,                 # smooth_glucose, d1, d2  (3ch)
            b[:, :, 1:6],     # iob, cob, net_basal, bolus, carbs (5ch)
        ], axis=2),
    },
    'fda_no_time_6ch': {
        'desc': 'FDA + symmetry (smooth + deriv + core treatment)',
        'build': lambda b, p, f: np.concatenate([
            f,                 # smooth_glucose, d1, d2  (3ch)
            b[:, :, 1:4],     # iob, cob, net_basal     (3ch)
        ], axis=2),
    },
    'fda_pk_no_time_6ch': {
        'desc': 'FDA + PK (smooth + deriv + continuous PK)',
        'build': lambda b, p, f: np.concatenate([
            f[:, :, 0:2],     # smooth_glucose, d1       (2ch)
            p[:, :, 6:7],     # pk net_balance           (1ch)
            p[:, :, 0:1],     # pk insulin_total         (1ch)
            p[:, :, 3:4],     # pk carb_rate             (1ch)
            p[:, :, 2:3],     # pk basal_ratio           (1ch)
        ], axis=2),
    },
}
VARIANT_ORDER = list(VARIANT_DEFS.keys())


# ── Label builders (parameterized by half) ────────────────────────────────

def build_uam_labels(bw, half):
    """UAM: rising glucose (>10 mg/dL/5min) with no carbs in history."""
    h = bw[:, :half]
    g = h[:, :, 0] * 400.0
    c = h[:, :, 5]
    roc = np.diff(g, axis=1)
    return ((roc > 10).any(axis=1) & (c.sum(axis=1) < 0.01)).astype(np.int64)

def build_override_labels(bw, half):
    """Override: future glucose excursion classes (normal / high / low)."""
    fg = bw[:, half:, 0] * 400.0
    hi, lo = (fg > 180).any(axis=1), (fg < 70).any(axis=1)
    labels = np.zeros(len(bw), dtype=np.int64)
    labels[hi] = 1; labels[lo] = 2
    return labels

def build_hypo_labels(bw, half):
    """Hypo: any glucose < 70 mg/dL in future half."""
    return ((bw[:, half:, 0] * 400.0 < 70).any(axis=1)).astype(np.int64)

def build_prolonged_high_labels(bw, half):
    """Prolonged high: >180 mg/dL for >50% of future half (episode-scale)."""
    fg = bw[:, half:, 0] * 400.0
    frac_high = (fg > 180).mean(axis=1)
    return (frac_high > 0.5).astype(np.int64)


# Tasks available per scale
TASKS_BY_SCALE = {
    '2h': {
        'uam':      {'fn': build_uam_labels,      'nc': 2, 'pm': 'f1',       'ref': 'EXP-349 no_time F1=0.971'},
        'override': {'fn': build_override_labels,  'nc': 3, 'pm': 'f1_macro', 'ref': 'EXP-349 no_time F1=0.844'},
        'hypo':     {'fn': build_hypo_labels,      'nc': 2, 'pm': 'auc',      'ref': 'EXP-349 no_time AUC=0.949'},
    },
    '6h': {
        'override':      {'fn': build_override_labels,       'nc': 3, 'pm': 'f1_macro', 'ref': 'new scale'},
        'hypo':          {'fn': build_hypo_labels,           'nc': 2, 'pm': 'auc',      'ref': 'new scale'},
        'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1',      'ref': 'new scale'},
    },
    '12h': {
        'override':      {'fn': build_override_labels,       'nc': 3, 'pm': 'f1_macro', 'ref': 'EXP-350 pk_no_time F1=0.597'},
        'hypo':          {'fn': build_hypo_labels,           'nc': 2, 'pm': 'auc',      'ref': 'EXP-350 no_time AUC=0.773'},
        'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1',      'ref': 'EXP-350 baseline F1=0.507'},
    },
}


# ── CNN architectures (scale-appropriate) ─────────────────────────────────

class ShallowCNN(nn.Module):
    """3-layer CNN for short sequences (2h = 12 history steps)."""
    def __init__(self, in_ch, nc):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, nc))

    def forward(self, x):
        return self.fc(self.conv(x.permute(0, 2, 1)).squeeze(-1))


class DeepCNN(nn.Module):
    """4-layer CNN + MaxPool for long sequences (6h/12h = 36-72 history steps)."""
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


def build_model(in_ch, nc, depth):
    if depth == 'shallow':
        return ShallowCNN(in_ch, nc)
    else:
        return DeepCNN(in_ch, nc)


def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, half, depth, epochs=50, bs=256, patience=10):
    """Train CNN and evaluate. Model receives ONLY history half (causal)."""
    in_ch = tx.shape[2]
    model = build_model(in_ch, nc, depth).to(device)
    w = compute_class_weights(ty, nc).to(device)
    crit = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)

    # Causal: extract history half ONLY — future values never enter model
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
        if metric > best_m:
            best_m, best_p, best_pr, wait = metric, preds.copy(), probs.copy(), 0
        else:
            wait += 1
            if wait >= patience: break

    r = {'epochs': ep + 1, 'in_channels': in_ch, 'history_steps': half}
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
    """Run all variants × tasks for one scale. Returns results dict."""
    cfg = SCALE_CONFIGS[scale_name]
    ws = cfg['window_size']
    half = ws // 2
    stride = cfg['stride']
    depth = cfg['cnn_depth']
    tasks = TASKS_BY_SCALE[scale_name]

    print(f"\n{'#'*70}")
    print(f"# SCALE: {scale_name} — {cfg['history_label']}")
    print(f"# window={ws} steps, history={half}, stride={stride}, CNN={depth}")
    print(f"{'#'*70}")

    bt, bv, pt, pv, ft, fv = window_and_split(patients, ws, stride)
    print(f"  {len(bt)} train, {len(bv)} val windows")

    # Build labels (from baseline windows, using correct half)
    labels = {}
    for tn, tc in tasks.items():
        ty, vy = tc['fn'](bt, half), tc['fn'](bv, half)
        labels[tn] = (ty, vy)
        if tc['nc'] == 2:
            print(f"  {tn}: prevalence={ty.mean():.3f}")
        else:
            print(f"  {tn}: distribution={np.bincount(ty, minlength=tc['nc']).tolist()}")

    scale_results = {
        'config': {
            'window_size': ws, 'half': half, 'stride': stride,
            'cnn_depth': depth, 'history_label': cfg['history_label'],
        },
        'n_train': int(len(bt)), 'n_val': int(len(bv)),
        'variants': {}, 'comparison': {},
    }

    for vn in VARIANT_ORDER:
        vd = VARIANT_DEFS[vn]
        print(f"\n{'='*60}\n[{scale_name}] {vn} — {vd['desc']}\n{'='*60}")
        tx = vd['build'](bt, pt, ft)
        vx = vd['build'](bv, pv, fv)
        nch = tx.shape[2]
        print(f"  {nch}ch, train shape: {tx.shape}")
        scale_results['variants'][vn] = {'desc': vd['desc'], 'n_channels': nch, 'tasks': {}}

        for tn, tc in tasks.items():
            ty, vy = labels[tn]
            seed_results = []
            for s in seeds:
                torch.manual_seed(s); np.random.seed(s)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed(s)
                r = train_and_eval(tx, ty, vx, vy, tc['nc'], device, half, depth)
                seed_results.append(r)

            # Aggregate across seeds
            agg = {}
            for k in seed_results[0]:
                vals = [sr[k] for sr in seed_results]
                if isinstance(vals[0], (int, float)):
                    agg[k] = float(np.mean(vals))
                    if len(vals) > 1:
                        agg[f'{k}_std'] = float(np.std(vals))
                elif isinstance(vals[0], list):
                    agg[k] = [float(np.mean(x)) for x in zip(*vals)]

            pm = tc['pm']
            print(f"  {tn}: {pm}={agg.get(pm, 0):.4f}")
            scale_results['variants'][vn]['tasks'][tn] = agg

    # Per-scale summary
    print(f"\n{'='*60}\n[{scale_name}] SUMMARY\n{'='*60}")
    for tn, tc in tasks.items():
        pm = tc['pm']
        print(f"\n  {tn} ({pm}) — ref: {tc['ref']}:")
        bl = scale_results['variants']['baseline_8ch']['tasks'][tn].get(pm, 0)
        nt = scale_results['variants']['no_time_6ch']['tasks'][tn].get(pm, 0)
        best_v, best_val = None, -1
        for vn in VARIANT_ORDER:
            v = scale_results['variants'][vn]['tasks'][tn].get(pm, 0)
            d = v - bl
            vs_nt = v - nt
            print(f"    {vn:25s}: {v:.4f} (Δbase={d:+.4f}, Δno_time={vs_nt:+.4f})")
            if v > best_val:
                best_val, best_v = v, vn
        scale_results['comparison'][tn] = {
            'metric': pm, 'baseline': float(bl), 'no_time_ref': float(nt),
            'best_variant': best_v, 'best_value': float(best_val),
            'delta_vs_baseline': float(best_val - bl),
            'delta_vs_no_time': float(best_val - nt),
        }

    return scale_results


def main():
    parser = argparse.ArgumentParser(description='EXP-351: FDA Multi-Scale Classification')
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--output', default='externals/experiments/exp351_fda_classification.json')
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 456])
    parser.add_argument('--scales', nargs='+', default=['2h', '6h', '12h'],
                        choices=['2h', '6h', '12h'],
                        help='Timescales to evaluate (default: all three)')
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"EXP-351: FDA-Enhanced Multi-Scale Classification")
    print(f"Device: {device}, Seeds: {args.seeds}, Scales: {args.scales}")
    t0 = time.time()

    # Load once, window per scale
    patients = load_patient_features(args.patients_dir)

    results = {
        'experiment': 'EXP-351',
        'title': 'FDA-Enhanced Multi-Scale Classification',
        'hypothesis': (
            'B-spline smoothed glucose + analytic derivatives combine with '
            'symmetry (no time) to beat raw features. FDA derivatives provide '
            'noise-robust rate-of-change (+15% SNR from EXP-331). '
            'PK channels expected to help more at longer scales (EXP-350).'
        ),
        'device': str(device), 'seeds': args.seeds,
        'scales': {},
        'cross_scale_summary': {},
    }

    for scale in args.scales:
        results['scales'][scale] = run_scale(scale, patients, device, args.seeds)

    # Cross-scale summary: best variant per task across all scales
    print(f"\n{'#'*70}")
    print(f"# CROSS-SCALE SUMMARY")
    print(f"{'#'*70}")

    all_tasks = set()
    for scale in args.scales:
        all_tasks.update(results['scales'][scale]['comparison'].keys())

    for tn in sorted(all_tasks):
        print(f"\n  {tn}:")
        css = {}
        for scale in args.scales:
            comp = results['scales'][scale].get('comparison', {}).get(tn)
            if comp:
                print(f"    {scale:4s}: best={comp['best_variant']:25s} "
                      f"val={comp['best_value']:.4f} "
                      f"(Δbase={comp['delta_vs_baseline']:+.4f})")
                css[scale] = comp
        results['cross_scale_summary'][tn] = css

    elapsed = time.time() - t0
    results['elapsed_seconds'] = float(elapsed)
    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    print(f"\nTotal: {elapsed:.0f}s")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {args.output}")


if __name__ == '__main__':
    main()
