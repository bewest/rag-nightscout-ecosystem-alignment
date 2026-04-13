#!/usr/bin/env python3
"""EXP-2637: Phase-Aware Stacking — Do Corrections During Recovery Cause Worse Outcomes?

BUILDS ON:
  - EXP-2624: Nadir at ~3.5h post-correction
  - EXP-2634: ALL recovery models fail (R² < 0) — system is feedback-coupled
  - EXP-2635: Bolus size r=-0.31 with recovery (only significant predictor)
  - EXP-2636: Dose-dependent ISF (running)

QUESTION: AID controllers and users sometimes deliver additional corrections during
the recovery phase (3.5h+). Does this "stacking" worsen outcomes — causing deeper
drops, more oscillation, or worse 6h endpoint glucose? If so, the practical
recommendation is to SUPPRESS corrections during recovery.

DESIGN: Compare two natural populations within our 219 corrections:
  - "Clean" corrections: no additional bolus within 4h post-correction
  - "Stacked" corrections: additional bolus(es) within 4h
Then separately, look at the FIRST correction in each cluster and measure whether
the time since PREVIOUS correction predicts outcome quality.

HYPOTHESES:
  H1: Stacked corrections (any bolus within 4h) have >30% higher glucose CV
      in the 6h window vs clean corrections
  H2: Time since previous correction correlates with 6h endpoint glucose
      (longer gap → closer to target, r > 0.2)
  H3: Clean recoveries reach target (80-120 mg/dL) more often than stacked
      (proportion difference > 15 percentage points)
  H4: Each additional unit of stacked insulin adds >5 mg/dL overshoot
      (glucose drops below nadir more after stacking)
"""
import json, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = ROOT / "externals" / "experiments" / "exp-2637_phase_stacking.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

STEPS_PER_HOUR = 12
MIN_BOLUS_U = 0.5
MAX_CARBS_WINDOW_G = 2.0
PRE_WINDOW_STEPS = 6
POST_WINDOW_STEPS = 72  # 6h
NADIR_SEARCH_STEPS = 48
MIN_DROP_MGDL = 10
STACKING_WINDOW = 24  # 2h pre-filter (EXP-2624)


def _extract_corrections_with_stacking(pdf):
    """Extract corrections AND check for stacking within 4h post-correction."""
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    n = len(glucose)
    events = []

    for i in range(PRE_WINDOW_STEPS, n - POST_WINDOW_STEPS):
        if bolus[i] < MIN_BOLUS_U:
            continue
        carb_window = carbs[max(0, i - 12):min(n, i + 12)]
        if np.nansum(carb_window) > MAX_CARBS_WINDOW_G:
            continue
        prior_bolus = bolus[max(0, i - STACKING_WINDOW):i]
        if np.nansum(prior_bolus) > 0.1:
            continue
        pre_window = glucose[i - PRE_WINDOW_STEPS:i]
        valid_pre = ~np.isnan(pre_window)
        if valid_pre.sum() < 3:
            continue
        pre_bg = float(np.nanmean(pre_window))
        if pre_bg < 120:
            continue
        post = glucose[i:i + POST_WINDOW_STEPS].copy()
        valid_post = ~np.isnan(post)
        if valid_post.sum() < POST_WINDOW_STEPS // 2:
            continue

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

        # Check for stacking: any bolus > 0.1U within 4h (48 steps) AFTER correction
        post_boluses = bolus[i + 1:min(n, i + 48)]
        stacked_total = float(np.nansum(post_boluses[post_boluses > 0.1]))
        n_stacked = int(np.sum(post_boluses > 0.1))
        is_stacked = stacked_total > 0.1

        # Check for carbs in post window (contamination flag)
        post_carbs = carbs[i + 1:min(n, i + POST_WINDOW_STEPS)]
        post_carb_total = float(np.nansum(post_carbs))

        # 6h glucose metrics
        valid_6h = ~np.isnan(post)
        glucose_cv = float(np.nanstd(post) / np.nanmean(post) * 100) if np.nanmean(post) > 0 else np.nan
        bg_6h = float(np.nanmean(post[60:72])) if np.sum(~np.isnan(post[60:72])) >= 3 else np.nan

        # Did glucose reach target (80-120)?
        bg_3h_6h = post[36:72]
        valid_late = ~np.isnan(bg_3h_6h)
        in_target = bool(np.any((bg_3h_6h[valid_late] >= 80) & (bg_3h_6h[valid_late] <= 120))) if valid_late.sum() > 0 else False

        # Post-nadir minimum (did glucose drop BELOW nadir later = overshoot)
        post_nadir_glucose = post[nadir_idx:]
        post_nadir_valid = ~np.isnan(post_nadir_glucose)
        if post_nadir_valid.sum() > 0:
            post_nadir_min = float(np.nanmin(post_nadir_glucose))
            overshoot = nadir_bg - post_nadir_min  # positive = went lower than nadir
        else:
            post_nadir_min = np.nan
            overshoot = np.nan

        # Time since previous correction (look back up to 24h)
        lookback = min(i, 288)  # 24h = 288 steps
        prev_boluses = bolus[i - lookback:i]
        prev_corr_mask = prev_boluses >= MIN_BOLUS_U
        if np.any(prev_corr_mask):
            last_idx = np.where(prev_corr_mask)[0][-1]
            time_since_prev_h = (lookback - last_idx) / STEPS_PER_HOUR
        else:
            time_since_prev_h = np.nan

        events.append({
            "index": int(i),
            "pre_bg": round(pre_bg, 1),
            "nadir_bg": round(nadir_bg, 1),
            "drop": round(drop, 1),
            "bolus_u": round(float(bolus[i]), 2),
            "nadir_time_h": round(nadir_idx / STEPS_PER_HOUR, 2),
            "is_stacked": is_stacked,
            "stacked_insulin_u": round(stacked_total, 2),
            "n_stacked_boluses": n_stacked,
            "post_carbs_g": round(post_carb_total, 1),
            "glucose_cv_pct": round(glucose_cv, 1),
            "bg_6h": round(bg_6h, 1) if not np.isnan(bg_6h) else None,
            "in_target_3h_6h": in_target,
            "overshoot_mgdl": round(overshoot, 1) if not np.isnan(overshoot) else None,
            "time_since_prev_h": round(time_since_prev_h, 2) if not np.isnan(time_since_prev_h) else None,
        })

    return events


