#!/usr/bin/env python3
"""EXP-2679: Circadian ISF Deep Dive (BG≥180 Corrections Only)

EXP-2678 revealed a genuine circadian ISF signal (p=0.0009) at BG≥180 that
was masked by meal noise in EXP-2673 (which reported p=0.18 with no BG floor).

This experiment characterizes the circadian pattern:
  1. What time-of-day bins show the strongest ISF differences?
  2. Is the pattern consistent across controllers?
  3. Is it consistent across patients?
  4. What is the magnitude of circadian ISF variation?
  5. Does it align with known dawn phenomenon timing?

Uses BG≥180 floor and 2h prior-bolus isolation.
"""

import json
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
DS = ROOT / "externals/ns-parquet/training/devicestatus.parquet"
MANIFEST = ROOT / "externals/experiments/autoprepare-qualified.json"
VIS_DIR = ROOT / "visualizations/circadian-isf-deep-dive"
EXP_DIR = ROOT / "externals/experiments"

VIS_DIR.mkdir(parents=True, exist_ok=True)

BG_FLOOR = 180
PRIOR_ISOLATION_H = 2.0
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


def extract_events(grid, ctrl_map):
    """Extract correction events with BG≥180 floor."""
    events = []
    for pid in grid.patient_id.unique():
        pgrid = grid[grid.patient_id == pid].sort_values("time")
        ctrl = ctrl_map.get(pid, "unknown")

        corrections = pgrid[(pgrid.bolus > MIN_DOSE) &
                            (pgrid.cob < MAX_COB) &
                            (pgrid.glucose >= BG_FLOOR)]

        for _, row in corrections.iterrows():
            bt = row.time
            pre = pgrid[(pgrid.time >= bt - pd.Timedelta(hours=PRIOR_ISOLATION_H)) &
                        (pgrid.time < bt)]
            if pre.bolus.sum() > 0.1:
                continue

            post = pgrid[(pgrid.time >= bt) &
                         (pgrid.time <= bt + pd.Timedelta(hours=2))]
            if len(post) < 6:
                continue

            bg0 = post.glucose.iloc[0]
            bg_2h = post.glucose.iloc[-1]
            if pd.isna(bg0) or pd.isna(bg_2h):
                continue

            drop = bg0 - bg_2h
            isf = drop / row.bolus

            events.append({
                "patient_id": pid,
                "controller": ctrl,
                "time": bt,
                "dose": row.bolus,
                "bg_at_bolus": bg0,
                "bg_drop": drop,
                "isf": isf,
                "hour": bt.hour if hasattr(bt, "hour") else pd.Timestamp(bt).hour,
                "scheduled_isf": row.scheduled_isf if pd.notna(row.get("scheduled_isf")) else np.nan,
            })

    return pd.DataFrame(events)


def panel1_hourly_isf(edf):
    """Panel 1: Hourly ISF profile with confidence intervals."""
    fig, ax = plt.subplots(figsize=(12, 6))

    hours = np.arange(24)
    hourly = edf.groupby("hour").isf.agg(["median", "mean", "std", "count"])
    hourly = hourly.reindex(hours)

    # Bootstrap CI for median
    ci_lo, ci_hi = [], []
    for h in hours:
        vals = edf[edf.hour == h].isf.dropna().values
        if len(vals) >= 5:
            boots = [np.median(np.random.choice(vals, len(vals), replace=True))
                     for _ in range(1000)]
            ci_lo.append(np.percentile(boots, 2.5))
            ci_hi.append(np.percentile(boots, 97.5))
        else:
            ci_lo.append(np.nan)
            ci_hi.append(np.nan)

    ax.fill_between(hours, ci_lo, ci_hi, alpha=0.2, color="blue", label="95% CI (bootstrap)")
    ax.plot(hours, hourly["median"], "bo-", lw=2, markersize=6, label="Median ISF")
    ax.plot(hours, hourly["mean"], "r--", lw=1, alpha=0.7, label="Mean ISF")

    # Mark event counts
    for h in hours:
        n = hourly.loc[h, "count"] if pd.notna(hourly.loc[h, "count"]) else 0
        ax.annotate(f"n={int(n)}", (h, ci_hi[h] if pd.notna(ci_hi[h]) else 0),
                    textcoords="offset points", xytext=(0, 8), fontsize=6,
                    ha="center", alpha=0.7)

    ax.axhline(edf.isf.median(), color="gray", ls="--", alpha=0.5, label="Overall median")
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Demand ISF (mg/dL per U)")
    ax.set_title(f"Panel 1: Hourly ISF Profile (BG≥{BG_FLOOR}, n={len(edf)})")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(hours)

    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig1_hourly_isf.png", dpi=150)
    plt.close(fig)
    print("  Panel 1: Hourly ISF saved")

    return {
        "overall_median": float(edf.isf.median()),
        "hourly_medians": {int(h): float(hourly.loc[h, "median"])
                           for h in hours if pd.notna(hourly.loc[h, "median"])},
    }


