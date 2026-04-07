#!/usr/bin/env python3
"""EXP-601–610: Model improvements, stacking prevention, clinical extensions.

Builds on breakthroughs from EXP-591-600:
1. Counter-regulatory +5.1 bias → implement hypo-corrected model
2. Stacking 3.3× worse → find optimal spacing, IOB-aware corrections
3. Clinical dashboard → cluster-based recs, dawn quantification
"""

import argparse, json, os, sys, warnings
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

SAVE_DIR = Path("externals/experiments")
SAVE_DIR.mkdir(parents=True, exist_ok=True)
PATIENTS_DIR = Path(__file__).parent.parent.parent / "externals" / "ns-data" / "patients"


def _bg_col(df):
    return "glucose" if "glucose" in df.columns else "sgv"


def _compute_flux_and_ar(df, pk, lags=6, reg=1e-6):
    """Compute flux + AR(6). Returns dict with all components."""
    sd = compute_supply_demand(df, pk)
    bg = df[_bg_col(df)].values.astype(float)
    valid = np.isfinite(bg)
    n = len(bg)

    demand = np.array(sd.get("demand", np.zeros(n)))
    supply = np.array(sd.get("supply", np.zeros(n)))
    hepatic = np.array(sd.get("hepatic", np.zeros(n)))
    bg_decay = np.array(sd.get("bg_decay", np.zeros(n)))
    carb_supply = np.array(sd.get("carb_supply", np.zeros(n)))
    net = np.array(sd.get("net", np.zeros(n)))

    flux_pred = demand + supply + hepatic + bg_decay

    # dBG on contiguous valid
    idx_v = np.where(valid)[0]
    bg_v = bg[idx_v]
    dbg_full = np.full(n, np.nan)
    dbg_v = np.diff(bg_v)
    for i in range(len(dbg_v)):
        dbg_full[idx_v[i]] = dbg_v[i]

    # AR residuals
    flux_resid = np.full(n, np.nan)
    for i in range(n):
        if np.isfinite(dbg_full[i]) and np.isfinite(flux_pred[i]):
            flux_resid[i] = dbg_full[i] - flux_pred[i]

    # fit AR(6) on training (first 80%)
    fr = flux_resid.copy()
    n_train = int(0.8 * n)
    rows_X, rows_y = [], []
    for t in range(lags, n_train):
        lag_vals = [fr[t - l] for l in range(1, lags + 1)]
        if all(np.isfinite(lag_vals)) and np.isfinite(fr[t]):
            rows_X.append(lag_vals)
            rows_y.append(fr[t])

    ar_pred = np.full(n, np.nan)
    ar_coef = np.zeros(lags)
    if len(rows_X) > lags + 2:
        X = np.array(rows_X)
        y = np.array(rows_y)
        XtX = X.T @ X + reg * np.eye(lags)
        Xty = X.T @ y
        ar_coef = np.linalg.solve(XtX, Xty)
        for t in range(lags, n):
            lag_vals = [fr[t - l] for l in range(1, lags + 1)]
            if all(np.isfinite(lag_vals)):
                ar_pred[t] = np.sum(ar_coef * lag_vals)

    combined_pred = np.full(n, np.nan)
    for t in range(n):
        if np.isfinite(flux_pred[t]) and np.isfinite(ar_pred[t]):
            combined_pred[t] = flux_pred[t] + ar_pred[t]

    return {
        "bg": bg, "dbg": dbg_full, "flux_pred": flux_pred,
        "ar_pred": ar_pred, "combined_pred": combined_pred,
        "flux_resid": flux_resid, "demand": demand, "supply": supply,
        "hepatic": hepatic, "bg_decay": bg_decay, "valid": valid,
        "sd": sd, "ar_coef": ar_coef, "n_train": n_train,
        "carb_supply": carb_supply, "net": net,
    }


