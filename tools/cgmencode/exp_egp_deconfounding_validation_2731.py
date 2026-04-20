#!/usr/bin/env python3
"""EXP-2731: EGP-Aware Deconfounding Validation.

Validates that adding supply-side physics (EGP + counter-regulation)
to the production BGI subtraction pipeline improves deconfounding quality.

EXP-2728 showed: profile ISF + EGP + counter-reg (MAE=46.9) beats
empirical ISF (51.0) in forward simulation.  This experiment tests
the SAME physics in the ANALYTIC deconfounding pipeline used by all
downstream experiments.

HYPOTHESES:
  H1: EGP-aware BGI reduces deviation variance (smaller residuals = better model)
  H2: EGP-aware correction events have less dose-dependent ISF artifact
  H3: EGP-aware BGI produces higher R² in correction analysis
  H4: Negative ISF rate drops with EGP correction (supply-side explains rises)
  H5: Per-patient ISF estimates converge (lower CV) with physics correction

METHOD:
  1. Run BGISubtraction three ways: classic, +EGP, +EGP+CR
  2. Extract correction events from each
  3. Compare: deviation variance, dose-ISF correlation, R², negative ISF rate
  4. Per-patient ISF extraction comparison

REFERENCES: EXP-2698, EXP-2727, EXP-2728
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
    IsolationFilter,
    ExperimentFilters,
    DEFAULT_COUNTER_REG_K,
)

# ── Paths ────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/egp-deconfounding-validation")

EXP_ID = 2731
TITLE = "EGP-Aware Deconfounding Validation"


def load_data():
    """Load grid and filter to qualified patients."""
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    if not qualified:
        qualified = [p["patient_id"] for p in manifest.get("patients", [])]
    grid = grid[grid["patient_id"].isin(qualified)]
    print(f"Loaded {len(grid)} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_correction_events(events_df: pd.DataFrame) -> pd.DataFrame:
    """Extract clean correction events: BG≥180, no carbs, bolus present."""
    cat = EventCategorizer()
    events = cat.categorize(events_df)
    corrections = events[
        (events["category"] == "correction")
        & (events["bg0"] >= 180.0)
        & (events["carbs_2h"] <= 1.0)
        & (events["bolus_2h"] >= 0.3)
    ].copy()
    return corrections


def compute_per_patient_isf(corrections: pd.DataFrame) -> pd.DataFrame:
    """Compute ISF = observed_drop / excess_insulin for each patient."""
    rows = []
    for pid in corrections["patient_id"].unique():
        pc = corrections[corrections["patient_id"] == pid]
        if len(pc) < 5:
            continue
        drops = pc["observed_drop"].values
        doses = pc["excess_insulin"].values
        valid = (doses > 0.1) & np.isfinite(drops)
        if valid.sum() < 5:
            continue
        isf_vals = drops[valid] / doses[valid]
        isf_vals = isf_vals[(isf_vals > 0) & (isf_vals < 500)]
        if len(isf_vals) < 5:
            continue
        rows.append({
            "patient_id": pid,
            "median_isf": float(np.median(isf_vals)),
            "mean_isf": float(np.mean(isf_vals)),
            "std_isf": float(np.std(isf_vals)),
            "cv_isf": float(np.std(isf_vals) / np.mean(isf_vals)) if np.mean(isf_vals) > 0 else np.nan,
            "pct_negative": float(np.mean(drops[valid] < 0)),
            "n_events": int(valid.sum()),
        })
    return pd.DataFrame(rows)


def analyze_arm(grid, label, egp_enabled, counter_reg_k):
    """Run one arm of the analysis and return summary metrics."""
    print(f"\n  [{label}] egp={egp_enabled}, creg={counter_reg_k}")
    bgi = BGISubtraction(
        egp_enabled=egp_enabled,
        counter_reg_k=counter_reg_k,
    )
    events = bgi.compute_deviations(grid)
    print(f"    Total events: {len(events)}")

    corrections = extract_correction_events(events)
    print(f"    Correction events (BG≥180, no carbs): {len(corrections)}")

    if len(corrections) < 30:
        print(f"    WARNING: too few corrections for analysis")
        return None

    # Metrics
    dev_var = float(corrections["deviation"].var())
    dev_std = float(corrections["deviation"].std())
    dev_mean = float(corrections["deviation"].mean())

    # Dose-ISF correlation (artifact detection)
    valid = corrections["excess_insulin"] > 0.1
    if valid.sum() > 30:
        isf_event = corrections.loc[valid, "observed_drop"] / corrections.loc[valid, "excess_insulin"]
        dose_isf_r, dose_isf_p = stats.spearmanr(
            corrections.loc[valid, "excess_insulin"],
            isf_event,
        )
    else:
        dose_isf_r, dose_isf_p = np.nan, np.nan

    # R² of expected vs observed drop
    if len(corrections) > 10:
        slope, intercept, r, p, se = stats.linregress(
            corrections["expected_drop"], corrections["observed_drop"]
        )
        r_squared = r ** 2
    else:
        r_squared = np.nan

    # Negative ISF rate
    neg_rate = float((corrections["observed_drop"] < 0).mean())

    # Per-patient ISF extraction
    pat_isf = compute_per_patient_isf(corrections)
    median_cv = float(pat_isf["cv_isf"].median()) if len(pat_isf) > 0 else np.nan
    median_isf = float(pat_isf["median_isf"].median()) if len(pat_isf) > 0 else np.nan

    # EGP contribution stats
    if "egp_contribution" in corrections.columns:
        egp_median = float(corrections["egp_contribution"].median())
        egp_mean = float(corrections["egp_contribution"].mean())
    else:
        egp_median = 0.0
        egp_mean = 0.0

    result = {
        "label": label,
        "n_corrections": len(corrections),
        "n_patients": int(corrections["patient_id"].nunique()),
        "deviation_mean": dev_mean,
        "deviation_std": dev_std,
        "deviation_var": dev_var,
        "dose_isf_r": float(dose_isf_r) if np.isfinite(dose_isf_r) else None,
        "dose_isf_p": float(dose_isf_p) if np.isfinite(dose_isf_p) else None,
        "r_squared": float(r_squared) if np.isfinite(r_squared) else None,
        "neg_isf_rate": neg_rate,
        "per_patient_median_isf": median_isf,
        "per_patient_median_cv": median_cv,
        "egp_contribution_median": egp_median,
        "egp_contribution_mean": egp_mean,
        "n_patients_isf": len(pat_isf),
    }

    print(f"    Deviation: mean={dev_mean:.1f}, std={dev_std:.1f}")
    print(f"    R²(expected→observed): {r_squared:.3f}" if np.isfinite(r_squared) else "    R²: N/A")
    print(f"    Dose-ISF r={dose_isf_r:.3f}" if np.isfinite(dose_isf_r) else "    Dose-ISF: N/A")
    print(f"    Negative ISF rate: {neg_rate:.1%}")
    print(f"    Per-patient ISF median: {median_isf:.1f}, CV: {median_cv:.2f}")
    print(f"    EGP contribution: median={egp_median:.1f}, mean={egp_mean:.1f}")

    return result


def make_dashboard(arms, hypotheses):
    """Generate comparison dashboard."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib not available, skipping dashboard)")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=14, fontweight="bold")

    labels = [a["label"] for a in arms]
    colors = ["#e74c3c", "#3498db", "#2ecc71"]

    # 1. Deviation std
    ax = axes[0, 0]
    vals = [a["deviation_std"] for a in arms]
    ax.bar(labels, vals, color=colors)
    ax.set_title("Deviation Std (lower = better model)")
    ax.set_ylabel("mg/dL")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.5, f"{v:.1f}", ha="center", fontsize=10)

    # 2. R² expected→observed
    ax = axes[0, 1]
    vals = [a["r_squared"] or 0 for a in arms]
    ax.bar(labels, vals, color=colors)
    ax.set_title("R² (expected vs observed drop)")
    ax.set_ylabel("R²")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.01, f"{v:.3f}", ha="center", fontsize=10)

    # 3. Dose-ISF correlation (artifact)
    ax = axes[0, 2]
    vals = [abs(a["dose_isf_r"] or 0) for a in arms]
    ax.bar(labels, vals, color=colors)
    ax.set_title("|Dose-ISF r| (lower = less artifact)")
    ax.set_ylabel("|Spearman r|")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.01, f"{v:.3f}", ha="center", fontsize=10)

    # 4. Negative ISF rate
    ax = axes[1, 0]
    vals = [a["neg_isf_rate"] * 100 for a in arms]
    ax.bar(labels, vals, color=colors)
    ax.set_title("Negative ISF Rate (lower = better)")
    ax.set_ylabel("%")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=10)

    # 5. Per-patient ISF CV
    ax = axes[1, 1]
    vals = [a["per_patient_median_cv"] for a in arms]
    ax.bar(labels, vals, color=colors)
    ax.set_title("Per-patient ISF CV (lower = more precise)")
    ax.set_ylabel("CV")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.01, f"{v:.2f}", ha="center", fontsize=10)

    # 6. Hypothesis results
    ax = axes[1, 2]
    ax.axis("off")
    text = f"EXP-{EXP_ID} Hypotheses\n" + "=" * 30 + "\n"
    for h_id, (passed, desc) in hypotheses.items():
        icon = "✓ PASS" if passed else "✗ FAIL"
        text += f"\n{icon}: {h_id}\n  {desc}\n"
    ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=9,
            verticalalignment="top", fontfamily="monospace")

    plt.tight_layout()
    out = VIZ_DIR / f"exp-{EXP_ID}-dashboard.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Dashboard: {out}")


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()

    # Three arms: classic, +EGP, +EGP+counter-reg
    arms = []
    configs = [
        ("A_classic", False, 0.0),
        ("B_egp", True, 0.0),
        ("C_egp+creg", True, DEFAULT_COUNTER_REG_K),
    ]

    for label, egp, creg in configs:
        result = analyze_arm(grid, label, egp, creg)
        if result:
            arms.append(result)

    if len(arms) < 3:
        print("\nERROR: Not enough arms completed")
        sys.exit(1)

    classic, egp, full = arms[0], arms[1], arms[2]

    # ── Hypotheses ────────────────────────────────────────────────────
    hypotheses = {}

    # H1: EGP reduces deviation variance
    h1 = egp["deviation_var"] < classic["deviation_var"]
    hypotheses["H1_egp_reduces_variance"] = (h1,
        f"EGP var={egp['deviation_var']:.0f} vs classic={classic['deviation_var']:.0f}")
    print(f"\n  {'PASS' if h1 else 'FAIL'} H1: EGP reduces deviation variance")

    # H2: EGP reduces dose-ISF artifact
    classic_r = abs(classic["dose_isf_r"] or 0)
    full_r = abs(full["dose_isf_r"] or 0)
    h2 = full_r < classic_r
    hypotheses["H2_reduces_dose_artifact"] = (h2,
        f"Full |r|={full_r:.3f} vs classic={classic_r:.3f}")
    print(f"  {'PASS' if h2 else 'FAIL'} H2: Full physics reduces dose-ISF artifact")

    # H3: EGP-aware R² higher
    h3 = (full["r_squared"] or 0) > (classic["r_squared"] or 0)
    hypotheses["H3_higher_r_squared"] = (h3,
        f"Full R²={full['r_squared']:.3f} vs classic={classic['r_squared']:.3f}")
    print(f"  {'PASS' if h3 else 'FAIL'} H3: Full physics R² > classic")

    # H4: Negative ISF rate drops
    h4 = full["neg_isf_rate"] < classic["neg_isf_rate"]
    hypotheses["H4_lower_neg_isf"] = (h4,
        f"Full neg={full['neg_isf_rate']:.1%} vs classic={classic['neg_isf_rate']:.1%}")
    print(f"  {'PASS' if h4 else 'FAIL'} H4: Negative ISF rate drops with physics")

    # H5: ISF estimates more precise (lower CV)
    h5 = full["per_patient_median_cv"] < classic["per_patient_median_cv"]
    hypotheses["H5_lower_isf_cv"] = (h5,
        f"Full CV={full['per_patient_median_cv']:.2f} vs classic={classic['per_patient_median_cv']:.2f}")
    print(f"  {'PASS' if h5 else 'FAIL'} H5: Per-patient ISF more precise")

    n_pass = sum(1 for v in hypotheses.values() if v[0])
    n_total = len(hypotheses)

    # ── Results table ─────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  {'Arm':<20} {'DevStd':>8} {'R²':>8} {'|DoseR|':>8} {'NegISF':>8} {'ISF_CV':>8} {'EGP':>8}")
    print(f"  {'-' * 68}")
    for a in arms:
        print(f"  {a['label']:<20} {a['deviation_std']:>8.1f} "
              f"{(a['r_squared'] or 0):>8.3f} "
              f"{abs(a['dose_isf_r'] or 0):>8.3f} "
              f"{a['neg_isf_rate']*100:>7.1f}% "
              f"{a['per_patient_median_cv']:>8.2f} "
              f"{a['egp_contribution_median']:>8.1f}")

    print(f"\n  Improvements (classic → full physics):")
    var_improve = (classic["deviation_var"] - full["deviation_var"]) / classic["deviation_var"] * 100
    print(f"    Deviation variance: {var_improve:+.1f}%")
    r2_improve = (full["r_squared"] or 0) - (classic["r_squared"] or 0)
    print(f"    R²: {r2_improve:+.3f}")
    neg_improve = (classic["neg_isf_rate"] - full["neg_isf_rate"]) * 100
    print(f"    Negative ISF rate: {neg_improve:+.1f} pp")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: EXP-{EXP_ID}: {n_pass}/{n_total} pass. "
          f"EGP+CR deviation std {full['deviation_std']:.1f} vs classic {classic['deviation_std']:.1f}. "
          f"R²: {(full['r_squared'] or 0):.3f} vs {(classic['r_squared'] or 0):.3f}")
    print(f"{'=' * 70}")

    # ── Dashboard ─────────────────────────────────────────────────────
    make_dashboard(arms, hypotheses)

    # ── Save results ──────────────────────────────────────────────────
    def clean(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp, datetime)):
            return obj.isoformat()
        return obj

    results = {
        "experiment_id": f"EXP-{EXP_ID}",
        "title": TITLE,
        "timestamp": datetime.now().isoformat(),
        "summary": f"{n_pass}/{n_total} pass. Full physics (EGP+CR) vs classic BGI subtraction.",
        "arms": arms,
        "hypotheses": {k: {"passed": bool(v[0]), "detail": v[1]} for k, v in hypotheses.items()},
        "improvements": {
            "variance_reduction_pct": round(var_improve, 1),
            "r_squared_gain": round(r2_improve, 3),
            "neg_isf_rate_reduction_pp": round(neg_improve, 1),
        },
    }

    out = RESULTS_DIR / f"exp-{EXP_ID}_egp_deconfounding_validation.json"
    out.write_text(json.dumps(results, indent=2, default=clean))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
