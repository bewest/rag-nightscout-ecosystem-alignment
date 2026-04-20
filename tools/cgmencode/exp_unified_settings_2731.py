#!/usr/bin/env python3
"""EXP-2731: Unified Per-Patient Settings Assessment

Combines ISF (EXP-2723), CR (EXP-2729), and basal drift (EXP-2724/2730) into
a unified per-patient settings quality report.  Scores each patient on overall
settings calibration quality and generates actionable recommendations.

Prior results:
  EXP-2723  Per-patient ISF — median profile ISF 55 vs recommended 2.6
  EXP-2729  Per-patient CR  — median profile CR 8.8 vs observed 4.9
  EXP-2730  Per-patient basal — most patients need non-trivial adjustment
  EXP-2726b Empirical ISF reduces MAE from 79.7 → 43.8 for 29/31 patients
  EXP-2727  EGP accounts for 42% of profile→empirical ISF gap

Hypotheses:
  H1  Settings calibration score correlates with TIR (r > 0.3)
  H2  >60% of patients need recalibration in ≥2 of 3 dimensions
  H3  ISF miscalibration is the dominant issue (lowest mean score)
  H4  Controller type predicts calibration quality (KW p < 0.05)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Paths ────────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/unified-settings")

ISF_RESULTS = RESULTS_DIR / "exp-2723_patient_settings.json"
CR_RESULTS = RESULTS_DIR / "exp-2729_carb_ratio.json"
BASAL_RESULTS = RESULTS_DIR / "exp-2730_basal_optimization.json"
DRIFT_RESULTS = RESULTS_DIR / "exp-2724_basal_circadian.json"

OUT_JSON = RESULTS_DIR / "exp-2731_unified_settings.json"

EXP_ID = "EXP-2731"
EXP_TITLE = "Unified Per-Patient Settings Assessment — Calibration Quality"


# ── Helpers ──────────────────────────────────────────────────────────────
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _safe_load_json(path: Path) -> dict | None:
    """Load JSON or return None if the file is missing / corrupt."""
    if not path.exists():
        print(f"  ⚠ {path.name} not found — scores for that dimension will be NaN")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        print(f"  ⚠ {path.name} unreadable ({exc}) — skipping")
        return None


def _extract_patient_key(record: dict, *candidate_keys: str) -> float | None:
    """Return the first present key's value, or None."""
    for k in candidate_keys:
        if k in record and record[k] is not None:
            try:
                return float(record[k])
            except (ValueError, TypeError):
                continue
    return None


def _index_by_patient(records: list[dict]) -> dict[str, dict]:
    """Convert a list of dicts with patient_id to a dict keyed by patient_id."""
    return {r["patient_id"]: r for r in records if "patient_id" in r}


def _grade(score: float) -> str:
    if np.isnan(score):
        return "N/A"
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    if score >= 20:
        return "D"
    return "F"


# ── Data loading ─────────────────────────────────────────────────────────
def load_grid():
    """Load the grid parquet filtered to qualified patients."""
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    return grid, qual


def load_prior_results():
    """Load ISF, CR, basal optimisation, and drift results."""
    isf_raw = _safe_load_json(ISF_RESULTS)
    cr_raw = _safe_load_json(CR_RESULTS)
    basal_raw = _safe_load_json(BASAL_RESULTS)
    drift_raw = _safe_load_json(DRIFT_RESULTS)

    # Index by patient_id — each file uses a different top-level list key
    isf_map: dict[str, dict] = {}
    if isf_raw:
        recs = isf_raw.get("per_patient", isf_raw.get("patients", []))
        isf_map = _index_by_patient(recs)

    cr_map: dict[str, dict] = {}
    if cr_raw:
        recs = cr_raw.get("per_patient", cr_raw.get("patients", []))
        cr_map = _index_by_patient(recs)

    basal_map: dict[str, dict] = {}
    if basal_raw:
        recs = basal_raw.get("schedules", basal_raw.get("per_patient", []))
        basal_map = _index_by_patient(recs)

    drift_map: dict[str, dict] = {}
    if drift_raw:
        recs = drift_raw.get("patient_results", drift_raw.get("per_patient", []))
        drift_map = _index_by_patient(recs)

    return isf_map, cr_map, basal_map, drift_map


