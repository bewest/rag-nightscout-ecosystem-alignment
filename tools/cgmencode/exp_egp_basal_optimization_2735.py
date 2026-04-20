"""EXP-2735: EGP-Aware Basal Rate Optimization.

EXP-2730 produced aggressive basal recommendations (median 67 % TDD change)
because fasting glucose drift includes both physiological drift AND controller
compensation effects, plus the continuous glucose supply from Endogenous Glucose
Production (EGP).  This experiment subtracts estimated EGP from drift before
converting to basal adjustments, producing more conservative and physiologically
grounded recommendations.

Predecessors
------------
- EXP-2724  Glucose drift has circadian structure (KW p<1e-38)
- EXP-2730  Drift→basal conversion gives aggressive recs (200-400 % for some)
- EXP-2727  EGP accounts for 42 % of profile→empirical ISF gap
- EXP-2728  Forward simulator supports egp_enabled with Hill equation
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Constants ────────────────────────────────────────────────────────────────

EXP_ID = "2735"
TITLE = "EGP-Aware Basal Optimization — Physiological Basal Recommendations"

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / f"exp-{EXP_ID}_egp_basal.json"
VIZ_DIR = Path("visualizations/egp-basal")

# Time blocks: 6 × 4-hour periods
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

# Window sizes (5-min steps)
FASTING_BOLUS_WINDOW = 24   # 2 h
FASTING_CARB_WINDOW = 36    # 3 h
DRIFT_HORIZON = 12          # 1 h

# ISF extraction parameters (mirrored from EXP-2730)
ISF_INDEPENDENCE_GAP = 24   # 2 h between ISF events
ISF_HORIZON = 24            # 2 h observation window for ISF
ISF_BG_THRESHOLD = 180      # mg/dL
ISF_MIN_DOSE = 0.3          # U

# Safety / filter thresholds
MIN_EVENTS_PER_BLOCK = 5
MIN_ISF = 1.0               # skip patient if ISF < 1
BASAL_CLAMP_LO = 0.05       # U/h safety floor
BASAL_CLAMP_HI = 5.0        # U/h safety ceiling


# ── EGP Estimation ───────────────────────────────────────────────────────────

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from production.metabolic_engine import _compute_hepatic_production

    def estimate_egp(iob: float, hour: float) -> float:
        """Estimate EGP rate in mg/dL per 5-min step (production model)."""
        return float(
            _compute_hepatic_production(np.array([iob]), np.array([hour]))[0]
        )
except ImportError:

    def estimate_egp(iob: float, hour: float) -> float:
        """Simplified EGP model: Hill equation + circadian."""
        EGP_MAX = 1.5   # mg/dL per 5-min at zero IOB
        K_HALF = 2.0    # IOB at which EGP is 50 % suppressed
        HILL_N = 2.0
        # Circadian: EGP ~20 % higher at dawn (4-8 am), lower at midday
        circadian = 1.0 + 0.2 * np.cos(2 * np.pi * (hour - 6) / 24)
        suppression = 1.0 / (1.0 + (max(iob, 0) / K_HALF) ** HILL_N)
        return EGP_MAX * suppression * circadian


# ── Data Loading ─────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load grid data filtered to qualified patients with controller labels."""
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    return grid


# ── Fasting Drift Extraction ────────────────────────────────────────────────