def _r2(actual, predicted, mask=None):
    """Compute R² with optional mask."""
    if mask is None:
        mask = np.isfinite(actual) & np.isfinite(predicted)
    a, p = actual[mask], predicted[mask]
    if len(a) < 10:
        return np.nan
    ss_res = np.sum((a - p) ** 2)
    ss_tot = np.sum((a - np.mean(a)) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else 0


# ── EXP-601: Hypo-corrected model ─────────────────────────────

def exp_601_hypo_corrected(patients, detail=False):
    """Add +5.1 mg/dL counter-regulatory bias correction in hypo range.

    The linear flux model under-predicts BG recovery by +5.1 mg/dL per step
    when BG<70 (EXP-591). Apply a piecewise correction and measure R² improvement.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg, dbg, comb = r["bg"], r["dbg"], r["combined_pred"]

        # Baseline R² in hypo range
        hypo_mask = np.isfinite(dbg) & np.isfinite(comb) & (bg < 70) & np.isfinite(bg)
        r2_baseline_hypo = _r2(dbg, comb, hypo_mask)

        # Patient-specific counter-regulatory bias
        if np.sum(hypo_mask) > 10:
            bias = float(np.mean(dbg[hypo_mask] - comb[hypo_mask]))
        else:
            bias = 5.1  # use population mean

        # Apply piecewise correction
        comb_corrected = comb.copy()
        for t in range(len(bg)):
            if np.isfinite(bg[t]) and bg[t] < 70:
                if np.isfinite(comb_corrected[t]):
                    comb_corrected[t] += bias
            elif np.isfinite(bg[t]) and bg[t] < 80:
                # Gradual transition 70-80
                frac = (80 - bg[t]) / 10
                if np.isfinite(comb_corrected[t]):
                    comb_corrected[t] += bias * frac

        r2_corrected_hypo = _r2(dbg, comb_corrected, hypo_mask)

        # Overall R² change
        all_mask = np.isfinite(dbg) & np.isfinite(comb)
        r2_baseline_all = _r2(dbg, comb, all_mask)
        all_mask2 = np.isfinite(dbg) & np.isfinite(comb_corrected)
        r2_corrected_all = _r2(dbg, comb_corrected, all_mask2)

        # Also test range-dependent corrections for ALL ranges
        range_biases = {}
        ranges = {"hypo": (0, 70), "low": (70, 100), "normal": (100, 180),
                  "high": (180, 250), "very_high": (250, 500)}
        for rname, (lo, hi) in ranges.items():
            rmask = np.isfinite(dbg) & np.isfinite(comb) & (bg >= lo) & (bg < hi) & np.isfinite(bg)
            if np.sum(rmask) > 10:
                range_biases[rname] = round(float(np.mean(dbg[rmask] - comb[rmask])), 3)

        results.append({
            "patient": p["name"],
            "bias_applied": round(bias, 2),
            "r2_hypo_baseline": round(r2_baseline_hypo, 4) if np.isfinite(r2_baseline_hypo) else None,
            "r2_hypo_corrected": round(r2_corrected_hypo, 4) if np.isfinite(r2_corrected_hypo) else None,
            "r2_hypo_improvement": round(r2_corrected_hypo - r2_baseline_hypo, 4)
                if np.isfinite(r2_baseline_hypo) and np.isfinite(r2_corrected_hypo) else None,
            "r2_all_baseline": round(r2_baseline_all, 4),
            "r2_all_corrected": round(r2_corrected_all, 4),
            "range_biases": range_biases,
        })

    improvements = [r["r2_hypo_improvement"] for r in results if r["r2_hypo_improvement"] is not None]
    all_improvements = [r["r2_all_corrected"] - r["r2_all_baseline"] for r in results]
    summary = {
        "mean_hypo_r2_improvement": round(np.mean(improvements), 4) if improvements else None,
        "mean_overall_r2_improvement": round(np.mean(all_improvements), 4),
        "hypo_improved_count": sum(1 for i in improvements if i > 0),
        "n_patients": len(improvements),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: hypo R² {r['r2_hypo_baseline']}→{r['r2_hypo_corrected']} "
                  f"(Δ={r['r2_hypo_improvement']}), overall {r['r2_all_baseline']}→{r['r2_all_corrected']}")

    return {"name": "Hypo-Corrected Model", "id": "EXP-601",
            "summary": summary, "patients": results}


# ── EXP-602: Range-dependent noise Kalman ──────────────────────

def exp_602_heteroscedastic_kalman(patients, detail=False):
    """Scale Kalman R by BG-range noise ratios from EXP-593.

    Noise structure: hypo 1.22×, normal 1.0×, very_high 1.42×.
    A heteroscedastic Kalman should improve by weighting observations
    by their expected noise level.
    """
    # Noise ratios from EXP-593
    noise_ratios = {
        (0, 70): 1.22,
        (70, 100): 1.05,
        (100, 150): 1.00,
        (150, 180): 1.07,
        (180, 250): 1.14,
        (250, 500): 1.42,
    }

    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg, dbg, comb = r["bg"], r["dbg"], r["combined_pred"]
        n = len(bg)

        # Baseline: scalar Kalman with fixed Q/R
        mask = np.isfinite(dbg) & np.isfinite(comb)
        n_train = r["n_train"]

        # Compute innovation variance from training
        innov = dbg[:n_train] - comb[:n_train]
        innov_valid = innov[np.isfinite(innov)]
        if len(innov_valid) < 100:
            continue
        innov_var = float(np.var(innov_valid))
        Q = 0.8 * innov_var
        R = 0.2 * innov_var

        # Run baseline Kalman
        def run_kalman(bg, comb, Q_arr, R_arr):
            x = bg[0] if np.isfinite(bg[0]) else 120.0
            P = innov_var
            preds = np.full(n, np.nan)
            for t in range(1, n):
                # Predict
                if np.isfinite(comb[t]):
                    x_pred = x + comb[t]
                else:
                    x_pred = x
                P_pred = P + Q_arr[t]

                # Update
                if np.isfinite(bg[t]):
                    K = P_pred / (P_pred + R_arr[t])
                    x = x_pred + K * (bg[t] - x_pred)
                    P = (1 - K) * P_pred
                    preds[t] = x_pred
                else:
                    x = x_pred
                    P = P_pred
            return preds

        # Baseline: constant Q/R
        Q_const = np.full(n, Q)
        R_const = np.full(n, R)
        preds_baseline = run_kalman(bg, comb, Q_const, R_const)

        # Heteroscedastic: scale R by BG-range noise
        R_hetero = np.full(n, R)
        for (lo, hi), ratio in noise_ratios.items():
            range_mask = np.isfinite(bg) & (bg >= lo) & (bg < hi)
            R_hetero[range_mask] = R * (ratio ** 2)  # variance scales as square

        preds_hetero = run_kalman(bg, comb, Q_const, R_hetero)

        # Compute skills (out-of-sample only)
        oos = slice(n_train, n)
        bg_oos = bg[oos]
        valid_oos = np.isfinite(bg_oos)

        if np.sum(valid_oos) < 100:
            continue

        def skill(preds):
            p_oos = preds[oos]
            m = valid_oos & np.isfinite(p_oos)
            if np.sum(m) < 50:
                return np.nan
            mse_model = np.mean((bg_oos[m] - p_oos[m]) ** 2)
            mse_persist = np.mean(np.diff(bg_oos[valid_oos]) ** 2)
            return 1 - mse_model / mse_persist if mse_persist > 0 else 0

        skill_baseline = skill(preds_baseline)
        skill_hetero = skill(preds_hetero)

        results.append({
            "patient": p["name"],
            "skill_baseline": round(skill_baseline, 4) if np.isfinite(skill_baseline) else None,
            "skill_hetero": round(skill_hetero, 4) if np.isfinite(skill_hetero) else None,
            "improvement": round(skill_hetero - skill_baseline, 4)
                if np.isfinite(skill_baseline) and np.isfinite(skill_hetero) else None,
        })

    improvements = [r["improvement"] for r in results if r["improvement"] is not None]
    summary = {
        "mean_skill_improvement": round(np.mean(improvements), 4) if improvements else None,
        "improved_count": sum(1 for i in improvements if i > 0),
        "n_patients": len(improvements),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: baseline={r['skill_baseline']}, "
                  f"hetero={r['skill_hetero']}, Δ={r['improvement']}")

    return {"name": "Heteroscedastic Kalman", "id": "EXP-602",
            "summary": summary, "patients": results}


# ── EXP-603: Impaired counter-regulatory detection ────────────

def exp_603_impaired_counter_reg(patients, detail=False):
    """Flag patients with impaired counter-regulatory response.

    Patient i had 51min exit time vs 27min mean (EXP-591).
    Detect patients >2σ above mean exit time — clinical hypo risk flag.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]

        # Find hypo episodes and measure exit times
        exit_times = []
        in_hypo = False
        entry_t = 0
        nadir = 999

        for t in range(len(bg)):
            if not np.isfinite(bg[t]):
                continue
            if bg[t] < 70 and not in_hypo:
                in_hypo = True
                entry_t = t
                nadir = bg[t]
            elif in_hypo:
                nadir = min(nadir, bg[t])
                if bg[t] >= 70:
                    exit_min = (t - entry_t) * 5
                    exit_times.append({
                        "exit_min": exit_min,
                        "nadir": float(nadir),
                        "severity": "severe" if nadir < 54 else "moderate",
                    })
                    in_hypo = False

        if not exit_times:
            results.append({"patient": p["name"], "n_hypos": 0, "mean_exit_min": None,
                           "severe_pct": None, "impaired": None})
            continue

        exits = [e["exit_min"] for e in exit_times]
        severe_exits = [e["exit_min"] for e in exit_times if e["severity"] == "severe"]
        moderate_exits = [e["exit_min"] for e in exit_times if e["severity"] == "moderate"]

        results.append({
            "patient": p["name"],
            "n_hypos": len(exit_times),
            "mean_exit_min": round(float(np.mean(exits)), 1),
            "median_exit_min": round(float(np.median(exits)), 1),
            "p90_exit_min": round(float(np.percentile(exits, 90)), 1),
            "severe_pct": round(len(severe_exits) / len(exit_times) * 100, 1),
            "mean_severe_exit": round(float(np.mean(severe_exits)), 1) if severe_exits else None,
            "mean_moderate_exit": round(float(np.mean(moderate_exits)), 1) if moderate_exits else None,
            "mean_nadir": round(float(np.mean([e["nadir"] for e in exit_times])), 1),
        })

    # Flag impaired: >2σ above mean
    mean_exits = [r["mean_exit_min"] for r in results if r["mean_exit_min"] is not None]
    if mean_exits:
        pop_mean = np.mean(mean_exits)
        pop_std = np.std(mean_exits)
        threshold = pop_mean + 2 * pop_std
        for r in results:
            if r["mean_exit_min"] is not None:
                r["impaired"] = r["mean_exit_min"] > threshold
                r["z_score"] = round((r["mean_exit_min"] - pop_mean) / pop_std, 2) if pop_std > 0 else 0
    else:
        threshold = None

    summary = {
        "population_mean_exit": round(pop_mean, 1) if mean_exits else None,
        "population_std": round(pop_std, 1) if mean_exits else None,
        "threshold_2sigma": round(threshold, 1) if threshold else None,
        "impaired_count": sum(1 for r in results if r.get("impaired")),
        "n_patients": len(mean_exits),
    }

    if detail:
        for r in results:
            flag = "⚠️ IMPAIRED" if r.get("impaired") else ""
            print(f"  {r['patient']}: exit={r['mean_exit_min']}min (z={r.get('z_score','')}), "
                  f"severe={r['severe_pct']}% {flag}")

    return {"name": "Impaired Counter-Regulatory", "id": "EXP-603",
            "summary": summary, "patients": results}


