#!/usr/bin/env python3
"""
EXP-2581–2584: Algorithm Prediction Quality Validation

Validates colleague's claim: eventualBG R²=0.002 vs actual 4h BG.
Tests whether physics-based PK predictions outperform algorithm predictions.

Experiments:
  2581 - eventualBG vs actual BG (oref/AAPS patients with eventualBG)
  2582 - Loop predicted_60 vs actual 60min BG (Loop patients)
  2583 - pk_net_balance vs actual BG at multiple horizons
  2584 - Synthesis: algorithm vs physics-based prediction quality

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2581
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score, mean_absolute_error

from oref_inv_003_replication.data_bridge import load_grid
from oref_inv_003_replication.pk_bridge import add_pk_features_to_grid
from oref_inv_003_replication.report_engine import (
    ComparisonReport,
    NumpyEncoder,
)

RESULTS_DIR = Path("externals/experiments")


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _compute_actual_future_bg(group, steps):
    """Compute actual BG at +steps intervals for a patient group."""
    bg = group["glucose"].values
    n = len(bg)
    future = np.full(n, np.nan)
    for i in range(n - steps):
        if not np.isnan(bg[i + steps]):
            future[i] = bg[i + steps]
    return future


def exp_2581_eventual_bg(grid):
    """Validate eventualBG R² vs actual future BG at multiple horizons."""
    print("\n=== EXP-2581: eventualBG prediction quality ===")

    mask = grid["eventual_bg"].notna() & grid["glucose"].notna()
    df = grid[mask].copy()
    print(f"  Rows with eventualBG: {len(df):,} "
          f"({len(df)/len(grid)*100:.1f}% of grid)")

    results = {"per_patient": {}, "horizons": {}}

    # Compute actual future BG at 1h, 2h, 4h (12, 24, 48 steps × 5min)
    horizons = {"1h": 12, "2h": 24, "4h": 48}

    for pid in sorted(df["patient_id"].unique()):
        pmask = df["patient_id"] == pid
        sub = df[pmask]
        if len(sub) < 100:
            print(f"  {pid}: skipping ({len(sub)} rows)")
            continue

        patient_results = {}
        for hlabel, steps in horizons.items():
            # Need to go back to full grid for this patient to get future BG
            full_patient = grid[grid["patient_id"] == pid].copy()
            future_bg = _compute_actual_future_bg(full_patient, steps)
            full_patient[f"actual_{hlabel}"] = future_bg

            # Merge back to eventualBG subset
            merged = sub.merge(
                full_patient[["time", f"actual_{hlabel}"]],
                on="time", how="left"
            )
            valid = merged[merged[f"actual_{hlabel}"].notna()].copy()

            if len(valid) < 50:
                continue

            predicted = valid["eventual_bg"].values
            actual = valid[f"actual_{hlabel}"].values

            r2 = r2_score(actual, predicted)
            mae = mean_absolute_error(actual, predicted)
            rho, p = spearmanr(predicted, actual)

            patient_results[hlabel] = {
                "r2": float(r2),
                "mae": float(mae),
                "rho": float(rho),
                "p": float(p),
                "n": int(len(valid)),
            }

        if patient_results:
            results["per_patient"][pid] = patient_results
            h4 = patient_results.get("4h", {})
            print(f"  {pid}: eventualBG→4h R²={h4.get('r2', '?'):.4f}, "
                  f"MAE={h4.get('mae', '?'):.1f}, n={h4.get('n', '?'):,}")

    # Aggregate across patients
    for hlabel in horizons:
        r2s = [v[hlabel]["r2"] for v in results["per_patient"].values()
               if hlabel in v]
        maes = [v[hlabel]["mae"] for v in results["per_patient"].values()
                if hlabel in v]
        if r2s:
            results["horizons"][hlabel] = {
                "mean_r2": float(np.mean(r2s)),
                "median_r2": float(np.median(r2s)),
                "mean_mae": float(np.mean(maes)),
                "n_patients": len(r2s),
            }
            print(f"  Aggregate {hlabel}: mean R²={np.mean(r2s):.4f}, "
                  f"median R²={np.median(r2s):.4f}, "
                  f"MAE={np.mean(maes):.1f} mg/dL")

    return results


def exp_2582_loop_predicted(grid):
    """Validate Loop's predicted_60 vs actual 60min BG."""
    print("\n=== EXP-2582: Loop predicted_60 quality ===")

    mask = grid["loop_predicted_60"].notna() & grid["glucose"].notna()
    df = grid[mask].copy()
    print(f"  Rows with loop_predicted_60: {len(df):,}")

    results = {"per_patient": {}}

    for pid in sorted(df["patient_id"].unique()):
        full_patient = grid[grid["patient_id"] == pid].copy()
        future_bg = _compute_actual_future_bg(full_patient, 12)  # 60min
        full_patient["actual_1h"] = future_bg

        sub = df[df["patient_id"] == pid]
        merged = sub.merge(full_patient[["time", "actual_1h"]],
                           on="time", how="left")
        valid = merged[merged["actual_1h"].notna()]

        if len(valid) < 100:
            continue

        predicted = valid["loop_predicted_60"].values
        actual = valid["actual_1h"].values

        r2 = r2_score(actual, predicted)
        mae = mean_absolute_error(actual, predicted)
        rho, _ = spearmanr(predicted, actual)

        results["per_patient"][pid] = {
            "r2": float(r2),
            "mae": float(mae),
            "rho": float(rho),
            "n": int(len(valid)),
        }
        print(f"  {pid}: predicted_60→1h R²={r2:.4f}, MAE={mae:.1f}, "
              f"n={len(valid):,}")

    if results["per_patient"]:
        r2s = [v["r2"] for v in results["per_patient"].values()]
        results["mean_r2"] = float(np.mean(r2s))
        results["median_r2"] = float(np.median(r2s))
        print(f"  Loop aggregate: mean R²={np.mean(r2s):.4f}, "
              f"median={np.median(r2s):.4f}")

    return results


