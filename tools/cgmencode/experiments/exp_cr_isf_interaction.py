#!/usr/bin/env python3
"""
exp_cr_isf_interaction.py — CR × ISF Nonlinearity Interaction (EXP-2537a–d)

Two independent nonlinearities have been discovered:
  1. ISF power-law (EXP-2511): ISF(dose) = ISF_base × dose^(-0.9).
     Larger boluses are LESS effective per unit.
  2. CR nonlinearity (EXP-2535): BG rise/gram DECREASES with meal size
     (5.50→0.59 mg/dL/g). Larger meals produce LESS BG rise per gram.

These go in OPPOSITE directions for meal boluses:
  - Larger meal → less BG rise per gram  (helps)
  - Larger bolus → less BG drop per unit (hurts)

Key question: do they cancel, or does one dominate?

Experiments:
  EXP-2537a: Net meal outcome by size — excursion, 4h delta, TIR by meal bin
  EXP-2537b: Predicted vs actual BG change — linear model error by meal size
  EXP-2537c: Optimal nonlinear correction — fit combined power-law model
  EXP-2537d: Clinical sweet spot — find meal size with best outcomes

Data columns (grid.parquet):
  glucose, carbs, bolus, bolus_smb, cob, iob, scheduled_cr, scheduled_isf

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_cr_isf_interaction.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_cr_isf_interaction.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "externals" / "experiments"

# ── Constants ────────────────────────────────────────────────────────

MERGE_WINDOW_MIN = 30       # Merge carb entries within this window
POST_MEAL_HOURS = 4         # Post-meal observation window
ROWS_PER_HOUR = 12          # 5-minute intervals
TIR_LOW = 70
TIR_HIGH = 180
MIN_MEALS = 5               # Minimum meals to include patient

MEAL_SIZE_BINS = {
    "small":      (0,   20),
    "medium":     (20,  50),
    "large":      (50, 100),
    "xl":         (100, float("inf")),
}


# ── Data Loading ─────────────────────────────────────────────────────

def load_data(tiny: bool = False) -> pd.DataFrame:
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    df["manual_bolus"] = (df["bolus"] - df["bolus_smb"]).clip(lower=0)
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


# ── Meal Extraction ─────────────────────────────────────────────────

def extract_meals(pdf: pd.DataFrame, patient_id: str) -> list[dict]:
    """Extract meal events for one patient.

    Merges nearby carb entries (within MERGE_WINDOW_MIN), captures
    pre-meal BG, post-meal trajectory, bolus, carbs, profile settings,
    and computes excursion/TIR metrics.
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    carb_idx = pdf.index[pdf["carbs"] > 0].tolist()
    if not carb_idx:
        return []

    # Group nearby carb entries into meal events
    groups: list[list[int]] = [[carb_idx[0]]]
    for idx in carb_idx[1:]:
        prev = groups[-1][-1]
        gap_min = (pdf.loc[idx, "time"] - pdf.loc[prev, "time"]).total_seconds() / 60
        if gap_min <= MERGE_WINDOW_MIN:
            groups[-1].append(idx)
        else:
            groups.append([idx])

    meals = []
    n_rows = len(pdf)
    post_rows = POST_MEAL_HOURS * ROWS_PER_HOUR  # 48 rows = 4h

    for grp in groups:
        start_idx = grp[0]
        end_idx = grp[-1]

        total_carbs = float(pdf.loc[grp, "carbs"].sum())
        if total_carbs < 1:
            continue

        pre_bg = pdf.loc[start_idx, "glucose"]
        if np.isnan(pre_bg):
            continue

        # Bolus window: 15 min before to 30 min after last carb entry
        bolus_start = max(0, start_idx - 3)
        bolus_end = min(n_rows - 1, end_idx + 6)
        manual_bolus = float(pdf.loc[bolus_start:bolus_end, "manual_bolus"].sum())
        total_bolus = float(pdf.loc[bolus_start:bolus_end, "bolus"].sum())

        profile_cr = float(pdf.loc[start_idx, "scheduled_cr"])
        profile_isf = float(pdf.loc[start_idx, "scheduled_isf"])
        pre_iob = float(pdf.loc[start_idx, "iob"])

        # Post-meal glucose trajectory
        post_end = min(n_rows - 1, start_idx + post_rows)
        post_glucose = pdf.loc[start_idx:post_end, "glucose"].values
        if len(post_glucose) < ROWS_PER_HOUR:
            continue
        valid_glucose = post_glucose[~np.isnan(post_glucose)]
        if len(valid_glucose) < 6:
            continue

        peak_bg = float(np.nanmax(post_glucose))
        peak_idx_rel = int(np.nanargmax(post_glucose))
        peak_time_min = peak_idx_rel * 5

        # BG at specific timepoints
        bg_at = {}
        for h in [1, 2, 3, 4]:
            idx_h = start_idx + h * ROWS_PER_HOUR
            if idx_h < n_rows:
                val = pdf.loc[idx_h, "glucose"]
                bg_at[f"bg_{h}h"] = float(val) if not np.isnan(val) else None
            else:
                bg_at[f"bg_{h}h"] = None

        # TIR at each hour window
        tir_at = {}
        for h in [1, 2, 3, 4]:
            end_h = min(n_rows - 1, start_idx + h * ROWS_PER_HOUR)
            window_g = pdf.loc[start_idx:end_h, "glucose"].dropna().values
            if len(window_g) > 0:
                in_range = ((window_g >= TIR_LOW) & (window_g <= TIR_HIGH)).mean()
                tir_at[f"tir_{h}h"] = float(in_range)
            else:
                tir_at[f"tir_{h}h"] = None

        # Meal size category
        size_cat = "xl"
        for cat, (lo, hi) in MEAL_SIZE_BINS.items():
            if lo <= total_carbs < hi:
                size_cat = cat
                break

        # Net 4h BG change
        bg_4h = bg_at.get("bg_4h")
        net_4h = (bg_4h - float(pre_bg)) if bg_4h is not None else None

        meals.append({
            "patient_id": patient_id,
            "total_carbs": total_carbs,
            "size_category": size_cat,
            "manual_bolus": manual_bolus,
            "total_bolus": total_bolus,
            "profile_cr": profile_cr,
            "profile_isf": profile_isf,
            "pre_bg": float(pre_bg),
            "pre_iob": pre_iob,
            "peak_bg": peak_bg,
            "peak_time_min": peak_time_min,
            "bg_rise": peak_bg - float(pre_bg),
            "net_4h": net_4h,
            **bg_at,
            **tir_at,
        })

    return meals