# ── EXP-604: Optimal correction spacing ────────────────────────

def exp_604_correction_spacing(patients, detail=False):
    """Find optimal wait time between corrections.

    From EXP-595: stacking (21%) reduces effectiveness 3.3×.
    What is the ideal spacing between demand spikes for best BG outcome?
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg, demand = r["bg"], r["demand"]

        dem_valid = demand[np.isfinite(demand)]
        if len(dem_valid) < 100:
            continue
        spike_threshold = np.percentile(dem_valid, 95)

        # Find demand spike events
        spikes = np.where(np.isfinite(demand) & (demand > spike_threshold))[0]
        events = []
        if len(spikes) > 0:
            current = [spikes[0]]
            for s in spikes[1:]:
                if s - current[-1] <= 3:
                    current.append(s)
                else:
                    events.append(current[0])  # event start
                    current = [s]
            events.append(current[0])

        # For each pair of consecutive events, measure spacing and outcome
        spacing_outcomes = []
        for i in range(len(events) - 1):
            spacing = (events[i + 1] - events[i]) * 5  # minutes
            t = events[i]
            t_out = t + 24  # 2h outcome
            if t_out < len(bg) and np.isfinite(bg[t]) and np.isfinite(bg[t_out]):
                bg_change = bg[t_out] - bg[t]
                spacing_outcomes.append({
                    "spacing_min": spacing,
                    "bg_change": float(bg_change),
                })

        if not spacing_outcomes:
            continue

        # Bin by spacing
        bins = [(0, 30), (30, 60), (60, 120), (120, 240), (240, 480)]
        bin_results = {}
        for lo, hi in bins:
            in_bin = [s for s in spacing_outcomes if lo <= s["spacing_min"] < hi]
            if in_bin:
                bin_results[f"{lo}-{hi}min"] = {
                    "count": len(in_bin),
                    "mean_bg_change": round(float(np.mean([s["bg_change"] for s in in_bin])), 1),
                }

        # Find optimal spacing (most negative BG change = best correction)
        best_bin = min(bin_results.items(), key=lambda x: x[1]["mean_bg_change"])

        results.append({
            "patient": p["name"],
            "n_event_pairs": len(spacing_outcomes),
            "bins": bin_results,
            "best_spacing": best_bin[0],
            "best_bg_change": best_bin[1]["mean_bg_change"],
        })

    # Population summary
    best_spacings = [r["best_spacing"] for r in results]
    summary = {
        "most_common_best": max(set(best_spacings), key=best_spacings.count) if best_spacings else None,
        "n_patients": len(results),
    }

    # Aggregate across patients by bin
    all_bins = {}
    for r in results:
        for bname, bdata in r["bins"].items():
            if bname not in all_bins:
                all_bins[bname] = []
            all_bins[bname].append(bdata["mean_bg_change"])
    summary["population_bins"] = {k: round(np.mean(v), 1) for k, v in sorted(all_bins.items())}

    if detail:
        for r in results:
            print(f"  {r['patient']}: best={r['best_spacing']} (ΔBG={r['best_bg_change']})")
        print(f"\n  Population bins: {summary['population_bins']}")

    return {"name": "Optimal Correction Spacing", "id": "EXP-604",
            "summary": summary, "patients": results}


# ── EXP-605: IOB-aware correction effectiveness ───────────────

def exp_605_iob_correction(patients, detail=False):
    """IOB at correction time predicts correction success.

    If IOB is already high when a correction is attempted, the correction
    is more likely to fail (insulin stacking). Use the IOB column from
    devicestatus to measure this.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue

        # Check for IOB column
        if "iob" not in df.columns:
            continue

        r = _compute_flux_and_ar(df, pk)
        bg, demand = r["bg"], r["demand"]
        iob = df["iob"].values.astype(float)

        dem_valid = demand[np.isfinite(demand)]
        if len(dem_valid) < 100:
            continue
        dem_p80 = np.percentile(dem_valid, 80)

        # Find correction events: high BG + high demand
        corrections = []
        t = 0
        while t < len(bg) - 24:
            if (np.isfinite(bg[t]) and bg[t] > 160 and
                np.isfinite(demand[t]) and demand[t] > dem_p80 and
                np.isfinite(iob[t])):
                bg_start = bg[t]
                bg_2h = bg[t + 24] if t + 24 < len(bg) and np.isfinite(bg[t + 24]) else None
                if bg_2h is not None:
                    success = bg_2h < 150
                    corrections.append({
                        "iob": float(iob[t]),
                        "bg_start": float(bg_start),
                        "bg_2h": float(bg_2h),
                        "bg_change": float(bg_2h - bg_start),
                        "success": success,
                    })
                t += 24
            else:
                t += 1

        if len(corrections) < 10:
            continue

        # Split by IOB median
        iobs = [c["iob"] for c in corrections]
        iob_median = np.median(iobs)

        low_iob = [c for c in corrections if c["iob"] <= iob_median]
        high_iob = [c for c in corrections if c["iob"] > iob_median]

        low_success = np.mean([c["success"] for c in low_iob]) if low_iob else None
        high_success = np.mean([c["success"] for c in high_iob]) if high_iob else None
        low_bg_change = np.mean([c["bg_change"] for c in low_iob]) if low_iob else None
        high_bg_change = np.mean([c["bg_change"] for c in high_iob]) if high_iob else None

        # Correlation between IOB and correction outcome
        iob_arr = np.array([c["iob"] for c in corrections])
        bg_change_arr = np.array([c["bg_change"] for c in corrections])
        if np.std(iob_arr) > 0 and np.std(bg_change_arr) > 0:
            corr = np.corrcoef(iob_arr, bg_change_arr)[0, 1]
        else:
            corr = 0

        results.append({
            "patient": p["name"],
            "n_corrections": len(corrections),
            "iob_median": round(float(iob_median), 2),
            "low_iob_success_rate": round(float(low_success * 100), 1) if low_success is not None else None,
            "high_iob_success_rate": round(float(high_success * 100), 1) if high_success is not None else None,
            "low_iob_bg_change": round(float(low_bg_change), 1) if low_bg_change is not None else None,
            "high_iob_bg_change": round(float(high_bg_change), 1) if high_bg_change is not None else None,
            "iob_bg_correlation": round(float(corr), 3),
        })

    success_diffs = [(r["low_iob_success_rate"] - r["high_iob_success_rate"])
                     for r in results
                     if r["low_iob_success_rate"] is not None and r["high_iob_success_rate"] is not None]

    summary = {
        "mean_success_diff_low_vs_high": round(np.mean(success_diffs), 1) if success_diffs else None,
        "low_iob_better": sum(1 for d in success_diffs if d > 0),
        "mean_iob_bg_corr": round(np.mean([r["iob_bg_correlation"] for r in results]), 3) if results else None,
        "n_patients": len(results),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: IOB_med={r['iob_median']}, "
                  f"low_success={r['low_iob_success_rate']}%, "
                  f"high_success={r['high_iob_success_rate']}%, "
                  f"r(IOB,ΔBG)={r['iob_bg_correlation']}")

    return {"name": "IOB-Aware Correction", "id": "EXP-605",
            "summary": summary, "patients": results}


