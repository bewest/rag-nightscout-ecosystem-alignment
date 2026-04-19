#!/usr/bin/env python3
"""EXP-2711: Circadian-Adjusted Settings Extraction

Uses BG-adjusted circadian ISF from EXP-2708 to produce actionable per-patient
settings tables. Evaluates clinical significance by comparing:
1. Profile ISF (what patients currently use)
2. Flat demand ISF (median of observed corrections)
3. Circadian demand ISF (6-block, BG-adjusted from EXP-2708)

For each patient, produces a recommended ISF schedule and evaluates how
different it is from their current profile — the "settings delta."

Hypotheses:
  H1: Circadian ISF differs from profile ISF by >20% for majority of patients
  H2: Per-patient circadian tables reduce BG prediction MAE vs flat ISF
  H3: Settings recommendations are clinically meaningful (ISF change >5 mg/dL/U)
  H4: Recommendations are stable (split-half consistency >0.5)

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2711_circadian_settings.json")
VIS_DIR = Path("visualizations/circadian-settings")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
MIN_EVENTS_PER_BLOCK = 10
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2711"
EXP_TITLE = "Circadian-Adjusted Settings Extraction"


def load_data():
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid["controller"] = grid["patient_id"].map(ctrl_map)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    grid = grid[grid["patient_id"].isin(qual)].copy()
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_and_adjust(grid):
    """Extract correction events and apply BG residualization."""
    from numpy.linalg import lstsq
    print("Extracting and adjusting events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    events = []

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue
        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
        if "scheduled_isf" not in pg.columns:
            continue
        profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or bg0 < BG_FLOOR:
                continue
            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))
            if carbs_2h > 5.0:
                continue
            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue
            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue
            try:
                hour = pd.Timestamp(pg["time"].iloc[i]).hour
            except Exception:
                hour = 0
            block_idx = min(hour // 4, 5)
            events.append({
                "patient_id": pid, "bg0": bg0, "observed_drop": observed_drop,
                "total_insulin": total_insulin, "demand_isf": demand_isf,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour, "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "controller": ctrl, "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)

    # BG residualization per patient
    adjusted = []
    for pid, pg in df.groupby("patient_id"):
        if len(pg) < 30:
            continue
        y = pg["demand_isf"].values
        med = float(np.median(y))
        X = np.column_stack([pg["bg0"].values, pg["total_insulin"].values,
                             pg["iob_start"].values, np.ones(len(pg))])
        beta, _, _, _ = lstsq(X, y, rcond=None)
        resid = y - X @ beta
        pg = pg.copy()
        pg["adjusted_isf"] = resid + med
        adjusted.append(pg)

    result = pd.concat(adjusted, ignore_index=True)
    print(f"  {len(result):,} events, {result['patient_id'].nunique()} patients")
    return result


def build_settings_table(events):
    """Build per-patient settings recommendations."""
    print("\nBuilding settings tables...")
    recommendations = []

    for pid, pg in events.groupby("patient_id"):
        ctrl = pg["controller"].iloc[0]
        profile_isf = pg["profile_isf"].iloc[0]
        flat_demand = float(pg["adjusted_isf"].median())

        rec = {
            "patient_id": pid, "controller": ctrl,
            "profile_isf": round(profile_isf, 1),
            "flat_demand_isf": round(flat_demand, 1),
            "n_events": int(len(pg)),
        }

        block_isfs = []
        for idx, bl in enumerate(BLOCK_LABELS):
            bd = pg[pg["block_idx"] == idx]["adjusted_isf"]
            if len(bd) >= MIN_EVENTS_PER_BLOCK:
                val = round(float(bd.median()), 1)
                rec[f"isf_{bl}"] = val
                block_isfs.append(val)
            else:
                rec[f"isf_{bl}"] = None
                block_isfs.append(flat_demand)
            rec[f"n_{bl}"] = int(len(bd))

        # Settings delta: how different is circadian from profile?
        deltas = [abs(v - profile_isf) for v in block_isfs]
        rec["max_delta"] = round(max(deltas), 1)
        rec["mean_delta"] = round(float(np.mean(deltas)), 1)
        rec["pct_change_max"] = round(100 * max(deltas) / max(profile_isf, 0.1), 1)

        # Circadian ratio
        if len(block_isfs) >= 2:
            rec["circadian_ratio"] = round(max(block_isfs) / max(min(block_isfs), 0.1), 2)
        else:
            rec["circadian_ratio"] = None

        recommendations.append(rec)

    return recommendations


def test_h1_profile_difference(recs):
    """H1: Circadian ISF differs from profile by >20% for majority."""
    print("\n── H1: Settings differ from profile? ──")
    pct_changes = [r["pct_change_max"] for r in recs if r["pct_change_max"] is not None]
    n_over_20 = sum(1 for p in pct_changes if p > 20)
    pct_over_20 = 100 * n_over_20 / max(len(pct_changes), 1)
    median_pct = float(np.median(pct_changes))
    verdict = bool(pct_over_20 > 50)
    print(f"  Patients with >20% ISF change: {n_over_20}/{len(pct_changes)} ({pct_over_20:.0f}%)")
    print(f"  Median max % change: {median_pct:.1f}%")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'}")
    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "pct_over_20": round(pct_over_20, 1),
        "median_max_pct_change": round(median_pct, 1),
        "n_patients": len(pct_changes),
    }


def test_h2_mae_improvement(events, recs):
    """H2: Circadian tables reduce BG prediction MAE vs flat."""
    print("\n── H2: Does circadian ISF reduce MAE? ──")

    rec_lookup = {r["patient_id"]: r for r in recs}
    per_patient = []

    for pid, pg in events.groupby("patient_id"):
        if pid not in rec_lookup:
            continue
        r = rec_lookup[pid]
        actual_drop = pg["observed_drop"].values
        dose = pg["total_insulin"].values

        # Profile ISF prediction
        pred_profile = dose * r["profile_isf"]
        mae_profile = float(np.mean(np.abs(actual_drop - pred_profile)))

        # Flat demand ISF
        pred_flat = dose * r["flat_demand_isf"]
        mae_flat = float(np.mean(np.abs(actual_drop - pred_flat)))

        # Circadian ISF
        pred_circ = np.zeros(len(pg))
        for j, (_, row) in enumerate(pg.iterrows()):
            bl = BLOCK_LABELS[row["block_idx"]]
            isf = r.get(f"isf_{bl}", r["flat_demand_isf"]) or r["flat_demand_isf"]
            pred_circ[j] = row["total_insulin"] * isf
        mae_circ = float(np.mean(np.abs(actual_drop - pred_circ)))

        per_patient.append({
            "patient_id": pid, "controller": r["controller"],
            "mae_profile": round(mae_profile, 1),
            "mae_flat": round(mae_flat, 1),
            "mae_circadian": round(mae_circ, 1),
            "improvement_vs_profile": round(100 * (mae_profile - mae_circ) / max(mae_profile, 0.1), 1),
            "improvement_vs_flat": round(100 * (mae_flat - mae_circ) / max(mae_flat, 0.1), 1),
        })

    med_profile = float(np.median([p["mae_profile"] for p in per_patient]))
    med_flat = float(np.median([p["mae_flat"] for p in per_patient]))
    med_circ = float(np.median([p["mae_circadian"] for p in per_patient]))
    n_improved = sum(1 for p in per_patient if p["mae_circadian"] < p["mae_flat"])
    pct = 100 * n_improved / max(len(per_patient), 1)

    verdict = bool(med_circ < med_flat and pct > 50)
    print(f"  Median MAE profile: {med_profile:.1f}")
    print(f"  Median MAE flat:    {med_flat:.1f}")
    print(f"  Median MAE circ:    {med_circ:.1f}")
    print(f"  Improved vs flat:   {n_improved}/{len(per_patient)} ({pct:.0f}%)")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "median_mae_profile": round(med_profile, 1),
        "median_mae_flat": round(med_flat, 1),
        "median_mae_circadian": round(med_circ, 1),
        "pct_improved_vs_flat": round(pct, 1),
        "per_patient": per_patient,
    }


def test_h3_clinical_significance(recs):
    """H3: ISF changes are clinically meaningful (>5 mg/dL/U)."""
    print("\n── H3: Clinically meaningful changes? ──")
    max_deltas = [r["max_delta"] for r in recs]
    mean_deltas = [r["mean_delta"] for r in recs]
    n_over_5 = sum(1 for d in max_deltas if d > 5)
    pct = 100 * n_over_5 / max(len(max_deltas), 1)
    median_max = float(np.median(max_deltas))
    median_mean = float(np.median(mean_deltas))
    verdict = bool(pct > 50 and median_max > 5)
    print(f"  Patients with max ISF delta > 5: {n_over_5}/{len(max_deltas)} ({pct:.0f}%)")
    print(f"  Median max delta: {median_max:.1f} mg/dL/U")
    print(f"  Median mean delta: {median_mean:.1f} mg/dL/U")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'}")
    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "pct_over_5": round(pct, 1),
        "median_max_delta": round(median_max, 1),
        "median_mean_delta": round(median_mean, 1),
    }


def test_h4_stability(events):
    """H4: Split-half stability of circadian ISF tables."""
    print("\n── H4: Temporal stability? ──")
    stabilities = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 60:
            continue
        half = len(pg) // 2
        first = pg.iloc[:half]
        second = pg.iloc[half:]
        first_isfs = []
        second_isfs = []
        for idx in range(6):
            f = first[first["block_idx"] == idx]["adjusted_isf"]
            s = second[second["block_idx"] == idx]["adjusted_isf"]
            if len(f) >= 5 and len(s) >= 5:
                first_isfs.append(float(f.median()))
                second_isfs.append(float(s.median()))
        if len(first_isfs) >= 3:
            r, p = stats.pearsonr(first_isfs, second_isfs)
            stabilities.append({"patient_id": pid, "r": round(float(r), 3), "p": float(p)})

    if len(stabilities) < 5:
        return {"h4_verdict": "SKIP", "reason": "insufficient patients"}

    med_r = float(np.median([s["r"] for s in stabilities]))
    n_stable = sum(1 for s in stabilities if s["r"] > 0.5)
    pct = 100 * n_stable / len(stabilities)
    verdict = bool(med_r > 0.5 and pct > 50)

    print(f"  Median split-half r: {med_r:.3f}")
    print(f"  Patients with r>0.5: {n_stable}/{len(stabilities)} ({pct:.0f}%)")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'}")
    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "median_r": round(med_r, 3),
        "pct_stable": round(pct, 1),
        "stabilities": stabilities,
    }


def make_visualization(recs, h1, h2, h3, h4):
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Settings delta distribution
    ax = axes[0, 0]
    deltas = [r["pct_change_max"] for r in recs]
    ax.hist(deltas, bins=15, color="coral", alpha=0.8, edgecolor="black")
    ax.axvline(20, color="red", linestyle="--", label="20% threshold")
    ax.set_xlabel("Max % ISF Change from Profile")
    ax.set_ylabel("Patients")
    ax.legend(fontsize=8)
    ax.set_title(f"H1: Settings Delta [{h1['h1_verdict']}]")

    # Panel 2: MAE comparison
    ax = axes[0, 1]
    if h2.get("per_patient"):
        pp = h2["per_patient"]
        models = ["Profile ISF", "Flat Demand", "Circadian"]
        vals = [h2["median_mae_profile"], h2["median_mae_flat"], h2["median_mae_circadian"]]
        colors = ["#d32f2f", "#ff9800", "#4caf50"]
        ax.bar(models, vals, color=colors, alpha=0.85)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.5, f"{v:.0f}", ha="center", fontsize=10)
        ax.set_ylabel("Median MAE (mg/dL)")
    ax.set_title(f"H2: MAE Improvement [{h2['h2_verdict']}]")

    # Panel 3: Example patient circadian pattern
    ax = axes[1, 0]
    # Show a few patients
    for rec in recs[:5]:
        vals = [rec.get(f"isf_{bl}", None) for bl in BLOCK_LABELS]
        if all(v is not None for v in vals):
            ax.plot(range(6), vals, "o-", alpha=0.5, markersize=4, label=rec["patient_id"][:8])
    ax.axhline(y=float(np.median([r["profile_isf"] for r in recs])), color="gray",
               linestyle="--", alpha=0.5, label="Median profile")
    ax.set_xticks(range(6))
    ax.set_xticklabels(BLOCK_LABELS, fontsize=8)
    ax.set_ylabel("Adjusted ISF (mg/dL/U)")
    ax.legend(fontsize=6, ncol=2)
    ax.set_title(f"H3: Per-Patient Circadian Patterns [{h3['h3_verdict']}]")

    # Panel 4: Stability
    ax = axes[1, 1]
    if h4.get("stabilities"):
        rs = [s["r"] for s in h4["stabilities"]]
        ax.hist(rs, bins=12, color="steelblue", alpha=0.8, edgecolor="black")
        ax.axvline(0.5, color="red", linestyle="--", label="r=0.5 threshold")
        ax.set_xlabel("Split-half r")
        ax.set_ylabel("Patients")
        ax.legend(fontsize=8)
    ax.set_title(f"H4: Stability [{h4['h4_verdict']}]")

    plt.tight_layout()
    plt.savefig(VIS_DIR / "circadian_settings.png", dpi=150)
    plt.close()
    print(f"  Visualization: {VIS_DIR / 'circadian_settings.png'}")


def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_and_adjust(grid)
    recs = build_settings_table(events)

    h1 = test_h1_profile_difference(recs)
    h2 = test_h2_mae_improvement(events, recs)
    h3 = test_h3_clinical_significance(recs)
    h4 = test_h4_stability(events)

    make_visualization(recs, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID, "title": EXP_TITLE,
        "n_events": int(len(events)), "n_patients": int(events["patient_id"].nunique()),
        "recommendations": recs,
        "hypotheses": {
            "H1_profile_difference": h1, "H2_mae_improvement": h2,
            "H3_clinical_significance": h3, "H4_stability": h4,
        },
        "verdict_summary": {"H1": h1["h1_verdict"], "H2": h2["h2_verdict"],
                            "H3": h3["h3_verdict"], "H4": h4["h4_verdict"]},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    print(f"\nVerdict: H1={h1['h1_verdict']} H2={h2['h2_verdict']} H3={h3['h3_verdict']} H4={h4['h4_verdict']}")
    return results

if __name__ == "__main__":
    main()
