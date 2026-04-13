#!/usr/bin/env python3
"""EXP-2624: Insulin Demand Phase Lag vs EGP Recovery.

MOTIVATION: After a correction bolus, glucose drops (insulin demand) then
recovers (EGP reasserting). The Hill equation model treats EGP suppression
as instantaneous, but physiology has a 2-6h lag: hepatic glucose production
is suppressed by insulin, then slowly recovers as insulin wanes.

This experiment extracts "correction natural experiments" — bolus events NOT
accompanied by carbs — and measures the glucose nadir timing and recovery
slope. If EGP recovery is delayed vs the Hill model's prediction, this has
implications for post-correction glucose prediction and ISF estimation.

HYPOTHESES:
  H1: Glucose nadir occurs 1.5-3h post-correction (consistent with DIA peak).
  H2: Post-nadir recovery slope is ≥0.5 mg/dL/hr (EGP reasserting, not flat).
  H3: Recovery slope correlates with pre-correction glucose level (r ≥ 0.3),
      as higher pre-BG → more EGP suppression → stronger recovery.
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
OUTFILE = RESULTS_DIR / "exp-2624_correction_egp_recovery.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

STEPS_PER_HOUR = 12
MIN_BOLUS_U = 0.5           # minimum correction bolus size
MAX_CARBS_WINDOW_G = 2.0    # max carbs in ±1h to qualify as "correction"
PRE_WINDOW_STEPS = 6        # 30 min before bolus (for pre-BG)
POST_WINDOW_STEPS = 72      # 6h after bolus (full DIA window)
NADIR_SEARCH_STEPS = 48     # search for nadir in first 4h
RECOVERY_FIT_STEPS = 24     # fit recovery slope over 2h post-nadir
MIN_DROP_MGDL = 10          # glucose must drop ≥10 mg/dL to be a valid correction


def _extract_correction_events(pdf):
    """Find correction bolus events not accompanied by carbs.

    Returns list of dicts with pre-BG, nadir, recovery info.
    """
    times = pd.to_datetime(pdf["time"])
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    n = len(glucose)

    events = []

    for i in range(PRE_WINDOW_STEPS, n - POST_WINDOW_STEPS):
        if bolus[i] < MIN_BOLUS_U:
            continue

        # Check no carbs in ±1h (12 steps)
        carb_window = carbs[max(0, i - 12):min(n, i + 12)]
        if np.nansum(carb_window) > MAX_CARBS_WINDOW_G:
            continue

        # Check no other bolus within 2h before (avoid stacking)
        prior_bolus = bolus[max(0, i - 24):i]
        if np.nansum(prior_bolus) > 0.1:
            continue

        # Pre-correction glucose
        pre_window = glucose[i - PRE_WINDOW_STEPS:i]
        valid_pre = ~np.isnan(pre_window)
        if valid_pre.sum() < 3:
            continue
        pre_bg = float(np.nanmean(pre_window))

        # Must be correcting from elevated glucose (>120)
        if pre_bg < 120:
            continue

        # Post-correction trajectory
        post = glucose[i:i + POST_WINDOW_STEPS]
        valid_post = ~np.isnan(post)
        if valid_post.sum() < POST_WINDOW_STEPS // 2:
            continue

        # Find nadir
        # Smooth with 15-min rolling to reduce noise
        smoothed = pd.Series(post).rolling(3, center=True, min_periods=1).mean().values
        nadir_search = smoothed[:NADIR_SEARCH_STEPS]
        valid_nadir = ~np.isnan(nadir_search)
        if valid_nadir.sum() < 6:
            continue

        nadir_idx = np.nanargmin(nadir_search)
        nadir_bg = float(nadir_search[nadir_idx])
        nadir_hours = nadir_idx * 5.0 / 60.0

        # Must drop meaningfully
        drop = pre_bg - nadir_bg
        if drop < MIN_DROP_MGDL:
            continue

        # Recovery: slope of glucose from nadir to nadir + 2h
        recovery_start = nadir_idx
        recovery_end = min(len(post), nadir_idx + RECOVERY_FIT_STEPS)
        recovery = post[recovery_start:recovery_end]
        valid_rec = ~np.isnan(recovery)
        if valid_rec.sum() < 6:
            continue

        t_hrs = np.arange(len(recovery)) * (5.0 / 60.0)
        slope, intercept = np.polyfit(t_hrs[valid_rec], recovery[valid_rec], 1)

        # IOB at correction time and at nadir
        iob_at_bolus = float(iob[i])
        iob_at_nadir = float(iob[min(i + nadir_idx, n - 1)])

        events.append({
            "index": int(i),
            "timestamp": str(times.iloc[i]),
            "bolus_u": float(bolus[i]),
            "pre_bg": pre_bg,
            "nadir_bg": nadir_bg,
            "drop_mgdl": drop,
            "nadir_hours": nadir_hours,
            "recovery_slope_mgdl_hr": float(slope),
            "iob_at_bolus": iob_at_bolus,
            "iob_at_nadir": iob_at_nadir,
            "hour_of_day": float(times.iloc[i].hour + times.iloc[i].minute / 60.0),
        })

    return events


def main():
    print("=" * 70)
    print("EXP-2624: Insulin Demand Phase Lag vs EGP Recovery")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    all_results = {}

    pooled_nadir_hours = []
    pooled_recovery_slope = []
    pooled_pre_bg = []
    pooled_drop = []

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288:
            print(f"  SKIP: insufficient data")
            continue

        events = _extract_correction_events(pdf)
        print(f"  Correction events found: {len(events)}")

        if len(events) < 5:
            print(f"  SKIP: too few events")
            continue

        nadir_hrs = [e["nadir_hours"] for e in events]
        recovery_slopes = [e["recovery_slope_mgdl_hr"] for e in events]
        pre_bgs = [e["pre_bg"] for e in events]
        drops = [e["drop_mgdl"] for e in events]

        pooled_nadir_hours.extend(nadir_hrs)
        pooled_recovery_slope.extend(recovery_slopes)
        pooled_pre_bg.extend(pre_bgs)
        pooled_drop.extend(drops)

        mean_nadir = float(np.mean(nadir_hrs))
        median_nadir = float(np.median(nadir_hrs))
        mean_recovery = float(np.mean(recovery_slopes))
        median_recovery = float(np.median(recovery_slopes))
        mean_drop = float(np.mean(drops))

        # Pre-BG → recovery slope correlation
        r_pre_rec, p_pre_rec = stats.pearsonr(pre_bgs, recovery_slopes)

        print(f"  Nadir timing: mean={mean_nadir:.1f}h median={median_nadir:.1f}h")
        print(f"  Mean drop: {mean_drop:.0f} mg/dL")
        print(f"  Recovery slope: mean={mean_recovery:.1f} median={median_recovery:.1f} mg/dL/hr")
        print(f"  Pre-BG → recovery: r={r_pre_rec:.3f} (p={p_pre_rec:.4f})")

        all_results[pid] = {
            "n_events": len(events),
            "nadir_mean_hours": mean_nadir,
            "nadir_median_hours": median_nadir,
            "recovery_slope_mean": mean_recovery,
            "recovery_slope_median": median_recovery,
            "mean_drop_mgdl": mean_drop,
            "mean_pre_bg": float(np.mean(pre_bgs)),
            "r_prebg_recovery": float(r_pre_rec),
            "p_prebg_recovery": float(p_pre_rec),
            "events": events,
        }

    # ── Hypothesis Testing ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_data = list(all_results.keys())

    # H1: Nadir at 1.5-3h
    if pooled_nadir_hours:
        median_nadir = float(np.median(pooled_nadir_hours))
        mean_nadir = float(np.mean(pooled_nadir_hours))
        h1_pass = 1.5 <= median_nadir <= 3.0
        print(f"  H1: Median nadir timing = {median_nadir:.2f}h "
              f"(expected: 1.5-3.0h) → {'PASS' if h1_pass else 'FAIL'}")
        print(f"      Mean={mean_nadir:.2f}h, σ={np.std(pooled_nadir_hours):.2f}h")
        # Distribution
        pct = np.percentile(pooled_nadir_hours, [10, 25, 50, 75, 90])
        print(f"      p10={pct[0]:.1f}h  p25={pct[1]:.1f}h  p50={pct[2]:.1f}h  "
              f"p75={pct[3]:.1f}h  p90={pct[4]:.1f}h")
    else:
        h1_pass = False
        median_nadir = 0
        print("  H1: No data → FAIL")

    # H2: Recovery slope ≥ 0.5 mg/dL/hr
    if pooled_recovery_slope:
        median_slope = float(np.median(pooled_recovery_slope))
        mean_slope = float(np.mean(pooled_recovery_slope))
        h2_pass = median_slope >= 0.5
        print(f"  H2: Median recovery slope = {median_slope:.1f} mg/dL/hr "
              f"(threshold: ≥0.5) → {'PASS' if h2_pass else 'FAIL'}")
        print(f"      Mean={mean_slope:.1f}, σ={np.std(pooled_recovery_slope):.1f}")
        pos_frac = sum(1 for s in pooled_recovery_slope if s > 0) / len(pooled_recovery_slope)
        print(f"      Positive recovery: {pos_frac:.1%} of events")
    else:
        h2_pass = False
        median_slope = 0
        print("  H2: No data → FAIL")

    # H3: Pre-BG → recovery slope (r ≥ 0.3)
    if len(pooled_pre_bg) >= 10:
        r_pool, p_pool = stats.pearsonr(pooled_pre_bg, pooled_recovery_slope)
        h3_pass = r_pool >= 0.3 and p_pool < 0.05
        print(f"  H3: Pooled r(pre_BG, recovery_slope) = {r_pool:.3f} "
              f"(p={p_pool:.4f}, threshold: r≥0.3) → {'PASS' if h3_pass else 'FAIL'}")
    else:
        h3_pass = False
        r_pool = 0
        p_pool = 1
        print("  H3: Insufficient data → FAIL")

    # ── Save ──────────────────────────────────────────────────────────
    summary = {
        "experiment": "EXP-2624",
        "title": "Insulin Demand Phase Lag vs EGP Recovery",
        "patients": patients_with_data,
        "per_patient": {p: {k: v for k, v in all_results[p].items() if k != "events"}
                        for p in patients_with_data},
        "pooled": {
            "n_events": len(pooled_nadir_hours),
            "nadir_median_hours": float(np.median(pooled_nadir_hours)) if pooled_nadir_hours else None,
            "nadir_mean_hours": float(np.mean(pooled_nadir_hours)) if pooled_nadir_hours else None,
            "recovery_slope_median": float(np.median(pooled_recovery_slope)) if pooled_recovery_slope else None,
            "recovery_slope_mean": float(np.mean(pooled_recovery_slope)) if pooled_recovery_slope else None,
            "r_prebg_recovery": float(r_pool),
            "p_prebg_recovery": float(p_pool),
        },
        "hypotheses": {
            "H1": {"statement": "Nadir at 1.5-3h post-correction",
                   "value": float(np.median(pooled_nadir_hours)) if pooled_nadir_hours else None,
                   "result": "PASS" if h1_pass else "FAIL"},
            "H2": {"statement": "Recovery slope ≥ 0.5 mg/dL/hr",
                   "value": float(np.median(pooled_recovery_slope)) if pooled_recovery_slope else None,
                   "result": "PASS" if h2_pass else "FAIL"},
            "H3": {"statement": "Pre-BG → recovery r ≥ 0.3",
                   "value": float(r_pool), "p": float(p_pool),
                   "result": "PASS" if h3_pass else "FAIL"},
        },
        "pooled_events": [{k: v for k, v in e.items()} for e in
                          sorted([e for pid in patients_with_data for e in all_results[pid]["events"]],
                                 key=lambda x: x["timestamp"])],
    }

    with open(OUTFILE, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")

    return summary


if __name__ == "__main__":
    main()
