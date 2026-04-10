#!/usr/bin/env python3
"""EXP-1783 to EXP-1790: Glycogen Proxy Deconfounding & Metabolic State Analysis.

Follows from EXP-1626–1628 (glycogen proxy construction, sensitivity correlation,
hypo recovery prediction) and EXP-1755 (glycogen proxy + information ceiling).

Key open question: The glycogen proxy (EXP-1627) showed Spearman r=1.000 between
proxy quintile and effective insulin sensitivity β. But this is confounded with
insulin delivery state — when "glycogen" is high (recent high glucose, recent
carbs), insulin delivery is also high. We need to deconfound.

  EXP-1783: IOB-conditioned glycogen sensitivity — stratify by IOB quartile,
            then test glycogen→β within each stratum. If glycogen still predicts
            β after conditioning on IOB, the effect is real.
  EXP-1784: Glucose-independent glycogen proxy — construct proxy using ONLY
            cumulative carb balance and time-since-last-meal (no glucose terms).
            Tests whether glucose contamination drives the correlation.
  EXP-1785: Post-exercise vs post-feast natural experiments — compare metabolic
            behavior in known glycogen-depleting vs glycogen-loading contexts.
            Exercise ≈ extended low IOB + falling glucose; feast ≈ high carbs + rising.
  EXP-1786: Glycogen state → cascade patterns — does glycogen level at excursion
            onset predict cascade chain length, type distribution, or rebound magnitude?
  EXP-1787: Counter-regulatory capacity by glycogen state — does the counter-reg
            floor (1.68 mg/dL/step) vary with inferred glycogen level?
  EXP-1788: Multi-day glycogen dynamics — track the proxy over multi-day windows.
            Do patients with depleted glycogen (extended fasting, exercise, extended
            time <80) show different next-day glucose patterns?
  EXP-1789: Metabolic context segmentation — classify every 5-min step into one
            of 6 metabolic contexts (fasting, post-meal, correction, hypo-recovery,
            exercise-like, stable) and compute supply/demand R² per context.
  EXP-1790: Residual variance decomposition — partition model residual into
            components: glycogen state, rescue carbs, circadian, sensor noise,
            unexplained. Quantifies the information ceiling per factor.

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_glycogen_deconfound_1783.py --figures
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cgmencode.exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path('externals/ns-data/patients')
RESULTS_DIR = Path('externals/experiments')
FIGURES_DIR = Path('docs/60-research/figures')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
LOW, HIGH = 70.0, 180.0


def _get_isf(pat):
    """Extract mean ISF in mg/dL from patient schedule."""
    sched = pat['df'].attrs.get('isf_schedule', [])
    if not sched:
        return 50.0
    vals = [e.get('value', e.get('sensitivity', 50)) for e in sched]
    v = float(np.median(vals))
    if v < 15:
        v *= 18.0182  # mmol/L → mg/dL
    return v


def _get_basal(pat):
    """Extract mean basal rate from patient schedule."""
    sched = pat['df'].attrs.get('basal_schedule', [])
    if not sched:
        return 0.8
    vals = [e.get('value', e.get('rate', 0.8)) for e in sched]
    return float(np.median(vals))


def _get_cr(pat):
    """Extract mean CR from patient schedule."""
    sched = pat['df'].attrs.get('cr_schedule', [])
    if not sched:
        return 10.0
    vals = [e.get('value', e.get('carbratio', 10)) for e in sched]
    return float(np.median(vals))


# ── Glycogen proxy construction ──────────────────────────────────────────

def compute_glycogen_proxy(glucose, carbs, iob, lookback_h=6):
    """Original glycogen proxy from EXP-1626 (arbitrary weights).

    Higher proxy = more glycogen expected (recent high glucose, carbs, less insulin).
    """
    lb = lookback_h * STEPS_PER_HOUR
    N = len(glucose)
    proxy = np.full(N, np.nan)

    for i in range(lb, N):
        window = slice(i - lb, i)
        # Glucose score: fraction of window above 120
        g_score = np.nanmean(glucose[window] > 120)
        # Carb score: total carbs (normalized to ~30g typical)
        c_score = min(np.nansum(carbs[window]) / 30.0, 2.0)
        # Insulin score: mean IOB (higher = more depletion)
        i_score = min(np.nanmean(np.abs(iob[window])) / 3.0, 2.0)
        # Hypo score: fraction of window below 80 (depletion signal)
        h_score = np.nanmean(glucose[window] < 80)

        proxy[i] = 0.4 * g_score + 0.3 * c_score - 0.2 * i_score - 0.1 * h_score

    return proxy


def compute_glycogen_proxy_glucose_free(carbs, iob, lookback_h=6):
    """Glucose-independent glycogen proxy (EXP-1784).

    Uses ONLY carb intake and insulin delivery — no glucose terms.
    If glycogen effect is real, it should still predict behavior.
    """
    lb = lookback_h * STEPS_PER_HOUR
    N = len(carbs)
    proxy = np.full(N, np.nan)

    for i in range(lb, N):
        window = slice(i - lb, i)
        # Net carb balance: carbs in minus insulin depletion
        c_total = np.nansum(carbs[window])
        i_total = np.nanmean(np.abs(iob[window]))
        # Time since last carb
        carb_steps = np.where(carbs[i - lb:i] > 0)[0]
        if len(carb_steps) > 0:
            time_since_carb = (lb - carb_steps[-1]) / STEPS_PER_HOUR
        else:
            time_since_carb = lookback_h  # max

        # Higher carbs, lower insulin, recent meal → higher glycogen
        proxy[i] = (c_total / 30.0) - (i_total / 3.0) - (time_since_carb / lookback_h) * 0.3

    return proxy


# ── Metabolic context classification ─────────────────────────────────────

def classify_metabolic_context(glucose, carbs, iob, bolus):
    """Classify each timestep into metabolic context (EXP-1789).

    Returns array of context labels:
      0 = fasting (no carbs 3h, low IOB)
      1 = post_meal (carbs within 2h)
      2 = correction (bolus without carbs)
      3 = hypo_recovery (glucose < 80 in past 30min)
      4 = exercise_like (falling glucose, low IOB, no carbs)
      5 = stable (none of the above, glucose in range)
    """
    N = len(glucose)
    ctx = np.full(N, 5, dtype=np.int32)  # default = stable

    for i in range(N):
        g = glucose[i]
        if np.isnan(g):
            continue

        # Check recent carbs
        carb_window_2h = max(0, i - 24)
        carb_window_3h = max(0, i - 36)
        recent_carbs_2h = np.nansum(carbs[carb_window_2h:i + 1])
        recent_carbs_3h = np.nansum(carbs[carb_window_3h:i + 1])

        # Check recent bolus without carbs
        bolus_window = max(0, i - 12)
        recent_bolus = np.nansum(bolus[bolus_window:i + 1])
        recent_carbs_1h = np.nansum(carbs[bolus_window:i + 1])

        # Check recent hypo
        hypo_window = max(0, i - 6)
        recent_hypo = np.any(glucose[hypo_window:i + 1] < 80)

        # Check glucose trend
        if i >= 3:
            trend = (glucose[i] - glucose[max(0, i - 3)]) / 3.0
        else:
            trend = 0.0

        # Priority ordering
        if recent_hypo and g < 100:
            ctx[i] = 3  # hypo_recovery
        elif recent_carbs_2h > 2:
            ctx[i] = 1  # post_meal
        elif recent_bolus > 0.5 and recent_carbs_1h < 2:
            ctx[i] = 2  # correction
        elif recent_carbs_3h < 2 and iob[i] < 0.5:
            ctx[i] = 0  # fasting
        elif trend < -1.0 and iob[i] < 0.3 and recent_carbs_2h < 2:
            ctx[i] = 4  # exercise_like
        # else stays 5 = stable

    return ctx


CONTEXT_NAMES = ['fasting', 'post_meal', 'correction', 'hypo_recovery',
                 'exercise_like', 'stable']


# ── Experiment implementations ───────────────────────────────────────────

def exp_1783_iob_conditioned_glycogen(patients):
    """IOB-conditioned glycogen → sensitivity analysis.

    Stratify by IOB quartile, then test glycogen→β within each stratum.
    """
    print("\n=== EXP-1783: IOB-Conditioned Glycogen Sensitivity ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Compute glycogen proxy
        gly = compute_glycogen_proxy(glucose, carbs, iob)
        valid = ~np.isnan(gly) & ~np.isnan(glucose)

        # Compute dBG (actual glucose change)
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        # Compute supply-demand
        sd = compute_supply_demand(df)
        net_flux = sd['net']
        demand = sd['demand']

        # Effective beta: actual_dBG / modeled_demand (where demand > threshold)
        demand_thresh = np.percentile(demand[demand > 0], 25) if np.any(demand > 0) else 0.1

        # IOB quartiles
        iob_valid = iob[valid]
        gly_valid = gly[valid]
        dbg_valid = dbg[valid]
        demand_valid = demand[valid]

        iob_quartiles = np.percentile(iob_valid[iob_valid > 0], [25, 50, 75]) if np.any(iob_valid > 0) else [0.1, 0.5, 1.0]

        strata = []
        for q_idx, (q_lo, q_hi, q_name) in enumerate([
            (0, iob_quartiles[0], 'Q1_low_iob'),
            (iob_quartiles[0], iob_quartiles[1], 'Q2'),
            (iob_quartiles[1], iob_quartiles[2], 'Q3'),
            (iob_quartiles[2], np.inf, 'Q4_high_iob'),
        ]):
            mask = valid.copy()
            mask &= (iob >= q_lo) & (iob < q_hi)
            mask &= (demand > demand_thresh)

            if mask.sum() < 50:
                strata.append({
                    'iob_quartile': q_name, 'n': int(mask.sum()),
                    'glycogen_beta_r': None, 'glycogen_beta_p': None
                })
                continue

            # Within this IOB stratum, correlate glycogen with effective beta
            g_stratum = gly[mask]
            d_stratum = demand[mask]
            actual_stratum = dbg[mask]

            # Effective beta = |actual_dBG| / demand (how much demand translates)
            eff_beta = np.abs(actual_stratum) / np.maximum(d_stratum, 0.01)
            # Cap extreme values
            eff_beta = np.clip(eff_beta, 0, 10)

            # Glycogen quintiles within stratum
            g_bins = np.percentile(g_stratum, [20, 40, 60, 80])
            g_labels = np.digitize(g_stratum, g_bins)
            quintile_betas = []
            for qi in range(5):
                qmask = g_labels == qi
                if qmask.sum() > 10:
                    quintile_betas.append(float(np.median(eff_beta[qmask])))

            if len(quintile_betas) >= 3:
                r_val, p_val = stats.spearmanr(range(len(quintile_betas)), quintile_betas)
            else:
                r_val, p_val = np.nan, np.nan

            strata.append({
                'iob_quartile': q_name,
                'n': int(mask.sum()),
                'glycogen_beta_r': float(r_val) if not np.isnan(r_val) else None,
                'glycogen_beta_p': float(p_val) if not np.isnan(p_val) else None,
                'quintile_betas': quintile_betas,
            })

        results.append({
            'name': name,
            'strata': strata,
        })

        # Summary for this patient
        sig_strata = sum(1 for s in strata if s.get('glycogen_beta_p') is not None
                         and s['glycogen_beta_p'] < 0.05)
        print(f"  {name}: {sig_strata}/4 IOB strata show significant glycogen→β (p<0.05)")

    # Population summary
    total_sig = sum(1 for r in results for s in r['strata']
                    if s.get('glycogen_beta_p') is not None and s['glycogen_beta_p'] < 0.05)
    total_strata = sum(1 for r in results for s in r['strata']
                       if s.get('glycogen_beta_r') is not None)
    print(f"\n  Population: {total_sig}/{total_strata} strata significant (p<0.05)")

    exp_result = {
        'experiment': 'EXP-1783',
        'title': 'IOB-Conditioned Glycogen Sensitivity',
        'n_patients': len(results),
        'total_significant_strata': total_sig,
        'total_testable_strata': total_strata,
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1783_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1784_glucose_free_proxy(patients):
    """Glucose-independent glycogen proxy test.

    If the glycogen→β correlation survives when glucose is removed from
    the proxy construction, the effect is more likely physiological.
    """
    print("\n=== EXP-1784: Glucose-Independent Glycogen Proxy ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Original proxy (with glucose)
        gly_orig = compute_glycogen_proxy(glucose, carbs, iob)
        # Glucose-free proxy
        gly_free = compute_glycogen_proxy_glucose_free(carbs, iob)

        valid = ~np.isnan(gly_orig) & ~np.isnan(gly_free) & ~np.isnan(glucose)

        # Compute actual dBG
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        sd = compute_supply_demand(df)
        demand = sd['demand']

        # Use a less aggressive threshold — just require non-trivial demand
        demand_thresh = 0.1  # mg/dL/step minimum
        mask = valid & (demand > demand_thresh) & ~np.isnan(dbg)
        if mask.sum() < 100:
            results.append({'name': name, 'n': int(mask.sum()),
                            'orig_r': None, 'free_r': None, 'proxy_corr': None})
            continue

        eff_beta = np.clip(np.abs(dbg[mask]) / np.maximum(demand[mask], 0.01), 0, 10)

        # Filter out constant eff_beta (variance needed for spearmanr)
        if np.std(eff_beta) < 1e-10:
            results.append({'name': name, 'n': int(mask.sum()),
                            'orig_r': None, 'free_r': None, 'proxy_corr': None})
            continue

        # Correlate both proxies with effective beta
        r_orig, p_orig = stats.spearmanr(gly_orig[mask], eff_beta)
        r_free, p_free = stats.spearmanr(gly_free[mask], eff_beta)
        # Correlation between the two proxies
        proxy_corr, _ = stats.spearmanr(gly_orig[mask], gly_free[mask])

        results.append({
            'name': name,
            'n': int(mask.sum()),
            'orig_r': float(r_orig),
            'orig_p': float(p_orig),
            'free_r': float(r_free),
            'free_p': float(p_free),
            'proxy_corr': float(proxy_corr),
        })

        print(f"  {name}: orig_r={r_orig:.3f} (p={p_orig:.2e}), "
              f"free_r={r_free:.3f} (p={p_free:.2e}), "
              f"proxy_corr={proxy_corr:.3f}")

    # Summary
    orig_sig = sum(1 for r in results if r.get('orig_p') is not None and r['orig_p'] < 0.05)
    free_sig = sum(1 for r in results if r.get('free_p') is not None and r['free_p'] < 0.05)
    mean_proxy_corr = np.nanmean([r['proxy_corr'] for r in results if r['proxy_corr'] is not None])
    print(f"\n  Original proxy significant: {orig_sig}/{len(results)}")
    print(f"  Glucose-free proxy significant: {free_sig}/{len(results)}")
    print(f"  Mean proxy correlation: {mean_proxy_corr:.3f}")

    exp_result = {
        'experiment': 'EXP-1784',
        'title': 'Glucose-Independent Glycogen Proxy',
        'n_patients': len(results),
        'orig_significant': orig_sig,
        'free_significant': free_sig,
        'mean_proxy_correlation': float(mean_proxy_corr),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1784_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1785_natural_experiment_contexts(patients):
    """Post-exercise-like vs post-feast natural experiments.

    Identify glycogen-depleting contexts (extended low glucose, low IOB, no carbs)
    vs glycogen-loading contexts (recent large meal, high glucose) and compare
    metabolic behavior in matched windows after each.
    """
    print("\n=== EXP-1785: Exercise-like vs Feast Natural Experiments ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        sd = compute_supply_demand(df)
        net = sd['net']
        hepatic = sd['hepatic']

        # Identify "depleted" windows: 2h+ of glucose<100, no carbs, low IOB
        depleted_windows = []
        # Identify "loaded" windows: glucose>150 after large meal (>30g in past 2h)
        loaded_windows = []

        for i in range(24, len(glucose) - 24):
            lookback = slice(i - 24, i)
            lookahead = slice(i, i + 24)

            if np.any(np.isnan(glucose[lookback])) or np.any(np.isnan(glucose[lookahead])):
                continue

            lb_glucose = glucose[lookback]
            lb_carbs = carbs[lookback]
            lb_iob = iob[lookback]

            # Depleted: 2h of glucose consistently <100, no carbs, low IOB
            if (np.all(lb_glucose < 100) and np.sum(lb_carbs) < 2 and
                    np.mean(lb_iob) < 0.3):
                depleted_windows.append(i)

            # Loaded: large meal (>30g) in past 2h and glucose >150
            if np.sum(lb_carbs) > 30 and glucose[i] > 150:
                loaded_windows.append(i)

        # Subsample to avoid temporal autocorrelation (min 1h apart)
        def thin(indices, min_gap=12):
            if not indices:
                return []
            result = [indices[0]]
            for idx in indices[1:]:
                if idx - result[-1] >= min_gap:
                    result.append(idx)
            return result

        depleted_windows = thin(depleted_windows)
        loaded_windows = thin(loaded_windows)

        if len(depleted_windows) < 5 or len(loaded_windows) < 5:
            results.append({'name': name, 'n_depleted': len(depleted_windows),
                            'n_loaded': len(loaded_windows), 'status': 'insufficient'})
            print(f"  {name}: insufficient (depleted={len(depleted_windows)}, loaded={len(loaded_windows)})")
            continue

        # Compare next-2h behavior after depleted vs loaded states
        def lookahead_stats(windows, glucose, net, hepatic):
            dg_2h = []
            mean_hepatic = []
            mean_net = []
            for w in windows:
                if w + 24 < len(glucose):
                    dg_2h.append(glucose[w + 24] - glucose[w])
                    mean_hepatic.append(np.mean(hepatic[w:w + 24]))
                    mean_net.append(np.mean(net[w:w + 24]))
            return {
                'delta_glucose_2h': float(np.median(dg_2h)) if dg_2h else None,
                'mean_hepatic': float(np.median(mean_hepatic)) if mean_hepatic else None,
                'mean_net_flux': float(np.median(mean_net)) if mean_net else None,
                'n': len(dg_2h),
            }

        depleted_stats = lookahead_stats(depleted_windows, glucose, net, hepatic)
        loaded_stats = lookahead_stats(loaded_windows, glucose, net, hepatic)

        results.append({
            'name': name,
            'n_depleted': depleted_stats['n'],
            'n_loaded': loaded_stats['n'],
            'depleted_delta_g_2h': depleted_stats['delta_glucose_2h'],
            'loaded_delta_g_2h': loaded_stats['delta_glucose_2h'],
            'depleted_hepatic': depleted_stats['mean_hepatic'],
            'loaded_hepatic': loaded_stats['mean_hepatic'],
            'depleted_net': depleted_stats['mean_net_flux'],
            'loaded_net': loaded_stats['mean_net_flux'],
        })

        print(f"  {name}: depleted ΔG={depleted_stats['delta_glucose_2h']:+.1f} "
              f"(n={depleted_stats['n']}), loaded ΔG={loaded_stats['delta_glucose_2h']:+.1f} "
              f"(n={loaded_stats['n']})")

    # Summary
    valid = [r for r in results if r.get('depleted_delta_g_2h') is not None]
    if valid:
        dep_dg = np.mean([r['depleted_delta_g_2h'] for r in valid])
        load_dg = np.mean([r['loaded_delta_g_2h'] for r in valid])
        dep_hep = np.mean([r['depleted_hepatic'] for r in valid])
        load_hep = np.mean([r['loaded_hepatic'] for r in valid])
        print(f"\n  Population depleted ΔG_2h: {dep_dg:+.1f}, loaded ΔG_2h: {load_dg:+.1f}")
        print(f"  Population depleted hepatic: {dep_hep:.2f}, loaded hepatic: {load_hep:.2f}")
    else:
        dep_dg = load_dg = dep_hep = load_hep = None

    exp_result = {
        'experiment': 'EXP-1785',
        'title': 'Exercise-like vs Feast Natural Experiments',
        'n_patients': len(results),
        'n_valid': len(valid),
        'population_depleted_dg_2h': float(dep_dg) if dep_dg is not None else None,
        'population_loaded_dg_2h': float(load_dg) if load_dg is not None else None,
        'population_depleted_hepatic': float(dep_hep) if dep_hep is not None else None,
        'population_loaded_hepatic': float(load_hep) if load_hep is not None else None,
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1785_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1786_glycogen_cascade_patterns(patients):
    """Glycogen state → cascade patterns.

    Does glycogen level at excursion onset predict cascade behavior?
    """
    print("\n=== EXP-1786: Glycogen State → Cascade Patterns ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        gly = compute_glycogen_proxy(glucose, carbs, iob)

        # Detect excursions (simple: rises/falls > 15 mg/dL)
        excursions = []
        MIN_EXCURSION = 15.0
        i = 0
        while i < len(glucose) - 6:
            if np.isnan(glucose[i]):
                i += 1
                continue
            # Look ahead for 15+ mg/dL rise or fall in next 30 min
            for j in range(1, min(7, len(glucose) - i)):
                if np.isnan(glucose[i + j]):
                    continue
                delta = glucose[i + j] - glucose[i]
                if abs(delta) >= MIN_EXCURSION:
                    excursions.append({
                        'start': i,
                        'delta': float(delta),
                        'glycogen': float(gly[i]) if not np.isnan(gly[i]) else None,
                    })
                    i = i + j + 1
                    break
            else:
                i += 1

        if not excursions or sum(1 for e in excursions if e['glycogen'] is not None) < 20:
            results.append({'name': name, 'n_excursions': len(excursions), 'status': 'insufficient'})
            print(f"  {name}: insufficient excursions with glycogen data")
            continue

        # Split excursions by glycogen tertile
        gly_vals = np.array([e['glycogen'] for e in excursions if e['glycogen'] is not None])
        gly_terts = np.percentile(gly_vals, [33, 67])

        tertile_stats = {}
        for t_name, lo, hi in [('depleted', -np.inf, gly_terts[0]),
                                ('moderate', gly_terts[0], gly_terts[1]),
                                ('full', gly_terts[1], np.inf)]:
            t_exc = [e for e in excursions
                      if e['glycogen'] is not None and lo <= e['glycogen'] < hi]
            if not t_exc:
                continue
            rises = [e['delta'] for e in t_exc if e['delta'] > 0]
            falls = [e['delta'] for e in t_exc if e['delta'] < 0]
            tertile_stats[t_name] = {
                'n': len(t_exc),
                'mean_rise': float(np.mean(rises)) if rises else None,
                'mean_fall': float(np.mean(falls)) if falls else None,
                'rise_fraction': len(rises) / len(t_exc),
            }

        # Key test: does excursion magnitude differ by glycogen state?
        dep_mag = np.array([abs(e['delta']) for e in excursions
                            if e['glycogen'] is not None and e['glycogen'] < gly_terts[0]])
        full_mag = np.array([abs(e['delta']) for e in excursions
                             if e['glycogen'] is not None and e['glycogen'] >= gly_terts[1]])

        if len(dep_mag) > 10 and len(full_mag) > 10:
            u_stat, u_p = stats.mannwhitneyu(dep_mag, full_mag, alternative='two-sided')
            mag_diff = float(np.median(full_mag) - np.median(dep_mag))
        else:
            u_stat, u_p, mag_diff = None, None, None

        results.append({
            'name': name,
            'n_excursions': len(excursions),
            'tertile_stats': tertile_stats,
            'magnitude_diff_full_vs_depleted': mag_diff,
            'mannwhitney_p': float(u_p) if u_p is not None else None,
        })

        sig = "**" if u_p is not None and u_p < 0.05 else ""
        print(f"  {name}: {len(excursions)} excursions, "
              f"mag diff (full-depleted)={mag_diff:+.1f} {sig}"
              if mag_diff is not None else f"  {name}: {len(excursions)} excursions (insufficient)")

    sig_count = sum(1 for r in results if r.get('mannwhitney_p') is not None
                    and r['mannwhitney_p'] < 0.05)
    testable = sum(1 for r in results if r.get('mannwhitney_p') is not None)
    print(f"\n  Population: {sig_count}/{testable} patients show significant magnitude difference")

    exp_result = {
        'experiment': 'EXP-1786',
        'title': 'Glycogen State → Cascade Patterns',
        'n_patients': len(results),
        'n_significant': sig_count,
        'n_testable': testable,
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1786_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1787_counter_reg_by_glycogen(patients):
    """Counter-regulatory capacity by glycogen state.

    Does the counter-reg floor (1.68 mg/dL/step) vary with glycogen?
    Hypothesis: depleted glycogen → weaker counter-regulatory response.
    """
    print("\n=== EXP-1787: Counter-Regulatory Capacity by Glycogen State ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        gly = compute_glycogen_proxy(glucose, carbs, iob)
        sd = compute_supply_demand(df)
        residual = np.zeros_like(glucose)
        residual[1:] = (glucose[1:] - glucose[:-1]) - sd['net'][:-1]

        # Find near-hypo windows (<85 mg/dL)
        near_hypo = glucose < 85
        # Measure max residual in 4-step post-nadir windows (counter-reg signal)
        counter_reg_events = []

        i = 0
        while i < len(glucose) - 5:
            if near_hypo[i] and not np.isnan(gly[i]):
                # Find local nadir
                window = glucose[i:min(i + 12, len(glucose))]
                if np.all(np.isnan(window)):
                    i += 1
                    continue
                nadir_offset = np.nanargmin(window)
                nadir_idx = i + nadir_offset

                # Measure recovery in 4 steps after nadir
                if nadir_idx + 4 < len(residual):
                    recovery = np.max(residual[nadir_idx:nadir_idx + 4])
                    counter_reg_events.append({
                        'glycogen': float(gly[i]),
                        'recovery_rate': float(recovery),
                        'nadir_glucose': float(glucose[nadir_idx]),
                    })
                    i = nadir_idx + 4  # skip past this event
                else:
                    i += 1
            else:
                i += 1

        if len(counter_reg_events) < 20:
            results.append({'name': name, 'n_events': len(counter_reg_events),
                            'status': 'insufficient'})
            print(f"  {name}: insufficient near-hypo events ({len(counter_reg_events)})")
            continue

        gly_arr = np.array([e['glycogen'] for e in counter_reg_events])
        rec_arr = np.array([e['recovery_rate'] for e in counter_reg_events])

        # Filter NaN values (from NaN glucose in recovery windows)
        finite_mask = np.isfinite(gly_arr) & np.isfinite(rec_arr)
        gly_arr = gly_arr[finite_mask]
        rec_arr = rec_arr[finite_mask]

        if len(gly_arr) < 20 or np.std(gly_arr) < 1e-10 or np.std(rec_arr) < 1e-10:
            results.append({'name': name, 'n_events': len(counter_reg_events),
                            'n_valid': int(finite_mask.sum()),
                            'spearman_r': None, 'spearman_p': None,
                            'status': 'insufficient_valid'})
            print(f"  {name}: {len(counter_reg_events)} events, "
                  f"{finite_mask.sum()} valid after NaN filter")
            continue

        r_val, p_val = stats.spearmanr(gly_arr, rec_arr)

        # Tertile comparison
        terts = np.percentile(gly_arr, [33, 67])
        dep_rec = rec_arr[gly_arr < terts[0]]
        full_rec = rec_arr[gly_arr >= terts[1]]

        results.append({
            'name': name,
            'n_events': len(counter_reg_events),
            'spearman_r': float(r_val),
            'spearman_p': float(p_val),
            'depleted_median_recovery': float(np.median(dep_rec)) if len(dep_rec) > 5 else None,
            'full_median_recovery': float(np.median(full_rec)) if len(full_rec) > 5 else None,
        })

        print(f"  {name}: r={r_val:.3f} (p={p_val:.2e}), "
              f"depleted recovery={np.median(dep_rec):.2f}, "
              f"full recovery={np.median(full_rec):.2f}"
              if len(dep_rec) > 5 and len(full_rec) > 5
              else f"  {name}: r={r_val:.3f} (p={p_val:.2e}), n={len(counter_reg_events)}")

    # Population
    valid = [r for r in results if r.get('spearman_r') is not None]
    if valid:
        mean_r = np.mean([r['spearman_r'] for r in valid])
        sig = sum(1 for r in valid if r['spearman_p'] < 0.05)
        dep_recs = [r['depleted_median_recovery'] for r in valid
                    if r.get('depleted_median_recovery') is not None]
        full_recs = [r['full_median_recovery'] for r in valid
                     if r.get('full_median_recovery') is not None]
        print(f"\n  Population mean r={mean_r:.3f}, {sig}/{len(valid)} significant")
        if dep_recs and full_recs:
            print(f"  Depleted recovery: {np.mean(dep_recs):.2f}, Full recovery: {np.mean(full_recs):.2f}")

    exp_result = {
        'experiment': 'EXP-1787',
        'title': 'Counter-Regulatory Capacity by Glycogen State',
        'n_patients': len(results),
        'n_valid': len(valid),
        'population_mean_r': float(mean_r) if valid else None,
        'n_significant': sig if valid else 0,
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1787_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1788_multiday_glycogen(patients):
    """Multi-day glycogen dynamics.

    Track glycogen proxy over 24h windows. Compare patients/days with
    chronically depleted vs loaded glycogen — how do next-day patterns differ?
    """
    print("\n=== EXP-1788: Multi-Day Glycogen Dynamics ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        gly = compute_glycogen_proxy(glucose, carbs, iob, lookback_h=6)

        # Compute daily averages
        n_days = len(glucose) // STEPS_PER_DAY
        if n_days < 7:
            results.append({'name': name, 'n_days': n_days, 'status': 'insufficient'})
            continue

        daily_gly = []
        daily_tir = []
        daily_tbr = []
        daily_tar = []
        daily_mean_g = []

        for d in range(n_days):
            s = d * STEPS_PER_DAY
            e = s + STEPS_PER_DAY
            day_gly = gly[s:e]
            day_g = glucose[s:e]

            valid_g = day_g[~np.isnan(day_g)]
            valid_gly = day_gly[~np.isnan(day_gly)]

            if len(valid_g) < STEPS_PER_DAY * 0.7:
                daily_gly.append(np.nan)
                daily_tir.append(np.nan)
                daily_tbr.append(np.nan)
                daily_tar.append(np.nan)
                daily_mean_g.append(np.nan)
                continue

            daily_gly.append(float(np.mean(valid_gly)) if len(valid_gly) > 0 else np.nan)
            daily_tir.append(float(np.mean((valid_g >= LOW) & (valid_g <= HIGH))))
            daily_tbr.append(float(np.mean(valid_g < LOW)))
            daily_tar.append(float(np.mean(valid_g > HIGH)))
            daily_mean_g.append(float(np.mean(valid_g)))

        daily_gly = np.array(daily_gly)
        daily_tir = np.array(daily_tir)
        daily_tbr = np.array(daily_tbr)
        daily_tar = np.array(daily_tar)

        # Test: does today's glycogen predict TOMORROW's outcomes?
        valid_pairs = (~np.isnan(daily_gly[:-1])) & (~np.isnan(daily_tir[1:]))
        if valid_pairs.sum() < 10:
            results.append({'name': name, 'n_days': n_days, 'status': 'insufficient_pairs'})
            continue

        today_gly = daily_gly[:-1][valid_pairs]
        tomorrow_tir = daily_tir[1:][valid_pairs]
        tomorrow_tbr = daily_tbr[1:][valid_pairs]

        r_tir, p_tir = stats.spearmanr(today_gly, tomorrow_tir)
        r_tbr, p_tbr = stats.spearmanr(today_gly, tomorrow_tbr)

        results.append({
            'name': name,
            'n_days': n_days,
            'n_valid_pairs': int(valid_pairs.sum()),
            'gly_to_next_tir_r': float(r_tir),
            'gly_to_next_tir_p': float(p_tir),
            'gly_to_next_tbr_r': float(r_tbr),
            'gly_to_next_tbr_p': float(p_tbr),
            'mean_daily_glycogen': float(np.nanmean(daily_gly)),
            'glycogen_daily_cv': float(np.nanstd(daily_gly) / max(np.nanmean(daily_gly), 0.01)),
        })

        print(f"  {name}: gly→TIR r={r_tir:.3f} (p={p_tir:.2e}), "
              f"gly→TBR r={r_tbr:.3f} (p={p_tbr:.2e})")

    valid = [r for r in results if r.get('gly_to_next_tir_r') is not None]
    if valid:
        mean_tir_r = np.mean([r['gly_to_next_tir_r'] for r in valid])
        mean_tbr_r = np.mean([r['gly_to_next_tbr_r'] for r in valid])
        tir_sig = sum(1 for r in valid if r['gly_to_next_tir_p'] < 0.05)
        print(f"\n  Population: gly→TIR mean r={mean_tir_r:.3f} ({tir_sig}/{len(valid)} sig)")
        print(f"  Population: gly→TBR mean r={mean_tbr_r:.3f}")

    exp_result = {
        'experiment': 'EXP-1788',
        'title': 'Multi-Day Glycogen Dynamics',
        'n_patients': len(results),
        'n_valid': len(valid) if valid else 0,
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1788_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1789_metabolic_context_r2(patients):
    """Supply/demand R² decomposed by metabolic context.

    Which contexts does the model predict well vs poorly?
    """
    print("\n=== EXP-1789: Metabolic Context Supply/Demand R² ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0) if 'bolus' in df.columns else np.zeros(len(glucose))

        ctx = classify_metabolic_context(glucose, carbs, iob, bolus)

        # Actual dBG
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        # Model prediction (net flux)
        sd = compute_supply_demand(df)
        net = sd['net']

        valid = ~np.isnan(glucose) & ~np.isnan(dbg)

        context_r2 = {}
        for c_idx, c_name in enumerate(CONTEXT_NAMES):
            mask = valid & (ctx == c_idx)
            n = mask.sum()
            if n < 50:
                context_r2[c_name] = {'n': int(n), 'r2': None, 'rmse': None}
                continue

            actual = dbg[mask]
            predicted = net[mask]

            ss_res = np.sum((actual - predicted) ** 2)
            ss_tot = np.sum((actual - np.mean(actual)) ** 2)
            r2 = 1.0 - ss_res / max(ss_tot, 1e-10)
            rmse = np.sqrt(np.mean((actual - predicted) ** 2))

            context_r2[c_name] = {
                'n': int(n),
                'r2': float(r2),
                'rmse': float(rmse),
                'fraction': float(n / valid.sum()),
                'mean_abs_dbg': float(np.mean(np.abs(actual))),
                'mean_abs_net': float(np.mean(np.abs(predicted))),
            }

        results.append({
            'name': name,
            'context_r2': context_r2,
        })

        best_ctx = max(context_r2.items(),
                       key=lambda x: x[1].get('r2', -999) if x[1].get('r2') is not None else -999)
        worst_ctx = min(context_r2.items(),
                        key=lambda x: x[1].get('r2', 999) if x[1].get('r2') is not None else 999)
        print(f"  {name}: best={best_ctx[0]} R²={best_ctx[1].get('r2', 'N/A'):.3f}, "
              f"worst={worst_ctx[0]} R²={worst_ctx[1].get('r2', 'N/A'):.3f}"
              if best_ctx[1].get('r2') is not None and worst_ctx[1].get('r2') is not None
              else f"  {name}: computed")

    # Population summary by context
    print(f"\n  Context-level R² (population mean):")
    for c_name in CONTEXT_NAMES:
        r2s = [r['context_r2'][c_name]['r2'] for r in results
               if r['context_r2'][c_name].get('r2') is not None]
        ns = [r['context_r2'][c_name]['n'] for r in results
              if r['context_r2'][c_name].get('n', 0) > 0]
        if r2s:
            print(f"    {c_name:20s}: R²={np.mean(r2s):+.3f} (n={int(np.mean(ns)):,})")

    exp_result = {
        'experiment': 'EXP-1789',
        'title': 'Metabolic Context Supply/Demand R²',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1789_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


def exp_1790_residual_variance_decomposition(patients):
    """Partition model residual into component sources.

    How much of the unexplained variance comes from each factor?
    Uses sequential R² improvement (add each factor and measure gain).
    """
    print("\n=== EXP-1790: Residual Variance Decomposition ===")
    results = []

    for pat in patients:
        df = pat['df']
        name = pat['name']
        glucose = df['glucose'].values.astype(np.float64)
        iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Actual dBG
        dbg = np.zeros_like(glucose)
        dbg[1:] = glucose[1:] - glucose[:-1]

        sd = compute_supply_demand(df)
        net = sd['net']

        gly = compute_glycogen_proxy(glucose, carbs, iob)

        # Hours for circadian
        if hasattr(df.index, 'hour'):
            hours = (df.index.hour + df.index.minute / 60.0).values
        else:
            hours = np.zeros(len(glucose))

        valid = ~np.isnan(glucose) & ~np.isnan(dbg) & ~np.isnan(gly)
        valid[0] = False  # dbg undefined at 0

        if valid.sum() < 200:
            results.append({'name': name, 'status': 'insufficient'})
            continue

        actual = dbg[valid]
        model_net = net[valid]

        # Base model residual
        residual_base = actual - model_net
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        ss_res_base = np.sum(residual_base ** 2)
        r2_base = 1.0 - ss_res_base / max(ss_tot, 1e-10)

        # Factor 1: Glycogen state (linear correction)
        gly_valid = gly[valid]
        # Fit: residual = a * glycogen + b
        A = np.column_stack([gly_valid, np.ones(len(gly_valid))])
        try:
            coeffs, _, _, _ = np.linalg.lstsq(A, residual_base, rcond=None)
            gly_correction = A @ coeffs
            ss_res_gly = np.sum((residual_base - gly_correction) ** 2)
            r2_after_gly = 1.0 - ss_res_gly / max(ss_tot, 1e-10)
            gly_improvement = r2_after_gly - r2_base
        except Exception:
            gly_improvement = 0.0
            r2_after_gly = r2_base

        # Factor 2: Circadian residual (4-harmonic fit)
        h_valid = hours[valid]
        harmonics = []
        for period in [24, 12, 8, 6]:
            harmonics.append(np.sin(2 * np.pi * h_valid / period))
            harmonics.append(np.cos(2 * np.pi * h_valid / period))
        A_circ = np.column_stack(harmonics + [np.ones(len(h_valid))])
        try:
            residual_after_gly = residual_base - gly_correction
            coeffs_c, _, _, _ = np.linalg.lstsq(A_circ, residual_after_gly, rcond=None)
            circ_correction = A_circ @ coeffs_c
            ss_res_circ = np.sum((residual_after_gly - circ_correction) ** 2)
            r2_after_circ = 1.0 - ss_res_circ / max(ss_tot, 1e-10)
            # Attribute circadian improvement relative to post-glycogen
            circ_improvement = r2_after_circ - r2_after_gly
        except Exception:
            circ_improvement = 0.0
            r2_after_circ = r2_after_gly

        # Factor 3: Rescue carb proxy (large positive residuals during hypo recovery)
        # Identify potential rescue carb windows
        near_hypo = glucose[valid] < 85
        large_positive_residual = residual_base > 2.0  # mg/dL/step
        rescue_proxy = near_hypo & large_positive_residual
        rescue_variance = np.sum(residual_base[rescue_proxy] ** 2) if rescue_proxy.sum() > 0 else 0
        rescue_fraction = rescue_variance / max(ss_res_base, 1e-10)

        # Remaining = sensor noise + unexplained
        explained_total = gly_improvement + circ_improvement
        remaining_fraction = 1.0 - (explained_total / max(abs(1.0 - r2_base), 1e-10))

        # Estimate sensor noise floor (CGM noise ~5 mg/dL → ~1 mg/dL/step variance)
        sensor_noise_var = 1.0 ** 2  # (mg/dL/step)^2
        sensor_noise_fraction = (sensor_noise_var * valid.sum()) / max(ss_res_base, 1e-10)

        results.append({
            'name': name,
            'n': int(valid.sum()),
            'r2_base': float(r2_base),
            'r2_after_glycogen': float(r2_after_gly),
            'r2_after_circadian': float(r2_after_circ),
            'glycogen_r2_gain': float(gly_improvement),
            'circadian_r2_gain': float(circ_improvement),
            'rescue_carb_fraction_of_residual': float(rescue_fraction),
            'sensor_noise_fraction_estimate': float(min(sensor_noise_fraction, 1.0)),
            'unexplained_fraction': float(max(0, remaining_fraction - sensor_noise_fraction - rescue_fraction)),
        })

        print(f"  {name}: base R²={r2_base:.3f}, +glycogen={gly_improvement:+.4f}, "
              f"+circadian={circ_improvement:+.4f}, rescue={rescue_fraction:.3f}")

    # Population summary
    valid_r = [r for r in results if r.get('r2_base') is not None]
    if valid_r:
        print(f"\n  Population residual decomposition:")
        for key in ['r2_base', 'glycogen_r2_gain', 'circadian_r2_gain',
                    'rescue_carb_fraction_of_residual', 'sensor_noise_fraction_estimate']:
            vals = [r[key] for r in valid_r]
            print(f"    {key:45s}: {np.mean(vals):+.4f}")

    exp_result = {
        'experiment': 'EXP-1790',
        'title': 'Residual Variance Decomposition',
        'n_patients': len(results),
        'patients': results,
    }
    out = RESULTS_DIR / 'exp-1790_glycogen_deconfound.json'
    out.write_text(json.dumps(exp_result, indent=2, default=str))
    print(f"  Saved: {out}")
    return exp_result


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(all_results):
    """Generate visualization figures for the experiment batch."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Figure 10: IOB-conditioned glycogen sensitivity (EXP-1783)
    r1783 = all_results.get('1783')
    if r1783:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        # Left: heatmap of glycogen→β r across patients × IOB strata
        patients = r1783['patients']
        pat_names = [p['name'] for p in patients]
        strata_names = ['Q1_low_iob', 'Q2', 'Q3', 'Q4_high_iob']
        heatmap = np.full((len(pat_names), 4), np.nan)
        for i, p in enumerate(patients):
            for j, s in enumerate(p['strata']):
                if s.get('glycogen_beta_r') is not None:
                    heatmap[i, j] = s['glycogen_beta_r']

        im = axes[0].imshow(heatmap, cmap='RdBu_r', vmin=-0.3, vmax=0.3, aspect='auto')
        axes[0].set_xticks(range(4))
        axes[0].set_xticklabels(['Q1\n(low IOB)', 'Q2', 'Q3', 'Q4\n(high IOB)'])
        axes[0].set_yticks(range(len(pat_names)))
        axes[0].set_yticklabels(pat_names)
        axes[0].set_title('Glycogen→β Spearman r\n(IOB-conditioned)')
        plt.colorbar(im, ax=axes[0], label='r')

        # Right: summary — fraction of strata significant
        sig_by_quartile = []
        for j in range(4):
            sig = sum(1 for p in patients if len(p['strata']) > j and
                      p['strata'][j].get('glycogen_beta_p') is not None and
                      p['strata'][j]['glycogen_beta_p'] < 0.05)
            total = sum(1 for p in patients if len(p['strata']) > j and
                        p['strata'][j].get('glycogen_beta_r') is not None)
            sig_by_quartile.append(sig / max(total, 1))

        axes[1].bar(range(4), sig_by_quartile, color=['#2196F3', '#4CAF50', '#FF9800', '#F44336'])
        axes[1].set_xticks(range(4))
        axes[1].set_xticklabels(['Q1\n(low IOB)', 'Q2', 'Q3', 'Q4\n(high IOB)'])
        axes[1].set_ylabel('Fraction significant (p<0.05)')
        axes[1].set_title('Glycogen→β significance\nby IOB stratum')
        axes[1].set_ylim(0, 1)
        axes[1].axhline(0.05, color='gray', linestyle='--', label='chance')

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'glycogen-fig10-iob-conditioned.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: {FIGURES_DIR / 'glycogen-fig10-iob-conditioned.png'}")

    # Figure 11: Metabolic context R² (EXP-1789)
    r1789 = all_results.get('1789')
    if r1789:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: R² by context (population)
        ctx_r2_means = {}
        for c_name in CONTEXT_NAMES:
            r2s = [r['context_r2'][c_name]['r2'] for r in r1789['patients']
                   if r['context_r2'][c_name].get('r2') is not None]
            ctx_r2_means[c_name] = np.mean(r2s) if r2s else 0

        colors = ['#4CAF50', '#FF9800', '#2196F3', '#F44336', '#9C27B0', '#607D8B']
        bars = axes[0].bar(range(len(CONTEXT_NAMES)),
                          [ctx_r2_means[c] for c in CONTEXT_NAMES],
                          color=colors)
        axes[0].set_xticks(range(len(CONTEXT_NAMES)))
        axes[0].set_xticklabels(CONTEXT_NAMES, rotation=45, ha='right')
        axes[0].set_ylabel('R²')
        axes[0].set_title('Supply/Demand Model R²\nby Metabolic Context')
        axes[0].axhline(0, color='black', linewidth=0.5)

        # Right: fraction of time in each context
        ctx_frac = {}
        for c_name in CONTEXT_NAMES:
            fracs = [r['context_r2'][c_name].get('fraction', 0) for r in r1789['patients']
                     if r['context_r2'][c_name].get('fraction') is not None]
            ctx_frac[c_name] = np.mean(fracs) if fracs else 0

        axes[1].pie([ctx_frac[c] for c in CONTEXT_NAMES],
                   labels=CONTEXT_NAMES, colors=colors, autopct='%1.0f%%')
        axes[1].set_title('Time Distribution\nAcross Metabolic Contexts')

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'glycogen-fig11-context-r2.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: {FIGURES_DIR / 'glycogen-fig11-context-r2.png'}")

    # Figure 12: Residual variance decomposition (EXP-1790)
    r1790 = all_results.get('1790')
    if r1790:
        valid_r = [r for r in r1790['patients'] if r.get('r2_base') is not None]
        if valid_r:
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))

            # Left: stacked bar of variance components per patient
            pat_names = [r['name'] for r in valid_r]
            gly_gain = [abs(r['glycogen_r2_gain']) for r in valid_r]
            circ_gain = [abs(r['circadian_r2_gain']) for r in valid_r]
            rescue_frac = [r['rescue_carb_fraction_of_residual'] * (1 - abs(r['r2_base'])) for r in valid_r]
            noise_frac = [r['sensor_noise_fraction_estimate'] * (1 - abs(r['r2_base'])) for r in valid_r]

            x = np.arange(len(pat_names))
            w = 0.6
            axes[0].bar(x, gly_gain, w, label='Glycogen', color='#4CAF50')
            axes[0].bar(x, circ_gain, w, bottom=gly_gain, label='Circadian', color='#2196F3')
            axes[0].bar(x, rescue_frac, w,
                       bottom=[g + c for g, c in zip(gly_gain, circ_gain)],
                       label='Rescue carbs', color='#FF9800')
            axes[0].bar(x, noise_frac, w,
                       bottom=[g + c + r for g, c, r in zip(gly_gain, circ_gain, rescue_frac)],
                       label='Sensor noise', color='#9E9E9E')
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(pat_names)
            axes[0].set_ylabel('Variance fraction')
            axes[0].set_title('Residual Variance Components')
            axes[0].legend(fontsize=8)

            # Right: population mean decomposition as horizontal bar
            # (can't use pie chart because R² gains are small fractions of large negative base)
            mean_base_r2 = np.mean([r['r2_base'] for r in valid_r])
            mean_gly = np.mean(gly_gain)
            mean_circ = np.mean(circ_gain)
            mean_rescue = np.mean(rescue_frac)
            mean_noise = np.mean(noise_frac)

            labels = ['Base model\n(S×D)', '+Glycogen', '+Circadian',
                      'Rescue carbs\n(residual frac)', 'Sensor noise\n(estimate)']
            vals = [mean_base_r2, mean_gly, mean_circ, mean_rescue, mean_noise]
            colors_bar = ['#F44336', '#4CAF50', '#2196F3', '#FF9800', '#9E9E9E']
            axes[1].barh(range(len(labels)), vals, color=colors_bar)
            axes[1].set_yticks(range(len(labels)))
            axes[1].set_yticklabels(labels)
            axes[1].set_xlabel('R² / fraction')
            axes[1].set_title('Population Mean\nVariance Decomposition')
            axes[1].axvline(0, color='black', linewidth=0.5)

            plt.tight_layout()
            fig.savefig(FIGURES_DIR / 'glycogen-fig12-variance-decomposition.png', dpi=150)
            plt.close(fig)
            print(f"  Saved: {FIGURES_DIR / 'glycogen-fig12-variance-decomposition.png'}")

    # Figure 13: Counter-reg by glycogen (EXP-1787) + natural experiment (EXP-1785)
    r1787 = all_results.get('1787')
    r1785 = all_results.get('1785')
    if r1787 or r1785:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        if r1787:
            valid = [r for r in r1787['patients'] if r.get('spearman_r') is not None]
            names = [r['name'] for r in valid]
            rs = [r['spearman_r'] for r in valid]
            colors = ['#F44336' if r['spearman_p'] < 0.05 else '#9E9E9E' for r in valid]
            axes[0].barh(range(len(names)), rs, color=colors)
            axes[0].set_yticks(range(len(names)))
            axes[0].set_yticklabels(names)
            axes[0].set_xlabel('Spearman r (glycogen → recovery rate)')
            axes[0].set_title('Counter-Regulatory Capacity\nvs Glycogen State')
            axes[0].axvline(0, color='black', linewidth=0.5)

        if r1785:
            valid = [r for r in r1785['patients']
                     if r.get('depleted_delta_g_2h') is not None]
            if valid:
                names = [r['name'] for r in valid]
                dep_dg = [r['depleted_delta_g_2h'] for r in valid]
                load_dg = [r['loaded_delta_g_2h'] for r in valid]
                x = np.arange(len(names))
                w = 0.35
                axes[1].bar(x - w/2, dep_dg, w, label='Depleted (exercise-like)',
                           color='#2196F3')
                axes[1].bar(x + w/2, load_dg, w, label='Loaded (post-feast)',
                           color='#FF9800')
                axes[1].set_xticks(x)
                axes[1].set_xticklabels(names)
                axes[1].set_ylabel('ΔGlucose 2h (mg/dL)')
                axes[1].set_title('Next-2h Glucose Change\nby Metabolic State')
                axes[1].legend()
                axes[1].axhline(0, color='black', linewidth=0.5)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / 'glycogen-fig13-counter-reg-natural.png', dpi=150)
        plt.close(fig)
        print(f"  Saved: {FIGURES_DIR / 'glycogen-fig13-counter-reg-natural.png'}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-1783–1790: Glycogen Deconfounding')
    parser.add_argument('--figures', action='store_true', help='Generate visualization figures')
    parser.add_argument('--experiments', type=str, default='all',
                        help='Comma-separated experiment numbers or "all"')
    args = parser.parse_args()

    print("Loading patient data...")
    patients = load_patients(str(PATIENTS_DIR))

    exp_map = {
        '1783': exp_1783_iob_conditioned_glycogen,
        '1784': exp_1784_glucose_free_proxy,
        '1785': exp_1785_natural_experiment_contexts,
        '1786': exp_1786_glycogen_cascade_patterns,
        '1787': exp_1787_counter_reg_by_glycogen,
        '1788': exp_1788_multiday_glycogen,
        '1789': exp_1789_metabolic_context_r2,
        '1790': exp_1790_residual_variance_decomposition,
    }

    if args.experiments == 'all':
        to_run = list(exp_map.keys())
    else:
        to_run = [e.strip() for e in args.experiments.split(',')]

    all_results = {}
    for exp_id in to_run:
        if exp_id in exp_map:
            result = exp_map[exp_id](patients)
            all_results[exp_id] = result
        else:
            print(f"  Unknown experiment: {exp_id}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(all_results)

    print("\n=== All experiments complete ===")


if __name__ == '__main__':
    main()
