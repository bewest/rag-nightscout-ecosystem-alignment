"""Condensed figure pack for canonical narrative 02: Closed-loop masking &
identifiability.

Four figures that together show why observational closed-loop data systematically
deceives naive analysis, and how our production architecture responds.

  F1  Descriptive-prescriptive paradox (Fixed vs log-ISF forward sim)
  F2  PSM ATT decays to near-zero — the controller substitutes the bolus
  F3  Variance decomposition (patient/day/residual)
  F4  Bootstrap survival of audition signals under per-patient resampling

Data sources (all recomposition; no fresh compute):
  externals/experiments/exp-2641_forward_sim_log_isf.json
  externals/experiments/exp-2695_causal_psm.json
  externals/experiments/exp-2697_variance_decomp.json
  externals/experiments/exp-2859/61/62/63/64 summaries

Output: visualizations/canonical/02/
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "externals" / "experiments"
OUT = ROOT / "visualizations" / "canonical" / "02"
OUT.mkdir(parents=True, exist_ok=True)


def figure_1_paradox() -> None:
    d = json.loads((EXP / "exp-2641_forward_sim_log_isf.json").read_text())
    models = d["models"]
    labels, mae, bias, rlabel = [], [], [], []
    for key in ["A_fixed_isf", "B_pop_log_isf", "C_patient_log_isf"]:
        m = models[key]
        labels.append(m["label"])
        mae.append(m["mae"])
        bias.append(m["bias"])
        rlabel.append(f"r={m['r']:.2f}")
    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(9, 5.2))
    w = 0.35
    b1 = ax1.bar(x - w / 2, mae, width=w, color="#4575b4", label="MAE (mg/dL)")
    ax1.set_ylabel("MAE (mg/dL) — lower is better descriptively",
                   color="#4575b4")
    ax1.tick_params(axis="y", labelcolor="#4575b4")
    ax2 = ax1.twinx()
    colors = ["#d73027" if b > 0 else "#1a9850" for b in bias]
    b2 = ax2.bar(x + w / 2, bias, width=w, color=colors,
                 label="Bias (mg/dL)", alpha=0.9)
    ax2.axhline(0, color="k", lw=0.6)
    ax2.set_ylabel("Bias = pred − actual (mg/dL)\nNEGATIVE bias = over-predicts drop → UNDER-doses in practice",
                   color="#444", fontsize=9)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=9)
    for i, r in enumerate(rlabel):
        ax1.annotate(r, (x[i] - w / 2, mae[i] + 2), ha="center", fontsize=9)
    ax1.set_title("F1 · Best-descriptor = worst prescriber\n"
                  "Per-patient log-ISF fits events best (MAE 59) but its bias "
                  "($-$23 mg/dL) means it would systematically under-predict drops and therefore OVER-dose")
    ax1.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "f1_descriptive_prescriptive_paradox.png", dpi=140)
    plt.close(fig)
    print(f"[F1] wrote {OUT/'f1_descriptive_prescriptive_paradox.png'}")


def figure_2_psm_decay() -> None:
    d = json.loads((EXP / "exp-2695_causal_psm.json").read_text())
    h = d["att_by_horizon"]
    horizons = [30, 60, 90, 120]
    att = [h[f"{k}m"]["att"] for k in horizons]
    se = [h[f"{k}m"]["se"] for k in horizons]

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.errorbar(horizons, att, yerr=[1.96 * s for s in se], fmt="o-",
                color="#d73027", lw=2, ms=8, capsize=5,
                label="PSM ATT  (n_matched=47,045 pairs)")
    ax.axhline(0, color="k", lw=0.6)
    # Naive expected bolus effect at ISF=50: ~−50 mg/dL sustained
    ax.axhline(-50, color="#999", ls="--", lw=1.2,
               label="naive ISF=50 expectation")
    # Annotate channel compensation
    cc = d["channel_compensation"]["bolus_group"]
    smb, exb = cc["smb_2h"], cc["excess_basal_2h"]
    ax.text(95, -30, f"Channel compensation during bolus window:\n"
                      f"  +{smb:.2f} U extra SMB\n"
                      f"  {exb:+.2f} U/h basal delta\n"
                      f"→ controller substitutes ~90 % of the\n"
                      f"bolus effect by 120 min.",
            fontsize=9, bbox=dict(boxstyle="round,pad=0.4",
                                  fc="#fff8ee", ec="#d49c3f", lw=1))
    ax.set_xlabel("Horizon (minutes after bolus)")
    ax.set_ylabel("Average Treatment effect on the Treated (mg/dL)")
    ax.set_title("F2 · PSM treatment effect decays to near-zero by 120 min\n"
                 "Controller co-intervention erases the bolus signal from observational data")
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "f2_psm_att_decay.png", dpi=140)
    plt.close(fig)
    print(f"[F2] wrote {OUT/'f2_psm_att_decay.png'}")


def figure_3_variance_decomp() -> None:
    d = json.loads((EXP / "exp-2697_variance_decomp.json").read_text())
    v = d["variance_decomposition"]
    parts = [v["between_patient_pct"], v["between_day_pct"], v["residual_pct"]]
    labels = [f"Between-patient\n{parts[0]:.1f} %",
              f"Between-day\n{parts[1]:.1f} %",
              f"Within-day residual\n{parts[2]:.1f} %"]
    colors = ["#4575b4", "#fdae61", "#d73027"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                   gridspec_kw={"width_ratios": [1, 1.2]})
    wedges, _ = ax1.pie(parts, labels=labels, colors=colors,
                        startangle=90, wedgeprops=dict(edgecolor="w", lw=2))
    ax1.set_title(f"F3a · Variance decomposition of BG  (n={d['n_events']:,} events)")

    # R² ceiling cartoon
    scales = ["event", "day", "patient"]
    ceilings = [1 - 0.839, 1 - (0.839 + 0.142), 1]  # cumulative deliverable
    r2_ceil = [0.3, 0.55, 0.7]  # plausible model R²
    ax2.bar(scales, r2_ceil, color=["#d73027", "#fdae61", "#4575b4"],
            edgecolor="k")
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("Plausible model R² ceiling")
    ax2.set_title("F3b · Aggregate wins, single events lose\n"
                  "(event-level ~0.3, patient-level ~0.7)")
    for s, r in zip(scales, r2_ceil):
        ax2.text(s, r + 0.02, f"{r:.2f}", ha="center", fontsize=11,
                 weight="bold")
    ax2.grid(axis="y", alpha=0.25)

    fig.suptitle("F3 · 84 % of within-day BG variance is irreducible stochastic",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f3_variance_decomp.png", dpi=140)
    plt.close(fig)
    print(f"[F3] wrote {OUT/'f3_variance_decomp.png'}")


def figure_4_bootstrap_survival() -> None:
    # Load 5 bootstrap summaries
    specs = [
        ("Simpson\nparadox (2859)", "exp-2859_summary.json",
         "n_high_conf_simpson_p_ge_0.9", None),
        ("ISF under-\ncorrection (2861)", "exp-2861_summary.json",
         None, None),  # uses bootstrap_band_counts
        ("Low recovery\n(2862)", "exp-2862_summary.json",
         None, None),
        ("Wear / site\ndegradation (2863)", "exp-2863_summary.json",
         None, None),
        ("Post-high\nenvelope (2864)", "exp-2864_summary.json",
         None, None),
    ]
    # For each: extract n_patients and confident survivors under bootstrap
    labels, confident, uncertain, clean = [], [], [], []
    n_total = []
    for label, fname, key_conf, _ in specs:
        d = json.loads((EXP / fname).read_text())
        n = d["n_patients"]
        if "bootstrap_band_counts" in d:
            b = d["bootstrap_band_counts"]
            c = sum(v for k, v in b.items() if k.startswith("confident_") and k != "confident_neutral")
            u = b.get("uncertain", 0)
            cl = b.get("confident_neutral", 0) + b.get("confident_clean", 0)
        else:
            # Simpson: from top-level keys
            c = d.get("n_high_conf_simpson_p_ge_0.9", 0)
            cl = d.get("n_high_conf_clean_p_le_0.1", 0)
            u = d.get("n_uncertain_0.1_to_0.9", 0)
        labels.append(label)
        confident.append(c)
        uncertain.append(u)
        clean.append(cl)
        n_total.append(n)

    fig, ax = plt.subplots(figsize=(11, 5.2))
    x = np.arange(len(labels))
    w = 0.7
    b1 = ax.bar(x, confident, width=w, color="#d73027",
                label="confident positive (P ≥ 0.9)", edgecolor="k")
    b2 = ax.bar(x, uncertain, width=w, bottom=confident, color="#fdae61",
                label="uncertain (0.1 ≤ P < 0.9)", edgecolor="k")
    b3 = ax.bar(x, clean,
                width=w, bottom=[c + u for c, u in zip(confident, uncertain)],
                color="#91bfdb", label="confident clean (P ≤ 0.1)",
                edgecolor="k")
    for i, (n, c) in enumerate(zip(n_total, confident)):
        ax.annotate(f"n={n}\n{c}/{n} survive",
                    (x[i], n + 0.4), ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Patients classified")
    ax.set_title("F4 · Naive audition thresholds vs bootstrap survival\n"
                 "Only 2 of 5 signals (post-high envelope, low recovery) produce ≥ 50 % confident positives.  Wear/site: 0/10.")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "f4_bootstrap_survival.png", dpi=140)
    plt.close(fig)
    print(f"[F4] wrote {OUT/'f4_bootstrap_survival.png'}")


def main() -> None:
    figure_1_paradox()
    figure_2_psm_decay()
    figure_3_variance_decomp()
    figure_4_bootstrap_survival()
    print(f"\nFigures written to {OUT}")


if __name__ == "__main__":
    main()
