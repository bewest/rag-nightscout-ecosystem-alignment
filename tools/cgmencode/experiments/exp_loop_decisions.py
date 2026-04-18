#!/usr/bin/env python3
"""
exp_loop_decisions.py — Loop Decision Quality Analysis (EXP-2538)

Analyzes AID loop decision quality: when does the loop make good vs bad
decisions?  Classifies each 5-min interval by loop action, traces outcomes
forward, identifies hypo pathways, and compares NS vs ODC controllers.

Experiments:
  EXP-2538a: Loop action classification and outcome tracking
  EXP-2538b: Decision outcome matrix (action × glucose zone → % good outcome)
  EXP-2538c: Hypo pathway analysis (what loop actions precede hypo events?)
  EXP-2538d: Missed opportunity analysis (hyperglycemia >250 with timid dosing)
  EXP-2538e: NS vs ODC controller comparison on all metrics

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_loop_decisions.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_loop_decisions.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[3]
VIZ_DIR = ROOT / "visualizations" / "loop-decisions"
RESULTS_DIR = ROOT / "externals" / "experiments"

# ── constants ────────────────────────────────────────────────────────────────
STEPS_1H = 12   # 5-min steps in 1 hour
STEPS_2H = 24
STEPS_4H = 48

HYPO_THRESHOLD = 70
HYPER_THRESHOLD = 180
SEVERE_HYPER = 250

GLUCOSE_ZONES = {
    "hypo":       (0, 70),
    "low_normal": (70, 100),
    "target":     (100, 140),
    "elevated":   (140, 180),
    "high":       (180, 9999),
}

ACTION_ORDER = ["aggressive", "high_temp", "neutral", "low_temp", "suspend"]

ACTION_LABELS = {
    "aggressive": "Aggressive (SMB)",
    "high_temp":  "High Temp Basal",
    "neutral":    "Neutral",
    "low_temp":   "Low Temp / Reducing",
    "suspend":    "Suspend (zero basal)",
}


# ── data loading ─────────────────────────────────────────────────────────────
def load_data(tiny: bool = False) -> pd.DataFrame:
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df.sort_values(["patient_id", "time"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


def controller_type(pid: str) -> str:
    return "ODC" if pid.startswith("odc") else "NS"


# ── action classification ────────────────────────────────────────────────────
def classify_actions(df: pd.DataFrame) -> pd.Series:
    """Classify each row into a loop action category.

    Priority order (first match wins):
      1. aggressive — SMB delivered (bolus_smb > 0)
      2. high_temp  — actual_basal > 1.5× scheduled (strong increase)
      3. suspend    — actual_basal near zero (< 0.01 U/h)
      4. low_temp   — actual_basal < 0.5× scheduled (reduction)
      5. neutral    — everything else
    """
    action = pd.Series("neutral", index=df.index, dtype="object")

    sched = df["scheduled_basal_rate"].values
    actual = df["actual_basal_rate"].values
    smb = df["bolus_smb"].values

    has_sched = ~np.isnan(sched) & (sched > 0.01)

    # Suspend: actual ≈ 0
    suspend_mask = (actual < 0.01) & has_sched
    action[suspend_mask] = "suspend"

    # Low temp: actual < 50% of scheduled but not zero
    low_mask = has_sched & (actual >= 0.01) & (actual < 0.5 * sched)
    action[low_mask] = "low_temp"

    # High temp: actual > 150% of scheduled
    high_mask = has_sched & (actual > 1.5 * sched)
    action[high_mask] = "high_temp"

    # Aggressive: SMB delivered (overrides everything)
    aggressive_mask = ~np.isnan(smb) & (smb > 0)
    action[aggressive_mask] = "aggressive"

    return action


# ── future glucose lookup ────────────────────────────────────────────────────
def add_future_glucose(df: pd.DataFrame) -> pd.DataFrame:
    """Add columns for glucose at +1h, +2h, +4h and min glucose in 4h window."""
    for label, steps in [("1h", STEPS_1H), ("2h", STEPS_2H), ("4h", STEPS_4H)]:
        df[f"glucose_{label}"] = np.nan

    df["glucose_min_4h"] = np.nan
    df["glucose_max_4h"] = np.nan

    for pid in df["patient_id"].unique():
        idx = df.index[df["patient_id"] == pid]
        g = df.loc[idx, "glucose"].values
        n = len(g)

        for label, steps in [("1h", STEPS_1H), ("2h", STEPS_2H), ("4h", STEPS_4H)]:
            future = np.full(n, np.nan)
            if steps < n:
                future[:n - steps] = g[steps:]
            df.loc[idx, f"glucose_{label}"] = future

        # Rolling min/max over next 4h
        g_min = np.full(n, np.nan)
        g_max = np.full(n, np.nan)
        for i in range(n - 1):
            end = min(i + STEPS_4H + 1, n)
            window = g[i + 1:end]
            valid = window[~np.isnan(window)]
            if len(valid) > 0:
                g_min[i] = np.nanmin(valid)
                g_max[i] = np.nanmax(valid)
        df.loc[idx, "glucose_min_4h"] = g_min
        df.loc[idx, "glucose_max_4h"] = g_max

    return df


# ── EXP-2538a: Action classification + outcomes ─────────────────────────────
def exp_2538a(df: pd.DataFrame) -> dict:
    """Loop action classification and forward outcome tracking."""
    print("=" * 70)
    print("EXP-2538a: Loop Action Classification & Outcomes")
    print("=" * 70)

    results = {}
    has_1h = df["glucose_1h"].notna()
    has_2h = df["glucose_2h"].notna()
    has_4h = df["glucose_4h"].notna()
    has_min4h = df["glucose_min_4h"].notna()

    header = (f"{'Action':<25} {'Count':>8} {'%':>6}  "
              f"{'BG now':>6} {'BG+1h':>6} {'BG+2h':>6} {'BG+4h':>6}  "
              f"{'→hypo%':>6} {'→hypr%':>6}")
    print(f"\n{header}")
    print("-" * len(header))

    for act in ACTION_ORDER:
        mask = df["action"] == act
        n = int(mask.sum())
        pct = 100 * n / len(df)

        # Mean glucose at action time
        gluc_now = float(df.loc[mask, "glucose"].mean()) if mask.any() else np.nan

        # Mean glucose at future horizons
        g1h = float(df.loc[mask & has_1h, "glucose_1h"].mean()) if (mask & has_1h).any() else np.nan
        g2h = float(df.loc[mask & has_2h, "glucose_2h"].mean()) if (mask & has_2h).any() else np.nan
        g4h = float(df.loc[mask & has_4h, "glucose_4h"].mean()) if (mask & has_4h).any() else np.nan

        # Hypo / hyper within 4h
        valid_4h = mask & has_min4h
        if valid_4h.any():
            hypo_4h = float(100 * (df.loc[valid_4h, "glucose_min_4h"] < HYPO_THRESHOLD).mean())
            hypr_4h = float(100 * (df.loc[valid_4h, "glucose_max_4h"] > HYPER_THRESHOLD).mean())
        else:
            hypo_4h = hypr_4h = np.nan

        label = ACTION_LABELS[act]
        print(f"{label:<25} {n:>8,} {pct:>5.1f}%  "
              f"{gluc_now:>6.1f} {g1h:>6.1f} {g2h:>6.1f} {g4h:>6.1f}  "
              f"{hypo_4h:>5.1f}% {hypr_4h:>5.1f}%")

        results[act] = {
            "count": n,
            "pct": round(pct, 2),
            "glucose_at_action": round(gluc_now, 1) if not np.isnan(gluc_now) else None,
            "glucose_1h": round(g1h, 1) if not np.isnan(g1h) else None,
            "glucose_2h": round(g2h, 1) if not np.isnan(g2h) else None,
            "glucose_4h": round(g4h, 1) if not np.isnan(g4h) else None,
            "hypo_within_4h_pct": round(hypo_4h, 2) if not np.isnan(hypo_4h) else None,
            "hyper_within_4h_pct": round(hypr_4h, 2) if not np.isnan(hypr_4h) else None,
        }

    return results


# ── EXP-2538b: Decision outcome matrix ──────────────────────────────────────
def exp_2538b(df: pd.DataFrame) -> dict:
    """2D matrix: [action] × [glucose zone] → % good outcome at 2h."""
    print("\n" + "=" * 70)
    print("EXP-2538b: Decision Outcome Matrix (% in 70-180 at 2h)")
    print("=" * 70)

    has_2h = df["glucose_2h"].notna()
    results = {}

    # Header
    zone_labels = list(GLUCOSE_ZONES.keys())
    header = f"{'Action':<25}" + "".join(f"  {z:>12}" for z in zone_labels) + "  | weighted"
    print(f"\n{header}")
    print("-" * len(header))

    for act in ACTION_ORDER:
        act_mask = df["action"] == act
        row = {}
        weighted_sum = 0
        weighted_n = 0

        cells = []
        for zone_name, (lo, hi) in GLUCOSE_ZONES.items():
            zone_mask = (df["glucose"] >= lo) & (df["glucose"] < hi)
            combined = act_mask & zone_mask & has_2h

            n = int(combined.sum())
            if n >= 10:
                g2h = df.loc[combined, "glucose_2h"]
                good = float(100 * ((g2h >= 70) & (g2h <= 180)).mean())
                weighted_sum += good * n
                weighted_n += n
            else:
                good = None

            row[zone_name] = {"n": n, "good_outcome_pct": round(good, 1) if good is not None else None}
            cells.append(f"{good:>5.1f}% n={n:<4}" if good is not None else f"{'—':>5} n={n:<4}")

        weighted = round(weighted_sum / weighted_n, 1) if weighted_n > 0 else None
        row["_weighted_good_pct"] = weighted

        label = ACTION_LABELS[act]
        print(f"{label:<25}" + "".join(f"  {c:>12}" for c in cells) +
              f"  | {weighted:.1f}%" if weighted else "")

        results[act] = row

    return results


# ── EXP-2538c: Hypo pathway analysis ────────────────────────────────────────
def exp_2538c(df: pd.DataFrame) -> dict:
    """Trace 4h of loop actions before every hypoglycemic event."""
    print("\n" + "=" * 70)
    print("EXP-2538c: Hypo Pathway Analysis")
    print("=" * 70)

    results = {"pathways": {}, "summary": {}}

    # Define pathway categories
    pathway_counts = {
        "loop_caused_aggressive": 0,   # SMBs in preceding window
        "loop_caused_high_temp": 0,    # high temp without SMB
        "loop_recognized_reducing": 0, # loop was already reducing/suspending
        "external_despite_caution": 0, # loop was cautious but hypo happened
    }
    pathway_examples = {k: [] for k in pathway_counts}
    pre_hypo_profiles = []

    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid]
        idx_arr = pdf.index.values
        gluc = pdf["glucose"].values
        actions = pdf["action"].values
        n = len(idx_arr)

        # Find hypo entries (avoid counting same event twice - require 30 min gap)
        hypo_mask = ~np.isnan(gluc) & (gluc < HYPO_THRESHOLD)
        hypo_positions = np.where(hypo_mask)[0]

        # Deduplicate: require at least 6 steps (30 min) between events
        deduped = []
        last = -999
        for pos in hypo_positions:
            if pos - last >= 6:
                deduped.append(pos)
                last = pos

        for pos in deduped:
            # Look back up to 4h (48 steps)
            start = max(0, pos - STEPS_4H)
            window_actions = actions[start:pos]

            if len(window_actions) == 0:
                continue

            # Count action types in the pre-hypo window
            n_aggressive = int(np.sum(window_actions == "aggressive"))
            n_high_temp = int(np.sum(window_actions == "high_temp"))
            n_suspend = int(np.sum(window_actions == "suspend"))
            n_low_temp = int(np.sum(window_actions == "low_temp"))
            n_neutral = int(np.sum(window_actions == "neutral"))

            total = len(window_actions)
            cautious_pct = 100 * (n_suspend + n_low_temp) / total if total > 0 else 0

            # When did the loop start reducing? (first suspend/low_temp working backward)
            reduction_lead_time = None
            for j in range(len(window_actions) - 1, -1, -1):
                if window_actions[j] in ("suspend", "low_temp"):
                    reduction_lead_time = (len(window_actions) - j) * 5  # minutes
                    break

            # Classify pathway
            if n_aggressive > 3:
                pathway = "loop_caused_aggressive"
            elif n_high_temp > total * 0.3:
                pathway = "loop_caused_high_temp"
            elif cautious_pct > 50:
                pathway = "loop_recognized_reducing"
            else:
                pathway = "external_despite_caution"

            pathway_counts[pathway] += 1

            profile = {
                "patient_id": pid,
                "glucose_at_hypo": float(gluc[pos]),
                "aggressive_pct": round(100 * n_aggressive / total, 1),
                "high_temp_pct": round(100 * n_high_temp / total, 1),
                "suspend_pct": round(100 * n_suspend / total, 1),
                "low_temp_pct": round(100 * n_low_temp / total, 1),
                "neutral_pct": round(100 * n_neutral / total, 1),
                "cautious_pct": round(cautious_pct, 1),
                "reduction_lead_time_min": reduction_lead_time,
                "pathway": pathway,
            }
            pre_hypo_profiles.append(profile)

            if len(pathway_examples[pathway]) < 3:
                pathway_examples[pathway].append(profile)

    total_events = sum(pathway_counts.values())
    print(f"\n  Total hypo events (<{HYPO_THRESHOLD} mg/dL): {total_events}")
    print(f"\n  Pathway Classification:")

    pathway_labels = {
        "loop_caused_aggressive": "Loop-caused (aggressive SMBs)",
        "loop_caused_high_temp":  "Loop-caused (high temp basal)",
        "loop_recognized_reducing": "Loop recognized (was reducing)",
        "external_despite_caution": "External (loop was cautious)",
    }

    for pw, count in pathway_counts.items():
        pct = 100 * count / total_events if total_events > 0 else 0
        label = pathway_labels[pw]
        print(f"    {label:<42} {count:>5} ({pct:>5.1f}%)")

    # Aggregate pre-hypo action profiles
    if pre_hypo_profiles:
        prof_df = pd.DataFrame(pre_hypo_profiles)
        print(f"\n  Pre-hypo action profile (mean across {len(prof_df)} events):")
        for col in ["aggressive_pct", "high_temp_pct", "neutral_pct", "low_temp_pct", "suspend_pct"]:
            print(f"    {col:<25} {prof_df[col].mean():>6.1f}%")
        lead_times = prof_df["reduction_lead_time_min"].dropna()
        if len(lead_times) > 0:
            print(f"\n  Reduction lead time (how early loop starts reducing):")
            print(f"    Mean: {lead_times.mean():.0f} min, "
                  f"Median: {lead_times.median():.0f} min, "
                  f"P25: {lead_times.quantile(0.25):.0f} min")

    results["pathway_counts"] = pathway_counts
    results["total_events"] = total_events
    if pre_hypo_profiles:
        results["summary"] = {
            "mean_aggressive_pct": round(prof_df["aggressive_pct"].mean(), 1),
            "mean_cautious_pct": round(prof_df["cautious_pct"].mean(), 1),
            "mean_reduction_lead_min": round(lead_times.mean(), 0) if len(lead_times) > 0 else None,
            "median_reduction_lead_min": round(lead_times.median(), 0) if len(lead_times) > 0 else None,
        }
    results["pathway_examples"] = {k: v for k, v in pathway_examples.items() if v}

    return results


# ── EXP-2538d: Missed opportunity analysis ───────────────────────────────────
def exp_2538d(df: pd.DataFrame) -> dict:
    """Analyze severe hyperglycemia (>250): was the loop aggressive enough?"""
    print("\n" + "=" * 70)
    print("EXP-2538d: Missed Opportunity Analysis (glucose > 250 mg/dL)")
    print("=" * 70)

    results = {"events": [], "summary": {}}

    excursion_profiles = []

    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid]
        idx_arr = pdf.index.values
        gluc = pdf["glucose"].values
        actions = pdf["action"].values
        smb_vals = pdf["bolus_smb"].values
        iob_vals = pdf["iob"].values
        n = len(idx_arr)

        # Find excursion peaks >250 (deduplicate: require 1h gap)
        over250 = ~np.isnan(gluc) & (gluc > SEVERE_HYPER)
        positions = np.where(over250)[0]

        deduped = []
        last = -999
        for pos in positions:
            if pos - last >= STEPS_1H:
                deduped.append(pos)
                last = pos

        for pos in deduped:
            # Look at action window: 1h before through 2h after the spike
            before_start = max(0, pos - STEPS_1H)
            after_end = min(n, pos + STEPS_2H)

            window_before = actions[before_start:pos]
            window_during = actions[pos:after_end]
            window_smb_before = smb_vals[before_start:pos]
            window_smb_during = smb_vals[pos:after_end]

            # SMB volume delivered
            smb_before = float(np.nansum(window_smb_before))
            smb_during = float(np.nansum(window_smb_during))
            smb_total = smb_before + smb_during

            # IOB at spike
            iob_at_spike = float(iob_vals[pos]) if not np.isnan(iob_vals[pos]) else None

            # Action distribution during excursion (1h before to 2h after)
            full_window = actions[before_start:after_end]
            total = len(full_window)
            n_aggressive = int(np.sum(full_window == "aggressive"))
            n_high_temp = int(np.sum(full_window == "high_temp"))
            n_suspend = int(np.sum(full_window == "suspend"))

            aggressive_pct = 100 * n_aggressive / total if total > 0 else 0

            # Time to first SMB after glucose exceeded 180
            # Look from 1h before peak for when glucose crossed 180
            cross_180_pos = None
            for j in range(before_start, pos):
                if not np.isnan(gluc[j]) and gluc[j] > HYPER_THRESHOLD:
                    cross_180_pos = j
                    break

            first_smb_after_180 = None
            if cross_180_pos is not None:
                for j in range(cross_180_pos, after_end):
                    if not np.isnan(smb_vals[j]) and smb_vals[j] > 0:
                        first_smb_after_180 = (j - cross_180_pos) * 5  # minutes
                        break

            profile = {
                "patient_id": pid,
                "controller": controller_type(pid),
                "peak_glucose": float(gluc[pos]),
                "iob_at_peak": iob_at_spike,
                "smb_before_1h_U": round(smb_before, 3),
                "smb_during_2h_U": round(smb_during, 3),
                "smb_total_3h_U": round(smb_total, 3),
                "aggressive_pct": round(aggressive_pct, 1),
                "suspend_in_window_pct": round(100 * n_suspend / total, 1) if total > 0 else 0,
                "time_to_smb_after_180_min": first_smb_after_180,
            }
            excursion_profiles.append(profile)

    total_excursions = len(excursion_profiles)
    print(f"\n  Total excursions > {SEVERE_HYPER} mg/dL: {total_excursions}")

    if total_excursions > 0:
        edf = pd.DataFrame(excursion_profiles)

        print(f"\n  Excursion Statistics:")
        print(f"    Mean peak glucose:      {edf['peak_glucose'].mean():.0f} mg/dL")
        print(f"    Mean IOB at peak:       {edf['iob_at_peak'].dropna().mean():.1f} U")
        print(f"    Mean total SMB (3h):    {edf['smb_total_3h_U'].mean():.2f} U")
        print(f"    Mean aggressive %:      {edf['aggressive_pct'].mean():.1f}%")

        # Time to first SMB after crossing 180
        smb_times = edf["time_to_smb_after_180_min"].dropna()
        if len(smb_times) > 0:
            print(f"\n  Time to first SMB after crossing 180 mg/dL:")
            print(f"    Mean: {smb_times.mean():.0f} min, "
                  f"Median: {smb_times.median():.0f} min")
            print(f"    No SMB in window: {total_excursions - len(smb_times)} "
                  f"({100*(total_excursions-len(smb_times))/total_excursions:.0f}%)")

        # Timidity score: % of excursions where aggressive_pct < 20
        timid = int((edf["aggressive_pct"] < 20).sum())
        print(f"\n  Timidity analysis:")
        print(f"    Excursions with <20% aggressive action: {timid} ({100*timid/total_excursions:.1f}%)")
        print(f"    Excursions with suspensions during spike: "
              f"{int((edf['suspend_in_window_pct'] > 0).sum())}")

        # By controller
        print(f"\n  By controller type:")
        for ctrl in ["NS", "ODC"]:
            cdf = edf[edf["controller"] == ctrl]
            if len(cdf) == 0:
                continue
            print(f"    {ctrl}: {len(cdf)} excursions, "
                  f"mean peak={cdf['peak_glucose'].mean():.0f}, "
                  f"mean SMB={cdf['smb_total_3h_U'].mean():.2f}U, "
                  f"aggressive={cdf['aggressive_pct'].mean():.1f}%")

        results["summary"] = {
            "total_excursions": total_excursions,
            "mean_peak_glucose": round(edf["peak_glucose"].mean(), 0),
            "mean_iob_at_peak": round(edf["iob_at_peak"].dropna().mean(), 2),
            "mean_smb_total_3h": round(edf["smb_total_3h_U"].mean(), 3),
            "mean_aggressive_pct": round(edf["aggressive_pct"].mean(), 1),
            "timid_pct": round(100 * timid / total_excursions, 1),
            "mean_time_to_smb_min": round(smb_times.mean(), 0) if len(smb_times) > 0 else None,
        }
        results["events"] = excursion_profiles[:20]  # first 20 for JSON

    return results


# ── EXP-2538e: Controller comparison ────────────────────────────────────────
def exp_2538e(df: pd.DataFrame) -> dict:
    """Compare NS vs ODC controllers across all decision quality metrics."""
    print("\n" + "=" * 70)
    print("EXP-2538e: NS vs ODC Controller Comparison")
    print("=" * 70)

    results = {}
    has_2h = df["glucose_2h"].notna()
    has_min4h = df["glucose_min_4h"].notna()

    for ctrl in ["NS", "ODC"]:
        if ctrl == "NS":
            cdf = df[~df["patient_id"].str.startswith("odc")]
        else:
            cdf = df[df["patient_id"].str.startswith("odc")]

        if len(cdf) == 0:
            continue

        ctrl_results = {
            "n_rows": int(len(cdf)),
            "n_patients": int(cdf["patient_id"].nunique()),
        }

        # Action distribution
        action_dist = {}
        for act in ACTION_ORDER:
            mask = cdf["action"] == act
            n = int(mask.sum())
            pct = round(100 * n / len(cdf), 2)
            action_dist[act] = {"count": n, "pct": pct}
        ctrl_results["action_distribution"] = action_dist

        # Aggression index: % of rows that are aggressive or high_temp
        n_agg = int(((cdf["action"] == "aggressive") | (cdf["action"] == "high_temp")).sum())
        aggression_idx = round(100 * n_agg / len(cdf), 2)
        ctrl_results["aggression_index"] = aggression_idx

        # Caution index: % of rows that are suspend or low_temp
        n_caut = int(((cdf["action"] == "suspend") | (cdf["action"] == "low_temp")).sum())
        caution_idx = round(100 * n_caut / len(cdf), 2)
        ctrl_results["caution_index"] = caution_idx

        # Glucose outcomes
        gluc = cdf["glucose"].dropna()
        ctrl_results["glycemic"] = {
            "mean_glucose": round(float(gluc.mean()), 1),
            "std_glucose": round(float(gluc.std()), 1),
            "cv_pct": round(float(100 * gluc.std() / gluc.mean()), 1) if gluc.mean() > 0 else None,
            "tir_pct": round(float(100 * ((gluc >= 70) & (gluc <= 180)).mean()), 1),
            "below_70_pct": round(float(100 * (gluc < 70).mean()), 2),
            "below_54_pct": round(float(100 * (gluc < 54).mean()), 2),
            "above_180_pct": round(float(100 * (gluc > 180).mean()), 1),
            "above_250_pct": round(float(100 * (gluc > 250).mean()), 2),
        }

        # Good outcome rate when acting aggressively
        agg_mask = (cdf["action"] == "aggressive") & has_2h.loc[cdf.index]
        if agg_mask.any():
            g2h = cdf.loc[agg_mask, "glucose_2h"]
            good = float(100 * ((g2h >= 70) & (g2h <= 180)).mean())
            ctrl_results["aggressive_good_outcome_pct"] = round(good, 1)

        # Hypo rate after aggressive action
        agg_4h_mask = (cdf["action"] == "aggressive") & has_min4h.loc[cdf.index]
        if agg_4h_mask.any():
            hypo_after_agg = float(100 * (cdf.loc[agg_4h_mask, "glucose_min_4h"] < HYPO_THRESHOLD).mean())
            ctrl_results["hypo_after_aggressive_pct"] = round(hypo_after_agg, 2)

        # Mean glucose change after aggressive action (delta at 2h)
        if agg_mask.any():
            g_now = cdf.loc[agg_mask, "glucose"]
            g_2h = cdf.loc[agg_mask, "glucose_2h"]
            valid = g_now.notna() & g_2h.notna()
            if valid.any():
                delta = float((g_2h[valid] - g_now[valid]).mean())
                ctrl_results["mean_glucose_delta_2h_after_aggressive"] = round(delta, 1)

        results[ctrl] = ctrl_results

    # Print comparison table
    if "NS" in results and "ODC" in results:
        ns = results["NS"]
        odc = results["ODC"]

        print(f"\n  {'Metric':<45} {'NS':>12} {'ODC':>12} {'Δ':>10}")
        print("  " + "-" * 79)

        def row(label, ns_val, odc_val, fmt=".1f", suffix=""):
            if ns_val is not None and odc_val is not None:
                delta = odc_val - ns_val
                print(f"  {label:<45} {ns_val:>11{fmt}}{suffix} {odc_val:>11{fmt}}{suffix} {delta:>+9{fmt}}")
            elif ns_val is not None:
                print(f"  {label:<45} {ns_val:>11{fmt}}{suffix} {'—':>12} {'—':>10}")
            elif odc_val is not None:
                print(f"  {label:<45} {'—':>12} {odc_val:>11{fmt}}{suffix} {'—':>10}")

        row("Patients", ns["n_patients"], odc["n_patients"], "d", "")
        row("Rows (5-min intervals)", ns["n_rows"], odc["n_rows"], ",d", "")
        print()
        row("Aggression index (%)", ns["aggression_index"], odc["aggression_index"])
        row("Caution index (%)", ns["caution_index"], odc["caution_index"])
        print()

        for act in ACTION_ORDER:
            ns_pct = ns["action_distribution"][act]["pct"]
            odc_pct = odc["action_distribution"][act]["pct"]
            row(f"  {ACTION_LABELS[act]} (%)", ns_pct, odc_pct)

        print()
        ng, og = ns["glycemic"], odc["glycemic"]
        row("Mean glucose (mg/dL)", ng["mean_glucose"], og["mean_glucose"])
        row("Glucose CV (%)", ng["cv_pct"], og["cv_pct"])
        row("TIR 70-180 (%)", ng["tir_pct"], og["tir_pct"])
        row("Time below 70 (%)", ng["below_70_pct"], og["below_70_pct"], ".2f")
        row("Time below 54 (%)", ng["below_54_pct"], og["below_54_pct"], ".2f")
        row("Time above 180 (%)", ng["above_180_pct"], og["above_180_pct"])
        row("Time above 250 (%)", ng["above_250_pct"], og["above_250_pct"], ".2f")

        print()
        ns_ago = ns.get("aggressive_good_outcome_pct")
        odc_ago = odc.get("aggressive_good_outcome_pct")
        row("Good outcome after SMB (%)", ns_ago, odc_ago)

        ns_hypo = ns.get("hypo_after_aggressive_pct")
        odc_hypo = odc.get("hypo_after_aggressive_pct")
        row("Hypo after SMB (%)", ns_hypo, odc_hypo, ".2f")

        ns_delta = ns.get("mean_glucose_delta_2h_after_aggressive")
        odc_delta = odc.get("mean_glucose_delta_2h_after_aggressive")
        row("Mean Δglucose 2h after SMB (mg/dL)", ns_delta, odc_delta)

    # Verdict
    print("\n  Interpretation:")
    if "NS" in results and "ODC" in results:
        ns_agg = ns["aggression_index"]
        odc_agg = odc["aggression_index"]
        more_agg = "ODC" if odc_agg > ns_agg else "NS"
        print(f"    • {more_agg} is more aggressive ({max(ns_agg, odc_agg):.1f}% vs {min(ns_agg, odc_agg):.1f}%)")

        ns_hypo_r = ns["glycemic"]["below_70_pct"]
        odc_hypo_r = odc["glycemic"]["below_70_pct"]
        more_hypo = "ODC" if odc_hypo_r > ns_hypo_r else "NS"
        print(f"    • {more_hypo} has more hypo time ({max(ns_hypo_r, odc_hypo_r):.2f}% vs {min(ns_hypo_r, odc_hypo_r):.2f}%)")

        ns_hyper = ns["glycemic"]["above_180_pct"]
        odc_hyper = odc["glycemic"]["above_180_pct"]
        less_hyper = "NS" if ns_hyper < odc_hyper else "ODC"
        print(f"    • {less_hyper} better prevents hyperglycemia ({min(ns_hyper, odc_hyper):.1f}% vs {max(ns_hyper, odc_hyper):.1f}%)")

    return results


# ── Visualization ────────────────────────────────────────────────────────────
def generate_visualizations(results_a: dict, results_b: dict,
                            results_c: dict, results_e: dict):
    """Generate loop decision quality figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping visualization")
        return

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # ── Figure 1: Action distribution + glucose trajectory ────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    actions = [a for a in ACTION_ORDER if a in results_a]
    counts = [results_a[a]["count"] for a in actions]
    labels = [ACTION_LABELS[a] for a in actions]
    colors = ["#d32f2f", "#ff9800", "#4caf50", "#2196f3", "#9c27b0"]

    axes[0].barh(range(len(actions)), counts, color=colors[:len(actions)])
    axes[0].set_yticks(range(len(actions)))
    axes[0].set_yticklabels(labels, fontsize=9)
    axes[0].set_xlabel("Count (5-min intervals)")
    axes[0].set_title("EXP-2538a: Loop Action Distribution")

    # Glucose trajectory by action type
    horizons = ["glucose_at_action", "glucose_1h", "glucose_2h", "glucose_4h"]
    x_labels = ["Now", "+1h", "+2h", "+4h"]
    for i, act in enumerate(actions):
        vals = [results_a[act].get(h) for h in horizons]
        vals = [v if v is not None else np.nan for v in vals]
        axes[1].plot(range(4), vals, marker="o", label=ACTION_LABELS[act],
                     color=colors[i], linewidth=2)

    axes[1].axhspan(70, 180, alpha=0.1, color="green", label="Target range")
    axes[1].set_xticks(range(4))
    axes[1].set_xticklabels(x_labels)
    axes[1].set_ylabel("Mean Glucose (mg/dL)")
    axes[1].set_title("EXP-2538a: Glucose Trajectory by Action")
    axes[1].legend(fontsize=7, loc="upper right")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_action_distribution.png", dpi=150)
    plt.close()
    print(f"  Saved fig1_action_distribution.png")

    # ── Figure 2: Decision outcome heatmap ────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5))

    zone_names = list(GLUCOSE_ZONES.keys())
    matrix = []
    for act in ACTION_ORDER:
        row = []
        for zn in zone_names:
            val = results_b.get(act, {}).get(zn, {}).get("good_outcome_pct")
            row.append(val if val is not None else np.nan)
        matrix.append(row)

    matrix = np.array(matrix)
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
    ax.set_yticks(range(len(ACTION_ORDER)))
    ax.set_yticklabels([ACTION_LABELS[a] for a in ACTION_ORDER], fontsize=9)
    ax.set_xticks(range(len(zone_names)))
    ax.set_xticklabels([z.replace("_", "\n") for z in zone_names], fontsize=9)
    ax.set_title("EXP-2538b: % Good Outcome (70-180 at 2h)\nAction × Starting Glucose Zone")

    # Annotate cells
    for i in range(len(ACTION_ORDER)):
        for j in range(len(zone_names)):
            val = matrix[i, j]
            if not np.isnan(val):
                color = "white" if val < 40 or val > 85 else "black"
                ax.text(j, i, f"{val:.0f}%", ha="center", va="center",
                        fontsize=9, fontweight="bold", color=color)

    plt.colorbar(im, ax=ax, shrink=0.8, label="% Good Outcome")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_decision_outcome_matrix.png", dpi=150)
    plt.close()
    print(f"  Saved fig2_decision_outcome_matrix.png")

    # ── Figure 3: Hypo pathway pie + controller comparison ────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Hypo pathways
    pw = results_c.get("pathway_counts", {})
    if pw and sum(pw.values()) > 0:
        pw_labels = {
            "loop_caused_aggressive": "Loop-caused\n(aggressive)",
            "loop_caused_high_temp": "Loop-caused\n(high temp)",
            "loop_recognized_reducing": "Loop recognized\n(reducing)",
            "external_despite_caution": "External\n(despite caution)",
        }
        pw_colors = ["#d32f2f", "#ff9800", "#4caf50", "#2196f3"]
        sizes = [pw.get(k, 0) for k in pw_labels]
        labels_pie = [pw_labels[k] for k in pw_labels]
        axes[0].pie(sizes, labels=labels_pie, colors=pw_colors, autopct="%1.1f%%",
                    startangle=90, textprops={"fontsize": 8})
        axes[0].set_title("EXP-2538c: Hypo Pathway Classification")

    # Controller comparison
    if "NS" in results_e and "ODC" in results_e:
        metrics = ["tir_pct", "below_70_pct", "above_180_pct", "above_250_pct"]
        metric_labels = ["TIR 70-180", "Below 70", "Above 180", "Above 250"]
        ns_vals = [results_e["NS"]["glycemic"].get(m, 0) for m in metrics]
        odc_vals = [results_e["ODC"]["glycemic"].get(m, 0) for m in metrics]

        x = np.arange(len(metrics))
        w = 0.35
        axes[1].bar(x - w / 2, ns_vals, w, label="NS", color="#2196f3")
        axes[1].bar(x + w / 2, odc_vals, w, label="ODC", color="#ff9800")
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(metric_labels, fontsize=9)
        axes[1].set_ylabel("% of time")
        axes[1].set_title("EXP-2538e: NS vs ODC Glycemic Outcomes")
        axes[1].legend()

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_hypo_pathways_controller.png", dpi=150)
    plt.close()
    print(f"  Saved fig3_hypo_pathways_controller.png")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="EXP-2538: Loop Decision Quality Analysis")
    parser.add_argument("--tiny", action="store_true", help="Use tiny dataset")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    # Classify loop actions
    print("Classifying loop actions...")
    df["action"] = classify_actions(df)
    act_counts = df["action"].value_counts()
    for act in ACTION_ORDER:
        n = act_counts.get(act, 0)
        print(f"  {ACTION_LABELS[act]:<25} {n:>8,} ({100*n/len(df):>5.1f}%)")

    # Compute future glucose columns
    print("\nComputing future glucose lookups (1h, 2h, 4h)...")
    df = add_future_glucose(df)
    print("  Done.\n")

    # Run experiments
    r_a = exp_2538a(df)
    r_b = exp_2538b(df)
    r_c = exp_2538c(df)
    r_d = exp_2538d(df)
    r_e = exp_2538e(df)

    # Visualizations
    print("\nGenerating visualizations...")
    generate_visualizations(r_a, r_b, r_c, r_e)

    # Save results
    all_results = {
        "experiment": "EXP-2538",
        "title": "Loop Decision Quality Analysis",
        "sub_experiments": {
            "exp_2538a_action_classification": r_a,
            "exp_2538b_decision_outcome_matrix": r_b,
            "exp_2538c_hypo_pathways": r_c,
            "exp_2538d_missed_opportunities": r_d,
            "exp_2538e_controller_comparison": r_e,
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2538_loop_decisions.json"
    with open(out_path, "w") as f:
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            raise TypeError(f"Cannot serialize {type(obj)}")
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
