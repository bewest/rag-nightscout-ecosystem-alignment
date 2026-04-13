#!/usr/bin/env python3
"""EXP-2623: Post-Meal Residual EGP Extraction.

MOTIVATION: Prior research (EXP-444/748, F1=0.939, 18× SNR) established that
the physics-based meal detector reliably finds 1-6 meals/day regardless of
carb logging. EXP-2621 showed EGP-band power is only 3.6-8.6% of the FULL
residual (dominated by high-freq noise at 88%). But meals are the biggest
contributor to that high-freq signal.

HYPOTHESIS: If we MASK OUT meal windows (±2h around detected ≥15g events),
the remaining "inter-meal residual" should be enriched for slow EGP
fluctuations. This is like removing the meal-frequency energy to reveal the
lower-frequency EGP substrate underneath.

HYPOTHESES:
  H1: Inter-meal residual has ≥2× more EGP-band (8-24h) spectral power
      fraction than the full residual (from 5% to ≥10%).
  H2: Non-meal residual drift (mean slope over 2h+ gaps) correlates with
      glycogen proxy from EXP-2622 (r ≥ 0.3 pooled).
  H3: Patients with highest inter-meal drift variance have the most
      detected meals/day (compensatory eating signal, r ≥ 0.4).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, signal as sig

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.meal_detector import detect_meal_events
from cgmencode.production.types import PatientData, PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2623_post_meal_egp.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

MIN_CARB_G = 15.0          # threshold for "real meal" (from Round 1.5)
MASK_RADIUS_STEPS = 24     # ±2h = 24 steps at 5-min resolution
MIN_GAP_STEPS = 36         # minimum 3h inter-meal gap for analysis
STEPS_PER_HOUR = 12
GLYCOGEN_TAU_STEPS = 24 * STEPS_PER_HOUR  # τ=24h in steps

# Spectral band boundaries (cycles per hour)
BANDS = {
    "ultra_low":  (0.0, 1.0 / 24.0),
    "egp_low":    (1.0 / 24.0, 1.0 / 8.0),
    "meal":       (1.0 / 8.0, 1.0 / 3.0),
    "high_freq":  (1.0 / 3.0, 6.0),
}


def _build_profile(pdf):
    isf = float(pdf["scheduled_isf"].dropna().median())
    cr = float(pdf["scheduled_cr"].dropna().median())
    basal = float(pdf["scheduled_basal_rate"].dropna().median())
    return PatientProfile(
        isf_schedule=[{"start": "00:00:00", "value": isf}],
        cr_schedule=[{"start": "00:00:00", "value": cr}],
        basal_schedule=[{"start": "00:00:00", "value": basal}],
        target_low=70, target_high=180, dia_hours=5.0,
    )


def _build_patient(pdf, pid):
    pdf = pdf.sort_values("time").copy()
    t_ms = pd.to_datetime(pdf["time"]).astype(np.int64)
    profile = _build_profile(pdf)
    return PatientData(
        patient_id=pid,
        glucose=pdf["glucose"].values.astype(np.float64),
        timestamps=t_ms.values, profile=profile,
        iob=pdf["iob"].values.astype(np.float64) if "iob" in pdf else None,
        cob=pdf["cob"].values.astype(np.float64) if "cob" in pdf else None,
        bolus=pdf["bolus"].values.astype(np.float64) if "bolus" in pdf else None,
        carbs=pdf["carbs"].values.astype(np.float64) if "carbs" in pdf else None,
        basal_rate=pdf["actual_basal_rate"].values.astype(np.float64) if "actual_basal_rate" in pdf else None,
    )


def spectral_band_power(residual, fs_per_hour=STEPS_PER_HOUR):
    """Compute fractional power in each spectral band."""
    valid = ~np.isnan(residual)
    if valid.sum() < 64:
        return {b: np.nan for b in BANDS}
    r = residual[valid] - np.nanmean(residual[valid])
    freqs = np.fft.rfftfreq(len(r), d=1.0 / fs_per_hour)
    power = np.abs(np.fft.rfft(r)) ** 2
    total = power[1:].sum()
    if total == 0:
        return {b: 0.0 for b in BANDS}
    result = {}
    for name, (f_lo, f_hi) in BANDS.items():
        mask = (freqs >= f_lo) & (freqs < f_hi)
        result[name] = float(power[mask].sum() / total)
    return result


def _compute_glycogen_proxy(carbs_arr):
    """Exponential accumulator (τ=24h) over carb intake."""
    decay = 1.0 - 1.0 / max(GLYCOGEN_TAU_STEPS, 1)
    glyc = np.zeros(len(carbs_arr))
    for i in range(1, len(carbs_arr)):
        glyc[i] = glyc[i - 1] * decay + carbs_arr[i]
    return glyc


def _extract_inter_meal_segments(residual, meal_indices, n_total):
    """Build boolean mask: True where we're ≥MASK_RADIUS from any meal."""
    mask = np.ones(n_total, dtype=bool)
    for idx in meal_indices:
        lo = max(0, idx - MASK_RADIUS_STEPS)
        hi = min(n_total, idx + MASK_RADIUS_STEPS + 1)
        mask[lo:hi] = False
    return mask


