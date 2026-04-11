#!/usr/bin/env python3
"""
exp_cr_response.py — Carb Ratio Response Curve Analysis (EXP-2535a–e)

Prior work established ISF nonlinearity (power-law β=0.9, EXP-2511–2518)
and carb survey statistics (EXP-1341: median 21.8g, 76.5% UAM). This
experiment analyzes the second leg of the therapy triangle: Carb Ratio.

CR = grams of carbs covered by 1U of insulin.
  Miscalibrated CR causes:
  - CR too low → over-bolus → hypoglycemia
  - CR too high → under-bolus → post-meal hyperglycemia

Experiments:
  EXP-2535a: Meal event extraction — identify meals, capture pre/post BG,
             bolus, carbs, profile CR. Report counts & size distributions.
  EXP-2535b: Effective CR computation — actual carbs/bolus vs profile CR.
             Compute CR ratio = effective_CR / profile_CR per patient.
  EXP-2535c: Dose-dependent CR — group by meal size (small/med/large/XL),
             compute per-gram BG excursion. Test for nonlinearity.
  EXP-2535d: CR adequacy — mean 4h BG delta per patient, compute ideal CR.
  EXP-2535e: Post-meal TIR — TIR at 1h/2h/3h/4h vs overall.

Data columns (grid.parquet):
  glucose, carbs, bolus, bolus_smb, cob, iob, scheduled_cr, scheduled_isf

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_cr_response.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_cr_response.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "externals" / "experiments"

# ── Constants ────────────────────────────────────────────────────────

MERGE_WINDOW_MIN = 30       # Merge carb entries within this window
POST_MEAL_HOURS = 4         # Post-meal observation window
ROWS_PER_HOUR = 12          # 5-minute intervals
TIR_LOW = 70
TIR_HIGH = 180
MIN_MEALS_FOR_ANALYSIS = 5  # Minimum meals to include patient

MEAL_SIZE_BINS = {
    "small": (0, 20),
    "medium": (20, 50),
    "large": (50, 100),
    "very_large": (100, float("inf")),
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
    # Manual bolus = total bolus minus SMB
    df["manual_bolus"] = (df["bolus"] - df["bolus_smb"]).clip(lower=0)
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


# ── Meal Event Extraction ───────────────────────────────────────────

def extract_meals(pdf: pd.DataFrame, patient_id: str) -> list[dict]:
    """Extract meal events for one patient.

    A meal event starts at a row where carbs > 0.  Consecutive carb entries
    within MERGE_WINDOW_MIN are merged into a single meal.  For each meal
    we capture pre-meal BG, post-meal trajectory, bolus, carbs, and
    profile settings.
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
        meal_time = pdf.loc[start_idx, "time"]

        # Total carbs in this meal
        total_carbs = float(pdf.loc[grp, "carbs"].sum())
        if total_carbs < 1:
            continue

        # Pre-meal glucose
        pre_bg = pdf.loc[start_idx, "glucose"]
        if np.isnan(pre_bg):
            continue

        # Bolus window: from 15 min before meal to 30 min after last carb entry
        bolus_start = max(0, start_idx - 3)  # 15 min before
        bolus_end = min(n_rows - 1, end_idx + 6)  # 30 min after
        manual_bolus = float(pdf.loc[bolus_start:bolus_end, "manual_bolus"].sum())
        total_bolus = float(pdf.loc[bolus_start:bolus_end, "bolus"].sum())
        smb_bolus = float(pdf.loc[bolus_start:bolus_end, "bolus_smb"].sum())

        # Profile CR and ISF at meal time
        profile_cr = float(pdf.loc[start_idx, "scheduled_cr"])
        profile_isf = float(pdf.loc[start_idx, "scheduled_isf"])

        # Pre-meal IOB
        pre_iob = float(pdf.loc[start_idx, "iob"])

        # Post-meal glucose trajectory
        post_start = start_idx
        post_end = min(n_rows - 1, start_idx + post_rows)
        post_window = pdf.loc[post_start:post_end]
        post_glucose = post_window["glucose"].values

        if len(post_glucose) < ROWS_PER_HOUR:
            continue  # Not enough post-meal data

        valid_glucose = post_glucose[~np.isnan(post_glucose)]
        if len(valid_glucose) < 6:
            continue

        peak_bg = float(np.nanmax(post_glucose))
        peak_idx_rel = int(np.nanargmax(post_glucose))
        peak_time_min = peak_idx_rel * 5

        # BG at 1h, 2h, 3h, 4h (indices 12, 24, 36, 48)
        bg_at = {}
        for h in [1, 2, 3, 4]:
            idx_h = start_idx + h * ROWS_PER_HOUR
            if idx_h < n_rows:
                val = pdf.loc[idx_h, "glucose"]
                bg_at[f"bg_{h}h"] = float(val) if not np.isnan(val) else None
            else:
                bg_at[f"bg_{h}h"] = None

        # Post-meal TIR at each hour window
        tir_at = {}
        for h in [1, 2, 3, 4]:
            end_h = min(n_rows - 1, start_idx + h * ROWS_PER_HOUR)
            window_g = pdf.loc[post_start:end_h, "glucose"].dropna().values
            if len(window_g) > 0:
                in_range = ((window_g >= TIR_LOW) & (window_g <= TIR_HIGH)).mean()
                tir_at[f"tir_{h}h"] = float(in_range)
            else:
                tir_at[f"tir_{h}h"] = None

        # Meal size category
        for cat, (lo, hi) in MEAL_SIZE_BINS.items():
            if lo <= total_carbs < hi:
                size_cat = cat
                break
        else:
            size_cat = "very_large"

        meals.append({
            "patient_id": patient_id,
            "meal_time": str(meal_time),
            "hour_of_day": float(pdf.loc[start_idx, "hour"]),
            "total_carbs": total_carbs,
            "size_category": size_cat,
            "manual_bolus": manual_bolus,
            "total_bolus": total_bolus,
            "smb_bolus": smb_bolus,
            "profile_cr": profile_cr,
            "profile_isf": profile_isf,
            "pre_bg": float(pre_bg),
            "pre_iob": pre_iob,
            "peak_bg": peak_bg,
            "peak_time_min": peak_time_min,
            "bg_rise": peak_bg - float(pre_bg),
            **bg_at,
            **tir_at,
        })

    return meals


