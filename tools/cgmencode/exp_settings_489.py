#!/usr/bin/env python3
"""EXP-489–494: Settings Assessment & Glycemic Fidelity Scoring.

Can metabolic flux analysis detect when therapy settings (basal, ISF, CR)
are misconfigured? The glucose:insulin integral balance should indicate
when settings are too far off for analysis to be meaningful.

EXP-489: Basal adequacy — overnight glucose drift vs basal rate
EXP-490: ISF fidelity — correction bolus outcomes vs configured ISF
EXP-491: CR fidelity — post-meal glucose rise vs configured CR
EXP-492: Glycemic fidelity score — composite settings quality
EXP-493: Residual characterization — per-patient residual fingerprint
EXP-494: Sensor/cannula age effects on residual

References:
  - continuous_pk.py: expand_schedule(), PK feature builder
  - exp_metabolic_441.py: compute_supply_demand()
  - exp_refined_483.py: assess_day_readiness(), precondition framework
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cgmencode.continuous_pk import expand_schedule
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-489: Basal Adequacy Score ─────────────────────────────────────────

def run_exp489(patients, detail=False):
    """Overnight glucose drift as basal adequacy measure.

    If basal is set correctly, fasting glucose should be flat overnight (0-5 AM).
    Systematic rise = basal too low. Systematic fall = basal too high.

    The integral of overnight glucose derivative is the "basal adequacy score":
    - Score ≈ 0: basal is adequate
    - Score > 0: basal too low (glucose rising = EGP > insulin action)
    - Score < 0: basal too high (glucose falling = insulin action > EGP)
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)

        if not hasattr(df.index, 'hour'):
            continue

        hours = df.index.hour

        # Overnight windows: 0-5 AM
        overnight_mask = (hours >= 0) & (hours < 5)
        # Also check if there's been a recent meal (skip those nights)
        # Use demand signal: if demand is elevated, there's residual meal insulin
        sd = compute_supply_demand(df, pk)
        demand = sd['demand']

        dates = df.index.date
        unique_dates = sorted(set(dates))

        night_drifts = []
        for d in unique_dates:
            day_mask = (dates == d) & overnight_mask
            idx = np.where(day_mask)[0]
            if len(idx) < 36:  # need ≥3h of overnight data
                continue

            bg_night = bg[idx]
            valid = ~np.isnan(bg_night)
            if valid.sum() < 30:
                continue

            # Check demand level — skip nights with high residual meal insulin
            dem_night = demand[idx]
            if np.mean(dem_night) > np.percentile(demand[demand > 0], 75):
                continue  # late meal or correction still active

            # Compute drift: linear regression of BG over time
            t = np.arange(len(bg_night))
            bg_clean = bg_night.copy()
            bg_clean[~valid] = np.nan
            mask_valid = ~np.isnan(bg_clean)
            if mask_valid.sum() < 20:
                continue

            slope, intercept, r, pval, se = stats.linregress(
                t[mask_valid], bg_clean[mask_valid])
            # slope in mg/dL per 5-min step → mg/dL/hour
            drift_per_hour = slope * 12

            night_drifts.append({
                'date': str(d),
                'drift_mgdl_per_hour': round(drift_per_hour, 2),
                'r_squared': round(r**2, 3),
                'bg_start': round(float(bg_clean[mask_valid][0]), 1),
                'bg_end': round(float(bg_clean[mask_valid][-1]), 1),
            })

        if not night_drifts:
            results[p['name']] = {'n_nights': 0, 'error': 'no valid overnight windows'}
            continue

        drifts = [n['drift_mgdl_per_hour'] for n in night_drifts]
        results[p['name']] = {
            'n_nights': len(night_drifts),
            'drift_mean': round(float(np.mean(drifts)), 2),
            'drift_std': round(float(np.std(drifts)), 2),
            'drift_median': round(float(np.median(drifts)), 2),
            'basal_adequate': abs(float(np.mean(drifts))) < 5.0,  # <5 mg/dL/h
            'basal_direction': 'too_low' if np.mean(drifts) > 5 else
                              ('too_high' if np.mean(drifts) < -5 else 'adequate'),
            'nights_rising': int(sum(1 for d in drifts if d > 3)),
            'nights_falling': int(sum(1 for d in drifts if d < -3)),
            'nights_flat': int(sum(1 for d in drifts if abs(d) <= 3)),
        }

        if detail:
            r = results[p['name']]
            symbol = '✓' if r['basal_adequate'] else '✗'
            print(f"  {p['name']}: drift={r['drift_mean']:+.1f} mg/dL/h "
                  f"({r['basal_direction']}) {symbol}  "
                  f"[{r['nights_rising']}↑ {r['nights_flat']}→ {r['nights_falling']}↓ "
                  f"of {r['n_nights']} nights]")

    return results


