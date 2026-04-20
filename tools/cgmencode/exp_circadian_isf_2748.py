#!/usr/bin/env python3
"""
EXP-2748: Time-of-Day ISF Variation
=====================================

Scientific Question
-------------------
Does ISF vary by time of day? Dawn phenomenon (insulin resistance 5-9am)
and diurnal variation are well-documented in diabetes literature. Our
waterfall ISF extraction (EXP-2719b) uses a flat correction factor. Can
time-stratified ISF improve prediction accuracy?

We extract correction episodes at BG≥180 and compute effective ISF by
time-of-day block, then test whether time-stratified ISF schedules improve
MAE over flat ISF.

Predecessors
------------
- EXP-2719b: Waterfall ISF extraction (flat correction factor)
- EXP-2739: ISF validation (68% improve with flat correction)
- EXP-2746: Circadian basal (significant pattern in 77% but small MAE impact)

Hypotheses
----------
H1: ISF varies significantly by time block (ANOVA p<0.05) for >50% of patients
H2: Dawn ISF (5-9am) is >15% lower than afternoon ISF (12-17) for >40%
H3: Time-stratified ISF improves MAE over flat ISF for >40% of patients
H4: Combined time-ISF + integrated pipeline improves for >30%
H5: Safety maintained (TBR not significantly worse)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EXP_2741 = Path("externals/experiments/exp-2741_cr_compensated.json")
EXP_2742 = Path("externals/experiments/exp-2742_egp_personalized_isf.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/circadian-isf")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

CORR_HORIZON = 24  # 2h in 5-min steps
BG_FLOOR = 180

TIME_BLOCKS = {
    "night":     (0, 5),
    "dawn":      (5, 9),
    "morning":   (9, 12),
    "afternoon": (12, 17),
    "evening":   (17, 21),
    "late_night":(21, 24),
}


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    isf_data = json.loads(EXP_2719B.read_text())
    isf_map = {p["patient_id"]: p.get("correction_factor", 1.0)
               for p in isf_data["results"]["2h"]["per_patient"]}

    cr_data = json.loads(EXP_2741.read_text())
    cr_map = {p["patient_id"]: p.get("compensated_cr")
              for p in cr_data["per_patient"]}

    egp_data = json.loads(EXP_2742.read_text())
    egp_map = {p["patient_id"]: p for p in egp_data["per_patient"]}

    return grid, isf_map, cr_map, egp_map


def extract_correction_episodes(pg: pd.DataFrame) -> list:
    """Extract correction episodes at BG≥180 with time-of-day info."""
    episodes = []
    corr_mask = (pg["glucose"] >= BG_FLOOR) & (pg["bolus"] > 0)
    corr_idx = pg.index[corr_mask]

    for idx in corr_idx:
        pos = pg.index.get_loc(idx)
        if pos + CORR_HORIZON >= len(pg):
            continue

        window = pg.iloc[pos:pos + CORR_HORIZON]
        glucose = window["glucose"].values
        if np.isnan(glucose).sum() > len(glucose) * 0.3:
            continue

        bg0 = float(glucose[0])
        bg_end = float(glucose[-1]) if not np.isnan(glucose[-1]) else bg0
        bolus = float(pg.iloc[pos]["bolus"])
        carbs = float(pg.iloc[pos].get("carbs", 0) or 0)
        isf = float(pg.iloc[pos].get("scheduled_isf", 50) or 50)

        # Compute total insulin in window (for deconfounding)
        sched_basal = float(pg.iloc[pos].get("scheduled_basal_rate", 0.8) or 0.8)
        net_basals = window.get("net_basal", pd.Series(sched_basal, index=window.index)).fillna(sched_basal).values
        excess_basal = float(np.sum((net_basals - sched_basal) * (5 / 60)))
        smbs = window.get("bolus_smb", pd.Series(0, index=window.index)).fillna(0).values
        total_smb = float(np.sum(smbs))
        total_insulin = bolus + total_smb + excess_basal

        # BG drop and effective ISF
        bg_drop = bg0 - bg_end
        effective_isf = bg_drop / total_insulin if total_insulin > 0.1 else None

        # Hour of day
        hour = 12
        if "time" in pg.columns:
            try:
                hour = pd.to_datetime(pg.iloc[pos]["time"]).hour
            except Exception:
                pass

        # Time block
        block = "unknown"
        for bname, (start, end) in TIME_BLOCKS.items():
            if start <= hour < end:
                block = bname
                break

        episodes.append({
            "bg0": bg0,
            "bg_end": bg_end,
            "bg_drop": float(bg_drop),
            "bolus": bolus,
            "carbs": carbs,
            "total_insulin": float(total_insulin),
            "effective_isf": float(effective_isf) if effective_isf and effective_isf > 0 else None,
            "scheduled_isf": isf,
            "hour": hour,
            "block": block,
            "trajectory": [float(v) if not np.isnan(v) else None for v in glucose],
        })

    return episodes


def analyze_time_variation(episodes: list) -> dict:
    """Analyze ISF variation across time blocks."""
    valid = [e for e in episodes if e["effective_isf"] is not None and 0 < e["effective_isf"] < 500]
    if len(valid) < 10:
        return {"n_valid": len(valid), "significant": False}

    # Group by time block
    block_isfs = {}
    for e in valid:
        b = e["block"]
        if b not in block_isfs:
            block_isfs[b] = []
        block_isfs[b].append(e["effective_isf"])

    # ANOVA
    groups = [v for v in block_isfs.values() if len(v) >= 3]
    if len(groups) >= 2:
        f_stat, anova_p = stats.f_oneway(*groups)
        if np.isnan(anova_p):
            anova_p = 1.0
    else:
        f_stat, anova_p = 0, 1.0

    # Dawn vs afternoon
    dawn_isf = block_isfs.get("dawn", [])
    afternoon_isf = block_isfs.get("afternoon", [])
    dawn_lower = False
    dawn_ratio = None
    if dawn_isf and afternoon_isf:
        dawn_med = np.median(dawn_isf)
        aft_med = np.median(afternoon_isf)
        if aft_med > 0:
            dawn_ratio = dawn_med / aft_med
            dawn_lower = dawn_med < aft_med * 0.85  # >15% lower

    block_medians = {b: float(np.median(v)) for b, v in block_isfs.items() if v}

    return {
        "n_valid": len(valid),
        "significant": anova_p < 0.05,
        "anova_p": float(anova_p),
        "anova_f": float(f_stat),
        "dawn_lower": dawn_lower,
        "dawn_ratio": float(dawn_ratio) if dawn_ratio else None,
        "block_medians": block_medians,
        "block_counts": {b: len(v) for b, v in block_isfs.items()},
    }


def build_isf_schedule(block_medians: dict, profile_isf: float) -> list:
    """Convert block medians to hourly ISF schedule."""
    schedule = []
    for h in range(24):
        block = "unknown"
        for bname, (start, end) in TIME_BLOCKS.items():
            if start <= h < end:
                block = bname
                break
        isf = block_medians.get(block, profile_isf)
        # Clamp to ±50% of profile
        isf = np.clip(isf, profile_isf * 0.5, profile_isf * 1.5)
        schedule.append((h, float(isf)))
    return schedule


def simulate_episodes(episodes, settings, profile_basal, isf_schedule=None):
    """Simulate correction episodes."""
    maes, tbrs = [], []

    for ep in episodes:
        if isf_schedule:
            s = TherapySettings(
                isf=settings.isf, cr=settings.cr, basal_rate=settings.basal_rate,
                dia_hours=settings.dia_hours, isf_schedule=isf_schedule,
            )
        else:
            s = settings

        bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
        carb_events = [CarbEvent(0, ep["carbs"])] if ep["carbs"] > 0 else []
        duration = CORR_HORIZON * 5 / 60

        try:
            result = forward_simulate(
                initial_glucose=ep["bg0"], settings=s,
                duration_hours=duration, start_hour=ep.get("hour", 12),
                bolus_events=bolus_events, carb_events=carb_events,
                initial_iob=0.0, metabolic_basal_rate=profile_basal,
                counter_reg_k=0.3, egp_enabled=True,
            )
            sim = np.array(result.glucose)
            actual = np.array([v if v is not None else np.nan for v in ep["trajectory"]])
            n = min(len(sim), len(actual))
            valid = ~np.isnan(actual[:n])
            if valid.sum() >= 3:
                maes.append(float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid]))))
                tbrs.append(float(np.sum(sim[:n] < 70)) / n)
        except Exception:
            pass

    if not maes:
        return {"mae": 999.0, "tbr": 0.0}
    return {"mae": float(np.median(maes)), "tbr": float(np.median(tbrs)) * 100}


def main():
    print("=" * 70)
    print("EXP-2748: Time-of-Day ISF Variation")
    print("=" * 70)

    grid, isf_map, cr_map, egp_map = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    results = []
    n_significant = 0
    n_dawn_lower = 0
    n_time_improves = 0
    n_integ_improves = 0
    tbr_diffs = []

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values(
            "time" if "time" in grid.columns else grid.columns[0]
        ).reset_index(drop=True)

        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # ISF/CR/EGP corrections
        isf_cf = isf_map.get(pid, 1.0)
        corrected_isf = float(np.clip(profile_isf / isf_cf, 5, 200))
        comp_cr = cr_map.get(pid)
        safe_cr = max(comp_cr, profile_cr * 0.7) if comp_cr and comp_cr > 0 else profile_cr
        egp_info = egp_map.get(pid, {})
        adj_isf = egp_info.get("adjusted_isf")
        final_isf = float(np.clip(adj_isf, 5, 200)) if adj_isf and adj_isf > 0 else corrected_isf

        episodes = extract_correction_episodes(pg)
        analysis = analyze_time_variation(episodes)

        if analysis.get("significant"):
            n_significant += 1
        if analysis.get("dawn_lower"):
            n_dawn_lower += 1

        # Build ISF schedule from block medians
        block_medians = analysis.get("block_medians", {})
        isf_schedule = build_isf_schedule(block_medians, profile_isf) if block_medians else []

        # Flat ISF schedule from corrected value
        corrected_isf_schedule = build_isf_schedule(
            {b: corrected_isf for b in TIME_BLOCKS}, corrected_isf
        ) if block_medians else []

        # Time-varying corrected ISF: apply correction factor to block medians
        time_corrected = {}
        for b, med in block_medians.items():
            # Scale block median by ratio of corrected/profile
            ratio = corrected_isf / profile_isf if profile_isf > 0 else 1
            time_corrected[b] = med * ratio
        time_isf_schedule = build_isf_schedule(time_corrected, corrected_isf) if time_corrected else []

        # Simulate: profile flat / time-stratified / integrated flat / integrated+time
        settings_profile = TherapySettings(isf=profile_isf, cr=profile_cr, basal_rate=profile_basal, dia_hours=6.0)
        settings_integ = TherapySettings(isf=final_isf, cr=safe_cr, basal_rate=profile_basal, dia_hours=6.0)

        r_profile = simulate_episodes(episodes, settings_profile, profile_basal)
        r_time = simulate_episodes(episodes, settings_profile, profile_basal, isf_schedule=isf_schedule)
        r_integ = simulate_episodes(episodes, settings_integ, profile_basal)
        r_integ_time = simulate_episodes(episodes, settings_integ, profile_basal, isf_schedule=time_isf_schedule)

        time_improves = r_time["mae"] < r_profile["mae"]
        integ_improves = r_integ_time["mae"] < r_integ["mae"]
        if time_improves:
            n_time_improves += 1
        if integ_improves:
            n_integ_improves += 1

        tbr_diffs.append(r_time["tbr"] - r_profile["tbr"])

        entry = {
            "patient_id": pid,
            "n_corrections": len(episodes),
            **analysis,
            "profile_mae": r_profile["mae"],
            "time_mae": r_time["mae"],
            "integrated_mae": r_integ["mae"],
            "integ_time_mae": r_integ_time["mae"],
            "time_improves": time_improves,
            "integ_improves": integ_improves,
            "profile_tbr": r_profile["tbr"],
            "time_tbr": r_time["tbr"],
        }
        results.append(entry)

        sig = "***" if analysis.get("significant") else "   "
        dawn = "D" if analysis.get("dawn_lower") else " "
        print(f"  {pid[:14]:<16} {sig} {dawn} corr={len(episodes):>4} valid={analysis.get('n_valid',0):>4} "
              f"MAE: prof={r_profile['mae']:>5.1f} time={r_time['mae']:>5.1f}{'+'if time_improves else '-'} "
              f"integ={r_integ['mae']:>5.1f}→{r_integ_time['mae']:>5.1f}{'+'if integ_improves else '-'}")

    # Hypotheses
    print(f"\n{'=' * 70}")
    h1 = n_significant / len(patients) > 0.5
    h2 = n_dawn_lower / len(patients) > 0.4
    h3 = n_time_improves / len(patients) > 0.4
    h4 = n_integ_improves / len(patients) > 0.3
    try:
        tbr_p = stats.ttest_1samp(np.array(tbr_diffs), 0)[1]
        if np.isnan(tbr_p): tbr_p = 1.0
    except:
        tbr_p = 1.0
    h5 = tbr_p > 0.05
    passed = sum([h1, h2, h3, h4, h5])
    print(f"HYPOTHESES: {passed}/5 pass")

    hypotheses = {
        "H1_time_varies": {"passed": h1, "n": n_significant, "fraction": n_significant / len(patients)},
        "H2_dawn_lower": {"passed": h2, "n": n_dawn_lower, "fraction": n_dawn_lower / len(patients)},
        "H3_time_improves": {"passed": h3, "n": n_time_improves, "fraction": n_time_improves / len(patients)},
        "H4_integ_improves": {"passed": h4, "n": n_integ_improves, "fraction": n_integ_improves / len(patients)},
        "H5_safety": {"passed": h5, "tbr_p": float(tbr_p)},
    }
    for k, v in hypotheses.items():
        print(f"  {'✓' if v['passed'] else '✗'} {k}")

    print(f"\n  Significant time variation: {n_significant}/{len(patients)}")
    print(f"  Dawn ISF lower: {n_dawn_lower}/{len(patients)}")
    print(f"  Time-stratified improves: {n_time_improves}/{len(patients)}")
    print(f"  Integrated+time improves: {n_integ_improves}/{len(patients)}")
    print(f"  TBR p-value: {tbr_p:.3f}")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2748_circadian_isf.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2748",
            "title": "Time-of-Day ISF Variation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "per_patient": results,
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(results, hypotheses)


def create_dashboard(results, hypotheses):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    rdf = pd.DataFrame(results)
    fig = plt.figure(figsize=(18, 10))
    fig.suptitle("EXP-2748: Time-of-Day ISF Variation", fontsize=14, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: ISF by time block (all patients aggregated)
    ax1 = fig.add_subplot(gs[0, 0])
    all_blocks = {}
    for r in results:
        bm = r.get("block_medians", {})
        for b, v in bm.items():
            if b not in all_blocks: all_blocks[b] = []
            all_blocks[b].append(v)
    if all_blocks:
        block_names = list(TIME_BLOCKS.keys())
        medians = [np.median(all_blocks[b]) if b in all_blocks else 0 for b in block_names]
        ax1.bar(range(len(block_names)), medians, color="steelblue", alpha=0.7)
        ax1.set_xticks(range(len(block_names)))
        ax1.set_xticklabels(block_names, rotation=30, fontsize=8)
        ax1.set_ylabel("Median ISF (mg/dL/U)")
        ax1.set_title("Population ISF by Time Block")

    # Panel 2: Dawn ratio distribution
    ax2 = fig.add_subplot(gs[0, 1])
    ratios = [r.get("dawn_ratio") for r in results if r.get("dawn_ratio") is not None]
    if ratios:
        ax2.hist(ratios, bins=15, color="steelblue", alpha=0.7, edgecolor="black")
        ax2.axvline(1.0, color="red", ls="--", lw=1)
        ax2.axvline(0.85, color="orange", ls="--", lw=1, label=">15% lower")
        ax2.set_xlabel("Dawn ISF / Afternoon ISF")
        ax2.set_ylabel("Count")
        ax2.set_title("Dawn Phenomenon Ratio")
        ax2.legend()

    # Panel 3: Profile vs Time MAE
    ax3 = fig.add_subplot(gs[0, 2])
    valid = rdf[(rdf["profile_mae"] < 900) & (rdf["time_mae"] < 900)]
    if len(valid) > 0:
        ax3.scatter(valid["profile_mae"], valid["time_mae"], c="steelblue", s=60, alpha=0.7)
        lim = max(valid["profile_mae"].max(), valid["time_mae"].max()) * 1.1
        ax3.plot([0, lim], [0, lim], "r--", lw=1)
    ax3.set_xlabel("Flat ISF MAE")
    ax3.set_ylabel("Time-Stratified ISF MAE")
    ax3.set_title("Flat vs Time-Stratified ISF")

    # Panel 4: All 4 configs per patient
    ax4 = fig.add_subplot(gs[1, 0:2])
    valid = rdf[rdf["profile_mae"] < 900]
    x = np.arange(len(valid))
    w = 0.2
    ax4.bar(x - 1.5*w, valid["profile_mae"], w, label="Profile", color="lightgray")
    ax4.bar(x - 0.5*w, valid["time_mae"], w, label="Time ISF", color="steelblue", alpha=0.7)
    ax4.bar(x + 0.5*w, valid["integrated_mae"], w, label="Integrated", color="orange", alpha=0.7)
    ax4.bar(x + 1.5*w, valid["integ_time_mae"], w, label="Integ+Time", color="green", alpha=0.7)
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(p)[:6] for p in valid["patient_id"]], rotation=45, fontsize=7)
    ax4.set_ylabel("MAE (mg/dL)")
    ax4.set_title("Per-Patient MAE: All Configurations")
    ax4.legend(fontsize=8)

    # Panel 5: Hypotheses
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        h_text += f"\n{tag} {k.replace('_', ' ')}"
    ax5.text(0.1, 0.9, h_text, transform=ax5.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2748-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2748-dashboard.png'}")


if __name__ == "__main__":
    main()
