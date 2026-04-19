#!/usr/bin/env python3
"""EXP-2636: Dose-Dependent ISF — Does Bolus Size Inflate Effective ISF?

BUILDS ON:
  - EXP-2635: Bolus size is the ONLY significant predictor of recovery (r=-0.307)
  - EXP-2634: ALL 5 recovery models have negative R² — no single model works
  - EXP-2624: Nadir at ~3.5h, recovery ~16.8 mg/dL/hr (N=212/219 events)
  - EXP-2541: DIA=6h confirmed for 16/19 patients

QUESTION: Larger boluses lead to SLOWER recovery (r=-0.31). This implies that
effective ISF is dose-dependent — a 3U correction has more residual IOB at nadir
than a 1U correction, so the apparent ISF (total drop / bolus) changes with dose.
Can we quantify this and use it to improve correction dosing?

METHODOLOGY: Uses EXACT EXP-2624 correction detection (same as EXP-2634).
  For each correction event, computes:
  - Apparent ISF = total_drop / bolus_size (what actually happened)
  - Scheduled ISF = from patient settings
  - Effective ISF ratio = apparent / scheduled
  - IOB at nadir = remaining insulin at nadir time

HYPOTHESES:
  H1: Large corrections (>2U) have ISF inflated >20% vs small (<1U)
      Rationale: More residual insulin at nadir → ongoing glucose lowering →
      apparent total drop is larger per unit than expected.
  H2: Apparent ISF correlates with bolus size (r > 0.2, positive)
      Rationale: Larger boluses → more total drop per unit (non-linear).
  H3: IOB at nadir explains ISF inflation better than bolus size alone
      Rationale: IOB at nadir is the MECHANISTIC variable — bolus size is
      just a proxy for how much insulin remains at 3.5h.
  H4: Dose-adjusted ISF reduces forward sim RMSE by >10%
      Rationale: If we scale ISF by dose, predictions should improve because
      we're accounting for residual insulin effects.
"""
import argparse
import json, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = ROOT / "externals" / "experiments" / "exp-2636_dose_dependent_isf.json"

STEPS_PER_HOUR = 12
MIN_BOLUS_U = 0.5
MAX_CARBS_WINDOW_G = 2.0
PRE_WINDOW_STEPS = 6
POST_WINDOW_STEPS = 72
NADIR_SEARCH_STEPS = 48
RECOVERY_FIT_STEPS = 24
MIN_DROP_MGDL = 10
STACKING_WINDOW = 72  # 6h at 5-min steps (Nyquist: ≥DIA=6h)

DIA_MIN = 360
PEAK_MIN = 75


def _exponential_iob(t_min, dia=DIA_MIN, peak=PEAK_MIN):
    if t_min <= 0:
        return 1.0
    if t_min >= dia:
        return 0.0
    tau = peak * (1 - peak / dia) / (1 - 2 * peak / dia)
    a = 2 * tau / dia
    S = 1 / (1 - a + (1 + a) * np.exp(-dia / tau))
    iob_frac = 1 - S * (1 - a) * (
        (t_min**2 / (tau * dia * (1 - a)) - t_min / tau - 1) * np.exp(-t_min / tau) + 1
    )
    return max(0, min(1, iob_frac))


