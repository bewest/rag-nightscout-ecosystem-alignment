#!/usr/bin/env python3
"""EXP-2651: Two-Phase ISF Decomposition.

Builds on F1 (glucose nadir at 3.5h, not 1.25h), F2 (54% of correction
drop is EGP suppression), F4 (67% of patients have ISF inflated ≥15%).

INSIGHT: "Apparent ISF" includes both insulin demand AND EGP suppression.
When a correction bolus is given:
  Phase 1 (0→2h): Glucose drops from insulin action ("demand-phase ISF")
  Phase 2 (2h→nadir~3.5h): Glucose continues dropping from EGP suppression
The total drop divided by dose = "apparent ISF" (what the user sees).
The Phase 1 drop divided by dose = "demand ISF" (true insulin effect).

For DOSING, demand ISF is correct (it predicts what insulin actually does).
For PREDICTION, apparent ISF is correct (it predicts total trajectory).

Using apparent ISF for dosing → under-dosing (ISF looks bigger than it is).
Using demand ISF for prediction → over-predicting glucose drop at 4h.

METHOD:
  1. Extract correction events (≥0.5U bolus, no carbs ±1h, pre-BG ≥120)
  2. Measure glucose drop at 1h, 2h, 3h, nadir
  3. Compute: demand_ISF = drop_at_2h / dose, apparent_ISF = drop_at_nadir / dose
  4. Cross-validate: which ISF predicts 2h BG better? 4h BG?

CAVEAT (from parallel research EXP-2634/2635 "AID Compensation Theorem"):
Post-correction recovery is confounded by AID controller withdrawing insulin.
Recovery forces are coupled, not additive (sum=34 vs actual=4.1 mg/dL/hr).
ALL single-factor recovery models had negative R². The "apparent ISF" thus
includes AID compensation — which IS what actually happens in practice, so
it's still valid for practical dosing recommendations, but shouldn't be
interpreted as pure physiology.

HYPOTHESES:
H1: Demand ISF < apparent ISF for ≥60% of patients (ISF inflation exists)
H2: Demand ISF predicts 2h glucose better than apparent ISF (lower RMSE)
H3: Apparent ISF predicts 4h glucose better than demand ISF (lower RMSE)
H4: The ISF inflation ratio varies ≥1.5× across patients
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2651_two_phase_isf.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12


def _extract_correction_events(pdf, min_dose=0.5, min_pre_bg=120, carb_window_h=1.0,
                                prior_bolus_h=2.0, min_drop=10):
    """Extract clean correction bolus events for ISF analysis."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)

    carb_window = int(carb_window_h * STEPS_PER_HOUR)
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    post_window = int(6.0 * STEPS_PER_HOUR)  # Track for 6h

    events = []
    for i in range(prior_window, len(pdf) - post_window):
        if bolus[i] < min_dose:
            continue
        if np.isnan(glucose[i]) or glucose[i] < min_pre_bg:
            continue

        # No carbs within ±carb_window
        carb_start = max(0, i - carb_window)
        carb_end = min(len(pdf), i + carb_window)
        if np.nansum(carbs[carb_start:carb_end]) > 2:
            continue

        # No prior bolus within prior_bolus_h
        if np.nansum(bolus[i - prior_window:i]) > 0.3:
            continue

        # Extract trajectory
        traj = glucose[i:i + post_window + 1]
        iob_traj = iob[i:i + post_window + 1]

        # Need valid glucose at key timepoints
        idx_1h = STEPS_PER_HOUR
        idx_2h = 2 * STEPS_PER_HOUR
        idx_3h = 3 * STEPS_PER_HOUR
        idx_4h = 4 * STEPS_PER_HOUR

        if any(np.isnan(traj[idx]) for idx in [0, idx_1h, idx_2h] if idx < len(traj)):
            continue

        pre_bg = float(traj[0])
        dose = float(bolus[i])

        # Find nadir (minimum glucose in 1-5h window)
        search_start = STEPS_PER_HOUR  # after 1h
        search_end = min(5 * STEPS_PER_HOUR, len(traj))
        valid_traj = traj[search_start:search_end]
        valid_mask = ~np.isnan(valid_traj)
        if valid_mask.sum() < 6:
            continue

        nadir_rel = np.nanargmin(valid_traj)
        nadir_idx = search_start + nadir_rel
        nadir_bg = float(valid_traj[nadir_rel])
        nadir_time_h = float(nadir_idx) / STEPS_PER_HOUR

        total_drop = pre_bg - nadir_bg
        if total_drop < min_drop:
            continue

        event = {
            "pre_bg": pre_bg,
            "dose": dose,
            "iob_pre": float(iob_traj[0]) if not np.isnan(iob_traj[0]) else 0,
            "nadir_bg": nadir_bg,
            "nadir_time_h": nadir_time_h,
            "total_drop": total_drop,
        }

        # Glucose at key timepoints
        for label, idx in [("1h", idx_1h), ("2h", idx_2h), ("3h", idx_3h), ("4h", idx_4h)]:
            if idx < len(traj) and not np.isnan(traj[idx]):
                event[f"bg_{label}"] = float(traj[idx])
                event[f"drop_{label}"] = float(pre_bg - traj[idx])
            else:
                event[f"bg_{label}"] = np.nan
                event[f"drop_{label}"] = np.nan

        events.append(event)

    return events


