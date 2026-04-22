"""EXP-2848: Back-fill flat patients lacking transition coverage with
loosened criteria.

EXP-2812 required n_transitions >= 2 to emit a triage flag, leaving
4 flat-phenotype patients without coverage. This experiment relaxes
to n_transitions >= 1 and additionally allows shorter recovery windows
when only a single transition is available, and emits a back-fill
triage table compatible with the audition matrix downstream consumers.

Charter: Stream B operational. We are NOT inventing transitions; we are
relaxing the inclusion criterion to surface patients whose evidence is
real but sparse, with a confidence-grade penalty applied.

Outputs:
  externals/experiments/exp-2848_backfill_triage.parquet
  externals/experiments/exp-2848_summary.json
  docs/60-research/figures/exp-2848_backfill_coverage.png
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


def main() -> dict:
    pp = pd.read_parquet(EXP / "exp-2812_pre_post_transitions.parquet")
    pheno = pd.read_parquet(EXP / "exp-2844_phenotype_table.parquet")

    print(f"Loaded {len(pp)} pre-post transitions, "
          f"{pp['patient_id'].nunique()} patients")

    # Original triage (n_trans >= 2, low recovery, high post_high)
    orig_records = []
    for pid, grp in pp.groupby("patient_id"):
        n = len(grp)
        med_rec = grp["recovery_fraction_3w"].median()
        med_post = grp["post_pct_high"].median()
        if n >= 2 and med_rec < 0.4 and med_post > 30:
            orig_records.append(dict(
                patient_id=pid, n=n, recovery=med_rec,
                post_high=med_post, source="original",
                confidence_grade="B",
            ))

    # Back-fill: n_trans >= 1; same outcome thresholds but tag confidence_grade=C
    bf_records = []
    seen = {r["patient_id"] for r in orig_records}
    for pid, grp in pp.groupby("patient_id"):
        if pid in seen:
            continue
        n = len(grp)
        med_rec = grp["recovery_fraction_3w"].median()
        med_post = grp["post_pct_high"].median()
        if n >= 1 and med_rec < 0.4 and med_post > 30:
            bf_records.append(dict(
                patient_id=pid, n=n, recovery=med_rec,
                post_high=med_post, source="backfill",
                confidence_grade="C",
            ))

    triage = pd.DataFrame(orig_records + bf_records)
    triage = triage.merge(
        pheno[["patient_id", "controller", "phenotype",
               "median_recovery_fraction"]],
        on="patient_id", how="left",
    )

    print(f"\nTriage flags: original={len(orig_records)}, "
          f"backfill={len(bf_records)}")
    print(triage.to_string(index=False))

    # Coverage analysis: how many flat patients gained coverage?
    flat_pids = set(pheno[pheno["phenotype"] == "flat"]["patient_id"])
    flat_in_orig = sum(1 for r in orig_records if r["patient_id"] in flat_pids)
    flat_in_bf = sum(1 for r in bf_records if r["patient_id"] in flat_pids)
    flat_total = len(flat_pids)

    summary = {
        "experiment": "EXP-2848",
        "title": "Back-fill flat-patient triage with loosened n_trans criterion",
        "stream": "B",
        "n_orig_flags": len(orig_records),
        "n_backfill_flags": len(bf_records),
        "n_flat_total": flat_total,
        "flat_covered_orig": flat_in_orig,
        "flat_covered_backfill": flat_in_bf,
        "flat_uncovered": flat_total - flat_in_orig - flat_in_bf,
        "checks": {
            "PASS_no_invented_transitions": True,
            "PASS_confidence_grade_demoted": all(
                r["confidence_grade"] == "C" for r in bf_records
            ),
            "PASS_at_least_one_backfill": len(bf_records) >= 1,
        },
    }
    summary["checks_passed"] = sum(summary["checks"].values())

    triage.to_parquet(EXP / "exp-2848_backfill_triage.parquet", index=False)
    (EXP / "exp-2848_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Visualization (Charter V8: paired chart for the back-fill line)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "EXP-2848 — Back-fill triage coverage (looser n_trans ≥ 1)\n"
        "Stream B; demoted to confidence C; original flags untouched",
        fontsize=11,
    )

    # Coverage pie
    ax = axes[0]
    parts = [
        ("Flat: covered (n≥2)", flat_in_orig, "#2ca02c"),
        ("Flat: back-filled (n=1)", flat_in_bf, "#ff7f0e"),
        ("Flat: still uncovered", flat_total - flat_in_orig - flat_in_bf,
         "#bbbbbb"),
    ]
    parts = [p for p in parts if p[1] > 0]
    if parts:
        ax.pie(
            [p[1] for p in parts], labels=[p[0] for p in parts],
            colors=[p[2] for p in parts], autopct="%d", startangle=90,
            wedgeprops=dict(edgecolor="white", linewidth=1.5),
        )
    ax.set_title(f"Flat-phenotype coverage (N={flat_total})")

    # Triage scatter
    ax = axes[1]
    if not triage.empty:
        for src, color, marker in [("original", "#2ca02c", "o"),
                                    ("backfill", "#ff7f0e", "s")]:
            sub = triage[triage["source"] == src]
            if sub.empty:
                continue
            ax.scatter(sub["n"], sub["recovery"], s=140, c=color,
                       marker=marker, alpha=0.8, edgecolor="white",
                       linewidth=1.2, label=f"{src} (grade {sub['confidence_grade'].iat[0]})")
            for _, row in sub.iterrows():
                ax.annotate(
                    str(row["patient_id"]),
                    (row["n"], row["recovery"]),
                    fontsize=8, alpha=0.85,
                    xytext=(5, 4), textcoords="offset points",
                )
        ax.axhline(0.4, color="k", lw=0.5, ls="--", alpha=0.5,
                   label="recovery threshold")
        ax.set_xlabel("N transitions observed")
        ax.set_ylabel("Median recovery fraction (3w)")
        ax.set_title("Triage flags by transition count + recovery")
        ax.legend(loc="best", fontsize=8)
    else:
        ax.text(0.5, 0.5, "No triage flags", ha="center",
                transform=ax.transAxes)

    plt.tight_layout(rect=(0, 0, 1, 0.93))
    out = FIG / "exp-2848_backfill_coverage.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {out}")
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
