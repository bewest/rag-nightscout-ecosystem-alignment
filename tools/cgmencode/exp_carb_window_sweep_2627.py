#!/usr/bin/env python3
"""EXP-2627: Optimal Carb History Window for EGP/Drift Prediction.

MOTIVATION: EXP-2622 showed 48h carbs → overnight drift r=-0.303, better
than 24h (r=-0.193). User asks: is 72h even more informative? Glycogen
repletion cycles are 10-72h; gluconeogenesis adaptation may need longer
windows. But longer windows also dilute signal with stale data.

APPROACH:
Sweep carb accumulation windows from 12h to 120h (5 days) in 6h steps,
plus glycogen exponential accumulators with τ from 12h to 96h.
For each window, compute correlation with overnight drift.
Report optimal window and diminishing returns boundary.

HYPOTHESES:
H1: 72h window has r² ≥ 0.01 higher than 48h (72h is meaningfully better)
H2: Optimal window is between 48-96h (glycogen timescale, not meal memory)
H3: Exponential accumulator (any τ) outperforms rectangular window at the
    optimal timescale (decay weighting > equal weighting)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2627_carb_window_sweep.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
STEPS_PER_HOUR = 12

# Window sweep: 12h to 120h in 6h increments
WINDOW_HOURS = list(range(12, 126, 6))  # 12, 18, 24, ..., 120

# Exponential tau sweep: 12h to 96h in 6h increments
TAU_HOURS = list(range(12, 102, 6))


def _extract_nights(pdf):
    """Extract clean overnight windows (00-06h, no carbs/bolus)."""
    pdf = pdf.sort_values("time").copy()
    t = pd.to_datetime(pdf["time"])
    pdf["hour"] = t.dt.hour
    pdf["date"] = t.dt.date

    dates = sorted(pdf["date"].unique())
    nights = []

    for date in dates:
        mask = (pdf["date"] == date) & (pdf["hour"] >= 0) & (pdf["hour"] < 6)
        night = pdf[mask]
        if len(night) < 36:  # need ≥3h
            continue

        gluc = night["glucose"].values
        valid = ~np.isnan(gluc)
        if valid.sum() < 36:
            continue

        # Check contamination
        if float(night["carbs"].fillna(0).sum()) > 2.0:
            continue
        if float(night["bolus"].fillna(0).sum()) > 0.5:
            continue

        # Drift rate
        t_hrs = np.arange(len(gluc)) * (5.0 / 60.0)
        slope, _ = np.polyfit(t_hrs[valid], gluc[valid], 1)

        # Position in full dataframe for lookback
        pos = pdf.index.get_loc(night.index[0])

        nights.append({
            "date": str(date),
            "drift_rate": float(slope),
            "pos": pos,
        })

    return nights


def _compute_rectangular_carbs(pdf, nights, window_hours):
    """Sum carbs in rectangular window before each night."""
    carbs_col = pdf["carbs"].fillna(0).values.astype(np.float64)
    steps = int(window_hours * STEPS_PER_HOUR)
    result = []
    for n in nights:
        start = max(0, n["pos"] - steps)
        result.append(float(carbs_col[start:n["pos"]].sum()))
    return np.array(result)


def _compute_exponential_carbs(pdf, nights, tau_hours):
    """Exponential accumulator of carbs with given tau."""
    carbs_col = pdf["carbs"].fillna(0).values.astype(np.float64)
    tau_steps = tau_hours * STEPS_PER_HOUR
    decay = 1.0 - 1.0 / max(tau_steps, 1)

    # Build full accumulator
    accum = np.zeros(len(carbs_col))
    for i in range(1, len(carbs_col)):
        accum[i] = accum[i - 1] * decay + carbs_col[i]

    result = []
    for n in nights:
        pos = n["pos"]
        result.append(float(accum[pos]) if pos < len(accum) else 0.0)
    return np.array(result)


def main():
    print("=" * 70)
    print("EXP-2627: Optimal Carb History Window for EGP/Drift Prediction")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)

    # Collect all nights across patients
    all_nights = []
    all_pdfs = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 7:
            continue
        nights = _extract_nights(pdf)
        if len(nights) < 10:
            continue
        all_pdfs[pid] = pdf
        for n in nights:
            n["patient"] = pid
        all_nights.extend(nights)
        print(f"  Patient {pid}: {len(nights)} clean nights")

    print(f"\n  Total pooled nights: {len(all_nights)}")
    drifts = np.array([n["drift_rate"] for n in all_nights])

    # ── Rectangular window sweep ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("RECTANGULAR WINDOW SWEEP")
    print("=" * 70)

    rect_results = []
    for wh in WINDOW_HOURS:
        # Compute per-patient, then pool
        all_carbs = []
        for pid, pdf in all_pdfs.items():
            p_nights = [n for n in all_nights if n["patient"] == pid]
            c = _compute_rectangular_carbs(pdf, p_nights, wh)
            all_carbs.extend(c)
        all_carbs = np.array(all_carbs)

        r, p = stats.pearsonr(all_carbs, drifts) if len(all_carbs) >= 10 else (np.nan, np.nan)
        r2 = r ** 2 if not np.isnan(r) else np.nan
        rect_results.append({
            "window_hours": wh,
            "r": float(r) if not np.isnan(r) else None,
            "r2": float(r2) if not np.isnan(r2) else None,
            "p": float(p) if not np.isnan(p) else None,
        })
        marker = " ←" if wh in [24, 48, 72] else ""
        print(f"  {wh:3d}h: r={r:.4f}  R²={r2:.4f}  p={p:.4f}{marker}")

    # ── Exponential tau sweep ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("EXPONENTIAL ACCUMULATOR SWEEP")
    print("=" * 70)

    exp_results = []
    for th in TAU_HOURS:
        all_accum = []
        for pid, pdf in all_pdfs.items():
            p_nights = [n for n in all_nights if n["patient"] == pid]
            c = _compute_exponential_carbs(pdf, p_nights, th)
            all_accum.extend(c)
        all_accum = np.array(all_accum)

        r, p = stats.pearsonr(all_accum, drifts) if len(all_accum) >= 10 else (np.nan, np.nan)
        r2 = r ** 2 if not np.isnan(r) else np.nan
        exp_results.append({
            "tau_hours": th,
            "r": float(r) if not np.isnan(r) else None,
            "r2": float(r2) if not np.isnan(r2) else None,
            "p": float(p) if not np.isnan(p) else None,
        })
        marker = " ←" if th in [24, 48, 72] else ""
        print(f"  τ={th:3d}h: r={r:.4f}  R²={r2:.4f}  p={p:.4f}{marker}")

    # ── Per-patient optimal windows ──────────────────────────────────
    print("\n" + "=" * 70)
    print("PER-PATIENT OPTIMAL WINDOWS")
    print("=" * 70)

    per_patient = {}
    for pid, pdf in all_pdfs.items():
        p_nights = [n for n in all_nights if n["patient"] == pid]
        p_drifts = np.array([n["drift_rate"] for n in p_nights])
        if len(p_drifts) < 10:
            continue

        best_rect_r2 = -1
        best_rect_wh = None
        for wh in WINDOW_HOURS:
            c = _compute_rectangular_carbs(pdf, p_nights, wh)
            r, _ = stats.pearsonr(c, p_drifts)
            if r ** 2 > best_rect_r2:
                best_rect_r2 = r ** 2
                best_rect_wh = wh

        best_exp_r2 = -1
        best_exp_tau = None
        for th in TAU_HOURS:
            c = _compute_exponential_carbs(pdf, p_nights, th)
            r, _ = stats.pearsonr(c, p_drifts)
            if r ** 2 > best_exp_r2:
                best_exp_r2 = r ** 2
                best_exp_tau = th

        # Get 48h and 72h for comparison
        c48 = _compute_rectangular_carbs(pdf, p_nights, 48)
        r48, _ = stats.pearsonr(c48, p_drifts)
        c72 = _compute_rectangular_carbs(pdf, p_nights, 72)
        r72, _ = stats.pearsonr(c72, p_drifts)

        per_patient[pid] = {
            "n_nights": len(p_nights),
            "best_rect_window_h": best_rect_wh,
            "best_rect_r2": float(best_rect_r2),
            "best_exp_tau_h": best_exp_tau,
            "best_exp_r2": float(best_exp_r2),
            "r_48h": float(r48),
            "r2_48h": float(r48 ** 2),
            "r_72h": float(r72),
            "r2_72h": float(r72 ** 2),
            "r2_improvement_72_vs_48": float(r72 ** 2 - r48 ** 2),
        }
        print(f"  Patient {pid}: best rect={best_rect_wh}h (R²={best_rect_r2:.4f}), "
              f"best exp τ={best_exp_tau}h (R²={best_exp_r2:.4f}), "
              f"48h R²={r48**2:.4f}, 72h R²={r72**2:.4f}, Δ={r72**2 - r48**2:+.4f}")

    # ── Hypothesis testing ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # Find pooled 48h and 72h values
    r2_48 = next(r["r2"] for r in rect_results if r["window_hours"] == 48)
    r2_72 = next(r["r2"] for r in rect_results if r["window_hours"] == 72)
    best_rect = max(rect_results, key=lambda x: x["r2"] or 0)
    best_exp = max(exp_results, key=lambda x: x["r2"] or 0)

    h1_delta = r2_72 - r2_48
    h1_pass = h1_delta >= 0.01
    print(f"\n  H1: 72h R² improvement ≥ 0.01 over 48h")
    print(f"      48h R² = {r2_48:.4f}, 72h R² = {r2_72:.4f}, Δ = {h1_delta:+.4f}")
    print(f"      → {'PASS' if h1_pass else 'FAIL'}")

    h2_pass = 48 <= best_rect["window_hours"] <= 96
    print(f"\n  H2: Optimal window between 48-96h")
    print(f"      Best rectangular: {best_rect['window_hours']}h (R²={best_rect['r2']:.4f})")
    print(f"      → {'PASS' if h2_pass else 'FAIL'}")

    h3_pass = (best_exp["r2"] or 0) > (best_rect["r2"] or 0)
    print(f"\n  H3: Exponential accumulator outperforms rectangular")
    print(f"      Best rectangular: {best_rect['window_hours']}h R²={best_rect['r2']:.4f}")
    print(f"      Best exponential: τ={best_exp['tau_hours']}h R²={best_exp['r2']:.4f}")
    print(f"      → {'PASS' if h3_pass else 'FAIL'}")

    # ── Save results ─────────────────────────────────────────────────
    results = {
        "experiment": "EXP-2627",
        "title": "Optimal Carb History Window for EGP/Drift Prediction",
        "n_nights": len(all_nights),
        "n_patients": len(all_pdfs),
        "rectangular_sweep": rect_results,
        "exponential_sweep": exp_results,
        "per_patient": per_patient,
        "hypotheses": {
            "H1_72h_better_than_48h": {
                "pass": h1_pass,
                "r2_48h": r2_48,
                "r2_72h": r2_72,
                "delta": h1_delta,
            },
            "H2_optimal_48_96h": {
                "pass": h2_pass,
                "best_window_hours": best_rect["window_hours"],
                "best_r2": best_rect["r2"],
            },
            "H3_exponential_better": {
                "pass": h3_pass,
                "best_rect_r2": best_rect["r2"],
                "best_exp_r2": best_exp["r2"],
                "best_exp_tau": best_exp["tau_hours"],
            },
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
