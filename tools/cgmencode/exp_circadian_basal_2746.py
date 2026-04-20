#!/usr/bin/env python3
"""
EXP-2746: Circadian Basal Profiling
====================================

Scientific Question
-------------------
Can time-of-day basal rate profiles improve glucose prediction over flat basal?
EXP-2745 showed flat basal adjustment WORSENS MAE (controller compensation),
but EXP-2740 showed 80% of patients have circadian mismatch >1 mg/dL/5min.

This experiment extracts hourly fasting drift for ALL 22 patients, converts
to circadian basal multipliers, and tests hourly basal schedules in the
forward simulator.

Key insight: We're not trying to find the "true" basal rate. We're finding
the relative circadian SHAPE — which hours need more vs less basal — while
keeping the total (TDD from basal) close to profile.

Predecessors
------------
- EXP-2745: Flat basal adjustment fails (1/22 improve) — controller compensates
- EXP-2740: 80% of patients show circadian EGP mismatch >1 mg/dL/5min
- EXP-2743: Integrated pipeline (ISF + CR + EGP) — 28% MAE improvement

Hypotheses
----------
H1: >50% of patients have significant circadian drift pattern (ANOVA p<0.05
    across 6 time blocks: night, dawn, morning, afternoon, evening, late night)
H2: Circadian basal profile improves MAE over flat profile for >40% of patients
H3: Circadian + integrated pipeline improves over integrated-only for >30%
H4: TBR is not significantly worse with circadian basal (paired t p>0.05)
H5: Dawn phenomenon (5-9am drift > median) present in >50% of patients
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
VIZ_DIR = Path("tools/visualizations/circadian-basal")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent, CarbEvent,
)

# ── Time blocks ──
TIME_BLOCKS = {
    "night":     (0, 5),    # 00:00-04:59
    "dawn":      (5, 9),    # 05:00-08:59
    "morning":   (9, 12),   # 09:00-11:59
    "afternoon": (12, 17),  # 12:00-16:59
    "evening":   (17, 21),  # 17:00-20:59
    "late_night":(21, 24),  # 21:00-23:59
}


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    # Load ISF corrections
    isf_data = json.loads(EXP_2719B.read_text())
    isf_map = {p["patient_id"]: p.get("correction_factor", 1.0)
               for p in isf_data["results"]["2h"]["per_patient"]}

    # Load CR corrections
    cr_data = json.loads(EXP_2741.read_text())
    cr_map = {p["patient_id"]: p.get("compensated_cr")
              for p in cr_data["per_patient"]}

    # Load EGP corrections
    egp_data = json.loads(EXP_2742.read_text())
    egp_map = {p["patient_id"]: p for p in egp_data["per_patient"]}

    return grid, isf_map, cr_map, egp_map


def identify_fasting(pg: pd.DataFrame, min_gap_h: float = 3.0) -> pd.DataFrame:
    """Identify fasting periods: no carbs or bolus for min_gap_h hours."""
    min_steps = int(min_gap_h * 12)  # 5-min steps

    # Mark non-fasting: carbs > 0 or bolus > 0
    carbs = pg["carbs"].fillna(0)
    bolus = pg["bolus"].fillna(0)
    non_fasting = (carbs > 0) | (bolus > 0)

    # Compute steps since last non-fasting event
    non_fast_idx = pg.index[non_fasting]
    steps_since = pd.Series(0, index=pg.index, dtype=int)

    last_event = -999
    for i, idx in enumerate(pg.index):
        if idx in non_fast_idx.values if hasattr(non_fast_idx, 'values') else idx in set(non_fast_idx):
            last_event = i
        steps_since.iloc[i] = i - last_event

    fasting = steps_since >= min_steps
    return pg[fasting].copy()


def extract_hourly_drift(fasting: pd.DataFrame) -> dict:
    """Extract per-hour glucose drift from fasting periods."""
    if len(fasting) < 50:
        return {}

    fasting = fasting.copy()
    glucose = fasting["glucose"].values
    drift = np.diff(glucose)
    fasting_diff = fasting.iloc[1:].copy()
    fasting_diff["drift"] = drift

    # Extract hour of day
    if "timestamp" in fasting_diff.columns:
        fasting_diff["hour"] = pd.to_datetime(fasting_diff["timestamp"]).dt.hour
    elif "time" in fasting_diff.columns:
        fasting_diff["hour"] = pd.to_datetime(fasting_diff["time"]).dt.hour
    else:
        # Use index position modulo 288 (24h of 5-min steps)
        fasting_diff["hour"] = (fasting_diff.index % 288) // 12

    hourly = {}
    for h in range(24):
        hdata = fasting_diff[fasting_diff["hour"] == h]["drift"]
        if len(hdata) >= 5:
            hourly[h] = {
                "median_drift": float(hdata.median()),
                "mean_drift": float(hdata.mean()),
                "std_drift": float(hdata.std()),
                "n": int(len(hdata)),
            }
    return hourly


def drift_to_basal_schedule(hourly_drift: dict, profile_basal: float,
                            profile_isf: float) -> list:
    """Convert hourly drift to basal schedule.

    Positive drift = glucose rising during fasting = need MORE basal
    Negative drift = glucose falling during fasting = need LESS basal

    basal_adjustment = drift / ISF * 12  (convert mg/dL/5min to U/hr)
    """
    if not hourly_drift:
        return []

    schedule = []
    for h in range(24):
        if h in hourly_drift:
            drift = hourly_drift[h]["median_drift"]
            # Convert drift (mg/dL per 5min) to basal change (U/hr)
            # drift = EGP - basal_effect → to fix, add drift/ISF to basal
            # 12 five-min steps per hour
            basal_change = drift / profile_isf * 12 if profile_isf > 0 else 0
            new_basal = max(0.05, profile_basal + basal_change)
            # Clamp to ±50% of profile
            new_basal = np.clip(new_basal, profile_basal * 0.5, profile_basal * 1.5)
            schedule.append((h, float(new_basal)))
        else:
            schedule.append((h, float(profile_basal)))

    return schedule


def test_circadian_significance(hourly_drift: dict) -> dict:
    """Test if circadian drift pattern is significant via ANOVA across time blocks."""
    block_data = {}
    for block_name, (start, end) in TIME_BLOCKS.items():
        vals = []
        for h in range(start, end):
            if h in hourly_drift:
                vals.extend([hourly_drift[h]["median_drift"]] * hourly_drift[h]["n"])
        if vals:
            block_data[block_name] = vals

    if len(block_data) < 3:
        return {"significant": False, "p": 1.0, "f_stat": 0}

    groups = list(block_data.values())
    try:
        f_stat, p_val = stats.f_oneway(*groups)
        if np.isnan(p_val):
            p_val = 1.0
    except Exception:
        f_stat, p_val = 0, 1.0

    # Dawn phenomenon: dawn block drift > median of all blocks
    dawn_vals = block_data.get("dawn", [])
    all_vals = [v for vals in block_data.values() for v in vals]
    dawn_above_median = (np.median(dawn_vals) > np.median(all_vals)) if dawn_vals else False

    return {
        "significant": p_val < 0.05,
        "p": float(p_val),
        "f_stat": float(f_stat),
        "dawn_phenomenon": bool(dawn_above_median),
        "block_medians": {k: float(np.median(v)) for k, v in block_data.items()},
    }


def extract_episodes(pg: pd.DataFrame, max_episodes: int = 80) -> list:
    """Extract correction and meal episodes for simulation."""
    episodes = []
    horizon = 24  # steps (2h)

    # Correction episodes: BG >= 180, bolus > 0
    if "glucose" in pg.columns and "bolus" in pg.columns:
        corr_mask = (pg["glucose"] >= 180) & (pg["bolus"] > 0)
        corr_idx = pg.index[corr_mask]
        for idx in corr_idx:
            pos = pg.index.get_loc(idx)
            if pos + horizon >= len(pg):
                continue
            window = pg.iloc[pos:pos + horizon]
            glucose = window["glucose"].values
            if np.isnan(glucose).sum() > len(glucose) * 0.3:
                continue
            hour = 12.0
            if "time" in pg.columns:
                try:
                    hour = pd.to_datetime(pg.iloc[pos]["time"]).hour
                except Exception:
                    pass
            episodes.append({
                "type": "correction",
                "bg0": float(glucose[0]),
                "bolus": float(pg.iloc[pos]["bolus"]),
                "carbs": float(pg.iloc[pos].get("carbs", 0) or 0),
                "trajectory": [float(v) if not np.isnan(v) else None for v in glucose],
                "horizon": horizon,
                "hour": hour,
            })

    # Meal episodes: carbs > 10
    if "carbs" in pg.columns:
        meal_mask = pg["carbs"] > 10
        meal_idx = pg.index[meal_mask]
        for idx in meal_idx:
            pos = pg.index.get_loc(idx)
            if pos + horizon >= len(pg):
                continue
            window = pg.iloc[pos:pos + horizon]
            glucose = window["glucose"].values
            if np.isnan(glucose).sum() > len(glucose) * 0.3:
                continue
            hour = 12.0
            if "time" in pg.columns:
                try:
                    hour = pd.to_datetime(pg.iloc[pos]["time"]).hour
                except Exception:
                    pass
            episodes.append({
                "type": "meal",
                "bg0": float(glucose[0]),
                "bolus": float(pg.iloc[pos].get("bolus", 0) or 0),
                "carbs": float(pg.iloc[pos]["carbs"]),
                "trajectory": [float(v) if not np.isnan(v) else None for v in glucose],
                "horizon": horizon,
                "hour": hour,
            })

    # Sample if too many
    if len(episodes) > max_episodes:
        rng = np.random.RandomState(42)
        episodes = [episodes[i] for i in rng.choice(len(episodes), max_episodes, replace=False)]

    return episodes


def simulate_patient(pg, settings, profile_basal):
    """Run forward simulation for a patient using episode-based approach."""
    episodes = extract_episodes(pg)
    if len(episodes) < 3:
        return {"mae": 999.0, "tir": 0.0, "tbr": 0.0}

    maes, tirs, tbrs = [], [], []
    for ep in episodes:
        bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
        carb_events = [CarbEvent(0, ep["carbs"])] if ep["carbs"] > 0 else []
        duration = ep["horizon"] * 5 / 60

        try:
            result = forward_simulate(
                initial_glucose=ep["bg0"], settings=settings,
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
                tirs.append(float(np.sum((sim[:n] >= 70) & (sim[:n] <= 180))) / n)
        except Exception:
            pass

    if not maes:
        return {"mae": 999.0, "tir": 0.0, "tbr": 0.0}

    return {
        "mae": float(np.median(maes)),
        "tir": float(np.median(tirs)) * 100,
        "tbr": float(np.median(tbrs)) * 100,
    }


def main():
    print("=" * 70)
    print("EXP-2746: Circadian Basal Profiling")
    print("=" * 70)

    grid, isf_map, cr_map, egp_map = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients\n")

    results = []
    n_significant = 0
    n_dawn = 0
    n_circ_improves = 0
    n_circ_integ_improves = 0
    tbr_diffs = []

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_index()
        profile_isf = float(pg["scheduled_isf"].median()) if "scheduled_isf" in pg else 50
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        # Extract fasting periods and hourly drift
        fasting = identify_fasting(pg)
        hourly_drift = extract_hourly_drift(fasting)

        # Test circadian significance
        circ_test = test_circadian_significance(hourly_drift)
        if circ_test["significant"]:
            n_significant += 1
        if circ_test.get("dawn_phenomenon"):
            n_dawn += 1

        # Build basal schedule
        basal_schedule = drift_to_basal_schedule(hourly_drift, profile_basal, profile_isf)

        # ISF correction
        isf_cf = isf_map.get(pid, 1.0)
        corrected_isf = float(np.clip(profile_isf / isf_cf, 5, 200))

        # CR correction
        comp_cr = cr_map.get(pid)
        if comp_cr and comp_cr > 0:
            safe_cr = max(comp_cr, profile_cr * 0.7)
        else:
            safe_cr = profile_cr

        # EGP ISF adjustment
        egp_info = egp_map.get(pid, {})
        adj_isf = egp_info.get("adjusted_isf")
        final_isf = float(np.clip(adj_isf, 5, 200)) if adj_isf and adj_isf > 0 else corrected_isf

        # Settings: profile (flat basal)
        settings_profile = TherapySettings(
            isf=profile_isf, cr=profile_cr, basal_rate=profile_basal,
            dia_hours=6.0,
        )

        # Settings: circadian basal only
        settings_circadian = TherapySettings(
            isf=profile_isf, cr=profile_cr, basal_rate=profile_basal,
            dia_hours=6.0,
            basal_schedule=basal_schedule,
        )

        # Settings: integrated + circadian
        settings_integrated_circ = TherapySettings(
            isf=final_isf, cr=safe_cr, basal_rate=profile_basal,
            dia_hours=6.0,
            basal_schedule=basal_schedule,
        )

        # Settings: integrated flat (from EXP-2743)
        settings_integrated_flat = TherapySettings(
            isf=final_isf, cr=safe_cr, basal_rate=profile_basal,
            dia_hours=6.0,
        )

        # Simulate
        r_profile = simulate_patient(pg, settings_profile, profile_basal)
        r_circadian = simulate_patient(pg, settings_circadian, profile_basal)
        r_integ_flat = simulate_patient(pg, settings_integrated_flat, profile_basal)
        r_integ_circ = simulate_patient(pg, settings_integrated_circ, profile_basal)

        circ_improves = r_circadian["mae"] < r_profile["mae"]
        integ_circ_improves = r_integ_circ["mae"] < r_integ_flat["mae"]
        if circ_improves:
            n_circ_improves += 1
        if integ_circ_improves:
            n_circ_integ_improves += 1

        tbr_diffs.append(r_circadian["tbr"] - r_profile["tbr"])

        schedule_summary = {}
        for h, val in basal_schedule:
            schedule_summary[str(h)] = round(val, 3)

        entry = {
            "patient_id": pid,
            "n_fasting_obs": len(fasting),
            "n_hours_with_data": len(hourly_drift),
            "circadian_significant": circ_test["significant"],
            "circadian_p": circ_test["p"],
            "dawn_phenomenon": circ_test.get("dawn_phenomenon", False),
            "block_medians": circ_test.get("block_medians", {}),
            "basal_schedule": schedule_summary,
            "profile_basal": profile_basal,
            "profile_mae": r_profile["mae"],
            "circadian_mae": r_circadian["mae"],
            "integrated_flat_mae": r_integ_flat["mae"],
            "integrated_circ_mae": r_integ_circ["mae"],
            "circadian_improves": circ_improves,
            "integ_circ_improves": integ_circ_improves,
            "profile_tbr": r_profile["tbr"],
            "circadian_tbr": r_circadian["tbr"],
        }
        results.append(entry)

        tag = "***" if circ_test["significant"] else "   "
        dawn = "D" if circ_test.get("dawn_phenomenon") else " "
        circ_imp = "+" if circ_improves else "-"
        integ_imp = "+" if integ_circ_improves else "-"
        print(f"  {pid[:14]:<16} {tag} {dawn} fasting={len(fasting):>5}  "
              f"hours={len(hourly_drift):>2}  "
              f"MAE: prof={r_profile['mae']:>5.1f} circ={r_circadian['mae']:>5.1f}{circ_imp} "
              f"integ={r_integ_flat['mae']:>5.1f}→{r_integ_circ['mae']:>5.1f}{integ_imp}")

    # Hypotheses
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: ", end="")

    h1 = n_significant / len(patients) > 0.5
    h2 = n_circ_improves / len(patients) > 0.4
    h3 = n_circ_integ_improves / len(patients) > 0.3
    try:
        tbr_t, tbr_p = stats.ttest_rel(
            [r["profile_tbr"] for r in results],
            [r["circadian_tbr"] for r in results]
        )
        if np.isnan(tbr_p):
            tbr_p = 1.0
    except Exception:
        tbr_p = 1.0
    h4 = tbr_p > 0.05
    h5 = n_dawn / len(patients) > 0.5

    passed = sum([h1, h2, h3, h4, h5])
    print(f"{passed}/5 pass")

    hypotheses = {
        "H1_circadian_significant": {
            "passed": h1, "n_significant": n_significant,
            "n_total": len(patients), "fraction": n_significant / len(patients),
        },
        "H2_circadian_improves_40pct": {
            "passed": h2, "n_improves": n_circ_improves,
            "n_total": len(patients), "fraction": n_circ_improves / len(patients),
        },
        "H3_circ_integ_improves_30pct": {
            "passed": h3, "n_improves": n_circ_integ_improves,
            "n_total": len(patients), "fraction": n_circ_integ_improves / len(patients),
        },
        "H4_safety_maintained": {
            "passed": h4, "tbr_p": float(tbr_p),
        },
        "H5_dawn_phenomenon_50pct": {
            "passed": h5, "n_dawn": n_dawn,
            "n_total": len(patients), "fraction": n_dawn / len(patients),
        },
    }

    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        print(f"  {tag} {k}")

    print(f"\n  Significant circadian: {n_significant}/{len(patients)}")
    print(f"  Dawn phenomenon: {n_dawn}/{len(patients)}")
    print(f"  Circadian improves over flat: {n_circ_improves}/{len(patients)}")
    print(f"  Circadian+integrated improves: {n_circ_integ_improves}/{len(patients)}")
    print(f"  TBR p-value: {tbr_p:.3f}")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2746_circadian_basal.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2746",
            "title": "Circadian Basal Profiling",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "per_patient": results,
            "summary": {
                "n_patients": len(patients),
                "n_significant": n_significant,
                "n_dawn": n_dawn,
                "n_circ_improves": n_circ_improves,
                "n_circ_integ_improves": n_circ_integ_improves,
                "tbr_p": float(tbr_p),
            },
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
    fig = plt.figure(figsize=(18, 12))
    fig.suptitle("EXP-2746: Circadian Basal Profiling", fontsize=14, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Panel 1: Profile vs Circadian MAE
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(rdf["profile_mae"], rdf["circadian_mae"], c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["profile_mae"].max(), rdf["circadian_mae"].max()) * 1.1
    ax1.plot([0, lim], [0, lim], "r--", lw=1)
    ax1.set_xlabel("Profile MAE (flat basal)")
    ax1.set_ylabel("Circadian MAE")
    ax1.set_title("Flat vs Circadian Basal")

    # Panel 2: Integrated flat vs integrated+circadian
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(rdf["integrated_flat_mae"], rdf["integrated_circ_mae"], c="steelblue", s=60, alpha=0.7)
    lim = max(rdf["integrated_flat_mae"].max(), rdf["integrated_circ_mae"].max()) * 1.1
    ax2.plot([0, lim], [0, lim], "r--", lw=1)
    ax2.set_xlabel("Integrated (flat basal) MAE")
    ax2.set_ylabel("Integrated + Circadian MAE")
    ax2.set_title("Adding Circadian to Integrated")

    # Panel 3: Dawn phenomenon
    ax3 = fig.add_subplot(gs[0, 2])
    dawn_present = rdf["dawn_phenomenon"].sum()
    ax3.pie([dawn_present, len(rdf) - dawn_present],
            labels=["Dawn phenomenon", "No dawn"],
            autopct="%1.0f%%", colors=["coral", "lightblue"], startangle=90)
    ax3.set_title(f"Dawn Phenomenon ({dawn_present}/{len(rdf)})")

    # Panel 4: Per-patient MAE comparison
    ax4 = fig.add_subplot(gs[1, :])
    x = np.arange(len(rdf))
    w = 0.2
    ax4.bar(x - 1.5*w, rdf["profile_mae"], w, label="Profile", color="lightgray")
    ax4.bar(x - 0.5*w, rdf["circadian_mae"], w, label="Circadian", color="steelblue", alpha=0.7)
    ax4.bar(x + 0.5*w, rdf["integrated_flat_mae"], w, label="Integrated", color="orange", alpha=0.7)
    ax4.bar(x + 1.5*w, rdf["integrated_circ_mae"], w, label="Integ+Circ", color="green", alpha=0.7)
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(p)[:6] for p in rdf["patient_id"]], rotation=45, fontsize=7)
    ax4.set_ylabel("MAE (mg/dL)")
    ax4.set_title("Per-Patient MAE: All Configurations")
    ax4.legend(fontsize=8)

    # Panel 5: Circadian drift heatmap (sample patients with significant circadian)
    ax5 = fig.add_subplot(gs[2, 0:2])
    sig_patients = rdf[rdf["circadian_significant"]]
    if len(sig_patients) > 0:
        heatmap_data = []
        labels = []
        for _, r in sig_patients.iterrows():
            blocks = r.get("block_medians", {})
            if blocks:
                row = [blocks.get(b, 0) for b in TIME_BLOCKS.keys()]
                heatmap_data.append(row)
                labels.append(str(r["patient_id"])[:8])
        if heatmap_data:
            im = ax5.imshow(heatmap_data, aspect="auto", cmap="RdBu_r",
                           vmin=-1, vmax=1)
            ax5.set_yticks(range(len(labels)))
            ax5.set_yticklabels(labels, fontsize=8)
            ax5.set_xticks(range(6))
            ax5.set_xticklabels(list(TIME_BLOCKS.keys()), rotation=30, fontsize=8)
            plt.colorbar(im, ax=ax5, label="Drift (mg/dL/5min)")
            ax5.set_title("Circadian Drift Pattern (significant patients)")

    # Panel 6: Hypothesis summary
    ax6 = fig.add_subplot(gs[2, 2])
    ax6.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        h_text += f"\n{tag} {k.replace('_', ' ')}"
    ax6.text(0.1, 0.9, h_text, transform=ax6.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2746-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2746-dashboard.png'}")


if __name__ == "__main__":
    main()