def extract_all_meals(df: pd.DataFrame) -> list[dict]:
    """Extract meals across all patients."""
    all_meals = []
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        meals = extract_meals(pdf, pid)
        all_meals.extend(meals)
    return all_meals


# ── EXP-2537a: Net Meal Outcome by Size ─────────────────────────────

def exp_2537a_net_meal_outcome(meals: list[dict]) -> dict:
    """Compare post-meal outcomes across meal size categories."""
    print("=" * 70)
    print("EXP-2537a: Net Meal Outcome by Size")
    print("=" * 70)

    bolused = [m for m in meals if m["manual_bolus"] > 0.1 and m["net_4h"] is not None]
    print(f"Analysing {len(bolused)} bolused meals with 4h follow-up\n")

    if not bolused:
        print("  ✗ No bolused meals with follow-up")
        return {"error": "no_bolused_meals"}

    # Header
    print(f"{'Category':<10} {'N':>5}  {'MeanCarbs':>9} {'MeanBolus':>10} "
          f"{'Bol/g':>6}  {'Excursion':>9} {'Rise/g':>7}  "
          f"{'Net4h':>7} {'Net4h/g':>8}  {'TIR2h':>6} {'TIR4h':>6}")
    print("-" * 105)

    size_results = {}
    cat_rise_per_g = {}

    for cat in MEAL_SIZE_BINS:
        cm = [m for m in bolused if m["size_category"] == cat]
        if not cm:
            size_results[cat] = {"n": 0}
            continue

        carbs = np.array([m["total_carbs"] for m in cm])
        boluses = np.array([m["manual_bolus"] for m in cm])
        rises = np.array([m["bg_rise"] for m in cm])
        nets = np.array([m["net_4h"] for m in cm])
        tir2 = np.array([m["tir_2h"] for m in cm if m.get("tir_2h") is not None])
        tir4 = np.array([m["tir_4h"] for m in cm if m.get("tir_4h") is not None])

        mc = float(np.mean(carbs))
        mb = float(np.mean(boluses))
        bpg = mb / max(mc, 1)
        mr = float(np.mean(rises))
        rpg = mr / max(mc, 1)
        mn = float(np.mean(nets))
        npg = mn / max(mc, 1)
        mt2 = float(np.mean(tir2) * 100) if len(tir2) else float("nan")
        mt4 = float(np.mean(tir4) * 100) if len(tir4) else float("nan")

        cat_rise_per_g[cat] = rpg

        print(f"{cat:<10} {len(cm):>5}  {mc:>9.1f} {mb:>10.2f} "
              f"{bpg:>6.3f}  {mr:>9.1f} {rpg:>7.2f}  "
              f"{mn:>+7.1f} {npg:>+8.3f}  {mt2:>5.1f}% {mt4:>5.1f}%")

        size_results[cat] = {
            "n": len(cm),
            "mean_carbs": round(mc, 1),
            "mean_bolus": round(mb, 2),
            "bolus_per_gram": round(bpg, 4),
            "mean_excursion": round(mr, 1),
            "rise_per_gram": round(rpg, 3),
            "mean_net_4h": round(mn, 1),
            "net_4h_per_gram": round(npg, 4),
            "tir_2h_pct": round(mt2, 1),
            "tir_4h_pct": round(mt4, 1),
            "excursion_std": round(float(np.std(rises)), 1),
            "net_4h_std": round(float(np.std(nets)), 1),
        }

    # Interpretation
    rpg_vals = [(c, v) for c, v in cat_rise_per_g.items() if v is not None]
    if len(rpg_vals) >= 2:
        first_rpg = rpg_vals[0][1]
        last_rpg = rpg_vals[-1][1]
        if abs(first_rpg) > 0.01:
            ratio = last_rpg / first_rpg
        else:
            ratio = 1.0

        net4_by_cat = {c: size_results[c].get("mean_net_4h", 0)
                       for c in MEAL_SIZE_BINS if size_results.get(c, {}).get("n", 0) > 0}
        net4_vals = list(net4_by_cat.values())
        net4_range = max(net4_vals) - min(net4_vals) if net4_vals else 0

        if net4_range < 15:
            verdict = "CANCEL"
            detail = (f"Net 4h outcomes span only {net4_range:.0f} mg/dL across "
                      f"size bins — nonlinearities largely cancel")
        elif last_rpg < first_rpg * 0.7:
            verdict = "CR_DOMINATES"
            detail = (f"Rise/g drops {ratio:.2f}× from smallest to largest — "
                      f"CR nonlinearity dominates (larger meals easier)")
        else:
            verdict = "ISF_DOMINATES"
            detail = (f"Rise/g ratio={ratio:.2f}× but net 4h worsens — "
                      f"ISF nonlinearity dominates (larger meals harder)")

        print(f"\n  Verdict: {verdict}")
        print(f"  {detail}")
    else:
        verdict = "INSUFFICIENT_DATA"
        detail = "Not enough size categories with data"
        ratio = None

    print()
    return {
        "n_meals": len(bolused),
        "size_results": size_results,
        "verdict": verdict,
        "detail": detail,
        "rise_per_gram_ratio_xl_vs_small": round(ratio, 3) if ratio is not None else None,
    }


