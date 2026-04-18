#!/usr/bin/env python3
"""EXP-2617: Suspension-Window Natural Experiments for Deconfounded Calibration.

INSIGHT: Loop suspends basal 47-69% of the time. During suspension, insulin
delivery is KNOWN (zero basal, only IOB decay). These windows are natural
experiments where we can estimate physiology parameters without loop confound.

Compare ISF/k calibrated from:
  A) All correction windows (current, loop-confounded)
  B) Suspension-only corrections (loop rate=0 during window)
  C) Non-suspension corrections (loop actively adjusting)

H1: Suspension-window ISF is closer to 1.0× than all-window ISF
    (less distortion from loop insulin accounting).
H2: counter_reg_k calibrated from suspension windows is LOWER than
    from all windows (k from all windows absorbs loop compensation).
H3: Suspension-window calibration produces better MAE on held-out
    suspension windows (≥10% improvement in cross-validation).

Also: Characterize suspension windows as a function of glucose level
and time of day to understand WHEN natural experiments occur.
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2617_suspension_natural.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
WINDOW_STEPS = 24  # 2h
ISF_GRID = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 2.5, 3.0]
K_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0]


def _classify_window(window_df):
    """Classify correction window by loop activity during window."""
    loop_rates = window_df["loop_enacted_rate"].values
    sched_rates = window_df["scheduled_basal_rate"].values

    valid_lr = ~np.isnan(loop_rates)
    if valid_lr.sum() < WINDOW_STEPS * 0.3:
        return "unknown"

    lr_valid = loop_rates[valid_lr]
    # Suspension: loop rate = 0 for ≥80% of window
    zero_frac = (lr_valid == 0).mean()
    if zero_frac >= 0.8:
        return "suspended"

    # Active: loop significantly different from schedule
    sr_valid = sched_rates[valid_lr]
    diff_frac = (np.abs(lr_valid - sr_valid) / np.maximum(sr_valid, 0.01) > 0.3).mean()
    if diff_frac >= 0.5:
        return "active"

    return "passive"  # loop making small adjustments


def _extract_classified_windows(pdf, max_per_class=30):
    """Extract correction windows classified by loop activity."""
    windows = {"suspended": [], "active": [], "passive": [], "unknown": []}

    bolus_mask = (pdf["bolus"] >= 0.5)
    for idx in pdf.index[bolus_mask]:
        pos = pdf.index.get_loc(idx)
        if pos + WINDOW_STEPS >= len(pdf):
            continue

        row = pdf.iloc[pos]
        pre_g = row["glucose"]
        if np.isnan(pre_g) or pre_g < 120:
            continue

        window = pdf.iloc[pos:pos + WINDOW_STEPS]

        if window["carbs"].sum() > 2:
            continue

        g_vals = window["glucose"].values
        valid = ~np.isnan(g_vals)
        if valid.sum() < WINDOW_STEPS * 0.5:
            continue

        end_g = g_vals[valid][-1]
        actual_drop = end_g - pre_g

        classification = _classify_window(window)
        if len(windows[classification]) >= max_per_class:
            continue

        # Actual insulin delivered during window
        actual_ins = np.nansum(window["actual_basal_rate"].values) * (5.0/60.0) + \
                     np.nansum(window["bolus_smb"].values)
        sched_ins = float(row["scheduled_basal_rate"]) * WINDOW_STEPS * (5.0/60.0)

        windows[classification].append({
            "pre_g": float(pre_g),
            "end_g": float(end_g),
            "actual_drop": float(actual_drop),
            "bolus": float(row["bolus"]),
            "isf": float(row["scheduled_isf"]),
            "cr": float(row["scheduled_cr"]),
            "basal": float(row["scheduled_basal_rate"]),
            "iob": float(row["iob"]) if not np.isnan(row["iob"]) else 0,
            "hour": int(row["time"].hour),
            "actual_insulin": float(actual_ins),
            "sched_insulin": float(sched_ins),
            "classification": classification,
        })

    return windows


def _calibrate_isf_k(windows, fixed_k=None):
    """Calibrate ISF (and optionally k) from windows."""
    if not windows:
        return None, None, float("inf")

    best_isf = 1.0
    best_k = 0.0
    best_mae = float("inf")

    k_values = [fixed_k] if fixed_k is not None else K_GRID

    for k in k_values:
        for isf_mult in ISF_GRID:
            errors = []
            for w in windows:
                settings = TherapySettings(
                    basal_rate=w["basal"],
                    isf=w["isf"] * isf_mult,
                    cr=w["cr"],
                )
                bolus_events = [InsulinEvent(time_minutes=0, units=w["bolus"])]
                result = forward_simulate(
                    initial_glucose=w["pre_g"],
                    settings=settings,
                    bolus_events=bolus_events,
                    carb_events=[],
                    duration_hours=2.0,
                    counter_reg_k=k,
                )
                sim_end = result.glucose[-1] if len(result.glucose) > 0 else w["pre_g"]
                sim_drop = sim_end - w["pre_g"]
                errors.append(abs(sim_drop - w["actual_drop"]))

            mae = np.mean(errors)
            if mae < best_mae:
                best_mae = mae
                best_isf = isf_mult
                best_k = k

    return best_isf, best_k, best_mae


def main():
    print("=" * 70)
    print("EXP-2617: Suspension-Window Natural Experiments")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}
    isf_susp_all = []
    isf_all_all = []
    k_susp_all = []
    k_all_all = []

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            continue

        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        classified = _extract_classified_windows(pdf)
        for cls, wins in classified.items():
            print(f"  {cls:>10s}: {len(wins)} windows")

        susp_wins = classified["suspended"]
        active_wins = classified["active"]
        all_wins = susp_wins + active_wins + classified["passive"]

        if len(susp_wins) < 5 or len(all_wins) < 10:
            print(f"  Insufficient windows, skipping")
            continue

        # Characterize suspension windows
        susp_hours = [w["hour"] for w in susp_wins]
        susp_glucose = [w["pre_g"] for w in susp_wins]
        print(f"  Suspension windows: mean glucose={np.mean(susp_glucose):.0f}, "
              f"night%={sum(1 for h in susp_hours if h < 6 or h >= 22)/len(susp_hours)*100:.0f}%")

        # Calibrate from ALL windows (joint ISF+k)
        isf_all, k_all, mae_all = _calibrate_isf_k(all_wins)
        print(f"  ALL:  ISF×{isf_all}, k={k_all}, MAE={mae_all:.1f}")

        # Calibrate from SUSPENSION windows only
        isf_susp, k_susp, mae_susp = _calibrate_isf_k(susp_wins)
        print(f"  SUSP: ISF×{isf_susp}, k={k_susp}, MAE={mae_susp:.1f}")

        # Calibrate from ACTIVE windows only
        if len(active_wins) >= 5:
            isf_active, k_active, mae_active = _calibrate_isf_k(active_wins)
            print(f"  ACT:  ISF×{isf_active}, k={k_active}, MAE={mae_active:.1f}")
        else:
            isf_active, k_active, mae_active = None, None, None

        # Cross-validation: calibrate on suspension, test on held-out suspension
        if len(susp_wins) >= 10:
            mid = len(susp_wins) // 2
            train = susp_wins[:mid]
            test = susp_wins[mid:]
            isf_cv, k_cv, _ = _calibrate_isf_k(train)
            # Evaluate on test
            errors_cv = []
            for w in test:
                settings = TherapySettings(basal_rate=w["basal"], isf=w["isf"] * isf_cv, cr=w["cr"])
                result = forward_simulate(
                    initial_glucose=w["pre_g"], settings=settings,
                    bolus_events=[InsulinEvent(time_minutes=0, units=w["bolus"])],
                    carb_events=[], duration_hours=2.0, counter_reg_k=k_cv,
                )
                sim_end = result.glucose[-1] if len(result.glucose) > 0 else w["pre_g"]
                errors_cv.append(abs((sim_end - w["pre_g"]) - w["actual_drop"]))
            mae_cv_susp = np.mean(errors_cv)

            # Compare: calibrate on ALL, test on same test set
            isf_cv2, k_cv2, _ = _calibrate_isf_k(all_wins[:len(train)])
            errors_cv2 = []
            for w in test:
                settings = TherapySettings(basal_rate=w["basal"], isf=w["isf"] * isf_cv2, cr=w["cr"])
                result = forward_simulate(
                    initial_glucose=w["pre_g"], settings=settings,
                    bolus_events=[InsulinEvent(time_minutes=0, units=w["bolus"])],
                    carb_events=[], duration_hours=2.0, counter_reg_k=k_cv2,
                )
                sim_end = result.glucose[-1] if len(result.glucose) > 0 else w["pre_g"]
                errors_cv2.append(abs((sim_end - w["pre_g"]) - w["actual_drop"]))
            mae_cv_all = np.mean(errors_cv2)

            cv_improvement = (mae_cv_all - mae_cv_susp) / mae_cv_all * 100 if mae_cv_all > 0 else 0
            print(f"  CV: susp-trained MAE={mae_cv_susp:.1f}, all-trained MAE={mae_cv_all:.1f}, "
                  f"improvement={cv_improvement:+.1f}%")
        else:
            mae_cv_susp = mae_cv_all = cv_improvement = None

        isf_susp_all.append(isf_susp)
        isf_all_all.append(isf_all)
        k_susp_all.append(k_susp)
        k_all_all.append(k_all)

        results[pid] = {
            "n_suspended": len(susp_wins),
            "n_active": len(active_wins),
            "n_all": len(all_wins),
            "all": {"isf": isf_all, "k": k_all, "mae": round(mae_all, 1)},
            "suspended": {"isf": isf_susp, "k": k_susp, "mae": round(mae_susp, 1)},
            "active": {"isf": isf_active, "k": k_active,
                       "mae": round(mae_active, 1) if mae_active else None},
            "cv_improvement_pct": round(cv_improvement, 1) if cv_improvement is not None else None,
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT ANALYSIS")
    print("=" * 70)

    # H1: Suspension ISF closer to 1.0
    dist_susp = np.mean([abs(x - 1.0) for x in isf_susp_all])
    dist_all = np.mean([abs(x - 1.0) for x in isf_all_all])
    h1_confirmed = dist_susp < dist_all
    print(f"\nH1 - ISF closer to 1.0:")
    print(f"  Suspension ISFs: {isf_susp_all}")
    print(f"  All-window ISFs: {isf_all_all}")
    print(f"  Mean dist: susp={dist_susp:.2f}, all={dist_all:.2f}")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # H2: k lower from suspension windows
    k_susp_mean = np.mean(k_susp_all)
    k_all_mean = np.mean(k_all_all)
    h2_confirmed = k_susp_mean < k_all_mean
    print(f"\nH2 - k lower from suspension:")
    print(f"  Suspension ks: {k_susp_all}")
    print(f"  All-window ks: {k_all_all}")
    print(f"  Mean k: susp={k_susp_mean:.1f}, all={k_all_mean:.1f}")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: CV improvement ≥10%
    cv_improvements = [r["cv_improvement_pct"] for r in results.values()
                       if r["cv_improvement_pct"] is not None]
    h3_count = sum(1 for x in cv_improvements if x >= 10)
    h3_confirmed = h3_count >= len(cv_improvements) * 0.5 if cv_improvements else False
    print(f"\nH3 - CV improvement ≥10%:")
    print(f"  Improvements: {cv_improvements}")
    print(f"  {h3_count}/{len(cv_improvements)} meet threshold")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # Summary table
    print(f"\n{'Pt':>5s}  {'nSusp':>5s}  {'nAll':>4s}  {'ISF_S':>6s}  {'ISF_A':>6s}  {'k_S':>4s}  {'k_A':>4s}  {'MAE_S':>6s}  {'MAE_A':>6s}  {'CV%':>5s}")
    print("-" * 72)
    for pid, r in sorted(results.items()):
        print(f"{pid:>5s}  {r['n_suspended']:>5d}  {r['n_all']:>4d}  "
              f"{r['suspended']['isf']:>6.1f}  {r['all']['isf']:>6.1f}  "
              f"{r['suspended']['k']:>4.1f}  {r['all']['k']:>4.1f}  "
              f"{r['suspended']['mae']:>6.1f}  {r['all']['mae']:>6.1f}  "
              f"{r['cv_improvement_pct']:>+4.1f}%" if r['cv_improvement_pct'] is not None else "  N/A")

    output = {
        "experiment": "EXP-2617",
        "title": "Suspension-Window Natural Experiments",
        "patients": results,
        "hypotheses": {
            "H1": {"dist_susp": round(dist_susp, 3), "dist_all": round(dist_all, 3),
                    "confirmed": h1_confirmed},
            "H2": {"k_susp_mean": round(k_susp_mean, 2), "k_all_mean": round(k_all_mean, 2),
                    "confirmed": h2_confirmed},
            "H3": {"improvements": cv_improvements, "confirmed": h3_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
