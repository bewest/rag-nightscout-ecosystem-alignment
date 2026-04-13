#!/usr/bin/env python3
"""EXP-2621: Residual Event Census & EGP-Band Spectral Decomposition.

MOTIVATION: The meal detector (EXP-748) reports 46.5% of detected glucose
rises as "unannounced meals." Most people eat 2-6 meals/day. If we see
3.7 events/day with 56% unannounced (patient a), the excess are likely
EGP fluctuations or insulin imbalance, not eating.

The residual signal captures ALL unexplained glucose changes:
  residual = actual_dBG - (supply - demand + decay)
This mixes real meals (3-8h absorption) with EGP fluctuations (10-72h
timescale) and sensor noise. Spectral decomposition should separate them.

APPROACH:
1. Run meal detection per patient, census events by time-of-day block
2. Flag physiologically implausible events (overnight 00-06, >6/day)
3. FFT of residual signal → partition power into frequency bands:
   - Ultra-low (<0.042 cph, >24h): multi-day metabolic drift
   - Low (0.042-0.125 cph, 8-24h): circadian EGP
   - Meal (0.125-0.33 cph, 3-8h): true meal absorption
   - High (>0.33 cph, <3h): corrections, sensor noise
4. Per-patient: what fraction of residual variance is EGP-band vs meal-band?

HYPOTHESES:
H1: ≥40% of overnight (00-06) "meal" events have <5g estimated carbs,
    indicating they are EGP fluctuations, not real meals.
H2: Spectral power in EGP-band (>8h periods, <0.125 cph) exceeds 20% of
    total residual variance for ≥6/9 patients.
H3: Patients with highest unannounced fraction (i: 84%, k: 88%) have
    significantly more EGP-band power than low-unannounced patients,
    measured by rank correlation r ≥ 0.5.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.meal_detector import detect_meal_events
from cgmencode.production.types import PatientData, PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2621_residual_census.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

TIME_BLOCKS = {
    "overnight":   (0, 6),
    "breakfast":   (6, 10),
    "midday":      (10, 14),
    "afternoon":   (14, 17),
    "dinner":      (17, 21),
    "evening":     (21, 24),
}

# Spectral band boundaries (cycles per hour)
BANDS = {
    "ultra_low":  (0.0, 1.0 / 24.0),     # >24h periods
    "egp_low":    (1.0 / 24.0, 1.0 / 8.0),  # 8-24h periods (circadian EGP)
    "meal":       (1.0 / 8.0, 1.0 / 3.0),    # 3-8h periods (meal absorption)
    "high_freq":  (1.0 / 3.0, 6.0),           # <3h (corrections, noise)
}

STEPS_PER_HOUR = 12  # 5-min resolution


def _build_profile(pdf: pd.DataFrame) -> PatientProfile:
    """Build PatientProfile from parquet columns (matches EXP-2604 pattern)."""
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def _build_patient(pdf: pd.DataFrame, pid: str) -> PatientData:
    """Build PatientData from a patient's parquet slice."""
    pdf = pdf.sort_values("time").copy()
    # datetime64[ms, UTC] → int64 gives ms since epoch directly
    t_ms = pd.to_datetime(pdf["time"]).astype(np.int64)
    profile = _build_profile(pdf)

    return PatientData(
        patient_id=pid,
        glucose=pdf["glucose"].values.astype(np.float64),
        timestamps=t_ms.values,
        profile=profile,
        iob=pdf["iob"].values.astype(np.float64) if "iob" in pdf.columns else None,
        cob=pdf["cob"].values.astype(np.float64) if "cob" in pdf.columns else None,
        bolus=pdf["bolus"].values.astype(np.float64) if "bolus" in pdf.columns else None,
        carbs=pdf["carbs"].values.astype(np.float64) if "carbs" in pdf.columns else None,
        basal_rate=pdf["actual_basal_rate"].values.astype(np.float64) if "actual_basal_rate" in pdf.columns else None,
    )


