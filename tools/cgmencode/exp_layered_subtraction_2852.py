"""EXP-2852 — Layered subtraction: regress out the fast (5-min) reactive
arrow then redo the 48h envelope coupling on the residuals.

Hypothesis (Stream B): the basal-vs-glucose 48h envelope coupling
mixes a fast reactive component (controller-suspends-on-high-BG,
captured at 5-min lag) with a slow structural component (state →
metabolic demand → both BG and basal up). Per EXP-2849, the cohort
median 48h coupling is +1.5% (near zero) — likely because the two
components partially cancel for many patients.

If we regress out the fast reactive arrow per patient at 5-min:
    actual_basal_rate_t = α + β · glucose_t + ε_t
then ε_t is "non-reactive basal demand" (the controller's set-point /
schedule + slow drift). Re-aggregating ε_t in 48h windows and re-
running the elevated-vs-normal envelope coupling should sharpen the
structural signal, especially for up_shift patients (EXP-2850).

Charter B compliant: ε_t is an operational residual, NOT EGP. We
make no biology claim. We only claim that conditioning on the fast
reactive arrow reveals the slow structural arrow more cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"


def envelope_shift(df: pd.DataFrame, value_col: str, window_h: int) -> dict:
    """Per-patient elevated-vs-normal shift for a given value column."""
    win = f"{int(window_h * 12)}min"  # 5-min grid
    df = df.set_index("time").sort_index()
    g = df["glucose"].rolling(win).mean()
    v = df[value_col].rolling(win).mean()
    pair = pd.concat([g, v], axis=1, keys=["g", "v"]).dropna()
    if len(pair) < 100:
        return {"n": int(len(pair)), "shift_pct": np.nan, "p": np.nan}
    # Non-overlapping samples: take 1 per window length
    step = int(window_h * 12)
    pair = pair.iloc[::step]
    if len(pair) < 6:
        return {"n": int(len(pair)), "shift_pct": np.nan, "p": np.nan}
    q33, q66 = pair["g"].quantile([1 / 3, 2 / 3])
    lo = pair[pair["g"] <= q33]["v"].dropna().to_numpy()
    hi = pair[pair["g"] >= q66]["v"].dropna().to_numpy()
    if len(lo) < 2 or len(hi) < 2:
        return {"n": int(len(pair)), "shift_pct": np.nan, "p": np.nan}
    base = np.mean(lo)
    if base == 0 or np.isnan(base):
        return {"n": int(len(pair)), "shift_pct": np.nan, "p": np.nan}
    shift_pct = 100.0 * (np.mean(hi) - base) / base
    try:
        u, p = stats.mannwhitneyu(hi, lo, alternative="two-sided")
    except ValueError:
        p = np.nan
    return {"n": int(len(pair)), "shift_pct": float(shift_pct), "p": float(p)}


def main() -> None:
    cols = ["patient_id", "time", "glucose", "actual_basal_rate"]
    df = pd.read_parquet(GRID, columns=cols)
    df = df.dropna(subset=["glucose", "actual_basal_rate"]).sort_values(
        ["patient_id", "time"]
    )

    rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        if len(g) < 24 * 12 * 7:  # need >=7 days
            continue
        g = g.sort_values("time").reset_index(drop=True)

        # Step 1: fit fast reactive arrow per patient
        x = g["glucose"].to_numpy()
        y = g["actual_basal_rate"].to_numpy()
        if np.std(x) < 1e-6 or np.std(y) < 1e-6:
            continue
        slope, intercept, r_value, _, _ = stats.linregress(x, y)
        residual = y - (intercept + slope * x)

        g_resid = g[["time", "glucose"]].copy()
        g_resid["actual_basal_rate"] = y          # raw
        g_resid["basal_residual"] = residual      # reactive-removed
        g_resid["time"] = pd.to_datetime(g_resid["time"], utc=True)

        for w in (24, 48):
            raw = envelope_shift(g_resid, "actual_basal_rate", w)
            res = envelope_shift(
                g_resid.assign(actual_basal_rate=g_resid["basal_residual"]),
                "actual_basal_rate",
                w,
            )
            rows.append({
                "patient_id": pid,
                "window_h": w,
                "raw_shift_pct": raw["shift_pct"],
                "raw_p": raw["p"],
                "resid_shift_pct": res["shift_pct"],
                "resid_p": res["p"],
                "fast_arrow_slope": float(slope),
                "fast_arrow_r": float(r_value),
                "n_samples": raw["n"],
            })

    out = pd.DataFrame(rows)
    out_path = EXPDIR / "exp-2852_layered_subtraction.parquet"
    out.to_parquet(out_path, index=False)

    # Cohort summary per window
    summary = []
    for w in sorted(out["window_h"].unique()):
        sub = out[out["window_h"] == w].dropna(
            subset=["raw_shift_pct", "resid_shift_pct"]
        )
        sub_sig_raw = sub[sub["raw_p"] < 0.01]
        sub_sig_res = sub[sub["resid_p"] < 0.01]
        # Sign-flip reduction: fraction of patients whose raw and residual
        # have OPPOSITE signs (those are the most-confounded patients).
        flip = sub[
            (np.sign(sub["raw_shift_pct"]) != np.sign(sub["resid_shift_pct"]))
            & (sub["raw_shift_pct"].abs() > 1)
            & (sub["resid_shift_pct"].abs() > 1)
        ]
        summary.append({
            "window_h": int(w),
            "n_patients": int(len(sub)),
            "raw_median_pct": float(sub["raw_shift_pct"].median()),
            "raw_iqr_pct": float(
                sub["raw_shift_pct"].quantile(0.75)
                - sub["raw_shift_pct"].quantile(0.25)
            ),
            "raw_n_sig_p01": int(len(sub_sig_raw)),
            "resid_median_pct": float(sub["resid_shift_pct"].median()),
            "resid_iqr_pct": float(
                sub["resid_shift_pct"].quantile(0.75)
                - sub["resid_shift_pct"].quantile(0.25)
            ),
            "resid_n_sig_p01": int(len(sub_sig_res)),
            "n_sign_flips": int(len(flip)),
            "median_abs_change": float(
                (sub["resid_shift_pct"] - sub["raw_shift_pct"]).abs().median()
            ),
        })

    out_summary = {
        "exp": "EXP-2852",
        "method": (
            "Per patient: fit basal_t = alpha + beta * glucose_t (fast arrow), "
            "subtract to get residual, re-run 48h envelope coupling on residual."
        ),
        "summary_by_window": summary,
        "interpretation": [
            "If residual median magnitude > raw median magnitude: structural "
            "signal sharpens after fast-arrow removal.",
            "If sign flips for many patients: raw 48h was dominated by "
            "reactive bleed-through, residual reveals true structural sign.",
        ],
    }
    out_json = EXPDIR / "exp-2852_summary.json"
    out_json.write_text(json.dumps(out_summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, w in zip(axes, [24, 48]):
            sub = out[out["window_h"] == w].dropna(
                subset=["raw_shift_pct", "resid_shift_pct"]
            )
            ax.scatter(
                sub["raw_shift_pct"],
                sub["resid_shift_pct"],
                s=60, color="#4472C4", edgecolor="black", alpha=0.7,
            )
            lim = max(
                sub["raw_shift_pct"].abs().max(),
                sub["resid_shift_pct"].abs().max(),
                10,
            ) * 1.1
            ax.plot([-lim, lim], [-lim, lim], "k--", alpha=0.3, label="y = x")
            ax.axhline(0, color="gray", linewidth=0.5)
            ax.axvline(0, color="gray", linewidth=0.5)
            ax.set_xlabel(f"RAW basal-shift % at {w}h envelope")
            ax.set_ylabel(f"RESIDUAL basal-shift % (reactive removed)")
            ax.set_title(
                f"{w}h window — median raw: "
                f"{sub['raw_shift_pct'].median():+.1f}% → "
                f"residual: {sub['resid_shift_pct'].median():+.1f}%"
            )
            ax.legend(fontsize=8)
        fig.suptitle(
            "EXP-2852: layered subtraction — does removing the fast reactive "
            "arrow sharpen the slow structural envelope?",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2852_layered_subtraction.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(out_summary, indent=2))


if __name__ == "__main__":
    main()
