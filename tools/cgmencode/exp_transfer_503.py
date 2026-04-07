#!/usr/bin/env python3
"""EXP-503/504/510: Cross-Patient Transfer, Multi-Week Aggregation, Production Scoring.

EXP-503: Do metabolic flux features from gold-standard patients (k) transfer
         to similar patients? Can we identify who would benefit from settings
         adjustments based on distance from gold-standard feature distributions?

EXP-504: Multi-week aggregation — do rolling 4-week averages of fidelity
         scores correlate with clinical markers (TIR, estimated A1C)?

EXP-510: Hepatic production model scoring — does the modeled hepatic glucose
         production track overnight BG trends? Can we score model accuracy?

References:
  - exp_settings_489.py: Fidelity scoring components
  - exp_fidelity_495.py: Weekly fidelity trends
  - exp_metabolic_441.py: compute_supply_demand()
  - continuous_pk.py: expand_schedule(), hepatic production model
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


# ── EXP-503: Cross-Patient Transfer ────────────────────────────────────

def _compute_patient_features(df, pk, sd=None):
    """Compute a feature vector summarizing a patient's metabolic profile."""
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

    hours = df.index.hour if hasattr(df.index, 'hour') else np.zeros(N)

    # Feature set: metabolic signatures
    features = {}

    # 1. Basic BG stats
    bg_valid = bg[valid]
    features['bg_mean'] = float(np.mean(bg_valid))
    features['bg_std'] = float(np.std(bg_valid))
    features['tir'] = float(np.mean((bg_valid >= 70) & (bg_valid <= 180)))
    features['time_below'] = float(np.mean(bg_valid < 70))
    features['time_above'] = float(np.mean(bg_valid > 180))

    # 2. Flux statistics
    features['flux_mean'] = float(np.mean(net_flux))
    features['flux_std'] = float(np.std(net_flux))
    features['flux_abs_mean'] = float(np.mean(np.abs(net_flux)))

    # 3. Residual statistics
    features['resid_mean'] = float(np.mean(residual))
    features['resid_std'] = float(np.std(residual))
    features['resid_mae'] = float(np.mean(np.abs(residual)))
    features['resid_skew'] = float(stats.skew(residual[~np.isnan(residual)]))

    # 4. Supply/demand balance
    features['supply_mean'] = float(np.mean(sd['supply']))
    features['demand_mean'] = float(np.mean(sd['demand']))
    features['balance_ratio'] = features['supply_mean'] / (features['demand_mean'] + 1e-6)

    # 5. Overnight stability (0-5 AM)
    overnight = (hours >= 0) & (hours < 5) & valid
    if overnight.sum() > 100:
        features['overnight_std'] = float(np.std(bg[overnight]))
        features['overnight_mean'] = float(np.mean(bg[overnight]))
    else:
        features['overnight_std'] = features['bg_std']
        features['overnight_mean'] = features['bg_mean']

    # 6. Circadian amplitude (daytime mean - nighttime mean)
    day = (hours >= 8) & (hours < 20) & valid
    night = ((hours >= 0) & (hours < 6)) & valid
    if day.sum() > 100 and night.sum() > 100:
        features['circadian_amp'] = float(np.mean(bg[day]) - np.mean(bg[night]))
    else:
        features['circadian_amp'] = 0.0

    # 7. Autocorrelation structure of residual
    r = residual[~np.isnan(residual)]
    if len(r) > 60:
        acf_30 = float(np.corrcoef(r[:-6], r[6:])[0, 1])
        features['resid_acf30'] = acf_30
    else:
        features['resid_acf30'] = 0.0

    return features


def run_exp503(patients, detail=False):
    """Cross-patient feature transfer analysis.

    Computes metabolic feature vectors for all patients, measures distance
    from gold-standard (patient k), and tests whether proximity predicts
    glycemic outcomes.
    """
    # First compute all feature vectors
    patient_features = {}
    for p in patients:
        features = _compute_patient_features(p['df'], p['pk'])
        patient_features[p['name']] = features

    # Identify gold standard (highest TIR with lowest time_below)
    best_name = max(patient_features.keys(),
                    key=lambda n: patient_features[n]['tir'] - patient_features[n]['time_below'])

    gold = patient_features[best_name]

    # Compute distances from gold standard
    feature_keys = sorted(gold.keys())
    distances = {}

    for name, feats in patient_features.items():
        # Normalized Euclidean distance (each feature scaled by gold-standard value)
        dist_components = {}
        for k in feature_keys:
            gv = gold[k]
            pv = feats[k]
            scale = abs(gv) + 1e-6
            dist_components[k] = ((pv - gv) / scale) ** 2

        total_dist = float(np.sqrt(sum(dist_components.values())))

        # Which features diverge most?
        top_divergent = sorted(dist_components.items(), key=lambda x: -x[1])[:5]

        distances[name] = {
            'total_distance': round(total_dist, 2),
            'features': {k: round(v, 2) for k, v in feats.items()},
            'top_divergent': {k: round(v, 2) for k, v in top_divergent},
            'tir': round(feats['tir'] * 100, 1),
            'bg_mean': round(feats['bg_mean'], 1),
        }

    # Test: does distance from gold-standard predict TIR?
    dists = [distances[n]['total_distance'] for n in distances if n != best_name]
    tirs = [distances[n]['tir'] for n in distances if n != best_name]

    if len(dists) >= 5:
        corr, pval = stats.pearsonr(dists, tirs)
    else:
        corr, pval = 0, 1

    results = {
        'gold_standard': best_name,
        'distance_tir_correlation': round(float(corr), 3),
        'distance_tir_pvalue': round(float(pval), 4),
        'patients': distances,
    }

    if detail:
        print(f"  Gold standard: {best_name} (TIR={distances[best_name]['tir']:.0f}%)")
        print(f"  Distance-TIR correlation: r={corr:.3f}, p={pval:.4f}")
        print()
        ranked = sorted(distances.items(), key=lambda x: x[1]['total_distance'])
        for name, d in ranked:
            marker = '★' if name == best_name else ' '
            divs = ', '.join(f"{k}" for k in list(d['top_divergent'].keys())[:3])
            print(f"  {marker} {name}: dist={d['total_distance']:5.2f} "
                  f"TIR={d['tir']:4.0f}% BG={d['bg_mean']:5.0f} "
                  f"divergent=[{divs}]")

    return results


