#!/usr/bin/env python3
"""
EXP-2734: Autocorrelation-Corrected Residuals for Settings Assessment
======================================================================

EXP-2719b showed 96% of patients have significant residuals from the
population model. But correction events closer than 2h share overlapping
insulin activity windows (DIA=4-6h), meaning residuals may be autocorrelated.
Autocorrelation inflates significance (p-values too small) and can bias
per-patient correction factors.

This experiment:
1. Reproduces EXP-2719b as baseline
2. Applies 2h minimum spacing subsampling (truly independent events)
3. Compares correction factors: correlated vs independent
4. Tests whether autocorrelation materially changes settings recommendations

If correction factors are stable under subsampling → 2719b results are robust.
If they shift → autocorrelation was biasing and we need the subsampled version.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.deconfounding import STEPS_PER_HOUR

EXP_ID = "2734"
TITLE = "Autocorrelation-Corrected Residuals for Settings Assessment"

BG_FLOOR = 150.0
HORIZONS = [2, 4, 6]
MIN_SPACING_H = 2.0  # Minimum hours between independent events

# EGP model (same as 2719b for reproducibility)
HILL_N = 1.5
HILL_K = 2.0
BASE_EGP = 1.5
CIRCADIAN_AMP = 0.15


def estimate_egp_per_step(iob: float, hour: float) -> float:
    iob_safe = max(float(np.nan_to_num(iob, nan=0.0)), 0.0)
    suppression = iob_safe ** HILL_N / (iob_safe ** HILL_N + HILL_K ** HILL_N) if iob_safe > 0 else 0.0
    egp_base = BASE_EGP * (1.0 - suppression)
    circadian = 1.0 + CIRCADIAN_AMP * np.sin(2.0 * np.pi * (hour - 5.0) / 24.0)
    return max(egp_base * circadian, 0.0)


def extract_events(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract correction events with multi-horizon features (same as 2719b)."""
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_iob = "iob" in grid.columns
    has_isf = "scheduled_isf" in grid.columns

    max_h_steps = int(max(HORIZONS) * STEPS_PER_HOUR)
    all_events = []

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < max_h_steps + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        controller = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        for i in range(len(pg) - max_h_steps):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue
            if "carbs" in pg.columns:
                c_start = max(0, i - STEPS_PER_HOUR)
                c_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            event = {
                "patient_id": pid,
                "controller": controller,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "roc_start": float((glucose[i] - glucose[max(0, i - 3)]) / 3 * STEPS_PER_HOUR) if i >= 3 else 0.0,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "profile_isf": float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan,
                "user_bolus": float(bolus[i]),
            }

            for h in HORIZONS:
                h_steps = int(h * STEPS_PER_HOUR)
                end_idx = i + h_steps
                bg_end = glucose[end_idx]
                if np.isnan(bg_end):
                    continue
                hk = f"{h}h"

                observed_drop = bg0 - bg_end
                event[f"observed_drop_{hk}"] = float(observed_drop)

                bolus_total = float(np.nansum(bolus[i:end_idx]))
                smb_total = float(np.nansum(smb[i:end_idx]))
                net_basal_total = float(np.nansum(net_basal[i:end_idx])) / STEPS_PER_HOUR
                excess_insulin = bolus_total + smb_total + net_basal_total
                event[f"excess_insulin_{hk}"] = excess_insulin
                event[f"bg0_centered_{hk}"] = bg0 - 120.0

                egp_total = 0.0
                for k in range(h_steps):
                    iob_k = float(iob[i + k]) if not np.isnan(iob[i + k]) else 0.0
                    hour_k = float(hours[i + k]) if i + k < len(hours) else hours[i]
                    egp_total += estimate_egp_per_step(iob_k, hour_k)
                event[f"egp_headwind_{hk}"] = egp_total

            all_events.append(event)

    return pd.DataFrame(all_events)