# ── EXP-2535a: Meal Event Summary ───────────────────────────────────

def exp_2535a_meal_extraction(df: pd.DataFrame) -> dict:
    """Extract meals across all patients. Report counts and distributions."""
    print("EXP-2535a: Meal Event Extraction")
    print("-" * 50)

    all_meals = []
    patient_summary = {}

    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        meals = extract_meals(pdf, pid)
        all_meals.extend(meals)

        if meals:
            carbs_arr = [m["total_carbs"] for m in meals]
            bolused = [m for m in meals if m["manual_bolus"] > 0]
            size_dist = {}
            for cat in MEAL_SIZE_BINS:
                size_dist[cat] = sum(1 for m in meals if m["size_category"] == cat)

            patient_summary[pid] = {
                "total_meals": len(meals),
                "meals_with_bolus": len(bolused),
                "pct_bolused": round(100 * len(bolused) / len(meals), 1),
                "mean_carbs": round(float(np.mean(carbs_arr)), 1),
                "median_carbs": round(float(np.median(carbs_arr)), 1),
                "profile_cr": meals[0]["profile_cr"],
                "size_distribution": size_dist,
                "sufficient_data": len(bolused) >= MIN_MEALS_FOR_ANALYSIS,
            }
        else:
            patient_summary[pid] = {
                "total_meals": 0,
                "meals_with_bolus": 0,
                "pct_bolused": 0,
                "mean_carbs": 0,
                "median_carbs": 0,
                "profile_cr": float(pdf["scheduled_cr"].median()),
                "size_distribution": {cat: 0 for cat in MEAL_SIZE_BINS},
                "sufficient_data": False,
            }

    # Print summary table
    print(f"\n{'Patient':<20} {'Meals':>6} {'Bolused':>8} {'%Bol':>6} "
          f"{'MeanCarbs':>10} {'MedCarbs':>9} {'CR':>5} {'Sml':>4} "
          f"{'Med':>4} {'Lrg':>4} {'XL':>4} {'OK':>3}")
    print("-" * 100)
    total_meals = 0
    total_bolused = 0
    for pid, s in sorted(patient_summary.items()):
        sd = s["size_distribution"]
        ok = "✓" if s["sufficient_data"] else "✗"
        print(f"{pid:<20} {s['total_meals']:>6} {s['meals_with_bolus']:>8} "
              f"{s['pct_bolused']:>5.1f}% {s['mean_carbs']:>10.1f} "
              f"{s['median_carbs']:>9.1f} {s['profile_cr']:>5.1f} "
              f"{sd.get('small',0):>4} {sd.get('medium',0):>4} "
              f"{sd.get('large',0):>4} {sd.get('very_large',0):>4} {ok:>3}")
        total_meals += s["total_meals"]
        total_bolused += s["meals_with_bolus"]

    print("-" * 100)
    print(f"{'TOTAL':<20} {total_meals:>6} {total_bolused:>8}")

    # Overall size distribution
    all_carbs = [m["total_carbs"] for m in all_meals]
    print(f"\nOverall: {total_meals} meals, {total_bolused} with manual bolus "
          f"({100*total_bolused/max(total_meals,1):.1f}%)")
    if all_carbs:
        print(f"  Carb distribution: mean={np.mean(all_carbs):.1f}g, "
              f"median={np.median(all_carbs):.1f}g, "
              f"p25={np.percentile(all_carbs,25):.1f}g, "
              f"p75={np.percentile(all_carbs,75):.1f}g")

    return {
        "total_meals": total_meals,
        "total_bolused": total_bolused,
        "pct_bolused": round(100 * total_bolused / max(total_meals, 1), 1),
        "carb_distribution": {
            "mean": round(float(np.mean(all_carbs)), 1) if all_carbs else 0,
            "median": round(float(np.median(all_carbs)), 1) if all_carbs else 0,
            "p25": round(float(np.percentile(all_carbs, 25)), 1) if all_carbs else 0,
            "p75": round(float(np.percentile(all_carbs, 75)), 1) if all_carbs else 0,
        },
        "patient_summary": patient_summary,
        "_meals": all_meals,  # passed to later experiments, stripped before save
    }


