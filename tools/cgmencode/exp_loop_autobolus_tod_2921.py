"""EXP-2921 - Loop TOD profile split by autobolus on/off.

Follow-up to EXP-2920: does autobolus-OFF Loop show oref0-like
midnight hypo? Does autobolus-ON Loop carry the dawn-hyper
signature? Same patient-mean-then-pool method.

Autobolus mapping from EXP-2919 (derived from bolus_smb column,
per-patient):
  OFF: a, f
  ON:  c, d, e, g, i

Scope: design-feature characterisation for AID-author audience.
NOT therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent.parent
HOURLY = REPO / "externals" / "experiments" / "exp-2920_hourly.parquet"
OUT_J = REPO / "externals" / "experiments" / "exp-2921_summary.json"
PNG = REPO / "docs" / "visualizations" / "exp-2921-loop-autobolus-tod.png"
PNG.parent.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(2921)
N_BOOT = 2000

LOOP_AUTOBOLUS_OFF = {"a", "f"}
LOOP_AUTOBOLUS_ON = {"c", "d", "e", "g", "i"}


def boot_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    hourly = pd.read_parquet(HOURLY)
    loop = hourly[hourly["lineage"] == "Loop (iOS)"].copy()
    loop["autobolus"] = loop["patient_id"].map(
        lambda p: "ON" if p in LOOP_AUTOBOLUS_ON else ("OFF" if p in LOOP_AUTOBOLUS_OFF else None)
    )
    loop = loop.dropna(subset=["autobolus"])
    print("[exp-2921] patients:")
    for ab, sub in loop.groupby("autobolus"):
        print(f"  {ab}: {sorted(sub['patient_id'].unique())}")

    cells = []
    for ab in ["OFF", "ON"]:
        for hr in range(24):
            sub = loop[(loop["autobolus"] == ab) & (loop["hour"] == hr)]
            n_pat = sub["patient_id"].nunique()
            if n_pat == 0:
                continue
            pm_hypo = sub.groupby("patient_id")["frac_hypo"].mean().values
            pm_hyper = sub.groupby("patient_id")["frac_hyper"].mean().values
            lo_h, hi_h = boot_ci(pm_hypo)
            lo_y, hi_y = boot_ci(pm_hyper)
            cells.append({
                "autobolus": ab, "hour": hr, "n_patients": int(n_pat),
                "mean_frac_hypo": float(pm_hypo.mean()),
                "ci_lo_hypo": lo_h, "ci_hi_hypo": hi_h,
                "mean_frac_hyper": float(pm_hyper.mean()),
                "ci_lo_hyper": lo_y, "ci_hi_hyper": hi_y,
            })
    df = pd.DataFrame(cells)
    summary = {
        "scope": "Loop autobolus on/off TOD split; AID-author scope; not therapy advice",
        "n_patients_off": int(loop[loop["autobolus"] == "OFF"]["patient_id"].nunique()),
        "n_patients_on": int(loop[loop["autobolus"] == "ON"]["patient_id"].nunique()),
        "hourly_cells": df.to_dict(orient="records"),
    }
    OUT_J.write_text(json.dumps(summary, indent=2, default=str))

    color = {"OFF": "#9467bd", "ON": "#1f77b4"}
    fig, (ax_h, ax_y) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ab in ["OFF", "ON"]:
        sub = df[df["autobolus"] == ab].sort_values("hour")
        n = sub["n_patients"].iloc[0]
        ax_h.plot(sub["hour"], sub["mean_frac_hypo"] * 100, "o-", color=color[ab],
                  label=f"autobolus {ab} (n={n})")
        ax_h.fill_between(sub["hour"], sub["ci_lo_hypo"] * 100, sub["ci_hi_hypo"] * 100,
                          color=color[ab], alpha=0.15)
        ax_y.plot(sub["hour"], sub["mean_frac_hyper"] * 100, "o-", color=color[ab],
                  label=f"autobolus {ab} (n={n})")
        ax_y.fill_between(sub["hour"], sub["ci_lo_hyper"] * 100, sub["ci_hi_hyper"] * 100,
                          color=color[ab], alpha=0.15)
    ax_h.set_ylabel("% cells < 54 mg/dL")
    ax_h.set_title("Loop severe hypoglycemia by hour - autobolus split\n95% bootstrap CI; AID-author scope")
    ax_h.legend(); ax_h.grid(alpha=0.3)
    ax_y.set_ylabel("% cells > 250 mg/dL")
    ax_y.set_xlabel("Hour of day")
    ax_y.set_title("Loop severe hyperglycemia by hour - autobolus split")
    ax_y.legend(); ax_y.grid(alpha=0.3); ax_y.set_xticks(range(0, 24, 2))
    plt.tight_layout(); plt.savefig(PNG, dpi=150)
    print(f"[exp-2921] {PNG}")
    print("\nPeak hours:")
    for ab in ["OFF", "ON"]:
        sub = df[df["autobolus"] == ab]
        ph = sub.loc[sub["mean_frac_hypo"].idxmax()]
        py = sub.loc[sub["mean_frac_hyper"].idxmax()]
        print(f"  {ab}: hypo peak hr={int(ph['hour'])} {ph['mean_frac_hypo']*100:.2f}%, "
              f"hyper peak hr={int(py['hour'])} {py['mean_frac_hyper']*100:.2f}%")


if __name__ == "__main__":
    main()
