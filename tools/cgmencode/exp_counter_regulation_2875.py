"""EXP-2875 — Counter-regulation detection in closed-loop hypo recovery.

Hypothesis:
  In type-1 diabetes, glucagon counter-regulation is often impaired but
  rarely absent. During AID-managed hypoglycemia recovery, the BG rise
  is driven by (a) basal suspension / IOB decay, (b) rescue carbs, and
  (c) hepatic glucagon release.

  If we restrict to recovery events with NO rescue carbs and minimal
  IOB at the recovery start, the observed BG rise rate exceeds what
  insulin withdrawal alone explains by an amount attributable to
  counter-regulation. Per-patient excess rise quantifies residual
  counter-regulatory capacity.

Method:
  1. Detect hypo events: BG < 70 sustained ≥2 cells (10min).
  2. Identify recovery: BG returns to ≥90 within 90min.
  3. Filter rescue-free: no carbs in [-15min, recovery+30min] window.
  4. For each event, compute:
       rise_rate = (BG_at_recovery - BG_at_nadir) / (t_recovery - t_nadir)
       iob_at_nadir, iob_decay (Δ over recovery window)
       basal_during_recovery (mean actual basal vs scheduled)
  5. Linear regression per patient: rise_rate ~ iob_at_nadir + basal_gap.
     Residual intercept = counter-regulation contribution (mg/dL/min).
  6. Compare counter-reg signature across controllers (Loop hypo-prevention
     bias may shorten hypo durations; Trio SMB substitution may produce
     different IOB profiles at nadir).

Charter: Stream B operational. Counter-regulation residual is observed
behavior; biological glucagon assay would be needed for ground truth.
The signal is the DIRECTION + MAGNITUDE of unexplained recovery rise.

Apply EXP-2873 NaN-percentile guard throughout.

Output:
  externals/experiments/exp-2875_counter_regulation_events.parquet
  externals/experiments/exp-2875_per_patient.parquet
  externals/experiments/exp-2875_summary.json
  docs/60-research/figures/exp-2875_counter_regulation.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")

HYPO_THRESHOLD = 70.0      # mg/dL
RECOVERY_TARGET = 90.0     # mg/dL
HYPO_MIN_CELLS = 2          # ≥10 min sustained hypo to count
RECOVERY_WINDOW_MIN = 90    # ≤90 min from nadir to recovery
CARB_BUFFER_MIN = 15        # exclude carbs in this pre-window
POST_BUFFER_MIN = 30        # exclude carbs this far past recovery
MIN_EVENTS_PER_PATIENT = 5  # for per-patient regression


def detect_hypo_recovery_events(g_pat: pd.DataFrame) -> list[dict]:
    """Find hypo events and their recoveries (rescue-free).

    Returns list of event dicts with nadir/recovery indices and
    measurement context.
    """
    g = g_pat.sort_values("time").reset_index(drop=True).copy()
    bg = g["glucose"].to_numpy()
    t = g["time"].to_numpy()
    n = len(g)
    if n < 20:
        return []

    is_hypo = bg < HYPO_THRESHOLD
    events = []
    i = 0
    while i < n:
        if not is_hypo[i] or np.isnan(bg[i]):
            i += 1
            continue
        # find run of hypo
        start = i
        while i < n and (is_hypo[i] or np.isnan(bg[i])):
            i += 1
        end = i  # exclusive
        if end - start < HYPO_MIN_CELLS:
            continue
        # nadir within run
        run_bg = bg[start:end]
        valid = ~np.isnan(run_bg)
        if not valid.any():
            continue
        nadir_off = int(np.nanargmin(run_bg))
        nadir_idx = start + nadir_off
        # find recovery: BG ≥ 90 within RECOVERY_WINDOW_MIN
        max_cells = RECOVERY_WINDOW_MIN // 5
        rec_idx = None
        for j in range(nadir_idx, min(n, nadir_idx + max_cells + 1)):
            if not np.isnan(bg[j]) and bg[j] >= RECOVERY_TARGET:
                rec_idx = j
                break
        if rec_idx is None or rec_idx == nadir_idx:
            continue
        events.append({
            "nadir_idx": nadir_idx,
            "rec_idx": rec_idx,
            "hypo_start_idx": start,
        })
    return events


def annotate_event(g_pat: pd.DataFrame, ev: dict) -> dict | None:
    """Compute per-event metrics; return None if rescue-carb contaminated."""
    nadir = ev["nadir_idx"]
    rec = ev["rec_idx"]
    n = len(g_pat)

    # Carbs check window
    carb_lookback_cells = CARB_BUFFER_MIN // 5
    carb_lookahead_cells = POST_BUFFER_MIN // 5
    lo = max(0, nadir - carb_lookback_cells)
    hi = min(n, rec + carb_lookahead_cells + 1)
    carbs_window = g_pat["carbs"].iloc[lo:hi].fillna(0).sum()
    if carbs_window > 0:
        return None

    bg_nadir = float(g_pat["glucose"].iloc[nadir])
    bg_rec = float(g_pat["glucose"].iloc[rec])
    if np.isnan(bg_nadir) or np.isnan(bg_rec):
        return None

    duration_min = (rec - nadir) * 5.0
    if duration_min <= 0:
        return None
    rise_rate = (bg_rec - bg_nadir) / duration_min  # mg/dL/min

    iob_nadir = g_pat["iob"].iloc[nadir]
    iob_rec = g_pat["iob"].iloc[rec]
    iob_decay = float(iob_nadir - iob_rec) if not np.isnan(iob_nadir) and not np.isnan(iob_rec) else np.nan

    # actual vs scheduled basal during recovery
    rec_slice = g_pat.iloc[nadir:rec + 1]
    actual_basal = float(rec_slice["actual_basal_rate"].mean())
    sched_basal = float(rec_slice["scheduled_basal_rate"].mean())
    basal_gap = actual_basal - sched_basal if not (np.isnan(actual_basal) or np.isnan(sched_basal)) else np.nan

    return dict(
        bg_nadir=bg_nadir,
        bg_rec=bg_rec,
        rise_rate=rise_rate,
        duration_min=duration_min,
        iob_nadir=float(iob_nadir) if not np.isnan(iob_nadir) else np.nan,
        iob_decay=iob_decay,
        actual_basal=actual_basal,
        sched_basal=sched_basal,
        basal_gap=basal_gap,
    )


def per_patient_regression(events: pd.DataFrame) -> dict | None:
    """Fit rise_rate ~ iob_nadir + basal_gap; residual intercept is the
    counter-regulation signature.
    """
    df = events.dropna(subset=["rise_rate", "iob_nadir", "basal_gap"])
    if len(df) < MIN_EVENTS_PER_PATIENT:
        return None
    y = df["rise_rate"].to_numpy()
    X = np.column_stack([np.ones(len(df)), df["iob_nadir"].to_numpy(),
                         df["basal_gap"].to_numpy()])
    try:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        intercept, b_iob, b_basal = coef
    except np.linalg.LinAlgError:
        return None
    yhat = X @ coef
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return dict(
        n_events=int(len(df)),
        intercept=float(intercept),
        beta_iob=float(b_iob),
        beta_basal=float(b_basal),
        r2=float(r2),
        median_rise_rate=float(np.median(y)),
        median_iob_nadir=float(np.median(df["iob_nadir"])),
    )


def main() -> None:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)

    # Optional controller info from a side parquet
    ctl_map = {}
    ctl_path = Path("externals/experiments/exp-2870_per_patient_crossover.parquet")
    if ctl_path.exists():
        cdf = pd.read_parquet(ctl_path)
        ctl_map = dict(zip(cdf["patient_id"], cdf["controller"]))

    all_events = []
    for pid, g_pat in g.groupby("patient_id"):
        evs = detect_hypo_recovery_events(g_pat)
        for ev in evs:
            ann = annotate_event(g_pat, ev)
            if ann is None:
                continue
            ann["patient_id"] = pid
            ann["controller"] = ctl_map.get(pid, "unknown")
            all_events.append(ann)

    events_df = pd.DataFrame(all_events)
    print(f"Rescue-free hypo→recovery events: {len(events_df)} "
          f"({events_df['patient_id'].nunique()} patients)")

    events_df.to_parquet(EXP / "exp-2875_counter_regulation_events.parquet",
                         index=False)

    # Per-patient regression
    per_patient = []
    for pid, g_p in events_df.groupby("patient_id"):
        res = per_patient_regression(g_p)
        if res is None:
            continue
        res["patient_id"] = pid
        res["controller"] = g_p["controller"].iloc[0]
        per_patient.append(res)
    pp_df = pd.DataFrame(per_patient)
    pp_df.to_parquet(EXP / "exp-2875_per_patient.parquet", index=False)

    print(f"\nPer-patient fits: {len(pp_df)}")
    if not pp_df.empty:
        print(pp_df[["patient_id", "controller", "n_events", "intercept",
                     "beta_iob", "beta_basal", "r2", "median_rise_rate"]]
              .to_string(index=False))

    # Cohort summary: counter-regulation is the residual intercept after
    # controlling for IOB and basal_gap. Population median intercept >0
    # suggests a baseline counter-regulation signature.
    summary = {
        "experiment": "EXP-2875",
        "title": "Counter-regulation detection in closed-loop hypo recovery",
        "stream": "B",
        "n_events_total": int(len(events_df)),
        "n_patients_with_events": int(events_df["patient_id"].nunique()) if len(events_df) else 0,
        "n_patients_fit": int(len(pp_df)),
    }
    if not pp_df.empty:
        ints = pp_df["intercept"].dropna().to_numpy()
        if len(ints) > 0:
            summary["intercept_median"] = float(np.median(ints))
            summary["intercept_iqr"] = [
                float(np.percentile(ints, 25)),
                float(np.percentile(ints, 75)),
            ]
            summary["frac_positive_intercept"] = float(np.mean(ints > 0))
            # By controller
            by_ctl = {}
            for ctl, sub in pp_df.groupby("controller"):
                if len(sub) >= 2:
                    by_ctl[ctl] = {
                        "n_patients": int(len(sub)),
                        "intercept_median": float(np.median(sub["intercept"])),
                        "rise_rate_median": float(np.median(sub["median_rise_rate"])),
                    }
            summary["by_controller"] = by_ctl

            # Verdict
            med = summary["intercept_median"]
            frac = summary["frac_positive_intercept"]
            if med > 0.3 and frac >= 0.7:
                verdict = ("DETECTED — population median intercept "
                           f"{med:.2f} mg/dL/min; {frac:.0%} patients have "
                           "positive residual rise after IOB+basal "
                           "correction. Consistent with preserved "
                           "counter-regulation in the cohort.")
            elif med > 0.1:
                verdict = ("PARTIAL — modest positive intercept "
                           f"({med:.2f} mg/dL/min); evidence is mixed "
                           "across patients.")
            else:
                verdict = ("ABSENT — intercept near zero; recovery is "
                           "explained by IOB decay and basal withdrawal "
                           "alone in this cohort.")
            summary["verdict"] = verdict
        else:
            summary["verdict"] = "INSUFFICIENT DATA"
    else:
        summary["verdict"] = "INSUFFICIENT DATA — no patients had ≥5 rescue-free events"

    (EXP / "exp-2875_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Figure: rise_rate vs iob_nadir per patient
    if not events_df.empty:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        ax = axes[0]
        for ctl, sub in events_df.groupby("controller"):
            ax.scatter(sub["iob_nadir"], sub["rise_rate"], alpha=0.4,
                       s=20, label=f"{ctl} (n={len(sub)})")
        ax.set_xlabel("IOB at nadir (U)")
        ax.set_ylabel("Rise rate (mg/dL/min)")
        ax.set_title("EXP-2875 — Rescue-free hypo recovery\n"
                     "Per-event rise rate vs IOB at nadir")
        ax.legend()
        ax.grid(alpha=0.3)
        ax.axhline(0, color="gray", ls=":", alpha=0.6)

        ax = axes[1]
        if not pp_df.empty:
            colors = {"Loop": "#1f77b4", "Trio": "#d62728",
                      "OpenAPS": "#2ca02c", "AAPS": "#9467bd",
                      "unknown": "#7f7f7f"}
            for ctl, sub in pp_df.groupby("controller"):
                ax.scatter(sub["beta_iob"], sub["intercept"], s=80,
                           color=colors.get(ctl, "#7f7f7f"),
                           label=f"{ctl} (n={len(sub)})", alpha=0.7,
                           edgecolors="black")
            ax.axhline(0, color="gray", ls=":", alpha=0.6)
            ax.axvline(0, color="gray", ls=":", alpha=0.6)
            ax.set_xlabel("β_IOB (mg/dL/min per U IOB)")
            ax.set_ylabel("Counter-reg residual intercept (mg/dL/min)")
            ax.set_title("Per-patient regression coefficients\n"
                         "Intercept >0 = unexplained recovery rise")
            ax.legend()
            ax.grid(alpha=0.3)
        plt.tight_layout()
        FIG.mkdir(parents=True, exist_ok=True)
        plt.savefig(FIG / "exp-2875_counter_regulation.png", dpi=120)
        plt.close()

    print(f"\nVerdict: {summary.get('verdict', 'N/A')}")


if __name__ == "__main__":
    main()