def spectral_band_power(residual: np.ndarray) -> dict:
    """Compute fraction of residual variance in each frequency band.

    Uses FFT on the residual signal (5-min resolution = 12 samples/hour).
    Returns dict mapping band name to fraction of total power.
    """
    r = np.nan_to_num(residual, nan=0.0)
    N = len(r)
    if N < 288:  # need at least 1 day
        return {b: np.nan for b in BANDS}

    # Detrend
    r = r - np.mean(r)

    # FFT
    fft_vals = np.fft.rfft(r)
    power = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(N, d=1.0 / STEPS_PER_HOUR)  # cycles per hour

    total_power = np.sum(power[1:])  # exclude DC
    if total_power < 1e-10:
        return {b: 0.0 for b in BANDS}

    band_power = {}
    for band_name, (f_low, f_high) in BANDS.items():
        mask = (freqs > f_low) & (freqs <= f_high)
        band_power[band_name] = float(np.sum(power[mask]) / total_power)

    return band_power


def census_meals_by_block(meals: list, days_of_data: float) -> dict:
    """Count meals per time block, normalize to per-day rates."""
    block_counts = {b: 0 for b in TIME_BLOCKS}
    block_small = {b: 0 for b in TIME_BLOCKS}  # <5g estimated
    block_unannounced = {b: 0 for b in TIME_BLOCKS}

    for m in meals:
        hour = m.hour_of_day
        for block_name, (h_start, h_end) in TIME_BLOCKS.items():
            if h_start <= hour < h_end:
                block_counts[block_name] += 1
                if m.estimated_carbs_g < 5.0:
                    block_small[block_name] += 1
                if not m.announced:
                    block_unannounced[block_name] += 1
                break

    total = sum(block_counts.values())
    days = max(days_of_data, 1.0)

    return {
        "total_events": total,
        "events_per_day": total / days,
        "days_of_data": days,
        "per_block": {
            b: {
                "count": block_counts[b],
                "per_day": block_counts[b] / days,
                "small_pct": (block_small[b] / max(block_counts[b], 1)) * 100,
                "unannounced_pct": (block_unannounced[b] / max(block_counts[b], 1)) * 100,
            }
            for b in TIME_BLOCKS
        },
        "overnight_events": block_counts["overnight"],
        "overnight_small_pct": (block_small["overnight"] / max(block_counts["overnight"], 1)) * 100,
        "unannounced_total": sum(block_unannounced.values()),
        "unannounced_pct": (sum(block_unannounced.values()) / max(total, 1)) * 100,
    }


