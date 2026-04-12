#!/usr/bin/env python3
"""EXP-2591: IOB-Corrected Endogenous Glucose Production Rate.

EXP-2590 showed that loop suspension windows have selection bias (loop
suspends when glucose is dropping) and residual IOB confounds the signal.
This experiment corrects for IOB:

    true_EGP = measured_slope + IOB_driven_drop_rate

Where IOB_driven_drop_rate = IOB × ISF / DIA × time_factor

Hypotheses:
  H1: After IOB correction, some patients show positive EGP (≥3 mg/dL/h),
      indicating endogenous glucose production that opposes insulin action.
  H2: IOB-corrected EGP is higher during dawn (03-06) than early night (00-03).
  H3: IOB-corrected EGP correlates with counter-regulation k (r > 0.3).
  H4: Forward simulator with IOB-corrected EGP as a constant drift term
      improves overnight prediction accuracy vs baseline.

Design:
  1. Reuse suspension windows from EXP-2590.
  2. For each window, estimate IOB-driven glucose drop:
     IOB_effect = IOB × ISF / remaining_DIA_hours
  3. Corrected EGP = measured_slope + IOB_effect
  4. Test circadian pattern and k correlation.
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

PATIENT_NIGHT_K = {
    "a": 7.0, "b": 10.0, "c": 5.0, "d": 7.0, "e": 7.0,
    "f": 1.0, "g": 2.0, "i": 10.0, "k": 0.0,
}
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "i": 3.0, "k": 0.0,
}

DIA_HOURS = 5.0  # Standard DIA


def extract_suspension_windows(pdf, min_minutes=60.0, max_actual_basal=0.05):
    """Extract suspension windows (reused from EXP-2590)."""
    pdf = pdf.sort_values("time").copy()
    t = pd.to_datetime(pdf["time"])
    night_mask = t.dt.hour < 6
    suspend_mask = pdf["actual_basal_rate"].fillna(0) <= max_actual_basal
    carb_mask = pdf["carbs"].fillna(0) == 0
    bolus_mask = pdf["bolus"].fillna(0) == 0
    eligible = night_mask & suspend_mask & carb_mask & bolus_mask
    eligible_idx = pdf.index[eligible].tolist()
    if not eligible_idx:
        return []

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


def measure_iob_corrected_egp(pdf, window_idx):
    """Measure EGP rate corrected for residual IOB effect.

    IOB-driven drop rate estimate:
      The remaining IOB will produce a glucose drop over the remaining DIA.
      Simplified: IOB_drop_rate ≈ IOB × ISF / (DIA/2) per hour
      (assuming roughly linear IOB decay, glucose drop is spread over DIA/2)

    true_EGP = measured_slope + IOB_drop_rate
    """
    w_data = pdf.loc[window_idx]
    gluc = w_data["glucose"].values
    valid = ~np.isnan(gluc)
    if valid.sum() < 6:
        return None

    t_hours = np.arange(len(gluc)) * (5.0 / 60.0)
    t_v = t_hours[valid]
    g_v = gluc[valid]
    slope, _ = np.polyfit(t_v, g_v, 1)

    t_ts = pd.to_datetime(w_data["time"])
    start_hour = float(t_ts.iloc[0].hour + t_ts.iloc[0].minute / 60.0)
    end_hour = float(t_ts.iloc[-1].hour + t_ts.iloc[-1].minute / 60.0)
    mid_hour = (start_hour + end_hour) / 2.0
    period = "dawn" if mid_hour >= 3.0 else "early_night"

    # IOB and ISF at window start
    iob = float(w_data["iob"].iloc[0]) if pd.notna(w_data["iob"].iloc[0]) else 0.0
    isf = float(w_data["scheduled_isf"].dropna().median())

    # Mean IOB across window (accounts for decay)
    mean_iob = float(w_data["iob"].fillna(0).mean())

    # IOB-driven glucose drop rate (mg/dL per hour)
    # Conservative estimate: IOB produces total drop = IOB × ISF,
    # spread over remaining DIA time. At midpoint of DIA, rate ≈ IOB × ISF / (DIA/2)
    # Using mean_iob for better estimate of average effect during window
    iob_drop_rate = mean_iob * isf / (DIA_HOURS / 2.0)

    # Corrected EGP: measured (negative from IOB) + correction (positive)
    corrected_egp = slope + iob_drop_rate

    return {
        "measured_slope": float(slope),
        "iob_start": iob,
        "mean_iob": mean_iob,
        "isf": isf,
        "iob_drop_rate": float(iob_drop_rate),
        "corrected_egp": float(corrected_egp),
        "start_glucose": float(g_v[0]),
        "duration_hours": float(t_v[-1] - t_v[0]),
        "n_points": int(valid.sum()),
        "start_hour": start_hour,
        "mid_hour": mid_hour,
        "period": period,
    }


def main():
    print("=" * 70)
    print("EXP-2591: IOB-Corrected Endogenous Glucose Production")
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
        print(f"  Suspension windows: {len(windows)}")
        if not windows:
            continue

        early_egps = []
        dawn_egps = []
        all_egps = []
        raw_slopes = []
        iob_corrections = []

        for w_idx in windows:
            m = measure_iob_corrected_egp(pdf, w_idx)
            if m is None:
                continue

            all_egps.append(m["corrected_egp"])
            raw_slopes.append(m["measured_slope"])
            iob_corrections.append(m["iob_drop_rate"])

            if m["period"] == "dawn":
                dawn_egps.append(m["corrected_egp"])
            else:
                early_egps.append(m["corrected_egp"])

        if not all_egps:
            continue

        mean_raw = float(np.mean(raw_slopes))
        mean_correction = float(np.mean(iob_corrections))
        mean_egp = float(np.mean(all_egps))
        median_egp = float(np.median(all_egps))
        mean_dawn = float(np.mean(dawn_egps)) if dawn_egps else float("nan")
        mean_early = float(np.mean(early_egps)) if early_egps else float("nan")

        g = pdf["glucose"].dropna()
        tir = float(((g >= 70) & (g <= 180)).mean()) if len(g) > 0 else float("nan")
        night_k = PATIENT_NIGHT_K.get(pid, 3.8)
        overall_k = PATIENT_K.get(pid, 1.5)

        dawn_delta = mean_dawn - mean_early if not np.isnan(mean_dawn) and not np.isnan(mean_early) else float("nan")

        print(f"  Raw slope: {mean_raw:+.1f} mg/dL/h")
        print(f"  IOB correction: +{mean_correction:.1f} mg/dL/h")
        print(f"  Corrected EGP: {mean_egp:+.1f} mg/dL/h (median {median_egp:+.1f})")
        print(f"  Dawn EGP: {mean_dawn:+.1f}, Early: {mean_early:+.1f}, Δ={dawn_delta:+.1f}" if not np.isnan(dawn_delta) else "")
        print(f"  k={overall_k}, night_k={night_k}, TIR={tir:.1%}")

        patient_results = {
            "patient_id": pid,
            "n_measurements": len(all_egps),
            "mean_raw_slope": mean_raw,
            "mean_iob_correction": mean_correction,
            "mean_corrected_egp": mean_egp,
            "median_corrected_egp": median_egp,
            "mean_dawn_egp": mean_dawn,
            "mean_early_night_egp": mean_early,
            "dawn_delta": dawn_delta,
            "n_dawn": len(dawn_egps),
            "n_early": len(early_egps),
            "night_k": night_k,
            "overall_k": overall_k,
            "tir": tir,
        }
        all_results[pid] = patient_results
        summary_rows.append({
            "patient": pid,
            "n": len(all_egps),
            "raw_slope": mean_raw,
            "iob_corr": mean_correction,
            "egp": mean_egp,
            "dawn_egp": mean_dawn,
            "early_egp": mean_early,
            "dawn_delta": dawn_delta,
            "k": overall_k,
            "night_k": night_k,
            "tir": tir,
        })

    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    sdf = pd.DataFrame(summary_rows)
    if sdf.empty:
        print("No results")
        return

    print(f"\n{'Pt':<3} {'N':>3} {'RawSlope':>8} {'IOBCorr':>7} {'EGP':>6} "
          f"{'Dawn':>6} {'Early':>6} {'Δ':>5} {'k':>4} {'nk':>4} {'TIR':>5}")
    print("-" * 70)
    for _, r in sdf.iterrows():
        dd = f"{r['dawn_delta']:+.1f}" if not np.isnan(r["dawn_delta"]) else " N/A"
        de = f"{r['dawn_egp']:+.1f}" if not np.isnan(r["dawn_egp"]) else "  N/A"
        ee = f"{r['early_egp']:+.1f}" if not np.isnan(r["early_egp"]) else "  N/A"
        print(f"{r['patient']:<3} {r['n']:>3} {r['raw_slope']:>+8.1f} {r['iob_corr']:>+7.1f} "
              f"{r['egp']:>+6.1f} {de:>6} {ee:>6} {dd:>5} {r['k']:>4.1f} {r['night_k']:>4.1f} {r['tir']:>5.1%}")

    # H1: Some patients have positive corrected EGP ≥ 3 mg/dL/h
    positive = sdf[sdf["egp"] >= 3.0]
    print(f"\nH1 - Patients with corrected EGP ≥ 3 mg/dL/h: {len(positive)}/{len(sdf)}")
    if len(positive) > 0:
        print(f"  Patients: {', '.join(positive['patient'].tolist())}")
    h1_confirmed = len(positive) >= 2
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # Population mean
    pop_egp = sdf["egp"].mean()
    print(f"  Population mean corrected EGP: {pop_egp:+.1f} mg/dL/h")

    # H2: Dawn > Early night
    valid_h2 = sdf.dropna(subset=["dawn_egp", "early_egp"])
    if len(valid_h2) >= 3:
        dawn_higher = (valid_h2["dawn_egp"] > valid_h2["early_egp"]).sum()
        print(f"\nH2 - Dawn > Early night EGP: {dawn_higher}/{len(valid_h2)}")
        mean_dd = valid_h2["dawn_delta"].mean()
        print(f"  Mean dawn delta: {mean_dd:+.1f} mg/dL/h")
        h2_confirmed = dawn_higher > len(valid_h2) / 2
        print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")
    else:
        h2_confirmed = False

    # H3: Corrected EGP correlates with k
    from scipy import stats
    valid_h3 = sdf.dropna(subset=["egp", "night_k"])
    if len(valid_h3) >= 4:
        r_k, p_k = stats.pearsonr(valid_h3["egp"], valid_h3["night_k"])
        print(f"\nH3 - Corrected EGP vs night k: r={r_k:.3f}, p={p_k:.3f}")
        h3_confirmed = r_k > 0.3
        print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

        r_tir, p_tir = stats.pearsonr(valid_h3["egp"], valid_h3["tir"])
        print(f"  Corrected EGP vs TIR: r={r_tir:.3f}, p={p_tir:.3f}")
    else:
        h3_confirmed = False

    # Clinical classification
    print(f"\nClinical EGP Classification:")
    for _, r in sdf.iterrows():
        egp = r["egp"]
        if egp >= 15:
            c = "STRONG positive EGP (significant endogenous production)"
        elif egp >= 5:
            c = "MODERATE positive EGP"
        elif egp >= 0:
            c = "MILD/negligible EGP"
        elif egp >= -10:
            c = "NET insulin effect still dominant (low EGP)"
        else:
            c = "STRONG net insulin effect (EGP << insulin)"
        print(f"  {r['patient']}: corrected EGP={egp:+.1f} mg/dL/h → {c}")

    output = {
        "experiment": "EXP-2591",
        "title": "IOB-Corrected EGP",
        "approach": "true_EGP = measured_slope + IOB × ISF / (DIA/2)",
        "summary": summary_rows,
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "patients": {pid: all_results[pid] for pid in all_results},
    }
    out_path = RESULTS_DIR / "exp-2591_iob_corrected_egp.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
