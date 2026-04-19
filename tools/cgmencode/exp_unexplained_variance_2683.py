#!/usr/bin/env python3
"""EXP-2683: What Drives the 86% Unexplained BG Drop Variance?

EXP-2681/2682 showed insulin (bolus + controller) explains only ~14% of BG drop.
This experiment investigates the remaining 86% by testing:

  1. Glucose momentum (ROC at correction time)
  2. Concurrent carbs (meal-contaminated events)
  3. Regression to the mean (high BG → mean BG, independent of insulin)
  4. Time of day effects
  5. Patient-level random effects
  6. Combined model with all predictors

5-panel dashboard:
  1. Glucose ROC vs BG drop — does momentum explain the drop?
  2. Carb-contaminated events: with vs without concurrent carbs
  3. Regression to mean: BG0 distribution and BG→mean convergence
  4. Random effects: per-patient vs within-patient variance
  5. Full model comparison: what explains BG drop?
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

VIS = Path("visualizations/unexplained-variance")
VIS.mkdir(parents=True, exist_ok=True)
EXP = Path("externals/experiments")

manifest = json.load(open(EXP / "autoprepare-qualified.json"))
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
ds = pd.read_parquet("externals/ns-parquet/training/devicestatus.parquet")
ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])].copy()
grid["controller"] = grid["patient_id"].map(ctrl_map)


def extract_events(df, bg_floor=180, isolation_hours=2, min_dose=0.1):
    """Extract correction events with full context for variance analysis."""
    events = []
    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        bolus_idx = pdf.index[pdf["bolus"] > min_dose].tolist()

        # Compute patient-level mean BG for regression to mean
        patient_mean_bg = pdf["glucose"].mean()

        for idx in bolus_idx:
            row = pdf.loc[idx]
            bg0 = row["glucose"]
            dose = row["bolus"]
            t0 = row["time"]

            if pd.isna(bg0) or bg0 < bg_floor:
                continue

            t_iso = pd.Timestamp(t0) - pd.Timedelta(hours=isolation_hours)
            if hasattr(t_iso, "tz") and t_iso.tz is None:
                try:
                    t_iso = t_iso.tz_localize("UTC")
                except Exception:
                    pass

            prior = pdf[(pdf["time"] >= t_iso) & (pdf["time"] < t0) & (pdf["bolus"] > min_dose)]
            if len(prior) > 0:
                continue

            t2h = pd.Timestamp(t0) + pd.Timedelta(hours=2)
            if hasattr(t2h, "tz") and t2h.tz is None:
                try:
                    t2h = t2h.tz_localize("UTC")
                except Exception:
                    pass

            window = pdf[(pdf["time"] >= t2h - pd.Timedelta(minutes=10)) &
                        (pdf["time"] <= t2h + pd.Timedelta(minutes=10))]
            if len(window) == 0:
                continue
            closest = window.iloc[(window["time"] - t2h).abs().argsort().iloc[0]]
            bg2h = closest["glucose"]
            if pd.isna(bg2h):
                continue

            # Concurrent carbs in 2h window
            carb_window = pdf[(pdf["time"] >= t0) & (pdf["time"] <= t2h)]
            total_carbs = carb_window["carbs"].sum() if "carbs" in carb_window.columns else 0
            has_carbs = total_carbs > 5  # >5g threshold

            # Glucose ROC at correction time
            glucose_roc = row.get("glucose_roc", np.nan)
            # If no ROC column, compute from prior readings
            if pd.isna(glucose_roc):
                t_prior = pd.Timestamp(t0) - pd.Timedelta(minutes=15)
                if hasattr(t_prior, "tz") and t_prior.tz is None:
                    try:
                        t_prior = t_prior.tz_localize("UTC")
                    except Exception:
                        pass
                prior_bg = pdf[(pdf["time"] >= t_prior - pd.Timedelta(minutes=5)) &
                              (pdf["time"] <= t_prior + pd.Timedelta(minutes=5))]
                if len(prior_bg) > 0:
                    glucose_roc = (bg0 - prior_bg["glucose"].iloc[0]) / 15  # mg/dL/min

            # Regression to mean: distance from patient mean
            dist_from_mean = bg0 - patient_mean_bg
            expected_regression = dist_from_mean * 0.5  # naive 50% regression

            events.append({
                "patient_id": pid,
                "controller": ctrl_map.get(pid, "unknown"),
                "bg0": bg0,
                "bg2h": bg2h,
                "bg_drop": bg0 - bg2h,
                "dose": dose,
                "glucose_roc": glucose_roc,
                "total_carbs": total_carbs,
                "has_carbs": has_carbs,
                "iob": row.get("iob", np.nan),
                "cob": row.get("cob", np.nan),
                "hour": pd.Timestamp(t0).hour,
                "patient_mean_bg": patient_mean_bg,
                "dist_from_mean": dist_from_mean,
            })

    return pd.DataFrame(events)


print("Extracting events with full context...")
ev = extract_events(grid)
ev_pos = ev[ev["bg_drop"] > 0].copy()
print(f"Total: {len(ev)}, positive: {len(ev_pos)}")

results = {"n_total": len(ev), "n_positive": len(ev_pos)}
colors = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# ── Panel 1: Glucose ROC vs BG Drop ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

ev_roc = ev_pos.dropna(subset=["glucose_roc"])
if len(ev_roc) > 10:
    for ctrl in ["loop", "trio", "openaps"]:
        sub = ev_roc[ev_roc["controller"] == ctrl]
        if len(sub) > 5:
            axes[0].scatter(sub["glucose_roc"], sub["bg_drop"], c=colors[ctrl],
                           alpha=0.3, s=20, label=ctrl)

    r_roc, p_roc = stats.spearmanr(ev_roc["glucose_roc"], ev_roc["bg_drop"])
    axes[0].set_xlabel("Glucose ROC at correction (mg/dL/min)")
    axes[0].set_ylabel("BG Drop at 2h (mg/dL)")
    axes[0].set_title(f"Momentum: ROC vs Drop (r={r_roc:.3f}, p={p_roc:.4f})")
    axes[0].axvline(0, color="gray", linestyle="--", alpha=0.3)
    axes[0].legend()
    results["roc_vs_drop"] = {"r": float(r_roc), "p": float(p_roc), "n": len(ev_roc)}
    print(f"  ROC vs drop: r={r_roc:.3f}, p={p_roc:.4f}")

    # ROC direction: rising vs falling at correction
    rising = ev_roc[ev_roc["glucose_roc"] > 0]
    falling = ev_roc[ev_roc["glucose_roc"] < 0]
    if len(rising) > 5 and len(falling) > 5:
        axes[1].boxplot([falling["bg_drop"].values, rising["bg_drop"].values],
                       labels=[f"Falling BG\n(n={len(falling)})", f"Rising BG\n(n={len(rising)})"])
        mw_stat, mw_p = stats.mannwhitneyu(falling["bg_drop"], rising["bg_drop"])
        axes[1].set_ylabel("BG Drop at 2h (mg/dL)")
        axes[1].set_title(f"Drop by BG Direction (Mann-Whitney p={mw_p:.4f})")
        results["rising_vs_falling"] = {
            "rising_median": float(rising["bg_drop"].median()),
            "falling_median": float(falling["bg_drop"].median()),
            "p": float(mw_p),
        }

plt.tight_layout()
plt.savefig(VIS / "fig1_glucose_roc.png", dpi=150)
plt.close()
print("Panel 1: ROC saved")

# ── Panel 2: Carb-Contaminated Events ───────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

with_carbs = ev_pos[ev_pos["has_carbs"]]
no_carbs = ev_pos[~ev_pos["has_carbs"]]
print(f"  With carbs (>5g): {len(with_carbs)} ({100*len(with_carbs)/len(ev_pos):.0f}%)")
print(f"  Without carbs: {len(no_carbs)}")

# 2a: BG drop distribution with vs without carbs
axes[0].hist(no_carbs["bg_drop"], bins=40, alpha=0.5, label=f"No carbs (n={len(no_carbs)})", density=True)
axes[0].hist(with_carbs["bg_drop"], bins=40, alpha=0.5, label=f"With carbs (n={len(with_carbs)})", density=True)
axes[0].set_xlabel("BG Drop at 2h (mg/dL)")
axes[0].set_ylabel("Density")
if len(with_carbs) > 5 and len(no_carbs) > 5:
    mw_stat, mw_p = stats.mannwhitneyu(no_carbs["bg_drop"], with_carbs["bg_drop"])
    axes[0].set_title(f"BG Drop: Carbs vs No Carbs (p={mw_p:.4f})")
    results["carb_effect"] = {
        "with_carbs_median": float(with_carbs["bg_drop"].median()),
        "no_carbs_median": float(no_carbs["bg_drop"].median()),
        "p": float(mw_p),
    }
else:
    axes[0].set_title("BG Drop: Carbs vs No Carbs")
axes[0].legend()

# 2b: R² improvement when excluding carb events
from numpy.linalg import lstsq

for label, data, ax_idx in [("All events", ev_pos, 0), ("No carbs", no_carbs, 1)]:
    valid = data.dropna(subset=["glucose_roc", "iob"]).copy()
    if len(valid) > 30:
        y = valid["bg_drop"].values
        X = np.column_stack([
            np.ones(len(valid)),
            valid["bg0"].values,
            valid["dose"].values,
        ])
        coefs, _, _, _ = lstsq(X, y, rcond=None)
        y_pred = X @ coefs
        r2 = np.corrcoef(y, y_pred)[0, 1] ** 2
        results[f"r2_{label.lower().replace(' ', '_')}"] = float(r2)

if len(with_carbs) > 5:
    # Carb amount vs bg_drop
    axes[1].scatter(with_carbs["total_carbs"], with_carbs["bg_drop"],
                   alpha=0.4, s=30, color="C3")
    r_carb, p_carb = stats.spearmanr(with_carbs["total_carbs"], with_carbs["bg_drop"])
    axes[1].set_xlabel("Total Carbs in 2h Window (g)")
    axes[1].set_ylabel("BG Drop (mg/dL)")
    axes[1].set_title(f"Carb Amount vs Drop (r={r_carb:.3f}, p={p_carb:.4f})")
    results["carb_amount_vs_drop"] = {"r": float(r_carb), "p": float(p_carb)}

plt.tight_layout()
plt.savefig(VIS / "fig2_carb_contamination.png", dpi=150)
plt.close()
print("Panel 2: Carb contamination saved")

# ── Panel 3: Regression to the Mean ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 3a: BG0 distribution (conditioning artifact)
axes[0].hist(ev_pos["bg0"], bins=40, alpha=0.7, color="steelblue")
axes[0].axvline(180, color="red", linestyle="--", label="BG≥180 cutoff")
axes[0].axvline(ev_pos["bg0"].median(), color="green", linestyle="--",
               label=f"Median: {ev_pos['bg0'].median():.0f}")
axes[0].set_xlabel("Starting BG (mg/dL)")
axes[0].set_ylabel("Count")
axes[0].set_title("Starting BG Distribution (BG≥180 filter)")
axes[0].legend()

# 3b: Distance from patient mean → BG drop
axes[1].scatter(ev_pos["dist_from_mean"], ev_pos["bg_drop"], alpha=0.2, s=15)
r_reg, p_reg = stats.spearmanr(ev_pos["dist_from_mean"], ev_pos["bg_drop"])
axes[1].set_xlabel("Distance from Patient Mean BG (mg/dL)")
axes[1].set_ylabel("BG Drop at 2h (mg/dL)")
axes[1].set_title(f"Regression to Mean (r={r_reg:.3f}, p={p_reg:.4f})")

# Add regression line
slope, intercept, _, _, _ = stats.linregress(ev_pos["dist_from_mean"], ev_pos["bg_drop"])
x_fit = np.linspace(ev_pos["dist_from_mean"].min(), ev_pos["dist_from_mean"].max(), 100)
axes[1].plot(x_fit, slope * x_fit + intercept, "r-", linewidth=2,
            label=f"slope={slope:.2f}")
axes[1].legend()

results["regression_to_mean"] = {
    "r": float(r_reg),
    "p": float(p_reg),
    "slope": float(slope),
    "median_dist_from_mean": float(ev_pos["dist_from_mean"].median()),
}
print(f"  Regression to mean: r={r_reg:.3f}, slope={slope:.2f}")

plt.tight_layout()
plt.savefig(VIS / "fig3_regression_to_mean.png", dpi=150)
plt.close()
print("Panel 3: Regression to mean saved")

# ── Panel 4: Per-Patient Random Effects ──────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Within-patient vs between-patient variance
patient_stats = ev_pos.groupby("patient_id").agg(
    mean_drop=("bg_drop", "mean"),
    std_drop=("bg_drop", "std"),
    n=("bg_drop", "count"),
    median_bg0=("bg0", "median"),
    median_dose=("dose", "median"),
    controller=("controller", "first"),
)

# Between-patient variance
var_between = patient_stats["mean_drop"].var()
# Mean within-patient variance
var_within = (patient_stats["std_drop"] ** 2).mean()
icc = var_between / (var_between + var_within) if (var_between + var_within) > 0 else 0

results["random_effects"] = {
    "var_between": float(var_between),
    "var_within": float(var_within),
    "icc": float(icc),
    "n_patients": len(patient_stats),
}
print(f"  ICC (intraclass correlation): {icc:.3f}")
print(f"  Between-patient variance: {var_between:.0f}")
print(f"  Within-patient variance: {var_within:.0f}")

axes[0].bar(["Between\nPatients", "Within\nPatients"],
           [var_between, var_within], color=["steelblue", "coral"], alpha=0.7)
axes[0].set_ylabel("Variance (mg/dL)²")
axes[0].set_title(f"Variance Decomposition (ICC={icc:.3f})")

# 4b: Per-patient mean drop vs characteristics
for ctrl in ["loop", "trio", "openaps"]:
    sub = patient_stats[patient_stats["controller"] == ctrl]
    if len(sub) > 0:
        axes[1].scatter(sub["median_bg0"], sub["mean_drop"],
                       s=sub["n"] * 3, c=colors[ctrl], alpha=0.6,
                       label=f"{ctrl} (n_pts={len(sub)})")

axes[1].set_xlabel("Patient Median Starting BG (mg/dL)")
axes[1].set_ylabel("Patient Mean BG Drop (mg/dL)")
axes[1].set_title("Per-Patient Mean Drop vs Starting BG")
axes[1].legend()

plt.tight_layout()
plt.savefig(VIS / "fig4_random_effects.png", dpi=150)
plt.close()
print("Panel 4: Random effects saved")

# ── Panel 5: Full Model Comparison ───────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 7))

from numpy.linalg import lstsq

# Build comprehensive model comparison
ev_full = ev_pos.dropna(subset=["glucose_roc", "iob"]).copy()
# Add patient fixed effects
patient_ids = ev_full["patient_id"].unique()
patient_map = {pid: i for i, pid in enumerate(patient_ids)}

models_r2 = {}

if len(ev_full) > 50:
    y = ev_full["bg_drop"].values

    # Single predictors
    for name, col in [
        ("BG₀", "bg0"),
        ("Glucose ROC", "glucose_roc"),
        ("Dose", "dose"),
        ("IOB", "iob"),
        ("Hour", "hour"),
        ("Dist from mean", "dist_from_mean"),
    ]:
        vals = ev_full[col].values
        mask = ~np.isnan(vals)
        if mask.sum() > 20:
            X = np.column_stack([np.ones(mask.sum()), vals[mask]])
            coefs, _, _, _ = lstsq(X, y[mask], rcond=None)
            y_pred = X @ coefs
            r2 = max(0, np.corrcoef(y[mask], y_pred)[0, 1] ** 2)
            models_r2[name] = r2

    # Has carbs indicator
    carb_indicator = ev_full["has_carbs"].astype(float).values
    X = np.column_stack([np.ones(len(ev_full)), carb_indicator])
    coefs, _, _, _ = lstsq(X, y, rcond=None)
    y_pred = X @ coefs
    r2 = max(0, np.corrcoef(y, y_pred)[0, 1] ** 2)
    models_r2["Has carbs"] = r2

    # Combined: BG0 + ROC + dose
    X_combo = np.column_stack([
        np.ones(len(ev_full)),
        ev_full["bg0"].values,
        ev_full["glucose_roc"].values,
        ev_full["dose"].values,
    ])
    coefs, _, _, _ = lstsq(X_combo, y, rcond=None)
    y_pred = X_combo @ coefs
    r2 = max(0, np.corrcoef(y, y_pred)[0, 1] ** 2)
    models_r2["BG₀ + ROC + dose"] = r2

    # Combined + carbs
    X_combo2 = np.column_stack([
        X_combo,
        carb_indicator,
    ])
    coefs, _, _, _ = lstsq(X_combo2, y, rcond=None)
    y_pred = X_combo2 @ coefs
    r2 = max(0, np.corrcoef(y, y_pred)[0, 1] ** 2)
    models_r2["+ carbs"] = r2

    # Patient fixed effects only
    patient_dummies = np.zeros((len(ev_full), len(patient_ids)))
    for i, row_data in enumerate(ev_full.itertuples()):
        pid_idx = patient_map.get(row_data.patient_id, 0)
        patient_dummies[i, pid_idx] = 1
    X_patient = patient_dummies
    coefs, _, _, _ = lstsq(X_patient, y, rcond=None)
    y_pred = X_patient @ coefs
    r2 = max(0, np.corrcoef(y, y_pred)[0, 1] ** 2)
    models_r2["Patient FE"] = r2

    # Full: patient FE + BG0 + ROC + dose + carbs
    X_full = np.column_stack([
        patient_dummies,
        ev_full["bg0"].values,
        ev_full["glucose_roc"].values,
        ev_full["dose"].values,
        carb_indicator,
    ])
    coefs, _, _, _ = lstsq(X_full, y, rcond=None)
    y_pred = X_full @ coefs
    r2 = max(0, np.corrcoef(y, y_pred)[0, 1] ** 2)
    models_r2["Full (FE + all)"] = r2

    # No-carbs subset
    nc = ev_full[~ev_full["has_carbs"]]
    if len(nc) > 30:
        y_nc = nc["bg_drop"].values
        X_nc = np.column_stack([
            np.ones(len(nc)),
            nc["bg0"].values,
            nc["glucose_roc"].values,
            nc["dose"].values,
        ])
        coefs, _, _, _ = lstsq(X_nc, y_nc, rcond=None)
        y_pred = X_nc @ coefs
        r2 = max(0, np.corrcoef(y_nc, y_pred)[0, 1] ** 2)
        models_r2["No-carbs subset"] = r2

    # Sort and plot
    sorted_models = sorted(models_r2.items(), key=lambda x: x[1])
    names = [m[0] for m in sorted_models]
    r2s = [m[1] for m in sorted_models]

    bars = ax.barh(names, r2s, color="steelblue", alpha=0.7)
    for bar, val in zip(bars, r2s):
        ax.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height()/2,
               f"{val:.3f}", va="center", fontsize=9)

    ax.set_xlabel("R²")
    ax.set_title(f"What Explains BG Drop? (n={len(ev_full)} events, BG≥180)")
    ax.axvline(0.5, color="gray", linestyle="--", alpha=0.3, label="R²=0.5")
    ax.set_xlim(0, max(r2s) * 1.2 + 0.05)

    results["full_model_comparison"] = {k: float(v) for k, v in models_r2.items()}

    print(f"\nFull Model Comparison (R²):")
    for name, r2 in sorted(models_r2.items(), key=lambda x: -x[1]):
        print(f"  {name}: {r2:.4f}")

plt.tight_layout()
plt.savefig(VIS / "fig5_full_model_comparison.png", dpi=150)
plt.close()
print("Panel 5: Full model comparison saved")

# Save
with open(EXP / "exp-2683_unexplained_variance.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*60}")
print(f"EXP-2683: Unexplained Variance — RESULTS")
print(f"{'='*60}")
print(f"Events: {len(ev_pos)} positive drops")
print(f"ICC (patient random effect): {results['random_effects']['icc']:.3f}")
if "roc_vs_drop" in results:
    print(f"Glucose ROC: r={results['roc_vs_drop']['r']:.3f}")
if "regression_to_mean" in results:
    print(f"Regression to mean: r={results['regression_to_mean']['r']:.3f}")
if "carb_effect" in results:
    print(f"Carb effect: with={results['carb_effect']['with_carbs_median']:.0f}, "
          f"without={results['carb_effect']['no_carbs_median']:.0f}, p={results['carb_effect']['p']:.4f}")
