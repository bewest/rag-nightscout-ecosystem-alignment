#!/usr/bin/env python3
"""EXP-2689: Confounding by Indication — Why Bolus Events Drop Less

EXP-2687 found that no-bolus events at BG≥180 drop MORE than bolus events.
This is likely confounding by indication: users bolus in harder-to-correct
situations. This experiment disentangles the confound.

Tests:
  1. Pre-event BG trajectory: are bolus events rising while no-bolus are falling?
  2. Concurrent carbs: do bolus events have more meal context?
  3. Controller state: was the controller already at max before bolus?
  4. BG₀-matched comparison: control for starting BG
  5. Within-patient comparison: same patient, bolus vs no-bolus
  6. Glucose ROC at event time: rising vs falling BG
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/confounding-analysis")
OUT.mkdir(parents=True, exist_ok=True)
EXP = pathlib.Path("externals/experiments")

# ── Load data ──────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid["controller"] = grid["patient_id"].map(ctrl_map)

manifest = json.loads((EXP / "autoprepare-qualified.json").read_text())
qual = manifest["qualified_patients"]
grid = grid[grid["patient_id"].isin(qual)]
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

FLOOR = 180
HORIZON = 24  # 2h
MIN_ISO = 6   # 30min

# ── Extract events with richer context ─────────────────────────────────
print("Extracting events with pre-event context...")
events = []
for pid in grid["patient_id"].unique():
    pg = grid[grid["patient_id"] == pid].reset_index(drop=True)
    ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    carbs_col = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
    iob_col = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
    net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.full(len(pg), np.nan)
    sched_basal = pg["scheduled_basal_rate"].values if "scheduled_basal_rate" in pg.columns else np.full(len(pg), np.nan)
    roc = pg["glucose_roc"].values if "glucose_roc" in pg.columns else np.full(len(pg), np.nan)
    
    eq_bg = np.nanmedian(glucose)
    
    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        if np.isnan(bg0) or bg0 < FLOOR:
            continue
        bg_2h = glucose[i + HORIZON]
        if np.isnan(bg_2h):
            continue
        
        has_bolus = bolus[i] > 0.5
        prior_bolus = np.nansum(bolus[max(0, i - MIN_ISO):i])
        future_bolus = np.nansum(bolus[i + 1:i + HORIZON])
        
        # Carbs in 2h window
        carbs_2h = np.nansum(carbs_col[i:i + HORIZON])
        carbs_prior_2h = np.nansum(carbs_col[max(0, i - HORIZON):i])
        
        # Pre-event BG trajectory (last 30 min)
        pre_bg = glucose[i - MIN_ISO:i + 1]
        pre_slope = np.nan
        if np.sum(~np.isnan(pre_bg)) >= 3:
            valid = ~np.isnan(pre_bg)
            x = np.arange(len(pre_bg))[valid]
            y = pre_bg[valid]
            if len(x) >= 3:
                pre_slope = np.polyfit(x, y, 1)[0]  # mg/dL per 5min
        
        # Glucose ROC at event
        roc_at = roc[i] if not np.isnan(roc[i]) else np.nan
        
        # IOB at event
        iob_at = iob_col[i]
        
        # Controller effort: net_basal relative to scheduled
        if not np.isnan(net_basal[i]) and not np.isnan(sched_basal[i]) and sched_basal[i] > 0:
            basal_ratio = net_basal[i] / sched_basal[i]
        else:
            basal_ratio = np.nan
        
        # Categorize
        if has_bolus and prior_bolus < 0.5:
            ev_type = "bolus"
        elif not has_bolus and future_bolus < 0.5 and prior_bolus < 0.5 and carbs_2h < 5:
            ev_type = "no_bolus"
        else:
            continue
        
        events.append({
            "patient_id": pid, "controller": ctrl, "event_type": ev_type,
            "bg0": bg0, "bg_2h": bg_2h, "drop": bg0 - bg_2h,
            "dose": bolus[i], "carbs_2h": carbs_2h, "carbs_prior_2h": carbs_prior_2h,
            "pre_slope": pre_slope, "roc_at": roc_at,
            "iob_at": iob_at, "basal_ratio": basal_ratio, "eq_bg": eq_bg,
        })

ev = pd.DataFrame(events)
bolus_ev = ev[ev["event_type"] == "bolus"]
null_ev = ev[ev["event_type"] == "no_bolus"]
print(f"  Bolus: {len(bolus_ev)}, No-bolus: {len(null_ev)}")

# ── Panel 1: Pre-event BG trajectory ─────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

# 1a: Distribution of pre-slope
axes[0].hist(bolus_ev["pre_slope"].dropna(), bins=50, alpha=0.6, label="Bolus", color="C0", density=True)
axes[0].hist(null_ev["pre_slope"].dropna(), bins=50, alpha=0.6, label="No-bolus", color="C1", density=True)
axes[0].axvline(bolus_ev["pre_slope"].median(), color="C0", ls="--", lw=2)
axes[0].axvline(null_ev["pre_slope"].median(), color="C1", ls="--", lw=2)
axes[0].set_xlabel("Pre-event BG slope (mg/dL per 5min)")
axes[0].set_title(f"Pre-event Trajectory\nBolus: {bolus_ev['pre_slope'].median():.2f}, Null: {null_ev['pre_slope'].median():.2f}")
axes[0].legend()

# 1b: Glucose ROC at event
axes[1].hist(bolus_ev["roc_at"].dropna(), bins=50, alpha=0.6, label="Bolus", color="C0", density=True)
axes[1].hist(null_ev["roc_at"].dropna(), bins=50, alpha=0.6, label="No-bolus", color="C1", density=True)
axes[1].set_xlabel("Glucose ROC at event (mg/dL/5min)")
axes[1].set_title("Glucose ROC at Event Time")
axes[1].legend()

# 1c: Summary
b_rising = (bolus_ev["pre_slope"] > 0).mean() * 100
n_rising = (null_ev["pre_slope"] > 0).mean() * 100
b_roc = bolus_ev["roc_at"].median()
n_roc = null_ev["roc_at"].median()
t, p = stats.mannwhitneyu(
    bolus_ev["pre_slope"].dropna(), null_ev["pre_slope"].dropna(), alternative="two-sided"
)
summary = (
    f"Pre-slope (median):\n"
    f"  Bolus:    {bolus_ev['pre_slope'].median():.3f}\n"
    f"  No-bolus: {null_ev['pre_slope'].median():.3f}\n"
    f"  Mann-Whitney p={p:.2e}\n\n"
    f"% with rising BG:\n"
    f"  Bolus:    {b_rising:.1f}%\n"
    f"  No-bolus: {n_rising:.1f}%\n\n"
    f"Glucose ROC (median):\n"
    f"  Bolus:    {b_roc:.3f}\n"
    f"  No-bolus: {n_roc:.3f}"
)
axes[2].text(0.1, 0.5, summary, transform=axes[2].transAxes, fontsize=11,
            va="center", fontfamily="monospace")
axes[2].axis("off")
axes[2].set_title("Summary")

plt.suptitle("EXP-2689: Pre-Event BG Trajectory — Bolus vs No-Bolus", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_pre_trajectory.png", dpi=150)
plt.close()
print("Panel 1: Pre-event trajectory saved")

# ── Panel 2: Concurrent carbs ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Bolus events: with and without carbs
bolus_meal = bolus_ev[bolus_ev["carbs_2h"] >= 5]
bolus_correction = bolus_ev[bolus_ev["carbs_2h"] < 5]

labels = ["Correction\n(no carbs)", "Meal bolus\n(carbs≥5g)", "No bolus\n(null)"]
drops = [bolus_correction["drop"].median(), bolus_meal["drop"].median(), null_ev["drop"].median()]
counts = [len(bolus_correction), len(bolus_meal), len(null_ev)]
colors_bar = ["C0", "C3", "C1"]

bars = axes[0].bar(labels, drops, color=colors_bar, alpha=0.7, edgecolor="k")
for bar, count in zip(bars, counts):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"n={count}", ha="center", fontsize=10)
axes[0].set_ylabel("Median BG drop (mg/dL)")
axes[0].set_title("BG Drop by Event Type")
axes[0].grid(True, alpha=0.3, axis="y")

# Show that correction boluses still drop less than null
axes[1].hist(bolus_correction["drop"], bins=40, alpha=0.5, label=f"Correction (n={len(bolus_correction)})", color="C0", density=True)
axes[1].hist(null_ev["drop"], bins=40, alpha=0.5, label=f"No-bolus (n={len(null_ev)})", color="C1", density=True)
axes[1].axvline(bolus_correction["drop"].median(), color="C0", ls="--", lw=2)
axes[1].axvline(null_ev["drop"].median(), color="C1", ls="--", lw=2)
axes[1].set_xlabel("BG drop (mg/dL)")
axes[1].set_title("Correction Bolus vs No-Bolus")
axes[1].legend()

plt.suptitle("EXP-2689: Meal vs Correction Bolus vs Null", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_carbs_confound.png", dpi=150)
plt.close()
print(f"Panel 2: Carbs confound saved (correction: {len(bolus_correction)}, meal: {len(bolus_meal)})")

# ── Panel 3: Controller state at event ────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

# 3a: IOB at event
axes[0].hist(bolus_ev["iob_at"].dropna(), bins=40, alpha=0.5, label="Bolus", color="C0", density=True)
axes[0].hist(null_ev["iob_at"].dropna(), bins=40, alpha=0.5, label="No-bolus", color="C1", density=True)
axes[0].set_xlabel("IOB at event (U)")
axes[0].set_title(f"IOB: Bolus={bolus_ev['iob_at'].median():.2f}U, Null={null_ev['iob_at'].median():.2f}U")
axes[0].legend()

# 3b: Basal ratio (net_basal / scheduled)
axes[1].hist(bolus_ev["basal_ratio"].dropna().clip(-1, 5), bins=40, alpha=0.5, label="Bolus", color="C0", density=True)
axes[1].hist(null_ev["basal_ratio"].dropna().clip(-1, 5), bins=40, alpha=0.5, label="No-bolus", color="C1", density=True)
axes[1].set_xlabel("Basal ratio (net / scheduled)")
axes[1].set_title(f"Basal ratio: Bolus={bolus_ev['basal_ratio'].median():.2f}, Null={null_ev['basal_ratio'].median():.2f}")
axes[1].legend()

# 3c: Summary
iob_diff = bolus_ev["iob_at"].median() - null_ev["iob_at"].median()
br_bolus = bolus_ev["basal_ratio"].median()
br_null = null_ev["basal_ratio"].median()
summary = (
    f"IOB at event:\n"
    f"  Bolus:    {bolus_ev['iob_at'].median():.2f} U\n"
    f"  No-bolus: {null_ev['iob_at'].median():.2f} U\n"
    f"  Diff:     {iob_diff:+.2f} U\n\n"
    f"Basal ratio (net/sched):\n"
    f"  Bolus:    {br_bolus:.2f}\n"
    f"  No-bolus: {br_null:.2f}\n\n"
    f"Interpretation:\n"
    f"  {'Higher' if iob_diff > 0 else 'Lower'} IOB at bolus events\n"
    f"  suggests {'more' if iob_diff > 0 else 'less'} prior insulin\n"
    f"  activity (controller was already dosing)."
)
axes[2].text(0.05, 0.5, summary, transform=axes[2].transAxes, fontsize=11,
            va="center", fontfamily="monospace")
axes[2].axis("off")

plt.suptitle("EXP-2689: Controller State at Event Time", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_controller_state.png", dpi=150)
plt.close()
print("Panel 3: Controller state saved")

# ── Panel 4: BG₀-matched within-patient ──────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# For patients with both bolus and no-bolus events, compare drops at similar BG₀
matched_results = []
for pid in ev["patient_id"].unique():
    b = bolus_ev[(bolus_ev["patient_id"] == pid) & (bolus_ev["carbs_2h"] < 5)]
    n = null_ev[null_ev["patient_id"] == pid]
    
    if len(b) >= 10 and len(n) >= 20:
        # BG₀-bin match
        for bg_lo in range(180, 320, 20):
            bg_hi = bg_lo + 20
            bm = b[(b["bg0"] >= bg_lo) & (b["bg0"] < bg_hi)]
            nm = n[(n["bg0"] >= bg_lo) & (n["bg0"] < bg_hi)]
            if len(bm) >= 3 and len(nm) >= 5:
                matched_results.append({
                    "patient_id": pid, "bg_bin": bg_lo + 10,
                    "bolus_drop": bm["drop"].mean(),
                    "null_drop": nm["drop"].mean(),
                    "treatment_effect": bm["drop"].mean() - nm["drop"].mean(),
                    "controller": b["controller"].iloc[0],
                })

mr = pd.DataFrame(matched_results)
if len(mr) > 0:
    colors_ctrl = {"loop": "C0", "trio": "C1", "openaps": "C2"}
    for ctrl in ["loop", "trio", "openaps"]:
        mc = mr[mr["controller"] == ctrl]
        if len(mc) > 0:
            axes[0].scatter(mc["null_drop"], mc["bolus_drop"], alpha=0.5, s=40,
                          label=ctrl.upper(), color=colors_ctrl[ctrl])
    lim = [-50, 150]
    axes[0].plot(lim, lim, "k--", alpha=0.5)
    axes[0].set_xlabel("Null drop (mg/dL)")
    axes[0].set_ylabel("Bolus drop (mg/dL)")
    axes[0].set_title("BG₀-Matched: Bolus vs Null Drop\n(correction boluses only)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Treatment effect distribution
    axes[1].hist(mr["treatment_effect"], bins=30, color="C2", alpha=0.7, edgecolor="k")
    axes[1].axvline(0, color="k", ls="--")
    axes[1].axvline(mr["treatment_effect"].median(), color="red", ls="--", lw=2,
                   label=f"Median: {mr['treatment_effect'].median():.1f}")
    axes[1].set_xlabel("Treatment effect (bolus − null, mg/dL)")
    axes[1].set_title("Within-Patient BG₀-Matched Treatment Effect")
    axes[1].legend()
else:
    axes[0].text(0.5, 0.5, "Insufficient matched data", ha="center", transform=axes[0].transAxes)
    axes[1].text(0.5, 0.5, "Insufficient matched data", ha="center", transform=axes[1].transAxes)

plt.suptitle("EXP-2689: Within-Patient Matched Comparison", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_matched.png", dpi=150)
plt.close()
print("Panel 4: Matched comparison saved")

# ── Panel 5: Stratify by pre-event slope (rising vs falling BG) ──────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Compare bolus and null events with FALLING pre-BG only
for i, (label, subset) in enumerate([("BG FALLING (slope<0)", ev[ev["pre_slope"] < 0]),
                                       ("BG RISING (slope>0)", ev[ev["pre_slope"] > 0])]):
    b = subset[subset["event_type"] == "bolus"]
    n = subset[subset["event_type"] == "no_bolus"]
    
    axes[i].hist(b["drop"], bins=40, alpha=0.5, label=f"Bolus (n={len(b)})", color="C0", density=True)
    axes[i].hist(n["drop"], bins=40, alpha=0.5, label=f"No-bolus (n={len(n)})", color="C1", density=True)
    axes[i].axvline(b["drop"].median(), color="C0", ls="--", lw=2)
    axes[i].axvline(n["drop"].median(), color="C1", ls="--", lw=2)
    
    diff = b["drop"].median() - n["drop"].median()
    axes[i].set_title(f"{label}\nBolus: {b['drop'].median():.0f}, Null: {n['drop'].median():.0f}, Δ={diff:.0f}")
    axes[i].set_xlabel("BG drop (mg/dL)")
    axes[i].legend()

plt.suptitle("EXP-2689: BG Drop Stratified by Pre-Event Trajectory", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_slope_stratified.png", dpi=150)
plt.close()
print("Panel 5: Slope-stratified saved")

# ── Panel 6: Comprehensive confound summary ──────────────────────────
fig, ax = plt.subplots(figsize=(12, 8))
ax.axis("off")

# Compute summary stats
correction_drop = bolus_correction["drop"].median()
meal_drop = bolus_meal["drop"].median()
null_drop = null_ev["drop"].median()

falling_b = ev[(ev["pre_slope"] < 0) & (ev["event_type"] == "bolus")]["drop"].median()
falling_n = ev[(ev["pre_slope"] < 0) & (ev["event_type"] == "no_bolus")]["drop"].median()
rising_b = ev[(ev["pre_slope"] > 0) & (ev["event_type"] == "bolus")]["drop"].median()
rising_n = ev[(ev["pre_slope"] > 0) & (ev["event_type"] == "no_bolus")]["drop"].median()

matched_te = mr["treatment_effect"].median() if len(mr) > 0 else np.nan

summary_text = f"""
EXP-2689: CONFOUNDING BY INDICATION — SUMMARY

