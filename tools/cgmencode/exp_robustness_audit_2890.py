"""EXP-2890 - Robustness audit of the EXP-2889 braking_ratio signal.

Before wiring braking_ratio into production/audition_matrix.py we
need to confirm the rho=-0.711 finding against cf_severe is robust
to:

  1. ISF choice (currently ISF_pop=50 mg/dL/U uniform).
     Sweep ISF in {30, 40, 50, 60, 70, 100} and see if rank-order
     and significance survive.

  2. Sampling (n=19 is small).  Bootstrap patients with replacement,
     recompute rho, report 95% CI.  If CI crosses 0, downgrade.

  3. Heterogeneous ISF per known patient.  Use profile ISF for
     a-k patients (EXP-2001), ISF_pop for the rest (ns-*), and
     re-test.  If per-patient ISF changes rank-order of cf_severe,
     the uniform ISF finding may be an artefact.

  4. Event-weighted vs patient-weighted pooling.  EXP-2889 computed
     per-patient cf_severe first then correlated; also test the
     event-weighted version as a check for Simpson-reversal.

  5. Exclude high-deficit outliers (> 99th pct basal_deficit * duration).
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

OUT = Path("externals/experiments")
FIGS = Path("docs/60-research/figures")
FIGS.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(42)


def compute_cf(events: pd.DataFrame, isf: float) -> pd.DataFrame:
    df = events.copy()
    df["extra_drop"] = df["basal_deficit_uh"] * df["duration_min"] / 60 * isf
    df["cf_nadir"] = df["bg_nadir"] - df["extra_drop"]
    df["cf_severe"] = (df["cf_nadir"] < 54).astype(int)
    return df


def per_patient_agg(events: pd.DataFrame) -> pd.DataFrame:
    return (events.groupby("patient_id")
                  .agg(cf_severe=("cf_severe", "mean"),
                       n=("cf_severe", "size"))
                  .reset_index())


def main() -> None:
    ev = pd.read_parquet(OUT / "exp-2889_event_replay.parquet")
    pheno = pd.read_parquet(OUT / "exp-2886_phenotype.parquet")[
        ["patient_id", "braking_ratio", "stack_score",
         "counter_reg_intercept", "hidden_leverage",
         "controller", "lineage"]]

    base_cols = ["patient_id", "bg_nadir", "basal_deficit_uh",
                 "duration_min"]
    ev = ev[base_cols].copy()

    # --------------------------------------------------------------
    # 1. ISF sweep
    # --------------------------------------------------------------
    isf_sweep = []
    for isf in [30, 40, 50, 60, 70, 100]:
        cf = compute_cf(ev, isf)
        pp = per_patient_agg(cf).merge(pheno, on="patient_id")
        pp = pp.dropna(subset=["braking_ratio", "cf_severe"])
        r, p = stats.spearmanr(pp["braking_ratio"], pp["cf_severe"])
        pop_mean_cf = float(cf["cf_severe"].mean())
        isf_sweep.append({
            "isf": isf, "rho": float(r), "p": float(p),
            "n": int(len(pp)), "pop_mean_cf_severe": pop_mean_cf,
        })
        print(f"  ISF={isf:3d}  rho={r:+.3f}  p={p:.4f}  "
              f"pop cf_severe={pop_mean_cf:.1%}")

    # --------------------------------------------------------------
    # 2. Bootstrap CI on primary finding (ISF=50)
    # --------------------------------------------------------------
    cf50 = compute_cf(ev, 50)
    pp50 = per_patient_agg(cf50).merge(pheno, on="patient_id")
    pp50 = pp50.dropna(subset=["braking_ratio", "cf_severe"])
    boot_rhos = []
    for _ in range(5000):
        idx = RNG.choice(len(pp50), len(pp50), replace=True)
        sample = pp50.iloc[idx]
        if sample["braking_ratio"].std() == 0 or sample["cf_severe"].std() == 0:
            continue
        r, _ = stats.spearmanr(sample["braking_ratio"],
                               sample["cf_severe"])
        if not np.isnan(r):
            boot_rhos.append(r)
    boot_rhos = np.array(boot_rhos)
    ci_lo, ci_hi = np.percentile(boot_rhos, [2.5, 97.5])
    boot_result = {
        "n_boots": int(len(boot_rhos)),
        "mean": float(boot_rhos.mean()),
        "median": float(np.median(boot_rhos)),
        "ci_lo": float(ci_lo),
        "ci_hi": float(ci_hi),
        "p_gt_zero": float((boot_rhos > 0).mean()),
        "crosses_zero": bool(ci_lo < 0 < ci_hi),
    }
    print(f"\nBootstrap rho  mean={boot_result['mean']:+.3f}  "
          f"95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}]  "
          f"crosses0={boot_result['crosses_zero']}")

    # --------------------------------------------------------------
    # 3. Per-patient ISF where available
    # --------------------------------------------------------------
    try:
        therapy = json.loads(
            Path("externals/experiments/exp-2001_therapy_profiles.json")
            .read_text())
        isf_map = {pid: v.get("effective_isf_median", 50)
                   for pid, v in therapy["exp2002_isf"].items()}
    except Exception:
        isf_map = {}

    per_pt = ev.copy()
    per_pt["isf"] = per_pt["patient_id"].map(isf_map).fillna(50.0)
    per_pt["extra_drop"] = (per_pt["basal_deficit_uh"]
                            * per_pt["duration_min"] / 60
                            * per_pt["isf"])
    per_pt["cf_nadir"] = per_pt["bg_nadir"] - per_pt["extra_drop"]
    per_pt["cf_severe"] = (per_pt["cf_nadir"] < 54).astype(int)
    ppp = per_patient_agg(per_pt).merge(pheno, on="patient_id")
    ppp = ppp.dropna(subset=["braking_ratio", "cf_severe"])
    r_pp, p_pp = stats.spearmanr(ppp["braking_ratio"], ppp["cf_severe"])
    patients_with_profile = sum(1 for pid in ppp["patient_id"]
                                if pid in isf_map)
    print(f"\nPer-patient ISF (n={len(ppp)}, profile-known="
          f"{patients_with_profile}):  rho={r_pp:+.3f}  p={p_pp:.4f}")

    # --------------------------------------------------------------
    # 4. Event-weighted version (Simpson reversal check)
    # --------------------------------------------------------------
    ev_weighted = cf50.merge(
        pheno[["patient_id", "braking_ratio"]], on="patient_id")
    ev_weighted = ev_weighted.dropna(subset=["braking_ratio"])
    r_ev, p_ev = stats.spearmanr(ev_weighted["braking_ratio"],
                                 ev_weighted["cf_severe"])
    print(f"Event-weighted (n={len(ev_weighted)}): "
          f"rho={r_ev:+.3f}  p={p_ev:.4e}")

    # --------------------------------------------------------------
    # 5. Drop extreme deficits
    # --------------------------------------------------------------
    q99 = (cf50["basal_deficit_uh"] * cf50["duration_min"] / 60).quantile(0.99)
    trimmed_events = cf50[
        (cf50["basal_deficit_uh"] * cf50["duration_min"] / 60) <= q99
    ]
    pp_t = per_patient_agg(trimmed_events).merge(pheno, on="patient_id")
    pp_t = pp_t.dropna(subset=["braking_ratio", "cf_severe"])
    r_t, p_t = stats.spearmanr(pp_t["braking_ratio"], pp_t["cf_severe"])
    print(f"Trimmed (99th pct extra_insulin removed, n={len(pp_t)}): "
          f"rho={r_t:+.3f}  p={p_t:.4f}")

    # --------------------------------------------------------------
    # Figure
    # --------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    ax = axes[0]
    xs = [s["isf"] for s in isf_sweep]
    ys = [s["rho"] for s in isf_sweep]
    ps = [s["p"] for s in isf_sweep]
    colors = ["firebrick" if p_ < 0.05 else "gray" for p_ in ps]
    ax.bar(xs, ys, width=6, color=colors)
    for x, y, p_ in zip(xs, ys, ps):
        ax.text(x, y - 0.03, f"p={p_:.3f}",
                ha="center", fontsize=7)
    ax.set_xlabel("ISF assumption (mg/dL/U)")
    ax.set_ylabel("Spearman rho (brake x cf_severe)")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_title("ISF sensitivity")
    ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    ax.hist(boot_rhos, bins=40, color="steelblue", alpha=0.8)
    ax.axvline(0, color="k", lw=0.5)
    ax.axvline(ci_lo, color="firebrick", ls="--",
               label=f"95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}]")
    ax.axvline(ci_hi, color="firebrick", ls="--")
    ax.set_xlabel("bootstrap rho")
    ax.set_ylabel("count")
    ax.set_title(f"Bootstrap (5k) rho distribution")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    ax = axes[2]
    labels = ["ISF=50\npatient-wt",
              "ISF=50\nevent-wt",
              "per-pt ISF\n(partial)",
              "ISF=50\ntrimmed"]
    vals = [isf_sweep[2]["rho"], r_ev, r_pp, r_t]
    ps2 = [isf_sweep[2]["p"], p_ev, p_pp, p_t]
    colors2 = ["firebrick" if p_ < 0.05 else "gray" for p_ in ps2]
    ax.bar(labels, vals, color=colors2)
    for i, (v, p_) in enumerate(zip(vals, ps2)):
        ax.text(i, v + (0.02 if v >= 0 else -0.05),
                f"p={p_:.3f}", ha="center", fontsize=8)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("Spearman rho")
    ax.set_title("Weighting / ISF variants")
    ax.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    fig_path = FIGS / "exp-2890_robustness_audit.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)

    summary = {
        "exp": "EXP-2890",
        "purpose": "robustness audit of EXP-2889 braking_ratio finding",
        "isf_sweep": isf_sweep,
        "bootstrap": boot_result,
        "per_patient_isf": {
            "rho": float(r_pp), "p": float(p_pp),
            "n_total": int(len(ppp)),
            "n_profile_known": int(patients_with_profile),
        },
        "event_weighted": {
            "rho": float(r_ev), "p": float(p_ev),
            "n_events": int(len(ev_weighted)),
        },
        "trimmed_99pct": {
            "rho": float(r_t), "p": float(p_t),
            "n": int(len(pp_t)),
        },
        "figure": str(fig_path),
    }
    (OUT / "exp-2890_robustness_audit_summary.json").write_text(
        json.dumps(summary, indent=2))
    print(f"\nWrote {fig_path}")


if __name__ == "__main__":
    main()
