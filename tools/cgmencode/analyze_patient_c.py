"""Patient C demonstration analysis using the new production tooling.

Runs the full production pipeline against patient C's grid data and
overlays the new Wave-12/13 facts loaders (correction-denominator ISF,
controller dynamics, basal mismatch, ISF-gap bootstrap). Side questions
addressed by this script:

  1. Per-patient EGP — feasible? does it help on patient C?
  2. Meal isolation thresholds — does the production 5g/10g/30g ladder
     pass the 2-8 meals/day smell test for patient C? Should the
     "substantial meal" floor be 50 g?

Outputs:
  reports/patient-c-analysis/
    plots/             — visualizations
    facts.json         — raw facts dump
    pipeline.json      — pipeline result excerpts
    meal_audit.csv     — per-day meal counts at each carb floor

The companion markdown report (PATIENT-C-REPORT.md) cites these.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "reports" / "patient-c-analysis"
PLOT_DIR = OUT / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────
# 1. Load patient C grid
# ─────────────────────────────────────────────────────────────────────

GRID_PATH = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
print(f"Loading {GRID_PATH} ...")
df_all = pd.read_parquet(GRID_PATH)
df = df_all[df_all["patient_id"] == "c"].copy()
df = df.sort_values("time").reset_index(drop=True)
print(f"Patient c: {len(df):,} rows over "
      f"{(df['time'].max() - df['time'].min()).total_seconds() / 86400:.1f} days")


# ─────────────────────────────────────────────────────────────────────
# 2. Glycemic summary
# ─────────────────────────────────────────────────────────────────────

g = df["glucose"].dropna()
glycemic = {
    "n_readings":    int(g.count()),
    "mean_mgdl":     float(g.mean()),
    "std_mgdl":      float(g.std()),
    "cv_pct":        float(100 * g.std() / g.mean()),
    "tir_70_180":    float(((g >= 70) & (g <= 180)).mean()),
    "tbr_lt70":      float((g < 70).mean()),
    "tbr_lt54":      float((g < 54).mean()),
    "tar_gt180":     float((g > 180).mean()),
    "tar_gt250":     float((g > 250).mean()),
    "ea1c_gmi_pct":  float(3.31 + 0.02392 * g.mean()),
}
print("\nGlycemic summary:")
for k, v in glycemic.items():
    if isinstance(v, float):
        print(f"  {k:14s} {v:.3f}" if v < 10 else f"  {k:14s} {v:.1f}")


# ─────────────────────────────────────────────────────────────────────
# 3. Pull facts from new + existing factloaders
# ─────────────────────────────────────────────────────────────────────

from tools.cgmencode.production.controller_dynamics_facts_loader import (
    ControllerDynamicsFactsLoader,
)
from tools.cgmencode.production.basal_mismatch_facts_loader import (
    BasalMismatchFactsLoader,
)
from tools.cgmencode.production.isf_gap_facts_loader import (
    IsfGapFactsLoader,
)
from tools.cgmencode.production.recovery_facts_loader import (
    RecoveryFactsLoader,
)
from tools.cgmencode.production.phenotype_facts_loader import (
    PhenotypeFactsLoader,
)

ctrl = ControllerDynamicsFactsLoader().lookup("c")
basal = BasalMismatchFactsLoader().lookup("c")
isfg = IsfGapFactsLoader().lookup("c")
try:
    recov = RecoveryFactsLoader().lookup("c")
except Exception:
    recov = None
try:
    phen = PhenotypeFactsLoader().lookup("c")
except Exception:
    phen = None

facts = {
    "controller_dynamics_EXP_2753": ctrl.__dict__,
    "basal_mismatch_EXP_2869":      basal.__dict__,
    "isf_gap_EXP_2861":             isfg.__dict__,
    "recovery_EXP_2862":            recov.__dict__ if recov else None,
    "phenotype":                    phen.__dict__ if phen else None,
}
print("\nFacts loaders:")
print(json.dumps(facts, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────────
# 4. Run production pipeline
# ─────────────────────────────────────────────────────────────────────

from tools.cgmencode.production.types import PatientData, PatientProfile
from tools.cgmencode.production.pipeline import run_pipeline

# Build profile from settings parquet
SETTINGS = REPO / "externals" / "ns-parquet" / "training" / "settings.parquet"
sett = pd.read_parquet(SETTINGS)
sett_c = sett[sett["patient_id"] == "c"]
print(f"\nSettings rows for c: {len(sett_c)}")

# Use median scheduled values from grid as profile
isf_median = float(df["scheduled_isf"].median())
cr_median = float(df["scheduled_cr"].median())
basal_median = float(df["scheduled_basal_rate"].median())

profile = PatientProfile(
    isf_schedule=[{"time": "00:00", "value": isf_median}],
    cr_schedule=[{"time": "00:00", "value": cr_median}],
    basal_schedule=[{"time": "00:00", "value": basal_median}],
    dia_hours=5.0,
)

# Build PatientData
ts_ms = (df["time"].astype("int64") // 1_000_000).to_numpy()
patient = PatientData(
    glucose=df["glucose"].to_numpy(dtype=float),
    timestamps=ts_ms,
    profile=profile,
    iob=df["iob"].to_numpy(dtype=float) if "iob" in df else None,
    cob=df["cob"].to_numpy(dtype=float) if "cob" in df else None,
    bolus=df["bolus"].to_numpy(dtype=float) if "bolus" in df else None,
    carbs=df["carbs"].to_numpy(dtype=float) if "carbs" in df else None,
    basal_rate=df["actual_basal_rate"].to_numpy(dtype=float),
    patient_id="c",
)

print(f"PatientData: {patient.days_of_data:.1f} days, "
      f"insulin={patient.has_insulin_data}")
print("Running pipeline ...")
result = run_pipeline(patient)

# Excerpt key fields
def _safe(o):
    if hasattr(o, "__dict__"):
        return {k: _safe(v) for k, v in o.__dict__.items()
                if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_safe(x) for x in o[:20]]
    if isinstance(o, dict):
        return {k: _safe(v) for k, v in o.items()}
    if isinstance(o, np.ndarray):
        return f"<array shape={o.shape}>"
    if hasattr(o, "value"):  # Enum
        return o.value
    if isinstance(o, (int, float, str, bool, type(None))):
        return o
    return str(o)

pipe_dump = _safe(result)
print(f"\nPipeline returned {len(getattr(result, 'recommendations', []) or [])} recommendations")


# ─────────────────────────────────────────────────────────────────────
# 5. Per-patient EGP estimation (Wave-10/11 fasting-drift method)
# ─────────────────────────────────────────────────────────────────────
#
# Identify clean fasting equilibrium windows and solve for the EGP rate
# that the controller is balancing against. This is a minimum-viable
# version of EXP-2739; safe because it is read-only (we only report the
# value, we do NOT replace _BASE_EGP).

print("\n" + "─" * 70)
print("PER-PATIENT EGP ANALYSIS (read-only, EXP-2739 method)")
print("─" * 70)

# Filter rows: clean fasting + equilibrium
fasting = df[
    (df["cob"].fillna(0) == 0)
    & (df["time_since_carb_min"].fillna(99999) >= 240)
    & (df["time_since_bolus_min"].fillna(99999) >= 240)
    & (df["exercise_active"].fillna(False) == False)  # noqa: E712
    & (df["override_active"].fillna(False) == False)  # noqa: E712
].copy()
print(f"Clean fasting rows: {len(fasting):,} ({100*len(fasting)/len(df):.1f}%)")

equilib = fasting[fasting["glucose_roc"].abs() <= 0.5].copy()
print(f"After equilibrium filter: {len(equilib):,} "
      f"({100*len(equilib)/len(df):.1f}%)")

# In equilibrium: by definition glucose change ≈ 0, so EGP ≈ insulin sink.
# A simple proxy: median glucose_roc *without* the equilibrium filter
# during very-low-IOB pure-fasting windows ⇒ uncovered EGP.
deep_fasting = fasting[fasting["iob"].fillna(0) < 0.5]
print(f"Deep-fasting (iob<0.5U): {len(deep_fasting):,}")
# glucose_roc is mg/dL per 5 min (per tools/ns2parquet/schemas.py:202)
egp_per_5min = float(deep_fasting["glucose_roc"].median()) if len(deep_fasting) else float("nan")

# Also: report basal multiplier the controller settled on during equilibrium
mult_during_equilib = (
    equilib["actual_basal_rate"].astype(float)
    / equilib["scheduled_basal_rate"].astype(float).replace(0, np.nan)
).dropna()
mult_med = float(mult_during_equilib.median()) if len(mult_during_equilib) else float("nan")

# Population EGP from EXP-2739 for context
POP_EGP_MGDL_PER_5MIN = 1.5  # _BASE_EGP in metabolic_engine.py
print(f"\nPopulation EGP (production constant): {POP_EGP_MGDL_PER_5MIN:.2f} mg/dL / 5min")
print(f"Patient C deep-fasting glucose_roc median (low IOB): "
      f"{egp_per_5min:.4f} mg/dL per 5 min  (population _BASE_EGP=1.5)")
print(f"Controller basal multiplier in equilibrium: {mult_med:.3f}")
print(f"  (median actual_basal / scheduled_basal during equilibrium)")
print(f"  i.e. controller delivers {mult_med*100:.0f}% of scheduled basal "
      f"to maintain equilibrium → suggests {(1-mult_med)*100:.0f}% basal headroom")

per_patient_egp = {
    "method": "EXP-2739 fasting-drift, deep-fasting subset",
    "population_egp_mgdl_per_5min": POP_EGP_MGDL_PER_5MIN,
    "patient_c_glucose_roc_mgdl_per_5min_lowiob": egp_per_5min,
    "patient_c_egp_proxy_mgdl_per_5min": float(egp_per_5min),
    "patient_c_equilib_basal_multiplier_median": mult_med,
    "n_deep_fasting_rows": int(len(deep_fasting)),
    "n_equilib_rows": int(len(equilib)),
    "interpretation": (
        f"Patient C's controller suspends to {mult_med*100:.0f}% of scheduled "
        "basal in fasting equilibrium, which is consistent with EXP-2865 "
        "basal-mismatch findings. Per-patient EGP could be back-solved as: "
        "EGP = scheduled_basal × ISF × mult_to_balance_drift. "
        "This is FEASIBLE but not yet productionized — the safety margin "
        "doctrine (EXP-2738) requires it be exposed via a facts loader, "
        "not swapped into _BASE_EGP."
    ),
}


# ─────────────────────────────────────────────────────────────────────
# 6. Meal-isolation smell test (≥5g vs ≥10g vs ≥30g vs ≥50g floor)
# ─────────────────────────────────────────────────────────────────────

print("\n" + "─" * 70)
print("MEAL-ISOLATION SMELL TEST (per-day count at each floor)")
print("─" * 70)

carb_events = df[df["carbs"].fillna(0) > 0][["time", "carbs"]].copy()
carb_events["date"] = pd.to_datetime(carb_events["time"]).dt.date
carb_events["hour"] = pd.to_datetime(carb_events["time"]).dt.hour

floors = [5, 10, 20, 30, 50]
audit_rows = []
for floor in floors:
    eligible = carb_events[carb_events["carbs"] >= floor]
    per_day = eligible.groupby("date").size()
    audit_rows.append({
        "floor_g":          floor,
        "n_events":         int(len(eligible)),
        "events_per_day":   float(per_day.mean()) if len(per_day) else 0.0,
        "median_per_day":   float(per_day.median()) if len(per_day) else 0.0,
        "max_per_day":      int(per_day.max()) if len(per_day) else 0,
        "n_days_with_meal": int(len(per_day)),
        "n_days_with_2to8": int(((per_day >= 2) & (per_day <= 8)).sum()),
        "evening_share_pct": float(100 * (eligible["hour"] >= 18).mean())
                              if len(eligible) else 0.0,
    })

audit = pd.DataFrame(audit_rows)
print(audit.to_string(index=False))
audit.to_csv(OUT / "meal_audit.csv", index=False)

# Smell test: for each floor, is the patient in 2-8 events/day?
total_days = (df["time"].max() - df["time"].min()).total_seconds() / 86400
smell = {}
for r in audit_rows:
    smell[f"{r['floor_g']}g"] = {
        "events_per_day": r["events_per_day"],
        "passes_2to8":    2 <= r["events_per_day"] <= 8,
        "share_of_days_in_2to8":
            r["n_days_with_2to8"] / total_days if total_days else 0.0,
    }

print("\nDoes patient C have 2-8 meal events/day at each floor?")
for k, v in smell.items():
    flag = "✅" if v["passes_2to8"] else "❌"
    print(f"  ≥{k:>4s}: {v['events_per_day']:5.2f}/day  "
          f"in 2-8 on {v['share_of_days_in_2to8']*100:5.1f}% of days  {flag}")


# ─────────────────────────────────────────────────────────────────────
# 7. Visualizations
# ─────────────────────────────────────────────────────────────────────

print("\nGenerating plots ...")

# 7a. AGP-style daily distribution
plt.figure(figsize=(10, 4.5))
df["hour_frac"] = pd.to_datetime(df["time"]).dt.hour + pd.to_datetime(df["time"]).dt.minute / 60.0
hourly = df.groupby(pd.cut(df["hour_frac"], bins=np.arange(0, 24.5, 0.5), include_lowest=True))["glucose"]
agp = hourly.agg([
    ("p10", lambda x: x.quantile(0.10)),
    ("p25", lambda x: x.quantile(0.25)),
    ("p50", lambda x: x.quantile(0.50)),
    ("p75", lambda x: x.quantile(0.75)),
    ("p90", lambda x: x.quantile(0.90)),
])
hours = np.arange(0, 24, 0.5) + 0.25
plt.fill_between(hours, agp["p10"], agp["p90"], alpha=0.2, label="10–90%")
plt.fill_between(hours, agp["p25"], agp["p75"], alpha=0.4, label="25–75%")
plt.plot(hours, agp["p50"], "k-", lw=2, label="median")
plt.axhspan(70, 180, color="green", alpha=0.06)
plt.axhline(70, color="orange", lw=1, ls="--")
plt.axhline(180, color="orange", lw=1, ls="--")
plt.xlabel("Hour of day")
plt.ylabel("Glucose (mg/dL)")
plt.title(f"Patient C — AGP (180 days, TIR={glycemic['tir_70_180']*100:.1f}%, eA1c={glycemic['ea1c_gmi_pct']:.1f}%)")
plt.xlim(0, 24)
plt.ylim(40, 350)
plt.legend(loc="upper right", fontsize=8)
plt.tight_layout()
plt.savefig(PLOT_DIR / "01_agp.png", dpi=120)
plt.close()

# 7b. Controller dynamics donut
plt.figure(figsize=(7, 5))
labels = ["User bolus", "Controller SMB", "Excess basal"]
sizes = [
    ctrl.mean_correction_fraction or 0,
    ctrl.mean_smb_fraction or 0,
    ctrl.mean_excess_basal_fraction or 0,
]
colors = ["#3b82f6", "#ef4444", "#a78bfa"]
plt.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, wedgeprops={"linewidth": 2, "edgecolor": "white"})
plt.title(f"Patient C: Insulin Channel Mix (Wave-13 EXP-2753)\n"
          f"controller={ctrl.controller_type}, n_events={ctrl.n_events}")
plt.tight_layout()
plt.savefig(PLOT_DIR / "02_controller_donut.png", dpi=120)
plt.close()

# 7c. ISF reconciliation bar
plt.figure(figsize=(8, 4.5))
labels2 = ["Profile ISF", "Correction-denom ISF\n(Wave-12 / EXP-2741)"]
values = [ctrl.isf_profile_median or 0, ctrl.isf_corr_denom_median or 0]
bars = plt.bar(labels2, values, color=["#94a3b8", "#10b981"], width=0.55)
for b, v in zip(bars, values):
    plt.text(b.get_x() + b.get_width()/2, b.get_height() + 2,
             f"{v:.1f} mg/dL/U", ha="center", fontsize=10, fontweight="bold")
gap = (ctrl.isf_corr_denom_median or 0) - (ctrl.isf_profile_median or 0)
plt.title(f"Patient C ISF Reconciliation — observed overshoots profile by "
          f"{gap:+.0f} mg/dL/U\n"
          f"gap_closure={ctrl.corr_denom_gap_closure:.2f} (negative ⇒ "
          f"observed > profile)")
plt.ylabel("ISF (mg/dL per Unit)")
plt.tight_layout()
plt.savefig(PLOT_DIR / "03_isf_reconciliation.png", dpi=120)
plt.close()

# 7d. Basal pattern (scheduled vs actual, hourly)
plt.figure(figsize=(10, 4))
hourly_basal = df.groupby(df["hour_frac"].round().astype(int)).agg(
    sched=("scheduled_basal_rate", "median"),
    actual=("actual_basal_rate", "median"),
)
plt.step(hourly_basal.index, hourly_basal["sched"], where="post",
         lw=2, label="Scheduled basal", color="#94a3b8")
plt.step(hourly_basal.index, hourly_basal["actual"], where="post",
         lw=2, label="Actual basal (Loop)", color="#ef4444")
plt.axhline(0, color="black", lw=0.5)
plt.xlim(0, 23)
plt.xlabel("Hour")
plt.ylabel("U/h (median)")
plt.title(f"Patient C: Loop suspends basal almost continuously\n"
          f"(p_basal_mismatch={basal.p_basal_mismatch:.2f}, "
          f"recommended_mult={basal.median_recommended_mult:.2f} — TRIAGE only)")
plt.legend()
plt.tight_layout()
plt.savefig(PLOT_DIR / "04_basal_pattern.png", dpi=120)
plt.close()

# 7e. Meal floor smell test
plt.figure(figsize=(9, 4.5))
fl = audit["floor_g"].astype(int).astype(str) + " g"
ax1 = plt.gca()
ax1.bar(fl, audit["events_per_day"], color="#3b82f6", alpha=0.7,
        label="Mean events/day")
ax1.axhspan(2, 8, color="green", alpha=0.1, label="2–8 / day target")
ax1.set_ylabel("Mean events / day", color="#3b82f6")
ax1.set_xlabel("Carb-event floor (g)")
ax1.set_title("Patient C: meal-isolation floor sensitivity\n"
              "(production uses 5g/10g/30g; 50g would exclude all but "
              f"{audit.iloc[-1]['n_events']} events in 180 days)")
ax2 = ax1.twinx()
ax2.plot(fl, audit["evening_share_pct"], "ro-", lw=2, label="% events ≥18:00")
ax2.set_ylabel("% events in evening (≥18:00)", color="red")
ax2.set_ylim(0, 100)
ax1.legend(loc="upper right")
plt.tight_layout()
plt.savefig(PLOT_DIR / "05_meal_floors.png", dpi=120)
plt.close()

# 7f. Per-patient EGP comparison
plt.figure(figsize=(8, 4))
labels3 = ["Population EGP\n(_BASE_EGP)", "Patient C estimate\n(deep-fasting glucose_roc)"]
egp_vals = [POP_EGP_MGDL_PER_5MIN, egp_per_5min]
plt.bar(labels3, egp_vals, color=["#94a3b8", "#0ea5e9"], width=0.5)
for i, v in enumerate(egp_vals):
    plt.text(i, v + 0.05 if v >= 0 else v - 0.15,
             f"{v:+.2f} mg/dL / 5min", ha="center", fontweight="bold")
plt.axhline(0, color="black", lw=0.5)
plt.title(f"Patient C: per-patient EGP vs population (EXP-2739 method)\n"
          f"controller-equilibrium basal multiplier = {mult_med:.2f}")
plt.ylabel("EGP (mg/dL per 5 min)")
plt.tight_layout()
plt.savefig(PLOT_DIR / "06_per_patient_egp.png", dpi=120)
plt.close()

print(f"  → {len(list(PLOT_DIR.glob('*.png')))} plots written to {PLOT_DIR}")


# ─────────────────────────────────────────────────────────────────────
# 8. Persist machine-readable outputs
# ─────────────────────────────────────────────────────────────────────

with (OUT / "facts.json").open("w") as f:
    json.dump({
        "patient_id": "c",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "glycemic_summary": glycemic,
        "facts_loaders": {
            k: (v if isinstance(v, dict) else (v.__dict__ if v else None))
            for k, v in facts.items()
        },
        "per_patient_egp": per_patient_egp,
        "meal_floor_audit": audit_rows,
        "meal_smell_test": smell,
    }, f, indent=2, default=str)

with (OUT / "pipeline.json").open("w") as f:
    json.dump(pipe_dump, f, indent=2, default=str)

print(f"\n✅ Done. Outputs in {OUT}")
