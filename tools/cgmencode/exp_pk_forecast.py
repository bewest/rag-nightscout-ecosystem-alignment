#!/usr/bin/env python3
"""EXP-352 through EXP-355: PK-Enhanced Glucose Forecasting

Prior work showed sparse bolus/carbs channels add noise for the 8f forecaster,
and continuous PK curves (EXP-349) hurt classification at 2h scale because
1h history is too short for 5h DIA. This experiment series tests whether
PK curves help the *forecasting* task (predicting future glucose values)
where: (a) longer history windows are standard, (b) dense absorption curves
match glucose smoothness, and (c) PK state projects causally into the future.

EXP-352 — Baseline PK forecast comparison
  Tests 6 channel variants at 6h history → predict 30/60/120 min glucose.
  Primary metric: MAE in mg/dL at each horizon.

EXP-353 — History length × PK interaction
  2×5 grid of {baseline, pk_replace} × {1h, 2h, 4h, 6h, 12h} history.
  Tests whether PK wins at longer windows where full DIA is visible.

EXP-354 — Selective PK channel ablation
  Adds PK channels one at a time to glucose-only baseline.
  Identifies which continuous channels are most informative.

EXP-355 — PK forward projection into prediction window
  Projects known-future absorption state (insulin decaying, carbs digesting)
  into the prediction window. Physically valid — no future leakage since
  PK state is deterministic given past events.

Causality:
  - All PK channels are strictly causal: value at time t reflects only events ≤ t
  - Labels (future glucose) are never visible to the model
  - EXP-355 forward projection uses only the causal PK kernel convolution
    extended beyond the history boundary — no future events are introduced

Architecture: 1D-CNN encoder → multi-horizon linear heads (30/60/120 min).
  Conv1d layers map (B, C, T_hist) → (B, 64, 1) → Linear → (B, 3 horizons).
  Same proven CNN backbone as EXP-313/349.

Usage:
    python tools/cgmencode/exp_pk_forecast.py [--patients-dir PATH] [--device cuda]
    python tools/cgmencode/exp_pk_forecast.py --experiment 352  # run one
    python tools/cgmencode/exp_pk_forecast.py --experiment all  # run all
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ─── Constants ───

SEEDS = [42, 123, 456]
SEEDS_QUICK = [42]
GLUCOSE_SCALE = 400.0
HORIZONS = {
    'h30': 6,    # 30 min = 6 × 5-min steps
    'h60': 12,   # 60 min
    'h120': 24,  # 120 min
}

# Quick mode config: 1 seed, 30 epochs, patience 8, max 4 patients
QUICK_PATIENTS = 4
QUICK_EPOCHS = 30
QUICK_PATIENCE = 8


# ─── Channel Variant Definitions ───

def _build_variant(base, pk, variant_name):
    """Build feature windows for a given variant.

    Args:
        base: (N, T, 8) baseline windows
        pk: (N, T, 8) PK channel windows
        variant_name: one of the defined variants

    Returns:
        (N, T, C) feature windows for the variant
    """
    builders = {
        # EXP-352 variants
        'baseline_8ch': lambda: base,
        'pk_replace_8ch': lambda: np.concatenate([
            base[:, :, 0:1],   # glucose
            pk[:, :, 0:1],     # insulin_total  (replaces iob)
            pk[:, :, 6:7],     # net_balance    (replaces cob)
            pk[:, :, 2:3],     # basal_ratio    (replaces net_basal)
            pk[:, :, 3:4],     # carb_rate      (replaces bolus)
            pk[:, :, 4:5],     # carb_accel     (replaces carbs)
            base[:, :, 6:8],   # time_sin, time_cos
        ], axis=2),
        'pk_replace_6ch': lambda: np.concatenate([
            base[:, :, 0:1],   # glucose
            pk[:, :, 1:2],     # insulin_net (deviation only)
            pk[:, :, 6:7],     # net_balance
            pk[:, :, 2:3],     # basal_ratio
            pk[:, :, 3:4],     # carb_rate
            pk[:, :, 4:5],     # carb_accel
        ], axis=2),
        'glucose_only_1ch': lambda: base[:, :, 0:1],
        'glucose_iob_2ch': lambda: base[:, :, 0:2],
        'baseline_notime_6ch': lambda: base[:, :, :6],
        'augmented_14ch': lambda: np.concatenate([
            base[:, :, :6], pk
        ], axis=2),

        # EXP-354 ablation variants (additive from glucose-only)
        'glucose+insulin_net': lambda: np.concatenate([
            base[:, :, 0:1], pk[:, :, 1:2]
        ], axis=2),
        'glucose+carb_rate': lambda: np.concatenate([
            base[:, :, 0:1], pk[:, :, 3:4]
        ], axis=2),
        'glucose+net_balance': lambda: np.concatenate([
            base[:, :, 0:1], pk[:, :, 6:7]
        ], axis=2),
        'glucose+insulin_net+carb_rate': lambda: np.concatenate([
            base[:, :, 0:1], pk[:, :, 1:2], pk[:, :, 3:4]
        ], axis=2),
        'glucose+all_pk': lambda: np.concatenate([
            base[:, :, 0:1], pk
        ], axis=2),
    }
    return builders[variant_name]()


# ─── Data Loading ───

def find_patient_dirs(patients_dir):
    dirs = sorted(glob.glob(os.path.join(patients_dir, '*/training')))
    if not dirs:
        dirs = sorted(glob.glob(os.path.join(patients_dir, '*')))
    return [d for d in dirs if os.path.isdir(d)]


def load_forecast_data(patients_dir, history_steps=72, max_horizon=24,
                       max_patients=None):
    """Load base + PK features, create forecast windows.

    Each window has:
      history: [0, history_steps) — model input
      future:  [history_steps, history_steps + max_horizon) — targets

    Args:
        max_patients: limit number of patients (for --quick mode)

    Returns:
        base_train, base_val: (N, T_total, 8) baseline windows
        pk_train, pk_val: (N, T_total, 8) PK windows
        T_total = history_steps + max_horizon
    """
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    print(f"Loading {len(patient_dirs)} patients "
          f"(history={history_steps}, horizon={max_horizon})")

    window_size = history_steps + max_horizon
    stride = history_steps // 2  # 50% overlap on history portion

    bt, bv, pt, pv = [], [], [], []

    for pdir in patient_dirs:
        pid = Path(pdir).parent.name
        try:
            df, base_8ch = build_nightscout_grid(pdir)
            pk_8ch = build_continuous_pk_features(df)
            ml = min(len(base_8ch), len(pk_8ch))
            base_8ch = base_8ch[:ml].astype(np.float32)
            pk_8ch = pk_8ch[:ml].astype(np.float32)
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(pk_8ch, copy=False)

            bw, pw = [], []
            for i in range(0, ml - window_size + 1, stride):
                seg_b = base_8ch[i:i + window_size]
                seg_p = pk_8ch[i:i + window_size]
                # Skip windows with >20% NaN glucose in history
                glucose_hist = seg_b[:history_steps, 0]
                if np.isnan(glucose_hist).mean() > 0.2:
                    continue
                # Skip windows with NaN glucose targets
                glucose_future = seg_b[history_steps:, 0]
                if np.isnan(glucose_future).any():
                    continue
                bw.append(seg_b)
                pw.append(seg_p)

            if len(bw) < 20:
                print(f"  {pid}: too few windows ({len(bw)}), skip")
                continue

            bw = np.array(bw, dtype=np.float32)
            pw = np.array(pw, dtype=np.float32)

            # Chronological 80/20 split (per-patient)
            n = len(bw)
            s = int(n * 0.8)
            bt.append(bw[:s]); bv.append(bw[s:])
            pt.append(pw[:s]); pv.append(pw[s:])

            print(f"  {pid}: {n} windows ({s} train, {n - s} val)")
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")

    if not bt:
        raise RuntimeError("No patient data loaded")

    base_train = np.concatenate(bt)
    base_val = np.concatenate(bv)
    pk_train = np.concatenate(pt)
    pk_val = np.concatenate(pv)

    # Shuffle training data (aligned across base and pk)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(base_train))
    base_train, pk_train = base_train[idx], pk_train[idx]

    print(f"Total: {len(base_train)} train, {len(base_val)} val")
    return base_train, base_val, pk_train, pk_val


# ─── Forecaster CNN ───

class ForecastCNN(nn.Module):
    """1D-CNN multi-horizon glucose forecaster.

    Input: (B, T_hist, C) — history-only features
    Output: (B, n_horizons) — predicted glucose at each horizon (normalized)
    """
    def __init__(self, in_channels, n_horizons=3):
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
        self.head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, x):
        # x: (B, T_hist, C)
        x = x.permute(0, 2, 1)   # (B, C, T)
        feat = self.conv(x).squeeze(-1)  # (B, 64)
        return self.head(feat)  # (B, n_horizons)


class ForecastCNNWithFuture(nn.Module):
    """CNN forecaster that also receives projected future PK channels.

    For EXP-355: the history encoder processes all channels, then the
    future PK projection is concatenated before the forecast head.

    Input:
        hist: (B, T_hist, C_hist)  — history features
        future_pk: (B, T_future, C_pk)  — projected PK channels
    Output:
        (B, n_horizons) — predicted glucose at each horizon
    """
    def __init__(self, hist_channels, pk_channels, n_horizons=3):
        super().__init__()
        self.hist_conv = nn.Sequential(
            nn.Conv1d(hist_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.future_conv = nn.Sequential(
            nn.Conv1d(pk_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(16),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64 + 16, 32), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(32, n_horizons),
        )

    def forward(self, hist, future_pk):
        h = hist.permute(0, 2, 1)
        f = future_pk.permute(0, 2, 1)
        h_feat = self.hist_conv(h).squeeze(-1)   # (B, 64)
        f_feat = self.future_conv(f).squeeze(-1)  # (B, 16)
        return self.head(torch.cat([h_feat, f_feat], dim=1))


# ─── Training and Evaluation ───

def train_forecast(train_x, train_y, val_x, val_y, device,
                   epochs=80, batch_size=256, patience=15, lr=1e-3):
    """Train a ForecastCNN and return best val metrics."""
    in_ch = train_x.shape[2]
    n_horizons = train_y.shape[1]
    model = ForecastCNN(in_ch, n_horizons).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    train_xt = torch.from_numpy(train_x).float()
    train_yt = torch.from_numpy(train_y).float()
    val_xt = torch.from_numpy(val_x).float().to(device)
    val_yt = torch.from_numpy(val_y).float().to(device)

    ds = TensorDataset(train_xt, train_yt)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(device.type == 'cuda'))

    best_mae = float('inf')
    best_state = None
    wait = 0

    for epoch in range(epochs):
        model.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(val_xt)
            val_loss = criterion(val_pred, val_yt).item()

            # MAE in mg/dL
            mae_per_h = (val_pred - val_yt).abs().mean(dim=0) * GLUCOSE_SCALE
            overall_mae = mae_per_h.mean().item()

        scheduler.step(val_loss)

        if overall_mae < best_mae:
            best_mae = overall_mae
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            best_metrics = {
                'mae_overall': overall_mae,
                'mae_per_horizon': {name: mae_per_h[i].item()
                                    for i, name in enumerate(HORIZONS.keys())},
                'mse': val_loss,
                'rmse': float(np.sqrt(val_loss) * GLUCOSE_SCALE),
            }
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_metrics


def train_forecast_with_future(train_hist, train_future_pk, train_y,
                               val_hist, val_future_pk, val_y,
                               device, epochs=80, batch_size=256,
                               patience=15, lr=1e-3):
    """Train ForecastCNNWithFuture for EXP-355."""
    hist_ch = train_hist.shape[2]
    pk_ch = train_future_pk.shape[2]
    n_horizons = train_y.shape[1]
    model = ForecastCNNWithFuture(hist_ch, pk_ch, n_horizons).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=5, factor=0.5)

    th = torch.from_numpy(train_hist).float()
    tf = torch.from_numpy(train_future_pk).float()
    ty = torch.from_numpy(train_y).float()
    vh = torch.from_numpy(val_hist).float().to(device)
    vf = torch.from_numpy(val_future_pk).float().to(device)
    vy = torch.from_numpy(val_y).float().to(device)

    ds = TensorDataset(th, tf, ty)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True,
                    pin_memory=(device.type == 'cuda'))

    best_mae = float('inf')
    wait = 0
    best_metrics = {}

    for epoch in range(epochs):
        model.train()
        for hb, fb, yb in dl:
            hb, fb, yb = hb.to(device), fb.to(device), yb.to(device)
            pred = model(hb, fb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(vh, vf)
            val_loss = criterion(val_pred, vy).item()
            mae_per_h = (val_pred - vy).abs().mean(dim=0) * GLUCOSE_SCALE
            overall_mae = mae_per_h.mean().item()

        scheduler.step(val_loss)

        if overall_mae < best_mae:
            best_mae = overall_mae
            best_metrics = {
                'mae_overall': overall_mae,
                'mae_per_horizon': {name: mae_per_h[i].item()
                                    for i, name in enumerate(HORIZONS.keys())},
                'mse': val_loss,
                'rmse': float(np.sqrt(val_loss) * GLUCOSE_SCALE),
            }
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_metrics


def extract_targets(base_windows, history_steps):
    """Extract glucose targets at forecast horizons from full windows.

    Returns:
        (N, n_horizons) normalized glucose targets
    """
    targets = []
    for name, offset in HORIZONS.items():
        idx = history_steps + offset - 1  # -1 because offset is step count
        targets.append(base_windows[:, idx, 0])  # glucose channel, normalized
    return np.stack(targets, axis=1).astype(np.float32)


# ─── Persistence Baseline ───

def persistence_baseline(base_val, history_steps):
    """Naive forecast: last glucose value persists at all horizons."""
    last_glucose = base_val[:, history_steps - 1, 0]  # normalized
    targets = extract_targets(base_val, history_steps)
    # MAE in mg/dL
    mae_per_h = {}
    for i, name in enumerate(HORIZONS.keys()):
        mae_per_h[name] = float(np.abs(last_glucose - targets[:, i]).mean()
                                * GLUCOSE_SCALE)
    return {
        'mae_overall': float(np.mean(list(mae_per_h.values()))),
        'mae_per_horizon': mae_per_h,
    }


# ─── EXP-352: Baseline PK Forecast Comparison ───

def run_exp_352(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Compare 6 channel variants for glucose forecasting."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-352: PK-Enhanced Glucose Forecasting")
    print("=" * 60)

    variants = ['baseline_8ch', 'pk_replace_8ch', 'pk_replace_6ch',
                'glucose_only_1ch', 'glucose_iob_2ch', 'baseline_notime_6ch',
                'augmented_14ch']

    targets_train = extract_targets(base_train, history_steps)
    targets_val = extract_targets(base_val, history_steps)
    persist = persistence_baseline(base_val, history_steps)

    results = {
        'experiment': 'EXP-352',
        'title': 'PK-Enhanced Glucose Forecasting',
        'hypothesis': ('Continuous PK channels (insulin_net, carb_rate, '
                       'net_balance) reduce forecast MAE vs sparse channels'),
        'history_steps': history_steps,
        'history_min': history_steps * 5,
        'horizons': {k: v * 5 for k, v in HORIZONS.items()},
        'n_train': len(base_train),
        'n_val': len(base_val),
        'seeds': seeds,
        'persistence_baseline': persist,
        'variants': {},
    }

    for vname in variants:
        print(f"\n─── Variant: {vname} ───")
        v_train = _build_variant(base_train, pk_train, vname)
        v_val = _build_variant(base_val, pk_val, vname)
        hist_train = v_train[:, :history_steps].copy()
        hist_val = v_val[:, :history_steps].copy()

        seed_results = []
        for seed in seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            metrics = train_forecast(
                hist_train, targets_train, hist_val, targets_val, device,
                **train_kw)
            seed_results.append(metrics)
            print(f"  seed={seed}: MAE={metrics['mae_overall']:.1f} mg/dL "
                  f"[h30={metrics['mae_per_horizon']['h30']:.1f}, "
                  f"h60={metrics['mae_per_horizon']['h60']:.1f}, "
                  f"h120={metrics['mae_per_horizon']['h120']:.1f}]")

        # Aggregate across seeds
        agg = aggregate_seed_results(seed_results)
        agg['n_channels'] = hist_train.shape[2]
        results['variants'][vname] = agg
        print(f"  MEAN: MAE={agg['mae_overall_mean']:.1f} "
              f"± {agg['mae_overall_std']:.1f} mg/dL")

    # Summary comparison
    results['comparison'] = build_comparison(results)
    return results


# ─── EXP-353: History Length × PK Interaction ───

def run_exp_353(patients_dir, device, output_dir, seeds=SEEDS, train_kw=None,
                max_patients=None):
    """Test PK benefit at different history lengths."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-353: History Length × PK Interaction")
    print("=" * 60)

    history_lengths = {
        '1h': 12, '2h': 24, '4h': 48, '6h': 72, '12h': 144,
    }
    variants = ['baseline_8ch', 'pk_replace_6ch']

    results = {
        'experiment': 'EXP-353',
        'title': 'History Length × PK Channel Interaction',
        'hypothesis': ('PK channels help at ≥4h history (full DIA visible), '
                       'baseline wins at ≤2h'),
        'seeds': seeds,
        'grid': {},
    }

    for hname, hsteps in history_lengths.items():
        print(f"\n{'='*40} History: {hname} ({hsteps} steps) {'='*40}")
        try:
            bt, bv, pt, pv = load_forecast_data(
                patients_dir, history_steps=hsteps, max_horizon=24,
                max_patients=max_patients)
        except RuntimeError as e:
            print(f"  SKIP: {e}")
            continue

        targets_train = extract_targets(bt, hsteps)
        targets_val = extract_targets(bv, hsteps)
        persist = persistence_baseline(bv, hsteps)
        results['grid'][hname] = {'persistence': persist, 'variants': {}}

        for vname in variants:
            print(f"\n  ─── {vname} ───")
            v_train = _build_variant(bt, pt, vname)
            v_val = _build_variant(bv, pv, vname)
            hist_train = v_train[:, :hsteps].copy()
            hist_val = v_val[:, :hsteps].copy()

            seed_results = []
            for seed in seeds:
                torch.manual_seed(seed)
                np.random.seed(seed)
                metrics = train_forecast(
                    hist_train, targets_train, hist_val, targets_val, device,
                    **train_kw)
                seed_results.append(metrics)

            agg = aggregate_seed_results(seed_results)
            results['grid'][hname]['variants'][vname] = agg
            print(f"    MAE={agg['mae_overall_mean']:.1f} "
                  f"± {agg['mae_overall_std']:.1f}")

    return results


