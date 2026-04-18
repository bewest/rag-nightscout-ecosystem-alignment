#!/usr/bin/env python3
"""EXP-2665: Nyquist-Aware Circadian Demand ISF

EXP-2664 used 4h time-of-day blocks — but insulin DIA ≈ 6h, so the
Nyquist minimum observation window is 2 × DIA = 12h. Corrections bleed
across 4h blocks, making block-level ISF estimates unreliable.

This experiment applies proper Nyquist constraints:
  1. Minimum block size = 12h (day 08-20, night 20-08)
  2. Prior bolus isolation ≥ 6h (full DIA clearance)
  3. Also test 8h blocks (marginal compliance) for comparison
  4. Compare: how many events survive strict isolation?

INSIGHT: The demand-phase measurement itself (0-2h) is short, but the
PRIOR insulin environment must be clean. With prior_bolus=2h, there's
still 4h of tail insulin from the prior dose affecting baseline IOB.
With prior_bolus=6h (= DIA), corrections are truly isolated.

HYPOTHESES:
  H1: Strict isolation (6h prior) yields different demand ISF than lax (2h)
  H2: 12h day/night split with strict isolation shows no circadian signal
  H3: 8h blocks with strict isolation show no circadian signal
  H4: Demand ISF is constant per patient (confirming EXP-2663 under strict conditions)

If H2/H3 pass → circadian profiling is definitively noise.
If H2/H3 fail → there IS a real circadian signal that lax filtering masked.
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
OUTFILE = RESULTS_DIR / "exp-2665_nyquist_circadian_isf.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12
DIA_H = 6.0

# Block definitions
BLOCKS_12H = [("day_08_20", 8, 20), ("night_20_08", 20, 8)]
BLOCKS_8H = [("00-08", 0, 8), ("08-16", 8, 16), ("16-24", 16, 24)]
BLOCKS_4H = [  # For comparison (sub-Nyquist)
    ("00-04", 0, 4), ("04-08", 4, 8), ("08-12", 8, 12),
    ("12-16", 12, 16), ("16-20", 16, 20), ("20-24", 20, 24),
]

N_BOOTSTRAP = 2000
MIN_EVENTS = 5


def in_block(hour, block_start, block_end):
    """Check if hour falls in block, handling midnight wraparound."""
    if block_start < block_end:
        return block_start <= hour < block_end
    else:  # wraps midnight (e.g., 20-08)
        return hour >= block_start or hour < block_end


def extract_corrections(pdf, prior_bolus_h=6.0, min_dose=0.5, min_pre_bg=120,
                        carb_window_h=1.0, demand_window_h=2.0):
    """Extract correction events with configurable prior-bolus isolation."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    hours = t.dt.hour.values
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

    carb_window = int(carb_window_h * STEPS_PER_HOUR)
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    demand_steps = int(demand_window_h * STEPS_PER_HOUR)
    nadir_start = STEPS_PER_HOUR  # 1h
    nadir_end = int(5.0 * STEPS_PER_HOUR)

    events = []
    for i in range(prior_window, len(pdf) - nadir_end):
        if bolus[i] < min_dose:
            continue
        if np.isnan(glucose[i]) or glucose[i] < min_pre_bg:
            continue

        # No carbs ± window
        cs = max(0, i - carb_window)
        ce = min(len(pdf), i + carb_window)
        if np.nansum(carbs[cs:ce]) > 2:
            continue

        # No prior bolus within prior_bolus_h (THE KEY NYQUIST FILTER)
        if np.nansum(bolus[i - prior_window:i]) > 0.3:
            continue

        # Need valid glucose at 2h
        idx_2h = i + demand_steps
        if idx_2h >= len(glucose) or np.isnan(glucose[idx_2h]):
            continue

        # Find nadir in 1-5h
        search = glucose[i + nadir_start:min(i + nadir_end, len(glucose))]
        valid_mask = ~np.isnan(search)
        if valid_mask.sum() < 6:
            continue

        nadir_bg = float(np.nanmin(search))
        total_drop = float(glucose[i]) - nadir_bg
        if total_drop < 10:
            continue

        pre_bg = float(glucose[i])
        dose = float(bolus[i])
        drop_2h = pre_bg - float(glucose[idx_2h])

        events.append({
            "hour": int(hours[i]),
            "pre_bg": pre_bg,
            "dose": dose,
            "drop_2h": drop_2h,
            "total_drop": total_drop,
            "demand_isf": drop_2h / dose,
            "apparent_isf": total_drop / dose,
        })

    return events


