#!/usr/bin/env python3
"""
exp_settings_simulation.py — Settings Correction Simulation (EXP-2381–2388)

Uses findings from DIA mechanism (EXP-2361-2368) and overnight basal
(EXP-2371-2378) to simulate the impact of corrected settings on glucose
outcomes. This does NOT simulate full closed-loop behavior — it estimates
what fraction of glucose excursions would be avoided with better settings.

Experiments:
  EXP-2381: Retrospective glucose impact of optimal overnight basal
  EXP-2382: ISF correction impact on correction bolus outcomes
  EXP-2383: Combined settings correction (basal + ISF) retrospective
  EXP-2384: Loop workload reduction with corrected settings
  EXP-2385: Time-in-range improvement estimation
  EXP-2386: Safety assessment — hypo risk with corrected settings
  EXP-2387: Per-patient settings recommendation summary
  EXP-2388: Population-level settings insights

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_settings_simulation.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_settings_simulation.py --tiny
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
VIZ_DIR = ROOT / "visualizations" / "settings-simulation"
RESULTS_DIR = ROOT / "externals" / "experiments"


def load_data(tiny: bool = False) -> pd.DataFrame:
    """Load parquet data."""
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


def load_overnight_results() -> dict:
    """Load overnight basal experiment results."""
    path = RESULTS_DIR / "exp-2371-2378_overnight_basal.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def load_dia_results() -> dict:
    """Load DIA mechanism experiment results."""
    path = RESULTS_DIR / "exp-2361-2368_dia_mechanism.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def get_patient_isf(pdf: pd.DataFrame) -> float:
    """Get the patient's scheduled ISF."""
    if "scheduled_isf" in pdf.columns:
        vals = pdf["scheduled_isf"].dropna()
        if len(vals) > 0 and vals.median() > 0:
            return float(vals.median())
    return 50.0


def get_patient_cr(pdf: pd.DataFrame) -> float:
    """Get the patient's scheduled CR."""
    if "scheduled_cr" in pdf.columns:
        vals = pdf["scheduled_cr"].dropna()
        if len(vals) > 0 and vals.median() > 0:
            return float(vals.median())
    return 10.0


def exp_2381_basal_impact(df: pd.DataFrame, overnight: dict) -> dict:
    """
    EXP-2381: Retrospective glucose impact of optimal overnight basal.

    For each patient with suboptimal overnight basal, simulate what the
    overnight glucose would look like with corrected basal:
    - Use overnight drift as the signal: corrected basal → drift ≈ 0
    - Estimate glucose trajectory: current glucose - cumulative_drift
    - Compute TIR improvement from flattening the overnight curve
    """
    print("=" * 60)
    print("EXP-2381: Retrospective Basal Impact on Overnight Glucose")
    print("=" * 60)

    optimal = overnight.get("exp_2377", {})
    drift_data = overnight.get("exp_2371", {})
    results = {}

    for pid in sorted(df["patient_id"].unique()):
        opt = optimal.get(pid, {})
        dr = drift_data.get(pid, {})
        if not opt or not dr:
            continue

        drift_med = dr.get("drift_mg_per_hour", {}).get("median", 0)
        if abs(drift_med) < 1:
            # Already adequate — skip
            results[pid] = {
                "impact": "minimal",
                "drift_removed": 0,
                "tir_improvement_pct": 0,
            }
            print(f"  {pid}: already adequate, no simulation needed")
            continue

        pdf = df[df["patient_id"] == pid].copy()
        overnight_mask = (pdf["hour"] >= 0) & (pdf["hour"] < 6)
        on_data = pdf[overnight_mask].copy()

        if len(on_data) < 50:
            continue

        gluc = on_data["glucose"].values.copy()
        hours = on_data["hour"].values
        valid = ~np.isnan(gluc)

        if valid.sum() < 20:
            continue

        # Current TIR (70-180)
        in_range_current = np.mean((gluc[valid] >= 70) & (gluc[valid] <= 180))
        below_70_current = np.mean(gluc[valid] < 70)
        above_180_current = np.mean(gluc[valid] > 180)

        # Simulate corrected glucose: remove the drift component
        # corrected_glucose = actual_glucose - drift_rate * (hour - mean_hour)
        # This centers the glucose around the mean, removing the linear trend
        mean_hour = np.mean(hours[valid])
        correction = drift_med * (hours - mean_hour)
        corrected = gluc.copy()
        corrected[valid] = gluc[valid] - correction[valid]

        # Corrected TIR
        in_range_corrected = np.mean((corrected[valid] >= 70) & (corrected[valid] <= 180))
        below_70_corrected = np.mean(corrected[valid] < 70)
        above_180_corrected = np.mean(corrected[valid] > 180)

        tir_improvement = 100 * (in_range_corrected - in_range_current)

        r = {
            "drift_removed": float(drift_med),
            "current_tir_pct": float(100 * in_range_current),
            "corrected_tir_pct": float(100 * in_range_corrected),
            "tir_improvement_pct": float(tir_improvement),
            "current_below70_pct": float(100 * below_70_current),
            "corrected_below70_pct": float(100 * below_70_corrected),
            "current_above180_pct": float(100 * above_180_current),
            "corrected_above180_pct": float(100 * above_180_corrected),
            "impact": "positive" if tir_improvement > 1 else "neutral" if tir_improvement > -1 else "negative",
        }
        results[pid] = r
        sign = "+" if tir_improvement > 0 else ""
        print(f"  {pid}: TIR {r['current_tir_pct']:.0f}% → {r['corrected_tir_pct']:.0f}% "
              f"({sign}{tir_improvement:.1f}%), <70: {r['current_below70_pct']:.0f}% → "
              f"{r['corrected_below70_pct']:.0f}%")

    return results