def main():
    df = pd.read_parquet(PARQUET)
    all_events = []
    per_patient = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        events = _extract_corrections_with_stacking(pdf)
        for e in events:
            e["patient_id"] = pid
        all_events.extend(events)

        if events:
            n_stacked = sum(1 for e in events if e["is_stacked"])
            per_patient[pid] = {
                "n_events": len(events),
                "n_clean": len(events) - n_stacked,
                "n_stacked": n_stacked,
                "pct_stacked": round(n_stacked / len(events) * 100, 1),
            }

        print(f"  Patient {pid}: {len(events)} corrections, "
              f"{sum(1 for e in events if e['is_stacked'])} stacked")

    print(f"\nTotal: {len(all_events)} corrections")

    # Split clean vs stacked
    clean = [e for e in all_events if not e["is_stacked"]]
    stacked = [e for e in all_events if e["is_stacked"]]
    print(f"Clean: {len(clean)}, Stacked: {len(stacked)}")

    # --- H1: Glucose CV comparison ---
    clean_cv = np.array([e["glucose_cv_pct"] for e in clean])
    stacked_cv = np.array([e["glucose_cv_pct"] for e in stacked])
    cv_diff_pct = (np.mean(stacked_cv) / np.mean(clean_cv) - 1) * 100 if len(clean_cv) > 0 and len(stacked_cv) > 0 else np.nan
    h1_ttest = sp_stats.ttest_ind(stacked_cv, clean_cv) if len(clean_cv) > 2 and len(stacked_cv) > 2 else None

    print(f"\n=== H1: Glucose CV (6h window) ===")
    print(f"  Clean: {np.mean(clean_cv):.1f}% ± {np.std(clean_cv):.1f}% (n={len(clean_cv)})")
    print(f"  Stacked: {np.mean(stacked_cv):.1f}% ± {np.std(stacked_cv):.1f}% (n={len(stacked_cv)})")
    print(f"  Difference: {cv_diff_pct:.1f}%")
    if h1_ttest:
        print(f"  t = {h1_ttest.statistic:.2f}, p = {h1_ttest.pvalue:.4f}")
    h1_pass = not np.isnan(cv_diff_pct) and cv_diff_pct > 30
    print(f"  → {'PASS' if h1_pass else 'FAIL'}")

    # --- H2: Time since previous → 6h endpoint ---
    times_since = np.array([e["time_since_prev_h"] for e in all_events
                            if e["time_since_prev_h"] is not None and e["bg_6h"] is not None])
    bg_6h_vals = np.array([e["bg_6h"] for e in all_events
                           if e["time_since_prev_h"] is not None and e["bg_6h"] is not None])
    # "Closer to target" = closer to 120; measure distance from 120
    dist_from_target = np.abs(bg_6h_vals - 120)
    r_time_dist, p_time_dist = sp_stats.pearsonr(times_since, dist_from_target) if len(times_since) > 5 else (np.nan, np.nan)

    print(f"\n=== H2: Time since prev → 6h distance from target ===")
    print(f"  r = {r_time_dist:.3f}, p = {p_time_dist:.4f} (n={len(times_since)})")
    print(f"  (negative r = longer gap → closer to target)")
    h2_pass = not np.isnan(r_time_dist) and r_time_dist < -0.2
    print(f"  → {'PASS' if h2_pass else 'FAIL'}")

    # --- H3: Target attainment ---
    clean_target = sum(1 for e in clean if e["in_target_3h_6h"]) / len(clean) * 100 if clean else 0
    stacked_target = sum(1 for e in stacked if e["in_target_3h_6h"]) / len(stacked) * 100 if stacked else 0
    target_diff = clean_target - stacked_target

    print(f"\n=== H3: Target attainment (80-120 in 3-6h window) ===")
    print(f"  Clean: {clean_target:.1f}% (n={len(clean)})")
    print(f"  Stacked: {stacked_target:.1f}% (n={len(stacked)})")
    print(f"  Difference: {target_diff:.1f} pp")
    h3_pass = target_diff > 15
    print(f"  → {'PASS' if h3_pass else 'FAIL'}")

    # --- H4: Stacked insulin → overshoot ---
    stacked_insulin = np.array([e["stacked_insulin_u"] for e in stacked
                                 if e["overshoot_mgdl"] is not None])
    stacked_overshoot = np.array([e["overshoot_mgdl"] for e in stacked
                                   if e["overshoot_mgdl"] is not None])
    if len(stacked_insulin) > 5:
        slope, intercept, r_val, p_val, _ = sp_stats.linregress(stacked_insulin, stacked_overshoot)
        h4_pass = slope > 5
    else:
        slope = intercept = r_val = p_val = np.nan
        h4_pass = False

    print(f"\n=== H4: Stacked insulin → overshoot ===")
    print(f"  Slope: {slope:.1f} mg/dL per stacked U")
    print(f"  r = {r_val:.3f}, p = {p_val:.4f} (n={len(stacked_insulin)})")
    print(f"  → {'PASS' if h4_pass else 'FAIL'}")

    # --- Summary ---
    results = {
        "experiment": "EXP-2637",
        "title": "Phase-Aware Stacking — Do Corrections During Recovery Cause Worse Outcomes?",
        "methodology": "EXP-2624 exact + 4h post-correction stacking detection",
        "n_events": len(all_events),
        "n_clean": len(clean),
        "n_stacked": len(stacked),
        "n_patients": len(per_patient),
        "hypotheses": {
            "H1": {
                "statement": "Stacked corrections have >30% higher glucose CV",
                "result": "PASS" if h1_pass else "FAIL",
                "clean_cv": round(float(np.mean(clean_cv)), 1),
                "stacked_cv": round(float(np.mean(stacked_cv)), 1),
                "cv_diff_pct": round(cv_diff_pct, 1) if not np.isnan(cv_diff_pct) else None,
                "p_value": round(float(h1_ttest.pvalue), 4) if h1_ttest else None,
            },
            "H2": {
                "statement": "Time since prev correction → closer to target (r < -0.2)",
                "result": "PASS" if h2_pass else "FAIL",
                "r": round(r_time_dist, 3) if not np.isnan(r_time_dist) else None,
                "p_value": round(p_time_dist, 4) if not np.isnan(p_time_dist) else None,
                "n": int(len(times_since)),
            },
            "H3": {
                "statement": "Clean recoveries reach target >15pp more often than stacked",
                "result": "PASS" if h3_pass else "FAIL",
                "clean_pct": round(clean_target, 1),
                "stacked_pct": round(stacked_target, 1),
                "diff_pp": round(target_diff, 1),
            },
            "H4": {
                "statement": "Each stacked U adds >5 mg/dL overshoot",
                "result": "PASS" if h4_pass else "FAIL",
                "slope_mgdl_per_u": round(slope, 1) if not np.isnan(slope) else None,
                "r": round(r_val, 3) if not np.isnan(r_val) else None,
                "p_value": round(p_val, 4) if not np.isnan(p_val) else None,
            },
        },
        "per_patient": per_patient,
        "events": all_events,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    main()
