#!/usr/bin/env python3
"""EXP-2664: Circadian Demand-Phase ISF Profiling

EXP-2652 showed 2-9× circadian variation in APPARENT ISF. EXP-2663 showed
demand ISF is dose-INDEPENDENT (|r|=0.156). This experiment asks:
does demand ISF have circadian variation?

WHY THIS MATTERS:
  - If demand ISF varies by time-of-day → circadian ISF schedules needed
  - If demand ISF is circadian-FLAT → single constant ISF per patient
  - Since demand ISF is dose-independent (EXP-2663), any circadian variation
    reflects genuine physiology (insulin sensitivity rhythm), not dose confounding

PHYSIOLOGICAL HYPOTHESIS:
  Insulin sensitivity IS circadian (well-established: cortisol, growth hormone,
  dawn phenomenon). The question is magnitude: does demand-phase ISF capture
  it, or was apparent ISF's circadian variation mostly EGP-driven?

HYPOTHESES:
  H1: Demand ISF has circadian variation (max/min ratio > 1.3) for ≥50% of patients
  H2: Circadian amplitude is SMALLER for demand than apparent ISF (EGP amplifies)
  H3: Circadian demand-ISF profile predicts 2h glucose better than flat demand ISF
  H4: Dawn block (04-08) has significantly different demand ISF than midday (12-16)
  H5: Day/night demand ISF split improves correction dosing recommendations

METHODOLOGY:
  1. Extract correction events with time-of-day (reuse EXP-2652 method)
  2. Bin into 4h blocks: 00-04, 04-08, 08-12, 12-16, 16-20, 20-24
  3. Compute demand ISF and apparent ISF per block
  4. Measure circadian amplitude for each ISF type
  5. Test prediction improvement: flat vs 2-block vs 6-block demand ISF
  6. Bootstrap CIs on per-block demand ISF medians

DATA: 19 patients, parquet grid, 5-min intervals
DEPENDS ON: EXP-2663 (dose-independence), EXP-2652 (circadian apparent)
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2664_circadian_demand_isf.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12

BLOCKS = [
    ("00-04", 0, 4),
    ("04-08", 4, 8),
    ("08-12", 8, 12),
    ("12-16", 12, 16),
    ("16-20", 16, 20),
    ("20-24", 20, 24),
]

DAY_BLOCKS = ["08-12", "12-16", "16-20"]
NIGHT_BLOCKS = ["20-24", "00-04", "04-08"]

MIN_EVENTS_BLOCK = 3
MIN_EVENTS_PATIENT = 15
N_BOOTSTRAP = 2000


def extract_correction_events(pdf):
    """Extract correction events with per-event demand and apparent ISF."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    hours = t.dt.hour.values
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

    carb_window = STEPS_PER_HOUR  # ±1h
    prior_window = 2 * STEPS_PER_HOUR
    post_window = 5 * STEPS_PER_HOUR
    demand_idx = 2 * STEPS_PER_HOUR  # 2h

    events = []
    for i in range(prior_window, len(pdf) - post_window):
        if bolus[i] < 0.5:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 120:
            continue

        cs = max(0, i - carb_window)
        ce = min(len(pdf), i + carb_window)
        if np.nansum(carbs[cs:ce]) > 2:
            continue

        if np.nansum(bolus[i - prior_window:i]) > 0.3:
            continue

        idx_2h = i + demand_idx
        if idx_2h >= len(glucose) or np.isnan(glucose[idx_2h]):
            continue

        # Find nadir in 1-5h
        search_start = i + STEPS_PER_HOUR
        search_end = min(i + post_window, len(glucose))
        search = glucose[search_start:search_end]
        valid_mask = ~np.isnan(search)
        if valid_mask.sum() < 6:
            continue

        nadir_bg = float(np.nanmin(search))
        nadir_rel = np.nanargmin(search)
        nadir_time_h = float(STEPS_PER_HOUR + nadir_rel) / STEPS_PER_HOUR
        total_drop = float(glucose[i]) - nadir_bg

        if total_drop < 10:
            continue

        pre_bg = float(glucose[i])
        dose = float(bolus[i])
        drop_2h = pre_bg - float(glucose[idx_2h])
        demand_isf = drop_2h / dose
        apparent_isf = total_drop / dose

        hour = int(hours[i])
        block = None
        for bname, bstart, bend in BLOCKS:
            if bstart <= hour < bend:
                block = bname
                break

        events.append({
            "hour": hour,
            "block": block,
            "pre_bg": pre_bg,
            "dose": dose,
            "drop_2h": drop_2h,
            "total_drop": total_drop,
            "bg_2h": float(glucose[idx_2h]),
            "nadir_time_h": nadir_time_h,
            "demand_isf": demand_isf,
            "apparent_isf": apparent_isf,
        })

    return events