# ── EXP-606: Cluster-based setting similarity ─────────────────

def exp_606_cluster_settings(patients, detail=False):
    """Compare settings within vs across clusters from EXP-599.

    Clusters: 0=(a,b,c,e,f,i), 1=(d,k), 2=(g,h,j).
    If patients in same cluster have similar settings, cluster membership
    can guide settings recommendations.
    """
    clusters = {
        "a": 0, "b": 0, "c": 0, "e": 0, "f": 0, "i": 0,
        "d": 1, "k": 1,
        "g": 2, "h": 2, "j": 2,
    }

    patient_settings = []
    for p in patients:
        df = p["df"]
        name = p["name"]
        if name not in clusters:
            continue

        # Extract settings
        isf_entries = df.attrs.get("isf_schedule", [])
        cr_entries = df.attrs.get("cr_schedule", [])
        basal_entries = df.attrs.get("basal_schedule", [])

        def mean_val(entries):
            if isinstance(entries, list) and entries:
                vals = [e["value"] for e in entries if "value" in e]
                return float(np.mean(vals)) if vals else None
            return None

        isf = mean_val(isf_entries)
        cr = mean_val(cr_entries)
        basal = mean_val(basal_entries)

        # Convert ISF to mg/dL if needed
        if isf is not None and isf < 15:
            isf *= 18.0182

        patient_settings.append({
            "name": name,
            "cluster": clusters[name],
            "isf": round(isf, 1) if isf else None,
            "cr": round(cr, 1) if cr else None,
            "basal": round(basal, 3) if basal else None,
        })

    # Compute within-cluster vs across-cluster variance
    cluster_groups = {}
    for ps in patient_settings:
        c = ps["cluster"]
        if c not in cluster_groups:
            cluster_groups[c] = []
        cluster_groups[c].append(ps)

    # Within-cluster ISF variance vs total
    all_isfs = [ps["isf"] for ps in patient_settings if ps["isf"] is not None]
    within_var = 0
    n_within = 0
    for c, group in cluster_groups.items():
        isfs = [ps["isf"] for ps in group if ps["isf"] is not None]
        if len(isfs) > 1:
            within_var += np.var(isfs) * len(isfs)
            n_within += len(isfs)
    within_var = within_var / n_within if n_within > 0 else 0
    total_var = np.var(all_isfs) if len(all_isfs) > 1 else 0

    results = patient_settings
    summary = {
        "within_cluster_isf_var": round(within_var, 1),
        "total_isf_var": round(total_var, 1),
        "cluster_explains_pct": round((1 - within_var / total_var) * 100, 1) if total_var > 0 else 0,
        "cluster_settings": {str(c): {
            "patients": [ps["name"] for ps in group],
            "mean_isf": round(np.mean([ps["isf"] for ps in group if ps["isf"]]), 1)
                if any(ps["isf"] for ps in group) else None,
            "mean_cr": round(np.mean([ps["cr"] for ps in group if ps["cr"]]), 1)
                if any(ps["cr"] for ps in group) else None,
        } for c, group in cluster_groups.items()},
    }

    if detail:
        for ps in patient_settings:
            print(f"  {ps['name']} (C{ps['cluster']}): ISF={ps['isf']}, CR={ps['cr']}, basal={ps['basal']}")
        print(f"\n  Cluster explains {summary['cluster_explains_pct']}% of ISF variance")

    return {"name": "Cluster Settings Similarity", "id": "EXP-606",
            "summary": summary, "patients": results}


