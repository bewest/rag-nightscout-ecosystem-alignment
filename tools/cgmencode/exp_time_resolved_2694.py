#!/usr/bin/env python3
"""EXP-2694: Time-Resolved Channel Decomposition

How do insulin channel effects evolve over time?
  - 0-30 min: Bolus onset, controller initial response
  - 30-60 min: SMB accumulation, peak bolus effect
  - 60-120 min: Full insulin curve, controller adaptation

Also addresses the negative coefficient paradox from EXP-2692: in closed-loop,
more insulin is given in HARDER situations (confounding by indication). By
looking at temporal evolution, we can separate the acute pharmacological effect
from the controller's strategic response.

Panels:
  1. Channel R² at each horizon (6, 12, 18, 24 steps = 30-120 min)
  2. Marginal effects vs time (how does bolus/SMB coefficient evolve?)
  3. Per-controller temporal profiles
  4. BG trajectory by insulin quartile (direct visualization)
  5. Matched comparison: high-bolus vs low-bolus at same starting BG
  6. Controller decision timing: when do SMBs fire relative to bolus?
"""

import json, pathlib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from numpy.linalg import lstsq

warnings.filterwarnings("ignore")
OUT = pathlib.Path("visualizations/time-resolved")
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
grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

FLOOR = 180
HORIZONS = [6, 12, 18, 24]  # steps (30, 60, 90, 120 min)
HORIZON_LABELS = ["30 min", "60 min", "90 min", "120 min"]
controllers = ["loop", "trio", "openaps"]
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# ── Extract time-resolved events ──────────────────────────────────────
print("Extracting time-resolved events...")
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

    for i in range(max(HORIZONS), len(pg) - max(HORIZONS)):
        bg0 = glucose[i]
        if np.isnan(bg0) or bg0 < FLOOR:
            continue

        # Check all horizons have valid glucose
        bg_at_horizons = {}
        valid = True
        for h in HORIZONS:
            bg_h = glucose[i + h]
            if np.isnan(bg_h):
                valid = False
                break
            bg_at_horizons[h] = bg_h
        if not valid:
            continue

        roc_start = roc[i] if not np.isnan(roc[i]) else 0
        iob_start = iob[i] if not np.isnan(iob[i]) else 0

        # Cumulative insulin at each horizon
        event = {
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "roc_start": roc_start, "iob_start": iob_start,
        }
        for h in HORIZONS:
            event[f"bg_{h*5}m"] = bg_at_horizons[h]
            event[f"drop_{h*5}m"] = bg0 - bg_at_horizons[h]
            event[f"bolus_{h*5}m"] = np.nansum(bolus[i:i+h])
            event[f"smb_{h*5}m"] = np.nansum(smb[i:i+h])
            basal_int = np.nansum(net_basal[i:i+h]) * (5.0/60.0)
            sched_int = np.nansum(sched_basal[i:i+h]) * (5.0/60.0)
            event[f"excess_basal_{h*5}m"] = basal_int - sched_int
            event[f"carbs_{h*5}m"] = np.nansum(carbs_col[i:i+h])
            event[f"total_insulin_{h*5}m"] = (event[f"bolus_{h*5}m"] +
                                               event[f"smb_{h*5}m"] + basal_int)
        events.append(event)

ev = pd.DataFrame(events)
print(f"  Events: {len(ev)}")

# ── Panel 1: R² at each horizon ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))

r2_by_horizon = {}
for h_idx, h in enumerate(HORIZONS):
    mins = h * 5
    features = ["bg0", f"bolus_{mins}m", f"smb_{mins}m", f"excess_basal_{mins}m",
                f"carbs_{mins}m", "roc_start", "iob_start"]
    clean = ev[features + [f"drop_{mins}m"]].dropna()
    X = clean[features].values
    y = clean[f"drop_{mins}m"].values

    X_n = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-10)
    X_n = np.column_stack([X_n, np.ones(len(X_n))])
    b, _, _, _ = lstsq(X_n, y, rcond=None)
    y_pred = X_n @ b
    r2 = 1 - np.sum((y - y_pred)**2) / np.sum((y - y.mean())**2)

    # Unique R² for each feature
    unique_r2 = {}
    for j, feat in enumerate(features):
        X_reduced = np.delete(X, j, axis=1)
        X_r = (X_reduced - X_reduced.mean(axis=0)) / (X_reduced.std(axis=0) + 1e-10)
        X_r = np.column_stack([X_r, np.ones(len(X_r))])
        b_r, _, _, _ = lstsq(X_r, y, rcond=None)
        y_r = X_r @ b_r
        r2_r = 1 - np.sum((y - y_r)**2) / np.sum((y - y.mean())**2)
        unique_r2[feat] = max(r2 - r2_r, 0)

    r2_by_horizon[mins] = {"total": r2, "unique": unique_r2, "n": len(clean)}

