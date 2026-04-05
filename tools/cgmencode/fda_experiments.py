#!/usr/bin/env python3
"""
fda_experiments.py — FDA experiment runners (EXP-328–341).

Registered in run_pattern_experiments.py EXPERIMENTS dict.
Each function follows the standard experiment pattern:
  1. Load data via load_multiscale_data / resolve_patient_paths
  2. Compute FDA features
  3. Evaluate against baselines
  4. Save results JSON to externals/experiments/

Usage:
    python3 -m tools.cgmencode.run_pattern_experiments fda-bootstrap
    python3 -m tools.cgmencode.run_pattern_experiments fpca-variance
"""

import json
import os
import time
import numpy as np


# ── EXP-328: FDA Toolchain Bootstrap ──────────────────────────────────

def run_fda_bootstrap(args):
    """EXP-328: FDA Toolchain Bootstrap.

    Hypothesis: scikit-fda can produce B-spline representations and FPCA
    decompositions from our existing 5-min CGM grids without data loss.

    Success Criteria:
      - B-spline round-trip error < 0.5 mg/dL at 5-min resolution
      - FPCA captures ≥90% variance with K ≤ 8 components (daily scale)
      - All FDA methods produce valid outputs
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, load_multiscale_data, save_results,
        SCALE_CONFIG,
    )
    from .fda_features import validate_fda_toolchain

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-328: FDA Toolchain Bootstrap")
    print("=" * 60)

    results = {
        'experiment': 'EXP-328',
        'name': 'fda-bootstrap',
        'method': 'Validate scikit-fda toolchain on existing CGM grids',
        'hypothesis': ('scikit-fda B-spline round-trip < 2 mg/dL interp '
                       'and FPCA 90% variance with K ≤ 8'),
        'fda_config': {
            'library': 'scikit-fda',
            'bspline_order': 4,
        },
        'scales': {},
    }

    all_pass = True
    for scale in ['fast', 'episode', 'daily', 'weekly']:
        print(f"\n{'─' * 40}")
        print(f"Scale: {scale} (window={SCALE_CONFIG[scale]['window']} @ "
              f"{SCALE_CONFIG[scale]['interval_min']}min)")
        print(f"{'─' * 40}")

        try:
            t0 = time.time()
            train, val = load_multiscale_data(patient_paths, scale=scale)
            load_time = time.time() - t0

            # Use a subsample for bootstrap (full dataset not needed)
            max_samples = min(2000, train.shape[0])
            subset = train[:max_samples]

            t0 = time.time()
            scale_results = validate_fda_toolchain(subset, scale_name=scale)
            fda_time = time.time() - t0

            scale_results['n_train'] = int(train.shape[0])
            scale_results['n_val'] = int(val.shape[0])
            scale_results['window_shape'] = list(train.shape[1:])
            scale_results['load_time_s'] = round(load_time, 2)
            scale_results['fda_time_s'] = round(fda_time, 2)

            results['scales'][scale] = scale_results
            if not scale_results['all_pass']:
                all_pass = False

        except Exception as e:
            print(f"  ERROR: {e}")
            results['scales'][scale] = {'error': str(e), 'all_pass': False}
            all_pass = False

    results['all_pass'] = all_pass
    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    print(f"\n{'=' * 60}")
    print(f"EXP-328 Result: {'✓ ALL SCALES PASS' if all_pass else '✗ SOME FAILED'}")
    print(f"{'=' * 60}")

    save_results(results, os.path.join(output_dir, 'exp328_fda_bootstrap.json'))
    return results


# ── EXP-329: FPCA Variance Structure Across Scales ───────────────────

def run_fpca_variance(args):
    """EXP-329: FPCA Variance Structure Across Scales.

    Hypothesis: FPCA eigenvalue decay rates differ by timescale, revealing
    which scales have the richest functional structure.

    Success Criteria:
      - Identify which scale achieves 95% variance with fewest components
      - PC1-3 are interpretable
      - Per-patient vs pooled variance gap < 15%
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, load_multiscale_data, save_results,
        SCALE_CONFIG, _get_cached_grid, _grid_to_features, _split_windows,
    )
    from .real_data_adapter import downsample_grid
    from .fda_features import fpca_variance_explained, fpca_scores

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-329: FPCA Variance Structure Across Scales")
    print("=" * 60)

    results = {
        'experiment': 'EXP-329',
        'name': 'fpca-variance-structure',
        'method': 'FPCA eigenvalue analysis across timescales',
        'fda_config': {
            'max_components': 20,
            'smooth_first': True,
        },
        'scales': {},
        'per_patient': {},
    }

    for scale in ['fast', 'episode', 'daily', 'weekly']:
        cfg = SCALE_CONFIG[scale]
        print(f"\n{'─' * 40}")
        print(f"Scale: {scale}")

        try:
            train, val = load_multiscale_data(patient_paths, scale=scale)
            glucose = train[:, :, 0]  # channel 0

            # Pooled FPCA
            max_k = min(20, glucose.shape[0] - 1, glucose.shape[1] - 1)
            n_knots = max(4, glucose.shape[1] // 6)
            var_info = fpca_variance_explained(
                glucose, max_components=max_k, n_knots=n_knots
            )
            var_info['n_train'] = int(train.shape[0])
            var_info['n_knots'] = n_knots

            results['scales'][scale] = var_info

            print(f"  Pooled: 90%→K={var_info['n_for_90']}, "
                  f"95%→K={var_info['n_for_95']}, "
                  f"99%→K={var_info['n_for_99']}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results['scales'][scale] = {'error': str(e)}

    # Per-patient FPCA at daily scale (richest expected structure)
    print(f"\n{'─' * 40}")
    print("Per-patient FPCA (daily scale)")
    for i, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        try:
            from .run_pattern_experiments import _get_cached_grid, _split_windows
            df, features = _get_cached_grid(path)
            if df is None:
                continue

            # Daily scale: downsample to 15-min, 96-step windows
            df_ds = downsample_grid(df, target_interval_min=15)
            feats = _grid_to_features(df_ds)
            windows = _split_windows(feats, 96, 1)
            if not windows or len(windows) < 5:
                continue

            glucose = np.array(windows, dtype=np.float32)[:, :, 0]
            max_k = min(15, glucose.shape[0] - 1)
            n_knots = max(4, 96 // 6)
            var_info = fpca_variance_explained(
                glucose, max_components=max_k, n_knots=n_knots
            )
            var_info['n_windows'] = len(windows)
            results['per_patient'][patient_id] = var_info

            print(f"  Patient {patient_id}: {len(windows)} windows, "
                  f"90%→K={var_info['n_for_90']}")

        except Exception as e:
            print(f"  Patient {patient_id}: ERROR {e}")

    # Compare pooled vs per-patient
    if results['scales'].get('daily') and results['per_patient']:
        pooled_n90 = results['scales']['daily'].get('n_for_90', 999)
        per_patient_n90s = [v.get('n_for_90', 999)
                            for v in results['per_patient'].values()
                            if 'n_for_90' in v]
        if per_patient_n90s:
            mean_pp_n90 = np.mean(per_patient_n90s)
            gap = abs(pooled_n90 - mean_pp_n90) / max(pooled_n90, 1) * 100
            results['pooled_vs_per_patient'] = {
                'pooled_n_for_90': pooled_n90,
                'mean_per_patient_n_for_90': float(mean_pp_n90),
                'gap_pct': float(gap),
                'pass': gap < 15,
            }
            print(f"\n  Pooled vs per-patient gap: {gap:.1f}% "
                  f"(target < 15%) "
                  f"{'✓ PASS' if gap < 15 else '✗ FAIL'}")

    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_results(results, os.path.join(output_dir, 'exp329_fpca_variance.json'))
    return results


# ── EXP-330: Glucodensity vs TIR — Information Content ────────────────

def run_glucodensity_vs_tir(args):
    """EXP-330: Glucodensity vs TIR — Information Content.

    Hypothesis: Glucodensity profiles contain strictly more information than
    time-in-range bins and can discriminate patient-states that TIR cannot.

    Baseline: 5-bin TIR (<54, 54-70, 70-180, 180-250, >250 mg/dL) per day.
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, load_multiscale_data, save_results,
    )
    from .fda_features import glucodensity
    from sklearn.cluster import KMeans
    from sklearn.metrics import (
        adjusted_rand_score, silhouette_score, mutual_info_score,
    )

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-330: Glucodensity vs TIR — Information Content")
    print("=" * 60)

    # Load daily-scale data (24h windows — glucodensity makes most sense here)
    train, val = load_multiscale_data(patient_paths, scale='daily')
    glucose = train[:, :, 0]  # normalized glucose (value / 400)

    # TIR bins: convert normalized back to mg/dL thresholds
    # 54/400=0.135, 70/400=0.175, 180/400=0.45, 250/400=0.625
    tir_thresholds = [0.135, 0.175, 0.45, 0.625]

    def compute_tir(glucose_windows):
        """Compute 5-bin TIR for each window."""
        n = glucose_windows.shape[0]
        tir = np.zeros((n, 5), dtype=np.float32)
        for i in range(n):
            g = glucose_windows[i]
            valid = g[~np.isnan(g)]
            if len(valid) == 0:
                continue
            tir[i, 0] = (valid < tir_thresholds[0]).mean()   # <54
            tir[i, 1] = ((valid >= tir_thresholds[0]) &
                         (valid < tir_thresholds[1])).mean()  # 54-70
            tir[i, 2] = ((valid >= tir_thresholds[1]) &
                         (valid < tir_thresholds[2])).mean()  # 70-180
            tir[i, 3] = ((valid >= tir_thresholds[2]) &
                         (valid < tir_thresholds[3])).mean()  # 180-250
            tir[i, 4] = (valid >= tir_thresholds[3]).mean()   # >250
        return tir

    print("\n  Computing TIR (5-bin)...")
    tir_features = compute_tir(glucose)

    print("  Computing glucodensity (50-bin KDE)...")
    gd_features = glucodensity(glucose, n_bins=50)

    # Cluster both representations and compare
    results = {
        'experiment': 'EXP-330',
        'name': 'glucodensity-vs-tir',
        'method': 'Compare TIR vs glucodensity via clustering quality',
        'n_samples': int(glucose.shape[0]),
        'tir_dim': 5,
        'glucodensity_dim': 50,
        'clustering': {},
    }

    for k in [3, 5, 7, 9]:
        print(f"\n  k-means k={k}:")

        # TIR clustering
        km_tir = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels_tir = km_tir.fit_predict(tir_features)
        sil_tir = silhouette_score(tir_features, labels_tir)

        # Glucodensity clustering
        km_gd = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels_gd = km_gd.fit_predict(gd_features)
        sil_gd = silhouette_score(gd_features, labels_gd)

        # Cross-comparison
        ari = adjusted_rand_score(labels_tir, labels_gd)
        mi = mutual_info_score(labels_tir, labels_gd)

        results['clustering'][f'k={k}'] = {
            'tir_silhouette': float(sil_tir),
            'glucodensity_silhouette': float(sil_gd),
            'delta_silhouette': float(sil_gd - sil_tir),
            'cross_ari': float(ari),
            'cross_mi': float(mi),
        }
        print(f"    TIR Sil={sil_tir:.3f}, GD Sil={sil_gd:.3f}, "
              f"Δ={sil_gd - sil_tir:+.3f}, ARI={ari:.3f}")

    # Find windows where TIR is similar but glucodensity differs
    from scipy.spatial.distance import cdist
    tir_dists = cdist(tir_features, tir_features, metric='euclidean')
    gd_dists = cdist(gd_features, gd_features, metric='euclidean')

    # Pairs with TIR dist < 10th percentile but GD dist > 90th percentile
    tir_thresh = np.percentile(tir_dists[np.triu_indices_from(tir_dists, k=1)], 10)
    gd_thresh = np.percentile(gd_dists[np.triu_indices_from(gd_dists, k=1)], 90)

    similar_tir_diff_gd = 0
    n_checked = 0
    for i in range(min(1000, glucose.shape[0])):
        for j in range(i + 1, min(1000, glucose.shape[0])):
            n_checked += 1
            if tir_dists[i, j] < tir_thresh and gd_dists[i, j] > gd_thresh:
                similar_tir_diff_gd += 1

    results['discrimination'] = {
        'pairs_checked': n_checked,
        'similar_tir_different_gd': similar_tir_diff_gd,
        'fraction': float(similar_tir_diff_gd / max(n_checked, 1)),
    }
    print(f"\n  Discrimination: {similar_tir_diff_gd}/{n_checked} pairs "
          f"have similar TIR but different glucodensity")

    # Success evaluation
    best_k = max(results['clustering'].keys(),
                 key=lambda k: results['clustering'][k]['delta_silhouette'])
    best_delta = results['clustering'][best_k]['delta_silhouette']
    results['success'] = {
        'best_k': best_k,
        'best_delta_silhouette': float(best_delta),
        'pass_silhouette': best_delta >= 0.05,
        'pass_discrimination': similar_tir_diff_gd > 0,
    }

    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_results(results, os.path.join(output_dir, 'exp330_glucodensity_vs_tir.json'))
    return results


# ── EXP-331: Functional Derivatives vs Finite Differences ────────────

def run_functional_derivatives(args):
    """EXP-331: Functional Derivatives vs Hand-Engineered Rate Features.

    Hypothesis: Derivatives from B-spline-smoothed glucose provide cleaner
    rate-of-change signal than finite-difference ROC features.

    Baseline: EXP-316 showed ISF-as-feature hurts override by -3.5%.
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, load_multiscale_data, save_results,
    )
    from .fda_features import functional_derivatives

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-331: Functional Derivatives vs Finite Differences")
    print("=" * 60)

    # Load fast-scale (2h) — standard event detection scale
    train, val = load_multiscale_data(patient_paths, scale='fast')
    glucose = train[:, :, 0]
    n_samples, n_points = glucose.shape

    print(f"\n  Data: {n_samples} train windows × {n_points} points")

    # 1. Finite difference derivative (current method)
    finite_diff_d1 = np.diff(glucose, axis=1)  # (N, T-1)
    # Pad to match original length
    finite_diff_d1 = np.concatenate(
        [finite_diff_d1, finite_diff_d1[:, -1:]], axis=1
    )

    # 2. B-spline derivative
    print("  Computing B-spline 1st derivatives...")
    n_knots = max(4, n_points // 6)
    bspline_d1 = functional_derivatives(glucose, order=1, n_knots=n_knots)

    # 3. B-spline 2nd derivative
    print("  Computing B-spline 2nd derivatives...")
    bspline_d2 = functional_derivatives(glucose, order=2, n_knots=n_knots)

    # 4. Compare SNR
    # Define "events" as glucose crossing thresholds
    # Event windows: glucose drops below 70/400=0.175 (hypo) or rises above 180/400=0.45
    hypo_mask = np.any(glucose < 0.175, axis=1)
    hyper_mask = np.any(glucose > 0.45, axis=1)
    stable_mask = ~hypo_mask & ~hyper_mask

    def compute_snr(deriv, event_mask, stable_mask):
        """Signal = mean |deriv| during events; noise = std during stable."""
        if event_mask.sum() == 0 or stable_mask.sum() == 0:
            return float('nan')
        signal = np.abs(deriv[event_mask]).mean()
        noise = deriv[stable_mask].std()
        return float(signal / max(noise, 1e-8))

    results = {
        'experiment': 'EXP-331',
        'name': 'functional-derivatives',
        'method': 'B-spline vs finite-difference derivative comparison',
        'n_samples': int(n_samples),
        'n_hypo': int(hypo_mask.sum()),
        'n_hyper': int(hyper_mask.sum()),
        'n_stable': int(stable_mask.sum()),
        'n_knots': n_knots,
    }

    # SNR comparison
    for label, event_mask in [('hypo', hypo_mask), ('hyper', hyper_mask)]:
        fd_snr = compute_snr(finite_diff_d1, event_mask, stable_mask)
        bs_snr = compute_snr(bspline_d1, event_mask, stable_mask)
        results[f'snr_{label}'] = {
            'finite_diff': fd_snr,
            'bspline': bs_snr,
            'ratio': float(bs_snr / max(fd_snr, 1e-8)),
        }
        print(f"  SNR ({label}): finite_diff={fd_snr:.3f}, "
              f"bspline={bs_snr:.3f}, ratio={bs_snr/max(fd_snr, 1e-8):.2f}×")

    # Correlation with future glucose change
    print("\n  Correlation with future glucose change...")
    for lead_steps, lead_min in [(3, 15), (6, 30), (12, 60)]:
        if lead_steps >= n_points:
            continue
        future_change = glucose[:, lead_steps:] - glucose[:, :-lead_steps]
        # Trim derivatives to match
        fd_trimmed = finite_diff_d1[:, :-lead_steps]
        bs_trimmed = bspline_d1[:, :-lead_steps]
        bs2_trimmed = bspline_d2[:, :-lead_steps]

        # Pearson correlation (flattened)
        fd_corr = np.corrcoef(fd_trimmed.flatten(),
                              future_change.flatten())[0, 1]
        bs_corr = np.corrcoef(bs_trimmed.flatten(),
                              future_change.flatten())[0, 1]
        bs2_corr = np.corrcoef(bs2_trimmed.flatten(),
                               future_change.flatten())[0, 1]

        results[f'corr_{lead_min}min'] = {
            'finite_diff': float(fd_corr),
            'bspline_d1': float(bs_corr),
            'bspline_d2': float(bs2_corr),
        }
        print(f"  {lead_min}min: fd={fd_corr:.3f}, bs_d1={bs_corr:.3f}, "
              f"bs_d2={bs2_corr:.3f}")

    # Overall noise level comparison
    fd_noise = finite_diff_d1[stable_mask].std()
    bs_noise = bspline_d1[stable_mask].std()
    results['noise_comparison'] = {
        'finite_diff_stable_std': float(fd_noise),
        'bspline_stable_std': float(bs_noise),
        'noise_reduction_pct': float((1 - bs_noise / max(fd_noise, 1e-8)) * 100),
    }
    print(f"\n  Noise: fd={fd_noise:.4f}, bs={bs_noise:.4f}, "
          f"reduction={((1 - bs_noise/max(fd_noise, 1e-8)) * 100):.1f}%")

    # Success criteria
    snr_ratios = [results.get(f'snr_{l}', {}).get('ratio', 0)
                  for l in ['hypo', 'hyper']]
    avg_snr_ratio = np.mean([r for r in snr_ratios if r > 0]) if snr_ratios else 0
    results['success'] = {
        'avg_snr_ratio': float(avg_snr_ratio),
        'pass_snr': avg_snr_ratio >= 1.5,
        'noise_reduction_pct': results['noise_comparison']['noise_reduction_pct'],
    }

    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_results(results, os.path.join(output_dir, 'exp331_functional_derivatives.json'))
    return results


# ── EXP-332: FPCA Scores as Pattern Retrieval Embeddings ─────────────

def run_fpca_retrieval(args):
    """EXP-332: FPCA Scores as Pattern Retrieval Embeddings.

    Hypothesis: FPCA scores at weekly scale provide better embeddings than
    GRU-learned embeddings (EXP-304 Sil=+0.326).

    Baseline: EXP-304 weekly GRU Sil=+0.326, LOO Sil=-0.360.
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, load_multiscale_data, save_results,
    )
    from .fda_features import fpca_scores, glucodensity, l2_distance_to_mean
    from sklearn.metrics import silhouette_score, adjusted_rand_score
    from sklearn.cluster import KMeans

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-332: FPCA Scores as Pattern Retrieval Embeddings")
    print("=" * 60)

    # Load weekly scale (7d @ 1hr = 168 steps) — same as EXP-304
    train, val = load_multiscale_data(patient_paths, scale='weekly')
    glucose = train[:, :, 0]

    print(f"\n  Data: {train.shape[0]} train windows × {train.shape[1]} points")

    results = {
        'experiment': 'EXP-332',
        'name': 'fpca-retrieval',
        'method': 'FPCA scores vs GRU embeddings for pattern retrieval',
        'baseline': {'exp304_gru_silhouette': 0.326, 'exp304_loo_silhouette': -0.360},
        'n_train': int(train.shape[0]),
        'fpca_results': {},
    }

    # Compute FPCA at various K
    for K in [5, 10, 15, 20]:
        k_actual = min(K, glucose.shape[0] - 1, glucose.shape[1] - 1)
        if k_actual < 2:
            continue

        print(f"\n  FPCA K={k_actual}:")
        n_knots = max(4, glucose.shape[1] // 12)
        scores, fpca_obj = fpca_scores(glucose, n_components=k_actual,
                                       n_knots=n_knots)

        # Clustering evaluation (k=9 to match episode labels)
        for n_clusters in [5, 7, 9]:
            if scores.shape[0] < n_clusters + 1:
                continue
            km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = km.fit_predict(scores)
            sil = silhouette_score(scores, labels)

            key = f'K={k_actual}_clusters={n_clusters}'
            results['fpca_results'][key] = {
                'n_components': k_actual,
                'n_clusters': n_clusters,
                'silhouette': float(sil),
                'delta_vs_gru': float(sil - 0.326),
            }
            print(f"    clusters={n_clusters}: Sil={sil:+.3f} "
                  f"(Δ vs GRU: {sil - 0.326:+.3f})")

    # Best result
    if results['fpca_results']:
        best_key = max(results['fpca_results'],
                       key=lambda k: results['fpca_results'][k]['silhouette'])
        best_sil = results['fpca_results'][best_key]['silhouette']
        results['best'] = {
            'config': best_key,
            'silhouette': float(best_sil),
            'pass_viable': best_sil > 0.20,
            'pass_beats_gru': best_sil > 0.326,
        }
        print(f"\n  Best: {best_key} → Sil={best_sil:+.3f}")

    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_results(results, os.path.join(output_dir, 'exp332_fpca_retrieval.json'))
    return results


# ── EXP-334: FPCA-Based ISF Drift Detection ──────────────────────────

def run_fpca_isf_drift(args):
    """EXP-334: FPCA-Based ISF Drift Detection.

    Hypothesis: Tracking FPCA score trajectories over biweekly windows
    detects ISF drift earlier than rolling-mean Spearman (EXP-312).

    Baseline: EXP-312 biweekly rolling, 9/11 significant, ~14 day latency.
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, save_results,
        _get_cached_grid, _grid_to_features, _split_windows,
    )
    from .real_data_adapter import downsample_grid
    from .fda_features import fpca_scores
    from scipy.stats import spearmanr

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-334: FPCA-Based ISF Drift Detection")
    print("=" * 60)

    results = {
        'experiment': 'EXP-334',
        'name': 'fpca-isf-drift',
        'method': 'FPCA score trajectories for ISF drift detection',
        'baseline': {'exp312_significant': '9/11', 'exp312_latency_days': 14},
        'per_patient': {},
    }

    n_significant = 0
    n_patients = 0

    for path in patient_paths:
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"\n  Patient {patient_id}:")

        try:
            df, features = _get_cached_grid(path)
            if df is None:
                print("    SKIP: no data")
                continue

            # Daily scale: 24h windows @ 15-min, stride=1 (daily)
            df_ds = downsample_grid(df, target_interval_min=15)
            feats = _grid_to_features(df_ds)
            windows = _split_windows(feats, 96, stride=1)

            if not windows or len(windows) < 14:
                print(f"    SKIP: only {len(windows) if windows else 0} windows")
                continue

            glucose_windows = np.array(windows, dtype=np.float32)[:, :, 0]
            n_days = glucose_windows.shape[0]

            # FPCA on this patient's daily windows
            K = min(5, n_days - 1)
            n_knots = max(4, 96 // 6)
            scores, fpca_obj = fpca_scores(glucose_windows, n_components=K,
                                           n_knots=n_knots)

            # Spearman correlation for each PC score over time (days)
            day_indices = np.arange(n_days)
            pc_results = {}
            any_significant = False

            for pc in range(K):
                rho, pval = spearmanr(day_indices, scores[:, pc])
                sig = pval < 0.05
                if sig:
                    any_significant = True
                pc_results[f'PC{pc+1}'] = {
                    'rho': float(rho),
                    'pval': float(pval),
                    'significant': bool(sig),
                }

            if any_significant:
                n_significant += 1

            n_patients += 1
            var_explained = fpca_obj.explained_variance_ratio_
            results['per_patient'][patient_id] = {
                'n_days': n_days,
                'n_components': K,
                'variance_explained': [float(v) for v in var_explained],
                'pc_spearman': pc_results,
                'any_significant': any_significant,
            }

            sig_pcs = [k for k, v in pc_results.items() if v['significant']]
            print(f"    {n_days} days, K={K}, "
                  f"sig PCs: {sig_pcs if sig_pcs else 'none'}")

        except Exception as e:
            print(f"    ERROR: {e}")

    results['summary'] = {
        'n_patients': n_patients,
        'n_significant': n_significant,
        'detection_rate': f'{n_significant}/{n_patients}',
        'pass': n_significant >= 9 if n_patients >= 11 else None,
    }

    print(f"\n  Summary: {n_significant}/{n_patients} patients with "
          f"significant FPCA drift")

    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_results(results, os.path.join(output_dir, 'exp334_fpca_isf_drift.json'))
    return results


# ── EXP-335: Functional Depth for Hypo Novelty Detection ─────────────

def run_depth_hypo(args):
    """EXP-335: Functional Depth for Hypoglycemia Novelty Detection.

    Hypothesis: Low functional depth (atypical glucose curves) correlates
    with hypoglycemic events, providing unsupervised signal complementary
    to supervised CNN.

    Baseline: EXP-322 hypo F1=0.676, AUC=0.958.
    """
    from .run_pattern_experiments import (
        resolve_patient_paths, load_multiscale_data, save_results,
    )
    from .fda_features import functional_depth, l2_distance_to_mean

    patient_paths = resolve_patient_paths(
        getattr(args, 'patients_dir', None) or 'externals/ns-data/patients'
    )
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'

    print("=" * 60)
    print("EXP-335: Functional Depth for Hypo Novelty Detection")
    print("=" * 60)

    # Fast scale — 2h windows for hypo detection
    train, val = load_multiscale_data(patient_paths, scale='fast')
    glucose = train[:, :, 0]

    # Label: hypo = any glucose < 70 mg/dL (0.175 normalized) in window
    hypo_labels = np.any(glucose < 0.175, axis=1).astype(int)
    hypo_rate = hypo_labels.mean()
    print(f"\n  Data: {glucose.shape[0]} windows, hypo rate={hypo_rate:.3f}")

    # Compute depth
    print("  Computing functional depth (may take a moment)...")
    # Use subsample for depth computation (O(n²))
    max_n = min(5000, glucose.shape[0])
    subset_idx = np.random.RandomState(42).choice(
        glucose.shape[0], max_n, replace=False
    )
    glucose_sub = glucose[subset_idx]
    labels_sub = hypo_labels[subset_idx]

    depths = functional_depth(glucose_sub)
    l2_dists = l2_distance_to_mean(glucose_sub)

    # Correlation between depth and hypo
    from scipy.stats import pointbiserialr
    depth_corr, depth_pval = pointbiserialr(labels_sub, depths)
    l2_corr, l2_pval = pointbiserialr(labels_sub, l2_dists)

    print(f"  Depth-hypo correlation: r={depth_corr:.3f} (p={depth_pval:.4f})")
    print(f"  L²-hypo correlation:   r={l2_corr:.3f} (p={l2_pval:.4f})")

    # Hypo rate by depth quartile
    depth_quartiles = np.percentile(depths, [25, 50, 75])
    q_labels = np.digitize(depths, depth_quartiles)  # 0-3
    quartile_hypo_rates = {}
    for q in range(4):
        mask = q_labels == q
        if mask.sum() > 0:
            rate = labels_sub[mask].mean()
            quartile_hypo_rates[f'Q{q+1}'] = {
                'n': int(mask.sum()),
                'hypo_rate': float(rate),
                'mean_depth': float(depths[mask].mean()),
            }
            print(f"  Q{q+1}: depth=[{depths[mask].min():.3f},{depths[mask].max():.3f}], "
                  f"hypo_rate={rate:.3f}, n={mask.sum()}")

    # Low-depth windows: hypo rate ≥ 2× average?
    low_depth_mask = depths < np.percentile(depths, 20)
    if low_depth_mask.sum() > 0:
        low_depth_hypo_rate = labels_sub[low_depth_mask].mean()
        enrichment = low_depth_hypo_rate / max(hypo_rate, 1e-8)
    else:
        low_depth_hypo_rate = 0
        enrichment = 0

    results = {
        'experiment': 'EXP-335',
        'name': 'depth-hypo',
        'method': 'Functional depth as hypo novelty signal',
        'baseline': {'exp322_hypo_f1': 0.676, 'exp322_hypo_auc': 0.958},
        'n_samples': int(max_n),
        'hypo_prevalence': float(hypo_rate),
        'depth_hypo_correlation': {
            'r': float(depth_corr),
            'pval': float(depth_pval),
        },
        'l2_hypo_correlation': {
            'r': float(l2_corr),
            'pval': float(l2_pval),
        },
        'quartile_hypo_rates': quartile_hypo_rates,
        'low_depth_enrichment': {
            'threshold': 'bottom 20%',
            'low_depth_hypo_rate': float(low_depth_hypo_rate),
            'overall_hypo_rate': float(hypo_rate),
            'enrichment_ratio': float(enrichment),
            'pass': enrichment >= 2.0,
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n  Low-depth enrichment: {enrichment:.1f}× "
          f"(target ≥ 2.0) "
          f"{'✓ PASS' if enrichment >= 2.0 else '✗ FAIL'}")

    save_results(results, os.path.join(output_dir, 'exp335_depth_hypo.json'))
    return results
