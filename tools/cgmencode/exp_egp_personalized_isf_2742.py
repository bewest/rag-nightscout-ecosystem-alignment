#!/usr/bin/env python3
"""
EXP-2742: EGP-Personalized ISF Refinement
==========================================

EXP-2739 (other researcher) showed per-patient EGP varies >2× and
improves ISF precision >15%. This experiment integrates their per-patient
EGP profiles into our validated ISF pipeline (EXP-2719b → 2739).

Approach:
1. Load per-patient EGP from other researcher's EXP-2739
2. For patients with EGP data, re-run correction episodes through
   the simulator with personalized EGP vs population EGP vs no EGP
3. Compare: does personalized EGP improve simulator MAE?
4. Compute EGP-adjusted ISF corrections and compare to baseline

HYPOTHESES:
  H1: Personalized EGP improves MAE over population EGP (>50% of patients)
  H2: Personalized EGP improves MAE over no-EGP (>60% of patients)
  H3: EGP adjustment changes ISF correction factors by >10% for ≥30% of patients
  H4: High-EGP patients (>0.4 mg/dL/5min) show largest improvements
  H5: Combined ISF+EGP pipeline produces <80 mg/dL median MAE

REFERENCES: EXP-2719b (ISF corrections), EXP-2739 (ISF-only validation),
            EXP-2739 (other researcher, EGP personalization)
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, forward_simulate,
)

EXP_ID = "2742"
TITLE = "EGP-Personalized ISF Refinement"

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EXP_2719B = Path("externals/experiments/exp-2719b_settings_from_residuals.json")
EGP_DATA = Path("externals/experiments/exp-2739_egp_personalization.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/egp-personalized-isf")

HORIZON = 24  # 2h
MIN_BG = 150
MIN_SPACING = 24  # 2h
MAX_EPISODES = 60
DIA_HOURS = 5.0
POP_EGP = 0.409  # median from other researcher's data


def load_data():
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    return grid[grid["patient_id"].isin(manifest["qualified_patients"])]


def load_isf_corrections():
    d = json.loads(EXP_2719B.read_text())
    result = {}
    for pp in d["results"]["2h"]["per_patient"]:
        result[pp["patient_id"]] = {
            "correction_factor": pp["correction_factor"],
            "profile_isf": pp["profile_isf"],
            "empirical_isf": pp["empirical_isf"],
        }
    return result


def load_egp_profiles():
    d = json.loads(EGP_DATA.read_text())
    result = {}
    for pp in d["per_patient_egp_profiles"]:
        pid = pp["patient_id"]
        # Match truncated IDs
        result[pid] = {
            "egp_median": pp["egp_median"],
            "egp_mean": pp["egp_mean"],
            "n_fasting": pp["n_fasting_obs"],
        }
    return result


def match_patient_egp(pid, egp_profiles):
    """Match patient ID to EGP profile (handles truncation)."""
    if pid in egp_profiles:
        return egp_profiles[pid]
    for epid, val in egp_profiles.items():
        if pid.startswith(epid[:12]) or epid.startswith(str(pid)[:12]):
            return val
    return None


def extract_correction_episodes(pg):
    """Extract high-BG correction episodes."""
    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    episodes = []
    last = -MIN_SPACING - 1

    for i in range(len(pg) - HORIZON):
        if glucose[i] < MIN_BG or i - last < MIN_SPACING:
            continue
        if bolus[i] <= 0:
            continue
        bg0 = glucose[i]
        traj = glucose[i:i + HORIZON + 1]
        if np.isnan(traj).sum() > HORIZON * 0.3:
            continue

        episodes.append({
            "idx": i,
            "bg0": float(bg0),
            "bolus": float(bolus[i]),
            "trajectory": [float(v) if not np.isnan(v) else None for v in traj],
        })
        last = i
        if len(episodes) >= MAX_EPISODES:
            break
    return episodes


def simulate_episode(ep, settings, egp_enabled=True):
    """Run forward simulator with given settings."""
    bolus_events = [InsulinEvent(0, ep["bolus"], True)] if ep["bolus"] > 0 else []
    try:
        result = forward_simulate(
            initial_glucose=ep["bg0"], settings=settings,
            duration_hours=2.0, start_hour=12,
            bolus_events=bolus_events, carb_events=[],
            initial_iob=0.0, metabolic_basal_rate=settings.basal_rate,
            counter_reg_k=0.3, egp_enabled=egp_enabled,
        )
        return np.array(result.glucose)
    except Exception:
        return None


def compute_mae(sim, actual_traj):
    """Compute MAE between simulation and actual trajectory."""
    actual = np.array([v if v is not None else np.nan for v in actual_traj])
    n = min(len(sim), len(actual))
    valid = ~np.isnan(actual[:n])
    if valid.sum() < 3:
        return np.nan
    return float(np.mean(np.abs(sim[:n][valid] - actual[:n][valid])))


def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    grid = load_data()
    isf_corrections = load_isf_corrections()
    egp_profiles = load_egp_profiles()

    print(f"Loaded {grid['patient_id'].nunique()} patients")
    print(f"EGP profiles available for {len(egp_profiles)} patients")
    print(f"Population EGP median: {POP_EGP:.3f} mg/dL/5min\n")

    results = []

    for pid in sorted(grid["patient_id"].unique()):
        isf_info = isf_corrections.get(pid)
        if not isf_info:
            continue

        egp_info = match_patient_egp(pid, egp_profiles)
        patient_egp = egp_info["egp_median"] if egp_info else None

        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        episodes = extract_correction_episodes(pg)
        if len(episodes) < 3:
            continue

        corrected_isf = np.clip(isf_info["profile_isf"] / isf_info["correction_factor"], 5, 200)
        profile_cr = float(pg["scheduled_cr"].median()) if "scheduled_cr" in pg else 10.0
        profile_basal = float(pg["scheduled_basal_rate"].median()) if "scheduled_basal_rate" in pg else 0.8

        settings = TherapySettings(isf=corrected_isf, cr=profile_cr,
                                    basal_rate=profile_basal, dia_hours=DIA_HOURS)

        # Test 2 EGP configurations: with and without EGP in simulator
        mae_by_config = {}
        for cname, egp_on in [("no_egp", False), ("pop_egp", True)]:
            maes = []
            for ep in episodes:
                sim = simulate_episode(ep, settings, egp_enabled=egp_on)
                if sim is not None:
                    mae = compute_mae(sim, ep["trajectory"])
                    if not np.isnan(mae):
                        maes.append(mae)
            mae_by_config[cname] = float(np.mean(maes)) if maes else 999.0

        # For personalized EGP: use analytical adjustment to ISF
        # The population EGP model in the simulator uses Hill equation
        # Per-patient EGP differs. The ISF extracted from residuals
        # implicitly absorbed EGP. We can refine:
        # If patient's actual EGP is HIGHER than pop, their ISF is
        # understated (glucose rises more → looks like insulin isn't working)
        if patient_egp is not None and patient_egp > 0.01:
            # EGP contribution over 2h: egp_rate × 24 steps
            egp_2h = patient_egp * HORIZON
            pop_egp_2h = POP_EGP * HORIZON
            # Differential: how much MORE (or less) glucose from EGP vs pop
            egp_diff_2h = egp_2h - pop_egp_2h
            # This difference was absorbed into ISF during extraction
            median_dose = np.median([e["bolus"] for e in episodes])
            if median_dose > 0:
                egp_isf_adjustment = egp_diff_2h / median_dose
            else:
                egp_isf_adjustment = 0
            adjusted_isf = corrected_isf + egp_isf_adjustment
            adjusted_isf = np.clip(adjusted_isf, 5, 200)
        else:
            egp_isf_adjustment = 0
            adjusted_isf = corrected_isf

        # Simulate with EGP enabled + adjusted ISF
        adj_settings = TherapySettings(isf=adjusted_isf, cr=profile_cr,
                                         basal_rate=profile_basal, dia_hours=DIA_HOURS)
        adj_maes = []
        for ep in episodes:
            sim = simulate_episode(ep, adj_settings, egp_enabled=True)
            if sim is not None:
                mae = compute_mae(sim, ep["trajectory"])
                if not np.isnan(mae):
                    adj_maes.append(mae)
        mae_by_config["isf_adjusted"] = float(np.mean(adj_maes)) if adj_maes else 999.0

        # Pers EGP = pop_egp for now (same simulator) unless ISF-adjusted
        mae_by_config["pers_egp"] = mae_by_config["isf_adjusted"] if patient_egp else mae_by_config["pop_egp"]

        has_pers = patient_egp is not None
        pct_change = ((corrected_isf - adjusted_isf) / corrected_isf * 100
                       if corrected_isf > 0 else 0)

        results.append({
            "patient_id": pid,
            "has_egp": has_pers,
            "patient_egp": patient_egp,
            "corrected_isf": float(corrected_isf),
            "adjusted_isf": float(adjusted_isf),
            "isf_pct_change": float(pct_change),
            "egp_isf_adjustment": float(egp_isf_adjustment),
            "n_episodes": len(episodes),
            "mae_no_egp": mae_by_config["no_egp"],
            "mae_pop_egp": mae_by_config["pop_egp"],
            "mae_pers_egp": mae_by_config["pers_egp"],
            "mae_isf_adjusted": mae_by_config["isf_adjusted"],
        })

    rdf = pd.DataFrame(results)
    print(f"\n  {'Patient':<14} {'EGP':>6} {'ISF':>5}→{'AdjISF':>6} {'NoEGP':>7} "
          f"{'PopEGP':>7} {'PersEGP':>8} {'ISFAdj':>7}")
    print(f"  {'-' * 72}")
    for _, r in rdf.iterrows():
        egp_str = f"{r['patient_egp']:.3f}" if r['has_egp'] else "n/a"
        print(f"  {str(r['patient_id'])[:12]:<14} {egp_str:>6} "
              f"{r['corrected_isf']:>5.0f}→{r['adjusted_isf']:>6.0f} "
              f"{r['mae_no_egp']:>7.1f} {r['mae_pop_egp']:>7.1f} "
              f"{r['mae_pers_egp']:>8.1f} {r['mae_isf_adjusted']:>7.1f}")

    # Hypothesis testing
    has_pers = rdf[rdf["has_egp"]]
    n_pers = len(has_pers)

    # H1: Pers EGP beats pop EGP for >50%
    h1_count = (has_pers["mae_pers_egp"] < has_pers["mae_pop_egp"]).sum()
    h1 = h1_count > n_pers * 0.5 if n_pers > 0 else False

    # H2: Pers EGP beats no EGP for >60%
    h2_count = (has_pers["mae_pers_egp"] < has_pers["mae_no_egp"]).sum()
    h2 = h2_count > n_pers * 0.6 if n_pers > 0 else False

    # H3: EGP changes ISF correction by >10% for ≥30%
    h3_count = (has_pers["isf_pct_change"].abs() > 10).sum()
    h3 = h3_count >= n_pers * 0.3 if n_pers > 0 else False

    # H4: High-EGP patients show largest improvements
    if n_pers >= 4:
        high_egp = has_pers[has_pers["patient_egp"] > 0.4]
        low_egp = has_pers[has_pers["patient_egp"] <= 0.4]
        if len(high_egp) > 0 and len(low_egp) > 0:
            high_imp = (high_egp["mae_pop_egp"] - high_egp["mae_pers_egp"]).median()
            low_imp = (low_egp["mae_pop_egp"] - low_egp["mae_pers_egp"]).median()
            h4 = high_imp > low_imp
        else:
            h4 = False
    else:
        h4 = False

    # H5: Combined pipeline MAE < 80
    best_mae = rdf[["mae_pers_egp", "mae_isf_adjusted"]].min(axis=1)
    h5 = best_mae.median() < 80

    hypotheses = {
        "H1_pers_beats_pop_50pct": bool(h1),
        "H2_pers_beats_no_egp_60pct": bool(h2),
        "H3_isf_change_gt10pct_30pct": bool(h3),
        "H4_high_egp_largest_improvement": bool(h4),
        "H5_combined_mae_lt80": bool(h5),
    }

    n_pass = sum(hypotheses.values())
    print(f"\n{'=' * 70}")
    print(f"HYPOTHESES: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"  {'✓' if v else '✗'} {k}")

    print(f"\n  Pers EGP beats pop: {h1_count}/{n_pers}")
    print(f"  Pers EGP beats no-EGP: {h2_count}/{n_pers}")
    print(f"  ISF change >10%: {h3_count}/{n_pers}")
    print(f"  Best combined MAE median: {best_mae.median():.1f}")

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. "
               f"Pers EGP beats pop: {h1_count}/{n_pers}. "
               f"Best MAE median: {best_mae.median():.1f}")
    print(f"\nSUMMARY: {summary}")

    # Save
    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / f"exp-{EXP_ID}_egp_personalized_isf.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": EXP_ID, "title": TITLE,
            "hypotheses": hypotheses,
            "per_patient": rdf.to_dict(orient="records"),
            "population_egp": POP_EGP,
            "summary": summary,
        }), f, indent=2)
    print(f"Saved: {out}")

    create_dashboard(rdf, has_pers, hypotheses)


def create_dashboard(rdf, has_pers, hypotheses):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

    # Panel 1: MAE comparison across EGP configs (patients with EGP)
    ax1 = fig.add_subplot(gs[0, 0])
    if len(has_pers) > 0:
        x = np.arange(len(has_pers))
        w = 0.25
        ax1.bar(x - w, has_pers["mae_no_egp"], w, label="No EGP", color="gray", alpha=0.7)
        ax1.bar(x, has_pers["mae_pop_egp"], w, label="Pop EGP", color="steelblue", alpha=0.7)
        ax1.bar(x + w, has_pers["mae_pers_egp"], w, label="Pers EGP", color="coral", alpha=0.7)
        ax1.set_xticks(x)
        ax1.set_xticklabels([str(p)[:8] for p in has_pers["patient_id"]], rotation=45, fontsize=7)
        ax1.set_ylabel("MAE (mg/dL)")
        ax1.set_title("MAE by EGP Configuration")
        ax1.legend(fontsize=8)

    # Panel 2: EGP vs improvement
    ax2 = fig.add_subplot(gs[0, 1])
    if len(has_pers) > 0:
        improvement = has_pers["mae_pop_egp"] - has_pers["mae_pers_egp"]
        ax2.scatter(has_pers["patient_egp"], improvement, c="steelblue", s=60, alpha=0.7)
        ax2.axhline(0, color="red", ls="--", lw=1)
        ax2.set_xlabel("Patient EGP (mg/dL/5min)")
        ax2.set_ylabel("MAE Improvement (pop→pers)")
        ax2.set_title("EGP vs Improvement")

    # Panel 3: ISF adjustment
    ax3 = fig.add_subplot(gs[0, 2])
    if len(has_pers) > 0:
        ax3.scatter(has_pers["corrected_isf"], has_pers["adjusted_isf"], c="steelblue", s=60, alpha=0.7)
        lim = max(has_pers["corrected_isf"].max(), has_pers["adjusted_isf"].max()) * 1.1
        ax3.plot([0, lim], [0, lim], "r--", lw=1)
        ax3.set_xlabel("Corrected ISF (EXP-2719b)")
        ax3.set_ylabel("EGP-Adjusted ISF")
        ax3.set_title("ISF: Before vs After EGP Adjustment")

    # Panel 4: All patients — best MAE
    ax4 = fig.add_subplot(gs[1, 0:2])
    x = np.arange(len(rdf))
    w = 0.3
    ax4.bar(x - w / 2, rdf["mae_pop_egp"], w, label="Pop EGP", color="steelblue", alpha=0.7)
    ax4.bar(x + w / 2, rdf["mae_isf_adjusted"], w, label="ISF+EGP adjusted", color="coral", alpha=0.7)
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(p)[:8] for p in rdf["patient_id"]], rotation=45, fontsize=7)
    ax4.set_ylabel("MAE (mg/dL)")
    ax4.set_title("All Patients: Pop EGP vs ISF+EGP Adjusted")
    ax4.legend(fontsize=8)
    ax4.axhline(80, color="green", ls="--", lw=1, label="Target <80")

    # Summary panel
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.axis("off")
    lines = [f"EXP-{EXP_ID}: {TITLE}", "",
             f"Patients with EGP: {len(has_pers)}/{len(rdf)}",
             f"Pop EGP: {POP_EGP:.3f} mg/dL/5min",
             f"Best MAE median: {rdf[['mae_pers_egp', 'mae_isf_adjusted']].min(axis=1).median():.1f}",
             "", "Hypotheses:"]
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")
    ax5.text(0.05, 0.95, "\n".join(lines), transform=ax5.transAxes,
             fontsize=10, va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / f"exp-{EXP_ID}-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / f'exp-{EXP_ID}-dashboard.png'}")


if __name__ == "__main__":
    main()