# ── EXP-2537b: Predicted vs Actual BG Change ────────────────────────

def exp_2537b_prediction_error(meals: list[dict]) -> dict:
    """Compare linear model predictions vs actual outcomes by meal size.

    Linear model:
      predicted_rise = carbs × ISF / CR  (expected BG rise from carbs)
      predicted_drop = bolus × ISF       (expected BG drop from insulin)
      predicted_net  = predicted_rise - predicted_drop
    """
    print("=" * 70)
    print("EXP-2537b: Linear Model Prediction Error by Meal Size")
    print("=" * 70)

    valid = [m for m in meals
             if m["manual_bolus"] > 0.1
             and m["net_4h"] is not None
             and not np.isnan(m["profile_isf"])
             and not np.isnan(m["profile_cr"])
             and m["profile_cr"] > 0]

    print(f"Analysing {len(valid)} meals with complete data\n")
    if not valid:
        return {"error": "no_valid_meals"}

    for m in valid:
        isf = m["profile_isf"]
        cr = m["profile_cr"]
        m["predicted_rise"] = m["total_carbs"] * isf / cr
        m["predicted_drop"] = m["manual_bolus"] * isf
        m["predicted_net"] = m["predicted_rise"] - m["predicted_drop"]
        m["prediction_error"] = m["net_4h"] - m["predicted_net"]

    print(f"{'Category':<10} {'N':>5}  {'PredRise':>8} {'PredDrop':>8} "
          f"{'PredNet':>8} {'ActNet':>8}  {'MeanErr':>8} {'MAE':>7}  "
          f"{'Bias':>10}")
    print("-" * 95)

    size_results = {}
    for cat in MEAL_SIZE_BINS:
        cm = [m for m in valid if m["size_category"] == cat]
        if not cm:
            size_results[cat] = {"n": 0}
            continue

        pred_rise = np.array([m["predicted_rise"] for m in cm])
        pred_drop = np.array([m["predicted_drop"] for m in cm])
        pred_net = np.array([m["predicted_net"] for m in cm])
        act_net = np.array([m["net_4h"] for m in cm])
        errors = np.array([m["prediction_error"] for m in cm])

        me = float(np.mean(errors))
        mae = float(np.mean(np.abs(errors)))

        if me > 10:
            bias_desc = "under-predicts rise"
        elif me < -10:
            bias_desc = "over-predicts rise"
        else:
            bias_desc = "~balanced"

        print(f"{cat:<10} {len(cm):>5}  {np.mean(pred_rise):>8.1f} "
              f"{np.mean(pred_drop):>8.1f} {np.mean(pred_net):>+8.1f} "
              f"{np.mean(act_net):>+8.1f}  {me:>+8.1f} {mae:>7.1f}  "
              f"{bias_desc:>10}")

        size_results[cat] = {
            "n": len(cm),
            "mean_predicted_rise": round(float(np.mean(pred_rise)), 1),
            "mean_predicted_drop": round(float(np.mean(pred_drop)), 1),
            "mean_predicted_net": round(float(np.mean(pred_net)), 1),
            "mean_actual_net": round(float(np.mean(act_net)), 1),
            "mean_error": round(me, 1),
            "mae": round(mae, 1),
            "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 1),
            "median_error": round(float(np.median(errors)), 1),
            "bias_description": bias_desc,
        }

    # Spearman correlation: meal size vs prediction error
    all_carbs = np.array([m["total_carbs"] for m in valid])
    all_errors = np.array([m["prediction_error"] for m in valid])
    r_carb_err, p_carb_err = spearmanr(all_carbs, all_errors)

    # Spearman: bolus size vs prediction error
    all_bolus = np.array([m["manual_bolus"] for m in valid])
    r_bolus_err, p_bolus_err = spearmanr(all_bolus, all_errors)

    print(f"\nCorrelations:")
    print(f"  meal_size  vs error: Spearman r = {r_carb_err:+.3f} (p = {p_carb_err:.2e})")
    print(f"  bolus_size vs error: Spearman r = {r_bolus_err:+.3f} (p = {p_bolus_err:.2e})")

    if r_carb_err > 0.05 and p_carb_err < 0.05:
        interp = ("Positive: linear model UNDER-predicts rise for large meals → "
                   "ISF nonlinearity dominates (bolus less effective)")
    elif r_carb_err < -0.05 and p_carb_err < 0.05:
        interp = ("Negative: linear model OVER-predicts rise for large meals → "
                   "CR nonlinearity dominates (large meals rise less per gram)")
    else:
        interp = "No significant size-dependent bias → nonlinearities approximately cancel"

    print(f"  Interpretation: {interp}")
    print()

    return {
        "n_meals": len(valid),
        "size_results": size_results,
        "correlations": {
            "meal_size_vs_error": {
                "spearman_r": round(float(r_carb_err), 4),
                "p_value": round(float(p_carb_err), 6),
            },
            "bolus_size_vs_error": {
                "spearman_r": round(float(r_bolus_err), 4),
                "p_value": round(float(p_bolus_err), 6),
            },
        },
        "interpretation": interp,
    }


