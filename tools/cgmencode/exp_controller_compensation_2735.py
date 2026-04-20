#!/usr/bin/env python3
"""
EXP-2735: Controller Compensation via Statistical Replay
=========================================================

The ISF hierarchy shows a 2.5× gap between simulator ISF (14) and profile ISF (55)
attributable to controller compensation — after a correction bolus, the controller
suspends basal and withholds SMBs, reducing net insulin delivered.

EXP-2727 found: during corrections, excess_basal averages -3.51 U over 6h (171%
suspension of scheduled basal). This experiment quantifies the compensation more
precisely and tests whether accounting for it closes the ISF gap.

APPROACH (statistical, not algorithmic replay):
1. For each correction episode, compute "counterfactual insulin" — what WOULD have
   been delivered if the controller had maintained scheduled basal (no suspension).
2. Compute compensation ratio = actual_net_insulin / counterfactual_insulin
3. Adjust simulator ISF by compensation ratio → "compensated ISF"
4. Test whether compensated ISF ≈ profile ISF (closing the gap)

Also: use oref0_predict.js bridge (if Node available) to get oref0's recommended
temp basal for a sample of episodes, validating the statistical approach.

HYPOTHESES:
  H1: Controller suspends >50% of scheduled basal during corrections
  H2: Compensation ratio is consistent across patients (CV < 0.3)
  H3: Compensated ISF is within 2× of profile ISF (vs 3.4× for simulator ISF)
  H4: Compensation correlates with controller type (Loop vs Trio vs AAPS)
  H5: Compensated ISF × compensation ratio ≈ profile ISF (multiplicative model)
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.deconfounding import STEPS_PER_HOUR
from production.forward_simulator import (
    TherapySettings, InsulinEvent, forward_simulate,
)

EXP_ID = "2735"
TITLE = "Controller Compensation via Statistical Replay"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/controller-compensation")

BG_FLOOR = 150.0
HORIZONS = [2, 4, 6]  # hours
MIN_SPACING_STEPS = int(2 * STEPS_PER_HOUR)


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)]
    print(f"Loaded {len(grid)} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_compensation_episodes(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract correction episodes with detailed insulin accounting."""
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_excess_basal = "excess_basal" in grid.columns
    has_sched_basal = "scheduled_basal_rate" in grid.columns
    has_iob = "iob" in grid.columns
    has_isf = "scheduled_isf" in grid.columns

    max_h_steps = int(max(HORIZONS) * STEPS_PER_HOUR)
    all_events = []

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < max_h_steps + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        excess_basal = pg["excess_basal"].values if has_excess_basal else np.zeros(len(pg))
        sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.full(len(pg), np.nan)
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        controller = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        last_idx = -MIN_SPACING_STEPS - 1
        for i in range(len(pg) - max_h_steps):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue
            if "carbs" in pg.columns:
                c_start = max(0, i - STEPS_PER_HOUR)
                c_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue
            if i - last_idx < MIN_SPACING_STEPS:
                continue
            last_idx = i

            event = {
                "patient_id": pid,
                "controller": controller,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "profile_isf": float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan,
                "user_bolus": float(bolus[i]),
            }

            for h in HORIZONS:
                h_steps = int(h * STEPS_PER_HOUR)
                end_idx = i + h_steps
                bg_end = glucose[end_idx]
                if np.isnan(bg_end):
                    continue
                hk = f"{h}h"

                observed_drop = bg0 - bg_end
                event[f"observed_drop_{hk}"] = float(observed_drop)

                # Detailed insulin accounting
                total_bolus = float(np.nansum(bolus[i:end_idx]))
                total_smb = float(np.nansum(smb[i:end_idx]))
                total_excess_basal_u = float(np.nansum(excess_basal[i:end_idx])) * (5.0 / 60.0)
                total_net_basal_u = float(np.nansum(net_basal[i:end_idx])) * (5.0 / 60.0)
                sched_basal_u = float(np.nansum(sched_basal[i:end_idx])) * (5.0 / 60.0)

                # Actual net insulin delivered
                actual_net_insulin = total_bolus + total_smb + total_net_basal_u
                event[f"actual_net_insulin_{hk}"] = actual_net_insulin
                event[f"total_bolus_{hk}"] = total_bolus
                event[f"total_smb_{hk}"] = total_smb
                event[f"net_basal_u_{hk}"] = total_net_basal_u
                event[f"excess_basal_u_{hk}"] = total_excess_basal_u
                event[f"sched_basal_u_{hk}"] = sched_basal_u

                # Counterfactual: if controller maintained scheduled basal
                # (no suspension, no extra temp basal)
                counterfactual_insulin = total_bolus + total_smb + sched_basal_u
                event[f"counterfactual_insulin_{hk}"] = counterfactual_insulin

                # Compensation ratio: how much did controller reduce insulin?
                if counterfactual_insulin > 0.1:
                    comp_ratio = actual_net_insulin / counterfactual_insulin
                else:
                    comp_ratio = 1.0
                event[f"compensation_ratio_{hk}"] = comp_ratio

                # Basal suspension fraction
                if sched_basal_u > 0.01:
                    basal_suspension = 1.0 - (total_net_basal_u / sched_basal_u)
                else:
                    basal_suspension = 0.0
                event[f"basal_suspension_{hk}"] = basal_suspension

                # ISF from different accounting methods
                if total_bolus > 0.1:
                    event[f"isf_bolus_only_{hk}"] = observed_drop / total_bolus
                if actual_net_insulin > 0.1:
                    event[f"isf_net_actual_{hk}"] = observed_drop / actual_net_insulin
                if counterfactual_insulin > 0.1:
                    event[f"isf_counterfactual_{hk}"] = observed_drop / counterfactual_insulin

            all_events.append(event)

    return pd.DataFrame(all_events)


