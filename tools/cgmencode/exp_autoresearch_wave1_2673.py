#!/usr/bin/env python3
"""EXP-2673: Autoresearch Wave 1 — Circadian Replication + Sensitivity Ratio Validation.

Two-part experiment now that autoprepare gate (EXP-2672) passed:

PART A — CIRCADIAN ISF REPLICATION (22 patients, 3 controllers)
  Replicate EXP-2665 finding (no circadian demand-ISF signal) on expanded dataset.
  Uses 2h prior-bolus isolation (EXP-2663 validated 2h gives same demand ISF as 6h).
  Note: 2h isolation is too strict for SMB controllers (Trio/OpenAPS) where SMBs
  arrive every ~1h. 2h isolation retains enough events across all controllers.
  12h Nyquist-strict day/night blocks.

PART B — SENSITIVITY RATIO vs DEMAND ISF (novel)
  Trio and some OpenAPS patients report `sensitivity_ratio` in devicestatus —
  the controller's real-time ISF multiplier. If this correlates with our
  independently extracted demand-ISF, it validates both approaches and opens
  a path to using the controller's own estimate as ground truth.

  sensitivity_ratio semantics:
    - Trio/oref1: ratio = autosens or DynISF sensitivity factor (0.5-1.5 typical)
    - Loop: NOT reported (0% coverage) — excluded from Part B
    - A ratio < 1 means "more insulin sensitive than profile"
    - A ratio > 1 means "more insulin resistant than profile"

  Hypothesis: Patients with higher sensitivity_ratio should have LOWER demand ISF
  (because ratio > 1 means resistant → need more insulin → lower mg/dL per unit)

OUTPUTS:
  - externals/experiments/exp-2673_autoresearch_wave1.json
  - visualizations/autoresearch-wave1/fig[1-6]_*.png
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
DS_PARQUET = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
OUTFILE = RESULTS_DIR / "exp-2673_autoresearch_wave1.json"
VIZ_DIR = Path("visualizations/autoresearch-wave1")
VIZ_DIR.mkdir(parents=True, exist_ok=True)

CTRL_COLORS = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}
CTRL_MARKERS = {"loop": "o", "trio": "s", "openaps": "D"}
CTRL_ORDER = ["loop", "trio", "openaps"]
STEPS_PER_HOUR = 12
DIA_H = 6.0
PRIOR_ISOLATION_H = 2.0  # 2h, not 6h — EXP-2663 validated equivalence; 6h kills SMB controllers
N_BOOTSTRAP = 2000
MIN_EVENTS_PER_BLOCK = 5


# ── Data Loading ──────────────────────────────────────────────────────

def load_qualified():
    """Load only qualified patients from manifest."""
    with open(MANIFEST) as f:
        manifest = json.load(f)
    qualified = manifest["qualified_patients"]

    df = pd.read_parquet(PARQUET)
    df = df[df.patient_id.isin(qualified)].copy()

    ds = pd.read_parquet(DS_PARQUET, columns=["patient_id", "controller"])
    ctrl = ds.groupby("patient_id")["controller"].agg(
        lambda x: x.value_counts().index[0]
    )
    df = df.merge(ctrl.rename("controller"), on="patient_id", how="left")
    df["controller"] = df["controller"].fillna("unknown")
    return df, qualified


# ── Part A: Circadian ISF Replication ─────────────────────────────────

def in_block(hour, block_start, block_end):
    if block_start < block_end:
        return block_start <= hour < block_end
    else:
        return hour >= block_start or hour < block_end


def extract_corrections(pdf, prior_bolus_h=6.0, min_dose=0.5, min_pre_bg=120,
                        carb_window_h=1.0, demand_window_h=2.0):
    """Extract correction events with strict prior-bolus isolation."""
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    hours = t.dt.hour + t.dt.minute / 60.0
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)

    carb_window = int(carb_window_h * STEPS_PER_HOUR)
    prior_window = int(prior_bolus_h * STEPS_PER_HOUR)
    demand_steps = int(demand_window_h * STEPS_PER_HOUR)
    events = []

    bolus_locs = np.where(bolus >= min_dose)[0]

    for loc in bolus_locs:
        if loc + demand_steps >= len(pdf) or loc < prior_window:
            continue

        pre_bg = glucose[loc - 1]
        if np.isnan(pre_bg) or pre_bg < min_pre_bg:
            continue

        # Carb exclusion
        c_start = max(0, loc - carb_window)
        c_end = min(len(pdf), loc + demand_steps + 1)
        if carbs[c_start:c_end].sum() > 0:
            continue

        # Prior bolus isolation
        prior_slice = bolus[max(0, loc - prior_window):loc]
        if prior_slice.sum() > 0:
            continue

        post_bg = glucose[loc + demand_steps]
        if np.isnan(post_bg):
            continue

        dose = bolus[loc]
        drop = pre_bg - post_bg
        isf = drop / dose

        events.append({
            "time": str(t.iloc[loc]),
            "hour": float(hours.iloc[loc]),
            "dose": float(dose),
            "pre_bg": float(pre_bg),
            "post_bg": float(post_bg),
            "drop": float(drop),
            "isf": float(isf),
        })
    return events


def bootstrap_ci(values, n_boot=N_BOOTSTRAP, ci=0.95):
    """Bootstrap confidence interval for median."""
    if len(values) < 3:
        return float(np.median(values)), np.nan, np.nan
    rng = np.random.default_rng(42)
    medians = [np.median(rng.choice(values, size=len(values), replace=True))
               for _ in range(n_boot)]
    alpha = (1 - ci) / 2
    lo, hi = np.quantile(medians, [alpha, 1 - alpha])
    return float(np.median(values)), float(lo), float(hi)


def run_part_a(df, qualified):
    """Part A: Circadian ISF replication with Nyquist-strict isolation."""
    print("\n" + "=" * 60)
    print("PART A: Circadian ISF Replication (22 patients)")
    print("=" * 60)

    block_defs = [("day_08_20", 8, 20), ("night_20_08", 20, 8)]
    results_a = {"patients": {}, "summary": {}}

    all_day_isfs = []
    all_night_isfs = []

    for pid in sorted(qualified):
        sub = df[df.patient_id == pid].copy()
        ct = sub.controller.iloc[0]
        events = extract_corrections(sub, prior_bolus_h=PRIOR_ISOLATION_H)

        day_events = [e for e in events if in_block(e["hour"], 8, 20)]
        night_events = [e for e in events if not in_block(e["hour"], 8, 20)]

        day_isfs = [e["isf"] for e in day_events]
        night_isfs = [e["isf"] for e in night_events]

        day_med, day_lo, day_hi = (bootstrap_ci(day_isfs)
                                    if len(day_isfs) >= MIN_EVENTS_PER_BLOCK
                                    else (np.nan, np.nan, np.nan))
        night_med, night_lo, night_hi = (bootstrap_ci(night_isfs)
                                          if len(night_isfs) >= MIN_EVENTS_PER_BLOCK
                                          else (np.nan, np.nan, np.nan))

        # Day/night ratio
        if not np.isnan(day_med) and not np.isnan(night_med) and night_med != 0:
            ratio = day_med / night_med
        else:
            ratio = np.nan

        results_a["patients"][pid] = {
            "controller": ct,
            "total_events": len(events),
            "day_events": len(day_events),
            "night_events": len(night_events),
            "day_isf": {"median": day_med, "ci_lo": day_lo, "ci_hi": day_hi},
            "night_isf": {"median": night_med, "ci_lo": night_lo, "ci_hi": night_hi},
            "day_night_ratio": float(ratio) if not np.isnan(ratio) else None,
        }

        if day_isfs:
            all_day_isfs.extend(day_isfs)
        if night_isfs:
            all_night_isfs.extend(night_isfs)

        tag = f"[{ct[:1].upper()}]"
        n_str = f"day={len(day_events)}, night={len(night_events)}"
        print(f"  {tag} {pid}: {len(events)} events ({n_str}), "
              f"day ISF={day_med:.1f}, night ISF={night_med:.1f}, "
              f"ratio={ratio:.2f}" if not np.isnan(ratio) else
              f"  {tag} {pid}: {len(events)} events ({n_str}), insufficient blocks")

    # Pooled day/night test
    if all_day_isfs and all_night_isfs:
        t_stat, p_val = stats.mannwhitneyu(all_day_isfs, all_night_isfs,
                                            alternative="two-sided")
        pooled_day_med = float(np.median(all_day_isfs))
        pooled_night_med = float(np.median(all_night_isfs))
        results_a["summary"] = {
            "pooled_day_median": pooled_day_med,
            "pooled_night_median": pooled_night_med,
            "pooled_day_n": len(all_day_isfs),
            "pooled_night_n": len(all_night_isfs),
            "mannwhitney_U": float(t_stat),
            "mannwhitney_p": float(p_val),
            "circadian_signal": p_val < 0.05,
        }
        print(f"\n  Pooled: day={pooled_day_med:.1f} (n={len(all_day_isfs)}), "
              f"night={pooled_night_med:.1f} (n={len(all_night_isfs)})")
        print(f"  Mann-Whitney U={t_stat:.0f}, p={p_val:.4f}")
        print(f"  Circadian signal: {'YES' if p_val < 0.05 else 'NO'}")

    # Per-controller test
    results_a["per_controller"] = {}
    for ct in CTRL_ORDER:
        ct_pats = [p for p in qualified if results_a["patients"].get(p, {}).get("controller") == ct]
        ct_day = []
        ct_night = []
        for pid in ct_pats:
            sub = df[df.patient_id == pid]
            events = extract_corrections(sub, prior_bolus_h=PRIOR_ISOLATION_H)
            ct_day.extend([e["isf"] for e in events if in_block(e["hour"], 8, 20)])
            ct_night.extend([e["isf"] for e in events if not in_block(e["hour"], 8, 20)])

        if len(ct_day) >= 10 and len(ct_night) >= 10:
            u, p = stats.mannwhitneyu(ct_day, ct_night, alternative="two-sided")
            results_a["per_controller"][ct] = {
                "day_median": float(np.median(ct_day)),
                "night_median": float(np.median(ct_night)),
                "day_n": len(ct_day),
                "night_n": len(ct_night),
                "p": float(p),
                "signal": p < 0.05,
            }
            print(f"  {ct}: day={np.median(ct_day):.1f} vs night={np.median(ct_night):.1f}, p={p:.4f}")
        else:
            results_a["per_controller"][ct] = {"status": "insufficient", "day_n": len(ct_day), "night_n": len(ct_night)}

    return results_a


# ── Part B: Sensitivity Ratio vs Demand ISF ───────────────────────────

def run_part_b(df, qualified):
    """Part B: Controller's sensitivity_ratio vs our extracted demand ISF."""
    print("\n" + "=" * 60)
    print("PART B: Sensitivity Ratio vs Demand ISF (Trio/OpenAPS)")
    print("=" * 60)

    results_b = {"patients": {}, "correlation": {}}

    # Only patients with sensitivity_ratio coverage
    sr_patients = []
    for pid in sorted(qualified):
        sub = df[df.patient_id == pid]
        ct = sub.controller.iloc[0]
        if ct == "loop":
            continue  # Loop has no sensitivity_ratio

        sr = sub["sensitivity_ratio"]
        sr_coverage = sr.notna().mean()
        if sr_coverage < 0.1:
            continue

        events = extract_corrections(sub, prior_bolus_h=PRIOR_ISOLATION_H)
        if len(events) < MIN_EVENTS_PER_BLOCK:
            continue

        # Extract median sensitivity_ratio around each correction event
        event_srs = []
        event_isfs = []
        for e in events:
            etime = pd.Timestamp(e["time"])
            # Get sensitivity_ratio in ±30min window around correction
            mask = (pd.to_datetime(sub["time"]) >= etime - pd.Timedelta(minutes=30)) & \
                   (pd.to_datetime(sub["time"]) <= etime + pd.Timedelta(minutes=30))
            nearby_sr = sub.loc[mask, "sensitivity_ratio"].dropna()
            if len(nearby_sr) > 0:
                event_srs.append(float(nearby_sr.median()))
                event_isfs.append(e["isf"])

        if len(event_srs) < 5:
            results_b["patients"][pid] = {"status": "insufficient_sr_overlap",
                                           "controller": ct, "n_events": len(events)}
            continue

        # Correlation: sensitivity_ratio vs demand ISF
        r, p = stats.pearsonr(event_srs, event_isfs)
        rho, rho_p = stats.spearmanr(event_srs, event_isfs)

        # Per-patient summary
        median_isf = float(np.median(event_isfs))
        median_sr = float(np.median(event_srs))
        scheduled_isf = float(sub["scheduled_isf"].median())

        # "Effective ISF" = scheduled_isf / sensitivity_ratio
        # (ratio > 1 means resistant → effective ISF should be lower)
        effective_isf = scheduled_isf / median_sr if median_sr > 0 else np.nan

        sr_patients.append(pid)
        results_b["patients"][pid] = {
            "controller": ct,
            "n_events": len(events),
            "n_sr_events": len(event_srs),
            "median_demand_isf": median_isf,
            "median_sensitivity_ratio": median_sr,
            "scheduled_isf": scheduled_isf,
            "effective_isf": float(effective_isf),
            "pearson_r": float(r),
            "pearson_p": float(p),
            "spearman_rho": float(rho),
            "spearman_p": float(rho_p),
        }

        print(f"  [{ct[:1].upper()}] {pid}: n={len(event_srs)}, "
              f"demand_ISF={median_isf:.1f}, SR={median_sr:.3f}, "
              f"effective_ISF={effective_isf:.1f}, "
              f"r={r:.3f} (p={p:.3f})")

    # Cross-patient correlation: does median SR predict median demand ISF?
    if len(sr_patients) >= 5:
        cross_srs = [results_b["patients"][p]["median_sensitivity_ratio"] for p in sr_patients]
        cross_isfs = [results_b["patients"][p]["median_demand_isf"] for p in sr_patients]
        cross_eff = [results_b["patients"][p]["effective_isf"] for p in sr_patients]

        r_cross, p_cross = stats.pearsonr(cross_srs, cross_isfs)
        rho_cross, rho_p_cross = stats.spearmanr(cross_srs, cross_isfs)

        # Also: does effective ISF (scheduled/SR) predict demand ISF?
        valid = [i for i in range(len(cross_eff)) if not np.isnan(cross_eff[i])]
        if len(valid) >= 5:
            eff_vals = [cross_eff[i] for i in valid]
            isf_vals = [cross_isfs[i] for i in valid]
            r_eff, p_eff = stats.pearsonr(eff_vals, isf_vals)
        else:
            r_eff, p_eff = np.nan, np.nan

        results_b["correlation"] = {
            "n_patients": len(sr_patients),
            "cross_patient_sr_vs_isf": {
                "pearson_r": float(r_cross),
                "pearson_p": float(p_cross),
                "spearman_rho": float(rho_cross),
                "spearman_p": float(rho_p_cross),
            },
            "effective_isf_vs_demand_isf": {
                "pearson_r": float(r_eff),
                "pearson_p": float(p_eff),
                "n": len(valid),
            },
        }
        print(f"\n  Cross-patient (n={len(sr_patients)}):")
        print(f"    SR vs demand ISF:  r={r_cross:.3f}, p={p_cross:.3f}")
        print(f"    Effective ISF vs demand ISF: r={r_eff:.3f}, p={p_eff:.3f}")
    else:
        results_b["correlation"] = {"status": "insufficient_patients", "n": len(sr_patients)}
        print(f"\n  Only {len(sr_patients)} patients with SR — insufficient for cross-patient analysis")

    return results_b, sr_patients