# ── EXP-2537c: Nonlinear Model Fit ──────────────────────────────────

def exp_2537c_nonlinear_model(meals: list[dict]) -> dict:
    """Fit combined nonlinear model and compare to linear baseline.

    Nonlinear: net = α × carbs^γ - β × bolus^δ + ε
    Linear:    net = α × carbs   - β × bolus   + ε
    """
    print("=" * 70)
    print("EXP-2537c: Nonlinear vs Linear Model Fit")
    print("=" * 70)

    valid = [m for m in meals
             if m["manual_bolus"] > 0.1
             and m["net_4h"] is not None
             and not np.isnan(m.get("net_4h", float("nan")))]

    carbs = np.array([m["total_carbs"] for m in valid], dtype=np.float64)
    bolus = np.array([m["manual_bolus"] for m in valid], dtype=np.float64)
    actual = np.array([m["net_4h"] for m in valid], dtype=np.float64)

    mask = np.isfinite(carbs) & np.isfinite(bolus) & np.isfinite(actual)
    mask &= (carbs > 0) & (bolus > 0)
    carbs, bolus, actual = carbs[mask], bolus[mask], actual[mask]

    n = len(carbs)
    print(f"Fitting on {n} meals with carbs > 0 and bolus > 0\n")

    if n < 20:
        print("  ✗ Too few meals for model fitting")
        return {"error": "insufficient_data", "n": n}

    ss_tot = float(np.sum((actual - np.mean(actual)) ** 2))

    # ── Linear model: net = a*carbs - b*bolus + c ──
    X_lin = np.column_stack([carbs, -bolus, np.ones(n)])
    try:
        theta_lin, res_lin, _, _ = np.linalg.lstsq(X_lin, actual, rcond=None)
        pred_lin = X_lin @ theta_lin
        ss_res_lin = float(np.sum((actual - pred_lin) ** 2))
        r2_lin = 1 - ss_res_lin / max(ss_tot, 1e-9)
        mae_lin = float(np.mean(np.abs(actual - pred_lin)))
    except Exception:
        r2_lin = 0.0
        mae_lin = float(np.std(actual))
        theta_lin = np.array([0, 0, 0])

    print(f"Linear model:    net = {theta_lin[0]:+.2f}×carbs "
          f"- {abs(theta_lin[1]):.2f}×bolus {theta_lin[2]:+.1f}")
    print(f"  R² = {r2_lin:.4f}, MAE = {mae_lin:.1f} mg/dL")

    # ── Nonlinear model: net = α × carbs^γ - β × bolus^δ + ε ──
    def nonlinear_loss(params):
        alpha, gamma, beta, delta, eps = params
        gamma_c = np.clip(gamma, 0.01, 3.0)
        delta_c = np.clip(delta, 0.01, 3.0)
        pred = alpha * np.power(carbs, gamma_c) - beta * np.power(bolus, delta_c) + eps
        return float(np.sum((actual - pred) ** 2))

    best_result = None
    best_loss = float("inf")
    for g0 in [0.5, 0.8, 1.0]:
        for d0 in [0.5, 0.8, 1.0]:
            x0 = [float(theta_lin[0]), g0, abs(float(theta_lin[1])), d0,
                   float(theta_lin[2])]
            try:
                res = minimize(nonlinear_loss, x0, method="Nelder-Mead",
                               options={"maxiter": 10000, "xatol": 1e-6,
                                        "fatol": 1e-6})
                if res.fun < best_loss:
                    best_loss = res.fun
                    best_result = res
            except Exception:
                continue

    if best_result is not None and best_result.success or best_loss < float("inf"):
        alpha, gamma, beta, delta, eps = best_result.x
        gamma = float(np.clip(gamma, 0.01, 3.0))
        delta = float(np.clip(delta, 0.01, 3.0))
        pred_nl = alpha * np.power(carbs, gamma) - beta * np.power(bolus, delta) + eps
        ss_res_nl = float(np.sum((actual - pred_nl) ** 2))
        r2_nl = 1 - ss_res_nl / max(ss_tot, 1e-9)
        mae_nl = float(np.mean(np.abs(actual - pred_nl)))

        print(f"\nNonlinear model: net = {alpha:+.3f}×carbs^{gamma:.3f} "
              f"- {abs(beta):.3f}×bolus^{delta:.3f} {eps:+.1f}")
        print(f"  R² = {r2_nl:.4f}, MAE = {mae_nl:.1f} mg/dL")
        print(f"  R² improvement: {r2_nl - r2_lin:+.4f} "
              f"({(r2_nl - r2_lin) / max(abs(r2_lin), 1e-9) * 100:+.1f}% relative)")

        print(f"\n  Exponents:")
        print(f"    γ (carb) = {gamma:.3f}  {'< 1 → sub-linear absorption (CR nonlinearity confirmed)' if gamma < 0.95 else '≈ 1 → linear' if gamma < 1.05 else '> 1 → super-linear'}")
        print(f"    δ (dose) = {delta:.3f}  {'< 1 → sub-linear action (ISF nonlinearity confirmed)' if delta < 0.95 else '≈ 1 → linear' if delta < 1.05 else '> 1 → super-linear'}")

        # Which nonlinearity is stronger?
        carb_deviation = abs(1.0 - gamma)
        dose_deviation = abs(1.0 - delta)
        if carb_deviation > dose_deviation * 1.3:
            dominance = "CR_NONLINEARITY_STRONGER"
            dom_detail = (f"Carb exponent deviates {carb_deviation:.3f} from linear vs "
                          f"{dose_deviation:.3f} for dose")
        elif dose_deviation > carb_deviation * 1.3:
            dominance = "ISF_NONLINEARITY_STRONGER"
            dom_detail = (f"Dose exponent deviates {dose_deviation:.3f} from linear vs "
                          f"{carb_deviation:.3f} for carbs")
        else:
            dominance = "COMPARABLE"
            dom_detail = (f"Both exponents deviate similarly from linear "
                          f"(carb: {carb_deviation:.3f}, dose: {dose_deviation:.3f})")

        print(f"\n  Dominance: {dominance}")
        print(f"  {dom_detail}")
    else:
        gamma = delta = alpha = beta = eps = float("nan")
        r2_nl = r2_lin
        mae_nl = mae_lin
        dominance = "FIT_FAILED"
        dom_detail = "Nonlinear optimizer did not converge"
        print("  ✗ Nonlinear fit failed to converge")

    # Per-patient fits
    print("\nPer-patient nonlinear fits:")
    print(f"  {'Patient':<20} {'N':>5}  {'γ(carb)':>8} {'δ(dose)':>8}  "
          f"{'R²_lin':>7} {'R²_nl':>7} {'ΔR²':>7}")
    print("  " + "-" * 75)

    patient_fits = {}
    patients = sorted(set(m["patient_id"] for m in valid))
    gammas, deltas = [], []

    for pid in patients:
        pm = [m for m in valid if m["patient_id"] == pid
              and m["total_carbs"] > 0 and m["manual_bolus"] > 0]
        if len(pm) < MIN_MEALS:
            continue

        pc = np.array([m["total_carbs"] for m in pm], dtype=np.float64)
        pb = np.array([m["manual_bolus"] for m in pm], dtype=np.float64)
        pa = np.array([m["net_4h"] for m in pm], dtype=np.float64)

        pmask = np.isfinite(pc) & np.isfinite(pb) & np.isfinite(pa)
        pc, pb, pa = pc[pmask], pb[pmask], pa[pmask]
        if len(pc) < MIN_MEALS:
            continue

        ss_tot_p = float(np.sum((pa - np.mean(pa)) ** 2))
        if ss_tot_p < 1e-6:
            continue

        # Linear
        Xp = np.column_stack([pc, -pb, np.ones(len(pc))])
        try:
            tp, _, _, _ = np.linalg.lstsq(Xp, pa, rcond=None)
            r2_lin_p = 1 - float(np.sum((pa - Xp @ tp) ** 2)) / ss_tot_p
        except Exception:
            r2_lin_p = 0.0

        # Nonlinear
        def loss_p(params):
            a, g, b, d, e = params
            g = np.clip(g, 0.01, 3.0)
            d = np.clip(d, 0.01, 3.0)
            pred = a * np.power(pc, g) - b * np.power(pb, d) + e
            return float(np.sum((pa - pred) ** 2))

        best_p = None
        best_lp = float("inf")
        for g0 in [0.5, 1.0]:
            for d0 in [0.5, 1.0]:
                try:
                    rp = minimize(loss_p, [1.0, g0, 1.0, d0, 0.0],
                                  method="Nelder-Mead",
                                  options={"maxiter": 5000})
                    if rp.fun < best_lp:
                        best_lp = rp.fun
                        best_p = rp
                except Exception:
                    continue

        if best_p is not None:
            _, gp, _, dp, _ = best_p.x
            gp = float(np.clip(gp, 0.01, 3.0))
            dp = float(np.clip(dp, 0.01, 3.0))
            r2_nl_p = 1 - best_lp / max(ss_tot_p, 1e-9)
            gammas.append(gp)
            deltas.append(dp)
            dr2 = r2_nl_p - r2_lin_p

            print(f"  {pid:<20} {len(pc):>5}  {gp:>8.3f} {dp:>8.3f}  "
                  f"{r2_lin_p:>7.4f} {r2_nl_p:>7.4f} {dr2:>+7.4f}")

            patient_fits[pid] = {
                "n": len(pc),
                "gamma": round(gp, 3),
                "delta": round(dp, 3),
                "r2_linear": round(r2_lin_p, 4),
                "r2_nonlinear": round(r2_nl_p, 4),
                "delta_r2": round(dr2, 4),
            }

    if gammas:
        print(f"\n  Population γ (carb):  {np.mean(gammas):.3f} ± {np.std(gammas):.3f}")
        print(f"  Population δ (dose):  {np.mean(deltas):.3f} ± {np.std(deltas):.3f}")

    print()
    return {
        "n_meals": n,
        "linear_model": {
            "coefficients": {
                "carb_coeff": round(float(theta_lin[0]), 4),
                "bolus_coeff": round(float(theta_lin[1]), 4),
                "intercept": round(float(theta_lin[2]), 1),
            },
            "r2": round(r2_lin, 4),
            "mae": round(mae_lin, 1),
        },
        "nonlinear_model": {
            "alpha": round(float(alpha), 4),
            "gamma_carb": round(float(gamma), 3),
            "beta": round(float(beta), 4),
            "delta_dose": round(float(delta), 3),
            "epsilon": round(float(eps), 1),
            "r2": round(float(r2_nl), 4),
            "mae": round(float(mae_nl), 1),
        },
        "r2_improvement": round(float(r2_nl - r2_lin), 4),
        "dominance": dominance,
        "dominance_detail": dom_detail,
        "per_patient": patient_fits,
        "population_gamma": {
            "mean": round(float(np.mean(gammas)), 3) if gammas else None,
            "std": round(float(np.std(gammas)), 3) if gammas else None,
        },
        "population_delta": {
            "mean": round(float(np.mean(deltas)), 3) if deltas else None,
            "std": round(float(np.std(deltas)), 3) if deltas else None,
        },
    }


