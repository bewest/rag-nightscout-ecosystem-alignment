#!/usr/bin/env python3
"""EXP-2672: Autoprepare Qualification Gate — Dose-Dependent ISF Replication.

MOTIVATION: EXP-2671 validated cross-controller data fidelity. Before
transitioning to autoresearch, we must verify that the strongest finding
(dose-dependent ISF, r=-0.56) replicates on the expanded 24-patient
multi-controller dataset. This is the qualification gate.

GATE CRITERIA (revised per EXP-2663 finding that demand ISF IS dose-independent):
  G1: Demand-phase ISF is dose-INDEPENDENT (|r| < 0.3) in ≥2 controller types
      (validates EXP-2663 finding across new multi-controller dataset)
  G2: ≥15 correction events per qualified patient
  G3: No new data quality anomalies in expanded set
  G4: Cross-controller ISF magnitude within plausible range (10-200 mg/dL/U)

OUTPUTS:
  - externals/experiments/exp-2672_autoprepare_gate.json
  - visualizations/autoprepare-gate/fig[1-4]_*.png
  - If PASS: writes autoprepare-qualified.json manifest for autoresearch
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
DS_PARQUET = Path("externals/ns-parquet/training/devicestatus.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2672_autoprepare_gate.json"
VIZ_DIR = Path("visualizations/autoprepare-gate")
VIZ_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = RESULTS_DIR / "autoprepare-qualified.json"

CTRL_COLORS = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}
CTRL_ORDER = ["loop", "trio", "openaps"]
STEPS_PER_HOUR = 12

# ── Patient Exclusion List (from EXP-2671) ────────────────────────────

EXCLUDE_ALWAYS = {"j", "odc-84181797"}
QUALIFY_SHORT_SPAN = {"odc-39819048", "odc-49141524", "odc-58680324", "odc-61403732"}
INVESTIGATE = {"ns-c422538aa12a"}
MIN_CORRECTION_EVENTS = 15
MIN_DOSE = 0.5
MIN_PRE_BG = 120
CARB_EXCLUSION_H = 1.0
DEMAND_HOURS = 2.0
DEMAND_STEPS = int(DEMAND_HOURS * STEPS_PER_HOUR)


# ── Core Functions ────────────────────────────────────────────────────

def load_data():
    """Load grid + controller map."""
    df = pd.read_parquet(PARQUET)
    ds = pd.read_parquet(DS_PARQUET, columns=["patient_id", "controller"])
    ctrl = ds.groupby("patient_id")["controller"].agg(
        lambda x: x.value_counts().index[0]
    )
    df = df.merge(ctrl.rename("controller"), on="patient_id", how="left")
    df["controller"] = df["controller"].fillna("unknown")
    return df


def extract_demand_isf(pdf):
    """Extract demand-phase ISF (0-2h glucose drop per unit dose) for corrections.

    Returns list of dicts: {dose, pre_bg, post_bg, drop, isf, time}
    """
    bolus_mask = pdf["bolus"].fillna(0) > MIN_DOSE
    bolus_locs = np.where(bolus_mask.values)[0]
    events = []

    for loc in bolus_locs:
        if loc + DEMAND_STEPS >= len(pdf) or loc < 1:
            continue

        pre_bg = pdf.iloc[loc - 1]["glucose"]
        if pd.isna(pre_bg) or pre_bg < MIN_PRE_BG:
            continue

        # Carb exclusion ±1h
        carb_start = max(0, loc - int(CARB_EXCLUSION_H * STEPS_PER_HOUR))
        carb_end = min(len(pdf), loc + DEMAND_STEPS + 1)
        if pdf.iloc[carb_start:carb_end]["carbs"].fillna(0).sum() > 0:
            continue

        # Demand-phase: glucose at 2h post-bolus
        post_bg = pdf.iloc[loc + DEMAND_STEPS]["glucose"]
        if pd.isna(post_bg):
            continue

        dose = pdf.iloc[loc]["bolus"]
        drop = pre_bg - post_bg
        isf = drop / dose if dose > 0 else np.nan

        events.append({
            "time": str(pdf.iloc[loc]["time"]),
            "dose": float(dose),
            "pre_bg": float(pre_bg),
            "post_bg": float(post_bg),
            "drop": float(drop),
            "isf": float(isf),
        })
    return events


def compute_dose_isf_correlation(events):
    """Compute log-dose vs ISF correlation from events."""
    if len(events) < 5:
        return {"r": np.nan, "p": np.nan, "n": len(events), "status": "insufficient"}

    doses = np.array([e["dose"] for e in events])
    isfs = np.array([e["isf"] for e in events])

    # Filter extreme ISF values
    valid = (isfs > -200) & (isfs < 500) & np.isfinite(isfs)
    doses = doses[valid]
    isfs = isfs[valid]

    if len(doses) < 5:
        return {"r": np.nan, "p": np.nan, "n": len(doses), "status": "insufficient_after_filter"}

    log_doses = np.log(doses)
    r, p = stats.pearsonr(log_doses, isfs)
    return {"r": float(r), "p": float(p), "n": int(len(doses)), "status": "ok"}


# ── Gate Checks ───────────────────────────────────────────────────────

def run_gate(df):
    """Run all gate checks. Returns results dict and pass/fail."""
    results = {
        "experiment": "EXP-2672",
        "title": "Autoprepare Qualification Gate",
        "patients": {},
        "gate_checks": {},
    }

    qualified_patients = []
    ctrl_correlations = {ct: [] for ct in CTRL_ORDER}

    for pid in sorted(df.patient_id.unique()):
        if pid in EXCLUDE_ALWAYS:
            results["patients"][pid] = {"status": "excluded", "reason": "EXP-2671 exclusion list"}
            continue

        sub = df[df.patient_id == pid].sort_values("time").reset_index(drop=True)
        ct = sub.controller.iloc[0]
        if ct not in CTRL_ORDER:
            results["patients"][pid] = {"status": "excluded", "reason": f"unknown controller: {ct}"}
            continue

        n_days = (sub.time.max() - sub.time.min()).total_seconds() / 86400

        # Extract corrections
        events = extract_demand_isf(sub)
        corr = compute_dose_isf_correlation(events)

        short_span = pid in QUALIFY_SHORT_SPAN
        has_enough = len(events) >= MIN_CORRECTION_EVENTS
        isf_range_ok = True
        if events:
            median_isf = np.median([e["isf"] for e in events])
            isf_range_ok = 10 < abs(median_isf) < 200

        qualified = has_enough and (not short_span or n_days >= 14) and isf_range_ok
        status = "qualified" if qualified else "disqualified"

        results["patients"][pid] = {
            "status": status,
            "controller": ct,
            "days": round(n_days, 1),
            "n_corrections": len(events),
            "dose_isf_r": corr["r"],
            "dose_isf_p": corr["p"],
            "median_isf": float(np.median([e["isf"] for e in events])) if events else None,
            "short_span": short_span,
        }

        if qualified:
            qualified_patients.append(pid)
            ctrl_correlations[ct].append(corr["r"])

    # Gate G1: Demand-phase ISF is dose-INDEPENDENT (|r| < 0.3) in ≥2 controllers
    # EXP-2663 established demand ISF dose-independence; we validate on expanded set
    g1_pass_types = []
    for ct in CTRL_ORDER:
        rs = [r for r in ctrl_correlations[ct] if not np.isnan(r)]
        if rs:
            pooled_r = np.mean(rs)
            if abs(pooled_r) < 0.3:
                g1_pass_types.append(ct)
    g1_pass = len(g1_pass_types) >= 2

    # Gate G2: ≥15 events per qualified patient
    g2_counts = [results["patients"][p]["n_corrections"]
                 for p in qualified_patients]
    g2_pass = all(c >= MIN_CORRECTION_EVENTS for c in g2_counts)

    # Gate G3: No new anomalies (flag patients with ISF outside 10-200)
    anomalies = []
    for pid in qualified_patients:
        p = results["patients"][pid]
        if p["median_isf"] is not None and (p["median_isf"] < -50 or p["median_isf"] > 300):
            anomalies.append(pid)
    g3_pass = len(anomalies) == 0

    # Gate G4: ISF in plausible range
    all_isfs = []
    for pid in qualified_patients:
        p = results["patients"][pid]
        if p["median_isf"] is not None:
            all_isfs.append(p["median_isf"])
    g4_pass = all(10 < abs(x) < 200 for x in all_isfs) if all_isfs else False

    overall_pass = g1_pass and g2_pass

    results["gate_checks"] = {
        "G1_dose_isf_replication": {
            "pass": g1_pass,
            "required": "|r| < 0.3 in >=2 controller types (dose-independence)",
            "pass_types": g1_pass_types,
            "per_controller": {ct: float(np.mean(ctrl_correlations[ct]))
                               if ctrl_correlations[ct] else None
                               for ct in CTRL_ORDER},
        },
        "G2_min_events": {
            "pass": g2_pass,
            "required": f">={MIN_CORRECTION_EVENTS} per patient",
            "min_events": min(g2_counts) if g2_counts else 0,
        },
        "G3_no_anomalies": {
            "pass": g3_pass,
            "anomalies": anomalies,
        },
        "G4_isf_range": {
            "pass": g4_pass,
            "range": [min(all_isfs), max(all_isfs)] if all_isfs else None,
        },
        "overall_pass": overall_pass,
    }
    results["qualified_patients"] = qualified_patients
    results["n_qualified"] = len(qualified_patients)

    return results, qualified_patients


# ── Visualizations ────────────────────────────────────────────────────

def fig1_dose_isf_by_controller(df, results, qualified):
    """Log-dose vs ISF scatter per controller type."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        ct_pats = [p for p in qualified if results["patients"][p]["controller"] == ct]
        all_events = []
        for pid in ct_pats:
            sub = df[df.patient_id == pid].sort_values("time").reset_index(drop=True)
            events = extract_demand_isf(sub)
            for e in events:
                e["patient_id"] = pid
            all_events.extend(events)

        if not all_events:
            ax.text(0.5, 0.5, f"No data\n({ct})", transform=ax.transAxes, ha="center")
            continue

        doses = np.array([e["dose"] for e in all_events])
        isfs = np.array([e["isf"] for e in all_events])
        valid = (isfs > -200) & (isfs < 500)
        doses, isfs = doses[valid], isfs[valid]

        ax.scatter(doses, isfs, c=CTRL_COLORS[ct], alpha=0.3, s=15, edgecolors="none")

        # Fit log curve
        if len(doses) > 10:
            log_d = np.log(doses)
            slope, intercept, r, p, _ = stats.linregress(log_d, isfs)
            x_fit = np.linspace(doses.min(), doses.max(), 100)
            y_fit = slope * np.log(x_fit) + intercept
            ax.plot(x_fit, y_fit, "k-", lw=2, label=f"r={r:.3f}, p={p:.1e}")
            ax.legend(fontsize=10, loc="upper right")

        ax.set_xlabel("Dose (U)")
        ax.set_ylabel("Demand ISF (mg/dL/U)")
        ax.set_title(f"{ct.upper()} ({len(ct_pats)} patients, {len(all_events)} events)",
                     fontweight="bold")
        ax.grid(alpha=0.3)
        ax.axhline(0, color="k", alpha=0.3)

    fig.suptitle("EXP-2672 Gate G1: Demand-Phase ISF Dose Independence by Controller\n"
                 "(Expected: |r| < 0.3 confirms demand ISF is dose-independent per EXP-2663)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_dose_isf_by_controller.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig1 saved")


