#!/usr/bin/env python3
"""EXP-349: PK-Enhanced CNN Classification with Symmetry Ablation

Tests whether continuous pharmacokinetic channels (from continuous_pk.py)
improve downstream classification tasks, and whether removing time features
respects time-translation invariance at the 2h scale.

Causality / future masking:
  - PK channels are strictly causal: value at time t reflects only events <= t
    (forward convolution of past doses through activity kernel)
  - Model receives ONLY history half of each window ([:HALF])
  - Labels use future glucose (override, hypo) or history glucose+carbs (UAM)
  - Known-future values (scheduled basal, ISF, time_sin/cos) are NOT provided
    to the model — only observable history
  - Unknown-future values (bolus, carbs, temp basal) never enter model input

Feature variants tested:
  baseline_8ch     : Standard [glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos]
  pk_replace_8ch   : [glucose, pk_total, pk_net_bal, pk_basal_ratio, pk_carb_rate, pk_carb_accel, time_sin, time_cos]
  no_time_6ch      : Baseline minus time channels (tests symmetry hypothesis)
  pk_no_time_6ch   : PK without time (maximum symmetry respect)
  augmented_16ch   : All 8 baseline + 8 PK channels

Tasks:
  UAM detection     (baseline F1=0.939, EXP-313)
  Override predict  (baseline F1=0.821, EXP-314)
  Hypo prediction   (baseline AUC=0.958, EXP-322)

Architecture: 3-layer 1D-CNN matching EXP-313 UAMCNN exactly.

Usage:
    python tools/cgmencode/exp_pk_classification.py [--patients-dir PATH] [--device cuda]
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ─── Channel Indices ───
# Base (from schema.py): glucose=0, iob=1, cob=2, net_basal=3, bolus=4, carbs=5, time_sin=6, time_cos=7
# PK (from continuous_pk.py): insulin_total=0, insulin_net=1, basal_ratio=2, carb_rate=3,
#                              carb_accel=4, hepatic=5, net_balance=6, isf_curve=7

WINDOW_SIZE = 24   # 2h at 5-min resolution
STRIDE = 12        # 50% overlap
HALF = WINDOW_SIZE // 2

VARIANT_DEFS = {
    'baseline_8ch': {
        'desc': 'Standard 8-channel features',
        'build': lambda b, p: b,
    },
    'pk_replace_8ch': {
        'desc': 'PK channels replace sparse treatment channels, keep time',
        'build': lambda b, p: np.concatenate([
            b[:, :, 0:1],   # glucose
            p[:, :, 0:1],   # insulin_total  (replaces iob)
            p[:, :, 6:7],   # net_balance    (replaces cob)
            p[:, :, 2:3],   # basal_ratio    (replaces net_basal)
            p[:, :, 3:4],   # carb_rate      (replaces bolus)
            p[:, :, 4:5],   # carb_accel     (replaces carbs)
            b[:, :, 6:8],   # time_sin, time_cos
        ], axis=2),
    },
    'no_time_6ch': {
        'desc': 'Baseline minus time channels (symmetry test)',
        'build': lambda b, p: b[:, :, :6],
    },
    'pk_no_time_6ch': {
        'desc': 'PK channels without time (maximum symmetry)',
        'build': lambda b, p: np.concatenate([
            b[:, :, 0:1],   # glucose
            p[:, :, 0:1],   # insulin_total
            p[:, :, 6:7],   # net_balance
            p[:, :, 2:3],   # basal_ratio
            p[:, :, 3:4],   # carb_rate
            p[:, :, 4:5],   # carb_accel
        ], axis=2),
    },
    'augmented_16ch': {
        'desc': 'All 8 baseline + 8 PK channels',
        'build': lambda b, p: np.concatenate([b, p], axis=2),
    },
}

VARIANT_ORDER = ['baseline_8ch', 'pk_replace_8ch', 'no_time_6ch',
                 'pk_no_time_6ch', 'augmented_16ch']


# ─── Data Loading ───

def find_patient_dirs(patients_dir):
    dirs = sorted(glob.glob(os.path.join(patients_dir, '*/training')))
    if not dirs:
        dirs = sorted(glob.glob(os.path.join(patients_dir, '*')))
    return [d for d in dirs if os.path.isdir(d)]


def load_all_data(patients_dir):
    """Load base + PK features for all patients, create aligned windows."""
    patient_dirs = find_patient_dirs(patients_dir)
    print(f"Loading {len(patient_dirs)} patients")

    all_base_train, all_base_val = [], []
    all_pk_train, all_pk_val = [], []

    for pdir in patient_dirs:
        pid = Path(pdir).parent.name
        try:
            df, base_8ch = build_nightscout_grid(pdir)
            pk_8ch = build_continuous_pk_features(df)

            # Align lengths (PK may trim edges)
            min_len = min(len(base_8ch), len(pk_8ch))
            base_8ch = base_8ch[:min_len].astype(np.float32)
            pk_8ch = pk_8ch[:min_len].astype(np.float32)
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(pk_8ch, copy=False)

            # Create aligned windows
            base_wins, pk_wins = [], []
            for i in range(0, min_len - WINDOW_SIZE + 1, STRIDE):
                base_wins.append(base_8ch[i:i + WINDOW_SIZE])
                pk_wins.append(pk_8ch[i:i + WINDOW_SIZE])

            if len(base_wins) < 20:
                print(f"  {pid}: too few windows ({len(base_wins)}), skip")
                continue

            base_wins = np.array(base_wins, dtype=np.float32)
            pk_wins = np.array(pk_wins, dtype=np.float32)

            # Chronological 80/20 split
            n = len(base_wins)
            split = int(n * 0.8)

            all_base_train.append(base_wins[:split])
            all_base_val.append(base_wins[split:])
            all_pk_train.append(pk_wins[:split])
            all_pk_val.append(pk_wins[split:])

            print(f"  {pid}: {n} windows ({split} train, {n - split} val)")
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")

    base_train = np.concatenate(all_base_train)
    base_val = np.concatenate(all_base_val)
    pk_train = np.concatenate(all_pk_train)
    pk_val = np.concatenate(all_pk_val)

    # Shuffle training (aligned)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(base_train))
    base_train, pk_train = base_train[idx], pk_train[idx]

    print(f"Total: {len(base_train)} train, {len(base_val)} val")
    return base_train, base_val, pk_train, pk_val


# ─── Label Builders (always from baseline windows with known channels) ───

def build_uam_labels(base_windows):
    """UAM = rapid glucose rise in history + no carbs in history.
    Matches EXP-313 exactly."""
    hist = base_windows[:, :HALF]
    glucose = hist[:, :, 0] * 400.0
    carbs = hist[:, :, 5]
    roc = np.diff(glucose, axis=1)
    rapid_rise = (roc > 10).any(axis=1)
    no_carbs = carbs.sum(axis=1) < 0.01
    return (rapid_rise & no_carbs).astype(np.int64)


def build_override_labels(base_windows):
    """Override: 0=normal, 1=high(>180), 2=low(<70). Matches EXP-311."""
    future_glucose = base_windows[:, HALF:, 0] * 400.0
    high = (future_glucose > 180).any(axis=1)
    low = (future_glucose < 70).any(axis=1)
    labels = np.zeros(len(base_windows), dtype=np.int64)
    labels[high] = 1
    labels[low] = 2
    return labels


def build_hypo_labels(base_windows):
    """Hypo: binary, any glucose < 70 in future half. Matches EXP-322."""
    future_glucose = base_windows[:, HALF:, 0] * 400.0
    return ((future_glucose < 70).any(axis=1)).astype(np.int64)


# ─── CNN Model (matches EXP-313 UAMCNN architecture) ───

class FlexCNN(nn.Module):
    """1D-CNN with configurable input channels, matching UAMCNN arch.

    Input: (B, T, C) where T = history-only timesteps.
    The caller is responsible for passing ONLY the history half —
    this model does NOT slice the window internally, ensuring no
    future information leaks through.
    """
    def __init__(self, in_channels, num_classes):
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
            nn.Linear(32, num_classes),
        )

    def forward(self, x):
        # x: (B, T_hist, C) — already history-only, no future values
        x = x.permute(0, 2, 1)   # (B, C, T)
        features = self.conv(x).squeeze(-1)
        return self.classifier(features)


# ─── Training ───

def compute_class_weights(labels, num_classes):
    counts = np.bincount(labels, minlength=num_classes).astype(float)
    counts = np.maximum(counts, 1.0)
    weights = len(labels) / (num_classes * counts)
    return torch.FloatTensor(weights)


def train_and_eval(train_x, train_y, val_x, val_y, num_classes, device,
                   epochs=50, batch_size=256, patience=10):
    """Train CNN on history-only input, return best validation metrics.

    Causality contract:
    - train_x/val_x are full windows (B, WINDOW_SIZE, C)
    - We extract ONLY the history half [:, :HALF, :] for model input
    - Labels were built from full windows (using future glucose for
      override/hypo, or history glucose+carbs for UAM)
    - PK channels at history timesteps are strictly causal: each value
      at time t only reflects events at times <= t (forward convolution)
    - Unknown future values (bolus, carbs, temp basal, their PK derivatives)
      are never seen by the model
    - Known future values (scheduled basal, ISF schedule, time_sin/cos)
      are also excluded for simplicity — only history is used
    """
    in_ch = train_x.shape[2]
    model = FlexCNN(in_ch, num_classes).to(device)

    weights = compute_class_weights(train_y, num_classes).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)

    # CRITICAL: Only pass history half to model — no future leakage
    train_hist = torch.from_numpy(train_x[:, :HALF].copy()).float()
    val_hist = torch.from_numpy(val_x[:, :HALF].copy()).float()
    train_labels = torch.from_numpy(train_y).long()

    train_ds = TensorDataset(train_hist, train_labels)
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                          pin_memory=(device.type == 'cuda'))

    best_metric = -1.0
    best_state = None
    wait = 0

    for epoch in range(epochs):
        model.train()
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            logits = model(val_hist.to(device))
            preds = logits.argmax(dim=1).cpu().numpy()
            probs = torch.softmax(logits, dim=1).cpu().numpy()

        if num_classes == 2:
            f1 = f1_score(val_y, preds, average='binary', zero_division=0)
            try:
                auc = roc_auc_score(val_y, probs[:, 1])
            except ValueError:
                auc = 0.0
            metric = auc  # AUC better for imbalanced binary
        else:
            f1 = f1_score(val_y, preds, average='macro', zero_division=0)
            metric = f1

        if metric > best_metric:
            best_metric = metric
            best_state = {
                'preds': preds.copy(),
                'probs': probs.copy(),
                'epoch': epoch,
            }
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    # Compute final metrics from best model
    bp = best_state['preds']
    bprobs = best_state['probs']
    result = {'epochs_trained': best_state['epoch'] + 1, 'in_channels': in_ch}

    if num_classes == 2:
        result['f1'] = float(f1_score(val_y, bp, average='binary', zero_division=0))
        try:
            result['auc'] = float(roc_auc_score(val_y, bprobs[:, 1]))
        except ValueError:
            result['auc'] = 0.0
        pos_mask = val_y == 1
        result['recall'] = float(bp[pos_mask].mean()) if pos_mask.any() else 0.0
        result['prevalence'] = float(val_y.mean())
    else:
        result['f1_macro'] = float(f1_score(val_y, bp, average='macro', zero_division=0))
        result['f1_weighted'] = float(f1_score(val_y, bp, average='weighted', zero_division=0))
        per_class = f1_score(val_y, bp, average=None, zero_division=0)
        result['f1_per_class'] = [float(x) for x in per_class]
        result['class_dist'] = [int(x) for x in np.bincount(val_y, minlength=num_classes)]

    return result


# ─── Task Definitions ───

TASKS = {
    'uam': {
        'label_fn': build_uam_labels,
        'num_classes': 2,
        'primary_metric': 'f1',
        'baseline_ref': 'EXP-313 F1=0.939',
    },
    'override': {
        'label_fn': build_override_labels,
        'num_classes': 3,
        'primary_metric': 'f1_macro',
        'baseline_ref': 'EXP-314 F1=0.821',
    },
    'hypo': {
        'label_fn': build_hypo_labels,
        'num_classes': 2,
        'primary_metric': 'auc',
        'baseline_ref': 'EXP-322 AUC=0.958',
    },
}


def main():
    parser = argparse.ArgumentParser(description='EXP-349: PK Classification Ablation')
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--output', default='externals/experiments/exp349_pk_classification.json')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 456],
                        help='Random seeds for multi-seed averaging')
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"EXP-349: PK-Enhanced CNN Classification")
    print(f"Device: {device}")
    print(f"Seeds: {args.seeds}")
    t0 = time.time()

    # ── Load data ──
    base_train, base_val, pk_train, pk_val = load_all_data(args.patients_dir)

    # ── Build labels (from baseline windows, fixed channels) ──
    labels = {}
    for task_name, tcfg in TASKS.items():
        ty = tcfg['label_fn'](base_train)
        vy = tcfg['label_fn'](base_val)
        if tcfg['num_classes'] == 2:
            info = f"pos_rate={ty.mean():.3f} ({ty.sum()}/{len(ty)})"
        else:
            info = f"dist={np.bincount(ty, minlength=tcfg['num_classes']).tolist()}"
        print(f"  {task_name}: {info}")
        labels[task_name] = (ty, vy)

    # ── Run all variant × task × seed combinations ──
    results = {
        'experiment': 'EXP-349',
        'title': 'PK-Enhanced CNN Classification with Symmetry Ablation',
        'hypothesis': (
            'H1: PK channels improve classification (pk_replace > baseline). '
            'H2: Removing time respects 2h symmetry (no_time >= baseline). '
            'H3: PK+symmetry is best (pk_no_time maximizes both).'
        ),
        'window': f'{WINDOW_SIZE} steps = {WINDOW_SIZE * 5} min',
        'n_train': int(len(base_train)),
        'n_val': int(len(base_val)),
        'device': str(device),
        'seeds': args.seeds,
        'variants': {},
        'comparison': {},
    }

    for variant_name in VARIANT_ORDER:
        vdef = VARIANT_DEFS[variant_name]
        print(f"\n{'=' * 60}")
        print(f"Variant: {variant_name} — {vdef['desc']}")
        print(f"{'=' * 60}")

        train_x = vdef['build'](base_train, pk_train)
        val_x = vdef['build'](base_val, pk_val)
        n_ch = train_x.shape[2]
        print(f"  Channels: {n_ch}, shape: {train_x.shape}")

        results['variants'][variant_name] = {
            'desc': vdef['desc'],
            'n_channels': n_ch,
            'tasks': {},
        }

        for task_name, tcfg in TASKS.items():
            train_y, val_y = labels[task_name]
            primary = tcfg['primary_metric']

            # Multi-seed runs
            seed_metrics = []
            for seed in args.seeds:
                torch.manual_seed(seed)
                np.random.seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed(seed)

                m = train_and_eval(
                    train_x, train_y, val_x, val_y,
                    tcfg['num_classes'], device,
                    epochs=args.epochs, batch_size=256, patience=10,
                )
                seed_metrics.append(m)

            # Aggregate across seeds
            agg = {}
            for key in seed_metrics[0]:
                vals = [sm[key] for sm in seed_metrics]
                if isinstance(vals[0], (int, float)):
                    agg[key] = float(np.mean(vals))
                    if len(vals) > 1:
                        agg[f'{key}_std'] = float(np.std(vals))
                elif isinstance(vals[0], list):
                    agg[key] = [float(np.mean(x)) for x in zip(*vals)]

            pval = agg.get(primary, 0)
            print(f"  {task_name}: {primary}={pval:.4f} ({n_ch}ch, {len(args.seeds)} seeds)")

            results['variants'][variant_name]['tasks'][task_name] = agg

    # ── Summary comparison ──
    print(f"\n{'=' * 60}")
    print("SUMMARY — Primary metrics by variant × task")
    print(f"{'=' * 60}")

    for task_name, tcfg in TASKS.items():
        primary = tcfg['primary_metric']
        print(f"\n{task_name} ({primary}) — ref: {tcfg['baseline_ref']}")

        baseline_val = results['variants']['baseline_8ch']['tasks'][task_name].get(primary, 0)
        best_val, best_var = -1, None

        for vname in VARIANT_ORDER:
            val = results['variants'][vname]['tasks'][task_name].get(primary, 0)
            delta = val - baseline_val
            marker = ' ←' if vname == 'baseline_8ch' else ''
            print(f"  {vname:25s}: {val:.4f} (Δ={delta:+.4f}){marker}")
            if val > best_val:
                best_val, best_var = val, vname

        delta = best_val - baseline_val
        print(f"  → Best: {best_var} (Δ={delta:+.4f})")

        results['comparison'][task_name] = {
            'primary_metric': primary,
            'baseline': float(baseline_val),
            'best_variant': best_var,
            'best_value': float(best_val),
            'delta_vs_baseline': float(delta),
        }

    # ── Symmetry analysis ──
    print(f"\nSYMMETRY ANALYSIS (time removal effect)")
    for task_name, tcfg in TASKS.items():
        primary = tcfg['primary_metric']
        with_time = results['variants']['baseline_8ch']['tasks'][task_name].get(primary, 0)
        no_time = results['variants']['no_time_6ch']['tasks'][task_name].get(primary, 0)
        pk_with_time = results['variants']['pk_replace_8ch']['tasks'][task_name].get(primary, 0)
        pk_no_time = results['variants']['pk_no_time_6ch']['tasks'][task_name].get(primary, 0)

        delta_base = no_time - with_time
        delta_pk = pk_no_time - pk_with_time
        print(f"  {task_name}: base Δ={delta_base:+.4f}, pk Δ={delta_pk:+.4f}  "
              f"{'✓ symmetry helps' if delta_base >= 0 and delta_pk >= 0 else '✗ time needed'}")

    elapsed = time.time() - t0
    results['elapsed_seconds'] = float(elapsed)
    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    print(f"\nTotal time: {elapsed:.0f}s")

    # Save
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {args.output}")


if __name__ == '__main__':
    main()
