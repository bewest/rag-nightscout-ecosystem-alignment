"""EXP-2893 — Hyper-side channel decomposition.

Counterpart to EXP-2892 (hypo protection).  During BG ascents
into hyper range (>180 mg/dL), how does insulin delivery
decompose across:
  channel_C (SMB):           sum(bolus_smb) during ascent
  channel_D (excess basal):  sum(max(actual-sched, 0) * dt)
  channel_E (user bolus):    sum(bolus - bolus_smb) during ascent

Expectation: oref1 leans on SMB (channel_C) heavily;
Loop has no SMB so lean on channel_D + E; oref0 has SMB
capability but uses it less aggressively per EXP-2892's
utilization finding.

Writes exp-2893_hyper_channels.{parquet,png,json}.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
EXP = ROOT / "externals" / "experiments"
FIG = ROOT / "docs" / "60-research" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(2893)

g = pd.read_parquet(GRID,
    columns=["patient_id","time","glucose","bolus","bolus_smb",
             "scheduled_basal_rate","actual_basal_rate"])
g = g.sort_values(["patient_id","time"]).reset_index(drop=True)

# Detect ascent events: window of BG crossing upward into >180 and
# returning below 180. Use simple method: find runs where BG > 180.
events = []
for pid, sub in g.groupby("patient_id"):
    sub = sub.reset_index(drop=True)
    above = (sub["glucose"] > 180).values
    if not above.any():
        continue
    # find contiguous runs
    diff = np.diff(np.concatenate(([0], above.astype(int), [0])))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    for s, e in zip(starts, ends):
        if e - s < 3:  # need at least 15 min
            continue
        # pre-ascent start: look back 12 rows (60 min) for the local minimum below 180
        pre_s = max(0, s - 12)
        pre_window = sub.iloc[pre_s:s]
        if len(pre_window) == 0 or pre_window["glucose"].notna().sum() == 0:
            continue
        low_idx = pre_window["glucose"].idxmin()
        asc_start = int(low_idx)
        asc_seg = sub.iloc[s:e]
        if asc_seg["glucose"].notna().sum() == 0:
            continue
        peak_idx = asc_seg["glucose"].idxmax()
        peak = int(peak_idx)
        # window from asc_start to peak is the ascent segment
        win = sub.iloc[asc_start:peak+1]
        if len(win) < 3:
            continue
        # Insulin during ascent
        smb = float(win["bolus_smb"].fillna(0).sum())
        bolus_total = float(win["bolus"].fillna(0).sum())
        user_bolus = max(0.0, bolus_total - smb)
        # basal: 5-min cadence; rates are U/h
        dt_h = 5.0 / 60.0
        sched_U = float((win["scheduled_basal_rate"].fillna(0) * dt_h).sum())
        actual_U = float((win["actual_basal_rate"].fillna(0) * dt_h).sum())
        excess_basal = max(0.0, actual_U - sched_U)
        bg_start = float(sub.iloc[asc_start]["glucose"])
        bg_peak = float(sub.iloc[peak]["glucose"])
        dur_min = (sub.iloc[peak]["time"] - sub.iloc[asc_start]["time"]).total_seconds() / 60
        events.append(dict(
            patient_id=pid, bg_start=bg_start, bg_peak=bg_peak,
            duration_min=dur_min, smb_U=smb, user_bolus_U=user_bolus,
            excess_basal_U=excess_basal, sched_basal_U=sched_U,
        ))

evt = pd.DataFrame(events)
evt = evt[(evt["bg_peak"] - evt["bg_start"] >= 20)  # real rise
          & (evt["duration_min"] >= 15)
          & (evt["duration_min"] <= 240)]
print(f"Ascent events: {len(evt)} across {evt['patient_id'].nunique()} patients")

# Merge lineage/tercile from 2891
sim = pd.read_parquet(EXP / "exp-2891_simpson_dose_response.parquet")[
    ["patient_id","lineage","tercile"]]
evt = evt.merge(sim, on="patient_id", how="inner")
print(f"After lineage merge: {len(evt)}")

# Per-patient means
per = (evt.groupby("patient_id")
          .agg(n_events=("bg_start","size"),
               smb_U=("smb_U","mean"),
               user_bolus_U=("user_bolus_U","mean"),
               excess_basal_U=("excess_basal_U","mean"),
               bg_rise=("bg_peak","mean"))
          .reset_index())
per = per.merge(sim, on="patient_id", how="inner")
per["total_U"] = per["smb_U"] + per["user_bolus_U"] + per["excess_basal_U"]
per["frac_smb"] = per["smb_U"] / per["total_U"].replace(0, np.nan)
per["frac_user"] = per["user_bolus_U"] / per["total_U"].replace(0, np.nan)
per["frac_excess_basal"] = per["excess_basal_U"] / per["total_U"].replace(0, np.nan)

by_lin = (per.groupby("lineage")
             .agg(n=("patient_id","nunique"),
                  smb_U=("smb_U","mean"),
                  user_bolus_U=("user_bolus_U","mean"),
                  excess_basal_U=("excess_basal_U","mean"),
                  frac_smb=("frac_smb","mean"),
                  frac_user=("frac_user","mean"),
                  frac_excess=("frac_excess_basal","mean"))
             .round(3))
print("\nBy lineage:")
print(by_lin)

by_tc = (per.groupby(["lineage","tercile"])
             .agg(n=("patient_id","nunique"),
                  frac_smb=("frac_smb","mean"),
                  frac_user=("frac_user","mean"),
                  frac_excess=("frac_excess_basal","mean"))
             .round(3))
print("\nBy lineage x tercile:")
print(by_tc)

# Figure: stacked bar of fractions
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
lin_order = ["oref0 (legacy)","Loop (iOS)","oref1 (modern)","unknown"]
plot_df = by_lin.reindex([l for l in lin_order if l in by_lin.index])
x = np.arange(len(plot_df))
axes[0].bar(x, plot_df["frac_smb"], label="SMB (channel C)", color="firebrick")
axes[0].bar(x, plot_df["frac_excess"], bottom=plot_df["frac_smb"],
            label="excess basal (channel D)", color="steelblue")
axes[0].bar(x, plot_df["frac_user"],
            bottom=plot_df["frac_smb"]+plot_df["frac_excess"],
            label="user bolus (channel E)", color="gray")
axes[0].set_xticks(x)
axes[0].set_xticklabels(plot_df.index, rotation=15)
axes[0].set_ylabel("fraction of ascent-window insulin")
axes[0].set_title("Hyper-correction channel composition")
axes[0].legend()
axes[0].set_ylim(0, 1.05)

# Magnitude
axes[1].bar(x - 0.22, plot_df["smb_U"], width=0.22, label="SMB", color="firebrick")
axes[1].bar(x,       plot_df["excess_basal_U"], width=0.22, label="excess basal", color="steelblue")
axes[1].bar(x + 0.22, plot_df["user_bolus_U"], width=0.22, label="user bolus", color="gray")
axes[1].set_xticks(x)
axes[1].set_xticklabels(plot_df.index, rotation=15)
axes[1].set_ylabel("mean U per ascent event")
axes[1].set_title("Absolute insulin per channel")
axes[1].legend()

plt.tight_layout()
out_png = FIG / "exp-2893_hyper_channels.png"
plt.savefig(out_png, dpi=120)
print(f"\nWrote {out_png.relative_to(ROOT)}")

per.to_parquet(EXP / "exp-2893_hyper_channels.parquet", index=False)
summary = {
    "n_events": int(len(evt)),
    "n_patients": int(per["patient_id"].nunique()),
    "by_lineage": by_lin.reset_index().to_dict(orient="records"),
    "by_lineage_tercile": by_tc.reset_index().to_dict(orient="records"),
}
(EXP / "exp-2893_hyper_channels_summary.json").write_text(json.dumps(summary, indent=2))
print("Wrote exp-2893_hyper_channels_summary.json")
