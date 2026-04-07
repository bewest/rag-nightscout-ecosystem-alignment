#!/usr/bin/env python3
"""EXP-495–500: ISF/CR Fidelity, Sensor Age, and Weekly Trends.

EXP-495: ISF fidelity — correction bolus outcomes vs configured ISF
EXP-496: CR fidelity — post-meal glucose excursion vs configured CR
EXP-500: Weekly fidelity trend — track settings quality over 6 months

References:
  - exp_settings_489.py: Basal adequacy, fidelity score, residual fingerprint
  - exp_refined_483.py: assess_day_readiness(), detect_meals_demand_weighted()
  - continuous_pk.py: expand_schedule(), build_continuous_pk_features()
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from cgmencode.continuous_pk import expand_schedule
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-495: ISF Fidelity ────────────────────────────────────────────────

def find_correction_boluses(df, pk):
    """Find correction-only boluses (bolus without carbs within ±30 min).

    A 'correction bolus' = insulin delivered to lower glucose, not to cover food.
    We identify these as bolus events where no carbs were entered within ±30 min.
    """
    if 'treatments' not in df.attrs:
        return []

    treatments = df.attrs.get('treatments', [])
    if not treatments:
        # Fallback: find bolus peaks in PK channel 1 (insulin_net) without carb peaks
        return _find_corrections_from_pk(df, pk)

    return []


def _find_corrections_from_pk(df, pk):
    """Identify correction-like events from PK channels.

    Strategy: Find periods where BG is elevated (>150), insulin_net is active
    (correction), and no carbs are present. Measure BG drop and insulin
    activity integral over 3h to compute effective ISF in mg/dL per
    activity-integral units.

    For SMB-dominant patients, corrections are sustained elevated insulin_net
    over 30-60 min, not single bolus jumps. The activity integral over the
    correction window is proportional to total insulin effect.
    """
    if pk is None or pk.shape[1] < 5:
        return []

    INS_NORM = 0.05  # PK_NORMALIZATION['insulin_net']
    insulin_net = pk[:, 1] * INS_NORM  # net insulin activity (U-activity/step)
    carb_rate = pk[:, 3]  # normalized carb absorption

    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)

    # Smooth insulin_net to find correction periods
    ins_smooth = pd.Series(insulin_net).rolling(6, center=True, min_periods=1).mean().values

    # Adaptive threshold: P60 of positive insulin activity
    pos_ins = ins_smooth[ins_smooth > 1e-6]
    ins_thresh = float(np.percentile(pos_ins, 60)) if len(pos_ins) > 100 else 0.001

    corrections = []
    i = 0
    N = len(df)

    while i < N - 36:  # need 3h post-correction
        # Trigger: BG > 150 AND insulin_net elevated
        if np.isnan(bg[i]) or bg[i] < 150:
            i += 1
            continue

        if ins_smooth[i] < ins_thresh:
            i += 1
            continue

        # No carbs in ±30 min
        window = slice(max(0, i - 6), min(N, i + 6))
        if np.max(carb_rate[window]) > 0.1:
            i += 6
            continue

        # Measure BG drop and insulin integral over 3h
        bg_3h = bg[i:i + 36]
        valid_3h = ~np.isnan(bg_3h)
        if valid_3h.sum() < 24:
            i += 12
            continue

        bg_start = bg[i]
        bg_end = float(bg_3h[valid_3h][-1])
        bg_drop = bg_start - bg_end

        # Insulin activity integral (proportional to total dose effect)
        ins_integral = float(np.sum(insulin_net[i:i + 36]))

        if ins_integral < 1e-4:
            i += 12
            continue

        # Effective ISF = BG drop / insulin integral (activity-units)
        effective_isf = float(bg_drop / ins_integral) if ins_integral > 0.001 else None

        corrections.append({
            'idx': i,
            'bg_start': float(bg_start),
            'bg_3h': bg_end,
            'bg_drop': float(bg_drop),
            'bg_nadir': float(np.nanmin(bg_3h)),
            'insulin_integral': ins_integral,
            'effective_isf': effective_isf,
        })
        i += 36  # skip 3h

    return corrections


def run_exp495(patients, detail=False):
    """Compare observed correction outcomes to configured ISF."""
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        # Get configured ISF from df.attrs (set by data loader)
        isf_sched = df.attrs.get('isf_schedule', [])
        units = df.attrs.get('profile_units', 'mg/dL')

        if isf_sched:
            isf_values = [entry['value'] for entry in isf_sched
                          if isinstance(entry, dict) and 'value' in entry]
            if isf_values:
                configured_isf = float(np.median(isf_values))
                if units == 'mmol/L' or configured_isf < 15:
                    configured_isf *= 18.0182
            else:
                configured_isf = None
        else:
            configured_isf = None

        corrections = _find_corrections_from_pk(df, pk)

        if len(corrections) < 5 or configured_isf is None:
            results[p['name']] = {
                'n_corrections': len(corrections),
                'configured_isf': configured_isf,
                'error': 'insufficient corrections or no ISF config'
            }
            if detail:
                print(f"  {p['name']}: {len(corrections)} corrections, ISF={configured_isf} — skipped")
            continue

        # Compute effective ISF from correction events (activity-integral units)
        valid_corrections = [c for c in corrections
                             if c.get('effective_isf') is not None and c['bg_drop'] > 10]
        if len(valid_corrections) < 5:
            results[p['name']] = {'n_corrections': len(corrections), 'error': 'too few valid corrections'}
            continue

        effective_isfs = [c['effective_isf'] for c in valid_corrections]
        median_effective = float(np.median(effective_isfs))

        # Calibrate: compute TDD from insulin activity integral to scale
        # The insulin activity integral over a full day ∝ TDD
        # We can compare relative ISF across patients and check temporal stability
        integrals = [c['insulin_integral'] for c in valid_corrections]
        drops = [c['bg_drop'] for c in valid_corrections]

        # Temporal stability: split into first/second half
        mid = len(valid_corrections) // 2
        if mid >= 3:
            early_isf = float(np.median(effective_isfs[:mid]))
            late_isf = float(np.median(effective_isfs[mid:]))
            isf_drift = late_isf - early_isf
            drift_pct = (isf_drift / early_isf * 100) if early_isf != 0 else 0
        else:
            early_isf = late_isf = median_effective
            isf_drift = 0.0
            drift_pct = 0.0

        # Consistency: IQR/median ratio (lower = more consistent corrections)
        iqr = float(np.percentile(effective_isfs, 75) - np.percentile(effective_isfs, 25))
        consistency = 1.0 - min(1.0, iqr / (abs(median_effective) + 1e-6))

        results[p['name']] = {
            'n_corrections': len(valid_corrections),
            'configured_isf': round(configured_isf, 1),
            'effective_isf_median': round(median_effective, 1),
            'effective_isf_iqr': [round(float(np.percentile(effective_isfs, 25)), 1),
                                   round(float(np.percentile(effective_isfs, 75)), 1)],
            'median_bg_drop': round(float(np.median(drops)), 1),
            'median_ins_integral': round(float(np.median(integrals)), 4),
            'early_isf': round(early_isf, 1),
            'late_isf': round(late_isf, 1),
            'isf_drift_pct': round(drift_pct, 1),
            'consistency': round(consistency, 3),
            'direction': 'drifting' if abs(drift_pct) > 20 else 'stable',
        }

        if detail:
            r = results[p['name']]
            sym = '→' if r['direction'] == 'stable' else '↕'
            print(f"  {p['name']}: ISF_cfg={r['configured_isf']:.0f} eff_med={r['effective_isf_median']:.1f} "
                  f"drift={r['isf_drift_pct']:+.0f}% consistency={r['consistency']:.2f} "
                  f"[{r['n_corrections']} corrections] {sym}")

    return results


# ── EXP-500: Weekly Fidelity Trend ───────────────────────────────────────

def compute_weekly_fidelity(df, pk, sd=None):
    """Compute fidelity score per week.

    Returns list of {week_start, composite_score, balance, residual, overnight, tir}.
    """
    if sd is None:
        sd = compute_supply_demand(df, pk)

    bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
    bg = df[bg_col].values.astype(np.float64)
    valid = ~np.isnan(bg)
    N = len(df)

    net_flux = sd['supply'] - sd['demand']
    dbg = np.zeros_like(bg)
    dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
    residual = dbg - net_flux

    if not hasattr(df.index, 'date'):
        return []

    dates = df.index.date
    hours = df.index.hour if hasattr(df.index, 'hour') else np.zeros(N)

    # Group into weeks
    unique_dates = sorted(set(dates))
    if len(unique_dates) < 7:
        return []

    weeks = []
    week_start = unique_dates[0]
    week_dates = []
    for d in unique_dates:
        if (d - week_start).days >= 7:
            weeks.append((week_start, week_dates))
            week_start = d
            week_dates = [d]
        else:
            week_dates.append(d)
    if week_dates:
        weeks.append((week_start, week_dates))

    weekly_scores = []
    for week_start, wdates in weeks:
        if len(wdates) < 5:  # need ≥5 days per week
            continue

        mask = np.isin(dates, wdates)
        idx = np.where(mask)[0]

        bg_week = bg[idx]
        valid_week = valid[idx]
        flux_week = net_flux[idx]
        resid_week = residual[idx]
        hours_week = hours[idx] if hasattr(hours, '__getitem__') else np.zeros(len(idx))

        # Balance score
        daily_flux = np.sum(flux_week)
        abs_flux = abs(daily_flux) / len(wdates)
        balance = float(100 * np.exp(-abs_flux / 500))

        # Residual score
        rmse = float(np.sqrt(np.nanmean(resid_week**2)))
        resid_score = max(0, min(100, 100 - (rmse - 2) * 12))

        # Overnight score
        overnight = (hours_week >= 0) & (hours_week < 5) & valid_week
        if overnight.sum() > 50:
            overnight_std = float(np.nanstd(bg_week[overnight]))
            overnight_score = max(0, min(100, 100 - (overnight_std - 15) * 2))
        else:
            overnight_score = 50.0

        # TIR
        if valid_week.sum() > 50:
            tir = float(np.mean((bg_week[valid_week] >= 70) & (bg_week[valid_week] <= 180)))
            tir_score = tir * 100
        else:
            tir_score = 50.0

        composite = 0.25 * balance + 0.25 * resid_score + 0.25 * overnight_score + 0.25 * tir_score

        weekly_scores.append({
            'week_start': str(week_start),
            'n_days': len(wdates),
            'composite': round(composite, 1),
            'balance': round(balance, 1),
            'residual': round(resid_score, 1),
            'overnight': round(overnight_score, 1),
            'tir': round(tir_score, 1),
        })

    return weekly_scores


def run_exp500(patients, detail=False):
    """Weekly fidelity trend over 6-month dataset."""
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']

        weekly = compute_weekly_fidelity(df, pk)
        if len(weekly) < 4:
            results[p['name']] = {'n_weeks': len(weekly), 'error': 'insufficient weeks'}
            continue

        composites = [w['composite'] for w in weekly]

        # Trend: linear regression of composite score over weeks
        x = np.arange(len(composites))
        slope, intercept, r, pval, se = stats.linregress(x, composites)

        # Stability: CV of weekly scores
        cv = np.std(composites) / (np.mean(composites) + 1e-6)

        # Best and worst weeks
        best_idx = int(np.argmax(composites))
        worst_idx = int(np.argmin(composites))

        results[p['name']] = {
            'n_weeks': len(weekly),
            'mean_score': round(float(np.mean(composites)), 1),
            'std_score': round(float(np.std(composites)), 1),
            'trend_slope': round(float(slope), 2),
            'trend_pvalue': round(float(pval), 4),
            'trend_direction': 'improving' if slope > 0.5 and pval < 0.1 else
                              ('degrading' if slope < -0.5 and pval < 0.1 else 'stable'),
            'cv': round(float(cv), 3),
            'best_week': weekly[best_idx],
            'worst_week': weekly[worst_idx],
            'weekly_scores': weekly,
        }

        if detail:
            r = results[p['name']]
            trend_sym = {'improving': '↑', 'degrading': '↓', 'stable': '→'}[r['trend_direction']]
            print(f"  {p['name']}: {r['mean_score']:.0f}±{r['std_score']:.0f}/100 "
                  f"over {r['n_weeks']} weeks {trend_sym} "
                  f"(slope={r['trend_slope']:+.1f}/wk, p={r['trend_pvalue']:.3f}) "
                  f"best={r['best_week']['composite']:.0f} worst={r['worst_week']['composite']:.0f}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-495–500: ISF/CR fidelity and weekly trends')
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

    print("\n═══ EXP-495: ISF Fidelity (Correction Outcomes) ═══")
    r495 = run_exp495(patients, detail=args.detail)
    all_results['exp495_isf_fidelity'] = r495

    adequate = sum(1 for v in r495.values() if v.get('direction') == 'stable')
    drifting = sum(1 for v in r495.values() if v.get('direction') == 'drifting')
    total = sum(1 for v in r495.values() if v.get('direction') and 'error' not in v)
    print(f"\n  Summary: {adequate}/{total} stable, {drifting}/{total} drifting")

    print("\n═══ EXP-500: Weekly Fidelity Trend ═══")
    r500 = run_exp500(patients, detail=args.detail)
    all_results['exp500_weekly_trend'] = r500

    for direction in ['improving', 'stable', 'degrading']:
        n = sum(1 for v in r500.values() if v.get('trend_direction') == direction)
        if n:
            print(f"  {direction}: {n} patients")

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
