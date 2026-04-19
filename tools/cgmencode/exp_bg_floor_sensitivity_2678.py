#!/usr/bin/env python3
"""EXP-2678: BG Floor Sensitivity Analysis

EXP-2677 showed that 57% of "correction" events have negative ISF because
they occur at in-range glucose (misclassified meals). None of EXP-2673-2675
used a BG floor filter.

This experiment re-runs KEY analyses from those experiments with BG ≥ 150
to determine if conclusions change:

  A. Circadian ISF (from 2673) — did the no-circadian-signal finding hold?
  B. ISF variance decomposition (from 2675) — patient vs controller %
  C. DynISF inflation ratio (from 2674) — sigmoid 6.6× vs log 2.5×

If conclusions are robust to BG floor, our methodology is sound.
If they change, earlier experiments need qualification.
"""

import json
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
DS = ROOT / "externals/ns-parquet/training/devicestatus.parquet"
MANIFEST = ROOT / "externals/experiments/autoprepare-qualified.json"
VIS_DIR = ROOT / "visualizations/bg-floor-sensitivity"
EXP_DIR = ROOT / "externals/experiments"

VIS_DIR.mkdir(parents=True, exist_ok=True)

BG_FLOORS = [0, 120, 150, 180]  # 0 = no filter (baseline)
PRIOR_ISOLATION_H = 2.0
MIN_DOSE = 0.3
MAX_COB = 5


def load_data():
    manifest = json.load(open(MANIFEST))
    qp = manifest["qualified_patients"]
    grid = pd.read_parquet(GRID)
    grid = grid[grid.patient_id.isin(qp)]
    ds = pd.read_parquet(DS)
    ds = ds[ds.patient_id.isin(qp)]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    return grid, ds, ctrl_map, qp


def extract_events(grid, bg_floor=0):
    """Extract correction events with given BG floor."""
    events = []
    for pid in grid.patient_id.unique():
        pgrid = grid[grid.patient_id == pid].sort_values("time")

        bg_mask = pgrid.glucose >= bg_floor if bg_floor > 0 else pd.Series(True, index=pgrid.index)
        corrections = pgrid[(pgrid.bolus > MIN_DOSE) & (pgrid.cob < MAX_COB) & bg_mask]

        for _, row in corrections.iterrows():
            bt = row.time
            pre = pgrid[(pgrid.time >= bt - pd.Timedelta(hours=PRIOR_ISOLATION_H)) &
                        (pgrid.time < bt)]
            if pre.bolus.sum() > 0.1:
                continue

            post = pgrid[(pgrid.time >= bt) &
                         (pgrid.time <= bt + pd.Timedelta(hours=2))]
            if len(post) < 6:
                continue

            bg0 = post.glucose.iloc[0]
            bg_2h = post.glucose.iloc[-1]
            if pd.isna(bg0) or pd.isna(bg_2h):
                continue

            drop = bg0 - bg_2h
            isf = drop / row.bolus

            events.append({
                "patient_id": pid,
                "time": bt,
                "dose": row.bolus,
                "bg_at_bolus": bg0,
                "bg_drop": drop,
                "isf": isf,
                "hour": bt.hour if hasattr(bt, "hour") else pd.Timestamp(bt).hour,
            })

    return pd.DataFrame(events)


def sensitivity_A_circadian(grid, ctrl_map):
    """Test A: Does circadian ISF finding (no signal) hold with BG floor?"""
    print("\n  Test A: Circadian ISF sensitivity")
    results = {}

    for bg_floor in BG_FLOORS:
        edf = extract_events(grid, bg_floor)
        if len(edf) < 50:
            results[bg_floor] = {"n": len(edf), "p": None}
            continue

        # 4-bin circadian test (matching EXP-2673 methodology)
        edf["time_bin"] = pd.cut(edf.hour, bins=[0, 6, 12, 18, 24],
                                 labels=["night", "morning", "afternoon", "evening"],
                                 right=False)
        groups = [g.isf.dropna().values for _, g in edf.groupby("time_bin", observed=True)
                  if len(g) >= 5]

        if len(groups) >= 3:
            stat, p = stats.kruskal(*groups)
            medians = edf.groupby("time_bin", observed=True).isf.median()
            results[bg_floor] = {
                "n": len(edf),
                "kruskal_stat": float(stat),
                "p_value": float(p),
                "signal": p < 0.05,
                "medians": {str(k): float(v) for k, v in medians.items()},
            }
            status = "SIGNAL" if p < 0.05 else "NO SIGNAL"
            print(f"    BG≥{bg_floor:3d}: n={len(edf):4d} p={p:.4f} → {status}")
        else:
            results[bg_floor] = {"n": len(edf), "p": None, "note": "too few groups"}

    return results


