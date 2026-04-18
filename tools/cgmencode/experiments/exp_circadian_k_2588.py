#!/usr/bin/env python3
"""EXP-2588: Circadian Counter-Regulation — Does k Vary by Time of Day?

Hypotheses:
  H1: Optimal counter-reg k differs between day (06-22) and night (22-06)
      by ≥ 0.5 (dawn phenomenon → stronger counter-reg overnight)
  H2: Night corrections show systematically different actual/sim ratio
      than day corrections (counter-reg is stronger overnight)
  H3: Using time-specific k values improves correction sim accuracy
      vs single population k

Rationale:
  Dawn phenomenon involves hepatic glucose production (HGP) surge
  in early morning hours. Counter-regulation (glucagon, HGP) may be
  stronger at night when cortisol and growth hormone rise. If so,
  the forward sim needs higher k overnight.

Design:
  Split corrections into day (06:00-22:00) and night (22:00-06:00).
  Calibrate k separately for each period. Compare accuracy.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2588_circadian_counter_reg.json")

PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "h": 0.0, "i": 3.0,
    "odc-74077367": 2.5, "odc-86025410": 0.5, "odc-96254963": 2.0,
}

K_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0]
SIM_HOURS = 2.0
SIM_STEPS = int(SIM_HOURS * 12)
MIN_CORRECTIONS = 15

DAY_START = 6.0
DAY_END = 22.0


def _is_night(hour: float) -> bool:
    return hour < DAY_START or hour >= DAY_END


def _extract_corrections(pdf: pd.DataFrame) -> list:
    """Extract corrections with time-of-day labels."""
    g = pdf["glucose"].values
    b = pdf["bolus"].values
    t = pd.to_datetime(pdf["time"])
    h = (t.dt.hour + t.dt.minute / 60.0).values
    carbs = pdf["carbs"].fillna(0).values
    iob = pdf["iob"].fillna(0).values
    isf = pdf["scheduled_isf"].values
    cr = pdf["scheduled_cr"].values
    basal_col = "scheduled_basal_rate" if "scheduled_basal_rate" in pdf.columns else "scheduled_basal"
    basal = pdf[basal_col].values

    N = len(g)
    corrections = []
    for i in range(N - SIM_STEPS):
        if b[i] < 0.5 or g[i] < 150 or carbs[i] > 1.0:
            continue
        if np.isnan(g[i]) or np.isnan(isf[i]) or np.isnan(cr[i]) or np.isnan(basal[i]):
            continue
        window_g = g[i : i + SIM_STEPS]
        valid = np.sum(~np.isnan(window_g))
        if valid < SIM_STEPS * 0.6:
            continue
        actual_end = np.nanmean(window_g[-3:])
        if np.isnan(actual_end):
            continue

        corrections.append({
            "g0": float(g[i]),
            "bolus": float(b[i]),
            "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            "hour": float(h[i]),
            "isf": float(isf[i]),
            "cr": float(cr[i]),
            "basal": float(basal[i]),
            "actual_drop": float(actual_end - g[i]),
            "is_night": _is_night(float(h[i])),
        })
    return corrections


def _calibrate_k(corrections: list, k_grid: list) -> dict:
    """Calibrate k for a set of corrections, return best k and stats."""
    if len(corrections) < MIN_CORRECTIONS:
        return {"k": None, "n": len(corrections), "status": "insufficient"}

    best_k = 1.5
    best_dist = float("inf")
    k_results = []

    for k in k_grid:
        ratios = []
        errors = []
        for c in corrections:
            try:
                s = TherapySettings(
                    isf=c["isf"], cr=c["cr"],
                    basal_rate=c["basal"], dia_hours=5.0,
                )
                r = forward_simulate(
                    initial_glucose=c["g0"], settings=s,
                    duration_hours=SIM_HOURS, start_hour=c["hour"],
                    bolus_events=[InsulinEvent(0, c["bolus"])],
                    carb_events=[], initial_iob=c["iob"],
                    noise_std=0, seed=42, counter_reg_k=k,
                )
                sim_drop = r.glucose[-1] - c["g0"]
                if abs(sim_drop) > 1.0:
                    ratios.append(c["actual_drop"] / sim_drop)
                    errors.append(abs(c["actual_drop"] - sim_drop))
            except Exception:
                pass

        if len(ratios) >= 10:
            ratio = float(np.mean(ratios))
            mae = float(np.mean(errors))
            dist = abs(ratio - 1.0)
            k_results.append({"k": k, "ratio": round(ratio, 3), "mae": round(mae, 1)})
            if dist < best_dist:
                best_dist = dist
                best_k = k

    return {
        "k": best_k,
        "n": len(corrections),
        "k_sweep": k_results,
        "best_ratio": round(1.0 - best_dist, 3) if best_dist < float("inf") else None,
    }


def run():
    df = pd.read_parquet(PARQUET)
    results = {"experiment": "EXP-2588", "patients": {}}

    day_ks = []
    night_ks = []
    all_ks = []

    for pid in sorted(PATIENT_K.keys()):
        pdf = df[df["patient_id"] == pid].sort_values("time")
        if len(pdf) == 0:
            continue

        corrections = _extract_corrections(pdf)
        day_corr = [c for c in corrections if not c["is_night"]]
        night_corr = [c for c in corrections if c["is_night"]]

        print(f"\n{'='*60}")
        print(f"Patient {pid}: {len(corrections)} total, {len(day_corr)} day, {len(night_corr)} night")

        all_cal = _calibrate_k(corrections, K_GRID)
        day_cal = _calibrate_k(day_corr, K_GRID)
        night_cal = _calibrate_k(night_corr, K_GRID)

        print(f"  All:   k={all_cal['k']}")
        print(f"  Day:   k={day_cal['k']} ({len(day_corr)} corrections)")
        print(f"  Night: k={night_cal['k']} ({len(night_corr)} corrections)")

        if day_cal["k"] is not None and night_cal["k"] is not None:
            diff = night_cal["k"] - day_cal["k"]
            print(f"  Δk (night - day) = {diff:+.1f}")
            day_ks.append(day_cal["k"])
            night_ks.append(night_cal["k"])
            all_ks.append(all_cal["k"])

        results["patients"][pid] = {
            "n_total": len(corrections),
            "n_day": len(day_corr),
            "n_night": len(night_corr),
            "k_all": all_cal["k"],
            "k_day": day_cal["k"],
            "k_night": night_cal["k"],
        }

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    if day_ks:
        print(f"  Day k:   mean={np.mean(day_ks):.1f}, median={np.median(day_ks):.1f}")
        print(f"  Night k: mean={np.mean(night_ks):.1f}, median={np.median(night_ks):.1f}")
        diffs = [n - d for n, d in zip(night_ks, day_ks)]
        print(f"  Δk (night-day): mean={np.mean(diffs):+.1f}, median={np.median(diffs):+.1f}")
        n_night_higher = sum(1 for d in diffs if d > 0.5)
        n_day_higher = sum(1 for d in diffs if d < -0.5)
        n_similar = sum(1 for d in diffs if abs(d) <= 0.5)
        print(f"  Night higher: {n_night_higher}, Day higher: {n_day_higher}, Similar: {n_similar}")

        results["summary"] = {
            "mean_day_k": round(float(np.mean(day_ks)), 1),
            "mean_night_k": round(float(np.mean(night_ks)), 1),
            "mean_delta": round(float(np.mean(diffs)), 1),
            "night_higher": n_night_higher,
            "day_higher": n_day_higher,
            "similar": n_similar,
        }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    run()
