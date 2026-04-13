#!/usr/bin/env python3
"""EXP-2625: Per-Patient EGP-Aware Settings Optimization.

MOTIVATION: Each patient's metabolic system is unique. EXP-2624 showed
population-level EGP phase lag (nadir at 3.5h vs insulin peak at 1.25h)
and recovery slope ≈ EGP rate. This experiment extracts PER-PATIENT
EGP parameters and uses them to derive individualized settings:

1. EGP Rate: post-correction recovery slope (adjusted for basal delivery)
2. EGP Phase Lag: individual nadir timing vs insulin peak
3. EGP-Corrected ISF: apparent ISF inflated by EGP suppression during correction
4. Basal Adequacy: recovery slope vs scheduled basal → is basal matching EGP?

DIA NOTE: All 9 NS patients have DIA=6.0h (pharmacokinetic, rapid-acting
insulin). ODC patients vary 3-7h, which would confound nadir timing if
DIA is set incorrectly. This analysis assumes DIA=6.0h is correct.

HYPOTHESES:
  H1: Per-patient recovery slope correlates with scheduled basal rate (r≥0.3).
      When basal matches EGP, the system is in equilibrium.
  H2: EGP-corrected ISF differs from raw ISF by ≥15% for ≥50% of patients.
      The EGP suppression inflates apparent ISF from corrections.
  H3: Per-patient nadir timing varies meaningfully (σ≥0.5h across patients).
      Individual EGP suppression dynamics differ — one size doesn't fit all.
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
OUTFILE = RESULTS_DIR / "exp-2625_egp_aware_settings.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Insulin model parameters (rapid-acting, DIA=6h, peak=75min)
DIA_HOURS = 6.0
PEAK_MIN = 75.0


def _insulin_activity_fraction(t_minutes):
    """Fraction of total insulin activity at time t (minutes).

    Uses the exponential model matching Loop/oref0/AAPS.
    Returns the cumulative fraction of insulin absorbed by time t.
    """
    td = DIA_HOURS * 60.0  # total duration in minutes
    tp = PEAK_MIN
    tau = tp * (1.0 - tp / td) / np.log(0.01)
    a = 2.0 * tau / td
    S = 1.0 / (1.0 - a + (1.0 + a) * np.exp(-td / tau))

    t = np.clip(t_minutes, 0, td)
    iob_fraction = 1.0 - S * (1.0 - a) * (
        (np.power(t, 2) / (tau * td * (1.0 - a)) - t / tau - 1.0) *
        np.exp(-t / tau) + 1.0
    )
    return np.clip(iob_fraction, 0, 1)


def _expected_nadir_time():
    """Time (hours) when insulin activity rate peaks.

    For rapid-acting with peak=75min, this is ≈1.25h.
    """
    return PEAK_MIN / 60.0


def _extract_correction_events(pdf):
    """Extract correction events — same criteria as EXP-2624."""
    times = pd.to_datetime(pdf["time"])
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    n = len(glucose)

    events = []
    PRE_STEPS = 6      # 30 min
    POST_STEPS = 72    # 6h
    NADIR_SEARCH = 48  # 4h

    for i in range(PRE_STEPS, n - POST_STEPS):
        if bolus[i] < 0.5:
            continue
        # No carbs ±1h
        if np.nansum(carbs[max(0, i - 12):min(n, i + 12)]) > 2.0:
            continue
        # No prior bolus 2h
        if np.nansum(bolus[max(0, i - 24):i]) > 0.1:
            continue

        pre_bg = float(np.nanmean(glucose[i - PRE_STEPS:i][~np.isnan(glucose[i - PRE_STEPS:i])]))
        if np.isnan(pre_bg) or pre_bg < 120:
            continue

        post = glucose[i:i + POST_STEPS]
        if np.sum(~np.isnan(post)) < POST_STEPS // 2:
            continue

        smoothed = pd.Series(post).rolling(3, center=True, min_periods=1).mean().values

        # Actual nadir (within 4h)
        nadir_search = smoothed[:NADIR_SEARCH]
        valid = ~np.isnan(nadir_search)
        if valid.sum() < 6:
            continue
        nadir_idx = np.nanargmin(nadir_search)
        nadir_bg = float(nadir_search[nadir_idx])
        nadir_hours = nadir_idx * 5.0 / 60.0

        drop = pre_bg - nadir_bg
        if drop < 10:
            continue

        # Glucose at insulin peak time (≈1.25h = 15 steps)
        peak_idx = int(PEAK_MIN / 5.0)
        if peak_idx < len(smoothed) and not np.isnan(smoothed[peak_idx]):
            bg_at_insulin_peak = float(smoothed[peak_idx])
        else:
            bg_at_insulin_peak = np.nan

        # Glucose at 2h (24 steps) — "insulin-only expected nadir"
        idx_2h = 24
        if idx_2h < len(smoothed) and not np.isnan(smoothed[idx_2h]):
            bg_at_2h = float(smoothed[idx_2h])
        else:
            bg_at_2h = np.nan

        # Recovery slope (2h post-nadir)
        rec_start = nadir_idx
        rec_end = min(len(post), nadir_idx + 24)
        rec = post[rec_start:rec_end]
        valid_rec = ~np.isnan(rec)
        if valid_rec.sum() < 6:
            continue
        t_hrs = np.arange(len(rec)) * (5.0 / 60.0)
        slope, _ = np.polyfit(t_hrs[valid_rec], rec[valid_rec], 1)

        # Apparent ISF (from total drop)
        apparent_isf = drop / bolus[i]

        # EGP-corrected ISF: what would ISF be if drop stopped at 2h?
        if not np.isnan(bg_at_2h):
            drop_at_2h = pre_bg - bg_at_2h
            if drop_at_2h > 0:
                corrected_isf = drop_at_2h / bolus[i]
            else:
                corrected_isf = np.nan
        else:
            corrected_isf = np.nan

        # Extra drop from EGP suppression (2h to nadir)
        if not np.isnan(bg_at_2h):
            egp_suppression_drop = bg_at_2h - nadir_bg
        else:
            egp_suppression_drop = np.nan

        # IOB fraction remaining at nadir
        iob_frac_at_nadir = 1.0 - _insulin_activity_fraction(nadir_hours * 60.0)

        events.append({
            "index": int(i),
            "timestamp": str(times.iloc[i]),
            "hour_of_day": float(times.iloc[i].hour + times.iloc[i].minute / 60.0),
            "bolus_u": float(bolus[i]),
            "pre_bg": pre_bg,
            "nadir_bg": nadir_bg,
            "drop_mgdl": drop,
            "nadir_hours": nadir_hours,
            "bg_at_insulin_peak": bg_at_insulin_peak,
            "bg_at_2h": bg_at_2h,
            "recovery_slope_mgdl_hr": float(slope),
            "apparent_isf": apparent_isf,
            "corrected_isf": corrected_isf if not np.isnan(corrected_isf) else None,
            "egp_suppression_drop": egp_suppression_drop if not np.isnan(egp_suppression_drop) else None,
            "iob_frac_at_nadir": iob_frac_at_nadir,
        })

    return events


def _per_patient_egp_profile(events, scheduled_basal, scheduled_isf):
    """Derive per-patient EGP parameters from correction events."""
    if len(events) < 5:
        return None

    nadir_hrs = [e["nadir_hours"] for e in events]
    recovery_slopes = [e["recovery_slope_mgdl_hr"] for e in events]
    apparent_isfs = [e["apparent_isf"] for e in events]
    corrected_isfs = [e["corrected_isf"] for e in events if e["corrected_isf"] is not None]
    egp_drops = [e["egp_suppression_drop"] for e in events if e["egp_suppression_drop"] is not None]

    # EGP Rate estimate: recovery slope + basal demand still being delivered
    # recovery_slope = EGP_rate - basal_effect
    # basal_effect ≈ scheduled_basal × ISF / DIA_hours (rough: avg insulin action from basal)
    # Simplified: recovery slope is a lower bound on EGP rate
    median_recovery = float(np.median(recovery_slopes))
    mean_recovery = float(np.mean(recovery_slopes))

    # At nadir, basal is still being delivered. The recovery slope includes
    # the net of EGP recovering minus basal still lowering glucose.
    # Estimated EGP rate = recovery_slope + basal_demand_rate_at_nadir
    # basal demand ≈ basal_rate * ISF (mg/dL/hr per U/hr × mg/dL/U = mg/dL/hr)
    # BUT ISF is per-unit correction, and basal is continuous. Need to account
    # for the fact that basal insulin accumulates to steady-state IOB.
    # Steady-state IOB from basal = basal_rate × DIA/2 ≈ basal × 3h
    # This is already absorbed in the "scheduled" basal — the system is
    # designed so basal + EGP = steady glucose. So:
    # At steady state: EGP_rate = basal_demand = basal_rate × ISF
    # After correction: glucose rises because EGP > (depleted insulin demand)
    basal_demand_rate = scheduled_basal * scheduled_isf  # mg/dL/hr equivalent

    # EGP rate estimate: during recovery, insulin from the correction is mostly
    # spent (70-85% at 3.5h), basal is running. Recovery = EGP - residual_all
    # For simplicity: estimated_egp ≈ recovery + basal_demand × 0.3
    # (since basal contributes ~30% of demand at the margins)
    estimated_egp_rate = median_recovery  # lower bound

    # ISF comparison
    median_apparent_isf = float(np.median(apparent_isfs))
    if corrected_isfs:
        median_corrected_isf = float(np.median(corrected_isfs))
        isf_inflation_pct = (median_apparent_isf - median_corrected_isf) / median_corrected_isf * 100
    else:
        median_corrected_isf = None
        isf_inflation_pct = None

    # EGP suppression contribution
    if egp_drops:
        median_egp_drop = float(np.median(egp_drops))
        egp_drop_frac = median_egp_drop / float(np.median([e["drop_mgdl"] for e in events]))
    else:
        median_egp_drop = None
        egp_drop_frac = None

    # Nadir timing distribution
    nadir_mean = float(np.mean(nadir_hrs))
    nadir_std = float(np.std(nadir_hrs))
    nadir_median = float(np.median(nadir_hrs))

    # Circadian variation: do corrections behave differently by time of day?
    day_events = [e for e in events if 6 <= e["hour_of_day"] < 22]
    night_events = [e for e in events if e["hour_of_day"] < 6 or e["hour_of_day"] >= 22]

    circadian = {}
    if len(day_events) >= 3 and len(night_events) >= 3:
        day_recovery = [e["recovery_slope_mgdl_hr"] for e in day_events]
        night_recovery = [e["recovery_slope_mgdl_hr"] for e in night_events]
        circadian = {
            "day_recovery_median": float(np.median(day_recovery)),
            "night_recovery_median": float(np.median(night_recovery)),
            "day_n": len(day_events),
            "night_n": len(night_events),
            "dawn_effect": float(np.median(night_recovery) - np.median(day_recovery)),
        }

    # Basal adequacy: is recovery slope suggesting basal is too low or too high?
    # If glucose rises fast after correction → EGP > basal demand → basal too low
    # If glucose barely recovers → basal ≈ matches EGP → basal adequate
    # If glucose continues falling → basal > EGP → basal possibly too high
    pos_recovery_frac = sum(1 for s in recovery_slopes if s > 0) / len(recovery_slopes)

    if median_recovery > 20:
        basal_assessment = "POSSIBLY_LOW"
        basal_detail = f"Fast recovery ({median_recovery:.0f} mg/dL/hr) suggests EGP exceeds basal demand"
    elif median_recovery < 2:
        basal_assessment = "POSSIBLY_HIGH"
        basal_detail = f"Minimal recovery ({median_recovery:.0f} mg/dL/hr) suggests basal well-matches or exceeds EGP"
    else:
        basal_assessment = "ADEQUATE"
        basal_detail = f"Moderate recovery ({median_recovery:.0f} mg/dL/hr) suggests reasonable basal-EGP balance"

    return {
        "n_events": len(events),
        "egp_parameters": {
            "recovery_slope_median": median_recovery,
            "recovery_slope_mean": mean_recovery,
            "estimated_egp_rate_lower_bound": estimated_egp_rate,
            "nadir_hours_median": nadir_median,
            "nadir_hours_mean": nadir_mean,
            "nadir_hours_std": nadir_std,
            "phase_lag_hours": nadir_median - _expected_nadir_time(),
        },
        "isf_analysis": {
            "scheduled_isf": scheduled_isf,
            "apparent_isf_median": median_apparent_isf,
            "corrected_isf_median": median_corrected_isf,
            "isf_inflation_pct": isf_inflation_pct,
            "egp_suppression_drop_median": median_egp_drop,
            "egp_drop_fraction_of_total": egp_drop_frac,
        },
        "basal_analysis": {
            "scheduled_basal_rate": scheduled_basal,
            "basal_demand_rate_mgdl_hr": basal_demand_rate,
            "recovery_slope_median": median_recovery,
            "positive_recovery_fraction": pos_recovery_frac,
            "assessment": basal_assessment,
            "detail": basal_detail,
        },
        "circadian": circadian,
    }


def main():
    print("=" * 70)
    print("EXP-2625: Per-Patient EGP-Aware Settings Optimization")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}
    patient_profiles = []

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288:
            print(f"  SKIP: insufficient data")
            continue

        scheduled_basal = float(pdf["scheduled_basal_rate"].dropna().median())
        scheduled_isf = float(pdf["scheduled_isf"].dropna().median())
        scheduled_cr = float(pdf["scheduled_cr"].dropna().median())

        events = _extract_correction_events(pdf)
        print(f"  Correction events: {len(events)}")

        profile = _per_patient_egp_profile(events, scheduled_basal, scheduled_isf)

        if profile is None:
            print(f"  SKIP: too few events (<5)")
            all_results[pid] = {
                "n_events": len(events),
                "status": "insufficient_data",
                "scheduled_basal": scheduled_basal,
                "scheduled_isf": scheduled_isf,
                "scheduled_cr": scheduled_cr,
            }
            continue

        egp = profile["egp_parameters"]
        isf = profile["isf_analysis"]
        bas = profile["basal_analysis"]

        print(f"  EGP Recovery: {egp['recovery_slope_median']:.1f} mg/dL/hr "
              f"(lower bound EGP rate)")
        print(f"  Nadir: {egp['nadir_hours_median']:.1f}h "
              f"(phase lag: {egp['phase_lag_hours']:.1f}h vs insulin peak)")
        print(f"  Apparent ISF: {isf['apparent_isf_median']:.0f} mg/dL/U "
              f"(scheduled: {isf['scheduled_isf']:.0f})")
        if isf['corrected_isf_median'] is not None:
            print(f"  EGP-Corrected ISF: {isf['corrected_isf_median']:.0f} mg/dL/U "
                  f"(inflation: {isf['isf_inflation_pct']:.0f}%)")
        print(f"  Basal: {bas['assessment']} — {bas['detail']}")
        if profile["circadian"]:
            c = profile["circadian"]
            print(f"  Circadian: day={c['day_recovery_median']:.1f}, "
                  f"night={c['night_recovery_median']:.1f} mg/dL/hr "
                  f"(dawn effect: {c['dawn_effect']:+.1f})")

        all_results[pid] = {
            "scheduled_basal": scheduled_basal,
            "scheduled_isf": scheduled_isf,
            "scheduled_cr": scheduled_cr,
            **profile,
        }
        patient_profiles.append({
            "patient": pid,
            "recovery_slope": egp["recovery_slope_median"],
            "nadir_hours": egp["nadir_hours_median"],
            "phase_lag": egp["phase_lag_hours"],
            "apparent_isf": isf["apparent_isf_median"],
            "corrected_isf": isf["corrected_isf_median"],
            "isf_inflation_pct": isf["isf_inflation_pct"],
            "scheduled_basal": scheduled_basal,
            "basal_assessment": bas["assessment"],
        })

    # ── Hypothesis Testing ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_data = [p for p in patient_profiles]

    # H1: Recovery slope correlates with scheduled basal
    if len(patients_with_data) >= 4:
        recovery_vals = [p["recovery_slope"] for p in patients_with_data]
        basal_vals = [p["scheduled_basal"] for p in patients_with_data]
        r_h1, p_h1 = stats.pearsonr(recovery_vals, basal_vals)
        h1_pass = abs(r_h1) >= 0.3
        print(f"  H1: r(recovery_slope, scheduled_basal) = {r_h1:.3f} "
              f"(p={p_h1:.3f}) → {'PASS' if h1_pass else 'FAIL'}")
        for p in patients_with_data:
            print(f"      {p['patient']}: recovery={p['recovery_slope']:.1f}, "
                  f"basal={p['scheduled_basal']:.2f}")
    else:
        h1_pass = False
        r_h1, p_h1 = 0, 1
        print("  H1: Insufficient patients → FAIL")

    # H2: EGP-corrected ISF differs by ≥15% for ≥50% of patients
    inflated = [p for p in patients_with_data
                if p["isf_inflation_pct"] is not None and abs(p["isf_inflation_pct"]) >= 15]
    total_with_isf = [p for p in patients_with_data if p["isf_inflation_pct"] is not None]
    if total_with_isf:
        frac_inflated = len(inflated) / len(total_with_isf)
        h2_pass = frac_inflated >= 0.5
        print(f"  H2: {len(inflated)}/{len(total_with_isf)} patients have ≥15% ISF inflation "
              f"({frac_inflated:.0%}) → {'PASS' if h2_pass else 'FAIL'}")
        for p in patients_with_data:
            if p["isf_inflation_pct"] is not None:
                marker = "***" if abs(p["isf_inflation_pct"]) >= 15 else ""
                print(f"      {p['patient']}: apparent={p['apparent_isf']:.0f}, "
                      f"corrected={p['corrected_isf']:.0f}, "
                      f"inflation={p['isf_inflation_pct']:.0f}% {marker}")
    else:
        h2_pass = False
        frac_inflated = 0
        print("  H2: No ISF data → FAIL")

    # H3: Nadir timing varies meaningfully (σ ≥ 0.5h across patients)
    if len(patients_with_data) >= 4:
        nadirs = [p["nadir_hours"] for p in patients_with_data]
        nadir_std = float(np.std(nadirs))
        h3_pass = nadir_std >= 0.5
        print(f"  H3: σ(nadir_hours) across patients = {nadir_std:.2f}h "
              f"(threshold: ≥0.5h) → {'PASS' if h3_pass else 'FAIL'}")
        print(f"      Range: {min(nadirs):.1f}h - {max(nadirs):.1f}h")
    else:
        h3_pass = False
        nadir_std = 0
        print("  H3: Insufficient patients → FAIL")

    # ── Summary Table ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PER-PATIENT EGP METABOLIC PROFILE")
    print("=" * 70)
    print(f"{'Pat':>4} {'RecovSlope':>10} {'Nadir_h':>8} {'PhaseLag':>8} "
          f"{'AppISF':>7} {'CorrISF':>8} {'Inflat%':>8} {'Basal':>6} {'Assessment':>15}")
    for p in patients_with_data:
        corr_str = f"{p['corrected_isf']:.0f}" if p["corrected_isf"] else "N/A"
        infl_str = f"{p['isf_inflation_pct']:.0f}%" if p["isf_inflation_pct"] else "N/A"
        print(f"{p['patient']:>4} {p['recovery_slope']:>10.1f} {p['nadir_hours']:>8.1f} "
              f"{p['phase_lag']:>8.1f} {p['apparent_isf']:>7.0f} {corr_str:>8} "
              f"{infl_str:>8} {p['scheduled_basal']:>6.2f} {p['basal_assessment']:>15}")

    # ── Save ──────────────────────────────────────────────────────────
    summary = {
        "experiment": "EXP-2625",
        "title": "Per-Patient EGP-Aware Settings Optimization",
        "dia_note": "All patients DIA=6.0h (pharmacokinetic, rapid-acting). "
                    "DIA is defined by insulin formulation, not patient. "
                    "User-adjustable DIA in some AID systems can confound results.",
        "insulin_model": {
            "dia_hours": DIA_HOURS,
            "peak_minutes": PEAK_MIN,
            "expected_pk_nadir_hours": _expected_nadir_time(),
        },
        "patients_analyzed": [p["patient"] for p in patients_with_data],
        "patients_insufficient": [pid for pid in FULL_PATIENTS
                                  if pid not in [p["patient"] for p in patients_with_data]],
        "per_patient": all_results,
        "hypotheses": {
            "H1": {
                "statement": "Recovery slope correlates with scheduled basal (r≥0.3)",
                "r": float(r_h1), "p": float(p_h1),
                "result": "PASS" if h1_pass else "FAIL",
            },
            "H2": {
                "statement": "EGP-corrected ISF differs ≥15% for ≥50% of patients",
                "fraction_inflated": float(frac_inflated) if total_with_isf else None,
                "result": "PASS" if h2_pass else "FAIL",
            },
            "H3": {
                "statement": "Per-patient nadir timing σ≥0.5h",
                "std_hours": float(nadir_std),
                "result": "PASS" if h3_pass else "FAIL",
            },
        },
        "patient_profiles": patient_profiles,
    }

    with open(OUTFILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")

    return summary


if __name__ == "__main__":
    main()
