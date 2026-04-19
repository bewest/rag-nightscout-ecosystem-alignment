#!/usr/bin/env python3
"""EXP-2676: Cross-Controller PK Model Comparison

Tests whether insulin pharmacokinetics (PK) can be modeled identically
across Loop, Trio, and OpenAPS controllers.

KEY FINDING from source code analysis:
  All 4 systems (Loop, oref0, AAPS, Trio) use the SAME exponential PK
  formula from LoopKit (GitHub issue #388). The only differences are:
    - DIA defaults: Loop=6h, oref0=3h, AAPS=profile, Trio=10h
    - Peak time: All default to 75min (rapid) or 55min (ultra-rapid)
    - oref0/Trio also support bilinear model

This experiment validates empirically whether the reported IOB/activity
values in devicestatus are consistent with the shared exponential model.

Panels:
  1. Theoretical PK curves (DIA × peak parameter space)
  2. IOB decomposition validity (bolus_iob + basal_iob ≈ total IOB)
  3. Empirical IOB decay after isolated boluses
  4. Insulin activity: theoretical vs observed
  5. pred_iob_30 accuracy (predicted vs actual)
  6. Cross-controller IOB semantics comparison
"""

import json
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import curve_fit

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
DS = ROOT / "externals/ns-parquet/training/devicestatus.parquet"
MANIFEST = ROOT / "externals/experiments/autoprepare-qualified.json"
VIS_DIR = ROOT / "visualizations/pk-model-comparison"
EXP_DIR = ROOT / "externals/experiments"

VIS_DIR.mkdir(parents=True, exist_ok=True)

# ── Shared Exponential PK Model (LoopKit / oref0 / AAPS / Trio) ────────
def exponential_iob(t_min, dia_min, peak_min):
    """Percent IOB remaining at time t_min after bolus.

    This is the SHARED formula across all 4 AID systems:
      Loop: ExponentialInsulinModel.swift
      oref0: lib/iob/calculate.js (exponential branch)
      AAPS: InsulinOrefBasePlugin.kt
      Trio: trio-oref/lib/iob/calculate.js

    Reference: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
    """
    t = np.asarray(t_min, dtype=float)
    td = float(dia_min)
    tp = float(peak_min)

    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))

    result = np.where(
        t <= 0, 1.0,
        np.where(
            t >= td, 0.0,
            1 - S * (1 - a) * (
                (t**2 / (tau * td * (1 - a)) - t / tau - 1)
                * np.exp(-t / tau) + 1
            )
        )
    )
    return np.clip(result, 0, 1)


def exponential_activity(t_min, dia_min, peak_min):
    """Insulin activity (negative derivative of IOB) at time t_min."""
    t = np.asarray(t_min, dtype=float)
    td = float(dia_min)
    tp = float(peak_min)

    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    S = 1 / (1 - a + (1 + a) * np.exp(-td / tau))

    result = np.where(
        (t <= 0) | (t >= td), 0.0,
        (S / (tau**2)) * t * (1 - t / td) * np.exp(-t / tau)
    )
    return np.clip(result, 0, None)


# ── oref0 Bilinear Model ────────────────────────────────────────────────
def bilinear_iob(t_min, dia_min=180):
    """oref0 bilinear IOB model (piecewise linear, peak at 75min scaled)."""
    t = np.asarray(t_min, dtype=float)
    dia = float(dia_min)
    # Scale to 3h reference
    scaled = t * 180.0 / dia

    result = np.zeros_like(t)
    for i in range(len(t)):
        s = scaled[i]
        if s <= 0:
            result[i] = 1.0
        elif s >= 180:
            result[i] = 0.0
        elif s < 75:
            x1 = s / 5.0 + 1
            result[i] = -0.001852 * x1**2 + 0.001852 * x1 + 1.0
        else:
            x2 = (s - 75) / 5.0
            result[i] = 0.001323 * x2**2 - 0.054233 * x2 + 0.55556
    return np.clip(result, 0, 1)


