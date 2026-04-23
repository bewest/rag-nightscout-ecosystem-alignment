"""EXP-2873 — Loop zero-variation re-test with relaxed coverage.

EXP-2872 found Loop has ZERO envelope-crossover phenotype variation
(all 6 patients = stream_B_normal). This is either:
  (a) A true algorithmic uniformity (Loop's PID/IMC structure
      produces a single envelope-coupling signature), or
  (b) An artifact of the contiguous-window filter:
      - cells_per_window * 0.8 fill rate
      - ≥6 non-overlapping windows
      - ≥3 elev / ≥3 norm tertile members

If we relax the criteria and (a) the same 6 Loop patients still all
classify as stream_B_normal, the algorithmic-uniformity finding is
robust. If (b) more Loop patients enter the cohort with varied
phenotypes, the prior finding was sample-bias.

Method: parameterize EXP-2851 thresholds, re-run with
  - fill fraction 0.6 (was 0.8)
  - min_windows = 4 (was 6)
  - min_tertile = 2 (was 3)
Then re-classify with EXP-2870 logic and compare Loop phenotype
counts and patient set baseline vs relaxed.

Output:
  externals/experiments/exp-2873_relaxed_envelope.parquet
  externals/experiments/exp-2873_summary.json
  docs/60-research/figures/exp-2873_loop_variation.png
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


def aggregate(g_pat: pd.DataFrame, window_h: int, fill_frac: float,
              min_windows: int) -> pd.DataFrame:
    cells = window_h * 12
    if len(g_pat) < cells * min_windows:
        return pd.DataFrame()
    g_pat = g_pat.sort_values("time").reset_index(drop=True)
    g_pat["window_id"] = g_pat.index // cells
    agg = (g_pat.groupby("window_id")
           .agg(n=("glucose", "size"),
                glucose=("glucose", "mean"),
                actual_basal=("actual_basal_rate", "mean"))
           .reset_index())
    return agg[agg["n"] >= cells * fill_frac].reset_index(drop=True)


def per_patient_signal(g_pat: pd.DataFrame, window_h: int,
                       fill_frac: float, min_windows: int,
                       min_tertile: int) -> dict | None:
    agg = aggregate(g_pat, window_h, fill_frac, min_windows)
    if agg.empty:
        return None
    agg = agg.dropna(subset=["glucose", "actual_basal"])
    if len(agg) < min_windows:
        return None
    q33, q67 = np.percentile(agg["glucose"], [33, 67])
    elev = agg[agg["glucose"] >= q67]
    norm = agg[agg["glucose"] <= q33]
    if len(elev) < min_tertile or len(norm) < min_tertile:
        return None
    bn = float(norm["actual_basal"].mean())
    if bn <= 0:
        return None
    be = float(elev["actual_basal"].mean())
    shift_pct = 100 * (be - bn) / bn
    try:
        _, p = stats.mannwhitneyu(elev["actual_basal"].dropna(),
                                  norm["actual_basal"].dropna(),
                                  alternative="two-sided")
    except ValueError:
        p = np.nan
    return dict(window_h=window_h, n_windows=int(len(agg)),
                basal_shift_pct=shift_pct,
                mannwhitney_p=float(p) if not np.isnan(p) else None)


def crossover(g: pd.DataFrame) -> dict:
    g = g.sort_values("window_h").reset_index(drop=True)
    co = None
    for _, r in g.iterrows():
        if r["basal_shift_pct"] >= 0:
            co = int(r["window_h"]); break
    return dict(patient_id=g["patient_id"].iloc[0],
                crossover_h=co,
                n_windows_observed=int(len(g)),
                max_window_observed=int(g["window_h"].max()),
                min_shift_pct=float(g["basal_shift_pct"].min()),
                max_shift_pct=float(g["basal_shift_pct"].max()),
                shift_at_max_window=float(
                    g.loc[g["window_h"].idxmax(), "basal_shift_pct"]))


def classify(row: dict) -> str:
    co = row["crossover_h"]
    last = row["shift_at_max_window"]
    never = co is None or (isinstance(co, float) and np.isnan(co))
    if never and last < 0:
        return "stream_A_dominant"
    if never:
        return "ambiguous"
    co = int(co)
    if co <= 6:
        return "stream_B_early"
    if co <= 24:
        return "stream_B_normal"
    return "stream_B_late"


def run_pass(g: pd.DataFrame, fill_frac: float, min_windows: int,
             min_tertile: int, label: str) -> pd.DataFrame:
    rows = []
    for pid, gp in g.groupby("patient_id"):
        for w in WINDOWS_HOURS:
            r = per_patient_signal(gp, w, fill_frac, min_windows, min_tertile)
            if r is None:
                continue
            r["patient_id"] = pid
            rows.append(r)
    sh = pd.DataFrame(rows)
    if sh.empty:
        return pd.DataFrame()
    cdf = pd.DataFrame([crossover(g) for _, g in sh.groupby("patient_id")])
    cdf["phenotype"] = cdf.apply(classify, axis=1)
    cdf["pass"] = label
    return cdf


def main() -> None:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)

    base = run_pass(g, 0.8, 6, 3, "baseline")
    relax = run_pass(g, 0.6, 4, 2, "relaxed")
    print(f"Baseline qualifying patients: {len(base)}")
    print(f"Relaxed qualifying patients: {len(relax)}")

    tx = pd.read_parquet(EXP / "exp-2812_pre_post_transitions.parquet",
                         columns=["patient_id", "controller"])
    cmap = tx.drop_duplicates("patient_id").set_index("patient_id")["controller"]
    base["controller"] = base["patient_id"].map(cmap)
    relax["controller"] = relax["patient_id"].map(cmap)

    print("\nBaseline phenotype × controller:")
    print(pd.crosstab(base["phenotype"], base["controller"], dropna=False))
    print("\nRelaxed phenotype × controller:")
    print(pd.crosstab(relax["phenotype"], relax["controller"], dropna=False))

    # Loop-specific deep dive
    base_loop = base[base["controller"] == "Loop"]
    relax_loop = relax[relax["controller"] == "Loop"]

    new_loop = set(relax_loop["patient_id"]) - set(base_loop["patient_id"])
    lost_loop = set(base_loop["patient_id"]) - set(relax_loop["patient_id"])

    print(f"\nLoop baseline: {len(base_loop)} patients, "
          f"phenotypes: {base_loop['phenotype'].value_counts().to_dict()}")
    print(f"Loop relaxed:  {len(relax_loop)} patients, "
          f"phenotypes: {relax_loop['phenotype'].value_counts().to_dict()}")
    print(f"Newly qualifying Loop patients: {len(new_loop)} {sorted(new_loop)}")
    if lost_loop:
        print(f"Loop patients dropped (relaxed shouldn't lose any): {lost_loop}")

    new_pheno = relax_loop[relax_loop["patient_id"].isin(new_loop)]
    if not new_pheno.empty:
        print("\nNewly-qualifying Loop patient phenotypes:")
        print(new_pheno[["patient_id", "phenotype",
                         "crossover_h", "shift_at_max_window"]].to_string(index=False))

    # Combine for output
    both = pd.concat([base, relax], ignore_index=True)
    both.to_parquet(EXP / "exp-2873_relaxed_envelope.parquet", index=False)

    summary = {
        "experiment": "EXP-2873",
        "title": "Loop zero-variation re-test with relaxed envelope coverage",
        "criteria": {
            "baseline": {"fill_frac": 0.8, "min_windows": 6, "min_tertile": 3},
            "relaxed": {"fill_frac": 0.6, "min_windows": 4, "min_tertile": 2},
        },
        "loop_baseline": {
            "n": int(len(base_loop)),
            "phenotypes": base_loop["phenotype"].value_counts().to_dict(),
        },
        "loop_relaxed": {
            "n": int(len(relax_loop)),
            "phenotypes": relax_loop["phenotype"].value_counts().to_dict(),
            "newly_qualifying": sorted(new_loop),
            "newly_qualifying_phenotypes": new_pheno[
                "phenotype"].value_counts().to_dict() if not new_pheno.empty else {},
        },
        "phenotype_x_controller": {
            "baseline": pd.crosstab(base["phenotype"],
                                    base["controller"]).to_dict(),
            "relaxed": pd.crosstab(relax["phenotype"],
                                   relax["controller"]).to_dict(),
        },
    }

    # Verdict
    relax_loop_uniq = relax_loop["phenotype"].nunique()
    if len(relax_loop) > len(base_loop) and relax_loop_uniq == 1:
        verdict = (f"ROBUST: relaxed criteria added "
                   f"{len(relax_loop) - len(base_loop)} Loop patients but "
                   f"all still classify as the same phenotype "
                   f"({relax_loop['phenotype'].iloc[0]}). "
                   "Loop algorithmic uniformity is supported.")
    elif relax_loop_uniq > 1:
        verdict = (f"NOT ROBUST: relaxed criteria reveals "
                   f"{relax_loop_uniq} phenotypes within Loop "
                   f"({relax_loop['phenotype'].value_counts().to_dict()}). "
                   "Prior 'zero variation' was a sample-size artifact.")
    elif len(relax_loop) == len(base_loop):
        verdict = ("INCONCLUSIVE: relaxation added no new Loop patients. "
                   "Cannot distinguish artifact from true uniformity.")
    else:
        verdict = "OTHER — see detailed counts."
    summary["verdict"] = verdict
    print(f"\nVERDICT: {verdict}")

    (EXP / "exp-2873_summary.json").write_text(
        json.dumps(summary, indent=2, default=str))

    # ---- Figure ----
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("EXP-2873 — Loop zero-variation re-test "
                 "with relaxed envelope coverage", fontsize=11)
    pheno_order = ["stream_A_dominant", "stream_B_late",
                   "stream_B_normal", "stream_B_early", "ambiguous"]

    for ax, df_, label in [(axes[0], base, "baseline (fill≥0.8, ≥6w, tert≥3)"),
                           (axes[1], relax, "relaxed (fill≥0.6, ≥4w, tert≥2)")]:
        ct = pd.crosstab(df_["phenotype"], df_["controller"], dropna=False)
        ct = ct.reindex([p for p in pheno_order if p in ct.index])
        ct.plot(kind="bar", stacked=True, ax=ax,
                color=[{"Loop": "#1f77b4", "Trio": "#d62728",
                        "OpenAPS": "#2ca02c"}.get(c, "#888888")
                       for c in ct.columns])
        ax.set_title(label, fontsize=10)
        ax.set_ylabel("patients")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(alpha=0.3)
    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2873_loop_variation.png", dpi=120)
    plt.close()


if __name__ == "__main__":
    main()
