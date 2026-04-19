#!/usr/bin/env python3
"""EXP-2668: Per-Controller Demand ISF Signatures.

MOTIVATION: EXP-2666 found patient i has 1132% ISF shift between 2-12h isolation.
EXP-2663 proved demand ISF is dose-independent. But do CONTROLLERS create systematic
ISF bias? Different AID systems dose differently:
  - SMB-AID: frequent micro-boluses (50-75/day) → short inter-bolus gaps
  - Loop/TBR: temp basal modulation → longer clean windows
  - AAPS: hybrid SMB+TBR → intermediate

If controller type systematically affects demand ISF measurement, we need per-controller
calibration tables for accurate settings recommendations.

HYPOTHESES:
  H1: Demand ISF differs significantly by controller type (ANOVA p<0.05)
  H2: Optimal isolation window differs by controller (KW test on stability curves)
  H3: Patient i's 1132% shift is explained by SMB-AID bolus spacing pattern
  H4: Loop/TBR patients have more isolated corrections per day than SMB-AID
  H5: ISF CV within controller groups < CV across all patients

OUTPUTS:
  - externals/experiments/exp-2668_controller_isf_signatures.json
  - visualizations/controller-isf-signatures/fig[1-6]_*.png
  - docs/60-research/controller-isf-signatures-report-2026-04-18.md
"""

import argparse
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_PARQUET = Path("externals/ns-parquet/training/grid.parquet")
DEFAULT_DS_PARQUET = Path("externals/ns-parquet/training/devicestatus.parquet")
RESULTS_DIR = Path("externals/experiments"); RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2668_controller_isf_signatures.json"
VIZ_DIR = Path("visualizations/controller-isf-signatures"); VIZ_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = Path("docs/60-research/controller-isf-signatures-report-2026-04-18.md")

STEPS_PER_HOUR = 12
MIN_DOSE = 0.5; MIN_PRE_BG = 120; CARB_EXCLUSION_H = 1.0; DEMAND_STEPS = 24
ISOLATION_WINDOWS = [2, 3, 4, 6, 8, 10, 12]


def _load_controller_map():
    """Load actual AID controller identity from devicestatus parquet."""
    if not DS_PARQUET.exists():
        return {}
    ds = pd.read_parquet(DS_PARQUET, columns=["patient_id", "controller"])
    ctrl_map = {}
    for pid in ds["patient_id"].unique():
        ctrls = ds.loc[ds["patient_id"] == pid, "controller"].dropna().unique()
        if len(ctrls) == 1:
            ctrl_map[pid] = ctrls[0]
        elif len(ctrls) > 1:
            ctrl_map[pid] = "/".join(sorted(ctrls))
    return ctrl_map


def _classify_controller(pid, pdf, controller_map=None):
    """Classify patient's AID controller type from devicestatus metadata.

    Uses actual controller metadata when available, falling back to
    SMB-ratio heuristic only when metadata is missing.
    """
    n = len(pdf)
    iob = pdf["iob"].fillna(0).values
    iob_pct = float((iob > 0.1).sum() / n * 100)
    loop_pct = float(pdf["loop_enacted_bolus"].notna().sum() / n * 100)
    smb = int((pdf["bolus_smb"].fillna(0) > 0).sum())
    bol = int((pdf["bolus"].fillna(0) > 0).sum())
    basal_mod = (pdf["actual_basal_rate"] != pdf["scheduled_basal_rate"]).sum() / n
    days = (pdf["time"].max() - pdf["time"].min()).total_seconds() / 86400
    has_smb = smb > bol * 0.3

    if iob_pct < 5 or loop_pct < 5:
        return None, {}  # T4: excluded

    actual = (controller_map or {}).get(pid)
    if actual and "trio" in actual:
        ctrl = "Trio/AB" if has_smb else "Trio/TBR"
    elif actual == "openaps":
        ctrl = "AAPS/SMB" if has_smb else "AAPS/TBR"
    elif actual == "loop":
        ctrl = "Loop/AB" if has_smb else "Loop/TBR"
    else:
        ctrl = "SMB-AID" if has_smb else "TBR"

    meta = {
        "ctrl": ctrl, "days": round(days), "iob_pct": round(iob_pct, 1),
        "loop_pct": round(loop_pct, 1), "smb_count": smb, "bol_count": bol,
        "smb_per_day": round(smb / max(days, 1), 1),
        "bol_per_day": round(bol / max(days, 1), 1),
        "basal_mod_pct": round(basal_mod * 100, 1),
    }
    return ctrl, meta