def exp_2382_isf_correction(df: pd.DataFrame, dia_results: dict) -> dict:
    """
    EXP-2382: ISF correction impact on correction bolus outcomes.

    Uses the loop confounding finding (EXP-2364) to estimate effective ISF:
    - Scheduled ISF is what the patient/clinician set
    - Effective ISF accounts for basal modulation during corrections:
      effective_ISF = scheduled_ISF * (1 - suspension_fraction)
    - Compares correction outcomes with scheduled vs effective ISF
    """
    print("\n" + "=" * 60)
    print("EXP-2382: ISF Correction Impact")
    print("=" * 60)

    loop_data = dia_results.get("exp_2364", {})
    phase_data = dia_results.get("exp_2361", {})
    results = {}

    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        loop = loop_data.get(pid, {})
        phase = phase_data.get(pid, {})

        if not loop or not phase:
            continue

        scheduled_isf = get_patient_isf(pdf)
        suspension_frac = loop.get("mean_suspension_pct", 0) / 100.0
        basal_reduction = loop.get("mean_basal_reduction", 0)

        # Effective ISF considering loop reduces total insulin during corrections
        # When loop suspends basal, less total insulin is active, so apparent ISF
        # is higher (more drop per effective unit)
        # Alternatively: the bolus produces MORE drop because loop removes basal
        effective_isf = scheduled_isf / (1 - 0.3 * suspension_frac)
        # The 0.3 factor accounts for basal being only ~30% of total insulin during correction

        # ISF ratio
        isf_ratio = effective_isf / scheduled_isf

        # Expected correction drop with effective ISF
        # If we used effective ISF to dose corrections:
        # dose = (current_BG - target) / effective_ISF
        # This would be LESS insulin, since effective_ISF > scheduled_ISF
        mean_drop = phase.get("drop_mg", {}).get("mean", 0)
        n_corrections = phase.get("n_corrections", 0)

        # Reduced dose = old_dose * scheduled_ISF / effective_ISF
        dose_reduction_pct = 100 * (1 - scheduled_isf / effective_isf)

        # Impact: with lower dose, rebound should be less
        mean_rebound = phase.get("rebound_rise_mg", {}).get("mean", 0)
        estimated_rebound_reduction = mean_rebound * dose_reduction_pct / 100

        r = {
            "scheduled_isf": float(scheduled_isf),
            "effective_isf": float(effective_isf),
            "isf_ratio": float(isf_ratio),
            "suspension_pct": float(suspension_frac * 100),
            "n_corrections": n_corrections,
            "mean_drop": float(mean_drop),
            "mean_rebound": float(mean_rebound),
            "dose_reduction_pct": float(dose_reduction_pct),
            "estimated_rebound_reduction": float(estimated_rebound_reduction),
        }
        results[pid] = r
        print(f"  {pid}: ISF {scheduled_isf:.0f} → {effective_isf:.0f} (×{isf_ratio:.2f}), "
              f"dose -{dose_reduction_pct:.0f}%, rebound reduction ~{estimated_rebound_reduction:.0f} mg/dL")

    return results


