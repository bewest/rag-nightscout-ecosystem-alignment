#!/usr/bin/env python3
"""EXP-2711: Baseline Return Model — Quantifying the Supply Side

MOTIVATION:
  EXP-2681 showed BG drops ~74 mg/dL regardless of insulin dose. EXP-2699 found
  ISF settings are 8-14× overestimated because the current pipeline attributes
  the ENTIRE BG drop to insulin, ignoring the supply side (EGP, homeostatic
  regulation, regression to mean).

  The ~56.5 mg/dL "baseline drop" IS the supply side — hepatic glucose production
  and homeostatic mechanisms pulling glucose toward equilibrium. In a homeostatic
  system, deconfounding requires modeling BOTH sides.

  This experiment quantifies the supply side empirically to enable bilateral
  subtraction in subsequent experiments (EXP-2712, 2713).

MODEL:
  observed_drop = supply_return(BG0, hour, glycogen) + insulin_effect + residual

  supply_return is modeled as:
    baseline_drop = β0 + β1×(BG0 - 120) + β2×hour_block + β3×carbs_48h

  The equilibrium target (~120 mg/dL) comes from metabolic_engine.py's
  _DECAY_TARGET = 120.0, validated in EXP-1771.

HYPOTHESES:
  H1: Supply model R² > 0.10 (BG0 alone explains most of the "baseline drop")
  H2: Supply model R² > demand model R² (supply > insulin for BG prediction)
  H3: After supply subtraction, insulin dose becomes a STRONGER predictor
      of the residual (removing supply unmasks the demand signal)
  H4: Per-patient supply models outperform population model by <5% R²
      (supply-side physics is universal, unlike demand-side ISF)

DESIGN:
  - Extract correction events: BG≥180, carbs<5g, dose≥0.3U, 2h horizon
  - Fit supply-only model: drop ~ f(BG0, hour, glycogen)
  - Fit demand-only model: drop ~ f(dose, IOB, channels)
  - Fit bilateral model: drop ~ f(supply_terms + demand_terms)
  - Compare R² waterfall: supply alone → + demand → bilateral
  - Measure: does supply subtraction UNMASK insulin signal?

PANELS (6-panel dashboard):
  1. BG drop vs starting BG (the supply curve) — per controller
  2. Supply model: fitted baseline return curve
  3. Demand-only vs supply-only vs bilateral R² comparison
  4. After supply subtraction: residual vs dose (unmasked insulin signal?)
  5. Per-patient supply intercepts (equilibrium points)
  6. Waterfall: stepwise R² from supply, demand, and interaction terms

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ──────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2711_baseline_return_model.json")
VIS_DIR = Path("visualizations/baseline-return-model")
VIS_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────
EXP_ID = "EXP-2711"
EXP_TITLE = "Baseline Return Model — Quantifying the Supply Side"

BG_FLOOR = 180.0
EQUILIBRIUM = 120.0        # metabolic_engine.py _DECAY_TARGET
HORIZON_STEPS = 24         # 2h demand phase
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12  # 48h at 5-min intervals

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

# EXP-2698 validated coefficients (demand side)
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5


# ── Data Loading ───────────────────────────────────────────────────────

def load_data():
    """Load grid + devicestatus, attach controller labels, filter to qualified."""
    print(f"[{EXP_ID}] Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid["controller"] = grid["patient_id"].map(ctrl_map)

    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    grid = grid[grid["patient_id"].isin(qual)].copy()

    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def compute_48h_carbs(grid):
    """Add 48h rolling carb history as glycogen proxy."""
    if "carbs" not in grid.columns:
        grid["carbs_48h"] = 0.0
        return grid

    result = []
    for pid, pg in grid.groupby("patient_id"):
        pg = pg.sort_values("time").copy()
        carbs = pg["carbs"].fillna(0).values
        carbs_48h = np.zeros(len(carbs))
        cumsum = np.cumsum(carbs)
        for i in range(len(carbs)):
            start = max(0, i - CARB_HISTORY_STEPS)
            carbs_48h[i] = cumsum[i] - (cumsum[start - 1] if start > 0 else 0)
        pg["carbs_48h"] = carbs_48h
        result.append(pg)
    return pd.concat(result, ignore_index=True)


# ── Event Extraction ───────────────────────────────────────────────────

def extract_events(grid):
    """Extract correction events with supply and demand features."""
    print(f"[{EXP_ID}] Extracting correction events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    has_carbs_48h = "carbs_48h" in grid.columns
    events = []

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].fillna(0).values
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        smb = pg["bolus_smb"].fillna(0).values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].fillna(0).values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].fillna(0).values if has_carbs else np.zeros(len(pg))
        carbs_48h = pg["carbs_48h"].values if has_carbs_48h else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue
            if bg0 < BG_FLOOR:
                continue

            # Demand-side features
            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))

            if carbs_2h > 5.0:
                continue  # not a clean correction

            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            # Supply-side features
            bg_above_eq = bg0 - EQUILIBRIUM  # distance from equilibrium
            iob_start = float(iob[i]) if not np.isnan(iob[i]) else 0.0
            roc_start = float(glucose[i] - glucose[i - 1]) if i > 0 else 0.0
            c48 = float(carbs_48h[i]) if not np.isnan(carbs_48h[i]) else 0.0

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour + ts.minute / 60.0
            except Exception:
                hour = 0.0
            block_idx = min(int(hour) // 4, 5)

            observed_drop = bg0 - bg_end

            events.append({
                "patient_id": pid,
                "controller": ctrl,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                # Supply-side
                "bg_above_eq": bg_above_eq,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "carbs_48h": c48,
                "roc_start": roc_start,
                # Demand-side
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "total_insulin": total_insulin,
                "iob_start": iob_start,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} correction events from {df['patient_id'].nunique()} patients")
    return df


# ── OLS Helper ─────────────────────────────────────────────────────────

def ols_r2(X, y):
    """Compute R² from OLS regression. Returns R², coefficients, predictions."""
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X_c, y_c = X[mask], y[mask]
    if len(y_c) < X_c.shape[1] + 2:
        return 0.0, np.zeros(X_c.shape[1]), np.full(len(y), np.nan)
    X_aug = np.column_stack([np.ones(len(X_c)), X_c])
    try:
        beta, _, _, _ = np.linalg.lstsq(X_aug, y_c, rcond=None)
    except np.linalg.LinAlgError:
        return 0.0, np.zeros(X_c.shape[1]), np.full(len(y), np.nan)
    pred_c = X_aug @ beta
    ss_res = np.sum((y_c - pred_c) ** 2)
    ss_tot = np.sum((y_c - np.mean(y_c)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Full predictions (including NaN rows as NaN)
    pred = np.full(len(y), np.nan)
    pred[mask] = pred_c
    return r2, beta, pred


# ── Analysis ───────────────────────────────────────────────────────────

def analyze_supply_vs_demand(df):
    """Core analysis: supply-only vs demand-only vs bilateral R²."""
    print(f"\n[{EXP_ID}] === SUPPLY vs DEMAND ANALYSIS ===")
    y = df["observed_drop"].values

    # --- Supply-only model ---
    # Model: drop ~ β0 + β1×bg_above_eq + β2×block_dummies + β3×carbs_48h
    block_dummies = pd.get_dummies(df["block_idx"], prefix="block", drop_first=True).values
    X_supply_bg = df[["bg_above_eq"]].values
    X_supply_full = np.column_stack([
        df["bg_above_eq"].values,
        block_dummies,
        df["carbs_48h"].values,
        df["roc_start"].values,
    ])

    r2_supply_bg, beta_supply_bg, pred_supply_bg = ols_r2(X_supply_bg, y)
    r2_supply_full, beta_supply_full, pred_supply_full = ols_r2(X_supply_full, y)

    print(f"  Supply (BG0 only):         R² = {r2_supply_bg:.4f}")
    print(f"  Supply (full):             R² = {r2_supply_full:.4f}")

    # --- Demand-only model ---
    X_demand_dose = df[["total_insulin"]].values
    X_demand_channels = np.column_stack([
        df["bolus_2h"].values,
        df["smb_2h"].values,
        df["excess_basal_2h"].values,
    ])
    X_demand_full = np.column_stack([
        df["total_insulin"].values,
        df["iob_start"].values,
    ])

    r2_demand_dose, _, _ = ols_r2(X_demand_dose, y)
    r2_demand_channels, _, _ = ols_r2(X_demand_channels, y)
    r2_demand_full, _, _ = ols_r2(X_demand_full, y)

    print(f"  Demand (dose only):        R² = {r2_demand_dose:.4f}")
    print(f"  Demand (channels):         R² = {r2_demand_channels:.4f}")
    print(f"  Demand (full):             R² = {r2_demand_full:.4f}")

    # --- Bilateral model ---
    X_bilateral = np.column_stack([
        df["bg_above_eq"].values,
        block_dummies,
        df["carbs_48h"].values,
        df["roc_start"].values,
        df["total_insulin"].values,
        df["iob_start"].values,
    ])
    r2_bilateral, beta_bilateral, pred_bilateral = ols_r2(X_bilateral, y)
    print(f"  Bilateral (supply+demand): R² = {r2_bilateral:.4f}")

    # --- Patient fixed effects + bilateral ---
    patient_dummies = pd.get_dummies(df["patient_id"], prefix="pid", drop_first=True).values
    X_full = np.column_stack([X_bilateral, patient_dummies])
    r2_full, _, pred_full = ols_r2(X_full, y)
    print(f"  Full (bilateral+FE):       R² = {r2_full:.4f}")

    # --- H3: Does supply subtraction unmask insulin signal? ---
    supply_residual = y - pred_supply_full
    mask = np.isfinite(supply_residual)
    r2_demand_on_raw, _, _ = ols_r2(X_demand_dose[mask], y[mask])
    r2_demand_on_residual, _, _ = ols_r2(X_demand_dose[mask], supply_residual[mask])
    print(f"\n  H3 — Insulin signal after supply subtraction:")
    print(f"    Dose→raw_drop R²:        {r2_demand_on_raw:.4f}")
    print(f"    Dose→supply_residual R²: {r2_demand_on_residual:.4f}")
    print(f"    Unmasking ratio:         {r2_demand_on_residual / max(r2_demand_on_raw, 0.001):.1f}×")

    return {
        "r2_supply_bg": r2_supply_bg,
        "r2_supply_full": r2_supply_full,
        "r2_demand_dose": r2_demand_dose,
        "r2_demand_channels": r2_demand_channels,
        "r2_demand_full": r2_demand_full,
        "r2_bilateral": r2_bilateral,
        "r2_full": r2_full,
        "r2_demand_on_raw": r2_demand_on_raw,
        "r2_demand_on_residual": r2_demand_on_residual,
        "supply_beta_intercept": float(beta_supply_bg[0]),
        "supply_beta_bg_above_eq": float(beta_supply_bg[1]),
        "pred_supply_full": pred_supply_full,
        "pred_bilateral": pred_bilateral,
    }


def analyze_per_patient_supply(df):
    """Per-patient supply model to test H4 (universality)."""
    print(f"\n[{EXP_ID}] === PER-PATIENT SUPPLY MODELS ===")
    results = []
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        if len(pdf) < 30:
            continue
        y = pdf["observed_drop"].values
        X = pdf[["bg_above_eq"]].values
        r2, beta, _ = ols_r2(X, y)

        # Supply-side equilibrium: where does predicted drop = 0?
        # drop = β0 + β1×(BG0-120) = 0  →  BG0 = 120 - β0/β1
        if len(beta) > 1 and abs(beta[1]) > 0.001:
            eq_point = EQUILIBRIUM - beta[0] / beta[1]
        else:
            eq_point = np.nan

        ctrl = pdf["controller"].iloc[0]
        mean_drop = float(np.mean(y))
        mean_bg0 = float(np.mean(pdf["bg0"]))
        mean_dose = float(np.mean(pdf["total_insulin"]))

        results.append({
            "patient_id": pid,
            "controller": ctrl,
            "n": len(pdf),
            "r2_supply": float(r2),
            "beta_intercept": float(beta[0]),
            "beta_bg_slope": float(beta[1]),
            "equilibrium_point": float(eq_point),
            "mean_drop": mean_drop,
            "mean_bg0": mean_bg0,
            "mean_dose": mean_dose,
        })
        print(f"  {pid:20s} {ctrl:8s} n={len(pdf):5d}  R²={r2:.3f}  "
              f"slope={beta[1]:.3f}  eq={eq_point:.0f} mg/dL  "
              f"drop={mean_drop:.0f}  dose={mean_dose:.1f}U")

    return results


def analyze_supply_curve_shape(df):
    """Characterize the supply return curve: linear? saturating? per-controller?"""
    print(f"\n[{EXP_ID}] === SUPPLY CURVE SHAPE ===")
    results = {}

    for ctrl in sorted(df["controller"].unique()):
        cdf = df[df["controller"] == ctrl]
        bg_above = cdf["bg_above_eq"].values
        drop = cdf["observed_drop"].values

        # Linear fit
        slope, intercept, r, p, se = stats.linregress(bg_above, drop)
        results[ctrl] = {
            "n": len(cdf),
            "slope": float(slope),
            "intercept": float(intercept),
            "r": float(r),
            "r2": float(r ** 2),
            "p": float(p),
            "mean_drop": float(np.mean(drop)),
            "mean_bg0": float(np.mean(cdf["bg0"])),
            "mean_dose": float(np.mean(cdf["total_insulin"])),
        }
        print(f"  {ctrl:8s}: slope={slope:.3f} mg/dL per mg/dL above eq, "
              f"intercept={intercept:.1f}, r={r:.3f}, "
              f"mean_drop={np.mean(drop):.1f}, mean_dose={np.mean(cdf['total_insulin']):.1f}U")

    return results


def stepwise_waterfall(df):
    """Stepwise R² waterfall: supply terms first, then demand terms."""
    print(f"\n[{EXP_ID}] === STEPWISE WATERFALL ===")
    y = df["observed_drop"].values
    steps = []
    X_cum = np.empty((len(df), 0))

    factor_sets = [
        ("BG_above_eq (supply)", df[["bg_above_eq"]].values),
        ("Circadian blocks (supply)", pd.get_dummies(df["block_idx"], prefix="blk", drop_first=True).values),
        ("48h carbs (supply)", df[["carbs_48h"]].values),
        ("Glucose ROC (supply)", df[["roc_start"]].values),
        ("Total insulin (demand)", df[["total_insulin"]].values),
        ("IOB start (demand)", df[["iob_start"]].values),
        ("Channels (demand)", df[["bolus_2h", "smb_2h", "excess_basal_2h"]].values),
        ("Patient FE", pd.get_dummies(df["patient_id"], prefix="pid", drop_first=True).values),
    ]

    prev_r2 = 0.0
    for name, X_new in factor_sets:
        X_cum = np.column_stack([X_cum, X_new]) if X_cum.shape[1] > 0 else X_new
        r2, _, _ = ols_r2(X_cum, y)
        delta = r2 - prev_r2
        steps.append({
            "factor": name,
            "cumulative_r2": float(r2),
            "delta_r2": float(delta),
            "n_columns": X_cum.shape[1],
        })
        print(f"  + {name:30s}  R²={r2:.4f}  Δ={delta:+.4f}  (cols={X_cum.shape[1]})")
        prev_r2 = r2

    return steps


# ── Visualization ──────────────────────────────────────────────────────

def plot_dashboard(df, analysis, per_patient, curve_shape, waterfall):
    """6-panel dashboard."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}\n"
                 f"N={len(df):,} events, {df['patient_id'].nunique()} patients",
                 fontsize=14, fontweight="bold")

    ctrl_colors = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}

    # Panel 1: BG drop vs starting BG (the supply curve)
    ax = axes[0, 0]
    for ctrl in sorted(df["controller"].unique()):
        cdf = df[df["controller"] == ctrl]
        ax.scatter(cdf["bg_above_eq"], cdf["observed_drop"],
                   alpha=0.05, s=2, color=ctrl_colors.get(ctrl, "gray"), label=ctrl)
        # Bin means
        bins = np.arange(60, 300, 20)
        bin_idx = np.digitize(cdf["bg_above_eq"], bins)
        for b in range(1, len(bins)):
            mask = bin_idx == b
            if mask.sum() > 10:
                ax.plot(bins[b - 1] + 10, cdf["observed_drop"].values[mask].mean(),
                        "o", color=ctrl_colors.get(ctrl, "gray"), markersize=6)
    ax.set_xlabel("BG above equilibrium (mg/dL)")
    ax.set_ylabel("Observed BG drop (mg/dL)")
    ax.set_title("Panel 1: Supply Curve\n(BG drop vs starting BG)")
    ax.legend(fontsize=8)
    ax.axhline(0, color="k", ls="--", alpha=0.3)

    # Panel 2: Supply model fit
    ax = axes[0, 1]
    pred = analysis["pred_supply_full"]
    actual = df["observed_drop"].values
    mask = np.isfinite(pred)
    ax.scatter(pred[mask], actual[mask], alpha=0.02, s=2, color="#666")
    lims = [min(pred[mask].min(), actual[mask].min()),
            max(pred[mask].max(), actual[mask].max())]
    ax.plot(lims, lims, "r--", alpha=0.5, label="Perfect")
    ax.set_xlabel("Supply model prediction (mg/dL)")
    ax.set_ylabel("Actual BG drop (mg/dL)")
    ax.set_title(f"Panel 2: Supply Model Fit\nR²={analysis['r2_supply_full']:.3f}")
    ax.legend(fontsize=8)

    # Panel 3: R² comparison bar chart
    ax = axes[0, 2]
    models = ["Supply\n(BG₀ only)", "Supply\n(full)", "Demand\n(dose)", "Demand\n(full)",
              "Bilateral", "Full\n(+FE)"]
    r2s = [analysis["r2_supply_bg"], analysis["r2_supply_full"],
           analysis["r2_demand_dose"], analysis["r2_demand_full"],
           analysis["r2_bilateral"], analysis["r2_full"]]
    colors = ["#4CAF50", "#2E7D32", "#2196F3", "#1565C0", "#9C27B0", "#4A148C"]
    bars = ax.bar(models, r2s, color=colors, edgecolor="white")
    for bar, r2 in zip(bars, r2s):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                f"{r2:.3f}", ha="center", fontsize=8)
    ax.set_ylabel("R²")
    ax.set_title("Panel 3: Supply vs Demand R²")
    ax.set_ylim(0, max(r2s) * 1.2)

    # Panel 4: Unmasking — insulin signal after supply subtraction
    ax = axes[1, 0]
    supply_resid = actual - pred
    mask2 = np.isfinite(supply_resid)
    dose = df["total_insulin"].values
    # Bin by dose
    dose_bins = np.percentile(dose[mask2], np.arange(0, 101, 10))
    dose_bin_idx = np.digitize(dose[mask2], dose_bins)
    raw_means = []
    resid_means = []
    bin_centers = []
    for b in range(1, len(dose_bins)):
        m = dose_bin_idx == b
        if m.sum() > 10:
            bin_centers.append((dose_bins[b - 1] + dose_bins[min(b, len(dose_bins) - 1)]) / 2)
            raw_means.append(np.mean(actual[mask2][m]))
            resid_means.append(np.mean(supply_resid[mask2][m]))
    ax.plot(bin_centers, raw_means, "o-", color="#2196F3", label="Raw drop vs dose")
    ax.plot(bin_centers, resid_means, "s-", color="#4CAF50", label="Supply-subtracted vs dose")
    ax.set_xlabel("Total insulin (U)")
    ax.set_ylabel("BG change (mg/dL)")
    ax.set_title(f"Panel 4: Unmasking Insulin Signal\n"
                 f"Dose→raw R²={analysis['r2_demand_on_raw']:.3f}, "
                 f"Dose→resid R²={analysis['r2_demand_on_residual']:.3f}")
    ax.legend(fontsize=8)
    ax.axhline(0, color="k", ls="--", alpha=0.3)

    # Panel 5: Per-patient equilibrium points
    ax = axes[1, 1]
    pp = pd.DataFrame(per_patient)
    for ctrl in sorted(pp["controller"].unique()):
        cpp = pp[pp["controller"] == ctrl]
        ax.scatter(cpp["beta_bg_slope"], cpp["equilibrium_point"],
                   s=cpp["n"] / 20, color=ctrl_colors.get(ctrl, "gray"),
                   alpha=0.7, label=ctrl, edgecolor="white")
        for _, row in cpp.iterrows():
            ax.annotate(row["patient_id"][:8], (row["beta_bg_slope"], row["equilibrium_point"]),
                        fontsize=5, alpha=0.6)
    ax.set_xlabel("Supply slope (mg/dL drop per mg/dL above eq)")
    ax.set_ylabel("Equilibrium point (mg/dL)")
    ax.set_title("Panel 5: Per-Patient Supply Parameters")
    ax.axhline(EQUILIBRIUM, color="red", ls="--", alpha=0.3, label=f"Eq={EQUILIBRIUM}")
    ax.legend(fontsize=8)

    # Panel 6: Waterfall
    ax = axes[1, 2]
    wf = pd.DataFrame(waterfall)
    supply_mask = wf["factor"].str.contains("supply")
    demand_mask = wf["factor"].str.contains("demand")
    fe_mask = wf["factor"].str.contains("FE")
    bar_colors = []
    for _, row in wf.iterrows():
        if "supply" in row["factor"]:
            bar_colors.append("#4CAF50")
        elif "demand" in row["factor"]:
            bar_colors.append("#2196F3")
        else:
            bar_colors.append("#9E9E9E")
    short_labels = [f.split("(")[0].strip() for f in wf["factor"]]
    ax.bar(short_labels, wf["delta_r2"], color=bar_colors, edgecolor="white")
    ax.set_ylabel("Δ R²")
    ax.set_title(f"Panel 6: Waterfall (Supply-First)\nTotal R²={wf['cumulative_r2'].iloc[-1]:.3f}")
    ax.tick_params(axis="x", rotation=45, labelsize=7)

    plt.tight_layout()
    out_path = VIS_DIR / "exp-2711-dashboard.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