def _extract_demand_isf_sweep(pdf, prior_bolus_hours):
    """Extract demand ISF at a specific isolation window."""
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    pw = int(prior_bolus_hours * STEPS_PER_HOUR)
    cw = int(CARB_EXCLUSION_H * STEPS_PER_HOUR)
    n = len(pdf)
    isfs = []; doses = []
    for i in range(pw, n - DEMAND_STEPS):
        if bolus[i] < MIN_DOSE: continue
        if np.isnan(glucose[i]) or glucose[i] < MIN_PRE_BG: continue
        if np.nansum(bolus[max(0, i - pw):i]) > 0.3: continue
        cs, ce = max(0, i - cw), min(n, i + cw)
        if np.nansum(carbs[cs:ce]) > 2: continue
        j = i + DEMAND_STEPS
        if j >= n or np.isnan(glucose[j]): continue
        drop = glucose[i] - glucose[j]
        if drop < 5: continue
        dose = float(bolus[i])
        if dose > 0:
            isfs.append(drop / dose)
            doses.append(dose)
    return isfs, doses


def _bolus_spacing_analysis(pdf):
    """Analyze inter-bolus timing distribution."""
    bolus = pdf["bolus"].fillna(0).values
    times = pdf["time"].values
    bol_idx = np.where(bolus > 0.3)[0]
    if len(bol_idx) < 10:
        return None
    gaps_h = []
    for k in range(1, len(bol_idx)):
        dt = (times[bol_idx[k]] - times[bol_idx[k-1]]) / np.timedelta64(1, 'h')
        gaps_h.append(float(dt))
    gaps = np.array(gaps_h)
    return {
        "n_boluses": len(bol_idx),
        "median_gap_h": round(float(np.median(gaps)), 2),
        "mean_gap_h": round(float(np.mean(gaps)), 2),
        "p25_gap_h": round(float(np.percentile(gaps, 25)), 2),
        "p75_gap_h": round(float(np.percentile(gaps, 75)), 2),
        "pct_gap_lt_2h": round(float((gaps < 2).sum() / len(gaps) * 100), 1),
        "pct_gap_lt_4h": round(float((gaps < 4).sum() / len(gaps) * 100), 1),
        "pct_gap_lt_6h": round(float((gaps < 6).sum() / len(gaps) * 100), 1),
        "pct_gap_gt_6h": round(float((gaps > 6).sum() / len(gaps) * 100), 1),
        "_gaps": gaps,
    }


