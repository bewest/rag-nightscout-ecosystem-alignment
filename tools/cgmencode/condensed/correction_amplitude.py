"""Condensed figure pack for canonical narrative 01: Physics of a Correction.

Produces four figures that jointly demonstrate how the T1D body responds
to an insulin correction dose at different amplitudes:

  F1  Nadir-centered glucose trace by dose quartile      (fresh compute)
  F2  Apparent ISF vs ln(dose), per-patient + pooled      (recompose)
  F3  BG-drop saturation curve vs dose                    (recompose)
  F4  SC->hepatic EGP suppression ceiling distribution    (recompose)

Data sources
  externals/ns-parquet/training/grid.parquet
  externals/experiments/exp-2636_dose_dependent_isf.json
  externals/experiments/exp-2640_per_patient_isf.json
  externals/experiments/exp-2656_sc_ceiling.json
  externals/experiments/exp-2681_bg_drop_model.json

Outputs
  visualizations/canonical/01/f1_nadir_centered_by_dose.png
  visualizations/canonical/01/f2_isf_vs_logdose.png
  visualizations/canonical/01/f3_drop_saturation.png
  visualizations/canonical/01/f4_sc_suppression_ceiling.png

Run
  python -m tools.cgmencode.condensed.correction_amplitude
or
  python tools/cgmencode/condensed/correction_amplitude.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "externals" / "experiments"
GRID = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = ROOT / "visualizations" / "canonical" / "01"
OUT.mkdir(parents=True, exist_ok=True)

# EXP-2624 correction-event criteria
BOLUS_MIN_U = 0.5
CARB_WINDOW_MIN = 60          # no carbs within +-1h
CARB_THRESHOLD_G = 2.0
STACKING_WINDOW_MIN = 360     # no prior bolus within 6h
BG_MIN = 120.0
DROP_MIN = 10.0
TRACE_HOURS = 6.0
SAMPLE_MIN = 5                # grid is 5-min sampled


def detect_correction_events(df: pd.DataFrame) -> pd.DataFrame:
    """Detect correction boluses per EXP-2624 criteria; return event rows."""
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)
    # Identify bolus rows
    bolus_mask = df["bolus"].fillna(0) >= BOLUS_MIN_U
    # User boluses only (exclude SMB). bolus_smb is the SMB component.
    bolus_mask &= (df["bolus"].fillna(0) - df["bolus_smb"].fillna(0)) >= BOLUS_MIN_U
    bolus_mask &= df["glucose"].fillna(0) >= BG_MIN
    bolus_mask &= df["carbs"].fillna(0) < CARB_THRESHOLD_G
    events = df.loc[bolus_mask, ["patient_id", "time", "bolus", "bolus_smb",
                                  "glucose", "iob", "carbs"]].copy()

    records: list[dict] = []
    for patient_id, pdf in df.groupby("patient_id", sort=False):
        pdf = pdf.set_index("time").sort_index()
        pev = events[events["patient_id"] == patient_id]
        last_bolus_time: pd.Timestamp | None = None
        for _, ev in pev.iterrows():
            t0 = ev["time"]
            # No stacking
            if last_bolus_time is not None and (t0 - last_bolus_time).total_seconds() / 60 < STACKING_WINDOW_MIN:
                last_bolus_time = t0
                continue
            # No carbs +-1h (already checked row carbs; expand window)
            w = pdf.loc[t0 - pd.Timedelta(minutes=CARB_WINDOW_MIN):
                       t0 + pd.Timedelta(minutes=CARB_WINDOW_MIN)]
            if (w["carbs"].fillna(0) >= CARB_THRESHOLD_G).any():
                last_bolus_time = t0
                continue
            # Trace out 0-6h
            trace = pdf.loc[t0: t0 + pd.Timedelta(hours=TRACE_HOURS)]
            if len(trace) < int(TRACE_HOURS * 60 / SAMPLE_MIN * 0.8):
                last_bolus_time = t0
                continue
            pre_bg = pdf.loc[t0 - pd.Timedelta(minutes=15): t0, "glucose"].median()
            nadir_bg = trace["glucose"].min()
            drop = pre_bg - nadir_bg
            if drop < DROP_MIN:
                last_bolus_time = t0
                continue
            # Normalize trace to pre_bg baseline; resample to 5-min grid 0..6h
            rel = (trace.index - t0).total_seconds() / 60.0
            glu = trace["glucose"].to_numpy()
            # Bin to 5-min centers
            bins = np.arange(0, TRACE_HOURS * 60 + SAMPLE_MIN, SAMPLE_MIN)
            idx = np.digitize(rel, bins) - 1
            binned = np.full(len(bins) - 1, np.nan)
            for i in range(len(bins) - 1):
                sel = glu[idx == i]
                if len(sel):
                    binned[i] = float(np.nanmean(sel))
            records.append({
                "patient_id": patient_id,
                "time": t0,
                "dose_u": float(ev["bolus"]),
                "pre_bg": float(pre_bg),
                "nadir_bg": float(nadir_bg),
                "drop": float(drop),
                "iob_at_bolus": float(ev["iob"]) if pd.notna(ev["iob"]) else np.nan,
                "trace": binned,
            })
            last_bolus_time = t0
    out = pd.DataFrame(records)
    return out


# ---------- F1 ---------------------------------------------------------

def figure_1_nadir_centered(events: pd.DataFrame) -> None:
    if events.empty:
        print("[F1] no events; skipping")
        return
    qs = np.quantile(events["dose_u"], [0.25, 0.5, 0.75])
    def _bin(d):
        if d < qs[0]: return 0
        if d < qs[1]: return 1
        if d < qs[2]: return 2
        return 3
    events = events.copy()
    events["qbin"] = events["dose_u"].apply(_bin)
    labels = [f"Q1  <{qs[0]:.1f} U",
              f"Q2  {qs[0]:.1f}\u2013{qs[1]:.1f} U",
              f"Q3  {qs[1]:.1f}\u2013{qs[2]:.1f} U",
              f"Q4  \u2265{qs[2]:.1f} U"]
    colors = ["#4575b4", "#91bfdb", "#fdae61", "#d73027"]
    t_axis = np.arange(0, TRACE_HOURS * 60, SAMPLE_MIN) / 60.0
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for q in range(4):
        sub = events[events["qbin"] == q]
        if sub.empty: continue
        mat = np.vstack(sub["trace"].tolist())
        # Re-baseline by pre-bg per event
        mat = mat - sub["pre_bg"].to_numpy()[:, None]
        med = np.nanmedian(mat, axis=0)
        p25 = np.nanpercentile(mat, 25, axis=0)
        p75 = np.nanpercentile(mat, 75, axis=0)
        ax.plot(t_axis, med, color=colors[q], lw=2,
                label=f"{labels[q]}   n={len(sub)}")
        ax.fill_between(t_axis, p25, p75, color=colors[q], alpha=0.12)
        # Mark nadir
        ni = int(np.nanargmin(med))
        ax.scatter([t_axis[ni]], [med[ni]], color=colors[q], s=40,
                   edgecolor="black", zorder=5)
    ax.axvline(3.5, color="grey", lw=0.8, ls=":", alpha=0.7)
    ax.text(3.52, ax.get_ylim()[1] * 0.9 if ax.get_ylim()[1] > 0 else -5,
            "EXP-2624 canonical nadir \u2248 3.5 h",
            fontsize=8, color="grey")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("Hours since correction bolus")
    ax.set_ylabel("\u0394 Glucose from pre-bolus baseline (mg/dL)")
    ax.set_title("F1 \u00b7 Nadir-centered response by dose quartile  \u2014  three-phase correction model")
    ax.legend(loc="lower left", fontsize=9, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "f1_nadir_centered_by_dose.png", dpi=140)
    plt.close(fig)
    print(f"[F1] wrote {OUT / 'f1_nadir_centered_by_dose.png'}  (n_events={len(events)})")


# ---------- F2 ---------------------------------------------------------

def figure_2_isf_vs_logdose() -> None:
    d36 = json.loads((EXP / "exp-2636_dose_dependent_isf.json").read_text())
    ev = pd.DataFrame(d36["events"])
    ev = ev[(ev["bolus_u"] > 0) & (ev["apparent_isf"].between(1, 500))]
    ev["ln_dose"] = np.log(ev["bolus_u"])

    # Pooled OLS fit on ev
    x = ev["ln_dose"].to_numpy()
    y = ev["apparent_isf"].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    # Per-patient thin traces (use per_patient curves if they contain points)
    per = d36.get("per_patient", {})
    # Scatter events light
    ax.scatter(ev["bolus_u"], ev["apparent_isf"], s=10, color="#888", alpha=0.25,
               label=f"events (n={len(ev)})")
    # Dose-response bins
    dr = d36["dose_response"]
    bin_centers = []
    bin_vals = []
    for row in dr:
        label = row["bin"]
        # extract numeric center
        import re
        nums = [float(x) for x in re.findall(r"[\d.]+", label)]
        if not nums: continue
        center = sum(nums) / len(nums) if len(nums) == 2 else nums[0] * 1.2
        bin_centers.append(center)
        bin_vals.append(row["mean_isf"])
    ax.plot(bin_centers, bin_vals, "o-", color="#d73027", lw=2,
            markersize=9, label="EXP-2636 bin means")
    # Log fit line
    xs = np.linspace(ev["bolus_u"].min(), ev["bolus_u"].max(), 100)
    ax.plot(xs, intercept + slope * np.log(xs), color="#4575b4", lw=2,
            label=f"pooled fit: ISF \u2248 {intercept:.0f} + {slope:.0f}\u00b7ln(dose)")
    ax.set_xscale("log")
    ax.set_xlabel("Correction dose (U) [log]")
    ax.set_ylabel("Apparent ISF (mg/dL per U)")
    ax.set_title("F2 \u00b7 Apparent ISF compresses logarithmically with dose  \u2014  4.6\u00d7 range")
    ax.grid(alpha=0.25, which="both")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    ax.set_ylim(0, min(250, ev["apparent_isf"].quantile(0.99) * 1.1))
    fig.tight_layout()
    fig.savefig(OUT / "f2_isf_vs_logdose.png", dpi=140)
    plt.close(fig)
    print(f"[F2] wrote {OUT / 'f2_isf_vs_logdose.png'}")


# ---------- F3 ---------------------------------------------------------

def figure_3_drop_saturation() -> None:
    d = json.loads((EXP / "exp-2681_bg_drop_model.json").read_text())
    bins = d["dose_bins"]
    centers, drops, ns = [], [], []
    for k, v in bins.items():
        centers.append(v["median_dose"])
        drops.append(v["median_drop"])
        ns.append(v["n"])
    centers = np.array(centers); drops = np.array(drops); ns = np.array(ns)

    # Overlay EXP-2875 counter-reg floor hypothesis: drop caps near 74 mg/dL
    # for most common doses; here we mark the asymptote.
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    sizes = 20 + 200 * (ns / ns.max())
    ax.scatter(centers, drops, s=sizes, color="#d73027", edgecolor="k",
               alpha=0.85, label="EXP-2681 dose bins (size \u221d n)")
    ax.plot(centers, drops, color="#d73027", alpha=0.5)
    ax.axhline(74, color="#4575b4", ls="--", lw=1.2,
               label="counter-reg BG drop floor \u2248 74 mg/dL")
    # Linear ISF=50 reference
    xs = np.linspace(0.2, centers.max(), 50)
    ax.plot(xs, 50 * xs, color="grey", ls=":", lw=1,
            label="linear ISF=50 reference")
    ax.set_xscale("log")
    ax.set_xlabel("Median dose in bin (U) [log]")
    ax.set_ylabel("Median BG drop (mg/dL)")
    ax.set_title("F3 \u00b7 BG drop saturates: a 10 U dose does not drop 10\u00d7 more than a 1 U dose")
    ax.grid(alpha=0.25, which="both")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    for c, dv, n in zip(centers, drops, ns):
        ax.annotate(f"n={n}", (c, dv), xytext=(4, 6),
                    textcoords="offset points", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "f3_drop_saturation.png", dpi=140)
    plt.close(fig)
    print(f"[F3] wrote {OUT / 'f3_drop_saturation.png'}")


# ---------- F4 ---------------------------------------------------------

def figure_4_sc_ceiling() -> None:
    d = json.loads((EXP / "exp-2656_sc_ceiling.json").read_text())
    rows = []
    for pid, pv in d.items():
        if not isinstance(pv, dict): continue
        if "fitted_ceiling" not in pv: continue
        rows.append({
            "patient_id": pid,
            "fitted_ceiling": pv["fitted_ceiling"],
            "pct_sticky": pv["pct_sticky"],
            "actual_to_predicted_ratio": pv.get("actual_to_predicted_ratio", np.nan),
            "n": pv.get("n_high_iob", np.nan),
        })
    df = pd.DataFrame(rows)
    df = df[df["fitted_ceiling"].between(0, 1)].sort_values("fitted_ceiling")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                   gridspec_kw={"width_ratios": [1.2, 1]})
    # Left: histogram of ceiling
    ax1.hist(df["fitted_ceiling"] * 100, bins=12, color="#d73027",
             edgecolor="black", alpha=0.85)
    ax1.axvline(df["fitted_ceiling"].median() * 100, color="#4575b4",
                ls="--", lw=2, label=f"cohort median  {df['fitted_ceiling'].median()*100:.0f}%")
    ax1.axvline(65, color="grey", ls=":", lw=2,
                label="cgmsim-lib literature  65%")
    ax1.set_xlabel("Fitted SC \u2192 hepatic EGP suppression ceiling (%)")
    ax1.set_ylabel("Patients")
    ax1.set_title(f"F4a \u00b7 Suppression ceiling distribution  (n={len(df)})")
    ax1.legend(loc="upper right", fontsize=9, frameon=False)
    ax1.grid(alpha=0.25)

    # Right: ceiling vs sticky-high fraction
    ax2.scatter(df["fitted_ceiling"] * 100, df["pct_sticky"] * 100,
                s=40, color="#d73027", edgecolor="k")
    # pearson
    valid = df.dropna(subset=["fitted_ceiling", "pct_sticky"])
    r = np.corrcoef(valid["fitted_ceiling"], valid["pct_sticky"])[0, 1]
    ax2.set_xlabel("Suppression ceiling (%)")
    ax2.set_ylabel("Sticky-hyper rate at high IOB (%)")
    ax2.set_title(f"F4b \u00b7 Lower ceiling \u2192 more sticky-highs  (r = {r:+.2f})")
    ax2.grid(alpha=0.25)
    for _, row in df.iterrows():
        ax2.annotate(str(row["patient_id"])[:6], (row["fitted_ceiling"] * 100,
                     row["pct_sticky"] * 100), fontsize=7, alpha=0.7,
                     xytext=(3, 3), textcoords="offset points")
    fig.suptitle("F4 \u00b7 Subcutaneous insulin has a hard ceiling on hepatic EGP suppression",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f4_sc_suppression_ceiling.png", dpi=140)
    plt.close(fig)
    print(f"[F4] wrote {OUT / 'f4_sc_suppression_ceiling.png'}")


def main() -> None:
    print("== Loading grid.parquet")
    cols = ["patient_id", "time", "glucose", "iob", "bolus", "bolus_smb",
            "carbs", "scheduled_isf"]
    df = pd.read_parquet(GRID, columns=cols)
    print(f"   {len(df):,} rows  \u00b7  {df['patient_id'].nunique()} patients")

    print("== Detecting correction events (EXP-2624 criteria)")
    events = detect_correction_events(df)
    print(f"   {len(events):,} correction events detected")

    figure_1_nadir_centered(events)
    figure_2_isf_vs_logdose()
    figure_3_drop_saturation()
    figure_4_sc_ceiling()
    print(f"\nFigures written to {OUT}")


if __name__ == "__main__":
    main()