# ── Per-patient glucose outcomes ─────────────────────────────────────────
def compute_glucose_outcomes(grid: pd.DataFrame) -> dict[str, dict]:
    """Compute TIR, CV, GMI etc. per patient from the grid."""
    outcomes: dict[str, dict] = {}
    for pid, gdf in grid.groupby("patient_id"):
        g = gdf["glucose"].dropna().values
        if len(g) == 0:
            continue
        mean_g = float(np.mean(g))
        std_g = float(np.std(g))
        n = len(g)
        tir = float(np.mean((g >= 70) & (g <= 180))) * 100
        below = float(np.mean(g < 70)) * 100
        above = float(np.mean(g > 180)) * 100
        cv = (std_g / mean_g * 100) if mean_g > 0 else np.nan
        gmi = 3.31 + 0.02392 * mean_g
        outcomes[pid] = {
            "mean_glucose": round(mean_g, 1),
            "glucose_sd": round(std_g, 1),
            "tir_70_180": round(tir, 1),
            "tir_below_70": round(below, 1),
            "tir_above_180": round(above, 1),
            "cv": round(cv, 1),
            "gmi": round(gmi, 2),
            "n_readings": int(n),
            "controller": gdf["controller"].iloc[0],
        }
    return outcomes


# ── Calibration scores ───────────────────────────────────────────────────
def _isf_score_for(rec: dict | None) -> tuple[float, float, float, float]:
    """Return (profile_isf, empirical_isf, ratio, score)."""
    if rec is None:
        return (np.nan, np.nan, np.nan, np.nan)
    prof = _extract_patient_key(rec, "profile_isf")
    emp = _extract_patient_key(
        rec,
        "recommended_isf",
        "deconfounded_isf",
        "normalized_isf",
        "raw_indep_isf",
        "raw_all_isf",
        "empirical_isf",
        "independent_isf",
    )
    if prof is None or emp is None or emp == 0:
        return (prof or np.nan, emp or np.nan, np.nan, np.nan)
    ratio = prof / emp
    # Negative ratio means opposite sign — maximally miscalibrated
    if ratio <= 0:
        return (prof, emp, round(ratio, 3), 0.0)
    score = max(0.0, 100.0 - abs(np.log2(ratio)) * 50.0)
    return (prof, emp, round(ratio, 3), round(score, 1))


def _cr_score_for(rec: dict | None) -> tuple[float, float, float, float]:
    """Return (profile_cr, empirical_cr, ratio, score)."""
    if rec is None:
        return (np.nan, np.nan, np.nan, np.nan)
    prof = _extract_patient_key(rec, "profile_cr")
    emp = _extract_patient_key(
        rec,
        "recommended_cr",
        "full_deconf_cr",
        "deconfounded_cr",
        "observed_cr_indep",
        "observed_cr_all",
        "empirical_cr",
    )
    if prof is None or emp is None or emp == 0:
        return (prof or np.nan, emp or np.nan, np.nan, np.nan)
    ratio = prof / emp
    if ratio <= 0:
        return (prof, emp, round(ratio, 3), 0.0)
    score = max(0.0, 100.0 - abs(np.log2(ratio)) * 50.0)
    return (prof, emp, round(ratio, 3), round(score, 1))


def _basal_score_for(basal_rec: dict | None) -> tuple[float, float]:
    """Return (max_adjustment_pct, score)."""
    if basal_rec is None:
        return (np.nan, np.nan)
    adj = _extract_patient_key(basal_rec, "max_adjustment_pct")
    if adj is None:
        return (np.nan, np.nan)
    adj = abs(adj)
    score = max(0.0, 100.0 - adj)
    return (round(adj, 1), round(score, 1))