# Plot stacked R²
channel_colors = {"bg0": "gray", "bolus": "C0", "smb": "C1", "excess_basal": "C2",
                  "carbs": "C4", "roc_start": "C5", "iob_start": "C6"}
bottom = np.zeros(len(HORIZONS))
for feat_short, color in [("bg0", "gray"), ("bolus", "C0"), ("smb", "C1"),
                           ("excess_basal", "C2"), ("carbs", "C4"),
                           ("roc_start", "C5"), ("iob_start", "C6")]:
    vals = []
    for h_idx, h in enumerate(HORIZONS):
        mins = h * 5
        # Map short name to full name
        for key in r2_by_horizon[mins]["unique"]:
            if feat_short in key:
                vals.append(r2_by_horizon[mins]["unique"][key])
                break
        else:
            vals.append(0)
    vals = np.array(vals)
    ax.bar(range(len(HORIZONS)), vals, bottom=bottom, color=color,
           label=feat_short, alpha=0.7, edgecolor="k")
    bottom += vals

# Total R² line
total_r2 = [r2_by_horizon[h*5]["total"] for h in HORIZONS]
ax.plot(range(len(HORIZONS)), total_r2, "ko-", markersize=8, lw=2, label="Total R²")

ax.set_xticks(range(len(HORIZONS)))
ax.set_xticklabels(HORIZON_LABELS)
ax.set_ylabel("R² (unique contribution)")
ax.set_title("Channel Contributions to BG Drop at Each Horizon")
ax.legend(loc="upper left", fontsize=9)
ax.grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2694: Time-Resolved R² Decomposition", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_r2_by_horizon.png", dpi=150)
plt.close()
print("Panel 1: R² by horizon saved")

# ── Panel 2: Marginal effects vs time ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Raw coefficients at each horizon
coefs_by_horizon = {}
for h_idx, h in enumerate(HORIZONS):
    mins = h * 5
    features = ["bg0", f"bolus_{mins}m", f"smb_{mins}m", f"excess_basal_{mins}m",
                f"carbs_{mins}m", "roc_start", "iob_start"]
    clean = ev[features + [f"drop_{mins}m"]].dropna()
    X = clean[features].values
    y = clean[f"drop_{mins}m"].values
    X_aug = np.column_stack([X, np.ones(len(X))])
    b, _, _, _ = lstsq(X_aug, y, rcond=None)

    # SE
    n = len(y)
    sigma2 = np.sum((y - X_aug @ b)**2) / max(n - len(b), 1)
    try:
        cov = sigma2 * np.linalg.inv(X_aug.T @ X_aug)
        se = np.sqrt(np.diag(cov))[:-1]
    except Exception:
        se = np.full(len(features), np.nan)

    coefs_by_horizon[mins] = {
        f: {"beta": float(b[i]), "se": float(se[i])} for i, f in enumerate(features)
    }

# 2a: Insulin channel coefficients over time
times = [h * 5 for h in HORIZONS]
for channel, color, label in [("bolus", "C0", "Bolus"), ("smb", "C1", "SMB"),
                                ("excess_basal", "C2", "Excess Basal")]:
    betas = []
    ses = []
    for t in times:
        for key in coefs_by_horizon[t]:
            if channel in key and key != "iob_start":
                betas.append(coefs_by_horizon[t][key]["beta"])
                ses.append(coefs_by_horizon[t][key]["se"])
                break
        else:
            betas.append(0)
            ses.append(0)
    axes[0].errorbar(times, betas, yerr=[1.96*s for s in ses],
                    fmt="o-", color=color, lw=2, capsize=5, markersize=8, label=label)