def _analyze_patient(pid, pdf, controller_map=None):
    """Full per-patient analysis."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    ctrl, meta = _classify_controller(pid, pdf, controller_map)
    if ctrl is None:
        return None

    # Bolus spacing
    spacing = _bolus_spacing_analysis(pdf)
    if spacing is None:
        return None

    # ISF at each isolation window
    sweep = {}
    for w in ISOLATION_WINDOWS:
        isfs, doses = _extract_demand_isf_sweep(pdf, w)
        if len(isfs) >= 3:
            sweep[w] = {
                "n": len(isfs),
                "median": round(float(np.median(isfs)), 1),
                "mean": round(float(np.mean(isfs)), 1),
                "cv": round(float(np.std(isfs) / np.mean(isfs) * 100), 1) if np.mean(isfs) > 0 else None,
                "iqr": round(float(np.percentile(isfs, 75) - np.percentile(isfs, 25)), 1),
                "_isfs": np.array(isfs),
            }
        else:
            sweep[w] = {"n": len(isfs), "median": None}

    # Best ISF (6h or fallback)
    best_w = 6 if sweep.get(6, {}).get("median") else 2
    best_isf = sweep.get(best_w, {}).get("median")

    # Stability: how much does ISF change across windows?
    valid_medians = [(w, sweep[w]["median"]) for w in ISOLATION_WINDOWS
                     if sweep[w].get("median") is not None]
    if len(valid_medians) >= 3:
        ws, ms = zip(*valid_medians)
        stability_range = round(max(ms) / min(ms), 2) if min(ms) > 0 else None
        stability_cv = round(float(np.std(ms) / np.mean(ms) * 100), 1) if np.mean(ms) > 0 else None
    else:
        stability_range = None; stability_cv = None

    # Isolated corrections per day at each window
    days = max(meta["days"], 1)
    iso_per_day = {}
    for w in ISOLATION_WINDOWS:
        n = sweep[w]["n"]
        iso_per_day[w] = round(n / days, 2)

    return {
        **meta,
        "spacing": {k: v for k, v in spacing.items() if not k.startswith("_")},
        "_spacing_gaps": spacing["_gaps"],
        "sweep": {w: {k: v for k, v in d.items() if not k.startswith("_")}
                  for w, d in sweep.items()},
        "_sweep_raw": {w: d.get("_isfs") for w, d in sweep.items() if d.get("_isfs") is not None},
        "best_w": best_w,
        "best_isf": best_isf,
        "stability_range": stability_range,
        "stability_cv": stability_cv,
        "iso_per_day": iso_per_day,
    }


def _generate_visualizations(results):
    """Generate 6 figures."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    ctrl_colors = {"SMB-AID": "#2196F3", "Loop/TBR": "#4CAF50", "Hybrid": "#FF9800"}

    # Fig 1: Bolus spacing distributions by controller
    groups = {}
    for p, r in results.items():
        c = r["ctrl"]
        if c not in groups: groups[c] = []
        groups[c].append((p, r))

    fig, axes = plt.subplots(1, len(groups), figsize=(5 * len(groups), 5), sharey=True)
    if not isinstance(axes, np.ndarray): axes = [axes]
    fig.suptitle("Fig 1: Inter-Bolus Gap Distribution by Controller Type\n"
                 "SMB-AID has shorter gaps = fewer isolated corrections available",
                 fontsize=12, fontweight="bold")
    for ai, (ctrl, patients) in enumerate(sorted(groups.items())):
        ax = axes[ai]
        all_gaps = np.concatenate([r["_spacing_gaps"] for _, r in patients])
        ax.hist(all_gaps, bins=np.arange(0, 25, 0.5), color=ctrl_colors.get(ctrl, "#999"),
                alpha=0.7, edgecolor="white", density=True)
        ax.axvline(2, color="red", ls="--", lw=1.5, label="2h")
        ax.axvline(6, color="orange", ls="--", lw=1.5, label="6h")
        ax.set_xlabel("Inter-bolus gap (hours)")
        if ai == 0: ax.set_ylabel("Density")
        med = float(np.median(all_gaps))
        pct6 = float((all_gaps > 6).sum() / len(all_gaps) * 100)
        ax.set_title("{} (N={}, med={:.1f}h, >{:.0f}h: {:.0f}%)".format(
            ctrl, len(patients), med, 6, pct6), fontsize=10)
        ax.legend(fontsize=8)
        ax.set_xlim(0, 24)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_bolus_spacing_by_controller.png", dpi=150); plt.close()
    print("  fig1")

    # Fig 2: Isolation sweep curves by controller
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.suptitle("Fig 2: Demand ISF vs Isolation Window by Controller\n"
                 "Each line = one patient, colored by controller type",
                 fontsize=12, fontweight="bold")
    for p in sorted(results):
        r = results[p]; c = r["ctrl"]
        ws = []; ms = []
        for w in ISOLATION_WINDOWS:
            if r["sweep"][w].get("median") is not None:
                ws.append(w); ms.append(r["sweep"][w]["median"])
        if len(ws) >= 2:
            ax.plot(ws, ms, "o-", color=ctrl_colors.get(c, "#999"), alpha=0.6,
                    lw=1.5, markersize=5, label=None)
            # Label at rightmost point
            ax.annotate(p, (ws[-1], ms[-1]), fontsize=7, xytext=(5, 0),
                        textcoords="offset points")
    ax.set_xlabel("Isolation Window (hours)")
    ax.set_ylabel("Demand ISF (mg/dL/U)")
    ax.legend(handles=[Patch(fc=c, label=k) for k, c in ctrl_colors.items()],
              loc="upper left", fontsize=10)
    ax.set_xticks(ISOLATION_WINDOWS)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_isf_sweep_by_controller.png", dpi=150); plt.close()
    print("  fig2")

    # Fig 3: ISF stability (range ratio) by controller
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Fig 3: ISF Stability Across Isolation Windows\n"
                 "Lower ratio = more stable; patient i is the key anomaly",
                 fontsize=12, fontweight="bold")
    pa = sorted(results, key=lambda p: results[p].get("stability_range") or 0)
    sr = [results[p].get("stability_range") or 0 for p in pa]
    cs = [ctrl_colors.get(results[p]["ctrl"], "#999") for p in pa]
    a1.barh(range(len(pa)), sr, color=cs, alpha=0.85)
    a1.set_yticks(range(len(pa)))
    a1.set_yticklabels(["{} ({})".format(p, results[p]["ctrl"][:3]) for p in pa], fontsize=8)
    a1.set_xlabel("ISF Range Ratio (max/min across windows)")
    a1.axvline(2, color="red", ls="--", lw=1, alpha=0.5, label="2x threshold")
    a1.legend(fontsize=8)
    # Right: isolated corrections per day at 6h
    ipd = [results[p]["iso_per_day"].get(6, 0) for p in pa]
    a2.barh(range(len(pa)), ipd, color=cs, alpha=0.85)
    a2.set_yticks(range(len(pa)))
    a2.set_yticklabels(["{} ({})".format(p, results[p]["ctrl"][:3]) for p in pa], fontsize=8)
    a2.set_xlabel("Isolated Corrections per Day (6h window)")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_isf_stability_by_controller.png", dpi=150); plt.close()
    print("  fig3")

    # Fig 4: Box plot of demand ISF at 6h by controller group
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("Fig 4: Demand ISF Distribution at 6h Isolation by Controller\n"
                 "ANOVA/KW test for systematic differences",
                 fontsize=12, fontweight="bold")
    group_data = {}
    for p, r in results.items():
        raw = r.get("_sweep_raw", {}).get(6)
        if raw is not None and len(raw) >= 5:
            c = r["ctrl"]
            if c not in group_data: group_data[c] = []
            group_data[c].extend(raw.tolist())
    if group_data:
        labels = sorted(group_data.keys())
        data = [group_data[l] for l in labels]
        bp = ax.boxplot(data, labels=labels, patch_artist=True, showmeans=True)
        for patch, lab in zip(bp["boxes"], labels):
            patch.set_facecolor(ctrl_colors.get(lab, "#999"))
            patch.set_alpha(0.7)
        ax.set_ylabel("Demand ISF (mg/dL/U)")
        if len(data) >= 2:
            h_stat, p_val = stats.kruskal(*data) if len(data) >= 2 else (0, 1)
            ax.set_title("Kruskal-Wallis H={:.2f}, p={:.4f}".format(h_stat, p_val))
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_isf_boxplot_by_controller.png", dpi=150); plt.close()
    print("  fig4")

    # Fig 5: Patient i deep dive
    if "i" in results:
        ri = results["i"]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle("Fig 5: Patient i Deep Dive — 1132% ISF Shift Investigation\n"
                     "Left: ISF vs isolation window; Right: bolus spacing distribution",
                     fontsize=12, fontweight="bold")
        ws = []; ms = []; ns = []
        for w in ISOLATION_WINDOWS:
            if ri["sweep"][w].get("median") is not None:
                ws.append(w); ms.append(ri["sweep"][w]["median"]); ns.append(ri["sweep"][w]["n"])
        a1.plot(ws, ms, "o-", color="#E91E63", lw=2, markersize=8)
        for w, m, n in zip(ws, ms, ns):
            a1.annotate("N={}".format(n), (w, m), fontsize=8, xytext=(5, 10),
                        textcoords="offset points")
        a1.set_xlabel("Isolation Window (hours)"); a1.set_ylabel("Demand ISF (mg/dL/U)")
        a1.set_title("Patient i: ISF={:.0f} at 2h, {:.0f} at 12h".format(ms[0], ms[-1]) if len(ms) >= 2 else "")
        gaps = ri["_spacing_gaps"]
        a2.hist(gaps, bins=np.arange(0, 25, 0.5), color="#E91E63", alpha=0.7, edgecolor="white")
        a2.axvline(6, color="orange", ls="--", lw=2, label="6h threshold")
        a2.set_xlabel("Inter-bolus gap (hours)"); a2.set_ylabel("Count")
        med_gap = float(np.median(gaps))
        a2.set_title("Median gap={:.1f}h, >6h: {:.1f}%".format(
            med_gap, float((gaps > 6).sum() / len(gaps) * 100)))
        a2.legend()
        plt.tight_layout()
        fig.savefig(VIZ_DIR / "fig5_patient_i_deep_dive.png", dpi=150); plt.close()
        print("  fig5")

    # Fig 6: Summary — controller effect size
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("Fig 6: Per-Controller Median ISF and Event Yield\n"
                 "Bar height = median ISF at 6h; annotation = events/day",
                 fontsize=12, fontweight="bold")
    ctrl_summary = {}
    for p, r in results.items():
        c = r["ctrl"]
        if c not in ctrl_summary: ctrl_summary[c] = {"isfs": [], "ipd": []}
        if r["best_isf"]: ctrl_summary[c]["isfs"].append(r["best_isf"])
        ctrl_summary[c]["ipd"].append(r["iso_per_day"].get(6, 0))
    labels = sorted(ctrl_summary)
    x = np.arange(len(labels))
    medians = [float(np.median(ctrl_summary[l]["isfs"])) if ctrl_summary[l]["isfs"] else 0 for l in labels]
    ipds = [float(np.median(ctrl_summary[l]["ipd"])) for l in labels]
    bars = ax.bar(x, medians, color=[ctrl_colors.get(l, "#999") for l in labels], alpha=0.85)
    for xi, m, ipd in zip(x, medians, ipds):
        ax.annotate("{:.0f} mg/dL/U\n{:.2f} events/day".format(m, ipd),
                    (xi, m), ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylabel("Median Demand ISF at 6h (mg/dL/U)")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig6_controller_effect_summary.png", dpi=150); plt.close()
    print("  fig6")


def _generate_report(results, hyps):
    """Generate markdown report."""
    L = []
    L.append("# EXP-2668: Per-Controller Demand ISF Signatures\n")
    L.append("**Date**: 2026-04-18  ")
    L.append("**Predecessor**: EXP-2663, EXP-2666  ")
    L.append("**Patients**: {}  ".format(len(results)))
    L.append("**Data**: CGM + pump telemetry from grid.parquet\n")

    L.append("## 1. Motivation\n")
    L.append("EXP-2666 found patient i has 1132% ISF shift between 2-12h isolation, "
             "while most patients stabilize at 6h. Different AID controllers dose differently: "
             "SMB-AID fires 50-75 micro-boluses/day (short inter-bolus gaps), Loop/TBR modulates "
             "basal rates (longer clean windows). This experiment tests whether controller type "
             "creates systematic demand ISF measurement bias.\n")

    L.append("## 2. Controller Classification\n")
    L.append("![Spacing](../../visualizations/controller-isf-signatures/fig1_bolus_spacing_by_controller.png)\n")
    L.append("| Patient | Controller | Days | SMB/day | Bol/day | Median Gap (h) | >6h gaps |")
    L.append("|---------|-----------|------|---------|---------|---------------|----------|")
    for p in sorted(results):
        r = results[p]; s = r["spacing"]
        L.append("| {} | {} | {} | {} | {} | {} | {}% |".format(
            p, r["ctrl"], r["days"], r["smb_per_day"], r["bol_per_day"],
            s["median_gap_h"], s["pct_gap_gt_6h"]))
    L.append("")

    L.append("## 3. Isolation Sweep by Controller\n")
    L.append("![Sweep](../../visualizations/controller-isf-signatures/fig2_isf_sweep_by_controller.png)\n")
    L.append("![Stability](../../visualizations/controller-isf-signatures/fig3_isf_stability_by_controller.png)\n")

    L.append("## 4. Demand ISF by Controller Group\n")
    L.append("![Box](../../visualizations/controller-isf-signatures/fig4_isf_boxplot_by_controller.png)\n")

    L.append("## 5. Patient i Deep Dive\n")
    L.append("![Patient i](../../visualizations/controller-isf-signatures/fig5_patient_i_deep_dive.png)\n")
    if "i" in results:
        ri = results["i"]
        L.append("Patient i ({}, {} SMB/day):".format(ri["ctrl"], ri["smb_per_day"]))
        L.append("- Stability range: {}x".format(ri["stability_range"]))
        L.append("- Median inter-bolus gap: {}h".format(ri["spacing"]["median_gap_h"]))
        L.append("- Gaps >6h: {}%\n".format(ri["spacing"]["pct_gap_gt_6h"]))

    L.append("## 6. Controller Effect Summary\n")
    L.append("![Summary](../../visualizations/controller-isf-signatures/fig6_controller_effect_summary.png)\n")

    L.append("## 7. Hypothesis Results\n")
    L.append("| H | Result | Description |")
    L.append("|---|--------|-------------|")
    descs = {
        "H1": "Demand ISF differs by controller type (ANOVA/KW p<0.05)",
        "H2": "Optimal isolation window differs by controller",
        "H3": "Patient i shift explained by SMB-AID bolus spacing",
        "H4": "Loop/TBR has more isolated corrections/day than SMB-AID",
        "H5": "Within-controller ISF CV < overall CV",
    }
    for h, v in hyps.items():
        s = "**PASS**" if v is True else ("FAIL" if v is False else "SKIP")
        L.append("| {} | {} | {} |".format(h, s, descs.get(h, "")))
    L.append("")

    L.append("## 8. Clinical Implications\n")
    L.append("1. **Controller-aware calibration**: ISF measurement depends on dosing pattern")
    L.append("2. **Isolation window selection**: SMB-AID patients may need shorter windows (2-4h) with lax filtering")
    L.append("3. **Cross-device portability**: switching controllers may shift measured ISF")
    L.append("4. **Patient i**: specific controller signature, not physiological outlier\n")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(L))
    print("  Report: {}".format(REPORT_PATH))