def compute_calibration(
    pid: str,
    isf_map: dict,
    cr_map: dict,
    basal_map: dict,
) -> dict:
    """Return calibration metrics for one patient."""
    prof_isf, emp_isf, isf_ratio, isf_score = _isf_score_for(isf_map.get(pid))
    prof_cr, emp_cr, cr_ratio, cr_score = _cr_score_for(cr_map.get(pid))
    max_adj, basal_score = _basal_score_for(basal_map.get(pid))

    scores = [s for s in (isf_score, cr_score, basal_score) if not np.isnan(s)]
    if len(scores) == 0:
        overall = np.nan
    elif len(scores) == 1:
        overall = scores[0]
    else:
        # Geometric mean of available dimension scores (clamp to >0 for log)
        clamped = [max(s, 0.01) for s in scores]
        overall = float(np.exp(np.mean(np.log(clamped))))
    overall = round(overall, 1) if not np.isnan(overall) else np.nan

    return {
        "profile_isf": prof_isf,
        "empirical_isf": emp_isf,
        "isf_ratio": isf_ratio,
        "isf_score": isf_score,
        "profile_cr": prof_cr,
        "empirical_cr": emp_cr,
        "cr_ratio": cr_ratio,
        "cr_score": cr_score,
        "max_basal_adjustment_pct": max_adj,
        "basal_score": basal_score,
        "overall_score": overall,
        "grade": _grade(overall),
        "n_dimensions_scored": len(scores),
    }


# ── Recommendations ──────────────────────────────────────────────────────
def generate_recommendations(cal: dict) -> list[str]:
    recs: list[str] = []
    isf_r = cal["isf_ratio"]
    cr_r = cal["cr_ratio"]
    adj = cal["max_basal_adjustment_pct"]

    if not np.isnan(isf_r) and (isf_r > 2.0 or isf_r < 0.5):
        recs.append(
            f"ISF: adjust from {cal['profile_isf']:.1f} to "
            f"{cal['empirical_isf']:.1f} (ratio {isf_r:.1f}×)"
        )
    elif not np.isnan(isf_r) and (isf_r > 1.3 or isf_r < 0.77):
        recs.append(
            f"ISF: consider tuning from {cal['profile_isf']:.1f} toward "
            f"{cal['empirical_isf']:.1f}"
        )

    if not np.isnan(cr_r) and (cr_r > 1.5 or cr_r < 0.67):
        recs.append(
            f"CR: adjust from {cal['profile_cr']:.1f} to "
            f"{cal['empirical_cr']:.1f} (ratio {cr_r:.1f}×)"
        )
    elif not np.isnan(cr_r) and (cr_r > 1.2 or cr_r < 0.83):
        recs.append(
            f"CR: consider tuning from {cal['profile_cr']:.1f} toward "
            f"{cal['empirical_cr']:.1f}"
        )

    if not np.isnan(adj) and adj > 20:
        recs.append(f"Basal: adjust ({adj:.0f}% change needed)")
    elif not np.isnan(adj) and adj > 10:
        recs.append(f"Basal: minor adjustment ({adj:.0f}% change)")

    if not recs:
        recs.append("Settings appear well-calibrated")
    return recs


# ── Hypothesis tests ─────────────────────────────────────────────────────
def test_h1(rows: list[dict]) -> dict:
    """H1: overall_score correlates with TIR (Pearson r > 0.3)."""
    pairs = [
        (r["overall_score"], r["tir_70_180"])
        for r in rows
        if not np.isnan(r["overall_score"]) and not np.isnan(r["tir_70_180"])
    ]
    if len(pairs) < 5:
        return {"h1_verdict": "SKIP", "reason": f"only {len(pairs)} patients with data"}
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    if np.std(x) < 1e-6 or np.std(y) < 1e-6:
        return {"h1_verdict": "SKIP", "reason": "constant array"}
    r, p = stats.pearsonr(x, y)
    verdict = "PASS" if r > 0.3 else "FAIL"
    return {
        "h1_verdict": verdict,
        "pearson_r": round(float(r), 4),
        "p_value": round(float(p), 6),
        "n_patients": len(pairs),
        "threshold": 0.3,
    }