def bootstrap_block_isf(isf_values, n_boot=N_BOOTSTRAP):
    """Bootstrap 95% CI on median ISF for a block."""
    n = len(isf_values)
    if n < MIN_EVENTS_BLOCK:
        return None
    rng = np.random.default_rng(42)
    medians = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        medians.append(float(np.median(isf_values[idx])))
    medians = np.array(medians)
    return {
        "median": round(float(np.median(medians)), 1),
        "ci_low": round(float(np.percentile(medians, 2.5)), 1),
        "ci_high": round(float(np.percentile(medians, 97.5)), 1),
    }


def analyze_patient(pid, events):
    """Full circadian analysis for one patient, comparing demand vs apparent."""
    edf = pd.DataFrame(events)
    n = len(events)

    # Global medians
    global_demand = float(edf["demand_isf"].median())
    global_apparent = float(edf["apparent_isf"].median())

    # Per-block analysis
    blocks = {}
    for bname, _, _ in BLOCKS:
        bdf = edf[edf["block"] == bname]
        bn = len(bdf)

        block_info = {"n": bn}
        if bn >= MIN_EVENTS_BLOCK:
            d_isf = float(bdf["demand_isf"].median())
            a_isf = float(bdf["apparent_isf"].median())
            block_info.update({
                "demand_isf": round(d_isf, 1),
                "apparent_isf": round(a_isf, 1),
                "demand_pct_of_global": round(d_isf / global_demand * 100, 0) if global_demand != 0 else None,
                "apparent_pct_of_global": round(a_isf / global_apparent * 100, 0) if global_apparent > 0 else None,
                "inflation_ratio": round(a_isf / d_isf, 2) if d_isf > 0 else None,
            })
            # Bootstrap CIs
            d_boot = bootstrap_block_isf(bdf["demand_isf"].values)
            a_boot = bootstrap_block_isf(bdf["apparent_isf"].values)
            if d_boot:
                block_info["demand_bootstrap"] = d_boot
            if a_boot:
                block_info["apparent_bootstrap"] = a_boot
        blocks[bname] = block_info

    # Circadian amplitude: max/min ratio across blocks with data
    valid_demand = [b["demand_isf"] for b in blocks.values()
                    if b.get("demand_isf") is not None and b["n"] >= MIN_EVENTS_BLOCK]
    valid_apparent = [b["apparent_isf"] for b in blocks.values()
                      if b.get("apparent_isf") is not None and b["n"] >= MIN_EVENTS_BLOCK]

    demand_amplitude = (max(valid_demand) / min(valid_demand)
                        if len(valid_demand) >= 2 and min(valid_demand) > 0
                        else 1.0)
    apparent_amplitude = (max(valid_apparent) / min(valid_apparent)
                          if len(valid_apparent) >= 2 and min(valid_apparent) > 0
                          else 1.0)

    # Day vs night
    day_events = edf[edf["block"].isin(DAY_BLOCKS)]
    night_events = edf[edf["block"].isin(NIGHT_BLOCKS)]

    day_demand = float(day_events["demand_isf"].median()) if len(day_events) >= 5 else None
    night_demand = float(night_events["demand_isf"].median()) if len(night_events) >= 5 else None
    day_apparent = float(day_events["apparent_isf"].median()) if len(day_events) >= 5 else None
    night_apparent = float(night_events["apparent_isf"].median()) if len(night_events) >= 5 else None

    day_night_ratio_demand = (day_demand / night_demand
                              if day_demand and night_demand and night_demand > 0
                              else None)
    day_night_ratio_apparent = (day_apparent / night_apparent
                                if day_apparent and night_apparent and night_apparent > 0
                                else None)

    # Dawn vs midday comparison (H4)
    dawn_block = blocks.get("04-08", {})
    midday_block = blocks.get("12-16", {})
    dawn_vs_midday = None
    if (dawn_block.get("demand_isf") is not None and
        midday_block.get("demand_isf") is not None and
        dawn_block["n"] >= MIN_EVENTS_BLOCK and
        midday_block["n"] >= MIN_EVENTS_BLOCK):
        # Mann-Whitney U test for dawn vs midday demand ISF
        dawn_events_df = edf[edf["block"] == "04-08"]["demand_isf"].values
        midday_events_df = edf[edf["block"] == "12-16"]["demand_isf"].values
        if len(dawn_events_df) >= 3 and len(midday_events_df) >= 3:
            u_stat, u_p = stats.mannwhitneyu(dawn_events_df, midday_events_df,
                                              alternative="two-sided")
            dawn_vs_midday = {
                "dawn_demand_isf": dawn_block["demand_isf"],
                "midday_demand_isf": midday_block["demand_isf"],
                "ratio": round(dawn_block["demand_isf"] / midday_block["demand_isf"], 2)
                    if midday_block["demand_isf"] > 0 else None,
                "u_stat": float(u_stat),
                "p_value": float(u_p),
                "significant": float(u_p) < 0.05,
            }

    # ── Prediction accuracy comparison ───────────────────────────
    valid = edf.dropna(subset=["bg_2h"])
    if len(valid) < MIN_EVENTS_PATIENT:
        return None

    # Model 1: flat demand ISF
    pred_flat = valid["pre_bg"] - valid["dose"] * global_demand
    rmse_flat = float(np.sqrt(np.mean((valid["bg_2h"] - pred_flat) ** 2)))

    # Model 2: day/night demand ISF
    rmse_daynight = rmse_flat
    if day_demand is not None and night_demand is not None:
        pred_dn = valid.apply(
            lambda r: r["pre_bg"] - r["dose"] * (
                day_demand if r["block"] in DAY_BLOCKS else night_demand
            ), axis=1)
        rmse_daynight = float(np.sqrt(np.mean((valid["bg_2h"] - pred_dn) ** 2)))

    # Model 3: per-block demand ISF
    def _block_demand(block):
        bi = blocks.get(block, {})
        return bi.get("demand_isf", global_demand) if bi.get("n", 0) >= MIN_EVENTS_BLOCK else global_demand

    pred_block = valid.apply(
        lambda r: r["pre_bg"] - r["dose"] * _block_demand(r["block"]),
        axis=1)
    rmse_block = float(np.sqrt(np.mean((valid["bg_2h"] - pred_block) ** 2)))

    # Model 4: flat apparent ISF (for comparison)
    pred_flat_app = valid["pre_bg"] - valid["dose"] * global_apparent
    rmse_flat_apparent = float(np.sqrt(np.mean((valid["bg_2h"] - pred_flat_app) ** 2)))

    improvement_dn = (rmse_flat - rmse_daynight) / rmse_flat * 100
    improvement_block = (rmse_flat - rmse_block) / rmse_flat * 100

    return {
        "n_events": n,
        "global_demand_isf": round(global_demand, 1),
        "global_apparent_isf": round(global_apparent, 1),
        "inflation_ratio": round(global_apparent / global_demand, 2) if global_demand > 0 else None,
        "blocks": blocks,
        "circadian_amplitude": {
            "demand_max_min_ratio": round(float(demand_amplitude), 2),
            "apparent_max_min_ratio": round(float(apparent_amplitude), 2),
            "demand_smaller": float(demand_amplitude) < float(apparent_amplitude),
        },
        "day_night": {
            "day_demand": round(day_demand, 1) if day_demand else None,
            "night_demand": round(night_demand, 1) if night_demand else None,
            "day_apparent": round(day_apparent, 1) if day_apparent else None,
            "night_apparent": round(night_apparent, 1) if night_apparent else None,
            "ratio_demand": round(day_night_ratio_demand, 2) if day_night_ratio_demand else None,
            "ratio_apparent": round(day_night_ratio_apparent, 2) if day_night_ratio_apparent else None,
        },
        "dawn_vs_midday": dawn_vs_midday,
        "prediction": {
            "rmse_flat_demand": round(rmse_flat, 1),
            "rmse_daynight_demand": round(rmse_daynight, 1),
            "rmse_perblock_demand": round(rmse_block, 1),
            "rmse_flat_apparent": round(rmse_flat_apparent, 1),
            "improvement_daynight_pct": round(improvement_dn, 1),
            "improvement_perblock_pct": round(improvement_block, 1),
        },
    }


