#!/usr/bin/env python3
"""EXP-511/514/518: Residual Clustering, Meal Response Typing, Compression Ratio.

EXP-511: Cluster residual time series into interpretable categories.
         Can we identify distinct "modes" of unexplained glucose behavior?

EXP-514: Cluster meals by absorption profile (fast, slow, biphasic).
         Different meal types produce characteristic demand curves.

EXP-518: Treat flux decomposition as lossy compression of the BG signal.
         How much of BG variability is captured by supply-demand alone?

References:
  - exp_metabolic_441.py: compute_supply_demand()
  - exp_transfer_503.py: _compute_patient_features()
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_metabolic_flux import load_patients

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'


# ── EXP-511: Residual Clustering ────────────────────────────────────────

def run_exp511(patients, detail=False):
    """Cluster residual patterns into interpretable categories.

    Extract 4-hour residual windows and cluster them. Categories might include:
    - Flat (well-modeled period)
    - Rising (unmodeled glucose production — dawn, stress, rebound)
    - Falling (unmodeled glucose uptake — exercise, over-correction)
    - Oscillating (sensor noise, rapid changes)
    - Spike (meal mismatch, delayed absorption)
    """
    all_window_features = []
    window_labels = []

    for p in patients:
        df = p['df']
        pk = p['pk']
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

        # Extract 4-hour non-overlapping windows (48 steps)
        window_size = 48
        for i in range(0, N - window_size, window_size):
            w = residual[i:i + window_size]
            v = valid[i:i + window_size]
            if v.sum() < window_size * 0.8:
                continue

            # Feature vector for this window
            w_clean = np.where(v, w, 0)
            features = {
                'mean': float(np.mean(w_clean)),
                'std': float(np.std(w_clean)),
                'slope': float(np.polyfit(np.arange(len(w_clean)), w_clean, 1)[0]),
                'max_abs': float(np.max(np.abs(w_clean))),
                'zero_crossings': int(np.sum(np.diff(np.sign(w_clean)) != 0)),
                'skew': float(stats.skew(w_clean)),
                'energy': float(np.sum(w_clean ** 2)),
                'hour': int(hours[i]),
            }
            all_window_features.append(features)
            window_labels.append(p['name'])

    if len(all_window_features) < 100:
        return {'error': 'insufficient windows'}

    # Build feature matrix
    feature_keys = ['mean', 'std', 'slope', 'max_abs', 'zero_crossings', 'skew', 'energy']
    X = np.array([[f[k] for k in feature_keys] for f in all_window_features])

    # Normalize features
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0) + 1e-6
    X_norm = (X - X_mean) / X_std

    # Hierarchical clustering into 5 categories
    linkage_matrix = linkage(X_norm, method='ward')
    clusters = fcluster(linkage_matrix, t=5, criterion='maxclust')

    # Characterize each cluster
    cluster_profiles = {}
    for c in range(1, 6):
        mask = clusters == c
        n = mask.sum()
        if n < 10:
            continue

        c_features = X[mask]
        c_hours = [all_window_features[i]['hour'] for i in range(len(mask)) if mask[i]]
        c_patients = [window_labels[i] for i in range(len(mask)) if mask[i]]

        # Dominant characteristics
        mean_mean = float(np.mean(c_features[:, 0]))
        mean_std = float(np.mean(c_features[:, 1]))
        mean_slope = float(np.mean(c_features[:, 2]))

        # Name the cluster based on characteristics
        if abs(mean_mean) < 1 and mean_std < 3:
            name = 'flat'
        elif mean_slope > 0.05:
            name = 'rising'
        elif mean_slope < -0.05:
            name = 'falling'
        elif mean_std > 5:
            name = 'volatile'
        else:
            name = 'moderate'

        # Hour distribution
        hour_buckets = {}
        for h in c_hours:
            b = f"{(h // 6) * 6:02d}-{((h // 6) + 1) * 6:02d}"
            hour_buckets[b] = hour_buckets.get(b, 0) + 1

        # Patient distribution
        patient_counts = {}
        for pat in c_patients:
            patient_counts[pat] = patient_counts.get(pat, 0) + 1

        cluster_profiles[f'cluster_{c}'] = {
            'name': name,
            'n_windows': int(n),
            'pct': round(n / len(clusters) * 100, 1),
            'mean_residual': round(mean_mean, 2),
            'mean_std': round(mean_std, 2),
            'mean_slope': round(mean_slope, 4),
            'hour_distribution': hour_buckets,
            'top_patients': dict(sorted(patient_counts.items(),
                                        key=lambda x: -x[1])[:5]),
        }

    results = {
        'n_windows': len(all_window_features),
        'n_clusters': len(cluster_profiles),
        'clusters': cluster_profiles,
    }

    if detail:
        for cname, cdata in sorted(cluster_profiles.items()):
            top_p = ', '.join(f"{k}:{v}" for k, v in list(cdata['top_patients'].items())[:3])
            print(f"  {cname} ({cdata['name']}): {cdata['pct']:.0f}% "
                  f"mean={cdata['mean_residual']:+.1f} std={cdata['mean_std']:.1f} "
                  f"slope={cdata['mean_slope']:+.3f} [{top_p}]")

    return results


# ── EXP-514: Meal Response Typing ───────────────────────────────────────

def run_exp514(patients, detail=False):
    """Classify meals by their demand/excursion profile.

    Types:
    - Fast: sharp demand spike, quick peak (<90 min), clean return
    - Slow: gradual demand rise, late peak (>120 min), extended tail
    - Biphasic: two demand peaks (initial carb + delayed fat/protein)
    - Flat: demand without BG response (well-covered meal)
    """
    all_meals = []

    for p in patients:
        df = p['df']
        pk = p['pk']
        sd = compute_supply_demand(df, pk)

        bg_col = 'glucose' if 'glucose' in df.columns else 'sgv'
        bg = df[bg_col].values.astype(np.float64)
        valid = ~np.isnan(bg)
        N = len(df)

        demand = sd['demand']
        demand_smooth = pd.Series(demand).rolling(6, center=True, min_periods=1).mean().values

        pos_demand = demand_smooth[demand_smooth > 0.01]
        if len(pos_demand) < 100:
            continue

        meal_thresh = float(np.percentile(pos_demand, 80))

        i = 0
        while i < N - 60:  # need 5h window
            if demand_smooth[i] > meal_thresh and valid[i]:
                # Extract 5h demand and BG profiles
                d_profile = demand[i:i + 60]
                bg_profile = bg[i:i + 60]
                bg_valid = ~np.isnan(bg_profile)

                if bg_valid.sum() < 40:
                    i += 12
                    continue

                bg_start = bg[i]
                if np.isnan(bg_start):
                    i += 6
                    continue

                # Profile features
                # Time to demand peak (within 3h)
                d_3h = d_profile[:36]
                peak_idx = int(np.argmax(d_3h))
                time_to_peak_min = peak_idx * 5

                # BG excursion (peak in 3h)
                bg_3h = bg_profile[:36]
                bg_peak = float(np.nanmax(bg_3h))
                excursion = bg_peak - bg_start

                # Time to BG peak
                bg_3h_filled = np.where(~np.isnan(bg_3h), bg_3h, -999)
                bg_peak_idx = int(np.argmax(bg_3h_filled))
                bg_peak_time_min = bg_peak_idx * 5

                # Late demand ratio (3-5h / 0-3h)
                early_demand = float(np.sum(d_profile[:36]))
                late_demand = float(np.sum(d_profile[36:]))
                tail_ratio = late_demand / (early_demand + 1e-6)

                # Biphasic: look for second peak after trough
                has_second_peak = False
                if len(d_profile) > 36:
                    d_late = d_profile[24:]  # after 2h
                    if len(d_late) > 12:
                        late_peaks = d_late > meal_thresh * 0.5
                        # Find runs of high demand
                        if np.sum(late_peaks) > 6:
                            has_second_peak = True

                # Classify
                if excursion < 20:
                    meal_type = 'flat'
                elif bg_peak_time_min < 60 and tail_ratio < 0.2:
                    meal_type = 'fast'
                elif has_second_peak:
                    meal_type = 'biphasic'
                elif bg_peak_time_min > 90 or tail_ratio > 0.4:
                    meal_type = 'slow'
                else:
                    meal_type = 'moderate'

                all_meals.append({
                    'patient': p['name'],
                    'type': meal_type,
                    'excursion': round(excursion, 1),
                    'time_to_peak': bg_peak_time_min,
                    'tail_ratio': round(tail_ratio, 3),
                    'demand_peak_min': time_to_peak_min,
                })
                i += 36
            else:
                i += 1

    if len(all_meals) < 50:
        return {'error': 'insufficient meals'}

    # Aggregate by type
    type_counts = {}
    type_stats = {}
    for t in ['fast', 'moderate', 'slow', 'biphasic', 'flat']:
        meals_of_type = [m for m in all_meals if m['type'] == t]
        n = len(meals_of_type)
        if n < 5:
            continue

        type_counts[t] = n
        excursions = [m['excursion'] for m in meals_of_type]
        peak_times = [m['time_to_peak'] for m in meals_of_type]
        tails = [m['tail_ratio'] for m in meals_of_type]

        # Per-patient breakdown
        patient_counts = {}
        for m in meals_of_type:
            patient_counts[m['patient']] = patient_counts.get(m['patient'], 0) + 1

        type_stats[t] = {
            'count': n,
            'pct': round(n / len(all_meals) * 100, 1),
            'median_excursion': round(float(np.median(excursions)), 1),
            'median_peak_time': round(float(np.median(peak_times)), 0),
            'median_tail': round(float(np.median(tails)), 3),
            'patient_distribution': dict(sorted(patient_counts.items(),
                                                key=lambda x: -x[1])[:5]),
        }

    results = {
        'n_meals': len(all_meals),
        'type_distribution': type_counts,
        'type_stats': type_stats,
    }

    if detail:
        for t, s in sorted(type_stats.items(), key=lambda x: -x[1]['count']):
            top_p = ', '.join(f"{k}:{v}" for k, v in list(s['patient_distribution'].items())[:3])
            print(f"  {t}: {s['pct']:.0f}% ({s['count']}) "
                  f"exc={s['median_excursion']:+.0f} peak={s['median_peak_time']:.0f}min "
                  f"tail={s['median_tail']:.3f} [{top_p}]")

    return results


# ── EXP-518: Compression Ratio ──────────────────────────────────────────

def run_exp518(patients, detail=False):
    """Measure how much of BG variability the flux decomposition captures.

    Treat (supply, demand) as a compressed representation of dBG/dt.
    Compression ratio = var(residual) / var(dBG) — lower is better.
    R² = 1 - var(residual)/var(dBG) — higher is better.
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

        net_flux = sd['supply'] - sd['demand']
        dbg = np.zeros_like(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
        residual = dbg - net_flux

        # Only compute where we have valid BG
        mask = valid & (np.arange(N) > 0)
        if mask.sum() < 1000:
            results[p['name']] = {'error': 'insufficient data'}
            continue

        dbg_var = float(np.var(dbg[mask]))
        resid_var = float(np.var(residual[mask]))
        flux_var = float(np.var(net_flux[mask]))

        if dbg_var < 1e-6:
            results[p['name']] = {'error': 'zero BG variance'}
            continue

        # R² of flux as predictor of dBG
        r_squared = 1.0 - resid_var / dbg_var
        compression = resid_var / dbg_var  # lower = better compression

        # Correlation
        corr, pval = stats.pearsonr(net_flux[mask], dbg[mask])

        # Per-hour R² (circadian variation in model quality)
        hours = df.index.hour if hasattr(df.index, 'hour') else np.zeros(N)
        hourly_r2 = {}
        for h in range(24):
            h_mask = mask & (hours == h)
            if h_mask.sum() < 100:
                continue
            h_dbg_var = float(np.var(dbg[h_mask]))
            h_resid_var = float(np.var(residual[h_mask]))
            if h_dbg_var > 1e-6:
                hourly_r2[str(h)] = round(1.0 - h_resid_var / h_dbg_var, 3)

        # Signal-to-noise ratio
        snr = flux_var / (resid_var + 1e-6)

        results[p['name']] = {
            'r_squared': round(r_squared, 4),
            'compression_ratio': round(compression, 4),
            'correlation': round(float(corr), 4),
            'snr': round(snr, 3),
            'dbg_std': round(float(np.sqrt(dbg_var)), 2),
            'resid_std': round(float(np.sqrt(resid_var)), 2),
            'flux_std': round(float(np.sqrt(flux_var)), 2),
            'hourly_r2': hourly_r2,
        }

        if detail:
            r = results[p['name']]
            quality = '✓' if r['r_squared'] > 0.1 else '~' if r['r_squared'] > 0 else '✗'
            print(f"  {p['name']}: R²={r['r_squared']:.3f} corr={r['correlation']:.3f} "
                  f"SNR={r['snr']:.2f} "
                  f"dBG_std={r['dbg_std']:.1f} resid_std={r['resid_std']:.1f} "
                  f"flux_std={r['flux_std']:.1f} {quality}")

    return results


# ── Main Runner ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-511/514/518: Residual clustering, meal typing, compression')
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

    print("\n═══ EXP-511: Residual Clustering ═══")
    r511 = run_exp511(patients, detail=args.detail)
    all_results['exp511_residual_clusters'] = r511

    print("\n═══ EXP-514: Meal Response Typing ═══")
    r514 = run_exp514(patients, detail=args.detail)
    all_results['exp514_meal_types'] = r514

    print("\n═══ EXP-518: Compression Ratio (Flux as BG Predictor) ═══")
    r518 = run_exp518(patients, detail=args.detail)
    all_results['exp518_compression'] = r518

    # Summary stats
    r2_values = [v['r_squared'] for v in r518.values() if 'r_squared' in v]
    if r2_values:
        print(f"\n  Mean R²: {np.mean(r2_values):.3f} "
              f"(range {min(r2_values):.3f} to {max(r2_values):.3f})")

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