def _extract_drift_events(pdf: pd.DataFrame) -> list:
    """Return fasting-period drift events with EGP estimates for one patient.

    A valid event has no bolus in prior 2 h, no carbs in prior 3 h,
    and valid glucose at both *t* and *t + 1 h*.
    """
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values if "bolus" in pdf.columns else np.zeros(len(pdf))
    carbs = pdf["carbs"].values if "carbs" in pdf.columns else np.zeros(len(pdf))
    iob = pdf["iob"].values if "iob" in pdf.columns else np.zeros(len(pdf))
    times = pdf["time"].values

    # Scheduled basal rate
    if "scheduled_basal_rate" in pdf.columns:
        sched = pdf["scheduled_basal_rate"].values
    elif "actual_basal_rate" in pdf.columns:
        sched = pdf["actual_basal_rate"].values
    elif "net_basal" in pdf.columns:
        sched = pdf["net_basal"].values
    else:
        sched = np.full(len(pdf), np.nan)

    n = len(glucose)
    events = []
    for i in range(FASTING_CARB_WINDOW, n - DRIFT_HORIZON):
        # Valid glucose at both endpoints
        if np.isnan(glucose[i]) or np.isnan(glucose[i + DRIFT_HORIZON]):
            continue

        # No bolus in prior 2 h
        win_bolus = bolus[max(0, i - FASTING_BOLUS_WINDOW + 1): i + 1]
        if np.nansum(win_bolus) > 0:
            continue

        # No carbs in prior 3 h
        win_carbs = carbs[max(0, i - FASTING_CARB_WINDOW + 1): i + 1]
        if np.nansum(win_carbs) > 0:
            continue

        raw_drift = float(glucose[i + DRIFT_HORIZON] - glucose[i])
        hour = pd.Timestamp(times[i]).hour + pd.Timestamp(times[i]).minute / 60.0
        block_idx = int(pd.Timestamp(times[i]).hour) // 4

        # EGP over the 1 h drift period (sum of 12 five-min steps)
        iob_start = float(iob[i]) if not np.isnan(iob[i]) else 0.0
        egp_total = sum(
            estimate_egp(iob_start, hour + step / 12.0) for step in range(DRIFT_HORIZON)
        )
        corrected_drift = raw_drift - egp_total

        events.append({
            "idx": i,
            "hour": round(hour, 2),
            "block_idx": block_idx,
            "block_label": BLOCK_LABELS[block_idx],
            "raw_drift": round(raw_drift, 3),
            "egp_total": round(egp_total, 3),
            "corrected_drift": round(corrected_drift, 3),
            "glucose": float(glucose[i]),
            "iob": round(iob_start, 3),
            "scheduled_basal": float(sched[i]) if not np.isnan(sched[i]) else np.nan,
        })
    return events