def cross_patient_circadian(all_results):
    """Cross-patient analysis of circadian patterns."""
    # Aggregate per-block demand ISFs across patients (normalized to each patient's global)
    block_ratios = defaultdict(list)
    for pid, r in all_results.items():
        gd = r["global_demand_isf"]
        if gd <= 0:
            continue
        for bname in [b[0] for b in BLOCKS]:
            bi = r["blocks"].get(bname, {})
            if bi.get("demand_isf") is not None and bi["n"] >= MIN_EVENTS_BLOCK:
                block_ratios[bname].append(bi["demand_isf"] / gd)

    # Cross-patient median circadian profile (normalized)
    profile = {}
    for bname in [b[0] for b in BLOCKS]:
        ratios = block_ratios.get(bname, [])
        if len(ratios) >= 3:
            profile[bname] = {
                "n_patients": len(ratios),
                "median_ratio": round(float(np.median(ratios)), 3),
                "iqr": [round(float(np.percentile(ratios, 25)), 3),
                        round(float(np.percentile(ratios, 75)), 3)],
            }

    return {
        "normalized_circadian_profile": profile,
        "most_sensitive_block": min(profile.items(), key=lambda x: x[1]["median_ratio"])[0]
            if profile else None,
        "least_sensitive_block": max(profile.items(), key=lambda x: x[1]["median_ratio"])[0]
            if profile else None,
    }


