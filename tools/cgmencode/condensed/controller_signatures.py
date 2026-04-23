"""Condensed figure pack for canonical narrative 03: AID Controller Signatures.

Four figures demonstrating that Loop, Trio, and OpenAPS are physically
distinct systems, not variations on a theme.

  F1  Suspension polarity (inverted Loop vs Trio)
  F2  Insulin delivery decomposition by controller (smb/manual/basal + suspend %)
  F3  Recovery fraction from S0→S1 state transitions by controller
  F4  Simpson decomposition: TIR by (phenotype × controller)

All recomposition (no fresh compute).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "externals" / "experiments"
OUT = ROOT / "visualizations" / "canonical" / "03"
OUT.mkdir(parents=True, exist_ok=True)

CTRL_COLORS = {"Loop": "#4575b4", "Trio": "#d73027", "OpenAPS": "#1a9850",
               "AAPS": "#984ea3"}


def figure_1_polarity() -> None:
    df = pd.read_parquet(EXP / "exp-2871_per_patient.parquet")
    counts = df.groupby("controller")["all_positive"].agg(["sum", "count"])
    counts["frac"] = counts["sum"] / counts["count"]
    controllers = ["Loop", "OpenAPS", "Trio"]
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    xs = np.arange(len(controllers))
    fracs = [counts.loc[c, "frac"] for c in controllers]
    ns = [counts.loc[c, "count"] for c in controllers]
    pos = [counts.loc[c, "sum"] for c in controllers]
    bars = ax.bar(xs, [f * 100 for f in fracs],
                  color=[CTRL_COLORS[c] for c in controllers], edgecolor="k")
    for i, (f, p, n) in enumerate(zip(fracs, pos, ns)):
        ax.annotate(f"{int(p)}/{int(n)}", (xs[i], f * 100 + 2), ha="center",
                    fontsize=11, weight="bold")
    ax.axhline(50, color="grey", ls=":", lw=1)
    ax.set_xticks(xs)
    ax.set_xticklabels(controllers, fontsize=11)
    ax.set_ylabel("% of patients with ALL-POSITIVE basal shift\n(suspend MORE when BG is ELEVATED)")
    ax.set_ylim(0, 105)
    ax.set_title(
        "F1 · Suspension polarity is INVERTED across controllers (EXP-2871)\n"
        "Loop suspends when BG is LOW (hypo safety). Trio suspends when BG is HIGH (under SMBs)."
    )
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "f1_suspension_polarity.png", dpi=140)
    plt.close(fig)
    print(f"[F1] wrote {OUT/'f1_suspension_polarity.png'}")


def figure_2_delivery_decomp() -> None:
    d = json.loads((EXP / "exp-2685_controller_strategy.json").read_text())
    controllers = ["Loop", "Trio", "OpenAPS"]
    smb = []; manual = []; basal = []; suspend = []
    for c in controllers:
        key = c.lower() + "_insulin_breakdown"
        b = d[key]
        smb.append(b["smb_daily"])
        manual.append(b["manual_daily"])
        basal.append(b["basal_daily"])
        suspend.append(d[c.lower() + "_strategy"]["suspend_pct"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2),
                                   gridspec_kw={"width_ratios": [1.5, 1]})
    xs = np.arange(len(controllers))
    w = 0.6
    b_basal = ax1.bar(xs, basal, w, color="#91bfdb", label="delivered basal", edgecolor="k")
    b_smb = ax1.bar(xs, smb, w, bottom=basal, color="#fdae61", label="SMB", edgecolor="k")
    b_man = ax1.bar(xs, manual, w, bottom=[b + s for b, s in zip(basal, smb)],
                    color="#d73027", label="user/manual bolus", edgecolor="k")
    totals = [b + s + m for b, s, m in zip(basal, smb, manual)]
    for i, t in enumerate(totals):
        ax1.annotate(f"{t:.0f} U/d", (xs[i], t + 4), ha="center", fontsize=10,
                     weight="bold")
    ax1.set_xticks(xs)
    ax1.set_xticklabels(controllers, fontsize=11)
    ax1.set_ylabel("Daily insulin (U/day)")
    ax1.set_title("F2a · Daily insulin delivery decomposition (EXP-2685)")
    ax1.legend(loc="upper left", fontsize=9, frameon=False)
    ax1.grid(axis="y", alpha=0.25)

    # Right panel: suspend %
    ax2.bar(xs, suspend, w, color=[CTRL_COLORS[c] for c in controllers],
            edgecolor="k")
    ax2.set_xticks(xs)
    ax2.set_xticklabels(controllers, fontsize=11)
    ax2.set_ylabel("% of time basal suspended")
    ax2.set_title("F2b · Time with basal = 0")
    ax2.set_ylim(0, 100)
    for i, s in enumerate(suspend):
        ax2.annotate(f"{s:.0f}%", (xs[i], s + 2), ha="center", fontsize=11,
                     weight="bold")
    ax2.grid(axis="y", alpha=0.25)

    fig.suptitle("F2 · Loop, Trio, OpenAPS are three fundamentally different delivery strategies",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f2_delivery_decomposition.png", dpi=140)
    plt.close(fig)
    print(f"[F2] wrote {OUT/'f2_delivery_decomposition.png'}")


def figure_3_recovery_by_controller() -> None:
    d = json.loads((EXP / "exp-2812_state_transition_audition.json").read_text())
    rec = d["recovery_by_controller"]
    controllers = ["Loop", "OpenAPS", "Trio"]
    means = [rec[c]["mean"] for c in controllers]
    medians = [rec[c]["median"] for c in controllers]
    counts = [rec[c]["count"] for c in controllers]

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    xs = np.arange(len(controllers))
    w = 0.35
    ax.bar(xs - w/2, means, w, color=[CTRL_COLORS[c] for c in controllers],
           edgecolor="k", label="mean")
    ax.bar(xs + w/2, medians, w, color=[CTRL_COLORS[c] for c in controllers],
           edgecolor="k", alpha=0.55, label="median")
    for i, (m, md, n) in enumerate(zip(means, medians, counts)):
        ax.annotate(f"n={int(n)}", (xs[i], max(m, md) + 0.02), ha="center",
                    fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(controllers, fontsize=11)
    ax.set_ylabel("Recovery fraction (48-h windows S1 → S0 within 3 windows)")
    ax.set_ylim(0, max(0.6, max(means) * 1.4))
    ax.set_title(
        "F3 · Recovery asymmetry after a well-controlled → moderate-high transition (EXP-2812)\n"
        "Loop's median recovery is 0.00 — Loop patients in this cohort tend not to self-recover from a slump."
    )
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "f3_recovery_by_controller.png", dpi=140)
    plt.close(fig)
    print(f"[F3] wrote {OUT/'f3_recovery_by_controller.png'}")


def figure_4_simpson() -> None:
    d = json.loads((EXP / "exp-2872_simpson_check.json").read_text())
    pooled = d["pooled_phenotype_tir"]
    matched = d["matched_pivot"]

    # Pooled bar
    phenotypes = ["stream_A_dominant", "stream_B_early", "stream_B_normal"]
    pooled_means = {p["phenotype"]: p["median"] for p in pooled}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.3),
                                   gridspec_kw={"width_ratios": [1, 1.6]})
    xs = np.arange(len(phenotypes))
    ax1.bar(xs, [pooled_means.get(p, np.nan) * 100 for p in phenotypes],
            color=["#d73027", "#fdae61", "#4575b4"], edgecolor="k")
    ax1.set_xticks(xs)
    ax1.set_xticklabels([p.replace("_", "\n") for p in phenotypes], fontsize=9)
    ax1.set_ylabel("Median TIR (%)")
    ax1.set_ylim(0, 100)
    ax1.set_title("F4a · POOLED: 30 pp phenotype → TIR gap")
    for i, p in enumerate(phenotypes):
        m = pooled_means.get(p, np.nan)
        if not np.isnan(m): ax1.annotate(f"{m*100:.0f}%", (xs[i], m*100 + 2),
                                         ha="center", fontsize=10, weight="bold")
    ax1.grid(axis="y", alpha=0.25)

    # Matched pivot: phenotype × controller heatmap
    controllers = ["Loop", "OpenAPS", "Trio"]
    M = np.full((len(phenotypes), len(controllers)), np.nan)
    for i, p in enumerate(phenotypes):
        for j, c in enumerate(controllers):
            v = matched.get(p, {}).get(c, None)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                M[i, j] = v * 100
    im = ax2.imshow(M, cmap="RdYlGn", vmin=40, vmax=100, aspect="auto")
    ax2.set_xticks(range(len(controllers)))
    ax2.set_xticklabels(controllers, fontsize=11)
    ax2.set_yticks(range(len(phenotypes)))
    ax2.set_yticklabels([p.replace("_", "\n") for p in phenotypes], fontsize=9)
    for i in range(len(phenotypes)):
        for j in range(len(controllers)):
            v = M[i, j]
            if np.isnan(v):
                ax2.text(j, i, "—", ha="center", va="center", fontsize=14,
                         color="grey")
            else:
                ax2.text(j, i, f"{v:.0f}%", ha="center", va="center",
                         fontsize=12, weight="bold",
                         color="k" if 60 < v < 85 else "white")
    ax2.set_title(
        "F4b · STRATIFIED: phenotype effect within-controller shrinks\n"
        "Within stream_B_early: Loop 58 → OpenAPS 64 → Trio 77  (controller gap ≫ phenotype gap)"
    )
    plt.colorbar(im, ax=ax2, shrink=0.8, label="Median TIR (%)")

    fig.suptitle("F4 · Simpson's paradox: most of the pooled phenotype→TIR gap is controller composition",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f4_simpson_decomposition.png", dpi=140)
    plt.close(fig)
    print(f"[F4] wrote {OUT/'f4_simpson_decomposition.png'}")


def main() -> None:
    figure_1_polarity()
    figure_2_delivery_decomp()
    figure_3_recovery_by_controller()
    figure_4_simpson()
    print(f"\nFigures written to {OUT}")


if __name__ == "__main__":
    main()
