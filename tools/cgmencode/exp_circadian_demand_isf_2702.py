#!/usr/bin/env python3
"""
EXP-2702: Circadian Demand-ISF on Full 22-Patient Cohort

Combines two validated findings:
  - Demand-phase ISF (0-2h truncation) is the extractable signal (EXP-2640, R²=0.805)
  - Circadian ISF varies 2-9× across 24h (EXP-2652/2664)

Hypothesis:
  H1: Demand-phase ISF varies significantly by 4h time block (circadian signal)
  H2: Circadian demand-ISF pattern differs by controller type
  H3: Per-patient circadian demand-ISF improves BG prediction vs flat ISF
  H4: Dawn phenomenon increases demand-ISF by >50% vs overnight

Methodology:
  1. Extract correction events using deconfounding pipeline (BG≥180, 2h horizon)
  2. Compute demand-phase ISF per event = observed_drop / total_insulin
  3. Group by 4h time block (6 blocks: 00-04, 04-08, 08-12, 12-16, 16-20, 20-24)
  4. Test circadian variation via Kruskal-Wallis and per-block medians
  5. Stratify by controller type
  6. Compare flat vs circadian ISF prediction error

Uses new deconfounding infrastructure (production modules).
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP = Path("externals/experiments")
VIS = Path("visualizations/circadian-demand-isf")
VIS.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2702"
TITLE = "Circadian Demand-ISF on 22-Patient Cohort"

# ── Constants ────────────────────────────────────────────────────────
BG_FLOOR = 180.0          # EXP-2680: reduces negative ISF from 57% to 10%
HORIZON_STEPS = 24         # 2h demand phase (EXP-2624)
MIN_DOSE = 0.3             # Minimum total insulin to compute ISF
MIN_EVENTS_PER_BLOCK = 5   # Minimum events per 4h block for patient
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]


def load_data():
    """Load grid, devicestatus, controller map, qualified patients."""
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
    return grid, ctrl_map


def extract_correction_events(grid):
    """Extract correction events with BGI subtraction and BG≥180 floor.

    Returns events with demand-phase ISF computed per event.
    """
    print("Extracting correction events...")
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
        times = pg["time"].values
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        # Patient-level median ISF for BGI subtraction
        if "scheduled_isf" in pg.columns:
            isf_val = np.nanmedian(pg["scheduled_isf"].values)
        else:
            continue

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue
            if bg0 < BG_FLOOR:
                continue

            # Accumulate insulin and carbs over 2h horizon
            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0  # steps to hours
            carbs_2h = float(np.nansum(carbs[i:i + h]))

            # Skip meal events (carbs contaminate ISF extraction)
            if carbs_2h > 5.0:
                continue

            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end

            # Demand-phase ISF = drop / dose (only meaningful when drop > 0)
            demand_isf = observed_drop / total_insulin

            # BGI-subtracted deviation
            expected_drop = total_insulin * isf_val
            deviation = observed_drop - expected_drop

            roc_start = float(glucose[i] - glucose[i - 1]) if not np.isnan(glucose[i - 1]) else 0.0

            try:
                ts = pd.Timestamp(times[i])
                hour = ts.hour
            except Exception:
                hour = 0

            # Assign time block
            block_idx = min(hour // 4, 5)

            events.append({
                "patient_id": pid,
                "time": times[i],
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "deviation": deviation,
                "expected_drop": expected_drop,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "roc_start": roc_start,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "controller": ctrl,
                "profile_isf": isf_val,
            })

    df = pd.DataFrame(events)
    # Filter positive ISF (negative means BG went up — misclassified)
    df_pos = df[df["demand_isf"] > 0].copy()
    print(f"  Total: {len(df):,} events, positive ISF: {len(df_pos):,} ({100*len(df_pos)/max(len(df),1):.0f}%)")
    return df_pos


def test_circadian_variation(events):
    """H1: Does demand-phase ISF vary significantly by 4h time block?"""
    print("\n── H1: Circadian variation in demand-phase ISF ──")

    # Population-level Kruskal-Wallis
    groups = [g["demand_isf"].values for _, g in events.groupby("block_idx") if len(g) >= 5]
    if len(groups) < 3:
        return {"h1_verdict": "SKIP", "reason": "Too few time blocks with data"}

    kw_stat, kw_p = stats.kruskal(*groups)

    # Per-block medians and IQRs
    block_stats = []
    for idx, label in enumerate(BLOCK_LABELS):
        block_data = events[events["block_idx"] == idx]["demand_isf"]
        if len(block_data) < 5:
            block_stats.append({"block": label, "n": len(block_data), "median": None, "iqr": None})
            continue
        q25, q50, q75 = np.percentile(block_data, [25, 50, 75])
        block_stats.append({
            "block": label,
            "n": int(len(block_data)),
            "median": round(float(q50), 1),
            "q25": round(float(q25), 1),
            "q75": round(float(q75), 1),
            "iqr": round(float(q75 - q25), 1),
        })

    medians = [b["median"] for b in block_stats if b["median"] is not None]
    if medians:
        circadian_ratio = max(medians) / max(min(medians), 0.1)
    else:
        circadian_ratio = None

    verdict = bool(kw_p < 0.05)
    print(f"  KW statistic: {kw_stat:.1f}, p={kw_p:.4f}")
    print(f"  Circadian ratio (max/min median): {circadian_ratio:.2f}×" if circadian_ratio else "  Insufficient data")
    for b in block_stats:
        if b["median"]:
            print(f"    {b['block']}: median {b['median']:.1f} mg/dL/U (n={b['n']})")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "kw_statistic": round(float(kw_stat), 2),
        "kw_p_value": float(kw_p),
        "circadian_ratio": round(float(circadian_ratio), 2) if circadian_ratio else None,
        "block_stats": block_stats,
    }


def test_controller_differences(events):
    """H2: Does circadian demand-ISF pattern differ by controller type?"""
    print("\n── H2: Controller-specific circadian patterns ──")

    controller_results = {}
    for ctrl, cg in events.groupby("controller"):
        if len(cg) < 30:
            controller_results[ctrl] = {"n": int(len(cg)), "verdict": "SKIP", "reason": "too few events"}
            continue

        groups = [g["demand_isf"].values for _, g in cg.groupby("block_idx") if len(g) >= 3]
        if len(groups) < 3:
            controller_results[ctrl] = {"n": int(len(cg)), "verdict": "SKIP", "reason": "too few blocks"}
            continue

        kw_stat, kw_p = stats.kruskal(*groups)

        block_medians = {}
        for idx, label in enumerate(BLOCK_LABELS):
            bd = cg[cg["block_idx"] == idx]["demand_isf"]
            if len(bd) >= 3:
                block_medians[label] = round(float(bd.median()), 1)

        medians_list = list(block_medians.values())
        ratio = max(medians_list) / max(min(medians_list), 0.1) if medians_list else None

        controller_results[ctrl] = {
            "n": int(len(cg)),
            "kw_statistic": round(float(kw_stat), 2),
            "kw_p_value": float(kw_p),
            "circadian_ratio": round(float(ratio), 2) if ratio else None,
            "block_medians": block_medians,
            "verdict": "PASS" if kw_p < 0.05 else "FAIL",
        }
        print(f"  {ctrl}: n={len(cg)}, KW p={kw_p:.4f}, ratio={ratio:.2f}×" if ratio else f"  {ctrl}: insufficient blocks")

    return {"h2_controller_results": controller_results}


def test_prediction_improvement(events):
    """H3: Does per-patient circadian ISF improve BG prediction vs flat ISF?"""
    print("\n── H3: Circadian ISF prediction improvement ──")

    patient_results = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            continue

        # Flat model: patient-median ISF
        flat_isf = pg["demand_isf"].median()
        flat_pred = pg["total_insulin"] * flat_isf
        flat_errors = (pg["observed_drop"] - flat_pred).values
        flat_mae = float(np.mean(np.abs(flat_errors)))

        # Circadian model: per-block median ISF
        block_isf = pg.groupby("block_idx")["demand_isf"].median()
        circ_pred = pg.apply(
            lambda r: r["total_insulin"] * block_isf.get(r["block_idx"], flat_isf), axis=1
        )
        circ_errors = (pg["observed_drop"] - circ_pred).values
        circ_mae = float(np.mean(np.abs(circ_errors)))

        improvement_pct = (flat_mae - circ_mae) / flat_mae * 100 if flat_mae > 0 else 0

        patient_results.append({
            "patient_id": pid,
            "n_events": int(len(pg)),
            "flat_mae": round(flat_mae, 1),
            "circ_mae": round(circ_mae, 1),
            "improvement_pct": round(improvement_pct, 1),
            "controller": pg["controller"].iloc[0],
        })

    df_res = pd.DataFrame(patient_results)
    n_improved = int((df_res["improvement_pct"] > 0).sum())
    mean_improvement = float(df_res["improvement_pct"].mean())
    median_improvement = float(df_res["improvement_pct"].median())

    verdict = bool(n_improved > len(df_res) * 0.6)  # >60% patients improve
    print(f"  {n_improved}/{len(df_res)} patients improved ({100*n_improved/max(len(df_res),1):.0f}%)")
    print(f"  Mean improvement: {mean_improvement:.1f}%, median: {median_improvement:.1f}%")
    print(f"  Flat MAE: {df_res['flat_mae'].median():.1f}, Circ MAE: {df_res['circ_mae'].median():.1f}")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "n_patients": int(len(df_res)),
        "n_improved": n_improved,
        "mean_improvement_pct": round(mean_improvement, 1),
        "median_improvement_pct": round(median_improvement, 1),
        "median_flat_mae": round(float(df_res["flat_mae"].median()), 1),
        "median_circ_mae": round(float(df_res["circ_mae"].median()), 1),
        "per_patient": patient_results,
    }


def test_dawn_phenomenon(events):
    """H4: Dawn phenomenon increases demand-ISF by >50% vs overnight."""
    print("\n── H4: Dawn phenomenon ISF amplification ──")

    # Dawn: 04-08, Overnight: 00-04
    dawn = events[events["block_idx"] == 1]["demand_isf"]
    overnight = events[events["block_idx"] == 0]["demand_isf"]

    if len(dawn) < 10 or len(overnight) < 10:
        return {"h4_verdict": "SKIP", "reason": "Too few dawn or overnight events"}

    dawn_median = float(dawn.median())
    overnight_median = float(overnight.median())
    amplification = (dawn_median - overnight_median) / overnight_median * 100 if overnight_median != 0 else 0

    # Mann-Whitney U test
    u_stat, u_p = stats.mannwhitneyu(dawn, overnight, alternative="greater")

    verdict = bool(amplification > 50 and u_p < 0.05)
    print(f"  Dawn median ISF: {dawn_median:.1f} mg/dL/U (n={len(dawn)})")
    print(f"  Overnight median ISF: {overnight_median:.1f} mg/dL/U (n={len(overnight)})")
    print(f"  Amplification: {amplification:.1f}% (threshold: 50%)")
    print(f"  Mann-Whitney p={u_p:.4f}")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "dawn_median_isf": round(dawn_median, 1),
        "overnight_median_isf": round(overnight_median, 1),
        "amplification_pct": round(amplification, 1),
        "mw_u_statistic": round(float(u_stat), 1),
        "mw_p_value": float(u_p),
        "dawn_n": int(len(dawn)),
        "overnight_n": int(len(overnight)),
    }


def compute_per_patient_circadian_table(events):
    """Extract per-patient × per-block demand ISF table for settings optimization."""
    print("\n── Per-patient circadian demand-ISF table ──")

    table = []
    for pid, pg in events.groupby("patient_id"):
        ctrl = pg["controller"].iloc[0]
        profile_isf = pg["profile_isf"].iloc[0]
        flat_isf = pg["demand_isf"].median()

        row = {
            "patient_id": pid,
            "controller": ctrl,
            "profile_isf": round(float(profile_isf), 1),
            "flat_demand_isf": round(float(flat_isf), 1),
            "n_total": int(len(pg)),
        }

        for idx, label in enumerate(BLOCK_LABELS):
            bd = pg[pg["block_idx"] == idx]["demand_isf"]
            row[f"isf_{label}"] = round(float(bd.median()), 1) if len(bd) >= MIN_EVENTS_PER_BLOCK else None
            row[f"n_{label}"] = int(len(bd))

        # Circadian range and ratio
        block_values = [row[f"isf_{label}"] for label in BLOCK_LABELS if row[f"isf_{label}"] is not None]
        if len(block_values) >= 2:
            row["circadian_ratio"] = round(max(block_values) / max(min(block_values), 0.1), 2)
            row["circadian_range"] = round(max(block_values) - min(block_values), 1)
        else:
            row["circadian_ratio"] = None
            row["circadian_range"] = None

        table.append(row)

    df_table = pd.DataFrame(table)
    n_with_ratio = df_table["circadian_ratio"].notna().sum()
    med_ratio = df_table["circadian_ratio"].median()
    print(f"  {n_with_ratio} patients with circadian ISF table")
    print(f"  Median circadian ratio: {med_ratio:.2f}×" if not pd.isna(med_ratio) else "  Insufficient data")
    return table


def make_visualization(events, block_stats, controller_results, patient_results):
    """Generate circadian demand-ISF visualization."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"{EXP_ID}: Circadian Demand-Phase ISF (N={len(events):,} events)", fontsize=14)

        # Panel 1: Population circadian ISF by block
        ax = axes[0, 0]
        valid_blocks = [b for b in block_stats if b["median"] is not None]
        if valid_blocks:
            x = range(len(valid_blocks))
            medians = [b["median"] for b in valid_blocks]
            q25s = [b["q25"] for b in valid_blocks]
            q75s = [b["q75"] for b in valid_blocks]
            labels = [b["block"] for b in valid_blocks]
            ax.bar(x, medians, color="steelblue", alpha=0.7)
            ax.errorbar(x, medians,
                        yerr=[np.array(medians) - np.array(q25s), np.array(q75s) - np.array(medians)],
                        fmt="none", color="black", capsize=5)
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45)
        ax.set_title("Demand-ISF by Time Block")
        ax.set_ylabel("ISF (mg/dL/U)")
        ax.set_xlabel("Time Block")

        # Panel 2: Per-controller circadian pattern
        ax = axes[0, 1]
        colors = {"Loop": "blue", "Trio": "green", "OpenAPS": "orange"}
        for ctrl, cr in controller_results.get("h2_controller_results", {}).items():
            if "block_medians" in cr and cr["block_medians"]:
                bm = cr["block_medians"]
                x_vals = [i for i, l in enumerate(BLOCK_LABELS) if l in bm]
                y_vals = [bm[l] for l in BLOCK_LABELS if l in bm]
                ax.plot(x_vals, y_vals, "o-", label=f"{ctrl} (n={cr['n']})", color=colors.get(ctrl, "gray"))
        ax.set_xticks(range(6))
        ax.set_xticklabels(BLOCK_LABELS, rotation=45)
        ax.legend()
        ax.set_title("Circadian ISF by Controller")
        ax.set_ylabel("ISF (mg/dL/U)")

        # Panel 3: Per-patient improvement (flat vs circadian)
        ax = axes[1, 0]
        if patient_results:
            pr_df = pd.DataFrame(patient_results)
            pr_df = pr_df.sort_values("improvement_pct")
            colors_list = ["green" if v > 0 else "red" for v in pr_df["improvement_pct"]]
            ax.barh(range(len(pr_df)), pr_df["improvement_pct"], color=colors_list, alpha=0.7)
            ax.axvline(0, color="black", linewidth=0.8)
            ax.set_yticks(range(len(pr_df)))
            ax.set_yticklabels([f"P{i}" for i in range(len(pr_df))], fontsize=7)
        ax.set_title("MAE Improvement: Circadian vs Flat ISF")
        ax.set_xlabel("Improvement (%)")

        # Panel 4: Dawn vs overnight ISF distribution
        ax = axes[1, 1]
        dawn = events[events["block_idx"] == 1]["demand_isf"]
        overnight = events[events["block_idx"] == 0]["demand_isf"]
        if len(dawn) > 0 and len(overnight) > 0:
            ax.hist(overnight, bins=30, alpha=0.5, label=f"Overnight 00-04 (n={len(overnight)})", color="navy")
            ax.hist(dawn, bins=30, alpha=0.5, label=f"Dawn 04-08 (n={len(dawn)})", color="orange")
            ax.axvline(overnight.median(), color="navy", linestyle="--")
            ax.axvline(dawn.median(), color="orange", linestyle="--")
            ax.legend()
        ax.set_title("Dawn vs Overnight ISF Distribution")
        ax.set_xlabel("Demand-ISF (mg/dL/U)")

        plt.tight_layout()
        path = VIS / "circadian_demand_isf.png"
        fig.savefig(path, dpi=150)
        plt.close()
        print(f"\n  Visualization saved: {path}")
    except ImportError:
        print("  matplotlib not available, skipping visualization")