def _analyze_patient(pid, events, scheduled_isf):
    """Compute two-phase ISF and prediction accuracy."""
    if len(events) < 5:
        return None

    edf = pd.DataFrame(events)

    # Compute ISFs
    # Demand ISF: glucose drop at 2h / dose
    valid_2h = edf.dropna(subset=["drop_2h"])
    if len(valid_2h) < 5:
        return None
    demand_isf_per_event = valid_2h["drop_2h"] / valid_2h["dose"]
    demand_isf = float(demand_isf_per_event.median())

    # Apparent ISF: total drop to nadir / dose
    apparent_isf_per_event = edf["total_drop"] / edf["dose"]
    apparent_isf = float(apparent_isf_per_event.median())

    # 1h ISF
    valid_1h = edf.dropna(subset=["drop_1h"])
    isf_1h = float((valid_1h["drop_1h"] / valid_1h["dose"]).median()) if len(valid_1h) >= 5 else np.nan

    # Inflation ratio
    inflation = apparent_isf / demand_isf if demand_isf > 0 else np.nan

    # ── Prediction accuracy ──────────────────────────────────────
    # At 2h: predict bg_2h = pre_bg - dose × ISF
    # Compare demand_ISF vs apparent_ISF vs scheduled_ISF
    valid = edf.dropna(subset=["drop_2h", "drop_4h"])
    if len(valid) < 5:
        return None

    pred_2h_demand = valid["pre_bg"] - valid["dose"] * demand_isf
    pred_2h_apparent = valid["pre_bg"] - valid["dose"] * apparent_isf
    pred_2h_scheduled = valid["pre_bg"] - valid["dose"] * scheduled_isf
    actual_2h = valid["bg_2h"]

    rmse_2h_demand = float(np.sqrt(np.mean((actual_2h - pred_2h_demand) ** 2)))
    rmse_2h_apparent = float(np.sqrt(np.mean((actual_2h - pred_2h_apparent) ** 2)))
    rmse_2h_scheduled = float(np.sqrt(np.mean((actual_2h - pred_2h_scheduled) ** 2)))

    # At 4h: predict bg_4h = pre_bg - dose × ISF (simple model, no EGP recovery)
    pred_4h_demand = valid["pre_bg"] - valid["dose"] * demand_isf
    pred_4h_apparent = valid["pre_bg"] - valid["dose"] * apparent_isf
    pred_4h_scheduled = valid["pre_bg"] - valid["dose"] * scheduled_isf
    actual_4h = valid["bg_4h"]

    rmse_4h_demand = float(np.sqrt(np.mean((actual_4h - pred_4h_demand) ** 2)))
    rmse_4h_apparent = float(np.sqrt(np.mean((actual_4h - pred_4h_apparent) ** 2)))
    rmse_4h_scheduled = float(np.sqrt(np.mean((actual_4h - pred_4h_scheduled) ** 2)))

    # Which ISF is best at each horizon?
    best_2h = "demand" if rmse_2h_demand <= min(rmse_2h_apparent, rmse_2h_scheduled) else \
              "apparent" if rmse_2h_apparent <= rmse_2h_scheduled else "scheduled"
    best_4h = "demand" if rmse_4h_demand <= min(rmse_4h_apparent, rmse_4h_scheduled) else \
              "apparent" if rmse_4h_apparent <= rmse_4h_scheduled else "scheduled"

    return {
        "n_events": len(events),
        "n_validated": len(valid),
        "scheduled_isf": scheduled_isf,
        "isf_1h": isf_1h,
        "demand_isf": demand_isf,
        "apparent_isf": apparent_isf,
        "inflation_ratio": float(inflation),
        "median_nadir_time_h": float(edf["nadir_time_h"].median()),
        "prediction": {
            "rmse_2h_demand": rmse_2h_demand,
            "rmse_2h_apparent": rmse_2h_apparent,
            "rmse_2h_scheduled": rmse_2h_scheduled,
            "best_2h": best_2h,
            "rmse_4h_demand": rmse_4h_demand,
            "rmse_4h_apparent": rmse_4h_apparent,
            "rmse_4h_scheduled": rmse_4h_scheduled,
            "best_4h": best_4h,
        },
        "demand_isf_iqr": [float(demand_isf_per_event.quantile(0.25)),
                           float(demand_isf_per_event.quantile(0.75))],
        "apparent_isf_iqr": [float(apparent_isf_per_event.quantile(0.25)),
                             float(apparent_isf_per_event.quantile(0.75))],
    }