def test_hypotheses(all_results, cross):
    """Evaluate all 5 hypotheses."""
    patients = list(all_results.values())
    hypotheses = {}

    # H1: demand ISF circadian variation > 1.3 for ≥50%
    n_var = sum(1 for r in patients if r["circadian_amplitude"]["demand_max_min_ratio"] > 1.3)
    hypotheses["H1_circadian_exists"] = {
        "description": "Demand ISF has circadian variation (max/min > 1.3) for ≥50% of patients",
        "n_varied": n_var,
        "n_total": len(patients),
        "fraction": round(n_var / len(patients), 2) if patients else None,
        "amplitudes": sorted([round(r["circadian_amplitude"]["demand_max_min_ratio"], 2)
                              for r in patients], reverse=True),
        "pass": n_var >= len(patients) / 2,
    }

    # H2: demand circadian amplitude < apparent circadian amplitude
    n_smaller = sum(1 for r in patients if r["circadian_amplitude"]["demand_smaller"])
    hypotheses["H2_demand_amplitude_smaller"] = {
        "description": "Demand ISF circadian amplitude is smaller than apparent (EGP amplifies)",
        "n_smaller": n_smaller,
        "n_total": len(patients),
        "fraction": round(n_smaller / len(patients), 2) if patients else None,
        "pass": n_smaller > len(patients) / 2,
    }

    # H3: circadian demand ISF improves 2h prediction (any level)
    n_improved = sum(1 for r in patients if r["prediction"]["improvement_perblock_pct"] > 0)
    improvements = [r["prediction"]["improvement_perblock_pct"] for r in patients]
    hypotheses["H3_prediction_improvement"] = {
        "description": "Circadian demand ISF profile predicts 2h glucose better than flat",
        "n_improved": n_improved,
        "n_total": len(patients),
        "fraction": round(n_improved / len(patients), 2) if patients else None,
        "mean_improvement_pct": round(float(np.mean(improvements)), 1),
        "median_improvement_pct": round(float(np.median(improvements)), 1),
        "pass": n_improved > len(patients) / 2,
    }

    # H4: dawn (04-08) significantly different from midday (12-16)
    n_sig = sum(1 for r in patients
                if r.get("dawn_vs_midday") and r["dawn_vs_midday"].get("significant"))
    n_tested = sum(1 for r in patients if r.get("dawn_vs_midday"))
    hypotheses["H4_dawn_different"] = {
        "description": "Dawn block has significantly different demand ISF than midday",
        "n_significant": n_sig,
        "n_tested": n_tested,
        "fraction": round(n_sig / n_tested, 2) if n_tested > 0 else None,
        "pass": n_sig >= n_tested / 2 if n_tested > 0 else False,
    }

    # H5: day/night split improves dosing
    n_dn_improved = sum(1 for r in patients if r["prediction"]["improvement_daynight_pct"] > 2)
    dn_improvements = [r["prediction"]["improvement_daynight_pct"] for r in patients]
    hypotheses["H5_daynight_split"] = {
        "description": "Day/night demand ISF split improves correction dosing (>2% RMSE reduction)",
        "n_improved": n_dn_improved,
        "n_total": len(patients),
        "fraction": round(n_dn_improved / len(patients), 2) if patients else None,
        "mean_improvement_pct": round(float(np.mean(dn_improvements)), 1),
        "pass": n_dn_improved > len(patients) / 2,
    }

    return hypotheses


