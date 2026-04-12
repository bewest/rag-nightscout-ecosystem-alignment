"""
EXP-2556: IOB-Dependent Power-Law ISF Validation
==================================================

Research question: Does the IOB-dependent power-law ISF dampening produce
more realistic correction trajectories in the forward simulator?

Background:
  EXP-2511-2518 established ISF(dose) = ISF_base × dose^(-0.9) with causal
  validation (4 methods, 17/17 patients). A 2U correction is 46% less
  effective per unit than a 1U correction. Without this dampening, the
  forward simulator overestimates large corrections.

Hypotheses:
  H6a: Power-law ISF reduces correction magnitude for large boluses (≥3U)
       by at least 30% compared to fixed ISF.
  H6b: Small corrections (≤1U) show less than 15% difference between
       power-law and fixed ISF.
  H6c: With power-law enabled, a 4U correction stays above 70 mg/dL
       (avoids simulator-induced hypo from ISF overestimation).
  H6d: Stacked boluses (2U+2U at 30min apart) show a different trajectory
       than a single 4U bolus (IOB stacking affects effective ISF).

Figures:
  fig_2556_dose_response.png      — Glucose drop vs bolus size ± power-law
  fig_2556_trajectories.png       — Time-series: 1U/2U/4U corrections
  fig_2556_stacked_vs_single.png  — Single 4U vs stacked 2U+2U
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
)


def _figures_dir() -> Path:
    d = Path(__file__).resolve().parents[3] / "docs" / "60-research" / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Experiment 1: Dose-response curve ────────────────────────────────

def exp_dose_response() -> dict:
    """Compare glucose drop vs bolus size with and without power-law."""
    doses = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]
    start_bg = 250.0
    results_fixed = []
    results_power = []

    for dose in doses:
        s_fixed = TherapySettings(isf=50, cr=10, basal_rate=0.8,
                                   iob_power_law=False)
        s_power = TherapySettings(isf=50, cr=10, basal_rate=0.8,
                                   iob_power_law=True)
        r_f = forward_simulate(start_bg, s_fixed, duration_hours=8.0,
                               bolus_events=[InsulinEvent(0, dose)], seed=42)
        r_p = forward_simulate(start_bg, s_power, duration_hours=8.0,
                               bolus_events=[InsulinEvent(0, dose)], seed=42)

        drop_f = start_bg - float(r_f.glucose.min())
        drop_p = start_bg - float(r_p.glucose.min())

        results_fixed.append({
            "dose": dose,
            "nadir": round(float(r_f.glucose.min()), 1),
            "drop": round(drop_f, 1),
            "drop_per_unit": round(drop_f / dose, 1),
        })
        results_power.append({
            "dose": dose,
            "nadir": round(float(r_p.glucose.min()), 1),
            "drop": round(drop_p, 1),
            "drop_per_unit": round(drop_p / dose, 1),
        })

    # H6a: Large corrections (≥3U) reduced by ≥30%
    large_fixed = [r for r in results_fixed if r["dose"] >= 3.0]
    large_power = [r for r in results_power if r["dose"] >= 3.0]
    reductions = [(f["drop"] - p["drop"]) / f["drop"] * 100
                  for f, p in zip(large_fixed, large_power)]
    h6a_pass = all(r >= 30 for r in reductions)

    # H6b: Small corrections (≤1U) differ by <15%
    small_fixed = [r for r in results_fixed if r["dose"] <= 1.0]
    small_power = [r for r in results_power if r["dose"] <= 1.0]
    small_diffs = [abs(f["drop"] - p["drop"]) / max(f["drop"], 0.1) * 100
                   for f, p in zip(small_fixed, small_power)]
    h6b_pass = all(d < 15 for d in small_diffs)

    return {
        "fixed_isf": results_fixed,
        "power_law_isf": results_power,
        "large_dose_reductions_pct": [round(r, 1) for r in reductions],
        "small_dose_diffs_pct": [round(d, 1) for d in small_diffs],
        "hypothesis_h6a_pass": h6a_pass,
        "hypothesis_h6b_pass": h6b_pass,
    }


# ── Experiment 2: Correction trajectories ───────────────────────────

def exp_correction_trajectories() -> dict:
    """Time-series comparison for 1U/2U/4U corrections."""
    doses_to_plot = [1.0, 2.0, 4.0]
    start_bg = 250.0
    traces = {}

    for dose in doses_to_plot:
        s_f = TherapySettings(isf=50, cr=10, basal_rate=0.8, iob_power_law=False)
        s_p = TherapySettings(isf=50, cr=10, basal_rate=0.8, iob_power_law=True)

        r_f = forward_simulate(start_bg, s_f, duration_hours=8.0,
                               bolus_events=[InsulinEvent(0, dose)], seed=42)
        r_p = forward_simulate(start_bg, s_p, duration_hours=8.0,
                               bolus_events=[InsulinEvent(0, dose)], seed=42)

        label = f"{dose}U"
        traces[label] = {
            "fixed": r_f.glucose.tolist(),
            "power_law": r_p.glucose.tolist(),
            "fixed_nadir": round(float(r_f.glucose.min()), 1),
            "power_nadir": round(float(r_p.glucose.min()), 1),
        }

    # H6c: 4U with power-law stays above 70
    h6c_pass = traces["4.0U"]["power_nadir"] >= 70

    return {
        "traces": traces,
        "start_bg": start_bg,
        "hypothesis_h6c_pass": h6c_pass,
    }


# ── Experiment 3: Stacked vs single bolus ───────────────────────────

def exp_stacked_vs_single() -> dict:
    """Compare single 4U bolus vs two stacked 2U boluses."""
    start_bg = 250.0
    s = TherapySettings(isf=50, cr=10, basal_rate=0.8, iob_power_law=True)

    # Single 4U at t=0
    r_single = forward_simulate(start_bg, s, duration_hours=8.0,
        bolus_events=[InsulinEvent(0, 4.0)], seed=42)

    # Stacked 2U+2U at 0 and 30min
    r_stacked = forward_simulate(start_bg, s, duration_hours=8.0,
        bolus_events=[InsulinEvent(0, 2.0), InsulinEvent(30, 2.0)], seed=42)

    # Without power-law for comparison
    s_off = TherapySettings(isf=50, cr=10, basal_rate=0.8, iob_power_law=False)
    r_single_off = forward_simulate(start_bg, s_off, duration_hours=8.0,
        bolus_events=[InsulinEvent(0, 4.0)], seed=42)
    r_stacked_off = forward_simulate(start_bg, s_off, duration_hours=8.0,
        bolus_events=[InsulinEvent(0, 2.0), InsulinEvent(30, 2.0)], seed=42)

    # H6d: With power-law, single vs stacked should differ
    # (single has higher peak IOB → more dampening → less total drop)
    single_nadir = float(r_single.glucose.min())
    stacked_nadir = float(r_stacked.glucose.min())
    diff_with_pl = abs(single_nadir - stacked_nadir)

    single_off_nadir = float(r_single_off.glucose.min())
    stacked_off_nadir = float(r_stacked_off.glucose.min())
    diff_without_pl = abs(single_off_nadir - stacked_off_nadir)

    # Power-law should create MORE difference between single/stacked
    h6d_pass = diff_with_pl > diff_without_pl

    return {
        "power_law": {
            "single_4U_nadir": round(single_nadir, 1),
            "stacked_2U2U_nadir": round(stacked_nadir, 1),
            "difference": round(diff_with_pl, 1),
            "single_trace": r_single.glucose.tolist(),
            "stacked_trace": r_stacked.glucose.tolist(),
        },
        "fixed": {
            "single_4U_nadir": round(single_off_nadir, 1),
            "stacked_2U2U_nadir": round(stacked_off_nadir, 1),
            "difference": round(diff_without_pl, 1),
        },
        "hypothesis_h6d_pass": h6d_pass,
    }


# ── Plot Figures ─────────────────────────────────────────────────────

def plot_all(results: dict, fig_dir: Path):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping figures")
        return

    # Fig 1: Dose-response curve
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    dr = results["dose_response"]
    doses = [r["dose"] for r in dr["fixed_isf"]]
    drops_f = [r["drop"] for r in dr["fixed_isf"]]
    drops_p = [r["drop"] for r in dr["power_law_isf"]]
    dpu_f = [r["drop_per_unit"] for r in dr["fixed_isf"]]
    dpu_p = [r["drop_per_unit"] for r in dr["power_law_isf"]]

    ax = axes[0]
    ax.plot(doses, drops_f, 'b-o', lw=2, label='Fixed ISF')
    ax.plot(doses, drops_p, 'r-o', lw=2, label='Power-law ISF')
    ax.set_xlabel("Bolus dose (U)")
    ax.set_ylabel("Total glucose drop (mg/dL)")
    ax.set_title("Dose-Response: Total Drop")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.plot(doses, dpu_f, 'b-o', lw=2, label='Fixed ISF')
    ax.plot(doses, dpu_p, 'r-o', lw=2, label='Power-law ISF')
    ax.axhline(50, color='gray', ls='--', alpha=0.5, label='Nominal ISF=50')
    ax.set_xlabel("Bolus dose (U)")
    ax.set_ylabel("Drop per unit (mg/dL/U)")
    ax.set_title("Effective ISF vs Dose")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.suptitle(f"H6a: {'PASS' if dr['hypothesis_h6a_pass'] else 'FAIL'}, "
                 f"H6b: {'PASS' if dr['hypothesis_h6b_pass'] else 'FAIL'}")
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_2556_dose_response.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig_2556_dose_response.png")

    # Fig 2: Trajectories
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    tr = results["trajectories"]["traces"]
    for idx, dose_label in enumerate(["1.0U", "2.0U", "4.0U"]):
        ax = axes[idx]
        data = tr[dose_label]
        t = np.arange(len(data["fixed"])) * 5 / 60
        ax.plot(t, data["fixed"], 'b-', lw=2, label=f'Fixed (nadir={data["fixed_nadir"]})')
        ax.plot(t, data["power_law"], 'r-', lw=2, label=f'Power-law (nadir={data["power_nadir"]})')
        ax.axhspan(70, 180, alpha=0.1, color='green')
        ax.axhline(70, color='red', ls='--', alpha=0.3)
        ax.set_xlabel("Hours")
        ax.set_ylabel("Glucose (mg/dL)")
        ax.set_title(f"{dose_label} Correction from 250")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(40, 260)
    fig.suptitle(f"Correction Trajectories (H6c: {'PASS' if results['trajectories']['hypothesis_h6c_pass'] else 'FAIL'})")
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_2556_trajectories.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig_2556_trajectories.png")

    # Fig 3: Stacked vs single
    fig, ax = plt.subplots(figsize=(10, 5))
    sv = results["stacked_vs_single"]
    t = np.arange(len(sv["power_law"]["single_trace"])) * 5 / 60
    ax.plot(t, sv["power_law"]["single_trace"], 'r-', lw=2,
            label=f'Single 4U (nadir={sv["power_law"]["single_4U_nadir"]})')
    ax.plot(t, sv["power_law"]["stacked_trace"], 'b-', lw=2,
            label=f'Stacked 2U+2U (nadir={sv["power_law"]["stacked_2U2U_nadir"]})')
    ax.axhspan(70, 180, alpha=0.1, color='green')
    ax.axhline(70, color='red', ls='--', alpha=0.3)
    ax.axvline(0, color='gray', ls='--', alpha=0.3)
    ax.axvline(0.5, color='gray', ls='--', alpha=0.3, label='2nd bolus (30min)')
    ax.set_xlabel("Hours")
    ax.set_ylabel("Glucose (mg/dL)")
    ax.set_title(f"Stacked vs Single (Power-Law ISF, H6d: {'PASS' if sv['hypothesis_h6d_pass'] else 'FAIL'})")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_2556_stacked_vs_single.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig_2556_stacked_vs_single.png")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EXP-2556: IOB-Dependent ISF")
    parser.add_argument("--figures", action="store_true")
    parser.add_argument("--json-out", type=str, default=None)
    args = parser.parse_args()

    print("=" * 60)
    print("EXP-2556: IOB-Dependent Power-Law ISF Validation")
    print("=" * 60)

    results = {}

    print("\n1. Dose-response comparison...")
    results["dose_response"] = exp_dose_response()
    dr = results["dose_response"]
    print("   Fixed ISF drop/unit:", [(r["dose"], r["drop_per_unit"]) for r in dr["fixed_isf"]])
    print("   Power-law drop/unit:", [(r["dose"], r["drop_per_unit"]) for r in dr["power_law_isf"]])
    print(f"   Large-dose reductions: {dr['large_dose_reductions_pct']}%")
    print(f"   H6a (large dose dampening ≥30%): {'PASS' if dr['hypothesis_h6a_pass'] else 'FAIL'}")
    print(f"   H6b (small dose diff <15%): {'PASS' if dr['hypothesis_h6b_pass'] else 'FAIL'}")

    print("\n2. Correction trajectories...")
    results["trajectories"] = exp_correction_trajectories()
    tr = results["trajectories"]
    for label, data in tr["traces"].items():
        print(f"   {label}: fixed nadir={data['fixed_nadir']}, "
              f"power-law nadir={data['power_nadir']}")
    print(f"   H6c (4U stays >70): {'PASS' if tr['hypothesis_h6c_pass'] else 'FAIL'}")

    print("\n3. Stacked vs single bolus...")
    results["stacked_vs_single"] = exp_stacked_vs_single()
    sv = results["stacked_vs_single"]
    print(f"   Power-law: single={sv['power_law']['single_4U_nadir']}, "
          f"stacked={sv['power_law']['stacked_2U2U_nadir']}, "
          f"diff={sv['power_law']['difference']}")
    print(f"   Fixed:     single={sv['fixed']['single_4U_nadir']}, "
          f"stacked={sv['fixed']['stacked_2U2U_nadir']}, "
          f"diff={sv['fixed']['difference']}")
    print(f"   H6d (power-law increases spread): {'PASS' if sv['hypothesis_h6d_pass'] else 'FAIL'}")

    # Summary
    hypotheses = {
        "H6a": dr["hypothesis_h6a_pass"],
        "H6b": dr["hypothesis_h6b_pass"],
        "H6c": tr["hypothesis_h6c_pass"],
        "H6d": sv["hypothesis_h6d_pass"],
    }
    results["summary"] = {
        "hypotheses": hypotheses,
        "all_pass": all(hypotheses.values()),
        "pass_count": sum(hypotheses.values()),
        "total": len(hypotheses),
    }

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {results['summary']['pass_count']}/{results['summary']['total']} hypotheses pass")
    for k, v in hypotheses.items():
        print(f"  {k}: {'PASS ✓' if v else 'FAIL ✗'}")
    print(f"{'=' * 60}")

    if args.figures:
        fig_dir = _figures_dir()
        print(f"\nGenerating figures in {fig_dir} ...")
        plot_all(results, fig_dir)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove traces from JSON
        clean = json.loads(json.dumps(results))
        if "trajectories" in clean:
            for label in clean["trajectories"].get("traces", {}):
                for k in ("fixed", "power_law"):
                    if k in clean["trajectories"]["traces"][label]:
                        del clean["trajectories"]["traces"][label][k]
        if "stacked_vs_single" in clean:
            for key in ("single_trace", "stacked_trace"):
                if key in clean["stacked_vs_single"].get("power_law", {}):
                    del clean["stacked_vs_single"]["power_law"][key]
        with open(out_path, "w") as f:
            json.dump(clean, f, indent=2)
        print(f"Results saved to {out_path}")

    return results


if __name__ == "__main__":
    main()
