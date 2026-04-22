"""EXP-2860 — Cross-validate bootstrap Simpson against other audition signals.

Bootstrap P(simpson) from EXP-2859 sorts patients into 3 groups:
high-conf Simpson (P>=0.9), boundary (0.1<P<0.9), confidently clean
(P<=0.1). Test whether these groups differ on OTHER audition inputs:
  - phenotype (EXP-2845)
  - structural basal step (β_slow proxy: actual_basal_s1 - actual_basal_s0
    from EXP-2843)
  - SMB share (EXP-2845)
  - mean basal level (EXP-2853)

If groups differ on these features, Simpson is correlated with
existing signals (partial duplicate). If groups are indistinguishable,
Simpson is a genuinely orthogonal signal worth carrying.

Charter B compliant.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"


def main() -> None:
    boot = pd.read_parquet(EXPDIR / "exp-2859_bootstrap_simpson.parquet")
    decomp = pd.read_parquet(EXPDIR / "exp-2853_simpson_decomposition.parquet")
    state = pd.read_parquet(EXPDIR / "exp-2843_state_basal_coupling.parquet")
    route = pd.read_parquet(EXPDIR / "exp-2845_per_patient_route.parquet")

    # State-coupling features
    state["d_basal_state"] = state["actual_basal_s1"] - state["actual_basal_s0"]
    state["d_glucose_state"] = state["glucose_s1"] - state["glucose_s0"]

    df = (
        boot[["patient_id", "p_simpson", "beta_fast_mean", "beta_slow_mean",
              "point_simpson"]]
        .merge(decomp[["patient_id", "mean_basal_uph", "frac_variance_within_window"]],
               on="patient_id", how="left")
        .merge(state[["patient_id", "d_basal_state", "d_glucose_state",
                      "n_s0_cells", "n_s1_cells"]],
               on="patient_id", how="left")
        .merge(route[["patient_id", "phenotype", "d_basal_uph", "d_smb_uph",
                      "smb_share_s1"]],
               on="patient_id", how="left")
    )

    # Categorize
    df["band"] = pd.cut(
        df["p_simpson"],
        bins=[-0.001, 0.1, 0.9, 1.001],
        labels=["clean", "boundary", "simpson"],
    )

    summary = {
        "exp": "EXP-2860",
        "method": (
            "Cross-tab bootstrap-Simpson bands (clean P<=0.1, boundary "
            "0.1<P<0.9, simpson P>=0.9) against other audition signals "
            "(phenotype, state-basal step, SMB share, mean basal)."
        ),
        "n_patients_total": int(len(df)),
        "by_band": {},
    }
    for band, g in df.groupby("band"):
        summary["by_band"][str(band)] = {
            "n": int(len(g)),
            "phenotype_counts": (
                g["phenotype"].value_counts(dropna=False).to_dict()
                if "phenotype" in g and g["phenotype"].notna().any()
                else {}
            ),
            "median_mean_basal_uph": (
                float(g["mean_basal_uph"].median())
                if g["mean_basal_uph"].notna().any() else None
            ),
            "median_d_basal_state_uph": (
                float(g["d_basal_state"].median())
                if g["d_basal_state"].notna().any() else None
            ),
            "median_d_glucose_state_mgdl": (
                float(g["d_glucose_state"].median())
                if g["d_glucose_state"].notna().any() else None
            ),
            "median_smb_share_s1": (
                float(g["smb_share_s1"].median())
                if "smb_share_s1" in g and g["smb_share_s1"].notna().any() else None
            ),
            "median_frac_variance_within_window": (
                float(g["frac_variance_within_window"].median())
                if g["frac_variance_within_window"].notna().any() else None
            ),
        }

    # Mann-Whitney clean vs boundary+simpson where N permits
    try:
        from scipy import stats as sst
        clean = df[df["band"] == "clean"]
        flagged = df[df["band"].isin(["boundary", "simpson"])]
        mw = {}
        for feat in ["mean_basal_uph", "d_basal_state", "d_glucose_state",
                     "smb_share_s1", "frac_variance_within_window"]:
            a = clean[feat].dropna().to_numpy() if feat in clean else []
            b = flagged[feat].dropna().to_numpy() if feat in flagged else []
            if len(a) >= 4 and len(b) >= 4:
                u = sst.mannwhitneyu(a, b, alternative="two-sided")
                mw[feat] = {
                    "p": float(u.pvalue),
                    "n_clean": int(len(a)),
                    "n_flagged": int(len(b)),
                }
        summary["mannwhitney_clean_vs_flagged"] = mw
    except Exception as e:  # noqa: BLE001
        summary["mw_error"] = str(e)

    df.to_parquet(EXPDIR / "exp-2860_simpson_xref.parquet", index=False)
    (EXPDIR / "exp-2860_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # Visualization
    try:
        import matplotlib.pyplot as plt
        feats = [
            ("mean_basal_uph", "mean basal (U/hr)"),
            ("d_basal_state", "Δ basal S1−S0 (U/hr)"),
            ("d_glucose_state", "Δ glucose S1−S0 (mg/dL)"),
            ("smb_share_s1", "SMB share in S1"),
        ]
        fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
        bands = ["clean", "boundary", "simpson"]
        colors = {"clean": "#43AA8B", "boundary": "#F8961E", "simpson": "#F94144"}
        for ax, (feat, label) in zip(axes, feats):
            data = []
            labels = []
            for band in bands:
                vals = df.loc[df["band"] == band, feat].dropna()
                if len(vals) > 0:
                    data.append(vals)
                    labels.append(f"{band}\nn={len(vals)}")
            if data:
                bp = ax.boxplot(data, labels=labels, showfliers=False, patch_artist=True)
                for patch, band_label in zip(bp["boxes"], bands[: len(data)]):
                    patch.set_facecolor(colors[band_label])
                    patch.set_alpha(0.7)
            ax.set_ylabel(label)
            p = summary.get("mannwhitney_clean_vs_flagged", {}).get(feat, {}).get("p")
            if p is not None:
                ax.set_title(f"{label}\nclean vs flagged p={p:.3f}", fontsize=10)
            else:
                ax.set_title(label, fontsize=10)
        fig.suptitle(
            "EXP-2860: bootstrap Simpson bands vs other audition signals",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2860_simpson_xref.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