def bootstrap_median(values, n_boot=N_BOOTSTRAP):
    """Bootstrap 95% CI on median."""
    if len(values) < MIN_EVENTS:
        return None
    rng = np.random.default_rng(42)
    medians = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(values), size=len(values))
        medians.append(float(np.median(values[idx])))
    medians = np.array(medians)
    return {
        "median": round(float(np.median(medians)), 2),
        "ci_low": round(float(np.percentile(medians, 2.5)), 2),
        "ci_high": round(float(np.percentile(medians, 97.5)), 2),
    }


def analyze_blocks(events, block_defs, label):
    """Analyze demand ISF by time-of-day blocks."""
    if not events:
        return None

    edf = pd.DataFrame(events)
    global_demand = float(edf["demand_isf"].median())
    global_apparent = float(edf["apparent_isf"].median())

    blocks = {}
    for bname, bstart, bend in block_defs:
        mask = edf["hour"].apply(lambda h: in_block(h, bstart, bend))
        bdf = edf[mask]
        bn = len(bdf)

        block_info = {"n": bn}
        if bn >= MIN_EVENTS:
            d_vals = bdf["demand_isf"].values
            a_vals = bdf["apparent_isf"].values
            block_info.update({
                "demand_isf": round(float(np.median(d_vals)), 1),
                "apparent_isf": round(float(np.median(a_vals)), 1),
                "demand_bootstrap": bootstrap_median(d_vals),
                "apparent_bootstrap": bootstrap_median(a_vals),
            })
        blocks[bname] = block_info

    # Circadian amplitude from blocks with data
    valid_demand = [b["demand_isf"] for b in blocks.values()
                    if b.get("demand_isf") is not None and b["n"] >= MIN_EVENTS]
    amplitude = (max(valid_demand) / min(valid_demand)
                 if len(valid_demand) >= 2 and min(valid_demand) > 0
                 else None)

    # Prediction: flat vs block-specific demand ISF
    valid = edf.copy()
    pred_flat = valid["pre_bg"] - valid["dose"] * global_demand
    rmse_flat = float(np.sqrt(np.mean((valid["drop_2h"] - valid["dose"] * global_demand) ** 2)))

    # Block-specific prediction
    def _get_block_isf(hour):
        for bname, bstart, bend in block_defs:
            if in_block(hour, bstart, bend):
                bi = blocks.get(bname, {})
                return bi.get("demand_isf", global_demand) if bi.get("n", 0) >= MIN_EVENTS else global_demand
        return global_demand

    valid["block_demand"] = valid["hour"].apply(_get_block_isf)
    rmse_block = float(np.sqrt(np.mean(
        (valid["drop_2h"] - valid["dose"] * valid["block_demand"]) ** 2)))

    improvement = (rmse_flat - rmse_block) / rmse_flat * 100 if rmse_flat > 0 else 0

    # Kruskal-Wallis test across blocks (non-parametric ANOVA)
    block_groups = []
    for bname, bstart, bend in block_defs:
        mask = edf["hour"].apply(lambda h: in_block(h, bstart, bend))
        vals = edf.loc[mask, "demand_isf"].values
        if len(vals) >= MIN_EVENTS:
            block_groups.append(vals)

    kw_stat, kw_p = (None, None)
    if len(block_groups) >= 2:
        try:
            kw_stat, kw_p = stats.kruskal(*block_groups)
        except ValueError:
            pass

    return {
        "label": label,
        "n_events": len(events),
        "n_blocks": len(block_defs),
        "global_demand_isf": round(global_demand, 1),
        "blocks": blocks,
        "amplitude": round(float(amplitude), 2) if amplitude else None,
        "rmse_flat": round(rmse_flat, 1),
        "rmse_block": round(rmse_block, 1),
        "improvement_pct": round(improvement, 1),
        "kruskal_wallis": {
            "statistic": round(float(kw_stat), 3) if kw_stat is not None else None,
            "p_value": float(kw_p) if kw_p is not None else None,
            "significant": float(kw_p) < 0.05 if kw_p is not None else False,
        },
    }