# ── EXP-2535b: Effective CR Computation ──────────────────────────────

def exp_2535b_effective_cr(meals: list[dict]) -> dict:
    """Compute effective CR = carbs / manual_bolus vs profile CR."""
    print("\nEXP-2535b: Effective CR Computation")
    print("-" * 50)

    # Filter to meals with meaningful manual bolus
    bolused = [m for m in meals if m["manual_bolus"] > 0.1]
    if not bolused:
        print("  No bolused meals found!")
        return {"error": "no_bolused_meals"}

    # Compute effective CR per meal
    for m in bolused:
        m["effective_cr"] = m["total_carbs"] / m["manual_bolus"]
        m["cr_ratio"] = m["effective_cr"] / m["profile_cr"]

    # Per-patient analysis
    patient_results = {}
    print(f"\n{'Patient':<20} {'N':>4} {'ProfCR':>7} {'EffCR':>7} "
          f"{'Ratio':>6} {'StdCR':>7} {'Interpret':<20}")
    print("-" * 85)

    for pid in sorted(set(m["patient_id"] for m in bolused)):
        pm = [m for m in bolused if m["patient_id"] == pid]
        if len(pm) < MIN_MEALS_FOR_ANALYSIS:
            continue

        eff_crs = [m["effective_cr"] for m in pm]
        cr_ratios = [m["cr_ratio"] for m in pm]
        profile_cr = pm[0]["profile_cr"]
        mean_eff = float(np.mean(eff_crs))
        median_eff = float(np.median(eff_crs))
        mean_ratio = float(np.mean(cr_ratios))
        std_eff = float(np.std(eff_crs))

        if mean_ratio > 1.15:
            interp = "under-dosing"
        elif mean_ratio < 0.85:
            interp = "over-dosing"
        else:
            interp = "well-matched"

        print(f"{pid:<20} {len(pm):>4} {profile_cr:>7.1f} {mean_eff:>7.1f} "
              f"{mean_ratio:>6.2f} {std_eff:>7.1f} {interp:<20}")

        patient_results[pid] = {
            "n_meals": len(pm),
            "profile_cr": profile_cr,
            "effective_cr_mean": round(mean_eff, 2),
            "effective_cr_median": round(median_eff, 2),
            "effective_cr_std": round(std_eff, 2),
            "cr_ratio_mean": round(mean_ratio, 3),
            "cr_ratio_median": round(float(np.median(cr_ratios)), 3),
            "interpretation": interp,
        }

    # Population summary
    all_ratios = [m["cr_ratio"] for m in bolused]
    pop_mean = float(np.mean(all_ratios))
    pop_median = float(np.median(all_ratios))
    pop_std = float(np.std(all_ratios))

    print("-" * 85)
    print(f"\nPopulation CR ratio: mean={pop_mean:.3f}, "
          f"median={pop_median:.3f}, std={pop_std:.3f}")
    if pop_mean > 1.0:
        print(f"  → Users use {pop_mean:.2f}× more carbs per unit than profile "
              f"suggests (effective CR > profile CR)")
    else:
        print(f"  → Users use {pop_mean:.2f}× fewer carbs per unit than profile "
              f"suggests (effective CR < profile CR)")

    return {
        "n_bolused_meals": len(bolused),
        "population": {
            "cr_ratio_mean": round(pop_mean, 3),
            "cr_ratio_median": round(pop_median, 3),
            "cr_ratio_std": round(pop_std, 3),
        },
        "patient_results": patient_results,
    }