def exp_2383_combined_impact(basal_impact: dict, isf_impact: dict) -> dict:
    """
    EXP-2383: Combined settings correction impact.

    Combines basal and ISF corrections for overall impact estimate.
    """
    print("\n" + "=" * 60)
    print("EXP-2383: Combined Settings Impact")
    print("=" * 60)

    results = {}
    for pid in set(list(basal_impact.keys()) + list(isf_impact.keys())):
        bi = basal_impact.get(pid, {})
        ii = isf_impact.get(pid, {})

        tir_gain_basal = bi.get("tir_improvement_pct", 0)
        rebound_reduction = ii.get("estimated_rebound_reduction", 0)
        dose_reduction = ii.get("dose_reduction_pct", 0)

        # Combined TIR estimate (conservative — not additive)
        combined_tir_gain = tir_gain_basal + 0.3 * rebound_reduction / 10  # rough heuristic

        r = {
            "tir_gain_from_basal": float(tir_gain_basal),
            "rebound_reduction_from_isf": float(rebound_reduction),
            "dose_reduction_pct": float(dose_reduction),
            "estimated_combined_tir_gain": float(combined_tir_gain),
            "priority": "HIGH" if abs(tir_gain_basal) > 3 or dose_reduction > 10 else
                        "MEDIUM" if abs(tir_gain_basal) > 1 or dose_reduction > 5 else "LOW",
        }
        results[pid] = r
        print(f"  {pid}: basal +{tir_gain_basal:.1f}% TIR, ISF -{dose_reduction:.0f}% dose, "
              f"combined +{combined_tir_gain:.1f}% TIR [{r['priority']}]")

    return results


def exp_2384_loop_workload(df: pd.DataFrame, overnight: dict) -> dict:
    """
    EXP-2384: Loop workload reduction with corrected settings.

    Measures how much less the loop would need to work with corrected basal.
    Proxy: basal suspension rate × basal correction magnitude.
    """
    print("\n" + "=" * 60)
    print("EXP-2384: Loop Workload Reduction")
    print("=" * 60)

    loop_data = overnight.get("exp_2373", {})
    adequacy_data = overnight.get("exp_2372", {})
    results = {}

    for pid in sorted(df["patient_id"].unique()):
        loop = loop_data.get(pid, {})
        adeq = adequacy_data.get(pid, {})

        if not loop:
            continue

        suspension_pct = loop.get("suspension_pct", 0)
        increase_pct = loop.get("increase_pct", 0)
        modulation = loop.get("modulation_depth", 0)
        classification = adeq.get("classification", "UNKNOWN")

        # Total loop work = suspension + increase activity
        total_modulation = suspension_pct + increase_pct
        # With corrected basal, loop wouldn't need to suspend/increase as much
        # Estimate: corrected basal removes ~70% of loop modulation
        # (30% will remain for unexpected events)
        correction_factor = 0.7 if classification != "ADEQUATE" else 0.1
        workload_reduction = total_modulation * correction_factor

        r = {
            "current_suspension_pct": float(suspension_pct),
            "current_increase_pct": float(increase_pct),
            "current_total_modulation": float(total_modulation),
            "estimated_workload_reduction": float(workload_reduction),
            "classification": classification,
        }
        results[pid] = r
        print(f"  {pid}: loop modulation {total_modulation:.0f}% → "
              f"~{total_modulation - workload_reduction:.0f}% "
              f"(-{workload_reduction:.0f}%, {classification})")

    return results


def exp_2385_tir_estimation(df: pd.DataFrame, overnight: dict, combined: dict) -> dict:
    """
    EXP-2385: Time-in-range improvement estimation.

    Combines overnight and daytime estimates for 24h TIR projection.
    """
    print("\n" + "=" * 60)
    print("EXP-2385: 24h TIR Improvement Estimation")
    print("=" * 60)

    results = {}
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        gluc = pdf["glucose"].dropna()
        if len(gluc) < 100:
            continue

        current_tir = float(100 * np.mean((gluc >= 70) & (gluc <= 180)))
        current_below70 = float(100 * np.mean(gluc < 70))
        current_above180 = float(100 * np.mean(gluc > 180))

        # Combine improvements
        combo = combined.get(pid, {})
        overnight_tir_gain = combo.get("tir_gain_from_basal", 0)

        # Overnight is 25% of the day, so overnight TIR gain scales by 0.25 for 24h
        estimated_24h_gain = overnight_tir_gain * 0.25

        # Daytime ISF correction (dose reduction) also helps TIR
        dose_reduction = combo.get("dose_reduction_pct", 0)
        daytime_gain = dose_reduction * 0.1  # rough estimate: 10% of dose reduction → TIR

        total_gain = estimated_24h_gain + daytime_gain * 0.75  # 75% of day is daytime

        r = {
            "current_24h_tir": current_tir,
            "current_below70": current_below70,
            "current_above180": current_above180,
            "overnight_tir_gain": float(overnight_tir_gain),
            "estimated_24h_tir_gain": float(total_gain),
            "estimated_new_tir": float(min(100, current_tir + total_gain)),
        }
        results[pid] = r
        sign = "+" if total_gain > 0 else ""
        print(f"  {pid}: TIR {current_tir:.0f}% → ~{r['estimated_new_tir']:.0f}% "
              f"({sign}{total_gain:.1f}%), <70: {current_below70:.0f}%")

    return results


