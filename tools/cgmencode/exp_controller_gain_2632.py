#!/usr/bin/env python3
"""EXP-2632: Controller Gain from Enacted vs Scheduled Basals

Measures AID controller aggressiveness around correction events by comparing
actual/enacted basal rates vs scheduled profiles. The ratio quantifies how
hard the AID is working to compensate.

Uses grid.parquet columns: scheduled_basal_rate, actual_basal_rate (or net_basal),
loop_enacted_rate, glucose, iob

Hypotheses:
  H1: AID modulation amplitude in 2-4h post-correction predicts rebound (r > 0.3)
  H2: Controller aggressiveness varies >3× across patients
  H3: Higher gain → more post-correction glucose CV (r > 0.2)
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
EXP2624 = ROOT / "externals" / "experiments" / "exp-2624_correction_egp_recovery.json"
OUT = ROOT / "externals" / "experiments" / "exp-2632_controller_gain.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
STEPS_PER_HOUR = 12
MAX_STEPS = 72  # 6h


def _load_data():
    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)

    # Detect correction events directly from grid (same criteria as EXP-2624)
    events = []
    for pid in FULL_PATIENTS:
        dp = df[df["patient_id"] == pid].copy().reset_index(drop=True)
        if len(dp) == 0:
            continue
        for i in range(6, len(dp) - MAX_STEPS):
            row = dp.iloc[i]
            if pd.isna(row.get("bolus")) or row["bolus"] <= 0.5:
                continue
            if pd.isna(row.get("glucose")) or row["glucose"] < 130:
                continue
            window = dp.iloc[max(0, i - 6):min(len(dp), i + 7)]
            carb_sum = window["carbs"].fillna(0).sum() if "carbs" in window.columns else 0
            if carb_sum > 0:
                continue
            events.append({
                "patient_id": pid,
                "timestamp": str(row["time"]),
                "bolus_u": float(row["bolus"]),
                "pre_bg": float(row["glucose"]),
            })

    print(f"Detected {len(events)} correction events, grid shape {df.shape}")
    for p in sorted(set(e["patient_id"] for e in events)):
        n = sum(1 for e in events if e["patient_id"] == p)
        print(f"  Patient {p}: {n} events")
    return events, df


def _get_basal_columns(df):
    """Detect which basal columns are available."""
    candidates = {
        "enacted": ["loop_enacted_rate", "actual_basal_rate", "net_basal"],
        "scheduled": ["scheduled_basal_rate"],
    }
    enacted_col = None
    for c in candidates["enacted"]:
        if c in df.columns and df[c].notna().sum() > 1000:
            enacted_col = c
            break
    sched_col = "scheduled_basal_rate" if "scheduled_basal_rate" in df.columns else None

    print(f"Basal columns: enacted={enacted_col}, scheduled={sched_col}")
    return enacted_col, sched_col


def _extract_window(df_patient, event_time, n_steps=MAX_STEPS):
    """Extract data window around correction event."""
    t0 = pd.Timestamp(event_time)
    # Pre-correction window (1h before) + post-correction (6h after)
    pre_start = t0 - pd.Timedelta(hours=1)
    post_end = t0 + pd.Timedelta(minutes=5 * n_steps)
    mask = (df_patient["time"] >= pre_start) & (df_patient["time"] < post_end)
    seg = df_patient.loc[mask].copy()
    if len(seg) < 20:
        return None
    seg["minutes_from_correction"] = (seg["time"] - t0).dt.total_seconds() / 60
    return seg


def _compute_modulation_metrics(seg, enacted_col, sched_col):
    """Compute controller modulation metrics in different time windows."""
    if enacted_col is None or sched_col is None:
        return None

    enacted = seg[enacted_col].dropna()
    scheduled = seg[sched_col].dropna()

    if len(enacted) < 5 or len(scheduled) < 5:
        return None

    # Align on common index
    common_idx = enacted.index.intersection(scheduled.index)
    if len(common_idx) < 5:
        return None

    e = enacted.loc[common_idx]
    s = scheduled.loc[common_idx]
    minutes = seg.loc[common_idx, "minutes_from_correction"]

    results = {}

    # Window-based metrics
    windows = {
        "pre_1h": (-60, 0),
        "post_0_1h": (0, 60),
        "post_1_2h": (60, 120),
        "post_2_4h": (120, 240),
        "post_4_6h": (240, 360),
    }

    for wname, (t_start, t_end) in windows.items():
        w_mask = (minutes >= t_start) & (minutes < t_end)
        e_w = e.loc[w_mask]
        s_w = s.loc[w_mask]

        if len(e_w) < 3 or s_w.mean() < 0.01:
            results[wname] = {
                "modulation_ratio": np.nan,
                "mean_enacted": np.nan,
                "mean_scheduled": np.nan,
                "abs_deviation": np.nan,
                "n_points": int(len(e_w)),
            }
            continue

        mod_ratio = float(e_w.mean() / s_w.mean())
        abs_dev = float(np.mean(np.abs(e_w.values - s_w.values)))

        results[wname] = {
            "modulation_ratio": mod_ratio,
            "mean_enacted": float(e_w.mean()),
            "mean_scheduled": float(s_w.mean()),
            "abs_deviation": abs_dev,
            "n_points": int(len(e_w)),
        }

    # Overall aggressiveness: max |enacted/scheduled - 1| across post-correction windows
    post_ratios = [results[w]["modulation_ratio"] for w in ["post_0_1h", "post_1_2h", "post_2_4h"]
                   if not np.isnan(results.get(w, {}).get("modulation_ratio", np.nan))]
    if post_ratios:
        results["max_modulation"] = float(max(abs(r - 1) for r in post_ratios))
        results["mean_modulation"] = float(np.mean([abs(r - 1) for r in post_ratios]))
    else:
        results["max_modulation"] = np.nan
        results["mean_modulation"] = np.nan

    return results


def _compute_rebound_metrics(seg):
    """Compute glucose rebound characteristics post-correction."""
    glucose = seg.set_index("minutes_from_correction")["glucose"].dropna()

    if len(glucose) < 20:
        return None

    # Find nadir
    post = glucose.loc[glucose.index >= 30]  # after 30min
    if len(post) < 10:
        return None

    nadir_time = post.idxmin()
    nadir_val = post.loc[nadir_time]

    # Glucose at correction
    near_zero = glucose.loc[(glucose.index >= -5) & (glucose.index <= 5)]
    g0 = float(near_zero.mean()) if len(near_zero) > 0 else np.nan

    # Rebound: max glucose after nadir
    post_nadir = glucose.loc[glucose.index > nadir_time]
    if len(post_nadir) < 3:
        rebound_magnitude = 0
        rebound_time = np.nan
    else:
        rebound_peak = post_nadir.max()
        rebound_magnitude = float(rebound_peak - nadir_val)
        rebound_time = float(post_nadir.idxmax())

    # Glucose CV in 2-6h window
    late = glucose.loc[(glucose.index >= 120) & (glucose.index <= 360)]
    late_cv = float(late.std() / late.mean()) if len(late) > 5 and late.mean() > 0 else np.nan

    return {
        "glucose_at_correction": float(g0),
        "nadir_glucose": float(nadir_val),
        "nadir_time_min": float(nadir_time),
        "correction_drop": float(g0 - nadir_val) if not np.isnan(g0) else np.nan,
        "rebound_magnitude": rebound_magnitude,
        "rebound_time_min": float(rebound_time) if not np.isnan(rebound_time) else np.nan,
        "late_glucose_cv": late_cv,
    }


def run():
    events, df = _load_data()
    enacted_col, sched_col = _get_basal_columns(df)

    all_results = []
    per_patient = {}

    for pid in FULL_PATIENTS:
        df_p = df[df["patient_id"] == pid]
        if len(df_p) == 0:
            continue

        p_events = [e for e in events if e.get("patient_id") == pid]
        if not p_events:
            print(f"  Patient {pid}: 0 events, skipping")
            continue

        p_modulations = []
        p_rebounds = []
        p_gains = []
        p_cvs = []

        for ev in p_events:
            t0 = ev.get("time") or ev.get("timestamp") or ev.get("correction_time")
            if t0 is None:
                continue

            seg = _extract_window(df_p, t0)
            if seg is None:
                continue

            mod = _compute_modulation_metrics(seg, enacted_col, sched_col)
            reb = _compute_rebound_metrics(seg)
            if mod is None or reb is None:
                continue

            event_result = {
                "patient_id": pid,
                "correction_time": str(t0),
                "modulation": mod,
                "rebound": reb,
            }
            all_results.append(event_result)

            if not np.isnan(mod.get("max_modulation", np.nan)):
                p_modulations.append(mod["max_modulation"])
            if not np.isnan(reb.get("rebound_magnitude", np.nan)):
                p_rebounds.append(reb["rebound_magnitude"])
            if not np.isnan(mod.get("mean_modulation", np.nan)) and not np.isnan(reb.get("late_glucose_cv", np.nan)):
                p_gains.append(mod["mean_modulation"])
                p_cvs.append(reb["late_glucose_cv"])

        per_patient[pid] = {
            "n_events": len([r for r in all_results if r["patient_id"] == pid]),
            "mean_max_modulation": float(np.mean(p_modulations)) if p_modulations else np.nan,
            "mean_rebound": float(np.mean(p_rebounds)) if p_rebounds else np.nan,
            "aggressiveness": float(np.mean(p_modulations)) if p_modulations else np.nan,
        }
        n = per_patient[pid]["n_events"]
        agg = per_patient[pid]["aggressiveness"]
        print(f"  Patient {pid}: {n} events, aggressiveness = {agg:.3f}")

    # === Hypothesis Tests ===
    print("\n=== HYPOTHESIS TESTS ===\n")

    # H1: Modulation amplitude predicts rebound (r > 0.3)
    mods = [r["modulation"]["max_modulation"] for r in all_results
            if not np.isnan(r["modulation"].get("max_modulation", np.nan))]
    rebs = [r["rebound"]["rebound_magnitude"] for r in all_results
            if not np.isnan(r["modulation"].get("max_modulation", np.nan))
            and not np.isnan(r["rebound"].get("rebound_magnitude", np.nan))]
    # Align lengths
    paired = [(r["modulation"]["max_modulation"], r["rebound"]["rebound_magnitude"])
              for r in all_results
              if not np.isnan(r["modulation"].get("max_modulation", np.nan))
              and not np.isnan(r["rebound"].get("rebound_magnitude", np.nan))]
    if len(paired) > 10:
        m_arr, r_arr = zip(*paired)
        r_mod_reb, p_mod_reb = stats.pearsonr(m_arr, r_arr)
        h1_pass = r_mod_reb > 0.3
        print(f"H1: Modulation amplitude vs rebound magnitude")
        print(f"    r = {r_mod_reb:.3f}, p = {p_mod_reb:.4f}, n = {len(paired)}")
        print(f"    → {'PASS' if h1_pass else 'FAIL'}")
    else:
        r_mod_reb, p_mod_reb = np.nan, np.nan
        h1_pass = False
        print(f"H1: Insufficient paired data (n={len(paired)})")

    # H2: Aggressiveness varies >3× across patients
    agg_vals = [v["aggressiveness"] for v in per_patient.values()
                if not np.isnan(v.get("aggressiveness", np.nan))]
    if len(agg_vals) >= 3:
        agg_range = max(agg_vals) / min(agg_vals) if min(agg_vals) > 0 else np.inf
        h2_pass = agg_range > 3.0
        print(f"\nH2: Controller aggressiveness range across patients")
        print(f"    Min = {min(agg_vals):.3f}, Max = {max(agg_vals):.3f}, Ratio = {agg_range:.1f}×")
        print(f"    → {'PASS' if h2_pass else 'FAIL'}")
    else:
        agg_range = np.nan
        h2_pass = False
        print(f"\nH2: Insufficient patient data (n={len(agg_vals)})")

    # H3: Higher gain → more glucose CV (r > 0.2)
    gain_cv_pairs = [(r["modulation"]["mean_modulation"], r["rebound"]["late_glucose_cv"])
                     for r in all_results
                     if not np.isnan(r["modulation"].get("mean_modulation", np.nan))
                     and not np.isnan(r["rebound"].get("late_glucose_cv", np.nan))]
    if len(gain_cv_pairs) > 10:
        g_arr, cv_arr = zip(*gain_cv_pairs)
        r_gain_cv, p_gain_cv = stats.pearsonr(g_arr, cv_arr)
        h3_pass = r_gain_cv > 0.2
        print(f"\nH3: Controller gain vs late glucose CV")
        print(f"    r = {r_gain_cv:.3f}, p = {p_gain_cv:.4f}, n = {len(gain_cv_pairs)}")
        print(f"    → {'PASS' if h3_pass else 'FAIL'}")
    else:
        r_gain_cv, p_gain_cv = np.nan, np.nan
        h3_pass = False
        print(f"\nH3: Insufficient data (n={len(gain_cv_pairs)})")

    # === Window-level modulation patterns ===
    window_names = ["pre_1h", "post_0_1h", "post_1_2h", "post_2_4h", "post_4_6h"]
    window_ratios = {}
    for wn in window_names:
        ratios = [r["modulation"][wn]["modulation_ratio"]
                  for r in all_results
                  if wn in r["modulation"]
                  and not np.isnan(r["modulation"][wn].get("modulation_ratio", np.nan))]
        if ratios:
            window_ratios[wn] = {
                "mean_ratio": float(np.mean(ratios)),
                "std": float(np.std(ratios)),
                "median": float(np.median(ratios)),
                "n": len(ratios),
            }
            print(f"\n  Window {wn}: ratio = {np.mean(ratios):.3f} ± {np.std(ratios):.3f} (n={len(ratios)})")

    summary = {
        "experiment": "EXP-2632",
        "title": "Controller Gain from Enacted vs Scheduled Basals",
        "enacted_column": enacted_col,
        "scheduled_column": sched_col,
        "n_events": len(all_results),
        "n_patients": len(per_patient),
        "hypotheses": {
            "H1": {
                "statement": "Modulation amplitude predicts rebound (r > 0.3)",
                "result": "PASS" if h1_pass else "FAIL",
                "r": float(r_mod_reb) if not np.isnan(r_mod_reb) else None,
                "p_value": float(p_mod_reb) if not np.isnan(p_mod_reb) else None,
            },
            "H2": {
                "statement": "Aggressiveness varies >3× across patients",
                "result": "PASS" if h2_pass else "FAIL",
                "range_ratio": float(agg_range) if not np.isnan(agg_range) else None,
                "patient_values": {pid: float(v["aggressiveness"])
                                   for pid, v in per_patient.items()
                                   if not np.isnan(v.get("aggressiveness", np.nan))},
            },
            "H3": {
                "statement": "Higher gain → more glucose CV (r > 0.2)",
                "result": "PASS" if h3_pass else "FAIL",
                "r": float(r_gain_cv) if not np.isnan(r_gain_cv) else None,
                "p_value": float(p_gain_cv) if not np.isnan(p_gain_cv) else None,
            },
        },
        "window_modulation": window_ratios,
        "per_patient": per_patient,
    }

    os.makedirs(OUT.parent, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    run()
