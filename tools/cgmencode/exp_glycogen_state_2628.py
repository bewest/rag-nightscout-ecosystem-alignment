#!/usr/bin/env python3
"""EXP-2628: Glycogen State Detection & Settings Stratification.

MOTIVATION: EXP-2622/2627 showed 48h carbs predict overnight drift (r=-0.30,
R²=9.2%). But correlation is continuous — can we classify discrete glycogen
states (low/nominal/high) that predict DIFFERENT settings needs?

If glycogen state modifies effective ISF and basal adequacy, then:
- A single ISF/basal is wrong on glycogen-depleted vs glycogen-loaded days
- Settings advisors should recommend conditional adjustments
- AID controllers should adapt to glycogen context

APPROACH:
1. Classify each day's glycogen state from 48h carb accumulation (per-patient
   terciles → low/nominal/high)
2. Cross-validate: do states predict overnight drift, mean glucose, TAR/TBR?
3. Test whether correction ISF differs by glycogen state
4. Test whether basal adequacy differs by glycogen state
5. Produce concrete recommendations: "on low-glycogen days, reduce basal by X%"

HYPOTHESES:
H1: Low-glycogen nights have drift ≥5 mg/dL/hr LOWER than high-glycogen nights
    (depleted liver → less EGP → glucose drifts down or stays flat)
H2: Corrections during high-glycogen periods have apparent ISF ≥20% higher
    than during low-glycogen (more EGP to suppress → bigger apparent effect)
H3: Glycogen state classification predicts next-day mean glucose (|r| ≥ 0.15)
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
OUTFILE = RESULTS_DIR / "exp-2628_glycogen_state_detection.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
STEPS_PER_HOUR = 12


def _build_daily_features(pdf):
    """Build per-day feature matrix for glycogen state classification."""
    pdf = pdf.sort_values("time").copy()
    t = pd.to_datetime(pdf["time"])
    pdf["hour"] = t.dt.hour + t.dt.minute / 60.0
    pdf["date"] = t.dt.date

    carbs_col = pdf["carbs"].fillna(0).values.astype(np.float64)
    glucose_col = pdf["glucose"].values.astype(np.float64)
    bolus_col = pdf["bolus"].fillna(0).values.astype(np.float64)
    basal_col = pdf["actual_basal_rate"].fillna(0).values.astype(np.float64)
    iob_col = pdf["iob"].fillna(0).values.astype(np.float64)

    # Build 48h rolling carb accumulator
    window_steps = 48 * STEPS_PER_HOUR
    carbs_48h = np.zeros(len(pdf))
    cumcarbs = np.cumsum(carbs_col)
    for i in range(len(pdf)):
        start = max(0, i - window_steps)
        carbs_48h[i] = cumcarbs[i] - (cumcarbs[start] if start > 0 else 0)

    dates = sorted(pdf["date"].unique())
    days = []

    for date in dates:
        day_mask = pdf["date"] == date
        day = pdf[day_mask]
        if len(day) < 200:  # need most of the day
            continue

        # Day features
        day_glucose = day["glucose"].dropna()
        if len(day_glucose) < 100:
            continue

        day_carbs = float(day["carbs"].fillna(0).sum())
        day_bolus = float(day["bolus"].fillna(0).sum())
        day_basal_total = float(day["actual_basal_rate"].fillna(0).sum() * 5.0 / 60.0)
        day_mean_glucose = float(day_glucose.mean())
        day_tir = float(((day_glucose >= 70) & (day_glucose <= 180)).mean() * 100)
        day_tar = float((day_glucose > 180).mean() * 100)
        day_tbr = float((day_glucose < 70).mean() * 100)

        # Glycogen proxy: 48h carbs at start of day
        day_start_idx = day.index[0]
        pos = pdf.index.get_loc(day_start_idx)
        glycogen_48h = float(carbs_48h[pos])

        # Overnight drift (this night: 00-06)
        night_mask = day_mask & (pdf["hour"] >= 0) & (pdf["hour"] < 6)
        night = pdf[night_mask]
        drift = np.nan
        if len(night) >= 36:
            ng = night["glucose"].dropna()
            if len(ng) >= 20:
                nc = float(night["carbs"].fillna(0).sum())
                nb = float(night["bolus"].fillna(0).sum())
                if nc <= 2.0 and nb <= 0.5:  # clean night
                    t_hrs = np.arange(len(ng)) * (5.0 / 60.0)
                    drift = float(np.polyfit(t_hrs, ng.values, 1)[0])

        # Insulin surplus: total insulin - carbs/CR (rough balance)
        scheduled_cr = day["scheduled_cr"].dropna()
        if len(scheduled_cr) > 0:
            cr = float(scheduled_cr.median())
            expected_bolus = day_carbs / cr if cr > 0 else 0
            insulin_surplus = day_bolus - expected_bolus
        else:
            insulin_surplus = np.nan

        days.append({
            "date": str(date),
            "carbs_today": day_carbs,
            "glycogen_48h": glycogen_48h,
            "bolus_today": day_bolus,
            "basal_today": day_basal_total,
            "mean_glucose": day_mean_glucose,
            "tir": day_tir,
            "tar": day_tar,
            "tbr": day_tbr,
            "overnight_drift": drift,
            "insulin_surplus": insulin_surplus,
        })

    return days


def _extract_corrections_with_glycogen(pdf):
    """Extract correction events with glycogen context."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs_col = pdf["carbs"].fillna(0).values.astype(np.float64)
    t = pd.to_datetime(pdf["time"])
    hours = (t.dt.hour + t.dt.minute / 60.0).values

    # 48h carb accumulator
    window_steps = 48 * STEPS_PER_HOUR
    cumcarbs = np.cumsum(carbs_col)

    events = []
    PRE_STEPS = 6
    POST_STEPS = 6 * STEPS_PER_HOUR  # 6h lookforward

    for i in range(PRE_STEPS, len(pdf) - POST_STEPS):
        if bolus[i] < 0.5:
            continue
        # No carbs within ±1h
        carb_window = carbs_col[max(0, i - 12):i + 12]
        if carb_window.sum() > 2:
            continue
        # No prior bolus within 2h
        prior_bolus = bolus[max(0, i - 24):i]
        if prior_bolus.sum() > 0.3:
            continue

        pre_bg = float(np.nanmean(glucose[i - PRE_STEPS:i]))
        if np.isnan(pre_bg) or pre_bg < 120:
            continue

        # Track glucose for 6h after
        post = glucose[i:i + POST_STEPS]
        valid = ~np.isnan(post)
        if valid.sum() < 30:
            continue

        nadir_bg = float(np.nanmin(post[valid]))
        drop = pre_bg - nadir_bg
        if drop < 10:
            continue

        nadir_idx = np.nanargmin(post)
        nadir_h = nadir_idx * 5.0 / 60.0

        # Recovery slope
        if nadir_idx + 12 < len(post):
            recovery_pts = post[nadir_idx:nadir_idx + 12]
            rv = recovery_pts[~np.isnan(recovery_pts)]
            if len(rv) >= 4:
                t_rec = np.arange(len(rv)) * (5.0 / 60.0)
                recovery_slope = float(np.polyfit(t_rec, rv, 1)[0])
            else:
                recovery_slope = np.nan
        else:
            recovery_slope = np.nan

        apparent_isf = drop / bolus[i]

        # Glycogen state at time of correction
        start_48 = max(0, i - window_steps)
        glycogen_48h = float(cumcarbs[i] - (cumcarbs[start_48] if start_48 > 0 else 0))

        events.append({
            "hour": float(hours[i]),
            "bolus": float(bolus[i]),
            "pre_bg": pre_bg,
            "nadir_bg": nadir_bg,
            "drop": drop,
            "nadir_h": nadir_h,
            "apparent_isf": apparent_isf,
            "recovery_slope": recovery_slope,
            "glycogen_48h": glycogen_48h,
        })

    return events


