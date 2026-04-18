#!/usr/bin/env python3
"""EXP-2652: Circadian ISF/Basal Profiling.

Builds on F6 (per-patient EGP recovery varies 4.7-44.8 mg/dL/hr) and the
finding that patient i has a dramatic day/night ISF split (+37 day, -4.5 night).

INSIGHT: Most AID users configure a single ISF and single basal rate, but
EGP and insulin sensitivity both have strong circadian patterns. The dawn
phenomenon is well-known, but our data can reveal the full circadian profile
for each patient.

METHOD:
  1. For each patient, bin correction events into 4h time blocks (6 blocks/day)
  2. Compute per-block apparent ISF from corrections
  3. Bin overnight drift by 4h blocks for basal profiling
  4. Compare: single-value vs 2-block (day/night) vs 6-block profiles
  5. Measure: which profiling reduces glucose variance?

HYPOTHESES:
H1: ≥50% of patients have ≥30% ISF variation across time-of-day blocks
H2: 2-block (day/night) profiles reduce correction RMSE ≥10% vs single-value
H3: Dawn block (04-08h) has the lowest effective ISF (most aggressive correction needed)
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2652_circadian_profiling.json"

STEPS_PER_HOUR = 12

# Isolation tiers (EXP-2666: 6h optimal for DIA=6h Nyquist compliance)
_STRICT_PRIOR_BOLUS_H = 6.0
_LAX_PRIOR_BOLUS_H = 2.0
_MIN_EVENTS = 5

# Time blocks — 6-block (4h) kept as secondary analysis
BLOCKS_4H = [
    ("00-04", 0, 4),
    ("04-08", 4, 8),
    ("08-12", 8, 12),
    ("12-16", 12, 16),
    ("16-20", 16, 20),
    ("20-24", 20, 24),
]

# Primary analysis: 12h blocks (Nyquist-correct for DIA=6h, per EXP-2665)
BLOCKS_12H = [
    ("day_08_20", 8, 20),
    ("night_20_08", 20, 8),   # wraps midnight
]

DAY_BLOCKS_4H = ["08-12", "12-16", "16-20"]
NIGHT_BLOCKS_4H = ["20-24", "00-04", "04-08"]


def _extract_correction_events_with_time(pdf, prior_bolus_h=6.0):
    """Extract correction events with time-of-day info.

    Uses 6h prior-bolus isolation by default (Nyquist-correct for DIA=6h,
    EXP-2666). Caller can reduce to 2h for SMB-heavy patients.
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    hours = t.dt.hour.values
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

    carb_window = STEPS_PER_HOUR
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    post_4h = 4 * STEPS_PER_HOUR

    events = []
    for i in range(prior_window, len(pdf) - post_4h):
        if bolus[i] < 0.5:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 120:
            continue

        # No carbs ±1h
        cs = max(0, i - carb_window)
        ce = min(len(pdf), i + carb_window)
        if np.nansum(carbs[cs:ce]) > 2:
            continue

        # No prior bolus 2h
        if np.nansum(bolus[i - prior_window:i]) > 0.3:
            continue

        # Trajectory at 2h and 4h
        idx_2h = i + 2 * STEPS_PER_HOUR
        idx_4h = i + 4 * STEPS_PER_HOUR

        if idx_4h >= len(glucose):
            continue

        bg_2h = glucose[idx_2h] if not np.isnan(glucose[idx_2h]) else np.nan
        bg_4h = glucose[idx_4h] if not np.isnan(glucose[idx_4h]) else np.nan

        if np.isnan(bg_2h):
            continue

        # Find nadir in 1-5h
        search = glucose[i + STEPS_PER_HOUR:min(i + 5 * STEPS_PER_HOUR, len(glucose))]
        valid_search = search[~np.isnan(search)]
        if len(valid_search) < 6:
            continue

        nadir_bg = float(np.nanmin(search))
        total_drop = glucose[i] - nadir_bg
        if total_drop < 10:
            continue

        hour = int(hours[i])
        # Map to 4h block (secondary)
        block_4h = None
        for bname, bstart, bend in BLOCKS_4H:
            if bstart <= hour < bend:
                block_4h = bname
                break

        # Map to 12h block (primary, Nyquist-correct)
        block_12h = "day_08_20" if 8 <= hour < 20 else "night_20_08"

        events.append({
            "hour": hour,
            "block": block_12h,
            "block_4h": block_4h,
            "pre_bg": float(glucose[i]),
            "dose": float(bolus[i]),
            "bg_2h": float(bg_2h),
            "bg_4h": float(bg_4h) if not np.isnan(bg_4h) else None,
            "nadir_bg": nadir_bg,
            "drop_2h": float(glucose[i] - bg_2h),
            "total_drop": total_drop,
            "apparent_isf": total_drop / float(bolus[i]),
            "demand_isf": float(glucose[i] - bg_2h) / float(bolus[i]),
        })

    return events


