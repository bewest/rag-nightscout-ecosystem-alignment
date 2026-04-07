#!/usr/bin/env python3
"""EXP-525/526/527: Advanced flux-to-BG modeling.

EXP-525: Windowed Lag Analysis — does the optimal lag vary during meal
         vs fasting periods? If meals produce different lag than fasting,
         a state-dependent lag correction could help.

EXP-526: Nonlinear Flux Model — polynomial + interaction terms.
         Linear flux→dBG R²≈5%. Nonlinear terms (supply×demand interaction,
         BG-level-dependent sensitivity, quadratic terms) may capture more.

EXP-527: Multi-Channel Lagged Regression — use supply, demand, hepatic
         as separate channels with independent lags. Each physiological
         process has different transport delay (insulin ~15min, carbs ~30min,
         hepatic ~immediate).

References:
  - exp_leadlag_521.py: EXP-521/522 (lag=+10min, R²≈5%)
  - exp_metabolic_441.py: compute_supply_demand()
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


def _get_bg(df):
    """Get BG array from df with correct column name."""
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return df[bg_col].values.astype(float)


def _compute_dbg(bg):
    """Centered-difference dBG/dt."""
    N = len(bg)
    dbg = np.full(N, np.nan)
    dbg[1:-1] = (bg[2:] - bg[:-2]) / 2.0
    if N > 1:
        dbg[0] = bg[1] - bg[0]
        dbg[-1] = bg[-1] - bg[-2]
    return dbg


# ── EXP-525: Windowed Lag Analysis ─────────────────────────────────────

def run_exp525(patients, detail=False):
    """Compare optimal lag during meal windows vs fasting windows.

    Meal windows: periods where carb_supply > threshold (active absorption)
    Fasting windows: periods where carb_supply ≈ 0 and demand is basal-only
    High-BG windows: BG > 180 (correction territory)
    Low-BG windows: BG < 100 (risk territory)
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        carb_supply = sd['carb_supply']
        hepatic = sd['hepatic']

        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg) & np.isfinite(net_flux)

        # Define condition masks
        carb_threshold = np.percentile(carb_supply[carb_supply > 0], 25) if np.any(carb_supply > 0) else 0.1
        conditions = {
            'meal': valid & (carb_supply > carb_threshold),
            'fasting': valid & (carb_supply < 0.01) & (demand < np.median(demand[valid])),
            'high_bg': valid & (bg > 180),
            'low_bg': valid & (bg < 100),
            'correction': valid & (bg > 150) & (demand > np.percentile(demand[valid], 75)),
        }

        MAX_LAG = 12  # ±60 min
        pat_results = {}

        for cname, mask in conditions.items():
            if mask.sum() < 500:
                pat_results[cname] = {'error': 'insufficient data', 'n': int(mask.sum())}
                continue

            flux_m = net_flux.copy()
            flux_m[~mask] = 0
            flux_m[mask] -= flux_m[mask].mean()

            dbg_m = dbg.copy()
            dbg_m[~mask] = 0
            dbg_m[mask] -= dbg_m[mask].mean()

            lags = np.arange(-MAX_LAG, MAX_LAG + 1)
            xcorr = np.zeros(len(lags))

            for i, lag in enumerate(lags):
                if lag >= 0:
                    n_ov = N - lag
                    if n_ov < 200:
                        continue
                    xcorr[i] = np.sum(flux_m[:n_ov] * dbg_m[lag:lag + n_ov])
                else:
                    alag = abs(lag)
                    n_ov = N - alag
                    if n_ov < 200:
                        continue
                    xcorr[i] = np.sum(flux_m[alag:alag + n_ov] * dbg_m[:n_ov])

            denom = max(np.sqrt(np.sum(flux_m ** 2) * np.sum(dbg_m ** 2)), 1e-10)
            xcorr /= denom

            best_idx = np.argmax(xcorr)
            best_lag = int(lags[best_idx])
            zero_idx = np.where(lags == 0)[0][0]

            pat_results[cname] = {
                'best_lag_min': best_lag * 5,
                'best_corr': round(float(xcorr[best_idx]), 4),
                'zero_corr': round(float(xcorr[zero_idx]), 4),
                'n': int(mask.sum()),
                'pct': round(mask.sum() / valid.sum() * 100, 1),
            }

        results[name] = pat_results

        if detail:
            parts = []
            for cname in ['meal', 'fasting', 'high_bg', 'correction']:
                r = pat_results.get(cname, {})
                if 'best_lag_min' in r:
                    parts.append(f"{cname}={r['best_lag_min']:+d}min({r['best_corr']:.2f})")
            print(f"  {name}: " + " | ".join(parts))

    # Population summary
    summary = {}
    for cname in ['meal', 'fasting', 'high_bg', 'low_bg', 'correction']:
        lags_c = [v[cname]['best_lag_min']
                  for v in results.values()
                  if isinstance(v.get(cname), dict) and 'best_lag_min' in v[cname]]
        if lags_c:
            summary[cname] = {
                'median_lag_min': int(np.median(lags_c)),
                'mean_lag_min': round(float(np.mean(lags_c)), 1),
                'n_patients': len(lags_c),
            }

    return {'patients': results, 'summary': summary}