# ── EXP-2535c: Dose-Dependent CR ────────────────────────────────────

def exp_2535c_dose_dependent_cr(meals: list[dict]) -> dict:
    """Test whether larger meals have different per-gram BG excursion."""
    print("\nEXP-2535c: Dose-Dependent CR (Meal Size → BG Response)")
    print("-" * 50)

    # Only include meals with valid post-meal data
    valid = [m for m in meals if m["bg_rise"] is not None
             and not np.isnan(m["bg_rise"])]

    if not valid:
        print("  No valid meals!")
        return {"error": "no_valid_meals"}

    # Overall by size category
    print(f"\n{'Category':<12} {'N':>5} {'MeanCarbs':>10} {'MeanRise':>9} "
          f"{'Rise/g':>7} {'PeakMin':>8} {'MeanBolus':>10} {'PctBolused':>11}")
    print("-" * 85)

    size_results = {}
    for cat, (lo, hi) in MEAL_SIZE_BINS.items():
        cat_meals = [m for m in valid if m["size_category"] == cat]
        if not cat_meals:
            size_results[cat] = {"n": 0}
            continue

        carbs = [m["total_carbs"] for m in cat_meals]
        rises = [m["bg_rise"] for m in cat_meals]
        peaks = [m["peak_time_min"] for m in cat_meals]
        boluses = [m["manual_bolus"] for m in cat_meals]
        bolused_pct = 100 * sum(1 for m in cat_meals if m["manual_bolus"] > 0) / len(cat_meals)

        mean_carbs = float(np.mean(carbs))
        mean_rise = float(np.mean(rises))
        rise_per_g = mean_rise / max(mean_carbs, 1)
        mean_peak = float(np.mean(peaks))
        mean_bolus = float(np.mean(boluses))

        print(f"{cat:<12} {len(cat_meals):>5} {mean_carbs:>10.1f} "
              f"{mean_rise:>9.1f} {rise_per_g:>7.2f} {mean_peak:>8.0f} "
              f"{mean_bolus:>10.2f} {bolused_pct:>10.1f}%")

        size_results[cat] = {
            "n": len(cat_meals),
            "mean_carbs": round(mean_carbs, 1),
            "mean_bg_rise": round(mean_rise, 1),
            "rise_per_gram": round(rise_per_g, 3),
            "mean_peak_time_min": round(mean_peak, 0),
            "mean_bolus": round(mean_bolus, 2),
            "pct_bolused": round(bolused_pct, 1),
        }

    # Per-patient dose-response for bolused meals
    print("\nPer-patient dose-response (bolused meals only):")
    print(f"{'Patient':<20} {'Small':>12} {'Medium':>12} {'Large':>12} "
          f"{'XL':>12} {'Trend':<15}")
    print("-" * 90)

    patient_dose = {}
    bolused = [m for m in valid if m["manual_bolus"] > 0.1]

    for pid in sorted(set(m["patient_id"] for m in bolused)):
        pm = [m for m in bolused if m["patient_id"] == pid]
        if len(pm) < MIN_MEALS_FOR_ANALYSIS:
            continue

        cat_rpg = {}
        parts = []
        for cat in MEAL_SIZE_BINS:
            cm = [m for m in pm if m["size_category"] == cat]
            if len(cm) >= 2:
                mc = float(np.mean([m["total_carbs"] for m in cm]))
                mr = float(np.mean([m["bg_rise"] for m in cm]))
                rpg = mr / max(mc, 1)
                cat_rpg[cat] = round(rpg, 2)
                parts.append(f"{rpg:>11.2f}")
            else:
                cat_rpg[cat] = None
                parts.append(f"{'n/a':>12}")

        # Determine trend
        vals = [cat_rpg[c] for c in ["small", "medium", "large", "very_large"]
                if cat_rpg.get(c) is not None]
        if len(vals) >= 2:
            if vals[-1] > vals[0] * 1.2:
                trend = "increasing"
            elif vals[-1] < vals[0] * 0.8:
                trend = "decreasing"
            else:
                trend = "flat"
        else:
            trend = "insufficient"

        print(f"{pid:<20} {''.join(parts)} {trend:<15}")
        patient_dose[pid] = {"rise_per_gram_by_size": cat_rpg, "trend": trend}

    # Nonlinearity test: correlation between meal size and rise/gram
    if bolused:
        carbs_arr = np.array([m["total_carbs"] for m in bolused])
        rpg_arr = np.array([m["bg_rise"] / max(m["total_carbs"], 1) for m in bolused])
        mask = ~(np.isnan(carbs_arr) | np.isnan(rpg_arr))
        if mask.sum() > 10:
            r = float(np.corrcoef(carbs_arr[mask], rpg_arr[mask])[0, 1])
            print(f"\nCorrelation(meal_size, rise_per_gram): r = {r:.3f}")
            if abs(r) > 0.1:
                direction = "larger meals → more rise/g" if r > 0 else "larger meals → less rise/g"
                print(f"  → Nonlinear signal: {direction}")
            else:
                print("  → Essentially linear (no significant dose-dependence)")
        else:
            r = None
    else:
        r = None

    return {
        "size_category_results": size_results,
        "patient_dose_response": patient_dose,
        "nonlinearity_correlation": round(r, 3) if r is not None else None,
    }