def _analyze_patient(pid, events, scheduled_isf):
    """Circadian ISF profiling for one patient.

    Primary analysis uses 12h day/night blocks (Nyquist-correct for DIA=6h).
    Secondary analysis uses 4h blocks for finer granularity.
    """
    if len(events) < 10:
        return None

    edf = pd.DataFrame(events)
    global_isf = float(edf["apparent_isf"].median())

    # ── Primary: 12h blocks (Nyquist-correct) ──────────────────
    day_events = edf[edf["block"] == "day_08_20"]
    night_events = edf[edf["block"] == "night_20_08"]
    day_isf = float(day_events["apparent_isf"].median()) if len(day_events) >= 5 else np.nan
    night_isf = float(night_events["apparent_isf"].median()) if len(night_events) >= 5 else np.nan
    day_demand = float(day_events["demand_isf"].median()) if len(day_events) >= 5 else np.nan
    night_demand = float(night_events["demand_isf"].median()) if len(night_events) >= 5 else np.nan

    # ── Secondary: 4h blocks (informational, sub-Nyquist) ─────
    block_results = {}
    for bname, _, _ in BLOCKS_4H:
        bdf = edf[edf["block_4h"] == bname]
        if len(bdf) < 3:
            block_results[bname] = {"n": 0, "isf": np.nan}
            continue

        block_isf = float(bdf["apparent_isf"].median())
        block_demand_isf = float(bdf["demand_isf"].median())

        block_results[bname] = {
            "n": len(bdf),
            "isf": block_isf,
            "demand_isf": block_demand_isf,
            "isf_pct_of_global": float(block_isf / global_isf * 100) if global_isf > 0 else 100,
        }

    # Variation metric: max ISF / min ISF across blocks with data
    valid_isfs = [b["isf"] for b in block_results.values()
                  if b["n"] >= 3 and not np.isnan(b["isf"])]
    if len(valid_isfs) >= 2:
        isf_variation = max(valid_isfs) / min(valid_isfs) if min(valid_isfs) > 0 else float('inf')
        isf_range_pct = (max(valid_isfs) - min(valid_isfs)) / global_isf * 100
    else:
        isf_variation = 1.0
        isf_range_pct = 0.0

    # Prediction accuracy: single ISF vs 2-block (12h) vs per-block (4h)
    valid = edf.dropna(subset=["bg_2h"])
    if len(valid) < 10:
        return None

    pred_single = valid["pre_bg"] - valid["dose"] * global_isf
    rmse_single = float(np.sqrt(np.mean((valid["bg_2h"] - pred_single) ** 2)))

    # 2-block (12h day/night) — primary
    if not np.isnan(day_isf) and not np.isnan(night_isf):
        pred_2block = valid.apply(
            lambda r: r["pre_bg"] - r["dose"] * (day_isf if r["block"] == "day_08_20" else night_isf),
            axis=1
        )
        rmse_2block = float(np.sqrt(np.mean((valid["bg_2h"] - pred_2block) ** 2)))
    else:
        rmse_2block = rmse_single

    # Per-block ISF (4h) — secondary
    def _block_isf(block_4h):
        br = block_results.get(block_4h, {})
        return br.get("isf", global_isf) if br.get("n", 0) >= 3 else global_isf

    pred_perblock = valid.apply(
        lambda r: r["pre_bg"] - r["dose"] * _block_isf(r["block_4h"]),
        axis=1
    )
    rmse_perblock = float(np.sqrt(np.mean((valid["bg_2h"] - pred_perblock) ** 2)))

    improvement_2block = (rmse_single - rmse_2block) / rmse_single * 100
    improvement_perblock = (rmse_single - rmse_perblock) / rmse_single * 100

    # Find lowest ISF block (most aggressive correction needed)
    lowest_block = min(
        [(b, r["isf"]) for b, r in block_results.items() if r["n"] >= 3 and not np.isnan(r["isf"])],
        key=lambda x: x[1],
        default=(None, None)
    )

    return {
        "n_events": len(events),
        "scheduled_isf": scheduled_isf,
        "global_isf": global_isf,
        "day_isf": day_isf,
        "night_isf": night_isf,
        "day_demand_isf": day_demand,
        "night_demand_isf": night_demand,
        "day_n": len(day_events),
        "night_n": len(night_events),
        "isf_variation": float(isf_variation),
        "isf_range_pct": float(isf_range_pct),
        "blocks_4h": block_results,
        "lowest_isf_block": lowest_block[0] if lowest_block[0] else "N/A",
        "prediction": {
            "rmse_single": rmse_single,
            "rmse_2block_12h": rmse_2block,
            "rmse_perblock_4h": rmse_perblock,
            "improvement_2block_pct": float(improvement_2block),
            "improvement_perblock_pct": float(improvement_perblock),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="EXP-2652: Circadian ISF/Basal Profiling")
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET,
                        help="Path to grid.parquet (default: %(default)s)")
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2652: Circadian ISF/Basal Profiling")
    print(f"  Data: {args.parquet}")
    print(f"  Primary blocks: 12h day/night (Nyquist-correct for DIA=6h)")
    print(f"  Secondary blocks: 4h (informational)")
    print("=" * 70)

    if not args.parquet.exists():
        print(f"ERROR: {args.parquet} not found", file=sys.stderr)
        sys.exit(1)

    df = pd.read_parquet(args.parquet)
    all_patients = sorted(df["patient_id"].unique())
    print(f"  Found {len(all_patients)} patients in dataset")

    has_controller = "controller" in df.columns
    results = {}

    for pid in all_patients:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pdf) < 288 * 14:
            continue

        scheduled_isf = float(pdf["scheduled_isf"].dropna().median()) if "scheduled_isf" in pdf.columns else 50.0

        # Tiered isolation: 6h (Nyquist-correct) → 2h fallback
        events = _extract_correction_events_with_time(pdf, prior_bolus_h=_STRICT_PRIOR_BOLUS_H)
        isolation_used = _STRICT_PRIOR_BOLUS_H
        if len(events) < _MIN_EVENTS:
            events = _extract_correction_events_with_time(pdf, prior_bolus_h=_LAX_PRIOR_BOLUS_H)
            isolation_used = _LAX_PRIOR_BOLUS_H

        r = _analyze_patient(pid, events, scheduled_isf)
        if r is None:
            print(f"  {pid}: insufficient data ({len(events)} events)")
            continue

        r["isolation_h"] = isolation_used
        if has_controller:
            ctrl = pdf["controller"].dropna().mode()
            r["controller"] = str(ctrl.iloc[0]) if len(ctrl) > 0 else "unknown"

        results[pid] = r
        p = r["prediction"]
        print(f"\n  {pid} ({r['n_events']} events):")
        print(f"    Global ISF: {r['global_isf']:.0f}, Day: {r['day_isf']:.0f}, "
              f"Night: {r['night_isf']:.0f}, Variation: {r['isf_variation']:.2f}×")
        print(f"    Lowest ISF block: {r['lowest_isf_block']}")
        print(f"    RMSE: single={p['rmse_single']:.1f}, 2-block(12h)={p['rmse_2block_12h']:.1f} "
              f"({p['improvement_2block_pct']:+.1f}%), "
              f"6-block(4h)={p['rmse_perblock_4h']:.1f} ({p['improvement_perblock_pct']:+.1f}%)")

        # Show per-block ISF (4h, informational)
        print(f"    Blocks(4h): ", end="")
        for bname, _, _ in BLOCKS_4H:
            bi = r["blocks_4h"].get(bname, {})
            if bi.get("n", 0) >= 3:
                print(f"{bname}={bi['isf']:.0f}({bi['n']})", end="  ")
            else:
                print(f"{bname}=—", end="  ")
        print()

    # ── Hypothesis testing ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients = list(results.values())

    # H1: ≥50% have ≥30% ISF variation
    high_var = sum(1 for r in patients if r["isf_range_pct"] >= 30)
    h1_pct = high_var / len(patients) * 100
    print(f"\n  H1: ≥50% of patients have ≥30% ISF variation across time blocks")
    variations = sorted([r["isf_range_pct"] for r in patients], reverse=True)
    print(f"      Variations: {[f'{v:.0f}%' for v in variations]}")
    print(f"      {high_var}/{len(patients)} ({h1_pct:.0f}%)")
    print(f"      → {'PASS' if h1_pct >= 50 else 'FAIL'}")

    # H2: 2-block (12h) reduces RMSE ≥10%
    good_2block = sum(1 for r in patients if r["prediction"]["improvement_2block_pct"] >= 10)
    h2_pct = good_2block / len(patients) * 100
    improvements = sorted([r["prediction"]["improvement_2block_pct"] for r in patients], reverse=True)
    print(f"\n  H2: 12h day/night profile reduces RMSE ≥10% for ≥50% of patients")
    print(f"      Improvements: {[f'{i:+.0f}%' for i in improvements]}")
    print(f"      → {'PASS' if h2_pct >= 50 else 'FAIL'}")

    # H3: Dawn block has lowest ISF (4h analysis, informational)
    dawn_lowest = sum(1 for r in patients if r["lowest_isf_block"] == "04-08")
    lowest_blocks = [r["lowest_isf_block"] for r in patients]
    from collections import Counter
    block_counts = Counter(lowest_blocks)
    print(f"\n  H3: Dawn (04-08h) has lowest ISF most often")
    print(f"      Block frequency: {dict(block_counts)}")
    print(f"      Dawn is lowest for {dawn_lowest}/{len(patients)}")
    most_common = block_counts.most_common(1)[0] if block_counts else ("N/A", 0)
    print(f"      Most common lowest: {most_common[0]} ({most_common[1]} patients)")
    print(f"      → {'PASS' if dawn_lowest == most_common[1] else 'FAIL'}")

    output = {
        "experiment": "EXP-2652",
        "parquet_source": str(args.parquet),
        "n_patients_analyzed": len(results),
        "primary_block_size": "12h (Nyquist-correct for DIA=6h)",
        "patients": results,
    }

    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