WHY DO BOLUS EVENTS DROP LESS THAN NO-BOLUS EVENTS?

1. CONCURRENT MEALS (primary confound):
   Correction bolus (no carbs):  {correction_drop:.0f} mg/dL drop
   Meal bolus (carbs ≥ 5g):      {meal_drop:.0f} mg/dL drop
   No-bolus (null model):        {null_drop:.0f} mg/dL drop
   → Meal boluses fight rising carbs, reducing observed drop

2. PRE-EVENT TRAJECTORY (secondary confound):
   Users bolus when BG is {('RISING' if bolus_ev['pre_slope'].median() > null_ev['pre_slope'].median() else 'FALLING')} more than no-bolus events
   Bolus pre-slope: {bolus_ev['pre_slope'].median():.3f} mg/dL/5min
   Null pre-slope:  {null_ev['pre_slope'].median():.3f} mg/dL/5min
   
   BG FALLING:  Bolus={falling_b:.0f}, Null={falling_n:.0f}, Δ={falling_b-falling_n:.0f}
   BG RISING:   Bolus={rising_b:.0f}, Null={rising_n:.0f}, Δ={rising_b-rising_n:.0f}

3. CONTROLLER STATE (confound direction):
   IOB at bolus: {bolus_ev['iob_at'].median():.2f} U vs null: {null_ev['iob_at'].median():.2f} U
   → {'Controller already dosing more heavily at bolus events' if bolus_ev['iob_at'].median() > null_ev['iob_at'].median() else 'Lower IOB at bolus events'}