# ── EXP-2535d: CR Adequacy Assessment ───────────────────────────────

def exp_2535d_cr_adequacy(meals: list[dict]) -> dict:
    """Assess whether profile CR leads to correct post-meal BG."""
    print("\nEXP-2535d: CR Adequacy Assessment")
    print("-" * 50)

    bolused = [m for m in meals if m["manual_bolus"] > 0.1
               and m.get("bg_4h") is not None]
    if not bolused:
        print("  No bolused meals with 4h follow-up!")
        return {"error": "no_data"}

    print(f"\n{'Patient':<20} {'N':>4} {'PreBG':>6} {'4hBG':>6} "
          f"{'Δ4h':>6} {'ProfCR':>7} {'IdealCR':>8} {'Adj%':>6} {'Verdict':<18}")
    print("-" * 90)

    patient_results = {}
    for pid in sorted(set(m["patient_id"] for m in bolused)):
        pm = [m for m in bolused if m["patient_id"] == pid]
        if len(pm) < MIN_MEALS_FOR_ANALYSIS:
            continue

        pre_bgs = [m["pre_bg"] for m in pm]
        bg_4h = [m["bg_4h"] for m in pm]
        deltas = [m["bg_4h"] - m["pre_bg"] for m in pm]
        carbs_arr = [m["total_carbs"] for m in pm]
        bolus_arr = [m["manual_bolus"] for m in pm]
        profile_cr = pm[0]["profile_cr"]
        profile_isf = pm[0]["profile_isf"]

        mean_delta = float(np.mean(deltas))
        mean_pre = float(np.mean(pre_bgs))
        mean_4h = float(np.mean(bg_4h))

        # Ideal CR computation:
        # Post-meal BG = pre_BG + (carbs/CR_eff - bolus) × ISF ≈ pre_BG
        # So ideal: bolus = carbs / CR_ideal
        # Mean delta tells us the systematic bias:
        #   delta = (carbs/CR_used - bolus_ideal) × ISF
        #   We want delta = 0, so adjustment = delta / ISF
        #   That gives us the extra insulin needed per meal
        # Average: extra_insulin = mean_delta / profile_isf
        # Current: bolus = carbs / effective_CR_used
        # Needed: bolus + extra = carbs / ideal_CR
        mean_carbs = float(np.mean(carbs_arr))
        mean_bolus = float(np.mean(bolus_arr))

        if profile_isf > 0 and mean_bolus > 0:
            extra_insulin = mean_delta / profile_isf
            ideal_bolus = mean_bolus + extra_insulin
            if ideal_bolus > 0.1:
                ideal_cr = mean_carbs / ideal_bolus
            else:
                ideal_cr = profile_cr
        else:
            ideal_cr = profile_cr

        adj_pct = 100 * (ideal_cr - profile_cr) / profile_cr

        if mean_delta > 20:
            verdict = "CR too high"
        elif mean_delta < -20:
            verdict = "CR too low"
        elif mean_delta > 10:
            verdict = "slightly high"
        elif mean_delta < -10:
            verdict = "slightly low"
        else:
            verdict = "adequate"

        print(f"{pid:<20} {len(pm):>4} {mean_pre:>6.0f} {mean_4h:>6.0f} "
              f"{mean_delta:>+6.0f} {profile_cr:>7.1f} {ideal_cr:>8.1f} "
              f"{adj_pct:>+5.0f}% {verdict:<18}")

        patient_results[pid] = {
            "n_meals": len(pm),
            "mean_pre_bg": round(mean_pre, 1),
            "mean_bg_4h": round(mean_4h, 1),
            "mean_delta_4h": round(mean_delta, 1),
            "profile_cr": profile_cr,
            "ideal_cr": round(ideal_cr, 1),
            "adjustment_pct": round(adj_pct, 1),
            "verdict": verdict,
        }

    # Population summary
    all_deltas = [m["bg_4h"] - m["pre_bg"] for m in bolused]
    pop_mean_delta = float(np.mean(all_deltas))
    pop_std_delta = float(np.std(all_deltas))

    print("-" * 90)
    print(f"\nPopulation 4h BG delta: mean={pop_mean_delta:+.1f} mg/dL, "
          f"std={pop_std_delta:.1f}")
    if pop_mean_delta > 10:
        print("  → Population tendency: under-bolusing (CR too high)")
    elif pop_mean_delta < -10:
        print("  → Population tendency: over-bolusing (CR too low)")
    else:
        print("  → Population: reasonably calibrated on average")

    return {
        "population": {
            "mean_delta_4h": round(pop_mean_delta, 1),
            "std_delta_4h": round(pop_std_delta, 1),
        },
        "patient_results": patient_results,
    }


