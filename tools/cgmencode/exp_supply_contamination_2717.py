#!/usr/bin/env python3
"""EXP-2717: Supply-Side Contamination of ISF Measurements

Our measured demand_ISF = bg_drop / insulin_dose conflates:
  - DEMAND: insulin pulling glucose down (fast, DIA ~6h)
  - SUPPLY: EGP/carb absorption pushing glucose up (slow, ~72h glycogen cycle)

When glucose is rising at correction time (81% of events), the supply side
is actively fighting the insulin. This contaminates ISF: measured ISF appears
LOWER (more resistant) when supply is high.

This experiment uses pre-correction glucose_roc as a proxy for the current
supply-demand balance and adjusts the observed BG drop by subtracting the
estimated supply contribution.

  adjusted_drop = observed_drop - (pre_roc × horizon_minutes / 5)
  supply_adjusted_ISF = adjusted_drop / dose

Hypotheses:
  H1: ISF is lower when pre-correction glucose is rising (supply fights insulin)
  H2: Supply-adjusted ISF has lower within-patient CV (more precise)
  H3: Supply-adjusted ISF explains more variance (higher R²) in multi-factor model
  H4: Supply contribution varies with glycogen state (48h carbs)

Design:
  - Extract correction events at BG≥180 with pre-correction glucose_roc
  - Split by supply state: rising (roc>0) vs falling (roc<0)
  - Compute supply-adjusted ISF
  - Compare variance, R², and multi-factor model performance

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
OUT_JSON = Path("externals/experiments/exp-2717_supply_contamination.json")
VIS_DIR = Path("visualizations/supply-contamination")

BG_FLOOR = 180.0
HORIZON_STEPS = 24  # 2h
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12  # 48h

BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2717"
EXP_TITLE = "Supply-Side Contamination of ISF"


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
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
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
    """Extract correction events with supply-side features."""
    print("Extracting correction events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    has_carbs_48h = "carbs_48h" in grid.columns
    has_roc = "glucose_roc" in grid.columns
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
        roc = pg["glucose_roc"].values if has_roc else np.full(len(pg), np.nan)
        cob = pg["cob"].values if "cob" in pg.columns else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" not in pg.columns:
            continue
        profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))

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

            # Pre-correction glucose_roc (supply proxy)
            pre_roc = float(roc[i]) if not np.isnan(roc[i]) else np.nan

            # Supply-adjusted drop: subtract supply contribution
            # Supply adds glucose at rate pre_roc mg/dL per 5min over horizon
            if not np.isnan(pre_roc):
                supply_contribution = pre_roc * h  # total supply effect over horizon (in mg/dL)
                adjusted_drop = observed_drop + supply_contribution  # add back what supply pushed up
                # Note: if roc > 0 (rising), supply is fighting insulin,
                # so the TRUE insulin effect is larger than observed
                supply_adjusted_isf = adjusted_drop / total_insulin
            else:
                supply_contribution = np.nan
                adjusted_drop = np.nan
                supply_adjusted_isf = np.nan

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
                "pre_roc": pre_roc,
                "supply_contribution": supply_contribution,
                "adjusted_drop": adjusted_drop,
                "supply_adjusted_isf": supply_adjusted_isf,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
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
    roc_valid = df["pre_roc"].notna().sum()
    print(f"  {roc_valid:,} ({100*roc_valid/len(df):.0f}%) have glucose_roc")
    return df


def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    print("\nLoading data...")
    grid = load_data()
    print("Computing 48h carbs...")
    grid = compute_48h_carbs(grid)
    print("Extracting events...")
    df = extract_events(grid)

    # Filter to events with glucose_roc
    ev = df[df["pre_roc"].notna()].copy()
    print(f"\n{len(ev):,} events with supply proxy (glucose_roc)")

    # Supply state classification
    ev["supply_state"] = np.where(ev["pre_roc"] > 0, "rising", "falling")
    n_rising = (ev["supply_state"] == "rising").sum()
    print(f"  Rising: {n_rising:,} ({100*n_rising/len(ev):.0f}%)")
    print(f"  Falling: {len(ev)-n_rising:,}")

    # ── H1: ISF lower when glucose is rising ──
    print("\n── H1: ISF lower when glucose is rising? ──")
    rising = ev[ev["supply_state"] == "rising"]["demand_isf"]
    falling = ev[ev["supply_state"] == "falling"]["demand_isf"]
    med_rising = rising.median()
    med_falling = falling.median()
    u_stat, u_p = stats.mannwhitneyu(rising, falling, alternative="less")
    h1_pass = bool(med_rising < med_falling and u_p < 0.05)
    print(f"  Median ISF rising:  {med_rising:.1f}")
    print(f"  Median ISF falling: {med_falling:.1f}")
    print(f"  Difference: {med_falling - med_rising:.1f} ({100*(med_falling-med_rising)/med_falling:.1f}%)")
    print(f"  Mann-Whitney p: {u_p:.6f}")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    # ── H2: Supply-adjusted ISF has lower CV ──
    print("\n── H2: Supply-adjusted ISF has lower within-patient CV? ──")
    ev_adj = ev[ev["supply_adjusted_isf"].notna() & (ev["supply_adjusted_isf"] > 0)].copy()
    raw_cvs = []
    adj_cvs = []
    for pid, pg in ev_adj.groupby("patient_id"):
        if len(pg) < 30:
            continue
        raw_cv = pg["demand_isf"].std() / max(pg["demand_isf"].mean(), 0.1)
        adj_cv = pg["supply_adjusted_isf"].std() / max(pg["supply_adjusted_isf"].mean(), 0.1)
        raw_cvs.append(raw_cv)
        adj_cvs.append(adj_cv)

    med_raw_cv = float(np.median(raw_cvs))
    med_adj_cv = float(np.median(adj_cvs))
    n_improved = sum(1 for r, a in zip(raw_cvs, adj_cvs) if a < r)
    h2_pass = bool(med_adj_cv < med_raw_cv and n_improved > len(raw_cvs) / 2)
    print(f"  Median raw CV:      {med_raw_cv:.3f}")
    print(f"  Median adjusted CV: {med_adj_cv:.3f}")
    print(f"  Patients improved:  {n_improved}/{len(raw_cvs)}")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    # ── H3: Supply-adjusted ISF improves multi-factor R² ──
    print("\n── H3: Supply-adjusted ISF improves R²? ──")
    from numpy.linalg import lstsq
    ev_valid = ev_adj.copy()
    # Raw demand ISF R² with multi-factor
    y_raw = ev_valid["demand_isf"].values
    ss_tot_raw = np.sum((y_raw - y_raw.mean()) ** 2)

    X = np.column_stack([
        pd.get_dummies(ev_valid["patient_id"], prefix="p").values,
        ev_valid["bg0"].values.reshape(-1, 1),
        pd.get_dummies(ev_valid["block_idx"], prefix="b").values,
        ev_valid["total_insulin"].values.reshape(-1, 1),
        ev_valid["iob_start"].values.reshape(-1, 1),
        ev_valid["carbs_48h"].values.reshape(-1, 1),
        np.ones((len(ev_valid), 1)),
    ])
    beta_raw, _, _, _ = lstsq(X, y_raw, rcond=None)
    r2_raw = 1 - np.sum((y_raw - X @ beta_raw) ** 2) / ss_tot_raw

    # Supply-adjusted ISF with same factors
    y_adj = ev_valid["supply_adjusted_isf"].values
    ss_tot_adj = np.sum((y_adj - y_adj.mean()) ** 2)
    beta_adj, _, _, _ = lstsq(X, y_adj, rcond=None)
    r2_adj = 1 - np.sum((y_adj - X @ beta_adj) ** 2) / ss_tot_adj

    # Raw ISF with supply as additional factor
    X_plus = np.column_stack([X, ev_valid["pre_roc"].values.reshape(-1, 1)])
    beta_plus, _, _, _ = lstsq(X_plus, y_raw, rcond=None)
    r2_plus = 1 - np.sum((y_raw - X_plus @ beta_plus) ** 2) / ss_tot_raw

    h3_pass = bool(r2_adj > r2_raw or r2_plus > r2_raw * 1.05)
    print(f"  R² raw ISF (multi-factor):           {r2_raw:.4f}")
    print(f"  R² supply-adjusted ISF (same factors):{r2_adj:.4f}")
    print(f"  R² raw ISF + supply factor:           {r2_plus:.4f}")
    print(f"  Supply adds ΔR²:                      {r2_plus - r2_raw:.4f}")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    # ── H4: Supply contribution varies with glycogen state ──
    print("\n── H4: Supply varies with glycogen state? ──")
    loaded = ev[ev["glycogen_state"] == "loaded"]["supply_contribution"].dropna()
    depleted = ev[ev["glycogen_state"] == "depleted"]["supply_contribution"].dropna()
    med_loaded = loaded.median()
    med_depleted = depleted.median()
    u2, p2 = stats.mannwhitneyu(loaded, depleted)
    h4_pass = bool(p2 < 0.05 and abs(med_loaded - med_depleted) > 5)
    print(f"  Median supply (loaded):   {med_loaded:.1f} mg/dL")
    print(f"  Median supply (depleted): {med_depleted:.1f} mg/dL")
    print(f"  Difference: {med_loaded - med_depleted:.1f}")
    print(f"  Mann-Whitney p: {p2:.6f}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    # ── Quantify supply-side magnitude ──
    print("\n── Supply-side magnitude ──")
    supply = ev["supply_contribution"].dropna()
    print(f"  Median supply contribution: {supply.median():.1f} mg/dL over 2h")
    print(f"  Mean: {supply.mean():.1f}, Std: {supply.std():.1f}")
    pct_of_drop = 100 * supply.abs().median() / ev["observed_drop"].median()
    print(f"  Supply as % of observed drop: {pct_of_drop:.1f}%")

    # Correlation: pre_roc vs demand_isf
    r_roc_isf = ev["pre_roc"].corr(ev["demand_isf"])
    print(f"  Correlation pre_roc ↔ demand_ISF: r={r_roc_isf:.3f}")

    # ── Visualization ──
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"{EXP_ID}: {EXP_TITLE}\nDemand (insulin, ~6h DIA) vs Supply (EGP/glycogen, ~72h cycle)",
                     fontsize=13, fontweight="bold")

        # Panel 1: ISF by supply state
        ax = axes[0, 0]
        data_r = ev[ev["supply_state"] == "rising"]["demand_isf"].values
        data_f = ev[ev["supply_state"] == "falling"]["demand_isf"].values
        data_r = data_r[~np.isnan(data_r)]
        data_f = data_f[~np.isnan(data_f)]
        ax.hist(data_r, bins=50, alpha=0.6, color="#F44336", label=f"Rising (n={len(data_r):,})", density=True)
        ax.hist(data_f, bins=50, alpha=0.6, color="#4CAF50", label=f"Falling (n={len(data_f):,})", density=True)
        ax.axvline(med_rising, color="#F44336", linestyle="--", linewidth=2)
        ax.axvline(med_falling, color="#4CAF50", linestyle="--", linewidth=2)
        ax.set_xlabel("Demand ISF (mg/dL/U)")
        ax.set_ylabel("Density")
        ax.set_title("ISF by Supply State")
        ax.set_xlim(0, 100)
        ax.legend(fontsize=8)

        # Panel 2: Supply contribution distribution
        ax = axes[0, 1]
        supply_vals = ev["supply_contribution"].dropna().values
        supply_vals = supply_vals[(supply_vals > -200) & (supply_vals < 400)]
        ax.hist(supply_vals, bins=60, color="#2196F3", alpha=0.7, edgecolor="white")
        ax.axvline(0, color="black", linewidth=1.5)
        ax.axvline(np.median(supply_vals), color="red", linewidth=2, label=f"Median={np.median(supply_vals):.0f}")
        ax.set_xlabel("Supply contribution (mg/dL over 2h)")
        ax.set_ylabel("Count")
        ax.set_title("Supply-Side Glucose Contribution\n(positive = glucose pushed UP)")
        ax.legend(fontsize=8)

        # Panel 3: CV comparison
        ax = axes[0, 2]
        ax.scatter(raw_cvs, adj_cvs, alpha=0.5, s=40, c="#9C27B0")
        lim = max(max(raw_cvs), max(adj_cvs)) * 1.1
        ax.plot([0, lim], [0, lim], "k--", alpha=0.3, label="Equal")
        ax.set_xlabel("Raw demand ISF CV")
        ax.set_ylabel("Supply-adjusted ISF CV")
        ax.set_title(f"Within-Patient CV\n({n_improved}/{len(raw_cvs)} improved)")
        ax.legend(fontsize=8)
        ax.set_aspect("equal")

        # Panel 4: R² comparison
        ax = axes[1, 0]
        bars = ax.bar(["Raw ISF\nmulti-factor", "Supply-adj\nmulti-factor", "Raw + supply\nfactor"],
                      [r2_raw, r2_adj, r2_plus],
                      color=["#9E9E9E", "#4CAF50", "#2196F3"], alpha=0.8)
        for bar, val in zip(bars, [r2_raw, r2_adj, r2_plus]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.002,
                    f"{val:.4f}", ha="center", fontsize=9)
        ax.set_ylabel("R2")
        ax.set_title("Multi-Factor Model R2")

        # Panel 5: Supply by glycogen state
        ax = axes[1, 1]
        loaded_v = ev[ev["glycogen_state"] == "loaded"]["supply_contribution"].dropna().values
        depleted_v = ev[ev["glycogen_state"] == "depleted"]["supply_contribution"].dropna().values
        ax.hist(loaded_v[(loaded_v > -200) & (loaded_v < 400)], bins=50, alpha=0.5,
                color="#FF9800", label=f"Loaded (med={med_loaded:.0f})", density=True)
        ax.hist(depleted_v[(depleted_v > -200) & (depleted_v < 400)], bins=50, alpha=0.5,
                color="#2196F3", label=f"Depleted (med={med_depleted:.0f})", density=True)
        ax.set_xlabel("Supply contribution (mg/dL)")
        ax.set_title("Supply by Glycogen State")
        ax.legend(fontsize=8)

        # Panel 6: Scorecard
        ax = axes[1, 2]
        ax.axis("off")
        scorecard = (
            f"H1: ISF lower when rising — {'PASS' if h1_pass else 'FAIL'}\n"
            f"    Rising={med_rising:.1f}, Falling={med_falling:.1f}\n\n"
            f"H2: Adjusted CV lower — {'PASS' if h2_pass else 'FAIL'}\n"
            f"    Raw CV={med_raw_cv:.3f}, Adj={med_adj_cv:.3f}\n\n"
            f"H3: Supply improves R2 — {'PASS' if h3_pass else 'FAIL'}\n"
            f"    R2: {r2_raw:.4f} -> {r2_plus:.4f}\n\n"
            f"H4: Supply varies w/ glycogen — {'PASS' if h4_pass else 'FAIL'}\n"
            f"    Loaded={med_loaded:.0f}, Depleted={med_depleted:.0f}\n\n"
            f"Supply as % of drop: {pct_of_drop:.0f}%\n"
            f"Corr(roc, ISF): r={r_roc_isf:.3f}"
        )
        ax.text(0.1, 0.9, scorecard, fontsize=11, fontfamily="monospace",
                verticalalignment="top", transform=ax.transAxes,
                bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        plt.tight_layout()
        plt.savefig(VIS_DIR / "supply_contamination.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Visualization: {VIS_DIR / 'supply_contamination.png'}")
    except ImportError:
        print("  (matplotlib not available)")

    # ── Results ──
    results = {
        "experiment": EXP_ID,
        "title": EXP_TITLE,
        "n_events": len(df),
        "n_with_roc": len(ev),
        "pct_rising": round(100 * n_rising / len(ev), 1),
        "median_isf_rising": round(float(med_rising), 1),
        "median_isf_falling": round(float(med_falling), 1),
        "supply_contribution_median": round(float(supply.median()), 1),
        "supply_as_pct_of_drop": round(float(pct_of_drop), 1),
        "corr_roc_isf": round(float(r_roc_isf), 3),
        "cv_raw": round(float(med_raw_cv), 3),
        "cv_adjusted": round(float(med_adj_cv), 3),
        "r2_raw": round(float(r2_raw), 4),
        "r2_adjusted": round(float(r2_adj), 4),
        "r2_raw_plus_supply": round(float(r2_plus), 4),
        "supply_delta_r2": round(float(r2_plus - r2_raw), 4),
        "hypotheses": {
            "H1": {"description": "ISF lower when rising", "pass": h1_pass,
                    "rising": round(float(med_rising), 1), "falling": round(float(med_falling), 1)},
            "H2": {"description": "Adjusted CV lower", "pass": h2_pass,
                    "raw_cv": round(float(med_raw_cv), 3), "adj_cv": round(float(med_adj_cv), 3)},
            "H3": {"description": "Supply improves R2", "pass": h3_pass,
                    "r2_raw": round(float(r2_raw), 4), "r2_plus": round(float(r2_plus), 4)},
            "H4": {"description": "Supply varies with glycogen", "pass": h4_pass,
                    "loaded": round(float(med_loaded), 1), "depleted": round(float(med_depleted), 1)},
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