def main():
    # Load
    grid, ctrl_map = load_data()

    # Extract
    events = extract_correction_events(grid)
    if len(events) == 0:
        print("ERROR: No correction events extracted")
        sys.exit(1)

    n_patients = events["patient_id"].nunique()
    print(f"\n{EXP_ID}: {TITLE}")
    print(f"  {len(events):,} correction events, {n_patients} patients")
    print(f"  Controllers: {events['controller'].value_counts().to_dict()}")

    # Test hypotheses
    h1 = test_circadian_variation(events)
    h2 = test_controller_differences(events)
    h3 = test_prediction_improvement(events)
    h4 = test_dawn_phenomenon(events)

    # Per-patient circadian ISF table
    circadian_table = compute_per_patient_circadian_table(events)

    # Visualization
    make_visualization(events, h1.get("block_stats", []), h2, h3.get("per_patient", []))

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY — {EXP_ID}")
    print(f"{'='*60}")
    print(f"  H1 (circadian variation):     {h1['h1_verdict']}")
    print(f"  H2 (controller differences):  {len([v for v in h2.get('h2_controller_results', {}).values() if v.get('verdict') == 'PASS'])} controllers show circadian pattern")
    print(f"  H3 (prediction improvement):  {h3.get('h3_verdict', 'SKIP')}")
    print(f"  H4 (dawn amplification):      {h4.get('h4_verdict', 'SKIP')}")

    # Save results
    results = {
        "experiment": EXP_ID,
        "title": TITLE,
        "n_events": int(len(events)),
        "n_patients": int(n_patients),
        "controllers": events["controller"].value_counts().to_dict(),
        "hypotheses": {
            "h1_circadian_variation": h1,
            "h2_controller_differences": h2,
            "h3_prediction_improvement": {k: v for k, v in h3.items() if k != "per_patient"},
            "h4_dawn_phenomenon": h4,
        },
        "circadian_table": circadian_table,
        "methodology": {
            "bg_floor": BG_FLOOR,
            "horizon_hours": 2.0,
            "min_dose": MIN_DOSE,
            "time_blocks": BLOCK_LABELS,
            "deconfounding": "BGI subtraction + BG floor + carb-free filter",
        },
    }

    out_path = EXP / "exp-2702_circadian_demand_isf.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved: {out_path}")

    return results


if __name__ == "__main__":
    main()