def main():
    print("=" * 70)
    print("EXP-2621: Residual Event Census & EGP-Band Spectral Decomposition")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288:
            print(f"  SKIP: insufficient data ({len(pdf)} rows)")
            continue

        patient = _build_patient(pdf, pid)
        metabolic = compute_metabolic_state(patient)
        # Extract hours using pandas (timezone-safe)
        times = pd.to_datetime(pdf["time"])
        hours = (times.dt.hour + times.dt.minute / 60.0).values.astype(np.float64)

        # Detect meals
        meals = detect_meal_events(
            patient.glucose, metabolic, hours,
            patient.timestamps, patient.profile,
        )
        days = len(pdf) / (288.0)  # 288 steps/day

        # Census by time block
        census = census_meals_by_block(meals, days)
        print(f"  Total events: {census['total_events']} ({census['events_per_day']:.1f}/day)")
        print(f"  Unannounced: {census['unannounced_pct']:.1f}%")
        print(f"  Overnight events: {census['overnight_events']} "
              f"({census['per_block']['overnight']['per_day']:.2f}/day)")
        ov_small = census['overnight_small_pct']
        print(f"  Overnight <5g: {ov_small:.1f}%")

        # Spectral decomposition
        band_power = spectral_band_power(metabolic.residual)
        egp_band = band_power.get("ultra_low", 0) + band_power.get("egp_low", 0)
        meal_band = band_power.get("meal", 0)
        print(f"  Spectral: EGP-band={egp_band:.3f}  meal-band={meal_band:.3f}  "
              f"high-freq={band_power.get('high_freq', 0):.3f}")

        all_results[pid] = {
            "census": census,
            "spectral_bands": band_power,
            "egp_band_total": egp_band,
            "meal_band_power": meal_band,
        }

    # ── Hypothesis testing ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_data = [p for p in FULL_PATIENTS if p in all_results]

    # H1: ≥40% of overnight events have <5g estimated carbs
    h1_values = []
    for pid in patients_with_data:
        ov_small = all_results[pid]["census"]["overnight_small_pct"]
        h1_values.append(ov_small)
        print(f"  H1 Patient {pid}: overnight <5g = {ov_small:.1f}%")

    h1_median = float(np.median(h1_values)) if h1_values else 0
    h1_pass = h1_median >= 40.0
    print(f"  H1 RESULT: median overnight <5g = {h1_median:.1f}% "
          f"(threshold: ≥40%) → {'PASS' if h1_pass else 'FAIL'}")

    # H2: EGP-band power ≥20% for ≥6/9 patients
    h2_count = 0
    for pid in patients_with_data:
        egp_pwr = all_results[pid]["egp_band_total"]
        passes = egp_pwr >= 0.20
        if passes:
            h2_count += 1
        print(f"  H2 Patient {pid}: EGP-band = {egp_pwr:.3f} → {'✓' if passes else '✗'}")

    h2_pass = h2_count >= 6
    print(f"  H2 RESULT: {h2_count}/9 patients with EGP-band ≥20% "
          f"(threshold: ≥6/9) → {'PASS' if h2_pass else 'FAIL'}")

    # H3: Rank correlation between unannounced% and EGP-band power
    unanno_vals = [all_results[p]["census"]["unannounced_pct"] for p in patients_with_data]
    egp_vals = [all_results[p]["egp_band_total"] for p in patients_with_data]
    if len(unanno_vals) >= 4:
        rho, p_val = stats.spearmanr(unanno_vals, egp_vals)
        h3_pass = rho >= 0.5
        print(f"  H3 RESULT: Spearman ρ(unannounced%, EGP-band) = {rho:.3f} "
              f"(p={p_val:.4f}) → {'PASS' if h3_pass else 'FAIL'}")
    else:
        rho, p_val = np.nan, np.nan
        h3_pass = False
        print(f"  H3 RESULT: insufficient data")

    # ── Summary ─────────────────────────────────────────────────────
    summary = {
        "experiment": "EXP-2621",
        "title": "Residual Event Census & EGP-Band Spectral Decomposition",
        "patients": patients_with_data,
        "per_patient": all_results,
        "hypotheses": {
            "H1": {
                "statement": "≥40% of overnight meal events have <5g estimated carbs",
                "metric": "median_overnight_small_pct",
                "value": h1_median,
                "threshold": 40.0,
                "result": "PASS" if h1_pass else "FAIL",
                "per_patient": {p: all_results[p]["census"]["overnight_small_pct"]
                                for p in patients_with_data},
            },
            "H2": {
                "statement": "EGP-band power ≥20% for ≥6/9 patients",
                "metric": "n_patients_passing",
                "value": h2_count,
                "threshold": 6,
                "result": "PASS" if h2_pass else "FAIL",
                "per_patient": {p: all_results[p]["egp_band_total"]
                                for p in patients_with_data},
            },
            "H3": {
                "statement": "Rank correlation(unannounced%, EGP-band) ≥ 0.5",
                "metric": "spearman_rho",
                "value": float(rho) if not np.isnan(rho) else None,
                "p_value": float(p_val) if not np.isnan(p_val) else None,
                "threshold": 0.5,
                "result": "PASS" if h3_pass else "FAIL",
            },
        },
        "population_summary": {
            "mean_events_per_day": float(np.mean([
                all_results[p]["census"]["events_per_day"] for p in patients_with_data])),
            "mean_unannounced_pct": float(np.mean(unanno_vals)),
            "mean_egp_band_power": float(np.mean(egp_vals)),
            "mean_meal_band_power": float(np.mean([
                all_results[p]["meal_band_power"] for p in patients_with_data])),
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {OUTFILE}")

    return summary


if __name__ == "__main__":
    main()