def _extract_corrections(pdf):
    """Extract correction events using EXACT EXP-2624 methodology."""
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    # Get scheduled ISF
    sched_isf = pdf["scheduled_isf"].fillna(0).values.astype(np.float64) if "scheduled_isf" in pdf.columns else np.full(len(glucose), np.nan)
    n = len(glucose)
    events = []

    for i in range(PRE_WINDOW_STEPS, n - POST_WINDOW_STEPS):
        if bolus[i] < MIN_BOLUS_U:
            continue
        carb_window = carbs[max(0, i - 12):min(n, i + 12)]
        if np.nansum(carb_window) > MAX_CARBS_WINDOW_G:
            continue
        prior_bolus = bolus[max(0, i - STACKING_WINDOW):i]
        if np.nansum(prior_bolus) > 0.1:
            continue
        pre_window = glucose[i - PRE_WINDOW_STEPS:i]
        valid_pre = ~np.isnan(pre_window)
        if valid_pre.sum() < 3:
            continue
        pre_bg = float(np.nanmean(pre_window))
        if pre_bg < 120:
            continue

        post = glucose[i:i + POST_WINDOW_STEPS].copy()
        valid_post = ~np.isnan(post)
        if valid_post.sum() < POST_WINDOW_STEPS // 2:
            continue

        smoothed = pd.Series(post).rolling(3, center=True, min_periods=1).mean().values
        nadir_search = smoothed[:NADIR_SEARCH_STEPS]
        valid_nadir = ~np.isnan(nadir_search)
        if valid_nadir.sum() < 6:
            continue

        nadir_idx = int(np.nanargmin(nadir_search))
        nadir_bg = float(nadir_search[nadir_idx])
        drop = pre_bg - nadir_bg
        if drop < MIN_DROP_MGDL:
            continue

        bolus_u = float(bolus[i])
        iob_at_corr = float(iob[i]) if not np.isnan(iob[i]) else 0.0

        # Compute IOB from the bolus at nadir time
        nadir_time_min = nadir_idx * 5
        iob_frac_at_nadir = _exponential_iob(nadir_time_min)
        bolus_iob_at_nadir = bolus_u * iob_frac_at_nadir

        # Total reported IOB at nadir
        iob_at_nadir = float(iob[i + nadir_idx]) if (i + nadir_idx < n and not np.isnan(iob[i + nadir_idx])) else np.nan

        # Apparent ISF = drop / bolus (what we observe)
        apparent_isf = drop / bolus_u

        # Scheduled ISF at correction time
        s_isf = float(sched_isf[i]) if not np.isnan(sched_isf[i]) else np.nan

        # Recovery slope (2h post-nadir)
        rec_start = nadir_idx
        rec_end = min(nadir_idx + RECOVERY_FIT_STEPS, len(post))
        rec_seg = post[rec_start:rec_end]
        rec_valid = ~np.isnan(rec_seg)
        if rec_valid.sum() >= 6:
            t_rec = np.arange(rec_valid.sum()) * 5.0 / 60.0
            recovery_slope = float(sp_stats.linregress(t_rec, rec_seg[rec_valid]).slope)
        else:
            recovery_slope = np.nan

        # 6h glucose at end
        bg_6h = float(np.nanmean(post[60:72])) if np.sum(~np.isnan(post[60:72])) >= 3 else np.nan

        events.append({
            "index": int(i),
            "pre_bg": round(pre_bg, 1),
            "nadir_bg": round(nadir_bg, 1),
            "drop": round(drop, 1),
            "bolus_u": round(bolus_u, 2),
            "nadir_time_h": round(nadir_idx / STEPS_PER_HOUR, 2),
            "apparent_isf": round(apparent_isf, 1),
            "scheduled_isf": round(s_isf, 1) if not np.isnan(s_isf) else None,
            "iob_at_correction": round(iob_at_corr, 2),
            "bolus_iob_at_nadir": round(bolus_iob_at_nadir, 3),
            "total_iob_at_nadir": round(iob_at_nadir, 2) if not np.isnan(iob_at_nadir) else None,
            "recovery_slope": round(recovery_slope, 1) if not np.isnan(recovery_slope) else None,
            "bg_6h": round(bg_6h, 1) if not np.isnan(bg_6h) else None,
        })

    return events


def _safe_pearsonr(x, y):
    """Pearson r with NaN/Inf filtering."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3 or np.std(x[mask]) < 1e-12 or np.std(y[mask]) < 1e-12:
        return np.nan, np.nan
    return sp_stats.pearsonr(x[mask], y[mask])


def _safe_linregress(x, y):
    """linregress with NaN/Inf filtering."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3:
        from types import SimpleNamespace
        return SimpleNamespace(slope=np.nan, intercept=np.nan, rvalue=np.nan,
                               pvalue=np.nan, stderr=np.nan)
    return sp_stats.linregress(x[mask], y[mask])


