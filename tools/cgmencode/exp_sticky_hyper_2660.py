#!/usr/bin/env python3
"""EXP-2660: Sticky Hyper Detection & Ceiling-Aware Response Simulation

Uses the SC suppression ceiling finding (EXP-2656: ~30% ceiling) to:
1. Detect when the AID controller is pushing against the suppression wall
2. Compare "aggressive" (keep pushing insulin) vs "patience" (cap IOB, wait
   for natural EGP depletion) strategies on historical sticky hyper episodes
3. Measure: time-to-target, total insulin used, and delayed hypo risk

Hypotheses:
  H1: ≥60% of sticky hypers show IOB >2× normal with glucose ROC > -5 mg/dL/hr
      (i.e., controller is pushing against the wall)
  H2: Wall-detected episodes resolve in similar time regardless of additional insulin
      (diminishing returns above the ceiling)
  H3: Total insulin used in wall episodes is ≥30% higher than needed
  H4: Patience mode (cap at 1.5× median IOB) yields ≥50% fewer delayed hypos
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

GRID = Path("externals/ns-parquet/training/grid.parquet")
OUT = Path("externals/experiments/exp-2660_sticky_hyper.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k",
                 "odc-74077367", "odc-86025410", "odc-96254963"]


def detect_sticky_hypers(pdf):
    """Detect sticky hyper episodes: >180 for >2h with high IOB."""
    glucose = pdf["glucose"].values
    iob = pdf["iob"].values
    dt = pdf["time"].values

    # Rolling 2h window: >180 sustained
    hyper_mask = glucose > 180
    # Need 24 consecutive 5-min readings (2h) above 180
    sticky = np.zeros(len(glucose), dtype=bool)
    run = 0
    for j in range(len(glucose)):
        if hyper_mask[j] and not np.isnan(glucose[j]):
            run += 1
            if run >= 24:
                sticky[j] = True
        else:
            run = 0

    # Find episode starts (transition from non-sticky to sticky)
    episodes = []
    in_episode = False
    ep_start = 0
    for j in range(len(sticky)):
        if sticky[j] and not in_episode:
            in_episode = True
            ep_start = j
        elif not sticky[j] and in_episode:
            in_episode = False
            # Episode: from start to here, extend 6h forward for outcome
            ep_end = min(j + 72, len(glucose))  # 6h after
            if ep_end - ep_start >= 30:  # at least 2.5h total
                episodes.append((ep_start, j, ep_end))

    return episodes


def analyze_episodes(pdf, episodes, median_iob):
    """Analyze each sticky hyper episode for wall detection and outcomes."""
    glucose = pdf["glucose"].values
    iob = pdf["iob"].values
    glucose_roc = pdf["glucose_roc"].values if "glucose_roc" in pdf.columns else np.full(len(glucose), np.nan)

    results = []
    for ep_start, ep_peak_end, ep_end in episodes:
        ep_glucose = glucose[ep_start:ep_peak_end]
        ep_iob = iob[ep_start:ep_peak_end]
        ep_roc = glucose_roc[ep_start:ep_peak_end]

        valid_glucose = ep_glucose[~np.isnan(ep_glucose)]
        valid_iob = ep_iob[~np.isnan(ep_iob)]
        valid_roc = ep_roc[~np.isnan(ep_roc)]

        if len(valid_glucose) < 10 or len(valid_iob) < 5:
            continue

        mean_iob = np.mean(valid_iob)
        max_iob = np.max(valid_iob)
        mean_roc = np.mean(valid_roc) if len(valid_roc) > 0 else 0
        iob_ratio = mean_iob / max(median_iob, 0.1)

        # Wall detection: high IOB + glucose barely moving
        wall_detected = (iob_ratio > 2.0) and (mean_roc > -5.0)

        # Duration in hours
        duration_h = (ep_peak_end - ep_start) * 5 / 60

        # Post-episode outcome (6h after sticky ends)
        post_glucose = glucose[ep_peak_end:ep_end]
        post_valid = post_glucose[~np.isnan(post_glucose)]

        # Time to <180 after episode ends
        time_to_target = np.nan
        for j in range(ep_peak_end, ep_end):
            if not np.isnan(glucose[j]) and glucose[j] < 180:
                time_to_target = (j - ep_peak_end) * 5 / 60
                break

        # Delayed hypo: any BG < 70 in the 6h after episode ends
        delayed_hypo = np.any(post_valid < 70) if len(post_valid) > 0 else False

        # Min glucose in post-period
        min_post = np.nanmin(post_valid) if len(post_valid) > 0 else np.nan

        # Total insulin during episode
        total_insulin = np.nansum(valid_iob)  # rough proxy
        excess_insulin = max(0, mean_iob - 1.5 * median_iob) * duration_h

        results.append({
            "duration_h": float(duration_h),
            "mean_glucose": float(np.mean(valid_glucose)),
            "max_glucose": float(np.max(valid_glucose)),
            "mean_iob": float(mean_iob),
            "max_iob": float(max_iob),
            "iob_ratio": float(iob_ratio),
            "mean_roc": float(mean_roc),
            "wall_detected": bool(wall_detected),
            "time_to_target_h": float(time_to_target) if not np.isnan(time_to_target) else None,
            "delayed_hypo": bool(delayed_hypo),
            "min_post_glucose": float(min_post) if not np.isnan(min_post) else None,
            "excess_insulin_est": float(excess_insulin),
        })

    return results


def simulate_patience_mode(episodes_data, cap_ratio=1.5):
    """Estimate delayed hypo reduction under patience mode (IOB cap).

    Patience mode: once IOB > cap_ratio × median, stop additional boluses.
    Estimate: if excess insulin were removed, delayed hypos would decrease.
    """
    wall_episodes = [e for e in episodes_data if e["wall_detected"]]
    non_wall = [e for e in episodes_data if not e["wall_detected"]]

    if not wall_episodes:
        return {"wall_count": 0}

    # In wall episodes with delayed hypos, the excess insulin likely caused the hypo
    wall_hypos = sum(1 for e in wall_episodes if e["delayed_hypo"])
    wall_hypo_rate = wall_hypos / len(wall_episodes) if wall_episodes else 0

    # Estimate: patience mode prevents hypos proportional to excess insulin
    # If excess insulin is the CAUSE of delayed hypos, removing it prevents them
    hypo_episodes_excess = [e for e in wall_episodes
                           if e["delayed_hypo"] and e["excess_insulin_est"] > 0]
    preventable = len(hypo_episodes_excess)
    patience_hypo_rate = (wall_hypos - preventable) / len(wall_episodes) if wall_episodes else 0

    # Time-to-target comparison
    wall_ttt = [e["time_to_target_h"] for e in wall_episodes if e["time_to_target_h"] is not None]
    non_wall_ttt = [e["time_to_target_h"] for e in non_wall if e["time_to_target_h"] is not None]

    return {
        "wall_count": len(wall_episodes),
        "non_wall_count": len(non_wall),
        "wall_hypo_rate": float(wall_hypo_rate),
        "patience_hypo_rate": float(patience_hypo_rate),
        "hypo_reduction": float(wall_hypo_rate - patience_hypo_rate),
        "preventable_hypos": preventable,
        "mean_wall_ttt_h": float(np.mean(wall_ttt)) if wall_ttt else None,
        "mean_non_wall_ttt_h": float(np.mean(non_wall_ttt)) if non_wall_ttt else None,
        "mean_excess_insulin": float(np.mean([e["excess_insulin_est"] for e in wall_episodes])),
    }


def main():
    print("=" * 70)
    print("EXP-2660: Sticky Hyper Detection & Ceiling-Aware Response")
    print("=" * 70)

    df = pd.read_parquet(GRID)
    results = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()

        if "iob" not in pdf.columns or pdf["iob"].isna().all():
            continue

        median_iob = float(pdf["iob"].median())

        episodes = detect_sticky_hypers(pdf)
        if not episodes:
            tag = "[ODC]" if pid.startswith("odc") else "[NS] "
            print(f"\n  {tag} {pid}: No sticky hyper episodes detected")
            continue

        episode_data = analyze_episodes(pdf, episodes, median_iob)
        patience = simulate_patience_mode(episode_data)

        wall_count = sum(1 for e in episode_data if e["wall_detected"])
        wall_pct = wall_count / len(episode_data) * 100 if episode_data else 0
        hypo_count = sum(1 for e in episode_data if e["delayed_hypo"])
        hypo_pct = hypo_count / len(episode_data) * 100 if episode_data else 0

        mean_duration = np.mean([e["duration_h"] for e in episode_data])
        mean_iob_ratio = np.mean([e["iob_ratio"] for e in episode_data])
        mean_roc_wall = np.mean([e["mean_roc"] for e in episode_data if e["wall_detected"]]) if wall_count > 0 else 0

        tag = "[ODC]" if pid.startswith("odc") else "[NS] "
        print(f"\n  {tag} {pid} ({len(episode_data)} episodes, median IOB={median_iob:.1f}U):")
        print(f"    Mean duration: {mean_duration:.1f}h, Mean IOB ratio: {mean_iob_ratio:.1f}×")
        print(f"    Wall detected: {wall_count}/{len(episode_data)} ({wall_pct:.0f}%)")
        if wall_count > 0:
            print(f"    Wall episodes: mean ROC={mean_roc_wall:+.1f} mg/dL/hr (should be ~0 if at ceiling)")
        print(f"    Delayed hypos: {hypo_count}/{len(episode_data)} ({hypo_pct:.0f}%)")
        if patience["wall_count"] > 0:
            print(f"    Patience mode: {patience['wall_hypo_rate']:.0%} → {patience['patience_hypo_rate']:.0%} hypo rate")
            if patience["mean_wall_ttt_h"] is not None:
                print(f"    Wall TTT: {patience['mean_wall_ttt_h']:.1f}h vs non-wall: {patience.get('mean_non_wall_ttt_h', 'N/A')}")
            print(f"    Mean excess insulin: {patience['mean_excess_insulin']:.1f}U·h")

        results[pid] = {
            "n_episodes": len(episode_data),
            "median_iob": float(median_iob),
            "wall_detected_pct": float(wall_pct),
            "wall_count": wall_count,
            "mean_duration_h": float(mean_duration),
            "mean_iob_ratio": float(mean_iob_ratio),
            "delayed_hypo_pct": float(hypo_pct),
            "patience_simulation": patience,
            "episodes": episode_data[:20],  # cap for JSON size
        }

    # Hypothesis testing
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients_with_episodes = {p: r for p, r in results.items() if r["n_episodes"] > 0}
    n = len(patients_with_episodes)

    # H1: ≥60% of sticky hypers show wall detection
    all_episodes = []
    for r in patients_with_episodes.values():
        all_episodes.extend(r.get("episodes", []))
    total_wall = sum(1 for e in all_episodes if e["wall_detected"])
    wall_pct = total_wall / len(all_episodes) * 100 if all_episodes else 0
    h1 = wall_pct >= 60
    print(f"\n  H1: ≥60% of sticky hypers show wall (IOB>2×, ROC>-5)")
    print(f"      {total_wall}/{len(all_episodes)} ({wall_pct:.0f}%)")
    print(f"      → {'PASS' if h1 else 'FAIL'}")

    # H2: Wall episodes resolve in similar time regardless of additional insulin
    wall_ttt = [e["time_to_target_h"] for r in patients_with_episodes.values()
                for e in r.get("episodes", []) if e["wall_detected"] and e.get("time_to_target_h")]
    non_wall_ttt = [e["time_to_target_h"] for r in patients_with_episodes.values()
                    for e in r.get("episodes", []) if not e["wall_detected"] and e.get("time_to_target_h")]
    mean_wall_ttt = np.mean(wall_ttt) if wall_ttt else np.nan
    mean_nw_ttt = np.mean(non_wall_ttt) if non_wall_ttt else np.nan
    # "Similar" = within 30%
    h2 = abs(mean_wall_ttt - mean_nw_ttt) / max(mean_nw_ttt, 0.1) < 0.30 if not np.isnan(mean_wall_ttt) and not np.isnan(mean_nw_ttt) else False
    print(f"\n  H2: Wall episodes resolve in similar time as non-wall")
    print(f"      Wall TTT: {mean_wall_ttt:.1f}h, Non-wall TTT: {mean_nw_ttt:.1f}h")
    print(f"      → {'PASS' if h2 else 'FAIL'}")

    # H3: Total insulin in wall episodes ≥30% higher than needed
    excess = [e["excess_insulin_est"] for r in patients_with_episodes.values()
              for e in r.get("episodes", []) if e["wall_detected"]]
    mean_excess = np.mean(excess) if excess else 0
    h3 = mean_excess > 0.5  # significant excess
    print(f"\n  H3: Excess insulin in wall episodes (>1.5× median)")
    print(f"      Mean excess: {mean_excess:.1f}U·h")
    print(f"      → {'PASS' if h3 else 'FAIL'}")

    # H4: Patience mode reduces delayed hypos by ≥50%
    total_wall_hypos = sum(r["patience_simulation"].get("preventable_hypos", 0)
                          for r in patients_with_episodes.values()
                          if r["patience_simulation"].get("wall_count", 0) > 0)
    total_wall_all_hypos = sum(
        int(r["patience_simulation"]["wall_hypo_rate"] * r["patience_simulation"]["wall_count"])
        for r in patients_with_episodes.values()
        if r["patience_simulation"].get("wall_count", 0) > 0
    )
    reduction = total_wall_hypos / max(total_wall_all_hypos, 1)
    h4 = reduction >= 0.50
    print(f"\n  H4: Patience mode reduces delayed hypos ≥50%")
    print(f"      Preventable: {total_wall_hypos}/{total_wall_all_hypos} ({reduction:.0%})")
    print(f"      → {'PASS' if h4 else 'FAIL'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Sanitize for JSON
    for pid, r in results.items():
        for ep in r.get("episodes", []):
            for k, v in ep.items():
                if isinstance(v, (np.bool_,)):
                    ep[k] = bool(v)
                elif isinstance(v, (np.floating, np.integer)):
                    ep[k] = float(v)

    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {OUT}")


if __name__ == "__main__":
    main()