# ── EXP-2535e: Post-Meal TIR Impact ─────────────────────────────────

def exp_2535e_postmeal_tir(df: pd.DataFrame, meals: list[dict]) -> dict:
    """Compare post-meal TIR at 1h/2h/3h/4h windows vs overall TIR."""
    print("\nEXP-2535e: Post-Meal TIR Impact")
    print("-" * 50)

    # Compute overall TIR per patient
    overall_tir = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        g = pdf["glucose"].dropna().values
        if len(g) > 0:
            overall_tir[pid] = float(((g >= TIR_LOW) & (g <= TIR_HIGH)).mean())

    # Post-meal TIR by patient
    print(f"\n{'Patient':<20} {'N':>4} {'OvTIR':>6} {'1hTIR':>6} "
          f"{'2hTIR':>6} {'3hTIR':>6} {'4hTIR':>6} {'ΔTIR1h':>7} "
          f"{'ΔTIR4h':>7}")
    print("-" * 80)

    patient_results = {}
    for pid in sorted(set(m["patient_id"] for m in meals)):
        pm = [m for m in meals if m["patient_id"] == pid]
        if len(pm) < MIN_MEALS_FOR_ANALYSIS:
            continue

        ov_tir = overall_tir.get(pid, 0)

        tir_by_h = {}
        for h in [1, 2, 3, 4]:
            key = f"tir_{h}h"
            vals = [m[key] for m in pm if m.get(key) is not None]
            tir_by_h[key] = float(np.mean(vals)) if vals else None

        parts = []
        for h in [1, 2, 3, 4]:
            v = tir_by_h.get(f"tir_{h}h")
            parts.append(f"{100*v:>5.1f}%" if v is not None else "  n/a ")

        d1 = (tir_by_h.get("tir_1h", ov_tir) - ov_tir) * 100 if tir_by_h.get("tir_1h") else 0
        d4 = (tir_by_h.get("tir_4h", ov_tir) - ov_tir) * 100 if tir_by_h.get("tir_4h") else 0

        print(f"{pid:<20} {len(pm):>4} {100*ov_tir:>5.1f}% "
              f"{''.join(parts)} {d1:>+6.1f}% {d4:>+6.1f}%")

        patient_results[pid] = {
            "n_meals": len(pm),
            "overall_tir": round(100 * ov_tir, 1),
            "postmeal_tir_1h": round(100 * tir_by_h["tir_1h"], 1) if tir_by_h.get("tir_1h") else None,
            "postmeal_tir_2h": round(100 * tir_by_h["tir_2h"], 1) if tir_by_h.get("tir_2h") else None,
            "postmeal_tir_3h": round(100 * tir_by_h["tir_3h"], 1) if tir_by_h.get("tir_3h") else None,
            "postmeal_tir_4h": round(100 * tir_by_h["tir_4h"], 1) if tir_by_h.get("tir_4h") else None,
            "delta_tir_1h": round(d1, 1),
            "delta_tir_4h": round(d4, 1),
        }

    # Population average
    all_tir_vals = {}
    for h in [1, 2, 3, 4]:
        key = f"tir_{h}h"
        vals = [m[key] for m in meals if m.get(key) is not None]
        all_tir_vals[key] = float(np.mean(vals)) if vals else None

    all_ov = float(np.mean(list(overall_tir.values())))

    print("-" * 80)
    print(f"\nPopulation overall TIR: {100*all_ov:.1f}%")
    for h in [1, 2, 3, 4]:
        v = all_tir_vals.get(f"tir_{h}h")
        if v is not None:
            delta = (v - all_ov) * 100
            print(f"  Post-meal TIR at {h}h: {100*v:.1f}% (Δ = {delta:+.1f}%)")

    # TIR by meal size
    print(f"\nPost-meal TIR by meal size (4h window):")
    print(f"  {'Category':<12} {'N':>5} {'TIR4h':>7}")
    for cat in MEAL_SIZE_BINS:
        cm = [m for m in meals if m["size_category"] == cat
              and m.get("tir_4h") is not None]
        if cm:
            mean_t = float(np.mean([m["tir_4h"] for m in cm]))
            print(f"  {cat:<12} {len(cm):>5} {100*mean_t:>6.1f}%")

    return {
        "population": {
            "overall_tir": round(100 * all_ov, 1),
            "postmeal_tir_1h": round(100 * all_tir_vals["tir_1h"], 1) if all_tir_vals.get("tir_1h") else None,
            "postmeal_tir_2h": round(100 * all_tir_vals["tir_2h"], 1) if all_tir_vals.get("tir_2h") else None,
            "postmeal_tir_3h": round(100 * all_tir_vals["tir_3h"], 1) if all_tir_vals.get("tir_3h") else None,
            "postmeal_tir_4h": round(100 * all_tir_vals["tir_4h"], 1) if all_tir_vals.get("tir_4h") else None,
        },
        "tir_by_meal_size": {
            cat: round(100 * float(np.mean([m["tir_4h"] for m in meals
                                            if m["size_category"] == cat
                                            and m.get("tir_4h") is not None])), 1)
            if any(m["size_category"] == cat and m.get("tir_4h") is not None for m in meals)
            else None
            for cat in MEAL_SIZE_BINS
        },
        "patient_results": patient_results,
    }


# ── Main ─────────────────────────────────────────────────────────────

def convert(obj):
    """JSON serializer for numpy types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    print("=" * 60)
    print("CARB RATIO RESPONSE CURVE ANALYSIS (EXP-2535a–e)")
    print("=" * 60)

    results = {}

    # EXP-2535a: Meal extraction
    res_a = exp_2535a_meal_extraction(df)
    meals = res_a.pop("_meals")
    results["exp_2535a"] = res_a
    print()

    # EXP-2535b: Effective CR
    results["exp_2535b"] = exp_2535b_effective_cr(meals)
    print()

    # EXP-2535c: Dose-dependent CR
    results["exp_2535c"] = exp_2535c_dose_dependent_cr(meals)
    print()

    # EXP-2535d: CR adequacy
    results["exp_2535d"] = exp_2535d_cr_adequacy(meals)
    print()

    # EXP-2535e: Post-meal TIR
    results["exp_2535e"] = exp_2535e_postmeal_tir(df, meals)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "exp-2535_cr_response.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