# ── EXP-2537d: Clinical Sweet Spot ──────────────────────────────────

def exp_2537d_clinical_sweet_spot(meals: list[dict]) -> dict:
    """Find the meal size range where nonlinearities best cancel.

    Uses finer-grained bins (10g increments) to find the TIR and
    outcome sweet spot.
    """
    print("=" * 70)
    print("EXP-2537d: Clinical Sweet Spot Analysis")
    print("=" * 70)

    bolused = [m for m in meals
               if m["manual_bolus"] > 0.1
               and m["net_4h"] is not None
               and m.get("tir_4h") is not None]

    print(f"Analysing {len(bolused)} bolused meals\n")
    if len(bolused) < 20:
        return {"error": "insufficient_data", "n": len(bolused)}

    # Fine-grained bins
    fine_bins = [(0, 15), (15, 30), (30, 50), (50, 75), (75, 100), (100, 150),
                 (150, float("inf"))]
    bin_labels = ["0-15g", "15-30g", "30-50g", "50-75g", "75-100g",
                  "100-150g", "150g+"]

    print(f"{'Bin':<12} {'N':>5}  {'TIR4h':>6} {'TIR2h':>6}  "
          f"{'MeanNet4h':>9} {'|Net4h|':>8}  {'Excursion':>9} {'Rise/g':>7}")
    print("-" * 80)

    bin_results = {}
    best_tir = -1.0
    best_bin = None
    best_abs_net = float("inf")
    easiest_bin = None

    for (lo, hi), label in zip(fine_bins, bin_labels):
        bm = [m for m in bolused if lo <= m["total_carbs"] < hi]
        if len(bm) < 3:
            bin_results[label] = {"n": len(bm)}
            continue

        tir4 = np.array([m["tir_4h"] for m in bm if m.get("tir_4h") is not None])
        tir2 = np.array([m["tir_2h"] for m in bm if m.get("tir_2h") is not None])
        nets = np.array([m["net_4h"] for m in bm])
        rises = np.array([m["bg_rise"] for m in bm])
        carbs_arr = np.array([m["total_carbs"] for m in bm])

        mt4 = float(np.mean(tir4) * 100) if len(tir4) else float("nan")
        mt2 = float(np.mean(tir2) * 100) if len(tir2) else float("nan")
        mn = float(np.mean(nets))
        abs_mn = float(np.mean(np.abs(nets)))
        mr = float(np.mean(rises))
        mc = float(np.mean(carbs_arr))
        rpg = mr / max(mc, 1)

        print(f"{label:<12} {len(bm):>5}  {mt4:>5.1f}% {mt2:>5.1f}%  "
              f"{mn:>+9.1f} {abs_mn:>8.1f}  {mr:>9.1f} {rpg:>7.2f}")

        if mt4 > best_tir and len(bm) >= 5:
            best_tir = mt4
            best_bin = label

        if abs_mn < best_abs_net and len(bm) >= 5:
            best_abs_net = abs_mn
            easiest_bin = label

        bin_results[label] = {
            "n": len(bm),
            "tir_4h_pct": round(mt4, 1),
            "tir_2h_pct": round(mt2, 1),
            "mean_net_4h": round(mn, 1),
            "mean_abs_net_4h": round(abs_mn, 1),
            "mean_excursion": round(mr, 1),
            "rise_per_gram": round(rpg, 3),
            "mean_carbs": round(mc, 1),
        }

    # Determine hardest bin (worst TIR)
    worst_tir = 101.0
    hardest_bin = None
    for label, r in bin_results.items():
        if r.get("n", 0) >= 5 and r.get("tir_4h_pct", 100) < worst_tir:
            worst_tir = r["tir_4h_pct"]
            hardest_bin = label

    # Per-patient sweet spot
    print(f"\nPer-patient best meal size (by TIR):")
    print(f"  {'Patient':<20} {'BestBin':<12} {'TIR':>6}  {'WorstBin':<12} {'TIR':>6}")
    print("  " + "-" * 60)

    patient_sweet = {}
    for pid in sorted(set(m["patient_id"] for m in bolused)):
        pm = [m for m in bolused if m["patient_id"] == pid]
        if len(pm) < MIN_MEALS:
            continue

        pat_best_tir = -1
        pat_best_bin = None
        pat_worst_tir = 101
        pat_worst_bin = None

        for (lo, hi), label in zip(fine_bins, bin_labels):
            bm = [m for m in pm if lo <= m["total_carbs"] < hi]
            if len(bm) < 2:
                continue
            t4 = [m["tir_4h"] for m in bm if m.get("tir_4h") is not None]
            if not t4:
                continue
            mt = float(np.mean(t4) * 100)
            if mt > pat_best_tir:
                pat_best_tir = mt
                pat_best_bin = label
            if mt < pat_worst_tir:
                pat_worst_tir = mt
                pat_worst_bin = label

        if pat_best_bin:
            print(f"  {pid:<20} {pat_best_bin:<12} {pat_best_tir:>5.1f}%  "
                  f"{pat_worst_bin or 'n/a':<12} "
                  f"{pat_worst_tir:>5.1f}%")
            patient_sweet[pid] = {
                "best_bin": pat_best_bin,
                "best_tir_pct": round(pat_best_tir, 1),
                "worst_bin": pat_worst_bin,
                "worst_tir_pct": round(pat_worst_tir, 1),
            }

    print(f"\n  Population sweet spot (best TIR):    {best_bin} ({best_tir:.1f}%)")
    print(f"  Population easiest (lowest |net4h|): {easiest_bin} "
          f"({best_abs_net:.1f} mg/dL)")
    print(f"  Hardest bin (worst TIR):             {hardest_bin} ({worst_tir:.1f}%)")

    # Clinical recommendation
    recs = []
    if best_bin:
        recs.append(f"Meal sizes around {best_bin} achieve the best post-meal TIR "
                    f"({best_tir:.0f}%)")
    if easiest_bin:
        recs.append(f"Meal sizes around {easiest_bin} have the smallest absolute "
                    f"4h BG displacement ({best_abs_net:.0f} mg/dL)")
    if hardest_bin:
        recs.append(f"Meal sizes around {hardest_bin} are hardest to dose correctly "
                    f"(TIR {worst_tir:.0f}%)")

    for i, rec in enumerate(recs, 1):
        print(f"\n  Rec {i}: {rec}")

    print()
    return {
        "n_meals": len(bolused),
        "fine_bin_results": bin_results,
        "sweet_spot": {
            "best_tir_bin": best_bin,
            "best_tir_pct": round(best_tir, 1),
            "easiest_dosing_bin": easiest_bin,
            "easiest_abs_net4h": round(best_abs_net, 1),
            "hardest_bin": hardest_bin,
            "hardest_tir_pct": round(worst_tir, 1) if worst_tir < 101 else None,
        },
        "per_patient": patient_sweet,
        "recommendations": recs,
    }


