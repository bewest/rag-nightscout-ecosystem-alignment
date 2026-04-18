#!/usr/bin/env python3
"""EXP-2666: Prior-Bolus Isolation Window Sweep for Demand ISF

EXP-2665 tested 2h vs 6h prior-bolus isolation with 12h/8h/4h blocks.
This experiment sweeps the full feasible range of isolation windows to:

  1. Determine if longer isolation reveals a circadian signal masked by noise
  2. Check whether demand ISF itself changes with stricter isolation
  3. Find the isolation threshold where demand ISF stabilizes
  4. Confirm or revise the "constant per patient" conclusion

ISOLATION WINDOWS: 2h, 4h, 6h, 8h, 10h, 12h
BLOCK SIZES: 12h (Nyquist-compliant), 8h (marginal)

FEASIBILITY (from bolus gap analysis):
  6h: 24-37% of gaps survive
  8h: 20-31%
  12h: 12-26%
  Beyond 12h: <15% — insufficient power

HYPOTHESES:
  H1: Demand ISF stabilizes by 6-8h isolation (no further change at 10-12h)
  H2: No circadian signal emerges at ANY isolation window
  H3: Event count drops monotonically; practical minimum is ≥8 events/patient
  H4: Cross-patient demand ISF rank order is preserved across isolation windows

If demand ISF changes significantly between 6h and 12h isolation, it means
the 6h window still had contamination — and longer isolation is needed.
If it stabilizes, 6h is sufficient (confirming EXP-2665).
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
OUTFILE = RESULTS_DIR / "exp-2666_isolation_sweep.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12

ISOLATION_WINDOWS = [2, 4, 6, 8, 10, 12]  # hours

BLOCKS_12H = [("day_08_20", 8, 20), ("night_20_08", 20, 8)]
BLOCKS_8H = [("00-08", 0, 8), ("08-16", 8, 16), ("16-24", 16, 24)]

MIN_EVENTS = 5
N_BOOTSTRAP = 1000


def in_block(hour, block_start, block_end):
    if block_start < block_end:
        return block_start <= hour < block_end
    else:
        return hour >= block_start or hour < block_end


def extract_corrections(pdf, prior_bolus_h):
    """Extract corrections with given isolation window."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    hours = t.dt.hour.values
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

    carb_window = STEPS_PER_HOUR  # ±1h
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    demand_steps = 2 * STEPS_PER_HOUR  # 2h
    nadir_start = STEPS_PER_HOUR
    nadir_end = 5 * STEPS_PER_HOUR

    events = []
    for i in range(prior_window, len(pdf) - nadir_end):
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

        idx_2h = i + demand_steps
        if idx_2h >= len(glucose) or np.isnan(glucose[idx_2h]):
            continue

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


def analyze_circadian(events, block_defs):
    """Test for circadian signal at given block definition."""
    if len(events) < MIN_EVENTS:
        return None

    edf = pd.DataFrame(events)
    global_demand = float(edf["demand_isf"].median())

    blocks = {}
    block_groups = []
    for bname, bstart, bend in block_defs:
        mask = edf["hour"].apply(lambda h: in_block(h, bstart, bend))
        bdf = edf[mask]
        bn = len(bdf)
        if bn >= 3:
            d_isf = float(bdf["demand_isf"].median())
            blocks[bname] = {"n": bn, "demand_isf": round(d_isf, 1)}
            block_groups.append(bdf["demand_isf"].values)
        else:
            blocks[bname] = {"n": bn}

    # Kruskal-Wallis
    kw_p = None
    if len(block_groups) >= 2:
        try:
            _, kw_p = stats.kruskal(*block_groups)
        except ValueError:
            pass

    # Prediction improvement
    pred_flat_err = (edf["drop_2h"] - edf["dose"] * global_demand) ** 2

    def _get_block_isf(hour):
        for bname, bstart, bend in block_defs:
            if in_block(hour, bstart, bend):
                bi = blocks.get(bname, {})
                return bi.get("demand_isf", global_demand) if bi.get("n", 0) >= 3 else global_demand
        return global_demand

    block_isfs = edf["hour"].apply(_get_block_isf)
    pred_block_err = (edf["drop_2h"] - edf["dose"] * block_isfs) ** 2

    rmse_flat = float(np.sqrt(pred_flat_err.mean()))
    rmse_block = float(np.sqrt(pred_block_err.mean()))
    improvement = (rmse_flat - rmse_block) / rmse_flat * 100 if rmse_flat > 0 else 0

    return {
        "blocks": blocks,
        "kw_p": round(float(kw_p), 4) if kw_p is not None else None,
        "kw_significant": float(kw_p) < 0.05 if kw_p is not None else False,
        "rmse_flat": round(rmse_flat, 1),
        "rmse_block": round(rmse_block, 1),
        "improvement_pct": round(improvement, 1),
    }


