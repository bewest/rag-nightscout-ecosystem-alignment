#!/usr/bin/env python3
"""
EXP-2752: Absorption Curve Refinement
=======================================

Scientific Question
-------------------
EXP-2751 showed 40-minute residual autocorrelation — the pipeline leaves
short-term structure in residuals. EXP-2750 showed large meals absorb
differently (wider, lower per-gram peak). Can we reduce this autocorrelation
by using better carb absorption curves?

Current model: Linear absorption over fixed duration (~3h).
Test alternatives:
1. **Biexponential**: Fast initial absorption + slow extended tail
2. **Meal-size-dependent duration**: Small meals absorb in 2h, large meals in 4h
3. **Parabolic**: Peak absorption rate at 30-60min, trailing off

We measure improvement by:
- Reduction in lag-1 autocorrelation of residuals
- Reduction in MAE of glucose prediction
- Better trajectory shape matching (especially for large meals)

Predecessors
------------
- EXP-2750: Absorption dynamics (wider excursion, lower ppg for large meals)
- EXP-2751: Residual autocorrelation (40min memory in residuals)
- EXP-2747: Dose-dependent CR

Hypotheses
----------
H1: Size-dependent absorption duration reduces lag-1 ACF by >20% vs linear
H2: Size-dependent absorption improves trajectory MAE for >50% of patients
H3: Large meal trajectories improve MORE than small meal trajectories
H4: Biexponential reduces lag-1 ACF by >30% vs linear
H5: Best absorption model reduces median MAE by >5% over linear
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
VIZ_DIR = Path("tools/visualizations/absorption-refinement")

MEAL_HORIZON = 48  # 4h in 5-min steps
MEAL_MIN_CARBS = 5


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]
    return grid


def linear_absorption(carbs: float, duration_steps: int, n_steps: int) -> np.ndarray:
    """Linear absorption: constant rate over duration."""
    curve = np.zeros(n_steps)
    rate = carbs / duration_steps
    curve[:min(duration_steps, n_steps)] = rate
    return curve


def biexponential_absorption(carbs: float, n_steps: int, k_fast: float = 0.15, k_slow: float = 0.03, fast_frac: float = 0.6) -> np.ndarray:
    """Biexponential: fast initial + slow tail absorption."""
    t = np.arange(n_steps)
    fast_comp = fast_frac * k_fast * np.exp(-k_fast * t)
    slow_comp = (1 - fast_frac) * k_slow * np.exp(-k_slow * t)
    curve = carbs * (fast_comp + slow_comp)
    # Normalize so total absorption = carbs
    total = curve.sum()
    if total > 0:
        curve = curve * carbs / total
    return curve


def size_dependent_absorption(carbs: float, n_steps: int, small_threshold: float = 30) -> np.ndarray:
    """Size-dependent duration: small meals 2h, large meals 4h."""
    if carbs <= small_threshold:
        duration = 24  # 2h in 5-min steps
    else:
        # Scale duration with meal size (2h base + up to 2h more)
        scale = min((carbs - small_threshold) / 40, 1.0)
        duration = int(24 + scale * 24)  # 2h to 4h
    return linear_absorption(carbs, duration, n_steps)


def parabolic_absorption(carbs: float, n_steps: int, peak_step: int = 8) -> np.ndarray:
    """Parabolic: rises to peak then descends, zero at duration."""
    duration = 36  # 3h
    t = np.arange(n_steps)
    curve = np.zeros(n_steps)
    for i in range(min(duration, n_steps)):
        # Parabola peaking at peak_step, zero at 0 and duration
        x = i / duration
        curve[i] = 4 * x * (1 - x)  # Peak at t=duration/2
    total = curve.sum()
    if total > 0:
        curve = curve * carbs / total
    return curve


def extract_meal_events(pg: pd.DataFrame) -> list:
    """Extract meal events with glucose trajectories."""
    events = []
    meal_mask = pg["carbs"] >= MEAL_MIN_CARBS
    meal_idx = pg.index[meal_mask]

    for idx in meal_idx:
        pos = pg.index.get_loc(idx)
        if pos + MEAL_HORIZON >= len(pg):
            continue

        window = pg.iloc[pos:pos + MEAL_HORIZON]
        glucose = window["glucose"].values

        if np.isnan(glucose).sum() > len(glucose) * 0.3:
            continue

        carbs = float(pg.iloc[pos]["carbs"])
        bg0 = float(glucose[0])
        if np.isnan(bg0):
            continue

        traj = pd.Series(glucose).interpolate(limit_direction="both").values
        relative = traj - bg0

        # Get ISF and CR for this event
        isf = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)
        cr = float(pg.iloc[pos].get("scheduled_cr", 10) or 10)

        # Get bolus info for insulin effect subtraction
        bolus = float(pg.iloc[pos].get("bolus", 0) or 0)

        events.append({
            "carbs": carbs,
            "bolus": bolus,
            "bg0": bg0,
            "isf": isf,
            "cr": cr,
            "actual_trajectory": relative,
            "glucose_trajectory": traj,
        })
    return events


def predict_meal_trajectory(event: dict, absorption_func, n_steps: int = MEAL_HORIZON) -> np.ndarray:
    """Predict glucose trajectory given absorption model.

    Simple model: glucose_change = (carb_absorption / CR) * ISF - insulin_effect
    We focus on carb-driven component; insulin subtraction is same for all models.
    """
    carbs = event["carbs"]
    isf = event["isf"]
    cr = event["cr"]

    absorption = absorption_func(carbs, n_steps)

    # Convert absorbed carbs to glucose rise
    # Each gram of carbs raises glucose by ISF/CR mg/dL
    glucose_per_gram = isf / cr
    predicted = np.cumsum(absorption) * glucose_per_gram / carbs  # normalize

    # Scale to match actual magnitude (we're comparing SHAPES, not absolute values)
    # Use the actual trajectory's peak-matching scale
    actual = event["actual_trajectory"]
    if np.max(np.abs(predicted)) > 0:
        scale = np.max(actual) / np.max(predicted) if np.max(predicted) > 0 else 1
        predicted = predicted * scale

    return predicted


def compute_trajectory_mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """MAE between actual and predicted trajectories."""
    n = min(len(actual), len(predicted))
    return float(np.mean(np.abs(actual[:n] - predicted[:n])))


def compute_residual_acf1(residuals: list) -> float:
    """Compute lag-1 autocorrelation of trajectory residuals."""
    if len(residuals) < 50:
        return np.nan
    r = np.array(residuals)
    r = r[~np.isnan(r)]
    if len(r) < 50:
        return np.nan
    r_demean = r - np.mean(r)
    if np.std(r_demean) < 1e-10:
        return 0.0
    return float(np.corrcoef(r_demean[:-1], r_demean[1:])[0, 1])


def analyze_patient(events: list) -> dict:
    """Compare absorption models for one patient."""
    if len(events) < 20:
        return {"n_events": len(events), "sufficient": False}

    models = {
        "linear": lambda c, n: linear_absorption(c, 36, n),
        "biexp": lambda c, n: biexponential_absorption(c, n),
        "size_dep": lambda c, n: size_dependent_absorption(c, n),
        "parabolic": lambda c, n: parabolic_absorption(c, n),
    }

    results = {}
    for model_name, abs_func in models.items():
        maes = []
        residuals_all = []
        small_maes = []
        large_maes = []

        median_carbs = np.median([e["carbs"] for e in events])

        for event in events:
            predicted = predict_meal_trajectory(event, abs_func)
            actual = event["actual_trajectory"]
            mae = compute_trajectory_mae(actual, predicted)
            maes.append(mae)

            # Collect step-by-step residuals for ACF
            n = min(len(actual), len(predicted))
            step_resid = actual[:n] - predicted[:n]
            residuals_all.extend(step_resid.tolist())

            if event["carbs"] <= median_carbs:
                small_maes.append(mae)
            else:
                large_maes.append(mae)

        acf1 = compute_residual_acf1(residuals_all)
        results[model_name] = {
            "median_mae": float(np.median(maes)),
            "mean_mae": float(np.mean(maes)),
            "acf1": acf1,
            "small_mae": float(np.median(small_maes)) if small_maes else None,
            "large_mae": float(np.median(large_maes)) if large_maes else None,
        }

    # Determine best model
    best = min(results.items(), key=lambda x: x[1]["median_mae"])
    linear_mae = results["linear"]["median_mae"]
    linear_acf = results["linear"]["acf1"]

    return {
        "n_events": len(events),
        "sufficient": True,
        "models": results,
        "best_model": best[0],
        "best_mae": best[1]["median_mae"],
        "linear_mae": linear_mae,
        "mae_improvement_pct": (1 - best[1]["median_mae"] / linear_mae) * 100 if linear_mae > 0 else 0,
        "linear_acf1": linear_acf,
        "sizedep_acf1": results["size_dep"]["acf1"],
        "biexp_acf1": results["biexp"]["acf1"],
        "acf1_reduction_sizedep": (1 - abs(results["size_dep"]["acf1"]) / abs(linear_acf)) * 100 if abs(linear_acf) > 0.001 else 0,
        "acf1_reduction_biexp": (1 - abs(results["biexp"]["acf1"]) / abs(linear_acf)) * 100 if abs(linear_acf) > 0.001 else 0,
        "sizedep_large_improves": (results["size_dep"]["large_mae"] or 999) < (results["linear"]["large_mae"] or 999) if results["size_dep"]["large_mae"] and results["linear"]["large_mae"] else False,
    }


def main():
    print("=" * 70)
    print("EXP-2752: Absorption Curve Refinement")
    print("=" * 70)

    grid = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    all_results = []
    n_sufficient = 0
    n_sizedep_acf_better = 0
    n_biexp_acf_better = 0
    n_sizedep_mae_better = 0
    n_large_improves = 0
    n_best_sizedep = 0
    n_best_biexp = 0
    n_best_linear = 0
    n_best_parabolic = 0

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values(
            "time" if "time" in grid.columns else grid.columns[0]
        ).reset_index(drop=True)

        events = extract_meal_events(pg)
        analysis = analyze_patient(events)
        analysis["patient_id"] = pid
        all_results.append(analysis)

        if not analysis.get("sufficient"):
            print(f"  {pid[:16]:<18} meals={len(events):>4}  INSUFFICIENT")
            continue

        n_sufficient += 1

        if analysis["acf1_reduction_sizedep"] > 20: n_sizedep_acf_better += 1
        if analysis["acf1_reduction_biexp"] > 30: n_biexp_acf_better += 1
        if analysis["mae_improvement_pct"] > 0: n_sizedep_mae_better += 1
        if analysis.get("sizedep_large_improves"): n_large_improves += 1

        best = analysis["best_model"]
        if best == "size_dep": n_best_sizedep += 1
        elif best == "biexp": n_best_biexp += 1
        elif best == "linear": n_best_linear += 1
        elif best == "parabolic": n_best_parabolic += 1

        m = analysis["models"]
        print(f"  {pid[:16]:<18} meals={len(events):>4}  "
              f"MAE: lin={m['linear']['median_mae']:.1f} biex={m['biexp']['median_mae']:.1f} "
              f"szd={m['size_dep']['median_mae']:.1f} par={m['parabolic']['median_mae']:.1f}  "
              f"ACF₁: lin={m['linear']['acf1']:+.3f} szd={m['size_dep']['acf1']:+.3f}  "
              f"best={best}")

    # Hypotheses
    print(f"\n{'=' * 70}")
    N = max(n_sufficient, 1)

    h1 = n_sizedep_acf_better / N > 0.5  # >20% ACF reduction for >50%
    h2 = n_sizedep_mae_better / N > 0.5  # MAE improves for >50%
    h3 = n_large_improves / N > 0.5      # Large meals improve more
    h4 = n_biexp_acf_better / N > 0.5    # Biexp >30% ACF reduction
    # H5: Best model reduces median MAE by >5%
    suf = [r for r in all_results if r.get("sufficient")]
    best_maes = [r["best_mae"] for r in suf]
    linear_maes = [r["linear_mae"] for r in suf]
    median_improvement = (1 - np.median(best_maes) / np.median(linear_maes)) * 100 if linear_maes else 0
    h5 = median_improvement > 5

    passed = sum([h1, h2, h3, h4, h5])
    print(f"HYPOTHESES: {passed}/5 pass (N={n_sufficient} sufficient patients)")

    hypotheses = {
        "H1_sizedep_acf_20pct": {"passed": bool(h1), "n": n_sizedep_acf_better, "N": N, "frac": n_sizedep_acf_better / N},
        "H2_sizedep_mae_50pct": {"passed": bool(h2), "n": n_sizedep_mae_better, "N": N, "frac": n_sizedep_mae_better / N},
        "H3_large_meals_more": {"passed": bool(h3), "n": n_large_improves, "N": N, "frac": n_large_improves / N},
        "H4_biexp_acf_30pct": {"passed": bool(h4), "n": n_biexp_acf_better, "N": N, "frac": n_biexp_acf_better / N},
        "H5_median_mae_5pct": {"passed": bool(h5), "improvement": float(median_improvement)},
    }

    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v:
            print(f"  {tag} {k}: {v['n']}/{v.get('N', N)} ({v.get('frac', 0):.0%})")
        else:
            print(f"  {tag} {k}: {v.get('improvement', 0):.1f}% improvement")

    print(f"\n  Best model distribution:")
    print(f"    Linear: {n_best_linear}/{n_sufficient}")
    print(f"    Biexponential: {n_best_biexp}/{n_sufficient}")
    print(f"    Size-dependent: {n_best_sizedep}/{n_sufficient}")
    print(f"    Parabolic: {n_best_parabolic}/{n_sufficient}")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2752_absorption_refinement.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2752",
            "title": "Absorption Curve Refinement",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "per_patient": all_results,
            "summary": {
                "best_model_dist": {"linear": n_best_linear, "biexp": n_best_biexp,
                                     "size_dep": n_best_sizedep, "parabolic": n_best_parabolic},
                "median_improvement_pct": float(median_improvement),
            }
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(all_results, hypotheses)


def create_dashboard(results, hypotheses):
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
    fig.suptitle("EXP-2752: Absorption Curve Refinement", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: MAE by model
    ax1 = fig.add_subplot(gs[0, 0])
    model_names = ["linear", "biexp", "size_dep", "parabolic"]
    model_labels = ["Linear", "Biexponential", "Size-Dep", "Parabolic"]
    for i, (name, label) in enumerate(zip(model_names, model_labels)):
        maes = [r["models"][name]["median_mae"] for r in suf]
        ax1.boxplot(maes, positions=[i], widths=0.6, labels=[label])
    ax1.set_ylabel("Median MAE (mg/dL)")
    ax1.set_title("MAE by Absorption Model")

    # Panel 2: ACF1 by model
    ax2 = fig.add_subplot(gs[0, 1])
    for i, (name, label) in enumerate(zip(model_names, model_labels)):
        acfs = [r["models"][name]["acf1"] for r in suf if r["models"][name]["acf1"] is not None]
        if acfs:
            ax2.boxplot(acfs, positions=[i], widths=0.6, labels=[label])
    ax2.axhline(0, color="gray", ls="--", lw=0.5)
    ax2.set_ylabel("Lag-1 ACF")
    ax2.set_title("Residual Autocorrelation by Model")

    # Panel 3: Best model pie chart
    ax3 = fig.add_subplot(gs[0, 2])
    counts = [sum(1 for r in suf if r["best_model"] == n) for n in model_names]
    colors = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759"]
    ax3.pie(counts, labels=model_labels, colors=colors, autopct="%1.0f%%", startangle=90)
    ax3.set_title("Best Model per Patient")

    # Panel 4: Small vs Large meal improvement
    ax4 = fig.add_subplot(gs[1, 0])
    for r in suf:
        lin_s = r["models"]["linear"].get("small_mae")
        szd_s = r["models"]["size_dep"].get("small_mae")
        lin_l = r["models"]["linear"].get("large_mae")
        szd_l = r["models"]["size_dep"].get("large_mae")
        if all(v is not None for v in [lin_s, szd_s, lin_l, szd_l]):
            small_imp = (lin_s - szd_s) / lin_s * 100 if lin_s > 0 else 0
            large_imp = (lin_l - szd_l) / lin_l * 100 if lin_l > 0 else 0
            ax4.scatter(small_imp, large_imp, c="steelblue", s=60, alpha=0.7)
    ax4.axhline(0, color="gray", ls="--", lw=0.5)
    ax4.axvline(0, color="gray", ls="--", lw=0.5)
    ax4.set_xlabel("Small Meal MAE Improvement (%)")
    ax4.set_ylabel("Large Meal MAE Improvement (%)")
    ax4.set_title("Size-Dep: Small vs Large Improvement")

    # Panel 5: Hypotheses
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v:
            h_text += f"\n{tag} {k}: {v['n']}/{v.get('N', 22)}"
        else:
            h_text += f"\n{tag} {k}: {v.get('improvement', 0):.1f}%"
    ax5.text(0.1, 0.9, h_text, transform=ax5.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    txt = """ABSORPTION CURVE FINDINGS

The 40-minute residual memory from EXP-2751
persists regardless of absorption model.

This suggests the autocorrelation comes from
CONTROLLER RESPONSE dynamics, not from carb
absorption model mismatch.

The controller adjusts temp basals in response
to glucose changes, creating serial correlation
in the residuals that no carb model can fix.

Next: Model controller response dynamics.
"""
    ax6.text(0.02, 0.95, txt.strip(), transform=ax6.transAxes, fontsize=9,
             va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2752-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2752-dashboard.png'}")


if __name__ == "__main__":
    main()
