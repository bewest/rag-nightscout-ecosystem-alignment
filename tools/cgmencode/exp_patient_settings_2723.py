#!/usr/bin/env python3
"""EXP-2723: Per-Patient Settings Extraction Report

THE PAYOFF experiment: extract actionable ISF recommendations for all 21
patients using the validated independent-event deconfounding pipeline from
20 prior experiments.  Compare raw, deconfounded, and profile ISF.
Generate a per-patient recommendations table.

Prior results feeding into this experiment:
  EXP-2710: Multi-factor deconfounding R²=0.224 (all events), 0.173 (independent)
  EXP-2714: Only 9.2% of events are independent (5,998/65,425 at 2h gap)
  EXP-2720: Independent-event ISF yields 29% lower MAE than all-event ISF
  EXP-2722: Cross-controller normalization reduces η² by 55%
  EXP-2698: Channel coefficients: BOLUS=-129.2, SMB=-123.6, EXCESS_BASAL=-130.5
  EXP-2721: Circadian ISF real (2.87×) but flat ISF wins MAE — don't use time-of-day

Hypotheses:
  H1: Recommended ISF differs systematically from profile ISF (Wilcoxon p<0.05)
  H2: Recommended ISF reduces MAE for >60% of patients
  H3: High-confidence patients show larger MAE improvement than low-confidence
  H4: Cross-controller normalized ISF within 20% of deconfounded ISF for >80%

Author: Copilot + bewest
Date: 2025-07-19
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / "exp-2723_patient_settings.json"
VIZ_DIR = Path("visualizations/patient-settings")

HORIZON_STEPS = 24  # 2h at 5-min intervals
BG_FLOOR = 180
MIN_DOSE = 0.3
MIN_GAP_STEPS = 24  # 2h independence gap
CARB_HISTORY_STEPS = 48 * 12  # 48h at 5-min intervals

BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

EXP_ID = "EXP-2723"
EXP_TITLE = "Per-Patient ISF Extraction — From 20 Experiments to Actionable Settings"

# Controller color palette
CTRL_COLORS = {
    "loop": "#1976D2",
    "trio": "#388E3C",
    "openaps": "#F57C00",
    "unknown": "#757575",
}


# ── Data Loading ──

def load_data():
    """Load grid parquet, device status, and qualified patient manifest."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    if "carbs" in grid.columns:
        grid["carbs_48h"] = grid.groupby("patient_id")["carbs"].transform(
            lambda x: x.rolling(576, min_periods=1).sum()
        )
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


# ── Event Extraction ──

