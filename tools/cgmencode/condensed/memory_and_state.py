"""Canonical narrative 04 figure pack: Metabolic Memory & State Structure.

  F1  Carb-memory window sweep — R² vs window length (rect + exp)
  F2  Two-state clustering — state means + transition matrix
  F3  State-conditional ISF & basal drift (per-patient decoupling)
  F4  Variance decomposition — between-patient vs between-day vs within-day

All recomposition from archived experiment outputs.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "externals" / "experiments"
OUT = ROOT / "visualizations" / "canonical" / "04"
OUT.mkdir(parents=True, exist_ok=True)


def figure_1_memory_sweep() -> None:
    d = json.loads((EXP / "exp-2627_carb_window_sweep.json").read_text())
    rect = d["rectangular_sweep"]
    expo = d["exponential_sweep"]
    rx = [r["window_hours"] for r in rect]; ry = [r["r2"] for r in rect]
    ex = [r["tau_hours"] for r in expo];    ey = [r["r2"] for r in expo]

    fig, ax = plt.subplots(figsize=(9, 5.3))
    ax.plot(rx, ry, "-o", color="#4575b4", lw=2, label="rectangular window")
    ax.plot(ex, ey, "-s", color="#d73027", lw=2, label="exponential decay (τ)")

    # peaks
    ri = int(np.argmax(ry)); ei = int(np.argmax(ey))
    ax.axvline(rx[ri], color="#4575b4", ls=":", alpha=0.5)
    ax.axvline(ex[ei], color="#d73027", ls=":", alpha=0.5)
    ax.annotate(f"rect peak\n{rx[ri]} h  R²={ry[ri]:.3f}",
                (rx[ri], ry[ri]), xytext=(rx[ri] + 3, ry[ri] + 0.005),
                fontsize=9, color="#4575b4")
    ax.annotate(f"exp peak\nτ={ex[ei]} h  R²={ey[ei]:.3f}",
                (ex[ei], ey[ei]), xytext=(ex[ei] + 3, ey[ei] - 0.015),
                fontsize=9, color="#d73027")

    ax.set_xlabel("Memory window length (hours)")
    ax.set_ylabel("R² of carb-load → overnight EGP/drift")
    ax.set_title(
        "F1 · Carb memory extends to ~48 h (EXP-2627)\n"
        "R² doubles from 12 h to 30–48 h window, then plateaus."
    )
    ax.legend(loc="lower right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "f1_memory_window_sweep.png", dpi=140)
    plt.close(fig)
    print(f"[F1] wrote {OUT/'f1_memory_window_sweep.png'}")


def figure_2_state_clustering() -> None:
    d = json.loads((EXP / "exp-2810_state_clustering.json").read_text())
    summary = d["state_summary"]
    T = d["transition_matrix"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.3),
                                   gridspec_kw={"width_ratios": [1.5, 1]})

    metrics = ["mean_glucose", "pct_in_range", "pct_high", "bg_volatility"]
    labels  = ["Mean BG\n(mg/dL)", "% in range\n(70–180)", "% high\n(>180)",
               "BG volatility\n(CV-ish)"]
    s0 = [summary[m]["0"] for m in metrics]
    s1 = [summary[m]["1"] for m in metrics]
    xs = np.arange(len(metrics))
    w = 0.38
    ax1.bar(xs - w/2, s0, w, color="#2b83ba", edgecolor="k",
            label=f"S0 stable ({d['state_distribution_pct']['0']:.0f}%)")
    ax1.bar(xs + w/2, s1, w, color="#d7191c", edgecolor="k",
            label=f"S1 elevated ({d['state_distribution_pct']['1']:.0f}%)")
    for i, (a, b) in enumerate(zip(s0, s1)):
        ax1.annotate(f"{a:.0f}", (xs[i] - w/2, a + 1), ha="center", fontsize=9)
        ax1.annotate(f"{b:.0f}", (xs[i] + w/2, b + 1), ha="center", fontsize=9)
    ax1.set_xticks(xs)
    ax1.set_xticklabels(labels, fontsize=9)
    ax1.set_title(
        "F2a · Two-state clustering of 48-h windows (EXP-2810)\n"
        "Separation ~42.6 mg/dL in mean BG; 30 pp in TIR."
    )
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(axis="y", alpha=0.25)

    # Transition matrix heatmap
    M = np.array([[T["0"]["0"], T["0"]["1"]],
                  [T["1"]["0"], T["1"]["1"]]])
    im = ax2.imshow(M, cmap="YlOrRd", vmin=0, vmax=1, aspect="auto")
    ax2.set_xticks([0, 1]); ax2.set_yticks([0, 1])
    ax2.set_xticklabels(["→ S0", "→ S1"]); ax2.set_yticklabels(["from S0", "from S1"])
    for i in range(2):
        for j in range(2):
            ax2.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center",
                     fontsize=18, weight="bold",
                     color="k" if M[i,j] < 0.6 else "white")
    ax2.set_title("F2b · 24-h transition matrix\nDiagonal persistence ≈ 0.85\n(state sticks — slow time constant)")

    fig.tight_layout()
    fig.savefig(OUT / "f2_state_structure.png", dpi=140)
    plt.close(fig)
    print(f"[F2] wrote {OUT/'f2_state_structure.png'}")


def figure_3_state_decoupling() -> None:
    df = pd.read_parquet(EXP / "exp-2811_per_state_extractions.parquet")
    d  = json.loads((EXP / "exp-2811_state_decoupling.json").read_text())

    # keep patients with both states
    by_pat = df.pivot_table(index="patient_id", columns="state",
                            values=["isf", "basal_drift"], aggfunc="first")
    isf0 = by_pat.get(("isf", 0)); isf1 = by_pat.get(("isf", 1))
    bd0  = by_pat.get(("basal_drift", 0)); bd1 = by_pat.get(("basal_drift", 1))

    isf_ok = (~isf0.isna()) & (~isf1.isna())
    bd_ok  = (~bd0.isna()) & (~bd1.isna())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.3))

    # Panel A: per-patient ISF in S0 vs S1
    if isf_ok.sum() >= 1:
        ax1.scatter(isf0[isf_ok], isf1[isf_ok], s=70, color="#4575b4",
                    edgecolor="k", zorder=3)
        for pid in isf0[isf_ok].index:
            ax1.plot([isf0[pid], isf0[pid]], [isf0[pid], isf1[pid]],
                     ":", color="grey", alpha=0.4, zorder=1)
    lim = np.nanmax([isf0.max(), isf1.max()]) if isf0.notna().any() else 100
    lim = float(np.nan_to_num(lim, nan=100))
    ax1.plot([0, lim * 1.05], [0, lim * 1.05], "--", color="grey",
             label="S0 = S1 (stable ISF)")
    ax1.set_xlabel("ISF in S0 — stable state (mg/dL per U)")
    ax1.set_ylabel("ISF in S1 — elevated state (mg/dL per U)")
    ax1.set_title(
        f"F3a · Per-patient ISF shifts state-conditionally (n={int(isf_ok.sum())})\n"
        f"{d['isf_varying_by_state_n']} / {d['n_patient_state_extractions']} patients show ISF change > 10% across states"
    )
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.set_xlim(0, lim * 1.05); ax1.set_ylim(0, lim * 1.05)

    # Panel B: basal drift S0 vs S1
    if bd_ok.sum() >= 1:
        ax2.scatter(bd0[bd_ok], bd1[bd_ok], s=70, color="#d73027",
                    edgecolor="k", zorder=3)
    all_bd = np.concatenate([bd0[bd_ok].values, bd1[bd_ok].values])
    m = float(max(abs(np.nanmin(all_bd)), abs(np.nanmax(all_bd))) * 1.1 + 1) if bd_ok.sum() else 20
    ax2.axhline(0, color="grey", lw=1); ax2.axvline(0, color="grey", lw=1)
    ax2.plot([-m, m], [-m, m], "--", color="grey", alpha=0.6,
             label="S0 = S1 (no state dependence)")
    ax2.set_xlabel("Basal drift in S0 (mg/dL per hour)")
    ax2.set_ylabel("Basal drift in S1 (mg/dL per hour)")
    ax2.set_title(
        f"F3b · State-conditional basal drift (n={int(bd_ok.sum())})\n"
        f"{d['basal_varying_by_state_n']} / {d['n_patient_state_extractions']} patients show basal-drift polarity change"
    )
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(alpha=0.25)
    ax2.set_xlim(-m, m); ax2.set_ylim(-m, m)

    fig.suptitle("F3 · Single global ISF/basal numbers are lossy — parameters are state-dependent (EXP-2811)",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f3_state_decoupling.png", dpi=140)
    plt.close(fig)
    print(f"[F3] wrote {OUT/'f3_state_decoupling.png'}")


def figure_4_variance_decomposition() -> None:
    d = json.loads((EXP / "exp-2697_variance_decomp.json").read_text())
    v = d["variance_decomposition"]
    labels = ["between-patient", "between-day\n(within patient)", "within-day\n(residual)"]
    vals = [v["between_patient_pct"], v["between_day_pct"], v["residual_pct"]]
    colors = ["#2b83ba", "#fdae61", "#d73027"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.3),
                                   gridspec_kw={"width_ratios": [1.2, 1]})

    bars = ax1.bar(labels, vals, color=colors, edgecolor="k")
    for b, v_ in zip(bars, vals):
        ax1.annotate(f"{v_:.1f}%", (b.get_x() + b.get_width() / 2, v_ + 1.5),
                     ha="center", fontsize=12, weight="bold")
    ax1.set_ylabel("% of response variance")
    ax1.set_ylim(0, 100)
    ax1.set_title(
        f"F4a · Variance decomposition (EXP-2697, n={d['n_events']:,} events)\n"
        "Within-day noise dominates — the ceiling for any descriptive fit."
    )
    ax1.grid(axis="y", alpha=0.25)

    # A pie as a second view — emphasise the 84 % floor
    ax2.pie(vals, labels=[f"{l}\n({v_:.1f}%)" for l, v_ in zip(labels, vals)],
            colors=colors, startangle=90, wedgeprops={"edgecolor": "k"})
    ax2.set_title("F4b · Same numbers, pie view\n(ICC_patient ≈ 0.019)")

    fig.suptitle(
        "F4 · 84% of bolus-response variance is within-day noise. Population models can only explain ~16%.",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(OUT / "f4_variance_decomposition.png", dpi=140)
    plt.close(fig)
    print(f"[F4] wrote {OUT/'f4_variance_decomposition.png'}")


def main() -> None:
    figure_1_memory_sweep()
    figure_2_state_clustering()
    figure_3_state_decoupling()
    figure_4_variance_decomposition()
    print(f"\nFigures written to {OUT}")


if __name__ == "__main__":
    main()