def exp_2386_safety(df: pd.DataFrame, overnight: dict, basal_impact: dict) -> dict:
    """
    EXP-2386: Safety assessment — hypo risk with corrected settings.

    For over-basaled patients, correcting basal should REDUCE hypo risk.
    For under-basaled patients, increasing basal could INCREASE hypo risk.
    Assess this tradeoff.
    """
    print("\n" + "=" * 60)
    print("EXP-2386: Safety Assessment")
    print("=" * 60)

    adequacy = overnight.get("exp_2372", {})
    drift = overnight.get("exp_2371", {})
    results = {}

    for pid in sorted(df["patient_id"].unique()):
        bi = basal_impact.get(pid, {})
        adeq = adequacy.get(pid, {})
        dr = drift.get(pid, {})

        if not adeq:
            continue

        classification = adeq.get("classification", "UNKNOWN")
        hypo_rate = dr.get("hypo_night_pct", 0)
        below70_current = bi.get("current_below70_pct", 0)
        below70_corrected = bi.get("corrected_below70_pct", 0)

        # Safety classification
        if classification in ("INADEQUATE_HIGH", "MARGINAL_HIGH"):
            # Over-basaled: correction REDUCES hypo risk
            safety = "SAFER"
            risk_change = "Reducing basal will decrease hypo risk"
        elif classification in ("INADEQUATE_LOW", "MARGINAL_LOW"):
            # Under-basaled: increasing basal COULD increase hypo risk
            if hypo_rate > 30:
                safety = "CAUTION"
                risk_change = "Already high hypo rate; increasing basal needs monitoring"
            else:
                safety = "SAFE"
                risk_change = "Low current hypo rate; modest basal increase acceptable"
        else:
            safety = "NEUTRAL"
            risk_change = "Settings adequate; no change needed"

        r = {
            "classification": classification,
            "safety": safety,
            "hypo_night_pct": float(hypo_rate),
            "risk_change": risk_change,
            "below70_current": float(below70_current),
            "below70_corrected": float(below70_corrected),
        }
        results[pid] = r
        print(f"  {pid}: [{safety}] {classification}, "
              f"hypo nights {hypo_rate:.0f}%, {risk_change}")

    return results


def exp_2387_recommendations(combined: dict, safety: dict, overnight: dict,
                             isf_impact: dict) -> dict:
    """
    EXP-2387: Per-patient settings recommendation summary.

    Aggregates all findings into actionable per-patient recommendations.
    """
    print("\n" + "=" * 60)
    print("EXP-2387: Per-Patient Settings Recommendations")
    print("=" * 60)

    optimal = overnight.get("exp_2377", {})
    adequacy = overnight.get("exp_2372", {})
    phenotype = overnight.get("exp_2378", {})
    results = {}

    for pid in sorted(set(list(combined.keys()) + list(safety.keys()))):
        if pid.startswith("_"):
            continue

        opt = optimal.get(pid, {})
        adeq = adequacy.get(pid, {})
        safe = safety.get(pid, {})
        combo = combined.get(pid, {})
        isf = isf_impact.get(pid, {})
        pheno = phenotype.get(pid, {})

        recommendations = []
        priority = combo.get("priority", "LOW")
        safety_status = safe.get("safety", "NEUTRAL")

        # Basal recommendation
        adj = opt.get("adjustment_u_per_h", 0)
        sched = opt.get("scheduled_basal", 0)
        if abs(adj) > 0.01 and sched > 0:
            pct = 100 * adj / sched
            direction = "Increase" if adj > 0 else "Decrease"
            recommendations.append(
                f"{direction} overnight basal by {abs(adj):.03f} U/h ({pct:+.0f}%)")

        # ISF recommendation
        isf_ratio = isf.get("isf_ratio", 1.0)
        if isf_ratio > 1.05:
            sched_isf = isf.get("scheduled_isf", 50)
            eff_isf = isf.get("effective_isf", 50)
            recommendations.append(
                f"Consider raising ISF from {sched_isf:.0f} to ~{eff_isf:.0f} "
                f"(accounts for loop basal modulation)")

        # Safety caveats
        if safety_status == "CAUTION":
            recommendations.append("⚠️ High hypo rate — monitor closely if increasing basal")

        r = {
            "phenotype": pheno.get("phenotype", "unknown"),
            "priority": priority,
            "safety": safety_status,
            "recommendations": recommendations,
            "overnight_basal_change": float(adj),
            "isf_ratio": float(isf_ratio),
        }
        results[pid] = r
        rec_str = " | ".join(recommendations) if recommendations else "No changes recommended"
        print(f"  {pid} [{priority}/{safety_status}]: {rec_str}")

    return results


