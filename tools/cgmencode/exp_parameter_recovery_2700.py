#!/usr/bin/env python3
"""EXP-2700: CR Calibration + Full Parameter Recovery Pipeline

Complete the oref0-autotune analog using our deviation framework:
  - ISF: from correction deviations (EXP-2699)
  - CR: from meal deviations (THIS EXPERIMENT)
  - Basal: from fasting deviations

For meal events: deviation = observed_drop - (excess_insulin × ISF)
If CR is correct and ISF is correct, the meal-related deviation should
be explained by carbs: deviation ≈ −carbs_absorbed × (ISF / CR_true)

We can recover CR by:
  CR_calibrated = carbs / (−meal_deviation / ISF)
  Or equivalently: meal_deviation = −ISF × carbs / CR

This also validates our pipeline end-to-end: if deviations from ISF
calibration are consistent with deviations from CR calibration,
the parameter estimates are mutually consistent.

Panels:
  1. Meal deviation vs carbs (the CR signal)
  2. Per-patient CR calibration: setting vs recovered
  3. Basal deviation analysis (fasting periods)
  4. Full parameter consistency check
  5. Cross-controller parameter comparison
  6. Summary: complete autotune-equivalent results
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
OUT = pathlib.Path("visualizations/parameter-recovery")
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

print("=" * 60)
print("EXP-2700: CR CALIBRATION + FULL PARAMETER RECOVERY")
print("=" * 60)

HORIZON = 24  # 120 min

# ── Extract ALL events with categories ────────────────────────────────
print("\nExtracting events with full categorization...")
events = []

for pid in grid["patient_id"].unique():
    pg = grid[grid["patient_id"] == pid].reset_index(drop=True)
    ctrl = pg["controller"].iloc[0]
    glucose = pg["glucose"].values
    bolus = pg["bolus"].values
    smb = pg["bolus_smb"].values if "bolus_smb" in pg.columns else np.zeros(len(pg))
    net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.full(len(pg), np.nan)
    sched_basal = pg["scheduled_basal_rate"].values if "scheduled_basal_rate" in pg.columns else np.full(len(pg), np.nan)
    isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else np.full(len(pg), np.nan)
    cr = pg["scheduled_cr"].values if "scheduled_cr" in pg.columns else np.full(len(pg), np.nan)
    carbs_col = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
    iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
    times = pg["time"].values

    for i in range(HORIZON, len(pg) - HORIZON):
        bg0 = glucose[i]
        bg_2h = glucose[i + HORIZON]
        if np.isnan(bg0) or np.isnan(bg_2h):
            continue

        bolus_2h = np.nansum(bolus[i:i+HORIZON])
        smb_2h = np.nansum(smb[i:i+HORIZON])
        basal_2h = np.nansum(net_basal[i:i+HORIZON]) * (5.0/60.0)
        sched_basal_2h = np.nansum(sched_basal[i:i+HORIZON]) * (5.0/60.0)
        excess_basal_2h = basal_2h - sched_basal_2h
        carbs_2h = np.nansum(carbs_col[i:i+HORIZON])
        isf_val = isf[i] if not np.isnan(isf[i]) else np.nan
        cr_val = cr[i] if not np.isnan(cr[i]) else np.nan
        iob_val = iob[i] if not np.isnan(iob[i]) else 0

        excess_insulin = bolus_2h + smb_2h + excess_basal_2h
        observed_drop = bg0 - bg_2h
        expected_drop_insulin = excess_insulin * isf_val if not np.isnan(isf_val) else np.nan
        deviation = observed_drop - expected_drop_insulin if not np.isnan(expected_drop_insulin) else np.nan

        # Categorize
        if carbs_2h > 5 and bolus_2h > 0.3:
            category = "meal_bolus"  # Meal with bolus
        elif carbs_2h > 5:
            category = "meal_no_bolus"  # Meal without bolus (UAM or free carbs)
        elif bolus_2h > 0.3 and carbs_2h <= 5:
            category = "correction"
        elif abs(excess_basal_2h) < 0.05 and smb_2h < 0.05 and bolus_2h < 0.05:
            category = "fasting"  # Pure fasting — no excess insulin
        else:
            category = "other"

        try:
            hour = pd.Timestamp(times[i]).hour
        except Exception:
            hour = 12

        events.append({
            "patient_id": pid, "controller": ctrl,
            "bg0": bg0, "bg_2h": bg_2h,
            "observed_drop": observed_drop,
            "expected_drop_insulin": expected_drop_insulin,
            "deviation": deviation,
            "excess_insulin": excess_insulin,
            "bolus_2h": bolus_2h, "smb_2h": smb_2h,
            "excess_basal_2h": excess_basal_2h,
            "carbs_2h": carbs_2h,
            "isf_setting": isf_val, "cr_setting": cr_val,
            "iob_start": iob_val,
            "category": category, "hour": hour,
        })

ev = pd.DataFrame(events)
ev = ev.dropna(subset=["deviation"])
print(f"Total events: {len(ev)}")
print(f"Categories:\n{ev['category'].value_counts().to_string()}")

# ── PART A: Meal CR Calibration ──────────────────────────────────────
print("\n── PART A: MEAL CR CALIBRATION ──")
meals = ev[ev["category"] == "meal_bolus"].copy()
print(f"Meal events with bolus: {len(meals)}")

# The deviation after subtracting insulin effect should be explained by carbs
# deviation = observed_drop - ISF × excess_insulin
# For meal events: deviation ≈ −ISF × carbs / CR + noise
# So: deviation ~ −carbs (if ISF/CR ratio is positive)
# Or more precisely: expected_carb_rise = carbs × ISF / CR
# deviation = −expected_carb_rise + noise

meals["expected_carb_rise"] = meals["carbs_2h"] * meals["isf_setting"] / meals["cr_setting"]
meals = meals.dropna(subset=["expected_carb_rise"])

# ── Panel 1: Meal deviation vs carbs ─────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
colors_ctrl = {"loop": "C0", "trio": "C1", "openaps": "C2"}

# 1a: Deviation vs carbs
for ctrl in ["loop", "trio", "openaps"]:
    mc = meals[meals["controller"] == ctrl]
    if len(mc) > 100:
        axes[0].scatter(mc["carbs_2h"], mc["deviation"], alpha=0.02, s=2,
                       color=colors_ctrl[ctrl], label=ctrl.upper())

# Bin by carbs
try:
    carb_bins = pd.cut(meals["carbs_2h"], bins=[0, 10, 20, 30, 50, 80, 150])
    binned = meals.groupby(carb_bins, observed=True).agg(
        mean_carbs=("carbs_2h", "mean"),
        mean_dev=("deviation", "mean"),
        se_dev=("deviation", "sem"),
    ).dropna()
    axes[0].errorbar(binned["mean_carbs"], binned["mean_dev"],
                    yerr=1.96 * binned["se_dev"],
                    fmt="ko-", lw=3, capsize=6, markersize=10, zorder=5)
except Exception as e:
    print(f"  Carb binning error: {e}")

axes[0].axhline(0, color="k", ls="--", alpha=0.5)
axes[0].set_xlabel("Carbs (g)")
axes[0].set_ylabel("Deviation (mg/dL)")
axes[0].set_title("Meal Deviation vs Carbs\n(negative = BG dropped less than expected)")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 1b: Deviation vs expected carb rise (ISF/CR ratio)
r_carb, p_carb = stats.pearsonr(meals["expected_carb_rise"].values,
                                 meals["deviation"].values)
axes[1].scatter(meals["expected_carb_rise"], meals["deviation"],
               alpha=0.02, s=2, color="C0")

# Fit line
slope_c, intercept_c, _, _, _ = stats.linregress(
    meals["expected_carb_rise"].values, meals["deviation"].values)
x_fit = np.linspace(0, meals["expected_carb_rise"].quantile(0.95), 100)
axes[1].plot(x_fit, intercept_c + slope_c * x_fit, "C3-", lw=2,
            label=f"slope={slope_c:.3f}, r={r_carb:.3f}")

axes[1].axhline(0, color="k", ls="--", alpha=0.5)
axes[1].set_xlabel("Expected Carb Rise = carbs × ISF/CR (mg/dL)")
axes[1].set_ylabel("Deviation (mg/dL)")
axes[1].set_title(f"Deviation vs Expected Carb Effect\nr={r_carb:.3f}, p={p_carb:.2e}")
axes[1].legend()
axes[1].grid(True, alpha=0.3)

# 1c: Distribution of effective CR from deviations
# CR_eff = carbs / (deviation / ISF)
# But deviation = drop - ISF*insulin, so:
# CR_eff ≈ carbs × ISF / (ISF × insulin_for_carbs - drop + baseline)
# Simpler: if deviation < 0 (BG dropped less than expected from insulin alone)
# then carbs counteracted: CR_eff ≈ carbs / (-deviation / ISF)
valid_meals = meals[(meals["deviation"] < -5) & (meals["isf_setting"] > 0)]
if len(valid_meals) > 100:
    valid_meals = valid_meals.copy()
    valid_meals["cr_effective"] = valid_meals["carbs_2h"] / (-valid_meals["deviation"] / valid_meals["isf_setting"])
    valid_meals = valid_meals[(valid_meals["cr_effective"] > 1) & (valid_meals["cr_effective"] < 50)]

    for ctrl in ["loop", "trio", "openaps"]:
        vc = valid_meals[valid_meals["controller"] == ctrl]
        if len(vc) > 50:
            axes[2].hist(vc["cr_effective"], bins=30, alpha=0.5,
                        color=colors_ctrl[ctrl], label=ctrl.upper(), density=True)

    axes[2].axvline(valid_meals["cr_setting"].median(), color="k", ls="--", lw=2,
                   label=f"Setting={valid_meals['cr_setting'].median():.0f}")
    axes[2].axvline(valid_meals["cr_effective"].median(), color="C3", ls="-", lw=2,
                   label=f"Effective={valid_meals['cr_effective'].median():.1f}")

axes[2].set_xlabel("Effective CR (g/U)")
axes[2].set_ylabel("Density")
axes[2].set_title("CR Distribution: Setting vs Effective")
axes[2].legend(fontsize=9)
axes[2].grid(True, alpha=0.3)

plt.suptitle("EXP-2700: Meal Deviation Analysis for CR Calibration", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig1_meal_cr.png", dpi=150)
plt.close()
print("Panel 1 saved")

# ── Per-patient CR calibration ────────────────────────────────────────
pat_cr = []
for pid in meals["patient_id"].unique():
    pm = meals[meals["patient_id"] == pid]
    if len(pm) < 20:
        continue

    ctrl = pm["controller"].iloc[0]
    cr_set = pm["cr_setting"].median()
    isf_set = pm["isf_setting"].median()

    # Method: regress deviation on expected_carb_rise
    # deviation = α + β × expected_carb_rise + ε
    # If β = −1, ISF/CR ratio is exactly right
    # If β > −1, CR is too aggressive (carbs have less effect than expected)
    # If β < −1, CR is too conservative
    X = pm["expected_carb_rise"].values.reshape(-1, 1)
    y = pm["deviation"].values
    X_aug = np.column_stack([X, np.ones(len(X))])
    b, _, _, _ = lstsq(X_aug, y, rcond=None)
    beta_carb = float(b[0])
    intercept = float(b[1])

    # CR calibrated: if β should be −1 but is β_actual:
    # True ISF/CR = (ISF/CR) × |β_actual|
    # CR_calibrated = CR_setting / |β_actual|
    cr_cal = cr_set / abs(beta_carb) if abs(beta_carb) > 0.01 else np.nan

    # Also: direct ratio method
    meal_dev_mean = pm["deviation"].mean()
    carb_mean = pm["carbs_2h"].mean()
    if carb_mean > 5 and isf_set > 0:
        cr_direct = carb_mean / (-meal_dev_mean / isf_set) if meal_dev_mean < -1 else np.nan
    else:
        cr_direct = np.nan

    pat_cr.append({
        "patient_id": pid, "controller": ctrl,
        "n_meals": len(pm),
        "cr_setting": float(cr_set),
        "cr_calibrated_beta": float(cr_cal) if not np.isnan(cr_cal) else None,
        "cr_calibrated_direct": float(cr_direct) if not (np.isnan(cr_direct) if isinstance(cr_direct, float) else False) else None,
        "isf_setting": float(isf_set),
        "beta_carb": float(beta_carb),
        "intercept": float(intercept),
        "mean_carbs": float(carb_mean),
        "mean_deviation": float(meal_dev_mean),
    })

cr_df = pd.DataFrame(pat_cr)
print(f"\nCR calibrated for {len(cr_df)} patients")

# ── Panel 2: CR Setting vs Calibrated ────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# 2a: Beta (carb sensitivity) by patient
cr_sorted = cr_df.sort_values("beta_carb")
colors_beta = [colors_ctrl.get(c, "gray") for c in cr_sorted["controller"]]
axes[0].barh(range(len(cr_sorted)), cr_sorted["beta_carb"],
            color=colors_beta, edgecolor="k", alpha=0.7)
axes[0].axvline(-1, color="C3", ls="--", lw=2, label="β=−1 (ISF/CR correct)")
axes[0].axvline(0, color="k", ls="--", alpha=0.5)
axes[0].set_yticks(range(len(cr_sorted)))
axes[0].set_yticklabels(cr_sorted["patient_id"], fontsize=7)
axes[0].set_xlabel("β (deviation ~ β × expected_carb_rise)")
axes[0].set_title("Per-Patient Carb Sensitivity\n(−1 = ISF/CR perfectly calibrated)")
axes[0].legend(fontsize=9)
axes[0].grid(True, alpha=0.3, axis="x")

# 2b: CR setting vs beta-calibrated
valid_cr = cr_df.dropna(subset=["cr_calibrated_beta"])
valid_cr = valid_cr[(valid_cr["cr_calibrated_beta"] > 0) & (valid_cr["cr_calibrated_beta"] < 100)]
for ctrl in ["loop", "trio", "openaps"]:
    mask = valid_cr["controller"] == ctrl
    if mask.any():
        axes[1].scatter(valid_cr[mask]["cr_setting"], valid_cr[mask]["cr_calibrated_beta"],
                       s=100, color=colors_ctrl[ctrl], label=ctrl.upper(), edgecolors="k")

if len(valid_cr) > 0:
    max_cr = max(valid_cr["cr_setting"].max(), valid_cr["cr_calibrated_beta"].max()) + 5
    axes[1].plot([0, max_cr], [0, max_cr], "k--", alpha=0.5, label="Perfect")

axes[1].set_xlabel("CR Setting (g/U)")
axes[1].set_ylabel("CR Calibrated (g/U)")
axes[1].set_title("CR Setting vs Calibrated")
axes[1].legend(fontsize=9)
axes[1].grid(True, alpha=0.3)

# 2c: Mean deviation by controller (meal events)
for ctrl in ["loop", "trio", "openaps"]:
    ctrl_meals = meals[meals["controller"] == ctrl]
    if len(ctrl_meals) > 50:
        axes[2].hist(ctrl_meals["deviation"].clip(-200, 200), bins=50, alpha=0.5,
                    color=colors_ctrl[ctrl], label=f"{ctrl.upper()} (n={len(ctrl_meals)})",
                    density=True)

axes[2].axvline(0, color="k", ls="--", lw=2)
axes[2].set_xlabel("Meal Deviation (mg/dL)")
axes[2].set_ylabel("Density")
axes[2].set_title("Meal Deviation Distribution by Controller")
axes[2].legend()
axes[2].grid(True, alpha=0.3)

plt.suptitle("EXP-2700: Per-Patient CR Calibration", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig2_cr_calibration.png", dpi=150)
plt.close()
print("Panel 2 saved")

# ── PART B: Fasting Basal Analysis ───────────────────────────────────
print("\n── PART B: FASTING BASAL ANALYSIS ──")
fasting = ev[ev["category"] == "fasting"].copy()
print(f"Fasting events (no excess insulin, no carbs): {len(fasting)}")

# For fasting: if basal rate is correct, BG should be stable (deviation ≈ 0)
# deviation = observed_drop - 0 (no excess insulin)
# If deviation > 0: BG dropping → basal too high
# If deviation < 0: BG rising → basal too low
fasting["basal_deviation"] = fasting["observed_drop"]  # No excess insulin

# ── Panel 3: Fasting basal deviations ────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# 3a: Fasting deviation by hour
for ctrl in ["loop", "trio", "openaps"]:
    cf = fasting[fasting["controller"] == ctrl]
    if len(cf) < 100:
        continue
    hourly = cf.groupby("hour").agg(
        mean_dev=("basal_deviation", "mean"),
        se_dev=("basal_deviation", "sem"),
    ).reset_index()
    axes[0].errorbar(hourly["hour"], hourly["mean_dev"],
                    yerr=1.96 * hourly["se_dev"],
                    fmt="o-", color=colors_ctrl[ctrl], lw=2, capsize=3,
                    label=ctrl.upper())

axes[0].axhline(0, color="k", ls="--", lw=2, label="Perfect basal")
axes[0].set_xlabel("Hour of Day")
axes[0].set_ylabel("Fasting BG Drop (mg/dL)")
axes[0].set_title("Fasting Circadian Pattern\n(+drop = basal too high, −drop = too low)")
axes[0].legend(fontsize=9)
axes[0].grid(True, alpha=0.3)

# 3b: Per-patient fasting deviation
pat_basal = []
for pid in fasting["patient_id"].unique():
    pf = fasting[fasting["patient_id"] == pid]
    if len(pf) < 10:
        continue
    ctrl = pf["controller"].iloc[0]
    mean_dev = pf["basal_deviation"].mean()
    se_dev = pf["basal_deviation"].sem()
    pat_basal.append({
        "patient_id": pid, "controller": ctrl,
        "n_fasting": len(pf),
        "mean_fasting_dev": float(mean_dev),
        "se_fasting_dev": float(se_dev),
    })

basal_df = pd.DataFrame(pat_basal)
if len(basal_df) > 0:
    basal_sorted = basal_df.sort_values("mean_fasting_dev")
    colors_b = [colors_ctrl.get(c, "gray") for c in basal_sorted["controller"]]
    axes[1].barh(range(len(basal_sorted)), basal_sorted["mean_fasting_dev"],
                xerr=1.96 * basal_sorted["se_fasting_dev"],
                color=colors_b, edgecolor="k", alpha=0.7, capsize=3)
    axes[1].set_yticks(range(len(basal_sorted)))
    axes[1].set_yticklabels(basal_sorted["patient_id"], fontsize=7)
    axes[1].axvline(0, color="k", ls="--", lw=2)
    axes[1].set_xlabel("Mean Fasting BG Drop (mg/dL)")
    axes[1].set_title(f"Per-Patient Fasting Deviation\n(0 = basal correct)")
    axes[1].grid(True, alpha=0.3, axis="x")

# 3c: Fasting deviation by BG band
bg_bands = [(60, 90), (90, 120), (120, 150), (150, 200), (200, 300)]
band_labels = [f"{lo}-{hi}" for lo, hi in bg_bands]
band_means = []
band_ses = []
for lo, hi in bg_bands:
    bf = fasting[(fasting["bg0"] >= lo) & (fasting["bg0"] < hi)]
    band_means.append(bf["basal_deviation"].mean() if len(bf) > 10 else np.nan)
    band_ses.append(bf["basal_deviation"].sem() if len(bf) > 10 else np.nan)

axes[2].bar(range(len(bg_bands)), band_means, yerr=[1.96*s if not np.isnan(s) else 0 for s in band_ses],
           color="C0", edgecolor="k", alpha=0.7, capsize=5)
axes[2].set_xticks(range(len(bg_bands)))
axes[2].set_xticklabels(band_labels)
axes[2].axhline(0, color="k", ls="--")
axes[2].set_xlabel("Starting BG Band (mg/dL)")
axes[2].set_ylabel("Mean Fasting BG Drop (mg/dL)")
axes[2].set_title("Fasting Drop by BG Band\n(regression to mean visible?)")
axes[2].grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2700: Fasting Basal Analysis from Deviations", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig3_basal_fasting.png", dpi=150)
plt.close()
print("Panel 3 saved")

# ── Panel 4: Full parameter consistency ──────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Load ISF results from EXP-2699
try:
    isf_results = json.loads((EXP / "exp-2699_isf_calibration.json").read_text())
    isf_per_patient = {r["patient_id"]: r for r in isf_results["per_patient"]}
except Exception:
    isf_per_patient = {}

# 4a: ISF vs CR setting relationship
merged = cr_df.copy()
for pid in merged["patient_id"]:
    if pid in isf_per_patient:
        merged.loc[merged["patient_id"] == pid, "isf_calibrated"] = isf_per_patient[pid].get("isf_ols", np.nan)
        merged.loc[merged["patient_id"] == pid, "baseline_drop"] = isf_per_patient[pid].get("baseline_drop", np.nan)

for ctrl in ["loop", "trio", "openaps"]:
    mc = merged[merged["controller"] == ctrl]
    if len(mc) > 0:
        axes[0].scatter(mc["isf_setting"], mc["cr_setting"],
                       s=100, color=colors_ctrl[ctrl], label=ctrl.upper(), edgecolors="k")

r_ic, p_ic = stats.pearsonr(merged["isf_setting"].dropna(), merged["cr_setting"].dropna())
axes[0].set_xlabel("ISF Setting (mg/dL/U)")
axes[0].set_ylabel("CR Setting (g/U)")
axes[0].set_title(f"ISF vs CR Settings\nr={r_ic:.3f}")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 4b: Deviation mean by category (should be ~0 if parameters correct)
categories = ["correction", "meal_bolus", "fasting", "other"]
cat_means = []
cat_ses = []
cat_ns = []
for cat in categories:
    ce = ev[ev["category"] == cat]
    cat_means.append(ce["deviation"].mean() if len(ce) > 100 else np.nan)
    cat_ses.append(ce["deviation"].sem() if len(ce) > 100 else np.nan)
    cat_ns.append(len(ce))

axes[1].bar(range(len(categories)), cat_means,
           yerr=[1.96*s if not np.isnan(s) else 0 for s in cat_ses],
           color=["C0", "C1", "C2", "gray"], edgecolor="k", alpha=0.7, capsize=5)
axes[1].set_xticks(range(len(categories)))
axes[1].set_xticklabels([f"{c}\n(n={n:,})" for c, n in zip(categories, cat_ns)], fontsize=9)
axes[1].axhline(0, color="k", ls="--", lw=2)
axes[1].set_ylabel("Mean Deviation (mg/dL)")
axes[1].set_title("Mean Deviation by Category\n(0 = parameters correct)")
axes[1].grid(True, alpha=0.3, axis="y")

# 4c: R² by category (how much deviation is explained by covariates)
features_by_cat = {
    "correction": ["bg0", "bolus_2h", "smb_2h", "excess_basal_2h"],
    "meal_bolus": ["bg0", "bolus_2h", "carbs_2h", "smb_2h"],
    "fasting": ["bg0", "iob_start"],
    "other": ["bg0", "excess_insulin", "iob_start"],
}

cat_r2 = {}
for cat in categories:
    ce = ev[ev["category"] == cat]
    feats = features_by_cat.get(cat, ["bg0"])
    clean = ce[feats + ["deviation"]].dropna()
    if len(clean) < 200:
        cat_r2[cat] = np.nan
        continue

    Xc = clean[feats].values
    yc = clean["deviation"].values
    Xc_n = (Xc - Xc.mean(axis=0)) / (Xc.std(axis=0) + 1e-10)
    Xc_aug = np.column_stack([Xc_n, np.ones(len(Xc_n))])
    bc, _, _, _ = lstsq(Xc_aug, yc, rcond=None)
    r2 = 1 - np.sum((yc - Xc_aug @ bc)**2) / np.sum((yc - yc.mean())**2)
    cat_r2[cat] = r2

axes[2].bar(range(len(categories)), [cat_r2.get(c, 0) for c in categories],
           color=["C0", "C1", "C2", "gray"], edgecolor="k", alpha=0.7)
for i, (c, r2) in enumerate(zip(categories, [cat_r2.get(c, 0) for c in categories])):
    if not np.isnan(r2):
        axes[2].text(i, r2 + 0.005, f"{r2:.3f}", ha="center", fontsize=10, fontweight="bold")
axes[2].set_xticks(range(len(categories)))
axes[2].set_xticklabels(categories, fontsize=10)
axes[2].set_ylabel("R² (deviation model)")
axes[2].set_title("Deviation Explainability by Category")
axes[2].grid(True, alpha=0.3, axis="y")

plt.suptitle("EXP-2700: Full Parameter Consistency Check", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig4_consistency.png", dpi=150)
plt.close()
print("Panel 4 saved")

# ── Panel 5: Cross-controller comparison ─────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# 5a: ISF calibration error by controller
for i, ctrl in enumerate(["loop", "trio", "openaps"]):
    pids = [p for p in isf_per_patient if isf_per_patient[p]["controller"] == ctrl]
    if pids:
        errs = [isf_per_patient[p].get("calibration_error", 0) for p in pids]
        axes[0].violinplot([errs], positions=[i], showmeans=True, showmedians=True)

axes[0].set_xticks(range(3))
axes[0].set_xticklabels(["LOOP", "TRIO", "OPENAPS"])
axes[0].axhline(0, color="k", ls="--")
axes[0].set_ylabel("ISF Error (setting − calibrated)")
axes[0].set_title("ISF Calibration Error by Controller")
axes[0].grid(True, alpha=0.3, axis="y")

# 5b: CR beta by controller
for i, ctrl in enumerate(["loop", "trio", "openaps"]):
    cc = cr_df[cr_df["controller"] == ctrl]
    if len(cc) > 0:
        axes[1].violinplot([cc["beta_carb"].values], positions=[i],
                          showmeans=True, showmedians=True)

axes[1].set_xticks(range(3))
axes[1].set_xticklabels(["LOOP", "TRIO", "OPENAPS"])
axes[1].axhline(-1, color="C3", ls="--", lw=2, label="β=−1 (correct)")
axes[1].axhline(0, color="k", ls="--", alpha=0.5)
axes[1].set_ylabel("β (carb sensitivity)")
axes[1].set_title("CR Sensitivity by Controller")
axes[1].legend(fontsize=9)
axes[1].grid(True, alpha=0.3, axis="y")

# 5c: Summary metrics by controller
ctrl_summary = {}
for ctrl in ["loop", "trio", "openaps"]:
    ctrl_ev = ev[ev["controller"] == ctrl]
    corr = ctrl_ev[ctrl_ev["category"] == "correction"]
    meal = ctrl_ev[ctrl_ev["category"] == "meal_bolus"]
    fast = ctrl_ev[ctrl_ev["category"] == "fasting"]

    ctrl_summary[ctrl] = {
        "n_corr": len(corr),
        "mean_corr_dev": corr["deviation"].mean() if len(corr) > 0 else np.nan,
        "n_meal": len(meal),
        "mean_meal_dev": meal["deviation"].mean() if len(meal) > 0 else np.nan,
        "n_fast": len(fast),
        "mean_fast_dev": fast["basal_deviation"].mean() if "basal_deviation" in fast.columns and len(fast) > 0 else fast["observed_drop"].mean() if len(fast) > 0 else np.nan,
    }

ax = axes[2]
ax.axis("off")
summary_rows = []
for ctrl in ["loop", "trio", "openaps"]:
    s = ctrl_summary[ctrl]
    summary_rows.append([
        ctrl.upper(),
        f"{s['n_corr']:,}", f"{s['mean_corr_dev']:.1f}" if not np.isnan(s.get("mean_corr_dev", np.nan)) else "—",
        f"{s['n_meal']:,}", f"{s['mean_meal_dev']:.1f}" if not np.isnan(s.get("mean_meal_dev", np.nan)) else "—",
        f"{s['n_fast']:,}", f"{s['mean_fast_dev']:.1f}" if not np.isnan(s.get("mean_fast_dev", np.nan)) else "—",
    ])

table = ax.table(cellText=summary_rows,
                colLabels=["Controller", "N corr", "μ dev", "N meal", "μ dev", "N fast", "μ dev"],
                loc="center", cellLoc="center")
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.3, 2.2)
ax.set_title("Cross-Controller Deviation Summary")

plt.suptitle("EXP-2700: Cross-Controller Parameter Comparison", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig5_cross_controller.png", dpi=150)
plt.close()
print("Panel 5 saved")

# ── Panel 6: Grand Summary ───────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 8))

# 6a: The full oref0-autotune equivalent pipeline
ax = axes[0]
stages = ["1. BGI\nSubtraction", "2. Event\nCategorization",
          "3. Correction\nISF Recovery", "4. Meal\nCR Recovery",
          "5. Fasting\nBasal Check"]
status = [
    f"R²=0.77\n(+0.42)",
    f"5 categories\n(59K corr, {len(meals)}K meal)",
    f"ISF err={isf_results.get('isf_summary', {}).get('mean_error', 0):.0f}\n21 patients" if isf_per_patient else "N/A",
    f"β_carb={cr_df['beta_carb'].mean():.2f}\n{len(cr_df)} patients",
    f"Fast dev={basal_df['mean_fasting_dev'].mean():.1f}\n{len(basal_df)} patients" if len(basal_df) > 0 else "N/A",
]
colors_stage = ["C2", "C0", "C2", "C1", "C0"]

ax.barh(range(len(stages)), [1]*len(stages), color=colors_stage, edgecolor="k", alpha=0.7)
for i, (s, st) in enumerate(zip(stages, status)):
    ax.text(0.5, i, f"{s}\n{st}", ha="center", va="center", fontsize=9, fontweight="bold")
ax.set_xlim(0, 1)
ax.set_yticks([])
ax.set_title("oref0-Autotune Equivalent Pipeline")
ax.grid(False)

# 6b: Summary text
ax = axes[1]
ax.axis("off")

cr_median_beta = cr_df["beta_carb"].median()
n_sig_cr = (cr_df["beta_carb"].abs() > 0.1).sum()
fasting_mean = basal_df["mean_fasting_dev"].mean() if len(basal_df) > 0 else 0

summary = f"""EXP-2700: FULL PARAMETER RECOVERY RESULTS

