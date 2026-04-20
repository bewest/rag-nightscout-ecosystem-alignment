#!/usr/bin/env python3
"""
EXP-2751: Residual Autocorrelation & Multi-Timescale Signal
=============================================================

Scientific Question
-------------------
After our pipeline subtracts known effects (ISF-based BGI, CR-based carb impact,
EGP baseline), do the RESIDUALS contain exploitable structure? If so, what timescales?

This is the key diagnostic for whether we need additional deconfounding factors:
- Autocorrelation at 1-6h → meal absorption tail, insulin activity tail
- Autocorrelation at 6-24h → circadian rhythm, activity patterns
- Autocorrelation at 24-72h → glycogen cycling, illness, stress
- No autocorrelation → residuals are white noise, pipeline is complete

Approach
--------
1. Run simulation pipeline (ISF+CR+EGP) for each patient
2. Compute residuals (actual - simulated glucose)
3. Compute autocorrelation function (ACF) at lags 1-288 (5min to 24h)
4. Identify significant autocorrelation (beyond 95% CI)
5. Spectral analysis to find dominant frequencies

This directly addresses the user's question about multi-timescale deconfounding:
can we subtract more known physics at different timescales?

Predecessors
------------
- EXP-2749: Enhanced pipeline (baseline for residual computation)
- EXP-2714: Autocorrelation structure (earlier, simpler version)
- EXP-2742: EGP personalization

Hypotheses
----------
H1: >80% of patients show significant autocorrelation at lag 1-12 (5-60min)
    → Short-term model mismatch (absorption/insulin kinetics)
H2: >50% show significant autocorrelation at lag 12-72 (1-6h)
    → Medium-term unmodeled factors (extended meal absorption)
H3: >30% show significant autocorrelation at lag 72-288 (6-24h)
    → Circadian/daily patterns
H4: Median first-insignificant lag > 6 steps (30min)
    → Residuals are NOT white noise; pipeline leaves structure
H5: Spectral analysis reveals peak at circadian frequency (period ~288 steps)
    for >30% of patients
"""

from __future__ import annotations
import json, sys, warnings
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import acf

warnings.filterwarnings("ignore")

