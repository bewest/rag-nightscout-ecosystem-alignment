#!/usr/bin/env python3
"""EXP-528/529/530: Convolutional flux models and residual decomposition.

EXP-528: FIR Filter Model — use recent flux HISTORY (not single lag) to
         predict dBG/dt. A Finite Impulse Response filter with N taps
         captures the full transfer function between flux and BG response.
         This is the natural next step after EXP-525-527 showed single-lag
         models plateau at ~6.5% R².

EXP-529: Residual Spectral Decomposition — what frequency content exists
         in the residuals? If dominated by low-frequency drift, different
         correction needed than if dominated by meal-frequency oscillations.

EXP-530: State-Dependent Model — partition data into states (fasting, meal,
         correction, dawn) and fit separate linear models for each. If
         different states have different dynamics (EXP-525 confirmed different
         lags), state-dependent modeling should improve substantially.

References:
  - exp_nonlinear_525.py: EXP-526 (full model R²=0.065)
  - exp_leadlag_521.py: EXP-521 (lag=+10min population)
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, signal as sig

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


def _get_bg(df):
    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return df[bg_col].values.astype(float)


def _compute_dbg(bg):
    N = len(bg)
    dbg = np.full(N, np.nan)
    dbg[1:-1] = (bg[2:] - bg[:-2]) / 2.0
    if N > 1:
        dbg[0] = bg[1] - bg[0]
        dbg[-1] = bg[-1] - bg[-2]
    return dbg


# ── EXP-528: FIR Filter Model ──────────────────────────────────────────

def run_exp528(patients, detail=False):
    """Use recent flux history to predict dBG/dt via FIR filter.

    For filter length L, the model is:
        dBG/dt[t] = sum_{k=0}^{L-1} h[k] * flux[t-k] + bias

    This captures the full impulse response: how much does flux at
    time t-k contribute to the BG change at time t?

    Test filter lengths: 1 (single point), 3 (15min), 6 (30min),
    12 (1h), 24 (2h), 36 (3h).
    """
    FILTER_LENGTHS = [1, 3, 6, 12, 24, 36]
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        channels = {
            'net': sd['net'],
            'supply': sd['supply'],
            'demand': sd['demand'],
            'hepatic': sd['hepatic'],
        }

        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid_base = np.isfinite(bg) & np.isfinite(dbg)
        for ch in channels.values():
            valid_base = valid_base & np.isfinite(ch)

        pat_results = {}

        for L in FILTER_LENGTHS:
            # Build Toeplitz-style feature matrix
            # For net-only FIR
            net = channels['net']
            start = L - 1
            valid_fir = valid_base[start:]

            # Build lagged feature matrix
            X_rows = []
            for t in range(start, N):
                if not valid_fir[t - start]:
                    continue
                row = net[t - L + 1:t + 1][::-1]  # most recent first
                if len(row) == L and np.all(np.isfinite(row)):
                    X_rows.append(row)

            if len(X_rows) < 1000:
                pat_results[f'L{L}'] = {'error': 'insufficient data'}
                continue

            X = np.array(X_rows)
            # Corresponding dBG values
            y_indices = []
            for t in range(start, N):
                if valid_fir[t - start]:
                    row = net[t - L + 1:t + 1]
                    if len(row) == L and np.all(np.isfinite(row)):
                        y_indices.append(t)

            y = dbg[y_indices]
            valid_y = np.isfinite(y)
            X = X[valid_y]
            y = y[valid_y]

            if len(y) < 1000:
                pat_results[f'L{L}'] = {'error': 'insufficient valid'}
                continue

            X_bias = np.column_stack([X, np.ones(len(X))])

            try:
                coeffs = np.linalg.lstsq(X_bias, y, rcond=None)[0]
                pred = X_bias @ coeffs
                y_var = np.var(y)
                r2 = 1.0 - np.var(y - pred) / y_var if y_var > 1e-6 else 0
                # Extract impulse response (filter taps)
                h = coeffs[:L].tolist()
            except Exception:
                r2 = None
                h = None

            pat_results[f'L{L}'] = {
                'r2': round(r2, 4) if r2 is not None else None,
                'n': len(y),
                'filter_taps': [round(x, 5) for x in h] if h else None,
            }

        # Also test 3-channel FIR (supply, demand, hepatic each with L=6 taps)
        L_multi = 6
        start = L_multi - 1
        X_multi_rows = []
        y_multi = []
        for t in range(start, N):
            if not valid_base[t]:
                continue
            rows = []
            ok = True
            for ch_name in ['supply', 'demand', 'hepatic']:
                ch = channels[ch_name]
                row = ch[t - L_multi + 1:t + 1][::-1]
                if len(row) != L_multi or not np.all(np.isfinite(row)):
                    ok = False
                    break
                rows.extend(row)
            if ok and np.isfinite(dbg[t]):
                X_multi_rows.append(rows)
                y_multi.append(dbg[t])

        if len(X_multi_rows) > 1000:
            X_m = np.array(X_multi_rows)
            y_m = np.array(y_multi)
            X_m_bias = np.column_stack([X_m, np.ones(len(X_m))])
            try:
                coeffs = np.linalg.lstsq(X_m_bias, y_m, rcond=None)[0]
                pred = X_m_bias @ coeffs
                r2_multi = 1.0 - np.var(y_m - pred) / np.var(y_m)
            except Exception:
                r2_multi = None
            pat_results['multi_3ch_L6'] = {
                'r2': round(r2_multi, 4) if r2_multi is not None else None,
                'n': len(y_m),
                'n_features': 3 * L_multi + 1,
            }

        results[name] = pat_results

        if detail:
            parts = [f"L{L}={pat_results[f'L{L}']['r2']:.3f}"
                     for L in FILTER_LENGTHS
                     if pat_results.get(f'L{L}', {}).get('r2') is not None]
            multi_r2 = pat_results.get('multi_3ch_L6', {}).get('r2')
            if multi_r2 is not None:
                parts.append(f"3ch×6={multi_r2:.3f}")
            print(f"  {name}: " + " | ".join(parts))

    # Summary across patients
    summary = {}
    for key_name in [f'L{L}' for L in FILTER_LENGTHS] + ['multi_3ch_L6']:
        vals = [v[key_name]['r2'] for v in results.values()
                if isinstance(v.get(key_name), dict) and v[key_name].get('r2') is not None]
        if vals:
            summary[key_name] = {
                'mean_r2': round(float(np.mean(vals)), 4),
                'max_r2': round(float(max(vals)), 4),
            }

    if detail and summary:
        print("\n  Population R² by filter length:")
        for k in summary:
            s = summary[k]
            print(f"    {k:12s}: mean={s['mean_r2']:.3f} max={s['max_r2']:.3f}")

    return {'patients': results, 'summary': summary}


# ── EXP-529: Residual Spectral Decomposition ───────────────────────────

def run_exp529(patients, detail=False):
    """Analyze frequency content of flux residuals.

    Key question: are residuals dominated by:
    - Very low freq (>24h) = multi-day drift (settings, hormones)
    - Circadian (~24h) = dawn phenomenon, daily patterns
    - Meal-freq (~4-8h) = unmodeled meal dynamics
    - High-freq (<1h) = sensor noise, rapid dynamics

    Use Welch's method for robust PSD estimation.
    """
    results = {}
    FS = 1.0 / (5 * 60)  # samples/second (5-min intervals)

    # Frequency bands (in cycles/hour)
    BANDS = {
        'ultra_low': (0, 1/24),      # > 24h period
        'circadian': (1/24, 1/12),    # 12-24h period
        'meal_freq': (1/12, 1/4),     # 4-12h period
        'post_meal': (1/4, 1/1),      # 1-4h period
        'high_freq': (1/1, 1/0.167),  # 10min-1h period
    }
    # Convert to Hz (cycles/second)
    BANDS_HZ = {k: (v[0] / 3600, v[1] / 3600) for k, v in BANDS.items()}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        net = sd['net']
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg) & np.isfinite(net)
        residual = dbg - net[:len(dbg)]

        # Fill NaN with 0 for spectral analysis (interpolation would be better
        # but for PSD estimation zero-fill is acceptable with Welch method)
        resid_clean = residual.copy()
        resid_clean[~valid] = 0

        # Welch PSD with 2h segments (24 points), 50% overlap
        nperseg = min(24 * 12, len(resid_clean) // 4)  # 12h segments
        try:
            freqs, psd = sig.welch(resid_clean, fs=FS, nperseg=nperseg,
                                   noverlap=nperseg // 2)
        except Exception:
            results[name] = {'error': 'welch failed'}
            continue

        total_power = np.trapezoid(psd, freqs)
        if total_power < 1e-10:
            results[name] = {'error': 'zero power'}
            continue

        band_power = {}
        for bname, (f_lo, f_hi) in BANDS_HZ.items():
            mask = (freqs >= f_lo) & (freqs < f_hi)
            if mask.any():
                bp = np.trapezoid(psd[mask], freqs[mask])
                band_power[bname] = {
                    'power': round(float(bp), 4),
                    'pct': round(float(bp / total_power * 100), 1),
                }

        # Dominant frequency
        dom_idx = np.argmax(psd[1:]) + 1  # skip DC
        dom_freq_hz = float(freqs[dom_idx])
        dom_period_hours = 1.0 / (dom_freq_hz * 3600) if dom_freq_hz > 0 else np.inf

        results[name] = {
            'total_power': round(float(total_power), 2),
            'band_power': band_power,
            'dominant_period_hours': round(dom_period_hours, 1),
            'dominant_freq_hz': round(dom_freq_hz, 8),
        }

        if detail:
            band_str = " ".join(f"{k}={v['pct']:.0f}%"
                                for k, v in band_power.items())
            print(f"  {name}: dom_period={dom_period_hours:.1f}h | {band_str}")

    # Population summary
    summary = {}
    for bname in BANDS:
        pcts = [v['band_power'][bname]['pct']
                for v in results.values()
                if isinstance(v.get('band_power'), dict) and bname in v.get('band_power', {})]
        if pcts:
            summary[bname] = {
                'mean_pct': round(float(np.mean(pcts)), 1),
                'std_pct': round(float(np.std(pcts)), 1),
            }

    if detail and summary:
        print("\n  Population band power (% of total):")
        for bname, s in summary.items():
            print(f"    {bname:15s}: {s['mean_pct']:.1f}% ± {s['std_pct']:.1f}%")

    return {'patients': results, 'summary': summary}


# ── EXP-530: State-Dependent Model ─────────────────────────────────────

def run_exp530(patients, detail=False):
    """Fit separate linear models for each metabolic state.

    States:
    1. Fasting: no carbs, low demand (basal only)
    2. Post-meal: active carb absorption (carb_supply > threshold)
    3. Correction: high BG + elevated demand (insulin correction)
    4. Recovery: falling BG after high (BG > 140, dBG < 0)
    5. Stable: BG in range, low flux (well-controlled)

    Compare: single global model vs state-mixture model (weighted R²).
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
        carb = sd['carb_supply']
        hepatic = sd['hepatic']

        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid = (np.isfinite(bg) & np.isfinite(dbg) & np.isfinite(net) &
                 np.isfinite(supply) & np.isfinite(demand))

        if valid.sum() < 3000:
            results[name] = {'error': 'insufficient data'}
            continue

        # Classify each timestep into states
        carb_thresh = np.percentile(carb[valid & (carb > 0)], 25) if np.any(carb[valid] > 0) else 0.1
        demand_med = np.median(demand[valid])

        states = np.full(N, 'unknown', dtype='U12')
        states[valid & (carb > carb_thresh)] = 'post_meal'
        states[valid & (carb <= 0.01) & (demand < demand_med) & (states == 'unknown')] = 'fasting'
        states[valid & (bg > 180) & (demand > demand_med) & (states == 'unknown')] = 'correction'
        states[valid & (bg > 140) & (dbg < -1) & (states == 'unknown')] = 'recovery'
        states[valid & (bg >= 70) & (bg <= 180) & (states == 'unknown')] = 'stable'
        # Everything else stays 'unknown'

        # Global model (baseline)
        X_global = np.column_stack([
            supply[valid], demand[valid], hepatic[valid],
            bg[valid], np.ones(valid.sum())
        ])
        y_global = dbg[valid]
        try:
            c_g = np.linalg.lstsq(X_global, y_global, rcond=None)[0]
            pred_g = X_global @ c_g
            r2_global = 1.0 - np.var(y_global - pred_g) / np.var(y_global)
        except Exception:
            r2_global = None

        # State-specific models
        state_results = {}
        pred_state = np.full(valid.sum(), np.nan)

        idx_valid = np.where(valid)[0]
        for state_name in ['fasting', 'post_meal', 'correction', 'recovery', 'stable']:
            s_mask = states[idx_valid] == state_name
            n_s = s_mask.sum()

            if n_s < 100:
                state_results[state_name] = {'n': int(n_s), 'error': 'too few'}
                continue

            X_s = X_global[s_mask]
            y_s = y_global[s_mask]
            y_var_s = np.var(y_s)

            if y_var_s < 1e-6:
                state_results[state_name] = {'n': int(n_s), 'r2': 0.0}
                pred_state[s_mask] = np.mean(y_s)
                continue

            try:
                c_s = np.linalg.lstsq(X_s, y_s, rcond=None)[0]
                pred_s = X_s @ c_s
                r2_s = 1.0 - np.var(y_s - pred_s) / y_var_s
                pred_state[s_mask] = pred_s
            except Exception:
                r2_s = None

            state_results[state_name] = {
                'n': int(n_s),
                'pct': round(n_s / valid.sum() * 100, 1),
                'r2': round(float(r2_s), 4) if r2_s is not None else None,
                'dbg_mean': round(float(np.mean(y_s)), 2),
                'dbg_std': round(float(np.std(y_s)), 2),
            }

        # Combined state model R² (weighted)
        has_pred = np.isfinite(pred_state)
        if has_pred.sum() > 1000:
            r2_combined = 1.0 - np.var(y_global[has_pred] - pred_state[has_pred]) / np.var(y_global[has_pred])
        else:
            r2_combined = None

        results[name] = {
            'r2_global': round(float(r2_global), 4) if r2_global is not None else None,
            'r2_state_combined': round(float(r2_combined), 4) if r2_combined is not None else None,
            'improvement': round(float(r2_combined - r2_global), 4) if r2_combined and r2_global else None,
            'states': state_results,
        }

        if detail:
            r = results[name]
            imp = r.get('improvement', 0) or 0
            state_parts = [f"{k}={v['r2']:.3f}({v['pct']:.0f}%)"
                          for k, v in state_results.items()
                          if v.get('r2') is not None]
            print(f"  {name}: global={r['r2_global']:.3f} → state={r['r2_state_combined']:.3f} "
                  f"(Δ={imp:+.3f})")
            print(f"       {' '.join(state_parts)}")

    # Summary
    r2g = [v['r2_global'] for v in results.values() if v.get('r2_global') is not None]
    r2s = [v['r2_state_combined'] for v in results.values() if v.get('r2_state_combined') is not None]
    imps = [v['improvement'] for v in results.values() if v.get('improvement') is not None]

    summary = {}
    if r2g:
        summary['global_r2'] = {'mean': round(float(np.mean(r2g)), 4), 'max': round(float(max(r2g)), 4)}
    if r2s:
        summary['state_r2'] = {'mean': round(float(np.mean(r2s)), 4), 'max': round(float(max(r2s)), 4)}
    if imps:
        summary['improvement'] = {'mean': round(float(np.mean(imps)), 4), 'max': round(float(max(imps)), 4)}

    if detail and summary:
        print(f"\n  Summary: global mean={summary.get('global_r2',{}).get('mean',0):.3f} "
              f"→ state mean={summary.get('state_r2',{}).get('mean',0):.3f} "
              f"(Δ={summary.get('improvement',{}).get('mean',0):+.3f})")

    return {'patients': results, 'summary': summary}


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-528/529/530: FIR filter, spectral, state-dependent models')
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

    print("\n═══ EXP-528: FIR Filter Model ═══")
    r528 = run_exp528(patients, detail=args.detail)
    all_results['exp528_fir_filter'] = r528

    print("\n═══ EXP-529: Residual Spectral Decomposition ═══")
    r529 = run_exp529(patients, detail=args.detail)
    all_results['exp529_spectral'] = r529

    print("\n═══ EXP-530: State-Dependent Model ═══")
    r530 = run_exp530(patients, detail=args.detail)
    all_results['exp530_state_dependent'] = r530

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
