#!/usr/bin/env python3
"""EXP-2658: Extended Prediction Horizon with Ceiling Model

Uses the SC suppression ceiling finding (EXP-2656: ~30%) to build a 3-phase
prediction model:
  Phase 1 (0-2h): Standard insulin-driven drop using demand ISF
  Phase 2 (2h-DIA): Ceiling-limited drop — glucose can't fall faster than
    (1 - ceiling) × dose_effect because EGP resists
  Phase 3 (DIA-8h): Recovery at (1-ceiling) × base_egp rate

Compare to "linear ISF" prediction at 2h, 4h, 6h, 8h.

Hypotheses:
  H1: 3-phase model has lower RMSE than linear at 4h horizon (≥20% improvement)
  H2: 3-phase model has lower RMSE at 6h horizon (≥30% improvement)
  H3: Phase 3 (recovery) prediction reduces 6-8h RMSE by ≥15%
  H4: Per-patient ceiling personalization further reduces RMSE (≥5%)
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

GRID = Path("externals/ns-parquet/training/grid.parquet")
CEILING_FILE = Path("externals/experiments/exp-2656_sc_ceiling.json")
OUT = Path("externals/experiments/exp-2658_extended_horizon.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k",
                 "odc-74077367", "odc-86025410", "odc-96254963"]

# Default parameters
DIA_H = 6.0
PEAK_MIN = 75
DEFAULT_CEILING = 0.30  # population median from EXP-2656
BASE_EGP = 18.0  # mg/dL/hr, from EXP-2624


def insulin_kernel(t_min, peak=PEAK_MIN, dia=DIA_H*60):
    """Exponential insulin model — fraction remaining at t_min."""
    tp = peak
    td = dia
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))
    iob = 1 - S * (1 - a) * ((np.power(t_min / tau, 2) / 2 +
           t_min / tau + 1) * np.exp(-t_min / tau) - 1)
    return np.clip(iob, 0, 1)


def find_corrections(pdf):
    """Gold-standard correction detection."""
    glucose = pdf["glucose"].values
    iob = pdf["iob"].values
    carbs = pdf.get("carbs", pd.Series(np.zeros(len(pdf)))).values
    bolus = pdf.get("bolus", pd.Series(np.zeros(len(pdf)))).values

    corrections = []
    for j in range(24, len(pdf) - 96):  # need 8h forward
        b = bolus[j] if not np.isnan(bolus[j]) else 0
        if b < 0.5:
            continue

        # No carbs within ±1h
        carb_window = carbs[max(0, j-12):j+12]
        if np.nanmax(carb_window) > 2.0:
            continue

        # No prior bolus within 2h
        prior_bolus = bolus[max(0, j-24):j]
        if np.nanmax(prior_bolus[:-1] if len(prior_bolus) > 1 else [0]) > 0.1:
            continue

        # Pre-BG check
        pre_window = glucose[max(0, j-6):j]
        valid_pre = pre_window[~np.isnan(pre_window)]
        if len(valid_pre) < 3 or np.mean(valid_pre) < 120:
            continue

        pre_bg = float(np.mean(valid_pre))

        # Need glucose at 2h, 4h, 6h, 8h (±15min)
        horizons = {}
        for h, label in [(24, "2h"), (48, "4h"), (72, "6h"), (96, "8h")]:
            window = glucose[j+h-3:j+h+3]
            valid = window[~np.isnan(window)]
            if len(valid) >= 1:
                horizons[label] = float(np.mean(valid))

        if len(horizons) < 3:
            continue

        corrections.append({
            "idx": int(j),
            "dose": float(b),
            "pre_bg": pre_bg,
            "actual": horizons,
        })

    return corrections


def predict_linear(pre_bg, dose, isf, horizon_h):
    """Standard linear ISF prediction: BG - dose × ISF, capped by DIA."""
    # Insulin effect: dose × ISF × fraction_delivered
    t_min = horizon_h * 60
    frac_delivered = 1 - insulin_kernel(t_min)
    return pre_bg - dose * isf * frac_delivered


def predict_3phase(pre_bg, dose, isf, ceiling, base_egp, horizon_h):
    """3-phase ceiling-aware prediction.

    Phase 1 (0-2h): Normal insulin action with EGP partially suppressed
    Phase 2 (2h-DIA): Insulin + ceiling — glucose drop limited
    Phase 3 (>DIA): EGP recovery at (1-ceiling) × base_egp rate
    """
    t_min = horizon_h * 60
    frac_delivered = 1 - insulin_kernel(t_min)

    # Pure insulin effect (demand-only)
    insulin_effect = dose * isf * frac_delivered

    # EGP counterforce: starts after ~1h, ramps up
    # At full ceiling, EGP provides (1-ceiling) × base_egp back
    if horizon_h <= 1.0:
        # Phase 1: minimal EGP contribution
        egp_effect = 0
    elif horizon_h <= DIA_H:
        # Phase 2: EGP recovery ramps — proportional to time past 1h
        hours_past_1 = horizon_h - 1.0
        # Recovery limited by ceiling: insulin can only suppress ceiling% of EGP
        # So (1-ceiling)% of EGP continues producing glucose
        egp_effect = (1 - ceiling) * base_egp * hours_past_1
    else:
        # Phase 3: full EGP recovery (insulin wearing off)
        hours_ceiling = DIA_H - 1.0  # hours of ceiling-limited phase
        hours_recovery = horizon_h - DIA_H
        egp_ceiling = (1 - ceiling) * base_egp * hours_ceiling
        egp_recovery = base_egp * hours_recovery  # full EGP now
        egp_effect = egp_ceiling + egp_recovery

    predicted = pre_bg - insulin_effect + egp_effect
    return predicted


def main():
    print("=" * 70)
    print("EXP-2658: Extended Prediction Horizon with Ceiling Model")
    print("=" * 70)

    df = pd.read_parquet(GRID)

    # Load per-patient ceiling from EXP-2656
    ceilings = {}
    if CEILING_FILE.exists():
        ceiling_data = json.loads(CEILING_FILE.read_text())
        for pid, p in ceiling_data.items():
            ceilings[pid] = p.get("fitted_ceiling", DEFAULT_CEILING)

    results = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()

        if "iob" not in pdf.columns or pdf["iob"].isna().all():
            continue

        isf = float(pdf["scheduled_isf"].dropna().median())
        ceiling = ceilings.get(pid, DEFAULT_CEILING)

        corrections = find_corrections(pdf)
        if len(corrections) < 5:
            tag = "[ODC]" if pid.startswith("odc") else "[NS] "
            print(f"\n  {tag} {pid}: {len(corrections)} corrections (insufficient)")
            continue

        # Predict at each horizon with both models
        horizons = ["2h", "4h", "6h", "8h"]
        horizon_hours = {"2h": 2.0, "4h": 4.0, "6h": 6.0, "8h": 8.0}

        errors = {h: {"linear": [], "3phase": [], "3phase_pop": []} for h in horizons}

        for corr in corrections:
            dose = corr["dose"]
            pre_bg = corr["pre_bg"]

            for h in horizons:
                if h not in corr["actual"]:
                    continue

                actual = corr["actual"][h]
                h_val = horizon_hours[h]

                # Linear prediction
                pred_linear = predict_linear(pre_bg, dose, isf, h_val)
                # 3-phase with per-patient ceiling
                pred_3phase = predict_3phase(pre_bg, dose, isf, ceiling, BASE_EGP, h_val)
                # 3-phase with population ceiling (30%)
                pred_3phase_pop = predict_3phase(pre_bg, dose, isf, DEFAULT_CEILING, BASE_EGP, h_val)

                errors[h]["linear"].append((actual - pred_linear) ** 2)
                errors[h]["3phase"].append((actual - pred_3phase) ** 2)
                errors[h]["3phase_pop"].append((actual - pred_3phase_pop) ** 2)

        # Compute RMSE at each horizon
        rmse = {}
        for h in horizons:
            if not errors[h]["linear"]:
                continue
            rmse[h] = {
                "linear": float(np.sqrt(np.mean(errors[h]["linear"]))),
                "3phase": float(np.sqrt(np.mean(errors[h]["3phase"]))),
                "3phase_pop": float(np.sqrt(np.mean(errors[h]["3phase_pop"]))),
                "n": len(errors[h]["linear"]),
            }

        if not rmse:
            continue

        tag = "[ODC]" if pid.startswith("odc") else "[NS] "
        print(f"\n  {tag} {pid} ({len(corrections)} corrections, ISF={isf:.0f}, ceiling={ceiling:.0%}):")
        for h in horizons:
            if h not in rmse:
                continue
            r = rmse[h]
            imp = (r["linear"] - r["3phase"]) / r["linear"] * 100
            imp_pop = (r["linear"] - r["3phase_pop"]) / r["linear"] * 100
            print(f"    {h}: Linear={r['linear']:.0f}, 3Phase={r['3phase']:.0f} "
                  f"({imp:+.0f}%), Pop={r['3phase_pop']:.0f} ({imp_pop:+.0f}%), N={r['n']}")

        results[pid] = {
            "n_corrections": len(corrections),
            "scheduled_isf": float(isf),
            "fitted_ceiling": float(ceiling),
            "rmse": rmse,
        }

    # Hypothesis testing
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_results = {p: r for p, r in results.items() if "4h" in r.get("rmse", {})}

    # H1: 3-phase RMSE < linear at 4h by ≥20%
    improvements_4h = []
    for pid, r in patients_with_results.items():
        rm = r["rmse"]["4h"]
        imp = (rm["linear"] - rm["3phase"]) / rm["linear"]
        improvements_4h.append(imp)
    h1_count = sum(1 for i in improvements_4h if i >= 0.20)
    print(f"\n  H1: 3-phase RMSE ≥20% better at 4h")
    imps_str = [f'{i:+.0%}' for i in improvements_4h]
    print(f"      {h1_count}/{len(improvements_4h)} patients")
    print(f"      Improvements: {imps_str}")
    print(f"      → {'PASS' if h1_count >= len(improvements_4h) * 0.5 else 'FAIL'}")

    # H2: 3-phase RMSE < linear at 6h by ≥30%
    patients_6h = {p: r for p, r in results.items() if "6h" in r.get("rmse", {})}
    improvements_6h = []
    for pid, r in patients_6h.items():
        rm = r["rmse"]["6h"]
        imp = (rm["linear"] - rm["3phase"]) / rm["linear"]
        improvements_6h.append(imp)
    h2_count = sum(1 for i in improvements_6h if i >= 0.30)
    imps_6h_str = [f'{i:+.0%}' for i in improvements_6h]
    print(f"\n  H2: 3-phase RMSE ≥30% better at 6h")
    print(f"      {h2_count}/{len(improvements_6h)} patients")
    print(f"      Improvements: {imps_6h_str}")
    print(f"      → {'PASS' if h2_count >= len(improvements_6h) * 0.5 else 'FAIL'}")

    # H3: Phase 3 (recovery) reduces 6-8h RMSE by ≥15%
    # Compare 3-phase (has recovery) vs linear (no recovery) at 8h
    patients_8h = {p: r for p, r in results.items() if "8h" in r.get("rmse", {})}
    improvements_8h = []
    for pid, r in patients_8h.items():
        rm = r["rmse"]["8h"]
        imp = (rm["linear"] - rm["3phase"]) / rm["linear"]
        improvements_8h.append(imp)
    h3_count = sum(1 for i in improvements_8h if i >= 0.15)
    imps_8h_str = [f'{i:+.0%}' for i in improvements_8h]
    print(f"\n  H3: Recovery prediction reduces 8h RMSE ≥15%")
    print(f"      {h3_count}/{len(improvements_8h)} patients")
    print(f"      Improvements: {imps_8h_str}")
    print(f"      → {'PASS' if h3_count >= len(improvements_8h) * 0.5 else 'FAIL'}")

    # H4: Per-patient ceiling > population ceiling ≥5%
    personalization_gains = []
    for pid, r in patients_with_results.items():
        if "4h" in r["rmse"]:
            rm = r["rmse"]["4h"]
            gain = (rm["3phase_pop"] - rm["3phase"]) / rm["3phase_pop"]
            personalization_gains.append(gain)
    h4_count = sum(1 for g in personalization_gains if g >= 0.05)
    gains_str = [f'{g:+.0%}' for g in personalization_gains]
    print(f"\n  H4: Per-patient ceiling gains ≥5% over population")
    print(f"      {h4_count}/{len(personalization_gains)} patients")
    print(f"      Gains: {gains_str}")
    print(f"      → {'PASS' if h4_count >= len(personalization_gains) * 0.5 else 'FAIL'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {OUT}")


if __name__ == "__main__":
    main()
