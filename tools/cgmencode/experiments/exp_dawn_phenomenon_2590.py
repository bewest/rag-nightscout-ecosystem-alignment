#!/usr/bin/env python3
"""EXP-2590: Dawn Phenomenon Quantification via Loop Suspension Windows.

Hypotheses:
  H1: During loop suspension periods (actual_basal ≈ 0, no bolus, no carbs),
      the rate of glucose rise IS the net endogenous glucose production (EGP)
      rate, measurable as mg/dL/h. This should be ≥5 mg/dL/h for dawn-prone
      patients.
  H2: EGP rate is higher during dawn hours (03-06) than early night (00-03),
      consistent with the dawn phenomenon (cortisol/growth hormone surge).
  H3: Per-patient EGP rate correlates with their optimal counter-regulation k
      (from EXP-2582/2588) — patients with higher EGP need higher k.

Design:
  1. Find windows where actual_basal ≈ 0 (suspended) for ≥1h, no carbs,
     glucose available.
  2. Measure glucose slope during these windows = proxy for net EGP.
  3. Split into early-night (00-03) vs dawn (03-06) to test circadian EGP.
  4. Cross-reference with per-patient k values.

Only FULL telemetry patients: a-g, i, k.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Per-patient night k from EXP-2588
PATIENT_NIGHT_K = {
    "a": 7.0, "b": 10.0, "c": 5.0, "d": 7.0, "e": 7.0,
    "f": 1.0, "g": 2.0, "i": 10.0, "k": 0.0,
}
# Per-patient overall k from EXP-2582
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "h": 0.0, "i": 3.0, "j": 0.0, "k": 0.0,
}


def extract_suspension_windows(pdf: pd.DataFrame, min_minutes: float = 60.0,
                                max_actual_basal: float = 0.05) -> list:
    """Extract windows where the loop has suspended basal delivery.

    Criteria:
      - actual_basal_rate ≈ 0 (< max_actual_basal)
      - No carbs
      - No bolus (bolus == 0)
      - Glucose available for ≥50% of rows
      - At least min_minutes long
    """
    pdf = pdf.sort_values("time").copy()
    t = pd.to_datetime(pdf["time"])

    # Night mask (00-06 only)
    night_mask = t.dt.hour < 6

    # Suspension mask
    suspend_mask = pdf["actual_basal_rate"].fillna(0) <= max_actual_basal

    # Fasting mask
    carb_mask = pdf["carbs"].fillna(0) == 0
    bolus_mask = pdf["bolus"].fillna(0) == 0

    eligible = night_mask & suspend_mask & carb_mask & bolus_mask
    eligible_idx = pdf.index[eligible].tolist()

    if not eligible_idx:
        return []

    # Group consecutive eligible rows
    windows = []
    current = [eligible_idx[0]]
    for i in range(1, len(eligible_idx)):
        gap = (t.loc[eligible_idx[i]] - t.loc[eligible_idx[i-1]]).total_seconds() / 60.0
        if gap <= 10.0:
            current.append(eligible_idx[i])
        else:
            windows.append(current)
            current = [eligible_idx[i]]
    windows.append(current)

    # Filter by duration and glucose
    min_rows = int(min_minutes / 5)
    valid = []
    for w in windows:
        if len(w) < min_rows:
            continue
        g = pdf.loc[w, "glucose"].values
        if (~np.isnan(g)).mean() < 0.50:
            continue
        valid.append(w)

    return valid


def measure_egp_rate(pdf: pd.DataFrame, window_idx: list) -> dict:
    """Measure endogenous glucose production rate from glucose slope."""
    w_data = pdf.loc[window_idx]
    gluc = w_data["glucose"].values
    valid = ~np.isnan(gluc)

    if valid.sum() < 6:
        return None

    t_hours = np.arange(len(gluc)) * (5.0 / 60.0)
    t_v = t_hours[valid]
    g_v = gluc[valid]

    slope, intercept = np.polyfit(t_v, g_v, 1)

    t_ts = pd.to_datetime(w_data["time"])
    start_hour = float(t_ts.iloc[0].hour + t_ts.iloc[0].minute / 60.0)
    end_hour = float(t_ts.iloc[-1].hour + t_ts.iloc[-1].minute / 60.0)
    mid_hour = (start_hour + end_hour) / 2.0

    # Classify as early_night (00-03) or dawn (03-06)
    period = "dawn" if mid_hour >= 3.0 else "early_night"

    # Check actual insulin delivery (should be ~0)
    actual_insulin = float(w_data["actual_basal_rate"].fillna(0).mean())
    iob = float(w_data["iob"].fillna(0).mean())

    return {
        "egp_rate_mg_h": float(slope),  # mg/dL per hour
        "start_glucose": float(g_v[0]),
        "end_glucose": float(g_v[-1]),
        "duration_hours": float(t_v[-1] - t_v[0]),
        "n_points": int(valid.sum()),
        "start_hour": start_hour,
        "end_hour": end_hour,
        "mid_hour": mid_hour,
        "period": period,
        "mean_actual_basal": actual_insulin,
        "mean_iob": iob,
        "mean_glucose": float(np.nanmean(gluc)),
    }


def main():
    print("=" * 70)
    print("EXP-2590: Dawn Phenomenon Quantification")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)

    all_results = {}
    summary_rows = []

    for pid in FULL_PATIENTS:
        print(f"\n--- Patient {pid} ---")
        pdf = df[df["patient_id"] == pid].copy()
        if pdf.empty:
            continue

        windows = extract_suspension_windows(pdf)
        print(f"  Suspension windows (≥1h, 00-06): {len(windows)}")

        if not windows:
            continue

        early_night_rates = []
        dawn_rates = []
        all_rates = []
        iob_values = []

        for w_idx in windows:
            egp = measure_egp_rate(pdf, w_idx)
            if egp is None:
                continue

            all_rates.append(egp["egp_rate_mg_h"])
            iob_values.append(egp["mean_iob"])

            if egp["period"] == "dawn":
                dawn_rates.append(egp["egp_rate_mg_h"])
            else:
                early_night_rates.append(egp["egp_rate_mg_h"])

        if not all_rates:
            print(f"  No valid measurements")
            continue

        mean_egp = float(np.mean(all_rates))
        median_egp = float(np.median(all_rates))
        mean_dawn = float(np.mean(dawn_rates)) if dawn_rates else float("nan")
        mean_early = float(np.mean(early_night_rates)) if early_night_rates else float("nan")
        mean_iob = float(np.mean(iob_values))

        # TIR
        g = pdf["glucose"].dropna()
        tir = float(((g >= 70) & (g <= 180)).mean()) if len(g) > 0 else float("nan")

        patient_k = PATIENT_K.get(pid, 1.5)
        night_k = PATIENT_NIGHT_K.get(pid, 3.8)

        patient_results = {
            "patient_id": pid,
            "n_windows": len(windows),
            "n_measurements": len(all_rates),
            "mean_egp_rate": mean_egp,
            "median_egp_rate": median_egp,
            "mean_dawn_egp": mean_dawn,
            "mean_early_night_egp": mean_early,
            "n_dawn": len(dawn_rates),
            "n_early": len(early_night_rates),
            "mean_iob": mean_iob,
            "tir": tir,
            "patient_k": patient_k,
            "night_k": night_k,
        }

        all_results[pid] = patient_results

        dawn_delta = mean_dawn - mean_early if not np.isnan(mean_dawn) and not np.isnan(mean_early) else float("nan")

        print(f"  Measurements: {len(all_rates)} (dawn={len(dawn_rates)}, early={len(early_night_rates)})")
        print(f"  Overall EGP: {mean_egp:+.1f} mg/dL/h (median {median_egp:+.1f})")
        print(f"  Dawn EGP: {mean_dawn:+.1f} mg/dL/h")
        print(f"  Early night EGP: {mean_early:+.1f} mg/dL/h")
        if not np.isnan(dawn_delta):
            print(f"  Dawn effect: {dawn_delta:+.1f} mg/dL/h")
        print(f"  Mean IOB during suspension: {mean_iob:.2f} U")
        print(f"  Patient k={patient_k}, night_k={night_k}")

        summary_rows.append({
            "patient": pid,
            "n_meas": len(all_rates),
            "mean_egp": mean_egp,
            "dawn_egp": mean_dawn,
            "early_egp": mean_early,
            "dawn_delta": dawn_delta,
            "mean_iob": mean_iob,
            "patient_k": patient_k,
            "night_k": night_k,
            "tir": tir,
        })

    # === Cross-patient analysis ===
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    sdf = pd.DataFrame(summary_rows)
    if sdf.empty:
        print("No valid results")
        return

    print(f"\n{'Patient':<4} {'N':>3} {'MeanEGP':>7} {'Dawn':>6} {'Early':>6} "
          f"{'Δ':>5} {'IOB':>5} {'k':>4} {'nk':>4} {'TIR':>5}")
    print("-" * 60)
    for _, r in sdf.iterrows():
        dawn_d = f"{r['dawn_delta']:+.1f}" if not np.isnan(r["dawn_delta"]) else "  N/A"
        dawn_e = f"{r['dawn_egp']:+.1f}" if not np.isnan(r["dawn_egp"]) else "   N/A"
        early_e = f"{r['early_egp']:+.1f}" if not np.isnan(r["early_egp"]) else "   N/A"
        print(f"{r['patient']:<4} {r['n_meas']:>3} {r['mean_egp']:>+7.1f} {dawn_e:>6} {early_e:>6} "
              f"{dawn_d:>5} {r['mean_iob']:>5.2f} {r['patient_k']:>4.1f} {r['night_k']:>4.1f} {r['tir']:>5.1%}")

    # H1: EGP rate ≥5 mg/dL/h for dawn-prone patients
    dawn_prone = sdf[sdf["mean_egp"] >= 5.0]
    print(f"\nH1 - Dawn-prone patients (EGP ≥ 5 mg/dL/h): {len(dawn_prone)}/{len(sdf)}")
    if len(dawn_prone) > 0:
        print(f"  Patients: {', '.join(dawn_prone['patient'].tolist())}")
    all_positive = sdf[sdf["mean_egp"] > 0]
    print(f"  Positive EGP (any rate): {len(all_positive)}/{len(sdf)}")
    h1_confirmed = len(dawn_prone) >= 2
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # H2: Dawn EGP > early night EGP
    valid_h2 = sdf.dropna(subset=["dawn_egp", "early_egp"])
    if len(valid_h2) >= 3:
        dawn_higher = (valid_h2["dawn_egp"] > valid_h2["early_egp"]).sum()
        print(f"\nH2 - Dawn > Early night EGP: {dawn_higher}/{len(valid_h2)} patients")
        mean_delta = valid_h2["dawn_delta"].mean()
        print(f"  Mean dawn delta: {mean_delta:+.1f} mg/dL/h")
        h2_confirmed = dawn_higher > len(valid_h2) / 2
        print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")
    else:
        print(f"\nH2 - Insufficient data ({len(valid_h2)} patients with both periods)")
        h2_confirmed = False

    # H3: EGP correlates with counter-reg k
    from scipy import stats
    valid_h3 = sdf.dropna(subset=["mean_egp", "night_k"])
    if len(valid_h3) >= 4:
        r_k, p_k = stats.pearsonr(valid_h3["mean_egp"], valid_h3["night_k"])
        print(f"\nH3 - EGP vs night k correlation:")
        print(f"  r = {r_k:.3f}, p = {p_k:.3f}")
        h3_confirmed = r_k > 0.3
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")
        print(f"  Interpretation: {'Higher EGP → higher k needed (consistent)' if r_k > 0 else 'No relationship'}")

        # Also check EGP vs TIR
        r_tir, p_tir = stats.pearsonr(valid_h3["mean_egp"], valid_h3["tir"])
        print(f"  EGP vs TIR: r = {r_tir:.3f}, p = {p_tir:.3f}")
    else:
        print(f"\nH3 - Insufficient data ({len(valid_h3)} patients)")
        h3_confirmed = False

    # Clinical interpretation
    print(f"\nClinical Interpretation:")
    for _, r in sdf.iterrows():
        egp = r["mean_egp"]
        if egp >= 15:
            severity = "SEVERE dawn phenomenon"
        elif egp >= 5:
            severity = "MODERATE dawn phenomenon"
        elif egp >= 0:
            severity = "MILD/no dawn phenomenon"
        else:
            severity = "No dawn phenomenon (glucose drops during suspension)"
        print(f"  {r['patient']}: EGP={egp:+.1f} mg/dL/h → {severity}")

    # Save results
    output = {
        "experiment": "EXP-2590",
        "title": "Dawn Phenomenon Quantification",
        "approach": "Measure glucose slope during loop suspension (actual_basal≈0) windows",
        "summary": summary_rows,
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "patients": {pid: all_results[pid] for pid in all_results},
    }

    out_path = RESULTS_DIR / "exp-2590_dawn_phenomenon.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
