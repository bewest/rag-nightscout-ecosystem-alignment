#!/usr/bin/env python3
"""EXP-2733: Simulator-Based ISF Extraction with Multi-Timescale Accounting.

The analytic ISF=drop/dose has a structural artifact (r=-0.83 dose dependence).
The forward simulator with physics (EXP-2728: MAE=46.9) works better because
it models dynamics causally. This experiment uses the simulator to EXTRACT ISF
rather than compute it from ratios.

METHOD: For each independent correction episode, find the ISF that minimizes
simulation error against actual glucose trajectory. This is the ISF that best
explains the data when EGP, counter-regulation, and DIA are properly modeled.

Key insight: simulator-extracted ISF accounts for:
  - EGP headwind (42% of gap)
  - Counter-regulation (10%)
  - DIA temporal profile (not just total drop)
  - Controller compensation (via actual insulin events, not just excess)

Also includes multi-timescale accounting:
  - 2h demand phase (ISF extraction)
  - 6h DIA window (persistent tail)
  - 72h insulin totals (sanity check / glycogen state proxy)

HYPOTHESES:
  H1: Simulator ISF has less dose-dependence artifact (|r| < 0.3)
  H2: Simulator ISF is closer to profile ISF (gap < 2x)
  H3: Simulator ISF has lower within-patient CV (more consistent)
  H4: Simulator ISF correlates with profile ISF (r > 0.3)
  H5: 72h TDD correlates with simulator ISF (metabolic context)

REFERENCES: EXP-2726b, EXP-2728, EXP-2732
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    forward_simulate,
    TherapySettings,
    InsulinEvent,
)
from production.types import TIR_LOW, TIR_HIGH

# ── Paths ────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/simulator-isf-extraction")

EXP_ID = 2733
TITLE = "Simulator-Based ISF Extraction — Causal Deconfounding"


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)]
    print(f"Loaded {len(grid)} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_independent_episodes(grid, bg_floor=150, min_dose=0.3,
                                  isolation_steps=24, max_per_patient=100):
    """Extract independent correction episodes for ISF fitting."""
    episodes = []
    has_smb = "bolus_smb" in grid.columns
    has_iob = "iob" in grid.columns

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < 72 + 10:  # need 6h episodes
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.zeros(len(pg))
        carbs = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
        basal_rate = pg["scheduled_basal_rate"].median() if "scheduled_basal_rate" in pg.columns else 1.0
        profile_isf = pg["scheduled_isf"].median() if "scheduled_isf" in pg.columns else 50.0

        try:
            times = pd.to_datetime(pg["time"])
        except Exception:
            continue

        last_used = -isolation_steps
        pat_episodes = []

        for i in range(1, len(pg) - 72):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < bg_floor:
                continue

            dose_2h = float(np.nansum(bolus[i:i+24]))
            if dose_2h < min_dose:
                continue

            # No carbs in [-1h, +2h]
            carb_window = float(np.nansum(carbs[max(0, i-12):i+24]))
            if carb_window > 1.0:
                continue

            # Independence
            if i - last_used < isolation_steps:
                continue

            # Get actual glucose trajectory (6h)
            actual_bg = glucose[i:i+72].copy()
            if np.isnan(actual_bg[:24]).mean() > 0.3:
                continue

            # Collect insulin events in 6h window
            insulin_events = []
            for j in range(72):
                if i + j < len(bolus):
                    b = float(bolus[i + j])
                    s = float(smb[i + j]) if has_smb else 0.0
                    if b > 0:
                        insulin_events.append({
                            "time_minutes": j * 5.0,
                            "units": b,
                            "is_bolus": True,
                        })
                    if s > 0:
                        insulin_events.append({
                            "time_minutes": j * 5.0,
                            "units": s,
                            "is_bolus": False,
                        })

            try:
                hour = times.iloc[i].hour + times.iloc[i].minute / 60.0
            except Exception:
                hour = 12.0

            pat_episodes.append({
                "patient_id": pid,
                "bg0": float(bg0),
                "actual_bg": actual_bg.tolist(),
                "insulin_events": insulin_events,
                "basal_rate": float(basal_rate),
                "profile_isf": float(profile_isf),
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "total_dose_2h": dose_2h,
                "total_dose_6h": float(np.nansum(bolus[i:i+72]) + np.nansum(smb[i:i+72])),
            })
            last_used = i

        # Sample if too many
        if len(pat_episodes) > max_per_patient:
            rng = np.random.RandomState(42)
            pat_episodes = [pat_episodes[j] for j in rng.choice(len(pat_episodes), max_per_patient, replace=False)]

        episodes.extend(pat_episodes)

    return episodes


def fit_isf_for_episode(ep, egp_enabled=True, counter_reg_k=0.3):
    """Find the ISF that minimizes simulation MAE for an episode."""
    actual_bg = np.array(ep["actual_bg"])
    n_valid = min(72, len(actual_bg))
    valid = ~np.isnan(actual_bg[:n_valid])
    if valid.sum() < 10:
        return None

    bolus_events = [
        InsulinEvent(ev["time_minutes"], ev["units"], ev["is_bolus"])
        for ev in ep["insulin_events"]
    ]

    def simulate_with_isf(isf_val):
        settings = TherapySettings(
            isf=isf_val, cr=10.0,
            basal_rate=ep["basal_rate"],
            dia_hours=5.0,
        )
        result = forward_simulate(
            initial_glucose=ep["bg0"],
            settings=settings,
            duration_hours=6.0,
            start_hour=ep["hour"],
            bolus_events=bolus_events,
            initial_iob=ep["iob_start"],
            metabolic_basal_rate=ep["basal_rate"],
            counter_reg_k=counter_reg_k,
            egp_enabled=egp_enabled,
        )
        sim_bg = result.glucose[:n_valid]
        return float(np.mean(np.abs(sim_bg[valid] - actual_bg[:n_valid][valid])))

    # Search over ISF range
    best_isf = None
    best_mae = float("inf")
    for isf_trial in [5, 10, 20, 30, 40, 50, 60, 80, 100, 120, 150]:
        try:
            mae = simulate_with_isf(isf_trial)
            if mae < best_mae:
                best_mae = mae
                best_isf = isf_trial
        except Exception:
            continue

    if best_isf is None:
        return None

    # Refine with golden section
    try:
        result = optimize.minimize_scalar(
            simulate_with_isf,
            bounds=(max(1, best_isf * 0.3), best_isf * 3.0),
            method="bounded",
        )
        if result.success:
            best_isf = result.x
            best_mae = result.fun
    except Exception:
        pass

    return {
        "sim_isf": float(best_isf),
        "sim_mae": float(best_mae),
    }


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()

    print("\nExtracting independent correction episodes...")
    episodes = extract_independent_episodes(grid)
    print(f"Extracted {len(episodes)} episodes from {len(set(e['patient_id'] for e in episodes))} patients")

    if len(episodes) < 50:
        print("ERROR: Too few episodes for analysis")
        sys.exit(1)

    # ── Fit ISF for each episode ─────────────────────────────────────
    print("\nFitting ISF per episode (this may take a while)...")
    results = []
    for idx, ep in enumerate(episodes):
        if idx % 100 == 0 and idx > 0:
            print(f"  {idx}/{len(episodes)}...")
        fit = fit_isf_for_episode(ep, egp_enabled=True, counter_reg_k=0.3)
        if fit is None:
            continue

        # Also compute naive ISF for comparison
        drop_2h = ep["bg0"] - ep["actual_bg"][min(23, len(ep["actual_bg"])-1)]
        naive_isf = drop_2h / ep["total_dose_2h"] if ep["total_dose_2h"] > 0.1 and not np.isnan(drop_2h) else np.nan

        results.append({
            "patient_id": ep["patient_id"],
            "bg0": ep["bg0"],
            "hour": ep["hour"],
            "total_dose_2h": ep["total_dose_2h"],
            "total_dose_6h": ep["total_dose_6h"],
            "iob_start": ep["iob_start"],
            "profile_isf": ep["profile_isf"],
            "sim_isf": fit["sim_isf"],
            "sim_mae": fit["sim_mae"],
            "naive_isf": naive_isf,
        })

    df = pd.DataFrame(results)
    print(f"\nFitted {len(df)} episodes successfully")

    # ── Per-patient aggregation ──────────────────────────────────────
    print(f"\n{'─' * 50}")
    print("Per-patient ISF comparison")
    print(f"{'─' * 50}")

    pat_data = []
    for pid in df["patient_id"].unique():
        pc = df[df["patient_id"] == pid]
        if len(pc) < 5:
            continue

        sim_vals = pc["sim_isf"].values
        naive_vals = pc["naive_isf"].dropna().values
        naive_pos = naive_vals[naive_vals > 0]
        profile = pc["profile_isf"].median()

        # Dose-ISF correlation
        sim_r, _ = stats.spearmanr(pc["total_dose_2h"], pc["sim_isf"]) if len(pc) > 5 else (np.nan, np.nan)
        naive_r = np.nan
        if len(naive_pos) > 5:
            mask = pc["naive_isf"].notna() & (pc["naive_isf"] > 0)
            naive_r_val, _ = stats.spearmanr(pc.loc[mask, "total_dose_2h"], pc.loc[mask, "naive_isf"])
            naive_r = float(naive_r_val)

        # 72h insulin context
        pg = grid[grid["patient_id"] == pid]
        total_hours = len(pg) * 5.0 / 60.0
        tdd = (pg["bolus"].sum() + pg.get("bolus_smb", pd.Series([0])).sum() +
               pg.get("scheduled_basal_rate", pd.Series([0])).median() * total_hours) / (total_hours / 24.0)

        pat_data.append({
            "patient_id": pid,
            "n_episodes": len(pc),
            "profile_isf": float(profile),
            "sim_isf_median": float(np.median(sim_vals)),
            "sim_isf_cv": float(np.std(sim_vals) / np.mean(sim_vals)) if np.mean(sim_vals) > 0 else np.nan,
            "naive_isf_median": float(np.median(naive_pos)) if len(naive_pos) > 0 else np.nan,
            "naive_isf_cv": float(np.std(naive_pos) / np.mean(naive_pos)) if len(naive_pos) > 0 and np.mean(naive_pos) > 0 else np.nan,
            "sim_dose_r": float(sim_r) if np.isfinite(sim_r) else np.nan,
            "naive_dose_r": float(naive_r) if np.isfinite(naive_r) else np.nan,
            "sim_mae_median": float(pc["sim_mae"].median()),
            "profile_gap_sim": float(profile / np.median(sim_vals)) if np.median(sim_vals) > 0 else np.nan,
            "profile_gap_naive": float(profile / np.median(naive_pos)) if len(naive_pos) > 0 and np.median(naive_pos) > 0 else np.nan,
            "tdd": float(tdd),
        })

    pat_df = pd.DataFrame(pat_data)
    print(f"Patients analyzed: {len(pat_df)}")

    print(f"\n  Population medians:")
    print(f"    Simulator ISF:  {pat_df['sim_isf_median'].median():.1f}")
    print(f"    Naive ISF:      {pat_df['naive_isf_median'].median():.1f}")
    print(f"    Profile ISF:    {pat_df['profile_isf'].median():.1f}")

    print(f"\n  Profile gap:")
    print(f"    Simulator: {pat_df['profile_gap_sim'].median():.1f}x")
    print(f"    Naive:     {pat_df['profile_gap_naive'].median():.1f}x")

    print(f"\n  Dose-ISF |r| (artifact):")
    print(f"    Simulator: {pat_df['sim_dose_r'].abs().median():.3f}")
    print(f"    Naive:     {pat_df['naive_dose_r'].abs().median():.3f}")

    print(f"\n  ISF CV (precision):")
    print(f"    Simulator: {pat_df['sim_isf_cv'].median():.3f}")
    print(f"    Naive:     {pat_df['naive_isf_cv'].median():.3f}")

    # Profile-sim correlation
    valid_both = pat_df.dropna(subset=["profile_isf", "sim_isf_median"])
    if len(valid_both) > 5:
        prof_sim_r, prof_sim_p = stats.spearmanr(valid_both["profile_isf"], valid_both["sim_isf_median"])
        print(f"\n  Profile ↔ Simulator ISF: r={prof_sim_r:.3f}, p={prof_sim_p:.3e}")
    else:
        prof_sim_r = np.nan

    # TDD-ISF correlation
    if len(pat_df.dropna(subset=["tdd", "sim_isf_median"])) > 5:
        tdd_r, tdd_p = stats.spearmanr(pat_df["tdd"].dropna(), pat_df["sim_isf_median"].dropna())
        print(f"  TDD ↔ Simulator ISF:    r={tdd_r:.3f}, p={tdd_p:.3e}")
    else:
        tdd_r = np.nan

    # ── Hypotheses ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  HYPOTHESES")
    print(f"{'=' * 70}")

    hypotheses = {}

    h1 = pat_df["sim_dose_r"].abs().median() < 0.3
    hypotheses["H1_low_dose_artifact"] = (h1,
        f"Simulator |dose-ISF r|={pat_df['sim_dose_r'].abs().median():.3f}")
    print(f"  {'PASS' if h1 else 'FAIL'} H1: Simulator ISF dose artifact < 0.3")

    h2 = pat_df["profile_gap_sim"].median() < 2.0
    hypotheses["H2_close_to_profile"] = (h2,
        f"Profile gap={pat_df['profile_gap_sim'].median():.1f}x")
    print(f"  {'PASS' if h2 else 'FAIL'} H2: Simulator ISF gap < 2x from profile")

    h3 = pat_df["sim_isf_cv"].median() < pat_df["naive_isf_cv"].median()
    hypotheses["H3_lower_cv"] = (h3,
        f"Sim CV={pat_df['sim_isf_cv'].median():.3f} vs naive={pat_df['naive_isf_cv'].median():.3f}")
    print(f"  {'PASS' if h3 else 'FAIL'} H3: Simulator ISF has lower CV")

    h4 = np.isfinite(prof_sim_r) and prof_sim_r > 0.3
    hypotheses["H4_profile_correlation"] = (h4,
        f"Profile-sim r={prof_sim_r:.3f}" if np.isfinite(prof_sim_r) else "insufficient data")
    print(f"  {'PASS' if h4 else 'FAIL'} H4: Profile correlates with simulator ISF")

    h5 = np.isfinite(tdd_r) and abs(tdd_r) > 0.3
    hypotheses["H5_tdd_context"] = (h5,
        f"TDD-ISF r={tdd_r:.3f}" if np.isfinite(tdd_r) else "insufficient data")
    print(f"  {'PASS' if h5 else 'FAIL'} H5: TDD correlates with simulator ISF")

    n_pass = sum(1 for v in hypotheses.values() if v[0])

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: EXP-{EXP_ID}: {n_pass}/5 pass.")
    print(f"  Simulator ISF median={pat_df['sim_isf_median'].median():.1f}, "
          f"profile gap={pat_df['profile_gap_sim'].median():.1f}x, "
          f"|dose-r|={pat_df['sim_dose_r'].abs().median():.3f}")
    print(f"{'=' * 70}")

    # ── Dashboard ─────────────────────────────────────────────────────
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        VIZ_DIR.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=14, fontweight="bold")

        # 1. ISF comparison
        ax = axes[0, 0]
        vals = [pat_df['naive_isf_median'].median(),
                pat_df['sim_isf_median'].median(),
                pat_df['profile_isf'].median()]
        ax.bar(["Naive\n(drop/dose)", "Simulator\n(physics)", "Profile\n(setting)"],
               vals, color=["#e74c3c", "#2ecc71", "#3498db"])
        ax.set_title("ISF Extraction Comparison")
        ax.set_ylabel("ISF (mg/dL per U)")
        for i, v in enumerate(vals):
            ax.text(i, v + 1, f"{v:.1f}", ha="center")

        # 2. Dose-ISF correlation
        ax = axes[0, 1]
        ax.bar(["Naive", "Simulator"],
               [pat_df['naive_dose_r'].abs().median(), pat_df['sim_dose_r'].abs().median()],
               color=["#e74c3c", "#2ecc71"])
        ax.set_title("|Dose-ISF r| (lower = less artifact)")
        ax.axhline(0.3, color="gray", linestyle="--", label="Target")
        ax.legend()

        # 3. ISF CV
        ax = axes[0, 2]
        ax.bar(["Naive", "Simulator"],
               [pat_df['naive_isf_cv'].median(), pat_df['sim_isf_cv'].median()],
               color=["#e74c3c", "#2ecc71"])
        ax.set_title("ISF CV (lower = more consistent)")

        # 4. Profile vs simulator ISF scatter
        ax = axes[1, 0]
        ax.scatter(pat_df["profile_isf"], pat_df["sim_isf_median"],
                   s=60, c="#2ecc71", edgecolors="k", linewidths=0.5)
        ax.set_xlabel("Profile ISF")
        ax.set_ylabel("Simulator ISF")
        ax.set_title(f"Profile vs Sim (r={prof_sim_r:.2f})" if np.isfinite(prof_sim_r) else "Profile vs Sim")
        max_val = max(pat_df["profile_isf"].max(), pat_df["sim_isf_median"].max()) * 1.1
        ax.plot([0, max_val], [0, max_val], "k--", alpha=0.3)

        # 5. Per-episode ISF distribution
        ax = axes[1, 1]
        ax.hist(df["sim_isf"], bins=30, color="#2ecc71", alpha=0.7, label="Simulator")
        naive_valid = df["naive_isf"].dropna()
        naive_pos = naive_valid[naive_valid > 0]
        if len(naive_pos) > 10:
            ax.hist(naive_pos.clip(upper=200), bins=30, color="#e74c3c", alpha=0.5, label="Naive")
        ax.set_title("Per-episode ISF distribution")
        ax.set_xlabel("ISF")
        ax.legend()

        # 6. Hypothesis results
        ax = axes[1, 2]
        ax.axis("off")
        text = f"EXP-{EXP_ID} Hypotheses\n" + "=" * 35 + "\n"
        for h_id, (passed, desc) in hypotheses.items():
            icon = "✓" if passed else "✗"
            text += f"\n{icon} {h_id}\n  {desc}\n"
        ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=9,
                verticalalignment="top", fontfamily="monospace")

        plt.tight_layout()
        out = VIZ_DIR / f"exp-{EXP_ID}-dashboard.png"
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Dashboard: {out}")
    except ImportError:
        print("  (matplotlib unavailable)")

    # ── Save ──────────────────────────────────────────────────────────
    def clean(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    out_json = {
        "experiment_id": f"EXP-{EXP_ID}",
        "title": TITLE,
        "timestamp": datetime.now().isoformat(),
        "summary": f"{n_pass}/5 pass. Simulator ISF={pat_df['sim_isf_median'].median():.1f}, "
                   f"profile gap={pat_df['profile_gap_sim'].median():.1f}x",
        "per_patient": pat_df.to_dict(orient="records"),
        "hypotheses": {k: {"passed": bool(v[0]), "detail": v[1]} for k, v in hypotheses.items()},
        "population": {
            "sim_isf_median": round(float(pat_df["sim_isf_median"].median()), 1),
            "naive_isf_median": round(float(pat_df["naive_isf_median"].median()), 1),
            "profile_isf_median": round(float(pat_df["profile_isf"].median()), 1),
            "n_episodes": len(df),
            "n_patients": len(pat_df),
        },
    }
    out = RESULTS_DIR / f"exp-{EXP_ID}_simulator_isf_extraction.json"
    out.write_text(json.dumps(out_json, indent=2, default=clean))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