axes[0].set_xlabel("Horizon (minutes)")
axes[0].set_ylabel("Marginal effect (mg/dL per U)")
axes[0].set_title("Insulin Channel Effects Over Time")
axes[0].axhline(0, color="k", ls="--", alpha=0.5)
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 2b: Non-insulin features
for feat, color, label in [("bg0", "gray", "BG₀ (per mg/dL)"),
                            ("roc_start", "C5", "ROC (per mg/dL/5min)"),
                            ("iob_start", "C6", "IOB₀ (per U)")]:
    betas = [coefs_by_horizon[t][feat]["beta"] for t in times]
    ses = [coefs_by_horizon[t][feat]["se"] for t in times]
    axes[1].errorbar(times, betas, yerr=[1.96*s for s in ses],
                    fmt="s-", color=color, lw=2, capsize=5, markersize=8, label=label)

axes[1].set_xlabel("Horizon (minutes)")
axes[1].set_ylabel("Marginal effect")
axes[1].set_title("Non-Insulin Features Over Time")
axes[1].axhline(0, color="k", ls="--", alpha=0.5)
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.suptitle("EXP-2694: Temporal Evolution of Marginal Effects", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_temporal_marginals.png", dpi=150)
plt.close()
print("Panel 2: Temporal marginals saved")

# ── Panel 3: Per-controller temporal profiles ─────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

for ax, ctrl in zip(axes, controllers):
    ec = ev[ev["controller"] == ctrl]
    for channel, color, label in [("bolus", "C0", "Bolus"), ("smb", "C1", "SMB"),
                                    ("excess_basal", "C2", "Excess Basal")]:
        betas = []
        ses = []
        for h in HORIZONS:
            mins = h * 5
            features = ["bg0", f"bolus_{mins}m", f"smb_{mins}m", f"excess_basal_{mins}m",
                        f"carbs_{mins}m", "roc_start", "iob_start"]
            clean = ec[features + [f"drop_{mins}m"]].dropna()
            if len(clean) < 100:
                betas.append(np.nan)
                ses.append(np.nan)
                continue
            X = clean[features].values
            y = clean[f"drop_{mins}m"].values
            X_aug = np.column_stack([X, np.ones(len(X))])
            b, _, _, _ = lstsq(X_aug, y, rcond=None)

            n = len(y)
            sigma2 = np.sum((y - X_aug @ b)**2) / max(n - len(b), 1)
            try:
                cov = sigma2 * np.linalg.inv(X_aug.T @ X_aug)
                se = np.sqrt(np.diag(cov))
            except Exception:
                se = np.full(len(b), np.nan)

            for j, f in enumerate(features):
                if channel in f and f != "iob_start":
                    betas.append(float(b[j]))
                    ses.append(float(se[j]))
                    break
            else:
                betas.append(np.nan)
                ses.append(np.nan)

        valid_idx = [i for i, b in enumerate(betas) if not np.isnan(b)]
        if valid_idx:
            t_vals = [HORIZONS[i] * 5 for i in valid_idx]
            b_vals = [betas[i] for i in valid_idx]
            s_vals = [1.96 * ses[i] for i in valid_idx]
            ax.errorbar(t_vals, b_vals, yerr=s_vals,
                       fmt="o-", color=color, lw=2, capsize=5, markersize=6, label=label)

    ax.set_xlabel("Horizon (minutes)")
    ax.set_ylabel("Marginal effect (mg/dL per U)")
    ax.set_title(f"{ctrl.upper()}")
    ax.axhline(0, color="k", ls="--", alpha=0.5)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2694: Controller-Specific Temporal Profiles", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_controller_temporal.png", dpi=150)
plt.close()
print("Panel 3: Controller temporal profiles saved")

# ── Panel 4: BG trajectory by bolus quartile ─────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