# ── Summary ──────────────────────────────────────────────────────────

def print_summary(results: dict) -> dict:
    """Print overall conclusions and clinical implications."""
    print("=" * 70)
    print("SUMMARY: CR × ISF Nonlinearity Interaction")
    print("=" * 70)

    conclusions = []

    # EXP-2537a verdict
    a = results.get("exp_2537a", {})
    verdict_a = a.get("verdict", "UNKNOWN")
    conclusions.append(f"Outcome by size: {verdict_a} — {a.get('detail', 'n/a')}")

    # EXP-2537b interpretation
    b = results.get("exp_2537b", {})
    interp_b = b.get("interpretation", "n/a")
    corr = b.get("correlations", {}).get("meal_size_vs_error", {})
    conclusions.append(f"Linear model bias: r={corr.get('spearman_r', 'n/a')}, "
                       f"p={corr.get('p_value', 'n/a')} — {interp_b}")

    # EXP-2537c model comparison
    c = results.get("exp_2537c", {})
    nl = c.get("nonlinear_model", {})
    gamma = nl.get("gamma_carb", 1.0)
    delta = nl.get("delta_dose", 1.0)
    dr2 = c.get("r2_improvement", 0)
    conclusions.append(f"Nonlinear model: γ(carb)={gamma:.3f}, δ(dose)={delta:.3f}, "
                       f"R² improvement={dr2:+.4f}")
    conclusions.append(f"Dominance: {c.get('dominance', 'UNKNOWN')} — "
                       f"{c.get('dominance_detail', 'n/a')}")

    # EXP-2537d sweet spot
    d = results.get("exp_2537d", {})
    ss = d.get("sweet_spot", {})
    if ss.get("best_tir_bin"):
        conclusions.append(f"Sweet spot: {ss['best_tir_bin']} "
                           f"(TIR {ss.get('best_tir_pct', 0):.0f}%)")
    if ss.get("hardest_bin"):
        conclusions.append(f"Hardest: {ss['hardest_bin']} "
                           f"(TIR {ss.get('hardest_tir_pct', 0):.0f}%)")

    # Overall verdict
    if gamma is not None and delta is not None:
        carb_dev = abs(1.0 - gamma)
        dose_dev = abs(1.0 - delta)
        if carb_dev < 0.1 and dose_dev < 0.1:
            overall = "BOTH_LINEAR — neither nonlinearity is clinically significant"
        elif abs(carb_dev - dose_dev) < 0.1:
            overall = "CANCEL — both nonlinearities are present and approximately cancel"
        elif carb_dev > dose_dev:
            overall = ("CR_DOMINATES — carb absorption nonlinearity is stronger; "
                       "larger meals are easier per gram than expected")
        else:
            overall = ("ISF_DOMINATES — insulin action nonlinearity is stronger; "
                       "larger boluses are less effective, making large meals harder")
    else:
        overall = "UNDETERMINED"

    conclusions.append(f"OVERALL: {overall}")

    print()
    for i, c in enumerate(conclusions, 1):
        print(f"  {i}. {c}")

    # Clinical implications
    print(f"\n{'Clinical Implications':}")
    implications = []
    if gamma < 0.95:
        implications.append(
            f"CR nonlinearity (γ={gamma:.2f}): a standard bolus for carbs over-"
            f"estimates the BG rise from large meals. Patients eating > 60g may "
            f"not need proportionally more insulin.")
    if delta < 0.95:
        implications.append(
            f"ISF nonlinearity (δ={delta:.2f}): larger correction boluses have "
            f"diminishing returns. Splitting large corrections may be more effective.")
    if abs(carb_dev - dose_dev) < 0.15:
        implications.append(
            "The two nonlinearities roughly offset each other for typical "
            "meal boluses. Standard linear dosing (carbs/CR) is a reasonable "
            "approximation despite both being individually nonlinear.")
    if ss.get("best_tir_bin") and ss.get("hardest_bin"):
        implications.append(
            f"Dosing accuracy peaks around {ss['best_tir_bin']} meals and is "
            f"worst around {ss['hardest_bin']} meals. Consider tighter monitoring "
            f"for meals in the difficult range.")

    for j, imp in enumerate(implications, 1):
        print(f"  {j}. {imp}")

    print()
    return {
        "conclusions": conclusions,
        "clinical_implications": implications,
        "overall_verdict": overall,
    }