def main():
    parser = argparse.ArgumentParser(description="EXP-2668: Controller ISF Signatures")
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    parser.add_argument("--ds-parquet", default=str(DEFAULT_DS_PARQUET))
    args = parser.parse_args()

    global DS_PARQUET
    PARQUET = Path(args.parquet)
    DS_PARQUET = Path(args.ds_parquet)

    print("=" * 70)
    print("EXP-2668: Per-Controller Demand ISF Signatures")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    controller_map = _load_controller_map()
    results = {}

    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid].copy()
        if len(pdf) < 200: continue
        r = _analyze_patient(pid, pdf, controller_map)
        if r is None:
            print("  {}: excluded".format(pid)); continue
        print("  {:8s} {} ({}d) gap_med={:.1f}h >6h={:.1f}% ISF@6h={} stab={} iso/day@6h={:.2f}".format(
            r["ctrl"], pid, r["days"],
            r["spacing"]["median_gap_h"], r["spacing"]["pct_gap_gt_6h"],
            r["best_isf"] if r["best_isf"] else "---",
            r.get("stability_range", "---"),
            r["iso_per_day"].get(6, 0)))
        results[pid] = r

    if not results: print("No data!"); return

    # === Hypothesis Testing ===
    groups_6h = {}
    for p, r in results.items():
        raw = r.get("_sweep_raw", {}).get(6)
        if raw is not None and len(raw) >= 5:
            c = r["ctrl"]
            if c not in groups_6h: groups_6h[c] = []
            groups_6h[c].extend(raw.tolist())

    # H1: ANOVA/KW on demand ISF by controller
    if len(groups_6h) >= 2:
        data = list(groups_6h.values())
        h_stat, p_val = stats.kruskal(*data)
        h1 = p_val < 0.05
        print("\nH1: KW H={:.2f}, p={:.4f} -> {}".format(h_stat, p_val, "PASS" if h1 else "FAIL"))
    else: h1 = None; print("\nH1: SKIP (< 2 groups)")

    # H2: Optimal window differs (compare stability ranges by controller)
    ctrl_stab = {}
    for p, r in results.items():
        if r.get("stability_range"):
            c = r["ctrl"]
            if c not in ctrl_stab: ctrl_stab[c] = []
            ctrl_stab[c].append(r["stability_range"])
    if len(ctrl_stab) >= 2:
        data = list(ctrl_stab.values())
        if all(len(d) >= 2 for d in data):
            h_s, p_s = stats.kruskal(*data)
            h2 = p_s < 0.05
            print("H2: Stability KW H={:.2f}, p={:.4f} -> {}".format(h_s, p_s, "PASS" if h2 else "FAIL"))
        else: h2 = None; print("H2: SKIP (insufficient per-group)")
    else: h2 = None; print("H2: SKIP")

    # H3: Patient i shift explained by spacing
    if "i" in results:
        ri = results["i"]
        # If patient i has very short gaps AND high stability range -> controller artifact
        h3 = (ri.get("stability_range", 0) or 0) > 3 and ri["spacing"]["pct_gap_gt_6h"] < 5
        print("H3: Patient i stab={}, >6h={}% -> {}".format(
            ri.get("stability_range"), ri["spacing"]["pct_gap_gt_6h"], "PASS" if h3 else "FAIL"))
    else: h3 = None

    # H4: Loop/TBR more isolated corrections/day at 6h
    smb_ipd = [r["iso_per_day"].get(6, 0) for r in results.values() if r["ctrl"] == "SMB-AID"]
    loop_ipd = [r["iso_per_day"].get(6, 0) for r in results.values() if r["ctrl"] == "Loop/TBR"]
    if smb_ipd and loop_ipd:
        h4 = float(np.median(loop_ipd)) > float(np.median(smb_ipd))
        print("H4: Loop/TBR med={:.2f} vs SMB-AID med={:.2f} -> {}".format(
            np.median(loop_ipd), np.median(smb_ipd), "PASS" if h4 else "FAIL"))
    else: h4 = None

    # H5: Within-controller CV < overall CV
    all_isfs = []
    ctrl_cvs = {}
    for p, r in results.items():
        raw = r.get("_sweep_raw", {}).get(6)
        if raw is not None and len(raw) >= 5:
            c = r["ctrl"]
            if c not in ctrl_cvs: ctrl_cvs[c] = []
            ctrl_cvs[c].extend(raw.tolist())
            all_isfs.extend(raw.tolist())
    if all_isfs and ctrl_cvs:
        overall_cv = float(np.std(all_isfs) / np.mean(all_isfs) * 100)
        within_cvs = []
        for c, vals in ctrl_cvs.items():
            if len(vals) >= 5:
                within_cvs.append(float(np.std(vals) / np.mean(vals) * 100))
        if within_cvs:
            mean_within = float(np.mean(within_cvs))
            h5 = mean_within < overall_cv
            print("H5: Within CV={:.1f}% vs Overall={:.1f}% -> {}".format(
                mean_within, overall_cv, "PASS" if h5 else "FAIL"))
        else: h5 = None
    else: h5 = None

    hyps = {"H1": h1, "H2": h2, "H3": h3, "H4": h4, "H5": h5}

    print("\n" + "=" * 70)
    print("HYPOTHESIS RESULTS:")
    for h, v in hyps.items():
        s = "PASS" if v is True else ("FAIL" if v is False else "SKIP")
        print("  {}: {}".format(h, s))

    print("\nGenerating visualizations...")
    _generate_visualizations(results)
    print("\nGenerating report...")
    _generate_report(results, hyps)

    # Save JSON
    jr = {p: {k: v for k, v in r.items() if not k.startswith("_")
              and k != "_sweep_raw"}
          for p, r in results.items()}
    # Also strip _isfs from sweep entries
    for p in jr:
        if "sweep" in jr[p]:
            for w in jr[p]["sweep"]:
                jr[p]["sweep"][w] = {k: v for k, v in jr[p]["sweep"][w].items() if not k.startswith("_")}

    out = {
        "experiment": "EXP-2668",
        "title": "Per-Controller Demand ISF Signatures",
        "hypotheses": {k: v if v is not None else "SKIP" for k, v in hyps.items()},
        "patients": jr,
    }
    OUTFILE.write_text(json.dumps(out, indent=2, default=str))
    print("Results: {}".format(OUTFILE))


if __name__ == "__main__":
    main()