4. WITHIN-PATIENT BG₀-MATCHED:
   Treatment effect: {matched_te:.1f} mg/dL (positive = bolus helps)
   → {'Bolus HELPS after controlling for confounds' if matched_te > 5 else 'Minimal/no treatment effect even after matching' if -5 <= matched_te <= 5 else 'Bolus still HURTS after matching (deeper confounding)'}

CONCLUSION:
The negative "treatment effect" from EXP-2687 is {'explained by' if abs(matched_te) < 10 else 'partially explained by'} confounding.
Users bolus in harder situations (rising BG, concurrent meals, controller already maxed).
"""

ax.text(0.05, 0.95, summary_text, transform=ax.transAxes, fontsize=10,
        va="top", fontfamily="monospace")

plt.suptitle("EXP-2689: Confounding Summary", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_summary.png", dpi=150)
plt.close()
print("Panel 6: Summary saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2689",
    "title": "Confounding by Indication Analysis",
    "bolus_events": int(len(bolus_ev)),
    "null_events": int(len(null_ev)),
    "correction_bolus_n": int(len(bolus_correction)),
    "meal_bolus_n": int(len(bolus_meal)),
    "correction_drop_median": float(correction_drop),
    "meal_drop_median": float(meal_drop),
    "null_drop_median": float(null_drop),
    "bolus_pre_slope": float(bolus_ev["pre_slope"].median()),
    "null_pre_slope": float(null_ev["pre_slope"].median()),
    "pre_slope_p": float(p),
    "bolus_iob_median": float(bolus_ev["iob_at"].median()),
    "null_iob_median": float(null_ev["iob_at"].median()),
    "matched_treatment_effect": float(matched_te) if not np.isnan(matched_te) else None,
    "falling_bg_bolus_drop": float(falling_b),
    "falling_bg_null_drop": float(falling_n),
    "rising_bg_bolus_drop": float(rising_b),
    "rising_bg_null_drop": float(rising_n),
}
(EXP / "exp-2689_confounding.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2689: Confounding by Indication — KEY NUMBERS
{'='*60}

  Correction bolus drop: {correction_drop:.0f} mg/dL (n={len(bolus_correction)})
  Meal bolus drop:       {meal_drop:.0f} mg/dL (n={len(bolus_meal)})
  No-bolus (null):       {null_drop:.0f} mg/dL (n={len(null_ev)})
  
  Pre-slope: bolus={bolus_ev['pre_slope'].median():.3f}, null={null_ev['pre_slope'].median():.3f}
  IOB at event: bolus={bolus_ev['iob_at'].median():.2f}U, null={null_ev['iob_at'].median():.2f}U
  
  BG₀-matched treatment effect: {matched_te:.1f} mg/dL
  
  Stratified by trajectory:
    Falling BG: bolus={falling_b:.0f}, null={falling_n:.0f}, Δ={falling_b-falling_n:.0f}
    Rising BG:  bolus={rising_b:.0f}, null={rising_n:.0f}, Δ={rising_b-rising_n:.0f}
""")
