#!/usr/bin/env python3
"""EXP-2629: Per-Patient Hill EGP Fitting & ODC Validation.

MOTIVATION: The metabolic engine uses a single Hill equation for all patients:
  suppression = IOB^1.5 / (IOB^1.5 + 2.0^1.5)
  EGP = base_rate × (1 - suppression) × circadian(hour)

But EXP-2624/2626 showed per-patient recovery rates ranging 4.7-44.8 mg/dL/hr
(10× variation!), suggesting hill_n, hill_k, and base_egp vary by patient.

This experiment:
1. Fits per-patient Hill parameters from correction events (NS patients)
2. Validates overnight drift findings on ODC patients with full telemetry
3. Tests the "overfull" hypothesis: extreme high-carb accumulation → sticky hypers
4. Characterizes the distribution of EGP parameters across 12 patients

HYPOTHESES:
H1: Per-patient Hill K (half-max IOB) varies ≥2× across patients
    (different insulin sensitivity of hepatic suppression)
H2: Overnight drift findings replicate in ODC patients: IOB@midnight
    predicts drift better than 48h carbs
H3: "Sticky hyper" events (>180 for ≥3h) have a distinct EGP signature:
    higher IOB but LOWER effective suppression (Hill curve flattened)
H4: Per-patient Hill fit improves correction prediction vs population fit
    (RMSE reduction ≥15% for ≥50% of patients)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2629_hill_fitting.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL

# Population Hill parameters (from metabolic_engine.py)
POP_HILL_N = 1.5
POP_HILL_K = 2.0
POP_BASE_EGP = 1.5  # mg/dL per 5-min = 18 mg/dL/hr

STEPS_PER_HOUR = 12
DIA_DEFAULT = 6.0  # hours


def hill_suppression(iob, hill_n, hill_k):
    """Hill equation suppression fraction (0 to 1)."""
    iob_safe = np.maximum(np.asarray(iob, dtype=np.float64), 0.0)
    k_safe = max(float(hill_k), 0.01)
    n = float(hill_n)
    num = np.power(iob_safe, n)
    den = num + k_safe ** n
    return np.where(den > 0, num / den, 0.0)


def egp_rate(iob, base_egp, hill_n, hill_k):
    """EGP rate in mg/dL per 5-min given IOB and Hill params."""
    return base_egp * (1.0 - hill_suppression(iob, hill_n, hill_k))


def _extract_fasting_windows(pdf, min_hours=2.0):
    """Extract fasting windows: no carbs, stable IOB, valid glucose.

    These are the cleanest observations of EGP vs IOB relationship.
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    glucose = pdf["glucose"].values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)

    min_steps = int(min_hours * STEPS_PER_HOUR)
    windows = []
    i = 0

    while i < len(pdf) - min_steps:
        # Find start of fasting window: no carbs and no bolus
        if carbs[i] > 0.5 or bolus[i] > 0.3 or np.isnan(glucose[i]):
            i += 1
            continue

        # Extend window while fasting continues
        j = i + 1
        while j < len(pdf) and carbs[j] <= 0.5 and bolus[j] <= 0.3:
            j += 1

        if j - i >= min_steps:
            seg_g = glucose[i:j]
            seg_iob = iob[i:j]
            valid = ~np.isnan(seg_g) & ~np.isnan(seg_iob)
            if valid.sum() >= min_steps:
                # Glucose rate of change (mg/dL per 5-min)
                g_roc = np.diff(seg_g[valid]) / 1.0  # per 5-min step
                iob_mid = (seg_iob[valid][:-1] + seg_iob[valid][1:]) / 2.0

                for k in range(len(g_roc)):
                    if not np.isnan(g_roc[k]):
                        windows.append({
                            "glucose_roc": float(g_roc[k]),
                            "iob": float(iob_mid[k]),
                            "glucose": float(seg_g[valid][k]),
                        })
        i = j

    return windows


