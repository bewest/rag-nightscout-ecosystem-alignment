#!/usr/bin/env python3
"""EXP-521/522/523/524: Temporal alignment, circadian residuals, TDD normalization.

EXP-521: Lead/Lag Cross-Correlation — find optimal temporal offset between
         flux and dBG/dt. EXP-518 showed positive correlation but negative R²,
         suggesting flux is temporally misaligned with BG response.

EXP-522: Lag-Corrected Compression — recompute R² after shifting flux by
         optimal lag from EXP-521. If R² becomes positive, temporal alignment
         is the key missing ingredient.

EXP-523: Circadian Lag Profile — does the optimal lag vary by time of day?
         Morning (dawn phenomenon) vs post-meal vs overnight may have different
         lag structures reflecting different physiological processes.

EXP-524: TDD-Normalized Cross-Patient Transfer — normalize all flux features
         by Total Daily Dose to remove absolute insulin scale. Does this
         improve cross-patient distance-to-TIR correlation from EXP-503?

References:
  - exp_metabolic_441.py: compute_supply_demand()
  - exp_residual_511.py: EXP-518 compression ratio (R²<0 baseline)
  - exp_transfer_503.py: EXP-503 cross-patient transfer (r=-0.960)
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, signal

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.continuous_pk import PK_NORMALIZATION

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-521: Lead/Lag Cross-Correlation ─────────────────────────────────

def run_exp521(patients, detail=False):
    """Find optimal temporal offset between flux and dBG/dt.

    Cross-correlate net_flux with dBG/dt at lags from -60min to +120min
    (negative = flux leads BG, positive = flux trails BG).
    Also decompose into supply-lag and demand-lag separately.
    """
    results = {}
    MAX_LAG_STEPS = 24   # ±120 min at 5-min steps
    STEP_MIN = 5

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        supply = sd['supply']
        demand = sd['demand']

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        N = len(bg)

        # dBG/dt via centered difference
        dbg = np.full(N, np.nan)
        dbg[1:-1] = (bg[2:] - bg[:-2]) / 2.0
        dbg[0] = bg[1] - bg[0] if N > 1 else 0
        dbg[-1] = bg[-1] - bg[-2] if N > 1 else 0

        valid = np.isfinite(bg) & np.isfinite(dbg) & np.isfinite(net_flux)
        if valid.sum() < 2000:
            results[name] = {'error': 'insufficient data'}
            continue

        # Zero-mean for cross-correlation
        dbg_zm = dbg.copy()
        dbg_zm[~valid] = 0
        dbg_zm[valid] -= dbg_zm[valid].mean()

        flux_zm = net_flux.copy()
        flux_zm[~valid] = 0
        flux_zm[valid] -= flux_zm[valid].mean()

        supply_zm = supply.copy()
        supply_zm[~valid] = 0
        supply_zm[valid] -= supply_zm[valid].mean()

        demand_zm = demand.copy()
        demand_zm[~valid] = 0
        demand_zm[valid] -= demand_zm[valid].mean()

        # Normalized cross-correlation at each lag
        lags = np.arange(-MAX_LAG_STEPS, MAX_LAG_STEPS + 1)
        xcorr_net = np.zeros(len(lags))
        xcorr_supply = np.zeros(len(lags))
        xcorr_demand = np.zeros(len(lags))

        dbg_norm = np.sqrt(np.sum(dbg_zm ** 2))
        flux_norm = np.sqrt(np.sum(flux_zm ** 2))
        supply_norm = np.sqrt(np.sum(supply_zm ** 2))
        demand_norm = np.sqrt(np.sum(demand_zm ** 2))

        for i, lag in enumerate(lags):
            if lag >= 0:
                # Shift flux forward (flux leads: flux[t] correlates with dbg[t+lag])
                n_overlap = N - abs(lag)
                if n_overlap < 1000:
                    continue
                xcorr_net[i] = np.sum(flux_zm[:n_overlap] * dbg_zm[lag:lag + n_overlap])
                xcorr_supply[i] = np.sum(supply_zm[:n_overlap] * dbg_zm[lag:lag + n_overlap])
                xcorr_demand[i] = np.sum(demand_zm[:n_overlap] * dbg_zm[lag:lag + n_overlap])
            else:
                # Shift flux backward (flux lags: flux[t-lag] correlates with dbg[t])
                n_overlap = N - abs(lag)
                if n_overlap < 1000:
                    continue
                alag = abs(lag)
                xcorr_net[i] = np.sum(flux_zm[alag:alag + n_overlap] * dbg_zm[:n_overlap])
                xcorr_supply[i] = np.sum(supply_zm[alag:alag + n_overlap] * dbg_zm[:n_overlap])
                xcorr_demand[i] = np.sum(demand_zm[alag:alag + n_overlap] * dbg_zm[:n_overlap])

        # Normalize
        denom_net = max(dbg_norm * flux_norm, 1e-10)
        denom_supply = max(dbg_norm * supply_norm, 1e-10)
        denom_demand = max(dbg_norm * demand_norm, 1e-10)
        xcorr_net /= denom_net
        xcorr_supply /= denom_supply
        xcorr_demand /= denom_demand

        # Find optimal lag (peak correlation)
        best_idx_net = np.argmax(xcorr_net)
        best_lag_net = int(lags[best_idx_net])
        best_corr_net = float(xcorr_net[best_idx_net])

        best_idx_supply = np.argmax(xcorr_supply)
        best_lag_supply = int(lags[best_idx_supply])
        best_corr_supply = float(xcorr_supply[best_idx_supply])

        # For demand, correlation with dBG should be NEGATIVE (more insulin → BG drops)
        best_idx_demand = np.argmin(xcorr_demand)
        best_lag_demand = int(lags[best_idx_demand])
        best_corr_demand = float(xcorr_demand[best_idx_demand])

        # Zero-lag correlation for reference
        zero_idx = np.where(lags == 0)[0][0]
        zero_corr = float(xcorr_net[zero_idx])

        # Build lag profile as list for JSON
        lag_profile = {str(int(l * STEP_MIN)): round(float(c), 4)
                       for l, c in zip(lags, xcorr_net)}

        results[name] = {
            'best_lag_net_min': best_lag_net * STEP_MIN,
            'best_lag_net_steps': best_lag_net,
            'best_corr_net': round(best_corr_net, 4),
            'zero_lag_corr': round(zero_corr, 4),
            'improvement_over_zero': round(best_corr_net - zero_corr, 4),
            'best_lag_supply_min': best_lag_supply * STEP_MIN,
            'best_corr_supply': round(best_corr_supply, 4),
            'best_lag_demand_min': best_lag_demand * STEP_MIN,
            'best_corr_demand': round(best_corr_demand, 4),
            'lag_profile_min': lag_profile,
        }

        if detail:
            r = results[name]
            delta = "+" if r['improvement_over_zero'] > 0 else ""
            print(f"  {name}: best_lag={r['best_lag_net_min']:+d}min "
                  f"corr={r['best_corr_net']:.3f} (zero-lag={r['zero_lag_corr']:.3f}, "
                  f"{delta}{r['improvement_over_zero']:.3f})")
            print(f"       supply_lag={r['best_lag_supply_min']:+d}min "
                  f"demand_lag={r['best_lag_demand_min']:+d}min")

    return results


# ── EXP-522: Lag-Corrected Compression ──────────────────────────────────

def run_exp522(patients, lag_results, detail=False):
    """Recompute R² after shifting flux by per-patient optimal lag.

    Compare R² at: zero lag (EXP-518 baseline), optimal per-patient lag,
    and a fixed population lag (median optimal).
    """
    # Determine population median lag
    opt_lags = [v['best_lag_net_steps'] for v in lag_results.values()
                if 'best_lag_net_steps' in v]
    pop_lag = int(np.median(opt_lags)) if opt_lags else 0

    results = {'population_lag_steps': pop_lag, 'population_lag_min': pop_lag * 5,
               'patients': {}}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        N = len(bg)

        # dBG/dt
        dbg = np.full(N, np.nan)
        dbg[1:-1] = (bg[2:] - bg[:-2]) / 2.0
        dbg[0] = bg[1] - bg[0] if N > 1 else 0
        dbg[-1] = bg[-1] - bg[-2] if N > 1 else 0

        valid = np.isfinite(bg) & np.isfinite(dbg) & np.isfinite(net_flux)
        if valid.sum() < 2000:
            results['patients'][name] = {'error': 'insufficient data'}
            continue

        def compute_r2_at_lag(flux, dbg_arr, valid_mask, lag_steps):
            """Compute R² with flux shifted by lag_steps."""
            n = len(flux)
            if lag_steps == 0:
                mask = valid_mask
                f = flux[mask]
                d = dbg_arr[mask]
            elif lag_steps > 0:
                # Flux leads: flux[t] predicts dbg[t + lag]
                end = n - lag_steps
                mask = valid_mask[:end] & valid_mask[lag_steps:]
                f = flux[:end][mask[:end]]
                d = dbg_arr[lag_steps:][mask[:end]]
            else:
                # Flux lags: flux[t - |lag|] predicts dbg[t]
                alag = abs(lag_steps)
                end = n - alag
                mask = valid_mask[alag:] & valid_mask[:end]
                f = flux[alag:][mask[:end]]
                d = dbg_arr[:end][mask[:end]]

            if len(f) < 1000:
                return None, None, None
            d_var = np.var(d)
            if d_var < 1e-6:
                return None, None, None

            # Linear regression: d = a*f + b
            slope, intercept, r_val, p_val, se = stats.linregress(f, d)
            predicted = slope * f + intercept
            resid_var = np.var(d - predicted)
            r2 = 1.0 - resid_var / d_var
            corr = float(r_val)
            return round(r2, 4), round(corr, 4), len(f)

        # Compute at zero, optimal, and population lags
        pat_lag = lag_results.get(name, {}).get('best_lag_net_steps', 0)

        r2_zero, corr_zero, n_zero = compute_r2_at_lag(net_flux, dbg, valid, 0)
        r2_opt, corr_opt, n_opt = compute_r2_at_lag(net_flux, dbg, valid, pat_lag)
        r2_pop, corr_pop, n_pop = compute_r2_at_lag(net_flux, dbg, valid, pop_lag)

        # Also test a set of fixed lags for comparison
        fixed_lags_min = [0, 5, 10, 15, 20, 30, 45, 60, 90]
        fixed_lag_r2 = {}
        for lag_min in fixed_lags_min:
            lag_steps = lag_min // 5
            r2, corr, n = compute_r2_at_lag(net_flux, dbg, valid, lag_steps)
            if r2 is not None:
                fixed_lag_r2[str(lag_min)] = {'r2': r2, 'corr': corr}

        results['patients'][name] = {
            'zero_lag_r2': r2_zero,
            'optimal_lag_steps': pat_lag,
            'optimal_lag_min': pat_lag * 5,
            'optimal_lag_r2': r2_opt,
            'population_lag_r2': r2_pop,
            'improvement_zero_to_opt': round(r2_opt - r2_zero, 4) if r2_opt and r2_zero else None,
            'improvement_zero_to_pop': round(r2_pop - r2_zero, 4) if r2_pop and r2_zero else None,
            'fixed_lag_r2': fixed_lag_r2,
        }

        if detail:
            r = results['patients'][name]
            imp = r['improvement_zero_to_opt'] or 0
            print(f"  {name}: zero R²={r['zero_lag_r2']:.3f} → opt R²={r['optimal_lag_r2']:.3f} "
                  f"(lag={r['optimal_lag_min']:+d}min, ΔR²={imp:+.3f}) "
                  f"pop R²={r['population_lag_r2']:.3f}")

    return results


# ── EXP-523: Circadian Lag Profile ──────────────────────────────────────

def run_exp523(patients, detail=False):
    """Does the optimal lag vary by time of day?

    Compute cross-correlation in 4 circadian windows:
    - Night (00-06): hepatic dominated, minimal meals
    - Morning (06-12): dawn + breakfast
    - Afternoon (12-18): lunch + post-prandial
    - Evening (18-24): dinner + bedtime

    Different lag structures would indicate different physiological
    processes dominate at different times.
    """
    MAX_LAG_STEPS = 18  # ±90 min
    STEP_MIN = 5
    windows = {
        'night_00_06': (0, 6),
        'morning_06_12': (6, 12),
        'afternoon_12_18': (12, 18),
        'evening_18_24': (18, 24),
    }

    results = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        N = len(bg)

        dbg = np.full(N, np.nan)
        dbg[1:-1] = (bg[2:] - bg[:-2]) / 2.0
        dbg[0] = bg[1] - bg[0] if N > 1 else 0
        dbg[-1] = bg[-1] - bg[-2] if N > 1 else 0

        valid = np.isfinite(bg) & np.isfinite(dbg) & np.isfinite(net_flux)

        hours = df.index.hour if hasattr(df.index, 'hour') else np.zeros(N, dtype=int)

        pat_results = {}
        for wname, (h_start, h_end) in windows.items():
            hour_mask = (hours >= h_start) & (hours < h_end) & valid
            if hour_mask.sum() < 500:
                pat_results[wname] = {'error': 'insufficient data'}
                continue

            # Extract contiguous-ish segments within this time window
            # Use the mask directly for cross-correlation
            flux_w = net_flux.copy()
            flux_w[~hour_mask] = 0
            flux_w[hour_mask] -= flux_w[hour_mask].mean()

            dbg_w = dbg.copy()
            dbg_w[~hour_mask] = 0
            dbg_w[hour_mask] -= dbg_w[hour_mask].mean()

            lags = np.arange(-MAX_LAG_STEPS, MAX_LAG_STEPS + 1)
            xcorr = np.zeros(len(lags))

            for i, lag in enumerate(lags):
                if lag >= 0:
                    n_ov = N - lag
                    xcorr[i] = np.sum(flux_w[:n_ov] * dbg_w[lag:lag + n_ov])
                else:
                    alag = abs(lag)
                    n_ov = N - alag
                    xcorr[i] = np.sum(flux_w[alag:alag + n_ov] * dbg_w[:n_ov])

            denom = max(np.sqrt(np.sum(flux_w ** 2) * np.sum(dbg_w ** 2)), 1e-10)
            xcorr /= denom

            best_idx = np.argmax(xcorr)
            best_lag = int(lags[best_idx])

            pat_results[wname] = {
                'best_lag_min': best_lag * STEP_MIN,
                'best_corr': round(float(xcorr[best_idx]), 4),
                'zero_corr': round(float(xcorr[np.where(lags == 0)[0][0]]), 4),
                'n_points': int(hour_mask.sum()),
            }

        results[name] = pat_results

        if detail:
            parts = []
            for wname in windows:
                if 'error' not in pat_results.get(wname, {}):
                    wr = pat_results[wname]
                    parts.append(f"{wname.split('_')[0]}={wr['best_lag_min']:+d}min"
                                 f"({wr['best_corr']:.2f})")
            print(f"  {name}: " + " | ".join(parts))

    # Population summary: median lag per window
    summary = {}
    for wname in windows:
        lags_w = [v[wname]['best_lag_min']
                  for v in results.values()
                  if isinstance(v.get(wname), dict) and 'best_lag_min' in v[wname]]
        if lags_w:
            summary[wname] = {
                'median_lag_min': int(np.median(lags_w)),
                'mean_lag_min': round(float(np.mean(lags_w)), 1),
                'std_lag_min': round(float(np.std(lags_w)), 1),
                'n_patients': len(lags_w),
            }

    return {'patients': results, 'summary': summary}


# ── EXP-524: TDD-Normalized Cross-Patient Features ─────────────────────

def run_exp524(patients, detail=False):
    """Normalize flux features by Total Daily Dose for cross-patient transfer.

    EXP-503 found r=-0.960 with raw features. TDD normalization should
    make patients more comparable by removing absolute insulin scale.

    TDD = total insulin delivery per day. Patient using 40U/day has 2×
    larger absolute flux values than patient using 20U/day, even with
    identical control. TDD normalization removes this confound.
    """
    features_raw = {}
    features_tdd = {}
    tir_values = {}

    for p in patients:
        df = p['df']
        pk = p.get('pk')
        name = p['name']

        sd = compute_supply_demand(df, pk)
        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(float)
        valid = np.isfinite(bg)

        if valid.sum() < 5000:
            continue

        # Compute TDD from insulin PK channel
        if pk is not None and pk.shape[1] >= 2:
            insulin_total = pk[:, 0] * PK_NORMALIZATION['insulin_total']
            # insulin_total is U/min activity; integrate over a day (288 steps × 5 min)
            daily_activity = []
            for day_start in range(0, len(insulin_total) - 288, 288):
                day_slice = insulin_total[day_start:day_start + 288]
                daily_activity.append(np.sum(np.abs(day_slice)) * 5.0)  # U-min activity
            tdd = float(np.median(daily_activity)) if daily_activity else 1.0
        else:
            tdd = 1.0

        tdd = max(tdd, 0.1)  # safety

        # Compute features (same as EXP-503 but with TDD normalization)
        net = sd['net']
        supply_arr = sd['supply']
        demand_arr = sd['demand']
        residual = np.diff(bg, prepend=bg[0]) - net[:len(bg)]

        # Valid mask must exclude NaN in both BG and flux
        valid_all = valid & np.isfinite(net[:len(bg)]) & np.isfinite(residual)
        bg_valid = bg[valid]
        tir = float(np.mean((bg_valid >= 70) & (bg_valid <= 180)))

        raw_feats = {
            'bg_mean': float(np.nanmean(bg)),
            'bg_std': float(np.nanstd(bg)),
            'tir': tir,
            'flux_mean': float(np.nanmean(np.abs(net))),
            'flux_std': float(np.nanstd(net)),
            'supply_mean': float(np.nanmean(supply_arr)),
            'demand_mean': float(np.nanmean(demand_arr)),
            'resid_mean': float(np.mean(np.abs(residual[valid_all]))),
            'resid_std': float(np.std(residual[valid_all])),
        }

        tdd_feats = {
            'bg_mean': raw_feats['bg_mean'],       # BG doesn't scale with TDD
            'bg_std': raw_feats['bg_std'],
            'tir': tir,
            'flux_mean': raw_feats['flux_mean'] / tdd,
            'flux_std': raw_feats['flux_std'] / tdd,
            'supply_mean': raw_feats['supply_mean'] / tdd,
            'demand_mean': raw_feats['demand_mean'] / tdd,
            'resid_mean': raw_feats['resid_mean'] / tdd,
            'resid_std': raw_feats['resid_std'] / tdd,
        }

        features_raw[name] = raw_feats
        features_tdd[name] = tdd_feats
        tir_values[name] = tir

        if detail:
            print(f"  {name}: TDD≈{tdd:.1f} U-act/day, TIR={tir:.1%}")

    if len(features_raw) < 3:
        return {'error': 'need ≥3 patients'}

    # Find gold standard (highest TIR)
    gold = max(tir_values, key=tir_values.get)

    # Compute distance from gold standard for raw and TDD-normalized
    def feature_distances(feat_dict, gold_name):
        # Z-score normalize all features before computing distances
        all_vecs = np.array([list(feat_dict[n].values()) for n in feat_dict])
        means = all_vecs.mean(axis=0)
        stds = all_vecs.std(axis=0)
        stds[stds < 1e-10] = 1.0

        gold_vec = (np.array(list(feat_dict[gold_name].values())) - means) / stds
        dists = {}
        for name, feats in feat_dict.items():
            if name == gold_name:
                dists[name] = 0.0
                continue
            vec = (np.array(list(feats.values())) - means) / stds
            dists[name] = float(np.sqrt(np.sum((vec - gold_vec) ** 2)))
        return dists

    dists_raw = feature_distances(features_raw, gold)
    dists_tdd = feature_distances(features_tdd, gold)

    # Correlate distance with TIR
    names = [n for n in features_raw if n != gold]
    tir_arr = np.array([tir_values[n] for n in names])
    dist_raw_arr = np.array([dists_raw[n] for n in names])
    dist_tdd_arr = np.array([dists_tdd[n] for n in names])

    if len(names) >= 3:
        corr_raw, pval_raw = stats.spearmanr(dist_raw_arr, tir_arr)
        corr_tdd, pval_tdd = stats.spearmanr(dist_tdd_arr, tir_arr)
        corr_raw = float(corr_raw) if np.isfinite(corr_raw) else None
        corr_tdd = float(corr_tdd) if np.isfinite(corr_tdd) else None
        pval_raw = float(pval_raw) if np.isfinite(pval_raw) else None
        pval_tdd = float(pval_tdd) if np.isfinite(pval_tdd) else None
    else:
        corr_raw = corr_tdd = pval_raw = pval_tdd = None

    results = {
        'gold_standard': gold,
        'n_patients': len(features_raw),
        'raw_correlation': round(corr_raw, 4) if corr_raw is not None else None,
        'raw_pvalue': round(pval_raw, 6) if pval_raw is not None else None,
        'tdd_correlation': round(corr_tdd, 4) if corr_tdd is not None else None,
        'tdd_pvalue': round(pval_tdd, 6) if pval_tdd is not None else None,
        'improvement': round(abs(corr_tdd) - abs(corr_raw), 4) if corr_raw is not None and corr_tdd is not None else None,
        'per_patient': {},
    }

    for name in features_raw:
        results['per_patient'][name] = {
            'tir': round(tir_values[name], 3),
            'dist_raw': round(dists_raw[name], 3),
            'dist_tdd': round(dists_tdd[name], 3),
        }

    if detail:
        print(f"\n  Gold standard: {gold} (TIR={tir_values[gold]:.1%})")
        if corr_raw is not None:
            print(f"  Raw distance↔TIR:  r={corr_raw:.3f} p={pval_raw:.4f}")
        if corr_tdd is not None:
            print(f"  TDD distance↔TIR:  r={corr_tdd:.3f} p={pval_tdd:.4f}")
        if results['improvement'] is not None:
            print(f"  Improvement: Δ|r|={results['improvement']:+.4f}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-521/522/523/524: Temporal alignment and normalization')
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

    print("\n═══ EXP-521: Lead/Lag Cross-Correlation ═══")
    r521 = run_exp521(patients, detail=args.detail)
    all_results['exp521_leadlag'] = r521

    print("\n═══ EXP-522: Lag-Corrected Compression ═══")
    r522 = run_exp522(patients, r521, detail=args.detail)
    all_results['exp522_lag_corrected'] = r522

    print("\n═══ EXP-523: Circadian Lag Profile ═══")
    r523 = run_exp523(patients, detail=args.detail)
    all_results['exp523_circadian_lag'] = r523

    print("\n═══ EXP-524: TDD-Normalized Cross-Patient ═══")
    r524 = run_exp524(patients, detail=args.detail)
    all_results['exp524_tdd_normalized'] = r524

    # Summary
    if r521:
        lag_mins = [v['best_lag_net_min'] for v in r521.values() if 'best_lag_net_min' in v]
        if lag_mins:
            print(f"\n  Population lag: median={int(np.median(lag_mins))}min, "
                  f"mean={np.mean(lag_mins):.0f}min, range={min(lag_mins)}..{max(lag_mins)}")

    if r522.get('patients'):
        improvements = [v['improvement_zero_to_opt']
                       for v in r522['patients'].values()
                       if isinstance(v.get('improvement_zero_to_opt'), (int, float))]
        if improvements:
            print(f"  Lag correction: mean ΔR²={np.mean(improvements):+.3f}")

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