GRID = Path("externals/ns-parquet/training/grid.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("tools/visualizations/residual-autocorrelation")

# Load pipeline corrections
ISF_CORRECTIONS = Path("externals/experiments/exp-2719b_per_patient_settings.json")
CR_CORRECTIONS = Path("externals/experiments/exp-2741_isf_multifactor.json")
EGP_CORRECTIONS = Path("externals/experiments/exp-2742_cr_multifactor.json")

MAX_LAG = 288  # 24 hours at 5-min resolution
CONFIDENCE_LEVEL = 0.05


def load_data():
    manifest = json.loads(MANIFEST.read_text())
    grid = pd.read_parquet(GRID)
    grid = grid[grid["patient_id"].isin(manifest["qualified_patients"])]

    # Load corrections
    corrections = {}
    if ISF_CORRECTIONS.exists():
        isf_data = json.loads(ISF_CORRECTIONS.read_text())
        for pid, pdata in isf_data.get("per_patient", {}).items():
            corrections.setdefault(pid, {})["isf_correction"] = pdata.get("correction_factor_2h", 1.0)

    if CR_CORRECTIONS.exists():
        cr_data = json.loads(CR_CORRECTIONS.read_text())
        for p in cr_data.get("per_patient", []):
            pid = p.get("patient_id", "")
            if pid and p.get("optimal_cr"):
                corrections.setdefault(pid, {})["optimal_cr"] = p["optimal_cr"]

    return grid, corrections


def compute_patient_residuals(pg: pd.DataFrame, corrections: dict) -> np.ndarray:
    """Compute simple residuals: actual glucose minus predicted from model.

    Rather than running full simulation (slow), we compute a SIMPLE residual:
    residual = glucose[t] - (glucose[t-1] + expected_change)
    where expected_change = -insulin_activity * ISF + carb_absorption * CR_inv

    This gives us the 5-minute innovation residual — what the simple model
    can't explain about each glucose change.
    """
    glucose = pg["glucose"].values
    n = len(glucose)
    residuals = np.full(n, np.nan)

    isf_corr = corrections.get("isf_correction", 1.0) or 1.0
    optimal_cr = corrections.get("optimal_cr")

    for i in range(1, n):
        if np.isnan(glucose[i]) or np.isnan(glucose[i-1]):
            continue

        actual_change = glucose[i] - glucose[i-1]

        # Expected insulin effect
        insulin_effect = 0
        if "insulin_activity" in pg.columns:
            ia = pg.iloc[i].get("insulin_activity", 0) or 0
            isf = (pg.iloc[i].get("scheduled_isf", 50) or 50) * isf_corr
            insulin_effect = -ia * isf * 5 / 60  # per 5-min step

        # Expected carb effect (simple linear absorption over ~3h = 36 steps)
        carb_effect = 0
        # Look back 36 steps for carbs
        lookback = min(i, 36)
        for j in range(lookback):
            c = pg.iloc[i - j].get("carbs", 0) or 0
            if c > 0:
                cr = optimal_cr if optimal_cr else (pg.iloc[i].get("scheduled_cr", 10) or 10)
                # Simple linear absorption: spread over 36 steps
                carb_effect += (c / cr) * (pg.iloc[i].get("scheduled_isf", 50) or 50) * isf_corr / 36

        expected_change = insulin_effect + carb_effect
        residuals[i] = actual_change - expected_change

    return residuals


def compute_simple_residuals(pg: pd.DataFrame) -> np.ndarray:
    """Simpler approach: glucose change residuals after removing trend."""
    glucose = pg["glucose"].values
    changes = np.diff(glucose)
    # Remove rolling mean (trend) to get innovation
    valid = ~np.isnan(changes)
    if valid.sum() < 100:
        return np.array([])

    # Detrend with 12-step (1h) rolling mean
    s = pd.Series(changes)
    trend = s.rolling(12, min_periods=1, center=True).mean()
    residuals = (s - trend).values
    return residuals[~np.isnan(residuals)]


def analyze_autocorrelation(residuals: np.ndarray) -> dict:
    """Compute ACF and identify significant lags."""
    if len(residuals) < MAX_LAG * 2:
        return {"sufficient": False, "n": len(residuals)}

    nlags = min(MAX_LAG, len(residuals) // 2 - 1)
    acf_vals, confint = acf(residuals, nlags=nlags, alpha=CONFIDENCE_LEVEL)

    # Confidence interval width (same for all lags under white noise assumption)
    ci_upper = confint[1:, 1] - acf_vals[1:]  # half-width above
    sig_threshold = ci_upper[0] if len(ci_upper) > 0 else 1.96 / np.sqrt(len(residuals))

    # Find significant lags
    significant = np.abs(acf_vals[1:]) > sig_threshold

    # Short-term (lags 1-12, 5-60min)
    short_sig = significant[:12].sum() if len(significant) >= 12 else 0
    short_frac = short_sig / min(12, len(significant))

    # Medium-term (lags 12-72, 1-6h)
    med_sig = significant[12:72].sum() if len(significant) >= 72 else 0
    med_frac = med_sig / min(60, max(len(significant) - 12, 1))

    # Long-term (lags 72-288, 6-24h)
    long_sig = significant[72:288].sum() if len(significant) >= 288 else 0
    long_frac = long_sig / min(216, max(len(significant) - 72, 1))

    # First insignificant lag
    insig = np.where(~significant)[0]
    first_insig = int(insig[0]) + 1 if len(insig) > 0 else nlags

    # Spectral analysis
    fft = np.fft.rfft(residuals[:min(len(residuals), 2880)])  # Use up to 10 days
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(min(len(residuals), 2880))

    # Find dominant frequency
    # Skip DC component (index 0) and very low frequencies
    if len(power) > 10:
        peak_idx = np.argmax(power[5:]) + 5
        peak_period = 1.0 / freqs[peak_idx] if freqs[peak_idx] > 0 else 0
        has_circadian = 200 < peak_period < 400  # ~288 steps = 24h ± margin
    else:
        peak_period = 0
        has_circadian = False

    return {
        "sufficient": True,
        "n": len(residuals),
        "short_sig_count": int(short_sig),
        "short_sig_frac": float(short_frac),
        "med_sig_count": int(med_sig),
        "med_sig_frac": float(med_frac),
        "long_sig_count": int(long_sig),
        "long_sig_frac": float(long_frac),
        "first_insig_lag": first_insig,
        "first_insig_minutes": first_insig * 5,
        "acf_lag1": float(acf_vals[1]) if len(acf_vals) > 1 else 0,
        "acf_lag12": float(acf_vals[12]) if len(acf_vals) > 12 else 0,
        "acf_lag72": float(acf_vals[72]) if len(acf_vals) > 72 else 0,
        "acf_lag144": float(acf_vals[144]) if len(acf_vals) > 144 else 0,
        "acf_lag288": float(acf_vals[min(288, len(acf_vals)-1)]) if len(acf_vals) > 100 else 0,
        "peak_spectral_period": float(peak_period),
        "has_circadian_peak": has_circadian,
        "sig_threshold": float(sig_threshold),
        "acf_values": acf_vals[:min(nlags+1, 289)].tolist(),
    }


def main():
    print("=" * 70)
    print("EXP-2751: Residual Autocorrelation & Multi-Timescale Signal")
    print("=" * 70)

    grid, corrections = load_data()
    patients = sorted(grid["patient_id"].unique())
    print(f"Loaded {len(patients)} patients, {len(corrections)} with corrections\n")

    results = []
    n_short_sig = 0
    n_med_sig = 0
    n_long_sig = 0
    n_circadian = 0
    first_insigs = []
    n_sufficient = 0

    for pid in patients:
        pg = grid[grid["patient_id"] == pid].sort_values(
            "time" if "time" in grid.columns else grid.columns[0]
        ).reset_index(drop=True)

        corr = corrections.get(pid, {})
        residuals = compute_simple_residuals(pg)

        if len(residuals) < MAX_LAG * 2:
            print(f"  {pid[:16]:<18} n={len(residuals):>6}  INSUFFICIENT")
            results.append({"patient_id": pid, "sufficient": False})
            continue

        analysis = analyze_autocorrelation(residuals)
        analysis["patient_id"] = pid
        results.append(analysis)
        n_sufficient += 1

        has_short = analysis["short_sig_frac"] > 0.5
        has_med = analysis["med_sig_frac"] > 0.3
        has_long = analysis["long_sig_frac"] > 0.2

        if has_short: n_short_sig += 1
        if has_med: n_med_sig += 1
        if has_long: n_long_sig += 1
        if analysis["has_circadian_peak"]: n_circadian += 1
        first_insigs.append(analysis["first_insig_lag"])

        print(f"  {pid[:16]:<18} n={len(residuals):>6}  "
              f"ACF₁={analysis['acf_lag1']:+.3f}  "
              f"ACF₁₂={analysis['acf_lag12']:+.3f}  "
              f"ACF₇₂={analysis['acf_lag72']:+.3f}  "
              f"1st_insig={analysis['first_insig_minutes']:>4}min  "
              f"{'CIRC' if analysis['has_circadian_peak'] else '    '}")

    # Hypotheses
    print(f"\n{'=' * 70}")
    N = max(n_sufficient, 1)

    h1 = n_short_sig / N > 0.8
    h2 = n_med_sig / N > 0.5
    h3 = n_long_sig / N > 0.3
    h4 = np.median(first_insigs) > 6 if first_insigs else False
    h5 = n_circadian / N > 0.3

    passed = sum([h1, h2, h3, h4, h5])
    print(f"HYPOTHESES: {passed}/5 pass (N={n_sufficient} sufficient patients)")

    hypotheses = {
        "H1_short_autocorr": {"passed": bool(h1), "n": n_short_sig, "N": N, "frac": n_short_sig / N},
        "H2_medium_autocorr": {"passed": bool(h2), "n": n_med_sig, "N": N, "frac": n_med_sig / N},
        "H3_long_autocorr": {"passed": bool(h3), "n": n_long_sig, "N": N, "frac": n_long_sig / N},
        "H4_not_white_noise": {"passed": bool(h4), "median_first_insig": float(np.median(first_insigs)) if first_insigs else 0},
        "H5_circadian_spectral": {"passed": bool(h5), "n": n_circadian, "N": N, "frac": n_circadian / N},
    }

    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v:
            print(f"  {tag} {k}: {v['n']}/{v.get('N', N)} ({v.get('frac', 0):.0%})")
        else:
            print(f"  {tag} {k}: median lag = {v.get('median_first_insig', 0):.0f} steps")

    print(f"\n  Median ACF at key lags:")
    suf = [r for r in results if r.get("sufficient")]
    for lag_name, lag_key in [("5min", "acf_lag1"), ("1h", "acf_lag12"),
                               ("6h", "acf_lag72"), ("12h", "acf_lag144"),
                               ("24h", "acf_lag288")]:
        vals = [r[lag_key] for r in suf if lag_key in r]
        if vals:
            print(f"    {lag_name}: {np.median(vals):+.4f}  (range {min(vals):+.4f} to {max(vals):+.4f})")

    print(f"  Median first insignificant lag: {np.median(first_insigs):.0f} steps ({np.median(first_insigs)*5:.0f} min)")

    def clean(obj):
        if isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list): return [clean(v) for v in obj]
        if isinstance(obj, (bool, np.bool_)): return bool(obj)
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        return obj

    out = RESULTS_DIR / "exp-2751_residual_autocorrelation.json"
    with open(out, "w") as f:
        json.dump(clean({
            "exp_id": "EXP-2751",
            "title": "Residual Autocorrelation & Multi-Timescale Signal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": hypotheses,
            "per_patient": results,
        }), f, indent=2)
    print(f"\nSaved: {out}")

    create_dashboard(results, hypotheses)


def create_dashboard(results, hypotheses):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    suf = [r for r in results if r.get("sufficient")]
    if not suf:
        return

    fig = plt.figure(figsize=(18, 14))
    fig.suptitle("EXP-2751: Residual Autocorrelation & Multi-Timescale Signal", fontsize=14, fontweight="bold")
    gs = GridSpec(3, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Panel 1: Mean ACF across all patients
    ax1 = fig.add_subplot(gs[0, :])
    all_acfs = [np.array(r["acf_values"]) for r in suf if r.get("acf_values")]
    if all_acfs:
        min_len = min(len(a) for a in all_acfs)
        acf_matrix = np.array([a[:min_len] for a in all_acfs])
        mean_acf = np.mean(acf_matrix, axis=0)
        q25 = np.percentile(acf_matrix, 25, axis=0)
        q75 = np.percentile(acf_matrix, 75, axis=0)
        lags_min = np.arange(min_len) * 5

        ax1.fill_between(lags_min, q25, q75, alpha=0.3, color="steelblue")
        ax1.plot(lags_min, mean_acf, "b-", lw=2, label="Mean ACF")
        sig = suf[0].get("sig_threshold", 0.05)
        ax1.axhline(sig, color="r", ls="--", lw=1, label=f"95% CI (±{sig:.3f})")
        ax1.axhline(-sig, color="r", ls="--", lw=1)
        ax1.axhline(0, color="gray", ls="-", lw=0.5)
        # Mark timescales
        for t, label in [(60, "1h"), (360, "6h"), (720, "12h"), (1440, "24h")]:
            if t < lags_min[-1]:
                ax1.axvline(t, color="gray", ls=":", lw=0.5)
                ax1.text(t, ax1.get_ylim()[1] * 0.9, label, fontsize=8, ha="center")
        ax1.set_xlabel("Lag (minutes)")
        ax1.set_ylabel("Autocorrelation")
        ax1.set_title("Population Mean ACF of Glucose Residuals")
        ax1.legend()

    # Panel 2: First insignificant lag histogram
    ax2 = fig.add_subplot(gs[1, 0])
    first_insigs = [r["first_insig_lag"] * 5 for r in suf]
    ax2.hist(first_insigs, bins=20, color="steelblue", edgecolor="white")
    ax2.axvline(np.median(first_insigs), color="red", ls="--", lw=2, label=f"Median: {np.median(first_insigs):.0f}min")
    ax2.set_xlabel("First Insignificant Lag (minutes)")
    ax2.set_ylabel("Patients")
    ax2.set_title("How Long is Residual Memory?")
    ax2.legend()

    # Panel 3: ACF at key lags
    ax3 = fig.add_subplot(gs[1, 1])
    lag_keys = [("ACF₁\n(5min)", "acf_lag1"), ("ACF₁₂\n(1h)", "acf_lag12"),
                ("ACF₇₂\n(6h)", "acf_lag72"), ("ACF₁₄₄\n(12h)", "acf_lag144"),
                ("ACF₂₈₈\n(24h)", "acf_lag288")]
    positions = range(len(lag_keys))
    for i, (label, key) in enumerate(lag_keys):
        vals = [r[key] for r in suf if key in r]
        if vals:
            bp = ax3.boxplot(vals, positions=[i], widths=0.6)
    ax3.set_xticks(list(positions))
    ax3.set_xticklabels([l for l, _ in lag_keys], fontsize=8)
    ax3.axhline(0, color="gray", ls="--", lw=0.5)
    ax3.set_ylabel("Autocorrelation")
    ax3.set_title("ACF at Key Timescales")

    # Panel 4: Circadian spectral peak
    ax4 = fig.add_subplot(gs[1, 2])
    periods = [r["peak_spectral_period"] * 5 / 60 for r in suf if r.get("peak_spectral_period", 0) > 0]
    if periods:
        ax4.hist(periods, bins=30, color="steelblue", edgecolor="white")
        ax4.axvline(24, color="red", ls="--", lw=2, label="24h")
        ax4.set_xlabel("Peak Spectral Period (hours)")
        ax4.set_ylabel("Patients")
        ax4.set_title("Dominant Spectral Period")
        ax4.legend()

    # Panel 5: Hypotheses
    ax5 = fig.add_subplot(gs[2, 0])
    ax5.axis("off")
    h_text = "HYPOTHESES\n"
    for k, v in hypotheses.items():
        tag = "✓" if v["passed"] else "✗"
        if "n" in v:
            h_text += f"\n{tag} {k}: {v['n']}/{v.get('N', 22)}"
        else:
            h_text += f"\n{tag} {k}: lag={v.get('median_first_insig', 0):.0f}"
    ax5.text(0.1, 0.9, h_text, transform=ax5.transAxes, fontsize=10,
             va="top", fontfamily="monospace")

    # Panel 6: Interpretation
    ax6 = fig.add_subplot(gs[2, 1:])
    ax6.axis("off")
    txt = """MULTI-TIMESCALE SIGNAL INTERPRETATION

Short-term (5-60min): Insulin/carb kinetics model mismatch
  → Improve absorption curves, insulin activity profiles

Medium-term (1-6h): Extended meal effects, exercise
  → Extended carb absorption model, activity factor

Long-term (6-24h): Circadian rhythm, glycogen state
  → Time-of-day ISF/CR adjustments, dawn phenomenon

Key question: How much residual variance can we still
explain with additional physics-based factors?
"""
    ax6.text(0.02, 0.95, txt.strip(), transform=ax6.transAxes, fontsize=9,
             va="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(VIZ_DIR / "exp-2751-dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {VIZ_DIR / 'exp-2751-dashboard.png'}")


if __name__ == "__main__":
    main()
