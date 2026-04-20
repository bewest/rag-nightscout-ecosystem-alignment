#!/usr/bin/env python3
"""EXP-2732: Multi-Factor Deconfounding — Supply + Demand.

The correct way to deconfound AID data requires modeling BOTH sides:
  - DEMAND: insulin lowers glucose (ISF × excess_insulin)
  - SUPPLY: EGP raises glucose (hepatic production opposing insulin)

EXP-2731 showed EGP reduces deviation bias 36% and variance 37% but
didn't improve ISF extraction because ISF was computed from raw
observed_drop / excess_insulin, ignoring EGP.

The proper extraction:
  observed_drop = ISF × excess_insulin − EGP_contribution
  true_ISF = (observed_drop + EGP_contribution) / excess_insulin

This experiment validates multi-factor deconfounding where EGP is
an explicit regressor alongside insulin dose.

HYPOTHESES:
  H1: Multi-factor R² (insulin + EGP) > single-factor R² (insulin only)
  H2: EGP-corrected ISF is higher than naive ISF (insulin worked harder)
  H3: EGP-corrected ISF has lower dose-dependence artifact
  H4: EGP-corrected ISF closer to profile ISF (closing the 10x gap)
  H5: EGP contribution is circadian (higher overnight = dawn phenomenon)

REFERENCES: EXP-2698, EXP-2727, EXP-2728, EXP-2731
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.deconfounding import (
    BGISubtraction,
    EventCategorizer,
    _estimate_egp_over_horizon,
    DEFAULT_COUNTER_REG_K,
)

# ── Paths ────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/multifactor-deconfounding")

EXP_ID = 2732
TITLE = "Multi-Factor Deconfounding — Supply + Demand"


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)]
    print(f"Loaded {len(grid)} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_correction_events(grid):
    """Run classic BGI + categorize, then filter to correction events."""
    bgi = BGISubtraction(egp_enabled=True, counter_reg_k=0.0)
    events = bgi.compute_deviations(grid)
    cat = EventCategorizer()
    events = cat.categorize(events)

    corrections = events[
        (events["category"] == "correction")
        & (events["bg0"] >= 180.0)
        & (events["carbs_2h"] <= 1.0)
        & (events["bolus_2h"] >= 0.3)
        & (events["excess_insulin"] > 0.1)
    ].copy()
    return corrections


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()
    corrections = extract_correction_events(grid)
    print(f"Correction events: {len(corrections)}, {corrections['patient_id'].nunique()} patients")

    # ── Part 1: Single-factor vs Multi-factor R² ─────────────────────
    print(f"\n{'─' * 50}")
    print("Part 1: Single-factor vs Multi-factor regression")
    print(f"{'─' * 50}")

    y = corrections["observed_drop"].values
    x_insulin = corrections["excess_insulin"].values
    x_egp = corrections["egp_contribution"].values

    # Single-factor: observed_drop ~ excess_insulin
    slope1, intercept1, r1, p1, se1 = stats.linregress(x_insulin, y)
    r2_single = r1 ** 2
    print(f"  Single-factor (insulin only):")
    print(f"    R² = {r2_single:.4f}")
    print(f"    slope = {slope1:.2f} (≈ population ISF)")
    print(f"    intercept = {intercept1:.2f}")

    # Multi-factor: observed_drop ~ excess_insulin + egp_contribution
    X = np.column_stack([x_insulin, x_egp, np.ones(len(y))])
    betas, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    y_pred = X @ betas
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2_multi = 1.0 - ss_res / ss_tot
    print(f"\n  Multi-factor (insulin + EGP):")
    print(f"    R² = {r2_multi:.4f}")
    print(f"    β_insulin = {betas[0]:.2f} (ISF, demand)")
    print(f"    β_EGP = {betas[1]:.2f} (supply-side coefficient)")
    print(f"    β_intercept = {betas[2]:.2f}")

    r2_gain = r2_multi - r2_single
    print(f"\n  R² gain from EGP: {r2_gain:+.4f}")

    # ── Part 2: EGP-corrected ISF extraction ─────────────────────────
    print(f"\n{'─' * 50}")
    print("Part 2: EGP-corrected ISF extraction")
    print(f"{'─' * 50}")

    # Naive ISF: observed_drop / excess_insulin
    naive_isf = y / x_insulin
    # EGP-corrected ISF: (observed_drop + EGP_contribution) / excess_insulin
    # EGP contribution is positive (glucose raised), so adding it recovers
    # the true insulin effect that was masked by EGP headwind
    corrected_isf = (y + x_egp) / x_insulin

    # Per-patient comparison
    patients_data = []
    for pid in corrections["patient_id"].unique():
        mask = corrections["patient_id"].values == pid
        pc = corrections[mask]
        if len(pc) < 5:
            continue

        naive_vals = naive_isf[mask]
        corrected_vals = corrected_isf[mask]

        # Filter to positive ISF
        naive_pos = naive_vals[naive_vals > 0]
        corrected_pos = corrected_vals[corrected_vals > 0]

        if len(naive_pos) < 5 or len(corrected_pos) < 5:
            continue

        # Profile ISF
        profile_isf = float(pc["isf_used"].median())

        # Dose-ISF correlation (artifact measure)
        doses = x_insulin[mask]
        naive_r, _ = stats.spearmanr(doses[naive_vals > 0], naive_pos)
        corrected_r, _ = stats.spearmanr(doses[corrected_vals > 0], corrected_pos)

        patients_data.append({
            "patient_id": pid,
            "n_events": len(pc),
            "profile_isf": profile_isf,
            "naive_isf_median": float(np.median(naive_pos)),
            "naive_isf_cv": float(np.std(naive_pos) / np.mean(naive_pos)),
            "corrected_isf_median": float(np.median(corrected_pos)),
            "corrected_isf_cv": float(np.std(corrected_pos) / np.mean(corrected_pos)),
            "naive_dose_r": float(naive_r),
            "corrected_dose_r": float(corrected_r),
            "isf_increase_pct": float(np.median(corrected_pos) / np.median(naive_pos) - 1) * 100,
            "profile_gap_naive": float(profile_isf / np.median(naive_pos)),
            "profile_gap_corrected": float(profile_isf / np.median(corrected_pos)),
        })

    pat_df = pd.DataFrame(patients_data)
    print(f"  Patients with enough events: {len(pat_df)}")

    print(f"\n  Population medians:")
    print(f"    Naive ISF:     {pat_df['naive_isf_median'].median():.1f}")
    print(f"    Corrected ISF: {pat_df['corrected_isf_median'].median():.1f}")
    print(f"    Profile ISF:   {pat_df['profile_isf'].median():.1f}")
    print(f"    ISF increase:  {pat_df['isf_increase_pct'].median():.1f}%")

    print(f"\n  Profile gap (profile / extracted):")
    print(f"    Naive:     {pat_df['profile_gap_naive'].median():.1f}x")
    print(f"    Corrected: {pat_df['profile_gap_corrected'].median():.1f}x")

    print(f"\n  Dose-ISF artifact |r|:")
    print(f"    Naive:     {pat_df['naive_dose_r'].abs().median():.3f}")
    print(f"    Corrected: {pat_df['corrected_dose_r'].abs().median():.3f}")

    print(f"\n  ISF CV (precision):")
    print(f"    Naive:     {pat_df['naive_isf_cv'].median():.3f}")
    print(f"    Corrected: {pat_df['corrected_isf_cv'].median():.3f}")

    # ── Part 3: Circadian EGP structure ──────────────────────────────
    print(f"\n{'─' * 50}")
    print("Part 3: Circadian EGP structure")
    print(f"{'─' * 50}")

    hour_int = corrections["hour"].astype(int) % 24
    hourly_egp = corrections.groupby(hour_int)["egp_contribution"].median()
    print(f"  EGP by hour (median mg/dL over 2h):")
    for h in [0, 4, 8, 12, 16, 20]:
        val = hourly_egp.get(h, 0)
        print(f"    {h:02d}:00 → {val:.1f}")

    # Dawn phenomenon: is overnight EGP higher?
    dawn_hours = [4, 5, 6, 7]
    midday_hours = [12, 13, 14, 15]
    dawn_egp = corrections[hour_int.isin(dawn_hours)]["egp_contribution"]
    midday_egp = corrections[hour_int.isin(midday_hours)]["egp_contribution"]
    if len(dawn_egp) > 30 and len(midday_egp) > 30:
        u_stat, u_p = stats.mannwhitneyu(dawn_egp, midday_egp, alternative="greater")
        dawn_effect = float(dawn_egp.median() - midday_egp.median())
        print(f"\n  Dawn phenomenon:")
        print(f"    Dawn (4-7AM) median EGP:  {dawn_egp.median():.1f}")
        print(f"    Midday (12-3PM) median:   {midday_egp.median():.1f}")
        print(f"    Difference:               {dawn_effect:+.1f}")
        print(f"    Mann-Whitney p:           {u_p:.2e}")
    else:
        dawn_effect = 0.0
        u_p = 1.0

    # ── Part 4: 72h insulin accounting sanity check ──────────────────
    print(f"\n{'─' * 50}")
    print("Part 4: 72h insulin accounting (sanity check)")
    print(f"{'─' * 50}")

    for pid in sorted(corrections["patient_id"].unique())[:5]:
        pg = grid[grid["patient_id"] == pid].sort_values("time")
        total_hours = len(pg) * 5.0 / 60.0
        total_bolus = pg["bolus"].sum() if "bolus" in pg.columns else 0
        total_smb = pg["bolus_smb"].sum() if "bolus_smb" in pg.columns else 0
        sched_basal = pg["scheduled_basal_rate"].median() if "scheduled_basal_rate" in pg.columns else 0
        total_sched_basal = sched_basal * total_hours
        total_insulin = total_bolus + total_smb + total_sched_basal
        tdd = total_insulin / (total_hours / 24.0) if total_hours > 0 else 0
        print(f"  {pid[:8]}: {total_hours:.0f}h, bolus={total_bolus:.1f}U, SMB={total_smb:.1f}U, "
              f"sched_basal={total_sched_basal:.1f}U, TDD≈{tdd:.1f}U/day")

    # ── Hypotheses ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  HYPOTHESES")
    print(f"{'=' * 70}")

    hypotheses = {}

    h1 = r2_multi > r2_single
    hypotheses["H1_multi_r2_better"] = (h1,
        f"Multi R²={r2_multi:.4f} vs single={r2_single:.4f}, gain={r2_gain:+.4f}")
    print(f"  {'PASS' if h1 else 'FAIL'} H1: Multi-factor R² > single-factor")

    h2 = pat_df["corrected_isf_median"].median() > pat_df["naive_isf_median"].median()
    hypotheses["H2_corrected_isf_higher"] = (h2,
        f"Corrected={pat_df['corrected_isf_median'].median():.1f} vs naive={pat_df['naive_isf_median'].median():.1f}")
    print(f"  {'PASS' if h2 else 'FAIL'} H2: EGP-corrected ISF higher than naive")

    h3 = pat_df["corrected_dose_r"].abs().median() < pat_df["naive_dose_r"].abs().median()
    hypotheses["H3_less_dose_artifact"] = (h3,
        f"|r| corrected={pat_df['corrected_dose_r'].abs().median():.3f} vs naive={pat_df['naive_dose_r'].abs().median():.3f}")
    print(f"  {'PASS' if h3 else 'FAIL'} H3: EGP-corrected ISF has less dose artifact")

    h4 = pat_df["profile_gap_corrected"].median() < pat_df["profile_gap_naive"].median()
    hypotheses["H4_closer_to_profile"] = (h4,
        f"Gap corrected={pat_df['profile_gap_corrected'].median():.1f}x vs naive={pat_df['profile_gap_naive'].median():.1f}x")
    print(f"  {'PASS' if h4 else 'FAIL'} H4: Corrected ISF closer to profile ISF")

    h5 = dawn_effect > 0 and u_p < 0.05
    hypotheses["H5_circadian_egp"] = (h5,
        f"Dawn effect={dawn_effect:+.1f}, p={u_p:.2e}")
    print(f"  {'PASS' if h5 else 'FAIL'} H5: EGP has circadian structure (dawn phenomenon)")

    n_pass = sum(1 for v in hypotheses.values() if v[0])

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: EXP-{EXP_ID}: {n_pass}/5 pass.")
    print(f"  Multi-factor R²={r2_multi:.4f} vs single={r2_single:.4f} (gain={r2_gain:+.4f})")
    print(f"  ISF: naive={pat_df['naive_isf_median'].median():.1f} → corrected={pat_df['corrected_isf_median'].median():.1f}")
    print(f"  Profile gap: {pat_df['profile_gap_naive'].median():.1f}x → {pat_df['profile_gap_corrected'].median():.1f}x")
    print(f"  β_insulin={betas[0]:.2f}, β_EGP={betas[1]:.2f}")
    print(f"{'=' * 70}")

    # ── Dashboard ─────────────────────────────────────────────────────
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        VIZ_DIR.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=14, fontweight="bold")

        # 1. R² comparison
        ax = axes[0, 0]
        ax.bar(["Insulin only", "Insulin+EGP"], [r2_single, r2_multi],
               color=["#e74c3c", "#2ecc71"])
        ax.set_title("R² (observed vs predicted drop)")
        ax.set_ylabel("R²")
        for i, v in enumerate([r2_single, r2_multi]):
            ax.text(i, v + 0.002, f"{v:.4f}", ha="center")

        # 2. ISF comparison (naive vs corrected vs profile)
        ax = axes[0, 1]
        vals = [pat_df["naive_isf_median"].median(),
                pat_df["corrected_isf_median"].median(),
                pat_df["profile_isf"].median()]
        bars = ax.bar(["Naive", "EGP-corrected", "Profile"],
                       vals, color=["#e74c3c", "#2ecc71", "#3498db"])
        ax.set_title("Median ISF (mg/dL per U)")
        for i, v in enumerate(vals):
            ax.text(i, v + 1, f"{v:.1f}", ha="center")

        # 3. Profile gap
        ax = axes[0, 2]
        ax.bar(["Naive", "EGP-corrected"],
               [pat_df["profile_gap_naive"].median(), pat_df["profile_gap_corrected"].median()],
               color=["#e74c3c", "#2ecc71"])
        ax.set_title("Profile / Extracted ISF gap (lower = better)")
        ax.axhline(y=1, color="gray", linestyle="--", label="No gap")
        ax.legend()

        # 4. Dose-ISF artifact
        ax = axes[1, 0]
        ax.bar(["Naive", "EGP-corrected"],
               [pat_df["naive_dose_r"].abs().median(), pat_df["corrected_dose_r"].abs().median()],
               color=["#e74c3c", "#2ecc71"])
        ax.set_title("|Dose-ISF r| artifact (lower = better)")

        # 5. Circadian EGP
        ax = axes[1, 1]
        hours_sorted = sorted(hourly_egp.index)
        ax.plot(hours_sorted, [hourly_egp[h] for h in hours_sorted], "o-", color="#3498db")
        ax.set_title("EGP by hour of day")
        ax.set_xlabel("Hour")
        ax.set_ylabel("EGP contribution (mg/dL)")
        ax.axvspan(4, 7, alpha=0.2, color="orange", label="Dawn")
        ax.legend()

        # 6. Per-patient ISF scatter
        ax = axes[1, 2]
        ax.scatter(pat_df["naive_isf_median"], pat_df["corrected_isf_median"],
                   c=pat_df["n_events"], cmap="viridis", s=50, edgecolors="k", linewidths=0.5)
        max_val = max(pat_df["naive_isf_median"].max(), pat_df["corrected_isf_median"].max()) * 1.1
        ax.plot([0, max_val], [0, max_val], "k--", alpha=0.3, label="y=x")
        ax.set_xlabel("Naive ISF")
        ax.set_ylabel("EGP-corrected ISF")
        ax.set_title("Per-patient ISF: naive vs corrected")
        ax.legend()
        plt.colorbar(ax.collections[0], ax=ax, label="N events")

        plt.tight_layout()
        out = VIZ_DIR / f"exp-{EXP_ID}-dashboard.png"
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Dashboard: {out}")
    except ImportError:
        print("  (matplotlib unavailable)")

    # ── Save ──────────────────────────────────────────────────────────
    def clean(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    results = {
        "experiment_id": f"EXP-{EXP_ID}",
        "title": TITLE,
        "timestamp": datetime.now().isoformat(),
        "summary": f"{n_pass}/5 pass. Multi-factor R²={r2_multi:.4f} vs single={r2_single:.4f}.",
        "regression": {
            "single_factor_r2": round(r2_single, 4),
            "multi_factor_r2": round(r2_multi, 4),
            "r2_gain": round(r2_gain, 4),
            "beta_insulin": round(float(betas[0]), 2),
            "beta_egp": round(float(betas[1]), 2),
            "beta_intercept": round(float(betas[2]), 2),
        },
        "isf_extraction": {
            "naive_isf_median": round(float(pat_df["naive_isf_median"].median()), 1),
            "corrected_isf_median": round(float(pat_df["corrected_isf_median"].median()), 1),
            "profile_isf_median": round(float(pat_df["profile_isf"].median()), 1),
            "profile_gap_naive": round(float(pat_df["profile_gap_naive"].median()), 1),
            "profile_gap_corrected": round(float(pat_df["profile_gap_corrected"].median()), 1),
            "isf_increase_pct": round(float(pat_df["isf_increase_pct"].median()), 1),
        },
        "circadian": {
            "dawn_effect": round(dawn_effect, 1),
            "dawn_p": float(u_p),
        },
        "per_patient": pat_df.to_dict(orient="records"),
        "hypotheses": {k: {"passed": bool(v[0]), "detail": v[1]} for k, v in hypotheses.items()},
        "n_corrections": len(corrections),
        "n_patients": int(corrections["patient_id"].nunique()),
    }

    out = RESULTS_DIR / f"exp-{EXP_ID}_multifactor_deconfounding.json"
    out.write_text(json.dumps(results, indent=2, default=clean))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
