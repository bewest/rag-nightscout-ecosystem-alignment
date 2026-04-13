#!/usr/bin/env python3
"""EXP-2634: Model Comparison — What Best Explains Post-Correction Recovery?

BUILDS ON:
  - EXP-2624: Nadir at ~3.5h, recovery slope ~16.8 mg/dL/hr (N=212)
  - EXP-2541: DIA=6h confirmed for 16/19 patients (predictive DIA ≠ pharmacodynamic)
  - EXP-2627: 48h carb window optimal for metabolic state
  - EXP-2629: Hill EGP under-predicts recovery by 2.1×
  - EXP-2630: Forces are coupled, not additive (sum=34, actual=4.1)
  - EXP-2633: Naive EGP addition HURTS prediction by 17.5%

QUESTION: EGP is one theory for post-correction recovery. What model actually
best explains the data? Recovery could be:
  1. NULL: Glucose stays at nadir (baseline)
  2. MEAN-REVERSION: Glucose drifts toward equilibrium (~120 mg/dL)
  3. IOB-DECAY: As insulin wears off (6h DIA, biexp), glucose rises
  4. HILL-EGP: Hepatic production inversely related to IOB
  5. PHASE-ISF: ISF effectiveness changes by phase (demand/recovery)

METHODOLOGY: Uses EXACT EXP-2624 correction detection (verified 212 events):
  - Bolus ≥ 0.5U, no carbs > 2g in ±1h, no prior bolus in 2h (SMB filter)
  - Pre-BG ≥ 120 mg/dL, glucose must drop ≥ 10 mg/dL
  - Nadir search: 4h, recovery fit: 2h post-nadir
  - DIA = 6h (validated), peak = 75min (rapid-acting)

HYPOTHESES:
  H1: IOB-decay model (6h biexp DIA) outperforms Hill EGP (RMSE improvement > 10%)
      Rationale: DIA=6h confirmed. Recovery may simply be insulin wearing off.
  H2: Mean-reversion explains > 20% of recovery variance (R² > 0.2)
      Rationale: Glucose has known equilibrium. Simpler model may suffice.
  H3: Best model captures < 50% of variance (R² < 0.5)
      Rationale: Post-correction dynamics are inherently noisy (AID coupling,
      meals, counter-regulation). No single-factor model should dominate.
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = ROOT / "externals" / "experiments" / "exp-2634_model_comparison.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Validated parameters
STEPS_PER_HOUR = 12
MIN_BOLUS_U = 0.5
MAX_CARBS_WINDOW_G = 2.0    # ±1h, matching EXP-2624
PRE_WINDOW_STEPS = 6        # 30 min
POST_WINDOW_STEPS = 72      # 6h (full DIA window)
NADIR_SEARCH_STEPS = 48     # 4h
RECOVERY_FIT_STEPS = 24     # 2h post-nadir
MIN_DROP_MGDL = 10          # validated threshold
STACKING_WINDOW = 24        # 2h — filters SMBs and stacked corrections

# Insulin model (validated: DIA=6h, peak=75min)
DIA_MIN = 360
PEAK_MIN = 75

# Hill parameters (metabolic_engine.py)
HILL_N = 1.5
HILL_K = 2.0
BASE_EGP_PER_5MIN = 1.5  # mg/dL per 5-min step

# Biexponential DIA (validated EXP-2525/2534: fast τ=0.8h 63%, slow τ=12h 37%)
BIEXP_FAST_TAU = 0.8    # hours
BIEXP_FAST_FRAC = 0.63
BIEXP_SLOW_TAU = 12.0   # hours
BIEXP_SLOW_FRAC = 0.37

# Mean-reversion equilibrium (from overnight baseline analysis)
EQUILIBRIUM_BG = 120.0   # mg/dL


def _exponential_iob(t_min, dia=DIA_MIN, peak=PEAK_MIN):
    """Fraction of insulin remaining at time t (standard exponential model)."""
    if t_min <= 0:
        return 1.0
    if t_min >= dia:
        return 0.0
    tau = peak * (1 - peak / dia) / (1 - 2 * peak / dia)
    a = 2 * tau / dia
    S = 1 / (1 - a + (1 + a) * np.exp(-dia / tau))
    iob_frac = 1 - S * (1 - a) * (
        (t_min**2 / (tau * dia * (1 - a)) - t_min / tau - 1) * np.exp(-t_min / tau) + 1
    )
    return max(0, min(1, iob_frac))


def _biexp_iob(t_hr):
    """Biexponential IOB: fast (τ=0.8h) + slow (τ=12h) component."""
    fast = BIEXP_FAST_FRAC * np.exp(-t_hr / BIEXP_FAST_TAU)
    slow = BIEXP_SLOW_FRAC * np.exp(-t_hr / BIEXP_SLOW_TAU)
    return fast + slow


def _hill_egp(iob):
    """Hill equation EGP rate (mg/dL per 5-min step)."""
    if iob <= 0 or np.isnan(iob):
        return BASE_EGP_PER_5MIN
    suppression = iob**HILL_N / (iob**HILL_N + HILL_K**HILL_N)
    return BASE_EGP_PER_5MIN * (1.0 - suppression)


def _extract_corrections(pdf):
    """Extract correction events using EXACT EXP-2624 methodology.

    Key filters that were MISSING from Round 2:
    - No prior bolus within 2h (SMB & stacking filter)
    - Minimum 10 mg/dL glucose drop
    - Smoothed nadir detection with 15-min rolling window
    """
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    n = len(glucose)
    events = []

    for i in range(PRE_WINDOW_STEPS, n - POST_WINDOW_STEPS):
        if bolus[i] < MIN_BOLUS_U:
            continue

        # No carbs in ±1h (12 steps) — EXP-2624 exact
        carb_window = carbs[max(0, i - 12):min(n, i + 12)]
        if np.nansum(carb_window) > MAX_CARBS_WINDOW_G:
            continue

        # No prior bolus within 2h — CRITICAL SMB/stacking filter
        prior_bolus = bolus[max(0, i - STACKING_WINDOW):i]
        if np.nansum(prior_bolus) > 0.1:
            continue

        # Pre-correction glucose
        pre_window = glucose[i - PRE_WINDOW_STEPS:i]
        valid_pre = ~np.isnan(pre_window)
        if valid_pre.sum() < 3:
            continue
        pre_bg = float(np.nanmean(pre_window))
        if pre_bg < 120:
            continue

        # Post-correction trajectory
        post = glucose[i:i + POST_WINDOW_STEPS].copy()
        valid_post = ~np.isnan(post)
        if valid_post.sum() < POST_WINDOW_STEPS // 2:
            continue

        # Smoothed nadir detection (15-min rolling, matching EXP-2624)
        smoothed = pd.Series(post).rolling(3, center=True, min_periods=1).mean().values
        nadir_search = smoothed[:NADIR_SEARCH_STEPS]
        valid_nadir = ~np.isnan(nadir_search)
        if valid_nadir.sum() < 6:
            continue

        nadir_idx = int(np.nanargmin(nadir_search))
        nadir_bg = float(nadir_search[nadir_idx])
        drop = pre_bg - nadir_bg

        if drop < MIN_DROP_MGDL:
            continue

        # IOB trajectory
        iob_post = iob[i:i + POST_WINDOW_STEPS].copy()

        # Recovery segment (2h post-nadir)
        rec_start = nadir_idx
        rec_end = min(nadir_idx + RECOVERY_FIT_STEPS, len(post))
        recovery = post[rec_start:rec_end]
        valid_rec = ~np.isnan(recovery)
        if valid_rec.sum() < 6:
            continue

        # Fit recovery slope
        x_rec = np.arange(valid_rec.sum()) * 5 / 60  # hours
        y_rec = recovery[valid_rec]
        if len(x_rec) >= 6:
            slope, intercept, r, p, se = sp_stats.linregress(x_rec, y_rec)
        else:
            slope = np.nan

        events.append({
            "index": i,
            "pre_bg": pre_bg,
            "nadir_bg": nadir_bg,
            "nadir_idx": nadir_idx,
            "nadir_hours": nadir_idx * 5 / 60,
            "drop_mgdl": drop,
            "bolus_u": float(bolus[i]),
            "iob_at_bolus": float(iob[i]),
            "iob_at_nadir": float(iob_post[nadir_idx]) if nadir_idx < len(iob_post) else np.nan,
            "recovery_slope": float(slope),
            "post_glucose": post.tolist(),
            "post_iob": iob_post.tolist(),
            "hour_of_day": float(pd.to_datetime(pdf.iloc[i]["time"]).hour +
                                 pd.to_datetime(pdf.iloc[i]["time"]).minute / 60),
        })

    return events


def _predict_null(nadir_bg, n_steps):
    """Model 0: Null — glucose stays at nadir."""
    return np.full(n_steps, nadir_bg)


def _predict_mean_reversion(nadir_bg, n_steps, tau_hr=3.0):
    """Model 1: Mean-reversion toward equilibrium BG.

    dG/dt = (EQUILIBRIUM - G) / tau
    """
    pred = np.full(n_steps, nadir_bg)
    for s in range(1, n_steps):
        dt_hr = 5 / 60  # 5-min steps
        pred[s] = pred[s - 1] + (EQUILIBRIUM_BG - pred[s - 1]) * dt_hr / tau_hr
    return pred


def _predict_iob_decay(nadir_bg, bolus_u, iob_at_nadir, nadir_idx, isf, n_steps):
    """Model 2: IOB decay — glucose rises as IOB wears off.

    Uses validated 6h DIA exponential model.
    As IOB decreases, the "missing insulin effect" raises glucose.
    """
    pred = np.full(n_steps, nadir_bg)
    for s in range(1, n_steps):
        t_from_nadir_min = s * 5
        # IOB at this point after nadir (using standard exponential decay)
        t_from_bolus_min = (nadir_idx + s) * 5
        iob_now = bolus_u * _exponential_iob(t_from_bolus_min)
        iob_prev = bolus_u * _exponential_iob(t_from_bolus_min - 5)
        # Insulin wearing off → glucose rises
        delta_iob = iob_prev - iob_now  # positive when insulin is wearing off
        pred[s] = pred[s - 1] + delta_iob * isf
    return pred


def _predict_biexp_decay(nadir_bg, bolus_u, nadir_idx, isf, n_steps):
    """Model 3: Biexponential IOB decay (fast τ=0.8h + slow τ=12h).

    Uses validated two-component model from EXP-2525/2534.
    """
    pred = np.full(n_steps, nadir_bg)
    for s in range(1, n_steps):
        t_from_bolus_hr = (nadir_idx + s) * 5 / 60
        t_prev_hr = (nadir_idx + s - 1) * 5 / 60
        iob_now = bolus_u * _biexp_iob(t_from_bolus_hr)
        iob_prev = bolus_u * _biexp_iob(t_prev_hr)
        delta_iob = iob_prev - iob_now
        pred[s] = pred[s - 1] + delta_iob * isf
    return pred


def _predict_hill_egp(nadir_bg, iob_trajectory, n_steps):
    """Model 4: Hill EGP — hepatic production suppressed by IOB.

    EGP rate at each step depends on current IOB via Hill equation.
    """
    pred = np.full(n_steps, nadir_bg)
    for s in range(1, n_steps):
        iob_now = iob_trajectory[s] if s < len(iob_trajectory) else 0
        egp_rate = _hill_egp(iob_now)  # mg/dL per 5-min step
        pred[s] = pred[s - 1] + egp_rate
    return pred


def _score_model(actual, predicted):
    """Compute RMSE and R² for model fit."""
    valid = ~np.isnan(actual) & ~np.isnan(predicted)
    if valid.sum() < 6:
        return np.nan, np.nan
    a = actual[valid]
    p = predicted[valid]
    rmse = float(np.sqrt(np.mean((a - p) ** 2)))
    ss_res = np.sum((a - p) ** 2)
    ss_tot = np.sum((a - np.mean(a)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return rmse, r2


def run():
    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)

    all_events = []
    model_scores = {m: {"rmse": [], "r2": []} for m in
                    ["null", "mean_reversion", "iob_decay", "biexp_decay", "hill_egp"]}
    per_patient = {}

    for pid in FULL_PATIENTS:
        dp = df[df["patient_id"] == pid].copy().reset_index(drop=True)
        if len(dp) == 0:
            continue

        events = _extract_corrections(dp)
        if not events:
            print(f"  Patient {pid}: 0 correction events")
            per_patient[pid] = {"n_events": 0}
            continue

        # Patient ISF (from scheduled_isf column)
        isf = dp["scheduled_isf"].dropna().median()
        if np.isnan(isf) or isf <= 0:
            isf = 50  # safe fallback

        p_scores = {m: {"rmse": [], "r2": []} for m in model_scores}

        for ev in events:
            nadir_idx = ev["nadir_idx"]
            nadir_bg = ev["nadir_bg"]
            bolus_u = ev["bolus_u"]
            iob_at_nadir = ev["iob_at_nadir"]

            # Recovery segment
            post_glucose = np.array(ev["post_glucose"])
            post_iob = np.array(ev["post_iob"])
            rec_start = nadir_idx
            rec_end = min(nadir_idx + RECOVERY_FIT_STEPS, len(post_glucose))
            actual_recovery = post_glucose[rec_start:rec_end]
            n_rec = len(actual_recovery)

            if n_rec < 6:
                continue

            # IOB trajectory from nadir onward
            iob_from_nadir = post_iob[rec_start:rec_end] if rec_end <= len(post_iob) else post_iob[rec_start:]

            # Generate predictions (all from nadir onward)
            preds = {
                "null": _predict_null(nadir_bg, n_rec),
                "mean_reversion": _predict_mean_reversion(nadir_bg, n_rec),
                "iob_decay": _predict_iob_decay(nadir_bg, bolus_u, iob_at_nadir,
                                                 nadir_idx, isf, n_rec),
                "biexp_decay": _predict_biexp_decay(nadir_bg, bolus_u, nadir_idx,
                                                     isf, n_rec),
                "hill_egp": _predict_hill_egp(nadir_bg, iob_from_nadir, n_rec),
            }

            for m_name, pred in preds.items():
                rmse, r2 = _score_model(actual_recovery, pred)
                if not np.isnan(rmse):
                    p_scores[m_name]["rmse"].append(rmse)
                    p_scores[m_name]["r2"].append(r2)
                    model_scores[m_name]["rmse"].append(rmse)
                    model_scores[m_name]["r2"].append(r2)

        # Per-patient summary
        p_summary = {"n_events": len(events)}
        for m_name in p_scores:
            if p_scores[m_name]["rmse"]:
                p_summary[f"{m_name}_rmse"] = float(np.mean(p_scores[m_name]["rmse"]))
                p_summary[f"{m_name}_r2"] = float(np.mean(p_scores[m_name]["r2"]))

        per_patient[pid] = p_summary
        n = len(events)
        print(f"  Patient {pid}: {n} corrections ({n / max(1, (dp['time'].max() - dp['time'].min()).days):.1f}/day)")

        all_events.extend(events)

    # === Model Comparison ===
    print(f"\nTotal corrections: {len(all_events)}")
    print(f"\n{'Model':<20} {'RMSE':>8} {'R²':>8} {'N':>6}")
    print("-" * 44)

    model_summary = {}
    for m_name in ["null", "mean_reversion", "iob_decay", "biexp_decay", "hill_egp"]:
        rmses = model_scores[m_name]["rmse"]
        r2s = model_scores[m_name]["r2"]
        if rmses:
            rmse_mean = np.mean(rmses)
            r2_mean = np.mean(r2s)
            model_summary[m_name] = {
                "rmse_mean": float(rmse_mean),
                "rmse_std": float(np.std(rmses)),
                "r2_mean": float(r2_mean),
                "r2_std": float(np.std(r2s)),
                "n": len(rmses),
            }
            print(f"  {m_name:<18} {rmse_mean:>8.1f} {r2_mean:>8.3f} {len(rmses):>6}")

    # === Hypothesis Tests ===
    print("\n=== HYPOTHESIS TESTS ===\n")

    # H1: IOB-decay outperforms Hill EGP (RMSE improvement > 10%)
    if "iob_decay" in model_summary and "hill_egp" in model_summary:
        iob_rmse = model_summary["iob_decay"]["rmse_mean"]
        hill_rmse = model_summary["hill_egp"]["rmse_mean"]
        h1_improvement = (hill_rmse - iob_rmse) / hill_rmse
        h1_pass = h1_improvement > 0.10
        print(f"H1: IOB-decay vs Hill EGP")
        print(f"    IOB-decay RMSE = {iob_rmse:.1f}, Hill RMSE = {hill_rmse:.1f}")
        print(f"    Improvement = {h1_improvement:.1%}")
        print(f"    → {'PASS' if h1_pass else 'FAIL'}")
    else:
        h1_improvement = np.nan
        h1_pass = False

    # H2: Mean-reversion R² > 0.2
    if "mean_reversion" in model_summary:
        mr_r2 = model_summary["mean_reversion"]["r2_mean"]
        h2_pass = mr_r2 > 0.2
        print(f"\nH2: Mean-reversion R²")
        print(f"    R² = {mr_r2:.3f}")
        print(f"    → {'PASS' if h2_pass else 'FAIL'}")
    else:
        mr_r2 = np.nan
        h2_pass = False

    # H3: Best model R² < 0.5 (inherently noisy)
    best_r2 = max(ms["r2_mean"] for ms in model_summary.values()) if model_summary else np.nan
    best_model = max(model_summary, key=lambda m: model_summary[m]["r2_mean"]) if model_summary else "none"
    h3_pass = best_r2 < 0.5
    print(f"\nH3: Best model R² < 0.5 (noisy system)")
    print(f"    Best = {best_model} with R² = {best_r2:.3f}")
    print(f"    → {'PASS' if h3_pass else 'FAIL'}")

    # === Summary ===
    summary = {
        "experiment": "EXP-2634",
        "title": "Model Comparison — What Best Explains Post-Correction Recovery?",
        "methodology": "EXP-2624 exact (bolus≥0.5U, carbs<2g/±1h, no stacking/2h, BG≥120, drop≥10)",
        "n_events": len(all_events),
        "n_patients": sum(1 for v in per_patient.values() if v["n_events"] > 0),
        "validated_priors": {
            "DIA": "6h (EXP-2541: 16/19 patients)",
            "nadir": "~3.5h (EXP-2624)",
            "48h_carbs": "optimal window (EXP-2627)",
            "biexp_DIA": "fast τ=0.8h 63% + slow τ=12h 37% (EXP-2525/2534)",
            "Hill_params": "n=1.5, K=2.0U, base=1.5 mg/dL/5min",
        },
        "hypotheses": {
            "H1": {
                "statement": "IOB-decay outperforms Hill EGP (RMSE improvement > 10%)",
                "result": "PASS" if h1_pass else "FAIL",
                "improvement_pct": float(h1_improvement * 100) if not np.isnan(h1_improvement) else None,
            },
            "H2": {
                "statement": "Mean-reversion R² > 0.2",
                "result": "PASS" if h2_pass else "FAIL",
                "r2": float(mr_r2) if not np.isnan(mr_r2) else None,
            },
            "H3": {
                "statement": "Best model R² < 0.5 (inherent noise)",
                "result": "PASS" if h3_pass else "FAIL",
                "best_model": best_model,
                "best_r2": float(best_r2) if not np.isnan(best_r2) else None,
            },
        },
        "model_summary": model_summary,
        "per_patient": per_patient,
    }

    os.makedirs(OUT.parent, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    run()