# ── EXP-504: Multi-Week Aggregation ─────────────────────────────────────

def run_exp504(patients, detail=False):
    """Test if 4-week rolling fidelity averages predict clinical markers.

    Computes rolling 4-week TIR, estimated A1C, and fidelity components.
    Tests correlation between metabolic fidelity and clinical outcomes.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        if not hasattr(df.index, 'date'):
            continue

        dates = df.index.date
        unique_dates = sorted(set(dates))

        if len(unique_dates) < 28:
            results[p['name']] = {'error': 'insufficient data'}
            continue

        # Compute daily metrics
        daily = []
        for d in unique_dates:
            mask = dates == d
            idx = np.where(mask)[0]
            bg_day = bg[idx]
            v = ~np.isnan(bg_day)
            if v.sum() < 200:  # need ≥70% of 288 points
                continue

            bgv = bg_day[v]
            tir = float(np.mean((bgv >= 70) & (bgv <= 180)))
            mean_bg = float(np.mean(bgv))
            gmi = (28.7 + 46.7 * (mean_bg / 18.0182)) / 10.929  # estimated A1C from GMI formula
            cv = float(np.std(bgv) / np.mean(bgv))

            daily.append({
                'date': d,
                'tir': tir,
                'mean_bg': mean_bg,
                'gmi': gmi,
                'cv': cv,
            })

        if len(daily) < 28:
            results[p['name']] = {'error': 'insufficient valid days'}
            continue

        # Rolling 4-week windows (28 days)
        windows = []
        for i in range(len(daily) - 27):
            window = daily[i:i + 28]
            tirs = [d['tir'] for d in window]
            gmis = [d['gmi'] for d in window]
            mean_bgs = [d['mean_bg'] for d in window]
            cvs = [d['cv'] for d in window]

            windows.append({
                'start': str(window[0]['date']),
                'end': str(window[-1]['date']),
                'tir_mean': round(float(np.mean(tirs)) * 100, 1),
                'gmi_mean': round(float(np.mean(gmis)), 2),
                'bg_mean': round(float(np.mean(mean_bgs)), 1),
                'cv_mean': round(float(np.mean(cvs)), 3),
            })

        if not windows:
            results[p['name']] = {'error': 'no complete windows'}
            continue

        # Overall patient summary
        all_tirs = [w['tir_mean'] for w in windows]
        all_gmis = [w['gmi_mean'] for w in windows]

        # Trend in GMI over the observation period
        x = np.arange(len(all_gmis))
        if len(x) >= 10:
            slope, intercept, r, pval, se = stats.linregress(x, all_gmis)
            gmi_trend = 'improving' if slope < -0.005 and pval < 0.1 else \
                        ('worsening' if slope > 0.005 and pval < 0.1 else 'stable')
        else:
            slope = pval = 0
            gmi_trend = 'insufficient'

        results[p['name']] = {
            'n_windows': len(windows),
            'tir_range': [round(min(all_tirs), 1), round(max(all_tirs), 1)],
            'gmi_range': [round(min(all_gmis), 2), round(max(all_gmis), 2)],
            'gmi_mean': round(float(np.mean(all_gmis)), 2),
            'gmi_trend_slope': round(float(slope), 4),
            'gmi_trend_pvalue': round(float(pval), 4),
            'gmi_trend': gmi_trend,
            'tir_mean': round(float(np.mean(all_tirs)), 1),
            'windows': windows[:5] + windows[-5:] if len(windows) > 10 else windows,
        }

        if detail:
            r = results[p['name']]
            trend_sym = {'improving': '↓', 'worsening': '↑', 'stable': '→', 'insufficient': '?'}[r['gmi_trend']]
            print(f"  {p['name']}: GMI={r['gmi_mean']:.1f}% TIR={r['tir_mean']:.0f}% "
                  f"[{r['tir_range'][0]:.0f}-{r['tir_range'][1]:.0f}%] "
                  f"trend={r['gmi_trend']} {trend_sym} (slope={r['gmi_trend_slope']:+.4f})")

    return results


# ── EXP-510: Hepatic Production Scoring ─────────────────────────────────

def run_exp510(patients, detail=False):
    """Score hepatic glucose production model against overnight BG trends.

    Theory: During 0-5 AM fasting, glucose changes should be primarily driven
    by basal insulin vs hepatic glucose production. If our hepatic model is
    accurate, the overnight supply-demand balance should predict BG drift.

    Metric: correlation between modeled supply-demand balance and observed
    dBG/dt during overnight fasting windows.
    """
    results = {}
    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        if not hasattr(df.index, 'hour'):
            continue

        hours = df.index.hour
        net_flux = sd['supply'] - sd['demand']

        # Observed dBG/dt
        dbg = np.zeros_like(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)

        # Overnight windows (0-5 AM, no carbs)
        overnight = (hours >= 0) & (hours < 5)
        carb_rate = pk[:, 3] if pk is not None and pk.shape[1] > 3 else np.zeros(N)
        no_carbs = carb_rate < 0.01  # no carb absorption

        mask = overnight & valid & no_carbs
        mask[0] = False  # skip first point (no dbg)

        if mask.sum() < 500:
            results[p['name']] = {'error': 'insufficient overnight data'}
            continue

        # Correlation: modeled net_flux vs observed dBG/dt
        flux_overnight = net_flux[mask]
        dbg_overnight = dbg[mask]

        # Remove NaN/inf
        finite = np.isfinite(flux_overnight) & np.isfinite(dbg_overnight)
        if finite.sum() < 100:
            results[p['name']] = {'error': 'insufficient finite overnight data'}
            continue

        corr, pval = stats.pearsonr(flux_overnight[finite], dbg_overnight[finite])

        # RMSE of modeled vs observed
        rmse = float(np.sqrt(np.mean((flux_overnight[finite] - dbg_overnight[finite]) ** 2)))

        # Bias: systematic over/under-prediction
        bias = float(np.mean(flux_overnight[finite] - dbg_overnight[finite]))

        # Hourly breakdown
        hour_stats = {}
        for h in range(0, 5):
            h_mask = mask & (hours == h)
            if h_mask.sum() < 50:
                continue
            flux_h = net_flux[h_mask]
            dbg_h = dbg[h_mask]
            fin = np.isfinite(flux_h) & np.isfinite(dbg_h)
            if fin.sum() < 30:
                continue
            h_corr, _ = stats.pearsonr(flux_h[fin], dbg_h[fin])
            h_bias = float(np.mean(flux_h[fin] - dbg_h[fin]))
            hour_stats[f'h{h}'] = {
                'correlation': round(float(h_corr), 3),
                'bias': round(h_bias, 3),
                'n_points': int(fin.sum()),
            }

        # Model quality assessment
        if corr > 0.3:
            quality = 'good'
        elif corr > 0.1:
            quality = 'moderate'
        else:
            quality = 'poor'

        results[p['name']] = {
            'correlation': round(float(corr), 3),
            'pvalue': round(float(pval), 6),
            'rmse': round(rmse, 3),
            'bias': round(bias, 3),
            'quality': quality,
            'n_points': int(finite.sum()),
            'hourly': hour_stats,
        }

        if detail:
            r = results[p['name']]
            sym = {'good': '✓', 'moderate': '~', 'poor': '✗'}[r['quality']]
            print(f"  {p['name']}: corr={r['correlation']:+.3f} rmse={r['rmse']:.3f} "
                  f"bias={r['bias']:+.3f} [{r['quality']}] {sym} "
                  f"({r['n_points']} overnight points)")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-503/504/510: Cross-patient, multi-week, production scoring')
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

    print("\n═══ EXP-503: Cross-Patient Feature Transfer ═══")
    r503 = run_exp503(patients, detail=args.detail)
    all_results['exp503_cross_patient'] = r503

    print("\n═══ EXP-504: Multi-Week Aggregation (GMI/TIR Trends) ═══")
    r504 = run_exp504(patients, detail=args.detail)
    all_results['exp504_multiweek'] = r504
    for direction in ['improving', 'stable', 'worsening']:
        n = sum(1 for v in r504.values() if v.get('gmi_trend') == direction)
        if n:
            print(f"  GMI {direction}: {n} patients")

    print("\n═══ EXP-510: Hepatic Production Model Scoring ═══")
    r510 = run_exp510(patients, detail=args.detail)
    all_results['exp510_production_scoring'] = r510
    for q in ['good', 'moderate', 'poor']:
        n = sum(1 for v in r510.values() if v.get('quality') == q)
        if n:
            print(f"  {q}: {n} patients")

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
