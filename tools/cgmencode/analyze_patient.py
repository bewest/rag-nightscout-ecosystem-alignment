"""Unified production-pipeline analyzer for any parquet-ingested patient.

This is the single source of truth that supersedes:
  - tools/cgmencode/analyze_patient_c.py  (now a thin wrapper)
  - tools/cgmencode/run_private_report.py (now a thin wrapper)

Inputs
------
  --patient-id    Patient ID as it appears in `grid.parquet["patient_id"]`
  --parquet-dir   Directory containing entries/treatments/devicestatus/
                  profiles/grid parquet files (default training cohort)
  --output        Output directory for reports/plots (default
                  `reports/{patient_id}-analysis/`)

Behaviour
---------
1. Loads the patient's grid + profile + settings.
2. Pulls Wave-12/13 facts (if available for this patient — facts loaders
   currently only have data for the trained cohort a-k).  Missing facts
   are skipped with a warning.
3. Runs `production.pipeline.run_pipeline()` for advisor/recommender/
   clinical-rules output.
4. Computes per-patient EGP, meal-isolation smell test, and clinical
   summary.
5. Renders a markdown clinical report + JSON facts + AGP / channel-mix /
   ISF / basal / meal-floor / EGP plots.

Examples
--------
  # Patient C (training cohort)
  python -m tools.cgmencode.analyze_patient --patient-id c

  # Live personal data (after `ns2parquet convert` ran)
  python -m tools.cgmencode.analyze_patient \
      --patient-id live-recent \
      --parquet-dir externals/ns-parquet/live-recent \
      --output externals/ns-data/live-recent/reports
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _safe(o):
    """Recursive dataclass / object → dict converter for JSON dumps."""
    if hasattr(o, "__dict__"):
        return {k: _safe(v) for k, v in o.__dict__.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_safe(x) for x in o[:20]]
    if isinstance(o, dict):
        return {k: _safe(v) for k, v in o.items()}
    if isinstance(o, np.ndarray):
        return f"<array shape={o.shape}>"
    if hasattr(o, "value"):
        return o.value
    if isinstance(o, (int, float, str, bool, type(None))):
        return o
    return str(o)


def _try_lookup(loader_cls, patient_id, label):
    try:
        return loader_cls().lookup(patient_id)
    except Exception as e:
        print(f"  [skip {label}: {e}]")
        return None


def analyze(patient_id: str, parquet_dir: Path, out_dir: Path) -> dict:
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load grid ─────────────────────────────────────────────────
    grid_path = parquet_dir / "grid.parquet"
    print(f"Loading {grid_path} ...")
    df_all = pd.read_parquet(grid_path)
    df = df_all[df_all["patient_id"] == patient_id].copy()
    if df.empty:
        raise SystemExit(
            f"No rows for patient_id='{patient_id}' in {grid_path}. "
            f"Available: {sorted(df_all['patient_id'].unique())[:20]}"
        )
    df = df.sort_values("time").reset_index(drop=True)
    days = (df["time"].max() - df["time"].min()).total_seconds() / 86400
    print(f"Patient {patient_id}: {len(df):,} rows over {days:.1f} days")

    # ── 2. Glycemic summary ──────────────────────────────────────────
    g = df["glucose"].dropna()
    glycemic = {
        "n_readings": int(g.count()),
        "mean_mgdl": float(g.mean()),
        "std_mgdl": float(g.std()),
        "cv_pct": float(100 * g.std() / g.mean()),
        "tir_70_180": float(((g >= 70) & (g <= 180)).mean()),
        "tbr_lt70": float((g < 70).mean()),
        "tbr_lt54": float((g < 54).mean()),
        "tar_gt180": float((g > 180).mean()),
        "tar_gt250": float((g > 250).mean()),
        "ea1c_gmi_pct": float(3.31 + 0.02392 * g.mean()),
    }
    print("Glycemic:", {k: round(v, 3) for k, v in glycemic.items()})

    # ── 3. Facts loaders (gracefully skip if patient absent) ─────────
    from tools.cgmencode.production.controller_dynamics_facts_loader import (
        ControllerDynamicsFactsLoader,
    )
    from tools.cgmencode.production.basal_mismatch_facts_loader import (
        BasalMismatchFactsLoader,
    )
    from tools.cgmencode.production.isf_gap_facts_loader import IsfGapFactsLoader
    from tools.cgmencode.production.recovery_facts_loader import RecoveryFactsLoader
    from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

    print("\nFacts loaders ...")
    ctrl = _try_lookup(ControllerDynamicsFactsLoader, patient_id, "controller_dynamics")
    basal = _try_lookup(BasalMismatchFactsLoader, patient_id, "basal_mismatch")
    isfg = _try_lookup(IsfGapFactsLoader, patient_id, "isf_gap")
    recov = _try_lookup(RecoveryFactsLoader, patient_id, "recovery")
    phen = _try_lookup(PhenotypeFactsLoader, patient_id, "phenotype")

    facts = {
        "controller_dynamics_EXP_2753": ctrl.__dict__ if ctrl else None,
        "basal_mismatch_EXP_2869": basal.__dict__ if basal else None,
        "isf_gap_EXP_2861": isfg.__dict__ if isfg else None,
        "recovery_EXP_2862": recov.__dict__ if recov else None,
        "phenotype": phen.__dict__ if phen else None,
    }

    # ── 4. Build PatientData and run the production pipeline ─────────
    from tools.cgmencode.production.types import PatientData, PatientProfile
    from tools.cgmencode.production.pipeline import run_pipeline

    isf_median = float(df["scheduled_isf"].median())
    cr_median = float(df["scheduled_cr"].median())
    basal_median = float(df["scheduled_basal_rate"].median())

    patient_tz = "UTC"
    profiles_path = parquet_dir / "profiles.parquet"
    if profiles_path.exists():
        try:
            pdf = pd.read_parquet(profiles_path, columns=["patient_id", "timezone"])
            tz_rows = pdf.loc[pdf["patient_id"] == patient_id, "timezone"].dropna()
            if len(tz_rows):
                patient_tz = str(tz_rows.iloc[0])
        except Exception as e:
            print(f"  [tz lookup failed: {e}]")
    print(f"Profile timezone: {patient_tz}")

    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": isf_median}],
        cr_schedule=[{"time": "00:00", "value": cr_median}],
        basal_schedule=[{"time": "00:00", "value": basal_median}],
        dia_hours=5.0,
        timezone=patient_tz,
    )

    ts_ms = df["time"].astype("int64").to_numpy()
    patient = PatientData(
        glucose=df["glucose"].to_numpy(dtype=float),
        timestamps=ts_ms,
        profile=profile,
        iob=df["iob"].to_numpy(dtype=float) if "iob" in df else None,
        cob=df["cob"].to_numpy(dtype=float) if "cob" in df else None,
        bolus=df["bolus"].to_numpy(dtype=float) if "bolus" in df else None,
        carbs=df["carbs"].to_numpy(dtype=float) if "carbs" in df else None,
        basal_rate=df["actual_basal_rate"].to_numpy(dtype=float)
        if "actual_basal_rate" in df
        else None,
        patient_id=patient_id,
    )
    print(f"PatientData: {patient.days_of_data:.1f} days, "
          f"insulin={patient.has_insulin_data}")
    print("Running pipeline ...")
    result = run_pipeline(patient)
    pipe_dump = _safe(result)
    n_recs = len(getattr(result, "recommendations", []) or [])
    print(f"  {n_recs} recommendation(s)")

    qc = getattr(result, "meal_logging_qc", None)
    if qc is not None:
        print(f"\nMeal-QC flag={qc.flag}  "
              f"logged={qc.n_logged} ({qc.logged_per_day:.2f}/day)  "
              f"inferred={qc.n_inferred} ({qc.inferred_per_day:.2f}/day)")

    # ── 5. Per-patient EGP estimate (read-only EXP-2739) ─────────────
    print("\nPer-patient EGP ...")
    fasting = df[
        (df["cob"].fillna(0) == 0)
        & (df["time_since_carb_min"].fillna(99999) >= 240)
        & (df["time_since_bolus_min"].fillna(99999) >= 240)
        & (df["exercise_active"].fillna(False) == False)  # noqa: E712
        & (df["override_active"].fillna(False) == False)  # noqa: E712
    ].copy()
    equilib = fasting[fasting["glucose_roc"].abs() <= 0.5].copy()
    deep_fasting = fasting[fasting["iob"].fillna(0) < 0.5]
    egp_per_5min = (
        float(deep_fasting["glucose_roc"].median()) if len(deep_fasting) else float("nan")
    )
    mult_during_equilib = (
        equilib["actual_basal_rate"].astype(float)
        / equilib["scheduled_basal_rate"].astype(float).replace(0, np.nan)
    ).dropna()
    mult_med = float(mult_during_equilib.median()) if len(mult_during_equilib) else float("nan")
    POP_EGP = 1.5
    per_patient_egp = {
        "method": "EXP-2739 fasting-drift, deep-fasting subset",
        "population_egp_mgdl_per_5min": POP_EGP,
        "patient_glucose_roc_lowiob_mgdl_per_5min": egp_per_5min,
        "controller_equilib_basal_multiplier": mult_med,
        "n_deep_fasting_rows": int(len(deep_fasting)),
        "n_equilib_rows": int(len(equilib)),
    }
    print(f"  EGP_proxy={egp_per_5min:.3f} mg/dL/5min (pop={POP_EGP:.2f}); "
          f"basal_mult_equilib={mult_med:.2f}")

    # ── 6. Meal-isolation smell test ─────────────────────────────────
    carb_events = df[df["carbs"].fillna(0) > 0][["time", "carbs"]].copy()
    carb_events["date"] = pd.to_datetime(carb_events["time"]).dt.date
    carb_events["hour"] = pd.to_datetime(carb_events["time"]).dt.hour
    audit_rows = []
    for floor in [5, 10, 20, 30, 50]:
        eligible = carb_events[carb_events["carbs"] >= floor]
        per_day = eligible.groupby("date").size()
        audit_rows.append({
            "floor_g": floor,
            "n_events": int(len(eligible)),
            "events_per_day": float(per_day.mean()) if len(per_day) else 0.0,
            "n_days_with_meal": int(len(per_day)),
            "n_days_with_2to8": int(((per_day >= 2) & (per_day <= 8)).sum()),
            "evening_share_pct": (
                float(100 * (eligible["hour"] >= 18).mean()) if len(eligible) else 0.0
            ),
        })
    audit = pd.DataFrame(audit_rows)
    audit.to_csv(out_dir / "meal_audit.csv", index=False)
    smell = {
        f"{r['floor_g']}g": {
            "events_per_day": r["events_per_day"],
            "passes_2to8": 2 <= r["events_per_day"] <= 8,
        }
        for r in audit_rows
    }

    # ── 7. Plots ─────────────────────────────────────────────────────
    print("\nPlots ...")

    # 7a. AGP
    df["hour_frac"] = (
        pd.to_datetime(df["time"]).dt.hour
        + pd.to_datetime(df["time"]).dt.minute / 60.0
    )
    hourly = df.groupby(
        pd.cut(df["hour_frac"], bins=np.arange(0, 24.5, 0.5), include_lowest=True)
    )["glucose"]
    agp = hourly.agg([
        ("p10", lambda x: x.quantile(0.10)),
        ("p25", lambda x: x.quantile(0.25)),
        ("p50", lambda x: x.quantile(0.50)),
        ("p75", lambda x: x.quantile(0.75)),
        ("p90", lambda x: x.quantile(0.90)),
    ])
    hours = np.arange(0, 24, 0.5) + 0.25
    plt.figure(figsize=(10, 4.5))
    plt.fill_between(hours, agp["p10"], agp["p90"], alpha=0.2, label="10–90%")
    plt.fill_between(hours, agp["p25"], agp["p75"], alpha=0.4, label="25–75%")
    plt.plot(hours, agp["p50"], "k-", lw=2, label="median")
    plt.axhspan(70, 180, color="green", alpha=0.06)
    plt.axhline(70, color="orange", lw=1, ls="--")
    plt.axhline(180, color="orange", lw=1, ls="--")
    plt.xlabel("Hour of day"); plt.ylabel("Glucose (mg/dL)")
    plt.title(f"{patient_id} — AGP ({days:.0f}d, "
              f"TIR={glycemic['tir_70_180']*100:.1f}%, "
              f"GMI={glycemic['ea1c_gmi_pct']:.1f}%)")
    plt.xlim(0, 24); plt.ylim(40, 350); plt.legend(loc="upper right", fontsize=8)
    plt.tight_layout(); plt.savefig(plot_dir / "01_agp.png", dpi=120); plt.close()

    # 7b. Controller dynamics donut (only if facts populated)
    ctrl_has_data = ctrl is not None and any(
        v not in (None, 0)
        for v in (
            ctrl.mean_correction_fraction,
            ctrl.mean_smb_fraction,
            ctrl.mean_excess_basal_fraction,
        )
    )
    if ctrl_has_data:
        plt.figure(figsize=(7, 5))
        sizes = [
            ctrl.mean_correction_fraction or 0,
            ctrl.mean_smb_fraction or 0,
            ctrl.mean_excess_basal_fraction or 0,
        ]
        plt.pie(
            sizes,
            labels=["User bolus", "Controller SMB", "Excess basal"],
            colors=["#3b82f6", "#ef4444", "#a78bfa"],
            autopct="%1.1f%%", startangle=90,
            wedgeprops={"linewidth": 2, "edgecolor": "white"},
        )
        plt.title(f"{patient_id}: Insulin Channel Mix\n"
                  f"controller={ctrl.controller_type}, n_events={ctrl.n_events}")
        plt.tight_layout()
        plt.savefig(plot_dir / "02_controller_donut.png", dpi=120); plt.close()

    # 7c. ISF reconciliation bar (only if facts populated)
    isf_has_data = ctrl is not None and (
        ctrl.isf_profile_median or ctrl.isf_corr_denom_median
    )
    if isf_has_data:
        plt.figure(figsize=(8, 4.5))
        values = [ctrl.isf_profile_median or 0, ctrl.isf_corr_denom_median or 0]
        bars = plt.bar(
            ["Profile ISF", "Correction-denom ISF\n(Wave-12 / EXP-2741)"],
            values, color=["#94a3b8", "#10b981"], width=0.55,
        )
        for b, v in zip(bars, values):
            plt.text(b.get_x() + b.get_width()/2, b.get_height() + 2,
                     f"{v:.1f} mg/dL/U", ha="center", fontweight="bold")
        gap = (ctrl.isf_corr_denom_median or 0) - (ctrl.isf_profile_median or 0)
        plt.title(f"{patient_id} ISF reconciliation — observed vs profile {gap:+.0f}")
        plt.ylabel("ISF (mg/dL/U)")
        plt.tight_layout()
        plt.savefig(plot_dir / "03_isf_reconciliation.png", dpi=120); plt.close()

    # 7d. Basal pattern
    if "scheduled_basal_rate" in df and "actual_basal_rate" in df:
        plt.figure(figsize=(10, 4))
        hb = df.groupby(df["hour_frac"].round().astype(int)).agg(
            sched=("scheduled_basal_rate", "median"),
            actual=("actual_basal_rate", "median"),
        )
        plt.step(hb.index, hb["sched"], where="post", lw=2,
                 label="Scheduled", color="#94a3b8")
        plt.step(hb.index, hb["actual"], where="post", lw=2,
                 label="Actual (Loop)", color="#ef4444")
        plt.axhline(0, color="black", lw=0.5); plt.xlim(0, 23)
        plt.xlabel("Hour"); plt.ylabel("U/h (median)")
        title = f"{patient_id}: scheduled vs actual basal"
        if basal and basal.p_basal_mismatch is not None:
            title += (f"\np_basal_mismatch={basal.p_basal_mismatch:.2f}, "
                      f"recommended_mult={basal.median_recommended_mult or 0:.2f}")
        plt.title(title); plt.legend(); plt.tight_layout()
        plt.savefig(plot_dir / "04_basal_pattern.png", dpi=120); plt.close()

    # 7e. Meal floor smell test
    plt.figure(figsize=(9, 4.5))
    fl = audit["floor_g"].astype(int).astype(str) + " g"
    ax1 = plt.gca()
    ax1.bar(fl, audit["events_per_day"], color="#3b82f6", alpha=0.7,
            label="Mean events/day")
    ax1.axhspan(2, 8, color="green", alpha=0.1, label="2–8/day target")
    ax1.set_ylabel("Mean events/day", color="#3b82f6")
    ax1.set_xlabel("Carb-event floor (g)")
    ax1.set_title(f"{patient_id}: meal-isolation floor sensitivity")
    ax2 = ax1.twinx()
    ax2.plot(fl, audit["evening_share_pct"], "ro-", lw=2, label="% events ≥18:00")
    ax2.set_ylabel("% events evening", color="red"); ax2.set_ylim(0, 100)
    ax1.legend(loc="upper right"); plt.tight_layout()
    plt.savefig(plot_dir / "05_meal_floors.png", dpi=120); plt.close()

    # 7f. EGP comparison
    plt.figure(figsize=(8, 4))
    plt.bar(
        ["Population EGP\n(_BASE_EGP)",
         f"{patient_id} estimate\n(deep-fasting glucose_roc)"],
        [POP_EGP, egp_per_5min], color=["#94a3b8", "#0ea5e9"], width=0.5,
    )
    for i, v in enumerate([POP_EGP, egp_per_5min]):
        plt.text(i, v + 0.05 if v >= 0 else v - 0.15,
                 f"{v:+.2f}", ha="center", fontweight="bold")
    plt.axhline(0, color="black", lw=0.5)
    plt.title(f"{patient_id}: per-patient EGP vs population\n"
              f"basal_mult_equilib={mult_med:.2f}")
    plt.ylabel("EGP (mg/dL/5min)")
    plt.tight_layout()
    plt.savefig(plot_dir / "06_per_patient_egp.png", dpi=120); plt.close()

    print(f"  → {len(list(plot_dir.glob('*.png')))} plots written to {plot_dir}")

    # ── 8. Persist machine-readable outputs ──────────────────────────
    payload = {
        "patient_id": patient_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parquet_dir": str(parquet_dir),
        "days_of_data": days,
        "profile_timezone": patient_tz,
        "glycemic_summary": glycemic,
        "facts_loaders": {k: _safe(v) if v else None for k, v in facts.items()},
        "per_patient_egp": per_patient_egp,
        "meal_floor_audit": audit_rows,
        "meal_smell_test": smell,
        "meal_logging_qc": _safe(qc) if qc is not None else None,
    }
    (out_dir / "facts.json").write_text(json.dumps(payload, indent=2, default=str))
    (out_dir / "pipeline.json").write_text(json.dumps(pipe_dump, indent=2, default=str))

    # ── 9. Render markdown clinical report ───────────────────────────
    _render_markdown_report(out_dir, patient_id, payload, result, df)

    print(f"\n✅ Done. Outputs in {out_dir}")
    return payload


def _render_markdown_report(out_dir, patient_id, payload, result, df):
    """Render a markdown clinical report; structure mirrors the previous
    private-report formatter so existing readers remain familiar."""
    g = payload["glycemic_summary"]
    egp = payload["per_patient_egp"]
    smell = payload["meal_smell_test"]
    recs = getattr(result, "recommendations", []) or []
    qc = getattr(result, "meal_logging_qc", None)

    lines = [
        f"# Clinical Analysis Report — patient `{patient_id}`",
        "",
        f"_Generated: {payload['generated_at_utc']}_  ",
        f"_Source parquet: `{payload['parquet_dir']}`_  ",
        f"_Profile timezone: `{payload['profile_timezone']}`_  ",
        f"_Days of data: {payload['days_of_data']:.1f}_",
        "",
        "## 1. Glycemic summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Mean glucose (mg/dL) | {g['mean_mgdl']:.1f} |",
        f"| GMI / eA1c (%) | {g['ea1c_gmi_pct']:.2f} |",
        f"| TIR 70–180 (%) | {g['tir_70_180']*100:.1f} |",
        f"| TBR <70 (%) | {g['tbr_lt70']*100:.2f} |",
        f"| TBR <54 (%) | {g['tbr_lt54']*100:.2f} |",
        f"| TAR >180 (%) | {g['tar_gt180']*100:.1f} |",
        f"| TAR >250 (%) | {g['tar_gt250']*100:.2f} |",
        f"| CV (%) | {g['cv_pct']:.1f} |",
        f"| n readings | {g['n_readings']:,} |",
        "",
        "## 2. Per-patient EGP (read-only)",
        "",
        f"- Method: {egp['method']}",
        f"- Patient glucose_roc (low-IOB fasting): "
        f"**{egp['patient_glucose_roc_lowiob_mgdl_per_5min']:.3f}** mg/dL/5min  "
        f"(population _BASE_EGP={egp['population_egp_mgdl_per_5min']:.2f})",
        f"- Controller basal multiplier in equilibrium: "
        f"**{egp['controller_equilib_basal_multiplier']:.2f}**",
        f"- Sample size: {egp['n_deep_fasting_rows']:,} deep-fasting rows, "
        f"{egp['n_equilib_rows']:,} equilibrium rows",
        "",
        "## 3. Meal-isolation smell test",
        "",
        "| Floor | Events/day | In 2–8 target? |",
        "|---|---|---|",
    ]
    for k, v in smell.items():
        flag = "✅" if v["passes_2to8"] else "❌"
        lines.append(f"| ≥{k} | {v['events_per_day']:.2f} | {flag} |")

    if qc is not None:
        lines += [
            "",
            "## 4. Meal-logging QC",
            "",
            f"- Flag: **{qc.flag}**",
            f"- Logged: {qc.n_logged} ({qc.logged_per_day:.2f}/day)",
            f"- Inferred (rises): {qc.n_inferred} ({qc.inferred_per_day:.2f}/day)",
        ]
        if qc.ratio is not None:
            lines.append(f"- Inferred / logged ratio: {qc.ratio:.2f}")

    lines += ["", "## 5. Recommendations", ""]
    if not recs:
        lines.append("_(none — pipeline produced no actionable recommendations)_")
    for i, rec in enumerate(recs, 1):
        # ActionRecommendation may wrap a SettingsRecommendation; render both.
        if hasattr(rec, "action_type"):
            action = getattr(rec, "action_type", "")
            prio = getattr(rec, "priority", "")
            desc = getattr(rec, "description", "")
            tir = getattr(rec, "predicted_tir_delta", None)
            tir_s = f", predicted TIR Δ {tir*100:+.1f} pp" if tir is not None else ""
            lines.append(f"### Rec {i}: {action} (priority {prio}){tir_s}")
            if desc:
                lines.append(f"- {desc}")
            sr = getattr(rec, "settings_rec", None)
            if sr is not None:
                pname = getattr(sr.parameter, "value", str(sr.parameter))
                cur = getattr(sr, "current_value", None)
                new = getattr(sr, "suggested_value", None)
                mag = getattr(sr, "magnitude_pct", None)
                lines.append(
                    f"- Settings change: **{pname}** {sr.direction} "
                    f"{cur} → {new}"
                    + (f" ({mag:+.0f} %)" if mag is not None else "")
                )
                if sr.rationale:
                    lines.append(f"- Rationale: {sr.rationale}")
        else:
            param_name = getattr(rec.parameter, "value", str(rec.parameter))
            direction = getattr(rec, "direction", "")
            cur = getattr(rec, "current_value", None)
            new = getattr(rec, "suggested_value", None)
            mag = getattr(rec, "magnitude_pct", None)
            delta_tir = getattr(rec, "predicted_tir_delta", None)
            rationale = getattr(rec, "rationale", None)
            lines.append(f"### Rec {i}: {param_name} — {direction}")
            if cur is not None and new is not None:
                mag_s = f" ({mag:+.0f} %)" if mag is not None else ""
                tir_s = (
                    f", predicted TIR Δ {delta_tir*100:+.1f} pp"
                    if delta_tir is not None
                    else ""
                )
                lines.append(f"- {cur} → {new}{mag_s}{tir_s}")
            if rationale:
                lines.append(f"- Rationale: {rationale}")
        lines.append("")

    lines += [
        "## 6. Plots",
        "",
        "- ![AGP](plots/01_agp.png)",
        "- ![Channel mix](plots/02_controller_donut.png)",
        "- ![ISF reconciliation](plots/03_isf_reconciliation.png)",
        "- ![Basal pattern](plots/04_basal_pattern.png)",
        "- ![Meal floors](plots/05_meal_floors.png)",
        "- ![EGP](plots/06_per_patient_egp.png)",
        "",
    ]
    (out_dir / "clinical-report.md").write_text("\n".join(lines))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--patient-id", required=True)
    p.add_argument("--parquet-dir", default=str(REPO / "externals/ns-parquet/training"),
                   help="Directory containing grid.parquet etc.")
    p.add_argument("--output", default=None,
                   help="Output dir (default: reports/{patient_id}-analysis/)")
    args = p.parse_args(argv)
    out_dir = Path(args.output) if args.output else REPO / f"reports/{args.patient_id}-analysis"
    analyze(args.patient_id, Path(args.parquet_dir), out_dir)


if __name__ == "__main__":
    main()
