#!/usr/bin/env python3
"""EXP-2677: AID Compensation Artifact in Correction Events

Investigates why 24-52% of correction boluses show NEGATIVE ISF (glucose
rises after correction) across ALL controllers. This is not Trio-specific.

Hypotheses:
  H1: AID controller reduces basal/SMBs after correction → net insulin unchanged
  H2: Glucose was already rising (carb tail, dawn phenomenon)
  H3: Corrections happen at glucose nadir → glucose would have risen anyway

Panels:
  1. Negative ISF prevalence by controller and patient
  2. Pre-bolus glucose trajectory (positive vs negative ISF events)
  3. Net insulin delivery: total IOB change during 0-2h window
  4. Basal adjustment: enacted rate before vs after correction
  5. Time-of-day distribution of negative vs positive ISF events
  6. Glucose level at correction: negative ISF at lower starting BG?
"""

import json
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
DS = ROOT / "externals/ns-parquet/training/devicestatus.parquet"
MANIFEST = ROOT / "externals/experiments/autoprepare-qualified.json"
VIS_DIR = ROOT / "visualizations/aid-compensation-artifact"
EXP_DIR = ROOT / "externals/experiments"

VIS_DIR.mkdir(parents=True, exist_ok=True)

PRIOR_ISOLATION_H = 2.0
POST_WINDOW_H = 2.0
MIN_DOSE = 0.3
MAX_COB = 5


def load_data():
    manifest = json.load(open(MANIFEST))
    qp = manifest["qualified_patients"]
    grid = pd.read_parquet(GRID)
    grid = grid[grid.patient_id.isin(qp)]
    ds = pd.read_parquet(DS)
    ds = ds[ds.patient_id.isin(qp)]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    return grid, ds, ctrl_map, qp


def extract_correction_events(grid, ctrl_map):
    """Extract correction events with full context."""
    events = []

    for pid in grid.patient_id.unique():
        pgrid = grid[grid.patient_id == pid].sort_values("time")
        ctrl = ctrl_map.get(pid, "unknown")

        corrections = pgrid[(pgrid.bolus > MIN_DOSE) & (pgrid.cob < MAX_COB)]

        for _, row in corrections.iterrows():
            bt = row.time
            if not isinstance(bt, pd.Timestamp):
                bt = pd.Timestamp(bt)

            # Pre window (-2h to 0)
            pre = pgrid[(pgrid.time >= bt - pd.Timedelta(hours=PRIOR_ISOLATION_H)) &
                        (pgrid.time < bt)]
            # Check isolation
            if pre.bolus.sum() > 0.1:
                continue

            # Post window (0 to +2h)
            post = pgrid[(pgrid.time >= bt) &
                         (pgrid.time <= bt + pd.Timedelta(hours=POST_WINDOW_H))]
            if len(post) < 6:
                continue

            bg0 = post.glucose.iloc[0]
            bg_2h = post.glucose.iloc[-1]
            if pd.isna(bg0) or pd.isna(bg_2h):
                continue

            drop = bg0 - bg_2h
            isf = drop / row.bolus

            # Context metrics
            event = {
                "patient_id": pid,
                "controller": ctrl,
                "time": bt,
                "dose": row.bolus,
                "bg_at_bolus": bg0,
                "bg_at_2h": bg_2h,
                "bg_drop": drop,
                "isf": isf,
                "negative_isf": isf < 0,
                "iob_at_bolus": row.iob if pd.notna(row.iob) else np.nan,
                "hour_of_day": bt.hour if hasattr(bt, 'hour') else pd.Timestamp(bt).hour,
            }

            # Pre-bolus glucose trend (ROC from -30min to 0)
            pre_30 = pgrid[(pgrid.time >= bt - pd.Timedelta(minutes=30)) &
                           (pgrid.time < bt)]
            if len(pre_30) >= 3 and pre_30.glucose.notna().sum() >= 3:
                bg_minus30 = pre_30.glucose.dropna().iloc[0]
                event["pre_roc"] = (bg0 - bg_minus30) / 30  # mg/dL/min
            else:
                event["pre_roc"] = np.nan

            # IOB change during window
            if pd.notna(row.iob) and pd.notna(post.iob.iloc[-1]):
                event["iob_change"] = post.iob.iloc[-1] - row.iob
            else:
                event["iob_change"] = np.nan

            # Net basal during window
            post_basal = post.actual_basal_rate.dropna()
            sched_basal = post.scheduled_basal_rate.dropna()
            if len(post_basal) > 3 and len(sched_basal) > 3:
                event["avg_enacted_basal"] = post_basal.mean()
                event["avg_scheduled_basal"] = sched_basal.mean()
                event["basal_ratio"] = post_basal.mean() / max(sched_basal.mean(), 0.01)
            else:
                event["avg_enacted_basal"] = np.nan
                event["avg_scheduled_basal"] = np.nan
                event["basal_ratio"] = np.nan

            # SMBs during post window
            post_smbs = post.bolus_smb.sum() if "bolus_smb" in post.columns else 0
            event["smbs_in_window"] = post_smbs

            events.append(event)

    return pd.DataFrame(events)


