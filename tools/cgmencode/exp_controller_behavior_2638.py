#!/usr/bin/env python3
"""EXP-2638: Controller Behavior Prediction — Can We Model the AID Instead of Physiology?

BUILDS ON:
  - EXP-2634: ALL physiological recovery models fail (R² < 0)
  - EXP-2635: IOB decay r=-0.07, system coupled through AID feedback loop
  - EXP-2630: Loop gain ~8× (AID absorbs 88% of metabolic forces)
  - EXP-2632: AID delivers 20-30% of scheduled basal around corrections

QUESTION: Since no physiological model works (the AID absorbs all signals), can
we instead model the AID CONTROLLER'S behavior? If enacted_rate/scheduled_rate
is predictable from (glucose, IOB, glucose_roc), then we can predict the controller
and work backwards to glucose trajectories.

DESIGN: For all grid data (not just corrections), model:
  controller_ratio = enacted_rate / scheduled_rate
as a function of (glucose, IOB, glucose_roc, time_since_last_bolus).

Also: analyze controller oscillation via FFT of the ratio signal to detect
ringing periods, and compute per-patient damping characteristics.

HYPOTHESES:
  H1: Controller ratio is predictable from (glucose, IOB, ROC) with R² > 0.3
      Rationale: Controllers are deterministic functions of sensor input.
  H2: Controller output has detectable oscillation period (FFT peak at 1-3h)
      Rationale: Feedback systems with delay produce characteristic oscillation.
  H3: Controller damping ratio ζ varies >2× across patients
      Rationale: Different patients have different controller settings/types.
  H4: Controller "ringing amplitude" correlates with glucose CV (r > 0.3)
      Rationale: More oscillation in controller → more oscillation in glucose.
"""
import json, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats
from scipy.fft import fft, fftfreq

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = ROOT / "externals" / "experiments" / "exp-2638_controller_behavior.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
STEPS_PER_HOUR = 12


