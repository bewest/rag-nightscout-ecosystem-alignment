#!/usr/bin/env python3
"""EXP-2671: Cross-Controller Data Fidelity Validation.

MOTIVATION: The dataset now spans 31 patients across 3 controller types
(Loop, Trio, OpenAPS) from 3 data sources. Before running cross-system
experiments, we must verify that the ns2parquet pipeline produces
semantically equivalent fields across controllers. Known risks:
  - OpenAPS enacted_rate may be percent-encoded (odc-96254963 confirmed)
  - Loop lacks sensitivity_ratio, eventual_bg (schema difference, not bug)
  - IOB computation semantics differ (exponential vs bilinear decay)
  - Patient j has zero IOB/COB (unknown controller, unusable)

HYPOTHESES:
  H1: Core field distributions (glucose, IOB, bolus) are comparable across
      controllers after accounting for patient-level variation
  H2: Correction event detection produces equivalent event rates across
      controller types (no systematic bias from SMB frequency)
  H3: IOB decay curves match expected DIA profiles per controller
  H4: Enacted rate vs actual basal rate are consistent (no percent encoding)
  H5: Controller-specific fields (sensitivity_ratio, eventual_bg) are
      correctly absent for Loop and present for Trio/OpenAPS

OUTPUTS:
  - visualizations/cross-controller-validation/fig[1-8]_*.png
  - externals/experiments/exp-2671_cross_controller_validation.json
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
DS_PARQUET = Path("externals/ns-parquet/training/devicestatus.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2671_cross_controller_validation.json"
VIZ_DIR = Path("visualizations/cross-controller-validation")
VIZ_DIR.mkdir(parents=True, exist_ok=True)

CTRL_COLORS = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800", "unknown": "#9E9E9E"}
CTRL_ORDER = ["loop", "trio", "openaps"]
STEPS_PER_HOUR = 12
MIN_DOSE = 0.5
MIN_PRE_BG = 120
CARB_EXCLUSION_H = 1.0


# ── Helpers ────────────────────────────────────────────────────────────

def load_data():
    """Load grid + controller map, assign controller per patient."""
    df = pd.read_parquet(PARQUET)
    ds = pd.read_parquet(DS_PARQUET, columns=["patient_id", "controller"])
    ctrl = ds.groupby("patient_id")["controller"].agg(
        lambda x: x.value_counts().index[0]
    )
    df = df.merge(ctrl.rename("controller"), on="patient_id", how="left")
    df["controller"] = df["controller"].fillna("unknown")
    return df


def _tir(glucose_series):
    """Time in range (70-180 mg/dL)."""
    valid = glucose_series.dropna()
    if len(valid) == 0:
        return np.nan
    return 100.0 * ((valid >= 70) & (valid <= 180)).mean()


def _tbr(glucose_series):
    """Time below range (<70 mg/dL)."""
    valid = glucose_series.dropna()
    if len(valid) == 0:
        return np.nan
    return 100.0 * (valid < 70).mean()


def detect_corrections(pdf):
    """Detect correction bolus events in a single patient's data.

    Returns DataFrame of correction events with pre-BG and dose.
    """
    bolus_mask = pdf["bolus"].fillna(0) > MIN_DOSE
    bolus_idx = pdf.index[bolus_mask]
    events = []
    for idx in bolus_idx:
        loc = pdf.index.get_loc(idx)
        if loc < 1:
            continue
        pre_bg = pdf.iloc[loc - 1]["glucose"]
        if pd.isna(pre_bg) or pre_bg < MIN_PRE_BG:
            continue
        # Exclude if carbs within ±1h
        carb_window = CARB_EXCLUSION_H * STEPS_PER_HOUR
        start = max(0, loc - int(carb_window))
        end = min(len(pdf), loc + int(carb_window) + 1)
        carbs_near = pdf.iloc[start:end]["carbs"].fillna(0).sum()
        if carbs_near > 0:
            continue
        dose = pdf.iloc[loc]["bolus"]
        events.append({"time": pdf.iloc[loc]["time"], "pre_bg": pre_bg, "dose": dose})
    return pd.DataFrame(events)


# ── Panel 1: Core Field Distribution Box Plots ────────────────────────

def fig1_field_distributions(df):
    """Box plots of core fields by controller type."""
    fields = [
        ("glucose", "Glucose (mg/dL)"),
        ("iob", "IOB (U)"),
        ("cob", "COB (g)"),
        ("bolus", "Non-zero Bolus (U)"),
        ("net_basal", "Net Basal (U/h)"),
        ("scheduled_isf", "Scheduled ISF"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.ravel()

    results = {}
    for i, (col, label) in enumerate(fields):
        ax = axes[i]
        data_by_ctrl = []
        labels = []
        for ct in CTRL_ORDER:
            sub = df[df.controller == ct][col].dropna()
            if col == "bolus":
                sub = sub[sub > 0]
            if len(sub) > 0:
                data_by_ctrl.append(sub.values)
                labels.append(f"{ct}\n(N={len(sub):,})")

                results[f"{col}_{ct}_mean"] = float(sub.mean())
                results[f"{col}_{ct}_std"] = float(sub.std())
                results[f"{col}_{ct}_n"] = int(len(sub))

        bp = ax.boxplot(data_by_ctrl, labels=labels, patch_artist=True,
                        showfliers=False, whis=[5, 95])
        for j, ct in enumerate(CTRL_ORDER[:len(data_by_ctrl)]):
            bp["boxes"][j].set_facecolor(CTRL_COLORS[ct])
            bp["boxes"][j].set_alpha(0.6)
        ax.set_title(label, fontsize=12, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2671 Panel 1: Core Field Distributions by Controller",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_field_distributions.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig1 saved")
    return results


# ── Panel 2: Per-Patient TIR / TBR by Controller ──────────────────────

def fig2_tir_by_controller(df):
    """Per-patient TIR and TBR, colored by controller."""
    patient_stats = []
    for pid in sorted(df.patient_id.unique()):
        sub = df[df.patient_id == pid]
        ct = sub.controller.iloc[0]
        if ct == "unknown":
            continue
        tir = _tir(sub.glucose)
        tbr = _tbr(sub.glucose)
        n_days = (sub.time.max() - sub.time.min()).total_seconds() / 86400
        patient_stats.append({
            "patient_id": pid, "controller": ct,
            "tir": tir, "tbr": tbr, "days": n_days,
        })
    ps = pd.DataFrame(patient_stats)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    for ct in CTRL_ORDER:
        sub = ps[ps.controller == ct]
        ax1.scatter(sub.days, sub.tir, c=CTRL_COLORS[ct], label=ct,
                    s=80, alpha=0.7, edgecolors="k", linewidths=0.5)
        ax2.scatter(sub.days, sub.tbr, c=CTRL_COLORS[ct], label=ct,
                    s=80, alpha=0.7, edgecolors="k", linewidths=0.5)

    ax1.set_xlabel("Days of Data")
    ax1.set_ylabel("Time in Range (%)")
    ax1.set_title("TIR (70-180) by Controller", fontweight="bold")
    ax1.legend()
    ax1.grid(alpha=0.3)
    ax1.axhline(70, color="green", ls="--", alpha=0.5, label="70% target")

    ax2.set_xlabel("Days of Data")
    ax2.set_ylabel("Time Below Range (%)")
    ax2.set_title("TBR (<70) by Controller", fontweight="bold")
    ax2.legend()
    ax2.grid(alpha=0.3)
    ax2.axhline(4, color="red", ls="--", alpha=0.5, label="4% safety limit")

    fig.suptitle("EXP-2671 Panel 2: Glycemic Outcomes by Controller",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_tir_by_controller.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig2 saved")
    return ps.to_dict("records")


# ── Panel 3: Correction Event Detection Equivalence ───────────────────

def fig3_correction_equivalence(df):
    """Compare correction event rates and profiles across controllers."""
    ctrl_events = {ct: [] for ct in CTRL_ORDER}
    per_patient = []

    for pid in sorted(df.patient_id.unique()):
        sub = df[df.patient_id == pid].copy()
        ct = sub.controller.iloc[0]
        if ct not in CTRL_ORDER:
            continue
        evts = detect_corrections(sub)
        n_days = (sub.time.max() - sub.time.min()).total_seconds() / 86400
        if n_days < 7:
            continue
        rate = len(evts) / n_days if n_days > 0 else 0
        per_patient.append({
            "patient_id": pid, "controller": ct,
            "n_events": len(evts), "days": n_days,
            "events_per_day": rate,
            "median_dose": float(evts.dose.median()) if len(evts) > 0 else np.nan,
            "median_pre_bg": float(evts.pre_bg.median()) if len(evts) > 0 else np.nan,
        })
        if len(evts) > 0:
            ctrl_events[ct].extend(evts.to_dict("records"))

    pp = pd.DataFrame(per_patient)
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # 3a: Events per day by controller
    ax = axes[0]
    for ct in CTRL_ORDER:
        sub = pp[pp.controller == ct]
        if len(sub) > 0:
            ax.bar(ct, sub.events_per_day.mean(), color=CTRL_COLORS[ct],
                   alpha=0.7, edgecolor="k")
            for _, row in sub.iterrows():
                ax.scatter(ct, row.events_per_day, c="k", s=30, zorder=5, alpha=0.5)
    ax.set_ylabel("Corrections / Day")
    ax.set_title("Detection Rate", fontweight="bold")
    ax.grid(axis="y", alpha=0.3)

    # 3b: Pre-BG distribution
    ax = axes[1]
    data = []
    labels = []
    for ct in CTRL_ORDER:
        evts = ctrl_events[ct]
        if evts:
            vals = [e["pre_bg"] for e in evts]
            data.append(vals)
            labels.append(f"{ct}\n(N={len(vals)})")
    if data:
        bp = ax.boxplot(data, labels=labels, patch_artist=True, showfliers=False)
        for j, ct in enumerate(CTRL_ORDER[:len(data)]):
            bp["boxes"][j].set_facecolor(CTRL_COLORS[ct])
            bp["boxes"][j].set_alpha(0.6)
    ax.set_ylabel("Pre-correction BG (mg/dL)")
    ax.set_title("Glucose at Correction", fontweight="bold")
    ax.grid(axis="y", alpha=0.3)

    # 3c: Dose distribution
    ax = axes[2]
    data = []
    labels = []
    for ct in CTRL_ORDER:
        evts = ctrl_events[ct]
        if evts:
            vals = [e["dose"] for e in evts]
            data.append(vals)
            labels.append(f"{ct}\n(N={len(vals)})")
    if data:
        bp = ax.boxplot(data, labels=labels, patch_artist=True, showfliers=False)
        for j, ct in enumerate(CTRL_ORDER[:len(data)]):
            bp["boxes"][j].set_facecolor(CTRL_COLORS[ct])
            bp["boxes"][j].set_alpha(0.6)
    ax.set_ylabel("Correction Dose (U)")
    ax.set_title("Dose at Correction", fontweight="bold")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("EXP-2671 Panel 3: Correction Event Detection Equivalence",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_correction_equivalence.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig3 saved")
    return {"per_patient": per_patient, "event_counts": {ct: len(v) for ct, v in ctrl_events.items()}}


# ── Panel 4: IOB Decay Curve Comparison ───────────────────────────────

def fig4_iob_decay_curves(df):
    """Compare post-bolus IOB decay profiles across controllers."""
    HORIZON_H = 7
    HORIZON_STEPS = HORIZON_H * STEPS_PER_HOUR

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    results = {}

    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        ct_patients = df[df.controller == ct].patient_id.unique()
        all_curves = []

        for pid in ct_patients:
            pdf = df[df.patient_id == pid].reset_index(drop=True)
            # Find isolated boluses (>2h gap before, no carbs ±1h)
            bolus_mask = pdf["bolus"].fillna(0) > MIN_DOSE
            bolus_locs = np.where(bolus_mask)[0]

            for loc in bolus_locs:
                if loc + HORIZON_STEPS >= len(pdf):
                    continue
                # Check isolation: no bolus in prior 2h
                prior_start = max(0, loc - 2 * STEPS_PER_HOUR)
                if pdf.iloc[prior_start:loc]["bolus"].fillna(0).sum() > 0.1:
                    continue
                # No carbs ±1h
                carb_start = max(0, loc - STEPS_PER_HOUR)
                carb_end = min(len(pdf), loc + STEPS_PER_HOUR)
                if pdf.iloc[carb_start:carb_end]["carbs"].fillna(0).sum() > 0:
                    continue

                iob_curve = pdf.iloc[loc:loc + HORIZON_STEPS]["iob"].values
                if np.isnan(iob_curve).sum() > HORIZON_STEPS * 0.3:
                    continue
                # Normalize to IOB at bolus time
                iob_at_bolus = iob_curve[0]
                if iob_at_bolus < 0.3:
                    continue
                all_curves.append(iob_curve / iob_at_bolus)

        if not all_curves:
            ax.text(0.5, 0.5, f"No data\n({ct})", transform=ax.transAxes, ha="center")
            continue

        curves = np.array(all_curves)
        hours = np.arange(HORIZON_STEPS) / STEPS_PER_HOUR
        median = np.nanmedian(curves, axis=0)
        p25 = np.nanpercentile(curves, 25, axis=0)
        p75 = np.nanpercentile(curves, 75, axis=0)

        ax.fill_between(hours, p25, p75, color=CTRL_COLORS[ct], alpha=0.2)
        ax.plot(hours, median, color=CTRL_COLORS[ct], lw=2.5,
                label=f"Median (N={len(all_curves)})")

        # Reference: exponential DIA=6h
        ref_exp = np.exp(-hours / 2.0)  # τ≈2h for DIA≈6h
        ax.plot(hours, ref_exp, "k--", alpha=0.4, label="Exp τ=2h ref")

        ax.set_xlabel("Hours post-bolus")
        ax.set_ylabel("IOB / IOB₀")
        ax.set_title(f"{ct.upper()} (N={len(all_curves)} events)", fontweight="bold")
        ax.legend(fontsize=9)
        ax.set_ylim(-0.1, 1.3)
        ax.grid(alpha=0.3)
        ax.axhline(0, color="k", alpha=0.3)

        results[f"{ct}_n_curves"] = len(all_curves)
        results[f"{ct}_iob_at_3h"] = float(np.nanmedian(curves[:, min(3 * STEPS_PER_HOUR, curves.shape[1] - 1)]))
        results[f"{ct}_iob_at_5h"] = float(np.nanmedian(curves[:, min(5 * STEPS_PER_HOUR, curves.shape[1] - 1)]))

    fig.suptitle("EXP-2671 Panel 4: IOB Decay Curves by Controller\n"
                 "(Isolated boluses, normalized to IOB at bolus time)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_iob_decay_curves.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig4 saved")
    return results


# ── Panel 5: Enacted Rate vs Actual Basal Audit ──────────────────────

def fig5_enacted_vs_actual(df):
    """Scatter enacted_rate vs actual_basal_rate per controller to detect encoding bugs."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    results = {}

    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        sub = df[df.controller == ct][["loop_enacted_rate", "actual_basal_rate", "patient_id"]].dropna()
        if len(sub) == 0:
            ax.text(0.5, 0.5, f"No data\n({ct})", transform=ax.transAxes, ha="center")
            continue

        n_patients = sub.patient_id.nunique()
        pct_mismatched = 100.0 * (np.abs(sub.loop_enacted_rate - sub.actual_basal_rate) > 5).mean()
        results[f"{ct}_pct_enacted_gt5_mismatch"] = float(pct_mismatched)
        results[f"{ct}_enacted_max"] = float(sub.loop_enacted_rate.max())

        # Sample for scatter (too many points otherwise)
        sample = sub.sample(min(5000, len(sub)), random_state=42)

        # Color by patient to see if one patient is the outlier
        patients = sorted(sample.patient_id.unique())
        for pid in patients:
            ps = sample[sample.patient_id == pid]
            has_bug = ps.loop_enacted_rate.max() > 10
            ax.scatter(ps.actual_basal_rate, ps.loop_enacted_rate,
                       s=8, alpha=0.3 if not has_bug else 0.6,
                       c="red" if has_bug else CTRL_COLORS[ct],
                       label=pid if has_bug else None)

        # Identity line
        max_val = min(sub.actual_basal_rate.max(), 10)
        ax.plot([0, max_val], [0, max_val], "k--", alpha=0.5, label="y=x")

        ax.set_xlabel("actual_basal_rate (U/h)")
        ax.set_ylabel("loop_enacted_rate")
        ax.set_title(f"{ct.upper()} ({n_patients} patients)\n"
                     f"Mismatch >5: {pct_mismatched:.1f}%",
                     fontweight="bold")
        ax.grid(alpha=0.3)
        if sub.loop_enacted_rate.max() > 10:
            ax.set_ylim(-1, min(sub.loop_enacted_rate.max() * 1.1, 160))
            ax.legend(fontsize=8, loc="upper left")
        else:
            ax.set_ylim(-0.5, max_val + 1)

    fig.suptitle("EXP-2671 Panel 5: Enacted Rate vs Actual Basal Rate\n"
                 "(Red = percent-encoding bug detected)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig5_enacted_vs_actual.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig5 saved")
    return results