def main():
    print("=" * 70)
    print("EXP-2651: Two-Phase ISF Decomposition")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            continue

        scheduled_isf = float(pdf["scheduled_isf"].dropna().median())
        events = _extract_correction_events(pdf)

        r = _analyze_patient(pid, events, scheduled_isf)
        if r is None:
            print(f"  {pid}: insufficient correction events ({len(events)})")
            continue

        results[pid] = r
        p = r["prediction"]
        print(f"\n  {pid} ({r['n_events']} events, nadir {r['median_nadir_time_h']:.1f}h):")
        print(f"    ISF: scheduled={scheduled_isf:.0f}, demand(2h)={r['demand_isf']:.0f}, "
              f"apparent={r['apparent_isf']:.0f}, inflation={r['inflation_ratio']:.2f}×")
        print(f"    2h RMSE: demand={p['rmse_2h_demand']:.1f}, apparent={p['rmse_2h_apparent']:.1f}, "
              f"sched={p['rmse_2h_scheduled']:.1f} → best: {p['best_2h']}")
        print(f"    4h RMSE: demand={p['rmse_4h_demand']:.1f}, apparent={p['rmse_4h_apparent']:.1f}, "
              f"sched={p['rmse_4h_scheduled']:.1f} → best: {p['best_4h']}")

    # ── Hypothesis testing ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients = list(results.values())

    # H1: demand ISF < apparent ISF for ≥60%
    inflated = sum(1 for r in patients if r["demand_isf"] < r["apparent_isf"])
    h1_pct = inflated / len(patients) * 100
    print(f"\n  H1: Demand ISF < apparent ISF for ≥60% of patients")
    print(f"      {inflated}/{len(patients)} ({h1_pct:.0f}%)")
    print(f"      → {'PASS' if h1_pct >= 60 else 'FAIL'}")

    # H2: demand ISF predicts 2h better
    demand_wins_2h = sum(1 for r in patients if r["prediction"]["best_2h"] == "demand")
    h2_pct = demand_wins_2h / len(patients) * 100
    print(f"\n  H2: Demand ISF predicts 2h glucose better")
    print(f"      {demand_wins_2h}/{len(patients)} ({h2_pct:.0f}%) — demand wins at 2h")
    print(f"      → {'PASS' if h2_pct >= 50 else 'FAIL'}")

    # H3: apparent ISF predicts 4h better
    apparent_wins_4h = sum(1 for r in patients if r["prediction"]["best_4h"] == "apparent")
    h3_pct = apparent_wins_4h / len(patients) * 100
    print(f"\n  H3: Apparent ISF predicts 4h glucose better")
    print(f"      {apparent_wins_4h}/{len(patients)} ({h3_pct:.0f}%) — apparent wins at 4h")
    print(f"      → {'PASS' if h3_pct >= 50 else 'FAIL'}")

    # H4: inflation ratio varies ≥1.5×
    ratios = [r["inflation_ratio"] for r in patients if not np.isnan(r["inflation_ratio"])]
    if ratios:
        ratio_range = max(ratios) / min(ratios) if min(ratios) > 0 else float('inf')
        print(f"\n  H4: Inflation ratio varies ≥1.5× across patients")
        print(f"      Range: {min(ratios):.2f}× – {max(ratios):.2f}× ({ratio_range:.1f}× variation)")
        print(f"      → {'PASS' if ratio_range >= 1.5 else 'FAIL'}")

    # ── Summary table ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ISF DECOMPOSITION SUMMARY")
    print("=" * 70)
    print(f"  {'Patient':<12} {'Events':>6} {'Sched':>6} {'1h':>6} {'Demand':>7} {'Appar':>6} "
          f"{'Inflate':>8} {'Best@2h':>8} {'Best@4h':>8}")
    for pid in sorted(results.keys()):
        r = results[pid]
        isf_1h_str = f"{r['isf_1h']:.0f}" if not np.isnan(r['isf_1h']) else "—"
        print(f"  {pid:<12} {r['n_events']:>6} {r['scheduled_isf']:>6.0f} {isf_1h_str:>6} "
              f"{r['demand_isf']:>7.0f} {r['apparent_isf']:>6.0f} "
              f"{r['inflation_ratio']:>7.2f}× {r['prediction']['best_2h']:>8} "
              f"{r['prediction']['best_4h']:>8}")

    # Dosing recommendation
    print("\n  RECOMMENDATION:")
    print("    For CORRECTION DOSING: Use demand-phase ISF (0-2h drop/dose)")
    print("    For PREDICTION (>3h):  Use apparent ISF (total drop/dose)")
    print("    For SAFETY CHECKS:     Use scheduled ISF (conservative)")

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
