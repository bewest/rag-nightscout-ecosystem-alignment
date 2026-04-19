#!/usr/bin/env python3
"""EXP-2721: BG-Adjusted Shrinkage Circadian ISF

Combines two validated findings:
  EXP-2708: BG-residualized circadian ISF peaks at 20-24h (true ratio 5.57×)
  EXP-2715: Shrinkage improves split-half stability +159% (0.235→0.609)

Goal: produce a stable, actionable per-patient circadian ISF schedule
using BG-adjusted ISF with Bayesian shrinkage toward the patient's flat
median (not population shape, as in EXP-2715).

Hypotheses:
  H1: BG-adjusted shrinkage ISF has better split-half stability than raw
  H2: Shrinkage reduces circadian ratio to physiological range (1.5-4×)
  H3: Circadian schedule improves MAE vs flat ISF for majority of patients
  H4: Optimal shrinkage k is consistent across patients (IQR < 2 orders)

Design:
  - Extract correction events (BG≥180, carbs<5g, dose≥0.3U, 2h horizon)
  - BG-residualize demand_isf via OLS (remove BG₀, dose, IOB confound)
  - Per patient, per 4h block, shrink toward patient flat median
  - Evaluate stability, circadian ratio, MAE, and k consistency

Author: Copilot + bewest
Date: 2025-07-18
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/circadian-shrinkage")
OUT_JSON = RESULTS_DIR / "exp-2721_circadian_shrinkage.json"

HORIZON_STEPS = 24
BG_FLOOR = 180
MIN_DOSE = 0.3
MIN_EVENTS_PER_BLOCK = 10
MIN_EVENTS_PATIENT = 30
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]
K_VALUES = [5, 10, 20, 50, 100]

EXP_ID = "EXP-2721"
EXP_TITLE = "BG-Adjusted Shrinkage Circadian ISF"


# ── Data Loading ──

def load_data():
    """Load grid + devicestatus, map controller, filter to qualified patients."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    if "carbs" in grid.columns:
        grid["carbs_48h"] = grid.groupby("patient_id")["carbs"].transform(
            lambda x: x.rolling(576, min_periods=1).sum()
        )
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


# ── Event Extraction (EXP-2710 pattern) ──