def subsample_independent(df: pd.DataFrame, min_spacing_steps: int) -> pd.DataFrame:
    """Subsample events per patient to enforce minimum spacing.

    Greedy forward pass: keep earliest event, skip any within min_spacing_steps,
    then keep next eligible event, etc. This maximizes N while ensuring independence.
    """
    independent = []
    for pid in sorted(df["patient_id"].unique()):
        pev = df[df["patient_id"] == pid].sort_values("idx").reset_index(drop=True)
        last_idx = -min_spacing_steps - 1
        for _, row in pev.iterrows():
            if row["idx"] - last_idx >= min_spacing_steps:
                independent.append(row)
                last_idx = row["idx"]
    if not independent:
        return pd.DataFrame()
    return pd.DataFrame(independent)


def fit_population_model(df: pd.DataFrame, horizon: int):
    """Fit population OLS model, return residuals."""
    hk = f"{horizon}h"
    drop_col = f"observed_drop_{hk}"
    exc_col = f"excess_insulin_{hk}"
    egp_col = f"egp_headwind_{hk}"
    bg0_col = f"bg0_centered_{hk}"

    needed = [drop_col, exc_col, egp_col, bg0_col, "roc_start", "iob_start"]
    valid = df.dropna(subset=[c for c in needed if c in df.columns]).copy()
    if len(valid) < 50:
        return None, None, None

    features = [exc_col, egp_col, bg0_col, "roc_start", "iob_start"]
    X = valid[features].values
    y = valid[drop_col].values

    X_aug = np.column_stack([X, np.ones(len(X))])
    b, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    y_pred = X_aug @ b
    valid["residual"] = y - y_pred
    valid["predicted"] = y_pred

    coefs = {features[i]: float(b[i]) for i in range(len(features))}
    coefs["intercept"] = float(b[-1])

    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return valid, coefs, r2


def per_patient_analysis(valid: pd.DataFrame, horizon: int):
    """Per-patient residual statistics."""
    hk = f"{horizon}h"
    results = []
    for pid in valid["patient_id"].unique():
        pv = valid[valid["patient_id"] == pid]
        if len(pv) < 5:  # Relaxed from 10 for subsampled data
            continue

        resid = pv["residual"].values
        observed = pv[f"observed_drop_{hk}"].values
        predicted = pv["predicted"].values
        excess = pv[f"excess_insulin_{hk}"].values

        mean_resid = float(np.mean(resid))
        se_resid = float(np.std(resid) / np.sqrt(len(resid)))
        t_stat = mean_resid / se_resid if se_resid > 0 else 0.0
        p_val = float(2 * stats.t.sf(abs(t_stat), len(resid) - 1)) if len(resid) > 1 else 1.0

        isf_vals = pv["profile_isf"].values
        profile_isf = float(np.nanmedian(isf_vals))

        mean_predicted = float(np.mean(predicted))
        mean_observed = float(np.mean(observed))
        correction_factor = mean_observed / mean_predicted if mean_predicted > 0 else 1.0

        mean_excess = float(np.mean(excess))
        empirical_isf = mean_observed / mean_excess if mean_excess > 0.1 else np.nan

        # Autocorrelation of residuals (Durbin-Watson-like)
        if len(resid) > 3:
            lag1_corr, lag1_p = stats.pearsonr(resid[:-1], resid[1:])
        else:
            lag1_corr, lag1_p = 0.0, 1.0

        results.append({
            "patient_id": pid,
            "controller": pv["controller"].iloc[0],
            "n_events": len(pv),
            "profile_isf": profile_isf,
            "mean_residual": mean_resid,
            "se_residual": se_resid,
            "p_value": p_val,
            "significant": p_val < 0.05,
            "mean_observed_drop": mean_observed,
            "mean_predicted_drop": mean_predicted,
            "correction_factor": correction_factor,
            "empirical_isf": empirical_isf,
            "mean_excess_insulin": mean_excess,
            "lag1_autocorr": float(lag1_corr),
            "lag1_autocorr_p": float(lag1_p),
            "direction": "ISF_too_high" if mean_resid > 0 else "ISF_too_low",
            "recommendation": (
                f"↓ ISF by {abs(1 - correction_factor) * 100:.0f}%" if correction_factor > 1.1
                else f"↑ ISF by {abs(1 - correction_factor) * 100:.0f}%" if correction_factor < 0.9
                else "Settings OK (±10%)"
            ),
        })

    return pd.DataFrame(results)


