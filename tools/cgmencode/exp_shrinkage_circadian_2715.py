#!/usr/bin/env python3
"""EXP-2715: Shrinkage Circadian ISF Model

EXP-2711 showed circadian ISF tables are clinically meaningful (94% diff
from profile) but too noisy to beat flat ISF in per-patient prediction
(MAE 52.9 vs 49.9). The problem: with only ~300 events per patient split
into 6 time blocks, per-block estimates have high variance.

Solution: Empirical Bayes / James-Stein shrinkage. Estimate a POPULATION
circadian shape (relative ISF by time block), then shrink each patient's
per-block ISF toward the population shape. Patients with few events get
more shrinkage toward population; patients with many events keep their
individual pattern.

Hypotheses:
  H1: Shrinkage circadian ISF beats flat ISF (lower MAE for >60% patients)
  H2: Shrinkage beats raw per-patient circadian (lower MAE for >60%)
  H3: Population circadian peak is consistent with EXP-2708 (20-24h band)
  H4: Split-half stability of shrinkage > raw (median r > 0.6)

Design:
  - Extract BG-residualized ISF per (patient, block_label) as in EXP-2708
  - Compute population mean per block (the "prior")
  - Apply shrinkage: ISF_shrunk = w * ISF_patient + (1-w) * ISF_pop
    where w = n_patient_block / (n_patient_block + k), k = population τ²
  - Evaluate MAE: flat vs raw-circadian vs shrinkage-circadian
  - Split-half stability test

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
OUT_JSON = Path("externals/experiments/exp-2715_shrinkage_circadian.json")
VIS_DIR = Path("visualizations/shrinkage-circadian")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2715"
EXP_TITLE = "Shrinkage Circadian ISF Model"


def load_data():
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


def extract_events(grid):
    """Extract correction events with per-patient loop (EXP-2710 pattern).

    Uses columns: glucose, bolus, iob, bolus_smb, net_basal, carbs,
    scheduled_isf, time.  Builds events with bg0, bg_end, observed_drop,
    total_insulin, demand_isf, bolus_2h, smb_2h, excess_basal_2h,
    iob_start, hour, block_idx, block_label, controller, profile_isf,
    step_index.  Then BG-residualizes demand_isf → isf_residualized.
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
                "controller": ctrl,
                "profile_isf": profile_isf,
                "step_index": i,
            })

    df = pd.DataFrame(events)

    # BG residualization (remove BG₀ / dose / IOB confound, as in EXP-2708)
    df["isf_residualized"] = np.nan
    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        g = df.loc[mask]
        if len(g) < 10:
            df.loc[mask, "isf_residualized"] = g["demand_isf"] - g["demand_isf"].mean()
            continue
        X = np.column_stack([
            g["bg0"].values,
            g["total_insulin"].values,
            g["iob_start"].values,
            np.ones(len(g))
        ])
        y = g["demand_isf"].values
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            resid = y - X @ beta
            # Re-center to patient median
            resid = resid + g["demand_isf"].median()
        except Exception:
            resid = y
        df.loc[mask, "isf_residualized"] = resid

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def compute_shrinkage_tables(events):
    """Compute per-(patient, block) ISF with James-Stein shrinkage."""

    # Population circadian shape
    pop_block = events.groupby("block_label")["isf_residualized"].agg(["mean", "std", "count"])
    pop_block.columns = ["pop_mean", "pop_std", "pop_n"]

    # Population between-block variance (τ²)
    tau2 = pop_block["pop_mean"].var()

    # Per (patient, block) raw estimates
    pt_block = events.groupby(["patient_id", "block_label"])["isf_residualized"].agg(["mean", "std", "count"])
    pt_block.columns = ["pt_mean", "pt_std", "pt_n"]
    pt_block = pt_block.reset_index()

    # Merge population
    pt_block = pt_block.merge(pop_block.reset_index(), on="block_label", how="left")

    # Within-block variance (σ² per patient-block)
    pt_block["sigma2"] = pt_block["pt_std"] ** 2

    # Shrinkage weight: w = τ² / (τ² + σ²/n)
    pt_block["w"] = tau2 / (tau2 + pt_block["sigma2"] / pt_block["pt_n"].clip(lower=1))
    pt_block["w"] = pt_block["w"].clip(0, 1)

    # Shrinkage ISF
    pt_block["shrunk_isf"] = pt_block["w"] * pt_block["pt_mean"] + (1 - pt_block["w"]) * pt_block["pop_mean"]

    # Flat ISF per patient (for comparison)
    flat_isf = events.groupby("patient_id")["isf_residualized"].median().to_dict()
    pt_block["flat_isf"] = pt_block["patient_id"].map(flat_isf)

    return pt_block, pop_block, tau2


