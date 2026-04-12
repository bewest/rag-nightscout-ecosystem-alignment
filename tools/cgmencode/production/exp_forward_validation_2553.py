"""
EXP-2553: Forward Simulator Validation
=======================================

Research question: Does the forward simulation engine produce physically
correct glucose trajectories across a range of synthetic patients and
clinical scenarios?

Hypotheses:
  H1: Steady-state basal produces flat glucose (residual < 5 mg/dL over 24h)
  H2: Correction bolus drop is proportional to ISF (r > 0.95)
  H3: Two-component DIA produces longer glucose-lowering tail than single-decay
  H4: Meal spike amplitude scales with ISF/CR (r > 0.9)
  H5: Basal mismatch produces predictable glucose drift direction

Method:
  - Generate synthetic patients with varied ISF (30-80), CR (8-15), basal (0.5-1.5)
  - Run each through forward_simulate with controlled inputs
  - Validate relationships between settings and outcomes
  - Compare two-component vs hypothetical single-component behavior

Figures:
  fig_2553_correction_isf.png   — Correction drop vs ISF linearity
  fig_2553_meal_response.png    — Meal spike across ISF/CR combinations
  fig_2553_basal_drift.png      — Glucose drift vs basal mismatch
  fig_2553_two_component_tail.png — Two-comp vs single-decay glucose tail
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


# ── Experiment 1: Correction vs ISF linearity ────────────────────────

def exp_correction_isf() -> dict:
    """Verify that correction bolus drop is proportional to ISF."""
    isf_values = np.arange(25, 85, 5)
    drops = []
    expected = []

    for isf in isf_values:
        s = TherapySettings(isf=float(isf), cr=10, basal_rate=0.8)
        bolus_units = 2.0  # standard correction
        r = forward_simulate(200.0, s, duration_hours=8.0,
                             bolus_events=[InsulinEvent(0, bolus_units)], seed=42)
        drop = 200.0 - r.glucose[-1]
        drops.append(drop)
        expected.append(float(isf) * bolus_units)

    drops = np.array(drops)
    expected = np.array(expected)
    correlation = float(np.corrcoef(drops, expected)[0, 1])

    # Linear fit
    slope, intercept = np.polyfit(expected, drops, 1)

    return {
        "isf_values": isf_values.tolist(),
        "drops": drops.tolist(),
        "expected_full": expected.tolist(),
        "correlation": round(correlation, 4),
        "slope": round(slope, 3),
        "intercept": round(intercept, 1),
        "hypothesis_h2_pass": correlation > 0.95,
    }


# ── Experiment 2: Steady-state stability ─────────────────────────────

def exp_steady_state() -> dict:
    """Verify fasting glucose stays flat at correct basal."""
    test_cases = [
        {"isf": 30, "cr": 8, "basal": 0.5},
        {"isf": 50, "cr": 10, "basal": 0.8},
        {"isf": 70, "cr": 12, "basal": 1.2},
        {"isf": 40, "cr": 15, "basal": 1.5},
    ]

    results = []
    for tc in test_cases:
        s = TherapySettings(isf=tc["isf"], cr=tc["cr"], basal_rate=tc["basal"])
        r = forward_simulate(120.0, s, duration_hours=24.0, seed=42)
        drift = abs(r.glucose[-1] - 120.0)
        max_deviation = float(np.max(np.abs(r.glucose - 120.0)))
        results.append({
            **tc,
            "final_glucose": round(float(r.glucose[-1]), 1),
            "drift": round(drift, 2),
            "max_deviation": round(max_deviation, 2),
            "mean_glucose": round(float(r.mean_glucose), 1),
        })

    max_drift = max(r["drift"] for r in results)
    return {
        "test_cases": results,
        "max_drift_all": round(max_drift, 2),
        "hypothesis_h1_pass": max_drift < 5.0,
    }


# ── Experiment 3: Two-component tail comparison ─────────────────────

def exp_two_component_tail() -> dict:
    """Compare two-comp DIA vs simulated single-component.

    We can't change the model constants easily, so we compare:
    - Standard model (two-comp: 63% fast + 37% persistent)
    - Correction from 200 → track glucose at 4h, 8h, 12h, 24h
    The persistent tail should show continued lowering past DIA.
    """
    s = TherapySettings(isf=50, cr=10, basal_rate=0.8, dia_hours=5.0)
    r = forward_simulate(200.0, s, duration_hours=24.0,
                         bolus_events=[InsulinEvent(0, 2.0)], seed=42)

    checkpoints = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24]
    glucose_at = {}
    for h in checkpoints:
        step = int(h * 12)
        if step < len(r.glucose):
            glucose_at[f"{h}h"] = round(float(r.glucose[step]), 1)

    # After DIA (5h), single-component should be done.
    # Two-component should still be lowering.
    drop_at_5h = 200.0 - glucose_at.get("5h", 200.0)
    drop_at_12h = 200.0 - glucose_at.get("12h", 200.0)
    additional_lowering = drop_at_12h - drop_at_5h

    return {
        "glucose_at_hours": glucose_at,
        "drop_at_5h": round(drop_at_5h, 1),
        "drop_at_12h": round(drop_at_12h, 1),
        "additional_lowering_5h_to_12h": round(additional_lowering, 1),
        "hypothesis_h3_pass": additional_lowering > 5.0,
        "iob_at_5h": round(float(r.iob[60]), 4),
        "iob_at_12h": round(float(r.iob[144]), 4),
        "full_trace": r.glucose.tolist(),
    }


# ── Experiment 4: Meal spike vs ISF/CR ───────────────────────────────

def exp_meal_response() -> dict:
    """Verify meal spike scales with ISF/CR ratio."""
    isf_values = [30, 40, 50, 60, 70, 80]
    cr_values = [8, 10, 12, 15]
    results = []

    for isf in isf_values:
        for cr in cr_values:
            s = TherapySettings(isf=isf, cr=cr, basal_rate=0.8)
            # Unbolused meal — pure carb effect
            r = forward_simulate(120.0, s, duration_hours=6.0,
                                 carb_events=[CarbEvent(30, 45)], seed=42)
            spike = float(r.glucose.max()) - 120.0
            isf_cr_ratio = isf / cr
            results.append({
                "isf": isf, "cr": cr,
                "isf_cr_ratio": round(isf_cr_ratio, 2),
                "spike": round(spike, 1),
                "max_glucose": round(float(r.glucose.max()), 1),
            })

    # Correlation between spike and ISF/CR ratio
    spikes = [r["spike"] for r in results]
    ratios = [r["isf_cr_ratio"] for r in results]
    correlation = float(np.corrcoef(spikes, ratios)[0, 1])

    return {
        "results": results,
        "correlation_spike_vs_isf_cr": round(correlation, 4),
        "hypothesis_h4_pass": correlation > 0.9,
    }


# ── Experiment 5: Basal mismatch drift ──────────────────────────────

def exp_basal_drift() -> dict:
    """Verify glucose drift direction/magnitude with basal mismatch."""
    metabolic_need = 0.8  # true need
    basal_rates = np.arange(0.3, 1.4, 0.1)
    final_glucoses = []
    mismatches = []

    for rate in basal_rates:
        s = TherapySettings(isf=50, cr=10, basal_rate=float(rate))
        r = forward_simulate(120.0, s, duration_hours=12.0,
                             metabolic_basal_rate=metabolic_need, seed=42)
        final_glucoses.append(float(r.glucose[-1]))
        mismatches.append(float(rate) - metabolic_need)

    final_glucoses = np.array(final_glucoses)
    mismatches = np.array(mismatches)
    correlation = float(np.corrcoef(mismatches, final_glucoses)[0, 1])

    # Verify direction: positive mismatch (too much insulin) → lower glucose
    low_basal_idx = np.argmin(basal_rates)
    high_basal_idx = np.argmax(basal_rates)
    direction_correct = final_glucoses[low_basal_idx] > final_glucoses[high_basal_idx]

    return {
        "basal_rates": basal_rates.tolist(),
        "mismatches": mismatches.tolist(),
        "final_glucoses": final_glucoses.tolist(),
        "correlation": round(correlation, 4),
        "direction_correct": bool(direction_correct),
        "hypothesis_h5_pass": bool(direction_correct) and abs(correlation) > 0.9,
    }


# ── Experiment 6: Typical day comparison across patient types ────────

def exp_typical_day_patients() -> dict:
    """Run typical day for diverse synthetic patients."""
    patients = [
        {"label": "Sensitive adult", "isf": 80, "cr": 15, "basal": 0.5},
        {"label": "Average adult", "isf": 50, "cr": 10, "basal": 0.8},
        {"label": "Resistant adult", "isf": 30, "cr": 8, "basal": 1.2},
        {"label": "Child/teen", "isf": 100, "cr": 20, "basal": 0.3},
        {"label": "High-dose adult", "isf": 25, "cr": 6, "basal": 1.8},
    ]

    results = []
    for p in patients:
        s = TherapySettings(isf=p["isf"], cr=p["cr"], basal_rate=p["basal"])
        r = simulate_typical_day(s, seed=42)
        summary = r.summary()
        summary["label"] = p["label"]
        summary["settings"] = {"isf": p["isf"], "cr": p["cr"], "basal": p["basal"]}
        summary["glucose_trace"] = r.glucose.tolist()
        results.append(summary)

    return {"patients": results}


# ── Plot Figures ─────────────────────────────────────────────────────

def plot_all(results: dict, fig_dir: Path):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping figures")
        return

    # Fig 1: Correction vs ISF
    fig, ax = plt.subplots(figsize=(8, 5))
    r = results["correction_isf"]
    ax.scatter(r["expected_full"], r["drops"], c='steelblue', s=50, zorder=3)
    ax.plot([0, max(r["expected_full"])], [0, max(r["expected_full"])],
            'k--', alpha=0.4, label='Perfect linearity')
    fit_x = np.linspace(0, max(r["expected_full"]), 50)
    ax.plot(fit_x, r["slope"] * fit_x + r["intercept"], 'r-',
            alpha=0.7, label=f'Fit: slope={r["slope"]}, r={r["correlation"]}')
    ax.set_xlabel('Expected Drop (ISF × Units, mg/dL)')
    ax.set_ylabel('Simulated Drop (mg/dL)')
    ax.set_title(f'EXP-2553: Correction Bolus vs ISF (r={r["correlation"]})')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / 'fig_2553_correction_isf.png', dpi=150)
    plt.close(fig)

    # Fig 2: Meal response heatmap
    r = results["meal_response"]
    isf_vals = sorted(set(x["isf"] for x in r["results"]))
    cr_vals = sorted(set(x["cr"] for x in r["results"]))
    spike_grid = np.zeros((len(isf_vals), len(cr_vals)))
    for entry in r["results"]:
        i = isf_vals.index(entry["isf"])
        j = cr_vals.index(entry["cr"])
        spike_grid[i, j] = entry["spike"]

    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(spike_grid, cmap='YlOrRd', aspect='auto',
                   origin='lower')
    ax.set_xticks(range(len(cr_vals)))
    ax.set_xticklabels(cr_vals)
    ax.set_yticks(range(len(isf_vals)))
    ax.set_yticklabels(isf_vals)
    ax.set_xlabel('CR (g/U)')
    ax.set_ylabel('ISF (mg/dL/U)')
    ax.set_title(f'EXP-2553: Unbolused Meal Spike (r(spike, ISF/CR)={r["correlation_spike_vs_isf_cr"]})')
    for i in range(len(isf_vals)):
        for j in range(len(cr_vals)):
            ax.text(j, i, f'{spike_grid[i, j]:.0f}',
                    ha='center', va='center', fontsize=8,
                    color='white' if spike_grid[i, j] > spike_grid.max() * 0.6 else 'black')
    fig.colorbar(im, label='Spike (mg/dL)')
    fig.tight_layout()
    fig.savefig(fig_dir / 'fig_2553_meal_response.png', dpi=150)
    plt.close(fig)

    # Fig 3: Basal drift
    r = results["basal_drift"]
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ['#d32f2f' if m < 0 else '#1976d2' if m > 0 else '#4caf50'
              for m in r["mismatches"]]
    ax.bar(range(len(r["basal_rates"])), r["final_glucoses"], color=colors)
    ax.set_xticks(range(len(r["basal_rates"])))
    ax.set_xticklabels([f'{b:.1f}' for b in r["basal_rates"]], rotation=45)
    ax.axhline(120, color='green', linestyle='--', alpha=0.5, label='Starting BG')
    ax.axhline(70, color='red', linestyle=':', alpha=0.5, label='Hypo')
    ax.axhline(180, color='orange', linestyle=':', alpha=0.5, label='Hyper')
    ax.set_xlabel('Basal Rate (U/hr) — metabolic need = 0.8')
    ax.set_ylabel('Glucose at 12h (mg/dL)')
    ax.set_title(f'EXP-2553: Basal Mismatch → Glucose Drift (r={r["correlation"]})')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    fig.tight_layout()
    fig.savefig(fig_dir / 'fig_2553_basal_drift.png', dpi=150)
    plt.close(fig)

    # Fig 4: Two-component tail
    r = results["two_component_tail"]
    hours = np.arange(len(r["full_trace"])) / 12.0
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(hours, r["full_trace"], 'b-', linewidth=1.5, label='Two-component DIA')
    ax.axhline(200, color='gray', linestyle=':', alpha=0.3)
    ax.axvspan(5, 24, alpha=0.08, color='orange', label='Beyond standard DIA (5h)')
    ax.axhline(70, color='red', linestyle=':', alpha=0.5)
    ax.axhline(180, color='orange', linestyle=':', alpha=0.5)
    checkpoints = r["glucose_at_hours"]
    for h_str, g in checkpoints.items():
        h = float(h_str.replace('h', ''))
        ax.plot(h, g, 'ro', markersize=6)
        ax.annotate(f'{g}', (h, g), textcoords="offset points",
                    xytext=(0, 10), ha='center', fontsize=7)
    ax.set_xlabel('Hours')
    ax.set_ylabel('Glucose (mg/dL)')
    ax.set_title(f'EXP-2553: Two-Component DIA Tail — '
                 f'Additional lowering 5-12h: {r["additional_lowering_5h_to_12h"]} mg/dL')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / 'fig_2553_two_component_tail.png', dpi=150)
    plt.close(fig)

    # Fig 5: Typical day multi-patient
    r = results["typical_day_patients"]
    fig, axes = plt.subplots(len(r["patients"]), 1, figsize=(12, 3 * len(r["patients"])),
                             sharex=True)
    for i, (ax, p) in enumerate(zip(axes, r["patients"])):
        hours = np.arange(len(p["glucose_trace"])) / 12.0
        ax.plot(hours, p["glucose_trace"], linewidth=1.2)
        ax.fill_between(hours, 70, 180, alpha=0.1, color='green')
        ax.axhline(70, color='red', linestyle=':', alpha=0.3)
        ax.axhline(180, color='orange', linestyle=':', alpha=0.3)
        ax.set_ylabel('mg/dL')
        s = p["settings"]
        ax.set_title(f'{p["label"]} (ISF={s["isf"]}, CR={s["cr"]}, '
                     f'basal={s["basal"]}) — TIR={p["tir"]}%, '
                     f'mean={p["mean_glucose"]}')
        ax.set_ylim(39, 350)
        # Meal markers at 7h, 12h, 18.5h
        for mh in [7, 12, 18.5]:
            ax.axvline(mh, color='gray', linestyle='--', alpha=0.2)
    axes[-1].set_xlabel('Hour of Day')
    fig.suptitle('EXP-2553: Typical Day — Diverse Patient Profiles', y=1.01)
    fig.tight_layout()
    fig.savefig(fig_dir / 'fig_2553_typical_day.png', dpi=150, bbox_inches='tight')
    plt.close(fig)

    print(f"  Saved 5 figures to {fig_dir}")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EXP-2553: Forward Simulator Validation")
    parser.add_argument("--figures", action="store_true", help="Generate figures")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2553: Forward Simulator Validation")
    print("=" * 70)

    results = {}

    # Run all experiments
    print("\n[1/6] Correction vs ISF linearity...")
    results["correction_isf"] = exp_correction_isf()
    r = results["correction_isf"]
    print(f"  Correlation: {r['correlation']}")
    print(f"  Slope: {r['slope']}, Intercept: {r['intercept']}")
    print(f"  H2 (r > 0.95): {'PASS ✓' if r['hypothesis_h2_pass'] else 'FAIL ✗'}")

    print("\n[2/6] Steady-state stability...")
    results["steady_state"] = exp_steady_state()
    r = results["steady_state"]
    print(f"  Max drift: {r['max_drift_all']} mg/dL")
    print(f"  H1 (drift < 5): {'PASS ✓' if r['hypothesis_h1_pass'] else 'FAIL ✗'}")

    print("\n[3/6] Two-component DIA tail...")
    results["two_component_tail"] = exp_two_component_tail()
    r = results["two_component_tail"]
    print(f"  Drop at 5h: {r['drop_at_5h']} mg/dL")
    print(f"  Drop at 12h: {r['drop_at_12h']} mg/dL")
    print(f"  Additional lowering 5-12h: {r['additional_lowering_5h_to_12h']} mg/dL")
    print(f"  H3 (persistent tail > 5): {'PASS ✓' if r['hypothesis_h3_pass'] else 'FAIL ✗'}")

    print("\n[4/6] Meal response vs ISF/CR...")
    results["meal_response"] = exp_meal_response()
    r = results["meal_response"]
    print(f"  Correlation (spike vs ISF/CR): {r['correlation_spike_vs_isf_cr']}")
    print(f"  H4 (r > 0.9): {'PASS ✓' if r['hypothesis_h4_pass'] else 'FAIL ✗'}")

    print("\n[5/6] Basal mismatch drift...")
    results["basal_drift"] = exp_basal_drift()
    r = results["basal_drift"]
    print(f"  Correlation (mismatch vs glucose): {r['correlation']}")
    print(f"  Direction correct: {r['direction_correct']}")
    print(f"  H5 (correct direction & |r| > 0.9): {'PASS ✓' if r['hypothesis_h5_pass'] else 'FAIL ✗'}")

    print("\n[6/6] Typical day — diverse patients...")
    results["typical_day_patients"] = exp_typical_day_patients()
    r = results["typical_day_patients"]
    for p in r["patients"]:
        print(f"  {p['label']}: TIR={p['tir']}%, mean={p['mean_glucose']}")

    # Remove full traces from JSON output (too large)
    results_json = json.loads(json.dumps(results, default=str))
    if "two_component_tail" in results_json:
        results_json["two_component_tail"].pop("full_trace", None)
    for p in results_json.get("typical_day_patients", {}).get("patients", []):
        p.pop("glucose_trace", None)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    hypotheses = {
        "H1 (steady-state < 5 mg/dL)": results["steady_state"]["hypothesis_h1_pass"],
        "H2 (correction r > 0.95)": results["correction_isf"]["hypothesis_h2_pass"],
        "H3 (persistent tail > 5 mg/dL)": results["two_component_tail"]["hypothesis_h3_pass"],
        "H4 (meal spike r > 0.9)": results["meal_response"]["hypothesis_h4_pass"],
        "H5 (basal drift direction)": results["basal_drift"]["hypothesis_h5_pass"],
    }
    all_pass = True
    for h, v in hypotheses.items():
        status = "PASS ✓" if v else "FAIL ✗"
        print(f"  {h}: {status}")
        if not v:
            all_pass = False
    print(f"\n  Overall: {'ALL PASS ✓' if all_pass else 'SOME FAILED ✗'}")

    results_json["summary"] = {
        "hypotheses": {k: v for k, v in hypotheses.items()},
        "all_pass": all_pass,
    }

    # Save JSON
    exp_dir = Path(__file__).resolve().parents[3] / "externals" / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    json_path = exp_dir / "exp-2553_forward_validation.json"
    with open(json_path, 'w') as f:
        json.dump(results_json, f, indent=2, default=str)
    print(f"\n  Results saved to {json_path}")

    if args.figures:
        print("\nGenerating figures...")
        plot_all(results, _figures_dir())

    if args.json:
        print(json.dumps(results_json, indent=2, default=str))


if __name__ == "__main__":
    main()
