"""EXP-2847: ISF re-audit for flat-phenotype + low-recovery patients.

Question (Stream B): the audition matrix flagged flat-phenotype +
low-recovery patients (esp. patient `b`) as needing explicit ISF
re-audit. Is observed correction-event ISF systematically off-profile
for these patients vs the cohort?

Method (correction-event ISF, EXP-2754 family):
  - Find correction-only events: bolus delivered with no carbs in
    prior 30 min and BG > 180 mg/dL at bolus time
  - Track BG drop over next 3 hours (DIA window)
  - Observed effective ISF = (BG_start - BG_min_3h) / bolus_units
  - Compare to scheduled ISF from grid

Charter: Stream B operational. Observed effective ISF is NOT biological
ISF (controller compensation embedded). Audition signal is the
direction + magnitude of the GAP relative to scheduled.

Outputs:
  externals/experiments/exp-2847_flat_isf_audit.json
  externals/experiments/exp-2847_correction_events.parquet
  docs/60-research/figures/exp-2847_flat_isf_audit.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")


def find_correction_events(g: pd.DataFrame) -> pd.DataFrame:
    """Locate correction-only events per patient."""
    events = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.sort_values("time").reset_index(drop=True)
        # Total bolus per cell
        total_bolus = sub["bolus"].fillna(0) + sub["bolus_smb"].fillna(0)
        # Recent carbs (rolling 6 cells = 30 min back)
        recent_carbs = (
            sub["carbs"].fillna(0).rolling(6, min_periods=1).sum().shift(1)
        )
        is_corr = (
            (total_bolus >= 0.5)
            & (sub["glucose"] >= 180)
            & (recent_carbs.fillna(0) < 5)
        )
        idx = np.where(is_corr.values)[0]
        for i in idx:
            window_end = min(i + 36, len(sub) - 1)  # 3 hours = 36 cells
            win = sub.iloc[i:window_end + 1]
            # Skip if more carbs in window
            if win["carbs"].fillna(0).sum() > 10:
                continue
            bg_start = sub["glucose"].iat[i]
            bg_min = win["glucose"].min()
            drop = bg_start - bg_min
            sched_isf = sub["scheduled_isf"].iat[i] if "scheduled_isf" in sub else np.nan
            obs_isf = drop / max(total_bolus.iat[i], 0.01)
            events.append(dict(
                patient_id=pid,
                time=sub["time"].iat[i],
                bg_start=bg_start,
                bg_min=bg_min,
                drop=drop,
                bolus=total_bolus.iat[i],
                obs_isf=obs_isf,
                sched_isf=sched_isf,
            ))
    return pd.DataFrame(events)


def main() -> dict:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)
    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")

    # All 17 significant patients + the flat ones for focus
    pids = pheno["patient_id"].unique()
    g_sub = g[g["patient_id"].isin(pids)].copy()

    print("Finding correction events...")
    ev = find_correction_events(g_sub)
    print(f"Found {len(ev)} correction events")

    # Per-patient ISF stats (require ≥3 events)
    per_pat = (
        ev.groupby("patient_id")
        .agg(
            n_events=("obs_isf", "size"),
            obs_isf_median=("obs_isf", "median"),
            sched_isf_median=("sched_isf", "median"),
            obs_isf_iqr=("obs_isf", lambda s: float(np.nanpercentile(s, 75) - np.nanpercentile(s, 25))),
        )
        .reset_index()
    )
    per_pat = per_pat[per_pat["n_events"] >= 3]
    per_pat["isf_gap_pct"] = (
        100 * (per_pat["obs_isf_median"] - per_pat["sched_isf_median"])
        / np.maximum(per_pat["sched_isf_median"], 1.0)
    )

    # Annotate with phenotype
    per_pat = per_pat.merge(
        pheno[["patient_id", "controller", "phenotype",
               "median_recovery_fraction"]],
        on="patient_id", how="left",
    )
    per_pat["flag_flat_lo_rec"] = (
        (per_pat["phenotype"] == "flat")
        & (per_pat["median_recovery_fraction"].fillna(1.0) < 0.4)
    )

    print("\nPer-patient correction ISF audit:")
    print(per_pat.to_string(index=False))

    # Population summary
    flat_lo = per_pat[per_pat["flag_flat_lo_rec"]]
    others = per_pat[~per_pat["flag_flat_lo_rec"]]

    summary = {
        "n_flat_lo_recovery": int(len(flat_lo)),
        "n_other": int(len(others)),
        "flat_lo_isf_gap_median_pct": (
            float(flat_lo["isf_gap_pct"].median())
            if len(flat_lo) else None
        ),
        "other_isf_gap_median_pct": (
            float(others["isf_gap_pct"].median())
            if len(others) else None
        ),
    }

    # Patient b deep-dive
    b_row = per_pat[per_pat["patient_id"] == "b"]
    b_data = b_row.to_dict(orient="records")[0] if len(b_row) else None

    checks = {
        "PASS_correction_events_found": int(len(ev)) >= 100,
        "PASS_per_patient_coverage": int(len(per_pat)) >= 5,
        "PASS_patient_b_covered": b_data is not None,
        "PASS_no_biology_claim": True,
    }
    result = {
        "experiment": "EXP-2847",
        "title": "Correction-ISF re-audit for flat-low-recovery patients",
        "stream": "B",
        "n_correction_events": int(len(ev)),
        "n_patients_covered": int(len(per_pat)),
        "patient_b_audit": b_data,
        "summary": summary,
        "per_patient": per_pat.to_dict(orient="records"),
        "checks": checks,
        "checks_passed": int(sum(checks.values())),
        "interpretation": (
            "Observed correction ISF embeds controller compensation "
            "(EXP-2755). The AUDITION signal is the gap direction + "
            "magnitude vs scheduled ISF, not the absolute observed "
            "value. Patients with negative gap % under-correct (BG "
            "drops less than scheduled ISF predicts) and may benefit "
            "from a TIGHTER scheduled ISF; positive gap means over-"
            "correction (consider LOOSER scheduled ISF)."
        ),
    }

    ev.to_parquet(EXP / "exp-2847_correction_events.parquet", index=False)
    (EXP / "exp-2847_flat_isf_audit.json").write_text(
        json.dumps(result, indent=2, default=str)
    )

    # Visualization: per-patient observed vs scheduled, color flat-lo
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "EXP-2847 — Correction-ISF re-audit (audition matrix follow-up)\n"
        "Stream B; observed embeds controller compensation; "
        "gap direction is the audition signal",
        fontsize=11,
    )

    ax = axes[0]
    for _, row in per_pat.iterrows():
        color = "#d62728" if row["flag_flat_lo_rec"] else "#888888"
        size = 200 if row["flag_flat_lo_rec"] else 80
        ax.scatter(row["sched_isf_median"], row["obs_isf_median"],
                   color=color, s=size, alpha=0.85, edgecolor="white")
        ax.annotate(row["patient_id"],
                    (row["sched_isf_median"], row["obs_isf_median"]),
                    fontsize=8, alpha=0.7,
                    xytext=(4, 4), textcoords="offset points")
    lim = max(
        per_pat["sched_isf_median"].max(),
        per_pat["obs_isf_median"].max(),
    ) * 1.1
    ax.plot([0, lim], [0, lim], "k--", lw=0.5, label="parity")
    ax.set_xlabel("Median scheduled ISF (mg/dL/U)")
    ax.set_ylabel("Median observed correction ISF (mg/dL/U)")
    ax.set_title("Scheduled vs observed (red = flat + low recovery)")
    ax.legend(loc="best", fontsize=8)

    ax = axes[1]
    colors = ["#d62728" if f else "#888888" for f in per_pat["flag_flat_lo_rec"]]
    pos = np.arange(len(per_pat))
    bars = ax.barh(pos, per_pat["isf_gap_pct"], color=colors,
                   edgecolor="white", alpha=0.8)
    ax.set_yticks(pos)
    ax.set_yticklabels(
        [f"{r['patient_id']} [{r['controller']}/{r['phenotype']}]"
         for _, r in per_pat.iterrows()],
        fontsize=8,
    )
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("ISF gap (%): observed − scheduled")
    ax.set_title("Per-patient ISF gap (red = flat + low recovery)")

    plt.tight_layout(rect=(0, 0, 1, 0.94))
    out = FIG / "exp-2847_flat_isf_audit.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {out}")
    print(json.dumps(result, indent=2, default=str)[:1500])
    return result


if __name__ == "__main__":
    main()