def main():
    parser = argparse.ArgumentParser(description="EXP-2636: Dose-Dependent ISF")
    parser.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    parquet_path = Path(args.parquet)
    out_path = Path(args.out)

    df = pd.read_parquet(parquet_path)
    patients = sorted(df["patient_id"].unique())

    all_events = []
    per_patient = {}

    for pid in patients:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        events = _extract_corrections(pdf)
        n_days = len(pdf) / (STEPS_PER_HOUR * 24)
        per_day = len(events) / n_days if n_days > 0 else 0

        if events:
            boluses = [e["bolus_u"] for e in events]
            isfs = [e["apparent_isf"] for e in events]
            per_patient[pid] = {
                "n_events": len(events),
                "events_per_day": round(per_day, 2),
                "mean_bolus": round(np.mean(boluses), 2),
                "mean_apparent_isf": round(np.mean(isfs), 1),
            }
            for e in events:
                e["patient_id"] = pid
            all_events.extend(events)

        print(f"  Patient {pid}: {len(events)} corrections ({per_day:.1f}/day)")

    print(f"\nTotal corrections: {len(all_events)}")

    # Extract arrays
    boluses = np.array([e["bolus_u"] for e in all_events])
    drops = np.array([e["drop"] for e in all_events])
    apparent_isfs = np.array([e["apparent_isf"] for e in all_events])
    nadir_times = np.array([e["nadir_time_h"] for e in all_events])
    bolus_iob_nadir = np.array([e["bolus_iob_at_nadir"] for e in all_events])
    total_iob_nadir = np.array([e["total_iob_at_nadir"] if e["total_iob_at_nadir"] is not None else np.nan for e in all_events])
    recovery_slopes = np.array([e["recovery_slope"] if e["recovery_slope"] is not None else np.nan for e in all_events])
    scheduled_isfs = np.array([e["scheduled_isf"] if e["scheduled_isf"] is not None else np.nan for e in all_events])

    # --- H1: Large vs small correction ISF inflation ---
    small_mask = boluses < 1.0
    large_mask = boluses >= 2.0
    mid_mask = (~small_mask) & (~large_mask)

    small_isf = apparent_isfs[small_mask]
    large_isf = apparent_isfs[large_mask]
    mid_isf = apparent_isfs[mid_mask]

    h1_inflation = (np.mean(large_isf) / np.mean(small_isf) - 1) * 100 if len(small_isf) > 0 and len(large_isf) > 0 else np.nan
    h1_ttest = sp_stats.ttest_ind(large_isf, small_isf) if len(small_isf) > 2 and len(large_isf) > 2 else None

    print(f"\n=== H1: Dose-dependent ISF ===")
    print(f"  Small (<1U): ISF = {np.mean(small_isf):.1f} ± {np.std(small_isf):.1f} (n={len(small_isf)})")
    print(f"  Medium (1-2U): ISF = {np.mean(mid_isf):.1f} ± {np.std(mid_isf):.1f} (n={len(mid_isf)})")
    print(f"  Large (≥2U): ISF = {np.mean(large_isf):.1f} ± {np.std(large_isf):.1f} (n={len(large_isf)})")
    print(f"  Inflation: {h1_inflation:.1f}%")
    if h1_ttest:
        print(f"  t = {h1_ttest.statistic:.2f}, p = {h1_ttest.pvalue:.4f}")
    h1_pass = not np.isnan(h1_inflation) and h1_inflation > 20
    print(f"  → {'PASS' if h1_pass else 'FAIL'}")

    # --- H2: Bolus size ↔ apparent ISF correlation ---
    r_bolus_isf, p_bolus_isf = _safe_pearsonr(boluses, apparent_isfs)
    print(f"\n=== H2: Bolus ↔ apparent ISF ===")
    print(f"  r = {r_bolus_isf:.3f}, p = {p_bolus_isf:.4f}")
    h2_pass = r_bolus_isf > 0.2
    print(f"  → {'PASS' if h2_pass else 'FAIL'}")

    # --- H3: IOB at nadir vs bolus size as ISF predictor ---
    # Compare: ISF ratio ~ bolus_size  vs  ISF ratio ~ bolus_iob_at_nadir
    valid_sched = ~np.isnan(scheduled_isfs) & (scheduled_isfs > 0)
    if valid_sched.sum() > 10:
        isf_ratio = apparent_isfs[valid_sched] / scheduled_isfs[valid_sched]
        r_bolus_ratio, _ = _safe_pearsonr(boluses[valid_sched], isf_ratio)
        r_iob_ratio, _ = _safe_pearsonr(bolus_iob_nadir[valid_sched], isf_ratio)
        valid_tiob = valid_sched & ~np.isnan(total_iob_nadir)
        if valid_tiob.sum() > 10:
            r_tiob_ratio, _ = _safe_pearsonr(total_iob_nadir[valid_tiob],
                                                  apparent_isfs[valid_tiob] / scheduled_isfs[valid_tiob])
        else:
            r_tiob_ratio = np.nan
    else:
        r_bolus_ratio = r_iob_ratio = r_tiob_ratio = np.nan
        isf_ratio = np.array([])

    print(f"\n=== H3: IOB at nadir vs bolus as ISF predictor ===")
    print(f"  r(bolus → ISF_ratio) = {r_bolus_ratio:.3f}")
    print(f"  r(bolus_IOB_nadir → ISF_ratio) = {r_iob_ratio:.3f}")
    print(f"  r(total_IOB_nadir → ISF_ratio) = {r_tiob_ratio:.3f}")
    h3_pass = not np.isnan(r_iob_ratio) and abs(r_iob_ratio) > abs(r_bolus_ratio)
    print(f"  → {'PASS' if h3_pass else 'FAIL'} (IOB {'>' if h3_pass else '<='} bolus as predictor)")

    # --- H4: Dose-adjusted ISF forward sim ---
    # Simulate predictions with and without dose adjustment
    # Standard: predicted_drop = bolus × scheduled_ISF
    # Dose-adjusted: predicted_drop = bolus × scheduled_ISF × scaling_factor(bolus)
    # where scaling_factor comes from the regression of ISF_ratio ~ bolus_size
    valid_for_sim = valid_sched.copy()
    if valid_for_sim.sum() > 10:
        # Fit linear dose adjustment: ISF_ratio = a + b × bolus
        slope, intercept, _, _, _ = _safe_linregress(boluses[valid_for_sim], isf_ratio)

        # Standard prediction
        std_pred_drop = boluses[valid_for_sim] * scheduled_isfs[valid_for_sim]
        # Dose-adjusted prediction
        adj_scaling = intercept + slope * boluses[valid_for_sim]
        adj_pred_drop = boluses[valid_for_sim] * scheduled_isfs[valid_for_sim] * adj_scaling

        actual_drop = drops[valid_for_sim]

        rmse_std = float(np.sqrt(np.mean((std_pred_drop - actual_drop)**2)))
        rmse_adj = float(np.sqrt(np.mean((adj_pred_drop - actual_drop)**2)))
        improvement = (rmse_std - rmse_adj) / rmse_std * 100

        # Also check: does scheduled ISF just under-predict?
        mean_isf_ratio_val = float(np.mean(isf_ratio))
        median_isf_ratio_val = float(np.median(isf_ratio))
    else:
        rmse_std = rmse_adj = improvement = np.nan
        slope = intercept = np.nan
        mean_isf_ratio_val = median_isf_ratio_val = np.nan

    print(f"\n=== H4: Dose-adjusted ISF prediction ===")
    print(f"  Standard RMSE: {rmse_std:.1f} mg/dL")
    print(f"  Dose-adjusted RMSE: {rmse_adj:.1f} mg/dL")
    print(f"  Improvement: {improvement:.1f}%")
    print(f"  ISF ratio (apparent/scheduled): mean={mean_isf_ratio_val:.2f}, median={median_isf_ratio_val:.2f}")
    print(f"  Dose scaling: ISF_ratio = {intercept:.3f} + {slope:.3f} × bolus_U")
    h4_pass = not np.isnan(improvement) and improvement > 10
    print(f"  → {'PASS' if h4_pass else 'FAIL'}")

    # --- Summary statistics ---
    # Dose-response curve: bin by bolus size
    bins = [(0, 0.75, "<0.75U"), (0.75, 1.25, "0.75-1.25U"), (1.25, 2.0, "1.25-2U"),
            (2.0, 3.0, "2-3U"), (3.0, 100, "≥3U")]
    dose_bins = []
    print(f"\n=== DOSE-RESPONSE CURVE ===")
    for lo, hi, label in bins:
        mask = (boluses >= lo) & (boluses < hi)
        n = mask.sum()
        if n >= 2:
            m_isf = float(np.mean(apparent_isfs[mask]))
            m_drop = float(np.mean(drops[mask]))
            m_rec = float(np.nanmean(recovery_slopes[mask]))
            m_nadir = float(np.mean(nadir_times[mask]))
            dose_bins.append({
                "bin": label, "n": int(n),
                "mean_isf": round(m_isf, 1), "mean_drop": round(m_drop, 1),
                "mean_recovery": round(m_rec, 1), "mean_nadir_h": round(m_nadir, 2),
            })
            print(f"  {label}: n={n}, ISF={m_isf:.1f}, drop={m_drop:.1f}, "
                  f"recovery={m_rec:.1f}, nadir={m_nadir:.2f}h")

    # Build results
    results = {
        "experiment": "EXP-2636",
        "title": "Dose-Dependent ISF — Does Bolus Size Inflate Effective ISF?",
        "methodology": "EXP-2624 exact (bolus≥0.5U, carbs<2g/±1h, no stacking/6h, BG≥120, drop≥10)",
        "n_events": len(all_events),
        "n_patients": len(per_patient),
        "validated_priors": {
            "DIA": "6h (EXP-2541)",
            "nadir": "~3.5h (EXP-2624)",
            "bolus_recovery_r": "-0.307 (EXP-2635)",
            "all_models_fail": "R² < 0 for all 5 models (EXP-2634)",
        },
        "hypotheses": {
            "H1": {
                "statement": "Large corrections (≥2U) have ISF inflated >20% vs small (<1U)",
                "result": "PASS" if h1_pass else "FAIL",
                "small_isf_mean": round(float(np.mean(small_isf)), 1) if len(small_isf) > 0 else None,
                "large_isf_mean": round(float(np.mean(large_isf)), 1) if len(large_isf) > 0 else None,
                "inflation_pct": round(h1_inflation, 1) if not np.isnan(h1_inflation) else None,
                "p_value": round(float(h1_ttest.pvalue), 4) if h1_ttest else None,
                "n_small": int(len(small_isf)),
                "n_large": int(len(large_isf)),
            },
            "H2": {
                "statement": "Apparent ISF correlates with bolus size (r > 0.2)",
                "result": "PASS" if h2_pass else "FAIL",
                "r": round(r_bolus_isf, 3),
                "p_value": round(p_bolus_isf, 4),
            },
            "H3": {
                "statement": "IOB at nadir explains ISF inflation better than bolus size",
                "result": "PASS" if h3_pass else "FAIL",
                "r_bolus_ratio": round(r_bolus_ratio, 3) if not np.isnan(r_bolus_ratio) else None,
                "r_bolus_iob_ratio": round(r_iob_ratio, 3) if not np.isnan(r_iob_ratio) else None,
                "r_total_iob_ratio": round(r_tiob_ratio, 3) if not np.isnan(r_tiob_ratio) else None,
            },
            "H4": {
                "statement": "Dose-adjusted ISF reduces prediction RMSE by >10%",
                "result": "PASS" if h4_pass else "FAIL",
                "rmse_standard": round(rmse_std, 1) if not np.isnan(rmse_std) else None,
                "rmse_adjusted": round(rmse_adj, 1) if not np.isnan(rmse_adj) else None,
                "improvement_pct": round(improvement, 1) if not np.isnan(improvement) else None,
                "scaling_intercept": round(intercept, 3) if not np.isnan(intercept) else None,
                "scaling_slope": round(slope, 3) if not np.isnan(slope) else None,
                "mean_isf_ratio": round(mean_isf_ratio_val, 2) if not np.isnan(mean_isf_ratio_val) else None,
                "median_isf_ratio": round(median_isf_ratio_val, 2) if not np.isnan(median_isf_ratio_val) else None,
            },
        },
        "dose_response": dose_bins,
        "per_patient": per_patient,
        "events": all_events,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {out_path}")


if __name__ == "__main__":
    main()