for ax, ctrl in zip(axes, controllers):
    ec = ev[ev["controller"] == ctrl].copy()
    if len(ec) < 100:
        ax.set_title(f"{ctrl.upper()}: insufficient data")
        continue

    # BG-matched comparison: within BG₀ bands, compare bolus quartiles
    ec["bg_band"] = pd.cut(ec["bg0"], bins=[180, 200, 250, 350], labels=["180-200", "200-250", "250+"])

    # Overall bolus quartiles (excluding zero-bolus)
    bolus_col = f"bolus_{HORIZONS[-1]*5}m"
    has_bolus = ec[ec[bolus_col] > 0]
    if len(has_bolus) < 20:
        ax.set_title(f"{ctrl.upper()}: too few bolus events")
        continue

    try:
        has_bolus["bolus_q"] = pd.qcut(has_bolus[bolus_col], 3, labels=["Low", "Med", "High"])
    except Exception:
        ax.set_title(f"{ctrl.upper()}: cannot quartile")
        continue

    # No-bolus group
    no_bolus = ec[ec[bolus_col] == 0].copy()
    no_bolus["bolus_q"] = "None"

    combined = pd.concat([has_bolus, no_bolus])

    for q, style, color in [("None", ":", "gray"), ("Low", "--", "C0"),
                             ("Med", "-", "C1"), ("High", "-", "C3")]:
        qd = combined[combined["bolus_q"] == q]
        if len(qd) < 10:
            continue
        traj = []
        for h in HORIZONS:
            mins = h * 5
            traj.append(qd[f"bg_{mins}m"].mean())
        ax.plot([0] + [h*5 for h in HORIZONS], [qd["bg0"].mean()] + traj,
               style, color=color, lw=2, marker="o", markersize=5,
               label=f"{q} (n={len(qd)}, mean={qd['bg0'].mean():.0f})")

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Mean BG (mg/dL)")
    ax.set_title(f"{ctrl.upper()}: BG Trajectory by Bolus Quartile")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(100, 280)