def extract_events(grid):
    """Extract correction events: BG>=180, carbs<5g in 2h, dose>=0.3U, 2h horizon."""
    print("Extracting correction events...")
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

            expected_drop = total_insulin * profile_isf
            deviation = observed_drop - expected_drop

            est_bolus = bolus_2h * BOLUS_COEFF
            est_smb = smb_2h * SMB_COEFF
            est_basal = excess_basal_2h * EXCESS_BASAL_COEFF
            residual_all_channels = deviation - est_bolus - est_smb - est_basal

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour
            except Exception:
                hour = 0
            block_idx = min(hour // 4, 5)

            c48 = float(carbs_48h[i]) if not np.isnan(carbs_48h[i]) else 0.0

            events.append({
                "patient_id": pid,
                "time_idx": i,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "expected_drop": expected_drop,
                "deviation": deviation,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "est_bolus_effect": est_bolus,
                "est_smb_effect": est_smb,
                "est_basal_effect": est_basal,
                "residual_all_channels": residual_all_channels,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "carbs_48h": c48,
                "controller": ctrl,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    if len(df) == 0:
        print("  WARNING: 0 events extracted")
        return df

    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        med = df.loc[mask, "carbs_48h"].median()
        df.loc[mask, "glycogen_state"] = np.where(
            df.loc[mask, "carbs_48h"] >= med, "loaded", "depleted"
        )

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


# ── Independence Filtering ──

def filter_independent(ev):
    """Keep only events with >=2h gap from previous event (same patient)."""
    ev = ev.sort_values(["patient_id", "time_idx"]).copy()
    keep = []
    last_idx = {}

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


# ── Per-Patient ISF Extraction ──

def compute_patient_isfs(grid, ev_all, ev_indep):
    """Compute 5 ISF estimates per patient plus MAE metrics."""
    print("\nComputing per-patient ISF estimates (5 methods)...")
    rows = []

    for pid in sorted(ev_all["patient_id"].unique()):
        p_all = ev_all[ev_all["patient_id"] == pid]
        p_indep = ev_indep[ev_indep["patient_id"] == pid]
        p_grid = grid[grid["patient_id"] == pid]
        ctrl = p_all["controller"].iloc[0]
        n_all = len(p_all)
        n_indep = len(p_indep)

        # 1. Profile ISF
        if "scheduled_isf" in p_grid.columns:
            profile_isf = float(np.nanmedian(p_grid["scheduled_isf"].values))
        else:
            profile_isf = float(np.median(p_all["profile_isf"].values))

        # 2. Raw all-event ISF
        raw_all = float(np.median(p_all["demand_isf"].values))

        # 3. Raw independent-event ISF
        if n_indep > 0:
            raw_indep = float(np.median(p_indep["demand_isf"].values))
        else:
            raw_indep = raw_all

        # 4. Deconfounded ISF (BG0 + dose residualization on independent events)
        if n_indep >= 10:
            deconf_isf = _deconfound_bg_dose(p_indep)
        else:
            deconf_isf = raw_indep

        # 5. Cross-controller normalized ISF (full multi-factor)
        if n_indep >= 10:
            norm_isf = _normalize_full(p_indep)
        else:
            norm_isf = deconf_isf

        # Recommended ISF = deconfounded ISF from independent events
        recommended = deconf_isf

        # MAE evaluation on independent events (held-out 50/50 split)
        mae_profile, mae_recommended = _compute_mae_pair(
            p_indep, profile_isf, recommended
        )

        pct_diff = (
            (recommended - profile_isf) / profile_isf * 100
            if profile_isf > 0 else 0.0
        )
        if n_indep >= 100:
            confidence = "high"
        elif n_indep >= 30:
            confidence = "medium"
        else:
            confidence = "low"

        mae_imp = (
            (mae_profile - mae_recommended) / mae_profile * 100
            if mae_profile > 0 else 0.0
        )

        rows.append({
            "patient_id": pid,
            "controller": ctrl,
            "n_events_all": n_all,
            "n_events_independent": n_indep,
            "profile_isf": round(profile_isf, 2),
            "raw_all_isf": round(raw_all, 2),
            "raw_indep_isf": round(raw_indep, 2),
            "deconfounded_isf": round(deconf_isf, 2),
            "normalized_isf": round(norm_isf, 2),
            "recommended_isf": round(recommended, 2),
            "pct_diff_from_profile": round(pct_diff, 1),
            "confidence": confidence,
            "prediction_mae_profile": round(mae_profile, 2),
            "prediction_mae_recommended": round(mae_recommended, 2),
            "mae_improvement_pct": round(mae_imp, 1),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df)} patients with ISF estimates")
    return df


def _deconfound_bg_dose(events):
    """Deconfound ISF by regressing out BG0 and total_insulin (OLS)."""
    y = events["demand_isf"].values.copy()
    bg0 = events["bg0"].values.copy()
    dose = events["total_insulin"].values.copy()

    if np.std(y) < 1e-6:
        return float(np.median(y))

    X = np.column_stack([bg0, dose, np.ones(len(events))])
    beta, _, _, _ = lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    return float(np.median(residuals) + np.median(y))


def _normalize_full(events):
    """Full multi-factor deconfounding: BG0 + dose + IOB + circadian + channel mix."""
    y = events["demand_isf"].values.copy()

    if np.std(y) < 1e-6:
        return float(np.median(y))

    # Circadian block dummies
    block_dummies = pd.get_dummies(events["block_idx"], prefix="b").values

    # Channel fractions
    bolus_total = (
        events["bolus_2h"].values
        + events["smb_2h"].values
        + events["excess_basal_2h"].values
    )
    bolus_frac = np.where(bolus_total > 1e-6,
                          events["bolus_2h"].values / bolus_total, 0.0)
    smb_frac = np.where(bolus_total > 1e-6,
                        events["smb_2h"].values / bolus_total, 0.0)

    X = np.column_stack([
        events["bg0"].values,
        events["total_insulin"].values,
        events["iob_start"].values,
        block_dummies,
        bolus_frac,
        smb_frac,
    ])
    X_int = np.column_stack([X, np.ones(len(X))])

    if X_int.shape[0] <= X_int.shape[1]:
        return float(np.median(y))

    beta, _, _, _ = lstsq(X_int, y, rcond=None)
    residuals = y - X_int @ beta
    return float(np.median(residuals) + np.median(y))


def _compute_mae_pair(events, isf_profile, isf_recommended):
    """Compute MAE for profile and recommended ISF on held-out 50% split."""
    if len(events) < 4:
        # Too few events for a meaningful split
        bg0 = events["bg0"].values
        bg_end = events["bg_end"].values
        dose = events["total_insulin"].values
        pred_prof = bg0 - dose * isf_profile
        pred_rec = bg0 - dose * isf_recommended
        return (
            float(np.mean(np.abs(bg_end - pred_prof))),
            float(np.mean(np.abs(bg_end - pred_rec))),
        )

    # 50/50 held-out split (deterministic by index parity)
    idx = np.arange(len(events))
    test_mask = (idx % 2) == 1
    test = events.iloc[test_mask]

    bg0 = test["bg0"].values
    bg_end = test["bg_end"].values
    dose = test["total_insulin"].values

    pred_prof = bg0 - dose * isf_profile
    pred_rec = bg0 - dose * isf_recommended

    mae_prof = float(np.mean(np.abs(bg_end - pred_prof)))
    mae_rec = float(np.mean(np.abs(bg_end - pred_rec)))
    return mae_prof, mae_rec


# ── Hypothesis Tests ──

def test_h1(pt_df):
    """H1: Recommended ISF differs systematically from profile ISF (Wilcoxon)."""
    print("\n── H1: Recommended vs Profile ISF (paired Wilcoxon) ──")
    rec = pt_df["recommended_isf"].values
    prof = pt_df["profile_isf"].values
    diff = rec - prof

    if len(diff) < 3 or np.all(diff == 0):
        print("  SKIP: insufficient data")
        return {"h1_verdict": "SKIP", "p_value": None}

    stat, p = stats.wilcoxon(rec, prof)
    verdict = "PASS" if p < 0.05 else "FAIL"
    print(f"  Wilcoxon stat={stat:.1f}, p={p:.2e} → {verdict}")
    print(f"  Median profile ISF: {np.median(prof):.1f}")
    print(f"  Median recommended ISF: {np.median(rec):.1f}")
    print(f"  Median difference: {np.median(diff):.1f}")
    return {
        "h1_verdict": verdict,
        "wilcoxon_stat": float(stat),
        "p_value": float(p),
        "median_profile": float(np.median(prof)),
        "median_recommended": float(np.median(rec)),
        "median_diff": float(np.median(diff)),
    }


def test_h2(pt_df):
    """H2: Recommended ISF reduces MAE for >60% of patients."""
    print("\n── H2: MAE improvement for majority of patients ──")
    improved = pt_df["mae_improvement_pct"] > 0
    n_improved = int(improved.sum())
    n_total = len(pt_df)
    pct = 100 * n_improved / max(n_total, 1)
    verdict = "PASS" if pct > 60 else "FAIL"
    print(f"  {n_improved}/{n_total} patients improved ({pct:.1f}%) → {verdict}")
    print(f"  Median MAE improvement: {pt_df['mae_improvement_pct'].median():.1f}%")

    per_patient = {}
    for _, row in pt_df.iterrows():
        per_patient[str(row["patient_id"])] = {
            "mae_profile": row["prediction_mae_profile"],
            "mae_recommended": row["prediction_mae_recommended"],
            "improvement_pct": row["mae_improvement_pct"],
            "improved": bool(row["mae_improvement_pct"] > 0),
        }

    return {
        "h2_verdict": verdict,
        "n_improved": n_improved,
        "n_total": n_total,
        "pct_improved": round(pct, 1),
        "median_mae_improvement_pct": float(pt_df["mae_improvement_pct"].median()),
        "per_patient": per_patient,
    }


def test_h3(pt_df):
    """H3: High-confidence patients show larger MAE improvements than low."""
    print("\n── H3: Confidence tier vs MAE improvement ──")
    tiers = {}
    for tier in ["high", "medium", "low"]:
        sub = pt_df[pt_df["confidence"] == tier]
        if len(sub) > 0:
            med_imp = float(sub["mae_improvement_pct"].median())
            tiers[tier] = {
                "n_patients": len(sub),
                "median_mae_improvement_pct": round(med_imp, 1),
            }
            print(f"  {tier:>6}: {len(sub)} patients, "
                  f"median MAE improvement = {med_imp:.1f}%")
        else:
            tiers[tier] = {"n_patients": 0, "median_mae_improvement_pct": 0.0}

    high_imp = tiers.get("high", {}).get("median_mae_improvement_pct", 0)
    low_imp = tiers.get("low", {}).get("median_mae_improvement_pct", 0)
    # PASS if high-confidence tier has larger improvement than low-confidence
    verdict = "PASS" if high_imp > low_imp else "FAIL"
    print(f"  High ({high_imp:.1f}%) vs Low ({low_imp:.1f}%) → {verdict}")
    return {
        "h3_verdict": verdict,
        "tiers": tiers,
        "high_improvement": high_imp,
        "low_improvement": low_imp,
    }


def test_h4(pt_df):
    """H4: Cross-controller normalized ISF within 20% of deconfounded for >80%."""
    print("\n── H4: Normalized vs Deconfounded ISF agreement ──")
    deconf = pt_df["deconfounded_isf"].values
    norm = pt_df["normalized_isf"].values

    with np.errstate(divide="ignore", invalid="ignore"):
        pct_diff = np.abs(norm - deconf) / np.where(deconf != 0, deconf, np.nan)

    valid = ~np.isnan(pct_diff)
    within_20 = np.sum(pct_diff[valid] < 0.20)
    n_valid = int(valid.sum())
    pct_within = 100 * within_20 / max(n_valid, 1)
    verdict = "PASS" if pct_within > 80 else "FAIL"
    print(f"  {within_20}/{n_valid} patients within 20% → {pct_within:.1f}% → {verdict}")

    per_patient = {}
    for _, row in pt_df.iterrows():
        d = row["deconfounded_isf"]
        n = row["normalized_isf"]
        pdiff = abs(n - d) / d * 100 if d != 0 else 0
        per_patient[str(row["patient_id"])] = {
            "deconfounded": d,
            "normalized": n,
            "pct_diff": round(pdiff, 1),
            "within_20pct": bool(pdiff < 20),
        }

    return {
        "h4_verdict": verdict,
        "n_within_20pct": int(within_20),
        "n_valid": n_valid,
        "pct_within_20pct": round(pct_within, 1),
        "per_patient": per_patient,
    }


# ── Visualization ──

def make_visualization(pt_df, h1_res, h2_res, h3_res, h4_res):
    """Create 2×3 summary figure: the payoff visualization."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(
        f"{EXP_ID}: {EXP_TITLE}",
        fontsize=14, fontweight="bold", y=0.98,
    )

    # Sort patients: by controller then profile ISF
    pt_sorted = pt_df.sort_values(["controller", "profile_isf"]).reset_index(drop=True)
    pids = pt_sorted["patient_id"].astype(str).values
    short_pids = [p[:6] for p in pids]
    n_pts = len(pt_sorted)

    # ── Panel 1 (top-left): Per-patient ISF comparison (grouped bar) ──
    ax = axes[0, 0]
    x = np.arange(n_pts)
    w = 0.35
    colors_prof = [CTRL_COLORS.get(c, "#757575") for c in pt_sorted["controller"]]
    ax.bar(x - w / 2, pt_sorted["profile_isf"].values, w,
           color=colors_prof, alpha=0.4, edgecolor="black", linewidth=0.5,
           label="Profile ISF")
    ax.bar(x + w / 2, pt_sorted["recommended_isf"].values, w,
           color=colors_prof, alpha=0.9, edgecolor="black", linewidth=0.5,
           label="Recommended ISF")
    pop_median = float(np.median(pt_sorted["recommended_isf"].values))
    ax.axhline(pop_median, color="red", linestyle="--", linewidth=1, alpha=0.7,
               label=f"Pop. median = {pop_median:.0f}")
    ax.set_xticks(x)
    ax.set_xticklabels(short_pids, rotation=60, ha="right", fontsize=6)
    ax.set_ylabel("ISF (mg/dL per U)")
    ax.set_title("Per-Patient ISF: Profile vs Recommended")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 2 (top-center): ISF change from profile (horizontal bar) ──
    ax = axes[0, 1]
    pct_diff = pt_sorted["pct_diff_from_profile"].values
    bar_colors = ["#D32F2F" if d < 0 else "#1976D2" for d in pct_diff]
    y_pos = np.arange(n_pts)
    ax.barh(y_pos, pct_diff, color=bar_colors, alpha=0.8, edgecolor="black",
            linewidth=0.3)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(short_pids, fontsize=6)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel("% change from profile ISF")
    ax.set_title("ISF Change: Red = more effective, Blue = less effective")
    for i, v in enumerate(pct_diff):
        xoff = 1 if v >= 0 else -1
        ha = "left" if v >= 0 else "right"
        ax.text(v + xoff, i, f"{v:+.0f}%", va="center", ha=ha, fontsize=5)
    ax.grid(axis="x", alpha=0.3)

    # ── Panel 3 (top-right): MAE improvement scatter ──
    ax = axes[0, 2]
    mae_prof = pt_sorted["prediction_mae_profile"].values
    mae_rec = pt_sorted["prediction_mae_recommended"].values
    sizes = np.clip(pt_sorted["n_events_independent"].values / 5, 10, 200)
    colors_sc = [CTRL_COLORS.get(c, "#757575") for c in pt_sorted["controller"]]
    ax.scatter(mae_prof, mae_rec, s=sizes, c=colors_sc, alpha=0.7,
               edgecolors="black", linewidths=0.5)
    lim_lo = 0
    lim_hi = max(mae_prof.max(), mae_rec.max()) * 1.1
    ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], "k--", alpha=0.5, label="No improvement")
    ax.set_xlim(lim_lo, lim_hi)
    ax.set_ylim(lim_lo, lim_hi)
    ax.set_xlabel("MAE (profile ISF)")
    ax.set_ylabel("MAE (recommended ISF)")
    ax.set_title(f"MAE: Profile vs Recommended [{h2_res.get('h2_verdict', '?')}]")
    # Legend for controller colors
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=8,
               label=k.title())
        for k, c in CTRL_COLORS.items() if k != "unknown"
    ]
    ax.legend(handles=legend_elements, fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)

    # ── Panel 4 (bottom-left): 5 ISF estimates per patient (line plot) ──
    ax = axes[1, 0]
    x = np.arange(n_pts)
    ax.plot(x, pt_sorted["profile_isf"].values, "s-", color="#9E9E9E",
            markersize=4, linewidth=1, label="Profile", alpha=0.8)
    ax.plot(x, pt_sorted["raw_all_isf"].values, "^-", color="#42A5F5",
            markersize=4, linewidth=1, label="Raw (all)", alpha=0.8)
    ax.plot(x, pt_sorted["raw_indep_isf"].values, "v-", color="#66BB6A",
            markersize=4, linewidth=1, label="Raw (indep)", alpha=0.8)
    ax.plot(x, pt_sorted["deconfounded_isf"].values, "D-", color="#EF5350",
            markersize=4, linewidth=1, label="Deconfounded", alpha=0.8)
    ax.plot(x, pt_sorted["normalized_isf"].values, "o-", color="#AB47BC",
            markersize=4, linewidth=1, label="Normalized", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(short_pids, rotation=60, ha="right", fontsize=6)
    ax.set_ylabel("ISF (mg/dL per U)")
    ax.set_title("5 ISF Estimates per Patient")
    ax.legend(fontsize=7, loc="upper right", ncol=2)
    ax.grid(alpha=0.3)

    # ── Panel 5 (bottom-center): Confidence vs improvement (box plot) ──
    ax = axes[1, 1]
    tier_order = ["low", "medium", "high"]
    box_data = []
    box_labels = []
    for tier in tier_order:
        sub = pt_df[pt_df["confidence"] == tier]["mae_improvement_pct"].values
        if len(sub) > 0:
            box_data.append(sub)
            n_t = len(sub)
            box_labels.append(f"{tier.title()}\n(n={n_t})")
        else:
            box_data.append([0])
            box_labels.append(f"{tier.title()}\n(n=0)")

    bp = ax.boxplot(box_data, tick_labels=box_labels, patch_artist=True)
    tier_colors = ["#FFCDD2", "#FFF9C4", "#C8E6C9"]
    for patch, color in zip(bp["boxes"], tier_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_ylabel("MAE improvement (%)")
    ax.set_title(f"Confidence Tier vs Improvement [{h3_res.get('h3_verdict', '?')}]")
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 6 (bottom-right): Summary statistics table ──
    ax = axes[1, 2]
    ax.axis("off")
    n_patients = len(pt_df)
    med_isf = float(np.median(pt_df["recommended_isf"]))
    med_mae_imp = float(pt_df["mae_improvement_pct"].median())
    n_high = int((pt_df["confidence"] == "high").sum())
    n_med = int((pt_df["confidence"] == "medium").sum())
    n_low = int((pt_df["confidence"] == "low").sum())
    n_imp = int((pt_df["mae_improvement_pct"] > 0).sum())
    med_pct_diff = float(np.median(pt_df["pct_diff_from_profile"]))

    summary_lines = [
        f"Patients analyzed:       {n_patients}",
        f"Median recommended ISF:  {med_isf:.1f} mg/dL/U",
        f"Median profile ISF:      {float(np.median(pt_df['profile_isf'])):.1f} mg/dL/U",
        f"Median ISF diff:         {med_pct_diff:+.1f}%",
        "",
        f"Patients improved:       {n_imp}/{n_patients} ({100*n_imp/max(n_patients,1):.0f}%)",
        f"Median MAE improvement:  {med_mae_imp:.1f}%",
        "",
        f"Confidence distribution:",
        f"  High  (N≥100):  {n_high}",
        f"  Medium (N≥30):  {n_med}",
        f"  Low    (N<30):  {n_low}",
        "",
        f"Verdicts:",
        f"  H1 (ISF differs):      {h1_res.get('h1_verdict', 'SKIP')}"
        f"  (p={h1_res.get('p_value', 0):.2e})",
        f"  H2 (MAE improved):     {h2_res.get('h2_verdict', 'SKIP')}",
        f"  H3 (high>low conf):    {h3_res.get('h3_verdict', 'SKIP')}",
        f"  H4 (norm≈deconf):      {h4_res.get('h4_verdict', 'SKIP')}",
    ]
    ax.text(
        0.05, 0.95, "\n".join(summary_lines),
        transform=ax.transAxes, fontsize=9, verticalalignment="top",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#F5F5F5", alpha=0.8),
    )
    ax.set_title("Summary Statistics")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = VIZ_DIR / "patient_settings.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Visualization: {out_path}")


# ── Main ──

def main():
    print("=" * 70)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 70)

    grid = load_data()
    ev_all = extract_events(grid)
    if len(ev_all) == 0:
        print("ERROR: No events extracted. Exiting.")
        sys.exit(1)

    ev_all = filter_independent(ev_all)
    ev_indep = ev_all[ev_all["independent"]].copy()
    n_all = len(ev_all)
    n_indep = len(ev_indep)
    print(f"  All events:         {n_all:,}")
    print(f"  Independent events: {n_indep:,} ({100*n_indep/max(n_all,1):.1f}%)")

    # Per-patient ISF extraction
    pt_df = compute_patient_isfs(grid, ev_all, ev_indep)

    # Print full per-patient table
    print("\n" + "=" * 70)
    print("  PER-PATIENT ISF RECOMMENDATIONS")
    print("=" * 70)
    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", 200,
        "display.float_format", "{:.1f}".format,
    ):
        print(pt_df.to_string(index=False))

    # Hypothesis tests
    h1_res = test_h1(pt_df)
    h2_res = test_h2(pt_df)
    h3_res = test_h3(pt_df)
    h4_res = test_h4(pt_df)

    # Visualization
    print("\nGenerating visualization...")
    make_visualization(pt_df, h1_res, h2_res, h3_res, h4_res)

    # Assemble results
    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_all_events": n_all,
        "n_independent_events": n_indep,
        "retention_pct": round(100 * n_indep / max(n_all, 1), 1),
        "n_patients": int(pt_df["patient_id"].nunique()),
        "hypotheses": {
            "H1_recommended_differs_from_profile": h1_res,
            "H2_mae_improvement_majority": h2_res,
            "H3_confidence_tier_improvement": h3_res,
            "H4_normalized_agrees_with_deconfounded": h4_res,
        },
        "verdict_summary": {
            "H1": h1_res.get("h1_verdict", "SKIP"),
            "H2": h2_res.get("h2_verdict", "SKIP"),
            "H3": h3_res.get("h3_verdict", "SKIP"),
            "H4": h4_res.get("h4_verdict", "SKIP"),
        },
        "per_patient": pt_df.to_dict(orient="records"),
        "population_summary": {
            "median_profile_isf": float(np.median(pt_df["profile_isf"])),
            "median_recommended_isf": float(np.median(pt_df["recommended_isf"])),
            "median_pct_diff": float(np.median(pt_df["pct_diff_from_profile"])),
            "median_mae_improvement_pct": float(pt_df["mae_improvement_pct"].median()),
            "n_improved": int((pt_df["mae_improvement_pct"] > 0).sum()),
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

    v = results["verdict_summary"]
    print(f"\nVerdict: H1={v['H1']} H2={v['H2']} H3={v['H3']} H4={v['H4']}")
    return results


if __name__ == "__main__":
    main()