def test_h2(rows: list[dict]) -> dict:
    """H2: >60% of patients need recalibration in ≥2 of 3 dimensions."""
    total = 0
    multi_recal = 0
    for r in rows:
        dims = [r.get("isf_score"), r.get("cr_score"), r.get("basal_score")]
        scored = [d for d in dims if d is not None and not np.isnan(d)]
        if len(scored) < 2:
            continue
        total += 1
        n_bad = sum(1 for d in scored if d < 60)
        if n_bad >= 2:
            multi_recal += 1
    pct = (multi_recal / total * 100) if total > 0 else 0
    verdict = "PASS" if pct > 60 else "FAIL"
    return {
        "h2_verdict": verdict,
        "pct_multi_recal": round(pct, 1),
        "n_multi_recal": multi_recal,
        "n_evaluated": total,
        "threshold_pct": 60,
    }


def test_h3(rows: list[dict]) -> dict:
    """H3: ISF miscalibration is the dominant issue (lowest mean score)."""
    isf_scores = [r["isf_score"] for r in rows if not np.isnan(r["isf_score"])]
    cr_scores = [r["cr_score"] for r in rows if not np.isnan(r["cr_score"])]
    basal_scores = [r["basal_score"] for r in rows if not np.isnan(r["basal_score"])]
    means = {}
    if isf_scores:
        means["ISF"] = round(float(np.mean(isf_scores)), 1)
    if cr_scores:
        means["CR"] = round(float(np.mean(cr_scores)), 1)
    if basal_scores:
        means["Basal"] = round(float(np.mean(basal_scores)), 1)
    if not means:
        return {"h3_verdict": "SKIP", "reason": "no dimension scores"}
    worst = min(means, key=means.get)
    verdict = "PASS" if worst == "ISF" else "FAIL"
    return {
        "h3_verdict": verdict,
        "mean_scores": means,
        "worst_dimension": worst,
    }


def test_h4(rows: list[dict]) -> dict:
    """H4: Controller type predicts calibration quality (KW p < 0.05)."""
    groups: dict[str, list[float]] = {}
    for r in rows:
        ctrl = r.get("controller", "unknown")
        sc = r.get("overall_score")
        if sc is not None and not np.isnan(sc):
            groups.setdefault(ctrl, []).append(sc)
    # Need ≥2 groups with ≥2 members each
    valid = {k: v for k, v in groups.items() if len(v) >= 2}
    if len(valid) < 2:
        return {
            "h4_verdict": "SKIP",
            "reason": f"only {len(valid)} controller groups with ≥2 patients",
        }
    arrays = list(valid.values())
    stat_val, p_val = stats.kruskal(*arrays)
    verdict = "PASS" if p_val < 0.05 else "FAIL"
    return {
        "h4_verdict": verdict,
        "kruskal_wallis_H": round(float(stat_val), 4),
        "p_value": round(float(p_val), 6),
        "group_medians": {k: round(float(np.median(v)), 1) for k, v in valid.items()},
        "group_sizes": {k: len(v) for k, v in valid.items()},
    }