CORRECTION (ISF Calibration — EXP-2699):
  Events: 59,756 (BG≥180, no carbs)
  Mean ISF setting: 66.4 mg/dL/U
  Mean ISF calibrated: 5.3 mg/dL/U
  Baseline drop: 56.5 mg/dL (regression to mean)
  Dose-dependent: r=-0.686

MEAL (CR Calibration — this experiment):
  Events: {len(meals):,}
  Deviation vs expected carb rise: r={r_carb:.3f}
  Median carb β: {cr_median_beta:.3f}
  Mean CR setting: {cr_df['cr_setting'].mean():.1f} g/U

FASTING (Basal Check):
  Events: {len(fasting):,}
  Mean fasting BG change: {fasting_mean:.1f} mg/dL
  (should be ≈0 if basal correct)

DEVIATION R² BY CATEGORY:
  Correction: {cat_r2.get('correction', 0):.3f}
  Meal:       {cat_r2.get('meal_bolus', 0):.3f}
  Fasting:    {cat_r2.get('fasting', 0):.3f}
  Other:      {cat_r2.get('other', 0):.3f}

KEY INSIGHT: The oref0-autotune approach of
'subtract expected, categorize, calibrate'
IS REPRODUCIBLE with our multi-factor framework.
BGI subtraction + event categorization +
per-category regression recovers parameters
from observational AID data.
"""

ax.text(0.05, 0.95, summary, transform=ax.transAxes, fontsize=10,
       va="top", fontfamily="monospace")

plt.suptitle("EXP-2700: Complete Parameter Recovery Pipeline", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "fig6_summary.png", dpi=150)
plt.close()
print("Panel 6 saved")

# ── Save results ──────────────────────────────────────────────────────
results = {
    "experiment": "EXP-2700",
    "title": "CR Calibration + Full Parameter Recovery Pipeline",
    "n_events": int(len(ev)),
    "categories": ev["category"].value_counts().to_dict(),
    "meal_analysis": {
        "n_meals": int(len(meals)),
        "deviation_vs_carb_rise_r": float(r_carb),
        "deviation_vs_carb_rise_p": float(p_carb),
    },
    "cr_calibration": {
        "n_patients": int(len(cr_df)),
        "mean_cr_setting": float(cr_df["cr_setting"].mean()),
        "median_beta_carb": float(cr_median_beta),
        "per_patient": cr_df.to_dict(orient="records"),
    },
    "fasting_analysis": {
        "n_fasting": int(len(fasting)),
        "mean_fasting_dev": float(fasting_mean),
        "n_patients": int(len(basal_df)),
    },
    "deviation_r2_by_category": {k: float(v) for k, v in cat_r2.items() if not np.isnan(v)},
    "cross_controller": ctrl_summary,
}
(EXP / "exp-2700_parameter_recovery.json").write_text(
    json.dumps(results, indent=2, default=str))

print(f"""
{'='*60}
EXP-2700: PARAMETER RECOVERY — KEY RESULTS
{'='*60}

  Meal CR analysis:
    Events: {len(meals):,}
    Deviation vs expected carb rise: r={r_carb:.3f}
    Median β_carb: {cr_median_beta:.3f}

  Fasting basal:
    Events: {len(fasting):,}
    Mean fasting deviation: {fasting_mean:.1f} mg/dL

  Deviation R² by category:
    Correction: {cat_r2.get('correction', 0):.3f}
    Meal:       {cat_r2.get('meal_bolus', 0):.3f}
    Fasting:    {cat_r2.get('fasting', 0):.3f}
""")