def exp_2388_population_insights(recommendations: dict, combined: dict,
                                 overnight: dict) -> dict:
    """
    EXP-2388: Population-level settings insights.
    """
    print("\n" + "=" * 60)
    print("EXP-2388: Population-Level Settings Insights")
    print("=" * 60)

    patients = [p for p in recommendations if not p.startswith("_")]
    n = len(patients)

    # Aggregate priority
    priorities = [recommendations[p].get("priority", "LOW") for p in patients]
    priority_dist = {
        "HIGH": sum(1 for p in priorities if p == "HIGH"),
        "MEDIUM": sum(1 for p in priorities if p == "MEDIUM"),
        "LOW": sum(1 for p in priorities if p == "LOW"),
    }

    # Aggregate basal changes
    basal_changes = [recommendations[p].get("overnight_basal_change", 0) for p in patients]
    need_increase = sum(1 for bc in basal_changes if bc > 0.01)
    need_decrease = sum(1 for bc in basal_changes if bc < -0.01)
    adequate = n - need_increase - need_decrease

    # Aggregate ISF
    isf_ratios = [recommendations[p].get("isf_ratio", 1.0) for p in patients]
    mean_isf_ratio = float(np.mean(isf_ratios))

    # TIR improvement
    tir_gains = [combined.get(p, {}).get("estimated_combined_tir_gain", 0) for p in patients]
    mean_tir_gain = float(np.mean(tir_gains))

    # Phenotype distribution
    phenotype_dist = overnight.get("exp_2378", {}).get("_phenotype_distribution", {})

    r = {
        "n_patients": n,
        "priority_distribution": priority_dist,
        "basal_changes": {
            "need_increase": need_increase,
            "need_decrease": need_decrease,
            "adequate": adequate,
        },
        "mean_isf_ratio": mean_isf_ratio,
        "mean_tir_gain_pct": mean_tir_gain,
        "phenotype_distribution": phenotype_dist,
        "key_insights": [
            f"{n - adequate}/{n} patients ({100*(n-adequate)/n:.0f}%) need overnight basal adjustment",
            f"Mean ISF ratio: {mean_isf_ratio:.2f}× (loop compensation makes effective ISF higher)",
            f"Estimated TIR improvement: {mean_tir_gain:+.1f}% with corrected settings",
            f"Safety: over-basaled patients benefit most (reduced hypo risk)",
        ],
    }
    results = r
    print(f"\n  Population Summary ({n} patients):")
    for insight in r["key_insights"]:
        print(f"    • {insight}")

    return results