def panel1_prevalence(edf):
    """Panel 1: Negative ISF prevalence by controller and patient."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # By controller
    ax = axes[0]
    for ctrl in ["loop", "trio", "openaps"]:
        sub = edf[edf.controller == ctrl]
        if len(sub) == 0:
            continue
        pct_neg = 100 * sub.negative_isf.mean()
        n = len(sub)
        color = {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl]
        ax.bar(ctrl.upper(), pct_neg, color=color, alpha=0.7)
        ax.text(ctrl.upper(), pct_neg + 1, f"n={n}\n{pct_neg:.0f}%",
                ha="center", fontsize=10)
    ax.set_ylabel("% Correction Events with Negative ISF")
    ax.set_title("Negative ISF Prevalence by Controller")
    ax.set_ylim(0, 60)
    ax.grid(True, alpha=0.3, axis="y")

    # By patient
    ax = axes[1]
    patient_stats = edf.groupby("patient_id").agg(
        pct_neg=("negative_isf", "mean"),
        n=("negative_isf", "count"),
        controller=("controller", "first")
    ).reset_index()
    patient_stats["pct_neg"] *= 100
    patient_stats = patient_stats.sort_values("pct_neg")

    colors = patient_stats.controller.map(
        {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}).values
    ax.barh(range(len(patient_stats)), patient_stats.pct_neg, color=colors, alpha=0.7)
    ax.set_yticks(range(len(patient_stats)))
    ax.set_yticklabels([f"{r.patient_id[:10]} (n={r.n})"
                        for _, r in patient_stats.iterrows()], fontsize=7)
    ax.set_xlabel("% Negative ISF Events")
    ax.set_title("Per-Patient Negative ISF Rate")
    ax.axvline(50, color="red", ls="--", alpha=0.5, label="50% threshold")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="x")

    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig1_negative_isf_prevalence.png", dpi=150)
    plt.close(fig)
    print("  Panel 1: Negative ISF prevalence saved")
    return {
        "overall_pct_neg": float(100 * edf.negative_isf.mean()),
        "by_controller": {ctrl: float(100 * sub.negative_isf.mean())
                          for ctrl in ["loop", "trio", "openaps"]
                          if len(sub := edf[edf.controller == ctrl]) > 0}
    }


def panel2_pre_trajectory(edf, grid):
    """Panel 2: Pre-bolus glucose trajectory for positive vs negative ISF."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        sub = edf[edf.controller == ctrl]
        if len(sub) < 20:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data",
                    transform=ax.transAxes, ha="center", va="center")
            continue

        pos = sub[~sub.negative_isf]
        neg = sub[sub.negative_isf]

        # Pre-bolus ROC comparison
        for group, label, color in [(pos, "Positive ISF", "green"), (neg, "Negative ISF", "red")]:
            rocs = group.pre_roc.dropna()
            if len(rocs) > 10:
                ax.hist(rocs, bins=30, alpha=0.4, color=color, density=True, label=label)
                ax.axvline(rocs.median(), color=color, ls="--", lw=2)

        ax.set_title(f"{ctrl.upper()}")
        ax.set_xlabel("Pre-bolus glucose ROC (mg/dL/min)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Panel 2: Pre-Bolus Glucose Trend (Positive vs Negative ISF)", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig2_pre_trajectory.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 2: Pre-trajectory saved")

    roc_pos = edf[~edf.negative_isf].pre_roc.dropna()
    roc_neg = edf[edf.negative_isf].pre_roc.dropna()
    return {
        "positive_isf_median_roc": float(roc_pos.median()) if len(roc_pos) > 0 else None,
        "negative_isf_median_roc": float(roc_neg.median()) if len(roc_neg) > 0 else None,
    }


def panel3_net_insulin(edf):
    """Panel 3: Net insulin delivery (IOB change) during 0-2h window."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    results = {}
    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        sub = edf[edf.controller == ctrl].dropna(subset=["iob_change"])
        if len(sub) < 20:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data",
                    transform=ax.transAxes, ha="center", va="center")
            continue

        pos = sub[~sub.negative_isf]
        neg = sub[sub.negative_isf]

        for group, label, color in [(pos, "Positive ISF", "green"), (neg, "Negative ISF", "red")]:
            if len(group) > 5:
                ax.hist(group.iob_change, bins=30, alpha=0.4, color=color,
                        density=True, label=f"{label} (med={group.iob_change.median():.2f})")
                ax.axvline(group.iob_change.median(), color=color, ls="--", lw=2)

        ax.set_title(f"{ctrl.upper()}")
        ax.set_xlabel("IOB change (0 to 2h) [U]")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.axvline(0, color="gray", ls="-", alpha=0.3)

        results[ctrl] = {
            "pos_median_iob_change": float(pos.iob_change.median()) if len(pos) > 0 else None,
            "neg_median_iob_change": float(neg.iob_change.median()) if len(neg) > 0 else None,
        }

    fig.suptitle("Panel 3: IOB Change During 2h Post-Correction (AID compensation signal)", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig3_net_insulin.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 3: Net insulin saved")
    return results


def panel4_basal_adjustment(edf):
    """Panel 4: Basal rate ratio (enacted/scheduled) around corrections."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    results = {}
    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        sub = edf[edf.controller == ctrl].dropna(subset=["basal_ratio"])
        if len(sub) < 20:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data",
                    transform=ax.transAxes, ha="center", va="center")
            continue

        pos = sub[~sub.negative_isf]
        neg = sub[sub.negative_isf]

        for group, label, color in [(pos, "Positive ISF", "green"), (neg, "Negative ISF", "red")]:
            ratios = group.basal_ratio.clip(0, 3)
            if len(ratios) > 5:
                ax.hist(ratios, bins=30, alpha=0.4, color=color, density=True,
                        label=f"{label} (med={ratios.median():.2f})")
                ax.axvline(ratios.median(), color=color, ls="--", lw=2)

        ax.axvline(1.0, color="gray", ls="-", lw=2, alpha=0.5, label="Scheduled rate")
        ax.set_title(f"{ctrl.upper()}")
        ax.set_xlabel("Basal ratio (enacted / scheduled)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        results[ctrl] = {
            "pos_median_ratio": float(pos.basal_ratio.median()) if len(pos) > 0 else None,
            "neg_median_ratio": float(neg.basal_ratio.median()) if len(neg) > 0 else None,
        }

    fig.suptitle("Panel 4: Basal Rate Adjustment During 2h Post-Correction", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig4_basal_adjustment.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 4: Basal adjustment saved")
    return results


def panel5_time_of_day(edf):
    """Panel 5: Time-of-day distribution of negative vs positive ISF."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        sub = edf[edf.controller == ctrl]
        if len(sub) < 20:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data",
                    transform=ax.transAxes, ha="center", va="center")
            continue

        hours = np.arange(24)
        pos_counts = sub[~sub.negative_isf].hour_of_day.value_counts().reindex(hours, fill_value=0)
        neg_counts = sub[sub.negative_isf].hour_of_day.value_counts().reindex(hours, fill_value=0)

        total = pos_counts + neg_counts
        neg_pct = np.where(total > 0, 100 * neg_counts / total, 0)

        ax.bar(hours, neg_pct, color="red", alpha=0.4, label="% Negative ISF")
        ax.set_xlabel("Hour of Day (UTC)")
        ax.set_ylabel("% Negative ISF")
        ax.set_title(f"{ctrl.upper()}")
        ax.set_ylim(0, 70)
        ax.axhline(edf[edf.controller == ctrl].negative_isf.mean() * 100,
                    color="black", ls="--", alpha=0.5, label="Overall mean")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Panel 5: Negative ISF Rate by Time of Day", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig5_time_of_day.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 5: Time of day saved")


def panel6_glucose_level(edf):
    """Panel 6: Starting glucose level for negative vs positive ISF events."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    results = {}
    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        sub = edf[edf.controller == ctrl]
        if len(sub) < 20:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data",
                    transform=ax.transAxes, ha="center", va="center")
            continue

        pos = sub[~sub.negative_isf]
        neg = sub[sub.negative_isf]

        for group, label, color in [(pos, "Positive ISF", "green"), (neg, "Negative ISF", "red")]:
            bg = group.bg_at_bolus.dropna()
            if len(bg) > 10:
                ax.hist(bg, bins=30, alpha=0.4, color=color, density=True,
                        label=f"{label} (med={bg.median():.0f})")
                ax.axvline(bg.median(), color=color, ls="--", lw=2)

        ax.axvline(180, color="orange", ls=":", alpha=0.5, label="High threshold")
        ax.set_title(f"{ctrl.upper()}")
        ax.set_xlabel("Glucose at correction (mg/dL)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        results[ctrl] = {
            "pos_median_bg": float(pos.bg_at_bolus.median()),
            "neg_median_bg": float(neg.bg_at_bolus.median()),
        }

    fig.suptitle("Panel 6: Starting Glucose Level (Positive vs Negative ISF)", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig6_glucose_level.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 6: Glucose level saved")
    return results


def main():
    print("=" * 70)
    print("EXP-2677: AID Compensation Artifact in Correction Events")
    print("=" * 70)

    print("\nLoading data...")
    grid, ds, ctrl_map, qp = load_data()

    print("Extracting correction events...")
    edf = extract_correction_events(grid, ctrl_map)
    print(f"  {len(edf)} correction events from {edf.patient_id.nunique()} patients")
    print(f"  {100 * edf.negative_isf.mean():.1f}% have negative ISF (glucose rose)")

    results = {
        "experiment": "EXP-2677",
        "title": "AID Compensation Artifact in Correction Events",
        "n_events": len(edf),
        "n_patients": int(edf.patient_id.nunique()),
        "overall_pct_negative": float(100 * edf.negative_isf.mean()),
    }

    print("\nRunning panels...")
    results["prevalence"] = panel1_prevalence(edf)
    results["pre_trajectory"] = panel2_pre_trajectory(edf, grid)
    results["net_insulin"] = panel3_net_insulin(edf)
    results["basal_adjustment"] = panel4_basal_adjustment(edf)
    panel5_time_of_day(edf)
    results["glucose_level"] = panel6_glucose_level(edf)

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n## Overall: {results['overall_pct_negative']:.1f}% negative ISF "
          f"({len(edf)} events, {edf.patient_id.nunique()} patients)")

    print("\n## Panel 1: Prevalence by Controller")
    for ctrl, pct in results["prevalence"]["by_controller"].items():
        n = len(edf[edf.controller == ctrl])
        print(f"  {ctrl.upper()}: {pct:.1f}% negative ({n} events)")

    print("\n## Panel 2: Pre-Bolus Glucose Trend")
    pt = results["pre_trajectory"]
    print(f"  Positive ISF events: median ROC = {pt['positive_isf_median_roc']:.3f} mg/dL/min"
          if pt['positive_isf_median_roc'] is not None else "  Positive ISF: no data")
    print(f"  Negative ISF events: median ROC = {pt['negative_isf_median_roc']:.3f} mg/dL/min"
          if pt['negative_isf_median_roc'] is not None else "  Negative ISF: no data")

    print("\n## Panel 3: IOB Change (AID compensation)")
    for ctrl, r in results["net_insulin"].items():
        print(f"  {ctrl.upper()}: pos ISF → IOB Δ={r['pos_median_iob_change']:.2f}U, "
              f"neg ISF → IOB Δ={r['neg_median_iob_change']:.2f}U"
              if r.get("pos_median_iob_change") is not None else f"  {ctrl.upper()}: no data")

    print("\n## Panel 4: Basal Adjustment")
    for ctrl, r in results["basal_adjustment"].items():
        if r.get("pos_median_ratio") is not None:
            print(f"  {ctrl.upper()}: pos ISF basal ratio={r['pos_median_ratio']:.2f}, "
                  f"neg ISF basal ratio={r['neg_median_ratio']:.2f}")

    print("\n## Panel 6: Starting Glucose")
    for ctrl, r in results["glucose_level"].items():
        print(f"  {ctrl.upper()}: pos ISF median BG={r['pos_median_bg']:.0f}, "
              f"neg ISF median BG={r['neg_median_bg']:.0f}")

    # Hypothesis evaluation
    print("\n## Hypothesis Evaluation")
    roc_neg = edf[edf.negative_isf].pre_roc.dropna()
    roc_pos = edf[~edf.negative_isf].pre_roc.dropna()
    if len(roc_neg) > 10 and len(roc_pos) > 10:
        print(f"  H2 (glucose rising): neg ISF median ROC = {roc_neg.median():.3f} "
              f"vs pos = {roc_pos.median():.3f} mg/dL/min")
        if roc_neg.median() > roc_pos.median():
            print("  → SUPPORTED: Negative ISF events have higher pre-bolus ROC")
        else:
            print("  → NOT SUPPORTED")

    iob_neg = edf[edf.negative_isf].iob_change.dropna()
    iob_pos = edf[~edf.negative_isf].iob_change.dropna()
    if len(iob_neg) > 10 and len(iob_pos) > 10:
        print(f"  H1 (AID backs off): neg ISF IOB change = {iob_neg.median():.2f} "
              f"vs pos = {iob_pos.median():.2f}")
        if iob_neg.median() < iob_pos.median():
            print("  → SUPPORTED: AID delivers less net insulin during negative ISF events")
        else:
            print("  → NOT SUPPORTED")

    bg_neg = edf[edf.negative_isf].bg_at_bolus.dropna()
    bg_pos = edf[~edf.negative_isf].bg_at_bolus.dropna()
    if len(bg_neg) > 10 and len(bg_pos) > 10:
        print(f"  H3 (low start): neg ISF start BG = {bg_neg.median():.0f} "
              f"vs pos = {bg_pos.median():.0f} mg/dL")
        if bg_neg.median() < bg_pos.median():
            print("  → SUPPORTED: Negative ISF events start at lower glucose")
        else:
            print("  → NOT SUPPORTED")

    with open(EXP_DIR / "exp-2677_aid_compensation_artifact.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {EXP_DIR / 'exp-2677_aid_compensation_artifact.json'}")

    return results


if __name__ == "__main__":
    main()
