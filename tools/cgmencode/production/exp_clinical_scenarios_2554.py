"""
EXP-2554: Clinical Scenario Demonstrations
===========================================

Research question: Can the forward simulation engine model clinically
meaningful therapy optimization scenarios?

Scenarios:
  S1: Pre-bolus timing — how much does 15min vs 30min pre-bolus improve TIR?
  S2: Basal optimization — overnight correction drift from incorrect basal
  S3: Exercise override — reduced basal by 50% for exercise
  S4: ISF correction effectiveness — undersensitive ISF (profile says 50, need 70)
  S5: Carb ratio correction — under-bolusing from wrong CR
  S6: Dawn phenomenon — ISF schedule with morning spike

Each scenario compares baseline vs modified therapy and generates side-by-side
visualizations showing glucose trajectories and TIR changes.

Figures:
  fig_2554_prebolus.png        — Pre-bolus timing comparison
  fig_2554_basal_overnight.png — Overnight basal correction
  fig_2554_exercise.png        — Exercise override effect
  fig_2554_isf_correction.png  — ISF correction effectiveness
  fig_2554_cr_correction.png   — CR correction effectiveness
  fig_2554_dawn.png            — Dawn phenomenon ISF schedule
  fig_2554_dashboard.png       — Summary dashboard all scenarios
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

from cgmencode.production.forward_simulator import (
    forward_simulate, compare_scenarios, simulate_typical_day,
    TherapySettings, InsulinEvent, CarbEvent,
)


def _figures_dir() -> Path:
    d = Path(__file__).resolve().parents[3] / "docs" / "60-research" / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Scenario 1: Pre-bolus Timing ─────────────────────────────────────

def scenario_prebolus() -> dict:
    """Compare no pre-bolus, 15min, and 30min pre-bolus for a 45g meal."""
    settings = TherapySettings(isf=50, cr=10, basal_rate=0.8)
    meal_time = 60  # minutes
    meal_grams = 45.0
    bolus_units = meal_grams / settings.cr  # 4.5U

    traces = {}
    summaries = {}

    for label, pre_min in [("No pre-bolus", 0), ("15min pre-bolus", 15),
                           ("30min pre-bolus", 30)]:
        r = forward_simulate(
            120.0, settings, duration_hours=6.0,
            bolus_events=[InsulinEvent(meal_time - pre_min, bolus_units)],
            carb_events=[CarbEvent(meal_time, meal_grams)],
            seed=42,
        )
        traces[label] = r.glucose.tolist()
        summaries[label] = {
            "tir": round(r.tir * 100, 1),
            "peak_glucose": round(float(r.glucose.max()), 1),
            "time_to_peak_min": round(float(np.argmax(r.glucose) * 5), 0),
            "mean_glucose": round(r.mean_glucose, 1),
        }

    peak_reduction = summaries["No pre-bolus"]["peak_glucose"] - summaries["30min pre-bolus"]["peak_glucose"]
    return {
        "traces": traces,
        "summaries": summaries,
        "peak_reduction_30min": round(peak_reduction, 1),
    }


# ── Scenario 2: Overnight Basal Correction ───────────────────────────

def scenario_overnight_basal() -> dict:
    """Overnight correction: basal too low (0.6 vs need of 0.8)."""
    metabolic_need = 0.8

    traces = {}
    summaries = {}

    for label, rate in [("Too low (0.6)", 0.6), ("Correct (0.8)", 0.8),
                        ("Too high (1.0)", 1.0)]:
        settings = TherapySettings(isf=50, cr=10, basal_rate=rate)
        r = forward_simulate(
            120.0, settings, duration_hours=10.0,
            start_hour=22.0,  # overnight
            metabolic_basal_rate=metabolic_need,
            seed=42,
        )
        traces[label] = r.glucose.tolist()
        summaries[label] = {
            "final_glucose": round(float(r.glucose[-1]), 1),
            "min_glucose": round(float(r.glucose.min()), 1),
            "max_glucose": round(float(r.glucose.max()), 1),
            "tir": round(r.tir * 100, 1),
            "tbr": round(r.tbr * 100, 1),
        }

    drift_low = summaries["Too low (0.6)"]["final_glucose"] - 120.0
    drift_high = 120.0 - summaries["Too high (1.0)"]["final_glucose"]
    return {
        "traces": traces,
        "summaries": summaries,
        "drift_from_low_basal": round(drift_low, 1),
        "drift_from_high_basal": round(drift_high, 1),
    }


# ── Scenario 3: Exercise Override ─────────────────────────────────────

def scenario_exercise() -> dict:
    """Exercise: reduce basal by 50% for 1h before and during exercise."""
    metabolic_need = 0.8

    # Baseline: normal basal, exercise at 120min for 60min
    base = TherapySettings(isf=50, cr=10, basal_rate=0.8)
    r_base = forward_simulate(120.0, base, duration_hours=6.0, seed=42)

    # With exercise temp basal: 0.4 U/hr from 60-180min (pre+during)
    # Model exercise as reduced metabolic basal rate during exercise window
    # Since we can't do time-varying metabolic rate, model as temp basal override
    exercise = TherapySettings(isf=50, cr=10, basal_rate=0.8,
                               basal_schedule=[(0, 0.8), (1, 0.4), (3, 0.8)])
    r_ex = forward_simulate(120.0, exercise, duration_hours=6.0,
                            metabolic_basal_rate=metabolic_need, seed=42)

    return {
        "traces": {
            "No override": r_base.glucose.tolist(),
            "50% temp basal (1-3h)": r_ex.glucose.tolist(),
        },
        "summaries": {
            "No override": {
                "tir": round(r_base.tir * 100, 1),
                "tbr": round(r_base.tbr * 100, 1),
                "min_glucose": round(float(r_base.glucose.min()), 1),
            },
            "50% temp basal": {
                "tir": round(r_ex.tir * 100, 1),
                "tbr": round(r_ex.tbr * 100, 1),
                "min_glucose": round(float(r_ex.glucose.min()), 1),
            },
        },
    }


# ── Scenario 4: ISF Correction ───────────────────────────────────────

def scenario_isf_correction() -> dict:
    """Profile says ISF=50, but patient really needs ISF=70. Show effect."""
    comp = compare_scenarios(
        200.0,
        baseline_settings=TherapySettings(isf=50, cr=10, basal_rate=0.8),
        modified_settings=TherapySettings(isf=70, cr=10, basal_rate=0.8),
        duration_hours=8.0,
        bolus_events=[InsulinEvent(0, 2.0)],
        seed=42,
        baseline_label="Current ISF=50",
        modified_label="Corrected ISF=70",
    )

    return {
        "traces": {
            comp.baseline_label: comp.baseline.glucose.tolist(),
            comp.modified_label: comp.modified.glucose.tolist(),
        },
        "summary": comp.summary(),
        "explanation": (
            "ISF=50 means 1U drops 50 mg/dL. ISF=70 means 1U drops 70 mg/dL. "
            "With 2U correction from 200: ISF50 expects 100 drop, ISF70 expects 140 drop. "
            "The two-component DIA distributes some effect beyond DIA window."
        ),
    }


# ── Scenario 5: CR Correction ────────────────────────────────────────

def scenario_cr_correction() -> dict:
    """Profile CR=10, but patient needs CR=8 (under-bolusing). Show effect.

    Both simulations use the same patient physiology (ISF=50, true CR=8).
    The difference is the bolus dose: under-bolused uses CR=10 for dosing,
    correctly bolused uses CR=8.
    """
    settings = TherapySettings(isf=50, cr=8, basal_rate=0.8)  # true patient CR=8
    meal = [CarbEvent(60, 60)]

    # Under-bolused: dose calculated with wrong CR=10 → 6U
    r_under = forward_simulate(120.0, settings, duration_hours=6.0,
        bolus_events=[InsulinEvent(60, 60.0 / 10)],  # 6U
        carb_events=meal, seed=42)

    # Correct bolus: dose calculated with correct CR=8 → 7.5U
    r_correct = forward_simulate(120.0, settings, duration_hours=6.0,
        bolus_events=[InsulinEvent(60, 60.0 / 8)],  # 7.5U
        carb_events=meal, seed=42)

    return {
        "traces": {
            "CR=10 (under-bolused, 6U)": r_under.glucose.tolist(),
            "CR=8 (correct, 7.5U)": r_correct.glucose.tolist(),
        },
        "summaries": {
            "CR=10 (under)": {
                "bolus": 6.0, "peak": round(float(r_under.glucose.max()), 1),
                "tir": round(r_under.tir * 100, 1),
            },
            "CR=8 (correct)": {
                "bolus": 7.5, "peak": round(float(r_correct.glucose.max()), 1),
                "tir": round(r_correct.tir * 100, 1),
            },
        },
        "peak_reduction": round(float(r_under.glucose.max() - r_correct.glucose.max()), 1),
    }


# ── Scenario 6: Dawn Phenomenon ISF Schedule ─────────────────────────

def scenario_dawn() -> dict:
    """Model dawn phenomenon with circadian ISF schedule.

    Dawn phenomenon: reduced insulin sensitivity 4-8am.
    Schedule: ISF=50 normally, ISF=35 during 4-8am.
    """
    flat = TherapySettings(isf=50, cr=10, basal_rate=0.8)
    circadian = TherapySettings(isf=50, cr=10, basal_rate=0.8,
        isf_schedule=[(0, 50), (4, 35), (8, 50)])

    # Overnight with correction at 3am
    r_flat = forward_simulate(150.0, flat, duration_hours=10.0,
        start_hour=22.0,
        bolus_events=[InsulinEvent(300, 1.5)],  # 3am correction (5h in)
        seed=42)
    r_dawn = forward_simulate(150.0, circadian, duration_hours=10.0,
        start_hour=22.0,
        bolus_events=[InsulinEvent(300, 1.5)],  # 3am correction (5h in)
        seed=42)

    return {
        "traces": {
            "Flat ISF=50": r_flat.glucose.tolist(),
            "Dawn ISF: 50→35→50": r_dawn.glucose.tolist(),
        },
        "summaries": {
            "Flat ISF": {
                "final_glucose": round(float(r_flat.glucose[-1]), 1),
                "min_glucose": round(float(r_flat.glucose.min()), 1),
                "tir": round(r_flat.tir * 100, 1),
            },
            "Dawn ISF": {
                "final_glucose": round(float(r_dawn.glucose[-1]), 1),
                "min_glucose": round(float(r_dawn.glucose.min()), 1),
                "tir": round(r_dawn.tir * 100, 1),
            },
        },
        "explanation": (
            "Dawn phenomenon reduces ISF from 50 to 35 during 4-8am. "
            "Corrections during this window are 30% less effective. "
            "The digital twin can model this and suggest adjusted dosing."
        ),
    }


# ── Plot Figures ─────────────────────────────────────────────────────

def plot_scenario(fig_dir: Path, filename: str, title: str,
                  traces: dict, annotations: dict = None,
                  xlabel: str = 'Hours', duration_hours: float = None):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ['#1976d2', '#d32f2f', '#4caf50', '#ff9800', '#9c27b0']

    for i, (label, trace) in enumerate(traces.items()):
        hours = np.arange(len(trace)) / 12.0
        ax.plot(hours, trace, color=colors[i % len(colors)],
                linewidth=1.5, label=label)

    ax.fill_between([0, hours[-1]], 70, 180, alpha=0.06, color='green')
    ax.axhline(70, color='red', linestyle=':', alpha=0.3)
    ax.axhline(180, color='orange', linestyle=':', alpha=0.3)
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(39, 350)

    if annotations:
        y_pos = 330
        for k, v in annotations.items():
            ax.annotate(f'{k}: {v}', xy=(0.02, y_pos),
                        xycoords=('axes fraction', 'data'),
                        fontsize=8, alpha=0.7)
            y_pos -= 15

    fig.tight_layout()
    fig.savefig(fig_dir / filename, dpi=150)
    plt.close(fig)


def plot_dashboard(fig_dir: Path, all_results: dict):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return

    scenarios = [
        ("Pre-Bolus Timing", "prebolus"),
        ("Overnight Basal", "overnight_basal"),
        ("Exercise Override", "exercise"),
        ("ISF Correction", "isf_correction"),
        ("CR Correction", "cr_correction"),
        ("Dawn Phenomenon", "dawn"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    colors = ['#1976d2', '#d32f2f', '#4caf50', '#ff9800']

    for idx, (ax, (title, key)) in enumerate(zip(axes.flat, scenarios)):
        r = all_results[key]
        for i, (label, trace) in enumerate(r["traces"].items()):
            hours = np.arange(len(trace)) / 12.0
            ax.plot(hours, trace, color=colors[i % len(colors)],
                    linewidth=1.2, label=label)
        ax.fill_between([0, hours[-1]], 70, 180, alpha=0.06, color='green')
        ax.axhline(70, color='red', linestyle=':', alpha=0.2)
        ax.axhline(180, color='orange', linestyle=':', alpha=0.2)
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=7, loc='upper right')
        ax.set_ylim(39, 320)
        ax.grid(True, alpha=0.2)
        if idx >= 3:
            ax.set_xlabel('Hours')
        if idx % 3 == 0:
            ax.set_ylabel('mg/dL')

    fig.suptitle('EXP-2554: Clinical Scenario Dashboard — Digital Twin Forward Simulation',
                 fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(fig_dir / 'fig_2554_dashboard.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved dashboard to {fig_dir / 'fig_2554_dashboard.png'}")


def plot_all(results: dict, fig_dir: Path):
    scenarios = [
        ("fig_2554_prebolus.png", "EXP-2554: Pre-Bolus Timing", "prebolus"),
        ("fig_2554_basal_overnight.png", "EXP-2554: Overnight Basal Correction", "overnight_basal"),
        ("fig_2554_exercise.png", "EXP-2554: Exercise Override", "exercise"),
        ("fig_2554_isf_correction.png", "EXP-2554: ISF Correction Effectiveness", "isf_correction"),
        ("fig_2554_cr_correction.png", "EXP-2554: CR Correction Effectiveness", "cr_correction"),
        ("fig_2554_dawn.png", "EXP-2554: Dawn Phenomenon ISF Schedule", "dawn"),
    ]

    for fname, title, key in scenarios:
        r = results[key]
        plot_scenario(fig_dir, fname, title, r["traces"])

    plot_dashboard(results, fig_dir)

    print(f"  Saved 7 figures to {fig_dir}")


def plot_dashboard_only(results: dict, fig_dir: Path):
    """Just the dashboard."""
    plot_dashboard(fig_dir, results)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EXP-2554: Clinical Scenario Demos")
    parser.add_argument("--figures", action="store_true", help="Generate figures")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2554: Clinical Scenario Demonstrations")
    print("=" * 70)

    results = {}

    print("\n[1/6] Pre-bolus timing...")
    results["prebolus"] = scenario_prebolus()
    r = results["prebolus"]
    for label, s in r["summaries"].items():
        print(f"  {label}: peak={s['peak_glucose']}, TIR={s['tir']}%")
    print(f"  Peak reduction (30min pre-bolus): {r['peak_reduction_30min']} mg/dL")

    print("\n[2/6] Overnight basal correction...")
    results["overnight_basal"] = scenario_overnight_basal()
    r = results["overnight_basal"]
    for label, s in r["summaries"].items():
        print(f"  {label}: final={s['final_glucose']}, TIR={s['tir']}%")

    print("\n[3/6] Exercise override...")
    results["exercise"] = scenario_exercise()
    r = results["exercise"]
    for label, s in r["summaries"].items():
        print(f"  {label}: TIR={s['tir']}%, TBR={s['tbr']}%, min={s['min_glucose']}")

    print("\n[4/6] ISF correction...")
    results["isf_correction"] = scenario_isf_correction()
    r = results["isf_correction"]
    print(f"  Summary: {json.dumps(r['summary'], indent=2)}")

    print("\n[5/6] CR correction...")
    results["cr_correction"] = scenario_cr_correction()
    r = results["cr_correction"]
    for label, s in r["summaries"].items():
        print(f"  {label}: bolus={s['bolus']}U, peak={s['peak']}, TIR={s['tir']}%")
    print(f"  Peak reduction: {r['peak_reduction']} mg/dL")

    print("\n[6/6] Dawn phenomenon ISF schedule...")
    results["dawn"] = scenario_dawn()
    r = results["dawn"]
    for label, s in r["summaries"].items():
        print(f"  {label}: final={s['final_glucose']}, min={s['min_glucose']}, TIR={s['tir']}%")

    # Remove traces from JSON (too large)
    results_json = {}
    for k, v in results.items():
        entry = {kk: vv for kk, vv in v.items() if kk != "traces"}
        results_json[k] = entry

    # Save JSON
    exp_dir = Path(__file__).resolve().parents[3] / "externals" / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    json_path = exp_dir / "exp-2554_clinical_scenarios.json"
    with open(json_path, 'w') as f:
        json.dump(results_json, f, indent=2, default=str)
    print(f"\n  Results saved to {json_path}")

    if args.figures:
        print("\nGenerating figures...")
        fig_dir = _figures_dir()
        scenarios_list = [
            ("fig_2554_prebolus.png", "EXP-2554: Pre-Bolus Timing", "prebolus"),
            ("fig_2554_basal_overnight.png", "EXP-2554: Overnight Basal Correction", "overnight_basal"),
            ("fig_2554_exercise.png", "EXP-2554: Exercise Override", "exercise"),
            ("fig_2554_isf_correction.png", "EXP-2554: ISF Correction Effectiveness", "isf_correction"),
            ("fig_2554_cr_correction.png", "EXP-2554: CR Correction Effectiveness", "cr_correction"),
            ("fig_2554_dawn.png", "EXP-2554: Dawn Phenomenon ISF Schedule", "dawn"),
        ]
        for fname, title, key in scenarios_list:
            r = results[key]
            plot_scenario(fig_dir, fname, title, r["traces"])

        plot_dashboard(fig_dir, results)
        print(f"  Saved 7 figures to {fig_dir}")

    if args.json:
        print(json.dumps(results_json, indent=2, default=str))


if __name__ == "__main__":
    main()