# ── Visualization ────────────────────────────────────────────────────────
def make_visualization(rows: list[dict], h1_res: dict):
    """Generate 2×2 unified settings figure."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    # Filter to patients with a valid overall score for most panels
    scored = [r for r in rows if not np.isnan(r["overall_score"])]
    scored.sort(key=lambda r: r["overall_score"])

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # ── Panel 1: Per-patient bar chart — 3 calibration dimensions ────────
    ax = axes[0, 0]
    pids = [r["patient_id"] for r in scored]
    isf_s = [r["isf_score"] if not np.isnan(r["isf_score"]) else 0 for r in scored]
    cr_s = [r["cr_score"] if not np.isnan(r["cr_score"]) else 0 for r in scored]
    bas_s = [r["basal_score"] if not np.isnan(r["basal_score"]) else 0 for r in scored]

    x = np.arange(len(pids))
    w = 0.25
    ax.bar(x - w, isf_s, w, label="ISF", color="C0", edgecolor="black", linewidth=0.5)
    ax.bar(x, cr_s, w, label="CR", color="C1", edgecolor="black", linewidth=0.5)
    ax.bar(x + w, bas_s, w, label="Basal", color="C2", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(pids, rotation=90, fontsize=7)
    ax.set_ylabel("Calibration Score (0–100)")
    ax.set_title("Per-Patient Calibration Scores (3 dimensions)", fontweight="bold")
    ax.axhline(60, color="orange", linestyle="--", alpha=0.5, label="Grade B threshold")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, 105)

    # ── Panel 2: Overall score vs TIR scatter ────────────────────────────
    ax = axes[0, 1]
    ctrl_colors = {}
    color_cycle = plt.cm.Set1.colors
    for r in scored:
        c = r.get("controller", "unknown")
        if c not in ctrl_colors:
            ctrl_colors[c] = color_cycle[len(ctrl_colors) % len(color_cycle)]

    for r in scored:
        tir = r.get("tir_70_180", np.nan)
        sc = r["overall_score"]
        if np.isnan(tir) or np.isnan(sc):
            continue
        c = r.get("controller", "unknown")
        ax.scatter(sc, tir, s=80, color=ctrl_colors[c], edgecolors="black",
                   linewidth=0.5, zorder=5, label=c)
        ax.annotate(
            r["patient_id"], (sc, tir), fontsize=6,
            ha="center", va="bottom", xytext=(0, 5),
            textcoords="offset points",
        )

    # Regression line
    xs = [r["overall_score"] for r in scored if not np.isnan(r.get("tir_70_180", np.nan))]
    ys = [r["tir_70_180"] for r in scored if not np.isnan(r.get("tir_70_180", np.nan))]
    if len(xs) >= 3 and np.std(xs) > 1e-6:
        slope, intercept, r_val, _, _ = stats.linregress(xs, ys)
        xr = np.linspace(min(xs), max(xs), 50)
        ax.plot(xr, slope * xr + intercept, "k--", alpha=0.5, linewidth=1)
        ax.text(
            0.05, 0.95, f"r = {r_val:.3f}",
            transform=ax.transAxes, fontsize=10, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

    # Deduplicate legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), fontsize=8, loc="lower right")
    ax.set_xlabel("Overall Calibration Score")
    ax.set_ylabel("TIR 70–180 (%)")
    ax.set_title("Calibration Quality vs Glucose Outcomes", fontweight="bold")
    ax.grid(True, alpha=0.3)

    # ── Panel 3: Grade distribution stacked bar ──────────────────────────
    ax = axes[1, 0]
    grade_order = ["A", "B", "C", "D", "F"]
    grade_colors = {"A": "#2ca02c", "B": "#98df8a", "C": "#ff7f0e",
                    "D": "#d62728", "F": "#7f0000"}
    # Build counts per controller × grade
    all_ctrls = sorted({r.get("controller", "unknown") for r in scored})
    ctrl_grade_counts = {c: {g: 0 for g in grade_order} for c in all_ctrls}
    for r in scored:
        g = r["grade"]
        c = r.get("controller", "unknown")
        if g in grade_order:
            ctrl_grade_counts[c][g] += 1

    x = np.arange(len(all_ctrls))
    bottoms = np.zeros(len(all_ctrls))
    for g in grade_order:
        vals = [ctrl_grade_counts[c][g] for c in all_ctrls]
        ax.bar(x, vals, bottom=bottoms, label=g, color=grade_colors[g],
               edgecolor="black", linewidth=0.5)
        bottoms += np.array(vals)

    ax.set_xticks(x)
    ax.set_xticklabels(all_ctrls, fontweight="bold")
    ax.set_ylabel("Number of Patients")
    ax.set_title("Grade Distribution by Controller", fontweight="bold")
    ax.legend(title="Grade", fontsize=8, loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 4: Settings drift dot plots ────────────────────────────────
    ax = axes[1, 1]
    # Sort by overall score (already sorted)
    pids_scored = [r["patient_id"] for r in scored]
    y_pos = np.arange(len(pids_scored))

    isf_ratios = []
    cr_ratios = []
    basal_pcts = []
    for r in scored:
        isf_ratios.append(r["isf_ratio"] if not np.isnan(r["isf_ratio"]) else None)
        cr_ratios.append(r["cr_ratio"] if not np.isnan(r["cr_ratio"]) else None)
        basal_pcts.append(
            r["max_basal_adjustment_pct"]
            if not np.isnan(r["max_basal_adjustment_pct"])
            else None
        )

    # Use log2 scale for ratios so ideal=0, and pct for basal (ideal=0)
    # Combine into one axis: ISF log2(ratio), CR log2(ratio), basal pct/50
    offset = 0.2
    for i, (ir, cr, bp) in enumerate(zip(isf_ratios, cr_ratios, basal_pcts)):
        if ir is not None and ir > 0:
            ax.scatter(np.log2(ir), i - offset, marker="o", s=40, color="C0",
                       edgecolors="black", linewidth=0.3, zorder=5)
        if cr is not None and cr > 0:
            ax.scatter(np.log2(cr), i, marker="s", s=40, color="C1",
                       edgecolors="black", linewidth=0.3, zorder=5)
        if bp is not None:
            ax.scatter(bp / 50, i + offset, marker="^", s=40, color="C2",
                       edgecolors="black", linewidth=0.3, zorder=5)

    ax.axvline(0, color="green", linewidth=1.5, alpha=0.7, label="Ideal (no drift)")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(pids_scored, fontsize=7)
    ax.set_xlabel("Deviation  (log₂ ratio for ISF/CR;  %change ÷ 50 for basal)")
    ax.set_title("Settings Drift from Profile", fontweight="bold")
    # Manual legend entries
    ax.scatter([], [], marker="o", color="C0", label="ISF ratio (log₂)", s=40)
    ax.scatter([], [], marker="s", color="C1", label="CR ratio (log₂)", s=40)
    ax.scatter([], [], marker="^", color="C2", label="Basal %Δ ÷ 50", s=40)
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        f"{EXP_ID}: Unified Settings Assessment — Per-Patient Calibration Quality",
        fontsize=14, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = VIZ_DIR / "unified_settings.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  → Saved {out}")


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    # [1] Load grid data
    print(f"[1/6] Loading grid data …")
    grid, qual = load_grid()
    print(f"  {len(grid)} rows, {grid['patient_id'].nunique()} patients")

    # [2] Load prior experiment results
    print("[2/6] Loading prior experiment results …")
    isf_map, cr_map, basal_map, drift_map = load_prior_results()
    print(
        f"  ISF: {len(isf_map)} patients  "
        f"CR: {len(cr_map)}  "
        f"Basal: {len(basal_map)}  "
        f"Drift: {len(drift_map)}"
    )

    # [3] Compute glucose outcomes
    print("[3/6] Computing glucose outcomes …")
    outcomes = compute_glucose_outcomes(grid)
    print(f"  Outcomes for {len(outcomes)} patients")

    # [4] Compute per-patient calibration + recommendations
    print("[4/6] Computing calibration scores …")
    all_pids = sorted(
        set(list(outcomes.keys()) + list(isf_map.keys())
            + list(cr_map.keys()) + list(basal_map.keys()))
    )
    # Keep only qualified patients (may be superset in some experiment files)
    all_pids = [p for p in all_pids if p in set(qual)]

    rows: list[dict] = []
    for pid in all_pids:
        cal = compute_calibration(pid, isf_map, cr_map, basal_map)
        recs = generate_recommendations(cal)
        out_row = outcomes.get(pid, {})
        row = {
            "patient_id": pid,
            "controller": out_row.get("controller", "unknown"),
            "tir_70_180": out_row.get("tir_70_180", np.nan),
            "cv": out_row.get("cv", np.nan),
            "mean_glucose": out_row.get("mean_glucose", np.nan),
            "gmi": out_row.get("gmi", np.nan),
            "n_readings": out_row.get("n_readings", 0),
            **cal,
            "recommendations": recs,
            "top_recommendation": recs[0] if recs else "",
        }
        rows.append(row)

    # ── Print per-patient table
    print()
    hdr = (
        f"{'patient_id':<20} {'ctrl':<10} {'TIR':>5} {'CV':>5} "
        f"{'ISF':>5} {'CR':>5} {'Bas':>5} {'All':>5} {'Gr':>3}  "
        f"Top Recommendation"
    )
    print(hdr)
    print("─" * len(hdr) + "─" * 30)
    for r in sorted(rows, key=lambda x: x.get("overall_score", -1) or -1):
        def _f(v, fmt=".0f"):
            return f"{v:{fmt}}" if not np.isnan(v) else "  —"

        print(
            f"{r['patient_id']:<20} {r['controller']:<10} "
            f"{_f(r['tir_70_180']):>5} {_f(r['cv']):>5} "
            f"{_f(r['isf_score']):>5} {_f(r['cr_score']):>5} "
            f"{_f(r['basal_score']):>5} {_f(r['overall_score']):>5} "
            f"{r['grade']:>3}  {r['top_recommendation']}"
        )
    print()

    # [5] Hypothesis testing
    print("[5/6] Testing hypotheses …")
    h1 = test_h1(rows)
    h2 = test_h2(rows)
    h3 = test_h3(rows)
    h4 = test_h4(rows)

    print(f"  H1 (score ↔ TIR):           {h1['h1_verdict']}  "
          f"(r={h1.get('pearson_r', '—')})")
    print(f"  H2 (≥2 dims need recal):     {h2['h2_verdict']}  "
          f"({h2.get('pct_multi_recal', '—')}% of patients)")
    print(f"  H3 (ISF worst dimension):    {h3['h3_verdict']}  "
          f"(means={h3.get('mean_scores', '—')})")
    print(f"  H4 (controller → quality):   {h4['h4_verdict']}  "
          f"(p={h4.get('p_value', '—')})")

    # [6] Visualization + JSON
    print("[6/6] Generating visualization + saving results …")
    make_visualization(rows, h1)

    # Population summary
    scored_rows = [r for r in rows if not np.isnan(r["overall_score"])]
    overall_scores = [r["overall_score"] for r in scored_rows]
    grade_dist = {}
    for r in scored_rows:
        grade_dist[r["grade"]] = grade_dist.get(r["grade"], 0) + 1

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_patients": len(rows),
        "n_patients_scored": len(scored_rows),
        "data_sources": {
            "isf": str(ISF_RESULTS),
            "cr": str(CR_RESULTS),
            "basal": str(BASAL_RESULTS),
            "drift": str(DRIFT_RESULTS),
        },
        "n_from_isf": len(isf_map),
        "n_from_cr": len(cr_map),
        "n_from_basal": len(basal_map),
        "n_from_drift": len(drift_map),
        "hypotheses": {
            "H1_score_correlates_TIR": h1,
            "H2_multi_dimension_recal": h2,
            "H3_ISF_worst_dimension": h3,
            "H4_controller_predicts_quality": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
        "population_summary": {
            "median_overall_score": round(float(np.median(overall_scores)), 1)
            if overall_scores else None,
            "mean_overall_score": round(float(np.mean(overall_scores)), 1)
            if overall_scores else None,
            "grade_distribution": grade_dist,
        },
        "per_patient": rows,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    print(f"\n✓ Results saved to {OUT_JSON}")

    v = results["verdict_summary"]
    print(f"\nVerdict: H1={v['H1']} H2={v['H2']} H3={v['H3']} H4={v['H4']}")
    return results


if __name__ == "__main__":
    main()