def panel2_by_controller(edf):
    """Panel 2: Circadian pattern by controller."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    results = {}
    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        sub = edf[edf.controller == ctrl]

        if len(sub) < 30:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nn={len(sub)} (insufficient)",
                    transform=ax.transAxes, ha="center", va="center")
            results[ctrl] = {"n": len(sub), "signal": None}
            continue

        hours = np.arange(24)
        hourly = sub.groupby("hour").isf.agg(["median", "count"]).reindex(hours)

        color = {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl]
        valid_hours = hourly.dropna(subset=["median"])
        ax.bar(valid_hours.index, valid_hours["median"], color=color, alpha=0.6)
        ax.axhline(sub.isf.median(), color="black", ls="--", alpha=0.5)

        # Kruskal-Wallis for this controller
        sub["time_bin"] = pd.cut(sub.hour, bins=[0, 6, 12, 18, 24],
                                 labels=["night", "morning", "afternoon", "evening"],
                                 right=False)
        groups = [g.isf.dropna().values for _, g in sub.groupby("time_bin", observed=True)
                  if len(g) >= 5]
        if len(groups) >= 3:
            stat, p = stats.kruskal(*groups)
            sig = "p<0.05 ⚠️" if p < 0.05 else f"p={p:.3f}"
            results[ctrl] = {"n": len(sub), "p": float(p), "signal": p < 0.05}
        else:
            sig = "too few bins"
            results[ctrl] = {"n": len(sub), "signal": None}

        ax.set_title(f"{ctrl.upper()} (n={len(sub)}, {sig})")
        ax.set_xlabel("Hour of Day (UTC)")
        ax.set_ylabel("Median ISF (mg/dL/U)")
        ax.grid(True, alpha=0.3)

    fig.suptitle("Panel 2: Circadian ISF by Controller", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig2_by_controller.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 2: By controller saved")
    return results


def panel3_by_patient(edf):
    """Panel 3: Per-patient circadian variation magnitude."""
    fig, ax = plt.subplots(figsize=(14, 6))

    patient_stats = []
    for pid in edf.patient_id.unique():
        sub = edf[edf.patient_id == pid]
        if len(sub) < 20:
            continue

        sub["time_bin"] = pd.cut(sub.hour, bins=[0, 6, 12, 18, 24],
                                 labels=["night", "morning", "afternoon", "evening"],
                                 right=False)
        bin_medians = sub.groupby("time_bin", observed=True).isf.median()
        if len(bin_medians) >= 3:
            variation = bin_medians.max() - bin_medians.min()
            relative = variation / abs(sub.isf.median()) if sub.isf.median() != 0 else 0
            patient_stats.append({
                "patient_id": pid,
                "controller": sub.controller.iloc[0],
                "n": len(sub),
                "overall_median_isf": sub.isf.median(),
                "circadian_range": variation,
                "relative_variation": relative,
                "peak_bin": bin_medians.idxmax(),
                "trough_bin": bin_medians.idxmin(),
            })

    if not patient_stats:
        ax.text(0.5, 0.5, "Insufficient per-patient data",
                transform=ax.transAxes, ha="center", va="center")
        fig.savefig(VIS_DIR / "fig3_by_patient.png", dpi=150)
        plt.close(fig)
        return {}

    pdf = pd.DataFrame(patient_stats).sort_values("relative_variation")

    colors = pdf.controller.map(
        {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}).values
    ax.barh(range(len(pdf)), pdf.relative_variation * 100, color=colors, alpha=0.7)
    ax.set_yticks(range(len(pdf)))
    ax.set_yticklabels([f"{r.patient_id[:10]} ({r.controller})"
                        for _, r in pdf.iterrows()], fontsize=7)
    ax.set_xlabel("Circadian ISF Variation (% of median)")
    ax.set_title(f"Panel 3: Per-Patient Circadian ISF Variation (n={len(pdf)} patients)")
    ax.axvline(50, color="red", ls="--", alpha=0.5, label=">50% variation")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig3_by_patient.png", dpi=150)
    plt.close(fig)
    print("  Panel 3: By patient saved")

    return {
        "patients_analyzed": len(pdf),
        "median_relative_variation": float(pdf.relative_variation.median() * 100),
        "patients_above_50pct": int((pdf.relative_variation > 0.5).sum()),
        "peak_trough": pdf[["patient_id", "peak_bin", "trough_bin"]].to_dict("records"),
    }


def panel4_dawn_phenomenon(edf):
    """Panel 4: Dawn phenomenon alignment — ISF comparison 4-8 AM vs rest."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Dawn = 4-8 AM UTC (approximate)
    edf["is_dawn"] = edf.hour.isin([4, 5, 6, 7])
    dawn = edf[edf.is_dawn]
    non_dawn = edf[~edf.is_dawn]

    # Violin plot
    ax = axes[0]
    data = [dawn.isf.dropna().values, non_dawn.isf.dropna().values]
    labels = [f"Dawn 4-8AM\n(n={len(dawn)})", f"Other hours\n(n={len(non_dawn)})"]

    vp = ax.violinplot(data, showmedians=True, showextrema=False)
    for i, body in enumerate(vp["bodies"]):
        body.set_facecolor(["orange", "steelblue"][i])
        body.set_alpha(0.4)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(labels)
    ax.set_ylabel("Demand ISF (mg/dL/U)")
    ax.set_title("Dawn vs Non-Dawn ISF")
    ax.grid(True, alpha=0.3)

    # Statistical test
    if len(dawn) >= 10 and len(non_dawn) >= 10:
        stat, p = stats.mannwhitneyu(dawn.isf.dropna(), non_dawn.isf.dropna(),
                                     alternative="two-sided")
        ax.text(0.5, 0.95, f"Mann-Whitney p={p:.4f}", transform=ax.transAxes,
                ha="center", va="top", fontsize=10,
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # 4-bin comparison
    ax = axes[1]
    edf["time_bin"] = pd.cut(edf.hour, bins=[0, 6, 12, 18, 24],
                             labels=["Night\n0-6", "Morning\n6-12",
                                     "Afternoon\n12-18", "Evening\n18-24"],
                             right=False)
    bin_data = []
    bin_labels = []
    bin_colors = ["#2c3e50", "#e67e22", "#27ae60", "#8e44ad"]
    for i, (name, group) in enumerate(edf.groupby("time_bin", observed=True)):
        vals = group.isf.dropna().values
        if len(vals) >= 5:
            bin_data.append(vals)
            bin_labels.append(f"{name}\n(n={len(vals)})")

    if bin_data:
        bp = ax.boxplot(bin_data, labels=bin_labels, patch_artist=True)
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(bin_colors[i % len(bin_colors)])
            patch.set_alpha(0.4)
    ax.set_ylabel("Demand ISF (mg/dL/U)")
    ax.set_title("ISF by Time-of-Day Bin")
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"Panel 4: Dawn Phenomenon Analysis (BG≥{BG_FLOOR})", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig4_dawn_phenomenon.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 4: Dawn phenomenon saved")

    dawn_med = float(dawn.isf.median()) if len(dawn) > 0 else None
    non_dawn_med = float(non_dawn.isf.median()) if len(non_dawn) > 0 else None
    return {
        "dawn_median_isf": dawn_med,
        "non_dawn_median_isf": non_dawn_med,
        "dawn_n": len(dawn),
        "non_dawn_n": len(non_dawn),
        "mann_whitney_p": float(p) if len(dawn) >= 10 and len(non_dawn) >= 10 else None,
    }


def panel5_magnitude(edf):
    """Panel 5: Quantify circadian ISF magnitude and clinical significance."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ISF heatmap by hour × controller
    ax = axes[0]
    pivot = edf.pivot_table(values="isf", index="controller", columns="hour",
                            aggfunc="median")
    # Normalize each controller to its mean
    normalized = pivot.div(pivot.mean(axis=1), axis=0)

    im = ax.imshow(normalized.values, aspect="auto", cmap="RdYlGn",
                   vmin=0.5, vmax=1.5)
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24), fontsize=6)
    ax.set_yticks(range(len(normalized)))
    ax.set_yticklabels([c.upper() for c in normalized.index])
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_title("Normalized ISF (1.0 = controller mean)")
    plt.colorbar(im, ax=ax, label="Relative ISF")

    # Distribution of ISF ratios (max/min per patient per day)
    ax = axes[1]
    ratios = []
    for pid in edf.patient_id.unique():
        sub = edf[edf.patient_id == pid]
        if len(sub) < 20:
            continue
        hourly = sub.groupby("hour").isf.median()
        if len(hourly) >= 6 and hourly.min() > 0:
            ratios.append(hourly.max() / hourly.min())

    if ratios:
        ax.hist(ratios, bins=15, color="steelblue", alpha=0.7, edgecolor="black")
        ax.axvline(np.median(ratios), color="red", ls="--", lw=2,
                   label=f"Median ratio = {np.median(ratios):.1f}×")
        ax.set_xlabel("Max hourly ISF / Min hourly ISF")
        ax.set_ylabel("Count (patients)")
        ax.set_title("Per-Patient ISF Max/Min Ratio")
        ax.legend()
    ax.grid(True, alpha=0.3)

    fig.suptitle(f"Panel 5: Circadian ISF Magnitude (BG≥{BG_FLOOR})", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig5_magnitude.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  Panel 5: Magnitude saved")

    return {
        "n_patients_with_ratio": len(ratios),
        "median_max_min_ratio": float(np.median(ratios)) if ratios else None,
        "mean_max_min_ratio": float(np.mean(ratios)) if ratios else None,
    }


def main():
    print("=" * 70)
    print("EXP-2679: Circadian ISF Deep Dive (BG≥180)")
    print("=" * 70)

    print("\nLoading data...")
    grid, ds, ctrl_map, qp = load_data()

    print("Extracting correction events (BG≥180)...")
    edf = extract_events(grid, ctrl_map)
    print(f"  {len(edf)} events from {edf.patient_id.nunique()} patients")
    print(f"  {100 * (edf.isf > 0).mean():.1f}% positive ISF")

    results = {
        "experiment": "EXP-2679",
        "title": "Circadian ISF Deep Dive (BG≥180)",
        "bg_floor": BG_FLOOR,
        "n_events": len(edf),
        "n_patients": int(edf.patient_id.nunique()),
    }

    print("\nRunning panels...")
    results["hourly"] = panel1_hourly_isf(edf)
    results["by_controller"] = panel2_by_controller(edf)
    results["by_patient"] = panel3_by_patient(edf)
    results["dawn"] = panel4_dawn_phenomenon(edf)
    results["magnitude"] = panel5_magnitude(edf)

    # Overall circadian test
    edf["time_bin"] = pd.cut(edf.hour, bins=[0, 6, 12, 18, 24],
                             labels=["night", "morning", "afternoon", "evening"],
                             right=False)
    groups = [g.isf.dropna().values for _, g in edf.groupby("time_bin", observed=True)
              if len(g) >= 5]
    if len(groups) >= 3:
        stat, p = stats.kruskal(*groups)
        results["kruskal_p"] = float(p)
    else:
        results["kruskal_p"] = None

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n  Overall Kruskal-Wallis: p={results['kruskal_p']:.6f}"
          if results['kruskal_p'] is not None else "  No overall test")

    print(f"\n## Hourly ISF Profile")
    hourly = results["hourly"]["hourly_medians"]
    if hourly:
        max_h = max(hourly, key=hourly.get)
        min_h = min(hourly, key=hourly.get)
        print(f"  Peak ISF: hour {max_h} = {hourly[max_h]:.1f} mg/dL/U")
        print(f"  Trough ISF: hour {min_h} = {hourly[min_h]:.1f} mg/dL/U")
        print(f"  Range: {hourly[max_h] - hourly[min_h]:.1f} mg/dL/U")

    print(f"\n## By Controller")
    for ctrl, r in results["by_controller"].items():
        sig = "SIGNAL" if r.get("signal") else "no signal"
        p = r.get("p", "N/A")
        print(f"  {ctrl.upper()}: n={r['n']} p={p} ({sig})")

    print(f"\n## Dawn Phenomenon")
    d = results["dawn"]
    if d.get("dawn_median_isf") is not None:
        print(f"  Dawn (4-8AM) median ISF: {d['dawn_median_isf']:.1f} mg/dL/U")
        print(f"  Non-dawn median ISF: {d['non_dawn_median_isf']:.1f} mg/dL/U")
        print(f"  Mann-Whitney p: {d['mann_whitney_p']:.4f}"
              if d['mann_whitney_p'] is not None else "")

    print(f"\n## Magnitude")
    m = results["magnitude"]
    if m.get("median_max_min_ratio"):
        print(f"  Median max/min hourly ISF ratio: {m['median_max_min_ratio']:.1f}×")
        print(f"  ({m['n_patients_with_ratio']} patients with sufficient data)")

    with open(EXP_DIR / "exp-2679_circadian_isf_deep_dive.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {EXP_DIR / 'exp-2679_circadian_isf_deep_dive.json'}")

    return results


if __name__ == "__main__":
    main()