# ── Default Parameters ──────────────────────────────────────────────────
SYSTEM_DEFAULTS = {
    "Loop (6h/75m)":       {"dia": 360, "peak": 75, "color": "#1f77b4", "ls": "-"},
    "Trio (10h/75m)":      {"dia": 600, "peak": 75, "color": "#2ca02c", "ls": "-"},
    "oref0 (3h/75m)":      {"dia": 180, "peak": 75, "color": "#d62728", "ls": "-"},
    "AAPS Lyumjev (6h/45m)": {"dia": 360, "peak": 45, "color": "#9467bd", "ls": "--"},
    "Fiasp (6h/55m)":      {"dia": 360, "peak": 55, "color": "#ff7f0e", "ls": "--"},
}


def load_data():
    """Load grid and devicestatus, filter to qualified patients."""
    manifest = json.load(open(MANIFEST))
    qp = manifest["qualified_patients"]

    grid = pd.read_parquet(GRID)
    grid = grid[grid.patient_id.isin(qp)]

    ds = pd.read_parquet(DS)
    ds = ds[ds.patient_id.isin(qp)]

    # Build controller map
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()

    return grid, ds, ctrl_map, qp


# ── Panel 1: Theoretical PK Curves ─────────────────────────────────────
def panel1_theoretical_curves():
    """Compare IOB and activity curves across system defaults."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    t = np.linspace(0, 720, 500)  # 12 hours

    # IOB curves
    ax = axes[0]
    for name, params in SYSTEM_DEFAULTS.items():
        iob = exponential_iob(t, params["dia"], params["peak"])
        ax.plot(t / 60, iob, color=params["color"], ls=params["ls"],
                lw=2, label=name)
    # Also add bilinear for oref0
    iob_bl = bilinear_iob(t, 180)
    ax.plot(t / 60, iob_bl, color="#d62728", ls=":", lw=2,
            label="oref0 bilinear (3h)")

    ax.set_xlabel("Hours after bolus")
    ax.set_ylabel("Fraction IOB remaining")
    ax.set_title("Panel 1a: Theoretical IOB Curves")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.axhline(0.05, color="gray", ls="--", alpha=0.5, label="5% threshold")

    # Activity curves
    ax = axes[1]
    for name, params in SYSTEM_DEFAULTS.items():
        act = exponential_activity(t, params["dia"], params["peak"])
        ax.plot(t / 60, act, color=params["color"], ls=params["ls"],
                lw=2, label=name)

    ax.set_xlabel("Hours after bolus")
    ax.set_ylabel("Insulin activity (fraction/min)")
    ax.set_title("Panel 1b: Theoretical Activity Curves")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_xlim(0, 12)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig1_theoretical_pk_curves.png", dpi=150)
    plt.close(fig)
    print("  Panel 1: Theoretical PK curves saved")


# ── Panel 2: IOB Decomposition Validity ─────────────────────────────────
def panel2_iob_decomposition(ds, ctrl_map):
    """Validate bolus_iob + basal_iob ≈ total IOB."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    results = {}

    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        pts = [p for p, c in ctrl_map.items() if c == ctrl]
        sub = ds[ds.patient_id.isin(pts)].copy()

        # Need all three columns
        mask = sub[["iob", "basal_iob", "bolus_iob"]].notna().all(axis=1)
        valid = sub[mask].copy()

        if len(valid) < 100:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data\n({len(valid)} rows)",
                    transform=ax.transAxes, ha="center", va="center", fontsize=14)
            results[ctrl] = {"n": len(valid), "available": False}
            continue

        valid["iob_sum"] = valid.bolus_iob + valid.basal_iob
        valid["error"] = valid.iob - valid.iob_sum

        # Scatter plot
        sample = valid.sample(min(5000, len(valid)), random_state=42)
        ax.scatter(sample.iob, sample.iob_sum, alpha=0.1, s=3,
                   color={"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl])
        lims = [min(valid.iob.min(), valid.iob_sum.min()),
                max(valid.iob.max(), valid.iob_sum.max())]
        ax.plot(lims, lims, "k--", lw=1, alpha=0.5)

        mae = valid.error.abs().mean()
        r = valid[["iob", "iob_sum"]].corr().iloc[0, 1]
        ax.set_title(f"{ctrl.upper()} (n={len(valid):,})\nMAE={mae:.4f}U, r={r:.6f}")
        ax.set_xlabel("Total IOB (U)")
        ax.set_ylabel("bolus_iob + basal_iob (U)")
        ax.grid(True, alpha=0.3)

        results[ctrl] = {
            "n": len(valid), "mae": float(mae), "r": float(r),
            "available": True
        }

    fig.suptitle("Panel 2: IOB Decomposition Validity (bolus + basal ≈ total)", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig2_iob_decomposition.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Panel 2: IOB decomposition saved")
    return results


# ── Panel 3: Empirical IOB Decay After Isolated Boluses ─────────────────
def panel3_empirical_decay(grid, ds, ctrl_map):
    """Extract IOB decay curves after isolated boluses, fit exponential model.

    KEY INSIGHT: Total IOB in an AID system NEVER shows pure PK decay because
    the controller keeps adding insulin. We compare total IOB (row 1) vs
    bolus_iob component (row 2) where available (Loop/Trio).
    """
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    results = {}

    for row_idx, (iob_col, row_label) in enumerate([
        ("iob", "Total IOB"),
        ("bolus_iob", "Bolus IOB Component"),
    ]):
        for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
            ax = axes[row_idx, idx]
            pts = [p for p, c in ctrl_map.items() if c == ctrl]

            all_traces = []
            for pid in pts:
                pgrid = grid[grid.patient_id == pid].sort_values("time")

                if iob_col not in pgrid.columns or pgrid[iob_col].notna().sum() < 100:
                    continue

                bolus_rows = pgrid[pgrid.bolus > 0.5]

                for _, brow in bolus_rows.iterrows():
                    bt_ts = brow["time"]
                    if not isinstance(bt_ts, pd.Timestamp):
                        bt_ts = pd.Timestamp(bt_ts)
                    if bt_ts.tzinfo is None and pgrid.time.dt.tz is not None:
                        bt_ts = bt_ts.tz_localize("UTC")

                    # 2h prior isolation
                    pre = pgrid[(pgrid.time >= bt_ts - pd.Timedelta(hours=2)) &
                                (pgrid.time < bt_ts)]
                    if pre.bolus.sum() > 0.1:
                        continue
                    if len(pre) > 0 and pre.cob.notna().any() and pre.cob.max() > 5:
                        continue

                    # 8h trace
                    post = pgrid[(pgrid.time >= bt_ts) &
                                 (pgrid.time <= bt_ts + pd.Timedelta(hours=8))]
                    post = post[post[iob_col].notna()].copy()
                    if len(post) < 12:
                        continue

                    t0_val = post[iob_col].iloc[0]
                    if t0_val < 0.3:
                        continue

                    minutes = (post.time - bt_ts).dt.total_seconds() / 60.0
                    frac = post[iob_col].values / t0_val

                    all_traces.append(pd.DataFrame({
                        "t_min": minutes.values, "frac_iob": frac,
                    }))

                if len(all_traces) >= 80:
                    break

            key = f"{iob_col}_{ctrl}"
            if len(all_traces) < 3:
                ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient data\n({len(all_traces)} traces)",
                        transform=ax.transAxes, ha="center", va="center", fontsize=14)
                results[key] = {"n_traces": len(all_traces), "fit": None}
                continue

            traces_df = pd.concat(all_traces, ignore_index=True)

            # Bin and compute median
            traces_df["t_bin"] = (traces_df.t_min / 5).round() * 5
            binned = traces_df.groupby("t_bin").frac_iob.agg(["median", "std", "count"])
            binned = binned[binned["count"] >= 3].reset_index()

            color = {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl]
            ax.fill_between(binned.t_bin / 60,
                            (binned["median"] - binned["std"]).clip(lower=-0.5),
                            (binned["median"] + binned["std"]).clip(upper=2.0),
                            alpha=0.15, color=color)
            ax.plot(binned.t_bin / 60, binned["median"], color=color, lw=2,
                    label=f"Empirical (n={len(all_traces)})")

            # Overlay theory curves
            t_th = np.linspace(0, 480, 200)
            for name, params in [
                ("6h/75m", {"dia": 360, "peak": 75}),
                ("10h/75m", {"dia": 600, "peak": 75}),
                ("3h/75m", {"dia": 180, "peak": 75}),
            ]:
                iob_th = exponential_iob(t_th, params["dia"], params["peak"])
                ax.plot(t_th / 60, iob_th, ls="--", lw=1, alpha=0.6,
                        label=f"Theory {name}")

            # Fit
            try:
                valid_bins = binned[(binned.t_bin >= 10) & (binned.t_bin <= 420)]
                if len(valid_bins) > 5:
                    popt, _ = curve_fit(
                        lambda t, dia, peak: exponential_iob(t, dia, peak),
                        valid_bins.t_bin.values, valid_bins["median"].values,
                        p0=[360, 75], bounds=([120, 30], [720, 150]),
                        maxfev=5000)
                    fit_dia, fit_peak = popt
                    iob_fit = exponential_iob(t_th, fit_dia, fit_peak)
                    ax.plot(t_th / 60, iob_fit, "k-", lw=2, alpha=0.8,
                            label=f"Fit: DIA={fit_dia:.0f}m pk={fit_peak:.0f}m")
                    results[key] = {
                        "n_traces": len(all_traces),
                        "fit_dia_min": float(fit_dia),
                        "fit_peak_min": float(fit_peak),
                    }
                else:
                    results[key] = {"n_traces": len(all_traces), "fit": "too few bins"}
            except Exception as e:
                results[key] = {"n_traces": len(all_traces), "fit_error": str(e)}

            ax.set_title(f"{ctrl.upper()} — {row_label}")
            ax.set_xlabel("Hours after bolus")
            ax.set_ylabel("Fraction remaining")
            ax.legend(fontsize=6, loc="upper right")
            ax.set_xlim(0, 8)
            ax.set_ylim(-0.2, 2.0)
            ax.grid(True, alpha=0.3)
            ax.axhline(0, color="gray", ls="-", alpha=0.3)
            ax.axhline(1, color="gray", ls=":", alpha=0.3)

    fig.suptitle("Panel 3: IOB Decay — Total (row 1) vs Bolus Component (row 2)", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig3_empirical_iob_decay.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Panel 3: Empirical IOB decay saved")
    return results


# ── Panel 4: Insulin Activity Validation ─────────────────────────────────
def panel4_activity_validation(ds, ctrl_map):
    """Compare reported insulin_activity against theoretical expectation."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    results = {}

    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        pts = [p for p, c in ctrl_map.items() if c == ctrl]
        sub = ds[ds.patient_id.isin(pts)].copy()

        mask = sub[["iob", "insulin_activity"]].notna().all(axis=1) & (sub.insulin_activity != 0)
        valid = sub[mask].copy()

        if len(valid) < 100:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient activity data\n({len(valid)} rows)",
                    transform=ax.transAxes, ha="center", va="center", fontsize=14)
            results[ctrl] = {"n": len(valid), "available": False}
            continue

        # Activity vs IOB scatterplot
        sample = valid.sample(min(5000, len(valid)), random_state=42)
        ax.scatter(sample.iob, sample.insulin_activity, alpha=0.1, s=3,
                   color={"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl])
        ax.set_xlabel("Total IOB (U)")
        ax.set_ylabel("Insulin Activity (U/min)")

        # Compute statistics
        r = valid[["iob", "insulin_activity"]].corr().iloc[0, 1]
        med_act = valid.insulin_activity.median()
        max_act = valid.insulin_activity.max()

        ax.set_title(f"{ctrl.upper()} (n={len(valid):,})\nr={r:.3f}, med={med_act:.4f}, max={max_act:.4f}")
        ax.grid(True, alpha=0.3)

        results[ctrl] = {
            "n": len(valid), "r_iob_activity": float(r),
            "median_activity": float(med_act), "max_activity": float(max_act),
            "available": True
        }

    fig.suptitle("Panel 4: Insulin Activity vs IOB", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig4_activity_validation.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Panel 4: Activity validation saved")
    return results


# ── Panel 5: pred_iob_30 BG Prediction Accuracy ─────────────────────────
def panel5_pred_bg_accuracy(grid, ds, ctrl_map):
    """Evaluate IOB-based BG prediction accuracy.

    pred_iob_30 is a GLUCOSE PREDICTION (mg/dL) at t+30min using IOB-only
    model, NOT an insulin prediction. Compare against actual glucose at t+30.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    results = {}

    for idx, ctrl in enumerate(["loop", "trio", "openaps"]):
        ax = axes[idx]
        pts = [p for p, c in ctrl_map.items() if c == ctrl]

        # Use grid for time-aligned glucose; DS for pred_iob_30
        gsub = grid[grid.patient_id.isin(pts)].copy()
        dsub = ds[ds.patient_id.isin(pts) & ds.pred_iob_30.notna()].copy()

        if len(dsub) < 100:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nInsufficient pred data\n({len(dsub)} rows)",
                    transform=ax.transAxes, ha="center", va="center", fontsize=14)
            results[ctrl] = {"n": 0, "available": False}
            continue

        # Match predictions to actual glucose 30 min later via grid
        # Grid is 5-min aligned, so t+30 = 6 rows later
        pairs = []
        for pid in pts:
            pg = gsub[gsub.patient_id == pid].sort_values("time")
            pd_sub = dsub[dsub.patient_id == pid].sort_values("created_at")
            if len(pd_sub) < 20 or len(pg) < 50:
                continue

            # Merge predictions onto nearest grid time
            pg_times = pg.time.values
            pg_glucose = pg.glucose.values

            for _, row in pd_sub.iterrows():
                t_pred = pd.Timestamp(row.created_at)
                if t_pred.tzinfo is None:
                    t_pred = t_pred.tz_localize("UTC")

                # Find grid row closest to t_pred + 30min
                t_target = t_pred + pd.Timedelta(minutes=30)
                diffs = np.abs((pg_times - t_target.to_datetime64()).astype("timedelta64[m]").astype(float))
                best_idx = np.argmin(diffs)
                if diffs[best_idx] > 5:  # within 5 min
                    continue
                actual_bg = pg_glucose[best_idx]
                if np.isnan(actual_bg):
                    continue

                pairs.append({
                    "predicted_bg": row.pred_iob_30,
                    "actual_bg": actual_bg,
                })
                if len(pairs) >= 3000:
                    break
            if len(pairs) >= 3000:
                break

        if len(pairs) < 50:
            ax.text(0.5, 0.5, f"{ctrl.upper()}\nCouldn't match pairs\n({len(pairs)})",
                    transform=ax.transAxes, ha="center", va="center", fontsize=14)
            results[ctrl] = {"n": len(pairs), "available": False}
            continue

        edf = pd.DataFrame(pairs)
        color = {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl]
        ax.scatter(edf.predicted_bg, edf.actual_bg, alpha=0.1, s=5, color=color)
        lims = [40, 400]
        ax.plot(lims, lims, "k--", lw=1, alpha=0.5)

        error = edf.actual_bg - edf.predicted_bg
        mae = error.abs().mean()
        rmse = np.sqrt((error**2).mean())
        r = edf[["predicted_bg", "actual_bg"]].corr().iloc[0, 1]

        ax.set_title(f"{ctrl.upper()} (n={len(edf):,})\nMAE={mae:.1f}mg/dL RMSE={rmse:.1f} r={r:.3f}")
        ax.set_xlabel("IOB-predicted BG at t+30m (mg/dL)")
        ax.set_ylabel("Actual BG at t+30m (mg/dL)")
        ax.set_xlim(40, 400)
        ax.set_ylim(40, 400)
        ax.grid(True, alpha=0.3)

        results[ctrl] = {
            "n": len(edf), "mae": float(mae), "rmse": float(rmse),
            "r": float(r), "available": True
        }

    fig.suptitle("Panel 5: IOB-Based BG Prediction at t+30min", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig5_pred_bg_accuracy.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Panel 5: pred BG accuracy saved")
    return results


# ── Panel 6: Cross-Controller IOB Semantics ──────────────────────────────
def panel6_iob_semantics(grid, ctrl_map):
    """Compare IOB distributions and dynamics across controllers.

    Key question: Does 'IOB = 2.0U' mean the same thing in Loop vs Trio vs OpenAPS?
    """
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    results = {}

    controllers = ["loop", "trio", "openaps"]

    # Row 1: IOB distributions
    for idx, ctrl in enumerate(controllers):
        ax = axes[0, idx]
        pts = [p for p, c in ctrl_map.items() if c == ctrl]
        sub = grid[grid.patient_id.isin(pts)]

        color = {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl]

        for pid in pts[:5]:
            psub = sub[sub.patient_id == pid]
            iob_valid = psub.iob.dropna()
            if len(iob_valid) > 100:
                ax.hist(iob_valid, bins=50, alpha=0.3, density=True,
                        label=pid[:8])

        ax.set_title(f"{ctrl.upper()} IOB Distribution")
        ax.set_xlabel("IOB (U)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=6, loc="upper right")
        ax.grid(True, alpha=0.3)

        # Stats
        iob_all = sub.iob.dropna()
        results[ctrl] = {
            "median_iob": float(iob_all.median()),
            "p90_iob": float(iob_all.quantile(0.9)),
            "max_iob": float(iob_all.max()),
            "pct_negative": float((iob_all < 0).mean() * 100),
        }

    # Row 2: IOB vs glucose relationship
    for idx, ctrl in enumerate(controllers):
        ax = axes[1, idx]
        pts = [p for p, c in ctrl_map.items() if c == ctrl]
        sub = grid[grid.patient_id.isin(pts)]

        valid = sub[sub.iob.notna() & sub.glucose.notna()]
        sample = valid.sample(min(5000, len(valid)), random_state=42)

        color = {"loop": "#1f77b4", "trio": "#2ca02c", "openaps": "#d62728"}[ctrl]
        ax.scatter(sample.glucose, sample.iob, alpha=0.05, s=3, color=color)
        ax.set_xlabel("Glucose (mg/dL)")
        ax.set_ylabel("IOB (U)")
        ax.set_title(f"{ctrl.upper()} IOB vs Glucose")
        ax.axhline(0, color="gray", ls="--", alpha=0.5)
        ax.axvline(180, color="orange", ls="--", alpha=0.5, label="High")
        ax.axvline(70, color="red", ls="--", alpha=0.5, label="Low")
        ax.grid(True, alpha=0.3)
        ax.set_xlim(40, 400)

        # Bin glucose and compute median IOB
        bins = np.arange(50, 350, 20)
        valid_binned = valid.copy()
        valid_binned["g_bin"] = pd.cut(valid_binned.glucose, bins)
        med_iob = valid_binned.groupby("g_bin", observed=True).iob.median()
        centers = [(b.left + b.right) / 2 for b in med_iob.index]
        ax.plot(centers, med_iob.values, "k-", lw=2, label="Median IOB")
        ax.legend(fontsize=7, loc="upper left")

    fig.suptitle("Panel 6: Cross-Controller IOB Semantics", y=1.02)
    fig.tight_layout()
    fig.savefig(VIS_DIR / "fig6_iob_semantics.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Panel 6: IOB semantics saved")
    return results


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("EXP-2676: Cross-Controller PK Model Comparison")
    print("=" * 70)

    print("\nLoading data...")
    grid, ds, ctrl_map, qp = load_data()
    n_by_ctrl = {}
    for p, c in ctrl_map.items():
        n_by_ctrl[c] = n_by_ctrl.get(c, 0) + 1
    print(f"  {len(qp)} patients: {n_by_ctrl}")

    results = {"experiment": "EXP-2676", "title": "Cross-Controller PK Model Comparison"}

    print("\nRunning panels...")

    # Panel 1: Theoretical curves (no data needed)
    panel1_theoretical_curves()

    # Panel 2: IOB decomposition
    results["decomposition"] = panel2_iob_decomposition(ds, ctrl_map)

    # Panel 3: Empirical decay
    results["empirical_decay"] = panel3_empirical_decay(grid, ds, ctrl_map)

    # Panel 4: Activity validation
    results["activity"] = panel4_activity_validation(ds, ctrl_map)

    # Panel 5: pred_iob_30 (actually BG prediction)
    results["pred_bg"] = panel5_pred_bg_accuracy(grid, ds, ctrl_map)

    # Panel 6: IOB semantics
    results["iob_semantics"] = panel6_iob_semantics(grid, ctrl_map)

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print("\n## Source Code Analysis (pre-experiment):")
    print("  ALL 4 systems use identical exponential PK formula")
    print("  (LoopKit GitHub issue #388)")
    print("  Key differences: DIA defaults (3h-10h), peak times (45-75m)")

    print("\n## Panel 2: IOB Decomposition")
    for ctrl, r in results["decomposition"].items():
        if r.get("available"):
            print(f"  {ctrl.upper()}: MAE={r['mae']:.4f}U, r={r['r']:.6f} (n={r['n']:,})")
        else:
            print(f"  {ctrl.upper()}: Insufficient data (n={r.get('n', 0)})")

    print("\n## Panel 3: Empirical IOB Decay (best-fit DIA/peak)")
    for key, r in results["empirical_decay"].items():
        if r.get("fit_dia_min"):
            print(f"  {key}: DIA={r['fit_dia_min']:.0f}min "
                  f"peak={r['fit_peak_min']:.0f}min "
                  f"(n={r['n_traces']} traces)")
        else:
            print(f"  {key}: {r.get('fit_error', r.get('fit', 'no data'))} "
                  f"(n={r.get('n_traces', 0)} traces)")

    print("\n## Panel 4: Activity Validation")
    for ctrl, r in results["activity"].items():
        if r.get("available"):
            print(f"  {ctrl.upper()}: r(IOB,activity)={r['r_iob_activity']:.3f} "
                  f"med={r['median_activity']:.4f}")

    print("\n## Panel 5: IOB-Based BG Prediction at t+30m")
    for ctrl, r in results["pred_bg"].items():
        if r.get("available"):
            print(f"  {ctrl.upper()}: MAE={r['mae']:.1f}mg/dL RMSE={r['rmse']:.1f} r={r['r']:.3f}")

    print("\n## Panel 6: IOB Semantics")
    for ctrl, r in results["iob_semantics"].items():
        print(f"  {ctrl.upper()}: median={r['median_iob']:.2f}U "
              f"P90={r['p90_iob']:.2f}U "
              f"neg={r['pct_negative']:.1f}%")

    # Save results
    with open(EXP_DIR / "exp-2676_pk_model_comparison.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {EXP_DIR / 'exp-2676_pk_model_comparison.json'}")

    return results


if __name__ == "__main__":
    main()
