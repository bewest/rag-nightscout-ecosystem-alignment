#!/usr/bin/env python3
"""EXP-2661: Dual-ISF Dosing Strategy — Simulation.

MOTIVATION: EXP-2651 showed demand-phase ISF (0-2h) is 2-10× smaller than
apparent ISF. Current AID systems use one ISF for everything. This means:
  - Corrections are UNDER-dosed (ISF too high → dose too small)
  - The controller waits too long because it expects a bigger drop per unit

EXP-2634 (parallel researcher) confirmed corrections don't follow ANY
single-factor model — but that's because the CONTROLLER is compensating.
If we use demand-ISF for dosing, the correction itself is more aggressive,
potentially reducing the need for the controller to compensate.

METHOD:
  Replay correction events from EXP-2651 with two dosing strategies:
  1. SCHEDULED ISF: dose = (current_bg - target) / scheduled_ISF
  2. DEMAND ISF:    dose = (current_bg - target) / demand_ISF

  For each strategy, simulate the 2h and 4h glucose outcome using the
  observed per-unit glucose response (not a model).

  Safety check: how often does demand-ISF dosing predict glucose < 70?
  Efficacy check: how often does it reach target (70-180)?

HYPOTHESES:
  H1: Demand-ISF dosing gets glucose to target (70-180) at 4h for ≥20%
      more corrections than scheduled ISF
  H2: Demand-ISF dosing increases hypo risk (<70) by <5% absolute
  H3: Mean 4h glucose is closer to target (120) with demand-ISF
  H4: The safety/efficacy tradeoff varies ≥2× across patients
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
OUTFILE = RESULTS_DIR / "exp-2661_dual_isf.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12
TARGET_BG = 110  # mg/dL


def _extract_corrections(pdf, min_dose=0.5, min_pre_bg=120,
                          carb_window_h=1.0, prior_bolus_h=2.0, min_drop=10):
    """Gold-standard correction detection (same as EXP-2624/2651)."""
    pdf = pdf.sort_values("time").reset_index(drop=True)

    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)

    carb_window = int(carb_window_h * STEPS_PER_HOUR)
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    post_window = int(6.0 * STEPS_PER_HOUR)

    events = []
    for i in range(prior_window, len(pdf) - post_window):
        if bolus[i] < min_dose:
            continue

        # Pre-BG check
        pre_bg = glucose[max(0, i-6):i+1]
        valid_pre = pre_bg[~np.isnan(pre_bg)]
        if len(valid_pre) < 3 or np.mean(valid_pre) < min_pre_bg:
            continue

        # No carbs within ±carb_window
        c_start = max(0, i - carb_window)
        c_end = min(len(pdf), i + carb_window)
        if np.nansum(carbs[c_start:c_end]) > 2.0:
            continue

        # No prior bolus within 2h (excludes SMBs)
        if np.nansum(bolus[i - prior_window:i]) > 0.3:
            continue

        # Track 6h trajectory
        traj = glucose[i:i + post_window + 1]
        iob_traj = iob[i:i + post_window + 1]

        # Need enough valid glucose
        valid_mask = ~np.isnan(traj)
        if np.sum(valid_mask) < post_window * 0.5:
            continue

        # Must drop ≥ min_drop mg/dL
        smoothed = pd.Series(traj).rolling(6, min_periods=3, center=True).mean().values
        nadir_window = int(5 * STEPS_PER_HOUR)
        nadir_idx = np.nanargmin(smoothed[:nadir_window]) if nadir_window <= len(smoothed) else 0
        if np.isnan(smoothed[nadir_idx]):
            continue
        total_drop = float(np.mean(valid_pre)) - smoothed[nadir_idx]
        if total_drop < min_drop:
            continue

        dose = float(bolus[i])
        pre_glucose = float(np.mean(valid_pre))

        # Glucose at 2h and 4h
        def _bg_at(h):
            idx = int(h * STEPS_PER_HOUR)
            w = traj[max(0, idx-3):idx+4]
            v = w[~np.isnan(w)]
            return float(np.mean(v)) if len(v) >= 2 else np.nan

        bg_2h = _bg_at(2)
        bg_4h = _bg_at(4)

        # Demand ISF: drop in 0-2h / dose
        drop_2h = pre_glucose - bg_2h if not np.isnan(bg_2h) else np.nan
        demand_isf = drop_2h / dose if not np.isnan(drop_2h) and dose > 0 else np.nan

        # Apparent ISF: total drop to nadir / dose
        apparent_isf = total_drop / dose

        events.append({
            "idx": int(i),
            "dose": dose,
            "pre_glucose": pre_glucose,
            "bg_2h": bg_2h,
            "bg_4h": bg_4h,
            "nadir": float(smoothed[nadir_idx]),
            "nadir_time_h": float(nadir_idx / STEPS_PER_HOUR),
            "drop_2h": drop_2h,
            "total_drop": total_drop,
            "demand_isf": demand_isf,
            "apparent_isf": apparent_isf,
        })

    return pd.DataFrame(events)


def _simulate_dosing(events_df, scheduled_isf, demand_isf_median):
    """Simulate outcomes under two dosing strategies.

    For each correction event, compute what DOSE would have been given
    under each strategy, then scale the observed glucose trajectory
    proportionally.

    Strategy 1: dose_sched = (pre_bg - target) / scheduled_ISF
    Strategy 2: dose_demand = (pre_bg - target) / demand_ISF

    Outcome scaling: if actual dose was D and actual bg_4h was X,
    then for a hypothetical dose D', bg_4h' ≈ pre_bg - (pre_bg - X) × (D'/D)
    This assumes linear dose-response in the observed range.
    """
    results = []
    for _, ev in events_df.iterrows():
        pre_bg = ev["pre_glucose"]
        actual_dose = ev["dose"]
        bg_4h = ev["bg_4h"]
        bg_2h = ev["bg_2h"]

        if np.isnan(bg_4h) or np.isnan(bg_2h) or actual_dose <= 0:
            continue

        # What each strategy would dose
        correction_needed = pre_bg - TARGET_BG
        if correction_needed <= 0:
            continue

        dose_sched = correction_needed / scheduled_isf
        dose_demand = correction_needed / demand_isf_median if demand_isf_median > 0 else 0

        # Cap demand dose at 2× scheduled for safety
        dose_demand_capped = min(dose_demand, dose_sched * 2.0)

        # Scale factor relative to actual dose
        scale_sched = dose_sched / actual_dose
        scale_demand = dose_demand_capped / actual_dose

        # Predicted outcomes (linear scaling)
        actual_drop_4h = pre_bg - bg_4h
        actual_drop_2h = pre_bg - bg_2h

        pred_bg_4h_sched = pre_bg - actual_drop_4h * scale_sched
        pred_bg_4h_demand = pre_bg - actual_drop_4h * scale_demand
        pred_bg_2h_sched = pre_bg - actual_drop_2h * scale_sched
        pred_bg_2h_demand = pre_bg - actual_drop_2h * scale_demand

        results.append({
            "pre_bg": pre_bg,
            "actual_dose": actual_dose,
            "dose_sched": dose_sched,
            "dose_demand": dose_demand_capped,
            "dose_ratio": dose_demand_capped / dose_sched if dose_sched > 0 else 1,
            "actual_bg_4h": bg_4h,
            "pred_bg_4h_sched": pred_bg_4h_sched,
            "pred_bg_4h_demand": pred_bg_4h_demand,
            "pred_bg_2h_sched": pred_bg_2h_sched,
            "pred_bg_2h_demand": pred_bg_2h_demand,
        })

    return pd.DataFrame(results)


def _analyze_patient(pid, pdf):
    """Per-patient dual-ISF simulation."""
    events = _extract_corrections(pdf)
    if len(events) < 5:
        return None

    scheduled_isf = float(pdf["scheduled_isf"].dropna().median())
    valid_demand = events["demand_isf"].dropna()
    valid_demand = valid_demand[valid_demand > 0]
    if len(valid_demand) < 3:
        return None
    demand_isf_median = float(valid_demand.median())

    sim = _simulate_dosing(events, scheduled_isf, demand_isf_median)
    if len(sim) < 5:
        return None

    # === Efficacy metrics ===
    in_range = lambda bg: (bg >= 70) & (bg <= 180)
    hypo = lambda bg: bg < 70

    # 4h outcomes
    tir_sched = float(in_range(sim["pred_bg_4h_sched"]).mean())
    tir_demand = float(in_range(sim["pred_bg_4h_demand"]).mean())
    hypo_sched = float(hypo(sim["pred_bg_4h_sched"]).mean())
    hypo_demand = float(hypo(sim["pred_bg_4h_demand"]).mean())

    # Mean 4h glucose
    mean_4h_sched = float(sim["pred_bg_4h_sched"].mean())
    mean_4h_demand = float(sim["pred_bg_4h_demand"].mean())

    # Distance from target
    dist_sched = float(np.abs(sim["pred_bg_4h_sched"] - TARGET_BG).mean())
    dist_demand = float(np.abs(sim["pred_bg_4h_demand"] - TARGET_BG).mean())

    # Dose ratio (demand / sched)
    mean_dose_ratio = float(sim["dose_ratio"].mean())

    return {
        "n_events": len(sim),
        "scheduled_isf": scheduled_isf,
        "demand_isf": demand_isf_median,
        "inflation_ratio": scheduled_isf / demand_isf_median if demand_isf_median > 0 else np.nan,
        "mean_dose_ratio": mean_dose_ratio,
        # 4h outcomes
        "tir_4h_sched": tir_sched,
        "tir_4h_demand": tir_demand,
        "tir_improvement": tir_demand - tir_sched,
        "hypo_4h_sched": hypo_sched,
        "hypo_4h_demand": hypo_demand,
        "hypo_increase": hypo_demand - hypo_sched,
        "mean_4h_sched": mean_4h_sched,
        "mean_4h_demand": mean_4h_demand,
        "dist_target_sched": dist_sched,
        "dist_target_demand": dist_demand,
    }


def main():
    print("=" * 70)
    print("EXP-2661: Dual-ISF Dosing Strategy Simulation")
    print("=" * 70)

    df_all = pd.read_parquet(PARQUET)
    results = {}

    for pid in ALL_PATIENTS:
        pdf = df_all[df_all["patient_id"] == pid].copy()
        if len(pdf) < 200:
            continue

        r = _analyze_patient(pid, pdf)
        if r is None:
            print(f"\n  {pid}: insufficient corrections")
            continue

        prefix = "[ODC]" if pid.startswith("odc") else "[NS] "
        print(f"\n  {prefix} {pid} ({r['n_events']} corrections):")
        print(f"    ISF: scheduled={r['scheduled_isf']:.0f}, "
              f"demand={r['demand_isf']:.0f}, inflation={r['inflation_ratio']:.1f}×")
        print(f"    Dose ratio (demand/sched): {r['mean_dose_ratio']:.2f}×")
        print(f"    4h TIR: sched={r['tir_4h_sched']*100:.0f}%, "
              f"demand={r['tir_4h_demand']*100:.0f}% "
              f"(Δ={r['tir_improvement']*100:+.0f}pp)")
        print(f"    4h hypo: sched={r['hypo_4h_sched']*100:.0f}%, "
              f"demand={r['hypo_4h_demand']*100:.0f}% "
              f"(Δ={r['hypo_increase']*100:+.0f}pp)")
        print(f"    Mean 4h BG: sched={r['mean_4h_sched']:.0f}, "
              f"demand={r['mean_4h_demand']:.0f}")
        print(f"    Dist from target: sched={r['dist_target_sched']:.0f}, "
              f"demand={r['dist_target_demand']:.0f}")

        results[pid] = r

    # === Hypothesis testing ===
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)
    total = len(results)

    # H1: Demand-ISF gets ≥20% more corrections to target
    better_tir = sum(1 for r in results.values() if r["tir_improvement"] >= 0.20)
    mean_tir_imp = np.mean([r["tir_improvement"] for r in results.values()])
    print(f"\n  H1: Demand-ISF TIR ≥20pp better for ≥50% of patients")
    print(f"      {better_tir}/{total} patients")
    print(f"      Mean TIR improvement: {mean_tir_imp*100:+.1f}pp")
    tir_imps = [f'{r["tir_improvement"]*100:+.0f}pp' for r in results.values()]
    print(f"      Per-patient: {tir_imps}")
    h1 = better_tir >= total / 2
    print(f"      → {'PASS' if h1 else 'FAIL'}")

    # H2: Hypo increase < 5% absolute
    max_hypo_increase = max(r["hypo_increase"] for r in results.values())
    print(f"\n  H2: Hypo increase < 5pp for all patients")
    print(f"      Max increase: {max_hypo_increase*100:+.1f}pp")
    hypo_incs = [f'{r["hypo_increase"]*100:+.0f}pp' for r in results.values()]
    print(f"      Per-patient: {hypo_incs}")
    h2 = max_hypo_increase < 0.05
    print(f"      → {'PASS' if h2 else 'FAIL'}")

    # H3: Mean 4h glucose closer to target
    closer = sum(1 for r in results.values()
                 if r["dist_target_demand"] < r["dist_target_sched"])
    print(f"\n  H3: Demand-ISF mean 4h BG closer to target")
    print(f"      {closer}/{total} patients closer")
    h3 = closer > total / 2
    print(f"      → {'PASS' if h3 else 'FAIL'}")

    # H4: Safety/efficacy tradeoff varies ≥2×
    ratios = [r["tir_improvement"] / max(0.001, r["hypo_increase"])
              if r["hypo_increase"] > 0 else 999
              for r in results.values()]
    finite_ratios = [r for r in ratios if r < 100]
    if finite_ratios:
        ratio_range = max(finite_ratios) / min(finite_ratios) if min(finite_ratios) > 0 else float("inf")
        print(f"\n  H4: Safety/efficacy ratio varies ≥2×")
        print(f"      Range: {ratio_range:.1f}×")
        h4 = ratio_range >= 2.0
        print(f"      → {'PASS' if h4 else 'FAIL'}")

    # Summary table
    print("\n" + "=" * 70)
    print("DOSING STRATEGY COMPARISON")
    print("=" * 70)
    print(f"  {'Patient':<16} {'Sched ISF':>9} {'Demand ISF':>10} {'Infl':>5} "
          f"{'Dose×':>6} {'ΔTIR':>6} {'ΔHypo':>6} {'Closer':>7}")
    for pid, r in results.items():
        closer_str = "✓" if r["dist_target_demand"] < r["dist_target_sched"] else "✗"
        print(f"  {pid:<16} {r['scheduled_isf']:>9.0f} {r['demand_isf']:>10.0f} "
              f"{r['inflation_ratio']:>5.1f}× {r['mean_dose_ratio']:>5.1f}× "
              f"{r['tir_improvement']*100:>+5.0f}pp {r['hypo_increase']*100:>+5.0f}pp "
              f"{closer_str:>7}")

    Path(OUTFILE).write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