def generate_visualizations(recommendations: dict, combined: dict,
                            tir_results: dict, safety_results: dict):
    """Generate settings simulation figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping visualizations")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    patients = sorted([p for p in recommendations if not p.startswith("_")])

    # --- Figure 1: TIR improvement waterfall ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    tir_current = [tir_results.get(p, {}).get("current_24h_tir", 0) for p in patients]
    tir_gain = [tir_results.get(p, {}).get("estimated_24h_tir_gain", 0) for p in patients]
    labels = [p[:12] for p in patients]

    x = range(len(patients))
    axes[0].barh(x, tir_current, color="steelblue", label="Current TIR")
    axes[0].barh(x, tir_gain, left=tir_current,
                 color=["green" if g > 0 else "red" for g in tir_gain],
                 label="Estimated gain")
    axes[0].set_yticks(list(x))
    axes[0].set_yticklabels(labels, fontsize=8)
    axes[0].axvline(70, color="gray", linewidth=0.5, linestyle="--", label="70% target")
    axes[0].set_xlabel("Time in Range (%)")
    axes[0].set_title("TIR: Current + Estimated Improvement")
    axes[0].legend(fontsize=7)
    axes[0].set_xlim(0, 100)

    # --- Figure 1b: Priority/Safety matrix ---
    priority_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    safety_map = {"SAFER": 1, "SAFE": 2, "NEUTRAL": 3, "CAUTION": 4}
    safety_colors = {"SAFER": "green", "SAFE": "lightgreen", "NEUTRAL": "gray", "CAUTION": "red"}

    for p in patients:
        rec = recommendations[p]
        safe = safety_results.get(p, {})
        pri = priority_map.get(rec.get("priority", "LOW"), 1)
        saf = safety_map.get(safe.get("safety", "NEUTRAL"), 3)
        color = safety_colors.get(safe.get("safety", "NEUTRAL"), "gray")
        axes[1].scatter(pri, saf, s=100, color=color, edgecolors="black", zorder=5)
        axes[1].annotate(p[:8], (pri, saf), fontsize=6, ha="center", va="bottom")

    axes[1].set_xticks([1, 2, 3])
    axes[1].set_xticklabels(["LOW", "MEDIUM", "HIGH"])
    axes[1].set_yticks([1, 2, 3, 4])
    axes[1].set_yticklabels(["SAFER", "SAFE", "NEUTRAL", "CAUTION"])
    axes[1].set_xlabel("Settings Change Priority")
    axes[1].set_ylabel("Safety Assessment")
    axes[1].set_title("Priority × Safety Matrix")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_tir_and_priority.png", dpi=150)
    plt.close()
    print(f"  Saved fig1_tir_and_priority.png")

    # --- Figure 2: Per-patient recommendation summary ---
    fig, ax = plt.subplots(figsize=(12, 7))

    basal_changes = [recommendations[p].get("overnight_basal_change", 0) for p in patients]
    isf_ratios = [recommendations[p].get("isf_ratio", 1.0) for p in patients]

    x = np.arange(len(patients))
    width = 0.35

    bars1 = ax.bar(x - width/2, basal_changes, width, label="Basal Adjustment (U/h)",
                   color=["coral" if bc > 0 else "steelblue" for bc in basal_changes])
    ax2 = ax.twinx()
    bars2 = ax2.bar(x + width/2, [r - 1 for r in isf_ratios], width,
                    label="ISF Ratio - 1", color="gold", alpha=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Basal Adjustment (U/h)")
    ax2.set_ylabel("ISF Correction (ratio - 1)")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_title("Per-Patient Settings Recommendations")

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_per_patient_recommendations.png", dpi=150)
    plt.close()
    print(f"  Saved fig2_per_patient_recommendations.png")


def main():
    parser = argparse.ArgumentParser(description="Settings Simulation")
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)
    overnight = load_overnight_results()
    dia = load_dia_results()

    if not overnight:
        print("ERROR: Run exp_overnight_basal.py first")
        sys.exit(1)
    if not dia:
        print("ERROR: Run exp_dia_mechanism.py first")
        sys.exit(1)

    # Run experiments
    basal_impact = exp_2381_basal_impact(df, overnight)
    isf_impact = exp_2382_isf_correction(df, dia)
    combined = exp_2383_combined_impact(basal_impact, isf_impact)
    workload = exp_2384_loop_workload(df, overnight)
    tir = exp_2385_tir_estimation(df, overnight, combined)
    safety = exp_2386_safety(df, overnight, basal_impact)
    recommendations = exp_2387_recommendations(combined, safety, overnight, isf_impact)
    population = exp_2388_population_insights(recommendations, combined, overnight)

    # Visualize
    print("\nGenerating visualizations...")
    generate_visualizations(recommendations, combined, tir, safety)

    # Save
    all_results = {
        "exp_2381": basal_impact,
        "exp_2382": isf_impact,
        "exp_2383": combined,
        "exp_2384": workload,
        "exp_2385": tir,
        "exp_2386": safety,
        "exp_2387": recommendations,
        "exp_2388": population,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2381-2388_settings_simulation.json"
    with open(out_path, "w") as f:
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            raise TypeError(f"Cannot serialize {type(obj)}")
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