# ── JSON Serialisation ──────────────────────────────────────────────

def convert(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="EXP-2537: CR × ISF Nonlinearity Interaction")
    parser.add_argument("--tiny", action="store_true",
                        help="Use tiny dataset for quick testing")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    print("=" * 70)
    print("EXP-2537: CR × ISF NONLINEARITY INTERACTION")
    print("=" * 70)
    print()

    # Extract meals
    print("Extracting meal events...")
    all_meals = extract_all_meals(df)
    bolused = [m for m in all_meals if m["manual_bolus"] > 0.1]
    print(f"  {len(all_meals)} total meals, {len(bolused)} with manual bolus\n")

    results = {
        "experiment": "EXP-2537",
        "title": "CR × ISF Nonlinearity Interaction",
        "hypothesis": ("Two opposing nonlinearities (sub-linear carb absorption "
                       "and sub-linear insulin action) may cancel, leaving linear "
                       "dosing as a reasonable approximation"),
        "n_patients": df["patient_id"].nunique(),
        "n_meals": len(all_meals),
        "n_bolused_meals": len(bolused),
    }

    results["exp_2537a"] = exp_2537a_net_meal_outcome(all_meals)
    results["exp_2537b"] = exp_2537b_prediction_error(all_meals)
    results["exp_2537c"] = exp_2537c_nonlinear_model(all_meals)
    results["exp_2537d"] = exp_2537d_clinical_sweet_spot(all_meals)
    results["summary"] = print_summary(results)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2537_cr_isf_interaction.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