# ── EXP-607: Dawn phenomenon quantification ───────────────────

def exp_607_dawn_phenomenon(patients, detail=False):
    """Quantify dawn phenomenon (04:00-08:00 BG rise) per patient.

    Dawn phenomenon is a well-known clinical effect where BG rises in early
    morning due to growth hormone and cortisol. Measure the net BG change
    04:00-08:00 relative to other 4-hour periods.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"]
        carb_supply = r["carb_supply"]

        if hasattr(df.index, 'hour'):
            hours = df.index.hour.values
        else:
            hours = np.array([(t * 5 // 60) % 24 for t in range(len(bg))])

        # Compute mean BG change in each 4-hour period
        periods = {
            "00-04": (0, 4), "04-08 (dawn)": (4, 8), "08-12": (8, 12),
            "12-16": (12, 16), "16-20": (16, 20), "20-24": (20, 24),
        }

        period_changes = {}
        for pname, (h_start, h_end) in periods.items():
            mask = (hours >= h_start) & (hours < h_end) & np.isfinite(bg)
            # Also filter for low carb supply (fasting-ish)
            cs_mask = mask & (carb_supply < 0.5)

            if np.sum(cs_mask) < 50:
                # Fall back to all data in period
                cs_mask = mask

            bg_in_period = bg[cs_mask]
            if len(bg_in_period) > 10:
                # Mean rate of BG change in this period
                dbg_period = np.diff(bg_in_period)
                period_changes[pname] = {
                    "mean_dbg": round(float(np.mean(dbg_period)), 3),
                    "mean_bg": round(float(np.mean(bg_in_period)), 1),
                    "n": int(len(bg_in_period)),
                }

        dawn_change = period_changes.get("04-08 (dawn)", {}).get("mean_dbg")
        other_changes = [v["mean_dbg"] for k, v in period_changes.items()
                        if k != "04-08 (dawn)" and v is not None]
        mean_other = float(np.mean(other_changes)) if other_changes else None

        dawn_excess = (dawn_change - mean_other) if dawn_change is not None and mean_other is not None else None

        results.append({
            "patient": p["name"],
            "dawn_dbg": round(dawn_change, 3) if dawn_change is not None else None,
            "mean_other_dbg": round(mean_other, 3) if mean_other is not None else None,
            "dawn_excess": round(dawn_excess, 3) if dawn_excess is not None else None,
            "dawn_bg": period_changes.get("04-08 (dawn)", {}).get("mean_bg"),
            "periods": period_changes,
        })

    dawn_excesses = [r["dawn_excess"] for r in results if r["dawn_excess"] is not None]
    summary = {
        "mean_dawn_excess": round(np.mean(dawn_excesses), 3) if dawn_excesses else None,
        "dawn_positive_count": sum(1 for d in dawn_excesses if d > 0),
        "n_patients": len(dawn_excesses),
    }

    if detail:
        for r in results:
            flag = "↑" if r["dawn_excess"] and r["dawn_excess"] > 0 else "↓"
            print(f"  {r['patient']}: dawn_dbg={r['dawn_dbg']}, excess={r['dawn_excess']} {flag}")

    return {"name": "Dawn Phenomenon", "id": "EXP-607",
            "summary": summary, "patients": results}


# ── EXP-608: Missing data tolerance ───────────────────────────

def exp_608_missing_data(patients, detail=False):
    """Test score robustness with artificial data gaps.

    Insert 10%, 20%, 30% random gaps and measure score stability.
    """
    results = []
    gap_rates = [0.0, 0.10, 0.20, 0.30, 0.40]

    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg = r["bg"].copy()

        # Compute baseline score (TIR + CV proxy)
        bg_valid = bg[np.isfinite(bg)]
        if len(bg_valid) < 1000:
            continue

        def mini_score(bg_arr):
            bv = bg_arr[np.isfinite(bg_arr)]
            if len(bv) < 100:
                return np.nan
            tir = np.mean((bv >= 70) & (bv <= 180)) * 100
            cv = np.std(bv) / np.mean(bv) * 100
            s_tir = min(100, tir / 0.70)
            s_cv = max(0, 100 - (cv - 20) * 3)
            return 0.6 * s_tir + 0.4 * s_cv

        baseline_score = mini_score(bg)

        gap_scores = {}
        for rate in gap_rates:
            scores = []
            for _ in range(5):  # 5 random gap patterns
                bg_gap = bg.copy()
                n_gap = int(len(bg_gap) * rate)
                gap_indices = np.random.choice(len(bg_gap), n_gap, replace=False)
                bg_gap[gap_indices] = np.nan
                scores.append(mini_score(bg_gap))
            valid_scores = [s for s in scores if np.isfinite(s)]
            if valid_scores:
                gap_scores[f"{int(rate*100)}%"] = {
                    "mean_score": round(float(np.mean(valid_scores)), 1),
                    "std": round(float(np.std(valid_scores)), 1),
                    "deviation_from_baseline": round(float(np.mean(valid_scores) - baseline_score), 1),
                }

        results.append({
            "patient": p["name"],
            "baseline_score": round(baseline_score, 1),
            "gap_scores": gap_scores,
        })

    # Summarize
    summary = {}
    for rate_str in ["0%", "10%", "20%", "30%", "40%"]:
        devs = [r["gap_scores"].get(rate_str, {}).get("deviation_from_baseline", 0)
                for r in results if rate_str in r["gap_scores"]]
        if devs:
            summary[rate_str] = {
                "mean_deviation": round(np.mean(devs), 1),
                "max_deviation": round(max(abs(d) for d in devs), 1),
            }

    if detail:
        for r in results:
            deviations = [f"{k}:Δ={v['deviation_from_baseline']}" for k, v in r["gap_scores"].items()]
            print(f"  {r['patient']}: baseline={r['baseline_score']}, {', '.join(deviations)}")

    return {"name": "Missing Data Tolerance", "id": "EXP-608",
            "summary": summary, "patients": results}


# ── EXP-609: Sensor age effect on residuals ───────────────────

def exp_609_sensor_age(patients, detail=False):
    """Detect sensor degradation from residual statistics over sensor session.

    Use sage_hours (sensor age in hours) column if available.
    Compare residual variance in fresh vs aged sensor periods.
    """
    results = []
    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue

        r = _compute_flux_and_ar(df, pk)
        residuals = r["dbg"] - r["combined_pred"]

        # Check for sage_hours column
        if "sage_hours" in df.columns:
            sage = df["sage_hours"].values.astype(float)
        else:
            # Proxy: split data into thirds chronologically
            sage = np.linspace(0, 240, len(residuals))

        # Bin by sensor age
        age_bins = [(0, 24), (24, 72), (72, 168), (168, 336)]  # hours
        age_results = {}
        for lo, hi in age_bins:
            mask = (sage >= lo) & (sage < hi) & np.isfinite(residuals)
            if np.sum(mask) < 50:
                continue
            res_bin = residuals[mask]
            age_results[f"{lo}-{hi}h"] = {
                "n": int(np.sum(mask)),
                "std": round(float(np.std(res_bin)), 3),
                "mean": round(float(np.mean(res_bin)), 3),
                "abs_mean": round(float(np.mean(np.abs(res_bin))), 3),
            }

        # Trend: does std increase with age?
        if len(age_results) >= 2:
            stds = [v["std"] for v in age_results.values()]
            trend = (stds[-1] - stds[0]) / stds[0] * 100 if stds[0] > 0 else 0
        else:
            trend = None

        results.append({
            "patient": p["name"],
            "has_sage": "sage_hours" in df.columns,
            "age_bins": age_results,
            "degradation_trend_pct": round(trend, 1) if trend is not None else None,
        })

    trends = [r["degradation_trend_pct"] for r in results if r["degradation_trend_pct"] is not None]
    summary = {
        "mean_degradation_trend": round(np.mean(trends), 1) if trends else None,
        "degrading_count": sum(1 for t in trends if t > 5),
        "n_patients": len(trends),
        "has_sage_data": sum(1 for r in results if r["has_sage"]),
    }

    if detail:
        for r in results:
            sage_str = "SAGE" if r["has_sage"] else "proxy"
            print(f"  {r['patient']} ({sage_str}): trend={r['degradation_trend_pct']}%")

    return {"name": "Sensor Age Effect", "id": "EXP-609",
            "summary": summary, "patients": results}


# ── EXP-610: Full piecewise model (all ranges corrected) ──────

def exp_610_piecewise_model(patients, detail=False):
    """Apply range-specific bias corrections across ALL BG ranges.

    Generalization of EXP-601: instead of just hypo correction,
    learn and apply bias for each BG range. Measure total R² improvement.
    """
    results = []
    ranges = [(0, 70), (70, 100), (100, 150), (150, 180), (180, 250), (250, 500)]

    for p in patients:
        df, pk = p["df"], p.get("pk")
        if pk is None:
            continue
        r = _compute_flux_and_ar(df, pk)
        bg, dbg, comb = r["bg"], r["dbg"], r["combined_pred"]
        n = len(bg)
        n_train = r["n_train"]

        # Learn range-specific biases from TRAINING data only
        range_biases = {}
        for lo, hi in ranges:
            train_mask = (np.arange(n) < n_train) & np.isfinite(dbg) & np.isfinite(comb) & np.isfinite(bg) & (bg >= lo) & (bg < hi)
            if np.sum(train_mask) > 20:
                range_biases[(lo, hi)] = float(np.mean(dbg[train_mask] - comb[train_mask]))
            else:
                range_biases[(lo, hi)] = 0.0

        # Apply piecewise correction
        comb_pw = comb.copy()
        for t in range(n):
            if not np.isfinite(bg[t]) or not np.isfinite(comb_pw[t]):
                continue
            for (lo, hi), bias in range_biases.items():
                if lo <= bg[t] < hi:
                    comb_pw[t] += bias
                    break

        # Evaluate on TEST data only
        test_mask = (np.arange(n) >= n_train) & np.isfinite(dbg)

        r2_baseline = _r2(dbg, comb, test_mask & np.isfinite(comb))
        r2_piecewise = _r2(dbg, comb_pw, test_mask & np.isfinite(comb_pw))

        # Per-range test R²
        range_r2 = {}
        for lo, hi in ranges:
            rmask = test_mask & np.isfinite(comb) & (bg >= lo) & (bg < hi)
            rmask_pw = test_mask & np.isfinite(comb_pw) & (bg >= lo) & (bg < hi)
            if np.sum(rmask) > 20:
                r2_base = _r2(dbg, comb, rmask)
                r2_pw = _r2(dbg, comb_pw, rmask_pw)
                range_r2[f"{lo}-{hi}"] = {
                    "r2_baseline": round(r2_base, 4) if np.isfinite(r2_base) else None,
                    "r2_piecewise": round(r2_pw, 4) if np.isfinite(r2_pw) else None,
                    "bias": round(range_biases[(lo, hi)], 3),
                }

        results.append({
            "patient": p["name"],
            "r2_baseline": round(r2_baseline, 4) if np.isfinite(r2_baseline) else None,
            "r2_piecewise": round(r2_piecewise, 4) if np.isfinite(r2_piecewise) else None,
            "improvement": round(r2_piecewise - r2_baseline, 4)
                if np.isfinite(r2_baseline) and np.isfinite(r2_piecewise) else None,
            "range_biases": {f"{lo}-{hi}": round(b, 3) for (lo, hi), b in range_biases.items()},
            "range_r2": range_r2,
        })

    improvements = [r["improvement"] for r in results if r["improvement"] is not None]
    summary = {
        "mean_r2_improvement": round(np.mean(improvements), 4) if improvements else None,
        "improved_count": sum(1 for i in improvements if i > 0),
        "n_patients": len(improvements),
    }

    if detail:
        for r in results:
            print(f"  {r['patient']}: R² {r['r2_baseline']}→{r['r2_piecewise']} "
                  f"(Δ={r['improvement']})")
            if r["range_biases"]:
                biases_str = ", ".join(f"{k}:{v}" for k, v in r["range_biases"].items())
                print(f"    biases: {biases_str}")

    return {"name": "Piecewise Range-Corrected Model", "id": "EXP-610",
            "summary": summary, "patients": results}


# ── main ──────────────────────────────────────────────────────

ALL_EXPERIMENTS = [
    ("EXP-601", exp_601_hypo_corrected),
    ("EXP-602", exp_602_heteroscedastic_kalman),
    ("EXP-603", exp_603_impaired_counter_reg),
    ("EXP-604", exp_604_correction_spacing),
    ("EXP-605", exp_605_iob_correction),
    ("EXP-606", exp_606_cluster_settings),
    ("EXP-607", exp_607_dawn_phenomenon),
    ("EXP-608", exp_608_missing_data),
    ("EXP-609", exp_609_sensor_age),
    ("EXP-610", exp_610_piecewise_model),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--max-patients", type=int, default=11)
    ap.add_argument("--exp", type=str, help="Run single experiment, e.g. EXP-601")
    args = ap.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients\n")

    experiments = ALL_EXPERIMENTS
    if args.exp:
        experiments = [(eid, fn) for eid, fn in ALL_EXPERIMENTS if eid == args.exp]
        if not experiments:
            print(f"Unknown experiment: {args.exp}")
            return

    for exp_id, exp_fn in experiments:
        print(f"{'='*60}")
        print(f"Running {exp_id}: {exp_fn.__doc__.split(chr(10))[0] if exp_fn.__doc__ else ''}")
        print(f"{'='*60}")

        try:
            result = exp_fn(patients, detail=args.detail)
            print(f"\nSummary: {json.dumps(result['summary'], indent=2, default=str)}")

            if args.save:
                safe_name = result["name"].lower().replace(" ", "_").replace("/", "_").replace("-", "_")[:30]
                fname = SAVE_DIR / f"{exp_id.lower()}_{safe_name}.json"
                with open(fname, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"Saved → {fname}")

        except Exception as e:
            import traceback
            print(f"ERROR in {exp_id}: {e}")
            traceback.print_exc()

        print()


if __name__ == "__main__":
    main()
