"""EXP-2850 — Reactive- vs Structural-dominant cluster characterization.

Cross-tab the EXP-2849 sign-consistent vs sign-crossing patients
against:
  - controller (Loop / Trio / OpenAPS)
  - SMB capability (smb_share_s1 > 0.05)
  - phenotype (down/flat/up)
  - 48h basal-shift magnitude

Goal (Stream B): determine whether sign-consistency is a candidate
5th audition factor (predictable across timescales) or just noise.

Charter B compliant. No biology claim. Sign-consistency describes
how the controller's measured response covaries with glucose across
operational timescales.
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
    piv = pd.read_parquet(EXPDIR / "exp-2849_per_patient_pivot.parquet")
    rt = pd.read_parquet(EXPDIR / "exp-2845_per_patient_route.parquet")
    ph = pd.read_parquet(EXPDIR / "exp-2844_phenotype_table.parquet")

    # sign consistency: across all available windows, with >=2 windows
    def consistency(row: pd.Series) -> dict:
        v = row.dropna()
        if len(v) < 2:
            return {"n_wins": int(len(v)), "consist": None, "signs": ""}
        signs = np.sign(v).astype(int)
        return {
            "n_wins": int(len(v)),
            "consist": bool((signs == signs.iloc[0]).all() and (signs != 0).all()),
            "signs": "".join("+" if s > 0 else "-" if s < 0 else "0" for s in signs),
            "mean_pct": float(v.mean()),
            "abs_mag": float(v.abs().mean()),
        }

    rows = piv.apply(consistency, axis=1).tolist()
    consist = pd.DataFrame(rows, index=piv.index).reset_index()

    # Merge controller + phenotype + SMB share
    rt_slim = rt[["patient_id", "controller", "phenotype", "smb_share_s1"]]
    ph_slim = ph[["patient_id", "median_recovery_fraction", "wear_delta_pct"]]
    merged = (
        consist.merge(rt_slim, on="patient_id", how="left")
               .merge(ph_slim, on="patient_id", how="left")
    )
    merged["smb_capable"] = merged["smb_share_s1"].fillna(0) > 0.05

    out_parquet = EXPDIR / "exp-2850_cluster_characterization.parquet"
    merged.to_parquet(out_parquet, index=False)

    # Cross-tabs (only over patients with consist != None)
    elig = merged[merged["consist"].notna()].copy()

    by_controller = elig.groupby("controller")["consist"].agg(["count", "sum", "mean"])
    by_phenotype = elig.groupby("phenotype")["consist"].agg(["count", "sum", "mean"])
    by_smb = elig.groupby("smb_capable")["consist"].agg(["count", "sum", "mean"])

    # 4-window sub-cohort (most informative)
    four = elig[elig["n_wins"] == 4]
    four_consist = four[four["consist"]]
    four_cross = four[~four["consist"]]

    summary = {
        "exp": "EXP-2850",
        "method": "Cross-tab EXP-2849 sign-consistency vs controller / phenotype / SMB-capable",
        "n_total": int(len(merged)),
        "n_eligible": int(len(elig)),
        "n_with_4_windows": int(len(four)),
        "by_controller": by_controller.reset_index().to_dict(orient="records"),
        "by_phenotype": by_phenotype.reset_index().to_dict(orient="records"),
        "by_smb_capable": by_smb.reset_index().to_dict(orient="records"),
        "four_window_consistent_patients": four_consist[
            ["patient_id", "controller", "phenotype", "smb_capable", "signs", "mean_pct"]
        ].to_dict(orient="records"),
        "four_window_crossing_patients": four_cross[
            ["patient_id", "controller", "phenotype", "smb_capable", "signs", "mean_pct"]
        ].to_dict(orient="records"),
    }

    # Decision: is sign-consistency a useful audition factor?
    # Heuristic: needs to differ by >=20pp across at least one of
    # controller / phenotype / smb_capable to be worth productionizing.
    diffs = []
    for grp_name, grp_df in (
        ("controller", by_controller),
        ("phenotype", by_phenotype),
        ("smb_capable", by_smb),
    ):
        if len(grp_df) >= 2:
            spread = float(grp_df["mean"].max() - grp_df["mean"].min())
            diffs.append((grp_name, spread))
    summary["max_factor_spreads"] = {n: s for n, s in diffs}
    summary["audition_factor_candidate"] = bool(any(s >= 0.20 for _, s in diffs))

    out_json = EXPDIR / "exp-2850_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))

    # Visualization
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

        for ax, (label, df) in zip(
            axes,
            [("controller", by_controller),
             ("phenotype", by_phenotype),
             ("smb_capable", by_smb)],
        ):
            df = df.dropna()
            xs = [str(x) for x in df.index]
            ax.bar(xs, df["mean"].values, color="#4472C4", edgecolor="black")
            for i, (frac, n) in enumerate(zip(df["mean"], df["count"])):
                ax.text(i, frac + 0.02, f"{frac*100:.0f}%\nn={int(n)}",
                        ha="center", fontsize=9)
            ax.set_ylim(0, 1.15)
            ax.set_ylabel("Fraction sign-consistent")
            ax.set_title(f"By {label}")
            ax.axhline(0.76, color="gray", linestyle="--", alpha=0.5, label="cohort baseline 76%")
            ax.legend(fontsize=8)

        fig.suptitle(
            "EXP-2850: sign-consistency cross-tabs (cohort baseline = 19/25 = 76%)",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2850_cluster_characterization.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