def _analyze_controller(pdf, pid):
    """Analyze controller behavior for one patient."""
    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    roc = pdf["glucose_roc"].fillna(0).values.astype(np.float64) if "glucose_roc" in pdf.columns else np.zeros(len(glucose))

    enacted = pdf["loop_enacted_rate"].fillna(np.nan).values.astype(np.float64) if "loop_enacted_rate" in pdf.columns else np.full(len(glucose), np.nan)
    scheduled = pdf["scheduled_basal_rate"].fillna(np.nan).values.astype(np.float64) if "scheduled_basal_rate" in pdf.columns else np.full(len(glucose), np.nan)

    # Controller ratio (enacted / scheduled)
    valid = (~np.isnan(enacted)) & (~np.isnan(scheduled)) & (scheduled > 0) & (~np.isnan(glucose))
    if valid.sum() < 100:
        return None

    ratio = enacted[valid] / scheduled[valid]
    g = glucose[valid]
    iob_v = iob[valid]
    roc_v = roc[valid]

    # Clip extreme ratios (some controllers report 0 or very high)
    ratio = np.clip(ratio, 0, 5)

    # --- Predictability (H1) ---
    # Multiple regression: ratio ~ glucose + IOB + ROC
    X = np.column_stack([g, iob_v, roc_v, np.ones(len(g))])
    valid_x = ~np.any(np.isnan(X), axis=1)
    X = X[valid_x]
    y = ratio[valid_x]

    if len(y) < 50:
        return None

    # Use least squares
    try:
        beta, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
        y_pred = X @ beta
        ss_res = np.sum((y - y_pred)**2)
        ss_tot = np.sum((y - np.mean(y))**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    except Exception:
        r2 = np.nan
        beta = np.full(4, np.nan)

    # --- Oscillation detection (H2) ---
    # Use enacted rate directly for FFT (need continuous segments)
    # Find longest continuous segment of valid data
    valid_mask = ~np.isnan(enacted) & (enacted >= 0)
    segments = []
    start = None
    for j in range(len(valid_mask)):
        if valid_mask[j]:
            if start is None:
                start = j
        else:
            if start is not None and j - start >= 144:  # min 12h segment
                segments.append((start, j))
            start = None
    if start is not None and len(valid_mask) - start >= 144:
        segments.append((start, len(valid_mask)))

    peak_period_h = np.nan
    peak_power = np.nan
    spectral_peaks = []

    if segments:
        # Use longest segment
        seg = max(segments, key=lambda s: s[1] - s[0])
        sig = enacted[seg[0]:seg[1]]
        sig = sig - np.mean(sig)  # Remove DC component
        n_fft = len(sig)
        yf = np.abs(fft(sig))[:n_fft // 2]
        xf = fftfreq(n_fft, d=5.0 / 60.0)[:n_fft // 2]  # in cycles/hour

        # Look for peaks in 0.3-3 cycles/hour range (period 0.33-3.3h)
        freq_mask = (xf > 0.3) & (xf < 3.0)
        if freq_mask.sum() > 0:
            peak_idx = np.argmax(yf[freq_mask])
            peak_freq = xf[freq_mask][peak_idx]
            peak_period_h = 1.0 / peak_freq if peak_freq > 0 else np.nan
            peak_power = float(yf[freq_mask][peak_idx])

            # Top 3 peaks
            sorted_idx = np.argsort(yf[freq_mask])[::-1][:3]
            for si in sorted_idx:
                f = xf[freq_mask][si]
                spectral_peaks.append({
                    "period_h": round(1.0 / f, 2) if f > 0 else None,
                    "power": round(float(yf[freq_mask][si]), 2),
                })

    # --- Damping characteristics (H3) ---
    # Compute autocorrelation of controller ratio to estimate damping
    ratio_centered = ratio - np.mean(ratio)
    n_r = len(ratio_centered)
    max_lag = min(n_r // 2, 144)  # up to 12h
    autocorr = np.correlate(ratio_centered[:max_lag * 2], ratio_centered[:max_lag * 2], mode='full')
    autocorr = autocorr[len(autocorr) // 2:]  # positive lags only
    autocorr = autocorr / autocorr[0] if autocorr[0] > 0 else autocorr

    # Find first zero crossing (quarter period) and first negative minimum
    zero_cross_lag = np.nan
    for j in range(1, len(autocorr)):
        if autocorr[j] < 0:
            zero_cross_lag = j / STEPS_PER_HOUR
            break

    # Damping: ratio of first positive peak to initial
    first_peak_lag = np.nan
    first_peak_val = np.nan
    for j in range(int(zero_cross_lag * STEPS_PER_HOUR * 2) if not np.isnan(zero_cross_lag) else 12, min(len(autocorr), 144)):
        if j > 0 and autocorr[j] > autocorr[j-1] and autocorr[j] > autocorr[j+1] if j+1 < len(autocorr) else False:
            first_peak_lag = j / STEPS_PER_HOUR
            first_peak_val = float(autocorr[j])
            break

    # Estimate damping ratio from autocorrelation decay
    if not np.isnan(first_peak_val) and first_peak_val > 0:
        damping_ratio = -np.log(first_peak_val) / (2 * np.pi) if first_peak_val < 1 else 0
    else:
        damping_ratio = np.nan

    # --- Ringing amplitude (H4) ---
    # CV of controller ratio
    ratio_cv = float(np.std(ratio) / np.mean(ratio) * 100) if np.mean(ratio) > 0 else np.nan
    # Glucose CV
    valid_gluc = ~np.isnan(glucose)
    glucose_cv = float(np.std(glucose[valid_gluc]) / np.mean(glucose[valid_gluc]) * 100) if valid_gluc.sum() > 100 else np.nan

    return {
        "n_valid": int(valid.sum()),
        "r2_predictability": round(r2, 3) if not np.isnan(r2) else None,
        "beta_glucose": round(float(beta[0]), 5) if not np.isnan(beta[0]) else None,
        "beta_iob": round(float(beta[1]), 4) if not np.isnan(beta[1]) else None,
        "beta_roc": round(float(beta[2]), 4) if not np.isnan(beta[2]) else None,
        "mean_ratio": round(float(np.mean(ratio)), 3),
        "std_ratio": round(float(np.std(ratio)), 3),
        "ratio_cv_pct": round(ratio_cv, 1) if not np.isnan(ratio_cv) else None,
        "glucose_cv_pct": round(glucose_cv, 1) if not np.isnan(glucose_cv) else None,
        "peak_period_h": round(peak_period_h, 2) if not np.isnan(peak_period_h) else None,
        "peak_power": round(peak_power, 2) if not np.isnan(peak_power) else None,
        "spectral_peaks": spectral_peaks,
        "damping_ratio": round(damping_ratio, 3) if not np.isnan(damping_ratio) else None,
        "zero_cross_h": round(zero_cross_lag, 2) if not np.isnan(zero_cross_lag) else None,
        "first_peak_h": round(first_peak_lag, 2) if not np.isnan(first_peak_lag) else None,
    }


def main():
    df = pd.read_parquet(PARQUET)
    per_patient = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        result = _analyze_controller(pdf, pid)
        if result:
            per_patient[pid] = result
            print(f"  Patient {pid}: R²={result['r2_predictability']}, "
                  f"ratio={result['mean_ratio']:.2f}±{result['std_ratio']:.2f}, "
                  f"period={result['peak_period_h']}h, "
                  f"ζ={result['damping_ratio']}")
        else:
            print(f"  Patient {pid}: insufficient data")

    patients_with_data = {k: v for k, v in per_patient.items() if v.get("r2_predictability") is not None}

    # --- H1: Predictability ---
    r2_vals = [v["r2_predictability"] for v in patients_with_data.values()]
    mean_r2 = float(np.mean(r2_vals)) if r2_vals else np.nan
    print(f"\n=== H1: Controller predictability ===")
    print(f"  Mean R² = {mean_r2:.3f} (n={len(r2_vals)} patients)")
    for pid, v in sorted(patients_with_data.items()):
        print(f"    {pid}: R²={v['r2_predictability']}")
    h1_pass = not np.isnan(mean_r2) and mean_r2 > 0.3
    print(f"  → {'PASS' if h1_pass else 'FAIL'}")

    # --- H2: Oscillation period ---
    periods = [v["peak_period_h"] for v in patients_with_data.values() if v.get("peak_period_h") is not None]
    mean_period = float(np.mean(periods)) if periods else np.nan
    print(f"\n=== H2: Oscillation period ===")
    print(f"  Mean period = {mean_period:.2f}h (n={len(periods)} patients)")
    for pid, v in sorted(patients_with_data.items()):
        print(f"    {pid}: {v.get('peak_period_h')}h")
    h2_pass = not np.isnan(mean_period) and 1.0 <= mean_period <= 3.0
    print(f"  → {'PASS' if h2_pass else 'FAIL'}")

    # --- H3: Damping ratio variation ---
    dampings = [v["damping_ratio"] for v in patients_with_data.values() if v.get("damping_ratio") is not None]
    if len(dampings) >= 2:
        damping_range = max(dampings) / min(dampings) if min(dampings) > 0 else np.nan
    else:
        damping_range = np.nan
    print(f"\n=== H3: Damping ratio variation ===")
    print(f"  Range: {min(dampings) if dampings else 'N/A':.3f} to {max(dampings) if dampings else 'N/A':.3f}")
    print(f"  Ratio: {damping_range:.1f}×")
    for pid, v in sorted(patients_with_data.items()):
        print(f"    {pid}: ζ={v.get('damping_ratio')}")
    h3_pass = not np.isnan(damping_range) and damping_range > 2
    print(f"  → {'PASS' if h3_pass else 'FAIL'}")

    # --- H4: Ringing amplitude ↔ glucose CV ---
    ratio_cvs = [v["ratio_cv_pct"] for v in patients_with_data.values() if v.get("ratio_cv_pct") is not None and v.get("glucose_cv_pct") is not None]
    glucose_cvs = [v["glucose_cv_pct"] for v in patients_with_data.values() if v.get("ratio_cv_pct") is not None and v.get("glucose_cv_pct") is not None]
    r_ringing, p_ringing = sp_stats.pearsonr(ratio_cvs, glucose_cvs) if len(ratio_cvs) > 3 else (np.nan, np.nan)

    print(f"\n=== H4: Controller ringing ↔ glucose CV ===")
    print(f"  r = {r_ringing:.3f}, p = {p_ringing:.4f} (n={len(ratio_cvs)} patients)")
    h4_pass = not np.isnan(r_ringing) and r_ringing > 0.3
    print(f"  → {'PASS' if h4_pass else 'FAIL'}")

    results = {
        "experiment": "EXP-2638",
        "title": "Controller Behavior Prediction — Can We Model the AID Instead of Physiology?",
        "n_patients": len(per_patient),
        "hypotheses": {
            "H1": {
                "statement": "Controller ratio predictable from (glucose, IOB, ROC) R² > 0.3",
                "result": "PASS" if h1_pass else "FAIL",
                "mean_r2": round(mean_r2, 3) if not np.isnan(mean_r2) else None,
            },
            "H2": {
                "statement": "Oscillation period detectable at 1-3h",
                "result": "PASS" if h2_pass else "FAIL",
                "mean_period_h": round(mean_period, 2) if not np.isnan(mean_period) else None,
            },
            "H3": {
                "statement": "Damping ratio varies >2× across patients",
                "result": "PASS" if h3_pass else "FAIL",
                "damping_range": round(damping_range, 1) if not np.isnan(damping_range) else None,
            },
            "H4": {
                "statement": "Controller ringing ↔ glucose CV (r > 0.3)",
                "result": "PASS" if h4_pass else "FAIL",
                "r": round(r_ringing, 3) if not np.isnan(r_ringing) else None,
                "p_value": round(p_ringing, 4) if not np.isnan(p_ringing) else None,
            },
        },
        "per_patient": per_patient,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    main()
