"""EXP-2877 — Counter-regulation dose-response vs hypo nadir depth.

Hypothesis:
  If the +1.42 mg/dL/min intercept from EXP-2875 reflects real hepatic
  glucagon counter-regulation, the residual rise rate should scale
  monotonically with hypo nadir depth. Deeper hypos (BG<55) trigger
  stronger counter-regulatory hormone cascades than mild hypos (BG 65-69).

  If intercept is FLAT across nadir strata, EXP-2875 is more likely a
  model-misspecification artifact (missing IOB decay kernel terms,
  non-linear basal-gap effects, etc.).

Method:
  - Reload EXP-2875 rescue-free events.
  - Bin by nadir depth: severe (<55), moderate (55-59), mild (60-64),
    borderline (65-69).
  - For each bin: compute cohort-level median rise_rate, median IOB at
    nadir, fit pooled regression (rise_rate ~ iob_nadir + basal_gap),
    extract intercept.
  - Also: per-patient regression including nadir_depth as a predictor.
    β_nadir < 0 (lower nadir → faster rise) supports dose-response.
  - Test monotonicity of intercept vs bin center via Spearman ρ.

Stream B — observed behavior. Dose-response is a physiology prediction.

Output:
  externals/experiments/exp-2877_nadir_strata.parquet
  externals/experiments/exp-2877_per_patient.parquet
  externals/experiments/exp-2877_summary.json
  docs/60-research/figures/exp-2877_dose_response.png
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

NADIR_BINS = [
    ("severe",     0,    55),
    ("moderate",  55,    60),
    ("mild",      60,    65),
    ("borderline", 65,   70),
]

MIN_EVENTS_PER_BIN = 20       # cohort-level minimum per stratum
MIN_EVENTS_PER_PATIENT = 10   # per-patient 4-predictor regression


def _bin_label(bg: float) -> str:
    for name, lo, hi in NADIR_BINS:
        if lo <= bg < hi:
            return name
    return "out_of_range"


def stratum_regression(df: pd.DataFrame) -> dict | None:
    sub = df.dropna(subset=["rise_rate", "iob_nadir", "basal_gap"])
    if len(sub) < MIN_EVENTS_PER_BIN:
        return None
    y = sub["rise_rate"].to_numpy()
    X = np.column_stack([
        np.ones(len(sub)),
        sub["iob_nadir"].to_numpy(),
        sub["basal_gap"].to_numpy(),
    ])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    intercept, b_iob, b_basal = coef
    yhat = X @ coef
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return dict(
        n_events=int(len(sub)),
        intercept=float(intercept),
        beta_iob=float(b_iob),
        beta_basal=float(b_basal),
        r2=float(r2),
        median_rise_rate=float(np.median(y)),
        median_nadir=float(sub["bg_nadir"].median()),
        median_iob_nadir=float(np.median(sub["iob_nadir"])),
    )


def per_patient_with_nadir(events: pd.DataFrame) -> dict | None:
    """Fit rise_rate ~ iob_nadir + basal_gap + nadir_depth per patient.

    nadir_depth = 70 - bg_nadir (positive; larger = deeper hypo).
    β_nadir > 0 supports dose-response (deeper → faster rise).
    """
    df = events.dropna(subset=["rise_rate", "iob_nadir", "basal_gap",
                               "bg_nadir"])
    if len(df) < MIN_EVENTS_PER_PATIENT:
        return None
    nadir_depth = 70.0 - df["bg_nadir"].to_numpy()
    y = df["rise_rate"].to_numpy()
    X = np.column_stack([
        np.ones(len(df)),
        df["iob_nadir"].to_numpy(),
        df["basal_gap"].to_numpy(),
        nadir_depth,
    ])
    try:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    intercept, b_iob, b_basal, b_nadir = coef
    yhat = X @ coef
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return dict(
        n_events=int(len(df)),
        intercept=float(intercept),
        beta_iob=float(b_iob),
        beta_basal=float(b_basal),
        beta_nadir=float(b_nadir),
        r2=float(r2),
    )


def main() -> None:
    ev = pd.read_parquet(EXP / "exp-2875_counter_regulation_events.parquet")
    print(f"Loaded {len(ev)} rescue-free events")

    ev["nadir_stratum"] = ev["bg_nadir"].apply(_bin_label)
    strata_counts = ev["nadir_stratum"].value_counts()
    print("\nStratum counts:")
    print(strata_counts.to_string())

    strata = []
    for name, lo, hi in NADIR_BINS:
        sub = ev[ev["nadir_stratum"] == name]
        r = stratum_regression(sub)
        if r is None:
            continue
        r["stratum"] = name
        r["bin_center"] = (lo + hi) / 2.0
        strata.append(r)
    strata_df = pd.DataFrame(strata)
    print("\nCohort-level stratum regressions:")
    if not strata_df.empty:
        print(strata_df[["stratum", "bin_center", "n_events", "intercept",
                         "beta_iob", "beta_basal", "r2", "median_rise_rate"]]
              .to_string(index=False))

    strata_df.to_parquet(EXP / "exp-2877_nadir_strata.parquet", index=False)

    # Per-patient 4-predictor regression with nadir_depth
    per_pat = []
    for pid, g in ev.groupby("patient_id"):
        res = per_patient_with_nadir(g)
        if res is None:
            continue
        res["patient_id"] = pid
        res["controller"] = g["controller"].iloc[0] if "controller" in g else "unknown"
        per_pat.append(res)
    pp_df = pd.DataFrame(per_pat)
    pp_df.to_parquet(EXP / "exp-2877_per_patient.parquet", index=False)

    print(f"\nPer-patient 4-predictor fits: {len(pp_df)}")
    if not pp_df.empty:
        print(pp_df[["patient_id", "controller", "n_events", "intercept",
                     "beta_iob", "beta_basal", "beta_nadir", "r2"]]
              .to_string(index=False))

    # Monotonicity test on strata
    summary = {
        "experiment": "EXP-2877",
        "title": "Counter-regulation dose-response vs nadir depth",
        "stream": "B",
        "bins": [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in NADIR_BINS],
    }

    if not strata_df.empty and len(strata_df) >= 3:
        rho, pval = stats.spearmanr(strata_df["bin_center"],
                                    strata_df["intercept"])
        # Deeper nadirs = lower bin_center. Dose-response predicts
        # NEGATIVE correlation between bin_center and intercept
        # (deeper → higher intercept).
        summary["stratum_spearman_rho"] = float(rho)
        summary["stratum_spearman_p"] = float(pval)
        summary["stratum_intercepts"] = dict(
            zip(strata_df["stratum"], strata_df["intercept"].round(3))
        )
        summary["stratum_median_rise"] = dict(
            zip(strata_df["stratum"], strata_df["median_rise_rate"].round(3))
        )

    if not pp_df.empty:
        betas = pp_df["beta_nadir"].dropna().to_numpy()
        if len(betas) > 0:
            summary["per_patient_beta_nadir_median"] = float(np.median(betas))
            summary["per_patient_beta_nadir_iqr"] = [
                float(np.percentile(betas, 25)),
                float(np.percentile(betas, 75)),
            ]
            summary["frac_positive_beta_nadir"] = float(np.mean(betas > 0))
            summary["n_patients_fit"] = int(len(pp_df))

            # Wilcoxon signed-rank vs 0
            try:
                stat, p = stats.wilcoxon(betas)
                summary["wilcoxon_stat"] = float(stat)
                summary["wilcoxon_p"] = float(p)
            except ValueError:
                pass

    # Verdict
    rho = summary.get("stratum_spearman_rho", None)
    beta_med = summary.get("per_patient_beta_nadir_median", None)
    frac_pos = summary.get("frac_positive_beta_nadir", None)
    wil_p = summary.get("wilcoxon_p", None)

    if beta_med is not None and frac_pos is not None:
        mono_strong = (rho is not None and rho <= -0.8)
        wil_strong = (wil_p is not None and wil_p < 0.01)
        if (mono_strong and wil_strong and frac_pos >= 0.9) or (
            beta_med > 0.05 and frac_pos >= 0.7 and
            (wil_p is None or wil_p < 0.05)
        ):
            verdict = (
                f"DOSE-RESPONSE CONFIRMED — stratum Spearman ρ={rho:+.2f}, "
                f"Wilcoxon p={wil_p:.2g} on per-patient β_nadir "
                f"(median {beta_med:+.3f}, {frac_pos:.0%} positive). "
                "Deeper hypos trigger faster recovery rise, consistent "
                "with hepatic glucagon counter-regulation as real "
                "physiology (not a model artifact)."
            )
        elif beta_med > 0.02:
            verdict = (
                f"WEAK DOSE-RESPONSE — median β_nadir={beta_med:+.3f}; "
                f"{frac_pos:.0%} positive. Consistent with partial "
                "counter-reg but also consistent with IOB model "
                "misspecification at extremes."
            )
        elif abs(beta_med) <= 0.02:
            verdict = (
                "FLAT — counter-reg residual does NOT scale with nadir "
                "depth. Suggests EXP-2875 intercept may be a model "
                "artifact; revisit IOB decay kernel and basal-gap "
                "linearity assumptions."
            )
        else:
            verdict = (
                f"INVERTED — β_nadir={beta_med:+.3f} (deeper = slower rise); "
                "unexpected. Could reflect brain-glucose protection "
                "kinetics or sampling bias on severe events."
            )
    else:
        verdict = "INSUFFICIENT DATA"

    summary["verdict"] = verdict
    (EXP / "exp-2877_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Figure: strata intercept + per-patient β_nadir
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    if not strata_df.empty:
        colors = ["#b22222", "#d95f02", "#e6ab02", "#66a61e"]
        ax.bar(strata_df["stratum"], strata_df["intercept"],
               color=colors[:len(strata_df)], edgecolor="black")
        for i, (_, row) in enumerate(strata_df.iterrows()):
            ax.text(i, row["intercept"],
                    f"n={int(row['n_events'])}\n{row['intercept']:+.2f}",
                    ha="center", va="bottom", fontsize=9)
        ax.axhline(0, color="gray", ls=":", alpha=0.6)
        ax.set_ylabel("Cohort-pooled intercept (mg/dL/min)")
        ax.set_title("Counter-reg intercept by nadir stratum\n"
                     "Real physiology → monotonic rise with severity")
        ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    if not pp_df.empty:
        ax.hist(pp_df["beta_nadir"].dropna(), bins=15, color="#1f77b4",
                edgecolor="black")
        ax.axvline(0, color="red", ls="--", alpha=0.8, label="β=0")
        ax.axvline(pp_df["beta_nadir"].median(), color="green",
                   ls="-", alpha=0.8,
                   label=f"median={pp_df['beta_nadir'].median():.3f}")
        ax.set_xlabel("β_nadir (mg/dL/min per mg/dL deeper)")
        ax.set_ylabel("# patients")
        ax.set_title("Per-patient dose-response slope\n"
                     "β_nadir > 0 supports glucagon hypothesis")
        ax.legend()
        ax.grid(alpha=0.3, axis="y")

    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2877_dose_response.png", dpi=120)
    plt.close()

    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
