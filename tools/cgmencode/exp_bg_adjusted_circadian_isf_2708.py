#!/usr/bin/env python3
"""EXP-2708: BG-Adjusted Circadian Demand-ISF Tables

Builds on EXP-2702 (circadian demand-ISF) and EXP-2705 (BG confound).

EXP-2702 found strong circadian ISF variation (2.02× per-patient, peak 12-16h).
EXP-2705 showed starting BG explains 71% of the joint model, and after BG
residualization the peak shifts from 12-16h to 16-20h.

This experiment produces the ACTIONABLE output: per-patient circadian ISF
tables after removing starting-BG confound.

Hypotheses:
  H1: BG-adjusted circadian tables differ from raw tables (peak shift)
  H2: Adjusted tables improve prediction accuracy (lower MAE vs raw)
  H3: Adjusted circadian ratio is smaller than raw (BG inflates variation)
  H4: Combined (circadian + BG-adjusted) model outperforms either alone

Design:
  - Extract correction events at BG≥180, carbs<5g, dose≥0.3U, 2h horizon
  - Residualize BG0, dose, IOB from demand-ISF via OLS
  - Re-center residuals to original ISF scale per patient
  - Build per-patient × per-block ISF tables (raw and adjusted)
  - Evaluate MAE of circadian ISF prediction vs flat median ISF

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2708_bg_adjusted_circadian_isf.json")
VIS_DIR = Path("visualizations/bg-adjusted-circadian-isf")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
MIN_EVENTS_PER_BLOCK = 10
MIN_EVENTS_PATIENT = 30
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2708"
EXP_TITLE = "BG-Adjusted Circadian Demand-ISF Tables"


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


def extract_correction_events(grid):
    """Extract correction events with circadian block assignment."""
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
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue
            if bg0 < BG_FLOOR:
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
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour
            except Exception:
                hour = 0

            block_idx = min(hour // 4, 5)

            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "controller": ctrl,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} positive-ISF events, {df['patient_id'].nunique()} patients")
    return df


def residualize_bg(events):
    """Remove BG0 and dose confounds from demand-ISF via OLS residualization.

    Returns events with 'adjusted_isf' column: residuals re-centered to
    per-patient median ISF scale.
    """
    print("\nResidualizing BG0, dose, IOB from demand-ISF...")
    from numpy.linalg import lstsq

    adjusted = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < MIN_EVENTS_PATIENT:
            continue

        y = pg["demand_isf"].values
        patient_median = float(np.median(y))

        # Covariates: BG0, total_insulin, IOB
        X = np.column_stack([
            pg["bg0"].values,
            pg["total_insulin"].values,
            pg["iob_start"].values,
            np.ones(len(pg)),
        ])

        beta, _, _, _ = lstsq(X, y, rcond=None)
        residuals = y - X @ beta

        # Re-center: shift residuals so patient median matches original
        adjusted_isf = residuals + patient_median

        pg_copy = pg.copy()
        pg_copy["adjusted_isf"] = adjusted_isf
        pg_copy["raw_isf"] = y
        adjusted.append(pg_copy)

    result = pd.concat(adjusted, ignore_index=True)
    print(f"  {len(result):,} events after residualization")
    return result


def build_circadian_tables(events, isf_col, label):
    """Build per-patient × per-block ISF table from specified column."""
    tables = []
    for pid, pg in events.groupby("patient_id"):
        ctrl = pg["controller"].iloc[0]
        flat_isf = float(pg[isf_col].median())

        row = {
            "patient_id": pid,
            "controller": ctrl,
            "flat_isf": round(flat_isf, 1),
            "n_total": int(len(pg)),
        }

        block_vals = []
        for idx, bl in enumerate(BLOCK_LABELS):
            bd = pg[pg["block_idx"] == idx][isf_col]
            val = round(float(bd.median()), 1) if len(bd) >= MIN_EVENTS_PER_BLOCK else None
            row[f"isf_{bl}"] = val
            row[f"n_{bl}"] = int(len(bd))
            if val is not None:
                block_vals.append(val)

        if len(block_vals) >= 2:
            row["circadian_ratio"] = round(max(block_vals) / max(min(block_vals), 0.1), 2)
            row["circadian_range"] = round(max(block_vals) - min(block_vals), 1)
            row["peak_block"] = BLOCK_LABELS[[row[f"isf_{bl}"] for bl in BLOCK_LABELS].index(max(block_vals))]
            row["trough_block"] = BLOCK_LABELS[[row[f"isf_{bl}"] for bl in BLOCK_LABELS].index(min(block_vals))]
        else:
            row["circadian_ratio"] = None
            row["circadian_range"] = None
            row["peak_block"] = None
            row["trough_block"] = None

        tables.append(row)

    return tables


def test_h1_pattern_shift(events):
    """H1: BG-adjusted circadian tables differ from raw (peak shifts)."""
    print("\n── H1: Do adjusted tables differ from raw? ──")

    raw_tables = build_circadian_tables(events, "raw_isf", "raw")
    adj_tables = build_circadian_tables(events, "adjusted_isf", "adjusted")

    # Population-level patterns
    raw_pop = {}
    adj_pop = {}
    for idx, bl in enumerate(BLOCK_LABELS):
        mask = events["block_idx"] == idx
        if mask.sum() >= 20:
            raw_pop[bl] = round(float(events.loc[mask, "raw_isf"].median()), 1)
            adj_pop[bl] = round(float(events.loc[mask, "adjusted_isf"].median()), 1)

    # Per-patient peak shifts
    n_shifted = 0
    n_patients = 0
    for raw_row, adj_row in zip(raw_tables, adj_tables):
        if raw_row["peak_block"] is not None and adj_row["peak_block"] is not None:
            n_patients += 1
            if raw_row["peak_block"] != adj_row["peak_block"]:
                n_shifted += 1

    pct_shifted = 100 * n_shifted / max(n_patients, 1)

    # Population peak
    raw_peak = max(raw_pop, key=raw_pop.get) if raw_pop else None
    adj_peak = max(adj_pop, key=adj_pop.get) if adj_pop else None

    pop_shifted = raw_peak != adj_peak

    # Rank correlation between raw and adjusted population pattern
    if len(raw_pop) >= 4 and len(adj_pop) >= 4:
        common = sorted(set(raw_pop.keys()) & set(adj_pop.keys()))
        r_rank, p_rank = stats.spearmanr(
            [raw_pop[k] for k in common],
            [adj_pop[k] for k in common],
        )
    else:
        r_rank, p_rank = np.nan, np.nan

    verdict = bool(pop_shifted or pct_shifted > 30)

    print(f"  Population raw peak: {raw_peak} ({raw_pop.get(raw_peak, '?')} mg/dL/U)")
    print(f"  Population adj peak: {adj_peak} ({adj_pop.get(adj_peak, '?')} mg/dL/U)")
    print(f"  Per-patient peak shifted: {n_shifted}/{n_patients} ({pct_shifted:.0f}%)")
    print(f"  Rank correlation: r={r_rank:.3f}")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "raw_population_pattern": raw_pop,
        "adjusted_population_pattern": adj_pop,
        "raw_peak": raw_peak,
        "adjusted_peak": adj_peak,
        "pop_peak_shifted": pop_shifted,
        "per_patient_pct_shifted": round(pct_shifted, 1),
        "rank_correlation": round(float(r_rank), 3) if not np.isnan(r_rank) else None,
        "raw_tables": raw_tables,
        "adjusted_tables": adj_tables,
    }


def test_h2_prediction_accuracy(events):
    """H2: Adjusted circadian ISF improves MAE over raw circadian ISF."""
    print("\n── H2: Does adjustment improve prediction accuracy? ──")

    raw_tables = build_circadian_tables(events, "raw_isf", "raw")
    adj_tables = build_circadian_tables(events, "adjusted_isf", "adjusted")

    # Build lookup dicts: {(pid, block_idx): isf_value}
    raw_lookup = {}
    adj_lookup = {}
    flat_raw_lookup = {}
    flat_adj_lookup = {}

    for rt in raw_tables:
        pid = rt["patient_id"]
        flat_raw_lookup[pid] = rt["flat_isf"]
        for idx, bl in enumerate(BLOCK_LABELS):
            val = rt[f"isf_{bl}"]
            if val is not None:
                raw_lookup[(pid, idx)] = val

    for at in adj_tables:
        pid = at["patient_id"]
        flat_adj_lookup[pid] = at["flat_isf"]
        for idx, bl in enumerate(BLOCK_LABELS):
            val = at[f"isf_{bl}"]
            if val is not None:
                adj_lookup[(pid, idx)] = val

    # Compute per-event errors for 4 models:
    # 1. Flat raw ISF, 2. Raw circadian ISF, 3. Flat adjusted ISF, 4. Adjusted circadian ISF
    errors = {"flat_raw": [], "circ_raw": [], "flat_adj": [], "circ_adj": []}
    per_patient_mae = []

    for pid, pg in events.groupby("patient_id"):
        if pid not in flat_raw_lookup or pid not in flat_adj_lookup:
            continue

        p_errors = {"flat_raw": [], "circ_raw": [], "flat_adj": [], "circ_adj": []}

        for _, row in pg.iterrows():
            actual = row["demand_isf"]
            bidx = row["block_idx"]

            # Flat raw
            e_flat_raw = abs(actual - flat_raw_lookup[pid])
            errors["flat_raw"].append(e_flat_raw)
            p_errors["flat_raw"].append(e_flat_raw)

            # Raw circadian
            if (pid, bidx) in raw_lookup:
                e_circ = abs(actual - raw_lookup[(pid, bidx)])
            else:
                e_circ = e_flat_raw
            errors["circ_raw"].append(e_circ)
            p_errors["circ_raw"].append(e_circ)

            # Flat adjusted
            e_flat_adj = abs(actual - flat_adj_lookup[pid])
            errors["flat_adj"].append(e_flat_adj)
            p_errors["flat_adj"].append(e_flat_adj)

            # Adjusted circadian
            actual_adj = row["adjusted_isf"]
            if (pid, bidx) in adj_lookup:
                e_circ_adj = abs(actual_adj - adj_lookup[(pid, bidx)])
            else:
                e_circ_adj = abs(actual_adj - flat_adj_lookup[pid])
            errors["circ_adj"].append(e_circ_adj)
            p_errors["circ_adj"].append(e_circ_adj)

        per_patient_mae.append({
            "patient_id": pid,
            "mae_flat_raw": round(float(np.mean(p_errors["flat_raw"])), 1),
            "mae_circ_raw": round(float(np.mean(p_errors["circ_raw"])), 1),
            "mae_circ_adj": round(float(np.mean(p_errors["circ_adj"])), 1),
            "improvement_raw": round(100 * (np.mean(p_errors["flat_raw"]) - np.mean(p_errors["circ_raw"])) / max(np.mean(p_errors["flat_raw"]), 0.1), 1),
            "improvement_adj": round(100 * (np.mean(p_errors["flat_raw"]) - np.mean(p_errors["circ_adj"])) / max(np.mean(p_errors["flat_raw"]), 0.1), 1),
        })

    mae = {k: round(float(np.mean(v)), 2) for k, v in errors.items()}
    improvement_raw_pct = 100 * (mae["flat_raw"] - mae["circ_raw"]) / max(mae["flat_raw"], 0.1)
    improvement_adj_pct = 100 * (mae["flat_raw"] - mae["circ_adj"]) / max(mae["flat_raw"], 0.1)
    adj_better_than_raw = mae["circ_adj"] < mae["circ_raw"]

    n_improved_adj = sum(1 for p in per_patient_mae if p["improvement_adj"] > 0)
    pct_improved = 100 * n_improved_adj / max(len(per_patient_mae), 1)

    verdict = bool(adj_better_than_raw and pct_improved > 50)

    print(f"  MAE flat raw:     {mae['flat_raw']:.2f}")
    print(f"  MAE circ raw:     {mae['circ_raw']:.2f} ({improvement_raw_pct:+.1f}%)")
    print(f"  MAE circ adj:     {mae['circ_adj']:.2f} ({improvement_adj_pct:+.1f}%)")
    print(f"  Adjusted better than raw: {adj_better_than_raw}")
    print(f"  Patients improved (adj vs flat): {n_improved_adj}/{len(per_patient_mae)} ({pct_improved:.0f}%)")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "mae_flat_raw": mae["flat_raw"],
        "mae_circ_raw": mae["circ_raw"],
        "mae_circ_adj": mae["circ_adj"],
        "improvement_raw_pct": round(improvement_raw_pct, 1),
        "improvement_adj_pct": round(improvement_adj_pct, 1),
        "adj_better_than_raw": adj_better_than_raw,
        "pct_patients_improved": round(pct_improved, 1),
        "per_patient_mae": per_patient_mae,
    }


def test_h3_ratio_reduction(events):
    """H3: BG adjustment reduces circadian ratio (BG inflates variation)."""
    print("\n── H3: Does adjustment reduce circadian ratio? ──")

    raw_tables = build_circadian_tables(events, "raw_isf", "raw")
    adj_tables = build_circadian_tables(events, "adjusted_isf", "adjusted")

    raw_ratios = [r["circadian_ratio"] for r in raw_tables if r["circadian_ratio"] is not None]
    adj_ratios = [r["circadian_ratio"] for r in adj_tables if r["circadian_ratio"] is not None]

    if len(raw_ratios) < 3 or len(adj_ratios) < 3:
        return {"h3_verdict": "SKIP", "reason": "insufficient data"}

    med_raw = float(np.median(raw_ratios))
    med_adj = float(np.median(adj_ratios))
    reduction_pct = 100 * (med_raw - med_adj) / max(med_raw, 0.1)

    stat, p = stats.wilcoxon(
        [r for r in raw_ratios[:len(adj_ratios)]],
        adj_ratios[:len(raw_ratios)],
        alternative="greater",
    )

    verdict = bool(med_adj < med_raw and p < 0.05)

    print(f"  Median raw ratio:  {med_raw:.2f}×")
    print(f"  Median adj ratio:  {med_adj:.2f}×")
    print(f"  Reduction: {reduction_pct:.1f}%")
    print(f"  Wilcoxon p: {p:.4f}")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "median_raw_ratio": round(med_raw, 2),
        "median_adj_ratio": round(med_adj, 2),
        "reduction_pct": round(reduction_pct, 1),
        "wilcoxon_p": round(float(p), 4),
        "n_patients": len(raw_ratios),
    }


def test_h4_combined_model(events):
    """H4: Combined (circadian block + BG0) model outperforms either alone."""
    print("\n── H4: Does combined model outperform single-factor? ──")
    from numpy.linalg import lstsq

    valid = events[["demand_isf", "bg0", "block_idx", "total_insulin", "iob_start", "patient_id"]].dropna()
    y = valid["demand_isf"].values
    ss_tot = np.sum((y - y.mean()) ** 2)

    # Model 1: BG0 only
    X_bg = np.column_stack([valid["bg0"].values, np.ones(len(valid))])
    beta, _, _, _ = lstsq(X_bg, y, rcond=None)
    r2_bg = 1 - np.sum((y - X_bg @ beta) ** 2) / ss_tot

    # Model 2: Block dummies only
    X_block = pd.get_dummies(valid["block_idx"], prefix="b").values
    X_block = np.column_stack([X_block, np.ones(len(valid))])
    beta, _, _, _ = lstsq(X_block, y, rcond=None)
    r2_block = 1 - np.sum((y - X_block @ beta) ** 2) / ss_tot

    # Model 3: BG0 + block dummies
    X_both = np.column_stack([valid["bg0"].values, pd.get_dummies(valid["block_idx"], prefix="b").values, np.ones(len(valid))])
    beta, _, _, _ = lstsq(X_both, y, rcond=None)
    r2_both = 1 - np.sum((y - X_both @ beta) ** 2) / ss_tot

    # Model 4: BG0 + block + dose + IOB
    X_full = np.column_stack([
        valid["bg0"].values,
        valid["total_insulin"].values,
        valid["iob_start"].values,
        pd.get_dummies(valid["block_idx"], prefix="b").values,
        np.ones(len(valid)),
    ])
    beta, _, _, _ = lstsq(X_full, y, rcond=None)
    r2_full = 1 - np.sum((y - X_full @ beta) ** 2) / ss_tot

    # Model 5: Patient dummies + BG0 + block (upper bound)
    X_patient = np.column_stack([
        valid["bg0"].values,
        pd.get_dummies(valid["block_idx"], prefix="b").values,
        pd.get_dummies(valid["patient_id"], prefix="p").values,
        np.ones(len(valid)),
    ])
    beta, _, _, _ = lstsq(X_patient, y, rcond=None)
    r2_patient = 1 - np.sum((y - X_patient @ beta) ** 2) / ss_tot

    combined_better = r2_both > max(r2_bg, r2_block)
    full_better = r2_full > r2_both

    verdict = bool(combined_better)

    print(f"  R² BG0 only:        {r2_bg:.4f}")
    print(f"  R² block only:      {r2_block:.4f}")
    print(f"  R² BG0+block:       {r2_both:.4f}")
    print(f"  R² BG0+block+dose+IOB: {r2_full:.4f}")
    print(f"  R² +patient (upper): {r2_patient:.4f}")
    print(f"  Combined > either:  {combined_better}")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "r2_bg_only": round(float(r2_bg), 4),
        "r2_block_only": round(float(r2_block), 4),
        "r2_bg_block": round(float(r2_both), 4),
        "r2_full": round(float(r2_full), 4),
        "r2_patient_upper": round(float(r2_patient), 4),
        "combined_better_than_either": combined_better,
        "full_better_than_combined": full_better,
    }


def make_visualization(events, h1, h2, h3, h4):
    """Create summary visualization."""
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Raw vs adjusted population pattern
    ax = axes[0, 0]
    raw_pat = h1.get("raw_population_pattern", {})
    adj_pat = h1.get("adjusted_population_pattern", {})
    if raw_pat and adj_pat:
        labels = sorted(set(raw_pat.keys()) & set(adj_pat.keys()))
        x = np.arange(len(labels))
        ax.bar(x - 0.2, [raw_pat[l] for l in labels], 0.4, label="Raw ISF", alpha=0.7, color="steelblue")
        ax.bar(x + 0.2, [adj_pat[l] for l in labels], 0.4, label="BG-adjusted ISF", alpha=0.7, color="coral")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45)
        ax.set_ylabel("Demand ISF (mg/dL/U)")
        ax.legend(fontsize=8)
    ax.set_title(f"H1: Pattern Shift [{h1['h1_verdict']}]")

    # Panel 2: MAE comparison
    ax = axes[0, 1]
    models = ["Flat\nRaw", "Circadian\nRaw", "Circadian\nAdjusted"]
    maes = [h2.get("mae_flat_raw", 0), h2.get("mae_circ_raw", 0), h2.get("mae_circ_adj", 0)]
    colors = ["gray", "steelblue", "coral"]
    ax.bar(models, maes, color=colors, alpha=0.8)
    ax.set_ylabel("MAE (mg/dL/U)")
    ax.set_title(f"H2: Prediction Accuracy [{h2['h2_verdict']}]")
    for i, v in enumerate(maes):
        ax.text(i, v + 0.1, f"{v:.1f}", ha="center", fontsize=9)

    # Panel 3: Circadian ratio comparison
    ax = axes[1, 0]
    if h3.get("h3_verdict") != "SKIP":
        raw_tables = h1.get("raw_tables", [])
        adj_tables = h1.get("adjusted_tables", [])
        raw_ratios = [t["circadian_ratio"] for t in raw_tables if t["circadian_ratio"] is not None]
        adj_ratios = [t["circadian_ratio"] for t in adj_tables if t["circadian_ratio"] is not None]
        ax.boxplot([raw_ratios, adj_ratios], labels=["Raw", "BG-Adjusted"])
        ax.set_ylabel("Circadian Ratio (max/min)")
        ax.axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    ax.set_title(f"H3: Ratio Reduction [{h3['h3_verdict']}]")

    # Panel 4: R² waterfall
    ax = axes[1, 1]
    r2_labels = ["BG₀", "Block", "BG₀+Block", "Full", "+Patient"]
    r2_vals = [h4.get("r2_bg_only", 0), h4.get("r2_block_only", 0),
               h4.get("r2_bg_block", 0), h4.get("r2_full", 0),
               h4.get("r2_patient_upper", 0)]
    ax.barh(r2_labels, r2_vals, color=["steelblue", "coral", "mediumpurple", "darkorange", "gray"])
    ax.set_xlabel("R²")
    ax.set_title(f"H4: Combined Model [{h4['h4_verdict']}]")

    plt.tight_layout()
    out_path = VIS_DIR / "bg_adjusted_circadian_isf.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  Visualization: {out_path}")


def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_correction_events(grid)
    if len(events) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    events = residualize_bg(events)

    h1 = test_h1_pattern_shift(events)
    h2 = test_h2_prediction_accuracy(events)
    h3 = test_h3_ratio_reduction(events)
    h4 = test_h4_combined_model(events)

    make_visualization(events, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {
            "H1_pattern_shift": h1,
            "H2_prediction_accuracy": h2,
            "H3_ratio_reduction": h3,
            "H4_combined_model": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    print(f"\nVerdict summary: H1={h1['h1_verdict']} H2={h2['h2_verdict']} H3={h3['h3_verdict']} H4={h4['h4_verdict']}")
    return results


if __name__ == "__main__":
    main()