# ── Hypothesis Testing ─────────────────────────────────────────────────

def test_hypotheses(analysis, per_patient):
    """Evaluate H1-H4."""
    results = {}

    # H1: Supply R² > 0.10
    h1 = analysis["r2_supply_full"] > 0.10
    results["H1"] = {
        "verdict": "PASS" if h1 else "FAIL",
        "supply_r2": analysis["r2_supply_full"],
        "threshold": 0.10,
    }

    # H2: Supply R² > Demand R²
    h2 = analysis["r2_supply_full"] > analysis["r2_demand_full"]
    results["H2"] = {
        "verdict": "PASS" if h2 else "FAIL",
        "supply_r2": analysis["r2_supply_full"],
        "demand_r2": analysis["r2_demand_full"],
        "ratio": analysis["r2_supply_full"] / max(analysis["r2_demand_full"], 0.001),
    }

    # H3: Supply subtraction unmasks insulin (residual R² > raw R²)
    h3 = analysis["r2_demand_on_residual"] > analysis["r2_demand_on_raw"]
    results["H3"] = {
        "verdict": "PASS" if h3 else "FAIL",
        "dose_r2_raw": analysis["r2_demand_on_raw"],
        "dose_r2_after_supply_subtraction": analysis["r2_demand_on_residual"],
        "unmasking_ratio": analysis["r2_demand_on_residual"] / max(analysis["r2_demand_on_raw"], 0.001),
    }

    # H4: Per-patient supply ≈ population (within 5% R²)
    pp = pd.DataFrame(per_patient)
    if len(pp) > 0:
        pop_r2 = analysis["r2_supply_bg"]
        patient_r2s = pp["r2_supply"].values
        mean_patient_r2 = float(np.mean(patient_r2s))
        gap = mean_patient_r2 - pop_r2
        h4 = gap < 0.05
        results["H4"] = {
            "verdict": "PASS" if h4 else "FAIL",
            "population_r2": pop_r2,
            "mean_per_patient_r2": mean_patient_r2,
            "gap": float(gap),
        }
    else:
        results["H4"] = {"verdict": "SKIP", "reason": "insufficient patients"}

    for h, v in results.items():
        print(f"  {h}: {v['verdict']}")
    return results


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print(f"\n{'=' * 60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'=' * 60}\n")

    grid = load_data()
    grid = compute_48h_carbs(grid)
    df = extract_events(grid)

    if len(df) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    analysis = analyze_supply_vs_demand(df)
    per_patient = analyze_per_patient_supply(df)
    curve_shape = analyze_supply_curve_shape(df)
    waterfall = stepwise_waterfall(df)

    print(f"\n[{EXP_ID}] === HYPOTHESIS TESTING ===")
    hypotheses = test_hypotheses(analysis, per_patient)

    # Visualize
    print(f"\n[{EXP_ID}] === VISUALIZATION ===")
    plot_dashboard(df, analysis, per_patient, curve_shape, waterfall)

    # Summary statistics
    summary = {
        "baseline_drop_mean": float(df["observed_drop"].mean()),
        "baseline_drop_median": float(df["observed_drop"].median()),
        "mean_bg0": float(df["bg0"].mean()),
        "mean_dose": float(df["total_insulin"].mean()),
        "supply_intercept": analysis["supply_beta_intercept"],
        "supply_slope": analysis["supply_beta_bg_above_eq"],
        "per_controller": curve_shape,
    }

    # Save results
    out = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": len(df),
        "n_patients": int(df["patient_id"].nunique()),
        "summary": summary,
        "r2_comparison": {
            "supply_bg_only": analysis["r2_supply_bg"],
            "supply_full": analysis["r2_supply_full"],
            "demand_dose_only": analysis["r2_demand_dose"],
            "demand_full": analysis["r2_demand_full"],
            "bilateral": analysis["r2_bilateral"],
            "full_with_FE": analysis["r2_full"],
        },
        "unmasking": {
            "dose_r2_on_raw_drop": analysis["r2_demand_on_raw"],
            "dose_r2_on_supply_residual": analysis["r2_demand_on_residual"],
        },
        "waterfall": waterfall,
        "per_patient": per_patient,
        "hypotheses": hypotheses,
        "verdict_summary": {k: v["verdict"] for k, v in hypotheses.items()},
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results: {OUT_JSON}")
    print(f"\n{'=' * 60}")
    print(f"  {EXP_ID} COMPLETE — Verdicts: {out['verdict_summary']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
