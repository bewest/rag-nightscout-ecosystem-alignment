"""exp_meal_size_audit.py — Per-meal decomposition of carb-size estimator.

Read-only diagnostic for the bias documented in plan.md:
`tools/cgmencode/production/meal_detector.py` sizes meals from the signed
3 h sum of physics residuals, which omits the glucose mopped up by the
AID's insulin response and lets post-peak negative residuals subtract.

For every meal detected by the production detector this script emits, per
event:

    pos_resid_int_mgdl     Σ max(residual, 0) in window
    signed_resid_int_mgdl  Σ residual                       (legacy basis)
    insulin_absorbed_mgdl  Σ demand                         (would-be rise)
    raw_bg_rise_mgdl       max(BG[window]) − BG[ev_start]
    legacy_carbs_g         current production estimator
    pos_only_carbs_g       F1 candidate (positive residual only)
    spectral_carbs_g       F1+F2 candidate (pos residual + insulin back)

Outputs CSV + summary + 6-panel plot to externals/experiments/ .

Usage (from repo root):
    python -m tools.cgmencode.exp_meal_size_audit --patient-id live-recent \\
        --parquet-dir externals/ns-parquet/live-recent
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]


def _load_patient(patient_id: str, parquet_dir: Path):
    """Mirror analyze_patient.py loader (kept local to avoid coupling)."""
    from tools.cgmencode.production.types import PatientData, PatientProfile

    grid_path = parquet_dir / "grid.parquet"
    df_all = pd.read_parquet(grid_path)
    df = df_all[df_all["patient_id"] == patient_id].copy()
    if df.empty:
        raise SystemExit(
            f"No rows for patient_id='{patient_id}' in {grid_path}."
        )
    df = df.sort_values("time").reset_index(drop=True)

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
        except Exception:
            pass

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
    return patient, isf_median, cr_median


def _events_from_detector(meals, ev_indices) -> List[tuple]:
    """Reconstruct (ev_start, ev_end) windows from production detector output.

    The production detector centers each meal at (start+end)//2 but does
    not return start/end. We re-derive them by re-running the burst-cluster
    logic so the audit numbers align exactly with what production sees.
    """
    return ev_indices  # populated by audit() below


def audit(patient_id: str, parquet_dir: Path, out_dir: Path) -> None:
    from tools.cgmencode.production.metabolic_engine import (
        compute_metabolic_state, _extract_hours,
    )
    from tools.cgmencode.production.data_quality import clean_glucose
    from tools.cgmencode.production.meal_detector import (
        DEFAULT_SIGMA_MULT, ROLLING_WINDOW, MERGE_GAP, MIN_CARB_SUPPLY,
        _classify_meal_window, _median_value,
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    patient, isf, cr = _load_patient(patient_id, parquet_dir)
    print(f"Loaded {patient_id}: {patient.days_of_data:.1f} days, "
          f"insulin={patient.has_insulin_data}, ISF={isf:.1f}, CR={cr:.1f}")

    cleaned = clean_glucose(patient.glucose)
    # Update glucose with cleaned values so metabolic engine sees it.
    patient.glucose = cleaned.glucose
    hours = _extract_hours(patient.timestamps, patient.profile.timezone)
    metabolic = compute_metabolic_state(patient)

    residuals = metabolic.residual
    demand = metabolic.demand
    carb_supply = metabolic.carb_supply
    glucose = cleaned.glucose
    N = len(residuals)
    print(f"residual stats: mean={np.nanmean(residuals):+.3f} "
          f"std={np.nanstd(residuals):.3f} N={N}")

    # ── Re-run burst-cluster logic to expose (ev_start, ev_end) ────
    resid_std = float(np.nanstd(residuals[np.isfinite(residuals)]))
    if resid_std < 1e-6:
        raise SystemExit("residual std ~ 0; nothing to audit")
    threshold = DEFAULT_SIGMA_MULT * resid_std
    resid_pos = np.maximum(np.nan_to_num(residuals, nan=0.0), 0.0)
    rolling_pos = np.convolve(resid_pos, np.ones(ROLLING_WINDOW), mode="same")
    burst_threshold = threshold * ROLLING_WINDOW * 0.5
    burst_idx = np.where(rolling_pos > burst_threshold)[0]
    print(f"σ={resid_std:.3f}  burst_threshold={burst_threshold:.3f}  "
          f"n_burst_steps={len(burst_idx)}")

    events: List[tuple] = []
    if len(burst_idx):
        cs, ce = burst_idx[0], burst_idx[0]
        for i in range(1, len(burst_idx)):
            if burst_idx[i] - ce <= MERGE_GAP:
                ce = burst_idx[i]
            else:
                events.append((cs, ce))
                cs = ce = burst_idx[i]
        events.append((cs, ce))
    print(f"detected events: {len(events)}")

    # ── Per-event decomposition ───────────────────────────────────
    # Baseline correction: the residual is biased by mean residual across
    # the whole record (model mis-calibration). For meal sizing we want
    # to subtract that drift so the integral reflects only the meal
    # excess above the patient's typical "no-meal" baseline.
    finite_resid = residuals[np.isfinite(residuals)]
    resid_baseline = float(np.median(finite_resid)) if len(finite_resid) else 0.0
    print(f"residual baseline (median) = {resid_baseline:+.4f} mg/dL/5min "
          f"(mean = {float(np.nanmean(residuals)):+.4f})")

    def _extend_window(ev_start: int, ev_end: int) -> tuple:
        """Adaptive window: extend backward to first sustained positive
        residual (up to 24 steps = 2 h before ev_start) and forward
        while pos_resid > σ/2 (up to 60 steps = 5 h after ev_end)."""
        # Backward: walk back while residual > 0 in 30-min average
        s = ev_start
        rolling_back_limit = max(0, ev_start - 24)
        while s > rolling_back_limit:
            window_avg = float(np.nanmean(residuals[max(0, s - 3):s + 1]))
            if window_avg <= 0:
                break
            s -= 1
        # Forward: walk forward while pos_resid > σ/2
        e = ev_end
        rolling_fwd_limit = min(N, ev_end + 60)
        sigma_floor = resid_std * 0.5
        while e < rolling_fwd_limit - 1:
            r = float(residuals[e + 1]) if np.isfinite(residuals[e + 1]) else 0.0
            if r < sigma_floor:
                # require 2 consecutive sub-floor steps to stop
                r2 = float(residuals[min(N - 1, e + 2)]) if e + 2 < N else 0.0
                if r2 < sigma_floor:
                    break
            e += 1
        return s, min(N, e + 1)

    rows = []
    for ev_start, ev_end in events:
        # Production window (3h after ev_end, ev_start unchanged)
        r_start = ev_start
        r_end = min(N, ev_end + 36)
        win_resid = residuals[r_start:r_end]
        win_demand = demand[r_start:r_end] if demand is not None else np.zeros(r_end - r_start)
        win_glu = glucose[r_start:r_end]

        signed_int = float(np.nansum(win_resid))
        pos_int = float(np.nansum(np.maximum(win_resid, 0.0)))
        ins_absorbed = float(np.nansum(win_demand))
        valid_glu = win_glu[np.isfinite(win_glu)]
        raw_rise = float(valid_glu.max() - valid_glu[0]) if len(valid_glu) >= 2 else 0.0

        legacy_g = abs(signed_int) * cr / max(isf, 1.0)
        pos_only_g = pos_int * cr / max(isf, 1.0)
        spectral_g = (pos_int + ins_absorbed) * cr / max(isf, 1.0)

        # Toggle A: subtract residual baseline (de-drift)
        n_steps = r_end - r_start
        baseline_corrected_pos = max(
            0.0, pos_int - max(0.0, resid_baseline) * n_steps
        )
        # If baseline negative, ADD that magnitude back (the model was
        # under-predicting, meaning meal residual was being eroded)
        baseline_added_pos = pos_int - resid_baseline * n_steps
        spectral_baseline_g = (
            (max(0.0, baseline_added_pos) + ins_absorbed) * cr / max(isf, 1.0)
        )

        # Toggle B+C: adaptive window
        ext_start, ext_end = _extend_window(ev_start, ev_end)
        ext_resid = residuals[ext_start:ext_end]
        ext_demand = demand[ext_start:ext_end] if demand is not None else np.zeros(ext_end - ext_start)
        ext_pos = float(np.nansum(np.maximum(ext_resid, 0.0)))
        ext_ins = float(np.nansum(ext_demand))
        ext_n = ext_end - ext_start
        ext_pos_baseline = max(0.0, ext_pos - resid_baseline * ext_n)
        spectral_extended_g = (ext_pos + ext_ins) * cr / max(isf, 1.0)
        spectral_full_g = (ext_pos_baseline + ext_ins) * cr / max(isf, 1.0)

        center = (ev_start + ev_end) // 2
        cs0 = max(0, ev_start - 6)
        cs1 = min(N, ev_end + 12)
        announced = float(np.nansum(carb_supply[cs0:cs1])) > MIN_CARB_SUPPLY

        rows.append(dict(
            ev_start=int(ev_start),
            ev_end=int(ev_end),
            ext_start=int(ext_start),
            ext_end=int(ext_end),
            window_steps_legacy=int(r_end - r_start),
            window_steps_extended=int(ext_n),
            center_idx=int(center),
            hour_of_day=float(hours[center]) if center < len(hours) else float("nan"),
            window=_classify_meal_window(float(hours[center])).value
                   if center < len(hours) else "snack",
            announced=bool(announced),
            signed_resid_int_mgdl=signed_int,
            pos_resid_int_mgdl=pos_int,
            insulin_absorbed_mgdl=ins_absorbed,
            raw_bg_rise_mgdl=raw_rise,
            legacy_carbs_g=legacy_g,
            pos_only_carbs_g=pos_only_g,
            spectral_carbs_g=spectral_g,
            spectral_baseline_corrected_g=spectral_baseline_g,
            spectral_extended_window_g=spectral_extended_g,
            spectral_full_g=spectral_full_g,
        ))

    df = pd.DataFrame(rows)
    csv_path = out_dir / "exp_meal_size_audit.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nwrote {csv_path}  ({len(df)} meals)")

    if len(df) == 0:
        return

    # ── Summary ───────────────────────────────────────────────────
    def _stats(s: pd.Series) -> str:
        return (f"mean={s.mean():6.1f}  median={s.median():6.1f}  "
                f"p90={s.quantile(0.9):6.1f}  max={s.max():6.1f}")

    print(f"\nmeals_per_day  = {len(df) / max(patient.days_of_data, 0.1):.2f}")
    print(f"announced rate = {df['announced'].mean():.2%}")
    print(f"\nlegacy_carbs_g                  {_stats(df.legacy_carbs_g)}")
    print(f"pos_only_carbs_g                {_stats(df.pos_only_carbs_g)}")
    print(f"spectral_carbs_g (production)   {_stats(df.spectral_carbs_g)}")
    print(f"spectral_baseline_corrected_g   {_stats(df.spectral_baseline_corrected_g)}")
    print(f"spectral_extended_window_g      {_stats(df.spectral_extended_window_g)}")
    print(f"spectral_full_g (all toggles)   {_stats(df.spectral_full_g)}")
    print(f"raw_bg_rise_mgdl                {_stats(df.raw_bg_rise_mgdl)}")
    print(f"\nwindow_steps  legacy median={df.window_steps_legacy.median():.0f}  "
          f"extended median={df.window_steps_extended.median():.0f}")
    for floor in (5, 10, 20, 30, 50, 80):
        n_legacy = int((df.legacy_carbs_g >= floor).sum())
        n_spec = int((df.spectral_carbs_g >= floor).sum())
        n_full = int((df.spectral_full_g >= floor).sum())
        print(f"  ≥{floor:>2}g   legacy={n_legacy:4d}  "
              f"spectral={n_spec:4d}  full={n_full:4d}")

    # ── Plot largest 6 meals (by spectral_carbs_g) ────────────────
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib unavailable — skipping plots")
        return

    top = df.nlargest(6, "spectral_carbs_g")
    fig, axes = plt.subplots(3, 2, figsize=(14, 10))
    iob = patient.iob if patient.iob is not None else np.zeros(N)
    for ax, (_, row) in zip(axes.flat, top.iterrows()):
        s = max(0, int(row.ev_start) - 12)
        e = min(N, int(row.ev_end) + 36)
        x = np.arange(e - s) * 5.0  # minutes
        ax2 = ax.twinx()
        ax.plot(x, glucose[s:e], "b-", label="BG")
        ax.axvline((row.ev_start - s) * 5.0, color="g", ls="--", alpha=0.5, label="ev_start")
        ax.axvline((row.ev_end - s) * 5.0, color="r", ls="--", alpha=0.5, label="ev_end")
        ax2.plot(x, residuals[s:e], "orange", alpha=0.6, label="residual")
        ax2.plot(x, demand[s:e] if demand is not None else np.zeros(e - s),
                 "purple", alpha=0.5, label="demand")
        ax.set_title(f"hr={row.hour_of_day:.1f}  "
                     f"legacy={row.legacy_carbs_g:.0f}g  "
                     f"spectral={row.spectral_carbs_g:.0f}g  "
                     f"raw_rise={row.raw_bg_rise_mgdl:.0f}mg/dL")
        ax.set_xlabel("min from window start")
        ax.set_ylabel("BG (mg/dL)")
        ax2.set_ylabel("residual / demand (mg/dL/5min)")
    fig.tight_layout()
    plot_path = out_dir / "exp_meal_size_audit.png"
    fig.savefig(plot_path, dpi=110)
    print(f"wrote {plot_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--patient-id", default="live-recent")
    p.add_argument("--parquet-dir",
                   default=str(REPO / "externals/ns-parquet/live-recent"))
    p.add_argument("--out-dir",
                   default=str(REPO / "externals/experiments"))
    args = p.parse_args()
    audit(args.patient_id, Path(args.parquet_dir), Path(args.out_dir))


if __name__ == "__main__":
    main()
