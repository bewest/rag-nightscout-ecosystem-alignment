"""EXP-3022b — per-patient ISF/CR/basal recommender smell test.

Picks 5 representative patients spanning controllers + phenotypes,
runs the production `run_pipeline()` (which exercises the full advisor
stack including inferred-meal-aware correction events), and emits a
consolidated cross-patient comparison report with embedded plots.

Demonstrates the EXP-3022b deliverable: the production stack already
ships per-patient ISF/CR/basal/correction-threshold recommendations
backed by inferred-meal deconfounding (EXP-3026/3026-EXT), the
phenotype-imputed safety floor (EXP-3027-FIX), and the carb-aware
per-patient (T*, M*) table validated by EXP-3030.

Inputs (frozen):
  externals/ns-parquet/training/grid.parquet
  externals/experiments/exp-3019_phenotype_imputed.parquet
  externals/experiments/inferred_meals_<pid>.parquet  (cached)

Outputs:
  reports/exp-3022b/<pid>/clinical-report.md  (one per patient)
  reports/exp-3022b/<pid>/plots/*.png
  reports/exp-3022b/<pid>/pipeline.json
  docs/60-research/exp-3022b-per-patient-recommender-2026-04-26.md
    (consolidated comparison + smell-test verdict)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cgmencode.analyze_patient import analyze  # noqa: E402

EXP_DIR = REPO / "externals" / "experiments"
NS_DIR = REPO / "externals" / "ns-parquet" / "training"
OUT_DIR = REPO / "reports" / "exp-3022b"

# Five representatives spanning controllers × phenotypes.
# Justification for each pick is documented in the consolidated report.
DEMO_PATIENTS = [
    # Loop_AB_ON, hidden_leverage, well-controlled (per memory: sweet-spot)
    ("g", "Loop_AB_ON", "hidden_leverage / sweet-spot"),
    # Loop_AB_ON, hidden_leverage, hypo-heavy (per memory: outlier)
    ("i", "Loop_AB_ON", "hidden_leverage / hypo outlier"),
    # Loop_AB_OFF, exposed_stacker (open-loop comparison)
    ("a", "Loop_AB_OFF", "exposed_stacker / open-loop"),
    # Trio_oref1, stacker_weak_defense
    ("ns-8f3527d1ee40", "Trio_oref1", "stacker_weak_defense"),
    # AAPS_oref0, lax_braking (extreme braking phenotype)
    ("odc-86025410", "AAPS_oref0", "lax_braking"),
]


def _summarize_recs(result) -> list[dict]:
    """Flatten ActionRecommendation/SettingsRecommendation into a row per rec."""
    rows = []
    for rec in getattr(result, "recommendations", []) or []:
        sr = getattr(rec, "settings_rec", rec)
        param = getattr(sr, "parameter", None)
        param_name = getattr(param, "value", str(param)) if param is not None else None
        rows.append({
            "action_type": getattr(rec, "action_type", None),
            "priority": getattr(rec, "priority", None),
            "parameter": param_name,
            "direction": getattr(sr, "direction", None),
            "current": getattr(sr, "current_value", None),
            "suggested": getattr(sr, "suggested_value", None),
            "magnitude_pct": getattr(sr, "magnitude_pct", None),
            "predicted_tir_delta": getattr(rec, "predicted_tir_delta",
                                           getattr(sr, "predicted_tir_delta", None)),
            "confidence": getattr(sr, "confidence", None),
            "description": (getattr(rec, "description", None)
                            or getattr(sr, "rationale", None) or "")[:200],
        })
    return rows


def _load_phenotype(pid: str) -> dict:
    df = pd.read_parquet(EXP_DIR / "exp-3019_phenotype_imputed.parquet")
    row = df[df["patient_id"] == pid]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "controller": r.get("controller"),
        "algorithm_mode": r.get("algorithm_mode"),
        "archetype": r.get("archetype"),
        "braking_ratio": r.get("braking_ratio"),
        "stack_score": r.get("stack_score"),
        "hypo_fraction": r.get("hypo_fraction"),
        "imputed": bool(r.get("imputed", False)),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []

    for pid, controller_label, phen_label in DEMO_PATIENTS:
        print(f"\n{'='*70}\n[EXP-3022b] {pid}  ({controller_label}, {phen_label})\n{'='*70}")
        out = OUT_DIR / pid
        try:
            payload = analyze(pid, NS_DIR, out)
        except SystemExit as e:
            print(f"  SKIP: {e}")
            continue
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            continue

        phen = _load_phenotype(pid)
        gly = payload["glycemic_summary"]
        # Pipeline result was persisted to pipeline.json by analyze().
        try:
            result_dump = json.loads((out / "pipeline.json").read_text())
        except Exception:
            result_dump = {}
        recs_raw = result_dump.get("recommendations", []) or []
        n_recs = len(recs_raw)

        actionable = [
            r for r in recs_raw
            if r.get("action_type") in
               ("adjust_isf", "adjust_cr", "adjust_basal_rate",
                "adjust_correction_threshold")
        ]
        params_touched = sorted({
            r.get("action_type", "").replace("adjust_", "")
            for r in actionable
        } - {""})

        max_tir = max(
            (float(r.get("predicted_tir_delta") or 0.0) for r in recs_raw),
            default=0.0,
        )

        summary_rows.append({
            "pid": pid,
            "controller_label": controller_label,
            "phenotype_label": phen_label,
            "archetype": phen.get("archetype"),
            "imputed_phenotype": phen.get("imputed"),
            "tir_pct": round(gly["tir_70_180"] * 100, 1),
            "tbr_pct": round(gly["tbr_lt70"] * 100, 2),
            "tar_pct": round(gly["tar_gt180"] * 100, 1),
            "cv_pct": round(gly["cv_pct"], 1),
            "n_recs": n_recs,
            "n_settings_actionable": len(actionable),
            "params_touched": ",".join(params_touched) or "—",
            "max_predicted_tir_delta_pp": round(max_tir, 1),
            "report_path": str((out / "clinical-report.md").relative_to(REPO)),
        })

    sdf = pd.DataFrame(summary_rows)
    sdf.to_csv(OUT_DIR / "summary.csv", index=False)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary_rows, indent=2, default=str))
    print(f"\n[EXP-3022b] summary.csv: {len(sdf)} patients")
    print(sdf.to_string(index=False))

    plot_cross_patient_summary()
    return 0


def plot_cross_patient_summary() -> Path:
    """Cross-patient comparison figure embedded in the consolidated report.

    Renders side-by-side:
      Left: per-patient settings recommendations as ratio (suggested/current)
            for each of (ISF, CR, basal_rate, correction_threshold). Ratio
            of 1.0 = no change. Bars > 1 mean recommend-increase.
      Right: baseline TIR per patient with a 70% reference line.

    Reads `pipeline.json` and `facts.json` from each per-patient output dir;
    must be invoked after `main()` has produced those files.
    """
    out_path = OUT_DIR / "cross_patient_summary.png"
    params = ["isf", "cr", "basal_rate", "correction_threshold"]
    data: dict = {p: {} for p in params}
    labels: list[str] = []
    tirs: list[float] = []
    pids: list[str] = []

    for pid, controller_label, phen_label in DEMO_PATIENTS:
        pj = OUT_DIR / pid / "pipeline.json"
        fj = OUT_DIR / pid / "facts.json"
        if not (pj.exists() and fj.exists()):
            continue
        pipe = json.loads(pj.read_text())
        facts = json.loads(fj.read_text())
        pids.append(pid)
        labels.append(f"{pid}\n{controller_label}\n{phen_label}")
        tirs.append(facts["glycemic_summary"]["tir_70_180"] * 100)
        for r in pipe.get("recommendations", []) or []:
            at = r.get("action_type", "")
            if not at.startswith("adjust_"):
                continue
            param = at[len("adjust_"):]
            if param not in data:
                continue
            sr = r.get("settings_rec") or {}
            cur, new = sr.get("current_value"), sr.get("suggested_value")
            if cur and new and cur != 0:
                data[param][pid] = float(new) / float(cur)

    fig, axes = plt.subplots(
        1, 2, figsize=(14, 5),
        gridspec_kw={"width_ratios": [2, 1]},
    )

    xs = np.arange(len(pids))
    width = 0.20
    colors = {"isf": "#1f77b4", "cr": "#ff7f0e",
              "basal_rate": "#2ca02c", "correction_threshold": "#d62728"}
    for i, p in enumerate(params):
        vals = [data[p].get(pid, 1.0) for pid in pids]
        axes[0].bar(xs + i * width - 1.5 * width, vals, width,
                    label=p, color=colors[p])
    axes[0].axhline(1.0, color="k", linestyle=":", alpha=0.5)
    axes[0].set_xticks(xs)
    axes[0].set_xticklabels(labels, fontsize=7)
    axes[0].set_ylabel("suggested / current  (1.0 = no change)")
    axes[0].set_title(
        "EXP-3022b: per-patient settings recommendations\n"
        "(ratio of suggested to current value; bars > 1.0 = increase)"
    )
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].grid(axis="y", alpha=0.3)
    ymax = max(
        5.0,
        max(max(data[p].values(), default=1.0) for p in data) + 0.5,
    )
    axes[0].set_ylim(0, ymax)

    bar_colors = ["#4daf4a" if t >= 70 else "#ff7f00" for t in tirs]
    axes[1].barh(range(len(labels)), tirs, color=bar_colors)
    axes[1].axvline(70, color="k", linestyle=":", alpha=0.5,
                    label="TIR target = 70%")
    axes[1].set_yticks(range(len(labels)))
    axes[1].set_yticklabels(pids, fontsize=8)
    axes[1].set_xlabel("TIR 70-180 (%)")
    axes[1].set_xlim(0, 100)
    axes[1].set_title("Baseline TIR")
    axes[1].invert_yaxis()
    axes[1].legend(loc="lower right", fontsize=8)
    axes[1].grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"[EXP-3022b] cross-patient figure: {out_path}")
    return out_path


if __name__ == "__main__":
    raise SystemExit(main())
