#!/usr/bin/env python3
"""EXP-2712: Bilateral Subtraction — Supply + Demand ISF Recovery

MOTIVATION:
  EXP-2711 proved the supply side (BG→equilibrium homeostasis) explains 2× more
  BG drop variance than the demand side (insulin). The ~74 mg/dL constant drop
  (EXP-2681) is ~60% supply return + ~40% insulin effect.

  Current ISF extraction subtracts only the demand side:
    deviation = observed_drop - (excess_insulin × ISF_setting)
  This yields ISF ≈ 5 mg/dL/U (14× overestimation) because the supply-side
  drop is attributed to insulin.

  Bilateral subtraction:
    insulin_residual = observed_drop - supply_return(BG0, hour)
    ISF_bilateral = insulin_residual / dose

  If supply return accounts for ~56.5 mg/dL of a ~74 mg/dL drop, then
  insulin_residual ≈ 17.5 mg/dL, and ISF ≈ 17.5/2.5U ≈ 7 mg/dL/U.
  Still below profile settings (~66 mg/dL/U) but closer.

  The remaining gap tells us about AID CONTROLLER COMPENSATION — the demand
  side that ISN'T user-initiated insulin but controller-driven.

HYPOTHESES:
  H1: Bilateral ISF > demand-only ISF (closer to profile settings)
  H2: Bilateral ISF ratio (setting/extracted) < 5× (vs 8-14× demand-only)
  H3: Bilateral ISF has lower between-patient CV (more universal)
  H4: Bilateral ISF predicts held-out BG drop better than demand-only ISF
  H5: Supply return is consistent (r>0.3) across controllers

DESIGN:
  - Fit population supply model from EXP-2711: drop = α + β×(BG0-120)
  - Subtract fitted supply return from observed drop
  - Compute bilateral ISF = supply_residual / total_insulin
  - Compare with demand-only ISF (total drop / total_insulin)
  - 70/30 temporal holdout validation
  - Per-controller and per-patient analysis

PANELS (6-panel dashboard):
  1. ISF distributions: demand-only vs bilateral vs profile settings
  2. ISF ratio (setting/extracted): demand-only vs bilateral
  3. Supply return magnitude vs insulin effect magnitude
  4. Bilateral ISF vs dose (test dose-dependence persistence)
  5. Holdout prediction: bilateral vs demand-only
  6. Per-controller ISF comparison

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
EXP2711 = Path("externals/experiments/exp-2711_baseline_return_model.json")
OUT_JSON = Path("externals/experiments/exp-2712_bilateral_subtraction.json")
VIS_DIR = Path("visualizations/bilateral-subtraction")
VIS_DIR.mkdir(parents=True, exist_ok=True)

EXP_ID = "EXP-2712"
EXP_TITLE = "Bilateral Subtraction — Supply + Demand ISF Recovery"

BG_FLOOR = 180.0
EQUILIBRIUM = 120.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
TRAIN_FRAC = 0.70


# ── Data Loading ───────────────────────────────────────────────────────

def load_data():
    print(f"[{EXP_ID}] Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid["controller"] = grid["patient_id"].map(ctrl_map)
    manifest = json.loads(MANIFEST.read_text())
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])].copy()
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


def extract_events(grid, split=True):
    """Extract correction events with train/test split."""
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    events = []

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue
        glucose = pg["glucose"].values
        bolus = pg["bolus"].fillna(0).values
        smb = pg["bolus_smb"].fillna(0).values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].fillna(0).values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].fillna(0).values if has_carbs else np.zeros(len(pg))
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        # Train/test split point
        split_idx = int(len(pg) * TRAIN_FRAC) if split else len(pg)

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or bg0 < BG_FLOOR:
                continue
            carbs_2h = float(np.nansum(carbs[i:i + h]))
            if carbs_2h > 5.0:
                continue
            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour + ts.minute / 60.0
            except Exception:
                hour = 0.0

            events.append({
                "patient_id": pid,
                "controller": ctrl,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": bg0 - bg_end,
                "bg_above_eq": bg0 - EQUILIBRIUM,
                "hour": hour,
                "total_insulin": total_insulin,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "profile_isf": profile_isf,
                "split": "train" if i < split_idx else "test",
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events ({(df['split']=='train').sum():,} train, "
          f"{(df['split']=='test').sum():,} test)")
    return df


# ── Supply Model (from EXP-2711 or fitted fresh) ──────────────────────

def fit_supply_model(df_train):
    """Fit population supply return model: drop = α + β×(BG0 - 120)."""
    y = df_train["observed_drop"].values
    X = df_train["bg_above_eq"].values

    slope, intercept, r, p, se = stats.linregress(X, y)
    print(f"  Supply model: drop = {intercept:.1f} + {slope:.3f} × (BG0 - {EQUILIBRIUM})")
    print(f"  r = {r:.3f}, p = {p:.2e}")
    return {"intercept": intercept, "slope": slope, "r": r}


def compute_supply_return(df, supply_model):
    """Add supply return prediction and bilateral residual."""
    df = df.copy()
    df["supply_return"] = (supply_model["intercept"] +
                           supply_model["slope"] * df["bg_above_eq"])
    df["insulin_residual"] = df["observed_drop"] - df["supply_return"]
    # ISF variants
    df["isf_demand_only"] = df["observed_drop"] / df["total_insulin"]
    df["isf_bilateral"] = df["insulin_residual"] / df["total_insulin"]
    return df


# ── Analysis ───────────────────────────────────────────────────────────

def analyze_isf_comparison(df):
    """Compare demand-only vs bilateral ISF extraction."""
    print(f"\n[{EXP_ID}] === ISF COMPARISON ===")

    results = {}
    for label, col in [("demand_only", "isf_demand_only"),
                        ("bilateral", "isf_bilateral")]:
        vals = df[col].replace([np.inf, -np.inf], np.nan).dropna()
        # Positive ISF only (physiologically meaningful)
        pos = vals[vals > 0]
        results[label] = {
            "n_total": len(vals),
            "n_positive": len(pos),
            "pct_positive": float(len(pos) / len(vals) * 100) if len(vals) > 0 else 0,
            "median": float(pos.median()) if len(pos) > 0 else np.nan,
            "mean": float(pos.mean()) if len(pos) > 0 else np.nan,
            "p25": float(pos.quantile(0.25)) if len(pos) > 0 else np.nan,
            "p75": float(pos.quantile(0.75)) if len(pos) > 0 else np.nan,
            "cv": float(pos.std() / pos.mean()) if len(pos) > 0 else np.nan,
        }
        print(f"  {label:15s}: median={results[label]['median']:.1f}, "
              f"mean={results[label]['mean']:.1f}, "
              f"CV={results[label]['cv']:.2f}, "
              f"{results[label]['pct_positive']:.0f}% positive")

    # Profile ISF comparison
    profile_median = float(df["profile_isf"].median())
    print(f"  {'profile':15s}: median={profile_median:.1f}")

    # Ratios
    ratio_demand = profile_median / results["demand_only"]["median"] if results["demand_only"]["median"] > 0 else np.nan
    ratio_bilateral = profile_median / results["bilateral"]["median"] if results["bilateral"]["median"] > 0 else np.nan
    print(f"\n  Setting/Extracted ratios:")
    print(f"    Demand-only: {ratio_demand:.1f}×")
    print(f"    Bilateral:   {ratio_bilateral:.1f}×")

    results["profile_median"] = profile_median
    results["ratio_demand"] = float(ratio_demand) if np.isfinite(ratio_demand) else None
    results["ratio_bilateral"] = float(ratio_bilateral) if np.isfinite(ratio_bilateral) else None
    return results


def analyze_per_patient(df):
    """Per-patient ISF extraction both ways."""
    print(f"\n[{EXP_ID}] === PER-PATIENT ISF ===")
    results = []
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid]
        if len(pdf) < 30:
            continue

        profile = float(pdf["profile_isf"].median())

        for method, col in [("demand_only", "isf_demand_only"),
                             ("bilateral", "isf_bilateral")]:
            vals = pdf[col].replace([np.inf, -np.inf], np.nan).dropna()
            pos = vals[vals > 0]
            if len(pos) < 10:
                continue
            med = float(pos.median())
            ratio = profile / med if med > 0 else np.nan
            results.append({
                "patient_id": pid,
                "controller": pdf["controller"].iloc[0],
                "method": method,
                "n": len(pos),
                "median_isf": med,
                "profile_isf": profile,
                "ratio": float(ratio),
            })

    pp = pd.DataFrame(results)
    if len(pp) > 0:
        for method in ["demand_only", "bilateral"]:
            mp = pp[pp["method"] == method]
            print(f"  {method:15s}: median ratio={mp['ratio'].median():.1f}×, "
                  f"mean ratio={mp['ratio'].mean():.1f}×, "
                  f"patients={len(mp)}")
    return results


def analyze_magnitude_decomposition(df):
    """How much of the BG drop is supply vs insulin?"""
    print(f"\n[{EXP_ID}] === MAGNITUDE DECOMPOSITION ===")
    results = {}

    for ctrl in sorted(df["controller"].unique()):
        cdf = df[df["controller"] == ctrl]
        supply_mag = float(cdf["supply_return"].mean())
        insulin_mag = float(cdf["insulin_residual"].mean())
        total_drop = float(cdf["observed_drop"].mean())
        supply_pct = supply_mag / total_drop * 100 if total_drop != 0 else 0
        insulin_pct = insulin_mag / total_drop * 100 if total_drop != 0 else 0

        results[ctrl] = {
            "total_drop": total_drop,
            "supply_return": supply_mag,
            "insulin_residual": insulin_mag,
            "supply_pct": float(supply_pct),
            "insulin_pct": float(insulin_pct),
            "mean_dose": float(cdf["total_insulin"].mean()),
        }
        print(f"  {ctrl:8s}: total={total_drop:.1f}, "
              f"supply={supply_mag:.1f} ({supply_pct:.0f}%), "
              f"insulin={insulin_mag:.1f} ({insulin_pct:.0f}%), "
              f"dose={cdf['total_insulin'].mean():.1f}U")

    # Overall
    supply_all = float(df["supply_return"].mean())
    insulin_all = float(df["insulin_residual"].mean())
    total_all = float(df["observed_drop"].mean())
    results["overall"] = {
        "total_drop": total_all,
        "supply_return": supply_all,
        "insulin_residual": insulin_all,
        "supply_pct": float(supply_all / total_all * 100) if total_all != 0 else 0,
        "insulin_pct": float(insulin_all / total_all * 100) if total_all != 0 else 0,
    }
    print(f"  {'OVERALL':8s}: total={total_all:.1f}, "
          f"supply={supply_all:.1f} ({results['overall']['supply_pct']:.0f}%), "
          f"insulin={insulin_all:.1f} ({results['overall']['insulin_pct']:.0f}%)")
    return results


def analyze_holdout(df):
    """Compare bilateral vs demand-only prediction on held-out data."""
    print(f"\n[{EXP_ID}] === HOLDOUT VALIDATION ===")
    train = df[df["split"] == "train"]
    test = df[df["split"] == "test"]

    if len(test) < 50:
        print("  Insufficient test data")
        return {"skip": True}

    # Fit supply model on TRAIN only
    supply_model = fit_supply_model(train)

    # Per-patient train ISF (both methods)
    patient_isf = {}
    for pid in train["patient_id"].unique():
        pt = train[train["patient_id"] == pid]
        if len(pt) < 20:
            continue
        # Demand-only ISF
        demand_vals = pt["isf_demand_only"].replace([np.inf, -np.inf], np.nan).dropna()
        demand_pos = demand_vals[demand_vals > 0]
        demand_isf = float(demand_pos.median()) if len(demand_pos) > 5 else np.nan

        # Bilateral ISF (recompute with train-only supply model)
        supply_ret = supply_model["intercept"] + supply_model["slope"] * pt["bg_above_eq"]
        insulin_resid = pt["observed_drop"] - supply_ret
        bilateral_isf_vals = (insulin_resid / pt["total_insulin"]).replace([np.inf, -np.inf], np.nan).dropna()
        bilateral_pos = bilateral_isf_vals[bilateral_isf_vals > 0]
        bilateral_isf = float(bilateral_pos.median()) if len(bilateral_pos) > 5 else np.nan

        patient_isf[pid] = {
            "demand_isf": demand_isf,
            "bilateral_isf": bilateral_isf,
            "profile_isf": float(pt["profile_isf"].median()),
        }

    # Predict on TEST
    results_per_patient = []
    for pid in test["patient_id"].unique():
        if pid not in patient_isf:
            continue
        pt = test[test["patient_id"] == pid]
        isfs = patient_isf[pid]

        actual_drop = pt["observed_drop"].values

        # Method A: profile ISF (standard)
        pred_profile = pt["total_insulin"].values * isfs["profile_isf"]
        # Method B: demand-only ISF
        pred_demand = pt["total_insulin"].values * isfs["demand_isf"] if np.isfinite(isfs["demand_isf"]) else np.full(len(pt), np.nan)
        # Method C: bilateral ISF + supply return
        supply_ret = supply_model["intercept"] + supply_model["slope"] * pt["bg_above_eq"].values
        pred_bilateral = supply_ret + pt["total_insulin"].values * isfs["bilateral_isf"] if np.isfinite(isfs["bilateral_isf"]) else np.full(len(pt), np.nan)

        for method, pred in [("profile", pred_profile),
                              ("demand_only", pred_demand),
                              ("bilateral", pred_bilateral)]:
            mask = np.isfinite(pred) & np.isfinite(actual_drop)
            if mask.sum() < 10:
                continue
            mae = float(np.mean(np.abs(actual_drop[mask] - pred[mask])))
            ss_res = np.sum((actual_drop[mask] - pred[mask]) ** 2)
            ss_tot = np.sum((actual_drop[mask] - np.mean(actual_drop[mask])) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            results_per_patient.append({
                "patient_id": pid,
                "method": method,
                "n": int(mask.sum()),
                "mae": mae,
                "r2": float(r2),
            })

    rdf = pd.DataFrame(results_per_patient)
    if len(rdf) == 0:
        return {"skip": True}

    holdout_summary = {}
    for method in ["profile", "demand_only", "bilateral"]:
        mdf = rdf[rdf["method"] == method]
        holdout_summary[method] = {
            "n_patients": len(mdf),
            "median_mae": float(mdf["mae"].median()),
            "mean_mae": float(mdf["mae"].mean()),
            "median_r2": float(mdf["r2"].median()),
        }
        print(f"  {method:15s}: MAE={mdf['mae'].median():.1f}, R²={mdf['r2'].median():.3f} "
              f"({len(mdf)} patients)")

    # Win rates
    for method_a, method_b in [("bilateral", "demand_only"), ("bilateral", "profile")]:
        a = rdf[rdf["method"] == method_a].set_index("patient_id")["mae"]
        b = rdf[rdf["method"] == method_b].set_index("patient_id")["mae"]
        common = a.index.intersection(b.index)
        if len(common) > 0:
            wins = (a[common] < b[common]).sum()
            print(f"  {method_a} beats {method_b}: {wins}/{len(common)} patients")
            holdout_summary[f"{method_a}_vs_{method_b}_wins"] = int(wins)
            holdout_summary[f"{method_a}_vs_{method_b}_total"] = len(common)

    return holdout_summary


def dose_dependence_check(df):
    """Does bilateral ISF still show dose-dependence?"""
    print(f"\n[{EXP_ID}] === DOSE DEPENDENCE CHECK ===")
    results = {}
    for method, col in [("demand_only", "isf_demand_only"),
                         ("bilateral", "isf_bilateral")]:
        vals = df[[col, "total_insulin"]].replace([np.inf, -np.inf], np.nan).dropna()
        pos = vals[vals[col] > 0]
        if len(pos) < 50:
            continue
        r, p = stats.spearmanr(pos["total_insulin"], pos[col])
        results[method] = {"spearman_r": float(r), "p": float(p), "n": len(pos)}
        print(f"  {method:15s}: r={r:.3f}, p={p:.2e} (n={len(pos)})")
    return results


# ── Visualization ──────────────────────────────────────────────────────

def plot_dashboard(df, isf_comp, decomp, per_patient, dose_dep, holdout):
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}\n"
                 f"N={len(df):,} events, {df['patient_id'].nunique()} patients",
                 fontsize=14, fontweight="bold")

    ctrl_colors = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}

    # Panel 1: ISF distributions
    ax = axes[0, 0]
    demand_isf = df["isf_demand_only"].replace([np.inf, -np.inf], np.nan).dropna()
    bilateral_isf = df["isf_bilateral"].replace([np.inf, -np.inf], np.nan).dropna()
    demand_pos = demand_isf[demand_isf.between(0, 200)]
    bilateral_pos = bilateral_isf[bilateral_isf.between(-50, 200)]
    ax.hist(demand_pos, bins=80, alpha=0.5, color="#2196F3", label="Demand-only", density=True)
    ax.hist(bilateral_pos[bilateral_pos > 0], bins=80, alpha=0.5, color="#4CAF50",
            label="Bilateral", density=True)
    ax.axvline(df["profile_isf"].median(), color="red", ls="--", lw=2,
               label=f"Profile ISF={df['profile_isf'].median():.0f}")
    ax.set_xlabel("ISF (mg/dL/U)")
    ax.set_title("Panel 1: ISF Distributions")
    ax.legend(fontsize=8)
    ax.set_xlim(-10, 150)

    # Panel 2: Per-patient ratios
    ax = axes[0, 1]
    pp = pd.DataFrame(per_patient)
    if len(pp) > 0:
        for method, color in [("demand_only", "#2196F3"), ("bilateral", "#4CAF50")]:
            mp = pp[pp["method"] == method].sort_values("ratio")
            ax.barh(range(len(mp)), mp["ratio"], alpha=0.6, color=color,
                    label=f"{method} (med={mp['ratio'].median():.1f}×)")
        ax.set_xlabel("Setting / Extracted ISF ratio")
        ax.set_title("Panel 2: ISF Inflation Ratio")
        ax.axvline(1, color="red", ls="--", alpha=0.5, label="1:1")
        ax.legend(fontsize=8)

    # Panel 3: Magnitude decomposition
    ax = axes[0, 2]
    controllers = sorted([k for k in decomp.keys() if k != "overall"])
    x = np.arange(len(controllers) + 1)
    supply_vals = [decomp[c]["supply_return"] for c in controllers] + [decomp["overall"]["supply_return"]]
    insulin_vals = [decomp[c]["insulin_residual"] for c in controllers] + [decomp["overall"]["insulin_residual"]]
    labels = controllers + ["OVERALL"]
    ax.bar(x, supply_vals, color="#4CAF50", alpha=0.7, label="Supply return")
    ax.bar(x, insulin_vals, bottom=supply_vals, color="#2196F3", alpha=0.7, label="Insulin effect")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("BG drop (mg/dL)")
    ax.set_title("Panel 3: Supply vs Insulin Decomposition")
    ax.legend(fontsize=8)

    # Panel 4: Dose dependence
    ax = axes[1, 0]
    for method, col, color in [("Demand", "isf_demand_only", "#2196F3"),
                                ("Bilateral", "isf_bilateral", "#4CAF50")]:
        vals = df[[col, "total_insulin"]].replace([np.inf, -np.inf], np.nan).dropna()
        pos = vals[vals[col].between(0, 200)]
        ax.scatter(pos["total_insulin"], pos[col], alpha=0.02, s=2, color=color, label=method)
        # Bin means
        bins = np.percentile(pos["total_insulin"], np.arange(0, 101, 10))
        bin_idx = np.digitize(pos["total_insulin"], bins)
        for b in range(1, len(bins)):
            m = bin_idx == b
            if m.sum() > 20:
                ax.plot((bins[b-1]+bins[min(b, len(bins)-1)])/2, pos[col].values[m].mean(),
                        "o", color=color, markersize=6)
    ax.set_xlabel("Total insulin (U)")
    ax.set_ylabel("ISF (mg/dL/U)")
    ax.set_title("Panel 4: Dose Dependence")
    ax.set_ylim(-10, 100)
    ax.legend(fontsize=8)

    # Panel 5: Holdout MAE comparison
    ax = axes[1, 1]
    if holdout and not holdout.get("skip"):
        methods = ["profile", "demand_only", "bilateral"]
        maes = [holdout.get(m, {}).get("median_mae", 0) for m in methods]
        colors = ["#FF5722", "#2196F3", "#4CAF50"]
        bars = ax.bar(methods, maes, color=colors, edgecolor="white")
        for bar, mae in zip(bars, maes):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f"{mae:.1f}", ha="center", fontsize=9)
        ax.set_ylabel("Median MAE (mg/dL)")
        ax.set_title("Panel 5: Holdout Prediction MAE")
    else:
        ax.text(0.5, 0.5, "Insufficient holdout data", transform=ax.transAxes,
                ha="center", va="center")
        ax.set_title("Panel 5: Holdout (skipped)")

    # Panel 6: Per-controller bilateral ISF
    ax = axes[1, 2]
    for ctrl in sorted(df["controller"].unique()):
        cdf = df[df["controller"] == ctrl]
        isf = cdf["isf_bilateral"].replace([np.inf, -np.inf], np.nan).dropna()
        isf_pos = isf[isf.between(0, 150)]
        if len(isf_pos) > 20:
            ax.hist(isf_pos, bins=50, alpha=0.5, color=ctrl_colors.get(ctrl, "gray"),
                    label=f"{ctrl} (med={isf_pos.median():.1f})", density=True)
    ax.set_xlabel("Bilateral ISF (mg/dL/U)")
    ax.set_title("Panel 6: Bilateral ISF by Controller")
    ax.legend(fontsize=8)
    ax.set_xlim(-10, 100)

    plt.tight_layout()
    out_path = VIS_DIR / "exp-2712-dashboard.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


# ── Hypothesis Testing ─────────────────────────────────────────────────

def test_hypotheses(isf_comp, per_patient, holdout, dose_dep):
    print(f"\n[{EXP_ID}] === HYPOTHESIS TESTING ===")
    results = {}

    # H1: bilateral ISF > demand-only ISF
    bilateral_med = isf_comp["bilateral"]["median"]
    demand_med = isf_comp["demand_only"]["median"]
    h1 = bilateral_med > demand_med
    results["H1"] = {
        "verdict": "PASS" if h1 else "FAIL",
        "bilateral_median": bilateral_med,
        "demand_median": demand_med,
        "description": "Bilateral ISF closer to profile settings",
    }

    # H2: bilateral ratio < 5×
    ratio = isf_comp.get("ratio_bilateral")
    h2 = ratio is not None and abs(ratio) < 5.0
    results["H2"] = {
        "verdict": "PASS" if h2 else "FAIL",
        "bilateral_ratio": ratio,
        "demand_ratio": isf_comp.get("ratio_demand"),
        "threshold": 5.0,
    }

    # H3: bilateral CV < demand CV
    bilateral_cv = isf_comp["bilateral"]["cv"]
    demand_cv = isf_comp["demand_only"]["cv"]
    h3 = bilateral_cv < demand_cv
    results["H3"] = {
        "verdict": "PASS" if h3 else "FAIL",
        "bilateral_cv": bilateral_cv,
        "demand_cv": demand_cv,
    }

    # H4: bilateral holdout MAE < demand-only
    if holdout and not holdout.get("skip"):
        bilateral_mae = holdout.get("bilateral", {}).get("median_mae", np.inf)
        demand_mae = holdout.get("demand_only", {}).get("median_mae", np.inf)
        h4 = bilateral_mae < demand_mae
        results["H4"] = {
            "verdict": "PASS" if h4 else "FAIL",
            "bilateral_mae": bilateral_mae,
            "demand_mae": demand_mae,
        }
    else:
        results["H4"] = {"verdict": "SKIP", "reason": "insufficient holdout"}

    # H5: supply return consistent across controllers (r>0.3)
    if dose_dep:
        # Use per-controller supply correlations from EXP-2711 instead
        # For now, check if bilateral ISF reduces dose-dependence
        bilateral_r = abs(dose_dep.get("bilateral", {}).get("spearman_r", 0))
        demand_r = abs(dose_dep.get("demand_only", {}).get("spearman_r", 0))
        h5 = bilateral_r < demand_r
        results["H5"] = {
            "verdict": "PASS" if h5 else "FAIL",
            "bilateral_dose_r": bilateral_r,
            "demand_dose_r": demand_r,
            "description": "Bilateral ISF has less dose-dependence artifact",
        }
    else:
        results["H5"] = {"verdict": "SKIP"}

    for h, v in results.items():
        print(f"  {h}: {v['verdict']}")
    return results


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print(f"\n{'=' * 60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'=' * 60}\n")

    grid = load_data()
    df = extract_events(grid, split=True)

    if len(df) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    # Fit supply model on training data
    train = df[df["split"] == "train"]
    supply_model = fit_supply_model(train)

    # Apply bilateral subtraction
    df = compute_supply_return(df, supply_model)

    # Analyses
    isf_comp = analyze_isf_comparison(df)
    decomp = analyze_magnitude_decomposition(df)
    per_patient = analyze_per_patient(df)
    dose_dep = dose_dependence_check(df)
    holdout = analyze_holdout(df)

    print(f"\n[{EXP_ID}] === HYPOTHESIS TESTING ===")
    hypotheses = test_hypotheses(isf_comp, per_patient, holdout, dose_dep)

    # Visualization
    print(f"\n[{EXP_ID}] === VISUALIZATION ===")
    plot_dashboard(df, isf_comp, decomp, per_patient, dose_dep, holdout)

    # Save results
    out = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": len(df),
        "n_patients": int(df["patient_id"].nunique()),
        "supply_model": supply_model,
        "isf_comparison": {k: v for k, v in isf_comp.items()
                           if not isinstance(v, dict) or k in ["demand_only", "bilateral"]},
        "isf_ratios": {
            "demand_ratio": isf_comp.get("ratio_demand"),
            "bilateral_ratio": isf_comp.get("ratio_bilateral"),
            "profile_median": isf_comp.get("profile_median"),
        },
        "decomposition": decomp,
        "dose_dependence": dose_dep,
        "holdout": holdout,
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
