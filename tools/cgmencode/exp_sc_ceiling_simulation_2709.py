#!/usr/bin/env python3
"""EXP-2709: SC Ceiling Estimation via BG-Controlled Dose-Response

EXP-2706 showed observational dose-response slope is POSITIVE (confounding by
indication: higher IOB → higher starting BG → more room to fall).

This experiment controls for starting BG to reveal the TRUE dose-response:
1. Residualize BG0 from marginal effect (ISF)
2. Within narrow BG bands, measure ISF vs IOB slope
3. Compare high-IOB events to matched low-IOB events at same BG0
4. Test whether power-law dampening (from forward_simulator) is detectable

If SC ceiling exists, after controlling for BG0, higher IOB should produce
LOWER marginal effect (diminishing returns on insulin).

Hypotheses:
  H1: After BG0 control, dose-response slope becomes negative (diminishing)
  H2: Within narrow BG bands, higher IOB → lower ISF (SC ceiling visible)
  H3: Power-law model fits better than linear (dose-response is curved)
  H4: Per-patient SC ceiling is detectable and temporally stable

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import curve_fit

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2709_sc_ceiling_simulation.json")
VIS_DIR = Path("visualizations/sc-ceiling-simulation")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
IOB_POWER_LAW_THRESHOLD = 1.5  # from forward_simulator.py
POWER_LAW_BETA = 0.9           # from forward_simulator.py

EXP_ID = "EXP-2709"
EXP_TITLE = "SC Ceiling via BG-Controlled Dose-Response"


def load_data():
    print("Loading data...")
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


def extract_events(grid):
    """Extract correction events with IOB for dose-response analysis."""
    print("Extracting events...")
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
        bolus = pg["bolus"].values
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or np.isnan(iob[i]):
                continue
            if bg0 < BG_FLOOR:
                continue

            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))
            total_insulin = bolus_2h + smb_2h + excess_basal_2h

            if carbs_2h > 5.0 or total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue

            events.append({
                "patient_id": pid,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "iob_start": float(iob[i]),
                "controller": ctrl,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def test_h1_bg_controlled_slope(events):
    """H1: After controlling for BG0, dose-response slope is negative."""
    print("\n── H1: BG-controlled dose-response slope ──")
    from numpy.linalg import lstsq

    valid = events[["demand_isf", "bg0", "iob_start", "total_insulin"]].dropna()
    y = valid["demand_isf"].values

    # Residualize BG0 from ISF
    X_bg = np.column_stack([valid["bg0"].values, np.ones(len(valid))])
    beta, _, _, _ = lstsq(X_bg, y, rcond=None)
    isf_resid = y - X_bg @ beta  # BG-independent ISF variation

    # Raw slope: ISF ~ IOB (expected positive from EXP-2706)
    raw_slope, raw_int, raw_r, raw_p, raw_se = stats.linregress(
        valid["iob_start"].values, y)

    # BG-controlled slope: ISF_residualized ~ IOB
    adj_slope, adj_int, adj_r, adj_p, adj_se = stats.linregress(
        valid["iob_start"].values, isf_resid)

    # Full model: ISF ~ BG0 + IOB + dose
    X_full = np.column_stack([
        valid["bg0"].values,
        valid["iob_start"].values,
        valid["total_insulin"].values,
        np.ones(len(valid)),
    ])
    beta_full, _, _, _ = lstsq(X_full, y, rcond=None)
    iob_coeff = float(beta_full[1])

    # Per-patient BG-controlled slopes
    patient_slopes = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 30:
            continue
        pv = pg[["demand_isf", "bg0", "iob_start"]].dropna()
        if len(pv) < 20:
            continue
        py = pv["demand_isf"].values
        pX_bg = np.column_stack([pv["bg0"].values, np.ones(len(pv))])
        pbeta, _, _, _ = lstsq(pX_bg, py, rcond=None)
        p_resid = py - pX_bg @ pbeta
        if len(p_resid) >= 10:
            s, _, r, p, _ = stats.linregress(pv["iob_start"].values, p_resid)
            patient_slopes.append({
                "patient_id": pid,
                "bg_controlled_slope": round(float(s), 3),
                "r_value": round(float(r), 3),
                "p_value": float(p),
                "n": int(len(pv)),
                "is_negative": bool(s < 0),
            })

    n_negative = sum(1 for p in patient_slopes if p["is_negative"])
    pct_negative = 100 * n_negative / max(len(patient_slopes), 1)

    verdict = bool(adj_slope < 0 and pct_negative > 50)

    print(f"  Raw slope (ISF~IOB):          {raw_slope:.3f} (r={raw_r:.3f}, p={raw_p:.4f})")
    print(f"  BG-controlled slope:           {adj_slope:.3f} (r={adj_r:.3f}, p={adj_p:.4f})")
    print(f"  IOB coefficient (full model): {iob_coeff:.3f}")
    print(f"  Per-patient negative slope:   {n_negative}/{len(patient_slopes)} ({pct_negative:.0f}%)")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "raw_slope": round(float(raw_slope), 3),
        "raw_r": round(float(raw_r), 3),
        "bg_controlled_slope": round(float(adj_slope), 3),
        "bg_controlled_r": round(float(adj_r), 3),
        "bg_controlled_p": round(float(adj_p), 4),
        "iob_coeff_full_model": round(iob_coeff, 3),
        "pct_patients_negative": round(pct_negative, 1),
        "patient_slopes": patient_slopes,
    }


def test_h2_within_bg_bands(events):
    """H2: Within narrow BG bands, higher IOB → lower ISF."""
    print("\n── H2: Within-BG-band IOB→ISF relationship ──")

    bg_bands = [(180, 210), (210, 240), (240, 270), (270, 300), (300, 350), (350, 400)]
    band_results = []

    for lo, hi in bg_bands:
        band = events[(events["bg0"] >= lo) & (events["bg0"] < hi)]
        if len(band) < 50:
            continue

        # Split by IOB median
        iob_med = band["iob_start"].median()
        low_iob = band[band["iob_start"] <= iob_med]
        high_iob = band[band["iob_start"] > iob_med]

        if len(low_iob) < 10 or len(high_iob) < 10:
            continue

        isf_low = float(low_iob["demand_isf"].median())
        isf_high = float(high_iob["demand_isf"].median())
        diff = isf_high - isf_low  # Negative = SC ceiling

        slope, _, r, p, _ = stats.linregress(band["iob_start"].values, band["demand_isf"].values)

        band_results.append({
            "band": f"{lo}-{hi}",
            "n": int(len(band)),
            "iob_median": round(float(iob_med), 1),
            "isf_low_iob": round(isf_low, 1),
            "isf_high_iob": round(isf_high, 1),
            "isf_diff": round(diff, 1),
            "slope": round(float(slope), 3),
            "r": round(float(r), 3),
            "p": float(p),
            "is_diminishing": bool(slope < 0),
        })
        print(f"  BG {lo}-{hi}: ISF low_IOB={isf_low:.1f}, high_IOB={isf_high:.1f}, diff={diff:.1f}, slope={slope:.3f}")

    n_diminishing = sum(1 for b in band_results if b["is_diminishing"])
    pct_dim = 100 * n_diminishing / max(len(band_results), 1)
    verdict = bool(pct_dim > 60)

    print(f"  Bands with diminishing returns: {n_diminishing}/{len(band_results)} ({pct_dim:.0f}%)")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "band_results": band_results,
        "pct_diminishing": round(pct_dim, 1),
    }


def test_h3_power_law_fit(events):
    """H3: Power-law model fits better than linear for dose-response."""
    print("\n── H3: Power-law vs linear dose-response ──")

    # Population-level: bin by IOB quintiles, compute median ISF
    events_valid = events[events["iob_start"] > 0.1].copy()
    if len(events_valid) < 200:
        return {"h3_verdict": "SKIP", "reason": "insufficient events"}

    # Create IOB bins
    try:
        events_valid["iob_bin"] = pd.qcut(events_valid["iob_start"], 10, duplicates="drop")
    except ValueError:
        events_valid["iob_bin"] = pd.cut(events_valid["iob_start"], 10)

    bins = events_valid.groupby("iob_bin", observed=True).agg(
        iob_mid=("iob_start", "median"),
        isf_med=("demand_isf", "median"),
        n=("demand_isf", "count"),
    ).dropna().reset_index()

    if len(bins) < 5:
        return {"h3_verdict": "SKIP", "reason": "insufficient bins"}

    x = bins["iob_mid"].values
    y_obs = bins["isf_med"].values

    # Fit linear: ISF = a × IOB + b
    def linear(iob, a, b):
        return a * iob + b

    # Fit power-law: ISF = ISF0 × (IOB / threshold)^(-beta)
    def power_law(iob, isf0, beta):
        return isf0 * np.maximum(iob / IOB_POWER_LAW_THRESHOLD, 0.01) ** (-beta)

    try:
        popt_lin, _ = curve_fit(linear, x, y_obs, p0=[0, np.median(y_obs)])
        y_lin = linear(x, *popt_lin)
        ss_res_lin = np.sum((y_obs - y_lin) ** 2)
    except Exception:
        ss_res_lin = np.inf
        popt_lin = [0, 0]

    try:
        popt_pow, _ = curve_fit(power_law, x, y_obs, p0=[np.median(y_obs), 0.5],
                                maxfev=5000, bounds=([0, 0], [np.inf, 5]))
        y_pow = power_law(x, *popt_pow)
        ss_res_pow = np.sum((y_obs - y_pow) ** 2)
    except Exception:
        ss_res_pow = np.inf
        popt_pow = [0, 0]

    ss_tot = np.sum((y_obs - y_obs.mean()) ** 2)
    r2_lin = 1 - ss_res_lin / max(ss_tot, 1e-10)
    r2_pow = 1 - ss_res_pow / max(ss_tot, 1e-10)

    power_better = r2_pow > r2_lin + 0.01

    # Per-patient power-law fits
    patient_fits = []
    for pid, pg in events_valid.groupby("patient_id"):
        if len(pg) < 50:
            continue
        try:
            pg_bins = pd.qcut(pg["iob_start"], 5, duplicates="drop")
            pg_grouped = pg.groupby(pg_bins, observed=True).agg(
                iob_mid=("iob_start", "median"),
                isf_med=("demand_isf", "median"),
            ).dropna().reset_index()
            if len(pg_grouped) < 3:
                continue
            px = pg_grouped["iob_mid"].values
            py = pg_grouped["isf_med"].values
            # Simple: is slope of IOB vs ISF negative?
            slope, _, r, p, _ = stats.linregress(px, py)
            patient_fits.append({
                "patient_id": pid,
                "binned_slope": round(float(slope), 3),
                "r": round(float(r), 3),
                "p": float(p),
                "is_diminishing": bool(slope < 0),
            })
        except Exception:
            continue

    n_dim = sum(1 for p in patient_fits if p["is_diminishing"])

    verdict = bool(power_better)
    print(f"  R² linear: {r2_lin:.4f} (slope={popt_lin[0]:.3f})")
    print(f"  R² power:  {r2_pow:.4f} (β={popt_pow[1]:.3f})")
    print(f"  Power-law better: {power_better}")
    print(f"  Per-patient diminishing (binned): {n_dim}/{len(patient_fits)}")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "r2_linear": round(float(r2_lin), 4),
        "r2_power_law": round(float(r2_pow), 4),
        "linear_slope": round(float(popt_lin[0]), 3),
        "power_law_beta": round(float(popt_pow[1]), 3),
        "power_law_isf0": round(float(popt_pow[0]), 1),
        "power_better": power_better,
        "iob_bins": [{"iob": round(float(x[i]), 1), "isf": round(float(y_obs[i]), 1)} for i in range(len(x))],
        "per_patient_diminishing": n_dim,
        "per_patient_total": len(patient_fits),
    }


def test_h4_per_patient_stability(events):
    """H4: Per-patient SC ceiling is detectable and temporally stable."""
    print("\n── H4: Per-patient SC ceiling stability ──")
    from numpy.linalg import lstsq

    patient_results = []
    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 60:
            continue

        # BG-control: residualize BG0
        pv = pg[["demand_isf", "bg0", "iob_start"]].dropna()
        if len(pv) < 40:
            continue
        py = pv["demand_isf"].values
        pX = np.column_stack([pv["bg0"].values, np.ones(len(pv))])
        pbeta, _, _, _ = lstsq(pX, py, rcond=None)
        p_resid = py - pX @ pbeta

        # Split-half temporal stability
        half = len(pv) // 2
        first_resid = p_resid[:half]
        second_resid = p_resid[half:]
        first_iob = pv["iob_start"].values[:half]
        second_iob = pv["iob_start"].values[half:]

        if len(first_resid) < 20 or len(second_resid) < 20:
            continue

        # Guard against constant IOB values
        if np.std(first_iob) < 1e-6 or np.std(second_iob) < 1e-6:
            continue

        s1, _, r1, p1, _ = stats.linregress(first_iob, first_resid)
        s2, _, r2, p2, _ = stats.linregress(second_iob, second_resid)

        # Overall BG-controlled slope
        s_all, _, r_all, p_all, _ = stats.linregress(pv["iob_start"].values, p_resid)

        patient_results.append({
            "patient_id": pid,
            "controller": pg["controller"].iloc[0],
            "n": int(len(pv)),
            "bg_controlled_slope": round(float(s_all), 3),
            "r_value": round(float(r_all), 3),
            "p_value": float(p_all),
            "first_half_slope": round(float(s1), 3),
            "second_half_slope": round(float(s2), 3),
            "is_negative": bool(s_all < 0),
            "is_consistent": bool((s1 < 0) == (s2 < 0)),
        })

    if len(patient_results) < 5:
        return {"h4_verdict": "SKIP", "reason": "insufficient patients"}

    n_negative = sum(1 for p in patient_results if p["is_negative"])
    n_consistent = sum(1 for p in patient_results if p["is_consistent"])

    first_slopes = [p["first_half_slope"] for p in patient_results]
    second_slopes = [p["second_half_slope"] for p in patient_results]
    stability_r, stability_p = stats.pearsonr(first_slopes, second_slopes)

    pct_negative = 100 * n_negative / len(patient_results)
    pct_consistent = 100 * n_consistent / len(patient_results)

    verdict = bool(pct_negative > 50 and stability_r > 0.3)

    print(f"  Patients with negative BG-controlled slope: {n_negative}/{len(patient_results)} ({pct_negative:.0f}%)")
    print(f"  Temporally consistent sign: {n_consistent}/{len(patient_results)} ({pct_consistent:.0f}%)")
    print(f"  Split-half stability: r={stability_r:.3f}")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'}")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "pct_negative_slope": round(pct_negative, 1),
        "pct_consistent": round(pct_consistent, 1),
        "split_half_r": round(float(stability_r), 3),
        "split_half_p": round(float(stability_p), 4),
        "patient_results": patient_results,
    }


def make_visualization(events, h1, h2, h3, h4):
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # Panel 1: Raw vs BG-controlled slope
    ax = axes[0, 0]
    if h1.get("patient_slopes"):
        raw_s = h1["raw_slope"]
        adj_s = h1["bg_controlled_slope"]
        ax.axhline(0, color="gray", linestyle="--", alpha=0.5)
        ps = h1["patient_slopes"]
        slopes = [p["bg_controlled_slope"] for p in ps]
        ax.hist(slopes, bins=20, alpha=0.7, color="coral", edgecolor="black")
        ax.axvline(0, color="black", linestyle="-", linewidth=2)
        ax.set_xlabel("BG-controlled IOB→ISF slope")
        ax.set_ylabel("Count")
    ax.set_title(f"H1: BG-Controlled Slope [{h1['h1_verdict']}]")

    # Panel 2: Within-BG-band slopes
    ax = axes[0, 1]
    if h2.get("band_results"):
        bands = h2["band_results"]
        labels = [b["band"] for b in bands]
        slopes = [b["slope"] for b in bands]
        colors = ["green" if s < 0 else "red" for s in slopes]
        ax.barh(labels, slopes, color=colors, alpha=0.7)
        ax.axvline(0, color="black", linestyle="-", linewidth=1)
        ax.set_xlabel("IOB→ISF slope within band")
    ax.set_title(f"H2: Within-BG-Band [{h2['h2_verdict']}]")

    # Panel 3: Power-law vs linear
    ax = axes[1, 0]
    if h3.get("iob_bins"):
        bins = h3["iob_bins"]
        x = [b["iob"] for b in bins]
        y = [b["isf"] for b in bins]
        ax.scatter(x, y, s=40, color="steelblue", zorder=3, label="Observed")
        x_fit = np.linspace(min(x), max(x), 50)
        # Linear
        a = h3["linear_slope"]
        b = y[0] - a * x[0]
        ax.plot(x_fit, a * x_fit + b, "r--", label=f"Linear R²={h3['r2_linear']:.3f}")
        # Power
        isf0 = h3.get("power_law_isf0", 25)
        beta = h3.get("power_law_beta", 0.5)
        y_pow = isf0 * np.maximum(np.array(x_fit) / IOB_POWER_LAW_THRESHOLD, 0.01) ** (-beta)
        ax.plot(x_fit, y_pow, "g-", label=f"Power R²={h3['r2_power_law']:.3f}")
        ax.set_xlabel("IOB (U)")
        ax.set_ylabel("Median ISF (mg/dL/U)")
        ax.legend(fontsize=8)
    ax.set_title(f"H3: Power-Law Fit [{h3['h3_verdict']}]")

    # Panel 4: Stability scatter
    ax = axes[1, 1]
    if h4.get("patient_results"):
        pr = h4["patient_results"]
        f_s = [p["first_half_slope"] for p in pr]
        s_s = [p["second_half_slope"] for p in pr]
        ax.scatter(f_s, s_s, alpha=0.6, s=30)
        lim = max(max(abs(v) for v in f_s + s_s), 1)
        ax.plot([-lim, lim], [-lim, lim], "k--", alpha=0.3)
        ax.axhline(0, color="gray", linestyle=":", alpha=0.3)
        ax.axvline(0, color="gray", linestyle=":", alpha=0.3)
        ax.set_xlabel("First-half slope")
        ax.set_ylabel("Second-half slope")
        r = h4.get("split_half_r", 0)
        ax.text(0.05, 0.95, f"r={r:.3f}", transform=ax.transAxes, fontsize=10, va="top")
    ax.set_title(f"H4: Stability [{h4['h4_verdict']}]")

    plt.tight_layout()
    out_path = VIS_DIR / "sc_ceiling_simulation.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  Visualization: {out_path}")


def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_events(grid)
    if len(events) < 100:
        print("ERROR: Too few events")
        sys.exit(1)

    h1 = test_h1_bg_controlled_slope(events)
    h2 = test_h2_within_bg_bands(events)
    h3 = test_h3_power_law_fit(events)
    h4 = test_h4_per_patient_stability(events)

    make_visualization(events, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "hypotheses": {
            "H1_bg_controlled_slope": h1,
            "H2_within_bg_bands": h2,
            "H3_power_law_fit": h3,
            "H4_per_patient_stability": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    print(f"\nVerdict summary: H1={h1['h1_verdict']} H2={h2['h2_verdict']} H3={h3['h3_verdict']} H4={h4['h4_verdict']}")
    return results


if __name__ == "__main__":
    main()