def sensitivity_B_variance(grid, ctrl_map):
    """Test B: Does ISF variance decomposition change with BG floor?"""
    print("\n  Test B: ISF variance decomposition sensitivity")
    results = {}

    for bg_floor in BG_FLOORS:
        edf = extract_events(grid, bg_floor)
        if len(edf) < 50:
            results[bg_floor] = {"n": len(edf)}
            continue

        edf["controller"] = edf.patient_id.map(ctrl_map)

        # Compute eta-squared for controller effect
        groups = [g.isf.dropna().values for _, g in edf.groupby("controller")
                  if len(g) >= 10]
        if len(groups) < 2:
            results[bg_floor] = {"n": len(edf), "note": "too few controllers"}
            continue

        all_isf = edf.isf.dropna()
        ss_total = ((all_isf - all_isf.mean()) ** 2).sum()
        ss_between = sum(len(g) * (np.mean(g) - all_isf.mean()) ** 2 for g in groups)
        eta_sq = ss_between / ss_total if ss_total > 0 else 0

        # Patient-level variance
        patient_groups = [g.isf.dropna().values for _, g in edf.groupby("patient_id")
                          if len(g) >= 5]
        if patient_groups:
            ss_patient = sum(len(g) * (np.mean(g) - all_isf.mean()) ** 2
                            for g in patient_groups)
            eta_patient = ss_patient / ss_total if ss_total > 0 else 0
        else:
            eta_patient = 0

        results[bg_floor] = {
            "n": len(edf),
            "eta_sq_controller": float(eta_sq),
            "eta_sq_patient": float(eta_patient),
            "pct_controller": float(100 * eta_sq),
            "pct_patient": float(100 * eta_patient),
        }
        print(f"    BG≥{bg_floor:3d}: n={len(edf):4d} "
              f"controller={100*eta_sq:.1f}% patient={100*eta_patient:.1f}%")

    return results


def sensitivity_C_dynisf(grid, ctrl_map):
    """Test C: Does DynISF inflation ratio change with BG floor?"""
    print("\n  Test C: DynISF inflation ratio sensitivity")

    FORMULA = {
        "ns-9b9a6a874e51": "sigmoid",
        "ns-adde5f4af7ca": "sigmoid",
        "ns-dde9e7c2e752": "sigmoid",
        "ns-554b16de7133": "sigmoid",
        "ns-6bef17b4c1ec": "sigmoid",
        "ns-c422538aa12a": "sigmoid",
        "ns-d444c120c23a": "log",
        "ns-8b3c1b50793c": "log",
        "ns-a9ce2317bead": "log",
        "ns-8ffa739b986b": "log",
        "ns-1ccae8a375b9": "log",
        "ns-8f3527d1ee40": "autoisf",
    }

    results = {}
    for bg_floor in BG_FLOORS:
        edf = extract_events(grid, bg_floor)
        edf["formula"] = edf.patient_id.map(FORMULA)
        edf = edf.dropna(subset=["formula"])

        if len(edf) < 20:
            results[bg_floor] = {"n": len(edf)}
            continue

        # Compare scheduled_isf (from profile) vs demand ISF
        # We need to merge scheduled_isf from grid
        merged = edf.copy()
        sched_isf = []
        for _, row in merged.iterrows():
            pgrid = grid[(grid.patient_id == row.patient_id)]
            closest = pgrid.iloc[(pgrid.time - row.time).abs().argsort()[:1]]
            if len(closest) > 0 and pd.notna(closest.scheduled_isf.iloc[0]):
                sched_isf.append(closest.scheduled_isf.iloc[0])
            else:
                sched_isf.append(np.nan)
        merged["scheduled_isf"] = sched_isf

        valid = merged.dropna(subset=["scheduled_isf", "isf"])
        valid = valid[valid.isf > 0]  # only positive ISF for inflation calc

        if len(valid) < 10:
            results[bg_floor] = {"n": len(edf), "n_valid": len(valid)}
            continue

        valid["inflation"] = valid.scheduled_isf / valid.isf

        by_formula = {}
        for formula in ["sigmoid", "log"]:
            fsub = valid[valid.formula == formula]
            if len(fsub) > 5:
                med = fsub.inflation.median()
                by_formula[formula] = {"n": len(fsub), "median_inflation": float(med)}
                print(f"    BG≥{bg_floor:3d} {formula}: n={len(fsub):4d} "
                      f"inflation={med:.1f}×")

        results[bg_floor] = {
            "n": len(edf),
            "n_positive_isf": len(valid),
            "by_formula": by_formula,
        }

    return results