# ── Visualizations ────────────────────────────────────────────────────

def fig1_circadian_by_controller(df, results_a, qualified):
    """Day vs night ISF per patient, grouped by controller."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        ct_pats = [p for p in qualified
                   if results_a["patients"].get(p, {}).get("controller") == ct]

        xs, ys, labels = [], [], []
        for pid in ct_pats:
            p = results_a["patients"][pid]
            d = p["day_isf"]["median"]
            n = p["night_isf"]["median"]
            if not np.isnan(d) and not np.isnan(n):
                xs.append(d)
                ys.append(n)
                labels.append(pid)

        if xs:
            ax.scatter(xs, ys, c=CTRL_COLORS[ct], s=80, alpha=0.7,
                      edgecolors="k", lw=0.5, zorder=3)
            for x, y, lab in zip(xs, ys, labels):
                ax.annotate(lab, (x, y), fontsize=6, alpha=0.7,
                           xytext=(3, 3), textcoords="offset points")

        # Identity line
        lims = [0, max(max(xs, default=50), max(ys, default=50)) * 1.2]
        ax.plot(lims, lims, "k--", alpha=0.3, label="Day = Night")
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.set_xlabel("Day ISF (08-20h, mg/dL/U)")
        ax.set_ylabel("Night ISF (20-08h, mg/dL/U)")

        pctrl = results_a.get("per_controller", {}).get(ct, {})
        p_val = pctrl.get("p", None)
        p_str = f"p={p_val:.3f}" if p_val is not None else "insufficient"
        ax.set_title(f"{ct.upper()} ({len(ct_pats)} pts, {p_str})", fontweight="bold")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9)

    fig.suptitle("EXP-2673A: Circadian Demand ISF — Day vs Night\n"
                 "(2h prior-bolus isolation, Nyquist-strict 12h blocks)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig1_circadian_day_vs_night.png", dpi=150)
    plt.close(fig)
    print("  [fig1] Day vs Night ISF by controller")


def fig2_circadian_ratios(results_a, qualified):
    """Day/night ISF ratio per patient — clustered around 1.0 = no circadian."""
    pids = sorted([p for p in qualified
                   if results_a["patients"].get(p, {}).get("day_night_ratio") is not None],
                  key=lambda p: results_a["patients"][p]["controller"])
    ratios = [results_a["patients"][p]["day_night_ratio"] for p in pids]
    colors = [CTRL_COLORS.get(results_a["patients"][p]["controller"], "#999") for p in pids]

    fig, ax = plt.subplots(figsize=(16, 5))
    bars = ax.bar(range(len(pids)), ratios, color=colors, alpha=0.7, edgecolor="k", lw=0.5)
    ax.axhline(1.0, color="red", ls="--", lw=2, label="No circadian effect (ratio=1)")
    ax.axhspan(0.8, 1.2, color="green", alpha=0.1, label="±20% range")
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, rotation=90, fontsize=7)
    ax.set_ylabel("Day/Night ISF Ratio")
    ax.set_title("EXP-2673A: Day/Night ISF Ratios (ratio ~1 = no circadian signal)",
                 fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=CTRL_COLORS[ct], label=ct.upper()) for ct in CTRL_ORDER]
    ax.legend(handles=legend_elements + [
        plt.Line2D([0], [0], color="red", ls="--", label="Ratio=1 (no circadian)"),
    ], loc="upper right")

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig2_circadian_ratios.png", dpi=150)
    plt.close(fig)
    print("  [fig2] Day/Night ISF ratios")


def fig3_pooled_distributions(df, qualified, results_a):
    """Pooled day vs night ISF distributions per controller."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    for ci, ct in enumerate(CTRL_ORDER):
        ax = axes[ci]
        ct_pats = [p for p in qualified
                   if results_a["patients"].get(p, {}).get("controller") == ct]

        day_isfs, night_isfs = [], []
        for pid in ct_pats:
            sub = df[df.patient_id == pid]
            events = extract_corrections(sub, prior_bolus_h=PRIOR_ISOLATION_H)
            day_isfs.extend([e["isf"] for e in events if in_block(e["hour"], 8, 20)])
            night_isfs.extend([e["isf"] for e in events if not in_block(e["hour"], 8, 20)])

        bins = np.linspace(-50, 150, 40)
        if day_isfs:
            ax.hist(day_isfs, bins=bins, alpha=0.5, color="gold", label=f"Day (n={len(day_isfs)})",
                   edgecolor="k", lw=0.3)
        if night_isfs:
            ax.hist(night_isfs, bins=bins, alpha=0.5, color="navy", label=f"Night (n={len(night_isfs)})",
                   edgecolor="k", lw=0.3)

        ax.set_xlabel("Demand ISF (mg/dL/U)")
        ax.set_ylabel("Count")
        ax.set_title(f"{ct.upper()}", fontweight="bold")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

    fig.suptitle("EXP-2673A: Pooled Day vs Night ISF Distributions\n"
                 "(2h isolation, 12h Nyquist blocks)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig3_pooled_day_night.png", dpi=150)
    plt.close(fig)
    print("  [fig3] Pooled day/night distributions")


