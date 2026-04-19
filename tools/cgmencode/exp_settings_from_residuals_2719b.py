#!/usr/bin/env python3
"""
EXP-2719b: Per-Patient Settings Assessment from Waterfall Residuals
====================================================================

Builds directly on EXP-2719's extended waterfall. The population model
(BG₀ + insulin + EGP + state → observed_drop) explains R²≈0.47-0.54.
The RESIDUAL carries the signal we need for settings assessment:

If a patient's corrections consistently OVERSHOOT the population model:
  → Their ISF is too large OR their CR is wrong → controller overdoses
If they consistently UNDERSHOOT:
  → Their ISF is too small → controller underdoses

This experiment:
1. Fits the population model (from EXP-2719)
2. Extracts per-patient residuals (signed deviations)
3. Tests whether systematic residuals predict profile ISF error
4. Computes settings adjustment recommendations

Key insight: Instead of extracting ISF by DIVISION (which fails, EXP-2717/2718),
extract ISF CORRECTIONS by looking at how each patient deviates from the
population model. The residual IS the settings error signal.

Causal frame: In T1D, the controller delivers insulin based on ISF setting.
If ISF is too high, it delivers too much → bigger drops → positive residual.
If ISF is too low, it delivers too little → smaller drops → negative residual.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.deconfounding import STEPS_PER_HOUR

EXP_ID = "2719b"
TITLE = "Per-Patient Settings Assessment from Waterfall Residuals"

BG_FLOOR = 150.0
HORIZONS = [2, 4, 6]

# EGP model
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
    """Extract correction events with multi-horizon features."""
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


def fit_population_model(df: pd.DataFrame, horizon: int):
    """Fit population-level multi-factor model, return residuals per patient."""
    hk = f"{horizon}h"
    drop_col = f"observed_drop_{hk}"
    exc_col = f"excess_insulin_{hk}"
    egp_col = f"egp_headwind_{hk}"
    bg0_col = f"bg0_centered_{hk}"

    needed = [drop_col, exc_col, egp_col, bg0_col, "roc_start", "iob_start"]
    valid = df.dropna(subset=[c for c in needed if c in df.columns]).copy()
    if len(valid) < 100:
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

    # Population R²
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot

    return valid, coefs, r2


def per_patient_analysis(valid: pd.DataFrame, horizon: int):
    """Extract per-patient residual statistics for settings assessment."""
    hk = f"{horizon}h"

    results = []
    for pid in valid["patient_id"].unique():
        pv = valid[valid["patient_id"] == pid]
        if len(pv) < 10:
            continue

        resid = pv["residual"].values
        observed = pv[f"observed_drop_{hk}"].values
        predicted = pv["predicted"].values
        excess = pv[f"excess_insulin_{hk}"].values

        # Mean residual: positive = actual drop > predicted (ISF too high, or patient more insulin-sensitive)
        mean_resid = float(np.mean(resid))
        se_resid = float(np.std(resid) / np.sqrt(len(resid)))
        t_stat = mean_resid / se_resid if se_resid > 0 else 0.0
        p_val = float(2 * stats.t.sf(abs(t_stat), len(resid) - 1)) if len(resid) > 1 else 1.0

        # Profile ISF
        isf_vals = pv["profile_isf"].values
        profile_isf = float(np.nanmedian(isf_vals))

        # Residual-implied ISF correction
        # If mean_resid > 0: patient drops MORE than predicted → ISF too high OR patient more sensitive
        # ISF correction factor: (predicted + residual) / predicted
        mean_predicted = float(np.mean(predicted))
        mean_observed = float(np.mean(observed))
        if mean_predicted > 0:
            correction_factor = mean_observed / mean_predicted
        else:
            correction_factor = 1.0

        # Implied ISF: how much does each unit of excess insulin actually lower BG for this patient?
        mean_excess = float(np.mean(excess))
        if mean_excess > 0.1:
            empirical_isf = mean_observed / mean_excess
        else:
            empirical_isf = np.nan

        # Does residual correlate with dose? (confounding check)
        if len(excess) > 10 and np.std(excess) > 0:
            r_dose, p_dose = stats.pearsonr(excess, resid)
        else:
            r_dose, p_dose = 0.0, 1.0

        # Circadian structure in residual
        if "hour" in pv.columns:
            night = pv[(pv["hour"] >= 0) & (pv["hour"] < 6)]["residual"]
            day = pv[(pv["hour"] >= 10) & (pv["hour"] < 16)]["residual"]
            if len(night) > 5 and len(day) > 5:
                circadian_diff = float(night.mean() - day.mean())
            else:
                circadian_diff = 0.0
        else:
            circadian_diff = 0.0

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
            "r_dose_residual": float(r_dose),
            "circadian_residual_diff": circadian_diff,
            "direction": "ISF_too_high" if mean_resid > 0 else "ISF_too_low",
            "recommendation": (
                f"↓ ISF by {abs(1 - correction_factor) * 100:.0f}%" if correction_factor > 1.1
                else f"↑ ISF by {abs(1 - correction_factor) * 100:.0f}%" if correction_factor < 0.9
                else "Settings OK (±10%)"
            ),
        })

    return pd.DataFrame(results)


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    grid = pd.read_parquet(data_path)
    print(f"Loaded {grid.shape[0]} rows × {grid.shape[1]} cols, {grid['patient_id'].nunique()} patients")

    df = extract_events(grid)
    print(f"Extracted {len(df)} events, {df['patient_id'].nunique()} patients")

    all_results = {}
    for h in HORIZONS:
        hk = f"{h}h"
        print(f"\n{'='*50}")
        print(f"  Horizon: {hk}")
        print(f"{'='*50}")

        valid, coefs, r2 = fit_population_model(df, h)
        if valid is None:
            continue

        print(f"  Population R² = {r2:.4f}, N = {len(valid)}")
        print(f"  Coefficients:")
        for k, v in coefs.items():
            print(f"    {k}: {v:.4f}")

        pat = per_patient_analysis(valid, h)
        if len(pat) == 0:
            continue

        n_sig = pat["significant"].sum()
        n_high = (pat["direction"] == "ISF_too_high").sum()
        n_low = (pat["direction"] == "ISF_too_low").sum()
        n_ok = len(pat) - n_high - n_low + (pat["correction_factor"].between(0.9, 1.1)).sum() - len(pat)

        print(f"\n  Per-patient results ({len(pat)} patients):")
        print(f"    Significant residuals: {n_sig}/{len(pat)} ({n_sig/len(pat)*100:.0f}%)")
        print(f"    ISF too high: {n_high}, ISF too low: {n_low}")

        print(f"\n  {'Patient':<12} {'N':>5} {'ISF':>6} {'MeanResid':>10} {'p':>8} {'CorrFact':>9} {'EmpISF':>7} {'Rec':<20}")
        print(f"  {'-'*80}")
        for _, row in pat.sort_values("mean_residual", ascending=False).iterrows():
            sig_mark = "*" if row["significant"] else " "
            print(f"  {row['patient_id'][:10]:<12} {row['n_events']:>5d} {row['profile_isf']:>6.1f} "
                  f"{row['mean_residual']:>+10.1f}{sig_mark} {row['p_value']:>8.4f} "
                  f"{row['correction_factor']:>9.2f} {row['empirical_isf']:>7.1f} {row['recommendation']:<20}")

        # Cross-patient: does profile ISF predict residual direction?
        valid_isf = pat.dropna(subset=["profile_isf", "mean_residual"])
        valid_isf = valid_isf[valid_isf["profile_isf"] > 0]
        if len(valid_isf) > 5:
            r_isf, p_isf = stats.pearsonr(valid_isf["profile_isf"], valid_isf["mean_residual"])
            print(f"\n  Profile ISF → residual: r={r_isf:.3f}, p={p_isf:.4f}")
            if abs(r_isf) > 0.3:
                print(f"    {'Higher ISF settings → MORE overshoot (ISF inflated)' if r_isf > 0 else 'Higher ISF → LESS overshoot (ISF conservative)'}")
            else:
                print(f"    No strong ISF-residual relationship (r={r_isf:.3f})")
        else:
            r_isf, p_isf = np.nan, np.nan

        # Correction factor distribution
        cf = pat["correction_factor"]
        print(f"\n  Correction factor: median={cf.median():.2f}, "
              f"IQR=[{cf.quantile(0.25):.2f}, {cf.quantile(0.75):.2f}]")
        print(f"  {(cf > 1.1).sum()} patients drop MORE than predicted (consider ↓ ISF)")
        print(f"  {(cf < 0.9).sum()} patients drop LESS than predicted (consider ↑ ISF)")
        print(f"  {cf.between(0.9, 1.1).sum()} patients within ±10% (settings OK)")

        all_results[hk] = {
            "r2_population": float(r2),
            "n_events": len(valid),
            "coefficients": coefs,
            "n_patients": len(pat),
            "n_significant": int(n_sig),
            "median_correction_factor": float(cf.median()),
            "r_isf_residual": float(r_isf) if not np.isnan(r_isf) else None,
            "per_patient": pat.to_dict(orient="records"),
        }

    # ── Hypotheses ───────────────────────────────────────────────
    h2_results = all_results.get("2h", {})
    h6_results = all_results.get("6h", {})

    # H1: Majority of patients have significant residuals (settings can be improved)
    h1_pass = h2_results.get("n_significant", 0) > h2_results.get("n_patients", 1) * 0.5

    # H2: Correction factor variance is meaningful (not all ≈1.0)
    cf_data = [p["correction_factor"] for p in h2_results.get("per_patient", []) if p.get("correction_factor")]
    h2_pass = len(cf_data) > 3 and np.std(cf_data) > 0.1

    # H3: Profile ISF correlates with residual direction (higher ISF → more overshoot)
    h3_pass = h2_results.get("r_isf_residual") is not None and abs(h2_results.get("r_isf_residual", 0)) > 0.2

    # H4: Results stable across horizons (2h vs 6h correction factors correlate)
    h4_pass = False
    if h2_results and h6_results:
        pats_2h = {p["patient_id"]: p["correction_factor"] for p in h2_results.get("per_patient", [])}
        pats_6h = {p["patient_id"]: p["correction_factor"] for p in h6_results.get("per_patient", [])}
        common = set(pats_2h.keys()) & set(pats_6h.keys())
        if len(common) > 5:
            cf2 = [pats_2h[p] for p in common]
            cf6 = [pats_6h[p] for p in common]
            r_horizon, _ = stats.pearsonr(cf2, cf6)
            h4_pass = r_horizon > 0.5
            print(f"\n  Horizon stability: 2h vs 6h correction factor r={r_horizon:.3f}")

    # H5: Residual-based recommendations are actionable (>30% of patients need change)
    need_change = [p for p in h2_results.get("per_patient", [])
                   if p.get("correction_factor", 1.0) > 1.1 or p.get("correction_factor", 1.0) < 0.9]
    h5_pass = len(need_change) > len(h2_results.get("per_patient", [])) * 0.3

    hypotheses = {
        "H1_majority_significant_residuals": bool(h1_pass),
        "H2_meaningful_correction_variance": bool(h2_pass),
        "H3_isf_predicts_residual": bool(h3_pass),
        "H4_stable_across_horizons": bool(h4_pass),
        "H5_actionable_recommendations": bool(h5_pass),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n  Hypotheses: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"    {'✓' if v else '✗'} {k}")

    # ── Save ─────────────────────────────────────────────────────
    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. N={len(df)} events, "
               f"{df['patient_id'].nunique()} patients. "
               f"Median correction factor: {h2_results.get('median_correction_factor', 'N/A')}")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_settings_from_residuals.json"

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
    create_dashboard(all_results, hypotheses)

    return hypotheses, all_results


def create_dashboard(all_results, hypotheses):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    for idx, h in enumerate(HORIZONS):
        hk = f"{h}h"
        data = all_results.get(hk, {})
        if not data:
            continue
        pats = pd.DataFrame(data.get("per_patient", []))
        if pats.empty:
            continue

        # Correction factor distribution
        ax = fig.add_subplot(gs[0, idx])
        cf = pats["correction_factor"].clip(0, 3)
        ax.hist(cf, bins=20, color="steelblue", edgecolor="white", alpha=0.8)
        ax.axvline(1.0, color="red", linewidth=2, linestyle="--", label="Perfect (1.0)")
        ax.axvline(cf.median(), color="orange", linewidth=2, label=f"Median ({cf.median():.2f})")
        ax.set_xlabel("Correction Factor")
        ax.set_ylabel("Patients")
        ax.set_title(f"{hk}: Correction Factor Distribution")
        ax.legend(fontsize=8)

    # Panel 4: Profile ISF vs mean residual (2h)
    ax4 = fig.add_subplot(gs[1, 0])
    data_2h = all_results.get("2h", {})
    if data_2h:
        pats_2h = pd.DataFrame(data_2h.get("per_patient", []))
        if not pats_2h.empty and "profile_isf" in pats_2h.columns:
            valid = pats_2h.dropna(subset=["profile_isf", "mean_residual"])
            colors = ["red" if r["significant"] else "gray" for _, r in valid.iterrows()]
            ax4.scatter(valid["profile_isf"], valid["mean_residual"], c=colors, alpha=0.7)
            ax4.axhline(0, color="black", linewidth=0.5)
            ax4.set_xlabel("Profile ISF (mg/dL/U)")
            ax4.set_ylabel("Mean Residual (mg/dL)")
            ax4.set_title("Profile ISF vs Residual (2h)")

    # Panel 5: Empirical ISF vs Profile ISF
    ax5 = fig.add_subplot(gs[1, 1])
    if data_2h:
        pats_2h = pd.DataFrame(data_2h.get("per_patient", []))
        if not pats_2h.empty:
            valid = pats_2h.dropna(subset=["profile_isf", "empirical_isf"])
            valid = valid[(valid["empirical_isf"] > 0) & (valid["empirical_isf"] < 200)]
            if len(valid) > 3:
                ax5.scatter(valid["profile_isf"], valid["empirical_isf"], color="steelblue", alpha=0.7)
                lims = [0, max(valid["profile_isf"].max(), valid["empirical_isf"].max()) * 1.1]
                ax5.plot(lims, lims, "r--", label="1:1 line")
                ax5.set_xlabel("Profile ISF (mg/dL/U)")
                ax5.set_ylabel("Empirical ISF (drop/dose)")
                ax5.set_title("Profile vs Empirical ISF")
                ax5.legend()

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [f"EXP-{EXP_ID}: Settings from Residuals", ""]
    for hk in ["2h", "4h", "6h"]:
        d = all_results.get(hk, {})
        if d:
            lines.append(f"{hk}: R²={d['r2_population']:.3f}, "
                        f"{d['n_significant']}/{d['n_patients']} significant")
    lines.append("")
    lines.append("Hypothesis Results:")
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")

    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=9, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "settings-from-residuals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
