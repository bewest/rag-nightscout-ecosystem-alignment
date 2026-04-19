#!/usr/bin/env python3
"""EXP-2675: Cross-Controller ISF Portability — Does Physiology Shine Through?

MOTIVATION:
  We now have demand ISF extracted from 22 patients across 3 controller types.
  The key question: is the extracted demand ISF a stable physiological property
  (determined by the patient's insulin sensitivity), or is it an artifact of
  the controller's behavior?

  If demand ISF is physiological, then:
  1. It should cluster by PATIENT (across days, conditions), not by controller type
  2. The ISF distribution shape should be similar across controller types
  3. The ISF-vs-dose relationship should be flat (dose-independent) per controller
  4. Cross-controller ISF ranges should overlap (similar patient populations)

APPROACH:
  Compare demand ISF extraction across controllers using:
  - Distribution analysis (per-controller ISF shape comparison)
  - Within-patient stability (coefficient of variation)
  - Between-patient variance (ANOVA: patient > controller as variance source)
  - Dose-independence verification per controller (replication of EXP-2663/2672)
  - ISF-vs-scheduled_ISF correlation (profile ISF as noisy ground truth)

OUTPUTS:
  - externals/experiments/exp-2675_cross_controller_isf.json
  - visualizations/autoresearch-wave3/fig[1-5]_*.png
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
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUTFILE = RESULTS_DIR / "exp-2675_cross_controller_isf.json"
VIZ_DIR = Path("visualizations/autoresearch-wave3")
VIZ_DIR.mkdir(parents=True, exist_ok=True)

CTRL_COLORS = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}
CTRL_ORDER = ["loop", "trio", "openaps"]
STEPS_PER_HOUR = 12


def load_qualified():
    with open(MANIFEST) as f:
        manifest = json.load(f)
    qualified = manifest["qualified_patients"]
    df = pd.read_parquet(PARQUET)
    df = df[df.patient_id.isin(qualified)].copy()
    ds = pd.read_parquet(DS_PARQUET, columns=["patient_id", "controller"])
    ctrl = ds.groupby("patient_id")["controller"].agg(lambda x: x.value_counts().index[0])
    df = df.merge(ctrl.rename("controller"), on="patient_id", how="left")
    df["controller"] = df["controller"].fillna("unknown")
    return df, qualified


def extract_corrections(pdf, prior_bolus_h=2.0, min_dose=0.3, min_pre_bg=100,
                        carb_window_h=1.0, demand_window_h=2.0):
    """Extract correction events with 2h isolation."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

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
        c_start = max(0, loc - carb_window)
        c_end = min(len(pdf), loc + demand_steps + 1)
        if carbs[c_start:c_end].sum() > 0:
            continue
        prior_slice = bolus[max(0, loc - prior_window):loc]
        if prior_slice.sum() > 0:
            continue
        post_bg = glucose[loc + demand_steps]
        if np.isnan(post_bg):
            continue

        dose = bolus[loc]
        drop = pre_bg - post_bg
        isf = drop / dose

        events.append({
            "dose": float(dose),
            "isf": float(isf),
            "pre_bg": float(pre_bg),
            "drop": float(drop),
        })
    return events


