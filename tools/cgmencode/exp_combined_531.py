#!/usr/bin/env python3
"""EXP-531/532/533: Combined models, noise-adjusted R², state transitions.

EXP-531: Combined FIR + State-Dependent Model — fit separate 3-channel
         FIR filters for each metabolic state. EXP-528 (R²=0.10) and
         EXP-530 (R²=0.10) each doubled performance; combining them
         should reach R²>0.15.

EXP-532: Noise-Floor-Adjusted R² — report R² relative to achievable
         ceiling per patient. Patient k has 74% noise; R²=0.03 there
         means ~12% of explainable variance captured.

EXP-533: State Transition Dynamics — Markov chain analysis. How long
         does each state persist? What transitions are most common?
         This informs how temporal models should handle state boundaries.

References:
  - exp_fir_528.py: EXP-528 (3ch FIR R²=0.102), EXP-530 (state R²=0.105)
  - exp_fir_528.py: EXP-529 (spectral noise floor)
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


def _classify_states(bg, dbg, carb_supply, demand, valid):
    """Classify each timestep into metabolic state."""
    N = len(bg)
    carb_pos = carb_supply[valid & (carb_supply > 0)]
    carb_thresh = np.percentile(carb_pos, 25) if len(carb_pos) > 0 else 0.1
    demand_med = np.median(demand[valid])

    states = np.full(N, -1, dtype=int)  # -1 = unknown
    STATE_NAMES = ['fasting', 'post_meal', 'correction', 'recovery', 'stable']

    states[valid & (carb_supply > carb_thresh)] = 1  # post_meal
    mask_unset = valid & (states == -1)
    states[mask_unset & (carb_supply <= 0.01) & (demand < demand_med)] = 0  # fasting
    mask_unset = valid & (states == -1)
    states[mask_unset & (bg > 180) & (demand > demand_med)] = 2  # correction
    mask_unset = valid & (states == -1)
    states[mask_unset & (bg > 140) & (dbg < -1)] = 3  # recovery
    mask_unset = valid & (states == -1)
    states[mask_unset & (bg >= 70) & (bg <= 180)] = 4  # stable

    return states, STATE_NAMES


# ── EXP-531: Combined FIR + State-Dependent ─────────────────────────────

def run_exp531(patients, detail=False):
    """State-specific 3-channel FIR filters.

    For each metabolic state, fit a separate 3ch×L6 FIR filter.
    Compare combined R² against global FIR and global state-dependent.
    """
    L = 6  # FIR filter length (30 min)
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        channels = [sd['supply'], sd['demand'], sd['hepatic']]
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg)
        for ch in channels:
            valid = valid & np.isfinite(ch)

        states, STATE_NAMES = _classify_states(
            bg, dbg, sd['carb_supply'], sd['demand'], valid)

        # Build FIR feature matrix for all valid points
        start = L - 1
        all_X = []
        all_y = []
        all_states = []
        all_indices = []

        for t in range(start, N):
            if not valid[t] or states[t] < 0:
                continue
            # Build 3-channel lagged features
            row = []
            ok = True
            for ch in channels:
                taps = ch[t - L + 1:t + 1][::-1]
                if len(taps) != L or not np.all(np.isfinite(taps)):
                    ok = False
                    break
                row.extend(taps)
            if ok and np.isfinite(dbg[t]):
                all_X.append(row)
                all_y.append(dbg[t])
                all_states.append(states[t])
                all_indices.append(t)

        if len(all_X) < 2000:
            results[name] = {'error': 'insufficient data'}
            continue

        all_X = np.array(all_X)
        all_y = np.array(all_y)
        all_states = np.array(all_states)
        y_var = np.var(all_y)

        if y_var < 1e-6:
            results[name] = {'error': 'zero variance'}
            continue

        # 1. Global FIR baseline
        X_bias = np.column_stack([all_X, np.ones(len(all_X))])
        try:
            c_g = np.linalg.lstsq(X_bias, all_y, rcond=None)[0]
            pred_global = X_bias @ c_g
            r2_global = 1.0 - np.var(all_y - pred_global) / y_var
        except Exception:
            r2_global = None
            pred_global = np.full(len(all_y), np.mean(all_y))

        # 2. State-specific FIR
        pred_state = np.full(len(all_y), np.nan)
        state_r2 = {}

        for s_idx, s_name in enumerate(STATE_NAMES):
            s_mask = all_states == s_idx
            n_s = s_mask.sum()
            if n_s < 50:
                state_r2[s_name] = {'n': int(n_s), 'error': 'too few'}
                pred_state[s_mask] = np.mean(all_y[s_mask]) if n_s > 0 else 0
                continue

            X_s = np.column_stack([all_X[s_mask], np.ones(n_s)])
            y_s = all_y[s_mask]
            y_var_s = np.var(y_s)

            if y_var_s < 1e-6:
                state_r2[s_name] = {'n': int(n_s), 'r2': 0.0}
                pred_state[s_mask] = np.mean(y_s)
                continue

            try:
                c_s = np.linalg.lstsq(X_s, y_s, rcond=None)[0]
                pred_s = X_s @ c_s
                r2_s = 1.0 - np.var(y_s - pred_s) / y_var_s
                pred_state[s_mask] = pred_s
            except Exception:
                r2_s = None
                pred_state[s_mask] = np.mean(y_s)

            state_r2[s_name] = {
                'n': int(n_s),
                'pct': round(n_s / len(all_y) * 100, 1),
                'r2': round(float(r2_s), 4) if r2_s is not None else None,
            }

        # Combined R²
        has_pred = np.isfinite(pred_state)
        if has_pred.sum() > 1000:
            r2_combined = 1.0 - np.var(all_y[has_pred] - pred_state[has_pred]) / np.var(all_y[has_pred])
        else:
            r2_combined = None

        # 3. Also add BG as a feature to the combined model
        bg_feat = bg[all_indices]
        X_bg = np.column_stack([all_X, bg_feat, np.ones(len(all_X))])
        pred_state_bg = np.full(len(all_y), np.nan)

        for s_idx, s_name in enumerate(STATE_NAMES):
            s_mask = all_states == s_idx
            if s_mask.sum() < 50:
                pred_state_bg[s_mask] = np.mean(all_y[s_mask]) if s_mask.sum() > 0 else 0
                continue
            X_sb = X_bg[s_mask]
            y_s = all_y[s_mask]
            try:
                c_sb = np.linalg.lstsq(X_sb, y_s, rcond=None)[0]
                pred_state_bg[s_mask] = X_sb @ c_sb
            except Exception:
                pred_state_bg[s_mask] = np.mean(y_s)

        has_pred_bg = np.isfinite(pred_state_bg)
        if has_pred_bg.sum() > 1000:
            r2_combined_bg = 1.0 - np.var(all_y[has_pred_bg] - pred_state_bg[has_pred_bg]) / np.var(all_y[has_pred_bg])
        else:
            r2_combined_bg = None

        results[name] = {
            'r2_global_fir': round(float(r2_global), 4) if r2_global is not None else None,
            'r2_state_fir': round(float(r2_combined), 4) if r2_combined is not None else None,
            'r2_state_fir_bg': round(float(r2_combined_bg), 4) if r2_combined_bg is not None else None,
            'improvement_over_global': round(float(r2_combined - r2_global), 4) if r2_combined and r2_global else None,
            'states': state_r2,
            'n': len(all_y),
        }

        if detail:
            r = results[name]
            imp = r.get('improvement_over_global', 0) or 0
            print(f"  {name}: global_fir={r['r2_global_fir']:.3f} → "
                  f"state_fir={r['r2_state_fir']:.3f} → "
                  f"state_fir+bg={r['r2_state_fir_bg']:.3f} "
                  f"(Δ={imp:+.3f})")
            state_parts = [f"{k}={v['r2']:.3f}({v.get('pct',0):.0f}%)"
                          for k, v in state_r2.items()
                          if v.get('r2') is not None]
            if state_parts:
                print(f"       {' '.join(state_parts)}")

    # Summary
    summary = {}
    for key in ['r2_global_fir', 'r2_state_fir', 'r2_state_fir_bg']:
        vals = [v[key] for v in results.values()
                if isinstance(v.get(key), (int, float))]
        if vals:
            summary[key] = {
                'mean': round(float(np.mean(vals)), 4),
                'max': round(float(max(vals)), 4),
            }

    if detail and summary:
        print(f"\n  Summary:")
        for k, s in summary.items():
            print(f"    {k:25s}: mean={s['mean']:.3f} max={s['max']:.3f}")

    return {'patients': results, 'summary': summary}


# ── EXP-532: Noise-Floor-Adjusted R² ───────────────────────────────────

def run_exp532(patients, detail=False):
    """Report R² relative to achievable ceiling per patient.

    Noise floor estimated from EXP-529 spectral analysis: fraction of
    residual power in high-frequency band (< 1h period).

    R²_adjusted = R² / (1 - noise_floor_fraction)
    """
    FS = 1.0 / (5 * 60)

    results = {}

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

        resid_clean = residual.copy()
        resid_clean[~valid] = 0

        # Estimate noise floor via Welch PSD
        nperseg = min(24 * 12, len(resid_clean) // 4)
        try:
            freqs, psd = sig.welch(resid_clean, fs=FS, nperseg=nperseg,
                                   noverlap=nperseg // 2)
        except Exception:
            results[name] = {'error': 'welch failed'}
            continue

        total_power = np.trapezoid(psd, freqs)
        # High-freq band: > 1 cycle/hour
        hf_mask = freqs >= (1.0 / 3600)
        hf_power = np.trapezoid(psd[hf_mask], freqs[hf_mask]) if hf_mask.any() else 0

        noise_fraction = hf_power / total_power if total_power > 0 else 0
        achievable_ceiling = 1.0 - noise_fraction

        # Compute raw R² (3ch linear, same as EXP-522 with regression)
        supply = sd['supply']
        demand = sd['demand']
        hepatic = sd['hepatic']

        X = np.column_stack([supply[valid], demand[valid], hepatic[valid],
                             bg[valid], np.ones(valid.sum())])
        y = dbg[valid]
        y_var = np.var(y)

        try:
            c = np.linalg.lstsq(X, y, rcond=None)[0]
            pred = X @ c
            r2_raw = 1.0 - np.var(y - pred) / y_var
        except Exception:
            r2_raw = 0

        r2_adjusted = r2_raw / achievable_ceiling if achievable_ceiling > 0.01 else 0
        pct_of_achievable = r2_adjusted * 100

        results[name] = {
            'noise_fraction': round(float(noise_fraction), 3),
            'achievable_ceiling': round(float(achievable_ceiling), 3),
            'r2_raw': round(float(r2_raw), 4),
            'r2_adjusted': round(float(r2_adjusted), 4),
            'pct_of_achievable': round(pct_of_achievable, 1),
        }

        if detail:
            r = results[name]
            print(f"  {name}: noise={r['noise_fraction']:.0%} "
                  f"ceiling={r['achievable_ceiling']:.2f} "
                  f"R²={r['r2_raw']:.3f} → adj={r['r2_adjusted']:.3f} "
                  f"({r['pct_of_achievable']:.0f}% of achievable)")

    return results


# ── EXP-533: State Transition Dynamics ──────────────────────────────────

def run_exp533(patients, detail=False):
    """Markov chain analysis of metabolic state transitions.

    Questions:
    - How long does each state persist (dwell time)?
    - Which transitions are most common?
    - Are there forbidden transitions?
    - Does transition rate correlate with control quality?
    """
    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        bg = _get_bg(df)
        dbg = _compute_dbg(bg)
        N = len(bg)

        valid = np.isfinite(bg) & np.isfinite(dbg)
        states, STATE_NAMES = _classify_states(
            bg, dbg, sd['carb_supply'], sd['demand'], valid)

        n_states = len(STATE_NAMES)

        # Transition matrix (raw counts)
        trans_counts = np.zeros((n_states, n_states), dtype=int)
        for t in range(1, N):
            s_prev = states[t - 1]
            s_curr = states[t]
            if s_prev >= 0 and s_curr >= 0:
                trans_counts[s_prev, s_curr] += 1

        # Normalize to transition probabilities
        row_sums = trans_counts.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        trans_prob = trans_counts / row_sums

        # Dwell times (consecutive steps in same state)
        dwell_times = {s: [] for s in range(n_states)}
        current_state = states[0]
        current_dwell = 1 if current_state >= 0 else 0

        for t in range(1, N):
            if states[t] == current_state and current_state >= 0:
                current_dwell += 1
            else:
                if current_state >= 0 and current_dwell > 0:
                    dwell_times[current_state].append(current_dwell)
                current_state = states[t]
                current_dwell = 1 if current_state >= 0 else 0

        if current_state >= 0 and current_dwell > 0:
            dwell_times[current_state].append(current_dwell)

        # State distribution
        state_counts = np.zeros(n_states, dtype=int)
        for s in range(n_states):
            state_counts[s] = (states == s).sum()

        # Transition rate (transitions per hour)
        total_transitions = sum(1 for t in range(1, N)
                               if states[t] != states[t-1]
                               and states[t] >= 0 and states[t-1] >= 0)
        hours = N * 5 / 60
        trans_rate = total_transitions / hours if hours > 0 else 0

        # Build results
        state_info = {}
        for s, s_name in enumerate(STATE_NAMES):
            dwells = dwell_times[s]
            if dwells:
                state_info[s_name] = {
                    'count': int(state_counts[s]),
                    'pct': round(state_counts[s] / N * 100, 1),
                    'n_episodes': len(dwells),
                    'mean_dwell_min': round(float(np.mean(dwells)) * 5, 1),
                    'median_dwell_min': round(float(np.median(dwells)) * 5, 1),
                    'max_dwell_min': round(float(np.max(dwells)) * 5, 1),
                    'self_transition_prob': round(float(trans_prob[s, s]), 3),
                }
            else:
                state_info[s_name] = {'count': 0, 'pct': 0}

        # Top transitions (excluding self-loops)
        top_trans = []
        for i in range(n_states):
            for j in range(n_states):
                if i != j and trans_counts[i, j] > 0:
                    top_trans.append({
                        'from': STATE_NAMES[i],
                        'to': STATE_NAMES[j],
                        'count': int(trans_counts[i, j]),
                        'prob': round(float(trans_prob[i, j]), 3),
                    })
        top_trans.sort(key=lambda x: -x['count'])

        results[name] = {
            'states': state_info,
            'transition_rate_per_hour': round(trans_rate, 2),
            'top_transitions': top_trans[:10],
        }

        if detail:
            print(f"  {name}: {trans_rate:.1f} trans/hr")
            for s_name, info in state_info.items():
                if info.get('mean_dwell_min'):
                    print(f"    {s_name:12s}: {info['pct']:4.1f}% "
                          f"dwell={info['median_dwell_min']:.0f}min "
                          f"(mean={info['mean_dwell_min']:.0f}min) "
                          f"P(stay)={info['self_transition_prob']:.2f}")

    # Population summary
    summary = {}
    trans_rates = [v['transition_rate_per_hour'] for v in results.values()
                   if 'transition_rate_per_hour' in v]
    if trans_rates:
        summary['transition_rate'] = {
            'mean': round(float(np.mean(trans_rates)), 2),
            'min': round(float(min(trans_rates)), 2),
            'max': round(float(max(trans_rates)), 2),
        }

    for s_name in ['fasting', 'post_meal', 'correction', 'recovery', 'stable']:
        dwells = [v['states'][s_name]['median_dwell_min']
                  for v in results.values()
                  if s_name in v.get('states', {})
                  and v['states'][s_name].get('median_dwell_min')]
        if dwells:
            summary[f'{s_name}_dwell'] = {
                'median_min': round(float(np.median(dwells)), 0),
                'mean_min': round(float(np.mean(dwells)), 0),
            }

    if detail and summary:
        print(f"\n  Population: trans_rate={summary.get('transition_rate',{}).get('mean',0):.1f}/hr")
        for s_name in ['fasting', 'post_meal', 'correction', 'recovery', 'stable']:
            key = f'{s_name}_dwell'
            if key in summary:
                print(f"    {s_name:12s}: median dwell={summary[key]['median_min']:.0f}min")

    return {'patients': results, 'summary': summary}


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-531/532/533: Combined model, noise-adjusted, state transitions')
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

    print("\n═══ EXP-531: Combined FIR + State-Dependent ═══")
    r531 = run_exp531(patients, detail=args.detail)
    all_results['exp531_combined'] = r531

    print("\n═══ EXP-532: Noise-Floor-Adjusted R² ═══")
    r532 = run_exp532(patients, detail=args.detail)
    all_results['exp532_noise_adjusted'] = r532

    print("\n═══ EXP-533: State Transition Dynamics ═══")
    r533 = run_exp533(patients, detail=args.detail)
    all_results['exp533_transitions'] = r533

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
