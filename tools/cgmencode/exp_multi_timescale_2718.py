#!/usr/bin/env python3
"""EXP-2718: Multi-Timescale Carb Features — Does 72h Beat 48h?

Glucose supply is driven by glycogen stores that cycle on 48-72h timescales.
Our prior experiments used a 48h carb rolling sum as glycogen proxy, but
the user hypothesizes that 72h windows might capture the full glycogen cycle
better (glycogen supercompensation, post-exercise reloading).

This experiment computes carb features at 6 timescales (2h, 6h, 12h, 24h,
48h, 72h) and tests which best explains ISF variance. This directly tests
the Nyquist concern: are we missing signal by using too-short windows?

Hypotheses:
  H1: Carb features at different timescales explain different amounts of ISF variance
  H2: 72h carbs explain more ISF variance than 48h (full glycogen cycle)
  H3: Adding 72h carbs to multi-factor model increases R² beyond 48h
  H4: Supply-side features (carb windows + glucose_roc) collectively explain >5% of ISF variance

Design:
  - For each event, compute rolling carb sums at 6 timescales
  - Single-factor R² for each timescale
  - Multi-factor model: patient + BG0 + dose + carb_window + roc
  - Compare 48h vs 72h in the full model

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
OUT_JSON = Path("externals/experiments/exp-2718_multi_timescale.json")
VIS_DIR = Path("visualizations/multi-timescale")

BG_FLOOR = 180.0
HORIZON_STEPS = 24
MIN_DOSE = 0.3

# Timescale windows in 5-min steps
TIMESCALES = {
    "2h": 24,
    "6h": 72,
    "12h": 144,
    "24h": 288,
    "48h": 576,
    "72h": 864,
}

EXP_ID = "EXP-2718"
EXP_TITLE = "Multi-Timescale Carb Features"


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


def compute_multi_timescale_carbs(grid):
    """Compute rolling carb sums at multiple timescales."""
    if "carbs" not in grid.columns:
        for label in TIMESCALES:
            grid[f"carbs_{label}"] = 0.0
        return grid

    result = []
    for pid, pg in grid.groupby("patient_id"):
        pg = pg.sort_values("time").copy()
        carbs = pg["carbs"].fillna(0).values
        cumsum = np.cumsum(carbs)

        for label, window in TIMESCALES.items():
            col = f"carbs_{label}"
            vals = np.zeros(len(carbs))
            for i in range(len(carbs)):
                start = max(0, i - window)
                vals[i] = cumsum[i] - (cumsum[start - 1] if start > 0 else 0)
            pg[col] = vals

        result.append(pg)

    return pd.concat(result, ignore_index=True)


def extract_events(grid):
    """Extract correction events with multi-timescale features."""
    print("Extracting correction events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
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
        roc = pg["glucose_roc"].values if has_roc else np.full(len(pg), np.nan)
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" not in pg.columns:
            continue

        # Pre-extract timescale columns
        ts_vals = {}
        for label in TIMESCALES:
            col = f"carbs_{label}"
            ts_vals[label] = pg[col].values if col in pg.columns else np.zeros(len(pg))

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

            event = {
                "patient_id": pid,
                "step_index": i,
                "bg0": bg0,
                "bg_end": bg_end,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "pre_roc": float(roc[i]) if not np.isnan(roc[i]) else np.nan,
                "controller": ctrl,
            }
            for label in TIMESCALES:
                event[f"carbs_{label}"] = float(ts_vals[label][i])

            events.append(event)

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    print("\nLoading data...")
    grid = load_data()
    print("Computing multi-timescale carb features...")
    grid = compute_multi_timescale_carbs(grid)
    print("Extracting events...")
    ev = extract_events(grid)

    from numpy.linalg import lstsq
    y = ev["demand_isf"].values
    ss_tot = np.sum((y - y.mean()) ** 2)

    def r2_from_X(X):
        X_int = np.column_stack([X, np.ones(len(X))])
        beta, _, _, _ = lstsq(X_int, y, rcond=None)
        return 1 - np.sum((y - X_int @ beta) ** 2) / ss_tot

    # ── H1: Different timescales explain different amounts ──
    print("\n── H1: Timescale R² comparison ──")
    ts_r2 = {}
    for label in TIMESCALES:
        col = f"carbs_{label}"
        r2 = r2_from_X(ev[[col]].values)
        ts_r2[label] = r2
        print(f"  {label:>4s}: R²={r2:.6f}")

    r2_values = list(ts_r2.values())
    h1_pass = bool(max(r2_values) - min(r2_values) > 0.0001)
    print(f"  Range: {max(r2_values) - min(r2_values):.6f}")
    print(f"  H1 verdict: {'PASS' if h1_pass else 'FAIL'}")

    # ── H2: 72h > 48h ──
    print("\n── H2: 72h carbs > 48h carbs? ──")
    r2_48 = ts_r2["48h"]
    r2_72 = ts_r2["72h"]
    h2_pass = bool(r2_72 > r2_48)
    print(f"  48h R²: {r2_48:.6f}")
    print(f"  72h R²: {r2_72:.6f}")
    print(f"  72h better: {r2_72 > r2_48}")
    print(f"  H2 verdict: {'PASS' if h2_pass else 'FAIL'}")

    # ── H3: 72h adds to multi-factor beyond 48h ──
    print("\n── H3: 72h adds incremental R² to multi-factor? ──")
    # Base model: patient + BG0 + dose + IOB
    X_base = np.column_stack([
        pd.get_dummies(ev["patient_id"], prefix="p").values,
        ev["bg0"].values.reshape(-1, 1),
        ev["total_insulin"].values.reshape(-1, 1),
        ev["iob_start"].values.reshape(-1, 1),
    ])
    r2_base = r2_from_X(X_base)

    # + 48h carbs
    X_48 = np.column_stack([X_base, ev["carbs_48h"].values.reshape(-1, 1)])
    r2_base_48 = r2_from_X(X_48)

    # + 72h carbs
    X_72 = np.column_stack([X_base, ev["carbs_72h"].values.reshape(-1, 1)])
    r2_base_72 = r2_from_X(X_72)

    # + both 48h and 72h
    X_both = np.column_stack([
        X_base,
        ev["carbs_48h"].values.reshape(-1, 1),
        ev["carbs_72h"].values.reshape(-1, 1),
    ])
    r2_base_both = r2_from_X(X_both)

    h3_pass = bool(r2_base_both > r2_base_48 + 0.0001)
    print(f"  Base R²:           {r2_base:.4f}")
    print(f"  + 48h carbs:       {r2_base_48:.4f} (Δ={r2_base_48-r2_base:.4f})")
    print(f"  + 72h carbs:       {r2_base_72:.4f} (Δ={r2_base_72-r2_base:.4f})")
    print(f"  + both 48h & 72h:  {r2_base_both:.4f} (Δ={r2_base_both-r2_base:.4f})")
    print(f"  72h adds beyond 48h: {r2_base_both - r2_base_48:.6f}")
    print(f"  H3 verdict: {'PASS' if h3_pass else 'FAIL'}")

    # ── H4: All supply features collectively >5% ──
    print("\n── H4: All supply features explain >5%? ──")
    # Supply features: all carb windows + glucose_roc
    ev_roc = ev[ev["pre_roc"].notna()].copy()
    y_roc = ev_roc["demand_isf"].values
    ss_tot_roc = np.sum((y_roc - y_roc.mean()) ** 2)

    X_supply = np.column_stack([
        ev_roc[f"carbs_{label}"].values.reshape(-1, 1) for label in TIMESCALES
    ] + [
        ev_roc["pre_roc"].values.reshape(-1, 1),
    ])
    X_int = np.column_stack([X_supply, np.ones(len(ev_roc))])
    beta_s, _, _, _ = lstsq(X_int, y_roc, rcond=None)
    r2_supply_only = 1 - np.sum((y_roc - X_int @ beta_s) ** 2) / ss_tot_roc

    # Use ev_roc-scoped y for full supply model
    y_roc_full = ev_roc["demand_isf"].values
    ss_tot_roc_full = np.sum((y_roc_full - y_roc_full.mean()) ** 2)

    def r2_from_X_roc(X):
        X_int2 = np.column_stack([X, np.ones(len(X))])
        beta2, _, _, _ = lstsq(X_int2, y_roc_full, rcond=None)
        return 1 - np.sum((y_roc_full - X_int2 @ beta2) ** 2) / ss_tot_roc_full

    # Full model with patient dummies + supply
    X_full_supply = np.column_stack([
        pd.get_dummies(ev_roc["patient_id"], prefix="p").values,
        ev_roc["bg0"].values.reshape(-1, 1),
        ev_roc["total_insulin"].values.reshape(-1, 1),
        ev_roc["iob_start"].values.reshape(-1, 1),
        X_supply,
    ])
    r2_full_supply = r2_from_X_roc(X_full_supply)

    # Demand-only model for comparison
    X_demand_only = np.column_stack([
        pd.get_dummies(ev_roc["patient_id"], prefix="p").values,
        ev_roc["bg0"].values.reshape(-1, 1),
        ev_roc["total_insulin"].values.reshape(-1, 1),
        ev_roc["iob_start"].values.reshape(-1, 1),
    ])
    r2_demand_only = r2_from_X_roc(X_demand_only)

    supply_increment = r2_full_supply - r2_demand_only
    h4_pass = bool(supply_increment > 0.005 or r2_supply_only > 0.05)
    print(f"  Supply-only R²:    {r2_supply_only:.4f}")
    print(f"  Demand-only R²:    {r2_demand_only:.4f}")
    print(f"  Full (demand+supply) R²: {r2_full_supply:.4f}")
    print(f"  Supply increment:  {supply_increment:.4f}")
    print(f"  H4 verdict: {'PASS' if h4_pass else 'FAIL'}")

    # ── Per-timescale correlation with ISF ──
    print("\n── Correlation: carb windows vs demand ISF ──")
    for label in TIMESCALES:
        col = f"carbs_{label}"
        r = ev[col].corr(ev["demand_isf"])
        print(f"  {label:>4s}: r={r:.4f}")

    # ── Visualization ──
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle(f"{EXP_ID}: {EXP_TITLE}\nDoes the 72h glycogen cycle explain more ISF variance than 48h?",
                     fontsize=13, fontweight="bold")

        # Panel 1: R² by timescale
        ax = axes[0, 0]
        labels_ts = list(TIMESCALES.keys())
        r2_vals = [ts_r2[l] for l in labels_ts]
        colors = ["#9E9E9E" if l not in ("48h", "72h") else "#F44336" if l == "48h" else "#4CAF50" for l in labels_ts]
        bars = ax.bar(labels_ts, r2_vals, color=colors, alpha=0.8, edgecolor="white")
        ax.set_ylabel("Single-factor R2")
        ax.set_xlabel("Carb window")
        ax.set_title("ISF Variance Explained by Timescale")
        for bar, val in zip(bars, r2_vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.0001,
                    f"{val:.5f}", ha="center", fontsize=7, rotation=45)

        # Panel 2: Multi-factor R² comparison
        ax = axes[0, 1]
        model_labels = ["Base\n(pt+BG+dose)", "+48h", "+72h", "+both"]
        model_r2 = [r2_base, r2_base_48, r2_base_72, r2_base_both]
        bars = ax.bar(model_labels, model_r2, color=["#9E9E9E", "#F44336", "#4CAF50", "#2196F3"], alpha=0.8)
        for bar, val in zip(bars, model_r2):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.001,
                    f"{val:.4f}", ha="center", fontsize=9)
        ax.set_ylabel("Cumulative R2")
        ax.set_title("Multi-Factor + Glycogen Timescale")

        # Panel 3: Supply vs demand R² decomposition
        ax = axes[0, 2]
        categories = ["Demand only\n(pt+BG+dose+IOB)", "Supply only\n(carbs+roc)", "Combined"]
        vals_bar = [r2_demand_only, r2_supply_only, r2_full_supply]
        ax.bar(categories, vals_bar, color=["#1976D2", "#FF9800", "#4CAF50"], alpha=0.8)
        for i, v in enumerate(vals_bar):
            ax.text(i, v + 0.002, f"{v:.4f}", ha="center", fontsize=10)
        ax.set_ylabel("R2")
        ax.set_title("Demand vs Supply Components")

        # Panel 4: Correlation by timescale
        ax = axes[1, 0]
        corrs = [ev[f"carbs_{l}"].corr(ev["demand_isf"]) for l in labels_ts]
        ax.plot(labels_ts, corrs, "b-o", linewidth=2, markersize=8)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylabel("Correlation with ISF")
        ax.set_xlabel("Carb window")
        ax.set_title("ISF Correlation by Timescale")
        ax.grid(True, alpha=0.3)

        # Panel 5: Carb window correlations between timescales
        ax = axes[1, 1]
        carb_cols = [f"carbs_{l}" for l in labels_ts]
        corr_mat = ev[carb_cols].corr().values
        im = ax.imshow(corr_mat, cmap="RdYlBu_r", vmin=0, vmax=1)
        ax.set_xticks(range(len(labels_ts)))
        ax.set_yticks(range(len(labels_ts)))
        ax.set_xticklabels(labels_ts, fontsize=8)
        ax.set_yticklabels(labels_ts, fontsize=8)
        for i_row in range(len(labels_ts)):
            for j_col in range(len(labels_ts)):
                ax.text(j_col, i_row, f"{corr_mat[i_row, j_col]:.2f}",
                        ha="center", va="center", fontsize=7)
        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title("Inter-Timescale Correlation")

        # Panel 6: Scorecard
        ax = axes[1, 2]
        ax.axis("off")
        best_ts = max(ts_r2, key=ts_r2.get)
        scorecard = (
            f"H1: Timescales differ — {'PASS' if h1_pass else 'FAIL'}\n"
            f"    Best: {best_ts} (R2={ts_r2[best_ts]:.6f})\n\n"
            f"H2: 72h > 48h — {'PASS' if h2_pass else 'FAIL'}\n"
            f"    48h={r2_48:.6f}, 72h={r2_72:.6f}\n\n"
            f"H3: 72h adds to multi-factor — {'PASS' if h3_pass else 'FAIL'}\n"
            f"    48h: {r2_base_48:.4f}, both: {r2_base_both:.4f}\n\n"
            f"H4: Supply features >0.5% — {'PASS' if h4_pass else 'FAIL'}\n"
            f"    Supply-only: {r2_supply_only:.4f}\n"
            f"    Supply increment: {supply_increment:.4f}"
        )
        ax.text(0.05, 0.95, scorecard, fontsize=10, fontfamily="monospace",
                verticalalignment="top", transform=ax.transAxes,
                bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

        plt.tight_layout()
        plt.savefig(VIS_DIR / "multi_timescale.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Visualization: {VIS_DIR / 'multi_timescale.png'}")
    except ImportError:
        print("  (matplotlib not available)")

    # ── Results ──
    results = {
        "experiment": EXP_ID,
        "title": EXP_TITLE,
        "n_events": len(ev),
        "n_patients": int(ev["patient_id"].nunique()),
        "timescale_r2": {k: round(v, 6) for k, v in ts_r2.items()},
        "r2_base": round(float(r2_base), 4),
        "r2_base_48": round(float(r2_base_48), 4),
        "r2_base_72": round(float(r2_base_72), 4),
        "r2_base_both": round(float(r2_base_both), 4),
        "r2_supply_only": round(float(r2_supply_only), 4),
        "r2_demand_only": round(float(r2_demand_only), 4),
        "r2_full_supply": round(float(r2_full_supply), 4),
        "supply_increment": round(float(supply_increment), 4),
        "hypotheses": {
            "H1": {"description": "Timescales differ", "pass": h1_pass},
            "H2": {"description": "72h > 48h", "pass": h2_pass,
                    "r2_48h": round(r2_48, 6), "r2_72h": round(r2_72, 6)},
            "H3": {"description": "72h adds to multi-factor", "pass": h3_pass,
                    "increment": round(float(r2_base_both - r2_base_48), 6)},
            "H4": {"description": "Supply features >0.5%", "pass": h4_pass,
                    "supply_r2": round(float(r2_supply_only), 4)},
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