# ── EXP-492: Glycemic Fidelity Score ─────────────────────────────────────

def run_exp492(patients, detail=False):
    """Composite score indicating how well settings match physiology.

    Components:
    1. Supply-demand balance: integral of (supply - demand) should ≈ 0 over 24h
    2. Residual magnitude: smaller residual = better model fit = better settings
    3. Overnight stability: flat overnight = adequate basal
    4. Post-meal recovery: returns to baseline within 4h = adequate CR/ISF

    Score 0-100 where 100 = perfect settings alignment.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        sd = compute_supply_demand(df, pk)

        valid = ~np.isnan(bg)
        N = len(df)

        # Component 1: Supply-demand balance
        # Net flux integral over sliding 24h windows should be small
        net_flux = sd['supply'] - sd['demand']
        if N > 288:
            daily_integrals = []
            for start in range(0, N - 288, 288):
                chunk = net_flux[start:start+288]
                daily_integrals.append(np.sum(chunk))
            abs_mean_integral = abs(np.mean(daily_integrals))
            # Exponential decay: τ=500 gives good separation
            # Perfect balance (0) → 100, typical imbalance (~1000) → 14
            balance_score = 100 * np.exp(-abs_mean_integral / 500)
        else:
            balance_score = 50.0

        # Component 2: Residual magnitude
        dbg = np.zeros_like(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
        predicted_dbg = net_flux
        residual = dbg - predicted_dbg
        residual_rmse = float(np.sqrt(np.nanmean(residual**2)))
        # Typical good: RMSE < 3 mg/dL per step; bad: > 10
        residual_score = max(0, min(100, 100 - (residual_rmse - 2) * 12))

        # Component 3: Overnight stability
        if hasattr(df.index, 'hour'):
            hours = df.index.hour
            overnight = (hours >= 0) & (hours < 5) & valid
            if overnight.sum() > 100:
                overnight_std = float(np.nanstd(bg[overnight]))
                overnight_score = max(0, min(100, 100 - (overnight_std - 15) * 2))
            else:
                overnight_score = 50.0
        else:
            overnight_score = 50.0

        # Component 4: Time in range as proxy for overall settings quality
        if valid.sum() > 100:
            tir = float(np.mean((bg[valid] >= 70) & (bg[valid] <= 180)))
            tir_score = tir * 100
        else:
            tir_score = 50.0

        # Composite: weighted average
        composite = (0.25 * balance_score + 0.25 * residual_score +
                    0.25 * overnight_score + 0.25 * tir_score)

        results[p['name']] = {
            'composite_score': round(composite, 1),
            'balance_score': round(balance_score, 1),
            'residual_score': round(residual_score, 1),
            'overnight_score': round(overnight_score, 1),
            'tir_score': round(tir_score, 1),
            'residual_rmse': round(residual_rmse, 2),
            'settings_quality': 'good' if composite >= 65 else
                               ('marginal' if composite >= 45 else 'poor'),
        }

        if detail:
            r = results[p['name']]
            print(f"  {p['name']}: {r['composite_score']:5.1f}/100 ({r['settings_quality']}) "
                  f"[bal={r['balance_score']:.0f} res={r['residual_score']:.0f} "
                  f"night={r['overnight_score']:.0f} tir={r['tir_score']:.0f}]")

    return results


# ── EXP-493: Residual Characterization ───────────────────────────────────

def run_exp493(patients, detail=False):
    """Per-patient residual fingerprint.

    Characterize the residual to understand WHY settings may be off:
    - Circadian pattern: when are residuals worst?
    - Autocorrelation: are residuals persistent (settings drift) or random (noise)?
    - Skewness: systematically positive (settings too aggressive) or negative?
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        sd = compute_supply_demand(df, pk)

        valid = ~np.isnan(bg)
        dbg = np.zeros_like(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
        predicted_dbg = sd['supply'] - sd['demand']
        residual = dbg - predicted_dbg

        # Replace NaN with 0 for analysis
        residual_clean = np.where(valid, residual, 0)

        # Circadian residual pattern (hourly means)
        if hasattr(df.index, 'hour'):
            hours = df.index.hour
            hourly_resid = {}
            for h in range(24):
                mask = (hours == h) & valid
                if mask.sum() > 10:
                    hourly_resid[h] = round(float(np.mean(residual[mask])), 3)

            worst_hour = max(hourly_resid, key=lambda h: abs(hourly_resid[h]))
            best_hour = min(hourly_resid, key=lambda h: abs(hourly_resid[h]))
        else:
            hourly_resid = {}
            worst_hour = best_hour = 0

        # Autocorrelation at lag 1, 6, 12, 36 (5min, 30min, 1h, 3h)
        acf = {}
        for lag in [1, 6, 12, 36]:
            if len(residual_clean) > lag + 100:
                r = np.corrcoef(residual_clean[lag:], residual_clean[:-lag])
                acf[f'lag_{lag*5}min'] = round(float(r[0, 1]), 3)

        # Skewness and kurtosis
        resid_valid = residual[valid & ~np.isnan(residual)]
        skew = float(stats.skew(resid_valid)) if len(resid_valid) > 100 else 0
        kurt = float(stats.kurtosis(resid_valid)) if len(resid_valid) > 100 else 0

        results[p['name']] = {
            'mean': round(float(np.nanmean(residual)), 3),
            'std': round(float(np.nanstd(residual)), 3),
            'skewness': round(skew, 3),
            'kurtosis': round(kurt, 3),
            'autocorrelation': acf,
            'worst_hour': int(worst_hour),
            'worst_hour_resid': hourly_resid.get(worst_hour, 0),
            'best_hour': int(best_hour),
            'persistent': acf.get('lag_30min', 0) > 0.3,  # >0.3 = settings issue
        }

        if detail:
            r = results[p['name']]
            persist = '⚠ persistent' if r['persistent'] else '✓ random'
            print(f"  {p['name']}: mean={r['mean']:+.2f} std={r['std']:.2f} "
                  f"skew={r['skewness']:+.2f} "
                  f"worst@{r['worst_hour']}h({r['worst_hour_resid']:+.2f}) "
                  f"acf30={acf.get('lag_30min', 0):.2f} {persist}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-489–494: Settings assessment & glycemic fidelity')
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    patients_dir = Path(args.patients_dir) if args.patients_dir else PATIENTS_DIR
    print(f"Loading patients...")
    patients = load_patients(str(patients_dir), max_patients=args.max_patients)
    print(f"  Loaded {len(patients)} patients")

    all_results = {}

    print("\n═══ EXP-489: Basal Adequacy (Overnight Drift) ═══")
    r489 = run_exp489(patients, detail=args.detail)
    all_results['exp489_basal_adequacy'] = r489

    # Summary
    adequate = sum(1 for v in r489.values() if v.get('basal_adequate'))
    print(f"\n  Summary: {adequate}/{len(r489)} patients have adequate basal "
          f"(drift < 5 mg/dL/h)")

    print("\n═══ EXP-492: Glycemic Fidelity Score ═══")
    r492 = run_exp492(patients, detail=args.detail)
    all_results['exp492_fidelity_score'] = r492

    scores = [v['composite_score'] for v in r492.values()]
    print(f"\n  Summary: mean={np.mean(scores):.1f}/100, "
          f"range={min(scores):.0f}–{max(scores):.0f}")
    for q in ['good', 'marginal', 'poor']:
        n = sum(1 for v in r492.values() if v['settings_quality'] == q)
        if n: print(f"    {q}: {n} patients")

    print("\n═══ EXP-493: Residual Characterization ═══")
    r493 = run_exp493(patients, detail=args.detail)
    all_results['exp493_residual_fingerprint'] = r493

    persistent = sum(1 for v in r493.values() if v.get('persistent'))
    print(f"\n  Summary: {persistent}/{len(r493)} patients have persistent residuals "
          f"(settings drift)")

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
