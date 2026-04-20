#!/usr/bin/env python3
"""
EXP-2753: Temporal Cross-Validation of Settings Pipeline
==========================================================

Scientific Question
-------------------
Do the settings recommendations from our pipeline GENERALIZE to unseen time
periods? This is the critical trust question: if we extract ISF and CR from
the first 70% of a patient's data, do those settings improve predictions on
the remaining 30%?

This is the most important validation experiment. Clinical adoption requires
temporal stability — settings that only work on the data they were derived
from are useless.

Approach
--------
For each patient:
1. Split data chronologically: 70% train / 30% test
2. On TRAIN set: Extract ISF correction (waterfall residuals) and CR (bilateral deconfounding)
3. On TEST set: Compare profile vs corrected settings via episode simulation
4. Measure: Does the TRAIN-derived correction improve TEST-set predictions?

Predecessors
------------
- EXP-2719b: Per-patient ISF from residuals
- EXP-2741: Bilateral CR deconfounding
- EXP-2743: Integrated pipeline validation (uses all data, no temporal split)
- EXP-2749: Enhanced pipeline (uses all data)

Hypotheses
----------
H1: Train-derived ISF corrections improve test MAE for >50% of patients
H2: Train-derived CR corrections improve test MAE for >50% of patients
H3: Combined pipeline improves test MAE for >50% of patients
H4: Test-set improvement is within 80% of train-set improvement (stability)
H5: No patient gets >20% WORSE on test set (safety)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/temporal-crossval")

TRAIN_FRAC = 0.70
CORRECTION_HORIZON = 24  # 2h in 5-min steps
MEAL_MIN_CARBS = 10
BG_MIN_CORRECTION = 180


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]
    return grid


def split_train_test(pg: pd.DataFrame):
    """Split chronologically."""
    n = len(pg)
    split_idx = int(n * TRAIN_FRAC)
    return pg.iloc[:split_idx].copy(), pg.iloc[split_idx:].copy()


def extract_isf_correction(pg: pd.DataFrame) -> float:
    """Extract ISF correction factor from waterfall residuals on training data.

    Method: For correction episodes (BG≥180, bolus>0), compute:
    - Expected BG drop using profile ISF: BGI = excess_insulin × ISF × 5/60
    - Actual BG drop over 2h
    - Correction factor = median(actual_drop / expected_drop)
    """
    corrections = []

    mask = (pg["glucose"] >= BG_MIN_CORRECTION) & (pg["bolus"] > 0)
    event_idx = pg.index[mask]

    for idx in event_idx:
        pos = pg.index.get_loc(idx)
        if pos + CORRECTION_HORIZON >= len(pg):
            continue

        bg0 = float(pg.iloc[pos]["glucose"])
        bg_end = float(pg.iloc[pos + CORRECTION_HORIZON]["glucose"])
        if np.isnan(bg0) or np.isnan(bg_end):
            continue

        actual_drop = bg0 - bg_end  # positive = glucose fell

        # Compute expected drop from insulin
        isf = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)
        total_insulin = 0
        for j in range(CORRECTION_HORIZON):
            if pos + j < len(pg):
                row = pg.iloc[pos + j]
                bolus = float(row.get("bolus", 0) or 0)
                smb = float(row.get("bolus_smb", 0) or 0)
                net_basal = float(row.get("net_basal", 0) or 0)
                sched_basal = float(row.get("scheduled_basal_rate", 0) or 0)
                excess_basal = (net_basal - sched_basal) * 5 / 60
                total_insulin += bolus + smb + excess_basal

        expected_drop = total_insulin * isf
        if expected_drop > 5:
            corrections.append(actual_drop / expected_drop)

    if len(corrections) >= 5:
        cf = float(np.median(corrections))
        return np.clip(cf, 0.2, 5.0)
    return 1.0


def extract_cr_correction(pg: pd.DataFrame) -> float:
    """Extract CR from bilateral meal deconfounding on training data.

    Method: For meal events (carbs≥10), compute effective CR:
    - BG rise after meal (subtract insulin BGI contribution)
    - Effective CR = carbs / (BG_rise_explained_by_carbs / ISF)
    """
    cr_values = []

    mask = pg["carbs"] >= MEAL_MIN_CARBS
    event_idx = pg.index[mask]

    for idx in event_idx:
        pos = pg.index.get_loc(idx)
        if pos + CORRECTION_HORIZON >= len(pg):
            continue

        bg0 = float(pg.iloc[pos]["glucose"])
        bg_peak_window = pg.iloc[pos:pos + CORRECTION_HORIZON]["glucose"]
        bg_peak = float(bg_peak_window.max())

        if np.isnan(bg0) or np.isnan(bg_peak):
            continue

        raw_rise = bg_peak - bg0

        # Subtract estimated insulin effect (bilateral deconfounding)
        isf = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)
        total_insulin = 0
        for j in range(CORRECTION_HORIZON):
            if pos + j < len(pg):
                row = pg.iloc[pos + j]
                bolus = float(row.get("bolus", 0) or 0)
                smb = float(row.get("bolus_smb", 0) or 0)
                net_basal = float(row.get("net_basal", 0) or 0)
                sched_basal = float(row.get("scheduled_basal_rate", 0) or 0)
                excess_basal = (net_basal - sched_basal) * 5 / 60
                total_insulin += bolus + smb + excess_basal

        insulin_effect = total_insulin * isf  # Expected BG drop from insulin
        carb_rise = raw_rise + insulin_effect  # What carbs actually did

        carbs = float(pg.iloc[pos]["carbs"])
        if carb_rise > 5 and carbs > 0:
            # CR = carbs / insulin_equiv, where insulin_equiv = carb_rise / ISF
            insulin_equiv = carb_rise / isf
            if insulin_equiv > 0.1:
                effective_cr = carbs / insulin_equiv
                if 1 < effective_cr < 50:
                    cr_values.append(effective_cr)

    if len(cr_values) >= 5:
        return float(np.median(cr_values))
    return None


def evaluate_on_episodes(pg: pd.DataFrame, isf_correction: float,
                          cr_correction: float, profile_cr: float) -> dict:
    """Evaluate settings on correction and meal episodes via simple prediction."""
    correction_results = {"profile": [], "corrected": []}
    meal_results = {"profile": [], "corrected": []}

    # Correction episodes
    mask = (pg["glucose"] >= BG_MIN_CORRECTION) & (pg["bolus"] > 0)
    for idx in pg.index[mask]:
        pos = pg.index.get_loc(idx)
        if pos + CORRECTION_HORIZON >= len(pg):
            continue

        bg0 = float(pg.iloc[pos]["glucose"])
        actual_traj = pg.iloc[pos:pos + CORRECTION_HORIZON]["glucose"].values
        if np.isnan(actual_traj).sum() > len(actual_traj) * 0.3:
            continue

        isf_profile = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)
        isf_corrected = isf_profile * isf_correction

        # Simple prediction: BG_t = BG_0 - cumulative_insulin × ISF
        predicted_profile = np.full(CORRECTION_HORIZON, bg0)
        predicted_corrected = np.full(CORRECTION_HORIZON, bg0)
        cum_insulin = 0

        for j in range(CORRECTION_HORIZON):
            if pos + j < len(pg):
                row = pg.iloc[pos + j]
                bolus = float(row.get("bolus", 0) or 0)
                smb = float(row.get("bolus_smb", 0) or 0)
                net_basal = float(row.get("net_basal", 0) or 0)
                sched_basal = float(row.get("scheduled_basal_rate", 0) or 0)
                excess_basal = (net_basal - sched_basal) * 5 / 60
                cum_insulin += bolus + smb + excess_basal

            predicted_profile[j] = bg0 - cum_insulin * isf_profile
            predicted_corrected[j] = bg0 - cum_insulin * isf_corrected

        actual_interp = pd.Series(actual_traj).interpolate(limit_direction="both").values
        mae_profile = float(np.nanmean(np.abs(actual_interp - predicted_profile)))
        mae_corrected = float(np.nanmean(np.abs(actual_interp - predicted_corrected)))

        correction_results["profile"].append(mae_profile)
        correction_results["corrected"].append(mae_corrected)

    # Meal episodes
    mask = pg["carbs"] >= MEAL_MIN_CARBS
    for idx in pg.index[mask]:
        pos = pg.index.get_loc(idx)
        if pos + CORRECTION_HORIZON >= len(pg):
            continue

        bg0 = float(pg.iloc[pos]["glucose"])
        actual_traj = pg.iloc[pos:pos + CORRECTION_HORIZON]["glucose"].values
        if np.isnan(actual_traj).sum() > len(actual_traj) * 0.3:
            continue

        carbs = float(pg.iloc[pos]["carbs"])
        isf = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)

        # Profile prediction
        cr_prof = float(pg.iloc[pos].get("scheduled_cr", 10) or 10)
        carb_rise_prof = (carbs / cr_prof) * isf
        # Corrected prediction
        cr_corr = cr_correction if cr_correction else cr_prof
        isf_corr = isf * isf_correction
        carb_rise_corr = (carbs / cr_corr) * isf_corr

        # Simple linear absorption over 2h
        predicted_profile = np.array([bg0 + carb_rise_prof * (j / CORRECTION_HORIZON)
                                       for j in range(CORRECTION_HORIZON)])
        predicted_corrected = np.array([bg0 + carb_rise_corr * (j / CORRECTION_HORIZON)
                                         for j in range(CORRECTION_HORIZON)])

        # Subtract insulin effect
        cum_insulin = 0
        for j in range(CORRECTION_HORIZON):
            if pos + j < len(pg):
                row = pg.iloc[pos + j]
                bolus = float(row.get("bolus", 0) or 0)
                smb = float(row.get("bolus_smb", 0) or 0)
                net_basal = float(row.get("net_basal", 0) or 0)
                sched_basal = float(row.get("scheduled_basal_rate", 0) or 0)
                excess_basal = (net_basal - sched_basal) * 5 / 60
                cum_insulin += bolus + smb + excess_basal
            predicted_profile[j] -= cum_insulin * isf
            predicted_corrected[j] -= cum_insulin * isf_corr

        actual_interp = pd.Series(actual_traj).interpolate(limit_direction="both").values
        mae_profile = float(np.nanmean(np.abs(actual_interp - predicted_profile)))
        mae_corrected = float(np.nanmean(np.abs(actual_interp - predicted_corrected)))

        meal_results["profile"].append(mae_profile)
        meal_results["corrected"].append(mae_corrected)

    return {
        "n_corrections": len(correction_results["profile"]),
        "n_meals": len(meal_results["profile"]),
        "corr_profile_mae": float(np.median(correction_results["profile"])) if correction_results["profile"] else None,
        "corr_corrected_mae": float(np.median(correction_results["corrected"])) if correction_results["corrected"] else None,
        "meal_profile_mae": float(np.median(meal_results["profile"])) if meal_results["profile"] else None,
        "meal_corrected_mae": float(np.median(meal_results["corrected"])) if meal_results["corrected"] else None,
    }


def main():
    print("=" * 70)
    print("EXP-2753: Temporal Cross-Validation of Settings Pipeline")
    print("=" * 70)

    grid = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients (train={TRAIN_FRAC*100:.0f}% / test={100-TRAIN_FRAC*100:.0f}%)\n")

    results = []
    n_isf_improves_test = 0
    n_cr_improves_test = 0
    n_combined_improves = 0
    n_worse_20pct = 0
    train_improvements = []
    test_improvements = []
    n_sufficient = 0

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values(
            "time" if "time" in grid.columns else grid.columns[0]
        ).reset_index(drop=True)

        train, test = split_train_test(pg)
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10

        # Extract on train
        isf_cf = extract_isf_correction(train)
        cr_corr = extract_cr_correction(train)

        # Evaluate on TRAIN
        train_eval = evaluate_on_episodes(train, isf_cf, cr_corr, profile_cr)
        # Evaluate on TEST
        test_eval = evaluate_on_episodes(test, isf_cf, cr_corr, profile_cr)

        # Combined MAE (correction + meal)
        def combined_mae(ev, key):
            vals = []
            if ev.get(f"corr_{key}_mae") is not None:
                vals.append(ev[f"corr_{key}_mae"])
            if ev.get(f"meal_{key}_mae") is not None:
                vals.append(ev[f"meal_{key}_mae"])
            return float(np.mean(vals)) if vals else None

        train_prof = combined_mae(train_eval, "profile")
        train_corr = combined_mae(train_eval, "corrected")
        test_prof = combined_mae(test_eval, "profile")
        test_corr = combined_mae(test_eval, "corrected")

        train_imp = ((train_prof - train_corr) / train_prof * 100
                     if train_prof and train_corr and train_prof > 0 else 0)
        test_imp = ((test_prof - test_corr) / test_prof * 100
                    if test_prof and test_corr and test_prof > 0 else 0)

        sufficient = (test_eval["n_corrections"] >= 5 or test_eval["n_meals"] >= 5)
        if sufficient:
            n_sufficient += 1

            # H1: ISF improves test
            if (test_eval.get("corr_corrected_mae") is not None and
                test_eval.get("corr_profile_mae") is not None and
                test_eval["corr_corrected_mae"] < test_eval["corr_profile_mae"]):
                n_isf_improves_test += 1

            # H2: CR improves test
            if (test_eval.get("meal_corrected_mae") is not None and
                test_eval.get("meal_profile_mae") is not None and
                test_eval["meal_corrected_mae"] < test_eval["meal_profile_mae"]):
                n_cr_improves_test += 1

            # H3: Combined
            if test_corr and test_prof and test_corr < test_prof:
                n_combined_improves += 1

            # H5: Safety
            if test_prof and test_corr and test_corr > test_prof * 1.2:
                n_worse_20pct += 1

            train_improvements.append(train_imp)
            test_improvements.append(test_imp)

        entry = {
            "patient_id": pid,
            "sufficient": sufficient,
            "isf_correction": float(isf_cf),
            "cr_correction": float(cr_corr) if cr_corr else None,
            "train_n_corr": train_eval["n_corrections"],
            "train_n_meal": train_eval["n_meals"],
            "test_n_corr": test_eval["n_corrections"],
            "test_n_meal": test_eval["n_meals"],
            "train_profile_mae": train_prof,
            "train_corrected_mae": train_corr,
            "train_improvement_pct": float(train_imp),
            "test_profile_mae": test_prof,
            "test_corrected_mae": test_corr,
            "test_improvement_pct": float(test_imp),
        }
        results.append(entry)

        status = "✓" if (test_corr and test_prof and test_corr < test_prof) else "✗"
        print(f"  {pid[:16]:<18} ISF_cf={isf_cf:.2f} CR={cr_corr or 0:.1f}  "
              f"train={train_imp:+5.1f}%  test={test_imp:+5.1f}%  "
              f"n_test={test_eval['n_corrections']+test_eval['n_meals']:>4} {status}")

    # Hypotheses
    print(f"\n{'=' * 70}")
    N = max(n_sufficient, 1)

    h1 = n_isf_improves_test / N > 0.5
    h2 = n_cr_improves_test / N > 0.5
    h3 = n_combined_improves / N > 0.5

    # H4: Stability — test improvement within 80% of train improvement
    if train_improvements and test_improvements:
        stability_ratios = []
        for ti, te in zip(train_improvements, test_improvements):
            if abs(ti) > 1:
                stability_ratios.append(te / ti if ti != 0 else 0)
        median_stability = float(np.median(stability_ratios)) if stability_ratios else 0
        h4 = median_stability > 0.8
    else:
        median_stability = 0
        h4 = False

    h5 = n_worse_20pct == 0

    passed = sum([h1, h2, h3, h4, h5])
    hypotheses = {
        "H1_isf_improves_test": {"passed": bool(h1), "n": n_isf_improves_test, "N": N},
        "H2_cr_improves_test": {"passed": bool(h2), "n": n_cr_improves_test, "N": N},
        "H3_combined_improves": {"passed": bool(h3), "n": n_combined_improves, "N": N},
        "H4_stability_80pct": {"passed": bool(h4), "median_stability": median_stability},
        "H5_safety_no_20pct_worse": {"passed": bool(h5), "n_worse": n_worse_20pct},
    }

    print(f"HYPOTHESES: {passed}/5 pass (N={n_sufficient} sufficient patients)")
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v and "N" in v:
            print(f"  {tag} {k}: {v['n']}/{v['N']} ({v['n']/v['N']:.0%})")
        elif "median_stability" in v:
            print(f"  {tag} {k}: stability ratio = {v['median_stability']:.2f}")
        else:
            print(f"  {tag} {k}: {v.get('n_worse', 0)} patients >20% worse")

    if train_improvements and test_improvements:
        print(f"\n  Median train improvement: {np.median(train_improvements):+.1f}%")
        print(f"  Median test improvement: {np.median(test_improvements):+.1f}%")
        print(f"  Correlation train↔test: {np.corrcoef(train_improvements, test_improvements)[0,1]:.3f}")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2753_temporal_crossval.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2753",
            "title": "Temporal Cross-Validation of Settings Pipeline",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "train_fraction": TRAIN_FRAC,
            "hypotheses": hypotheses,
            "per_patient": results,
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(results, hypotheses, train_improvements, test_improvements)


def create_dashboard(results, hypotheses, train_imp, test_imp):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    suf = [r for r in results if r.get("sufficient")]
    if not suf:
        return

    fig = plt.figure(figsize=(18, 12))
    fig.suptitle("EXP-2753: Temporal Cross-Validation", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: Train vs Test improvement
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(train_imp, test_imp, c="steelblue", s=60, alpha=0.7)
    lim = max(abs(min(train_imp + test_imp)), abs(max(train_imp + test_imp))) * 1.2
    ax1.plot([-lim, lim], [-lim, lim], "r--", lw=1, label="Perfect transfer")
    ax1.plot([-lim, lim], [0, 0], "gray", ls="--", lw=0.5)
    ax1.plot([0, 0], [-lim, lim], "gray", ls="--", lw=0.5)
    ax1.set_xlabel("Train Set Improvement (%)")
    ax1.set_ylabel("Test Set Improvement (%)")
    ax1.set_title("Train vs Test Improvement")
    ax1.legend()

    # Panel 2: Test improvement distribution
    ax2 = fig.add_subplot(gs[0, 1])
    colors = ["#59a14f" if v > 0 else "#e15759" for v in test_imp]
    ax2.barh(range(len(suf)), [r["test_improvement_pct"] for r in suf], color=colors)
    ax2.set_yticks(range(len(suf)))
    ax2.set_yticklabels([r["patient_id"][:10] for r in suf], fontsize=7)
    ax2.axvline(0, color="black", lw=0.5)
    ax2.set_xlabel("Test Set Improvement (%)")
    ax2.set_title("Per-Patient Test Performance")

    # Panel 3: ISF correction stability
    ax3 = fig.add_subplot(gs[0, 2])
    isf_cfs = [r["isf_correction"] for r in suf]
    ax3.hist(isf_cfs, bins=15, color="steelblue", edgecolor="white")
    ax3.axvline(1.0, color="red", ls="--", lw=2, label="No correction")
    ax3.set_xlabel("ISF Correction Factor")
    ax3.set_ylabel("Patients")
    ax3.set_title("Train-Derived ISF Corrections")
    ax3.legend()

    # Panel 4: Profile MAE vs Corrected MAE (test set)
    ax4 = fig.add_subplot(gs[1, 0])
    test_profs = [r["test_profile_mae"] for r in suf if r["test_profile_mae"]]
    test_corrs = [r["test_corrected_mae"] for r in suf if r["test_corrected_mae"]]
    if test_profs and test_corrs:
        n = min(len(test_profs), len(test_corrs))
        ax4.scatter(test_profs[:n], test_corrs[:n], c="steelblue", s=60, alpha=0.7)
        lim = max(max(test_profs[:n]), max(test_corrs[:n])) * 1.1
        ax4.plot([0, lim], [0, lim], "r--", lw=1)
        ax4.set_xlabel("Test Profile MAE (mg/dL)")
        ax4.set_ylabel("Test Corrected MAE (mg/dL)")
        ax4.set_title("Test Set: Profile vs Corrected MAE")

    # Panel 5: Hypotheses
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v and "N" in v:
            h_text += f"\n{tag} {k}: {v['n']}/{v['N']}"
        elif "median_stability" in v:
            h_text += f"\n{tag} {k}: {v['median_stability']:.2f}"
        else:
            h_text += f"\n{tag} {k}: {v.get('n_worse', 0)} worse"
    ax5.text(0.1, 0.9, h_text, transform=ax5.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    r_val = np.corrcoef(train_imp, test_imp)[0, 1] if len(train_imp) > 2 else 0
    txt = f"""TEMPORAL CROSS-VALIDATION

Train/Test split: {TRAIN_FRAC*100:.0f}%/{100-TRAIN_FRAC*100:.0f}%
Patients sufficient: {len(suf)}/{len(results)}

Median train improvement: {np.median(train_imp):+.1f}%
Median test improvement:  {np.median(test_imp):+.1f}%
Train↔Test correlation:   r = {r_val:.3f}

Settings derived from training data
{"generalize" if np.median(test_imp) > 0 else "do NOT generalize"} to unseen time periods.
"""
    ax6.text(0.02, 0.95, txt.strip(), transform=ax6.transAxes, fontsize=9,
             va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2753-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2753-dashboard.png'}")


if __name__ == "__main__":
    main()