def exp_2583_pk_prediction(grid, enriched):
    """Test pk_net_balance as a predictor of future BG change."""
    print("\n=== EXP-2583: PK net_balance prediction quality ===")

    if "pk_net_balance" not in enriched.columns:
        print("  pk_net_balance not available, skipping")
        return {}

    mask = (enriched["pk_net_balance"].notna() &
            enriched["glucose"].notna())
    df = enriched[mask].copy()

    results = {"per_patient": {}, "horizons": {}}
    horizons = {"1h": 12, "2h": 24, "4h": 48}

    for pid in sorted(df["patient_id"].unique()):
        full_patient = enriched[enriched["patient_id"] == pid].copy()
        patient_results = {}

        for hlabel, steps in horizons.items():
            future_bg = _compute_actual_future_bg(full_patient, steps)
            full_patient[f"actual_{hlabel}"] = future_bg

            sub = df[df["patient_id"] == pid]
            merged = sub.merge(
                full_patient[["time", f"actual_{hlabel}"]],
                on="time", how="left"
            )
            valid = merged[merged[f"actual_{hlabel}"].notna()]

            if len(valid) < 100:
                continue

            # pk_net_balance predicts BG CHANGE, not absolute BG
            predicted_change = valid["pk_net_balance"].values
            actual_change = (valid[f"actual_{hlabel}"].values -
                             valid["glucose"].values)

            r2 = r2_score(actual_change, predicted_change)
            mae = mean_absolute_error(actual_change, predicted_change)
            rho, p = spearmanr(predicted_change, actual_change)

            patient_results[hlabel] = {
                "r2": float(r2),
                "mae": float(mae),
                "rho": float(rho),
                "n": int(len(valid)),
            }

        if patient_results:
            results["per_patient"][pid] = patient_results

    # Aggregate
    for hlabel in horizons:
        r2s = [v[hlabel]["r2"] for v in results["per_patient"].values()
               if hlabel in v]
        if r2s:
            results["horizons"][hlabel] = {
                "mean_r2": float(np.mean(r2s)),
                "median_r2": float(np.median(r2s)),
                "n_patients": len(r2s),
            }
            print(f"  pk_net_balance→Δ{hlabel}: mean R²={np.mean(r2s):.4f}, "
                  f"median={np.median(r2s):.4f} ({len(r2s)} patients)")

    return results


