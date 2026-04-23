"""EXP-2851 — Fast-scale envelope coupling (reactive-loop probe).

Extends EXP-2849 with 1h, 2h, 3h windows to locate where the
audition basal-shift signal dissolves into AR(1) noise, per the
dual-timescale architecture (memories: hourly = settings/BGI,
5-min = AR(1) momentum).

Hypothesis: signal loses power steeply below 6h because short
windows are dominated by reactive intervention cycles (SMB /
correction / suspension) rather than the envelope-demand
relationship that drives multi-day state clustering.

Output (Charter V8 compliant):
  externals/experiments/exp-2851_fast_scale_envelope.parquet
  externals/experiments/exp-2851_summary.json
  docs/60-research/figures/exp-2851_fast_scale_envelope.png

Interpretation lens: if frac_sig drops sharply between 6h → 3h,
that's confirmation the envelope signal is a slow-timescale
phenomenon and audition cannot collapse below ~6h without losing
the demand/response coupling. If signal holds, reactive-loop
dynamics themselves carry envelope structure (unexpected).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")
WINDOWS_HOURS = [1, 2, 3, 6, 12, 24, 48]


def aggregate_windows(g_pat: pd.DataFrame, window_h: int) -> pd.DataFrame:
    cells_per_window = window_h * 12
    if len(g_pat) < cells_per_window * 6:
        return pd.DataFrame()
    g_pat = g_pat.sort_values("time").reset_index(drop=True)
    g_pat["window_id"] = g_pat.index // cells_per_window
    agg = (
        g_pat.groupby("window_id")
        .agg(
            n=("glucose", "size"),
            glucose=("glucose", "mean"),
            actual_basal=("actual_basal_rate", "mean"),
        )
        .reset_index()
    )
    return agg[agg["n"] >= cells_per_window * 0.8].reset_index(drop=True)


def per_patient_signal(g_pat: pd.DataFrame, window_h: int) -> dict | None:
    agg = aggregate_windows(g_pat, window_h)
    if len(agg) < 6:
        return None
    q33, q67 = np.percentile(agg["glucose"], [33, 67])
    elev = agg[agg["glucose"] >= q67]
    norm = agg[agg["glucose"] <= q33]
    if len(elev) < 3 or len(norm) < 3:
        return None
    basal_elev = float(elev["actual_basal"].mean())
    basal_norm = float(norm["actual_basal"].mean())
    if basal_norm <= 0:
        return None
    shift_pct = 100 * (basal_elev - basal_norm) / basal_norm
    try:
        u, p = stats.mannwhitneyu(
            elev["actual_basal"].dropna(),
            norm["actual_basal"].dropna(),
            alternative="two-sided",
        )
    except ValueError:
        p = np.nan
    return dict(
        window_h=window_h,
        n_windows=int(len(agg)),
        n_elev=int(len(elev)),
        n_norm=int(len(norm)),
        basal_shift_pct=shift_pct,
        mannwhitney_p=float(p) if not np.isnan(p) else None,
    )


def main() -> None:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)

    rows = []
    for pid, g_pat in g.groupby("patient_id"):
        for w in WINDOWS_HOURS:
            r = per_patient_signal(g_pat, w)
            if r is None:
                continue
            r["patient_id"] = pid
            rows.append(r)

    df = pd.DataFrame(rows)
    print(f"Fast-scale rows: {len(df)} "
          f"({df['patient_id'].nunique()} patients × ≤{len(WINDOWS_HOURS)} windows)")

    summary_rows = []
    for w in WINDOWS_HOURS:
        sub = df[df["window_h"] == w]
        if sub.empty:
            continue
        n = len(sub)
        n_sig01 = int((sub["mannwhitney_p"].fillna(1.0) < 0.01).sum())
        n_sig05 = int((sub["mannwhitney_p"].fillna(1.0) < 0.05).sum())
        summary_rows.append(dict(
            window_h=w,
            n_patients=n,
            frac_sig_p01=round(n_sig01 / n, 3),
            frac_sig_p05=round(n_sig05 / n, 3),
            median_shift_pct=float(sub["basal_shift_pct"].median()),
            iqr_shift_pct=float(np.percentile(sub["basal_shift_pct"], 75)
                                - np.percentile(sub["basal_shift_pct"], 25)),
        ))
    summary_df = pd.DataFrame(summary_rows)
    print("\nCohort summary by window:")
    print(summary_df.to_string(index=False))

    df.to_parquet(EXP / "exp-2851_fast_scale_envelope.parquet", index=False)

    # Find the dissolution window: largest consecutive drop in frac_sig_p01
    deltas = []
    for i in range(1, len(summary_rows)):
        a, b = summary_rows[i - 1], summary_rows[i]
        deltas.append((a["window_h"], b["window_h"],
                       b["frac_sig_p01"] - a["frac_sig_p01"]))

    summary = {
        "experiment": "EXP-2851",
        "title": "Fast-scale envelope coupling",
        "stream": "B",
        "windows_h": WINDOWS_HOURS,
        "n_patients_total": int(df["patient_id"].nunique()),
        "by_window": summary_rows,
        "adjacent_deltas_p01": [
            {"from_h": a, "to_h": b, "delta_frac_sig": round(d, 3)}
            for a, b, d in deltas
        ],
        "checks": {
            "PASS_all_windows_covered": len(summary_rows) == len(WINDOWS_HOURS),
            "PASS_signal_monotone_with_window": all(
                summary_rows[i]["frac_sig_p01"] >= summary_rows[i - 1]["frac_sig_p01"] - 0.05
                for i in range(1, len(summary_rows))
            ),
            "PASS_6h_maintains_half_signal": any(
                r["window_h"] == 6 and r["frac_sig_p01"] >= 0.5
                for r in summary_rows
            ),
            "PASS_1h_shows_dissolution": any(
                r["window_h"] == 1 and r["frac_sig_p01"] < 0.5
                for r in summary_rows
            ),
        },
    }
    summary["checks_passed"] = sum(summary["checks"].values())

    if summary["checks"]["PASS_1h_shows_dissolution"]:
        interp = ("Envelope signal dissolves by 1h windows — consistent "
                  "with dual-timescale architecture: 5-min/1h is AR(1) "
                  "domain, not envelope-demand. Audition cannot collapse "
                  "below ~6h without losing the signal.")
    else:
        interp = ("Envelope signal persists at 1h — reactive-loop dynamics "
                  "themselves carry envelope structure (unexpected). "
                  "Warrants dual-timescale re-examination.")
    summary["interpretation"] = interp

    (EXP / "exp-2851_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Figure
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    x = np.arange(len(summary_df))
    ax.plot(x, summary_df["frac_sig_p01"], "o-", label="p<0.01", color="#d62728")
    ax.plot(x, summary_df["frac_sig_p05"], "s--", label="p<0.05", color="#ff7f0e")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{w}h" for w in summary_df["window_h"]])
    ax.set_xlabel("Aggregation window")
    ax.set_ylabel("Fraction of patients with significant envelope shift")
    ax.set_title("EXP-2851 — Fast-scale envelope dissolution\n"
                 "Stream B; where does the audition basal-shift signal fail?")
    ax.axhline(0.5, color="gray", ls=":", alpha=0.6, label="half-cohort")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2851_fast_scale_envelope.png", dpi=120)
    plt.close()

    print(f"\nChecks passed: {summary['checks_passed']}/4")
    print(f"Interpretation: {summary['interpretation']}")


if __name__ == "__main__":
    main()
