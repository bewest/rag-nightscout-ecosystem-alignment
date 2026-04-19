#!/usr/bin/env python3
"""EXP-2674: DynISF Formula × Demand ISF × Sensitivity Ratio Deep Dive.

EXP-2673B found promising but underpowered results (n=6, r=0.59). This
experiment expands the analysis using ALL 12 Trio DynISF patients, relaxing
isolation to get more events, and stratifying by DynISF formula type.

DynISF Formula Annotations (from public Nightscout sites):
  Sigmoid: ns-9b9a, ns-adde, ns-dde9, ns-554b, ns-6bef, ns-c422  (6 patients)
  Log:     ns-d444, ns-8b3c, ns-a9ce, ns-8ffa, ns-1cca           (5 patients)
  AutoISF: ns-8f35                                                 (1 patient)

KEY QUESTIONS:
  Q1: Does sensitivity_ratio distribution differ between sigmoid and log?
  Q2: Does the DynISF formula type affect demand ISF extraction?
  Q3: What is the effective_ISF/demand_ISF inflation ratio per formula type?
  Q4: Can sensitivity_ratio at time of correction predict ISF?
  Q5: Do patients with wider SR range have better ISF prediction?

METHODOLOGICAL NOTE:
  Using 1h prior-bolus isolation (not 6h) — Trio patients use SMBs every ~1h,
  and EXP-2663 validated that 2h isolation gives same demand ISF as 6h.
  With 1h we accept more noise but get far more events per patient.

OUTPUTS:
  - externals/experiments/exp-2674_dynisf_sr_deep_dive.json
  - visualizations/autoresearch-wave2/fig[1-6]_*.png
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

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
DS_PARQUET = Path("externals/ns-parquet/training/devicestatus.parquet")
RESULTS_DIR = Path("externals/experiments")
OUTFILE = RESULTS_DIR / "exp-2674_dynisf_sr_deep_dive.json"
VIZ_DIR = Path("visualizations/autoresearch-wave2")
VIZ_DIR.mkdir(parents=True, exist_ok=True)

STEPS_PER_HOUR = 12

# DynISF formula annotations (from public Nightscout sites)
FORMULA = {
    "ns-9b9a6a874e51": "sigmoid",
    "ns-adde5f4af7ca": "sigmoid",
    "ns-dde9e7c2e752": "sigmoid",
    "ns-554b16de7133": "sigmoid",
    "ns-6bef17b4c1ec": "sigmoid",
    "ns-c422538aa12a": "sigmoid",
    "ns-d444c120c23a": "log",
    "ns-8b3c1b50793c": "log",
    "ns-a9ce2317bead": "log",
    "ns-8ffa739b986b": "log",
    "ns-1ccae8a375b9": "log",
    "ns-8f3527d1ee40": "autoisf",
}

FORMULA_COLORS = {"sigmoid": "#E91E63", "log": "#3F51B5", "autoisf": "#FF9800"}
TRIO_PATIENTS = list(FORMULA.keys())


def load_data():
    """Load grid + controller map for Trio patients."""
    df = pd.read_parquet(PARQUET)
    df = df[df.patient_id.isin(TRIO_PATIENTS)].copy()
    return df


def extract_corrections(pdf, prior_bolus_h=1.0, min_dose=0.3, min_pre_bg=100,
                        carb_window_h=1.0, demand_window_h=2.0):
    """Extract correction events with relaxed isolation for SMB controllers.

    min_dose lowered to 0.3U (Trio gives smaller boluses than Loop).
    min_pre_bg lowered to 100 (DynISF patients may correct from lower BG).
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    sr = pdf["sensitivity_ratio"].values.astype(np.float64) if "sensitivity_ratio" in pdf.columns else np.full(len(pdf), np.nan)

    carb_window = int(carb_window_h * STEPS_PER_HOUR)
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    demand_steps = int(demand_window_h * STEPS_PER_HOUR)
    events = []

    bolus_locs = np.where(bolus >= min_dose)[0]

    for loc in bolus_locs:
        if loc + demand_steps >= len(pdf) or loc < max(prior_window, 1):
            continue

        pre_bg = glucose[loc - 1]
        if np.isnan(pre_bg) or pre_bg < min_pre_bg:
            continue

        # Carb exclusion
        c_start = max(0, loc - carb_window)
        c_end = min(len(pdf), loc + demand_steps + 1)
        if carbs[c_start:c_end].sum() > 0:
            continue

        # Prior manual bolus isolation
        prior_slice = bolus[max(0, loc - prior_window):loc]
        if prior_slice.sum() > 0:
            continue

        post_bg = glucose[loc + demand_steps]
        if np.isnan(post_bg):
            continue

        dose = bolus[loc]
        drop = pre_bg - post_bg
        isf = drop / dose

        # Get sensitivity_ratio at correction time (±15 min)
        sr_window = sr[max(0, loc - 3):loc + 4]
        sr_at_event = float(np.nanmedian(sr_window)) if np.any(~np.isnan(sr_window)) else np.nan

        events.append({
            "time": str(t.iloc[loc]),
            "hour": float(t.iloc[loc].hour + t.iloc[loc].minute / 60),
            "dose": float(dose),
            "pre_bg": float(pre_bg),
            "post_bg": float(post_bg),
            "drop": float(drop),
            "isf": float(isf),
            "sr_at_event": sr_at_event,
        })
    return events


