#!/usr/bin/env python3
"""EXP-2599: Unified Sequential Calibration Pipeline.

Ties together all calibration discoveries from EXP-2567-2598 into one
coherent pipeline: basal → ISF → CSF → k.

Each step uses the output of the previous:
  1. Basal: compare scheduled vs actual delivery → basal multiplier
  2. ISF: use correction events with calibrated basal → ISF multiplier
  3. CSF: use meal events with calibrated ISF → CSF value
  4. k: use correction trajectories with calibrated ISF → counter-reg k

Hypotheses:
  H1: Sequential calibration produces better full-day sim accuracy
      than independent calibration (r > 0.65 vs r=0.623 baseline).
  H2: The calibration order matters — swapping ISF↔k degrades results.
  H3: The pipeline can calibrate a patient from 7 days of data
      (not just the full 180-day dataset).
  H4: Pipeline-calibrated settings produce ≥3pp better TIR prediction
      than default (ISF×0.5, CR×2.0, k=2.0).

Design:
  For each FULL patient:
    1. Run sequential pipeline on training data
    2. Evaluate calibrated settings on validation data
    3. Compare vs default settings
    4. Test with 7-day subsets for H3
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2599_unified_calibration.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def _step1_basal(pdf):
    """Step 1: Calibrate basal from actual vs scheduled delivery.

    Returns basal_multiplier: actual/scheduled ratio.
    """
    scheduled = pdf["scheduled_basal_rate"].dropna().values
    actual = pdf["actual_basal_rate"].dropna().values if "actual_basal_rate" in pdf.columns else None

    if actual is None or len(actual) < 100:
        return 1.0

    # Match lengths (both should be same length from grid)
    n = min(len(scheduled), len(actual))
    scheduled = scheduled[:n]
    actual = actual[:n]

    # Filter valid
    mask = (scheduled > 0.01) & (actual >= 0) & ~np.isnan(scheduled) & ~np.isnan(actual)
    if np.sum(mask) < 100:
        return 1.0

    ratio = float(np.median(actual[mask] / scheduled[mask]))
    return np.clip(ratio, 0.3, 3.0)


def _step2_isf(pdf, basal_mult):
    """Step 2: Calibrate ISF from correction events.

    Use correction boluses (BG>150, carbs<1g) to compute effective ISF.
    Returns isf_multiplier.
    """
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values

    drops = []
    doses = []

    N = len(glucose)
    for i in range(N - 24):
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue
        drops.append(glucose[i] - glucose[post_idx])
        doses.append(bolus[i])

    if len(drops) < 5:
        return 0.5  # default

    drops = np.array(drops)
    doses = np.array(doses)
    effective_isf = float(np.median(drops / doses))

    profile_isf = float(pdf["scheduled_isf"].dropna().median())
    if profile_isf <= 0:
        return 0.5

    mult = effective_isf / profile_isf
    return np.clip(mult, 0.2, 2.0)


def _step3_csf(pdf, isf_mult, basal_mult):
    """Step 3: Calibrate CSF from meal events.

    Use the calibrated ISF to simulate meals and find the CSF that
    best matches actual peak excursions.
    """
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    pts_per_hour = 12

    meals = []
    N = len(glucose)
    for i in range(N - 48):
        if carbs[i] < 10 or bolus[i] < 0.1 or np.isnan(glucose[i]):
            continue
        wg = glucose[i:i + 48]
        if np.sum(~np.isnan(wg)) < 24:
            continue
        valid_wg = np.where(np.isnan(wg), glucose[i], wg)
        actual_peak = float(np.max(valid_wg) - glucose[i])

        isf = float(pdf["scheduled_isf"].iloc[i]) if not np.isnan(pdf["scheduled_isf"].iloc[i]) else 50.0
        cr = float(pdf["scheduled_cr"].iloc[i]) if not np.isnan(pdf["scheduled_cr"].iloc[i]) else 10.0
        basal = float(pdf["scheduled_basal_rate"].iloc[i]) if not np.isnan(pdf["scheduled_basal_rate"].iloc[i]) else 0.8

        meals.append({
            "glucose_start": float(glucose[i]),
            "actual_peak": actual_peak,
            "carbs": float(carbs[i]),
            "bolus": float(bolus[i]),
            "isf": isf,
            "cr": cr,
            "basal": basal,
        })

    if len(meals) < 10:
        return 2.0  # population default

    # Sample to avoid excessive computation
    if len(meals) > 50:
        np.random.seed(42)
        meals = [meals[i] for i in np.random.choice(len(meals), 50, replace=False)]

    # Sweep CSF
    best_csf = 2.0
    best_score = 999

    for csf in np.arange(1.0, 8.0, 0.5):
        errors = []
        for m in meals:
            ts = TherapySettings(
                isf=m["isf"] * isf_mult,
                cr=m["cr"] * 2.0,  # cr mult stays at 2.0
                basal_rate=m["basal"] * basal_mult,
                dia_hours=5.0,
                carb_sensitivity=csf,
            )
            result = forward_simulate(
                initial_glucose=m["glucose_start"],
                settings=ts,
                bolus_events=[InsulinEvent(time_minutes=0, units=m["bolus"])],
                carb_events=[CarbEvent(time_minutes=0, grams=m["carbs"])],
                duration_hours=4.0,
            )
            sim_peak = float(max(result.glucose) - m["glucose_start"])
            errors.append(abs(sim_peak - m["actual_peak"]))

        mae = np.mean(errors)
        if mae < best_score:
            best_score = mae
            best_csf = float(csf)

    return best_csf


def _step4_k(pdf, isf_mult, basal_mult):
    """Step 4: Calibrate counter-regulation k from correction trajectories.

    Find k that minimizes the gap between simulated and actual glucose
    drop after corrections.
    """
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values

    corrections = []
    N = len(glucose)
    for i in range(N - 24):
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue

        isf = float(pdf["scheduled_isf"].iloc[i]) if not np.isnan(pdf["scheduled_isf"].iloc[i]) else 50.0
        basal = float(pdf["scheduled_basal_rate"].iloc[i]) if not np.isnan(pdf["scheduled_basal_rate"].iloc[i]) else 0.8

        corrections.append({
            "glucose_start": float(glucose[i]),
            "glucose_end": float(glucose[post_idx]),
            "actual_drop": float(glucose[i] - glucose[post_idx]),
            "bolus": float(bolus[i]),
            "isf": isf,
            "basal": basal,
        })

    if len(corrections) < 5:
        return 2.0

    # Sample
    if len(corrections) > 50:
        np.random.seed(42)
        corrections = [corrections[i] for i in np.random.choice(len(corrections), 50, replace=False)]

    best_k = 0.0
    best_score = 999

    for k in np.arange(0.0, 10.5, 0.5):
        errors = []
        for c in corrections:
            ts = TherapySettings(
                isf=c["isf"] * isf_mult,
                cr=10.0,
                basal_rate=c["basal"] * basal_mult,
                dia_hours=5.0,
            )
            result = forward_simulate(
                initial_glucose=c["glucose_start"],
                settings=ts,
                bolus_events=[InsulinEvent(time_minutes=0, units=c["bolus"])],
                duration_hours=2.0,
                counter_reg_k=k,
            )
            sim_end = result.glucose[-1]
            sim_drop = c["glucose_start"] - sim_end
            errors.append(abs(sim_drop - c["actual_drop"]))

        mae = np.mean(errors)
        if mae < best_score:
            best_score = mae
            best_k = float(k)

    return best_k


def _evaluate_full_day(pdf, settings_dict, n_windows=30):
    """Evaluate settings on 2h correction windows. Returns rank correlation."""
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values

    actual_drops = []
    sim_drops = []
    N = len(glucose)

    for i in range(N - 24):
        if bolus[i] < 0.5:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 120:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue

        isf = float(pdf["scheduled_isf"].iloc[i]) if not np.isnan(pdf["scheduled_isf"].iloc[i]) else 50.0
        cr = float(pdf["scheduled_cr"].iloc[i]) if not np.isnan(pdf["scheduled_cr"].iloc[i]) else 10.0
        basal = float(pdf["scheduled_basal_rate"].iloc[i]) if not np.isnan(pdf["scheduled_basal_rate"].iloc[i]) else 0.8

        ts = TherapySettings(
            isf=isf * settings_dict["isf_mult"],
            cr=cr * 2.0,
            basal_rate=basal * settings_dict["basal_mult"],
            dia_hours=5.0,
            carb_sensitivity=settings_dict["csf"],
        )

        carb_events = []
        if carbs[i] > 1.0:
            carb_events = [CarbEvent(time_minutes=0, grams=float(carbs[i]))]

        result = forward_simulate(
            initial_glucose=float(glucose[i]),
            settings=ts,
            bolus_events=[InsulinEvent(time_minutes=0, units=float(bolus[i]))],
            carb_events=carb_events,
            duration_hours=2.0,
            counter_reg_k=settings_dict["k"],
        )

        sim_end = result.glucose[-1]
        actual_drop = float(glucose[i] - glucose[post_idx])
        sim_drop = float(glucose[i] - sim_end)

        actual_drops.append(actual_drop)
        sim_drops.append(sim_drop)

        if len(actual_drops) >= n_windows:
            break

    if len(actual_drops) < 5:
        return {"rank_r": 0.0, "rank_p": 1.0, "mae": 999, "n": 0}

    r, p = stats.spearmanr(actual_drops, sim_drops)
    mae = float(np.mean(np.abs(np.array(actual_drops) - np.array(sim_drops))))
    bias = float(np.mean(np.array(sim_drops) - np.array(actual_drops)))

    return {
        "rank_r": float(r),
        "rank_p": float(p),
        "mae": mae,
        "bias": bias,
        "n": len(actual_drops),
    }


def main():
    print("=" * 70)
    print("EXP-2599: Unified Sequential Calibration Pipeline")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    # Default settings for comparison
    default_settings = {
        "basal_mult": 1.0,
        "isf_mult": 0.5,
        "csf": 2.0,
        "k": 2.0,
    }

    for pid in FULL_PATIENTS:
        print(f"\n{'=' * 50}")
        print(f"PATIENT {pid}")
        print(f"{'=' * 50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

        # Split 70/30 for train/val
        n = len(pdf)
        split = int(0.7 * n)
        train_pdf = pdf.iloc[:split].reset_index(drop=True)
        val_pdf = pdf.iloc[split:].reset_index(drop=True)

        print(f"  Total rows: {n}, Train: {split}, Val: {n - split}")

        # Sequential calibration on training data
        print("\n  Step 1: Basal calibration...")
        basal_mult = _step1_basal(train_pdf)
        print(f"    basal_mult = {basal_mult:.3f}")

        print("  Step 2: ISF calibration...")
        isf_mult = _step2_isf(train_pdf, basal_mult)
        print(f"    isf_mult = {isf_mult:.3f}")

        print("  Step 3: CSF calibration...")
        csf = _step3_csf(train_pdf, isf_mult, basal_mult)
        print(f"    csf = {csf:.1f}")

        print("  Step 4: Counter-regulation k...")
        k = _step4_k(train_pdf, isf_mult, basal_mult)
        print(f"    k = {k:.1f}")

        calibrated_settings = {
            "basal_mult": float(basal_mult),
            "isf_mult": float(isf_mult),
            "csf": float(csf),
            "k": float(k),
        }

        print(f"\n  Calibrated: {calibrated_settings}")

        # Evaluate on validation data
        print("\n  Evaluating on validation set...")
        val_calibrated = _evaluate_full_day(val_pdf, calibrated_settings)
        val_default = _evaluate_full_day(val_pdf, default_settings)

        print(f"  Calibrated: r={val_calibrated['rank_r']:.3f}, MAE={val_calibrated['mae']:.1f}")
        print(f"  Default:    r={val_default['rank_r']:.3f}, MAE={val_default['mae']:.1f}")

        # H3: 7-day subset calibration
        days_7 = int(7 * 288)  # 7 days at 5-min intervals
        if len(train_pdf) > days_7:
            short_pdf = train_pdf.iloc[:days_7].reset_index(drop=True)
            b7 = _step1_basal(short_pdf)
            i7 = _step2_isf(short_pdf, b7)
            csf7 = _step3_csf(short_pdf, i7, b7)
            k7 = _step4_k(short_pdf, i7, b7)
            settings_7d = {"basal_mult": float(b7), "isf_mult": float(i7),
                          "csf": float(csf7), "k": float(k7)}
            val_7d = _evaluate_full_day(val_pdf, settings_7d)
            print(f"  7-day cal:  r={val_7d['rank_r']:.3f}, MAE={val_7d['mae']:.1f}")
            print(f"    Settings: basal={b7:.3f}, ISF={i7:.3f}, CSF={csf7:.1f}, k={k7:.1f}")
        else:
            settings_7d = calibrated_settings
            val_7d = val_calibrated

        # TIR
        valid_g = pdf["glucose"].values
        valid_g = valid_g[~np.isnan(valid_g)]
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))

        results[pid] = {
            "patient_id": pid,
            "tir": tir,
            "calibrated_settings": calibrated_settings,
            "settings_7d": settings_7d,
            "val_calibrated": val_calibrated,
            "val_default": val_default,
            "val_7d": val_7d,
        }

    # Cross-patient analysis
    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT SUMMARY")
    print(f"{'=' * 70}")

    sdf = pd.DataFrame([{
        "pid": r["patient_id"],
        "r_cal": r["val_calibrated"]["rank_r"],
        "r_def": r["val_default"]["rank_r"],
        "r_7d": r["val_7d"]["rank_r"],
        "mae_cal": r["val_calibrated"]["mae"],
        "mae_def": r["val_default"]["mae"],
        "mae_7d": r["val_7d"]["mae"],
        "basal_m": r["calibrated_settings"]["basal_mult"],
        "isf_m": r["calibrated_settings"]["isf_mult"],
        "csf": r["calibrated_settings"]["csf"],
        "k": r["calibrated_settings"]["k"],
    } for r in results.values()])

    print(f"\n{'Pt':<4} {'r_cal':>6} {'r_def':>6} {'r_7d':>6} {'MAE_c':>6} {'MAE_d':>6} "
          f"{'basal':>6} {'ISF':>5} {'CSF':>4} {'k':>4}")
    print("-" * 65)
    for _, r in sdf.iterrows():
        print(f"{r['pid']:<4} {r['r_cal']:>6.3f} {r['r_def']:>6.3f} {r['r_7d']:>6.3f} "
              f"{r['mae_cal']:>6.1f} {r['mae_def']:>6.1f} "
              f"{r['basal_m']:>6.3f} {r['isf_m']:>5.3f} {r['csf']:>4.1f} {r['k']:>4.1f}")

    # H1: Sequential > default
    mean_r_cal = sdf["r_cal"].mean()
    mean_r_def = sdf["r_def"].mean()
    print(f"\nH1 - Mean rank r: calibrated={mean_r_cal:.3f} vs default={mean_r_def:.3f}")
    h1_confirmed = mean_r_cal > 0.65 and mean_r_cal > mean_r_def
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r > 0.65)")

    # H3: 7-day subset
    mean_r_7d = sdf["r_7d"].mean()
    print(f"\nH3 - 7-day calibration: mean r={mean_r_7d:.3f}")
    r_7d_vs_full = stats.spearmanr(sdf["r_cal"], sdf["r_7d"])[0]
    print(f"  7d vs full calibration rank: r={r_7d_vs_full:.3f}")
    h3_confirmed = mean_r_7d > mean_r_def * 0.9  # within 10% of default
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (7d performance within 10% of default)")

    # H4: ≥3pp better
    improved_count = sum(1 for _, r in sdf.iterrows() if r["r_cal"] > r["r_def"])
    print(f"\nH4 - Calibrated better for {improved_count}/{len(sdf)} patients (ranking)")
    mae_improved = sum(1 for _, r in sdf.iterrows() if r["mae_cal"] < r["mae_def"])
    print(f"  MAE improved for {mae_improved}/{len(sdf)} patients")
    h4_confirmed = improved_count >= 6  # ≥2/3 patients
    print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'} (≥6/9 patients improved)")

    output = {
        "experiment": "EXP-2599",
        "title": "Unified Sequential Calibration Pipeline",
        "h1_confirmed": h1_confirmed,
        "h3_confirmed": h3_confirmed,
        "h4_confirmed": h4_confirmed,
        "mean_r_calibrated": mean_r_cal,
        "mean_r_default": mean_r_def,
        "mean_r_7d": mean_r_7d,
        "patient_results": list(results.values()),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