# ── Panel 6: Field Coverage Heatmap ───────────────────────────────────

def fig6_field_coverage(df):
    """Heatmap of non-null percentage per column per controller."""
    audit_cols = [
        "glucose", "iob", "cob", "net_basal", "bolus", "bolus_smb", "carbs",
        "sensitivity_ratio", "scheduled_isf", "scheduled_cr",
        "loop_predicted_30", "loop_predicted_60", "loop_predicted_min",
        "eventual_bg", "insulin_req",
        "loop_enacted_rate", "loop_enacted_bolus",
        "actual_basal_rate", "scheduled_basal_rate",
        "glucose_roc", "glucose_accel",
    ]
    audit_cols = [c for c in audit_cols if c in df.columns]

    coverage = {}
    for ct in CTRL_ORDER:
        sub = df[df.controller == ct]
        coverage[ct] = {col: 100.0 * sub[col].notna().mean() for col in audit_cols}

    cov_df = pd.DataFrame(coverage).loc[audit_cols]

    fig, ax = plt.subplots(figsize=(10, 12))
    im = ax.imshow(cov_df.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)

    ax.set_xticks(range(len(CTRL_ORDER)))
    ax.set_xticklabels([ct.upper() for ct in CTRL_ORDER], fontsize=12)
    ax.set_yticks(range(len(audit_cols)))
    ax.set_yticklabels(audit_cols, fontsize=10)

    for i in range(len(audit_cols)):
        for j in range(len(CTRL_ORDER)):
            val = cov_df.values[i, j]
            color = "white" if val < 40 else "black"
            ax.text(j, i, f"{val:.0f}%", ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold")

    plt.colorbar(im, ax=ax, label="% Non-Null", shrink=0.6)
    ax.set_title("EXP-2671 Panel 6: Field Coverage by Controller Type",
                 fontsize=14, fontweight="bold", pad=15)
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig6_field_coverage.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig6 saved")
    return cov_df.to_dict()


# ── Panel 7: Glucose Trace Samples ────────────────────────────────────

def fig7_glucose_traces(df):
    """48h glucose trace samples — one per controller — for visual sanity check."""
    fig, axes = plt.subplots(3, 1, figsize=(18, 12), sharex=False)

    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        # Pick the patient with most data
        ct_pats = df[df.controller == ct].groupby("patient_id").size()
        if len(ct_pats) == 0:
            continue
        pid = ct_pats.idxmax()
        sub = df[df.patient_id == pid].sort_values("time").iloc[:576]  # 48h

        hours = (sub.time - sub.time.iloc[0]).dt.total_seconds() / 3600

        ax.fill_between(hours, 70, 180, color="green", alpha=0.08)
        ax.plot(hours, sub.glucose, color=CTRL_COLORS[ct], lw=1.2, label="Glucose")

        # Overlay boluses
        bol_mask = sub.bolus.fillna(0) > 0
        if bol_mask.any():
            ax.scatter(hours[bol_mask], sub[bol_mask].glucose,
                       marker="v", s=sub[bol_mask].bolus * 40,
                       c="red", alpha=0.6, label="Bolus", zorder=5)

        # Overlay carbs
        carb_mask = sub.carbs.fillna(0) > 0
        if carb_mask.any():
            ax.scatter(hours[carb_mask], sub[carb_mask].glucose,
                       marker="^", s=sub[carb_mask].carbs * 3,
                       c="orange", alpha=0.6, label="Carbs", zorder=5)

        # IOB on secondary axis
        ax2 = ax.twinx()
        ax2.fill_between(hours, 0, sub.iob.fillna(0), color="purple", alpha=0.1)
        ax2.set_ylabel("IOB (U)", color="purple", fontsize=10)
        ax2.set_ylim(0, sub.iob.max() * 2 if sub.iob.notna().any() else 5)
        ax2.tick_params(axis="y", labelcolor="purple")

        ax.set_ylabel("Glucose (mg/dL)")
        ax.set_title(f"{ct.upper()} — Patient {pid} (48h sample)", fontweight="bold")
        ax.legend(loc="upper left", fontsize=9)
        ax.set_ylim(40, 350)
        ax.grid(alpha=0.3)
        ax.axhline(70, color="red", ls=":", alpha=0.3)
        ax.axhline(180, color="red", ls=":", alpha=0.3)

    axes[-1].set_xlabel("Hours")
    fig.suptitle("EXP-2671 Panel 7: 48h Glucose Traces by Controller\n"
                 "(Visual sanity check: glucose + bolus + carbs + IOB overlay)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig7_glucose_traces.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig7 saved")


# ── Panel 8: Per-Patient Column Summary ───────────────────────────────

def fig8_per_patient_summary(df):
    """Per-patient bar chart of key metrics, sorted by controller."""
    patient_stats = []
    for pid in sorted(df.patient_id.unique()):
        sub = df[df.patient_id == pid]
        ct = sub.controller.iloc[0]
        if ct == "unknown":
            continue
        n_days = (sub.time.max() - sub.time.min()).total_seconds() / 86400
        patient_stats.append({
            "patient_id": pid, "controller": ct, "days": n_days,
            "mean_iob": sub.iob.mean(),
            "mean_glucose": sub.glucose.mean(),
            "bolus_per_day": (sub.bolus.fillna(0) > 0).sum() / max(n_days, 1),
            "smb_per_day": (sub.bolus_smb.fillna(0) > 0).sum() / max(n_days, 1),
            "carbs_per_day": (sub.carbs.fillna(0) > 0).sum() / max(n_days, 1),
            "tir": _tir(sub.glucose),
            "glucose_pct": 100 * sub.glucose.notna().mean(),
            "iob_pct": 100 * (sub.iob != 0).mean(),
        })

    ps = pd.DataFrame(patient_stats)
    ps = ps.sort_values(["controller", "patient_id"])

    metrics = [
        ("bolus_per_day", "Boluses/Day"),
        ("smb_per_day", "SMBs/Day"),
        ("mean_iob", "Mean IOB (U)"),
        ("carbs_per_day", "Carb Entries/Day"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(20, 10))
    axes = axes.ravel()

    for i, (col, label) in enumerate(metrics):
        ax = axes[i]
        colors = [CTRL_COLORS[ct] for ct in ps.controller]
        bars = ax.bar(range(len(ps)), ps[col], color=colors, alpha=0.7, edgecolor="k", lw=0.5)
        ax.set_xticks(range(len(ps)))
        ax.set_xticklabels(ps.patient_id, rotation=90, fontsize=7)
        ax.set_ylabel(label)
        ax.set_title(label, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)

    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=CTRL_COLORS[ct], label=ct.upper()) for ct in CTRL_ORDER]
    axes[0].legend(handles=legend_elements, loc="upper right")

    fig.suptitle("EXP-2671 Panel 8: Per-Patient Metrics by Controller",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig8_per_patient_summary.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ fig8 saved")

    # Flag patients with suspicious data
    flags = []
    for _, row in ps.iterrows():
        issues = []
        if row["iob_pct"] < 5:
            issues.append("IOB mostly zero")
        if row["glucose_pct"] < 50:
            issues.append("Low glucose coverage")
        if row["days"] < 14:
            issues.append("Short data span")
        if row["bolus_per_day"] < 0.5:
            issues.append("Very few boluses")
        if issues:
            flags.append({"patient_id": row["patient_id"], "controller": row["controller"],
                          "issues": issues})
    return flags


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("EXP-2671: Cross-Controller Data Fidelity Validation")
    print("=" * 60)

    print("\nLoading data...")
    df = load_data()
    n_patients = df.patient_id.nunique()
    for ct in CTRL_ORDER + ["unknown"]:
        n = df[df.controller == ct].patient_id.nunique()
        print(f"  {ct}: {n} patients")
    print(f"  Total: {n_patients} patients, {len(df):,} rows")

    results = {"experiment": "EXP-2671", "title": "Cross-Controller Data Fidelity Validation"}

    print("\n1/8: Field distributions...")
    results["distributions"] = fig1_field_distributions(df)

    print("2/8: TIR by controller...")
    results["tir"] = fig2_tir_by_controller(df)

    print("3/8: Correction event equivalence...")
    results["corrections"] = fig3_correction_equivalence(df)

    print("4/8: IOB decay curves...")
    results["iob_decay"] = fig4_iob_decay_curves(df)

    print("5/8: Enacted rate vs actual basal...")
    results["enacted_audit"] = fig5_enacted_vs_actual(df)

    print("6/8: Field coverage heatmap...")
    results["coverage"] = fig6_field_coverage(df)

    print("7/8: Glucose trace samples...")
    fig7_glucose_traces(df)

    print("8/8: Per-patient summary...")
    results["patient_flags"] = fig8_per_patient_summary(df)

    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    # Check H1: distributions comparable
    for col in ["glucose", "iob", "cob"]:
        means = [results["distributions"].get(f"{col}_{ct}_mean", np.nan) for ct in CTRL_ORDER]
        print(f"  {col} means: " + ", ".join(f"{ct}={m:.1f}" for ct, m in zip(CTRL_ORDER, means)))

    # Check H4: enacted rate bugs
    for ct in CTRL_ORDER:
        mismatch = results["enacted_audit"].get(f"{ct}_pct_enacted_gt5_mismatch", 0)
        emax = results["enacted_audit"].get(f"{ct}_enacted_max", 0)
        flag = " ⚠️  PERCENT BUG" if emax > 10 else " ✓"
        print(f"  {ct} enacted_rate: max={emax:.0f}, mismatch={mismatch:.1f}%{flag}")

    # Check H3: IOB decay
    for ct in CTRL_ORDER:
        iob3 = results["iob_decay"].get(f"{ct}_iob_at_3h", np.nan)
        iob5 = results["iob_decay"].get(f"{ct}_iob_at_5h", np.nan)
        ncurves = results["iob_decay"].get(f"{ct}_n_curves", 0)
        print(f"  {ct} IOB decay: @3h={iob3:.2f}, @5h={iob5:.2f} (N={ncurves})")

    # Patient flags
    if results["patient_flags"]:
        print(f"\n  ⚠️  FLAGGED PATIENTS ({len(results['patient_flags'])}):")
        for f in results["patient_flags"]:
            print(f"    {f['patient_id']} ({f['controller']}): {', '.join(f['issues'])}")

    # Correction events
    evt_counts = results["corrections"]["event_counts"]
    print(f"\n  Correction events detected: " +
          ", ".join(f"{ct}={evt_counts.get(ct, 0)}" for ct in CTRL_ORDER))

    # Save results
    with open(OUTFILE, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\n  Results → {OUTFILE}")
    print(f"  Figures → {VIZ_DIR}/")


if __name__ == "__main__":
    main()
