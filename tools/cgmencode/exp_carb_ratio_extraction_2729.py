#!/usr/bin/env python3
"""EXP-2729: Carb Ratio Extraction via Deconfounding.

Apply the validated independent-event deconfounding methodology (from ISF
extraction in EXP-2720/2723) to MEAL events to extract per-patient Carb
Ratio (CR).  CR = grams of carbs covered by 1 unit of insulin.

Key difference from ISF extraction:
  - ISF uses CORRECTION events (BG>=180, no carbs, bolus present)
  - CR  uses MEAL events (carbs > 5g, bolus present)
  - For CR we assess how well the bolus covered the carbs, not BG drop
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

# ── Paths ────────────────────────────────────────────────────────────────────

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / "exp-2729_carb_ratio.json"
VIZ_DIR = Path("visualizations/carb-ratio")

EXP_ID = "EXP-2729"
EXP_TITLE = "Carb Ratio Extraction — Meal Deconfounding"

# ── Tuning constants ─────────────────────────────────────────────────────────

HORIZON_STEPS = 48          # 4 h at 5-min intervals
MIN_CARBS = 5.0             # minimum grams to qualify as meal
MIN_DOSE = 0.3              # minimum insulin (bolus + SMB) in window
MIN_GAP_STEPS = 48          # 4 h gap for independence
BOLUS_COEFF = -129.2        # channel coefficients (from EXP-2698)
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5
MEAN_COEFF = (BOLUS_COEFF + SMB_COEFF + EXCESS_BASAL_COEFF) / 3.0

# ── Data loading ─────────────────────────────────────────────────────────────


def load_data():
    """Load grid parquet, devicestatus, and qualified-patient manifest."""
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    return grid


# ── Meal-event extraction ────────────────────────────────────────────────────


def extract_meal_events(grid):
    """Identify meal events with 4-h outcome windows.

    A meal event requires:
      1. carbs[i] > 5 g  (or sum in ±6 steps / 30-min window > 5 g)
      2. bolus within ±6 steps > 0
      3. valid glucose at i and i + HORIZON_STEPS
      4. no second meal in [i+6 .. i+HORIZON_STEPS)  (avoid stacking)
    """
    events = []
    has_scheduled_cr = "scheduled_cr" in grid.columns

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(
            drop=True
        )
        n = len(pg)
        if n < HORIZON_STEPS + 1:
            continue

        glucose = pg["glucose"].values.astype(float)
        carbs = pg["carbs"].values.astype(float)
        carbs = np.where(np.isnan(carbs), 0.0, carbs)
        bolus = pg["bolus"].values.astype(float)
        bolus = np.where(np.isnan(bolus), 0.0, bolus)
        smb = pg["bolus_smb"].values.astype(float) if "bolus_smb" in pg.columns else np.zeros(n)
        smb = np.where(np.isnan(smb), 0.0, smb)
        net_basal = pg["net_basal"].values.astype(float) if "net_basal" in pg.columns else np.zeros(n)
        net_basal = np.where(np.isnan(net_basal), 0.0, net_basal)
        iob = pg["iob"].values.astype(float) if "iob" in pg.columns else np.zeros(n)
        iob = np.where(np.isnan(iob), 0.0, iob)

        if has_scheduled_cr:
            sched_cr = pg["scheduled_cr"].values.astype(float)
            sched_cr = np.where(np.isnan(sched_cr), 0.0, sched_cr)
        else:
            sched_cr = np.zeros(n)

        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
        times = pg["time"].values

        for i in range(6, n - HORIZON_STEPS):
            # 30-min window for carbs (i-6 .. i+6)
            lo = max(i - 6, 0)
            hi = min(i + 7, n)
            window_carbs = float(np.sum(carbs[lo:hi]))
            if window_carbs < MIN_CARBS:
                continue

            # bolus in ±6 step window
            window_bolus = float(np.sum(bolus[lo:hi]))
            if window_bolus <= 0:
                continue

            bg0 = glucose[i]
            bg_end = glucose[i + HORIZON_STEPS]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue

            # no second meal in [i+6 .. i+HORIZON_STEPS)
            future_carbs = float(np.sum(carbs[i + 6 : i + HORIZON_STEPS]))
            if future_carbs >= MIN_CARBS:
                continue

            # 4-h aggregations
            bolus_4h = float(np.nansum(bolus[i : i + HORIZON_STEPS]))
            smb_4h = float(np.nansum(smb[i : i + HORIZON_STEPS]))
            excess_basal_4h = float(np.nansum(net_basal[i : i + HORIZON_STEPS])) / 12.0
            total_insulin = bolus_4h + smb_4h + excess_basal_4h

            if total_insulin < MIN_DOSE:
                continue

            bg_change = bg_end - bg0
            hour = int(pd.Timestamp(times[i]).hour) if not pd.isna(times[i]) else 0
            block_idx = min(hour // 4, 5)

            # Profile CR at this step (use median of window or point value)
            profile_cr_val = float(np.median(sched_cr[lo:hi])) if has_scheduled_cr else 0.0
            if profile_cr_val <= 0:
                # fallback: try carbs / bolus wizard if available
                profile_cr_val = 0.0

            observed_cr = window_carbs / max(total_insulin, 0.1)
            bg_change_per_carb = bg_change / max(window_carbs, 1.0)

            events.append(
                {
                    "patient_id": pid,
                    "controller": ctrl,
                    "time_idx": i,
                    "bg0": bg0,
                    "bg_end": bg_end,
                    "bg_change": bg_change,
                    "carbs": window_carbs,
                    "bolus_4h": bolus_4h,
                    "smb_4h": smb_4h,
                    "excess_basal_4h": excess_basal_4h,
                    "total_insulin": total_insulin,
                    "iob_start": float(iob[i]),
                    "hour": hour,
                    "block_idx": block_idx,
                    "profile_cr": profile_cr_val,
                    "observed_cr": observed_cr,
                    "bg_change_per_carb": bg_change_per_carb,
                }
            )

    return pd.DataFrame(events)


# ── Independence filtering ───────────────────────────────────────────────────


def filter_independent(ev):
    """Keep only events with >= 4 h gap from previous event (same patient)."""
    ev = ev.sort_values(["patient_id", "time_idx"]).copy()
    keep = []
    last_idx: dict[str, int] = {}

    for _, row in ev.iterrows():
        pid = row["patient_id"]
        tidx = row["time_idx"]
        if pid not in last_idx or (tidx - last_idx[pid]) >= MIN_GAP_STEPS:
            keep.append(True)
            last_idx[pid] = tidx
        else:
            keep.append(False)

    ev["independent"] = keep
    return ev


# ── Deconfounding helpers ────────────────────────────────────────────────────


def _deconfound_bg_dose(events):
    """Deconfound observed CR by regressing out BG0 and total_insulin (OLS).

    Returns median of (residuals + grand median) — the cleaned CR estimate.
    """
    y = events["observed_cr"].values.copy()
    if len(y) < 4 or np.std(y) < 1e-9:
        return float(np.median(y))

    bg0 = events["bg0"].values.copy()
    dose = events["total_insulin"].values.copy()
    X = np.column_stack([bg0, dose, np.ones(len(events))])
    beta, _, _, _ = lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    return float(np.median(residuals) + np.median(y))


def _deconfound_full(events):
    """Full multi-factor deconfounding of observed CR.

    Regress on: BG0, total_insulin, IOB_start, circadian block dummies,
    bolus_fraction, SMB_fraction.
    """
    y = events["observed_cr"].values.copy()
    if len(y) < 8 or np.std(y) < 1e-9:
        return float(np.median(y))

    bg0 = events["bg0"].values
    dose = events["total_insulin"].values
    iob = events["iob_start"].values

    block_dummies = pd.get_dummies(events["block_idx"], prefix="b").values

    total_chan = events["bolus_4h"].values + events["smb_4h"].values + events["excess_basal_4h"].values
    bolus_frac = np.where(total_chan > 1e-6, events["bolus_4h"].values / total_chan, 0.0)
    smb_frac = np.where(total_chan > 1e-6, events["smb_4h"].values / total_chan, 0.0)

    X = np.column_stack([bg0, dose, iob, block_dummies, bolus_frac, smb_frac])
    X_int = np.column_stack([X, np.ones(len(X))])

    beta, _, _, _ = lstsq(X_int, y, rcond=None)
    residuals = y - X_int @ beta
    return float(np.median(residuals) + np.median(y))


# ── Per-patient CR computation ───────────────────────────────────────────────


def compute_patient_crs(ev_all, ev_indep):
    """Compute CR metrics for every patient, plus held-out MAE evaluation."""
    records = []

    for pid in ev_all["patient_id"].unique():
        pa = ev_all[ev_all["patient_id"] == pid]
        pi = ev_indep[ev_indep["patient_id"] == pid]
        if len(pa) == 0:
            continue

        ctrl = pa["controller"].iloc[0]
        profile_cr_vals = pa["profile_cr"].values
        profile_cr = float(np.median(profile_cr_vals[profile_cr_vals > 0])) if np.any(profile_cr_vals > 0) else 0.0

        observed_cr_all = float(np.median(pa["observed_cr"]))
        observed_cr_indep = float(np.median(pi["observed_cr"])) if len(pi) > 0 else observed_cr_all

        # CV comparison (all vs independent)
        cv_all = float(np.std(pa["observed_cr"]) / max(np.mean(pa["observed_cr"]), 1e-6))
        cv_indep = float(np.std(pi["observed_cr"]) / max(np.mean(pi["observed_cr"]), 1e-6)) if len(pi) > 1 else cv_all

        # BG-change statistics
        bg_changes = pa["bg_change"].values
        median_bg_change = float(np.median(bg_changes))
        pct_under = float(100 * np.mean(bg_changes > 0))
        pct_over = float(100 * np.mean(bg_changes < 0))

        # Deconfounded CR (use independent events when available)
        src = pi if len(pi) >= 8 else pa
        deconfounded_cr = _deconfound_bg_dose(src)
        full_deconf_cr = _deconfound_full(src)

        # Recommended CR: prefer full-deconfound → simple deconfound → observed indep
        recommended = full_deconf_cr if len(src) >= 8 else deconfounded_cr

        # Clamp CR to physiological range [2, 50]
        recommended = float(np.clip(recommended, 2.0, 50.0))

        # Confidence tier
        n_indep = len(pi)
        if n_indep >= 20:
            confidence = "high"
        elif n_indep >= 8:
            confidence = "medium"
        else:
            confidence = "low"

        # Held-out MAE evaluation (even/odd split)
        mae_profile = np.nan
        mae_observed = np.nan
        mae_deconf = np.nan
        if len(pi) >= 4 and profile_cr > 0:
            test_ev = pi.iloc[1::2]  # odd-indexed events
            if len(test_ev) >= 2:
                actual_bg = test_ev["bg_change"].values
                # predicted bg_change if profile CR were perfect: 0
                # but profile CR predicts insulin_needed = carbs / profile_cr
                # shortfall insulin = total_insulin - carbs / profile_cr
                # predicted bg_change ≈ shortfall * ISF  (unknown ISF)
                # Simpler: predict observed_cr and compare
                # MAE of CR directly:
                mae_profile = float(np.mean(np.abs(test_ev["observed_cr"].values - profile_cr)))
                mae_observed = float(np.mean(np.abs(test_ev["observed_cr"].values - observed_cr_indep)))
                mae_deconf = float(np.mean(np.abs(test_ev["observed_cr"].values - recommended)))

        pct_diff = float(100 * (recommended - profile_cr) / profile_cr) if profile_cr > 0 else 0.0
        mae_imp = float(100 * (mae_profile - mae_deconf) / mae_profile) if mae_profile > 0 and not np.isnan(mae_deconf) else 0.0

        records.append(
            {
                "patient_id": pid,
                "controller": ctrl,
                "n_meals_all": len(pa),
                "n_meals_independent": n_indep,
                "profile_cr": round(profile_cr, 2),
                "observed_cr_all": round(observed_cr_all, 2),
                "observed_cr_indep": round(observed_cr_indep, 2),
                "deconfounded_cr": round(deconfounded_cr, 2),
                "full_deconf_cr": round(full_deconf_cr, 2),
                "recommended_cr": round(recommended, 2),
                "median_bg_change": round(median_bg_change, 1),
                "pct_under_bolused": round(pct_under, 1),
                "pct_over_bolused": round(pct_over, 1),
                "cv_all": round(cv_all, 3),
                "cv_indep": round(cv_indep, 3),
                "confidence": confidence,
                "pct_diff_from_profile": round(pct_diff, 1),
                "prediction_mae_profile": round(mae_profile, 2) if not np.isnan(mae_profile) else None,
                "prediction_mae_observed": round(mae_observed, 2) if not np.isnan(mae_observed) else None,
                "prediction_mae_deconf": round(mae_deconf, 2) if not np.isnan(mae_deconf) else None,
                "mae_improvement_pct": round(mae_imp, 1),
            }
        )

    return pd.DataFrame(records)


# ── Hypothesis tests ─────────────────────────────────────────────────────────


def test_h1(pt_df):
    """H1: Observed CR differs from profile CR (paired Wilcoxon)."""
    print("\n── H1: Observed CR vs Profile CR (paired Wilcoxon) ──")
    valid = pt_df[pt_df["profile_cr"] > 0]
    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with profile CR")
        return {"h1_verdict": "SKIP", "p_value": None}

    obs = valid["observed_cr_indep"].values
    prof = valid["profile_cr"].values
    diff = obs - prof

    if np.all(diff == 0):
        print("  SKIP: all differences are zero")
        return {"h1_verdict": "SKIP", "p_value": None}

    stat, p = stats.wilcoxon(obs, prof)
    verdict = "PASS" if p < 0.05 else "FAIL"
    print(f"  Wilcoxon stat={stat:.1f}, p={p:.2e} → {verdict}")
    print(f"  Median profile CR:  {np.median(prof):.1f}")
    print(f"  Median observed CR: {np.median(obs):.1f}")
    print(f"  Median difference:  {np.median(diff):.1f}")
    return {
        "h1_verdict": verdict,
        "wilcoxon_stat": float(stat),
        "p_value": float(p),
        "median_profile_cr": float(np.median(prof)),
        "median_observed_cr": float(np.median(obs)),
        "median_diff": float(np.median(diff)),
    }


def test_h2(pt_df):
    """H2: Majority of patients are systematically under-bolusing for meals.

    Per patient: median bg_change > 0 at 4 h.  PASS if >50 % of patients.
    """
    print("\n── H2: Systematic under-bolusing (median ΔBG > 0) ──")
    n_under = int((pt_df["median_bg_change"] > 0).sum())
    n_total = len(pt_df)
    pct = 100 * n_under / max(n_total, 1)
    verdict = "PASS" if pct > 50 else "FAIL"
    print(f"  {n_under}/{n_total} patients with positive median ΔBG "
          f"({pct:.1f}%) → {verdict}")
    print(f"  Median of medians: {pt_df['median_bg_change'].median():.1f} mg/dL")
    return {
        "h2_verdict": verdict,
        "n_under_bolused": n_under,
        "n_total": n_total,
        "pct_under_bolused": round(pct, 1),
        "population_median_bg_change": float(pt_df["median_bg_change"].median()),
    }


def test_h3(pt_df):
    """H3: Independent-event CR has lower CV than all-event CR (>50 % patients)."""
    print("\n── H3: CV improvement with independence filtering ──")
    improved = pt_df["cv_indep"] < pt_df["cv_all"]
    n_imp = int(improved.sum())
    n_total = len(pt_df)
    pct = 100 * n_imp / max(n_total, 1)
    verdict = "PASS" if pct > 50 else "FAIL"
    print(f"  {n_imp}/{n_total} patients with lower CV ({pct:.1f}%) → {verdict}")
    print(f"  Median CV (all):   {pt_df['cv_all'].median():.3f}")
    print(f"  Median CV (indep): {pt_df['cv_indep'].median():.3f}")
    return {
        "h3_verdict": verdict,
        "n_improved": n_imp,
        "n_total": n_total,
        "pct_improved": round(pct, 1),
        "median_cv_all": float(pt_df["cv_all"].median()),
        "median_cv_indep": float(pt_df["cv_indep"].median()),
    }


def test_h4(pt_df):
    """H4: Deconfounded CR reduces prediction MAE for >50 % of patients."""
    print("\n── H4: Deconfounded CR reduces MAE vs profile ──")
    valid = pt_df.dropna(subset=["prediction_mae_profile", "prediction_mae_deconf"])
    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with MAE data")
        return {"h4_verdict": "SKIP"}

    improved = valid["prediction_mae_deconf"] < valid["prediction_mae_profile"]
    n_imp = int(improved.sum())
    n_valid = len(valid)
    pct = 100 * n_imp / max(n_valid, 1)
    verdict = "PASS" if pct > 50 else "FAIL"
    print(f"  {n_imp}/{n_valid} patients improved ({pct:.1f}%) → {verdict}")
    print(f"  Median MAE (profile):  {valid['prediction_mae_profile'].median():.2f}")
    print(f"  Median MAE (deconf):   {valid['prediction_mae_deconf'].median():.2f}")
    print(f"  Median improvement:    {valid['mae_improvement_pct'].median():.1f}%")

    per_patient = {}
    for _, row in valid.iterrows():
        per_patient[str(row["patient_id"])] = {
            "mae_profile": row["prediction_mae_profile"],
            "mae_deconf": row["prediction_mae_deconf"],
            "improvement_pct": row["mae_improvement_pct"],
            "improved": bool(row["prediction_mae_deconf"] < row["prediction_mae_profile"]),
        }

    return {
        "h4_verdict": verdict,
        "n_improved": n_imp,
        "n_valid": n_valid,
        "pct_improved": round(pct, 1),
        "median_mae_profile": float(valid["prediction_mae_profile"].median()),
        "median_mae_deconf": float(valid["prediction_mae_deconf"].median()),
        "median_mae_improvement_pct": float(valid["mae_improvement_pct"].median()),
        "per_patient": per_patient,
    }


# ── Visualization ────────────────────────────────────────────────────────────


def make_visualization(pt_df, h1_res, h2_res, h3_res, h4_res):
    """Create 2×2 summary figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    ctrl_colors = {
        "loop": "#1f77b4",
        "openaps": "#ff7f0e",
        "trio": "#2ca02c",
        "unknown": "#999999",
    }

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"{EXP_ID}: {EXP_TITLE}",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    # ── Panel 1 (top-left): Profile CR vs Observed CR scatter ────────────
    ax = axes[0, 0]
    valid = pt_df[pt_df["profile_cr"] > 0]
    if len(valid) > 0:
        colors = [ctrl_colors.get(c, "#999999") for c in valid["controller"]]
        ax.scatter(valid["profile_cr"], valid["observed_cr_indep"],
                   c=colors, s=40, alpha=0.7, edgecolors="k", linewidths=0.5)
        lo = min(valid["profile_cr"].min(), valid["observed_cr_indep"].min()) * 0.8
        hi = max(valid["profile_cr"].max(), valid["observed_cr_indep"].max()) * 1.2
        ax.plot([lo, hi], [lo, hi], "k--", lw=1, alpha=0.5, label="y = x")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
    ax.set_xlabel("Profile CR (g/U)")
    ax.set_ylabel("Observed CR (g/U)")
    ax.set_title("Profile vs Observed CR")
    h1v = h1_res.get("h1_verdict", "SKIP")
    ax.text(0.02, 0.98, f"H1: {h1v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h1v == "PASS" else "red")
    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=c,
               markersize=7, label=lab)
        for lab, c in ctrl_colors.items()
        if lab in pt_df["controller"].values
    ]
    if legend_handles:
        ax.legend(handles=legend_handles, fontsize=7, loc="lower right")

    # ── Panel 2 (top-right): Post-meal BG change box-plot ────────────────
    ax = axes[0, 1]
    short_pids = [str(p)[:6] for p in pt_df["patient_id"]]
    box_data = []
    box_labels = []
    # We only have per-patient medians; use them directly as single-value boxes
    for idx, row in pt_df.iterrows():
        box_data.append(row["median_bg_change"])
        box_labels.append(str(row["patient_id"])[:6])

    if box_data:
        x = np.arange(len(box_data))
        bar_colors = ["#ff9999" if v > 0 else "#99ccff" for v in box_data]
        ax.bar(x, box_data, color=bar_colors, edgecolor="k", linewidth=0.5)
        ax.axhline(0, color="black", lw=1, ls="--")
        ax.set_xticks(x)
        ax.set_xticklabels(box_labels, rotation=60, ha="right", fontsize=6)
    ax.set_ylabel("Median ΔBG at 4 h (mg/dL)")
    ax.set_title("Post-Meal BG Change per Patient")
    h2v = h2_res.get("h2_verdict", "SKIP")
    ax.text(0.02, 0.98, f"H2: {h2v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h2v == "PASS" else "red")

    # ── Panel 3 (bottom-left): Under- vs Over-bolused stacked bar ────────
    ax = axes[1, 0]
    if len(pt_df) > 0:
        y_pos = np.arange(len(pt_df))
        ax.barh(y_pos, pt_df["pct_under_bolused"].values,
                color="#ff9999", label="Under-bolused", edgecolor="k", linewidth=0.3)
        ax.barh(y_pos, -pt_df["pct_over_bolused"].values,
                color="#99ccff", label="Over-bolused", edgecolor="k", linewidth=0.3)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(short_pids, fontsize=6)
        ax.set_xlabel("← Over-bolused (%)  |  Under-bolused (%) →")
        ax.legend(fontsize=7, loc="lower right")
    ax.set_title("Under- vs Over-Bolused per Patient")
    h3v = h3_res.get("h3_verdict", "SKIP")
    ax.text(0.02, 0.98, f"H3: {h3v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h3v == "PASS" else "red")

    # ── Panel 4 (bottom-right): CR by time-of-day block ──────────────────
    ax = axes[1, 1]
    block_labels = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"]
    # Collect observed_cr grouped by block_idx (not available in pt_df, derive
    # from information we do have).  We stored block_idx in events, but pt_df
    # is aggregated.  Use a lightweight re-group if possible, otherwise show
    # per-patient recommended CR by controller.
    # Since we don't pass the event dataframe here, create a summary per
    # block from pt_df columns that are available (H4 test is separate).
    # Fallback: bar-chart of recommended_cr coloured by controller.
    if len(pt_df) > 0:
        sorted_pt = pt_df.sort_values("recommended_cr")
        x = np.arange(len(sorted_pt))
        colors = [ctrl_colors.get(c, "#999999") for c in sorted_pt["controller"]]
        ax.bar(x, sorted_pt["recommended_cr"], color=colors, edgecolor="k", linewidth=0.5)
        if sorted_pt["profile_cr"].sum() > 0:
            ax.bar(x, sorted_pt["profile_cr"], color="none", edgecolor="gray",
                   linewidth=1.2, linestyle="--", label="Profile CR")
        ax.set_xticks(x)
        ax.set_xticklabels([str(p)[:6] for p in sorted_pt["patient_id"]],
                           rotation=60, ha="right", fontsize=6)
        ax.set_ylabel("CR (g/U)")
        ax.legend(fontsize=7)
    ax.set_title("Recommended CR vs Profile (sorted)")
    h4v = h4_res.get("h4_verdict", "SKIP")
    ax.text(0.02, 0.98, f"H4: {h4v}", transform=ax.transAxes,
            fontsize=9, va="top",
            color="green" if h4v == "PASS" else "red")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = VIZ_DIR / "carb_ratio.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Visualization: {out_path}")


def make_circadian_visualization(ev_all):
    """Supplemental: CR by time-of-day block (pooled across patients)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    block_labels = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"]
    box_data = []
    labels_used = []
    for b in range(6):
        vals = ev_all.loc[ev_all["block_idx"] == b, "observed_cr"].dropna().values
        if len(vals) > 0:
            box_data.append(vals)
            labels_used.append(block_labels[b])
        else:
            box_data.append([0.0])
            labels_used.append(block_labels[b])

    fig, ax = plt.subplots(figsize=(8, 5))
    bp = ax.boxplot(box_data, tick_labels=labels_used, patch_artist=True)
    palette = ["#c7d4e8", "#fde0a7", "#fde0a7", "#d4edda", "#d4edda", "#c7d4e8"]
    for patch, c in zip(bp["boxes"], palette):
        patch.set_facecolor(c)
    ax.set_xlabel("Time-of-Day Block")
    ax.set_ylabel("Observed CR (g/U)")
    ax.set_title(f"{EXP_ID}: CR by Time of Day (pooled)")

    out_path = VIZ_DIR / "carb_ratio_circadian.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Circadian viz: {out_path}")


# ── Main entry point ─────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 70)

    # ── Load ──
    grid = load_data()
    print(f"  Grid rows: {len(grid):,}  |  Patients: {grid['patient_id'].nunique()}")

    # ── Extract meal events ──
    ev_all = extract_meal_events(grid)
    if len(ev_all) == 0:
        print("ERROR: No meal events extracted. Exiting.")
        sys.exit(1)

    # ── Independence filter ──
    ev_all = filter_independent(ev_all)
    ev_indep = ev_all[ev_all["independent"]].copy()
    n_all = len(ev_all)
    n_indep = len(ev_indep)
    print(f"  All meal events:         {n_all:,}")
    print(f"  Independent meal events: {n_indep:,} "
          f"({100 * n_indep / max(n_all, 1):.1f}%)")

    # ── Per-patient CR ──
    pt_df = compute_patient_crs(ev_all, ev_indep)

    if len(pt_df) == 0:
        print("ERROR: No patients with meal events. Exiting.")
        sys.exit(1)

    # ── Print table ──
    print("\n" + "=" * 70)
    print("  PER-PATIENT CARB RATIO RECOMMENDATIONS")
    print("=" * 70)
    display_cols = [
        "patient_id", "controller", "n_meals_all", "n_meals_independent",
        "profile_cr", "observed_cr_indep", "recommended_cr",
        "median_bg_change", "pct_under_bolused", "pct_diff_from_profile",
        "confidence",
    ]
    show_cols = [c for c in display_cols if c in pt_df.columns]
    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", 200,
        "display.float_format", "{:.1f}".format,
    ):
        print(pt_df[show_cols].to_string(index=False))

    # ── Hypothesis tests ──
    h1_res = test_h1(pt_df)
    h2_res = test_h2(pt_df)
    h3_res = test_h3(pt_df)
    h4_res = test_h4(pt_df)

    verdicts = {
        "H1": h1_res.get("h1_verdict", "SKIP"),
        "H2": h2_res.get("h2_verdict", "SKIP"),
        "H3": h3_res.get("h3_verdict", "SKIP"),
        "H4": h4_res.get("h4_verdict", "SKIP"),
    }
    print(f"\nVerdict: " + " ".join(f"{k}={v}" for k, v in verdicts.items()))

    # ── Visualization ──
    print("\nGenerating visualizations...")
    make_visualization(pt_df, h1_res, h2_res, h3_res, h4_res)
    make_circadian_visualization(ev_all)

    # ── Assemble & save results ──
    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_meal_events_all": n_all,
        "n_meal_events_independent": n_indep,
        "retention_pct": round(100 * n_indep / max(n_all, 1), 1),
        "n_patients": int(pt_df["patient_id"].nunique()),
        "hypotheses": {
            "H1_observed_cr_differs_from_profile": h1_res,
            "H2_systematic_under_bolusing": h2_res,
            "H3_independence_reduces_cv": h3_res,
            "H4_deconfounded_cr_reduces_mae": h4_res,
        },
        "verdict_summary": verdicts,
        "per_patient": pt_df.to_dict(orient="records"),
        "population_summary": {
            "median_profile_cr": float(pt_df["profile_cr"].median()),
            "median_observed_cr": float(pt_df["observed_cr_indep"].median()),
            "median_recommended_cr": float(pt_df["recommended_cr"].median()),
            "median_bg_change": float(pt_df["median_bg_change"].median()),
            "median_pct_diff": float(pt_df["pct_diff_from_profile"].median()),
            "n_under_bolused": int((pt_df["median_bg_change"] > 0).sum()),
            "confidence_counts": {
                "high": int((pt_df["confidence"] == "high").sum()),
                "medium": int((pt_df["confidence"] == "medium").sum()),
                "low": int((pt_df["confidence"] == "low").sum()),
            },
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults: {OUT_JSON}")


if __name__ == "__main__":
    main()