def main():
    print("=" * 70)
    print("EXP-2664: Circadian Demand-Phase ISF Profiling")
    print("=" * 70)

    if not PARQUET.exists():
        print(f"ERROR: {PARQUET} not found")
        sys.exit(1)

    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df):,} rows")

    all_results = {}

    print("\n--- Per-Patient Circadian Analysis ---")
    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            continue

        events = extract_correction_events(pdf)
        result = analyze_patient(pid, events)
        if result is None:
            print(f"  {pid}: insufficient data ({len(events)} events)")
            continue

        all_results[pid] = result
        ca = result["circadian_amplitude"]
        pr = result["prediction"]
        dn = result["day_night"]

        print(f"\n  {pid} ({result['n_events']} events):")
        print(f"    Global demand ISF: {result['global_demand_isf']:.0f}  "
              f"(apparent: {result['global_apparent_isf']:.0f}, "
              f"inflation: {result.get('inflation_ratio', '?')}×)")

        # Per-block demand ISF
        print("    Blocks (demand ISF): ", end="")
        for bname, _, _ in BLOCKS:
            bi = result["blocks"].get(bname, {})
            if bi.get("demand_isf") is not None and bi["n"] >= MIN_EVENTS_BLOCK:
                boot = bi.get("demand_bootstrap", {})
                ci = f" [{boot.get('ci_low','?')}-{boot.get('ci_high','?')}]" if boot else ""
                print(f"{bname}={bi['demand_isf']:.0f}{ci}({bi['n']})", end="  ")
            else:
                print(f"{bname}=—", end="  ")
        print()

        print(f"    Circadian amplitude: demand={ca['demand_max_min_ratio']:.2f}×  "
              f"apparent={ca['apparent_max_min_ratio']:.2f}×  "
              f"{'demand<apparent ✓' if ca['demand_smaller'] else 'demand≥apparent ✗'}")

        if dn.get("day_demand") and dn.get("night_demand"):
            print(f"    Day/night demand: {dn['day_demand']:.0f} / {dn['night_demand']:.0f} "
                  f"(ratio={dn.get('ratio_demand', '?')})")

        if result.get("dawn_vs_midday"):
            dvm = result["dawn_vs_midday"]
            sig = "***" if dvm["p_value"] < 0.001 else "**" if dvm["p_value"] < 0.01 else "*" if dvm["significant"] else "ns"
            print(f"    Dawn vs midday: {dvm['dawn_demand_isf']:.0f} vs {dvm['midday_demand_isf']:.0f} "
                  f"(ratio={dvm.get('ratio', '?')}, p={dvm['p_value']:.3f} {sig})")

        print(f"    RMSE: flat={pr['rmse_flat_demand']:.0f}, "
              f"day/night={pr['rmse_daynight_demand']:.0f} ({pr['improvement_daynight_pct']:+.1f}%), "
              f"per-block={pr['rmse_perblock_demand']:.0f} ({pr['improvement_perblock_pct']:+.1f}%)")

    # ── Cross-patient ────────────────────────────────────────────
    print("\n--- Cross-Patient Circadian Profile ---")
    cross = cross_patient_circadian(all_results)
    profile = cross.get("normalized_circadian_profile", {})
    print("  Normalized demand ISF (1.0 = patient mean):")
    for bname in [b[0] for b in BLOCKS]:
        bi = profile.get(bname, {})
        if bi:
            iqr = bi["iqr"]
            print(f"    {bname}: {bi['median_ratio']:.3f} [{iqr[0]:.3f} - {iqr[1]:.3f}] "
                  f"(n={bi['n_patients']} patients)")
    if cross.get("most_sensitive_block"):
        print(f"  Most insulin-sensitive (lowest ISF): {cross['most_sensitive_block']}")
        print(f"  Least insulin-sensitive (highest ISF): {cross['least_sensitive_block']}")

    # ── Hypothesis testing ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS RESULTS")
    print("=" * 70)
    hyp = test_hypotheses(all_results, cross)
    for hid, h in sorted(hyp.items()):
        status = "PASS ✓" if h["pass"] else "FAIL ✗"
        detail = ""
        if "fraction" in h and h["fraction"] is not None:
            detail = f" ({h['fraction']*100:.0f}%)"
        print(f"  {hid}: {status}{detail}")
        print(f"    {h['description']}")
        if "amplitudes" in h:
            print(f"    Amplitudes: {h['amplitudes']}")
        if "mean_improvement_pct" in h:
            print(f"    Mean improvement: {h['mean_improvement_pct']:+.1f}%")

    # ── Clinical interpretation ──────────────────────────────────
    print("\n" + "=" * 70)
    print("CLINICAL INTERPRETATION")
    print("=" * 70)

    amplitudes = [r["circadian_amplitude"]["demand_max_min_ratio"] for r in all_results.values()]
    mean_amp = np.mean(amplitudes)
    median_amp = np.median(amplitudes)

    # Use prediction improvement as the ground truth, not amplitude ratios.
    # High amplitude + negative prediction improvement = NOISE, not signal.
    mean_block_improvement = np.mean(block_improvements)
    mean_dn_improvement = np.mean(dn_improvements)

    if mean_block_improvement > 5:
        print("  Circadian demand ISF profiling IMPROVES prediction.")
        print("  → Consider day/night or per-block ISF schedules.")
    elif mean_block_improvement > 0:
        print("  Circadian demand ISF profiling has MARGINAL benefit.")
        print("  → Day/night split may help select patients; per-block is overkill.")
    else:
        print("  Circadian demand ISF profiling WORSENS prediction.")
        print("  → High max/min ratios reflect per-event NOISE, not circadian signal.")
        print("  → Demand ISF should be treated as a constant per patient (EXP-2663).")
        print("  → Apparent ISF's circadian variation (EXP-2652) is driven by EGP,")
        print("    not insulin sensitivity rhythm.")

    dn_improvements = [r["prediction"]["improvement_daynight_pct"] for r in all_results.values()]
    block_improvements = [r["prediction"]["improvement_perblock_pct"] for r in all_results.values()]
    print(f"\n  Mean prediction improvement from day/night split: {np.mean(dn_improvements):+.1f}%")
    print(f"  Mean prediction improvement from per-block profile: {np.mean(block_improvements):+.1f}%")

    # Compare apparent vs demand circadian amplitude
    demand_amps = [r["circadian_amplitude"]["demand_max_min_ratio"] for r in all_results.values()]
    apparent_amps = [r["circadian_amplitude"]["apparent_max_min_ratio"] for r in all_results.values()]
    print(f"\n  Circadian amplitudes:")
    print(f"    Demand ISF:   median={np.median(demand_amps):.2f}×, "
          f"range=[{min(demand_amps):.2f}-{max(demand_amps):.2f}]")
    print(f"    Apparent ISF: median={np.median(apparent_amps):.2f}×, "
          f"range=[{min(apparent_amps):.2f}-{max(apparent_amps):.2f}]")

    if np.median(demand_amps) < np.median(apparent_amps):
        ratio = np.median(apparent_amps) / np.median(demand_amps)
        print(f"    → EGP amplifies circadian variation by {ratio:.1f}×")
    else:
        print("    → Demand ISF has equal or greater circadian variation (unexpected)")

    # ── Save results ─────────────────────────────────────────────
    def convert(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"{type(obj)} not serializable")

    results = {
        "experiment": "EXP-2664",
        "title": "Circadian Demand-Phase ISF Profiling",
        "n_patients": len(all_results),
        "per_patient": all_results,
        "cross_patient": cross,
        "hypotheses": hyp,
        "summary": {
            "median_demand_amplitude": round(float(np.median(demand_amps)), 2),
            "median_apparent_amplitude": round(float(np.median(apparent_amps)), 2),
            "egp_amplification": round(float(np.median(apparent_amps) / np.median(demand_amps)), 2)
                if np.median(demand_amps) > 0 else None,
            "mean_improvement_daynight": round(float(np.mean(dn_improvements)), 1),
            "mean_improvement_perblock": round(float(np.mean(block_improvements)), 1),
            "recommendation": "constant_isf" if mean_block_improvement <= 0 else (
                "circadian_schedule" if mean_block_improvement > 5 else "daynight_only"),
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