def main():
    print("=" * 70)
    print("EXP-2666: Prior-Bolus Isolation Window Sweep")
    print("=" * 70)
    print(f"Isolation windows: {ISOLATION_WINDOWS}h")
    print(f"Block sizes: 12h (Nyquist), 8h (marginal)")

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

        patient_result = {"sweeps": {}}
        isf_by_window = []

        print(f"\n{'='*50}")
        print(f"  {pid}")
        print(f"{'='*50}")

        for iso_h in ISOLATION_WINDOWS:
            events = extract_corrections(pdf, prior_bolus_h=iso_h)
            n = len(events)

            sweep = {"n_events": n, "isolation_h": iso_h}

            if n >= MIN_EVENTS:
                demands = np.array([e["demand_isf"] for e in events])
                sweep["demand_isf_median"] = round(float(np.median(demands)), 1)
                sweep["demand_isf_iqr"] = [
                    round(float(np.percentile(demands, 25)), 1),
                    round(float(np.percentile(demands, 75)), 1),
                ]
                sweep["demand_isf_mean"] = round(float(np.mean(demands)), 1)

                # Bootstrap CI on median
                rng = np.random.default_rng(42)
                boot_medians = []
                for _ in range(N_BOOTSTRAP):
                    idx = rng.integers(0, n, size=n)
                    boot_medians.append(float(np.median(demands[idx])))
                boot_medians = np.array(boot_medians)
                sweep["bootstrap_ci"] = [
                    round(float(np.percentile(boot_medians, 2.5)), 1),
                    round(float(np.percentile(boot_medians, 97.5)), 1),
                ]

                isf_by_window.append((iso_h, float(np.median(demands)), n))

                # Circadian at 12h and 8h blocks
                circ_12h = analyze_circadian(events, BLOCKS_12H)
                circ_8h = analyze_circadian(events, BLOCKS_8H)
                sweep["circadian_12h"] = circ_12h
                sweep["circadian_8h"] = circ_8h

                # Print summary
                ci = sweep["bootstrap_ci"]
                kw12 = circ_12h["kw_p"] if circ_12h and circ_12h.get("kw_p") else "N/A"
                kw8 = circ_8h["kw_p"] if circ_8h and circ_8h.get("kw_p") else "N/A"
                imp12 = circ_12h["improvement_pct"] if circ_12h else 0
                imp8 = circ_8h["improvement_pct"] if circ_8h else 0

                print(f"  {iso_h:>2}h: n={n:>3}, demand_ISF={sweep['demand_isf_median']:>6.1f} "
                      f"[{ci[0]:>5.1f}-{ci[1]:>5.1f}], "
                      f"12h: KW={kw12!s:>6} imp={imp12:>+5.1f}%, "
                      f"8h: KW={kw8!s:>6} imp={imp8:>+5.1f}%")
            else:
                print(f"  {iso_h:>2}h: n={n:>3} (insufficient)")

            patient_result["sweeps"][str(iso_h)] = sweep

        # Stability analysis: does ISF stabilize?
        if len(isf_by_window) >= 3:
            windows = [w[0] for w in isf_by_window]
            isfs = [w[1] for w in isf_by_window]

            # Find where ISF stops changing (< 10% shift from previous)
            stable_at = None
            for j in range(1, len(isfs)):
                if isfs[j-1] != 0:
                    pct_change = abs(isfs[j] - isfs[j-1]) / abs(isfs[j-1]) * 100
                else:
                    pct_change = 0
                if pct_change < 10 and stable_at is None:
                    stable_at = windows[j]

            patient_result["stability"] = {
                "isf_trajectory": [{"isolation_h": w, "demand_isf": round(i, 1), "n": c}
                                    for w, i, c in isf_by_window],
                "stabilizes_at_h": stable_at,
                "total_shift_pct": round(abs(isfs[-1] - isfs[0]) / abs(isfs[0]) * 100, 1)
                    if isfs[0] != 0 else None,
            }

            print(f"  Stability: {'stabilizes at ' + str(stable_at) + 'h' if stable_at else 'not stable'}, "
                  f"total shift: {patient_result['stability'].get('total_shift_pct', '?')}%")

        all_results[pid] = patient_result

    # ── Cross-patient summary ────────────────────────────────────
    print("\n" + "=" * 70)
    print("CROSS-PATIENT SUMMARY")
    print("=" * 70)

    # Event counts per isolation window
    print("\n  Events per patient by isolation window:")
    print(f"  {'Patient':<15}", end="")
    for iso_h in ISOLATION_WINDOWS:
        print(f"  {iso_h}h", end="")
    print()
    for pid, r in sorted(all_results.items()):
        print(f"  {pid:<15}", end="")
        for iso_h in ISOLATION_WINDOWS:
            n = r["sweeps"].get(str(iso_h), {}).get("n_events", 0)
            print(f"  {n:>3}", end="")
        print()

    # Demand ISF per isolation window
    print("\n  Demand ISF median by isolation window:")
    print(f"  {'Patient':<15}", end="")
    for iso_h in ISOLATION_WINDOWS:
        print(f"  {iso_h:>5}h", end="")
    print()
    for pid, r in sorted(all_results.items()):
        print(f"  {pid:<15}", end="")
        for iso_h in ISOLATION_WINDOWS:
            isf = r["sweeps"].get(str(iso_h), {}).get("demand_isf_median")
            print(f"  {isf:>5.0f}" if isf is not None else "    —", end="")
        print()

    # KW significance count per window × block-size
    print("\n  Kruskal-Wallis significant counts (12h blocks | 8h blocks):")
    for iso_h in ISOLATION_WINDOWS:
        n_sig_12 = 0
        n_sig_8 = 0
        n_tested_12 = 0
        n_tested_8 = 0
        for r in all_results.values():
            sw = r["sweeps"].get(str(iso_h), {})
            c12 = sw.get("circadian_12h")
            c8 = sw.get("circadian_8h")
            if c12 and c12.get("kw_p") is not None:
                n_tested_12 += 1
                if c12["kw_significant"]:
                    n_sig_12 += 1
            if c8 and c8.get("kw_p") is not None:
                n_tested_8 += 1
                if c8["kw_significant"]:
                    n_sig_8 += 1
        print(f"  {iso_h:>2}h: 12h blocks {n_sig_12}/{n_tested_12} sig | "
              f"8h blocks {n_sig_8}/{n_tested_8} sig")

    # Stability summary
    print("\n  ISF Stabilization:")
    stable_windows = []
    for pid, r in sorted(all_results.items()):
        stab = r.get("stability", {})
        sw = stab.get("stabilizes_at_h")
        shift = stab.get("total_shift_pct", "?")
        if sw:
            stable_windows.append(sw)
        print(f"  {pid:<15}: stabilizes at {sw}h, total shift={shift}%")

    if stable_windows:
        print(f"\n  Median stabilization window: {np.median(stable_windows):.0f}h")

    # Rank order preservation (H4)
    print("\n  Rank Order Preservation (Spearman):")
    # Get ISFs at each window for patients that have data at all windows
    common_pids = []
    for pid in all_results:
        has_all = all(all_results[pid]["sweeps"].get(str(h), {}).get("demand_isf_median") is not None
                      for h in [2, 6])
        if has_all:
            common_pids.append(pid)

    if len(common_pids) >= 4:
        isf_2h = [all_results[p]["sweeps"]["2"]["demand_isf_median"] for p in common_pids]
        isf_6h = [all_results[p]["sweeps"]["6"]["demand_isf_median"] for p in common_pids]
        rho, p_val = stats.spearmanr(isf_2h, isf_6h)
        print(f"  2h vs 6h: rho={rho:.3f}, p={p_val:.3f} (n={len(common_pids)} patients)")

        # Check longer windows if enough data
        for iso_h in [8, 10, 12]:
            pids_with = [p for p in common_pids
                         if all_results[p]["sweeps"].get(str(iso_h), {}).get("demand_isf_median") is not None]
            if len(pids_with) >= 4:
                isf_ref = [all_results[p]["sweeps"]["2"]["demand_isf_median"] for p in pids_with]
                isf_test = [all_results[p]["sweeps"][str(iso_h)]["demand_isf_median"] for p in pids_with]
                rho, p_val = stats.spearmanr(isf_ref, isf_test)
                print(f"  2h vs {iso_h}h: rho={rho:.3f}, p={p_val:.3f} (n={len(pids_with)} patients)")

    # ── Hypothesis testing ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("HYPOTHESIS RESULTS")
    print("=" * 70)

    # H1: ISF stabilizes by 6-8h
    n_stable_6_8 = sum(1 for w in stable_windows if w <= 8)
    h1 = n_stable_6_8 > len(stable_windows) / 2 if stable_windows else False
    print(f"\n  H1: ISF stabilizes by 6-8h isolation")
    print(f"      {n_stable_6_8}/{len(stable_windows)} patients → {'PASS' if h1 else 'FAIL'}")

    # H2: No circadian signal at ANY window
    any_sig = False
    for iso_h in ISOLATION_WINDOWS:
        for r in all_results.values():
            sw = r["sweeps"].get(str(iso_h), {})
            for bkey in ["circadian_12h", "circadian_8h"]:
                c = sw.get(bkey, {})
                if c and c.get("kw_significant"):
                    any_sig = True
    h2 = not any_sig
    print(f"\n  H2: No circadian signal at ANY isolation window")
    print(f"      Any significant: {any_sig} → {'PASS' if h2 else 'FAIL'}")

    # H3: Events drop monotonically; ≥8 events at practical maximum
    practical_counts = []
    for r in all_results.values():
        for iso_h in [8, 10]:
            n = r["sweeps"].get(str(iso_h), {}).get("n_events", 0)
            if n > 0:
                practical_counts.append(n)
    n_sufficient = sum(1 for c in practical_counts if c >= 8)
    h3 = n_sufficient > len(practical_counts) / 2 if practical_counts else False
    print(f"\n  H3: ≥8 events at 8-10h isolation for majority of patients")
    print(f"      {n_sufficient}/{len(practical_counts)} → {'PASS' if h3 else 'FAIL'}")

    # H4: Rank order preserved
    h4 = False
    if len(common_pids) >= 4:
        isf_2h = [all_results[p]["sweeps"]["2"]["demand_isf_median"] for p in common_pids]
        isf_6h = [all_results[p]["sweeps"]["6"]["demand_isf_median"] for p in common_pids]
        rho, _ = stats.spearmanr(isf_2h, isf_6h)
        h4 = rho > 0.7
        print(f"\n  H4: Rank order preserved (Spearman rho > 0.7)")
        print(f"      rho={rho:.3f} → {'PASS' if h4 else 'FAIL'}")

    # ── Final interpretation ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)

    if h1 and h2:
        print("  Demand ISF stabilizes by 6-8h and shows no circadian signal")
        print("  at any isolation window. CONFIRMED: constant per patient.")
        print("  6h isolation is sufficient; longer windows lose events without")
        print("  changing the answer.")
    elif h2:
        print("  No circadian signal, but ISF doesn't fully stabilize.")
        print("  Consider using 8-10h isolation for production to be safe.")
    elif h1:
        print("  ISF stabilizes, but some circadian signal detected.")
        print("  Investigate which patients/windows show significance.")
    else:
        print("  Neither stable nor non-circadian. More data needed.")

    # ── Save ─────────────────────────────────────────────────────
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
        "experiment": "EXP-2666",
        "title": "Prior-Bolus Isolation Window Sweep",
        "isolation_windows_h": ISOLATION_WINDOWS,
        "n_patients": len(all_results),
        "per_patient": all_results,
        "hypotheses": {
            "H1_stabilizes_6_8h": h1,
            "H2_no_circadian_any_window": h2,
            "H3_sufficient_events": h3,
            "H4_rank_preserved": h4,
        },
        "summary": {
            "median_stabilization_h": float(np.median(stable_windows)) if stable_windows else None,
            "any_circadian_signal": any_sig,
            "recommendation": "6h_isolation" if (h1 and h2) else "8h_isolation",
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