def _fit_hill_params(windows):
    """Fit Hill parameters (base_egp, hill_n, hill_k) from fasting windows.

    Model: glucose_roc = base_egp × (1 - suppression(IOB)) - demand_offset
    During fasting, glucose_roc ≈ EGP(IOB) - basal_insulin_effect
    We fit: glucose_roc = A × (1 - IOB^n / (IOB^n + K^n)) + B

    A = base EGP rate (mg/dL per 5-min)
    B = offset (basal insulin effect, should be negative)
    n = Hill coefficient
    K = half-max IOB
    """
    iob = np.array([w["iob"] for w in windows])
    roc = np.array([w["glucose_roc"] for w in windows])

    def model(params, iob):
        A, n, K, B = params
        n = max(n, 0.3)
        K = max(K, 0.1)
        A = max(A, 0.01)
        iob_safe = np.maximum(iob, 0.0)
        num = np.power(iob_safe, n)
        den = num + K ** n
        supp = np.where(den > 0, num / den, 0.0)
        return A * (1.0 - supp) + B

    def residuals(params):
        pred = model(params, iob)
        return roc - pred

    # Initial guesses
    x0 = [POP_BASE_EGP, POP_HILL_N, POP_HILL_K, -1.0]
    bounds = ([0.1, 0.3, 0.1, -10], [5.0, 5.0, 15.0, 5.0])

    try:
        result = optimize.least_squares(residuals, x0, bounds=bounds,
                                        method='trf', max_nfev=5000)
        A, n, K, B = result.x
        n = max(n, 0.3)
        K = max(K, 0.1)
        A = max(A, 0.01)

        pred = model(result.x, iob)
        ss_res = np.sum((roc - pred) ** 2)
        ss_tot = np.sum((roc - np.mean(roc)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        rmse = float(np.sqrt(np.mean((roc - pred) ** 2)))

        # Population model comparison
        pop_pred = POP_BASE_EGP * (1.0 - hill_suppression(iob, POP_HILL_N, POP_HILL_K)) - 1.0
        pop_rmse = float(np.sqrt(np.mean((roc - pop_pred) ** 2)))

        return {
            "base_egp": float(A),
            "base_egp_hr": float(A * 12),  # convert to mg/dL/hr
            "hill_n": float(n),
            "hill_k": float(K),
            "offset": float(B),
            "r2": float(r2),
            "rmse": float(rmse),
            "pop_rmse": float(pop_rmse),
            "rmse_improvement_pct": float((pop_rmse - rmse) / pop_rmse * 100) if pop_rmse > 0 else 0,
            "n_points": len(windows),
        }
    except Exception as e:
        return {"error": str(e), "n_points": len(windows)}


def _overnight_drift_vs_iob(pdf):
    """Replicate overnight drift analysis (IOB@midnight vs drift)."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    pdf["hour"] = t.dt.hour
    pdf["date"] = t.dt.date

    carbs_col = pdf["carbs"].fillna(0).values
    iob_col = pdf["iob"].fillna(0).values

    # 48h carb accumulator
    cum = np.cumsum(carbs_col)
    c48 = np.zeros(len(pdf))
    s48 = 48 * STEPS_PER_HOUR
    for i in range(len(pdf)):
        c48[i] = cum[i] - (cum[max(0, i - s48)] if i >= s48 else 0)

    rows = []
    for date in sorted(pdf["date"].unique()):
        night = pdf[(pdf["date"] == date) & (pdf["hour"] >= 0) & (pdf["hour"] < 6)]
        if len(night) < 36:
            continue
        ng = night["glucose"].dropna()
        if len(ng) < 20:
            continue
        nc = float(night["carbs"].fillna(0).sum())
        nb = float(night["bolus"].fillna(0).sum())
        if nc > 2 or nb > 0.5:
            continue

        slope = float(np.polyfit(np.arange(len(ng)) * (5 / 60), ng.values, 1)[0])
        pos = pdf.index.get_loc(night.index[0])
        iob_mn = float(iob_col[pos]) if pos < len(iob_col) else 0
        carbs_48h = float(c48[pos])

        rows.append({"drift": slope, "iob_midnight": iob_mn, "carbs_48h": carbs_48h})

    if len(rows) < 5:
        return None

    rdf = pd.DataFrame(rows)
    r_iob, p_iob = stats.pearsonr(rdf["iob_midnight"], rdf["drift"])
    r_carb, p_carb = stats.pearsonr(rdf["carbs_48h"], rdf["drift"])

    return {
        "n_nights": len(rows),
        "drift_mean": float(rdf["drift"].mean()),
        "drift_std": float(rdf["drift"].std()),
        "r_iob_drift": float(r_iob),
        "p_iob_drift": float(p_iob),
        "r_carbs_drift": float(r_carb),
        "p_carbs_drift": float(p_carb),
        "iob_better_than_carbs": bool(abs(r_iob) > abs(r_carb)),
    }


def _sticky_hyper_analysis(pdf):
    """Analyze EGP signature during sticky hyper episodes."""
    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)

    # Find sticky hyper runs (>180 for ≥3h)
    above = glucose > 180
    runs = []
    start = None
    for i in range(len(above)):
        if above[i] and not np.isnan(glucose[i]):
            if start is None:
                start = i
        else:
            if start is not None and (i - start) >= 36:
                runs.append((start, i))
            start = None

    if len(runs) < 5:
        return None

    # For each sticky hyper: measure effective suppression
    # If Hill model is right, at high IOB, glucose should still be dropping
    # If glucose is flat or rising despite high IOB, suppression is "stuck"
    sticky_iob = []
    sticky_roc = []
    for s, e in runs:
        seg_iob = iob[s:e]
        seg_g = glucose[s:e]
        valid = ~np.isnan(seg_g) & ~np.isnan(seg_iob)
        if valid.sum() < 12:
            continue
        mean_iob = float(np.mean(seg_iob[valid]))
        # glucose rate during the episode (should be negative if insulin working)
        if valid.sum() >= 6:
            t_hrs = np.arange(valid.sum()) * (5.0 / 60.0)
            slope = float(np.polyfit(t_hrs, seg_g[valid], 1)[0])
        else:
            slope = np.nan
        sticky_iob.append(mean_iob)
        sticky_roc.append(slope)

    sticky_iob = np.array(sticky_iob)
    sticky_roc = np.array(sticky_roc)
    valid_mask = ~np.isnan(sticky_roc)

    if valid_mask.sum() < 5:
        return None

    si = sticky_iob[valid_mask]
    sr = sticky_roc[valid_mask]

    # Expected glucose roc from population Hill model
    expected_roc = POP_BASE_EGP * (1.0 - hill_suppression(si, POP_HILL_N, POP_HILL_K)) * 12 - 18
    # The -18 is approximate basal insulin effect in mg/dL/hr

    # Compare: positive residual = glucose falling less than expected = "stuck"
    residual = sr - expected_roc

    # In-range comparison: sample normal IOB range
    inrange = (glucose >= 70) & (glucose <= 180) & (~np.isnan(glucose))
    normal_iob = float(np.mean(iob[inrange])) if inrange.sum() > 0 else 0

    return {
        "n_episodes": len(runs),
        "n_analyzed": int(valid_mask.sum()),
        "sticky_iob_mean": float(np.mean(si)),
        "sticky_iob_median": float(np.median(si)),
        "sticky_roc_mean": float(np.mean(sr)),
        "sticky_roc_median": float(np.median(sr)),
        "normal_iob_mean": normal_iob,
        "pct_positive_roc": float((sr > 0).mean() * 100),
        "expected_roc_mean": float(np.mean(expected_roc)),
        "residual_mean": float(np.mean(residual)),
    }


def main():
    print("=" * 70)
    print("EXP-2629: Per-Patient Hill EGP Fitting & ODC Validation")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    # ── Part 1: Per-patient Hill fitting ─────────────────────────────
    print("\n" + "=" * 70)
    print("PART 1: PER-PATIENT HILL CURVE FITTING")
    print("=" * 70)

    hill_fits = {}
    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 7:
            continue

        windows = _extract_fasting_windows(pdf)
        if len(windows) < 50:
            print(f"  {pid}: only {len(windows)} fasting points, skip fitting")
            continue

        fit = _fit_hill_params(windows)
        hill_fits[pid] = fit

        if "error" in fit:
            print(f"  {pid}: fitting error: {fit['error']}")
        else:
            print(f"  {pid}: base_egp={fit['base_egp_hr']:.1f} mg/dL/hr, "
                  f"n={fit['hill_n']:.2f}, K={fit['hill_k']:.1f}U, "
                  f"R²={fit['r2']:.3f}, RMSE improvement={fit['rmse_improvement_pct']:+.1f}%")

    results["hill_fits"] = hill_fits

    # Distribution analysis
    fitted = {k: v for k, v in hill_fits.items() if "error" not in v}
    if len(fitted) >= 3:
        hill_ks = [v["hill_k"] for v in fitted.values()]
        hill_ns = [v["hill_n"] for v in fitted.values()]
        base_egps = [v["base_egp_hr"] for v in fitted.values()]

        print(f"\n  Hill K distribution: {np.min(hill_ks):.1f} – {np.max(hill_ks):.1f}U "
              f"(range {np.max(hill_ks)/np.min(hill_ks):.1f}×)")
        print(f"  Hill n distribution: {np.min(hill_ns):.2f} – {np.max(hill_ns):.2f}")
        print(f"  Base EGP distribution: {np.min(base_egps):.1f} – {np.max(base_egps):.1f} mg/dL/hr")

        results["hill_distribution"] = {
            "k_min": float(np.min(hill_ks)),
            "k_max": float(np.max(hill_ks)),
            "k_ratio": float(np.max(hill_ks) / np.min(hill_ks)),
            "n_min": float(np.min(hill_ns)),
            "n_max": float(np.max(hill_ns)),
            "base_egp_min": float(np.min(base_egps)),
            "base_egp_max": float(np.max(base_egps)),
            "n_patients_fitted": len(fitted),
        }

    # ── Part 2: ODC validation ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("PART 2: ODC OVERNIGHT DRIFT VALIDATION")
    print("=" * 70)

    drift_results = {}
    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            continue
        dr = _overnight_drift_vs_iob(pdf)
        if dr is None:
            continue
        drift_results[pid] = dr
        marker = "ODC" if pid.startswith("odc") else "NS"
        iob_win = "✓" if dr["iob_better_than_carbs"] else "✗"
        print(f"  [{marker}] {pid}: {dr['n_nights']} nights, "
              f"IOB→drift r={dr['r_iob_drift']:.3f}, "
              f"carbs→drift r={dr['r_carbs_drift']:.3f}, "
              f"IOB better: {iob_win}")

    results["drift_validation"] = drift_results

    # Count how many ODC patients confirm IOB > carbs
    odc_confirmed = sum(1 for k, v in drift_results.items()
                        if k.startswith("odc") and v["iob_better_than_carbs"])
    odc_total = sum(1 for k in drift_results if k.startswith("odc"))
    print(f"\n  ODC confirmation: {odc_confirmed}/{odc_total} patients confirm IOB > carbs")

    # ── Part 3: Sticky hyper analysis ────────────────────────────────
    print("\n" + "=" * 70)
    print("PART 3: STICKY HYPER EGP SIGNATURE")
    print("=" * 70)

    sticky_results = {}
    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 7:
            continue
        sr = _sticky_hyper_analysis(pdf)
        if sr is None:
            continue
        sticky_results[pid] = sr
        print(f"  {pid}: {sr['n_episodes']} episodes, "
              f"IOB={sr['sticky_iob_mean']:.1f}U (vs normal {sr['normal_iob_mean']:.1f}U), "
              f"glucose roc={sr['sticky_roc_mean']:+.1f} mg/dL/hr, "
              f"{sr['pct_positive_roc']:.0f}% still rising")

    results["sticky_hypers"] = sticky_results

    # ── Part 4: Hypothesis testing ───────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # H1: Hill K varies ≥2× across patients
    if "hill_distribution" in results:
        h1_pass = results["hill_distribution"]["k_ratio"] >= 2.0
        print(f"\n  H1: Hill K varies ≥2× across patients")
        print(f"      Range: {results['hill_distribution']['k_min']:.1f} – "
              f"{results['hill_distribution']['k_max']:.1f}U "
              f"({results['hill_distribution']['k_ratio']:.1f}×)")
        print(f"      → {'PASS' if h1_pass else 'FAIL'}")
    else:
        h1_pass = False
        print(f"\n  H1: SKIP (insufficient fits)")

    # H2: IOB@midnight predicts drift better than carbs in ODC patients
    h2_pass = odc_confirmed > 0 and odc_confirmed >= odc_total / 2
    print(f"\n  H2: IOB@midnight better than carbs for ODC patients")
    print(f"      {odc_confirmed}/{odc_total} confirm")
    print(f"      → {'PASS' if h2_pass else 'FAIL'}")

    # H3: Sticky hypers have distinct EGP signature
    if sticky_results:
        pct_rising = [v["pct_positive_roc"] for v in sticky_results.values()]
        mean_pct_rising = np.mean(pct_rising)
        h3_pass = mean_pct_rising >= 40  # ≥40% of time glucose still rising
        print(f"\n  H3: Sticky hypers show glucose rising despite high IOB")
        print(f"      Mean % time rising: {mean_pct_rising:.0f}%")
        print(f"      → {'PASS' if h3_pass else 'FAIL'}")
    else:
        h3_pass = False

    # H4: Per-patient fit improves RMSE ≥15% for ≥50% of patients
    if fitted:
        improvements = [v["rmse_improvement_pct"] for v in fitted.values()]
        pct_improved = sum(1 for i in improvements if i >= 15) / len(improvements) * 100
        h4_pass = pct_improved >= 50
        print(f"\n  H4: Per-patient Hill fit improves RMSE ≥15% for ≥50% of patients")
        print(f"      Improvements: {[f'{i:.0f}%' for i in sorted(improvements, reverse=True)]}")
        print(f"      {pct_improved:.0f}% of patients improved ≥15%")
        print(f"      → {'PASS' if h4_pass else 'FAIL'}")
    else:
        h4_pass = False

    results["hypotheses"] = {
        "H1_hill_k_varies_2x": {"pass": bool(h1_pass)},
        "H2_odc_iob_better": {"pass": bool(h2_pass),
                               "odc_confirmed": odc_confirmed,
                               "odc_total": odc_total},
        "H3_sticky_egp_signature": {"pass": bool(h3_pass)},
        "H4_personal_fit_improves": {"pass": bool(h4_pass)},
    }

    # ── Settings implications ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PER-PATIENT EGP PARAMETER IMPLICATIONS")
    print("=" * 70)

    for pid in sorted(fitted.keys()):
        f = fitted[pid]
        k_ratio = f["hill_k"] / POP_HILL_K
        n_ratio = f["hill_n"] / POP_HILL_N
        egp_ratio = f["base_egp_hr"] / (POP_BASE_EGP * 12)

        # At typical correction IOB (2U), what's the suppression difference?
        pop_supp = hill_suppression(2.0, POP_HILL_N, POP_HILL_K)
        pers_supp = hill_suppression(2.0, f["hill_n"], f["hill_k"])

        basal_implication = "increase" if egp_ratio > 1.15 else \
                            "decrease" if egp_ratio < 0.85 else "adequate"
        isf_implication = "lower" if pers_supp < pop_supp - 0.1 else \
                          "higher" if pers_supp > pop_supp + 0.1 else "adequate"

        print(f"\n  {pid}:")
        print(f"    EGP base: {f['base_egp_hr']:.1f} mg/dL/hr "
              f"({egp_ratio:.2f}× population)")
        print(f"    Hill K: {f['hill_k']:.1f}U ({k_ratio:.2f}× pop) — "
              f"{'easier' if k_ratio < 0.8 else 'harder' if k_ratio > 1.2 else 'normal'} "
              f"to suppress")
        print(f"    Suppression@2U: personal={pers_supp:.0%} vs pop={pop_supp:.0%}")
        print(f"    → Basal: {basal_implication}, ISF: {isf_implication}")

    # ── Save ─────────────────────────────────────────────────────────
    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
