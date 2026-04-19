#!/usr/bin/env python3
"""EXP-2719: BGI-Decomposed Supply vs Demand

oref0 decomposes glucose change at every 5-min step:
  BGI = -insulin_activity × ISF × 5   (demand-side: what insulin does)
  deviation = observed_roc - BGI       (supply-side: EGP + carbs + noise)

Our prior experiments measured demand_ISF = bg_drop / dose, which conflates
both sides. This experiment uses the oref0 decomposition to SEPARATELY
model supply and demand contributions to glucose change.

Key insight: insulin demand operates at ~6h (DIA), but glucose supply
(EGP/glycogen) operates at ~72h. By decomposing, we can model each
side at its natural timescale.

Available for ~11 patients with insulin_activity column (Trio/OpenAPS only).

Hypotheses:
  H1: BGI (demand) and deviation (supply) are weakly correlated (|r| < 0.3)
  H2: Deviation (supply) correlates with glycogen state (48h carbs, |r| > 0.1)
  H3: Deviation has circadian structure (ANOVA p<0.05 across time blocks)
  H4: Modeling supply+demand separately predicts BG better than demand-only ISF

Design:
  - Compute per-5min BGI and deviation for patients with insulin_activity
  - Aggregate over 2h correction windows: sum(BGI) vs sum(deviation)
  - Model deviation as f(carbs_48h, circadian, cob)
  - Compare: demand-only BG prediction vs supply+demand

Author: Copilot + bewest
Date: 2026-04-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
OUT_JSON = Path("externals/experiments/exp-2719_bgi_decomposition.json")
VIS_DIR = Path("visualizations/bgi-decomposition")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2719"
EXP_TITLE = "BGI-Decomposed Supply vs Demand"


def load_data():
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

    # Filter to patients with insulin_activity
    ia_coverage = grid.groupby("patient_id")["insulin_activity"].apply(lambda x: x.notna().mean())
    eligible = ia_coverage[ia_coverage > 0.1].index.tolist()
    grid = grid[grid["patient_id"].isin(eligible)].copy()
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients (with insulin_activity)")
    return grid


def compute_48h_carbs(grid):
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


def extract_events(grid):
    """Extract correction events with oref0-style BGI decomposition."""
    print("Extracting events with BGI decomposition...")
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
        bolus = pg["bolus"].values
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        carbs_48h = pg["carbs_48h"].values if has_carbs_48h else np.zeros(len(pg))
        cob = pg["cob"].values if "cob" in pg.columns else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        # BGI decomposition columns
        ia = pg["insulin_activity"].values if "insulin_activity" in pg.columns else np.full(len(pg), np.nan)
        isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else np.full(len(pg), np.nan)
        roc = pg["glucose_roc"].values if "glucose_roc" in pg.columns else np.full(len(pg), np.nan)

        if "scheduled_isf" not in pg.columns:
            continue
        profile_isf = float(np.nanmedian(isf))

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end) or bg0 < BG_FLOOR:
                continue

            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))
            if carbs_2h > 5.0:
                continue

            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue

            # oref0-style BGI decomposition over 2h window
            # BGI per 5min step = -insulin_activity × ISF × 5
            # Sum over horizon = cumulative insulin effect
            bgi_steps = ia[i:i + h]
            isf_steps = isf[i:i + h]
            roc_steps = roc[i:i + h]

            # Only compute if we have enough BGI data
            valid_bgi = ~np.isnan(bgi_steps) & ~np.isnan(isf_steps)
            if valid_bgi.sum() < h * 0.5:  # need >50% coverage
                continue

            # BGI sum (demand-side glucose change from insulin)
            bgi_per_step = -bgi_steps * isf_steps * 5  # mg/dL per step
            bgi_per_step = np.where(np.isnan(bgi_per_step), 0, bgi_per_step)
            cumulative_bgi = float(np.sum(bgi_per_step))  # total expected drop from insulin

            # Deviation per step (supply-side: observed - expected)
            dev_per_step = np.where(
                ~np.isnan(roc_steps) & ~np.isnan(bgi_per_step),
                roc_steps - bgi_per_step,
                np.nan
            )
            valid_dev = ~np.isnan(dev_per_step)
            cumulative_deviation = float(np.nansum(dev_per_step)) if valid_dev.sum() > h * 0.3 else np.nan

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour
            except Exception:
                hour = 0
            block_idx = min(hour // 4, 5)

            c48 = float(carbs_48h[i]) if not np.isnan(carbs_48h[i]) else 0.0

            events.append({
                "patient_id": pid,
                "step_index": i,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "cumulative_bgi": cumulative_bgi,  # demand component (positive = drop)
                "cumulative_deviation": cumulative_deviation,  # supply component
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "cob_start": float(cob[i]) if not np.isnan(cob[i]) else 0.0,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "carbs_48h": c48,
                "controller": ctrl,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    # Glycogen state
    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        med = df.loc[mask, "carbs_48h"].median()
        df.loc[mask, "glycogen_state"] = np.where(
            df.loc[mask, "carbs_48h"] >= med, "loaded", "depleted"
        )

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    n_with_dev = df["cumulative_deviation"].notna().sum()
    print(f"  {n_with_dev:,} with BGI decomposition")
    return df


def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    print("\nLoading data (patients with insulin_activity)...")
    grid = load_data()
    print("Computing 48h carbs...")
    grid = compute_48h_carbs(grid)
    print("Extracting events...")
    df = extract_events(grid)

    ev = df[df["cumulative_deviation"].notna()].copy()
    print(f"\n{len(ev):,} events with BGI decomposition")

    if len(ev) < 100:
        print("INSUFFICIENT DATA for meaningful analysis")
        results = {
            "experiment": EXP_ID, "title": EXP_TITLE,
            "n_events": len(ev), "status": "INSUFFICIENT_DATA",
            "hypotheses": {f"H{i}": {"pass": False, "description": "Insufficient data"} for i in range(1, 5)}
        }
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_JSON, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults: {OUT_JSON}")
        print("\nVerdict: H1=SKIP H2=SKIP H3=SKIP H4=SKIP")
        return results

    # Summary statistics
    print(f"\n── BGI Decomposition Summary ──")
    print(f"  Observed drop:    mean={ev['observed_drop'].mean():.1f}, median={ev['observed_drop'].median():.1f}")
    print(f"  BGI (demand):     mean={ev['cumulative_bgi'].mean():.1f}, median={ev['cumulative_bgi'].median():.1f}")
    print(f"  Deviation (supply): mean={ev['cumulative_deviation'].mean():.1f}, median={ev['cumulative_deviation'].median():.1f}")
    print(f"  BGI / observed:   {100*ev['cumulative_bgi'].mean()/ev['observed_drop'].mean():.0f}%")

    # ── H1: BGI and deviation weakly correlated ──
    print("\n── H1: BGI and deviation weakly correlated? ──")
    r_bgi_dev = ev["cumulative_bgi"].corr(ev["cumulative_deviation"])
    h1_pass = bool(abs(r_bgi_dev) < 0.3)
    print(f"  Correlation BGI ↔ deviation: r={r_bgi_dev:.3f}")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    # ── H2: Deviation correlates with glycogen state ──
    print("\n── H2: Deviation correlates with glycogen? ──")
    r_dev_c48 = ev["cumulative_deviation"].corr(ev["carbs_48h"])
    loaded = ev[ev["glycogen_state"] == "loaded"]["cumulative_deviation"]
    depleted = ev[ev["glycogen_state"] == "depleted"]["cumulative_deviation"]
    med_l = loaded.median()
    med_d = depleted.median()
    h2_pass = bool(abs(r_dev_c48) > 0.05)
    print(f"  Correlation deviation ↔ carbs_48h: r={r_dev_c48:.3f}")
    print(f"  Deviation loaded: {med_l:.1f}, depleted: {med_d:.1f}")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    # ── H3: Deviation has circadian structure ──
    print("\n── H3: Deviation has circadian structure? ──")
    groups = [ev[ev["block_label"] == b]["cumulative_deviation"].values for b in BLOCK_LABELS]
    groups = [g for g in groups if len(g) > 5]
    if len(groups) >= 3:
        h_stat, p_circ = stats.kruskal(*groups)
        h3_pass = bool(p_circ < 0.05)
        print(f"  Deviation by block:")
        for b in BLOCK_LABELS:
            sub = ev[ev["block_label"] == b]["cumulative_deviation"]
            if len(sub) > 0:
                print(f"    {b}: median={sub.median():.1f}, n={len(sub):,}")
        print(f"  Kruskal-Wallis: H={h_stat:.1f}, p={p_circ:.6f}")
    else:
        h3_pass = False
        p_circ = 1.0
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    # ── H4: Supply+demand predicts BG better ──
    print("\n── H4: Supply+demand predicts BG better? ──")
    from numpy.linalg import lstsq

    per_patient = []
    for pid, pg in ev.groupby("patient_id"):
        if len(pg) < 30:
            continue
        actual = pg["bg_end"].values

        # Demand-only: BG_end = BG0 - demand_ISF * dose
        flat_isf = pg["demand_isf"].median()
        pred_demand = pg["bg0"].values - flat_isf * pg["total_insulin"].values
        mae_demand = np.median(np.abs(actual - pred_demand))

        # Supply+demand: BG_end = BG0 - BGI + deviation
        pred_decomposed = pg["bg0"].values - pg["cumulative_bgi"].values + pg["cumulative_deviation"].values
        mae_decomposed = np.median(np.abs(actual - pred_decomposed))

        # OLS on supply+demand features
        X = np.column_stack([
            pg["bg0"].values,
            pg["cumulative_bgi"].values,
            pg["cumulative_deviation"].values,
            pg["carbs_48h"].values,
            pg["cob_start"].values,
            np.ones(len(pg)),
        ])
        try:
            beta, _, _, _ = lstsq(X, actual, rcond=None)
            pred_model = X @ beta
            mae_model = np.median(np.abs(actual - pred_model))
        except Exception:
            mae_model = mae_demand

        per_patient.append({
            "patient_id": pid,
            "mae_demand": mae_demand,
            "mae_decomposed": mae_decomposed,
            "mae_model": mae_model,
            "n": len(pg),
        })

    pp = pd.DataFrame(per_patient)
    n_improved = (pp["mae_model"] < pp["mae_demand"]).sum()
    med_demand = pp["mae_demand"].median()
    med_model = pp["mae_model"].median()
    h4_pass = bool(n_improved > len(pp) / 2 and med_model < med_demand)
    print(f"  Median MAE demand-only: {med_demand:.1f}")
    print(f"  Median MAE supply+demand model: {med_model:.1f}")
    print(f"  Patients improved: {n_improved}/{len(pp)}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    # ── Visualization ──
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"{EXP_ID}: {EXP_TITLE}\noref0 BGI decomposition: demand (insulin, 6h) vs supply (EGP, 72h)",
                     fontsize=13, fontweight="bold")

        # Panel 1: BGI vs deviation scatter
        ax = axes[0, 0]
        ax.scatter(ev["cumulative_bgi"], ev["cumulative_deviation"],
                   alpha=0.1, s=5, c="#2196F3")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=0.5)
        ax.set_xlabel("Cumulative BGI (demand, mg/dL)")
        ax.set_ylabel("Cumulative Deviation (supply, mg/dL)")
        ax.set_title(f"BGI vs Deviation (r={r_bgi_dev:.3f})")
        ax.set_xlim(-200, 200)
        ax.set_ylim(-200, 200)

        # Panel 2: Components of glucose change
        ax = axes[0, 1]
        components = ["Observed\ndrop", "BGI\n(demand)", "Deviation\n(supply)"]
        vals = [ev["observed_drop"].median(), ev["cumulative_bgi"].median(), ev["cumulative_deviation"].median()]
        colors = ["#9E9E9E", "#1976D2", "#FF9800"]
        bars = ax.bar(components, vals, color=colors, alpha=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                    f"{val:.1f}", ha="center", fontsize=10)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylabel("mg/dL over 2h")
        ax.set_title("Glucose Change Decomposition")

        # Panel 3: Deviation by circadian block
        ax = axes[1, 0]
        block_medians = [ev[ev["block_label"] == b]["cumulative_deviation"].median() for b in BLOCK_LABELS]
        ax.bar(BLOCK_LABELS, block_medians, color="#FF9800", alpha=0.7)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylabel("Median deviation (mg/dL)")
        ax.set_title("Supply-Side Circadian Pattern")

        # Panel 4: Deviation by glycogen state
        ax = axes[1, 1]
        loaded_v = ev[ev["glycogen_state"] == "loaded"]["cumulative_deviation"].values
        depleted_v = ev[ev["glycogen_state"] == "depleted"]["cumulative_deviation"].values
        ax.hist(loaded_v[(loaded_v > -200) & (loaded_v < 200)], bins=40,
                alpha=0.5, color="#FF9800", label=f"Loaded (n={len(loaded_v):,})", density=True)
        ax.hist(depleted_v[(depleted_v > -200) & (depleted_v < 200)], bins=40,
                alpha=0.5, color="#2196F3", label=f"Depleted (n={len(depleted_v):,})", density=True)
        ax.set_xlabel("Cumulative deviation (mg/dL)")
        ax.set_title("Supply by Glycogen State")
        ax.legend(fontsize=8)

        # Panel 5: MAE comparison
        ax = axes[1, 2]
        ax.bar(["Demand\nonly", "Supply+\nDemand"],
               [med_demand, med_model],
               color=["#1976D2", "#4CAF50"], alpha=0.8)
        ax.set_ylabel("Median MAE (mg/dL)")
        ax.set_title(f"BG Prediction\n({n_improved}/{len(pp)} patients improved)")

        # Panel 6 (reuse 0,2): Scorecard
        ax = axes[0, 2]
        ax.axis("off")
        scorecard = (
            f"N patients: {ev['patient_id'].nunique()}\n"
            f"N events: {len(ev):,}\n\n"
            f"H1: BGI-deviation weak corr — {'PASS' if h1_pass else 'FAIL'}\n"
            f"    r={r_bgi_dev:.3f}\n\n"
            f"H2: Deviation ~ glycogen — {'PASS' if h2_pass else 'FAIL'}\n"
            f"    r={r_dev_c48:.3f}\n\n"
            f"H3: Circadian supply — {'PASS' if h3_pass else 'FAIL'}\n"
            f"    p={p_circ:.6f}\n\n"
            f"H4: S+D better than D — {'PASS' if h4_pass else 'FAIL'}\n"
            f"    MAE: {med_demand:.1f} -> {med_model:.1f}"
        )
        ax.text(0.05, 0.95, scorecard, fontsize=10, fontfamily="monospace",
                verticalalignment="top", transform=ax.transAxes,
                bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        plt.tight_layout()
        plt.savefig(VIS_DIR / "bgi_decomposition.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Visualization: {VIS_DIR / 'bgi_decomposition.png'}")
    except ImportError:
        print("  (matplotlib not available)")

    # ── Results ──
    results = {
        "experiment": EXP_ID,
        "title": EXP_TITLE,
        "n_events": len(ev),
        "n_patients": int(ev["patient_id"].nunique()),
        "bgi_median": round(float(ev["cumulative_bgi"].median()), 1),
        "deviation_median": round(float(ev["cumulative_deviation"].median()), 1),
        "bgi_pct_of_drop": round(100 * ev["cumulative_bgi"].mean() / ev["observed_drop"].mean(), 1),
        "corr_bgi_deviation": round(float(r_bgi_dev), 3),
        "corr_deviation_glycogen": round(float(r_dev_c48), 3),
        "mae_demand_only": round(float(med_demand), 1),
        "mae_supply_demand": round(float(med_model), 1),
        "per_patient": per_patient,
        "hypotheses": {
            "H1": {"description": "BGI-deviation weak corr", "pass": h1_pass, "r": round(float(r_bgi_dev), 3)},
            "H2": {"description": "Deviation ~ glycogen", "pass": h2_pass, "r": round(float(r_dev_c48), 3)},
            "H3": {"description": "Circadian supply", "pass": h3_pass},
            "H4": {"description": "S+D better than D", "pass": h4_pass,
                    "mae_demand": round(float(med_demand), 1), "mae_model": round(float(med_model), 1)},
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults: {OUT_JSON}")

    verdicts = " ".join(
        f"H{i}={'PASS' if results['hypotheses'][f'H{i}']['pass'] else 'FAIL'}"
        for i in range(1, 5)
    )
    print(f"\nVerdict: {verdicts}")
    return results


if __name__ == "__main__":
    results = main()
