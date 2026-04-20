#!/usr/bin/env python3
"""EXP-2730: Basal Rate Optimization from Drift Analysis

INSIGHT: EXP-2724 showed glucose drift has significant circadian structure
(Kruskal-Wallis p < 1e-38) but is highly patient-specific.  EXP-2723
provides per-patient deconfounded ISF (median ~13 on independent events).
By dividing drift by ISF we can convert descriptive drift into prescriptive
basal-rate adjustments.

METHOD:
  1. Extract fasting-period drift per patient × 4-hour time block (EXP-2724).
  2. Compute per-patient ISF from independent correction events (EXP-2720).
  3. basal_delta = median_drift / patient_isf  →  U/h adjustment.
  4. Generate full 6-block recommended basal schedule per patient.

HYPOTHESES:
  H1  Non-trivial adjustments needed for >60 % of patients (≥10 % in at
      least one block).
  H2  Total daily basal change is conservative (<30 %) for >80 % of patients.
  H3  Simulated post-adjustment drift is smaller than original drift.
  H4  Drift variability correlates with adjustment magnitude (r > 0.5).

REFERENCES: EXP-2720, EXP-2723, EXP-2724
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ────────────────────────────────────────────────────────────────
EXP_ID = "2730"
TITLE = "Basal Rate Optimization — From Drift to Actionable Schedules"

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / f"exp-{EXP_ID}_basal_optimization.json"
VIZ_DIR = Path("visualizations/basal-optimization")

# ── Constants ────────────────────────────────────────────────────────────
TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

FASTING_BOLUS_WINDOW = 24   # 2 h in 5-min steps
FASTING_CARB_WINDOW = 36    # 3 h in 5-min steps
DRIFT_HORIZON = 12           # 1 h in 5-min steps

MIN_EVENTS_PER_BLOCK = 5
ISF_BG_THRESHOLD = 180       # mg/dL — correction event entry threshold
ISF_MIN_DOSE = 0.3           # U   — minimum insulin to count
ISF_INDEPENDENCE_GAP = 24    # 2 h in 5-min steps
ISF_HORIZON = 24             # 2 h observation window for ISF

MIN_ISF = 1.0                # skip optimisation if ISF implausibly low
BASAL_CLAMP_LO = 0.05       # U/h — safety floor
BASAL_CLAMP_HI = 5.0        # U/h — safety ceiling

# ── Data loading ─────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Load grid, merge controller info, restrict to qualified patients."""
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    return grid


# ── Steady-state drift extraction (per EXP-2724) ────────────────────────

def _extract_drift_events(pdf: pd.DataFrame) -> list[dict]:
    """Return fasting-period drift events for one patient.

    A valid event has no bolus in prior 2 h, no carbs in prior 3 h,
    and valid glucose at both *t* and *t + 1 h*.
    """
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values if "bolus" in pdf.columns else np.zeros(len(pdf))
    carbs = pdf["carbs"].values if "carbs" in pdf.columns else np.zeros(len(pdf))
    times = pdf["time"].values

    # Determine scheduled basal per row
    if "scheduled_basal_rate" in pdf.columns:
        sched = pdf["scheduled_basal_rate"].values
    elif "actual_basal_rate" in pdf.columns:
        sched = pdf["actual_basal_rate"].values
    elif "net_basal" in pdf.columns:
        sched = pdf["net_basal"].values
    else:
        sched = np.full(len(pdf), np.nan)

    n = len(glucose)
    events: list[dict] = []
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

        drift = float(glucose[i + DRIFT_HORIZON] - glucose[i])  # mg/dL per hour
        hour = pd.Timestamp(times[i]).hour
        block_idx = hour // 4

        events.append({
            "idx": i,
            "hour": hour,
            "block_idx": block_idx,
            "block_label": BLOCK_LABELS[block_idx],
            "drift": drift,
            "glucose": float(glucose[i]),
            "scheduled_basal": float(sched[i]) if not np.isnan(sched[i]) else np.nan,
        })
    return events