def compare_arms(baseline_pats: pd.DataFrame, independent_pats: pd.DataFrame, horizon: str):
    """Compare correction factors between baseline and independent-subsampled arms."""
    common_pids = set(baseline_pats["patient_id"]) & set(independent_pats["patient_id"])
    if len(common_pids) < 5:
        return {}

    bl = baseline_pats[baseline_pats["patient_id"].isin(common_pids)].set_index("patient_id")
    ind = independent_pats[independent_pats["patient_id"].isin(common_pids)].set_index("patient_id")

    cf_bl = bl.loc[sorted(common_pids), "correction_factor"].values
    cf_ind = ind.loc[sorted(common_pids), "correction_factor"].values

    r_cf, p_cf = stats.pearsonr(cf_bl, cf_ind)
    mae_cf = float(np.mean(np.abs(cf_bl - cf_ind)))
    max_shift = float(np.max(np.abs(cf_bl - cf_ind)))
    mean_shift = float(np.mean(cf_ind - cf_bl))

    # How many patients change recommendation category?
    def categorize(cf):
        if cf > 1.1:
            return "decrease"
        elif cf < 0.9:
            return "increase"
        return "ok"

    cat_bl = [categorize(c) for c in cf_bl]
    cat_ind = [categorize(c) for c in cf_ind]
    n_changed = sum(1 for a, b in zip(cat_bl, cat_ind) if a != b)

    # Paired t-test on correction factors
    t_stat, p_paired = stats.ttest_rel(cf_bl, cf_ind)

    return {
        "n_common_patients": len(common_pids),
        "r_correction_factor": float(r_cf),
        "p_correlation": float(p_cf),
        "mae_correction_factor": mae_cf,
        "max_shift": max_shift,
        "mean_shift": mean_shift,
        "n_recommendation_changed": n_changed,
        "paired_t_stat": float(t_stat),
        "paired_p_value": float(p_paired),
    }


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    grid = pd.read_parquet(data_path)
    print(f"Loaded {grid.shape[0]} rows × {grid.shape[1]} cols, {grid['patient_id'].nunique()} patients")

    # ── Extract all events ───────────────────────────────────────
    df_all = extract_events(grid)
    print(f"Extracted {len(df_all)} total events, {df_all['patient_id'].nunique()} patients")

    # ── Subsample to independent events ──────────────────────────
    min_spacing_steps = int(MIN_SPACING_H * STEPS_PER_HOUR)
    df_ind = subsample_independent(df_all, min_spacing_steps)
    print(f"Independent events (≥{MIN_SPACING_H}h spacing): {len(df_ind)} ({len(df_ind)/len(df_all)*100:.0f}% retained)")

    # ── Per-patient event counts ─────────────────────────────────
    for pid in sorted(df_all["patient_id"].unique()):
        n_all = len(df_all[df_all["patient_id"] == pid])
        n_ind = len(df_ind[df_ind["patient_id"] == pid]) if len(df_ind) > 0 else 0
        print(f"  {pid[:12]:<14} {n_all:>5} → {n_ind:>5} ({n_ind/max(n_all,1)*100:.0f}%)")

    all_results = {}

    for h in HORIZONS:
        hk = f"{h}h"
        print(f"\n{'=' * 60}")
        print(f"  Horizon: {hk}")
        print(f"{'=' * 60}")

        # ── ARM 1: All events (baseline, reproducing 2719b) ──────
        print(f"\n  ARM 1: All events (baseline)")
        valid_all, coefs_all, r2_all = fit_population_model(df_all, h)
        if valid_all is None:
            print(f"  Skipping {hk} — insufficient data")
            continue
        pats_all = per_patient_analysis(valid_all, h)
        print(f"  Population R² = {r2_all:.4f}, N = {len(valid_all)}")
        print(f"  {pats_all['significant'].sum()}/{len(pats_all)} patients significant")

        # Autocorrelation diagnostics for baseline
        mean_lag1 = pats_all["lag1_autocorr"].mean()
        sig_autocorr = (pats_all["lag1_autocorr_p"] < 0.05).sum()
        print(f"  Lag-1 autocorrelation: mean r={mean_lag1:.3f}, {sig_autocorr}/{len(pats_all)} significant")

        # ── ARM 2: Independent events (2h subsampled) ────────────
        print(f"\n  ARM 2: Independent events (≥{MIN_SPACING_H}h)")
        valid_ind, coefs_ind, r2_ind = fit_population_model(df_ind, h)
        if valid_ind is None:
            print(f"  Skipping independent arm — insufficient data")
            continue
        pats_ind = per_patient_analysis(valid_ind, h)
        print(f"  Population R² = {r2_ind:.4f}, N = {len(valid_ind)}")
        print(f"  {pats_ind['significant'].sum()}/{len(pats_ind)} patients significant")

        # Autocorrelation diagnostics for independent
        mean_lag1_ind = pats_ind["lag1_autocorr"].mean()
        sig_autocorr_ind = (pats_ind["lag1_autocorr_p"] < 0.05).sum()
        print(f"  Lag-1 autocorrelation: mean r={mean_lag1_ind:.3f}, {sig_autocorr_ind}/{len(pats_ind)} significant")

        # ── Compare arms ─────────────────────────────────────────
        comp = compare_arms(pats_all, pats_ind, hk)
        if comp:
            print(f"\n  COMPARISON (all vs independent):")
            print(f"    Correction factor correlation: r={comp['r_correction_factor']:.3f}")
            print(f"    MAE of correction factors: {comp['mae_correction_factor']:.3f}")
            print(f"    Max shift: {comp['max_shift']:.3f}")
            print(f"    Mean shift: {comp['mean_shift']:+.3f}")
            print(f"    Recommendations changed: {comp['n_recommendation_changed']}/{comp['n_common_patients']}")
            print(f"    Paired t-test: t={comp['paired_t_stat']:.3f}, p={comp['paired_p_value']:.4f}")

        # ── Coefficient comparison ────────────────────────────────
        print(f"\n  COEFFICIENTS COMPARISON:")
        print(f"    {'Feature':<30} {'Baseline':>10} {'Independent':>12}")
        print(f"    {'-'*55}")
        for feat in coefs_all:
            c_all = coefs_all.get(feat, 0)
            c_ind = coefs_ind.get(feat, 0) if coefs_ind else 0
            print(f"    {feat:<30} {c_all:>10.4f} {c_ind:>12.4f}")

        # ── Patient detail table ──────────────────────────────────
        if comp:
            common = set(pats_all["patient_id"]) & set(pats_ind["patient_id"])
            bl_map = pats_all.set_index("patient_id")
            ind_map = pats_ind.set_index("patient_id")
            print(f"\n  {'Patient':<12} {'N_all':>6} {'N_ind':>6} {'CF_all':>7} {'CF_ind':>7} {'Shift':>7} {'AC_r':>6} {'Changed':>8}")
            print(f"  {'-'*65}")
            for pid in sorted(common):
                cf_all = bl_map.loc[pid, "correction_factor"]
                cf_ind = ind_map.loc[pid, "correction_factor"]
                n_all = bl_map.loc[pid, "n_events"]
                n_ind = ind_map.loc[pid, "n_events"]
                ac_r = bl_map.loc[pid, "lag1_autocorr"]
                changed = "YES" if (cf_all > 1.1) != (cf_ind > 1.1) or (cf_all < 0.9) != (cf_ind < 0.9) else ""
                print(f"  {str(pid)[:10]:<12} {n_all:>6} {n_ind:>6} {cf_all:>7.2f} {cf_ind:>7.2f} {cf_ind - cf_all:>+7.3f} {ac_r:>6.2f} {changed:>8}")

        all_results[hk] = {
            "baseline": {
                "r2": float(r2_all),
                "n_events": len(valid_all),
                "coefficients": coefs_all,
                "n_patients": len(pats_all),
                "n_significant": int(pats_all["significant"].sum()),
                "mean_lag1_autocorr": float(mean_lag1),
                "n_sig_autocorr": int(sig_autocorr),
                "per_patient": pats_all.to_dict(orient="records"),
            },
            "independent": {
                "r2": float(r2_ind),
                "n_events": len(valid_ind),
                "coefficients": coefs_ind,
                "n_patients": len(pats_ind),
                "n_significant": int(pats_ind["significant"].sum()),
                "mean_lag1_autocorr": float(mean_lag1_ind),
                "n_sig_autocorr": int(sig_autocorr_ind),
                "per_patient": pats_ind.to_dict(orient="records"),
            },
            "comparison": comp,
        }

    # ── Hypotheses ───────────────────────────────────────────────
    h2_data = all_results.get("2h", {})
    comp_2h = h2_data.get("comparison", {})

    # H1: Baseline shows significant autocorrelation (>30% of patients have lag-1 r sig)
    bl_autocorr = h2_data.get("baseline", {}).get("n_sig_autocorr", 0)
    bl_npats = h2_data.get("baseline", {}).get("n_patients", 1)
    h1_pass = bl_autocorr > bl_npats * 0.3

    # H2: Subsampling reduces autocorrelation (mean lag-1 r decreases)
    bl_mean_ac = h2_data.get("baseline", {}).get("mean_lag1_autocorr", 0)
    ind_mean_ac = h2_data.get("independent", {}).get("mean_lag1_autocorr", 0)
    h2_pass = abs(ind_mean_ac) < abs(bl_mean_ac)

    # H3: Correction factors are stable (r > 0.8 between arms)
    h3_pass = comp_2h.get("r_correction_factor", 0) > 0.8

    # H4: Few patients change recommendation category (<20%)
    n_changed = comp_2h.get("n_recommendation_changed", 999)
    n_common = comp_2h.get("n_common_patients", 1)
    h4_pass = n_changed < n_common * 0.2

    # H5: No systematic shift (paired t-test p > 0.05)
    h5_pass = comp_2h.get("paired_p_value", 0) > 0.05

    hypotheses = {
        "H1_baseline_has_autocorrelation": bool(h1_pass),
        "H2_subsampling_reduces_autocorr": bool(h2_pass),
        "H3_correction_factors_stable": bool(h3_pass),
        "H4_few_recommendations_change": bool(h4_pass),
        "H5_no_systematic_shift": bool(h5_pass),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    # Interpretation
    print(f"\nINTERPRETATION:")
    if h3_pass and h4_pass:
        print("  ✅ 2719b correction factors are ROBUST to autocorrelation.")
        print("  The subsampled (independent) estimates agree well with full-data estimates.")
        print("  → Safe to use full-data correction factors for settings recommendations.")
    elif h3_pass and not h4_pass:
        print("  ⚠️  Factors correlate well but some patients change category.")
        print("  → Consider using subsampled factors for borderline patients.")
    else:
        print("  ❌ Autocorrelation materially biases correction factors.")
        print("  → Must use subsampled (independent) events for settings assessment.")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"N_all={len(df_all)}, N_ind={len(df_ind)} "
               f"({len(df_ind)/max(len(df_all),1)*100:.0f}% retained). "
               f"CF correlation r={comp_2h.get('r_correction_factor', 0):.3f}")
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # ── Save ─────────────────────────────────────────────────────
    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_autocorr_residuals.json"

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(clean({"exp_id": EXP_ID, "title": TITLE,
                          "hypotheses": hypotheses, "results": all_results,
                          "summary": summary}), f, indent=2)
    print(f"Saved: {out_path}")

    # Dashboard
    create_dashboard(all_results, hypotheses, df_all, df_ind)

    return hypotheses, all_results