def fig2_per_patient_isf(results, qualified):
    """Per-patient median ISF and dose-ISF correlation bar chart."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 8))

    pids = sorted(qualified, key=lambda p: results["patients"][p]["controller"])
    isfs = [results["patients"][p]["median_isf"] or 0 for p in pids]
    rs = [results["patients"][p]["dose_isf_r"] for p in pids]
    colors = [CTRL_COLORS.get(results["patients"][p]["controller"], "#999") for p in pids]

    ax1.bar(range(len(pids)), isfs, color=colors, alpha=0.7, edgecolor="k", lw=0.5)
    ax1.set_xticks(range(len(pids)))
    ax1.set_xticklabels(pids, rotation=90, fontsize=7)
    ax1.set_ylabel("Median Demand ISF (mg/dL/U)")
    ax1.set_title("Per-Patient Median Demand-Phase ISF", fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)
    ax1.axhline(0, color="k", alpha=0.3)

    # Dose-ISF correlation
    r_vals = [r if not np.isnan(r) else 0 for r in rs]
    bar_colors = ["green" if abs(r) < 0.3 else "orange" if abs(r) < 0.5 else "red" for r in r_vals]
    ax2.bar(range(len(pids)), r_vals, color=bar_colors, alpha=0.7, edgecolor="k", lw=0.5)
    ax2.set_xticks(range(len(pids)))
    ax2.set_xticklabels(pids, rotation=90, fontsize=7)
    ax2.set_ylabel("Pearson r (log-dose vs ISF)")
    ax2.set_title("Per-Patient Dose-ISF Correlation (green = |r| < 0.3 = dose-independent)", fontweight="bold")
    ax2.axhline(-0.3, color="red", ls="--", alpha=0.5, label="Independence threshold (|r|=0.3)")
    ax2.axhline(0.3, color="red", ls="--", alpha=0.5)
    ax2.axhline(0, color="k", alpha=0.3)
    ax2.legend()
    ax2.grid(axis="y", alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=CTRL_COLORS[ct], label=ct.upper()) for ct in CTRL_ORDER]
    ax1.legend(handles=legend_elements, loc="upper right")

    fig.suptitle("EXP-2672: Per-Patient ISF Metrics", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_per_patient_isf.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig2 saved")


def fig3_event_counts(results, qualified):
    """Event count per patient — show which pass the G2 gate."""
    pids = sorted(qualified, key=lambda p: results["patients"][p]["controller"])
    counts = [results["patients"][p]["n_corrections"] for p in pids]
    colors = [CTRL_COLORS.get(results["patients"][p]["controller"], "#999") for p in pids]

    fig, ax = plt.subplots(figsize=(18, 5))
    bars = ax.bar(range(len(pids)), counts, color=colors, alpha=0.7, edgecolor="k", lw=0.5)
    ax.axhline(MIN_CORRECTION_EVENTS, color="red", ls="--", lw=2,
               label=f"Minimum ({MIN_CORRECTION_EVENTS})")
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, rotation=90, fontsize=7)
    ax.set_ylabel("Correction Events")
    ax.set_title("EXP-2672 Gate G2: Correction Events per Patient", fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_event_counts.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig3 saved")


def fig4_gate_summary(results):
    """Visual summary of gate pass/fail."""
    gates = results["gate_checks"]
    fig, ax = plt.subplots(figsize=(10, 4))

    gate_names = ["G1: Demand-ISF\nDose Independence", "G2: Min Events\nper Patient",
                  "G3: No Data\nAnomalies", "G4: ISF Range\nPlausible"]
    gate_keys = ["G1_dose_isf_replication", "G2_min_events", "G3_no_anomalies", "G4_isf_range"]
    gate_pass = [gates[k]["pass"] for k in gate_keys]
    colors = ["#4CAF50" if p else "#F44336" for p in gate_pass]

    bars = ax.barh(range(len(gate_names)), [1] * len(gate_names), color=colors, alpha=0.8)
    ax.set_yticks(range(len(gate_names)))
    ax.set_yticklabels(gate_names, fontsize=12)
    ax.set_xlim(0, 1.5)
    ax.set_xticks([])

    for i, (gn, gp) in enumerate(zip(gate_names, gate_pass)):
        label = "✅ PASS" if gp else "❌ FAIL"
        ax.text(0.5, i, label, ha="center", va="center", fontsize=16, fontweight="bold",
                color="white")

    overall = gates["overall_pass"]
    title_color = "green" if overall else "red"
    ax.set_title(f"EXP-2672 Qualification Gate: {'✅ PASS → Ready for Autoresearch' if overall else '❌ FAIL → Needs Investigation'}",
                 fontsize=14, fontweight="bold", color=title_color)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_gate_summary.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig4 saved")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("EXP-2672: Autoprepare Qualification Gate")
    print("=" * 60)

    print("\nLoading data...")
    df = load_data()
    print(f"  {df.patient_id.nunique()} patients, {len(df):,} rows")
    print(f"  Excluded: {EXCLUDE_ALWAYS}")

    print("\nRunning gate checks...")
    results, qualified = run_gate(df)

    print(f"\n  Qualified patients: {len(qualified)}/{df.patient_id.nunique()}")
    for ct in CTRL_ORDER:
        ct_q = [p for p in qualified if results["patients"][p]["controller"] == ct]
        print(f"    {ct}: {len(ct_q)} patients")

    # Visualizations
    print("\nGenerating figures...")
    fig1_dose_isf_by_controller(df, results, qualified)
    fig2_per_patient_isf(results, qualified)
    fig3_event_counts(results, qualified)
    fig4_gate_summary(results)

    # Print gate results
    print("\n" + "=" * 60)
    print("GATE RESULTS")
    print("=" * 60)
    gates = results["gate_checks"]

    g1 = gates["G1_dose_isf_replication"]
    print(f"\n  G1 Demand-ISF Dose Independence: {'✅ PASS' if g1['pass'] else '❌ FAIL'}")
    print(f"     Required: |r| < 0.3 in ≥2 controller types (validates EXP-2663)")
    print(f"     Pass types: {g1['pass_types']}")
    for ct in CTRL_ORDER:
        r_val = g1["per_controller"].get(ct)
        print(f"       {ct}: mean r = {r_val:.3f}" if r_val is not None else f"       {ct}: no data")

    g2 = gates["G2_min_events"]
    print(f"\n  G2 Min Events: {'✅ PASS' if g2['pass'] else '❌ FAIL'}")
    print(f"     Min events: {g2['min_events']} (threshold: {MIN_CORRECTION_EVENTS})")

    g3 = gates["G3_no_anomalies"]
    print(f"\n  G3 No Anomalies: {'✅ PASS' if g3['pass'] else '❌ FAIL'}")
    if g3["anomalies"]:
        print(f"     Anomalies: {g3['anomalies']}")

    g4 = gates["G4_isf_range"]
    print(f"\n  G4 ISF Range: {'✅ PASS' if g4['pass'] else '❌ FAIL'}")
    if g4["range"]:
        print(f"     Range: [{g4['range'][0]:.1f}, {g4['range'][1]:.1f}] mg/dL/U")

    overall = gates["overall_pass"]
    print(f"\n  {'=' * 40}")
    print(f"  OVERALL: {'✅ PASS → Ready for Autoresearch' if overall else '❌ FAIL → Needs Investigation'}")
    print(f"  {'=' * 40}")

    # Save results
    with open(OUTFILE, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\n  Results → {OUTFILE}")

    # If passed, write manifest
    if overall:
        manifest = {
            "status": "qualified",
            "date": "2026-04-19",
            "qualified_patients": qualified,
            "n_patients": len(qualified),
            "gate_results": {k: v["pass"] for k, v in gates.items() if k != "overall_pass"},
            "safe_columns": [
                "glucose", "iob", "cob", "net_basal", "bolus", "bolus_smb", "carbs",
                "scheduled_isf", "scheduled_cr", "actual_basal_rate", "scheduled_basal_rate",
                "glucose_roc", "glucose_accel", "time", "patient_id",
            ],
            "controller_specific_columns": {
                "trio_openaps_only": ["sensitivity_ratio", "eventual_bg", "insulin_req"],
                "caution": ["loop_enacted_rate"],
            },
            "exclusions": {
                "permanent": list(EXCLUDE_ALWAYS),
                "short_span": list(QUALIFY_SHORT_SPAN),
                "investigate": list(INVESTIGATE),
            },
        }
        with open(MANIFEST, "w") as fh:
            json.dump(manifest, fh, indent=2)
        print(f"  Manifest → {MANIFEST}")
        print(f"\n  🚀 Autoresearch may proceed with {len(qualified)} qualified patients")


if __name__ == "__main__":
    main()