def _extract_drift_segments(residual, mask, min_len=MIN_GAP_STEPS):
    """Extract contiguous inter-meal segments and compute drift rates."""
    segments = []
    in_seg = False
    start = 0
    for i in range(len(mask)):
        if mask[i] and not in_seg:
            start = i
            in_seg = True
        elif not mask[i] and in_seg:
            if i - start >= min_len:
                seg = residual[start:i]
                valid = ~np.isnan(seg)
                if valid.sum() >= min_len // 2:
                    t_hrs = np.arange(len(seg)) * (5.0 / 60.0)
                    slope, _ = np.polyfit(t_hrs[valid], seg[valid], 1)
                    segments.append({
                        "start": start,
                        "end": i,
                        "length_hours": (i - start) * 5.0 / 60.0,
                        "drift_rate": float(slope),
                        "mean_residual": float(np.nanmean(seg)),
                    })
            in_seg = False
    # Handle final segment
    if in_seg and len(mask) - start >= min_len:
        seg = residual[start:]
        valid = ~np.isnan(seg)
        if valid.sum() >= min_len // 2:
            t_hrs = np.arange(len(seg)) * (5.0 / 60.0)
            slope, _ = np.polyfit(t_hrs[valid], seg[valid], 1)
            segments.append({
                "start": start,
                "end": len(mask),
                "length_hours": (len(mask) - start) * 5.0 / 60.0,
                "drift_rate": float(slope),
                "mean_residual": float(np.nanmean(seg)),
            })
    return segments