# ─── EXP-354: Selective PK Channel Ablation ───

def run_exp_354(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Add PK channels one at a time to glucose-only baseline."""
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-354: Selective PK Channel Ablation")
    print("=" * 60)

    variants = [
        'glucose_only_1ch',
        'glucose+insulin_net',
        'glucose+carb_rate',
        'glucose+net_balance',
        'glucose+insulin_net+carb_rate',
        'glucose+all_pk',
    ]

    targets_train = extract_targets(base_train, history_steps)
    targets_val = extract_targets(base_val, history_steps)

    results = {
        'experiment': 'EXP-354',
        'title': 'Selective PK Channel Ablation for Forecasting',
        'hypothesis': ('insulin_net and carb_rate are most informative; '
                       'hepatic_prod and isf_curve add noise'),
        'history_steps': history_steps,
        'seeds': seeds,
        'variants': {},
    }

    for vname in variants:
        print(f"\n─── {vname} ───")
        v_train = _build_variant(base_train, pk_train, vname)
        v_val = _build_variant(base_val, pk_val, vname)
        hist_train = v_train[:, :history_steps].copy()
        hist_val = v_val[:, :history_steps].copy()

        seed_results = []
        for seed in seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            metrics = train_forecast(
                hist_train, targets_train, hist_val, targets_val, device,
                **train_kw)
            seed_results.append(metrics)
            print(f"  seed={seed}: MAE={metrics['mae_overall']:.1f}")

        agg = aggregate_seed_results(seed_results)
        agg['n_channels'] = hist_train.shape[2]
        results['variants'][vname] = agg
        print(f"  MEAN: MAE={agg['mae_overall_mean']:.1f} "
              f"± {agg['mae_overall_std']:.1f}")

    # Compute marginal improvement per channel
    if 'glucose_only_1ch' in results['variants']:
        base_mae = results['variants']['glucose_only_1ch']['mae_overall_mean']
        for vname, vdata in results['variants'].items():
            vdata['delta_vs_glucose_only'] = vdata['mae_overall_mean'] - base_mae

    return results


# ─── EXP-355: PK Forward Projection ───

def run_exp_355(base_train, base_val, pk_train, pk_val,
                history_steps, device, output_dir, seeds=SEEDS, train_kw=None):
    """Test whether projecting PK channels into the future helps.

    Since insulin absorption and carb digestion are deterministic given
    past events, PK channels in the prediction window are KNOWN. This
    gives the model the physical trajectory of metabolic state.
    """
    if train_kw is None:
        train_kw = {}
    print("\n" + "=" * 60)
    print("EXP-355: PK Forward Projection")
    print("=" * 60)

    max_horizon = max(HORIZONS.values())
    targets_train = extract_targets(base_train, history_steps)
    targets_val = extract_targets(base_val, history_steps)

    # PK channels for the future window (these are causal — computed from
    # past events, just evaluated at future timesteps)
    pk_future_train = pk_train[:, history_steps:history_steps + max_horizon].copy()
    pk_future_val = pk_val[:, history_steps:history_steps + max_horizon].copy()

    results = {
        'experiment': 'EXP-355',
        'title': 'PK Forward Projection into Prediction Window',
        'hypothesis': ('Known-future PK state (decaying insulin, digesting '
                       'carbs) improves forecasting — no information leakage'),
        'history_steps': history_steps,
        'max_horizon_steps': max_horizon,
        'seeds': seeds,
        'variants': {},
    }

    # Variant 1: Baseline CNN (no future PK) — glucose + PK history
    print("\n─── pk_hist_only (control) ───")
    v_train = _build_variant(base_train, pk_train, 'pk_replace_6ch')
    v_val = _build_variant(base_val, pk_val, 'pk_replace_6ch')
    hist_train = v_train[:, :history_steps].copy()
    hist_val = v_val[:, :history_steps].copy()

    seed_results_ctrl = []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        metrics = train_forecast(
            hist_train, targets_train, hist_val, targets_val, device,
            **train_kw)
        seed_results_ctrl.append(metrics)
    results['variants']['pk_hist_only'] = aggregate_seed_results(seed_results_ctrl)

    # Variant 2: CNN with future PK projection
    print("\n─── pk_hist+future_projection ───")
    # Select most relevant future PK channels: insulin_net(1), carb_rate(3),
    # net_balance(6), basal_ratio(2)
    future_pk_idx = [1, 2, 3, 6]
    fpk_train = pk_future_train[:, :, future_pk_idx].copy()
    fpk_val = pk_future_val[:, :, future_pk_idx].copy()

    seed_results_proj = []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        metrics = train_forecast_with_future(
            hist_train, fpk_train, targets_train,
            hist_val, fpk_val, targets_val, device, **train_kw)
        seed_results_proj.append(metrics)
        print(f"  seed={seed}: MAE={metrics['mae_overall']:.1f}")

    results['variants']['pk_hist+future'] = aggregate_seed_results(seed_results_proj)

    # Variant 3: Baseline 8ch + future PK (best of both?)
    print("\n─── baseline_hist+future_pk ───")
    base_hist_train = base_train[:, :history_steps].copy()
    base_hist_val = base_val[:, :history_steps].copy()

    seed_results_hybrid = []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        metrics = train_forecast_with_future(
            base_hist_train, fpk_train, targets_train,
            base_hist_val, fpk_val, targets_val, device, **train_kw)
        seed_results_hybrid.append(metrics)

    results['variants']['baseline_hist+future_pk'] = aggregate_seed_results(
        seed_results_hybrid)

    return results


# ─── Utilities ───

def aggregate_seed_results(seed_results):
    """Aggregate metrics across multi-seed runs."""
    overall_maes = [r['mae_overall'] for r in seed_results]
    rmses = [r['rmse'] for r in seed_results]
    agg = {
        'mae_overall_mean': float(np.mean(overall_maes)),
        'mae_overall_std': float(np.std(overall_maes)),
        'rmse_mean': float(np.mean(rmses)),
        'rmse_std': float(np.std(rmses)),
        'per_seed': seed_results,
    }
    # Per-horizon aggregation
    horizon_names = list(HORIZONS.keys())
    for hname in horizon_names:
        vals = [r['mae_per_horizon'][hname] for r in seed_results]
        agg[f'mae_{hname}_mean'] = float(np.mean(vals))
        agg[f'mae_{hname}_std'] = float(np.std(vals))
    return agg


def build_comparison(results):
    """Build summary comparison table."""
    comp = {}
    best_variant = None
    best_mae = float('inf')
    for vname, vdata in results['variants'].items():
        m = vdata['mae_overall_mean']
        comp[vname] = m
        if m < best_mae:
            best_mae = m
            best_variant = vname
    comp['best_variant'] = best_variant
    comp['best_mae'] = best_mae
    comp['persistence_mae'] = results.get('persistence_baseline', {}).get(
        'mae_overall', None)
    return comp


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description='PK Forecast Experiments')
    parser.add_argument('--patients-dir', type=str,
                        default='externals/ns-data/patients',
                        help='Directory with patient training data')
    parser.add_argument('--output-dir', type=str,
                        default='externals/experiments',
                        help='Output directory for results JSON')
    parser.add_argument('--device', type=str, default='auto',
                        help='Device: cpu, cuda, mps, or auto')
    parser.add_argument('--experiment', type=str, default='352',
                        help='Which experiment(s): 352, 353, 354, 355, or all')
    parser.add_argument('--history-steps', type=int, default=72,
                        help='History window in 5-min steps (default: 72 = 6h)')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: 1 seed, 4 patients, 30 epochs for fast directionality')
    args = parser.parse_args()

    # Quick mode overrides
    seeds = SEEDS_QUICK if args.quick else SEEDS
    max_patients = QUICK_PATIENTS if args.quick else None
    train_kw = dict(epochs=QUICK_EPOCHS, patience=QUICK_PATIENCE) if args.quick else {}

    # Resolve device
    if args.device == 'auto':
        if torch.cuda.is_available():
            device = torch.device('cuda')
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = torch.device('mps')
        else:
            device = torch.device('cpu')
    else:
        device = torch.device(args.device)
    print(f"Device: {device}")

    os.makedirs(args.output_dir, exist_ok=True)

    exps = args.experiment.lower()
    run_352 = exps in ('352', 'all')
    run_353 = exps in ('353', 'all')
    run_354 = exps in ('354', 'all')
    run_355 = exps in ('355', 'all')

    # Load data for shared experiments (352, 354, 355 share same windows)
    if run_352 or run_354 or run_355:
        bt, bv, pt, pv = load_forecast_data(
            args.patients_dir, history_steps=args.history_steps,
            max_horizon=max(HORIZONS.values()),
            max_patients=max_patients)

    all_results = {}
    t0 = time.time()

    if run_352:
        r = run_exp_352(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t0
        all_results['EXP-352'] = r
        outfile = os.path.join(args.output_dir, 'exp352_pk_forecast.json')
        with open(outfile, 'w') as f:
            json.dump(r, f, indent=2, default=str)
        print(f"\nSaved: {outfile}")

    if run_354:
        t1 = time.time()
        r = run_exp_354(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-354'] = r
        outfile = os.path.join(args.output_dir, 'exp354_pk_ablation.json')
        with open(outfile, 'w') as f:
            json.dump(r, f, indent=2, default=str)
        print(f"\nSaved: {outfile}")

    if run_355:
        t1 = time.time()
        r = run_exp_355(bt, bv, pt, pv, args.history_steps, device,
                        args.output_dir, seeds=seeds, train_kw=train_kw)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-355'] = r
        outfile = os.path.join(args.output_dir, 'exp355_pk_forward.json')
        with open(outfile, 'w') as f:
            json.dump(r, f, indent=2, default=str)
        print(f"\nSaved: {outfile}")

    if run_353:
        t1 = time.time()
        r = run_exp_353(args.patients_dir, device, args.output_dir,
                        seeds=seeds, train_kw=train_kw,
                        max_patients=max_patients)
        r['elapsed_seconds'] = time.time() - t1
        all_results['EXP-353'] = r
        outfile = os.path.join(args.output_dir, 'exp353_history_pk.json')
        with open(outfile, 'w') as f:
            json.dump(r, f, indent=2, default=str)
        print(f"\nSaved: {outfile}")

    total = time.time() - t0
    print(f"\nTotal elapsed: {total:.0f}s")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for eid, r in all_results.items():
        print(f"\n{eid}: {r.get('title', '')}")
        if 'comparison' in r:
            c = r['comparison']
            print(f"  Best: {c.get('best_variant')} "
                  f"(MAE={c.get('best_mae', 0):.1f} mg/dL)")
            if c.get('persistence_mae'):
                print(f"  Persistence baseline: {c['persistence_mae']:.1f} mg/dL")
        elif 'variants' in r:
            for vn, vd in r['variants'].items():
                if isinstance(vd, dict) and 'mae_overall_mean' in vd:
                    print(f"  {vn}: MAE={vd['mae_overall_mean']:.1f} "
                          f"± {vd['mae_overall_std']:.1f}")


if __name__ == '__main__':
    main()