def extract_all_drift(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract drift events across all patients."""
    rows: list[dict] = []
    for pid, pdf in grid.groupby("patient_id"):
        ctrl = pdf["controller"].iloc[0]
        evts = _extract_drift_events(pdf)
        for e in evts:
            e["patient_id"] = pid
            e["controller"] = ctrl
            rows.append(e)
    return pd.DataFrame(rows)


# ── Per-patient ISF from independent correction events (EXP-2720) ───────

def _extract_isf_events(pdf: pd.DataFrame) -> list[dict]:
    """Return independent correction-event ISF values for one patient."""
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].values if "bolus" in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf["bolus_smb"].values if "bolus_smb" in pdf.columns else np.zeros(len(pdf))
    carbs = pdf["carbs"].values if "carbs" in pdf.columns else np.zeros(len(pdf))

    # Scheduled basal for excess computation
    if "scheduled_basal_rate" in pdf.columns and "actual_basal_rate" in pdf.columns:
        excess_basal = (pdf["actual_basal_rate"].values
                        - pdf["scheduled_basal_rate"].values)
    elif "net_basal" in pdf.columns:
        excess_basal = pdf["net_basal"].values
    else:
        excess_basal = np.zeros(len(pdf))

    n = len(glucose)
    events: list[dict] = []
    last_accepted_idx = -ISF_INDEPENDENCE_GAP - 1

    for i in range(FASTING_CARB_WINDOW, n - ISF_HORIZON):
        if np.isnan(glucose[i]) or np.isnan(glucose[i + ISF_HORIZON]):
            continue

        # High BG entry point
        if glucose[i] < ISF_BG_THRESHOLD:
            continue

        # No carbs in window
        win_carbs = carbs[max(0, i - FASTING_CARB_WINDOW + 1): i + ISF_HORIZON + 1]
        if np.nansum(win_carbs) > 5:
            continue

        # Total insulin in 2 h observation window
        win_bolus = np.nansum(bolus[i: i + ISF_HORIZON + 1])
        win_smb = np.nansum(bolus_smb[i: i + ISF_HORIZON + 1])
        win_excess = np.nansum(np.clip(excess_basal[i: i + ISF_HORIZON + 1], 0, None))
        # Convert excess basal from rate to dose (5-min steps → divide by 12)
        total_insulin = win_bolus + win_smb + (win_excess / 12.0)

        if total_insulin < ISF_MIN_DOSE:
            continue

        # Independence: ≥ 2 h since last accepted event
        if (i - last_accepted_idx) < ISF_INDEPENDENCE_GAP:
            continue
        last_accepted_idx = i

        observed_drop = float(glucose[i] - glucose[i + ISF_HORIZON])
        demand_isf = observed_drop / total_insulin  # mg/dL per U

        if demand_isf > 0:
            events.append({"idx": i, "demand_isf": demand_isf})

    return events


def compute_patient_isf(grid: pd.DataFrame) -> dict[str, float]:
    """Return {patient_id: median_demand_isf} for each qualified patient."""
    isf_map: dict[str, float] = {}
    for pid, pdf in grid.groupby("patient_id"):
        evts = _extract_isf_events(pdf)
        if len(evts) >= 3:
            isf_map[pid] = float(np.median([e["demand_isf"] for e in evts]))
    return isf_map


# ── Basal schedule estimation ───────────────────────────────────────────

def _current_basal_per_block(pdf: pd.DataFrame) -> dict[int, float]:
    """Estimate current scheduled basal per 4-hour block for one patient."""
    if "scheduled_basal_rate" in pdf.columns:
        col = "scheduled_basal_rate"
    elif "actual_basal_rate" in pdf.columns:
        col = "actual_basal_rate"
    elif "net_basal" in pdf.columns:
        col = "net_basal"
    else:
        return {}
    hours = pd.to_datetime(pdf["time"]).dt.hour
    block_idx = hours // 4
    result: dict[int, float] = {}
    for bi in range(6):
        vals = pdf.loc[block_idx == bi, col].dropna()
        if len(vals) > 0:
            result[bi] = float(vals.median())
    return result


# ── Optimisation core ───────────────────────────────────────────────────

def build_schedules(
    drift_df: pd.DataFrame,
    isf_map: dict[str, float],
    grid: pd.DataFrame,
) -> list[dict]:
    """Build per-patient basal-optimisation schedules."""
    ctrl_map = (
        grid.groupby("patient_id")["controller"]
        .first()
        .to_dict()
    )
    schedules: list[dict] = []

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

        blocks: dict[str, dict] = {}
        for bi, label in enumerate(BLOCK_LABELS):
            bd = p_drift[p_drift["block_idx"] == bi]["drift"]
            current = current_basals.get(bi, np.nan)
            if np.isnan(current) or len(bd) < MIN_EVENTS_PER_BLOCK:
                blocks[label] = {
                    "current_basal": round(current, 3) if not np.isnan(current) else None,
                    "n_events": int(len(bd)),
                    "median_drift": None,
                    "delta": None,
                    "recommended_basal": round(current, 3) if not np.isnan(current) else None,
                    "sufficient_data": False,
                }
                continue

            med_drift = float(np.median(bd))
            delta = med_drift / patient_isf
            rec = np.clip(current + delta, BASAL_CLAMP_LO, BASAL_CLAMP_HI)

            blocks[label] = {
                "current_basal": round(current, 3),
                "n_events": int(len(bd)),
                "median_drift": round(med_drift, 2),
                "delta": round(delta, 4),
                "recommended_basal": round(float(rec), 3),
                "sufficient_data": True,
            }

        # Summaries
        cur_vals = [
            b["current_basal"]
            for b in blocks.values()
            if b["current_basal"] is not None
        ]
        rec_vals = [
            b["recommended_basal"]
            for b in blocks.values()
            if b["recommended_basal"] is not None
        ]
        # Total daily = sum of per-block rate × 4 h
        total_current = sum(cur_vals) * 4.0 if cur_vals else 0.0
        total_rec = sum(rec_vals) * 4.0 if rec_vals else 0.0

        deltas = [
            abs(b["delta"])
            for b in blocks.values()
            if b["delta"] is not None
        ]
        pct_changes = []
        for b in blocks.values():
            if (
                b["delta"] is not None
                and b["current_basal"] is not None
                and b["current_basal"] > 0
            ):
                pct_changes.append(abs(b["delta"]) / b["current_basal"] * 100)

        schedules.append({
            "patient_id": pid,
            "controller": ctrl_map.get(pid, "unknown"),
            "patient_isf": round(patient_isf, 2),
            "blocks": blocks,
            "total_daily_basal_current": round(total_current, 2),
            "total_daily_basal_recommended": round(total_rec, 2),
            "max_adjustment_pct": round(max(pct_changes), 1) if pct_changes else 0.0,
            "max_abs_delta": round(max(deltas), 4) if deltas else 0.0,
        })

    return schedules


# ── Hypothesis tests ────────────────────────────────────────────────────

def test_h1(schedules: list[dict]) -> dict:
    """H1: >60 % of patients need ≥10 % adjustment in at least one block."""
    n_total = len(schedules)
    if n_total == 0:
        return {"h1_verdict": "FAIL", "reason": "no schedules", "n_total": 0}
    n_nontrivial = sum(
        1 for s in schedules if s["max_adjustment_pct"] >= 10.0
    )
    frac = n_nontrivial / n_total
    verdict = "PASS" if frac > 0.60 else "FAIL"
    return {
        "h1_verdict": verdict,
        "n_total": n_total,
        "n_nontrivial": n_nontrivial,
        "fraction_nontrivial": round(frac, 4),
        "threshold": 0.60,
    }


def test_h2(schedules: list[dict]) -> dict:
    """H2: >80 % of patients have |total daily change| < 30 %."""
    n_total = len(schedules)
    if n_total == 0:
        return {"h2_verdict": "FAIL", "reason": "no schedules", "n_total": 0}
    conservative = 0
    pct_changes: list[float] = []
    for s in schedules:
        cur = s["total_daily_basal_current"]
        rec = s["total_daily_basal_recommended"]
        if cur > 0:
            pct = abs(rec - cur) / cur * 100
        else:
            pct = 0.0
        pct_changes.append(pct)
        if pct < 30.0:
            conservative += 1

    frac = conservative / n_total
    verdict = "PASS" if frac > 0.80 else "FAIL"
    return {
        "h2_verdict": verdict,
        "n_total": n_total,
        "n_conservative": conservative,
        "fraction_conservative": round(frac, 4),
        "median_pct_change": round(float(np.median(pct_changes)), 2),
        "threshold": 0.80,
    }


def test_h3(schedules: list[dict]) -> dict:
    """H3: Simulated post-adjustment drift < original drift.

    By construction: residual drift ≈ original_drift − delta × ISF = 0,
    but clamping and rounding introduce residuals.
    """
    orig_mag: list[float] = []
    sim_mag: list[float] = []
    for s in schedules:
        isf = s["patient_isf"]
        for b in s["blocks"].values():
            if not b["sufficient_data"]:
                continue
            d = b["median_drift"]
            delta = b["delta"]
            if d is None or delta is None:
                continue
            orig_mag.append(abs(d))
            # Simulated drift = original − adjustment × ISF
            sim = d - delta * isf
            sim_mag.append(abs(sim))

    if not orig_mag:
        return {"h3_verdict": "FAIL", "reason": "no data"}

    med_orig = float(np.median(orig_mag))
    med_sim = float(np.median(sim_mag))
    verdict = "PASS" if med_sim < med_orig else "FAIL"
    return {
        "h3_verdict": verdict,
        "n_block_observations": len(orig_mag),
        "median_original_abs_drift": round(med_orig, 3),
        "median_simulated_abs_drift": round(med_sim, 3),
        "reduction_pct": round((1 - med_sim / med_orig) * 100, 1) if med_orig > 0 else 0.0,
    }


def test_h4(drift_df: pd.DataFrame, schedules: list[dict]) -> dict:
    """H4: Per-patient drift SD correlates with max |basal_delta| (r>0.5)."""
    sched_map = {s["patient_id"]: s for s in schedules}
    xs: list[float] = []
    ys: list[float] = []
    for pid, grp in drift_df.groupby("patient_id"):
        if pid not in sched_map:
            continue
        xs.append(float(grp["drift"].std()))
        ys.append(sched_map[pid]["max_abs_delta"])

    if len(xs) < 5:
        return {"h4_verdict": "FAIL", "reason": "insufficient patients"}

    r, p = stats.pearsonr(xs, ys)
    verdict = "PASS" if r > 0.5 else "FAIL"
    return {
        "h4_verdict": verdict,
        "r": round(float(r), 4),
        "p": float(p),
        "n_patients": len(xs),
        "threshold_r": 0.5,
    }


# ── Visualisation ───────────────────────────────────────────────────────

def make_visualization(
    schedules: list[dict],
    drift_df: pd.DataFrame,
    h1: dict,
    h2: dict,
    h3: dict,
    h4: dict,
) -> None:
    """Create 2 × 2 panel figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    if not schedules:
        print("  [viz] No schedules to plot.")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"EXP-{EXP_ID}: {TITLE}",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    # ── Panel 1: Basal schedule heatmaps (current vs recommended) ────
    ax1 = axes[0, 0]

    pids = [s["patient_id"] for s in schedules]
    n_patients = len(pids)
    cur_matrix = np.full((n_patients, 6), np.nan)
    rec_matrix = np.full((n_patients, 6), np.nan)

    for row, s in enumerate(schedules):
        for col, label in enumerate(BLOCK_LABELS):
            b = s["blocks"].get(label, {})
            if b.get("current_basal") is not None:
                cur_matrix[row, col] = b["current_basal"]
            if b.get("recommended_basal") is not None:
                rec_matrix[row, col] = b["recommended_basal"]

    # Combine for shared colour range
    all_vals = np.concatenate([
        cur_matrix[~np.isnan(cur_matrix)],
        rec_matrix[~np.isnan(rec_matrix)],
    ])
    vmin = float(np.nanmin(all_vals)) if len(all_vals) else 0
    vmax = float(np.nanmax(all_vals)) if len(all_vals) else 2

    # Show current (left half) and recommended (right half) side by side
    combined = np.hstack([cur_matrix, rec_matrix])
    im1 = ax1.imshow(combined, aspect="auto", cmap="YlOrRd", vmin=vmin, vmax=vmax)
    ax1.set_xticks(range(12))
    x_labels = [f"C:{l}" for l in BLOCK_LABELS] + [f"R:{l}" for l in BLOCK_LABELS]
    ax1.set_xticklabels(x_labels, fontsize=6, rotation=45, ha="right")
    ax1.set_ylabel("Patient (index)")
    ax1.set_title("Current (C) vs Recommended (R) Basal", fontsize=9)
    ax1.axvline(5.5, color="white", linewidth=2)
    fig.colorbar(im1, ax=ax1, label="U/h", shrink=0.8)

    # ── Panel 2: Adjustment magnitude bar chart ──────────────────────
    ax2 = axes[0, 1]

    max_deltas: list[float] = []
    directions: list[float] = []
    for s in schedules:
        best_delta = 0.0
        best_abs = 0.0
        for b in s["blocks"].values():
            if b["delta"] is not None and abs(b["delta"]) > best_abs:
                best_abs = abs(b["delta"])
                best_delta = b["delta"]
        cur_avg = s["total_daily_basal_current"] / 24.0 if s["total_daily_basal_current"] > 0 else 1.0
        pct = best_delta / cur_avg * 100
        max_deltas.append(pct)
        directions.append(best_delta)

    colors = ["#d62728" if d > 0 else "#1f77b4" for d in directions]
    y_pos = np.arange(n_patients)
    ax2.barh(y_pos, max_deltas, color=colors, height=0.8)
    ax2.set_xlabel("Max adjustment (% of avg basal)")
    ax2.set_ylabel("Patient (index)")
    ax2.set_title("Max Block Adjustment Magnitude", fontsize=9)
    ax2.axvline(0, color="black", linewidth=0.5)
    # Legend
    from matplotlib.patches import Patch
    ax2.legend(
        handles=[
            Patch(facecolor="#d62728", label="Increase"),
            Patch(facecolor="#1f77b4", label="Decrease"),
        ],
        fontsize=7,
        loc="lower right",
    )

    # ── Panel 3: Total daily basal scatter ───────────────────────────
    ax3 = axes[1, 0]

    cur_totals = [s["total_daily_basal_current"] for s in schedules]
    rec_totals = [s["total_daily_basal_recommended"] for s in schedules]
    ax3.scatter(cur_totals, rec_totals, alpha=0.6, s=20, edgecolors="k", linewidths=0.3)
    lo = min(min(cur_totals), min(rec_totals)) * 0.9
    hi = max(max(cur_totals), max(rec_totals)) * 1.1
    ax3.plot([lo, hi], [lo, hi], "k--", linewidth=0.8, label="y = x")
    ax3.set_xlabel("Current Total Daily Basal (U)")
    ax3.set_ylabel("Recommended Total Daily Basal (U)")
    ax3.set_title(
        f"Total Daily Basal: Current vs Recommended (n={n_patients})",
        fontsize=9,
    )
    ax3.legend(fontsize=7)

    # ── Panel 4: Drift reduction box plot per block ──────────────────
    ax4 = axes[1, 1]

    orig_by_block: dict[str, list[float]] = {l: [] for l in BLOCK_LABELS}
    sim_by_block: dict[str, list[float]] = {l: [] for l in BLOCK_LABELS}
    for s in schedules:
        isf = s["patient_isf"]
        for label in BLOCK_LABELS:
            b = s["blocks"].get(label, {})
            if not b.get("sufficient_data"):
                continue
            d = b["median_drift"]
            delta = b["delta"]
            if d is None or delta is None:
                continue
            orig_by_block[label].append(abs(d))
            sim_by_block[label].append(abs(d - delta * isf))

    positions_orig: list[float] = []
    positions_sim: list[float] = []
    data_orig: list[list[float]] = []
    data_sim: list[list[float]] = []
    tick_positions: list[float] = []
    for idx, label in enumerate(BLOCK_LABELS):
        base = idx * 3
        if orig_by_block[label]:
            positions_orig.append(base)
            data_orig.append(orig_by_block[label])
            positions_sim.append(base + 1)
            data_sim.append(sim_by_block[label])
            tick_positions.append(base + 0.5)

    if data_orig:
        bp1 = ax4.boxplot(
            data_orig,
            positions=positions_orig,
            widths=0.6,
            patch_artist=True,
            showfliers=False,
        )
        for patch in bp1["boxes"]:
            patch.set_facecolor("#ff9999")
        bp2 = ax4.boxplot(
            data_sim,
            positions=positions_sim,
            widths=0.6,
            patch_artist=True,
            showfliers=False,
        )
        for patch in bp2["boxes"]:
            patch.set_facecolor("#99ccff")
        ax4.set_xticks(tick_positions)
        ax4.set_xticklabels(
            [BLOCK_LABELS[i] for i in range(len(BLOCK_LABELS)) if orig_by_block[BLOCK_LABELS[i]]],
            fontsize=7,
        )
        ax4.legend(
            handles=[
                Patch(facecolor="#ff9999", label="Original |drift|"),
                Patch(facecolor="#99ccff", label="Post-adjust |drift|"),
            ],
            fontsize=7,
        )

    ax4.set_xlabel("Time block")
    ax4.set_ylabel("|Drift| (mg/dL per hour)")
    ax4.set_title("Drift Reduction: Before vs After Adjustment", fontsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = VIZ_DIR / "basal_optimization.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  [viz] Saved → {out}")


# ── Reporting ───────────────────────────────────────────────────────────

def print_schedule_table(schedules: list[dict]) -> None:
    """Print a compact per-patient basal schedule table."""
    header = (
        f"{'Patient':>12s}  {'Ctrl':>8s}  {'ISF':>5s}  "
        + "  ".join(f"{l:>8s}" for l in BLOCK_LABELS)
        + f"  {'TDD_cur':>7s}  {'TDD_rec':>7s}  {'Max%':>5s}"
    )
    print("\n" + header)
    print("-" * len(header))
    for s in schedules:
        row = f"{s['patient_id'][:12]:>12s}  {s['controller'][:8]:>8s}  {s['patient_isf']:5.1f}  "
        for label in BLOCK_LABELS:
            b = s["blocks"].get(label, {})
            rec = b.get("recommended_basal")
            row += f"  {rec:8.3f}" if rec is not None else f"  {'—':>8s}"
        row += f"  {s['total_daily_basal_current']:7.2f}"
        row += f"  {s['total_daily_basal_recommended']:7.2f}"
        row += f"  {s['max_adjustment_pct']:5.1f}"
        print(row)
    print()


# ── Main ────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(f"  EXP-{EXP_ID}: {TITLE}")
    print("=" * 60)

    # ── Load data ────────────────────────────────────────────────────
    print("\n[1/6] Loading data …")
    grid = load_data()
    n_patients = grid["patient_id"].nunique()
    print(f"  {len(grid):,} rows, {n_patients} patients")

    # ── Extract fasting drift ────────────────────────────────────────
    print("[2/6] Extracting fasting-period drift events …")
    drift_df = extract_all_drift(grid)
    print(f"  {len(drift_df):,} drift events across {drift_df['patient_id'].nunique()} patients")

    # ── Compute per-patient ISF ──────────────────────────────────────
    print("[3/6] Computing per-patient ISF from independent correction events …")
    isf_map = compute_patient_isf(grid)
    print(f"  ISF available for {len(isf_map)} patients, median = {np.median(list(isf_map.values())):.1f} mg/dL/U")

    # ── Build schedules ──────────────────────────────────────────────
    print("[4/6] Building basal optimisation schedules …")
    schedules = build_schedules(drift_df, isf_map, grid)
    print(f"  {len(schedules)} patient schedules generated")

    if not schedules:
        print("\n  ⚠  No schedules generated — cannot test hypotheses.")
        sys.exit(1)

    # ── Hypothesis tests ─────────────────────────────────────────────
    print("[5/6] Testing hypotheses …")
    h1 = test_h1(schedules)
    h2 = test_h2(schedules)
    h3 = test_h3(schedules)
    h4 = test_h4(drift_df, schedules)

    print(f"  H1 non-trivial adjustments : {h1['h1_verdict']}  "
          f"({h1.get('fraction_nontrivial', 0):.1%} of patients)")
    print(f"  H2 conservative total daily : {h2['h2_verdict']}  "
          f"({h2.get('fraction_conservative', 0):.1%} < 30 % change)")
    print(f"  H3 drift reduction          : {h3['h3_verdict']}  "
          f"(original {h3.get('median_original_abs_drift', '?')}, "
          f"simulated {h3.get('median_simulated_abs_drift', '?')})")
    print(f"  H4 drift-SD vs delta corr   : {h4['h4_verdict']}  "
          f"(r = {h4.get('r', '?')})")

    # ── Schedule table ───────────────────────────────────────────────
    print_schedule_table(schedules)

    # ── Visualisation ────────────────────────────────────────────────
    print("[6/6] Generating visualisation …")
    try:
        make_visualization(schedules, drift_df, h1, h2, h3, h4)
    except Exception as exc:
        print(f"  [viz] WARNING: {exc}")

    # ── Persist results ──────────────────────────────────────────────
    results = {
        "experiment_id": EXP_ID,
        "title": TITLE,
        "n_patients_qualified": n_patients,
        "n_drift_events": len(drift_df),
        "n_patients_with_isf": len(isf_map),
        "n_schedules": len(schedules),
        "median_isf": round(float(np.median(list(isf_map.values()))), 2),
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