def extract_all_drift(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract fasting drift events across all patients."""
    rows = []
    for pid, pdf in grid.groupby("patient_id"):
        evts = _extract_drift_events(pdf)
        for e in evts:
            e["patient_id"] = pid
            rows.append(e)
    if not rows:
        return pd.DataFrame(columns=[
            "patient_id", "idx", "hour", "block_idx", "block_label",
            "raw_drift", "egp_total", "corrected_drift", "glucose",
            "iob", "scheduled_basal",
        ])
    return pd.DataFrame(rows)


# ── ISF Estimation ───────────────────────────────────────────────────────────

def _extract_isf_events(pdf: pd.DataFrame) -> list:
    """Return independent correction-event ISF values for one patient."""
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values if "bolus" in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf["bolus_smb"].values if "bolus_smb" in pdf.columns else np.zeros(len(pdf))
    carbs = pdf["carbs"].values if "carbs" in pdf.columns else np.zeros(len(pdf))

    if "scheduled_basal_rate" in pdf.columns and "actual_basal_rate" in pdf.columns:
        excess_basal = pdf["actual_basal_rate"].values - pdf["scheduled_basal_rate"].values
    elif "net_basal" in pdf.columns:
        excess_basal = pdf["net_basal"].values
    else:
        excess_basal = np.zeros(len(pdf))

    n = len(glucose)
    events = []
    last_accepted_idx = -ISF_INDEPENDENCE_GAP - 1

    for i in range(FASTING_CARB_WINDOW, n - ISF_HORIZON):
        if np.isnan(glucose[i]) or np.isnan(glucose[i + ISF_HORIZON]):
            continue
        if glucose[i] < ISF_BG_THRESHOLD:
            continue

        win_carbs = carbs[max(0, i - FASTING_CARB_WINDOW + 1): i + ISF_HORIZON + 1]
        if np.nansum(win_carbs) > 5:
            continue

        win_bolus = np.nansum(bolus[i: i + ISF_HORIZON + 1])
        win_smb = np.nansum(bolus_smb[i: i + ISF_HORIZON + 1])
        win_excess = np.nansum(
            np.clip(excess_basal[i: i + ISF_HORIZON + 1], 0, None)
        )
        total_insulin = win_bolus + win_smb + (win_excess / 12.0)

        if total_insulin < ISF_MIN_DOSE:
            continue
        if (i - last_accepted_idx) < ISF_INDEPENDENCE_GAP:
            continue
        last_accepted_idx = i

        observed_drop = float(glucose[i] - glucose[i + ISF_HORIZON])
        demand_isf = observed_drop / total_insulin

        if demand_isf > 0:
            events.append({"idx": i, "demand_isf": demand_isf})
    return events


def compute_patient_isf(grid: pd.DataFrame) -> dict:
    """Return {patient_id: median_demand_isf} for each qualified patient."""
    isf_map = {}
    for pid, pdf in grid.groupby("patient_id"):
        evts = _extract_isf_events(pdf)
        if len(evts) >= 3:
            isf_map[pid] = float(np.median([e["demand_isf"] for e in evts]))
    return isf_map


# ── Current Basal Per Block ──────────────────────────────────────────────────

def _current_basal_per_block(pdf: pd.DataFrame) -> dict:
    """Return {block_idx: median_scheduled_basal} for one patient."""
    if "scheduled_basal_rate" in pdf.columns:
        col = "scheduled_basal_rate"
    elif "actual_basal_rate" in pdf.columns:
        col = "actual_basal_rate"
    elif "net_basal" in pdf.columns:
        col = "net_basal"
    else:
        return {}

    result = {}
    hours = pd.to_datetime(pdf["time"]).dt.hour
    for bi, (lo, hi) in enumerate(TIME_BLOCKS):
        mask = (hours >= lo) & (hours < hi)
        vals = pdf.loc[mask, col].dropna()
        if len(vals) > 0:
            result[bi] = float(np.median(vals))
    return result


# ── Schedule Builder ─────────────────────────────────────────────────────────

def build_schedules(
    drift_df: pd.DataFrame,
    isf_map: dict,
    grid: pd.DataFrame,
) -> list:
    """Build per-patient EGP-corrected basal optimisation schedules.

    Returns a list of dicts, each containing both raw (EXP-2730 style) and
    EGP-corrected basal recommendations so they can be compared directly.
    """
    ctrl_map = grid.groupby("patient_id")["controller"].first().to_dict()
    schedules = []

    for pid, pdf in grid.groupby("patient_id"):
        if pid not in isf_map:
            continue
        patient_isf = isf_map[pid]
        if patient_isf < MIN_ISF:
            continue

        current_basals = _current_basal_per_block(pdf)
        if not current_basals:
            continue

        p_drift = drift_df[drift_df["patient_id"] == pid]

        blocks = {}
        raw_pct_changes = []
        corr_pct_changes = []

        for bi, label in enumerate(BLOCK_LABELS):
            bd = p_drift[p_drift["block_idx"] == bi]
            current = current_basals.get(bi, np.nan)

            if np.isnan(current) or len(bd) < MIN_EVENTS_PER_BLOCK:
                blocks[label] = {
                    "current_basal": round(current, 3) if not np.isnan(current) else None,
                    "n_events": int(len(bd)),
                    "median_raw_drift": None,
                    "median_egp": None,
                    "median_corrected_drift": None,
                    "raw_delta": None,
                    "corrected_delta": None,
                    "raw_recommended": round(current, 3) if not np.isnan(current) else None,
                    "corrected_recommended": round(current, 3) if not np.isnan(current) else None,
                    "sufficient_data": False,
                }
                continue

            med_raw = float(np.median(bd["raw_drift"]))
            med_egp = float(np.median(bd["egp_total"]))
            med_corr = float(np.median(bd["corrected_drift"]))

            raw_delta = med_raw / patient_isf
            corr_delta = med_corr / patient_isf

            raw_rec = float(np.clip(current + raw_delta, BASAL_CLAMP_LO, BASAL_CLAMP_HI))
            corr_rec = float(np.clip(current + corr_delta, BASAL_CLAMP_LO, BASAL_CLAMP_HI))

            blocks[label] = {
                "current_basal": round(current, 3),
                "n_events": int(len(bd)),
                "median_raw_drift": round(med_raw, 2),
                "median_egp": round(med_egp, 2),
                "median_corrected_drift": round(med_corr, 2),
                "raw_delta": round(raw_delta, 4),
                "corrected_delta": round(corr_delta, 4),
                "raw_recommended": round(raw_rec, 3),
                "corrected_recommended": round(corr_rec, 3),
                "sufficient_data": True,
            }

            if current > 0:
                raw_pct_changes.append(abs(raw_delta) / current * 100)
                corr_pct_changes.append(abs(corr_delta) / current * 100)

        # TDD summaries: rate × 4 h per block
        cur_vals = [
            b["current_basal"] for b in blocks.values()
            if b["current_basal"] is not None
        ]
        raw_vals = [
            b["raw_recommended"] for b in blocks.values()
            if b["raw_recommended"] is not None
        ]
        corr_vals = [
            b["corrected_recommended"] for b in blocks.values()
            if b["corrected_recommended"] is not None
        ]

        total_cur = sum(cur_vals) * 4.0 if cur_vals else 0.0
        total_raw = sum(raw_vals) * 4.0 if raw_vals else 0.0
        total_corr = sum(corr_vals) * 4.0 if corr_vals else 0.0

        raw_tdd_pct = (
            abs(total_raw - total_cur) / total_cur * 100 if total_cur > 0 else 0.0
        )
        corr_tdd_pct = (
            abs(total_corr - total_cur) / total_cur * 100 if total_cur > 0 else 0.0
        )

        schedules.append({
            "patient_id": pid,
            "controller": ctrl_map.get(pid, "unknown"),
            "patient_isf": round(patient_isf, 2),
            "blocks": blocks,
            "total_daily_basal_current": round(total_cur, 2),
            "total_daily_basal_raw_recommended": round(total_raw, 2),
            "total_daily_basal_corrected_recommended": round(total_corr, 2),
            "raw_tdd_change_pct": round(raw_tdd_pct, 1),
            "egp_corrected_tdd_change_pct": round(corr_tdd_pct, 1),
            "is_more_conservative": bool(corr_tdd_pct < raw_tdd_pct),
            "max_raw_block_pct": round(max(raw_pct_changes), 1) if raw_pct_changes else 0.0,
            "max_corr_block_pct": round(max(corr_pct_changes), 1) if corr_pct_changes else 0.0,
        })

    return schedules


# ── Hypothesis Tests ─────────────────────────────────────────────────────────

def test_h1(drift_df: pd.DataFrame) -> dict:
    """H1: EGP accounts for >20 % of fasting drift magnitude.

    Compare |raw_drift| vs |egp_component| across all events.
    PASS if median(egp_fraction) > 0.20.
    """
    if drift_df.empty:
        return {"h1_verdict": "FAIL", "reason": "no drift events"}

    raw_abs = drift_df["raw_drift"].abs()
    egp_abs = drift_df["egp_total"].abs()

    # Avoid division by zero: only events with |raw_drift| > 1 mg/dL
    mask = raw_abs > 1.0
    if mask.sum() == 0:
        return {"h1_verdict": "FAIL", "reason": "no events with |drift| > 1"}

    fractions = (egp_abs[mask] / raw_abs[mask]).values
    med_frac = float(np.median(fractions))
    verdict = "PASS" if med_frac > 0.20 else "FAIL"

    return {
        "h1_verdict": verdict,
        "n_events": int(mask.sum()),
        "median_egp_fraction": round(med_frac, 4),
        "mean_egp_fraction": round(float(np.mean(fractions)), 4),
        "p25_egp_fraction": round(float(np.percentile(fractions, 25)), 4),
        "p75_egp_fraction": round(float(np.percentile(fractions, 75)), 4),
        "threshold": 0.20,
    }


def test_h2(schedules: list) -> dict:
    """H2: EGP-corrected basal recommendations are more conservative.

    Per patient: |egp_corrected_tdd_change| < |raw_tdd_change|.
    PASS if >70 % of patients have more conservative recommendations.
    """
    n_total = len(schedules)
    if n_total == 0:
        return {"h2_verdict": "FAIL", "reason": "no schedules"}

    n_conservative = sum(1 for s in schedules if s["is_more_conservative"])
    frac = n_conservative / n_total
    verdict = "PASS" if frac > 0.70 else "FAIL"

    raw_pcts = [s["raw_tdd_change_pct"] for s in schedules]
    corr_pcts = [s["egp_corrected_tdd_change_pct"] for s in schedules]

    return {
        "h2_verdict": verdict,
        "n_total": n_total,
        "n_more_conservative": n_conservative,
        "fraction_more_conservative": round(frac, 4),
        "median_raw_tdd_change_pct": round(float(np.median(raw_pcts)), 2),
        "median_corrected_tdd_change_pct": round(float(np.median(corr_pcts)), 2),
        "threshold": 0.70,
    }


def test_h3(schedules: list) -> dict:
    """H3: EGP-corrected recommendations have fewer extreme adjustments.

    Count patients with >100 % TDD change: raw vs corrected.
    PASS if corrected has fewer extreme patients.
    """
    if not schedules:
        return {"h3_verdict": "FAIL", "reason": "no schedules"}

    thresholds = [50, 100, 200]
    comparisons = {}
    all_pass = True

    for thr in thresholds:
        n_raw = sum(1 for s in schedules if s["raw_tdd_change_pct"] > thr)
        n_corr = sum(1 for s in schedules if s["egp_corrected_tdd_change_pct"] > thr)
        comparisons[f">{thr}pct_raw"] = n_raw
        comparisons[f">{thr}pct_corrected"] = n_corr
        comparisons[f">{thr}pct_reduction"] = n_raw - n_corr

    # Primary criterion: fewer patients with >100 % TDD change
    n_raw_100 = comparisons[">100pct_raw"]
    n_corr_100 = comparisons[">100pct_corrected"]
    verdict = "PASS" if n_corr_100 < n_raw_100 else "FAIL"

    return {
        "h3_verdict": verdict,
        "n_total": len(schedules),
        "comparisons": comparisons,
    }


def test_h4(drift_df: pd.DataFrame) -> dict:
    """H4: EGP correction is circadian — larger at dawn, smaller at midday.

    Compare EGP contribution by time block.
    PASS if dawn (04-08) EGP contribution > midday (12-16) contribution.
    """
    if drift_df.empty:
        return {"h4_verdict": "FAIL", "reason": "no drift events"}

    egp_by_block = {}
    for bi, label in enumerate(BLOCK_LABELS):
        bd = drift_df[drift_df["block_idx"] == bi]
        if len(bd) >= 3:
            egp_by_block[label] = round(float(bd["egp_total"].median()), 3)
        else:
            egp_by_block[label] = None

    dawn_egp = egp_by_block.get("04-08")
    midday_egp = egp_by_block.get("12-16")

    if dawn_egp is None or midday_egp is None:
        return {
            "h4_verdict": "FAIL",
            "reason": "insufficient data for dawn or midday blocks",
            "egp_by_block": egp_by_block,
        }

    verdict = "PASS" if dawn_egp > midday_egp else "FAIL"

    return {
        "h4_verdict": verdict,
        "dawn_04_08_egp": dawn_egp,
        "midday_12_16_egp": midday_egp,
        "dawn_minus_midday": round(dawn_egp - midday_egp, 3),
        "egp_by_block": egp_by_block,
    }


# ── Printing ─────────────────────────────────────────────────────────────────

def print_comparison_table(schedules: list) -> None:
    """Print a per-patient comparison of raw vs EGP-corrected TDD changes."""
    header = (
        f"{'Patient':>12s}  {'Ctrl':>8s}  {'ISF':>5s}  "
        f"{'TDD_cur':>7s}  {'TDD_raw':>7s}  {'TDD_egp':>7s}  "
        f"{'Raw%':>6s}  {'EGP%':>6s}  {'Conserv':>7s}"
    )
    print("\n" + header)
    print("-" * len(header))
    for s in schedules:
        conserv = "  yes" if s["is_more_conservative"] else "   no"
        print(
            f"{s['patient_id'][:12]:>12s}  {s['controller'][:8]:>8s}  "
            f"{s['patient_isf']:5.1f}  "
            f"{s['total_daily_basal_current']:7.2f}  "
            f"{s['total_daily_basal_raw_recommended']:7.2f}  "
            f"{s['total_daily_basal_corrected_recommended']:7.2f}  "
            f"{s['raw_tdd_change_pct']:6.1f}  "
            f"{s['egp_corrected_tdd_change_pct']:6.1f}  "
            f"{conserv:>7s}"
        )
    print()


# ── Visualisation ────────────────────────────────────────────────────────────

def make_visualization(
    schedules: list,
    drift_df: pd.DataFrame,
    h1: dict,
    h2: dict,
    h3: dict,
    h4: dict,
) -> None:
    """Create 2×2 panel figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    if not schedules:
        print("  [viz] No schedules to plot.")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"EXP-{EXP_ID}: {TITLE}",
        fontsize=13, fontweight="bold", y=0.98,
    )

    # ── Panel 1: Drift decomposition by time block ──────────────────────────
    ax1 = axes[0, 0]
    egp_means = []
    residual_means = []
    valid_labels = []

    for bi, label in enumerate(BLOCK_LABELS):
        bd = drift_df[drift_df["block_idx"] == bi]
        if len(bd) >= 3:
            egp_means.append(float(bd["egp_total"].median()))
            residual = bd["raw_drift"] - bd["egp_total"]
            residual_means.append(float(residual.median()))
            valid_labels.append(label)

    if valid_labels:
        x = np.arange(len(valid_labels))
        w = 0.6
        ax1.bar(x, egp_means, w, label="EGP component", color="#4c72b0", alpha=0.85)
        ax1.bar(x, residual_means, w, bottom=egp_means,
                label="Residual drift", color="#dd8452", alpha=0.85)
        ax1.set_xticks(x)
        ax1.set_xticklabels(valid_labels, fontsize=8)
        ax1.axhline(0, color="grey", linewidth=0.5, linestyle="--")
        ax1.legend(fontsize=8)
    ax1.set_title("Drift Decomposition by Time Block", fontsize=10)
    ax1.set_ylabel("mg/dL per hour", fontsize=9)
    ax1.set_xlabel("Time block", fontsize=9)

    # ── Panel 2: TDD change comparison scatter ──────────────────────────────
    ax2 = axes[0, 1]
    raw_pcts = [s["raw_tdd_change_pct"] for s in schedules]
    corr_pcts = [s["egp_corrected_tdd_change_pct"] for s in schedules]

    ax2.scatter(raw_pcts, corr_pcts, alpha=0.6, s=30, edgecolors="k", linewidths=0.3)
    lim = max(max(raw_pcts, default=1), max(corr_pcts, default=1)) * 1.1
    ax2.plot([0, lim], [0, lim], "r--", linewidth=1, label="y = x (no change)")
    ax2.set_xlim(0, lim)
    ax2.set_ylim(0, lim)
    ax2.set_xlabel("Raw TDD Change %", fontsize=9)
    ax2.set_ylabel("EGP-Corrected TDD Change %", fontsize=9)
    ax2.set_title("TDD Change: Raw vs EGP-Corrected", fontsize=10)
    ax2.legend(fontsize=8)

    n_below = sum(1 for r, c in zip(raw_pcts, corr_pcts) if c < r)
    ax2.text(
        0.05, 0.92,
        f"{n_below}/{len(schedules)} below y=x\n(more conservative)",
        transform=ax2.transAxes, fontsize=8, va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8),
    )

    # ── Panel 3: Extreme adjustment counts ──────────────────────────────────
    ax3 = axes[1, 0]
    thresholds_list = [50, 100, 200]
    raw_counts = []
    corr_counts = []
    for thr in thresholds_list:
        raw_counts.append(sum(1 for s in schedules if s["raw_tdd_change_pct"] > thr))
        corr_counts.append(
            sum(1 for s in schedules if s["egp_corrected_tdd_change_pct"] > thr)
        )

    x3 = np.arange(len(thresholds_list))
    w3 = 0.3
    ax3.bar(x3 - w3 / 2, raw_counts, w3, label="Raw", color="#c44e52", alpha=0.85)
    ax3.bar(x3 + w3 / 2, corr_counts, w3, label="EGP-corrected", color="#4c72b0", alpha=0.85)
    ax3.set_xticks(x3)
    ax3.set_xticklabels([f">{t}%" for t in thresholds_list], fontsize=9)
    ax3.set_ylabel("# Patients", fontsize=9)
    ax3.set_xlabel("TDD Change Threshold", fontsize=9)
    ax3.set_title("Extreme Adjustment Counts", fontsize=10)
    ax3.legend(fontsize=8)
    # Integer y-axis ticks
    ymax3 = max(max(raw_counts, default=0), max(corr_counts, default=0))
    if ymax3 > 0:
        ax3.set_yticks(range(0, ymax3 + 2))

    # ── Panel 4: Top-5 per-patient basal schedule comparison ────────────────
    ax4 = axes[1, 1]

    # Find 5 patients where EGP correction makes the biggest difference
    diffs = []
    for s in schedules:
        diff = abs(s["raw_tdd_change_pct"] - s["egp_corrected_tdd_change_pct"])
        diffs.append((diff, s))
    diffs.sort(key=lambda x: x[0], reverse=True)
    top5 = [s for _, s in diffs[:5]]

    colors_cycle = ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3"]
    for idx, s in enumerate(top5):
        cur_line = []
        raw_line = []
        corr_line = []
        x_vals = []
        for bi, label in enumerate(BLOCK_LABELS):
            b = s["blocks"].get(label, {})
            if b.get("current_basal") is not None:
                x_vals.append(bi)
                cur_line.append(b["current_basal"])
                raw_line.append(b.get("raw_recommended", b["current_basal"]))
                corr_line.append(b.get("corrected_recommended", b["current_basal"]))

        c = colors_cycle[idx % len(colors_cycle)]
        pid_short = s["patient_id"][:8]
        if x_vals:
            ax4.plot(x_vals, cur_line, "o-", color=c, alpha=0.3, markersize=3)
            ax4.plot(x_vals, raw_line, "s--", color=c, alpha=0.5, markersize=3)
            ax4.plot(x_vals, corr_line, "^-", color=c, alpha=0.9, markersize=4,
                     label=pid_short)

    ax4.set_xticks(range(len(BLOCK_LABELS)))
    ax4.set_xticklabels(BLOCK_LABELS, fontsize=8)
    ax4.set_ylabel("Basal Rate (U/h)", fontsize=9)
    ax4.set_xlabel("Time block", fontsize=9)
    ax4.set_title("Top-5 Patients: Current (○), Raw (□), EGP-corr (△)", fontsize=9)
    if top5:
        ax4.legend(fontsize=7, loc="best", ncol=2)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = VIZ_DIR / "egp_basal.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  [viz] Saved → {out}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 65)
    print(f"  EXP-{EXP_ID}: {TITLE}")
    print("=" * 65)

    # [1/6] Load data
    print("\n[1/6] Loading data …")
    grid = load_data()
    n_patients = grid["patient_id"].nunique()
    print(f"  {len(grid):,} rows, {n_patients} patients")

    # [2/6] Extract fasting drift events with EGP estimates
    print("[2/6] Extracting fasting-period drift events with EGP …")
    drift_df = extract_all_drift(grid)
    n_drift_patients = drift_df["patient_id"].nunique() if not drift_df.empty else 0
    print(f"  {len(drift_df):,} drift events across {n_drift_patients} patients")

    if drift_df.empty:
        print("\n  ⚠  No drift events extracted — cannot proceed.")
        sys.exit(1)

    # Drift summary
    med_raw = float(drift_df["raw_drift"].median())
    med_egp = float(drift_df["egp_total"].median())
    med_corr = float(drift_df["corrected_drift"].median())
    print(f"  Median raw drift: {med_raw:+.2f} mg/dL/h")
    print(f"  Median EGP component: {med_egp:+.2f} mg/dL/h")
    print(f"  Median corrected drift: {med_corr:+.2f} mg/dL/h")

    # [3/6] Compute per-patient ISF
    print("[3/6] Computing per-patient ISF from independent correction events …")
    isf_map = compute_patient_isf(grid)
    if isf_map:
        print(
            f"  ISF available for {len(isf_map)} patients, "
            f"median = {np.median(list(isf_map.values())):.1f} mg/dL/U"
        )
    else:
        print("  ⚠  No ISF estimates — cannot build schedules.")
        sys.exit(1)

    # [4/6] Build schedules
    print("[4/6] Building EGP-corrected basal schedules …")
    schedules = build_schedules(drift_df, isf_map, grid)
    print(f"  {len(schedules)} patient schedules generated")

    if not schedules:
        print("\n  ⚠  No schedules generated — cannot test hypotheses.")
        sys.exit(1)

    # [5/6] Hypothesis tests
    print("[5/6] Testing hypotheses …")
    h1 = test_h1(drift_df)
    h2 = test_h2(schedules)
    h3 = test_h3(schedules)
    h4 = test_h4(drift_df)

    print(
        f"  H1 EGP fraction of drift    : {h1['h1_verdict']}  "
        f"(median fraction = {h1.get('median_egp_fraction', '?')})"
    )
    print(
        f"  H2 more conservative         : {h2['h2_verdict']}  "
        f"({h2.get('fraction_more_conservative', 0):.1%} of patients)"
    )
    print(
        f"  H3 fewer extreme adjustments : {h3['h3_verdict']}  "
        f"(>100 %: raw={h3.get('comparisons', {}).get('>100pct_raw', '?')}, "
        f"corr={h3.get('comparisons', {}).get('>100pct_corrected', '?')})"
    )
    print(
        f"  H4 circadian EGP             : {h4['h4_verdict']}  "
        f"(dawn={h4.get('dawn_04_08_egp', '?')}, "
        f"midday={h4.get('midday_12_16_egp', '?')})"
    )

    # Print comparison table
    print_comparison_table(schedules)

    # [6/6] Visualisation & persist
    print("[6/6] Generating visualisation …")
    try:
        make_visualization(schedules, drift_df, h1, h2, h3, h4)
    except Exception as exc:
        print(f"  [viz] WARNING: {exc}")

    # Assemble results
    results = {
        "experiment_id": EXP_ID,
        "title": TITLE,
        "n_patients_qualified": int(n_patients),
        "n_drift_events": int(len(drift_df)),
        "n_patients_with_isf": len(isf_map),
        "n_schedules": len(schedules),
        "median_isf": round(float(np.median(list(isf_map.values()))), 2),
        "drift_summary": {
            "median_raw_drift": round(med_raw, 3),
            "median_egp_component": round(med_egp, 3),
            "median_corrected_drift": round(med_corr, 3),
        },
        "hypotheses": {
            "H1": h1,
            "H2": h2,
            "H3": h3,
            "H4": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
        "schedules": schedules,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults → {OUT_JSON}")

    v = results["verdict_summary"]
    print(f"\nVerdict: H1={v['H1']} H2={v['H2']} H3={v['H3']} H4={v['H4']}")


if __name__ == "__main__":
    main()