# ── EXP-526: Nonlinear Flux Model ──────────────────────────────────────

def run_exp526(patients, detail=False):
    """Polynomial + interaction features for flux→dBG prediction.

    Features:
    1. Linear: supply, demand, net (baseline from EXP-522)
    2. Quadratic: supply², demand², net²
    3. Interaction: supply×demand
    4. BG-dependent: net×bg_level (sensitivity varies with BG)
    5. Rate-of-change: Δsupply, Δdemand (acceleration terms)

    Compare R² across feature sets to find which nonlinear terms help most.
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']

        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid = (np.isfinite(bg) & np.isfinite(dbg) &
                 np.isfinite(net) & np.isfinite(supply) & np.isfinite(demand))

        if valid.sum() < 2000:
            results[name] = {'error': 'insufficient data'}
            continue

        # Apply +10min population lag (from EXP-521)
        lag = 2  # 10min = 2 steps
        end = N - lag
        v = valid[:end] & valid[lag:]
        if v.sum() < 2000:
            results[name] = {'error': 'insufficient data after lag'}
            continue

        y = dbg[lag:][v[:end]]

        # Acceleration terms
        d_supply = np.diff(supply, prepend=supply[0])
        d_demand = np.diff(demand, prepend=demand[0])

        # Feature sets
        feature_sets = {
            'linear_net': np.column_stack([net[:end][v[:end]]]),
            'linear_3ch': np.column_stack([
                supply[:end][v[:end]],
                demand[:end][v[:end]],
                sd['hepatic'][:end][v[:end]],
            ]),
            'quadratic': np.column_stack([
                net[:end][v[:end]],
                net[:end][v[:end]] ** 2,
            ]),
            'interaction': np.column_stack([
                supply[:end][v[:end]],
                demand[:end][v[:end]],
                supply[:end][v[:end]] * demand[:end][v[:end]],
            ]),
            'bg_dependent': np.column_stack([
                net[:end][v[:end]],
                net[:end][v[:end]] * bg[:end][v[:end]],
                bg[:end][v[:end]],
            ]),
            'acceleration': np.column_stack([
                net[:end][v[:end]],
                d_supply[:end][v[:end]],
                d_demand[:end][v[:end]],
            ]),
            'full': np.column_stack([
                supply[:end][v[:end]],
                demand[:end][v[:end]],
                sd['hepatic'][:end][v[:end]],
                supply[:end][v[:end]] * demand[:end][v[:end]],
                net[:end][v[:end]] * bg[:end][v[:end]],
                net[:end][v[:end]] ** 2,
                d_supply[:end][v[:end]],
                d_demand[:end][v[:end]],
            ]),
        }

        y_var = np.var(y)
        if y_var < 1e-6:
            results[name] = {'error': 'zero target variance'}
            continue

        pat_results = {}
        for fname, X in feature_sets.items():
            # OLS regression
            X_bias = np.column_stack([X, np.ones(len(X))])
            try:
                # Use pseudoinverse for stability
                coeffs = np.linalg.lstsq(X_bias, y, rcond=None)[0]
                pred = X_bias @ coeffs
                resid_var = np.var(y - pred)
                r2 = 1.0 - resid_var / y_var
                corr = float(np.corrcoef(pred, y)[0, 1])
            except Exception:
                r2 = None
                corr = None

            pat_results[fname] = {
                'r2': round(r2, 4) if r2 is not None else None,
                'corr': round(corr, 4) if corr is not None else None,
                'n_features': X.shape[1],
            }

        results[name] = pat_results

        if detail:
            parts = [f"{k}={v['r2']:.3f}" for k, v in pat_results.items()
                     if v.get('r2') is not None]
            print(f"  {name}: " + " | ".join(parts))

    # Population summary
    summary = {}
    fnames = ['linear_net', 'linear_3ch', 'quadratic', 'interaction',
              'bg_dependent', 'acceleration', 'full']
    for fname in fnames:
        r2_vals = [v[fname]['r2'] for v in results.values()
                   if isinstance(v.get(fname), dict) and v[fname].get('r2') is not None]
        if r2_vals:
            summary[fname] = {
                'mean_r2': round(float(np.mean(r2_vals)), 4),
                'median_r2': round(float(np.median(r2_vals)), 4),
                'max_r2': round(float(max(r2_vals)), 4),
                'n_patients': len(r2_vals),
            }

    if detail and summary:
        print("\n  Population R² summary:")
        for fname in fnames:
            if fname in summary:
                s = summary[fname]
                print(f"    {fname:15s}: mean={s['mean_r2']:.3f} "
                      f"median={s['median_r2']:.3f} max={s['max_r2']:.3f}")

    return {'patients': results, 'summary': summary}


# ── EXP-527: Multi-Channel Lagged Regression ───────────────────────────

def run_exp527(patients, detail=False):
    """Use supply, demand, hepatic as separate channels with independent lags.

    Each physiological process has a different transport delay:
    - Hepatic production: ~immediate (EGP → blood glucose is fast)
    - Insulin action: ~15-25min (subQ → plasma → receptor binding → GLUT4)
    - Carb absorption: ~20-40min (gut → portal → systemic)

    Build multi-channel regressor where each channel can have its own lag.
    Test: optimal per-channel lags vs uniform lag vs zero lag.
    """
    # Test lag combinations
    CHANNEL_LAGS_TO_TEST = [0, 1, 2, 3, 4, 6, 8, 10]  # steps (×5min each)

    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        supply = sd['supply']     # hepatic + carb
        demand = sd['demand']     # insulin
        hepatic = sd['hepatic']   # hepatic alone
        carb = sd['carb_supply']  # carb alone

        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid = (np.isfinite(bg) & np.isfinite(dbg) &
                 np.isfinite(supply) & np.isfinite(demand))

        if valid.sum() < 2000:
            results[name] = {'error': 'insufficient data'}
            continue

        y_var_full = np.var(dbg[valid])
        if y_var_full < 1e-6:
            results[name] = {'error': 'zero variance'}
            continue

        # Test each channel with each lag independently
        channel_data = {
            'hepatic': hepatic,
            'carb': carb,
            'demand': demand,
        }

        best_per_channel = {}
        for ch_name, ch_data in channel_data.items():
            best_r2 = -np.inf
            best_lag = 0

            for lag in CHANNEL_LAGS_TO_TEST:
                if lag == 0:
                    mask = valid
                    x = ch_data[mask]
                    y = dbg[mask]
                else:
                    end = N - lag
                    mask = valid[:end] & valid[lag:]
                    x = ch_data[:end][mask[:end]]
                    y = dbg[lag:][mask[:end]]

                if len(x) < 1000:
                    continue

                X = np.column_stack([x, np.ones(len(x))])
                try:
                    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
                    pred = X @ coeffs
                    r2 = 1.0 - np.var(y - pred) / np.var(y)
                except Exception:
                    r2 = -np.inf

                if r2 > best_r2:
                    best_r2 = r2
                    best_lag = lag

            best_per_channel[ch_name] = {
                'best_lag_steps': best_lag,
                'best_lag_min': best_lag * 5,
                'best_r2': round(float(best_r2), 4) if best_r2 > -np.inf else None,
            }

        # Now build combined model with per-channel optimal lags
        # Simpler approach: shift each channel, truncate to common length
        max_lag = max(v['best_lag_steps'] for v in best_per_channel.values())
        usable_len = N - max_lag if max_lag > 0 else N

        if usable_len < 1000:
            results[name] = {
                'error': 'insufficient overlap',
                'per_channel': best_per_channel,
            }
            continue

        # Target: dBG/dt at [max_lag:N] (the latest possible window)
        y_comb = dbg[max_lag:max_lag + usable_len]

        # Build per-channel-lag feature matrix
        channels_shifted = []
        for ch_name, ch_data in channel_data.items():
            lag = best_per_channel[ch_name]['best_lag_steps']
            # Channel at time t predicts dBG at time t+lag
            # Align so channel[t - (max_lag - lag)] maps to dBG[t]
            offset = max_lag - lag
            ch_shifted = ch_data[offset:offset + usable_len]
            channels_shifted.append(ch_shifted)

        # Common valid mask
        mask_comb = np.isfinite(y_comb)
        for ch in channels_shifted:
            mask_comb = mask_comb & np.isfinite(ch[:len(mask_comb)])

        n_valid = mask_comb.sum()
        if n_valid < 1000:
            results[name] = {
                'error': 'insufficient aligned data',
                'per_channel': best_per_channel,
            }
            continue

        y_v = y_comb[mask_comb]
        X_multi = np.column_stack([ch[:len(mask_comb)][mask_comb] for ch in channels_shifted]
                                   + [np.ones(n_valid)])
        y_var = np.var(y_v)

        try:
            coeffs = np.linalg.lstsq(X_multi, y_v, rcond=None)[0]
            pred = X_multi @ coeffs
            r2_multi = 1.0 - np.var(y_v - pred) / y_var
        except Exception:
            r2_multi = None

        # Compare: uniform lag (population +10min = 2 steps)
        uniform_lag = 2
        end_u = N - uniform_lag
        y_u_raw = dbg[uniform_lag:uniform_lag + end_u]
        X_h = hepatic[:end_u]
        X_c = carb[:end_u]
        X_d = demand[:end_u]
        mask_u = np.isfinite(y_u_raw) & np.isfinite(X_h) & np.isfinite(X_c) & np.isfinite(X_d)
        if mask_u.sum() > 1000:
            y_u = y_u_raw[mask_u]
            X_u = np.column_stack([
                X_h[mask_u], X_c[mask_u], X_d[mask_u], np.ones(mask_u.sum())
            ])
            try:
                c_u = np.linalg.lstsq(X_u, y_u, rcond=None)[0]
                r2_uniform = 1.0 - np.var(y_u - X_u @ c_u) / np.var(y_u)
            except Exception:
                r2_uniform = None
        else:
            r2_uniform = None

        # Zero-lag baseline
        mask_0 = np.isfinite(dbg) & np.isfinite(hepatic) & np.isfinite(carb) & np.isfinite(demand)
        if mask_0.sum() > 1000:
            y_0 = dbg[mask_0]
            X_0 = np.column_stack([
                hepatic[mask_0], carb[mask_0], demand[mask_0], np.ones(mask_0.sum())
            ])
            try:
                c_0 = np.linalg.lstsq(X_0, y_0, rcond=None)[0]
                r2_zero = 1.0 - np.var(y_0 - X_0 @ c_0) / np.var(y_0)
            except Exception:
                r2_zero = None
        else:
            r2_zero = None

        results[name] = {
            'per_channel': best_per_channel,
            'r2_zero_lag': round(float(r2_zero), 4) if r2_zero is not None else None,
            'r2_uniform_lag': round(float(r2_uniform), 4) if r2_uniform is not None else None,
            'r2_per_channel_lag': round(float(r2_multi), 4) if r2_multi is not None else None,
            'n_samples': int(n_valid),
        }

        if detail:
            ch_info = " ".join(f"{k}={v['best_lag_min']}min"
                               for k, v in best_per_channel.items())
            r2z = results[name].get('r2_zero_lag', 0) or 0
            r2u = results[name].get('r2_uniform_lag', 0) or 0
            r2m = results[name].get('r2_per_channel_lag', 0) or 0
            print(f"  {name}: zero={r2z:.3f} uniform={r2u:.3f} multi={r2m:.3f} | {ch_info}")

    # Summary
    r2_keys = ['r2_zero_lag', 'r2_uniform_lag', 'r2_per_channel_lag']
    summary = {}
    for key in r2_keys:
        vals = [v[key] for v in results.values()
                if isinstance(v.get(key), (int, float)) and v[key] is not None]
        if vals:
            summary[key] = {
                'mean': round(float(np.mean(vals)), 4),
                'median': round(float(np.median(vals)), 4),
                'max': round(float(max(vals)), 4),
            }

    if detail and summary:
        print("\n  Summary:")
        for key in r2_keys:
            if key in summary:
                s = summary[key]
                print(f"    {key:25s}: mean={s['mean']:.3f} max={s['max']:.3f}")

    return {'patients': results, 'summary': summary}


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-525/526/527: Advanced flux-to-BG modeling')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    print("Loading patients...")
    patients = load_patients(str(patients_dir), max_patients=args.max_patients)
    print(f"  Loaded {len(patients)} patients")

    all_results = {}

    print("\n═══ EXP-525: Windowed Lag Analysis ═══")
    r525 = run_exp525(patients, detail=args.detail)
    all_results['exp525_windowed_lag'] = r525

    print("\n═══ EXP-526: Nonlinear Flux Model ═══")
    r526 = run_exp526(patients, detail=args.detail)
    all_results['exp526_nonlinear'] = r526

    print("\n═══ EXP-527: Multi-Channel Lagged Regression ═══")
    r527 = run_exp527(patients, detail=args.detail)
    all_results['exp527_multichannel'] = r527

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for key, val in all_results.items():
            path = RESULTS_DIR / f"{key}.json"
            with open(path, 'w') as f:
                json.dump(val, f, indent=2, default=str)
            print(f"\nSaved: {path}")

    return all_results


if __name__ == '__main__':
    main()