def fit_simulator_isf(episodes: pd.DataFrame, sample_size=500) -> pd.DataFrame:
    """Fit ISF per episode using forward simulator (from EXP-2733 approach)."""
    has_smb = "total_smb_2h" in episodes.columns

    if len(episodes) > sample_size:
        rng = np.random.RandomState(42)
        sample = episodes.iloc[rng.choice(len(episodes), sample_size, replace=False)].copy()
    else:
        sample = episodes.copy()

    results = []
    for _, ep in sample.iterrows():
        bg0 = ep["bg0"]
        profile_isf = ep.get("profile_isf", 55.0)
        if np.isnan(profile_isf) or profile_isf <= 0:
            profile_isf = 55.0

        basal_rate = 0.8  # default
        bolus_events = []
        total_bolus = ep.get("total_bolus_2h", ep.get("user_bolus", 0))
        if total_bolus > 0:
            bolus_events.append(InsulinEvent(time_minutes=0, units=float(total_bolus)))

        total_smb = ep.get("total_smb_2h", 0)
        if total_smb > 0:
            bolus_events.append(InsulinEvent(time_minutes=15, units=float(total_smb), is_bolus=False))

        iob_start = ep.get("iob_start", 0)
        hour = ep.get("hour", 12.0)

        # Target: 2h observed drop
        drop_2h = ep.get("observed_drop_2h", np.nan)
        if np.isnan(drop_2h):
            continue
        actual_end_2h = bg0 - drop_2h

        def sim_error(isf_val):
            settings = TherapySettings(isf=isf_val, cr=10.0, basal_rate=basal_rate, dia_hours=5.0)
            try:
                result = forward_simulate(
                    initial_glucose=bg0, settings=settings, duration_hours=2.0,
                    start_hour=hour, bolus_events=bolus_events,
                    initial_iob=float(iob_start), metabolic_basal_rate=basal_rate,
                    counter_reg_k=0.3, egp_enabled=True,
                )
                sim_end = result.glucose[min(24, len(result.glucose) - 1)]
                return abs(sim_end - actual_end_2h)
            except Exception:
                return 1000.0

        # Grid search then refine
        best_isf, best_err = 10.0, 1000.0
        for isf_try in np.arange(5, 200, 5):
            err = sim_error(isf_try)
            if err < best_err:
                best_isf, best_err = isf_try, err

        # Refine with golden section
        try:
            res = optimize.minimize_scalar(sim_error, bounds=(max(2, best_isf - 10), best_isf + 10),
                                           method="bounded", options={"maxiter": 30})
            if res.fun < best_err:
                best_isf, best_err = float(res.x), float(res.fun)
        except Exception:
            pass

        comp_ratio = ep.get("compensation_ratio_2h", 1.0)
        compensated_isf = best_isf / comp_ratio if comp_ratio > 0.01 else best_isf

        results.append({
            "patient_id": ep["patient_id"],
            "controller": ep["controller"],
            "simulator_isf": best_isf,
            "sim_mae": best_err,
            "compensation_ratio": comp_ratio,
            "compensated_isf": compensated_isf,
            "profile_isf": profile_isf,
            "bg0": bg0,
            "drop_2h": drop_2h,
            "total_dose": total_bolus + total_smb,
        })

    return pd.DataFrame(results)


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()

    # ── Extract episodes ─────────────────────────────────────────
    episodes = extract_compensation_episodes(grid)
    print(f"Extracted {len(episodes)} episodes, {episodes['patient_id'].nunique()} patients")

    # ── Compensation Analysis ────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  CONTROLLER COMPENSATION ANALYSIS")
    print(f"{'=' * 60}")

    compensation_summary = {}
    for h in HORIZONS:
        hk = f"{h}h"
        comp_col = f"compensation_ratio_{hk}"
        susp_col = f"basal_suspension_{hk}"

        valid = episodes.dropna(subset=[comp_col])
        if len(valid) < 10:
            continue

        comp = valid[comp_col]
        susp = valid[susp_col]

        print(f"\n  {hk} Horizon:")
        print(f"    Compensation ratio: median={comp.median():.3f}, mean={comp.mean():.3f}, "
              f"std={comp.std():.3f}, CV={comp.std()/comp.mean():.3f}")
        print(f"    Basal suspension: median={susp.median():.1%}, mean={susp.mean():.1%}")

        # Per-controller
        for ctrl in sorted(valid["controller"].unique()):
            cv = valid[valid["controller"] == ctrl]
            cc = cv[comp_col]
            cs = cv[susp_col]
            print(f"    {ctrl:>10}: comp_ratio={cc.median():.3f}, suspension={cs.median():.1%}, n={len(cv)}")

        # Per-patient median compensation
        pat_comp = valid.groupby("patient_id")[comp_col].median()
        print(f"    Per-patient: median comp={pat_comp.median():.3f}, IQR=[{pat_comp.quantile(0.25):.3f}, {pat_comp.quantile(0.75):.3f}]")
        print(f"    CV of per-patient medians: {pat_comp.std()/pat_comp.mean():.3f}")

        # ISF from different accounting methods
        isf_cols = [f"isf_bolus_only_{hk}", f"isf_net_actual_{hk}", f"isf_counterfactual_{hk}"]
        print(f"\n    ISF accounting:")
        for col in isf_cols:
            if col in valid.columns:
                vals = valid[col].dropna()
                vals = vals[(vals > 0) & (vals < 500)]
                if len(vals) > 10:
                    print(f"      {col}: median={vals.median():.1f}, mean={vals.mean():.1f}")

        compensation_summary[hk] = {
            "n_events": len(valid),
            "comp_ratio_median": float(comp.median()),
            "comp_ratio_mean": float(comp.mean()),
            "comp_ratio_cv": float(comp.std() / comp.mean()) if comp.mean() > 0 else np.nan,
            "basal_suspension_median": float(susp.median()),
            "per_patient_comp_median": float(pat_comp.median()),
            "per_patient_comp_cv": float(pat_comp.std() / pat_comp.mean()) if pat_comp.mean() > 0 else np.nan,
        }

    # ── Simulator ISF with compensation correction ───────────────
    print(f"\n{'=' * 60}")
    print("  SIMULATOR ISF + COMPENSATION CORRECTION")
    print(f"{'=' * 60}")

    sim_results = fit_simulator_isf(episodes)
    print(f"  Fitted {len(sim_results)} episodes")

    if len(sim_results) > 0:
        # Aggregate per patient
        pat_sim = sim_results.groupby("patient_id").agg({
            "simulator_isf": "median",
            "compensated_isf": "median",
            "profile_isf": "median",
            "compensation_ratio": "median",
            "controller": "first",
        }).reset_index()

        print(f"\n  Per-patient ISF comparison ({len(pat_sim)} patients):")
        print(f"  {'Patient':<12} {'Ctrl':>6} {'ProfISF':>8} {'SimISF':>7} {'CompR':>6} {'CompISF':>8} {'Gap':>6}")
        print(f"  {'-'*55}")
        for _, r in pat_sim.sort_values("profile_isf").iterrows():
            gap = r["profile_isf"] / r["compensated_isf"] if r["compensated_isf"] > 0 else np.nan
            print(f"  {str(r['patient_id'])[:10]:<12} {r['controller'][:6]:>6} {r['profile_isf']:>8.1f} "
                  f"{r['simulator_isf']:>7.1f} {r['compensation_ratio']:>6.2f} "
                  f"{r['compensated_isf']:>8.1f} {gap:>6.2f}×")

        # Overall summary
        med_sim = pat_sim["simulator_isf"].median()
        med_comp_isf = pat_sim["compensated_isf"].median()
        med_prof = pat_sim["profile_isf"].median()
        print(f"\n  MEDIANS: Profile={med_prof:.1f}, Simulator={med_sim:.1f}, Compensated={med_comp_isf:.1f}")
        print(f"  Gap: Profile/Simulator = {med_prof/med_sim:.2f}×, Profile/Compensated = {med_prof/med_comp_isf:.2f}×")

        # Correlation: compensated ISF vs profile ISF
        valid_both = pat_sim.dropna(subset=["profile_isf", "compensated_isf"])
        valid_both = valid_both[(valid_both["profile_isf"] > 0) & (valid_both["compensated_isf"] > 0)]
        if len(valid_both) > 5:
            r_comp, p_comp = stats.pearsonr(valid_both["profile_isf"], valid_both["compensated_isf"])
            r_sim, p_sim = stats.pearsonr(valid_both["profile_isf"], valid_both["simulator_isf"])
            print(f"\n  Profile ↔ Simulator ISF: r={r_sim:.3f} (p={p_sim:.4f})")
            print(f"  Profile ↔ Compensated ISF: r={r_comp:.3f} (p={p_comp:.4f})")
        else:
            r_comp, p_comp, r_sim, p_sim = 0, 1, 0, 1

        sim_summary = {
            "n_episodes": len(sim_results),
            "n_patients": len(pat_sim),
            "median_simulator_isf": float(med_sim),
            "median_compensated_isf": float(med_comp_isf),
            "median_profile_isf": float(med_prof),
            "gap_profile_sim": float(med_prof / med_sim) if med_sim > 0 else np.nan,
            "gap_profile_comp": float(med_prof / med_comp_isf) if med_comp_isf > 0 else np.nan,
            "r_profile_compensated": float(r_comp),
            "r_profile_simulator": float(r_sim),
        }
    else:
        sim_summary = {}
        pat_sim = pd.DataFrame()

    # ── Hypotheses ───────────────────────────────────────────────
    comp_2h = compensation_summary.get("2h", {})

    # H1: Controller suspends >50% of scheduled basal during corrections
    h1_pass = comp_2h.get("basal_suspension_median", 0) > 0.50

    # H2: Compensation ratio consistent across patients (CV < 0.3)
    h2_pass = comp_2h.get("per_patient_comp_cv", 999) < 0.3

    # H3: Compensated ISF within 2× of profile (vs 3.4× for simulator)
    gap_comp = sim_summary.get("gap_profile_comp", 999)
    h3_pass = gap_comp < 2.0

    # H4: Compensation correlates with controller type
    h4_pass = False
    if len(episodes) > 0 and "compensation_ratio_2h" in episodes.columns:
        ctrl_groups = episodes.groupby("controller")["compensation_ratio_2h"].median()
        if len(ctrl_groups) >= 2:
            h4_pass = ctrl_groups.max() - ctrl_groups.min() > 0.05

    # H5: Multiplicative model: simulator_ISF × (1/comp_ratio) ≈ profile_ISF
    gap_sim = sim_summary.get("gap_profile_sim", 999)
    h5_pass = gap_comp < gap_sim * 0.7  # at least 30% reduction in gap

    hypotheses = {
        "H1_basal_suspension_gt_50pct": bool(h1_pass),
        "H2_compensation_consistent": bool(h2_pass),
        "H3_compensated_isf_within_2x": bool(h3_pass),
        "H4_controller_type_matters": bool(h4_pass),
        "H5_multiplicative_model_helps": bool(h5_pass),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Compensation ratio={comp_2h.get('comp_ratio_median', '?'):.3f}, "
               f"Basal suspension={comp_2h.get('basal_suspension_median', 0):.1%}. "
               f"Gap: sim {sim_summary.get('gap_profile_sim', '?'):.2f}× → "
               f"compensated {sim_summary.get('gap_profile_comp', '?'):.2f}×")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    # ── Save ─────────────────────────────────────────────────────
    out_path = RESULTS_DIR / f"exp-{EXP_ID}_controller_compensation.json"

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(clean({
            "exp_id": EXP_ID, "title": TITLE,
            "hypotheses": hypotheses,
            "compensation_summary": compensation_summary,
            "simulator_summary": sim_summary,
            "per_patient": pat_sim.to_dict(orient="records") if len(pat_sim) > 0 else [],
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out_path}")

    # Dashboard
    create_dashboard(compensation_summary, sim_summary, pat_sim, hypotheses, episodes)

    return hypotheses


def create_dashboard(comp_summary, sim_summary, pat_sim, hypotheses, episodes):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 14))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Panel 1: Compensation ratio distribution by horizon
    ax1 = fig.add_subplot(gs[0, 0])
    for h_idx, h in enumerate(HORIZONS):
        hk = f"{h}h"
        col = f"compensation_ratio_{hk}"
        if col in episodes.columns:
            vals = episodes[col].dropna()
            vals = vals[(vals > 0) & (vals < 3)]
            ax1.hist(vals, bins=30, alpha=0.5, label=hk, density=True)
    ax1.axvline(1.0, color="red", linewidth=2, linestyle="--", label="No compensation")
    ax1.set_xlabel("Compensation Ratio (actual/counterfactual)")
    ax1.set_ylabel("Density")
    ax1.set_title("Controller Compensation Ratio")
    ax1.legend(fontsize=8)

    # Panel 2: Basal suspension distribution
    ax2 = fig.add_subplot(gs[0, 1])
    col = "basal_suspension_2h"
    if col in episodes.columns:
        vals = episodes[col].dropna()
        vals = vals[(vals > -1) & (vals < 2)]
        ax2.hist(vals * 100, bins=30, color="steelblue", edgecolor="white", alpha=0.8)
        ax2.axvline(0, color="black", linewidth=0.5)
        ax2.axvline(vals.median() * 100, color="orange", linewidth=2, label=f"Median: {vals.median():.0%}")
        ax2.set_xlabel("Basal Suspension (%)")
        ax2.set_ylabel("Episodes")
        ax2.set_title("2h: Basal Suspension During Corrections")
        ax2.legend(fontsize=8)

    # Panel 3: Compensation by controller type
    ax3 = fig.add_subplot(gs[0, 2])
    col = "compensation_ratio_2h"
    if col in episodes.columns:
        ctrl_data = []
        ctrl_labels = []
        for ctrl in sorted(episodes["controller"].unique()):
            vals = episodes[episodes["controller"] == ctrl][col].dropna()
            vals = vals[(vals > 0) & (vals < 3)]
            if len(vals) > 10:
                ctrl_data.append(vals.values)
                ctrl_labels.append(ctrl)
        if ctrl_data:
            ax3.boxplot(ctrl_data, labels=ctrl_labels)
            ax3.axhline(1.0, color="red", linewidth=1, linestyle="--")
            ax3.set_ylabel("Compensation Ratio")
            ax3.set_title("Compensation by Controller")

    # Panel 4: Profile ISF vs Compensated ISF
    ax4 = fig.add_subplot(gs[1, 0])
    if len(pat_sim) > 0:
        valid = pat_sim.dropna(subset=["profile_isf", "compensated_isf"])
        valid = valid[(valid["compensated_isf"] > 0) & (valid["compensated_isf"] < 500)]
        if len(valid) > 3:
            ax4.scatter(valid["profile_isf"], valid["compensated_isf"], color="steelblue", alpha=0.7, s=60)
            lims = [0, max(valid["profile_isf"].max(), valid["compensated_isf"].max()) * 1.1]
            ax4.plot(lims, lims, "r--", linewidth=1, label="1:1")
            ax4.set_xlabel("Profile ISF (mg/dL/U)")
            ax4.set_ylabel("Compensated ISF (mg/dL/U)")
            ax4.set_title("Profile vs Compensated ISF")
            ax4.legend(fontsize=8)

    # Panel 5: ISF gap reduction waterfall
    ax5 = fig.add_subplot(gs[1, 1])
    if sim_summary:
        categories = ["Empirical\n(6)", "Simulator\n(sim)", "Compensated\n(comp)", "Profile\n(prof)"]
        values = [6.0, sim_summary.get("median_simulator_isf", 14),
                  sim_summary.get("median_compensated_isf", 30),
                  sim_summary.get("median_profile_isf", 55)]
        colors = ["#e74c3c", "#f39c12", "#2ecc71", "#3498db"]
        ax5.bar(range(len(categories)), values, color=colors, edgecolor="white")
        ax5.set_xticks(range(len(categories)))
        ax5.set_xticklabels(categories, fontsize=9)
        ax5.set_ylabel("ISF (mg/dL/U)")
        ax5.set_title("ISF Gap Decomposition")
        for i, v in enumerate(values):
            ax5.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=9, fontweight="bold")

    # Panel 6: Per-patient gap (profile/compensated)
    ax6 = fig.add_subplot(gs[1, 2])
    if len(pat_sim) > 0:
        valid = pat_sim.dropna(subset=["profile_isf", "compensated_isf"])
        valid = valid[valid["compensated_isf"] > 0]
        if len(valid) > 3:
            gaps = valid["profile_isf"] / valid["compensated_isf"]
            ax6.hist(gaps.clip(0, 10), bins=20, color="steelblue", edgecolor="white", alpha=0.8)
            ax6.axvline(1.0, color="red", linewidth=2, linestyle="--", label="Perfect (1.0)")
            ax6.axvline(gaps.median(), color="orange", linewidth=2, label=f"Median: {gaps.median():.2f}×")
            ax6.set_xlabel("Gap: Profile ISF / Compensated ISF")
            ax6.set_ylabel("Patients")
            ax6.set_title("Remaining ISF Gap After Compensation")
            ax6.legend(fontsize=8)

    # Row 3: Summary
    ax7 = fig.add_subplot(gs[2, :])
    ax7.axis("off")
    lines = [f"EXP-{EXP_ID}: {TITLE}", ""]
    lines.append(f"Episodes: {len(episodes)}, Patients: {episodes['patient_id'].nunique()}")
    lines.append("")
    for hk in ["2h", "4h", "6h"]:
        d = comp_summary.get(hk, {})
        if d:
            lines.append(f"{hk}: comp_ratio={d.get('comp_ratio_median', 0):.3f}, "
                        f"suspension={d.get('basal_suspension_median', 0):.1%}, "
                        f"n={d.get('n_events', 0)}")
    lines.append("")
    if sim_summary:
        lines.append(f"ISF: Simulator={sim_summary.get('median_simulator_isf', '?'):.1f}, "
                     f"Compensated={sim_summary.get('median_compensated_isf', '?'):.1f}, "
                     f"Profile={sim_summary.get('median_profile_isf', '?'):.1f}")
        lines.append(f"Gap: sim {sim_summary.get('gap_profile_sim', '?'):.2f}× → "
                     f"compensated {sim_summary.get('gap_profile_comp', '?'):.2f}×")
    lines.append("")
    lines.append("Hypotheses:")
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")

    ax7.text(0.05, 0.95, "\n".join(lines), transform=ax7.transAxes,
             fontsize=9, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VIZ_DIR / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