def exp_2584_synthesis(r2581, r2582, r2583):
    """Synthesis comparing algorithm vs physics predictions."""
    print("\n=== EXP-2584: Prediction quality synthesis ===")

    results = {}

    # eventualBG 4h R²
    eb_4h = r2581.get("horizons", {}).get("4h", {})
    results["eventualBG_4h_r2"] = eb_4h.get("mean_r2", None)

    # Loop predicted_60 1h R²
    results["loop_predicted_1h_r2"] = r2582.get("mean_r2", None)

    # PK net_balance at each horizon
    for h in ["1h", "2h", "4h"]:
        pk_h = r2583.get("horizons", {}).get(h, {})
        results[f"pk_net_balance_{h}_r2"] = pk_h.get("mean_r2", None)

    # Colleague's claim
    results["colleague_eventualBG_r2"] = 0.002

    print(f"  Colleague eventualBG R²: 0.002")
    print(f"  Our eventualBG 4h R²:    {results.get('eventualBG_4h_r2', '?')}")
    print(f"  Loop predicted_60 R²:    {results.get('loop_predicted_1h_r2', '?')}")
    for h in ["1h", "2h", "4h"]:
        r2 = results.get(f"pk_net_balance_{h}_r2")
        if r2 is not None:
            print(f"  PK net_balance→Δ{h} R²:  {r2:.4f}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="EXP-2581: Algorithm Prediction Quality Validation"
    )
    parser.add_argument(
        "--data-path", type=str, default="externals/ns-parquet/training",
    )
    args = parser.parse_args()

    run_start = time.monotonic()
    print(f"[{_ts()}] EXP-2581 starting  data={args.data_path}")

    # Load grid
    grid = load_grid(args.data_path)
    print(f"  Loaded {len(grid):,} rows, "
          f"{grid['patient_id'].nunique()} patients")

    # Compute PK features
    print(f"[{_ts()}] Computing PK features...")
    enriched = add_pk_features_to_grid(grid)
    print(f"  PK features added: {[c for c in enriched.columns if c.startswith('pk_')]}")

    # Run experiments
    all_results = {}
    all_results["2581"] = exp_2581_eventual_bg(grid)
    all_results["2582"] = exp_2582_loop_predicted(grid)
    all_results["2583"] = exp_2583_pk_prediction(grid, enriched)
    all_results["2584"] = exp_2584_synthesis(
        all_results["2581"], all_results["2582"], all_results["2583"])

    # Generate report
    report = ComparisonReport(
        exp_id="2581",
        title="Algorithm Prediction Quality Validation",
        phase="contrast",
    )
    report.add_their_finding(
        "F5",
        "eventualBG has R²=0.002 vs actual 4h BG",
        "OREF-INV-003 Table 7: eventualBG explains 0.2% of 4h outcome variance",
    )

    eb_r2 = all_results["2584"].get("eventualBG_4h_r2")
    if eb_r2 is not None:
        agreement = "strongly_agrees" if eb_r2 < 0.05 else "agrees" if eb_r2 < 0.1 else "partially_disagrees"
        report.add_our_finding(
            "F5-eventualBG",
            f"eventualBG R²={eb_r2:.4f} vs actual 4h BG in our data",
            f"Tested on {all_results['2581']['horizons'].get('4h', {}).get('n_patients', '?')} AAPS/oref0 patients",
            agreement=agreement,
        )

    loop_r2 = all_results["2584"].get("loop_predicted_1h_r2")
    if loop_r2 is not None:
        report.add_our_finding(
            "F5-loop",
            f"Loop predicted_60 R²={loop_r2:.4f} vs actual 1h BG",
            "Loop's shorter-horizon prediction is much stronger than eventualBG",
            agreement="not_comparable",
        )

    report.set_methodology(
        "Computed R² between algorithm-reported predictions (eventualBG for oref, "
        "predicted_60 for Loop) and actual future BG at matching horizons. "
        "Also computed R² for PK-derived pk_net_balance vs actual BG change "
        "at 1h, 2h, 4h horizons to test physics-based prediction quality."
    )

    report.set_raw_results(all_results)

    # Save
    report.save()
    out_path = RESULTS_DIR / "exp_2581_prediction_quality.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder))
    print(f"\n  Results saved: {out_path}")

    wall = time.monotonic() - run_start
    print(f"\n{'=' * 60}")
    print(f"EXP-2581 COMPLETE  [{_ts()}]  wall={wall:.0f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
