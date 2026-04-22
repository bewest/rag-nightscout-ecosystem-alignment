"""EXP-2858 — What drives Simpson flips?

Site-change detection (EXP-795) is too unreliable to cross-reference
(<15% detection rate). Instead, characterize what GLUCOSE/INSULIN
state changes accompany Simpson flips in unstable patients.

For each adjacent pair of rolling 30d windows from EXP-2856 where the
Simpson flag flips, compute deltas in:
  - mean glucose
  - glucose CV
  - mean basal
  - mean total insulin (TDD proxy via mean basal × 24)

Compare flip-pair deltas to no-flip-pair deltas. If a feature
discriminates, audition can use it as a "recompute Simpson" trigger.

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
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

WINDOW_DAYS = 30
STRIDE_DAYS = 15


def main() -> None:
    rolling = pd.read_parquet(EXPDIR / "exp-2856_rolling_simpson.parquet")
    cols = ["patient_id", "time", "glucose", "actual_basal_rate"]
    df = pd.read_parquet(GRID, columns=cols).dropna(
        subset=["glucose", "actual_basal_rate"]
    )
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values(["patient_id", "time"])

    # Per (patient, window) compute summary stats
    feat_rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        sub = rolling[rolling["patient_id"] == pid]
        if sub.empty:
            continue
        t0 = g["time"].min()
        for _, row in sub.iterrows():
            ws = t0 + pd.Timedelta(days=int(row["window_start_day"]))
            we = ws + pd.Timedelta(days=WINDOW_DAYS)
            w = g[(g["time"] >= ws) & (g["time"] < we)]
            if w.empty:
                continue
            mg = float(w["glucose"].mean())
            sg = float(w["glucose"].std())
            mb = float(w["actual_basal_rate"].mean())
            feat_rows.append({
                "patient_id": pid,
                "window_start_day": int(row["window_start_day"]),
                "simpson": bool(row["simpson"]),
                "mean_glucose": mg,
                "cv_glucose": sg / mg if mg > 0 else np.nan,
                "mean_basal": mb,
            })
    feats = pd.DataFrame(feat_rows)
    feats.to_parquet(EXPDIR / "exp-2858_window_features.parquet", index=False)

    # Build adjacent-window pairs per patient
    pairs = []
    for pid, sub in feats.sort_values(["patient_id", "window_start_day"]).groupby("patient_id"):
        sub = sub.reset_index(drop=True)
        for i in range(len(sub) - 1):
            a, b = sub.iloc[i], sub.iloc[i + 1]
            if int(b["window_start_day"]) - int(a["window_start_day"]) != STRIDE_DAYS:
                continue
            pairs.append({
                "patient_id": pid,
                "from_day": int(a["window_start_day"]),
                "flipped": bool(a["simpson"] != b["simpson"]),
                "d_mean_glucose": b["mean_glucose"] - a["mean_glucose"],
                "d_cv_glucose": b["cv_glucose"] - a["cv_glucose"],
                "d_mean_basal": b["mean_basal"] - a["mean_basal"],
                "abs_d_mean_glucose": abs(b["mean_glucose"] - a["mean_glucose"]),
                "abs_d_cv_glucose": abs(b["cv_glucose"] - a["cv_glucose"]),
                "abs_d_mean_basal": abs(b["mean_basal"] - a["mean_basal"]),
            })
    pdf = pd.DataFrame(pairs)
    pdf.to_parquet(EXPDIR / "exp-2858_pairs.parquet", index=False)

    flip = pdf[pdf["flipped"]]
    keep = pdf[~pdf["flipped"]]

    def _stats(s: pd.Series) -> dict:
        return {
            "n": int(s.notna().sum()),
            "median": float(s.median()) if s.notna().any() else None,
            "iqr": [
                float(s.quantile(0.25)) if s.notna().any() else None,
                float(s.quantile(0.75)) if s.notna().any() else None,
            ],
        }

    summary = {
        "exp": "EXP-2858",
        "method": (
            "Adjacent rolling-30d window pairs from EXP-2856; compare "
            "absolute deltas in mean glucose, glucose CV, and mean basal "
            "between flip pairs (Simpson change) and non-flip pairs."
        ),
        "n_pairs_total": int(len(pdf)),
        "n_flip_pairs": int(len(flip)),
        "n_keep_pairs": int(len(keep)),
        "frac_flip": float(len(flip) / len(pdf)) if len(pdf) else 0.0,
        "flip_pairs": {
            "abs_d_mean_glucose_mgdl": _stats(flip["abs_d_mean_glucose"]),
            "abs_d_cv_glucose": _stats(flip["abs_d_cv_glucose"]),
            "abs_d_mean_basal_Uhr": _stats(flip["abs_d_mean_basal"]),
        },
        "keep_pairs": {
            "abs_d_mean_glucose_mgdl": _stats(keep["abs_d_mean_glucose"]),
            "abs_d_cv_glucose": _stats(keep["abs_d_cv_glucose"]),
            "abs_d_mean_basal_Uhr": _stats(keep["abs_d_mean_basal"]),
        },
    }

    # Mann-Whitney for each feature
    try:
        from scipy import stats as sst
        for feat in ["abs_d_mean_glucose", "abs_d_cv_glucose", "abs_d_mean_basal"]:
            a = flip[feat].dropna().to_numpy()
            b = keep[feat].dropna().to_numpy()
            if len(a) > 3 and len(b) > 3:
                u = sst.mannwhitneyu(a, b, alternative="two-sided")
                summary.setdefault("mannwhitney_p", {})[feat] = float(u.pvalue)
    except Exception as e:  # noqa: BLE001
        summary["mw_error"] = str(e)

    (EXPDIR / "exp-2858_summary.json").write_text(json.dumps(summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        for ax, feat, label in zip(
            axes,
            ["abs_d_mean_glucose", "abs_d_cv_glucose", "abs_d_mean_basal"],
            ["|Δ mean glucose| (mg/dL)", "|Δ CV glucose|", "|Δ mean basal| (U/hr)"],
        ):
            data = [keep[feat].dropna(), flip[feat].dropna()]
            ax.boxplot(data, labels=["no flip", "flip"], showfliers=False)
            ax.set_ylabel(label)
            p = summary.get("mannwhitney_p", {}).get(feat)
            if p is not None:
                ax.set_title(f"{label}\nMann-Whitney p={p:.3f}")
        fig.suptitle(
            "EXP-2858: Window-pair deltas — Simpson flip vs no flip",
            fontsize=11,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2858_flip_drivers.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
