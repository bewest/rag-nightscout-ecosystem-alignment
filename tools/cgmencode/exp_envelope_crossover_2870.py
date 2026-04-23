"""EXP-2870 — Envelope-coupling crossover per patient.

Builds on EXP-2851 finding (envelope→basal shift sign FLIPS between
12h and 24h cohort-wide). Question: does each patient have a
characteristic crossover window? Is the crossover hour itself a
phenotype that predicts audition signature?

Hypothesis:
  - Patients dominated by reactive intervention (controller suspends
    aggressively, e.g. patient C) stay NEGATIVE even at 48h —
    "Stream A dominant."
  - Patients with passive controllers / well-tuned settings cross to
    positive earlier (~12-24h) — "Stream B dominant."
  - Crossover hour correlates with audition flags (basal_mismatch,
    isf_over_correction).

Method:
  - For each patient × window, compute shift_pct (top vs bottom
    glucose tertile) on actual_basal_rate. Same as EXP-2849/2851.
  - Determine per-patient crossover: smallest window_h at which
    shift_pct >= 0. If never crosses → label "stream_A_dominant".
  - Cross-tab vs controller, vs audition flags (basal_mismatch P).
  - Cross-tab vs simple settings (median scheduled basal, TIR).

Output:
  externals/experiments/exp-2870_per_patient_crossover.parquet
  externals/experiments/exp-2870_summary.json
  docs/60-research/figures/exp-2870_crossover_phenotype.png

Charter: Stream B operational (envelope structure), no biological
claim. Uses EXP-2851's shift_pct directly — purely descriptive
phenotype derivation.
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

WINDOWS = [1, 2, 3, 6, 12, 24, 48]


def _load_shifts() -> pd.DataFrame:
    p = EXP / "exp-2851_fast_scale_envelope.parquet"
    if not p.exists():
        raise SystemExit("EXP-2851 artifact required; run exp_fast_scale_envelope_2851.py first")
    return pd.read_parquet(p)


def crossover_hour(g: pd.DataFrame) -> dict:
    """Per-patient: find smallest window where shift_pct >= 0."""
    g = g.sort_values("window_h").reset_index(drop=True)
    crossover = None
    for _, r in g.iterrows():
        if r["basal_shift_pct"] >= 0:
            crossover = int(r["window_h"])
            break
    return dict(
        patient_id=g["patient_id"].iloc[0],
        crossover_h=crossover,
        n_windows_observed=int(len(g)),
        max_window_observed=int(g["window_h"].max()),
        min_shift_pct=float(g["basal_shift_pct"].min()),
        max_shift_pct=float(g["basal_shift_pct"].max()),
        shift_at_max_window=float(
            g.loc[g["window_h"].idxmax(), "basal_shift_pct"]
        ),
    )


def classify(row: dict) -> str:
    """Phenotype from crossover hour."""
    co = row["crossover_h"]
    last_shift = row["shift_at_max_window"]
    # pandas converts None → NaN in numeric column; treat NaN as "never crossed"
    never_crossed = co is None or (isinstance(co, float) and np.isnan(co))
    if never_crossed and last_shift < 0:
        return "stream_A_dominant"  # never crosses, reactive-loop dominant
    if never_crossed:
        return "ambiguous"
    co = int(co)
    if co <= 6:
        return "stream_B_early"  # envelope dominates by 6h
    if co <= 24:
        return "stream_B_normal"  # envelope dominates by 24h
    return "stream_B_late"  # only at 48h


def main() -> None:
    sh = _load_shifts()
    print(f"Loaded {len(sh)} (patient × window) rows from EXP-2851")

    rows = [crossover_hour(g) for _, g in sh.groupby("patient_id")]
    cdf = pd.DataFrame(rows)
    cdf["phenotype"] = cdf.apply(classify, axis=1)

    print("\nCrossover hour distribution:")
    print(cdf["crossover_h"].fillna(-1).astype(int).value_counts().sort_index())

    print("\nPhenotype distribution:")
    print(cdf["phenotype"].value_counts())

    # ---- Cross-tab vs controller (pulled from EXP-2812 transitions) ----
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet",
                        columns=["patient_id",
                                 "scheduled_basal_rate", "glucose"])
    ctrl = (
        g.groupby("patient_id")
        .agg(
            median_sched_basal=("scheduled_basal_rate", "median"),
            tir=("glucose", lambda s: float(((s >= 70) & (s <= 180)).mean())),
            mean_glucose=("glucose", "mean"),
        )
        .reset_index()
    )
    # Best-effort controller from EXP-2812 transitions
    tx_path = EXP / "exp-2812_pre_post_transitions.parquet"
    if tx_path.exists():
        tx = pd.read_parquet(tx_path, columns=["patient_id", "controller"])
        ctrl_map = (tx.drop_duplicates("patient_id")
                    .set_index("patient_id")["controller"])
        ctrl["controller"] = ctrl["patient_id"].map(ctrl_map)
    cdf = cdf.merge(ctrl, on="patient_id", how="left")

    # ---- Cross-tab vs basal_mismatch audition signal ----
    bm_path = EXP / "exp-2869_per_patient_summary.parquet"
    if not bm_path.exists():
        bm_path = EXP / "exp-2865_per_patient_summary.parquet"
    if bm_path.exists():
        bm = pd.read_parquet(bm_path)
        # Best-effort: pick whichever column carries the per-patient max p
        for col in ("max_mismatch_p", "p_basal_mismatch", "p_high_mismatch"):
            if col in bm.columns:
                cdf = cdf.merge(
                    bm[["patient_id", col]].rename(
                        columns={col: "basal_mismatch_p"}
                    ),
                    on="patient_id", how="left",
                )
                break

    cdf.to_parquet(EXP / "exp-2870_per_patient_crossover.parquet", index=False)

    # ---- Phenotype × controller ----
    if "controller" in cdf.columns:
        ct = pd.crosstab(cdf["phenotype"], cdf["controller"])
        print("\nPhenotype × controller:")
        print(ct)

    # ---- Phenotype median basal & TIR ----
    pheno_summary = (
        cdf.groupby("phenotype")
        .agg(
            n=("patient_id", "size"),
            median_sched_basal=("median_sched_basal", "median"),
            median_tir=("tir", "median"),
            median_mean_glucose=("mean_glucose", "median"),
        )
        .reset_index()
    )
    print("\nPhenotype × settings:")
    print(pheno_summary.to_string(index=False))

    summary = {
        "experiment": "EXP-2870",
        "title": "Per-patient envelope crossover phenotype",
        "stream": "B",
        "n_patients": int(len(cdf)),
        "phenotype_counts": cdf["phenotype"].value_counts().to_dict(),
        "phenotype_settings": pheno_summary.to_dict(orient="records"),
        "checks": {
            "PASS_phenotype_diverse": cdf["phenotype"].nunique() >= 3,
            "PASS_stream_A_minority": (
                int((cdf["phenotype"] == "stream_A_dominant").sum())
                < int(len(cdf) * 0.5)
            ),
            "PASS_stream_A_lower_tir": (
                cdf.loc[cdf["phenotype"] == "stream_A_dominant", "tir"].median()
                < cdf.loc[cdf["phenotype"].str.startswith("stream_B"), "tir"].median()
                if (cdf["phenotype"] == "stream_A_dominant").any()
                and cdf["phenotype"].str.startswith("stream_B").any()
                else False
            ),
        },
    }
    summary["checks_passed"] = sum(summary["checks"].values())

    if summary["checks"]["PASS_stream_A_lower_tir"]:
        interp = ("Stream-A-dominant patients (envelope shift never crosses to "
                  "positive) have lower TIR than Stream-B patients. The "
                  "crossover hour is a phenotype that predicts therapy quality.")
    else:
        interp = ("Crossover hour does not cleanly stratify TIR. Phenotype "
                  "may still be useful for audition-window personalization "
                  "but does not reduce to a single-axis quality marker.")
    summary["interpretation"] = interp

    (EXP / "exp-2870_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # ---- Figure ----
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("EXP-2870 — Per-patient envelope crossover phenotype",
                 fontsize=12)

    ax = axes[0]
    pheno_order = ["stream_A_dominant", "stream_B_late",
                   "stream_B_normal", "stream_B_early", "ambiguous"]
    pheno_present = [p for p in pheno_order if p in cdf["phenotype"].values]
    counts = [int((cdf["phenotype"] == p).sum()) for p in pheno_present]
    ax.barh(pheno_present, counts, color=["#d62728", "#ff7f0e",
                                          "#2ca02c", "#1f77b4", "#888"][:len(pheno_present)])
    ax.set_xlabel("N patients")
    ax.set_title("Phenotype distribution")

    ax = axes[1]
    if "tir" in cdf.columns and pheno_present:
        data = [cdf.loc[cdf["phenotype"] == p, "tir"].dropna().values
                for p in pheno_present]
        bp = ax.boxplot(data, labels=pheno_present, showmeans=True)
        ax.set_ylabel("TIR (70-180)")
        ax.set_title("TIR by phenotype")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(alpha=0.3)

    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2870_crossover_phenotype.png", dpi=120)
    plt.close()

    print(f"\nChecks passed: {summary['checks_passed']}/3")
    print(f"Interpretation: {summary['interpretation']}")


if __name__ == "__main__":
    main()