def main():
    print("=" * 70)
    print("EXP-2665: Nyquist-Aware Circadian Demand ISF")
    print("=" * 70)
    print(f"DIA = {DIA_H}h → Nyquist min block = {2*DIA_H}h")

    if not PARQUET.exists():
        print(f"ERROR: {PARQUET} not found")
        sys.exit(1)

    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df):,} rows")

    all_results = {}

    for pid in ALL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            continue

        # Extract with BOTH isolation levels
        events_lax = extract_corrections(pdf, prior_bolus_h=2.0)
        events_strict = extract_corrections(pdf, prior_bolus_h=DIA_H)

        if len(events_strict) < MIN_EVENTS:
            print(f"\n  {pid}: strict={len(events_strict)} events (skip), lax={len(events_lax)}")
            continue

        print(f"\n  {pid}: strict={len(events_strict)} events, lax={len(events_lax)} "
              f"(kept {len(events_strict)/max(len(events_lax),1)*100:.0f}%)")

        # Global demand ISF comparison: strict vs lax
        strict_demand = np.median([e["demand_isf"] for e in events_strict])
        lax_demand = np.median([e["demand_isf"] for e in events_lax])
        isf_shift = (strict_demand - lax_demand) / abs(lax_demand) * 100 if lax_demand != 0 else 0
        print(f"    Demand ISF: strict={strict_demand:.1f}, lax={lax_demand:.1f} "
              f"(shift={isf_shift:+.0f}%)")

        # Analyze with all three block sizes
        result = {
            "n_lax": len(events_lax),
            "n_strict": len(events_strict),
            "retention_pct": round(len(events_strict) / max(len(events_lax), 1) * 100, 0),
            "demand_isf_lax": round(float(lax_demand), 1),
            "demand_isf_strict": round(float(strict_demand), 1),
            "isf_shift_pct": round(float(isf_shift), 1),
        }

        for block_defs, label in [
            (BLOCKS_12H, "12h (Nyquist-compliant)"),
            (BLOCKS_8H, "8h (marginal)"),
            (BLOCKS_4H, "4h (sub-Nyquist)"),
        ]:
            analysis = analyze_blocks(events_strict, block_defs, label)
            key = f"blocks_{label.split('h')[0]}h"
            result[key] = analysis

            if analysis:
                kw = analysis["kruskal_wallis"]
                sig = "***" if kw.get("p_value") and kw["p_value"] < 0.001 else \
                      "**" if kw.get("p_value") and kw["p_value"] < 0.01 else \
                      "*" if kw.get("significant") else "ns"
                print(f"    {label}: improvement={analysis['improvement_pct']:+.1f}%, "
                      f"KW p={kw.get('p_value', 'N/A'):.3f} {sig}" if kw.get("p_value") else
                      f"    {label}: improvement={analysis['improvement_pct']:+.1f}%, KW=N/A")

                # Print block ISFs
                for bname, bi in analysis["blocks"].items():
                    if bi.get("demand_isf") is not None:
                        boot = bi.get("demand_bootstrap", {})
                        ci = f" [{boot.get('ci_low','?')}-{boot.get('ci_high','?')}]" if boot else ""
                        print(f"      {bname}: demand={bi['demand_isf']:.0f}{ci} (n={bi['n']})")

        all_results[pid] = result

    # ── Cross-patient summary ────────────────────────────────────
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    patients = list(all_results.values())
    if not patients:
        print("No patients with sufficient data")
        return

    # Event retention
    retentions = [r["retention_pct"] for r in patients]
    print(f"\n  Strict isolation retention: {np.median(retentions):.0f}% median "
          f"(range {min(retentions):.0f}-{max(retentions):.0f}%)")

    # ISF shift
    shifts = [r["isf_shift_pct"] for r in patients]
    print(f"  ISF shift (strict vs lax): {np.median(shifts):+.1f}% median "
          f"(range {min(shifts):+.0f} to {max(shifts):+.0f}%)")

    # Per block-size: how many patients have significant KW?
    for bsize in ["12h", "8h", "4h"]:
        key = f"blocks_{bsize}"
        n_sig = 0
        n_tested = 0
        improvements = []
        for r in patients:
            analysis = r.get(key)
            if analysis and analysis.get("kruskal_wallis", {}).get("p_value") is not None:
                n_tested += 1
                if analysis["kruskal_wallis"]["significant"]:
                    n_sig += 1
                improvements.append(analysis["improvement_pct"])

        if n_tested > 0:
            print(f"\n  {bsize} blocks:")
            print(f"    KW significant: {n_sig}/{n_tested} patients")
            print(f"    Mean prediction improvement: {np.mean(improvements):+.1f}%")
            print(f"    Median prediction improvement: {np.median(improvements):+.1f}%")

    # ── Hypothesis testing ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS RESULTS")
    print("=" * 70)

    # H1: strict isolation changes ISF
    shift_significant = sum(1 for s in shifts if abs(s) > 15)
    h1 = shift_significant > len(shifts) / 2
    print(f"\n  H1: Strict isolation yields different demand ISF (>15% shift)")
    print(f"      {shift_significant}/{len(shifts)} patients  → {'PASS' if h1 else 'FAIL'}")

    # H2: 12h blocks show no circadian signal
    n_sig_12h = sum(1 for r in patients
                    if r.get("blocks_12h", {}).get("kruskal_wallis", {}).get("significant"))
    n_tested_12h = sum(1 for r in patients
                       if r.get("blocks_12h", {}).get("kruskal_wallis", {}).get("p_value") is not None)
    h2 = n_sig_12h <= n_tested_12h / 2
    print(f"\n  H2: 12h day/night split shows no circadian signal")
    print(f"      Significant: {n_sig_12h}/{n_tested_12h}  → {'PASS' if h2 else 'FAIL'}")

    # H3: 8h blocks show no circadian signal
    n_sig_8h = sum(1 for r in patients
                   if r.get("blocks_8h", {}).get("kruskal_wallis", {}).get("significant"))
    n_tested_8h = sum(1 for r in patients
                      if r.get("blocks_8h", {}).get("kruskal_wallis", {}).get("p_value") is not None)
    h3 = n_sig_8h <= n_tested_8h / 2
    print(f"\n  H3: 8h blocks show no circadian signal")
    print(f"      Significant: {n_sig_8h}/{n_tested_8h}  → {'PASS' if h3 else 'FAIL'}")

    # H4: demand ISF constant per patient
    # Check if ANY block size shows consistent improvement
    any_helpful = False
    for bsize in ["12h", "8h", "4h"]:
        key = f"blocks_{bsize}"
        imps = [r[key]["improvement_pct"] for r in patients
                if r.get(key) and r[key].get("improvement_pct") is not None]
        if imps and np.mean(imps) > 3:
            any_helpful = True
    h4 = not any_helpful
    print(f"\n  H4: Demand ISF is constant per patient (no block size helps >3%)")
    print(f"      → {'PASS' if h4 else 'FAIL'}")

    # ── Clinical interpretation ──────────────────────────────────
    print("\n" + "=" * 70)
    print("CLINICAL INTERPRETATION")
    print("=" * 70)

    if h2 and h3 and h4:
        print("  CONFIRMED: Demand ISF has no detectable circadian variation.")
        print("  This holds at ALL Nyquist-appropriate window sizes (12h, 8h).")
        print("  → Use a single constant demand ISF per patient.")
        print("  → Apparent ISF circadian variation (EXP-2652) was EGP-driven.")
    elif h2 and h3:
        print("  No circadian signal detected, but strict isolation changes ISF.")
        print("  → Investigate whether prior insulin contamination affects demand ISF.")
    else:
        print("  Circadian signal detected at Nyquist-appropriate windows.")
        print("  → Consider circadian demand ISF scheduling.")

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
        "experiment": "EXP-2665",
        "title": "Nyquist-Aware Circadian Demand ISF",
        "dia_h": DIA_H,
        "nyquist_min_block_h": 2 * DIA_H,
        "n_patients": len(all_results),
        "per_patient": all_results,
        "summary": {
            "median_retention_pct": round(float(np.median(retentions)), 0),
            "median_isf_shift_pct": round(float(np.median(shifts)), 1),
            "conclusion": "constant_demand_isf" if (h2 and h3 and h4) else "circadian_detected",
        },
        "hypotheses": {
            "H1_strict_changes_isf": h1,
            "H2_12h_no_signal": h2,
            "H3_8h_no_signal": h3,
            "H4_constant_per_patient": h4,
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