def main():
    print("=" * 70)
    print("EXP-2628: Glycogen State Detection & Settings Stratification")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_patient_results = {}
    pooled_days = []
    pooled_corrections = []

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288 * 14:
            print(f"  SKIP: insufficient data")
            continue

        days = _build_daily_features(pdf)
        corrections = _extract_corrections_with_glycogen(pdf)
        print(f"  Days: {len(days)}, Corrections: {len(corrections)}")

        if len(days) < 30:
            continue

        # ── Classify glycogen state via per-patient terciles ──────────
        glyc = np.array([d["glycogen_48h"] for d in days])
        t33 = np.percentile(glyc, 33.3)
        t67 = np.percentile(glyc, 66.7)

        for d in days:
            if d["glycogen_48h"] <= t33:
                d["glycogen_state"] = "low"
            elif d["glycogen_48h"] <= t67:
                d["glycogen_state"] = "nominal"
            else:
                d["glycogen_state"] = "high"
            d["patient"] = pid

        print(f"  Glycogen thresholds: low<{t33:.0f}g, nominal<{t67:.0f}g, high≥{t67:.0f}g")

        # ── State → overnight drift ──────────────────────────────────
        drift_by_state = {}
        for state in ["low", "nominal", "high"]:
            state_days = [d for d in days if d["glycogen_state"] == state
                          and not np.isnan(d["overnight_drift"])]
            if state_days:
                drifts = [d["overnight_drift"] for d in state_days]
                drift_by_state[state] = {
                    "n": len(drifts),
                    "mean": float(np.mean(drifts)),
                    "std": float(np.std(drifts)),
                    "median": float(np.median(drifts)),
                }

        if "low" in drift_by_state and "high" in drift_by_state:
            delta = drift_by_state["high"]["mean"] - drift_by_state["low"]["mean"]
            print(f"  Overnight drift: low={drift_by_state['low']['mean']:.1f}, "
                  f"high={drift_by_state['high']['mean']:.1f}, Δ={delta:+.1f} mg/dL/hr")
        else:
            delta = np.nan

        # ── State → mean glucose ─────────────────────────────────────
        mg_by_state = {}
        for state in ["low", "nominal", "high"]:
            state_days = [d for d in days if d["glycogen_state"] == state]
            if state_days:
                mgs = [d["mean_glucose"] for d in state_days]
                mg_by_state[state] = {
                    "n": len(mgs),
                    "mean": float(np.mean(mgs)),
                    "median": float(np.median(mgs)),
                }

        if "low" in mg_by_state and "high" in mg_by_state:
            print(f"  Mean glucose: low={mg_by_state['low']['mean']:.0f}, "
                  f"high={mg_by_state['high']['mean']:.0f} mg/dL")

        # ── State → TIR ──────────────────────────────────────────────
        tir_by_state = {}
        for state in ["low", "nominal", "high"]:
            state_days = [d for d in days if d["glycogen_state"] == state]
            if state_days:
                tirs = [d["tir"] for d in state_days]
                tir_by_state[state] = float(np.mean(tirs))

        if tir_by_state:
            print(f"  TIR: " + ", ".join(f"{s}={v:.0f}%" for s, v in tir_by_state.items()))

        # ── Corrections stratified by glycogen state ─────────────────
        if corrections:
            c_glyc = np.array([c["glycogen_48h"] for c in corrections])
            for c in corrections:
                if c["glycogen_48h"] <= t33:
                    c["glycogen_state"] = "low"
                elif c["glycogen_48h"] <= t67:
                    c["glycogen_state"] = "nominal"
                else:
                    c["glycogen_state"] = "high"
                c["patient"] = pid

            isf_by_state = {}
            for state in ["low", "nominal", "high"]:
                state_corr = [c for c in corrections if c["glycogen_state"] == state]
                if state_corr:
                    isfs = [c["apparent_isf"] for c in state_corr]
                    isf_by_state[state] = {
                        "n": len(isfs),
                        "mean": float(np.mean(isfs)),
                        "median": float(np.median(isfs)),
                    }

            if isf_by_state:
                parts = [f"{s}={v['mean']:.0f} (n={v['n']})" for s, v in isf_by_state.items()]
                print(f"  Apparent ISF: " + ", ".join(parts))
        else:
            isf_by_state = {}

        all_patient_results[pid] = {
            "n_days": len(days),
            "n_corrections": len(corrections),
            "glycogen_thresholds": {"t33": float(t33), "t67": float(t67)},
            "drift_by_state": drift_by_state,
            "mean_glucose_by_state": mg_by_state,
            "tir_by_state": tir_by_state,
            "isf_by_state": isf_by_state,
            "drift_delta_high_minus_low": float(delta) if not np.isnan(delta) else None,
        }

        pooled_days.extend(days)
        pooled_corrections.extend(corrections)

    # ── POOLED ANALYSIS ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("POOLED ANALYSIS")
    print("=" * 70)
    print(f"  Total days: {len(pooled_days)}, corrections: {len(pooled_corrections)}")

    # Per-patient terciles already applied — analyze pooled states
    for state in ["low", "nominal", "high"]:
        s_days = [d for d in pooled_days if d["glycogen_state"] == state]
        drifts = [d["overnight_drift"] for d in s_days if not np.isnan(d["overnight_drift"])]
        mgs = [d["mean_glucose"] for d in s_days]
        tirs = [d["tir"] for d in s_days]
        s_corr = [c for c in pooled_corrections if c["glycogen_state"] == state]
        isfs = [c["apparent_isf"] for c in s_corr]
        recov = [c["recovery_slope"] for c in s_corr if not np.isnan(c["recovery_slope"])]

        print(f"\n  [{state.upper()}] N={len(s_days)} days, {len(s_corr)} corrections")
        if drifts:
            print(f"    Overnight drift: {np.mean(drifts):.1f}±{np.std(drifts):.1f} mg/dL/hr")
        print(f"    Mean glucose: {np.mean(mgs):.0f}±{np.std(mgs):.0f} mg/dL")
        print(f"    TIR: {np.mean(tirs):.1f}%")
        if isfs:
            print(f"    Apparent ISF: {np.mean(isfs):.1f}±{np.std(isfs):.1f} mg/dL/U (median {np.median(isfs):.1f})")
        if recov:
            print(f"    Recovery slope: {np.mean(recov):.1f}±{np.std(recov):.1f} mg/dL/hr")

    # ── Statistical tests ────────────────────────────────────────────
    low_drifts = [d["overnight_drift"] for d in pooled_days
                  if d["glycogen_state"] == "low" and not np.isnan(d["overnight_drift"])]
    high_drifts = [d["overnight_drift"] for d in pooled_days
                   if d["glycogen_state"] == "high" and not np.isnan(d["overnight_drift"])]
    nom_drifts = [d["overnight_drift"] for d in pooled_days
                  if d["glycogen_state"] == "nominal" and not np.isnan(d["overnight_drift"])]

    if low_drifts and high_drifts:
        t_stat, p_val = stats.ttest_ind(low_drifts, high_drifts)
        drift_delta = np.mean(high_drifts) - np.mean(low_drifts)
        print(f"\n  Drift: high-low = {drift_delta:+.1f} mg/dL/hr (t={t_stat:.2f}, p={p_val:.4f})")

    # Correction ISF by state
    low_isf = [c["apparent_isf"] for c in pooled_corrections if c["glycogen_state"] == "low"]
    high_isf = [c["apparent_isf"] for c in pooled_corrections if c["glycogen_state"] == "high"]
    if len(low_isf) >= 5 and len(high_isf) >= 5:
        t_stat, p_val = stats.ttest_ind(low_isf, high_isf)
        isf_delta_pct = (np.mean(high_isf) - np.mean(low_isf)) / np.mean(low_isf) * 100
        print(f"  ISF: high vs low = {isf_delta_pct:+.1f}% (t={t_stat:.2f}, p={p_val:.4f})")
        print(f"    Low: {np.mean(low_isf):.1f} (n={len(low_isf)}), "
              f"High: {np.mean(high_isf):.1f} (n={len(high_isf)})")

    # Glycogen → next-day glucose correlation
    glyc_values = [d["glycogen_48h"] for d in pooled_days]
    mg_values = [d["mean_glucose"] for d in pooled_days]
    r_glyc_mg, p_glyc_mg = stats.pearsonr(glyc_values, mg_values)
    print(f"  Glycogen→mean glucose: r={r_glyc_mg:.3f} (p={p_glyc_mg:.4f})")

    # ── HYPOTHESIS TESTING ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    h1_pass = False
    if low_drifts and high_drifts:
        h1_delta = np.mean(high_drifts) - np.mean(low_drifts)
        h1_pass = abs(h1_delta) >= 5.0
        print(f"\n  H1: |drift_high - drift_low| ≥ 5 mg/dL/hr")
        print(f"      Δ = {h1_delta:+.1f} mg/dL/hr")
        print(f"      → {'PASS' if h1_pass else 'FAIL'}")

    h2_pass = False
    if len(low_isf) >= 5 and len(high_isf) >= 5:
        h2_delta = (np.mean(high_isf) - np.mean(low_isf)) / np.mean(low_isf) * 100
        h2_pass = h2_delta >= 20
        print(f"\n  H2: ISF during high-glycogen ≥ 20% higher than low-glycogen")
        print(f"      Δ = {h2_delta:+.1f}%")
        print(f"      → {'PASS' if h2_pass else 'FAIL'}")

    h3_pass = abs(r_glyc_mg) >= 0.15
    print(f"\n  H3: Glycogen → next-day mean glucose |r| ≥ 0.15")
    print(f"      r = {r_glyc_mg:.3f}")
    print(f"      → {'PASS' if h3_pass else 'FAIL'}")

    # ── SETTINGS IMPLICATIONS ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SETTINGS IMPLICATIONS")
    print("=" * 70)

    if low_drifts and high_drifts:
        drift_range = np.mean(high_drifts) - np.mean(low_drifts)
        print(f"\n  Overnight drift swing: {drift_range:+.1f} mg/dL/hr between states")
        # Convert drift to basal adjustment: drift / ISF_median
        all_isf = [c["apparent_isf"] for c in pooled_corrections]
        if all_isf:
            med_isf = np.median(all_isf)
            basal_adjustment = drift_range / med_isf
            print(f"  Implied basal adjustment: {basal_adjustment:+.2f} U/hr "
                  f"(drift / median ISF {med_isf:.0f})")
            pct_adjustment = basal_adjustment / np.mean(
                [d["basal_today"] / 24 for d in pooled_days if d["basal_today"] > 0]
            ) * 100
            print(f"  As percentage of mean basal: {pct_adjustment:+.0f}%")

    # Per-patient state summaries
    print("\n  Per-patient glycogen state impact:")
    for pid in sorted(all_patient_results.keys()):
        pr = all_patient_results[pid]
        dd = pr.get("drift_delta_high_minus_low")
        isf_states = pr.get("isf_by_state", {})
        tir_states = pr.get("tir_by_state", {})
        if dd is not None:
            tir_range = ""
            if "low" in tir_states and "high" in tir_states:
                tir_range = f", TIR: low={tir_states['low']:.0f}% high={tir_states['high']:.0f}%"
            isf_info = ""
            if "low" in isf_states and "high" in isf_states:
                isf_info = f", ISF: low={isf_states['low']['mean']:.0f} high={isf_states['high']['mean']:.0f}"
            print(f"    {pid}: drift Δ={dd:+.1f} mg/dL/hr{isf_info}{tir_range}")

    # ── SAVE ─────────────────────────────────────────────────────────
    pooled_summary = {}
    for state in ["low", "nominal", "high"]:
        s_days = [d for d in pooled_days if d["glycogen_state"] == state]
        drifts = [d["overnight_drift"] for d in s_days if not np.isnan(d["overnight_drift"])]
        mgs = [d["mean_glucose"] for d in s_days]
        tirs = [d["tir"] for d in s_days]
        s_corr = [c for c in pooled_corrections if c["glycogen_state"] == state]
        isfs = [c["apparent_isf"] for c in s_corr]
        recov = [c["recovery_slope"] for c in s_corr if not np.isnan(c["recovery_slope"])]
        pooled_summary[state] = {
            "n_days": len(s_days),
            "n_corrections": len(s_corr),
            "drift_mean": float(np.mean(drifts)) if drifts else None,
            "drift_std": float(np.std(drifts)) if drifts else None,
            "mean_glucose": float(np.mean(mgs)),
            "tir": float(np.mean(tirs)),
            "apparent_isf_mean": float(np.mean(isfs)) if isfs else None,
            "apparent_isf_median": float(np.median(isfs)) if isfs else None,
            "recovery_slope_mean": float(np.mean(recov)) if recov else None,
        }

    results = {
        "experiment": "EXP-2628",
        "title": "Glycogen State Detection & Settings Stratification",
        "n_days": len(pooled_days),
        "n_corrections": len(pooled_corrections),
        "n_patients": len(all_patient_results),
        "pooled_summary": pooled_summary,
        "per_patient": all_patient_results,
        "hypotheses": {
            "H1_drift_delta_5": {
                "pass": bool(h1_pass),
                "delta": float(h1_delta) if low_drifts and high_drifts else None,
            },
            "H2_isf_20pct_higher": {
                "pass": bool(h2_pass),
                "delta_pct": float(h2_delta) if len(low_isf) >= 5 and len(high_isf) >= 5 else None,
            },
            "H3_glycogen_glucose_r": {
                "pass": bool(h3_pass),
                "r": float(r_glyc_mg),
                "p": float(p_glyc_mg),
            },
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