def main():
    print("EXP-2674: DynISF Formula × Demand ISF × Sensitivity Ratio")
    print("=" * 65)

    df = load_data()
    print(f"Loaded {df.patient_id.nunique()} Trio patients, {len(df):,} rows")

    results = {
        "experiment": "EXP-2674",
        "title": "DynISF Formula × Demand ISF × Sensitivity Ratio Deep Dive",
        "patients": {},
        "formula_comparison": {},
        "sr_prediction": {},
    }

    # Per-patient analysis
    all_events = {}
    for pid in sorted(TRIO_PATIENTS):
        sub = df[df.patient_id == pid]
        if len(sub) == 0:
            continue

        formula = FORMULA[pid]
        events = extract_corrections(sub)

        # Patient-level stats
        sched_isf = float(sub["scheduled_isf"].median())
        sr_med = float(sub["sensitivity_ratio"].dropna().median()) if sub["sensitivity_ratio"].notna().any() else np.nan
        sr_std = float(sub["sensitivity_ratio"].dropna().std()) if sub["sensitivity_ratio"].notna().sum() > 5 else np.nan
        sr_range = (float(sub["sensitivity_ratio"].dropna().quantile(0.05)),
                    float(sub["sensitivity_ratio"].dropna().quantile(0.95))) if sub["sensitivity_ratio"].notna().sum() > 10 else (np.nan, np.nan)

        isfs = [e["isf"] for e in events if -200 < e["isf"] < 500]
        srs_at_event = [e["sr_at_event"] for e in events if not np.isnan(e["sr_at_event"])]
        isfs_with_sr = [e["isf"] for e in events if not np.isnan(e["sr_at_event"]) and -200 < e["isf"] < 500]

        # Event-level SR-ISF correlation
        if len(isfs_with_sr) >= 5 and len(set(srs_at_event[:len(isfs_with_sr)])) > 1:
            r_event, p_event = stats.pearsonr(srs_at_event[:len(isfs_with_sr)], isfs_with_sr)
        else:
            r_event, p_event = np.nan, np.nan

        effective_isf = sched_isf / sr_med if sr_med > 0 else np.nan
        demand_isf = float(np.median(isfs)) if isfs else np.nan
        inflation = effective_isf / demand_isf if demand_isf > 0 and not np.isnan(effective_isf) else np.nan

        results["patients"][pid] = {
            "formula": formula,
            "n_events": len(events),
            "n_valid_isf": len(isfs),
            "n_with_sr": len(isfs_with_sr),
            "demand_isf_median": demand_isf,
            "scheduled_isf": sched_isf,
            "sr_median": sr_med,
            "sr_std": sr_std,
            "sr_5pct": sr_range[0],
            "sr_95pct": sr_range[1],
            "effective_isf": float(effective_isf) if not np.isnan(effective_isf) else None,
            "inflation_ratio": float(inflation) if not np.isnan(inflation) else None,
            "event_sr_isf_r": float(r_event) if not np.isnan(r_event) else None,
            "event_sr_isf_p": float(p_event) if not np.isnan(p_event) else None,
        }

        all_events[pid] = events

        n_str = f"n={len(events)}, ISF={demand_isf:.1f}" if isfs else f"n={len(events)}, no valid ISF"
        print(f"  [{formula[:3]}] {pid}: {n_str}, SR={sr_med:.3f}±{sr_std:.3f}, "
              f"sched={sched_isf:.0f}, eff={effective_isf:.1f}, "
              f"infl={inflation:.1f}×" if not np.isnan(inflation) else
              f"  [{formula[:3]}] {pid}: {n_str}")

    # Q1: Formula comparison
    print("\n" + "-" * 50)
    print("Q1: SR Distribution by Formula Type")
    for ftype in ["sigmoid", "log", "autoisf"]:
        fpats = [p for p in TRIO_PATIENTS if FORMULA[p] == ftype and p in results["patients"]]
        if not fpats:
            continue
        srs = [results["patients"][p]["sr_median"] for p in fpats if not np.isnan(results["patients"][p]["sr_median"])]
        stds = [results["patients"][p]["sr_std"] for p in fpats if not np.isnan(results["patients"][p].get("sr_std", np.nan))]
        print(f"  {ftype}: n={len(fpats)}, SR median={np.median(srs):.3f}, "
              f"SR std range=[{min(stds):.3f}, {max(stds):.3f}]" if stds else
              f"  {ftype}: n={len(fpats)}, SR median={np.median(srs):.3f}")

        results["formula_comparison"][ftype] = {
            "n_patients": len(fpats),
            "sr_medians": srs,
            "sr_stds": stds,
            "sr_pooled_median": float(np.median(srs)) if srs else None,
        }

    # Q2 & Q3: Demand ISF and inflation by formula
    print("\nQ2/Q3: Demand ISF and Inflation by Formula")
    for ftype in ["sigmoid", "log"]:
        fpats = [p for p in TRIO_PATIENTS if FORMULA[p] == ftype and p in results["patients"]
                 and results["patients"][p].get("inflation_ratio") is not None]
        if fpats:
            infls = [results["patients"][p]["inflation_ratio"] for p in fpats]
            disfs = [results["patients"][p]["demand_isf_median"] for p in fpats]
            print(f"  {ftype}: demand ISF median={np.median(disfs):.1f}, "
                  f"inflation range=[{min(infls):.1f}×, {max(infls):.1f}×]")
            results["formula_comparison"][ftype].update({
                "demand_isf_medians": disfs,
                "inflation_ratios": infls,
            })

    # Q4: Pooled SR-ISF prediction
    print("\nQ4: Event-Level SR Predicts ISF?")
    all_sr_events = []
    all_isf_events = []
    all_formula_events = []
    for pid in TRIO_PATIENTS:
        if pid not in all_events:
            continue
        formula = FORMULA[pid]
        for e in all_events[pid]:
            if not np.isnan(e["sr_at_event"]) and -200 < e["isf"] < 500:
                all_sr_events.append(e["sr_at_event"])
                all_isf_events.append(e["isf"])
                all_formula_events.append(formula)

    if len(all_sr_events) >= 10:
        r_pooled, p_pooled = stats.pearsonr(all_sr_events, all_isf_events)
        rho_pooled, rho_p = stats.spearmanr(all_sr_events, all_isf_events)
        print(f"  Pooled (n={len(all_sr_events)}): Pearson r={r_pooled:.3f} (p={p_pooled:.3f}), "
              f"Spearman rho={rho_pooled:.3f}")
        results["sr_prediction"] = {
            "pooled_n": len(all_sr_events),
            "pooled_pearson_r": float(r_pooled),
            "pooled_pearson_p": float(p_pooled),
            "pooled_spearman_rho": float(rho_pooled),
            "pooled_spearman_p": float(rho_p),
        }

        # Per-formula pooled
        for ftype in ["sigmoid", "log"]:
            idx = [i for i, f in enumerate(all_formula_events) if f == ftype]
            if len(idx) >= 10:
                fsrs = [all_sr_events[i] for i in idx]
                fisfs = [all_isf_events[i] for i in idx]
                fr, fp = stats.pearsonr(fsrs, fisfs)
                print(f"  {ftype} (n={len(idx)}): r={fr:.3f} (p={fp:.3f})")
                results["sr_prediction"][ftype] = {
                    "n": len(idx), "r": float(fr), "p": float(fp)
                }

    # ── Figures ───────────────────────────────────────────────────────
    print("\nGenerating figures...")

    # Fig 1: SR Distribution by formula type
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for fi, ftype in enumerate(["sigmoid", "log", "autoisf"]):
        ax = axes[fi]
        fpats = [p for p in TRIO_PATIENTS if FORMULA[p] == ftype]
        for pid in fpats:
            sub = df[df.patient_id == pid]
            sr_vals = sub["sensitivity_ratio"].dropna()
            if len(sr_vals) > 0:
                ax.hist(sr_vals, bins=30, alpha=0.5, label=pid[-4:],
                       edgecolor="k", lw=0.3)
        ax.set_xlabel("Sensitivity Ratio")
        ax.set_ylabel("Count")
        ax.set_title(f"{ftype.upper()} ({len(fpats)} patients)", fontweight="bold")
        ax.axvline(1.0, color="red", ls="--", alpha=0.5, label="Baseline (1.0)")
        ax.legend(fontsize=6)
        ax.grid(alpha=0.3)

    fig.suptitle("EXP-2674: Sensitivity Ratio Distribution by DynISF Formula",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_sr_distributions.png", dpi=150)
    plt.close(fig)
    print("  [fig1] SR distributions by formula")

    # Fig 2: Demand ISF vs Effective ISF per patient
    fig, ax = plt.subplots(figsize=(10, 8))
    for pid in TRIO_PATIENTS:
        if pid not in results["patients"]:
            continue
        p = results["patients"][pid]
        if p.get("effective_isf") is None or np.isnan(p["demand_isf_median"]):
            continue
        formula = FORMULA[pid]
        ax.scatter(p["effective_isf"], p["demand_isf_median"],
                  c=FORMULA_COLORS[formula], s=120,
                  marker="o" if formula == "sigmoid" else "s",
                  edgecolors="k", lw=0.5, zorder=3)
        ax.annotate(pid[-4:], (p["effective_isf"], p["demand_isf_median"]),
                   fontsize=7, xytext=(4, 4), textcoords="offset points")

    lims = ax.get_xlim()
    x = np.linspace(0, max(lims[1], 100), 100)
    ax.plot(x, x, "k--", alpha=0.3, label="1:1")
    ax.plot(x, x/2, "b:", alpha=0.3, label="2× inflation")
    ax.plot(x, x/5, "r:", alpha=0.3, label="5× inflation")

    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    legend = [
        Patch(facecolor=FORMULA_COLORS["sigmoid"], label="Sigmoid"),
        Patch(facecolor=FORMULA_COLORS["log"], label="Log"),
        Patch(facecolor=FORMULA_COLORS["autoisf"], label="AutoISF"),
        Line2D([0], [0], ls="--", c="k", label="1:1"),
        Line2D([0], [0], ls=":", c="b", label="2× inflation"),
        Line2D([0], [0], ls=":", c="r", label="5× inflation"),
    ]
    ax.legend(handles=legend, loc="upper left")
    ax.set_xlabel("Effective ISF (scheduled_ISF / sensitivity_ratio)")
    ax.set_ylabel("Demand ISF (0-2h drop/dose)")
    ax.set_title("EXP-2674: Effective ISF vs Demand ISF by DynISF Formula\n"
                 "(EXP-2651 predicted 2-10× inflation)", fontweight="bold")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_effective_vs_demand.png", dpi=150)
    plt.close(fig)
    print("  [fig2] Effective vs demand ISF")

    # Fig 3: Event-level SR vs ISF colored by formula
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    for ftype, ax in [("sigmoid", ax1), ("log", ax2)]:
        fpats = [p for p in TRIO_PATIENTS if FORMULA[p] == ftype and p in all_events]
        for pid in fpats:
            evts = all_events[pid]
            srs = [e["sr_at_event"] for e in evts if not np.isnan(e["sr_at_event"]) and -200 < e["isf"] < 500]
            isfs = [e["isf"] for e in evts if not np.isnan(e["sr_at_event"]) and -200 < e["isf"] < 500]
            if srs:
                ax.scatter(srs, isfs, alpha=0.4, s=20, label=pid[-4:], edgecolors="none")

        if ftype in results.get("sr_prediction", {}):
            r = results["sr_prediction"][ftype]["r"]
            p = results["sr_prediction"][ftype]["p"]
            ax.set_title(f"{ftype.upper()} (r={r:.3f}, p={p:.3f})", fontweight="bold")
        else:
            ax.set_title(f"{ftype.upper()}", fontweight="bold")
        ax.set_xlabel("Sensitivity Ratio at Correction")
        ax.set_ylabel("Demand ISF (mg/dL/U)")
        ax.axhline(0, color="k", alpha=0.3)
        ax.axvline(1.0, color="red", ls="--", alpha=0.3)
        ax.legend(fontsize=6)
        ax.grid(alpha=0.3)

    fig.suptitle("EXP-2674: Event-Level SR vs Demand ISF by Formula",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_event_sr_vs_isf.png", dpi=150)
    plt.close(fig)
    print("  [fig3] Event-level SR vs ISF by formula")

    # Fig 4: Inflation ratio by patient
    fig, ax = plt.subplots(figsize=(14, 5))
    pids_with_infl = [p for p in TRIO_PATIENTS if p in results["patients"]
                      and results["patients"][p].get("inflation_ratio") is not None]
    pids_with_infl.sort(key=lambda p: FORMULA[p])
    infls = [results["patients"][p]["inflation_ratio"] for p in pids_with_infl]
    colors = [FORMULA_COLORS[FORMULA[p]] for p in pids_with_infl]

    ax.bar(range(len(pids_with_infl)), infls, color=colors, alpha=0.7, edgecolor="k", lw=0.5)
    ax.axhline(1.0, color="k", ls="--", alpha=0.3, label="No inflation")
    ax.axhline(2.0, color="blue", ls=":", alpha=0.3, label="2× inflation")
    ax.axhline(5.0, color="red", ls=":", alpha=0.3, label="5× inflation")
    ax.set_xticks(range(len(pids_with_infl)))
    ax.set_xticklabels(pids_with_infl, rotation=90, fontsize=7)
    ax.set_ylabel("Effective ISF / Demand ISF (inflation ratio)")
    ax.set_title("EXP-2674: ISF Inflation Ratio by Patient and DynISF Formula",
                 fontweight="bold")
    legend = [Patch(facecolor=FORMULA_COLORS[f], label=f.upper()) for f in ["sigmoid", "log", "autoisf"]]
    ax.legend(handles=legend, loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_inflation_ratios.png", dpi=150)
    plt.close(fig)
    print("  [fig4] Inflation ratios by patient/formula")

    # Fig 5: Per-patient event-level correlation heatmap
    fig, ax = plt.subplots(figsize=(12, 5))
    pids_with_r = [p for p in TRIO_PATIENTS if p in results["patients"]
                   and results["patients"][p].get("event_sr_isf_r") is not None]
    pids_with_r.sort(key=lambda p: FORMULA[p])
    rs = [results["patients"][p]["event_sr_isf_r"] for p in pids_with_r]
    ps = [results["patients"][p]["event_sr_isf_p"] for p in pids_with_r]
    colors = [FORMULA_COLORS[FORMULA[p]] for p in pids_with_r]
    bar_alpha = [0.9 if pv < 0.05 else 0.3 for pv in ps]

    bars = ax.bar(range(len(pids_with_r)), rs, color=colors, edgecolor="k", lw=0.5)
    for bar, alpha in zip(bars, bar_alpha):
        bar.set_alpha(alpha)

    ax.axhline(0, color="k", alpha=0.3)
    ax.set_xticks(range(len(pids_with_r)))
    ax.set_xticklabels(pids_with_r, rotation=90, fontsize=7)
    ax.set_ylabel("Pearson r (SR vs ISF, per event)")
    ax.set_title("EXP-2674: Per-Patient Event-Level SR-ISF Correlation\n"
                 "(solid = p<0.05, faded = not significant)", fontweight="bold")
    legend = [Patch(facecolor=FORMULA_COLORS[f], label=f.upper()) for f in ["sigmoid", "log", "autoisf"]]
    ax.legend(handles=legend, loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig5_per_patient_sr_isf_r.png", dpi=150)
    plt.close(fig)
    print("  [fig5] Per-patient SR-ISF correlations")

    # Fig 6: Summary
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Panel 1: SR range (5th-95th pctile) per patient
    for pid in sorted(TRIO_PATIENTS, key=lambda p: FORMULA[p]):
        if pid not in results["patients"]:
            continue
        p = results["patients"][pid]
        lo, hi = p.get("sr_5pct", np.nan), p.get("sr_95pct", np.nan)
        med = p["sr_median"]
        if np.isnan(lo) or np.isnan(hi):
            continue
        y = sorted(TRIO_PATIENTS, key=lambda x: FORMULA[x]).index(pid)
        ax1.barh(y, hi - lo, left=lo, color=FORMULA_COLORS[FORMULA[pid]],
                alpha=0.6, edgecolor="k", lw=0.5)
        ax1.plot(med, y, "ko", ms=6, zorder=3)

    pids_sorted = sorted(TRIO_PATIENTS, key=lambda p: FORMULA[p])
    ax1.set_yticks(range(len(pids_sorted)))
    ax1.set_yticklabels(pids_sorted, fontsize=7)
    ax1.axvline(1.0, color="red", ls="--", alpha=0.5)
    ax1.set_xlabel("Sensitivity Ratio (5th-95th percentile)")
    ax1.set_title("SR Range per Patient", fontweight="bold")
    ax1.grid(axis="x", alpha=0.3)

    # Panel 2: Summary text
    ax2.axis("off")
    lines = [
        "EXP-2674 SUMMARY",
        "=" * 40,
        f"Patients: {len(results['patients'])} Trio DynISF",
        f"  Sigmoid: {sum(1 for p in results['patients'] if FORMULA.get(p)=='sigmoid')}",
        f"  Log: {sum(1 for p in results['patients'] if FORMULA.get(p)=='log')}",
        f"  AutoISF: {sum(1 for p in results['patients'] if FORMULA.get(p)=='autoisf')}",
        "",
    ]

    sr_pred = results.get("sr_prediction", {})
    if sr_pred.get("pooled_n"):
        lines.extend([
            "Pooled SR-ISF Prediction:",
            f"  n={sr_pred['pooled_n']} events",
            f"  Pearson r={sr_pred['pooled_pearson_r']:.3f}",
            f"  Spearman rho={sr_pred['pooled_spearman_rho']:.3f}",
        ])
        for ft in ["sigmoid", "log"]:
            if ft in sr_pred:
                lines.append(f"  {ft}: r={sr_pred[ft]['r']:.3f} (n={sr_pred[ft]['n']})")

    lines.extend(["", "Inflation (effective/demand):"])
    for ft in ["sigmoid", "log"]:
        fc = results.get("formula_comparison", {}).get(ft, {})
        if "inflation_ratios" in fc:
            lines.append(f"  {ft}: {min(fc['inflation_ratios']):.1f}-{max(fc['inflation_ratios']):.1f}×")

    ax2.text(0.05, 0.95, "\n".join(lines), transform=ax2.transAxes,
            fontsize=10, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.suptitle("EXP-2674: DynISF Formula Analysis Summary", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig6_summary.png", dpi=150)
    plt.close(fig)
    print("  [fig6] Summary")

    # Conclusions
    conclusions = []
    for ft in ["sigmoid", "log"]:
        fc = results.get("formula_comparison", {}).get(ft, {})
        if "inflation_ratios" in fc:
            med_infl = float(np.median(fc["inflation_ratios"]))
            conclusions.append(f"{ft} patients: median inflation = {med_infl:.1f}×")

    if sr_pred.get("pooled_pearson_r") is not None:
        r = sr_pred["pooled_pearson_r"]
        if abs(r) > 0.3:
            conclusions.append(f"Pooled SR-ISF: r={r:.3f} — SR has predictive value")
        else:
            conclusions.append(f"Pooled SR-ISF: r={r:.3f} — SR weakly predictive")

    results["conclusions"] = conclusions
    print("\n" + "=" * 65)
    print("CONCLUSIONS")
    for c in conclusions:
        print(f"  → {c}")

    with open(OUTFILE, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nResults → {OUTFILE}")


if __name__ == "__main__":
    main()