def fig4_sr_vs_demand_isf(df, results_b, sr_patients):
    """sensitivity_ratio vs demand ISF: event-level and cross-patient."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Panel 1: Event-level scatter (all events, colored by patient)
    cmap = plt.cm.tab20
    for i, pid in enumerate(sr_patients):
        sub = df[df.patient_id == pid]
        ct = sub.controller.iloc[0]
        events = extract_corrections(sub, prior_bolus_h=PRIOR_ISOLATION_H)

        event_srs, event_isfs = [], []
        for e in events:
            etime = pd.Timestamp(e["time"])
            mask = (pd.to_datetime(sub["time"]) >= etime - pd.Timedelta(minutes=30)) & \
                   (pd.to_datetime(sub["time"]) <= etime + pd.Timedelta(minutes=30))
            nearby_sr = sub.loc[mask, "sensitivity_ratio"].dropna()
            if len(nearby_sr) > 0:
                event_srs.append(float(nearby_sr.median()))
                event_isfs.append(e["isf"])

        if event_srs:
            ax1.scatter(event_srs, event_isfs, c=[cmap(i % 20)] * len(event_srs),
                       alpha=0.3, s=15, edgecolors="none", label=pid if i < 15 else None)

    ax1.set_xlabel("Sensitivity Ratio (controller's estimate)")
    ax1.set_ylabel("Demand ISF (mg/dL/U)")
    ax1.set_title("Event-Level: SR vs Demand ISF", fontweight="bold")
    ax1.grid(alpha=0.3)
    ax1.axhline(0, color="k", alpha=0.3)
    ax1.legend(fontsize=6, ncol=2, loc="upper left")

    # Panel 2: Cross-patient (median SR vs median demand ISF)
    srs = [results_b["patients"][p]["median_sensitivity_ratio"] for p in sr_patients]
    isfs = [results_b["patients"][p]["median_demand_isf"] for p in sr_patients]
    cts = [results_b["patients"][p]["controller"] for p in sr_patients]

    for pid, sr, isf, ct in zip(sr_patients, srs, isfs, cts):
        ax2.scatter(sr, isf, c=CTRL_COLORS.get(ct, "#999"), s=100,
                   marker=CTRL_MARKERS.get(ct, "o"), edgecolors="k", lw=0.5, zorder=3)
        ax2.annotate(pid, (sr, isf), fontsize=6, alpha=0.7,
                    xytext=(3, 3), textcoords="offset points")

    # Fit line
    if len(srs) >= 5:
        slope, intercept, r, p, _ = stats.linregress(srs, isfs)
        x_fit = np.linspace(min(srs) * 0.95, max(srs) * 1.05, 100)
        y_fit = slope * x_fit + intercept
        ax2.plot(x_fit, y_fit, "r-", lw=2, label=f"r={r:.3f}, p={p:.3f}")
        ax2.legend(fontsize=10)

    ax2.set_xlabel("Median Sensitivity Ratio")
    ax2.set_ylabel("Median Demand ISF (mg/dL/U)")
    ax2.set_title("Cross-Patient: SR vs Demand ISF", fontweight="bold")
    ax2.grid(alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=CTRL_COLORS[ct], label=ct.upper())
                      for ct in ["trio", "openaps"]]
    ax2.legend(handles=legend_elements + [
        plt.Line2D([0], [0], color="r", label=f"r={r:.3f}" if len(srs) >= 5 else ""),
    ], loc="upper right")

    fig.suptitle("EXP-2673B: Controller Sensitivity Ratio vs Extracted Demand ISF\n"
                 "(Does the controller's own ISF estimate match our extraction?)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig4_sr_vs_demand_isf.png", dpi=150)
    plt.close(fig)
    print("  [fig4] SR vs demand ISF (event + cross-patient)")


def fig5_effective_isf(results_b, sr_patients):
    """Effective ISF (scheduled/SR) vs demand ISF — does profile ISF predict demand?"""
    valid = [p for p in sr_patients
             if not np.isnan(results_b["patients"][p].get("effective_isf", np.nan))]

    fig, ax = plt.subplots(figsize=(8, 8))

    eff_isfs = [results_b["patients"][p]["effective_isf"] for p in valid]
    dem_isfs = [results_b["patients"][p]["median_demand_isf"] for p in valid]
    cts = [results_b["patients"][p]["controller"] for p in valid]

    for pid, eff, dem, ct in zip(valid, eff_isfs, dem_isfs, cts):
        ax.scatter(eff, dem, c=CTRL_COLORS.get(ct, "#999"), s=100,
                  marker=CTRL_MARKERS.get(ct, "o"), edgecolors="k", lw=0.5, zorder=3)
        ax.annotate(pid, (eff, dem), fontsize=6, alpha=0.7,
                   xytext=(3, 3), textcoords="offset points")

    # Identity line
    lims = [0, max(max(eff_isfs, default=50), max(dem_isfs, default=50)) * 1.2]
    ax.plot(lims, lims, "k--", alpha=0.3, label="Effective = Demand")

    # 2:1 and 1:2 lines (for the known 2-10× inflation)
    ax.plot(lims, [x / 2 for x in lims], "b:", alpha=0.3, label="Demand = Effective/2")
    ax.plot(lims, [x / 5 for x in lims], "r:", alpha=0.3, label="Demand = Effective/5")

    if len(eff_isfs) >= 5:
        slope, intercept, r, p, _ = stats.linregress(eff_isfs, dem_isfs)
        x_fit = np.linspace(min(eff_isfs), max(eff_isfs), 100)
        y_fit = slope * x_fit + intercept
        ax.plot(x_fit, y_fit, "r-", lw=2, label=f"Fit: r={r:.3f}, p={p:.3f}")

    ax.set_xlabel("Effective ISF (scheduled_isf / sensitivity_ratio, mg/dL/U)")
    ax.set_ylabel("Demand ISF (extracted, mg/dL/U)")
    ax.set_title("EXP-2673B: Effective ISF vs Demand ISF\n"
                 "(Tests EXP-2651 finding that profile ISF is 2-10× inflated)",
                 fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    ax.set_xlim(lims)
    ax.set_ylim(lims)

    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig5_effective_vs_demand_isf.png", dpi=150)
    plt.close(fig)
    print("  [fig5] Effective ISF vs demand ISF")


def fig6_summary_dashboard(results_a, results_b, sr_patients, qualified):
    """Summary dashboard with key metrics from both parts."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Panel 1: Events per patient (Part A)
    ax = axes[0, 0]
    pids = sorted(qualified, key=lambda p: results_a["patients"].get(p, {}).get("controller", ""))
    events = [results_a["patients"].get(p, {}).get("total_events", 0) for p in pids]
    colors = [CTRL_COLORS.get(results_a["patients"].get(p, {}).get("controller", ""), "#999") for p in pids]
    ax.bar(range(len(pids)), events, color=colors, alpha=0.7, edgecolor="k", lw=0.3)
    ax.set_xticks(range(len(pids)))
    ax.set_xticklabels(pids, rotation=90, fontsize=5)
    ax.set_ylabel("Strict-Isolated Events")
    ax.set_title("Part A: Events per Patient (2h isolation)", fontweight="bold", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    # Panel 2: Circadian ratios distribution
    ax = axes[0, 1]
    ratios = [results_a["patients"][p]["day_night_ratio"]
              for p in qualified if results_a["patients"].get(p, {}).get("day_night_ratio") is not None]
    if ratios:
        ax.hist(ratios, bins=15, color="#607D8B", alpha=0.7, edgecolor="k", lw=0.5)
        ax.axvline(1.0, color="red", ls="--", lw=2, label="No circadian")
        ax.set_xlabel("Day/Night ISF Ratio")
        ax.set_ylabel("Count")
        ax.set_title(f"Part A: Day/Night Ratio Distribution (median={np.median(ratios):.2f})",
                     fontweight="bold", fontsize=10)
        ax.legend()
    ax.grid(alpha=0.3)

    # Panel 3: Sensitivity ratio distribution (Part B patients)
    ax = axes[1, 0]
    if sr_patients:
        sr_vals = [results_b["patients"][p]["median_sensitivity_ratio"] for p in sr_patients]
        cts = [results_b["patients"][p]["controller"] for p in sr_patients]
        sr_colors = [CTRL_COLORS.get(ct, "#999") for ct in cts]
        ax.bar(range(len(sr_patients)), sr_vals, color=sr_colors, alpha=0.7, edgecolor="k", lw=0.5)
        ax.set_xticks(range(len(sr_patients)))
        ax.set_xticklabels(sr_patients, rotation=90, fontsize=6)
        ax.axhline(1.0, color="red", ls="--", lw=1.5, label="Baseline (SR=1)")
        ax.set_ylabel("Median Sensitivity Ratio")
        ax.set_title("Part B: Sensitivity Ratio per Patient", fontweight="bold", fontsize=10)
        ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Panel 4: Text summary
    ax = axes[1, 1]
    ax.axis("off")
    summary_a = results_a.get("summary", {})
    corr_b = results_b.get("correlation", {})

    lines = [
        "EXP-2673 SUMMARY",
        "=" * 35,
        "",
        "Part A: Circadian ISF Replication",
        f"  Patients: {len(qualified)} (22 qualified)",
        f"  Pooled day ISF:  {summary_a.get('pooled_day_median', '?'):.1f} mg/dL/U" if isinstance(summary_a.get('pooled_day_median'), float) else "  Pooled day ISF:  N/A",
        f"  Pooled night ISF: {summary_a.get('pooled_night_median', '?'):.1f} mg/dL/U" if isinstance(summary_a.get('pooled_night_median'), float) else "  Pooled night ISF: N/A",
        f"  Mann-Whitney p: {summary_a.get('mannwhitney_p', '?'):.4f}" if isinstance(summary_a.get('mannwhitney_p'), float) else "  Mann-Whitney p: N/A",
        f"  Circadian signal: {'YES' if summary_a.get('circadian_signal') else 'NO'}",
        "",
        "Part B: Sensitivity Ratio Validation",
        f"  Patients with SR: {len(sr_patients)}",
    ]

    cross = corr_b.get("cross_patient_sr_vs_isf", {})
    if cross:
        lines.extend([
            f"  SR vs demand ISF: r={cross.get('pearson_r', '?'):.3f}" if isinstance(cross.get('pearson_r'), float) else "  SR vs demand ISF: N/A",
            f"  Effective ISF vs demand: r={corr_b.get('effective_isf_vs_demand_isf', {}).get('pearson_r', '?'):.3f}" if isinstance(corr_b.get('effective_isf_vs_demand_isf', {}).get('pearson_r'), float) else "  Effective ISF vs demand: N/A",
        ])

    ax.text(0.05, 0.95, "\n".join(lines), transform=ax.transAxes,
            fontsize=10, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.suptitle("EXP-2673: Autoresearch Wave 1 Summary", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(VIZ_DIR / "fig6_summary_dashboard.png", dpi=150)
    plt.close(fig)
    print("  [fig6] Summary dashboard")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("EXP-2673: Autoresearch Wave 1")
    print("Part A: Circadian ISF Replication | Part B: Sensitivity Ratio Validation")
    print("=" * 70)

    df, qualified = load_qualified()
    print(f"Loaded {len(qualified)} qualified patients, {len(df):,} rows")

    # Part A
    results_a = run_part_a(df, qualified)

    # Part B
    results_b, sr_patients = run_part_b(df, qualified)

    # Figures
    print("\nGenerating figures...")
    fig1_circadian_by_controller(df, results_a, qualified)
    fig2_circadian_ratios(results_a, qualified)
    fig3_pooled_distributions(df, qualified, results_a)
    if sr_patients:
        fig4_sr_vs_demand_isf(df, results_b, sr_patients)
        fig5_effective_isf(results_b, sr_patients)
    fig6_summary_dashboard(results_a, results_b, sr_patients, qualified)

    # Combined results
    results = {
        "experiment": "EXP-2673",
        "title": "Autoresearch Wave 1",
        "n_qualified": len(qualified),
        "part_a_circadian": results_a,
        "part_b_sensitivity_ratio": results_b,
    }

    # Conclusions
    circadian_signal = results_a.get("summary", {}).get("circadian_signal", None)
    cross_corr = results_b.get("correlation", {}).get("cross_patient_sr_vs_isf", {})

    conclusions = []
    if circadian_signal is False:
        conclusions.append("CONFIRMED: Demand ISF has no circadian variation (replicates EXP-2665 on 22 patients)")
    elif circadian_signal is True:
        conclusions.append("NEW: Circadian signal detected in demand ISF on expanded dataset — investigate further")

    if isinstance(cross_corr.get("pearson_r"), float):
        r = cross_corr["pearson_r"]
        if abs(r) > 0.5:
            conclusions.append(f"NEW: Controller sensitivity_ratio strongly predicts demand ISF (r={r:.3f})")
        elif abs(r) > 0.3:
            conclusions.append(f"MODERATE: Controller sensitivity_ratio moderately predicts demand ISF (r={r:.3f})")
        else:
            conclusions.append(f"WEAK: Controller sensitivity_ratio weakly correlated with demand ISF (r={r:.3f})")

    results["conclusions"] = conclusions
    print("\n" + "=" * 70)
    print("CONCLUSIONS")
    for c in conclusions:
        print(f"  → {c}")

    with open(OUTFILE, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nResults → {OUTFILE}")
    print(f"Figures → {VIZ_DIR}/fig[1-6]_*.png")


if __name__ == "__main__":
    main()