def make_summary_figure(results_a, results_b, results_c):
    """Create summary visualization showing sensitivity across BG floors."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # A: Circadian p-value
    ax = axes[0]
    floors = [f for f in BG_FLOORS if results_a.get(f, {}).get("p_value") is not None]
    pvals = [results_a[f]["p_value"] for f in floors]
    ns = [results_a[f]["n"] for f in floors]
    ax.plot(floors, pvals, "bo-", lw=2, markersize=8)
    ax.axhline(0.05, color="red", ls="--", label="p=0.05 significance")
    for f, p, n in zip(floors, pvals, ns):
        ax.annotate(f"n={n}", (f, p), textcoords="offset points",
                    xytext=(5, 10), fontsize=8)
    ax.set_xlabel("BG Floor (mg/dL)")
    ax.set_ylabel("Kruskal-Wallis p-value")
    ax.set_title("A: Circadian ISF Signal")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, max(pvals) * 1.3 if pvals else 1)

    # B: Variance decomposition
    ax = axes[1]
    floors_b = [f for f in BG_FLOORS if "pct_controller" in results_b.get(f, {})]
    ctrl_pct = [results_b[f]["pct_controller"] for f in floors_b]
    pat_pct = [results_b[f]["pct_patient"] for f in floors_b]
    ax.plot(floors_b, ctrl_pct, "rs-", lw=2, markersize=8, label="Controller η²")
    ax.plot(floors_b, pat_pct, "bo-", lw=2, markersize=8, label="Patient η²")
    ax.set_xlabel("BG Floor (mg/dL)")
    ax.set_ylabel("% Variance Explained")
    ax.set_title("B: ISF Variance Decomposition")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # C: DynISF inflation
    ax = axes[2]
    for formula, color, marker in [("sigmoid", "red", "s"), ("log", "blue", "o")]:
        floors_c = []
        inflations = []
        for f in BG_FLOORS:
            r = results_c.get(f, {}).get("by_formula", {}).get(formula)
            if r and r.get("median_inflation"):
                floors_c.append(f)
                inflations.append(r["median_inflation"])
        if floors_c:
            ax.plot(floors_c, inflations, color=color, marker=marker, lw=2,
                    markersize=8, label=f"{formula}")
    ax.set_xlabel("BG Floor (mg/dL)")
    ax.set_ylabel("Profile ISF / Demand ISF (×)")
    ax.set_title("C: DynISF Inflation Ratio")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(1, color="gray", ls=":", alpha=0.5)

    fig.suptitle("EXP-2678: BG Floor Sensitivity Analysis", y=1.03, fontsize=14)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig1_sensitivity_summary.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("\n  Summary figure saved")


def main():
    print("=" * 70)
    print("EXP-2678: BG Floor Sensitivity Analysis")
    print("=" * 70)

    print("\nLoading data...")
    grid, ds, ctrl_map, qp = load_data()
    print(f"  {len(qp)} patients loaded")

    results = {
        "experiment": "EXP-2678",
        "title": "BG Floor Sensitivity Analysis",
        "bg_floors_tested": BG_FLOORS,
    }

    print("\nRunning sensitivity tests...")
    results["circadian"] = sensitivity_A_circadian(grid, ctrl_map)
    results["variance"] = sensitivity_B_variance(grid, ctrl_map)
    results["dynisf"] = sensitivity_C_dynisf(grid, ctrl_map)

    make_summary_figure(results["circadian"], results["variance"], results["dynisf"])

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SENSITIVITY VERDICTS")
    print("=" * 70)

    # A: Circadian
    print("\n## A: Circadian ISF")
    any_signal = False
    for f in BG_FLOORS:
        r = results["circadian"].get(f, {})
        if r.get("p_value") is not None:
            sig = "SIGNAL ⚠️" if r["p_value"] < 0.05 else "no signal ✅"
            print(f"  BG≥{f:3d}: p={r['p_value']:.4f} ({sig}, n={r['n']})")
            if r["p_value"] < 0.05:
                any_signal = True
    verdict_a = "SENSITIVE" if any_signal else "ROBUST"
    print(f"  Verdict: {verdict_a} — " +
          ("BG floor reveals/changes circadian signal" if any_signal else
           "No circadian ISF at any BG floor"))

    # B: Variance
    print("\n## B: ISF Variance Decomposition")
    for f in BG_FLOORS:
        r = results["variance"].get(f, {})
        if "pct_controller" in r:
            print(f"  BG≥{f:3d}: controller={r['pct_controller']:.1f}% "
                  f"patient={r['pct_patient']:.1f}% (n={r['n']})")
    ctrl_range = [results["variance"][f]["pct_controller"] for f in BG_FLOORS
                  if "pct_controller" in results["variance"].get(f, {})]
    verdict_b = "ROBUST" if max(ctrl_range) - min(ctrl_range) < 10 else "SENSITIVE"
    print(f"  Verdict: {verdict_b}")

    # C: DynISF
    print("\n## C: DynISF Inflation")
    for f in BG_FLOORS:
        r = results["dynisf"].get(f, {}).get("by_formula", {})
        parts = []
        for formula in ["sigmoid", "log"]:
            if formula in r:
                parts.append(f"{formula}={r[formula]['median_inflation']:.1f}×")
        if parts:
            print(f"  BG≥{f:3d}: {', '.join(parts)}")
    verdict_c = "CHECK MANUALLY"
    print(f"  Verdict: {verdict_c}")

    results["verdicts"] = {
        "circadian": verdict_a,
        "variance": verdict_b,
        "dynisf": verdict_c,
    }

    with open(EXP_DIR / "exp-2678_bg_floor_sensitivity.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {EXP_DIR / 'exp-2678_bg_floor_sensitivity.json'}")

    return results


if __name__ == "__main__":
    main()