def main():
    print("EXP-2675: Cross-Controller ISF Portability")
    print("=" * 55)

    df, qualified = load_qualified()
    print(f"Loaded {len(qualified)} patients, {len(df):,} rows")

    results = {"experiment": "EXP-2675", "patients": {}, "comparisons": {}}

    # Per-patient extraction
    ctrl_events = {ct: [] for ct in CTRL_ORDER}
    ctrl_isf_medians = {ct: [] for ct in CTRL_ORDER}
    patient_data = []

    for pid in sorted(qualified):
        sub = df[df.patient_id == pid]
        ct = sub.controller.iloc[0]
        if ct not in CTRL_ORDER:
            continue

        events = extract_corrections(sub)
        isfs = [e["isf"] for e in events if -200 < e["isf"] < 500]
        sched_isf = float(sub["scheduled_isf"].median())

        if len(isfs) < 5:
            results["patients"][pid] = {"controller": ct, "status": "insufficient", "n": len(isfs)}
            continue

        med_isf = float(np.median(isfs))
        cv = float(np.std(isfs) / abs(np.mean(isfs))) if np.mean(isfs) != 0 else np.nan
        iqr = float(np.percentile(isfs, 75) - np.percentile(isfs, 25))

        # Dose-independence check
        doses = [e["dose"] for e in events if -200 < e["isf"] < 500]
        if len(doses) >= 5:
            r_dose, p_dose = stats.pearsonr(np.log(doses), isfs)
        else:
            r_dose, p_dose = np.nan, np.nan

        results["patients"][pid] = {
            "controller": ct,
            "n_events": len(isfs),
            "demand_isf_median": med_isf,
            "demand_isf_iqr": iqr,
            "cv": cv,
            "scheduled_isf": sched_isf,
            "dose_isf_r": float(r_dose) if not np.isnan(r_dose) else None,
            "inflation": sched_isf / med_isf if med_isf > 0 else None,
        }

        ctrl_events[ct].extend(isfs)
        ctrl_isf_medians[ct].append(med_isf)
        patient_data.append({"pid": pid, "ct": ct, "isfs": isfs, "med": med_isf,
                            "sched": sched_isf, "cv": cv})

        print(f"  [{ct[:1].upper()}] {pid}: n={len(isfs)}, "
              f"ISF={med_isf:.1f}±{iqr:.1f}, CV={cv:.2f}, "
              f"sched={sched_isf:.0f}, dose_r={r_dose:.3f}" if not np.isnan(r_dose) else
              f"  [{ct[:1].upper()}] {pid}: n={len(isfs)}, ISF={med_isf:.1f}")

    # ── Cross-Controller Comparisons ──────────────────────────────────
    print("\n" + "=" * 55)
    print("CROSS-CONTROLLER COMPARISONS")

    # 1. Distribution comparison (Kruskal-Wallis)
    ctrl_lists = [ctrl_events[ct] for ct in CTRL_ORDER if ctrl_events[ct]]
    if len(ctrl_lists) >= 2:
        h_stat, kw_p = stats.kruskal(*ctrl_lists)
        print(f"\n  Kruskal-Wallis (event-level ISF): H={h_stat:.1f}, p={kw_p:.4f}")
        results["comparisons"]["kruskal_wallis"] = {
            "H": float(h_stat), "p": float(kw_p),
            "interpretation": "ISFs differ by controller" if kw_p < 0.05 else "ISFs similar across controllers"
        }

    # 2. Per-controller summary
    for ct in CTRL_ORDER:
        if ctrl_events[ct]:
            vals = ctrl_events[ct]
            print(f"  {ct}: n={len(vals)}, median={np.median(vals):.1f}, "
                  f"IQR=[{np.percentile(vals, 25):.1f}, {np.percentile(vals, 75):.1f}]")
            results["comparisons"][ct] = {
                "n_events": len(vals),
                "median": float(np.median(vals)),
                "iqr_lo": float(np.percentile(vals, 25)),
                "iqr_hi": float(np.percentile(vals, 75)),
                "n_patients": len(ctrl_isf_medians[ct]),
            }

    # 3. Scheduled ISF vs demand ISF correlation (does profile predict physiology?)
    all_sched = [p["sched"] for p in patient_data if p["med"] > 0]
    all_demand = [p["med"] for p in patient_data if p["med"] > 0]
    if len(all_sched) >= 5:
        r_sched, p_sched = stats.pearsonr(all_sched, all_demand)
        rho_sched, rho_p = stats.spearmanr(all_sched, all_demand)
        print(f"\n  Scheduled ISF vs demand ISF (cross-patient):")
        print(f"    Pearson r={r_sched:.3f} (p={p_sched:.4f})")
        print(f"    Spearman rho={rho_sched:.3f} (p={rho_p:.4f})")
        results["comparisons"]["sched_vs_demand"] = {
            "pearson_r": float(r_sched), "pearson_p": float(p_sched),
            "spearman_rho": float(rho_sched), "spearman_p": float(rho_p),
            "n": len(all_sched),
        }

    # 4. Within-patient CV comparison (is ISF more stable for some controllers?)
    for ct in CTRL_ORDER:
        cvs = [p["cv"] for p in patient_data if p["ct"] == ct and not np.isnan(p["cv"])]
        if cvs:
            print(f"  {ct} median CV: {np.median(cvs):.2f} ({len(cvs)} patients)")
            results["comparisons"][f"{ct}_cv"] = {
                "median_cv": float(np.median(cvs)), "n": len(cvs)
            }

    # 5. Variance decomposition (patient vs controller)
    if len(patient_data) >= 5:
        # Build matrix for 2-way analysis
        from collections import defaultdict
        ct_isfs = defaultdict(list)
        for p in patient_data:
            ct_isfs[p["ct"]].append(p["med"])

        # Between-controller variance
        all_meds = [p["med"] for p in patient_data]
        grand_mean = np.mean(all_meds)
        ss_between = sum(len(ct_isfs[ct]) * (np.mean(ct_isfs[ct]) - grand_mean) ** 2
                        for ct in CTRL_ORDER if ct_isfs[ct])
        ss_within = sum((m - np.mean(ct_isfs[ct])) ** 2
                       for ct in CTRL_ORDER for m in ct_isfs[ct])
        ss_total = sum((m - grand_mean) ** 2 for m in all_meds)
        eta_sq = ss_between / ss_total if ss_total > 0 else 0

        print(f"\n  Variance decomposition:")
        print(f"    eta^2 (controller): {eta_sq:.3f} ({eta_sq*100:.1f}% of variance)")
        print(f"    Residual (patient): {(1-eta_sq)*100:.1f}%")
        results["comparisons"]["variance_decomposition"] = {
            "eta_squared_controller": float(eta_sq),
            "residual_patient": float(1 - eta_sq),
            "interpretation": "Patient physiology dominates" if eta_sq < 0.2 else "Controller type matters"
        }

    # ── Figures ───────────────────────────────────────────────────────
    print("\nGenerating figures...")

    # Fig 1: ISF distributions per controller (violin + box)
    fig, ax = plt.subplots(figsize=(10, 6))
    parts = []
    positions = []
    for ci, ct in enumerate(CTRL_ORDER):
        vals = ctrl_events[ct]
        if vals:
            filtered = [v for v in vals if -100 < v < 200]
            vp = ax.violinplot([filtered], positions=[ci], showmedians=True)
            for body in vp["bodies"]:
                body.set_facecolor(CTRL_COLORS[ct])
                body.set_alpha(0.5)
            vp["cmedians"].set_color("k")

    ax.set_xticks(range(len(CTRL_ORDER)))
    ax.set_xticklabels([f"{ct.upper()}\n(n={len(ctrl_events[ct])})" for ct in CTRL_ORDER])
    ax.set_ylabel("Demand ISF (mg/dL/U)")
    ax.set_title("EXP-2675: Demand ISF Distribution by Controller Type\n"
                 "(Violin plots, 2h isolation)", fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(0, color="k", alpha=0.3)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_isf_distributions.png", dpi=150)
    plt.close(fig)
    print("  [fig1] ISF distributions")

    # Fig 2: Scheduled ISF vs Demand ISF
    fig, ax = plt.subplots(figsize=(10, 8))
    for p in patient_data:
        if p["med"] > 0:
            ax.scatter(p["sched"], p["med"],
                      c=CTRL_COLORS[p["ct"]], s=100,
                      edgecolors="k", lw=0.5, zorder=3)
            ax.annotate(p["pid"][-4:] if len(p["pid"]) > 4 else p["pid"],
                       (p["sched"], p["med"]),
                       fontsize=6, xytext=(3, 3), textcoords="offset points")

    lims = [0, max(max(p["sched"] for p in patient_data),
                   max(p["med"] for p in patient_data if p["med"] > 0)) * 1.1]
    x = np.linspace(0, lims[1], 100)
    ax.plot(x, x, "k--", alpha=0.3, label="1:1 (no inflation)")
    ax.plot(x, x/2, "b:", alpha=0.3, label="2× inflation")
    ax.plot(x, x/5, "r:", alpha=0.3, label="5× inflation")
    ax.plot(x, x/10, "m:", alpha=0.3, label="10× inflation")

    if len(all_sched) >= 5:
        slope, intercept, r, p, _ = stats.linregress(all_sched, all_demand)
        x_fit = np.linspace(min(all_sched), max(all_sched), 100)
        ax.plot(x_fit, slope * x_fit + intercept, "r-", lw=2,
               label=f"Fit: r={r:.3f}")

    from matplotlib.patches import Patch
    legend = [Patch(facecolor=CTRL_COLORS[ct], label=ct.upper()) for ct in CTRL_ORDER]
    legend.extend([
        plt.Line2D([0], [0], ls="--", c="k", label="1:1"),
        plt.Line2D([0], [0], ls=":", c="b", label="2×"),
        plt.Line2D([0], [0], ls=":", c="r", label="5×"),
    ])
    if len(all_sched) >= 5:
        legend.append(plt.Line2D([0], [0], c="r", lw=2, label=f"r={r:.3f}"))
    ax.legend(handles=legend, loc="upper left")
    ax.set_xlabel("Scheduled ISF (profile, mg/dL/U)")
    ax.set_ylabel("Demand ISF (extracted, mg/dL/U)")
    ax.set_title("EXP-2675: Profile ISF vs Demand ISF\n"
                 "(Does the profile predict true sensitivity?)", fontweight="bold")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_scheduled_vs_demand.png", dpi=150)
    plt.close(fig)
    print("  [fig2] Scheduled vs demand ISF")

    # Fig 3: Per-patient ISF CV (stability)
    fig, ax = plt.subplots(figsize=(14, 5))
    pdata_sorted = sorted(patient_data, key=lambda p: p["ct"])
    pids = [p["pid"] for p in pdata_sorted]
    cvs = [p["cv"] for p in pdata_sorted]
    colors = [CTRL_COLORS[p["ct"]] for p in pdata_sorted]

    ax.bar(range(len(pids)), cvs, color=colors, alpha=0.7, edgecolor="k", lw=0.5)
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, rotation=90, fontsize=6)
    ax.set_ylabel("Coefficient of Variation")
    ax.set_title("EXP-2675: Within-Patient Demand ISF Stability\n"
                 "(Lower CV = more stable ISF)", fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    legend = [Patch(facecolor=CTRL_COLORS[ct], label=ct.upper()) for ct in CTRL_ORDER]
    ax.legend(handles=legend, loc="upper right")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_isf_stability.png", dpi=150)
    plt.close(fig)
    print("  [fig3] ISF stability (CV)")

    # Fig 4: Dose-independence per controller (replication)
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        ct_pats = [p for p in patient_data if p["ct"] == ct]
        all_d, all_i = [], []

        for p in ct_pats:
            pid = p["pid"]
            sub = df[df.patient_id == pid]
            events = extract_corrections(sub)
            for e in events:
                if -200 < e["isf"] < 500 and e["dose"] > 0:
                    all_d.append(e["dose"])
                    all_i.append(e["isf"])

        if all_d:
            ax.scatter(all_d, all_i, c=CTRL_COLORS[ct], alpha=0.3, s=15, edgecolors="none")
            if len(all_d) >= 10:
                log_d = np.log(all_d)
                slope, intercept, r, p, _ = stats.linregress(log_d, all_i)
                x_fit = np.linspace(min(all_d), max(all_d), 100)
                y_fit = slope * np.log(x_fit) + intercept
                ax.plot(x_fit, y_fit, "k-", lw=2, label=f"r={r:.3f}, p={p:.1e}")
                ax.legend(fontsize=10)

        ax.set_xlabel("Dose (U)")
        ax.set_ylabel("Demand ISF (mg/dL/U)")
        n_pts = len([p for p in ct_pats])
        n_evts = len(all_d)
        ax.set_title(f"{ct.upper()} ({n_pts} pts, {n_evts} events)", fontweight="bold")
        ax.grid(alpha=0.3)
        ax.axhline(0, color="k", alpha=0.3)

    fig.suptitle("EXP-2675: Dose-Independence Verification per Controller\n"
                 "(Flat line = dose-independent ISF, validates EXP-2663/2672)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_dose_independence.png", dpi=150)
    plt.close(fig)
    print("  [fig4] Dose-independence per controller")

    # Fig 5: Variance decomposition summary
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Pie chart of variance
    if "variance_decomposition" in results["comparisons"]:
        vd = results["comparisons"]["variance_decomposition"]
        eta = vd["eta_squared_controller"]
        sizes = [eta * 100, (1 - eta) * 100]
        labels = [f"Controller Type\n({eta*100:.1f}%)", f"Patient (Physiology)\n({(1-eta)*100:.1f}%)"]
        colors_pie = ["#FF9800", "#2196F3"]
        ax1.pie(sizes, labels=labels, colors=colors_pie, autopct="", startangle=90)
        ax1.set_title("Variance Decomposition: What Drives ISF?", fontweight="bold")

    # Summary text
    ax2.axis("off")
    lines = [
        "EXP-2675 SUMMARY",
        "=" * 40,
        "",
    ]

    for ct in CTRL_ORDER:
        c = results["comparisons"].get(ct, {})
        cv_data = results["comparisons"].get(f"{ct}_cv", {})
        if c:
            lines.append(f"{ct.upper()} (n={c.get('n_patients', '?')} pts, {c.get('n_events', '?')} events)")
            lines.append(f"  Median ISF: {c.get('median', '?'):.1f} mg/dL/U")
            lines.append(f"  IQR: [{c.get('iqr_lo', '?'):.1f}, {c.get('iqr_hi', '?'):.1f}]")
            if cv_data:
                lines.append(f"  Median CV: {cv_data.get('median_cv', '?'):.2f}")
            lines.append("")

    kw = results["comparisons"].get("kruskal_wallis", {})
    if kw:
        lines.append(f"Kruskal-Wallis: p={kw.get('p', '?'):.4f}")
        lines.append(f"  {kw.get('interpretation', '')}")

    svd = results["comparisons"].get("sched_vs_demand", {})
    if svd:
        lines.extend([
            "",
            f"Profile vs Demand ISF: r={svd.get('pearson_r', '?'):.3f}",
        ])

    vd = results["comparisons"].get("variance_decomposition", {})
    if vd:
        lines.extend([
            "",
            f"Variance: {vd.get('interpretation', '')}",
            f"  Controller: {vd['eta_squared_controller']*100:.1f}%",
            f"  Patient: {vd['residual_patient']*100:.1f}%",
        ])

    ax2.text(0.05, 0.95, "\n".join(lines), transform=ax2.transAxes,
            fontsize=9, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.suptitle("EXP-2675: Cross-Controller ISF Portability Summary",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig5_summary.png", dpi=150)
    plt.close(fig)
    print("  [fig5] Summary")

    # Conclusions
    conclusions = []
    if "variance_decomposition" in results["comparisons"]:
        eta = results["comparisons"]["variance_decomposition"]["eta_squared_controller"]
        if eta < 0.1:
            conclusions.append(f"Controller type explains only {eta*100:.1f}% of ISF variance — physiology dominates")
        elif eta < 0.3:
            conclusions.append(f"Controller type explains {eta*100:.1f}% of ISF variance — moderate effect")
        else:
            conclusions.append(f"Controller type explains {eta*100:.1f}% of ISF variance — significant effect")

    if "kruskal_wallis" in results["comparisons"]:
        kw_p = results["comparisons"]["kruskal_wallis"]["p"]
        if kw_p > 0.05:
            conclusions.append(f"ISF distributions not significantly different across controllers (p={kw_p:.3f})")
        else:
            conclusions.append(f"ISF distributions differ across controllers (p={kw_p:.3f}) — investigate subgroups")

    if "sched_vs_demand" in results["comparisons"]:
        r = results["comparisons"]["sched_vs_demand"]["pearson_r"]
        conclusions.append(f"Profile ISF {'predicts' if abs(r) > 0.3 else 'weakly predicts'} demand ISF (r={r:.3f})")

    results["conclusions"] = conclusions
    print("\n" + "=" * 55)
    print("CONCLUSIONS")
    for c in conclusions:
        print(f"  -> {c}")

    with open(OUTFILE, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nResults -> {OUTFILE}")


if __name__ == "__main__":
    main()