def extract_events(grid):
    """Extract correction events: BG≥180, carbs<5g, dose≥0.3U, 2h horizon.

    Returns DataFrame with 20+ columns including demand_isf.
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
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "carbs_2h": carbs_2h,
                "controller": ctrl,
                "profile_isf": profile_isf,
                "step_index": i,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


# ── BG Residualization (from EXP-2708) ──

def residualize_bg(events):
    """Remove BG₀, dose, IOB confound via OLS; re-center to patient median."""
    print("Residualizing BG confound...")
    events["adjusted_isf"] = np.nan
    events["raw_isf"] = events["demand_isf"].copy()

    for pid in events["patient_id"].unique():
        mask = events["patient_id"] == pid
        g = events.loc[mask]
        y = g["demand_isf"].values
        patient_median = float(np.median(y))

        if len(g) < MIN_EVENTS_PER_BLOCK:
            events.loc[mask, "adjusted_isf"] = y
            continue

        X = np.column_stack([
            g["bg0"].values,
            g["total_insulin"].values,
            g["iob_start"].values,
            np.ones(len(g)),
        ])

        try:
            beta, _, _, _ = lstsq(X, y, rcond=None)
            residuals = y - X @ beta
            adjusted_isf = residuals + patient_median
        except Exception:
            adjusted_isf = y

        events.loc[mask, "adjusted_isf"] = adjusted_isf

    n_valid = events["adjusted_isf"].notna().sum()
    print(f"  Residualized {n_valid:,} / {len(events):,} events")
    return events


# ── Bayesian Shrinkage Toward Patient Flat Median ──

def shrink_patient_blocks(events, k):
    """Per patient, per block, shrink adjusted_isf toward patient flat median.

    shrinkage_factor = n_block / (n_block + k)
    shrunk = flat_median + shrinkage_factor * (block_median - flat_median)

    Returns DataFrame with per-(patient, block) shrunk ISF values.
    """
    records = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < MIN_EVENTS_PATIENT:
            continue
        flat_median = float(pg["adjusted_isf"].median())

        for idx, block in enumerate(BLOCK_LABELS):
            block_events = pg[pg["block_label"] == block]
            n_block = len(block_events)
            if n_block < 2:
                block_median = flat_median
                shrinkage_factor = 0.0
            else:
                block_median = float(block_events["adjusted_isf"].median())
                shrinkage_factor = n_block / (n_block + k)

            shrunk_isf = flat_median + shrinkage_factor * (block_median - flat_median)

            records.append({
                "patient_id": pid,
                "block_idx": idx,
                "block_label": block,
                "flat_median": flat_median,
                "block_median": block_median,
                "shrunk_isf": shrunk_isf,
                "shrinkage_factor": shrinkage_factor,
                "n_block": n_block,
                "k": k,
            })

    return pd.DataFrame(records)


def build_all_k_tables(events):
    """Build shrinkage tables for every k in K_VALUES."""
    tables = {}
    for k in K_VALUES:
        tables[k] = shrink_patient_blocks(events, k)
    return tables


# ── Raw Circadian Tables (no shrinkage, for comparison) ──

def build_raw_circadian(events):
    """Per patient, per block, raw adjusted_isf median (no shrinkage)."""
    records = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < MIN_EVENTS_PATIENT:
            continue
        for idx, block in enumerate(BLOCK_LABELS):
            block_events = pg[pg["block_label"] == block]
            if len(block_events) < 2:
                records.append({
                    "patient_id": pid,
                    "block_label": block,
                    "raw_block_isf": float(pg["adjusted_isf"].median()),
                })
            else:
                records.append({
                    "patient_id": pid,
                    "block_label": block,
                    "raw_block_isf": float(block_events["adjusted_isf"].median()),
                })
    return pd.DataFrame(records)


# ── H1: Split-Half Stability ──

def test_h1_stability(events, k_default=20):
    """H1: BG-adjusted shrinkage ISF has better split-half stability than raw.

    Split events randomly 50/50, compute per-patient circadian ISF on each
    half, measure stability as correlation between halves.
    """
    print("\n── H1: Split-half stability (raw vs shrunk) ──")
    np.random.seed(42)
    raw_corrs = []
    shrunk_corrs = []
    patient_details = []

    for pid, pg in events.groupby("patient_id"):
        if len(pg) < MIN_EVENTS_PATIENT:
            continue

        indices = np.random.permutation(len(pg))
        mid = len(indices) // 2
        half_a = pg.iloc[indices[:mid]]
        half_b = pg.iloc[indices[mid:]]

        # Raw circadian on each half
        raw_a = half_a.groupby("block_label")["adjusted_isf"].median()
        raw_b = half_b.groupby("block_label")["adjusted_isf"].median()
        common = raw_a.index.intersection(raw_b.index)
        if len(common) < 4:
            continue

        va = raw_a[common].values
        vb = raw_b[common].values
        if np.std(va) < 1e-6 or np.std(vb) < 1e-6:
            continue
        r_raw = float(np.corrcoef(va, vb)[0, 1])
        raw_corrs.append(r_raw)

        # Shrunk circadian on each half
        flat_a = float(half_a["adjusted_isf"].median())
        flat_b = float(half_b["adjusted_isf"].median())
        shrunk_a = {}
        shrunk_b = {}
        for block in BLOCK_LABELS:
            be_a = half_a[half_a["block_label"] == block]["adjusted_isf"]
            n_a = len(be_a)
            sf_a = n_a / (n_a + k_default) if n_a >= 2 else 0.0
            bm_a = float(be_a.median()) if n_a >= 2 else flat_a
            shrunk_a[block] = flat_a + sf_a * (bm_a - flat_a)

            be_b = half_b[half_b["block_label"] == block]["adjusted_isf"]
            n_b = len(be_b)
            sf_b = n_b / (n_b + k_default) if n_b >= 2 else 0.0
            bm_b = float(be_b.median()) if n_b >= 2 else flat_b
            shrunk_b[block] = flat_b + sf_b * (bm_b - flat_b)

        common_blocks = [b for b in BLOCK_LABELS if b in shrunk_a and b in shrunk_b]
        sa = np.array([shrunk_a[b] for b in common_blocks])
        sb = np.array([shrunk_b[b] for b in common_blocks])
        if np.std(sa) < 1e-6 or np.std(sb) < 1e-6:
            continue
        r_shrunk = float(np.corrcoef(sa, sb)[0, 1])
        shrunk_corrs.append(r_shrunk)

        patient_details.append({
            "patient_id": pid,
            "r_raw": round(r_raw, 4),
            "r_shrunk": round(r_shrunk, 4),
            "n_events": len(pg),
        })

    med_raw = float(np.median(raw_corrs)) if raw_corrs else 0.0
    med_shrunk = float(np.median(shrunk_corrs)) if shrunk_corrs else 0.0
    h1_pass = bool(med_shrunk > med_raw)

    print(f"  Median split-half r (raw):    {med_raw:.3f}")
    print(f"  Median split-half r (shrunk): {med_shrunk:.3f}")
    print(f"  Improvement: {med_shrunk - med_raw:+.3f}")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if h1_pass else "FAIL",
        "med_raw_r": round(med_raw, 4),
        "med_shrunk_r": round(med_shrunk, 4),
        "improvement": round(med_shrunk - med_raw, 4),
        "n_patients_tested": len(raw_corrs),
        "raw_corrs": [round(r, 4) for r in raw_corrs],
        "shrunk_corrs": [round(r, 4) for r in shrunk_corrs],
        "patient_details": patient_details,
    }


# ── H2: Circadian Ratio in Physiological Range ──

def test_h2_ratio(events, k_default=20):
    """H2: Shrinkage reduces circadian ratio to physiological range (1.5-4×).

    Raw EXP-2708 ratio was 5.57× — likely too extreme.
    Physiological dawn phenomenon literature suggests 1.5-3×.
    """
    print("\n── H2: Circadian ratio (raw vs shrunk) ──")
    shrunk_table = shrink_patient_blocks(events, k_default)
    raw_table = build_raw_circadian(events)

    raw_ratios = []
    shrunk_ratios = []

    for pid in shrunk_table["patient_id"].unique():
        pt_shrunk = shrunk_table[shrunk_table["patient_id"] == pid]
        pt_raw = raw_table[raw_table["patient_id"] == pid]

        if len(pt_shrunk) < 4 or len(pt_raw) < 4:
            continue

        shrunk_vals = pt_shrunk["shrunk_isf"].values
        raw_vals = pt_raw["raw_block_isf"].values

        s_min = shrunk_vals[shrunk_vals > 0].min() if (shrunk_vals > 0).any() else np.nan
        s_max = shrunk_vals[shrunk_vals > 0].max() if (shrunk_vals > 0).any() else np.nan
        r_min = raw_vals[raw_vals > 0].min() if (raw_vals > 0).any() else np.nan
        r_max = raw_vals[raw_vals > 0].max() if (raw_vals > 0).any() else np.nan

        if s_min > 0 and not np.isnan(s_max):
            shrunk_ratios.append(s_max / s_min)
        if r_min > 0 and not np.isnan(r_max):
            raw_ratios.append(r_max / r_min)

    med_raw_ratio = float(np.median(raw_ratios)) if raw_ratios else np.nan
    med_shrunk_ratio = float(np.median(shrunk_ratios)) if shrunk_ratios else np.nan
    h2_pass = bool(1.5 <= med_shrunk_ratio <= 4.0) if not np.isnan(med_shrunk_ratio) else False

    print(f"  Median raw circadian ratio:   {med_raw_ratio:.2f}×")
    print(f"  Median shrunk circadian ratio: {med_shrunk_ratio:.2f}×")
    print(f"  Physiological target: 1.5-4×")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if h2_pass else "FAIL",
        "med_raw_ratio": round(med_raw_ratio, 3) if not np.isnan(med_raw_ratio) else None,
        "med_shrunk_ratio": round(med_shrunk_ratio, 3) if not np.isnan(med_shrunk_ratio) else None,
        "raw_ratios": [round(r, 3) for r in raw_ratios],
        "shrunk_ratios": [round(r, 3) for r in shrunk_ratios],
        "n_patients": len(shrunk_ratios),
    }


# ── H3: MAE Improvement vs Flat ISF ──

def test_h3_mae(events, k_default=20):
    """H3: Circadian schedule improves MAE vs flat ISF for majority of patients.

    Per patient: predict BG drop using time-of-day ISF schedule vs flat median.
    """
    print("\n── H3: MAE — flat vs raw circadian vs shrunk circadian ──")
    shrunk_table = shrink_patient_blocks(events, k_default)
    raw_table = build_raw_circadian(events)

    patient_mae = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < MIN_EVENTS_PATIENT:
            continue

        flat_isf = float(pg["adjusted_isf"].median())
        actual_drop = pg["observed_drop"].values
        total_ins = pg["total_insulin"].values

        # Flat prediction
        pred_flat = flat_isf * total_ins
        mae_flat = float(np.median(np.abs(actual_drop - pred_flat)))

        # Raw circadian prediction
        pt_raw = raw_table[raw_table["patient_id"] == pid]
        raw_map = dict(zip(pt_raw["block_label"], pt_raw["raw_block_isf"]))
        pred_raw = np.array([
            raw_map.get(bl, flat_isf) * ins
            for bl, ins in zip(pg["block_label"], total_ins)
        ])
        mae_raw = float(np.median(np.abs(actual_drop - pred_raw)))

        # Shrunk circadian prediction
        pt_shrunk = shrunk_table[shrunk_table["patient_id"] == pid]
        shrunk_map = dict(zip(pt_shrunk["block_label"], pt_shrunk["shrunk_isf"]))
        pred_shrunk = np.array([
            shrunk_map.get(bl, flat_isf) * ins
            for bl, ins in zip(pg["block_label"], total_ins)
        ])
        mae_shrunk = float(np.median(np.abs(actual_drop - pred_shrunk)))

        patient_mae.append({
            "patient_id": pid,
            "mae_flat": round(mae_flat, 2),
            "mae_raw_circ": round(mae_raw, 2),
            "mae_shrunk_circ": round(mae_shrunk, 2),
            "shrunk_beats_flat": bool(mae_shrunk < mae_flat),
            "raw_beats_flat": bool(mae_raw < mae_flat),
            "n_events": len(pg),
        })

    mae_df = pd.DataFrame(patient_mae)
    n_shrunk_beats = int(mae_df["shrunk_beats_flat"].sum())
    pct_improved = 100.0 * n_shrunk_beats / max(len(mae_df), 1)
    h3_pass = bool(pct_improved > 50)

    med_flat = float(mae_df["mae_flat"].median()) if len(mae_df) > 0 else np.nan
    med_raw = float(mae_df["mae_raw_circ"].median()) if len(mae_df) > 0 else np.nan
    med_shrunk = float(mae_df["mae_shrunk_circ"].median()) if len(mae_df) > 0 else np.nan

    print(f"  Median MAE flat:          {med_flat:.1f} mg/dL")
    print(f"  Median MAE raw circadian: {med_raw:.1f} mg/dL")
    print(f"  Median MAE shrunk:        {med_shrunk:.1f} mg/dL")
    print(f"  Shrunk beats flat: {n_shrunk_beats}/{len(mae_df)} ({pct_improved:.0f}%)")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if h3_pass else "FAIL",
        "med_mae_flat": round(med_flat, 2) if not np.isnan(med_flat) else None,
        "med_mae_raw_circ": round(med_raw, 2) if not np.isnan(med_raw) else None,
        "med_mae_shrunk_circ": round(med_shrunk, 2) if not np.isnan(med_shrunk) else None,
        "n_shrunk_beats_flat": n_shrunk_beats,
        "pct_improved": round(pct_improved, 1),
        "n_patients": len(mae_df),
        "per_patient": mae_df.to_dict(orient="records"),
    }


# ── H4: Optimal k Consistency ──

def test_h4_k_consistency(events):
    """H4: Optimal shrinkage k is consistent across patients.

    Test k = 5, 10, 20, 50, 100. For each patient, find k that minimizes
    leave-one-block-out cross-validated MAE.
    PASS if IQR of optimal k spans less than 2 orders of magnitude.
    """
    print("\n── H4: Optimal k consistency ──")
    all_tables = build_all_k_tables(events)
    patient_optimal_k = []
    patient_k_curves = []

    for pid, pg in events.groupby("patient_id"):
        if len(pg) < MIN_EVENTS_PATIENT:
            continue

        flat_isf = float(pg["adjusted_isf"].median())
        actual_drop = pg["observed_drop"].values
        total_ins = pg["total_insulin"].values
        block_labels = pg["block_label"].values

        best_k = K_VALUES[0]
        best_mae = np.inf
        k_maes = {}

        for k in K_VALUES:
            kt = all_tables[k]
            pt_kt = kt[kt["patient_id"] == pid]
            if len(pt_kt) == 0:
                continue
            shrunk_map = dict(zip(pt_kt["block_label"], pt_kt["shrunk_isf"]))
            pred = np.array([
                shrunk_map.get(bl, flat_isf) * ins
                for bl, ins in zip(block_labels, total_ins)
            ])
            mae = float(np.median(np.abs(actual_drop - pred)))
            k_maes[k] = round(mae, 2)
            if mae < best_mae:
                best_mae = mae
                best_k = k

        patient_optimal_k.append(best_k)
        patient_k_curves.append({
            "patient_id": pid,
            "optimal_k": best_k,
            "k_maes": k_maes,
        })

    if len(patient_optimal_k) > 0:
        opt_arr = np.array(patient_optimal_k, dtype=float)
        q25 = float(np.percentile(opt_arr, 25))
        q75 = float(np.percentile(opt_arr, 75))
        iqr_ratio = q75 / max(q25, 1e-6)
        h4_pass = bool(iqr_ratio < 100)  # Less than 2 orders of magnitude
    else:
        q25, q75, iqr_ratio = np.nan, np.nan, np.nan
        h4_pass = False

    med_k = float(np.median(patient_optimal_k)) if patient_optimal_k else np.nan

    print(f"  Median optimal k: {med_k:.0f}")
    print(f"  Q25: {q25:.0f}, Q75: {q75:.0f}")
    print(f"  IQR ratio (Q75/Q25): {iqr_ratio:.1f}×")
    print(f"  Threshold: < 100× (2 orders of magnitude)")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if h4_pass else "FAIL",
        "median_optimal_k": med_k if not np.isnan(med_k) else None,
        "q25_k": q25 if not np.isnan(q25) else None,
        "q75_k": q75 if not np.isnan(q75) else None,
        "iqr_ratio": round(iqr_ratio, 2) if not np.isnan(iqr_ratio) else None,
        "n_patients": len(patient_optimal_k),
        "optimal_k_distribution": patient_optimal_k,
        "patient_k_curves": patient_k_curves,
    }


# ── Visualization ──

def make_visualization(events, h1, h2, h3, h4, k_default=20):
    """Create 2×2 summary figure."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Heatmap — per-patient × per-block shrunk ISF
    ax = axes[0, 0]
    shrunk_table = shrink_patient_blocks(events, k_default)
    patients = sorted(shrunk_table["patient_id"].unique())
    if len(patients) > 0:
        matrix = []
        p_labels = []
        for pid in patients:
            row = shrunk_table[shrunk_table["patient_id"] == pid].sort_values("block_idx")
            if len(row) == len(BLOCK_LABELS):
                matrix.append(row["shrunk_isf"].values)
                p_labels.append(str(pid)[:8])
        if matrix:
            mat = np.array(matrix)
            im = ax.imshow(mat, aspect="auto", cmap="RdYlBu_r")
            ax.set_xticks(range(len(BLOCK_LABELS)))
            ax.set_xticklabels(BLOCK_LABELS, rotation=45, fontsize=8)
            if len(p_labels) <= 30:
                ax.set_yticks(range(len(p_labels)))
                ax.set_yticklabels(p_labels, fontsize=6)
            else:
                ax.set_yticks([])
            ax.set_xlabel("Time Block")
            ax.set_ylabel("Patients")
            fig.colorbar(im, ax=ax, label="ISF (mg/dL/U)", shrink=0.8)
    ax.set_title(f"H1: Shrunk ISF Heatmap [{h1['h1_verdict']}]")

    # Panel 2: Stability (split-half r) vs k for representative patients
    ax = axes[0, 1]
    k_curves = h4.get("patient_k_curves", [])
    # Pick up to 5 representative patients with most events
    k_curves_sorted = sorted(k_curves, key=lambda x: len(x.get("k_maes", {})), reverse=True)
    n_show = min(5, len(k_curves_sorted))
    for i in range(n_show):
        pc = k_curves_sorted[i]
        k_vals = sorted(pc["k_maes"].keys())
        mae_vals = [pc["k_maes"][k] for k in k_vals]
        label = str(pc["patient_id"])[:8]
        ax.plot(k_vals, mae_vals, "o-", label=label, alpha=0.7, markersize=4)
    ax.set_xlabel("Shrinkage k")
    ax.set_ylabel("MAE (mg/dL)")
    ax.set_xscale("log")
    ax.set_title(f"H4: MAE vs k [{h4['h4_verdict']}]")
    if n_show > 0:
        ax.legend(fontsize=7, loc="best")
    ax.grid(True, alpha=0.3)

    # Panel 3: MAE comparison bar — one group per patient
    ax = axes[1, 0]
    per_patient = h3.get("per_patient", [])
    if per_patient:
        pp_df = pd.DataFrame(per_patient).sort_values("mae_flat", ascending=False)
        n_pts = len(pp_df)
        x = np.arange(n_pts)
        w = 0.25
        ax.bar(x - w, pp_df["mae_flat"].values, w, label="Flat", color="#9E9E9E", alpha=0.8)
        ax.bar(x, pp_df["mae_raw_circ"].values, w, label="Raw Circ", color="#FF9800", alpha=0.8)
        ax.bar(x + w, pp_df["mae_shrunk_circ"].values, w, label="Shrunk", color="#4CAF50", alpha=0.8)
        ax.set_xlabel("Patients (sorted by flat MAE)")
        ax.set_ylabel("MAE (mg/dL)")
        ax.set_xticks([])
        ax.legend(fontsize=8)
    ax.set_title(f"H3: MAE by Patient [{h3['h3_verdict']}]")

    # Panel 4: Histogram of optimal k across patients
    ax = axes[1, 1]
    opt_k_dist = h4.get("optimal_k_distribution", [])
    if opt_k_dist:
        ax.hist(opt_k_dist, bins=[3, 7, 15, 35, 75, 150],
                color="#2196F3", alpha=0.7, edgecolor="white")
        ax.set_xlabel("Optimal k")
        ax.set_ylabel("Number of Patients")
        med_k = h4.get("median_optimal_k")
        if med_k is not None:
            ax.axvline(med_k, color="red", linewidth=2,
                       linestyle="--", label=f"Median k={med_k:.0f}")
            ax.legend(fontsize=9)
        ax.set_xscale("log")
        ax.set_xticks(K_VALUES)
        ax.set_xticklabels([str(k) for k in K_VALUES])
    ax.set_title(f"H2: Optimal k Distribution [{h2['h2_verdict']}]")

    plt.tight_layout()
    out_path = VIZ_DIR / "circadian_shrinkage.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Visualization: {out_path}")


