#!/usr/bin/env python3
"""EXP-2626: Supply/Demand Asymmetry Synthesis & Settings Impact.

Synthesizes EXP-2621-2625 findings into actionable settings recommendations
and quantifies the fundamental asymmetry between EGP supply and insulin demand.

KEY INSIGHT: Insulin demand and EGP supply operate on fundamentally different
timescales. This breaks the symmetry assumption in AID controllers that use
a single ISF for both correction dosing and glucose prediction.

  Insulin Demand: peak at 1.25h, DIA=6h, well-characterized exponential model
  EGP Supply: suppression onset ~1h, full suppression 2-3h, recovery 3.5h+

The 2.25h phase lag between insulin peak and glucose nadir means:
  - Apparent ISF from corrections is INFLATED (25-188% per patient)
  - Corrections appear more effective than they are
  - Post-correction "rebounds" are actually EGP recovery, not failed corrections
  - Basal rate should match EGP rate, but EGP is circadian
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
OUTFILE = RESULTS_DIR / "exp-2626_asymmetry_synthesis.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Insulin model: DIA=6h, peak=75min (rapid-acting)
DIA_HOURS = 6.0
PEAK_MIN = 75.0


def _insulin_iob_fraction(t_minutes):
    """IOB fraction remaining at time t (0 to DIA).

    Uses the exponential model matching Loop/oref0/AAPS:
    LoopKit InsulinMath.swift, oref0 calculate.js, AAPS InsulinOrefBasePlugin.kt
    """
    td = DIA_HOURS * 60.0
    tp = PEAK_MIN
    tau = tp * (1.0 - tp / td) / (1.0 - 2.0 * tp / td)
    a = 2.0 * tau / td
    S = 1.0 / (1.0 - a + (1.0 + a) * np.exp(-td / tau))
    t = np.clip(t_minutes, 0, td)
    # IOB = fraction of insulin NOT YET absorbed
    absorbed = S * (1.0 - a) * (
        (np.power(t, 2) / (tau * td * (1.0 - a)) - t / tau - 1.0) *
        np.exp(-t / tau) + 1.0
    )
    return np.clip(1.0 - absorbed, 0, 1)


def _compute_asymmetry_metrics(events):
    """Compute supply/demand asymmetry metrics from correction events.

    For each correction event, we can observe:
    1. Demand phase: pre-BG to BG@2h (insulin-dominated)
    2. Transition: BG@2h to nadir (mixed: waning demand + suppressed supply)
    3. Supply phase: nadir to nadir+2h (EGP recovery)
    """
    metrics = []
    for e in events:
        bg_2h = e.get("bg_at_2h")
        if bg_2h is None:
            continue

        pre_bg = e["pre_bg"]
        nadir_bg = e["nadir_bg"]
        nadir_h = e["nadir_hours"]
        recovery = e["recovery_slope_mgdl_hr"]
        bolus = e["bolus_u"]

        bg_2h = e.get("bg_at_2h")
        if bg_2h is None or np.isnan(bg_2h):
            # Fall back: estimate bg at 2h from nadir interpolation
            # If nadir is at 3.5h and we know pre_bg and nadir_bg,
            # linear interpolation at 2h: pre_bg + (nadir_bg - pre_bg) * (2/nadir_h)
            if nadir_h > 0.5:
                bg_2h = pre_bg + (nadir_bg - pre_bg) * (2.0 / nadir_h)
            else:
                continue

        # Phase 1: Demand-driven drop (0 to 2h)
        demand_drop = pre_bg - bg_2h
        demand_rate = demand_drop / 2.0  # mg/dL/hr

        # Phase 2: Transition drop (2h to nadir)
        transition_time = max(nadir_h - 2.0, 0.083)  # at least 5 min
        transition_drop = bg_2h - nadir_bg
        transition_rate = transition_drop / transition_time

        # Phase 3: Recovery (supply reasserting)
        supply_rate = recovery  # mg/dL/hr, already computed

        # Asymmetry ratio: how much faster is demand than supply recovery?
        if abs(supply_rate) > 0.1:
            asymmetry_ratio = abs(demand_rate) / abs(supply_rate)
        else:
            asymmetry_ratio = float("inf")

        # IOB at nadir (how much insulin is left when glucose bottoms)
        iob_frac = _insulin_iob_fraction(nadir_h * 60)

        # Effective ISF at different phases
        # Demand ISF: drop in first 2h / bolus × IOB_used
        iob_used_2h = 1.0 - _insulin_iob_fraction(120)
        if iob_used_2h > 0:
            demand_isf = demand_drop / (bolus * iob_used_2h)
        else:
            demand_isf = np.nan

        # Total ISF (apparent): total drop / bolus
        apparent_isf = (pre_bg - nadir_bg) / bolus

        metrics.append({
            "demand_rate": demand_rate,
            "transition_rate": transition_rate,
            "supply_rate": supply_rate,
            "asymmetry_ratio": min(asymmetry_ratio, 100),
            "demand_drop": demand_drop,
            "transition_drop": transition_drop,
            "total_drop": pre_bg - nadir_bg,
            "iob_at_nadir_frac": iob_frac,
            "demand_isf": demand_isf if not np.isnan(demand_isf) else None,
            "apparent_isf": apparent_isf,
            "nadir_hours": nadir_h,
            "bolus_u": bolus,
            "pre_bg": pre_bg,
        })

    return metrics


def _compute_basal_recommendation(recovery_slope, scheduled_basal, scheduled_isf,
                                  circadian=None):
    """Derive basal adjustment from EGP recovery.

    If recovery is high, glucose rises fast after corrections → EGP > basal demand.
    Conservative recommendation: adjust 50% of the gap.
    """
    # Recovery slope is net: EGP_rate - residual_insulin_effect
    # At 3.5h post-bolus, ~30% of correction IOB remains + full basal IOB
    # The recovery slope IS the supply-demand imbalance signal

    if recovery_slope > 20:
        direction = "increase"
        magnitude = recovery_slope / scheduled_isf * 0.5  # conservative 50%
        confidence = "moderate"
    elif recovery_slope > 5:
        direction = "slight_increase"
        magnitude = recovery_slope / scheduled_isf * 0.3
        confidence = "low"
    elif recovery_slope < -5:
        direction = "decrease"
        magnitude = abs(recovery_slope) / scheduled_isf * 0.3
        confidence = "low"
    else:
        direction = "maintain"
        magnitude = 0
        confidence = "high"

    rec = {
        "current_basal": scheduled_basal,
        "suggested_basal": round(scheduled_basal + magnitude, 2),
        "adjustment_u_hr": round(magnitude, 3),
        "direction": direction,
        "confidence": confidence,
        "basis": f"Recovery slope {recovery_slope:.1f} mg/dL/hr",
    }

    # Circadian-specific recommendations
    if circadian and circadian.get("day_n", 0) >= 3 and circadian.get("night_n", 0) >= 3:
        day_rec = circadian["day_recovery_median"]
        night_rec = circadian["night_recovery_median"]
        dawn_effect = circadian["dawn_effect"]

        if abs(dawn_effect) > 10:
            rec["circadian_note"] = (
                f"Day/night split: day={day_rec:.0f}, night={night_rec:.0f} mg/dL/hr. "
                f"Consider separate day/night basal rates."
            )
            if night_rec > day_rec + 5:
                rec["night_adjustment"] = round(
                    (night_rec - day_rec) / scheduled_isf * 0.3, 3)
            elif day_rec > night_rec + 5:
                rec["day_adjustment"] = round(
                    (day_rec - night_rec) / scheduled_isf * 0.3, 3)

    return rec


def _compute_isf_recommendation(apparent_isf, corrected_isf, scheduled_isf,
                                inflation_pct):
    """Derive ISF adjustment from EGP-corrected analysis."""
    rec = {
        "scheduled_isf": scheduled_isf,
        "apparent_isf_from_corrections": round(apparent_isf, 1),
    }

    if corrected_isf is not None and inflation_pct is not None:
        rec["egp_corrected_isf"] = round(corrected_isf, 1)
        rec["inflation_pct"] = round(inflation_pct, 1)

        if inflation_pct > 30:
            rec["recommendation"] = (
                f"ISF likely inflated ~{inflation_pct:.0f}% by EGP suppression. "
                f"True ISF ≈ {corrected_isf:.0f} mg/dL/U. "
                f"Correction doses may need to be larger than ISF suggests."
            )
            rec["action"] = "review_isf_lower"
        elif inflation_pct > 15:
            rec["recommendation"] = (
                f"Moderate ISF inflation (~{inflation_pct:.0f}%). "
                f"Consider ISF closer to {corrected_isf:.0f}."
            )
            rec["action"] = "monitor"
        else:
            rec["recommendation"] = "ISF appears minimally affected by EGP suppression."
            rec["action"] = "no_change"
    else:
        rec["recommendation"] = "Insufficient data for EGP correction."
        rec["action"] = "insufficient_data"

    return rec


def main():
    print("=" * 70)
    print("EXP-2626: Supply/Demand Asymmetry Synthesis")
    print("=" * 70)

    # Load prior results
    with open(RESULTS_DIR / "exp-2625_egp_aware_settings.json") as f:
        r25 = json.load(f)

    df = pd.read_parquet(PARQUET)
    all_results = {}
    all_asymmetry = []
    all_recommendations = []

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288:
            continue

        scheduled_basal = float(pdf["scheduled_basal_rate"].dropna().median())
        scheduled_isf = float(pdf["scheduled_isf"].dropna().median())
        scheduled_cr = float(pdf["scheduled_cr"].dropna().median())

        # TIR metrics
        glucose = pdf["glucose"].dropna()
        tir = float(((glucose >= 70) & (glucose <= 180)).mean() * 100)
        tar = float((glucose > 180).mean() * 100)
        tbr = float((glucose < 70).mean() * 100)
        mean_bg = float(glucose.mean())
        cv = float(glucose.std() / glucose.mean() * 100)

        p25 = r25["per_patient"].get(pid, {})

        if "egp_parameters" not in p25:
            print(f"  No EGP data (too few corrections)")
            all_results[pid] = {
                "status": "insufficient_corrections",
                "scheduled": {"basal": scheduled_basal, "isf": scheduled_isf, "cr": scheduled_cr},
                "outcomes": {"tir": tir, "tar": tar, "tbr": tbr, "mean_bg": mean_bg, "cv": cv},
            }
            continue

        egp = p25["egp_parameters"]
        isf_data = p25["isf_analysis"]
        circ = p25.get("circadian", {})

        # Asymmetry metrics from correction events
        # Re-extract events for detailed phase analysis
        from exp_egp_settings_2625 import _extract_correction_events
        events = _extract_correction_events(pdf)
        asymmetry = _compute_asymmetry_metrics(events)
        all_asymmetry.extend(asymmetry)

        if asymmetry:
            med_demand = float(np.median([m["demand_rate"] for m in asymmetry]))
            med_supply = float(np.median([m["supply_rate"] for m in asymmetry]))
            med_ratio = float(np.median([m["asymmetry_ratio"] for m in asymmetry
                                         if m["asymmetry_ratio"] < 100]))
            med_iob = float(np.median([m["iob_at_nadir_frac"] for m in asymmetry]))
            demand_isfs = [m["demand_isf"] for m in asymmetry if m["demand_isf"] is not None]
            med_demand_isf = float(np.median(demand_isfs)) if demand_isfs else None

            print(f"  Asymmetry: demand={med_demand:.0f}, supply={med_supply:.0f} mg/dL/hr "
                  f"(ratio={med_ratio:.1f}×)")
            print(f"  IOB at nadir: {med_iob:.0%} remaining")
            if med_demand_isf:
                print(f"  Demand-phase ISF: {med_demand_isf:.0f} vs apparent {isf_data['apparent_isf_median']:.0f}")
        else:
            med_demand = med_supply = med_ratio = med_iob = med_demand_isf = None

        # Recommendations
        basal_rec = _compute_basal_recommendation(
            egp["recovery_slope_median"], scheduled_basal, scheduled_isf, circ)
        isf_rec = _compute_isf_recommendation(
            isf_data["apparent_isf_median"],
            isf_data.get("corrected_isf_median"),
            scheduled_isf,
            isf_data.get("isf_inflation_pct"))

        print(f"  Basal: {basal_rec['direction']} ({basal_rec['current_basal']:.2f} → "
              f"{basal_rec['suggested_basal']:.2f} U/hr)")
        print(f"  ISF: {isf_rec['action']}")
        if "circadian_note" in basal_rec:
            print(f"  ⚠ {basal_rec['circadian_note']}")

        patient_rec = {
            "patient": pid,
            "scheduled": {"basal": scheduled_basal, "isf": scheduled_isf, "cr": scheduled_cr},
            "outcomes": {"tir": tir, "tar": tar, "tbr": tbr, "mean_bg": mean_bg, "cv": cv},
            "egp": {
                "recovery_slope": egp["recovery_slope_median"],
                "phase_lag_hours": egp["phase_lag_hours"],
                "nadir_hours": egp["nadir_hours_median"],
            },
            "asymmetry": {
                "demand_rate": med_demand,
                "supply_rate": med_supply,
                "ratio": med_ratio,
                "iob_at_nadir_frac": med_iob,
                "demand_phase_isf": med_demand_isf,
            },
            "recommendations": {
                "basal": basal_rec,
                "isf": isf_rec,
            },
        }
        all_results[pid] = patient_rec
        all_recommendations.append(patient_rec)

    # ── Population-Level Asymmetry ────────────────────────────────────
    print("\n" + "=" * 70)
    print("POPULATION-LEVEL SUPPLY/DEMAND ASYMMETRY")
    print("=" * 70)

    if all_asymmetry:
        demand_rates = [m["demand_rate"] for m in all_asymmetry]
        supply_rates = [m["supply_rate"] for m in all_asymmetry]
        ratios = [m["asymmetry_ratio"] for m in all_asymmetry if m["asymmetry_ratio"] < 100]
        iob_at_nadir = [m["iob_at_nadir_frac"] for m in all_asymmetry]
        transition_drops = [m["transition_drop"] for m in all_asymmetry]

        print(f"  N correction events: {len(all_asymmetry)}")
        print(f"  Demand rate: median={np.median(demand_rates):.0f} mg/dL/hr")
        print(f"  Supply recovery: median={np.median(supply_rates):.0f} mg/dL/hr")
        print(f"  Asymmetry ratio: median={np.median(ratios):.1f}× (demand faster)")
        print(f"  IOB at nadir: median={np.median(iob_at_nadir):.0%}")
        print(f"  Transition drop (2h→nadir): median={np.median(transition_drops):.0f} mg/dL")
        print(f"    This is the EGP-suppression glucose drop NOT explained by insulin")

        # Fraction of total drop from EGP suppression
        total_drops = [m["total_drop"] for m in all_asymmetry]
        egp_fracs = [t / d if d > 0 else 0 for t, d in zip(transition_drops, total_drops)]
        print(f"  EGP suppression fraction of total drop: median={np.median(egp_fracs):.0%}")

    # ── AID Controller Implications ──────────────────────────────────
    print("\n" + "=" * 70)
    print("AID CONTROLLER IMPLICATIONS")
    print("=" * 70)
    print("""
  Current AID controllers (Loop, oref0, Trio) assume:
    1. ISF is symmetric — same value for prediction and dosing
    2. Glucose nadir from correction ≈ insulin peak (1-2h)
    3. Post-correction glucose = f(IOB, ISF) with no EGP dynamics

  Our findings show:
    1. ISF is ASYMMETRIC — demand-phase ISF ≠ apparent ISF ≠ true ISF
    2. Nadir is at 3.5h (2.25h AFTER insulin peak) due to EGP suppression
    3. Post-correction glucose has 3 phases: demand, transition, recovery

  Practical consequences:
    - Controllers OVER-PREDICT correction effectiveness at 2h
    - Controllers UNDER-PREDICT correction effectiveness at 3.5h
    - Post-correction "rebounds" at 4-6h are EGP recovery, not failed corrections
    - "Stacking" algorithms using ISF may stack too aggressively
      (thinking each unit does more than its demand-phase effect alone)

  Proposed improvements:
    1. Dual-ISF: Use demand-phase ISF for correction sizing,
       apparent ISF for prediction horizon
    2. EGP recovery term in prediction: after correction, model
       glucose recovery at patient-specific rate (4.7-44.8 mg/dL/hr)
    3. Circadian EGP: use time-of-day recovery rates for overnight
       vs daytime basal and correction behavior
    """)

    # ── Save ──────────────────────────────────────────────────────────
    summary = {
        "experiment": "EXP-2626",
        "title": "Supply/Demand Asymmetry Synthesis & Settings Impact",
        "population_asymmetry": {
            "n_events": len(all_asymmetry),
            "demand_rate_median": float(np.median(demand_rates)) if all_asymmetry else None,
            "supply_rate_median": float(np.median(supply_rates)) if all_asymmetry else None,
            "asymmetry_ratio_median": float(np.median(ratios)) if ratios else None,
            "iob_at_nadir_median": float(np.median(iob_at_nadir)) if all_asymmetry else None,
            "egp_suppression_frac_median": float(np.median(egp_fracs)) if all_asymmetry else None,
        },
        "per_patient": all_results,
        "recommendations": all_recommendations,
        "asymmetry_events": all_asymmetry[:50],  # sample for viz
    }

    with open(OUTFILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")

    return summary


if __name__ == "__main__":
    main()