def create_dashboard(all_results, hypotheses, df_all, df_ind):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 14))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Row 1: Correction factor scatter (baseline vs independent) for each horizon
    for idx, h in enumerate(HORIZONS):
        hk = f"{h}h"
        data = all_results.get(hk, {})
        comp = data.get("comparison", {})
        bl_pats = pd.DataFrame(data.get("baseline", {}).get("per_patient", []))
        ind_pats = pd.DataFrame(data.get("independent", {}).get("per_patient", []))
        if bl_pats.empty or ind_pats.empty:
            continue

        common = set(bl_pats["patient_id"]) & set(ind_pats["patient_id"])
        if len(common) < 3:
            continue

        bl = bl_pats[bl_pats["patient_id"].isin(common)].set_index("patient_id")
        ind = ind_pats[ind_pats["patient_id"].isin(common)].set_index("patient_id")
        pids = sorted(common)

        ax = fig.add_subplot(gs[0, idx])
        cf_bl = [bl.loc[p, "correction_factor"] for p in pids]
        cf_ind = [ind.loc[p, "correction_factor"] for p in pids]
        ax.scatter(cf_bl, cf_ind, color="steelblue", alpha=0.7, s=50)
        lims = [min(min(cf_bl), min(cf_ind)) * 0.9, max(max(cf_bl), max(cf_ind)) * 1.1]
        ax.plot(lims, lims, "r--", linewidth=1, label="1:1")
        r_val = comp.get("r_correction_factor", 0)
        ax.set_xlabel("Baseline CF")
        ax.set_ylabel("Independent CF")
        ax.set_title(f"{hk}: CF Comparison (r={r_val:.3f})")
        ax.legend(fontsize=8)

    # Row 2: Autocorrelation diagnostics
    # Panel 4: Lag-1 autocorrelation distribution (baseline)
    ax4 = fig.add_subplot(gs[1, 0])
    data_2h = all_results.get("2h", {})
    if data_2h:
        bl_pats = pd.DataFrame(data_2h.get("baseline", {}).get("per_patient", []))
        if not bl_pats.empty:
            ax4.hist(bl_pats["lag1_autocorr"], bins=20, color="salmon", edgecolor="white", alpha=0.8, label="Baseline")
            ind_pats = pd.DataFrame(data_2h.get("independent", {}).get("per_patient", []))
            if not ind_pats.empty:
                ax4.hist(ind_pats["lag1_autocorr"], bins=20, color="steelblue", edgecolor="white", alpha=0.6, label="Independent")
            ax4.axvline(0, color="black", linewidth=0.5)
            ax4.set_xlabel("Lag-1 Autocorrelation")
            ax4.set_ylabel("Patients")
            ax4.set_title("2h: Residual Autocorrelation")
            ax4.legend(fontsize=8)

    # Panel 5: N events baseline vs independent per patient
    ax5 = fig.add_subplot(gs[1, 1])
    if data_2h:
        bl_pats = pd.DataFrame(data_2h.get("baseline", {}).get("per_patient", []))
        ind_pats = pd.DataFrame(data_2h.get("independent", {}).get("per_patient", []))
        if not bl_pats.empty and not ind_pats.empty:
            common = set(bl_pats["patient_id"]) & set(ind_pats["patient_id"])
            if common:
                bl = bl_pats[bl_pats["patient_id"].isin(common)].set_index("patient_id")
                ind = ind_pats[ind_pats["patient_id"].isin(common)].set_index("patient_id")
                pids = sorted(common)
                n_bl = [bl.loc[p, "n_events"] for p in pids]
                n_ind = [ind.loc[p, "n_events"] for p in pids]
                x = range(len(pids))
                ax5.bar([i - 0.2 for i in x], n_bl, 0.4, color="salmon", label="Baseline")
                ax5.bar([i + 0.2 for i in x], n_ind, 0.4, color="steelblue", label="Independent")
                ax5.set_xticks(list(x))
                ax5.set_xticklabels([str(p)[:6] for p in pids], rotation=45, fontsize=7)
                ax5.set_ylabel("N events")
                ax5.set_title("Events: Baseline vs Independent")
                ax5.legend(fontsize=8)

    # Panel 6: Shift in correction factors
    ax6 = fig.add_subplot(gs[1, 2])
    if data_2h:
        comp = data_2h.get("comparison", {})
        bl_pats = pd.DataFrame(data_2h.get("baseline", {}).get("per_patient", []))
        ind_pats = pd.DataFrame(data_2h.get("independent", {}).get("per_patient", []))
        if not bl_pats.empty and not ind_pats.empty:
            common = set(bl_pats["patient_id"]) & set(ind_pats["patient_id"])
            if common:
                bl = bl_pats[bl_pats["patient_id"].isin(common)].set_index("patient_id")
                ind = ind_pats[ind_pats["patient_id"].isin(common)].set_index("patient_id")
                pids = sorted(common)
                shifts = [ind.loc[p, "correction_factor"] - bl.loc[p, "correction_factor"] for p in pids]
                colors = ["red" if abs(s) > 0.1 else "steelblue" for s in shifts]
                ax6.bar(range(len(pids)), shifts, color=colors, alpha=0.7)
                ax6.axhline(0, color="black", linewidth=0.5)
                ax6.set_xticks(range(len(pids)))
                ax6.set_xticklabels([str(p)[:6] for p in pids], rotation=45, fontsize=7)
                ax6.set_ylabel("CF Shift (ind - baseline)")
                ax6.set_title("Correction Factor Shift per Patient")

    # Row 3: Summary panel
    ax7 = fig.add_subplot(gs[2, :])
    ax7.axis("off")
    lines = [f"EXP-{EXP_ID}: Autocorrelation-Corrected Residuals", ""]
    lines.append(f"Total events: {len(df_all)} → Independent: {len(df_ind)} "
                 f"({len(df_ind)/max(len(df_all),1)*100:.0f}% retained, ≥{MIN_SPACING_H}h spacing)")
    lines.append("")
    for hk in ["2h", "4h", "6h"]:
        d = all_results.get(hk, {})
        comp = d.get("comparison", {})
        if d:
            bl = d.get("baseline", {})
            ind = d.get("independent", {})
            lines.append(f"{hk}: R²(bl)={bl.get('r2', 0):.3f} vs R²(ind)={ind.get('r2', 0):.3f} | "
                        f"CF corr r={comp.get('r_correction_factor', 0):.3f} | "
                        f"Changed: {comp.get('n_recommendation_changed', '?')}/{comp.get('n_common_patients', '?')}")
    lines.append("")
    lines.append("Hypothesis Results:")
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")
    lines.append("")
    # Interpretation
    h3 = hypotheses.get("H3_correction_factors_stable", False)
    h4 = hypotheses.get("H4_few_recommendations_change", False)
    if h3 and h4:
        lines.append("→ 2719b correction factors are ROBUST to autocorrelation")
    elif h3:
        lines.append("→ Factors stable but some borderline patients shift category")
    else:
        lines.append("→ Autocorrelation materially biases — use independent events")

    ax7.text(0.05, 0.95, "\n".join(lines), transform=ax7.transAxes,
             fontsize=9, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "autocorr-residuals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
