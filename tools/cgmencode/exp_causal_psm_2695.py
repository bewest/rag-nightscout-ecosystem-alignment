#!/usr/bin/env python3
"""EXP-2695: Propensity Score Matching for Causal Bolus Effect

The fundamental problem: in closed-loop AID, the controller co-intervenes
through multiple channels, creating confounding by indication. Simple regression
yields NEGATIVE coefficients for insulin (EXP-2692).

Solution: Propensity Score Matching (PSM). Match treatment events (user bolus)
to control events (no user bolus) based on observable pre-treatment confounders:
  - Starting BG (bg0)
  - BG rate of change (roc_start)
  - IOB at event start (iob_start)
  - Recent carbs (carbs before event)
  - Controller type
  - Time of day (circadian confound)

Then compare matched outcomes. The matched difference is our best causal estimate
of the bolus effect.

Panels:
  1. Propensity score distribution: treatment vs control
  2. Covariate balance before/after matching (Love plot)
  3. Matched BG trajectories: bolus vs no-bolus
  4. Dose-response within matched bolus events
  5. Controller-stratified matched effects
  6. Sensitivity analysis: varying caliper width
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from scipy.spatial.distance import cdist
from numpy.linalg import lstsq

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/causal-psm")
OUT.mkdir(parents=True, exist_ok=True)
EXP = pathlib.Path("externals/experiments")

# ── Load data ──────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid["controller"] = grid["patient_id"].map(ctrl_map)

manifest = json.loads((EXP / "autoprepare-qualified.json").read_text())
qual = manifest["qualified_patients"]
grid = grid[grid["patient_id"].isin(qual)].copy()
grid["time"] = pd.to_datetime(grid["time"], utc=True)
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

FLOOR = 180
HORIZON = 24  # 120 min
HORIZONS = [6, 12, 18, 24]  # 30, 60, 90, 120 min

# ── Extract events with pre-treatment covariates ──────────────────────
print("Extracting events with pre-treatment covariates...")
events = []
for pid in grid["patient_id"].unique():
    pg = grid[grid["patient_id"] == pid].reset_index(drop=True)
    ctrl = pg["controller"].iloc[0]
    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    smb = pg["bolus_smb"].values if "bolus_smb" in pg.columns else np.zeros(len(pg))
    net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.full(len(pg), np.nan)
    sched_basal = pg["scheduled_basal_rate"].values if "scheduled_basal_rate" in pg.columns else np.full(len(pg), np.nan)
    iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
    carbs_col = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
    roc = pg["glucose_roc"].values if "glucose_roc" in pg.columns else np.full(len(pg), np.nan)
    times = pg["time"].values

    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        if np.isnan(bg0) or bg0 < FLOOR:
            continue

        # Check all horizons
        bg_at = {}
        valid = True
        for h in HORIZONS:
            bgh = glucose[i + h]
            if np.isnan(bgh):
                valid = False
                break
            bg_at[h] = bgh
        if not valid:
            continue

        # Pre-treatment covariates
        roc_start = roc[i] if not np.isnan(roc[i]) else 0
        iob_start = iob[i] if not np.isnan(iob[i]) else 0

        # Carbs in prior 30 min (pre-treatment)
        carbs_prior = np.nansum(carbs_col[max(0, i-6):i])

        # Hour of day (circadian)
        try:
            hour = pd.Timestamp(times[i]).hour
        except Exception:
            hour = 12

        # Treatment: user bolus in first 15 min (3 steps)
        bolus_15m = np.nansum(bolus[i:i+3])
        treatment = 1 if bolus_15m > 0.3 else 0

        # Outcome channels at each horizon
        event = {
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "roc_start": roc_start, "iob_start": iob_start,
            "carbs_prior": carbs_prior, "hour": hour,
            "treatment": treatment, "bolus_dose": bolus_15m,
            "ctrl_loop": 1 if ctrl == "loop" else 0,
            "ctrl_trio": 1 if ctrl == "trio" else 0,
        }
        for h in HORIZONS:
            mins = h * 5
            event[f"bg_{mins}m"] = bg_at[h]
            event[f"drop_{mins}m"] = bg0 - bg_at[h]
            event[f"smb_{mins}m"] = np.nansum(smb[i:i+h])
            basal_int = np.nansum(net_basal[i:i+h]) * (5.0/60.0)
            sched_int = np.nansum(sched_basal[i:i+h]) * (5.0/60.0)
            event[f"excess_basal_{mins}m"] = basal_int - sched_int

        events.append(event)

ev = pd.DataFrame(events)
treated = ev[ev["treatment"] == 1]
control = ev[ev["treatment"] == 0]
print(f"  Total events: {len(ev)} (treated={len(treated)}, control={len(control)})")

# ── Step 1: Propensity score estimation (logistic via OLS approx) ─────
print("Estimating propensity scores...")
ps_features = ["bg0", "roc_start", "iob_start", "carbs_prior", "hour",
               "ctrl_loop", "ctrl_trio"]
ps_data = ev[ps_features + ["treatment"]].dropna()

X_ps = ps_data[ps_features].values
y_ps = ps_data["treatment"].values

# Standardize
X_mean = X_ps.mean(axis=0)
X_std = X_ps.std(axis=0) + 1e-10
X_ps_n = (X_ps - X_mean) / X_std

# Logistic approximation via iteratively reweighted least squares (simplified)
# Use linear probability model for speed, clip to [0.01, 0.99]
X_ps_aug = np.column_stack([X_ps_n, np.ones(len(X_ps_n))])
b_ps, _, _, _ = lstsq(X_ps_aug, y_ps, rcond=None)
ps_raw = X_ps_aug @ b_ps
ps = np.clip(ps_raw, 0.01, 0.99)
ev_ps = ps_data.copy()
ev_ps["ps"] = ps
ev_ps.index = ps_data.index

# Merge ps back
ev["ps"] = np.nan
ev.loc[ev_ps.index, "ps"] = ev_ps["ps"]

# ── Step 2: Nearest-neighbor matching ─────────────────────────────────
print("Matching treatment to control events...")

treated_ps = ev[(ev["treatment"] == 1) & ev["ps"].notna()].copy()
control_ps = ev[(ev["treatment"] == 0) & ev["ps"].notna()].copy()

CALIPER = 0.05  # max PS distance for match

# Match features: PS + BG band (exact match on BG band for tighter control)
treated_ps["bg_band"] = pd.cut(treated_ps["bg0"], bins=[180, 200, 220, 250, 300, 500],
                                labels=[0, 1, 2, 3, 4]).astype(float)
control_ps["bg_band"] = pd.cut(control_ps["bg0"], bins=[180, 200, 220, 250, 300, 500],
                                labels=[0, 1, 2, 3, 4]).astype(float)

matched_treat = []
matched_ctrl = []
used_ctrl = set()

for bg_band in range(5):
    t_band = treated_ps[treated_ps["bg_band"] == bg_band]
    c_band = control_ps[control_ps["bg_band"] == bg_band]

    if len(t_band) == 0 or len(c_band) == 0:
        continue

    t_ps_vals = t_band["ps"].values.reshape(-1, 1)
    c_ps_vals = c_band["ps"].values.reshape(-1, 1)

    # Distance matrix
    dist = cdist(t_ps_vals, c_ps_vals, metric="euclidean")

    for i in range(len(t_band)):
        # Find nearest unused control
        dists = dist[i]
        sorted_idx = np.argsort(dists)
        for j in sorted_idx:
            c_idx = c_band.index[j]
            if c_idx not in used_ctrl and dists[j] <= CALIPER:
                matched_treat.append(t_band.index[i])
                matched_ctrl.append(c_idx)
                used_ctrl.add(c_idx)
                break

print(f"  Matched pairs: {len(matched_treat)}")

mt = ev.loc[matched_treat].copy()
mc = ev.loc[matched_ctrl].copy()

# ── Panel 1: Propensity score distributions ───────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 1a: Before matching
axes[0].hist(treated_ps["ps"], bins=50, alpha=0.5, color="C3", label=f"Bolus (n={len(treated_ps)})", density=True)
axes[0].hist(control_ps["ps"], bins=50, alpha=0.5, color="C0", label=f"No bolus (n={len(control_ps)})", density=True)
axes[0].set_xlabel("Propensity Score")
axes[0].set_ylabel("Density")
axes[0].set_title("Before Matching")
axes[0].legend()

# 1b: After matching
axes[1].hist(mt["ps"], bins=50, alpha=0.5, color="C3", label=f"Bolus (n={len(mt)})", density=True)
axes[1].hist(mc["ps"], bins=50, alpha=0.5, color="C0", label=f"No bolus (n={len(mc)})", density=True)
axes[1].set_xlabel("Propensity Score")
axes[1].set_ylabel("Density")
axes[1].set_title("After Matching")
axes[1].legend()

plt.suptitle("EXP-2695: Propensity Score Distributions", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_ps_distribution.png", dpi=150)
plt.close()
print("Panel 1: PS distributions saved")

# ── Panel 2: Covariate balance (Love plot) ────────────────────────────
fig, ax = plt.subplots(figsize=(10, 7))

balance_vars = ["bg0", "roc_start", "iob_start", "carbs_prior", "hour"]
smd_before = []
smd_after = []

for var in balance_vars:
    # Before matching
    t_mean = treated_ps[var].mean()
    c_mean = control_ps[var].mean()
    pooled_sd = np.sqrt((treated_ps[var].var() + control_ps[var].var()) / 2)
    smd_b = (t_mean - c_mean) / (pooled_sd + 1e-10)
    smd_before.append(abs(smd_b))

    # After matching
    t_mean_a = mt[var].mean()
    c_mean_a = mc[var].mean()
    pooled_sd_a = np.sqrt((mt[var].var() + mc[var].var()) / 2)
    smd_a = (t_mean_a - c_mean_a) / (pooled_sd_a + 1e-10)
    smd_after.append(abs(smd_a))

y_pos = range(len(balance_vars))
ax.scatter(smd_before, y_pos, marker="x", s=100, color="C3", zorder=3, label="Before matching")
ax.scatter(smd_after, y_pos, marker="o", s=100, color="C0", zorder=3, label="After matching")
ax.set_yticks(y_pos)
ax.set_yticklabels(balance_vars)
ax.axvline(0.1, color="k", ls="--", alpha=0.5, label="0.1 threshold")
ax.set_xlabel("|Standardized Mean Difference|")
ax.set_title("Covariate Balance: Before vs After Matching")
ax.legend()
ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2695: Love Plot — Covariate Balance", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_love_plot.png", dpi=150)
plt.close()
print("Panel 2: Love plot saved")

# ── Panel 3: Matched BG trajectories ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 3a: Mean trajectories
for group, data, color, label in [("Bolus", mt, "C3", "Bolus (matched)"),
                                   ("No bolus", mc, "C0", "No bolus (matched)")]:
    traj = [data["bg0"].mean()]
    traj_se = [data["bg0"].sem()]
    for h in HORIZONS:
        mins = h * 5
        traj.append(data[f"bg_{mins}m"].mean())
        traj_se.append(data[f"bg_{mins}m"].sem())

    times = [0] + [h * 5 for h in HORIZONS]
    axes[0].plot(times, traj, "o-", color=color, lw=2.5, markersize=8, label=label)
    traj = np.array(traj)
    traj_se = np.array(traj_se)
    axes[0].fill_between(times, traj - 1.96 * traj_se, traj + 1.96 * traj_se,
                         alpha=0.2, color=color)

axes[0].set_xlabel("Time (minutes)")
axes[0].set_ylabel("Mean BG (mg/dL)")
axes[0].set_title(f"PS-Matched BG Trajectories (n={len(mt)} pairs)")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 3b: Treatment effect over time
att = []  # average treatment effect on treated
att_se = []
att_p = []
for h in HORIZONS:
    mins = h * 5
    diff = mt[f"drop_{mins}m"].values - mc[f"drop_{mins}m"].values
    att.append(diff.mean())
    att_se.append(diff.std() / np.sqrt(len(diff)))
    t_stat, p_val = stats.ttest_rel(mt[f"drop_{mins}m"].values, mc[f"drop_{mins}m"].values)
    att_p.append(p_val)

times = [h * 5 for h in HORIZONS]
att = np.array(att)
att_se = np.array(att_se)

bars = axes[1].bar(range(len(HORIZONS)), att, color=["C2" if a > 0 else "C3" for a in att],
                   edgecolor="k", alpha=0.7)
axes[1].errorbar(range(len(HORIZONS)), att, yerr=1.96 * att_se, fmt="none",
                color="k", capsize=6, lw=2)
axes[1].set_xticks(range(len(HORIZONS)))
axes[1].set_xticklabels([f"{h*5}m\np={p:.3f}" for h, p in zip(HORIZONS, att_p)])
axes[1].set_ylabel("ATT: Extra BG drop from bolus (mg/dL)")
axes[1].axhline(0, color="k", ls="--")
axes[1].set_title("Average Treatment Effect on Treated (ATT)")
axes[1].grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2695: Propensity Score Matched Causal Estimates", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_matched_trajectories.png", dpi=150)
plt.close()
print(f"Panel 3: Matched trajectories saved (ATT at 120m = {att[-1]:+.1f} mg/dL)")

# ── Panel 4: Dose-response within matched bolus events ────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Within matched bolus events, does dose predict additional drop?
mt_bolus = mt[mt["bolus_dose"] > 0].copy()

# 4a: Dose vs BG drop (matched events only)
axes[0].scatter(mt_bolus["bolus_dose"], mt_bolus["drop_120m"], alpha=0.05, s=5, color="C3")

# Binned means
try:
    bins = pd.qcut(mt_bolus["bolus_dose"], 8, duplicates="drop")
    binned = mt_bolus.groupby(bins).agg(
        mean_dose=("bolus_dose", "mean"),
        mean_drop=("drop_120m", "mean"),
        se=("drop_120m", "sem"),
        n=("drop_120m", "count"),
    )
    axes[0].errorbar(binned["mean_dose"], binned["mean_drop"],
                    yerr=1.96 * binned["se"], fmt="ko-", lw=2, capsize=5, markersize=8,
                    zorder=5)
except Exception:
    pass

r_dose, p_dose = stats.pearsonr(mt_bolus["bolus_dose"].values, mt_bolus["drop_120m"].values)
axes[0].set_xlabel("Bolus Dose (U)")
axes[0].set_ylabel("BG Drop at 120m (mg/dL)")
axes[0].set_title(f"Dose-Response (matched bolus events)\nr={r_dose:.3f}, p={p_dose:.2e}")
axes[0].grid(True, alpha=0.3)

# 4b: Dose-stratified matched effects
if len(mt_bolus) >= 100:
    try:
        mt_bolus["dose_group"] = pd.qcut(mt_bolus["bolus_dose"], 3, labels=["Low", "Med", "High"])
        dose_effects = []
        for dg in ["Low", "Med", "High"]:
            t_group = mt_bolus[mt_bolus["dose_group"] == dg]
            c_group = mc.loc[t_group.index.intersection(mc.index)]
            if len(c_group) < 10:
                # Use all matched controls for comparison
                c_mean = mc["drop_120m"].mean()
                dose_effects.append({
                    "group": dg,
                    "mean_dose": t_group["bolus_dose"].mean(),
                    "mean_drop": t_group["drop_120m"].mean(),
                    "control_drop": c_mean,
                    "att": t_group["drop_120m"].mean() - c_mean,
                    "n": len(t_group),
                })
            else:
                dose_effects.append({
                    "group": dg,
                    "mean_dose": t_group["bolus_dose"].mean(),
                    "mean_drop": t_group["drop_120m"].mean(),
                    "control_drop": c_group["drop_120m"].mean(),
                    "att": t_group["drop_120m"].mean() - c_group["drop_120m"].mean(),
                    "n": len(t_group),
                })

        de = pd.DataFrame(dose_effects)
        bars = axes[1].bar(range(3), de["att"], color=["C0", "C1", "C3"],
                          edgecolor="k", alpha=0.7)
        axes[1].set_xticks(range(3))
        axes[1].set_xticklabels([f"{row['group']}\n({row['mean_dose']:.1f}U, n={row['n']})"
                                for _, row in de.iterrows()])
        for bar, val in zip(bars, de["att"]):
            axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                        f"{val:+.1f}", ha="center", fontsize=11)
        axes[1].set_ylabel("ATT (extra BG drop, mg/dL)")
        axes[1].set_title("ATT by Dose Group")
        axes[1].axhline(0, color="k", ls="--")
        axes[1].grid(True, alpha=0.3, axis="y")
    except Exception as e:
        axes[1].text(0.5, 0.5, f"Insufficient data\n{e}", transform=axes[1].transAxes,
                    ha="center", fontsize=12)

plt.suptitle("EXP-2695: Within-Bolus Dose-Response", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_dose_response.png", dpi=150)
plt.close()
print("Panel 4: Dose-response saved")

# ── Panel 5: Controller-stratified matched effects ────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

controllers = ["loop", "trio", "openaps"]
ctrl_atts = {}

for ax, ctrl in zip(axes, controllers):
    mt_c = mt[mt["controller"] == ctrl]
    mc_c = mc[mc["controller"] == ctrl]

    if len(mt_c) < 20:
        ax.set_title(f"{ctrl.upper()}: insufficient matched pairs")
        continue

    # Re-match within controller
    ctrl_att = []
    ctrl_att_se = []
    for h in HORIZONS:
        mins = h * 5
        # Use all matched pairs for this controller
        t_drops = mt_c[f"drop_{mins}m"].values
        c_drops = mc_c[f"drop_{mins}m"].values
        min_n = min(len(t_drops), len(c_drops))
        diff = t_drops[:min_n] - c_drops[:min_n]
        ctrl_att.append(diff.mean())
        ctrl_att_se.append(diff.std() / np.sqrt(len(diff)))

    ctrl_atts[ctrl] = ctrl_att

    times = [h * 5 for h in HORIZONS]
    ctrl_att = np.array(ctrl_att)
    ctrl_att_se = np.array(ctrl_att_se)

    ax.bar(range(len(HORIZONS)), ctrl_att,
          color=["C2" if a > 0 else "C3" for a in ctrl_att],
          edgecolor="k", alpha=0.7)
    ax.errorbar(range(len(HORIZONS)), ctrl_att, yerr=1.96 * ctrl_att_se,
               fmt="none", color="k", capsize=6, lw=2)
    ax.set_xticks(range(len(HORIZONS)))
    ax.set_xticklabels([f"{h*5}m" for h in HORIZONS])
    ax.set_ylabel("ATT (mg/dL)")
    ax.set_title(f"{ctrl.upper()} (n={len(mt_c)} pairs)")
    ax.axhline(0, color="k", ls="--")
    ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2695: Controller-Stratified Causal Effects", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_controller_att.png", dpi=150)
plt.close()
print("Panel 5: Controller ATT saved")

# ── Panel 6: Sensitivity + channel compensation ──────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 6a: Sensitivity to caliper width — use existing matches + filter by distance
calipers = [0.01, 0.02, 0.05, 0.10, 0.20]
caliper_atts = []
caliper_ns = []

# Compute PS distance for existing matched pairs
ps_dist = np.abs(mt["ps"].values - mc["ps"].values)

for cal in calipers:
    mask = ps_dist <= cal
    if mask.sum() > 0:
        t_drops = mt.loc[mt.index[mask], "drop_120m"].values
        c_drops = mc.loc[mc.index[mask], "drop_120m"].values
        diff = t_drops - c_drops
        caliper_atts.append(np.nanmean(diff))
        caliper_ns.append(int(mask.sum()))
    else:
        caliper_atts.append(np.nan)
        caliper_ns.append(0)

ax2 = axes[0].twinx()
axes[0].plot(calipers, caliper_atts, "o-", color="C0", lw=2.5, markersize=8, label="ATT")
ax2.plot(calipers, caliper_ns, "s--", color="C3", lw=1.5, markersize=6, label="N pairs")
axes[0].set_xlabel("Caliper Width")
axes[0].set_ylabel("ATT at 120m (mg/dL)", color="C0")
ax2.set_ylabel("Number of Matched Pairs", color="C3")
axes[0].set_title("Sensitivity to Caliper Width")
axes[0].axhline(0, color="k", ls=":", alpha=0.5)
axes[0].legend(loc="upper left")
ax2.legend(loc="upper right")

# 6b: Channel compensation — how does controller respond differently?
comp_data = []
for label, data in [("Bolus (matched)", mt), ("No bolus (matched)", mc)]:
    comp_data.append({
        "Group": label,
        "SMB 2h (U)": data["smb_120m"].mean(),
        "Excess basal (U)": data["excess_basal_120m"].mean(),
        "BG drop (mg/dL)": data["drop_120m"].mean(),
    })

comp = pd.DataFrame(comp_data).set_index("Group")
comp[["SMB 2h (U)", "Excess basal (U)"]].plot(kind="barh", ax=axes[1],
    color=["C1", "C2"], edgecolor="k", alpha=0.7)
axes[1].set_xlabel("Mean Value")
axes[1].set_title("Controller Channel Compensation\n(PS-Matched Events)")
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis="x")

plt.suptitle("EXP-2695: Sensitivity & Channel Compensation", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_sensitivity.png", dpi=150)
plt.close()
print("Panel 6: Sensitivity saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2695",
    "title": "Propensity Score Matching for Causal Bolus Effect",
    "n_total": int(len(ev)),
    "n_treated": int(len(treated)),
    "n_control": int(len(control)),
    "n_matched_pairs": int(len(matched_treat)),
    "caliper": float(CALIPER),
    "covariate_balance": {
        v: {"smd_before": float(b), "smd_after": float(a)}
        for v, b, a in zip(balance_vars, smd_before, smd_after)
    },
    "att_by_horizon": {
        f"{h*5}m": {"att": float(a), "se": float(s), "p": float(p)}
        for h, a, s, p in zip(HORIZONS, att, att_se, att_p)
    },
    "channel_compensation": {
        "bolus_group": {"smb_2h": float(mt["smb_120m"].mean()),
                       "excess_basal_2h": float(mt["excess_basal_120m"].mean())},
        "no_bolus_group": {"smb_2h": float(mc["smb_120m"].mean()),
                          "excess_basal_2h": float(mc["excess_basal_120m"].mean())},
    },
    "sensitivity": {
        str(c): {"att": float(a), "n": int(n)}
        for c, a, n in zip(calipers, caliper_atts, caliper_ns)
    },
}
(EXP / "exp-2695_causal_psm.json").write_text(json.dumps(results, indent=2))

print(f"""
{'='*60}
EXP-2695: Propensity Score Matching — CAUSAL ESTIMATES
{'='*60}

  Matched pairs: {len(matched_treat)}
  Caliper: {CALIPER}

  COVARIATE BALANCE (|SMD| before → after):""")
for v, b, a in zip(balance_vars, smd_before, smd_after):
    print(f"    {v:15s}: {b:.3f} → {a:.3f} {'✓' if a < 0.1 else '✗'}")

print(f"""
  AVERAGE TREATMENT EFFECT ON TREATED (ATT):""")
for h, a, s, p in zip(HORIZONS, att, att_se, att_p):
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"    {h*5:3d} min: {a:+.1f} mg/dL (SE={s:.1f}, p={p:.3f}) {sig}")

print(f"""
  CHANNEL COMPENSATION (PS-matched):
    Bolus group: SMB={mt['smb_120m'].mean():.2f}U, excess_basal={mt['excess_basal_120m'].mean():.2f}U
    No-bolus:    SMB={mc['smb_120m'].mean():.2f}U, excess_basal={mc['excess_basal_120m'].mean():.2f}U

  SENSITIVITY TO CALIPER:""")
for c, a, n in zip(calipers, caliper_atts, caliper_ns):
    print(f"    caliper={c:.2f}: ATT={a:+.1f}, n={n}")