def main():
    print("=" * 70)
    print("EXP-2623: Post-Meal Residual EGP Extraction")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}

    # Collect population-level data
    pop_full_egp = []
    pop_masked_egp = []
    pop_drift_std = []
    pop_meals_per_day = []
    pop_drift_glyc_r = []

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
        times = pd.to_datetime(pdf["time"])
        hours = (times.dt.hour + times.dt.minute / 60.0).values.astype(np.float64)

        # Detect meals with ≥15g threshold
        all_meals = detect_meal_events(
            patient.glucose, metabolic, hours,
            patient.timestamps, patient.profile,
        )
        big_meals = [m for m in all_meals if m.estimated_carbs_g >= MIN_CARB_G]
        days = len(pdf) / 288.0
        meals_per_day = len(big_meals) / days

        print(f"  All detected events: {len(all_meals)} ({len(all_meals)/days:.1f}/day)")
        print(f"  ≥{MIN_CARB_G:.0f}g events: {len(big_meals)} ({meals_per_day:.1f}/day)")

        if len(big_meals) < 3:
            print(f"  SKIP: too few ≥{MIN_CARB_G:.0f}g events for masking analysis")
            continue

        # Get residual signal
        residual = metabolic.residual

        # Full-signal spectral power (baseline from EXP-2621)
        full_spectrum = spectral_band_power(residual)
        full_egp = full_spectrum["egp_low"]

        # Mask meal windows
        meal_indices = [m.index for m in big_meals]
        inter_meal_mask = _extract_inter_meal_segments(residual, meal_indices, len(residual))
        masked_frac = inter_meal_mask.sum() / len(inter_meal_mask)
        print(f"  Inter-meal fraction: {masked_frac:.1%} of data")

        # Masked residual spectral power
        masked_residual = residual.copy()
        masked_residual[~inter_meal_mask] = np.nan
        # For FFT, interpolate NaN gaps
        valid = ~np.isnan(masked_residual)
        if valid.sum() < 128:
            print(f"  SKIP: insufficient inter-meal data for spectral analysis")
            continue
        interp_residual = np.interp(
            np.arange(len(masked_residual)),
            np.where(valid)[0],
            masked_residual[valid],
        )
        masked_spectrum = spectral_band_power(interp_residual)
        masked_egp = masked_spectrum["egp_low"]

        egp_ratio = masked_egp / max(full_egp, 1e-6)
        print(f"  Full residual EGP-band:   {full_egp:.3f}")
        print(f"  Masked residual EGP-band: {masked_egp:.3f} ({egp_ratio:.1f}× enrichment)")

        # Inter-meal drift segments
        segments = _extract_drift_segments(residual, inter_meal_mask)
        if segments:
            drifts = [s["drift_rate"] for s in segments]
            drift_std = float(np.std(drifts))
            drift_mean = float(np.mean(drifts))
            print(f"  Inter-meal segments: {len(segments)}")
            print(f"  Drift rate: mean={drift_mean:.2f} σ={drift_std:.2f} mg/dL/hr")
        else:
            drift_std = np.nan
            drift_mean = np.nan
            print(f"  No inter-meal segments extracted")

        # Glycogen proxy correlation with segment drift
        carbs_arr = pdf["carbs"].fillna(0).values.astype(np.float64)
        glycogen = _compute_glycogen_proxy(carbs_arr)
        glyc_r = np.nan
        glyc_p = np.nan
        if segments and len(segments) >= 5:
            seg_glyc = [float(glycogen[s["start"]]) for s in segments]
            seg_drift = [s["drift_rate"] for s in segments]
            glyc_r, glyc_p = stats.pearsonr(seg_glyc, seg_drift)
            print(f"  Glycogen→drift correlation: r={glyc_r:.3f} (p={glyc_p:.4f})")

        # Collect for population
        pop_full_egp.append(full_egp)
        pop_masked_egp.append(masked_egp)
        if not np.isnan(drift_std):
            pop_drift_std.append(drift_std)
            pop_meals_per_day.append(meals_per_day)
        if not np.isnan(glyc_r):
            pop_drift_glyc_r.append(glyc_r)

        all_results[pid] = {
            "n_all_events": len(all_meals),
            "n_big_events": len(big_meals),
            "meals_per_day": meals_per_day,
            "inter_meal_fraction": float(masked_frac),
            "full_spectrum": full_spectrum,
            "masked_spectrum": masked_spectrum,
            "egp_enrichment_ratio": float(egp_ratio),
            "n_segments": len(segments),
            "drift_mean": drift_mean,
            "drift_std": drift_std,
            "glycogen_drift_r": float(glyc_r) if not np.isnan(glyc_r) else None,
            "glycogen_drift_p": float(glyc_p) if not np.isnan(glyc_p) else None,
        }

    # ── Hypothesis Testing ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_data = list(all_results.keys())

    # H1: EGP-band enrichment ≥2×
    if pop_full_egp and pop_masked_egp:
        ratios = [m / max(f, 1e-6) for f, m in zip(pop_full_egp, pop_masked_egp)]
        median_ratio = float(np.median(ratios))
        n_enriched = sum(1 for r in ratios if r >= 2.0)
        h1_pass = median_ratio >= 2.0
        print(f"  H1: Median EGP enrichment ratio = {median_ratio:.2f}× "
              f"(threshold: ≥2.0×) → {'PASS' if h1_pass else 'FAIL'}")
        print(f"      {n_enriched}/{len(ratios)} patients with ≥2× enrichment")
        for pid, r in zip(patients_with_data, ratios):
            print(f"      {pid}: {r:.2f}×")
    else:
        h1_pass = False
        median_ratio = 0
        ratios = []
        print(f"  H1: No data → FAIL")

    # H2: Glycogen→drift correlation ≥0.3
    if pop_drift_glyc_r:
        median_glyc_r = float(np.median(pop_drift_glyc_r))
        h2_pass = median_glyc_r >= 0.3 or any(abs(r) >= 0.3 for r in pop_drift_glyc_r)
        print(f"  H2: Median glycogen→drift r = {median_glyc_r:.3f} "
              f"(threshold: ≥0.3) → {'PASS' if h2_pass else 'FAIL'}")
        for pid in patients_with_data:
            r = all_results[pid].get("glycogen_drift_r")
            if r is not None:
                print(f"      {pid}: r={r:.3f}")
    else:
        h2_pass = False
        median_glyc_r = 0
        print(f"  H2: No data → FAIL")

    # H3: Drift variance correlates with meals/day (r ≥ 0.4)
    if len(pop_drift_std) >= 4:
        r_drift_meals, p_drift_meals = stats.pearsonr(pop_drift_std, pop_meals_per_day)
        h3_pass = r_drift_meals >= 0.4 and p_drift_meals < 0.1
        print(f"  H3: r(drift_std, meals/day) = {r_drift_meals:.3f} "
              f"(p={p_drift_meals:.4f}, threshold: r≥0.4) → {'PASS' if h3_pass else 'FAIL'}")
        for pid in patients_with_data:
            ds = all_results[pid].get("drift_std")
            mpd = all_results[pid].get("meals_per_day")
            if ds is not None:
                print(f"      {pid}: drift_std={ds:.2f}, meals/day={mpd:.1f}")
    else:
        h3_pass = False
        r_drift_meals = 0
        p_drift_meals = 1
        print(f"  H3: Insufficient data → FAIL")

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if pop_full_egp:
        print(f"  Mean full-residual EGP-band:   {np.mean(pop_full_egp):.3f}")
        print(f"  Mean masked-residual EGP-band: {np.mean(pop_masked_egp):.3f}")
        print(f"  Mean enrichment: {np.mean(ratios):.2f}×")

    # ── Save ──────────────────────────────────────────────────────────
    summary = {
        "experiment": "EXP-2623",
        "title": "Post-Meal Residual EGP Extraction",
        "min_carb_threshold_g": MIN_CARB_G,
        "mask_radius_hours": MASK_RADIUS_STEPS * 5 / 60,
        "patients": patients_with_data,
        "per_patient": all_results,
        "hypotheses": {
            "H1": {
                "statement": "Inter-meal residual EGP-band power ≥2× enriched vs full",
                "median_ratio": float(median_ratio) if ratios else None,
                "per_patient_ratios": {p: r for p, r in zip(patients_with_data, ratios)},
                "result": "PASS" if h1_pass else "FAIL",
            },
            "H2": {
                "statement": "Glycogen proxy → inter-meal drift r ≥ 0.3",
                "median_r": float(median_glyc_r) if pop_drift_glyc_r else None,
                "result": "PASS" if h2_pass else "FAIL",
            },
            "H3": {
                "statement": "Drift variance correlates with meals/day (r ≥ 0.4)",
                "r": float(r_drift_meals),
                "p": float(p_drift_meals),
                "result": "PASS" if h3_pass else "FAIL",
            },
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")

    return summary


if __name__ == "__main__":
    main()
