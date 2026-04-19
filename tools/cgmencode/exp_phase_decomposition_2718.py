#!/usr/bin/env python3
"""
EXP-2718: Correction Phase Decomposition — Insulin Activity vs BG Response
===========================================================================

Motivated by EXP-2717/2717b finding that ISF = BG_drop / excess_insulin
DECREASES with horizon. This is paradoxical unless the insulin and BG drop
occur at DIFFERENT times within the window.

Hypothesis: A correction event has distinct phases:
  Phase 1 (0-2h): Peak insulin delivery + peak BG drop
  Phase 2 (2-4h): Controller suspension/reduction + BG stabilization
  Phase 3 (4-6h): Low insulin + possible EGP-driven rise

If BG drop is concentrated in Phase 1 while insulin accumulates across all
phases, then the apparent ISF = total_drop / total_insulin will be diluted
by post-correction insulin that doesn't contribute additional drop.

The RIGHT approach: compute ISF using INCREMENTAL drop and INCREMENTAL insulin
within each phase. Phase 1 ISF should be closer to profile than whole-window ISF.

Additional multi-factor deconfounding:
  - Subtract BG₀ controller-dose confound at each phase boundary
  - Track EGP headwind contribution per phase
  - Compute insulin activity (not just delivery) per phase
  - Track controller state transitions (active correction → suspension)

Causal frame (T1D):
  - Insulin delivered in Phase 1 has residual activity in Phase 2-3
  - Phase 2-3 insulin is RESPONSE to the drop, not additional correction
  - The controller suspends precisely BECAUSE glucose dropped
  - This feedback creates the ISF dilution at longer horizons
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.deconfounding import STEPS_PER_HOUR

EXP_ID = "2718"
TITLE = "Correction Phase Decomposition — Insulin Activity vs BG Response"

# Phase boundaries (hours from correction start)
PHASES = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 6)]
PHASE_LABELS = ["0-1h", "1-2h", "2-3h", "3-4h", "4-6h"]

BG_FLOOR = 150.0
DEFAULT_DIA_HOURS = 5.0


@dataclass
class Result:
    exp_id: str
    title: str
    hypotheses: dict
    metrics: dict
    summary: str


def insulin_activity_fraction(t_minutes: float, dia_hours: float = DEFAULT_DIA_HOURS) -> float:
    if t_minutes <= 0:
        return 1.0
    dia_min = dia_hours * 60.0
    if t_minutes >= dia_min:
        return 0.0
    return float(np.exp(-3.0 * t_minutes / dia_min))


def analyze(grid: pd.DataFrame) -> Result:
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_sched_basal = "scheduled_basal_rate" in grid.columns
    has_iob = "iob" in grid.columns
    has_isf = "scheduled_isf" in grid.columns
    has_controller = "controller" in grid.columns

    all_events = []
    patient_profiles = {}

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        max_steps = int(6 * STEPS_PER_HOUR)
        if len(pg) < max_steps + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        controller = pg["controller"].iloc[0] if has_controller else "unknown"

        valid_isf = profile_isf[~np.isnan(profile_isf)]
        if len(valid_isf) > 0:
            patient_profiles[pid] = float(np.median(valid_isf))

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        for i in range(len(pg) - max_steps):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue

            # Carb-free check
            if "carbs" in pg.columns:
                c_start = max(0, i - STEPS_PER_HOUR)
                c_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            event = {
                "patient_id": pid,
                "controller": controller,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "profile_isf": float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan,
                "user_bolus": float(bolus[i]),
            }

            # Track glucose trajectory at phase boundaries
            bg_at_boundary = [bg0]
            for _, end_h in PHASES:
                end_step = i + int(end_h * STEPS_PER_HOUR)
                if end_step < len(glucose):
                    bg_at_boundary.append(float(glucose[end_step]))
                else:
                    bg_at_boundary.append(np.nan)

            # For each phase, compute incremental metrics
            cumulative_excess = 0.0
            cumulative_drop = 0.0

            for phase_idx, ((start_h, end_h), label) in enumerate(zip(PHASES, PHASE_LABELS)):
                start_step = i + int(start_h * STEPS_PER_HOUR)
                end_step = i + int(end_h * STEPS_PER_HOUR)

                if end_step >= len(glucose):
                    break

                bg_start_phase = glucose[start_step]
                bg_end_phase = glucose[end_step]
                if np.isnan(bg_start_phase) or np.isnan(bg_end_phase):
                    continue

                # Incremental BG change in this phase
                phase_drop = float(bg_start_phase - bg_end_phase)  # positive = fell

                # Incremental insulin delivered in this phase
                phase_bolus = float(np.nansum(bolus[start_step:end_step]))
                phase_smb = float(np.nansum(smb[start_step:end_step]))
                phase_net_basal = float(np.nansum(net_basal[start_step:end_step])) / STEPS_PER_HOUR
                phase_excess = phase_bolus + phase_smb + phase_net_basal

                # Insulin ACTIVITY in this phase (from all prior deliveries)
                # This is insulin delivered before and during the phase that is
                # being absorbed during the phase
                phase_activity = 0.0
                for k in range(start_step, end_step):
                    # Activity from all prior deliveries
                    lookback = min(k - i, int(6 * STEPS_PER_HOUR))
                    for j in range(max(0, lookback)):
                        delivery_step = k - j
                        if delivery_step < 0 or delivery_step >= len(bolus):
                            continue
                        t_min = j * 5.0
                        t_min_next = (j + 1) * 5.0
                        # Absorption in this step = activity(t) - activity(t+5min)
                        absorption = (insulin_activity_fraction(t_min) -
                                      insulin_activity_fraction(t_min_next))
                        step_insulin = (float(bolus[delivery_step]) +
                                        float(smb[delivery_step]) +
                                        float(net_basal[delivery_step]) / STEPS_PER_HOUR)
                        phase_activity += step_insulin * absorption

                # IOB at phase boundaries
                iob_start = float(iob[start_step]) if not np.isnan(iob[start_step]) else 0.0
                iob_end = float(iob[end_step]) if not np.isnan(iob[end_step]) else 0.0
                iob_change = iob_end - iob_start

                cumulative_excess += phase_excess
                cumulative_drop += phase_drop

                event[f"drop_{label}"] = phase_drop
                event[f"excess_{label}"] = phase_excess
                event[f"activity_{label}"] = phase_activity
                event[f"iob_start_{label}"] = iob_start
                event[f"iob_change_{label}"] = iob_change
                event[f"bg_{label}"] = float(bg_start_phase)

                # Phase-level ISF
                if phase_excess > 0.01:
                    event[f"isf_delivery_{label}"] = phase_drop / phase_excess
                if phase_activity > 0.01:
                    event[f"isf_activity_{label}"] = phase_drop / phase_activity

                # Cumulative ISF up to this phase
                if cumulative_excess > 0.01:
                    event[f"isf_cumulative_{label}"] = cumulative_drop / cumulative_excess

            # Total 6h metrics
            bg_6h = glucose[i + int(6 * STEPS_PER_HOUR)] if i + int(6 * STEPS_PER_HOUR) < len(glucose) else np.nan
            if not np.isnan(bg_6h):
                event["bg_drop_6h"] = bg0 - bg_6h
                event["bg_6h"] = float(bg_6h)

            all_events.append(event)

    if not all_events:
        return Result(EXP_ID, TITLE, {}, {}, "No events")

    df = pd.DataFrame(all_events)
    n_events = len(df)
    n_patients = df["patient_id"].nunique()
    print(f"  Events: {n_events}, patients: {n_patients}")

    median_profile = float(np.nanmedian(list(patient_profiles.values()))) if patient_profiles else np.nan

    # ── H1: BG drop is concentrated in Phase 1-2 ────────────────
    drop_by_phase = {}
    excess_by_phase = {}
    for label in PHASE_LABELS:
        drop_col = f"drop_{label}"
        exc_col = f"excess_{label}"
        if drop_col in df.columns:
            valid = df[drop_col].dropna()
            drop_by_phase[label] = float(valid.median())
        if exc_col in df.columns:
            valid = df[exc_col].dropna()
            excess_by_phase[label] = float(valid.median())

    total_drop = sum(drop_by_phase.values())
    total_excess = sum(excess_by_phase.values())

    drop_fracs = {k: v / total_drop if total_drop > 0 else 0 for k, v in drop_by_phase.items()}
    excess_fracs = {k: v / total_excess if total_excess > 0 else 0 for k, v in excess_by_phase.items()}

    h1_pass = (drop_fracs.get("0-1h", 0) + drop_fracs.get("1-2h", 0)) > 0.6
    print(f"\n  H1 (drop concentrated in Phase 1-2): {'PASS' if h1_pass else 'FAIL'}")
    print(f"    BG drop by phase (median):  {' | '.join(f'{k}={v:+.1f}' for k, v in drop_by_phase.items())}")
    print(f"    Drop fraction:              {' | '.join(f'{k}={v:.0%}' for k, v in drop_fracs.items())}")
    print(f"    Excess insulin by phase:    {' | '.join(f'{k}={v:.2f}U' for k, v in excess_by_phase.items())}")
    print(f"    Excess fraction:            {' | '.join(f'{k}={v:.0%}' for k, v in excess_fracs.items())}")

    # ── H2: Phase 1 ISF is closer to profile than whole-window ───
    phase_isf_delivery = {}
    phase_isf_activity = {}
    phase_isf_cumulative = {}
    for label in PHASE_LABELS:
        for prefix, target_dict in [("isf_delivery", phase_isf_delivery),
                                     ("isf_activity", phase_isf_activity),
                                     ("isf_cumulative", phase_isf_cumulative)]:
            col = f"{prefix}_{label}"
            if col in df.columns:
                valid = df[col].dropna()
                valid_pos = valid[valid > 0]
                if len(valid_pos) > 10:
                    target_dict[label] = float(valid_pos.median())

    # Check if early-phase ISF is closer to profile
    isf_0_1h = phase_isf_delivery.get("0-1h", np.nan)
    isf_whole = phase_isf_cumulative.get("4-6h", np.nan)
    if not np.isnan(isf_0_1h) and not np.isnan(isf_whole) and median_profile > 0:
        dist_early = abs(isf_0_1h - median_profile)
        dist_whole = abs(isf_whole - median_profile)
        h2_pass = dist_early < dist_whole
    else:
        h2_pass = False

    print(f"\n  H2 (Phase 1 ISF closer to profile): {'PASS' if h2_pass else 'FAIL'}")
    print(f"    Profile ISF: {median_profile:.1f}")
    print(f"    ISF by delivery: {' | '.join(f'{k}={v:.1f}' for k, v in phase_isf_delivery.items())}")
    print(f"    ISF by activity: {' | '.join(f'{k}={v:.1f}' for k, v in phase_isf_activity.items())}")
    print(f"    ISF cumulative:  {' | '.join(f'{k}={v:.1f}' for k, v in phase_isf_cumulative.items())}")

    # ── H3: Controller reduces insulin in Phase 2-3 (suspension) ─
    iob_changes = {}
    for label in PHASE_LABELS:
        col = f"iob_change_{label}"
        if col in df.columns:
            valid = df[col].dropna()
            iob_changes[label] = float(valid.median())

    # Controller should REDUCE IOB in later phases
    h3_pass = (iob_changes.get("2-3h", 0) < iob_changes.get("0-1h", 0) and
               iob_changes.get("3-4h", 0) < iob_changes.get("0-1h", 0))

    print(f"\n  H3 (controller reduces insulin in later phases): {'PASS' if h3_pass else 'FAIL'}")
    print(f"    IOB change by phase: {' | '.join(f'{k}={v:+.3f}U' for k, v in iob_changes.items())}")

    # ── H4: Activity-based ISF is more stable across phases ──────
    if phase_isf_activity and phase_isf_delivery:
        activity_vals = [v for v in phase_isf_activity.values() if v > 0]
        delivery_vals = [v for v in phase_isf_delivery.values() if v > 0]
        if len(activity_vals) >= 3 and len(delivery_vals) >= 3:
            cv_activity = float(np.std(activity_vals) / np.mean(activity_vals))
            cv_delivery = float(np.std(delivery_vals) / np.mean(delivery_vals))
            h4_pass = cv_activity < cv_delivery
        else:
            cv_activity = cv_delivery = np.nan
            h4_pass = False
    else:
        cv_activity = cv_delivery = np.nan
        h4_pass = False

    print(f"\n  H4 (activity-based ISF more stable): {'PASS' if h4_pass else 'FAIL'}")
    print(f"    CV(activity ISF): {cv_activity:.3f}, CV(delivery ISF): {cv_delivery:.3f}")

    # ── H5: Phase 1 ISF × Phase 1 insulin ≈ Phase 1 drop ────────
    # Sanity: does the accounting close within each phase?
    phase_balance = {}
    for label in PHASE_LABELS:
        drop = drop_by_phase.get(label, np.nan)
        exc = excess_by_phase.get(label, np.nan)
        isf = phase_isf_delivery.get(label, np.nan)
        if not np.isnan(drop) and not np.isnan(exc) and not np.isnan(isf):
            predicted = isf * exc
            ratio = predicted / drop if abs(drop) > 0.1 else np.nan
            phase_balance[label] = {
                "actual_drop": drop,
                "predicted_drop": predicted,
                "ratio": ratio,
            }

    h5_pass = any(0.8 < v.get("ratio", 0) < 1.2 for v in phase_balance.values())
    print(f"\n  H5 (phase-level balance closes): {'PASS' if h5_pass else 'FAIL'}")
    for k, v in phase_balance.items():
        print(f"    {k}: actual={v['actual_drop']:.1f}, predicted={v['predicted_drop']:.1f}, "
              f"ratio={v.get('ratio', 'N/A')}")

    # ── Glucose trajectory ───────────────────────────────────────
    bg_trajectory = {}
    for label in PHASE_LABELS:
        col = f"bg_{label}"
        if col in df.columns:
            valid = df[col].dropna()
            bg_trajectory[label] = {
                "median": float(valid.median()),
                "q25": float(valid.quantile(0.25)),
                "q75": float(valid.quantile(0.75)),
            }

    if "bg_6h" in df.columns:
        valid = df["bg_6h"].dropna()
        bg_trajectory["6h_end"] = {
            "median": float(valid.median()),
            "q25": float(valid.quantile(0.25)),
            "q75": float(valid.quantile(0.75)),
        }

    print(f"\n  Glucose trajectory (median):")
    for k, v in bg_trajectory.items():
        print(f"    {k}: {v['median']:.0f} mg/dL [{v['q25']:.0f}-{v['q75']:.0f}]")

    # ── Compile ──────────────────────────────────────────────────
    hypotheses = {
        "H1_drop_concentrated_early": h1_pass,
        "H2_early_isf_closer_to_profile": h2_pass,
        "H3_controller_reduces_later": h3_pass,
        "H4_activity_isf_more_stable": h4_pass,
        "H5_phase_balance_closes": h5_pass,
    }

    metrics = {
        "n_events": n_events,
        "n_patients": n_patients,
        "median_profile_isf": float(median_profile) if not np.isnan(median_profile) else None,
        "drop_by_phase": drop_by_phase,
        "drop_fractions": drop_fracs,
        "excess_by_phase": excess_by_phase,
        "excess_fractions": excess_fracs,
        "isf_by_delivery": phase_isf_delivery,
        "isf_by_activity": phase_isf_activity,
        "isf_cumulative": phase_isf_cumulative,
        "iob_changes": iob_changes,
        "cv_activity_isf": float(cv_activity) if not np.isnan(cv_activity) else None,
        "cv_delivery_isf": float(cv_delivery) if not np.isnan(cv_delivery) else None,
        "phase_balance": phase_balance,
        "bg_trajectory": bg_trajectory,
        "patient_profiles": patient_profiles,
    }

    n_pass = sum(hypotheses.values())
    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. N={n_events}, {n_patients} patients. "
               f"Drop fracs: {' | '.join(f'{k}={v:.0%}' for k, v in drop_fracs.items())}. "
               f"ISF(0-1h)={phase_isf_delivery.get('0-1h', 0):.1f}, "
               f"ISF(4-6h)={phase_isf_cumulative.get('4-6h', 0):.1f}, "
               f"Profile={median_profile:.1f}.")

    return Result(EXP_ID, TITLE, hypotheses, metrics, summary)


# ── Visualization ────────────────────────────────────────────────────

def create_dashboard(result: Result) -> Optional[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return None

    m = result.metrics
    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    profile_isf = m.get("median_profile_isf", 55)

    # Panel 1: Drop and excess by phase (stacked)
    ax1 = fig.add_subplot(gs[0, 0])
    drops = m.get("drop_by_phase", {})
    excesses = m.get("excess_by_phase", {})
    if drops:
        labels = list(drops.keys())
        x = range(len(labels))
        ax1_twin = ax1.twinx()
        bars1 = ax1.bar([i - 0.15 for i in x], [drops[l] for l in labels], 0.3,
                        color="coral", label="BG drop (mg/dL)")
        bars2 = ax1_twin.bar([i + 0.15 for i in x], [excesses.get(l, 0) for l in labels], 0.3,
                             color="steelblue", label="Excess insulin (U)")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(labels, fontsize=8)
        ax1.set_ylabel("BG drop (mg/dL)", color="coral")
        ax1_twin.set_ylabel("Excess insulin (U)", color="steelblue")
        ax1.set_title("BG Drop vs Insulin by Phase")
        ax1.legend(loc="upper left", fontsize=7)
        ax1_twin.legend(loc="upper right", fontsize=7)

    # Panel 2: ISF by phase — delivery vs activity vs cumulative
    ax2 = fig.add_subplot(gs[0, 1])
    isf_del = m.get("isf_by_delivery", {})
    isf_act = m.get("isf_by_activity", {})
    isf_cum = m.get("isf_cumulative", {})
    if isf_del:
        labels = list(isf_del.keys())
        x = range(len(labels))
        if isf_del:
            ax2.plot(x, [isf_del.get(l, np.nan) for l in labels], "o-",
                     color="steelblue", label="By delivery")
        if isf_act:
            ax2.plot(range(len(isf_act)), [isf_act.get(l, np.nan) for l in labels[:len(isf_act)]],
                     "s-", color="coral", label="By activity")
        if isf_cum:
            ax2.plot(range(len(isf_cum)), [isf_cum.get(l, np.nan) for l in labels[:len(isf_cum)]],
                     "D-", color="darkgreen", label="Cumulative")
        if profile_isf:
            ax2.axhline(profile_isf, color="red", linestyle="--", label=f"Profile={profile_isf:.0f}")
        ax2.set_xticks(list(x))
        ax2.set_xticklabels(labels, fontsize=8)
        ax2.set_ylabel("ISF (mg/dL/U)")
        ax2.set_title("ISF Across Correction Phases")
        ax2.legend(fontsize=7)

    # Panel 3: IOB trajectory
    ax3 = fig.add_subplot(gs[0, 2])
    iob_ch = m.get("iob_changes", {})
    if iob_ch:
        labels = list(iob_ch.keys())
        vals = [iob_ch[l] for l in labels]
        colors = ["coral" if v > 0 else "steelblue" for v in vals]
        ax3.bar(range(len(labels)), vals, color=colors)
        ax3.axhline(0, color="black", linewidth=0.5)
        ax3.set_xticks(range(len(labels)))
        ax3.set_xticklabels(labels, fontsize=8)
        ax3.set_ylabel("IOB Change (U)")
        ax3.set_title("Controller IOB Response by Phase")

    # Panel 4: Glucose trajectory
    ax4 = fig.add_subplot(gs[1, 0])
    bg_traj = m.get("bg_trajectory", {})
    if bg_traj:
        labels = list(bg_traj.keys())
        medians = [bg_traj[l]["median"] for l in labels]
        q25 = [bg_traj[l]["q25"] for l in labels]
        q75 = [bg_traj[l]["q75"] for l in labels]
        x = range(len(labels))
        ax4.plot(x, medians, "o-", color="darkgreen", linewidth=2)
        ax4.fill_between(x, q25, q75, alpha=0.2, color="darkgreen")
        ax4.axhline(180, color="red", linestyle=":", alpha=0.5, label="High (180)")
        ax4.axhline(70, color="orange", linestyle=":", alpha=0.5, label="Low (70)")
        ax4.set_xticks(list(x))
        ax4.set_xticklabels(labels, rotation=45, fontsize=7)
        ax4.set_ylabel("Glucose (mg/dL)")
        ax4.set_title("Glucose Trajectory Through Correction")
        ax4.legend(fontsize=7)

    # Panel 5: Drop fraction pie/bar
    ax5 = fig.add_subplot(gs[1, 1])
    drop_fracs = m.get("drop_fractions", {})
    if drop_fracs:
        labels = list(drop_fracs.keys())
        vals = [max(0, drop_fracs[l]) for l in labels]  # Only positive
        if sum(vals) > 0:
            colors = plt.cm.Set3(np.linspace(0, 0.8, len(labels)))
            ax5.pie(vals, labels=labels, colors=colors, autopct="%1.0f%%", startangle=90)
            ax5.set_title("BG Drop Distribution by Phase")

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [
        f"N = {m.get('n_events', 0)} events, {m.get('n_patients', 0)} patients",
        f"Profile ISF = {profile_isf:.1f} mg/dL/U",
        "",
        "Phase ISF (delivery):",
    ]
    for k, v in m.get("isf_by_delivery", {}).items():
        lines.append(f"  {k}: {v:.1f} mg/dL/U")
    lines.append("")
    lines.append("Hypotheses:")
    for k, v in result.hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")

    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=9, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "phase-decomposition"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")
    return str(out_path)


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"\nLoading {data_path}...")
    grid = pd.read_parquet(data_path)
    print(f"  {grid.shape[0]} rows × {grid.shape[1]} cols, {grid['patient_id'].nunique()} patients")

    result = analyze(grid)

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {result.summary}")
    print(f"{'=' * 70}")

    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_phase_decomposition.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(clean({"exp_id": EXP_ID, "title": TITLE,
                         "hypotheses": result.hypotheses,
                         "metrics": result.metrics, "summary": result.summary}), f, indent=2)
    print(f"Saved: {out_path}")

    create_dashboard(result)
    return result


if __name__ == "__main__":
    main()