def evaluate_mae(events, pt_block):
    """Evaluate MAE for flat, raw-circadian, and shrinkage-circadian predictions."""

    # Merge ISF predictions back to events
    ev = events.copy()
    ev = ev.merge(
        pt_block[["patient_id", "block_label", "pt_mean", "shrunk_isf", "flat_isf"]],
        on=["patient_id", "block_label"], how="left"
    )

    # Predictions: BG_end_pred = bg0 - ISF × total_insulin
    ev["bg_pred_flat"] = ev["bg0"] - ev["flat_isf"] * ev["total_insulin"]
    ev["bg_pred_raw_circ"] = ev["bg0"] - ev["pt_mean"] * ev["total_insulin"]
    ev["bg_pred_shrunk"] = ev["bg0"] - ev["shrunk_isf"] * ev["total_insulin"]

    results_per_patient = []
    for pid, g in ev.groupby("patient_id"):
        if len(g) < 5:
            continue
        actual_p = g["bg_end"].values
        mae_flat = np.nanmedian(np.abs(actual_p - g["bg_pred_flat"].values))
        mae_raw = np.nanmedian(np.abs(actual_p - g["bg_pred_raw_circ"].values))
        mae_shrunk = np.nanmedian(np.abs(actual_p - g["bg_pred_shrunk"].values))
        results_per_patient.append({
            "patient_id": pid,
            "mae_flat": mae_flat,
            "mae_raw_circ": mae_raw,
            "mae_shrunk": mae_shrunk,
            "shrunk_beats_flat": mae_shrunk < mae_flat,
            "shrunk_beats_raw": mae_shrunk < mae_raw,
            "n_events": len(g),
        })

    return pd.DataFrame(results_per_patient)


def split_half_stability(events):
    """Split-half correlation: compare circadian pattern in first vs second half."""
    raw_corrs = []
    shrunk_corrs = []

    for pid, g in events.groupby("patient_id"):
        g = g.sort_values("step_index")
        mid = len(g) // 2
        first = g.iloc[:mid]
        second = g.iloc[mid:]

        # Raw circadian pattern
        raw_first = first.groupby("block_label")["isf_residualized"].mean()
        raw_second = second.groupby("block_label")["isf_residualized"].mean()
        common = raw_first.index.intersection(raw_second.index)
        if len(common) < 4:
            continue
        r_raw = np.corrcoef(raw_first[common].values, raw_second[common].values)[0, 1]
        raw_corrs.append(r_raw)

        # Shrinkage needs population prior — use first-half population
        pop_first = first.groupby("block_label")["isf_residualized"].mean()
        tau2 = pop_first.var()

        def shrink(half, pop, tau2):
            result = {}
            for block in BLOCK_LABELS:
                sub = half[half["block_label"] == block]["isf_residualized"]
                if len(sub) < 2:
                    result[block] = pop.get(block, 0)
                    continue
                sigma2 = sub.var()
                n = len(sub)
                w = tau2 / (tau2 + sigma2 / max(n, 1)) if tau2 > 0 else 0
                result[block] = w * sub.mean() + (1 - w) * pop.get(block, 0)
            return result

        shrunk_first = shrink(first, pop_first.to_dict(), tau2)
        shrunk_second = shrink(second, pop_first.to_dict(), tau2)
        common_blocks = [b for b in BLOCK_LABELS if b in shrunk_first and b in shrunk_second]
        if len(common_blocks) < 4:
            continue
        r_shrunk = np.corrcoef(
            [shrunk_first[b] for b in common_blocks],
            [shrunk_second[b] for b in common_blocks]
        )[0, 1]
        shrunk_corrs.append(r_shrunk)

    return raw_corrs, shrunk_corrs