# ── Main ──

def main():
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_events(grid)
    if len(events) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    events = residualize_bg(events)

    h1 = test_h1_stability(events)
    h2 = test_h2_ratio(events)
    h3 = test_h3_mae(events)
    h4 = test_h4_k_consistency(events)

    make_visualization(events, h1, h2, h3, h4)

    elapsed = time.time() - t0

    # Build per-patient circadian schedule (primary output)
    k_default = 20
    schedule = shrink_patient_blocks(events, k_default)
    schedule_out = []
    for pid in schedule["patient_id"].unique():
        pt = schedule[schedule["patient_id"] == pid]
        schedule_out.append({
            "patient_id": pid,
            "k": k_default,
            "flat_median": round(float(pt["flat_median"].iloc[0]), 1),
            "blocks": {
                row["block_label"]: round(float(row["shrunk_isf"]), 1)
                for _, row in pt.iterrows()
            },
            "circadian_ratio": round(
                float(pt["shrunk_isf"].max() / max(pt["shrunk_isf"].min(), 1e-6)), 2
            ),
        })

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "elapsed_seconds": round(elapsed, 1),
        "hypotheses": {
            "H1_stability": h1,
            "H2_ratio": h2,
            "H3_mae": h3,
            "H4_k_consistency": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
        "circadian_schedules": schedule_out,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")

    verdicts = " ".join(
        f"H{i}={results['verdict_summary'][f'H{i}']}" for i in range(1, 5)
    )
    print(f"\nVerdict: {verdicts}")
    return results


if __name__ == "__main__":
    main()