plt.suptitle("EXP-2694: BG Trajectories by Bolus Dose", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_bg_trajectories.png", dpi=150)
plt.close()
print("Panel 4: BG trajectories saved")

# ── Panel 5: BG₀-matched bolus comparison ────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Narrow BG bands for matching
for band_lo, band_hi in [(190, 210), (220, 250)]:
    band = ev[(ev["bg0"] >= band_lo) & (ev["bg0"] <= band_hi)]
    bolus_col = f"bolus_{HORIZONS[-1]*5}m"
    has_bol = band[band[bolus_col] > 0.5]
    no_bol = band[band[bolus_col] <= 0.1]

    if len(has_bol) < 20 or len(no_bol) < 20:
        continue

    ax_idx = 0 if band_lo == 190 else 1
    ax = axes[ax_idx]

    for group, data, color, label in [("No bolus", no_bol, "gray", "No bolus"),
                                       ("Bolus", has_bol, "C0", "Bolus ≥0.5U")]:
        traj = [data["bg0"].mean()]
        for h in HORIZONS:
            mins = h * 5
            traj.append(data[f"bg_{mins}m"].mean())
        ax.plot([0] + [h*5 for h in HORIZONS], traj, "o-", color=color, lw=2.5,
               markersize=7, label=f"{label} (n={len(data)})")

        # CI
        for j, h in enumerate(HORIZONS):
            mins = h * 5
            se = data[f"bg_{mins}m"].sem()
            ax.fill_between([mins], [traj[j+1] - 1.96*se], [traj[j+1] + 1.96*se],
                           alpha=0.2, color=color)

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Mean BG (mg/dL)")
    ax.set_title(f"BG₀-Matched: {band_lo}-{band_hi} mg/dL\n(all controllers)")
    ax.legend()
    ax.grid(True, alpha=0.3)

plt.suptitle("EXP-2694: BG₀-Matched Bolus Effect", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_matched_comparison.png", dpi=150)
plt.close()
print("Panel 5: Matched comparison saved")

# ── Panel 6: SMB timing relative to bolus ─────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# How does the controller respond to a bolus?
bolus_events = ev[ev[f"bolus_{HORIZONS[0]*5}m"] > 0.5]  # Events with bolus in first 30 min
no_bolus_events = ev[ev[f"bolus_{HORIZONS[-1]*5}m"] <= 0.1]  # Events with no bolus at all

# 6a: SMB accumulation pattern
for group, data, color, label in [("With bolus", bolus_events, "C0", "After user bolus"),
                                   ("No bolus", no_bolus_events, "gray", "No user bolus")]:
    smb_cum = []
    for h in HORIZONS:
        mins = h * 5
        smb_cum.append(data[f"smb_{mins}m"].mean())
    axes[0].plot([h*5 for h in HORIZONS], smb_cum, "o-", color=color, lw=2.5,
               markersize=8, label=f"{label} (n={len(data)})")
    for j, h in enumerate(HORIZONS):
        se = data[f"smb_{h*5}m"].sem()
        axes[0].fill_between([h*5], [smb_cum[j] - 1.96*se], [smb_cum[j] + 1.96*se],
                            alpha=0.2, color=color)

axes[0].set_xlabel("Time (minutes)")
axes[0].set_ylabel("Cumulative SMB insulin (U)")
axes[0].set_title("SMB Accumulation: With vs Without User Bolus")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 6b: Excess basal pattern
for group, data, color, label in [("With bolus", bolus_events, "C0", "After user bolus"),
                                   ("No bolus", no_bolus_events, "gray", "No user bolus")]:
    basal_cum = []
    for h in HORIZONS:
        mins = h * 5
        basal_cum.append(data[f"excess_basal_{mins}m"].mean())
    axes[1].plot([h*5 for h in HORIZONS], basal_cum, "o-", color=color, lw=2.5,
               markersize=8, label=f"{label} (n={len(data)})")

axes[1].set_xlabel("Time (minutes)")
axes[1].set_ylabel("Cumulative excess basal (U)")
axes[1].set_title("Excess Basal Delivery: With vs Without User Bolus")
axes[1].legend()
axes[1].axhline(0, color="k", ls=":", alpha=0.5)
axes[1].grid(True, alpha=0.3)

plt.suptitle("EXP-2694: Controller Response to User Bolus", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_controller_response.png", dpi=150)
plt.close()
print("Panel 6: Controller response saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2694",
    "title": "Time-Resolved Channel Decomposition",
    "n_events": int(len(ev)),
    "r2_by_horizon": {str(h*5): {
        "total_r2": float(r2_by_horizon[h*5]["total"]),
        "n": int(r2_by_horizon[h*5]["n"]),
    } for h in HORIZONS},
    "coefs_by_horizon": coefs_by_horizon,
    "bg_matched_comparison": {
        "band_190_210": {
            "bolus_n": int(len(has_bol)) if 'has_bol' in dir() else 0,
            "no_bolus_n": int(len(no_bol)) if 'no_bol' in dir() else 0,
        }
    },
}
(EXP / "exp-2694_time_resolved.json").write_text(json.dumps(results, indent=2, default=str))

# Print summary
print(f"""
{'='*60}
EXP-2694: Time-Resolved Channel Decomposition — SUMMARY
{'='*60}

  Events: {len(ev)}

  R² BY HORIZON:""")
for h in HORIZONS:
    mins = h * 5
    r2 = r2_by_horizon[mins]["total"]
    n = r2_by_horizon[mins]["n"]
    print(f"    {mins:3d} min: R²={r2:.4f} (n={n})")

print(f"""
  MARGINAL EFFECTS AT 120 min (BG drop per 1U):""")
for feat in ["bolus_120m", "smb_120m", "excess_basal_120m"]:
    if feat in coefs_by_horizon[120]:
        c = coefs_by_horizon[120][feat]
        print(f"    {feat:20s}: {c['beta']:+.2f} ± {1.96*c['se']:.2f} mg/dL/U")

print(f"""
  CONTROLLER RESPONSE TO USER BOLUS:
    SMB after bolus:   {bolus_events[f'smb_{HORIZONS[-1]*5}m'].mean():.2f}U (2h cumulative)
    SMB without bolus: {no_bolus_events[f'smb_{HORIZONS[-1]*5}m'].mean():.2f}U
    Excess basal after bolus:   {bolus_events[f'excess_basal_{HORIZONS[-1]*5}m'].mean():.2f}U
    Excess basal without bolus: {no_bolus_events[f'excess_basal_{HORIZONS[-1]*5}m'].mean():.2f}U
""")