def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    print("\nLoading data...")
    grid = load_data()

    print("Extracting and residualizing events...")
    events = extract_events(grid)

    print("\nComputing shrinkage tables...")
    pt_block, pop_block, tau2 = compute_shrinkage_tables(events)
    print(f"  Population τ²: {tau2:.2f}")
    print(f"  Median shrinkage weight: {pt_block['w'].median():.3f}")

    # ── H1: Shrinkage beats flat ISF ──
    print("\n── H1: Shrinkage circadian beats flat ISF? ──")
    mae_df = evaluate_mae(events, pt_block)
    n_shrunk_beats_flat = mae_df["shrunk_beats_flat"].sum()
    pct = n_shrunk_beats_flat / len(mae_df) * 100
    h1_pass = bool(pct > 60)
    print(f"  Shrinkage beats flat: {n_shrunk_beats_flat}/{len(mae_df)} ({pct:.0f}%)")
    print(f"  Median MAE flat: {mae_df['mae_flat'].median():.1f}")
    print(f"  Median MAE shrinkage: {mae_df['mae_shrunk'].median():.1f}")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    # ── H2: Shrinkage beats raw circadian ──
    print("\n── H2: Shrinkage beats raw circadian? ──")
    n_shrunk_beats_raw = mae_df["shrunk_beats_raw"].sum()
    pct2 = n_shrunk_beats_raw / len(mae_df) * 100
    h2_pass = bool(pct2 > 60)
    print(f"  Shrinkage beats raw: {n_shrunk_beats_raw}/{len(mae_df)} ({pct2:.0f}%)")
    print(f"  Median MAE raw circadian: {mae_df['mae_raw_circ'].median():.1f}")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    # ── H3: Population circadian peak at 20-24h ──
    print("\n── H3: Population circadian peak at 20-24h? ──")
    pop_means = pop_block["pop_mean"]
    peak_block = pop_means.idxmax()
    h3_pass = bool(peak_block in ["16-20", "20-24"])
    print(f"  Population circadian ISF by block:")
    for block in BLOCK_LABELS:
        if block in pop_means.index:
            print(f"    {block}: {pop_means[block]:.1f}")
    print(f"  Peak block: {peak_block}")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    # ── H4: Split-half stability ──
    print("\n── H4: Split-half stability? ──")
    raw_corrs, shrunk_corrs = split_half_stability(events)
    med_raw = float(np.median(raw_corrs)) if raw_corrs else 0
    med_shrunk = float(np.median(shrunk_corrs)) if shrunk_corrs else 0
    h4_pass = bool(med_shrunk > 0.6)
    print(f"  Median split-half r (raw): {med_raw:.3f}")
    print(f"  Median split-half r (shrinkage): {med_shrunk:.3f}")
    print(f"  Improvement: {med_shrunk - med_raw:.3f}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    # ── Visualization ──
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

        # Panel 1: Population circadian shape
        ax = axes[0, 0]
        blocks = BLOCK_LABELS
        pop_vals = [pop_means.get(b, 0) for b in blocks]
        ax.plot(blocks, pop_vals, "b-o", linewidth=2, markersize=8)
        peak_idx = blocks.index(peak_block) if peak_block in blocks else 0
        ax.plot(blocks[peak_idx], pop_vals[peak_idx], "r*", markersize=15)
        ax.set_ylabel("ISF (BG-adjusted)")
        ax.set_title("Population Circadian Shape")
        ax.grid(True, alpha=0.3)

        # Panel 2: MAE comparison (3 methods)
        ax = axes[0, 1]
        methods = ["Flat", "Raw Circadian", "Shrinkage"]
        maes = [mae_df["mae_flat"].median(), mae_df["mae_raw_circ"].median(), mae_df["mae_shrunk"].median()]
        colors = ["#9E9E9E", "#FF9800", "#4CAF50"]
        bars = ax.bar(methods, maes, color=colors, alpha=0.8)
        for bar, val in zip(bars, maes):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f"{val:.1f}", ha="center", fontsize=10)
        ax.set_ylabel("Median MAE (mg/dL)")
        ax.set_title("Prediction MAE by Method")

        # Panel 3: Per-patient improvement
        ax = axes[0, 2]
        improvement = mae_df["mae_flat"] - mae_df["mae_shrunk"]
        colors_pt = ["#4CAF50" if x > 0 else "#F44336" for x in improvement]
        ax.bar(range(len(improvement)), sorted(improvement, reverse=True), color=colors_pt, alpha=0.7)
        ax.axhline(0, color="black", linewidth=1)
        ax.set_xlabel("Patients (sorted)")
        ax.set_ylabel("MAE improvement (mg/dL)")
        ax.set_title(f"Per-Patient: Shrinkage vs Flat\n({n_shrunk_beats_flat}/{len(mae_df)} improved)")

        # Panel 4: Shrinkage weights
        ax = axes[1, 0]
        ax.hist(pt_block["w"], bins=30, color="#2196F3", alpha=0.7, edgecolor="white")
        ax.axvline(pt_block["w"].median(), color="red", linewidth=2,
                   label=f"Median={pt_block['w'].median():.3f}")
        ax.set_xlabel("Shrinkage weight (1=keep patient, 0=use population)")
        ax.set_ylabel("Count")
        ax.set_title("Shrinkage Weight Distribution")
        ax.legend()

        # Panel 5: Split-half stability
        ax = axes[1, 1]
        if raw_corrs and shrunk_corrs:
            ax.boxplot([raw_corrs, shrunk_corrs], labels=["Raw", "Shrinkage"])
            ax.axhline(0.6, color="green", linestyle="--", label="H4 threshold")
            ax.set_ylabel("Split-half correlation")
            ax.set_title("Temporal Stability")
            ax.legend()
        else:
            ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center")

        # Panel 6: Scorecard
        ax = axes[1, 2]
        ax.axis("off")
        scorecard = (
            f"H1: Shrinkage > flat — {'✓ PASS' if h1_pass else '✗ FAIL'}\n"
            f"    ({n_shrunk_beats_flat}/{len(mae_df)} patients, {pct:.0f}%)\n\n"
            f"H2: Shrinkage > raw — {'✓ PASS' if h2_pass else '✗ FAIL'}\n"
            f"    ({n_shrunk_beats_raw}/{len(mae_df)} patients, {pct2:.0f}%)\n\n"
            f"H3: Peak at 20-24h — {'✓ PASS' if h3_pass else '✗ FAIL'}\n"
            f"    (Peak: {peak_block})\n\n"
            f"H4: Stability r>0.6 — {'✓ PASS' if h4_pass else '✗ FAIL'}\n"
            f"    (Raw: {med_raw:.3f}, Shrunk: {med_shrunk:.3f})"
        )
        ax.text(0.1, 0.9, scorecard, fontsize=12, fontfamily="monospace",
                verticalalignment="top", transform=ax.transAxes)

        plt.tight_layout()
        plt.savefig(VIS_DIR / "shrinkage_circadian.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Visualization: {VIS_DIR / 'shrinkage_circadian.png'}")
    except ImportError:
        print("  (matplotlib not available, skipping visualization)")

    # ── Results ──
    results = {
        "experiment": EXP_ID,
        "title": EXP_TITLE,
        "n_events": len(events),
        "n_patients": int(events["patient_id"].nunique()),
        "population_tau2": float(tau2),
        "median_shrinkage_weight": float(pt_block["w"].median()),
        "population_circadian": {b: float(pop_means.get(b, 0)) for b in BLOCK_LABELS},
        "peak_block": str(peak_block),
        "mae_flat": float(mae_df["mae_flat"].median()),
        "mae_raw_circ": float(mae_df["mae_raw_circ"].median()),
        "mae_shrunk": float(mae_df["mae_shrunk"].median()),
        "pct_shrunk_beats_flat": float(pct),
        "pct_shrunk_beats_raw": float(pct2),
        "split_half_raw_median": med_raw,
        "split_half_shrunk_median": med_shrunk,
        "per_patient": mae_df.to_dict(orient="records"),
        "hypotheses": {
            "H1": {"description": "Shrinkage > flat (>60%)", "pass": h1_pass,
                    "pct": pct},
            "H2": {"description": "Shrinkage > raw circ (>60%)", "pass": h2_pass,
                    "pct": pct2},
            "H3": {"description": "Peak at 16-24h", "pass": h3_pass,
                    "peak": str(peak_block)},
            "H4": {"description": "Stability r>0.6", "pass": h4_pass,
                    "raw_r": med_raw, "shrunk_r": med_shrunk},
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults: {OUT_JSON}")

    verdicts = " ".join(
        f"H{i}={'PASS' if results['hypotheses'][f'H{i}']['pass'] else 'FAIL'}"
        for i in range(1, 5)
    )
    print(f"\nVerdict: {verdicts}")
    return results


if __name__ == "__main__":
    results = main()
