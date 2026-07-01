"""therapy_trajectory_state.py — per-patient therapy-trajectory turns.

Turns a patient's raw longitudinal grid (CGM + insulin + context) into a
sequence of fixed-length "turns" with continuous emission features plus a
cheap, interpretable rule-based outcome label per turn.

This is the concrete first build step from the state-aware-harness
parallel analysis in
``docs/60-research/state-aware-harness-parallels-2026-07-01.md``. The
design intentionally mirrors (not copies) the Candidly/LangSmith
architecture described there:

  * a "turn" here is a fixed 72-hour, sequential, non-overlapping window
    of a patient's therapy trajectory (not a chat message), chosen
    because it is long enough to include ~3 repetitions of each daily
    basal segment (enough to see a within-turn trend) while staying
    short enough to still be state-like rather than a whole-history
    average. Day-type (weekday/weekend) is intentionally *not* used as a
    hard turn boundary; it is carried as a continuous feature
    (``weekend_day_fraction``) so it can be validated as predictive
    rather than assumed.
  * "emissions" are patient/physiology-side signals computed directly
    from the trace (time-in-range breakdown, data completeness, meal and
    bolus activity, override/exercise/suspension activity) — the
    analog of Candidly's user-side turn features. In addition to the
    surface-level glycemic/activity features, this module folds in
    validated physiology features already researched elsewhere in this
    package rather than re-deriving proxies from scratch:

      - supply/demand flux (hepatic production, carb absorption, insulin
        demand, net flux) from ``metabolic_engine.compute_metabolic_state``
        (EXP-1771/1772) — an EGP proxy;
      - insulin "wall"/saturation detection from
        ``clinical_rules.detect_insulin_saturation`` (EXP-2660/2662) — the
        closest validated proxy for an "overflowing" supply-vs-demand
        state, where insulin is delivered but glucose barely responds;
      - a 48h trailing-carbs glycogen-loading proxy (EXP-2622/2627: r=-0.303
        with subsequent overnight drift; low-carb history -> rising BG
        ["emptier" stores], high-carb history -> falling BG ["fuller"
        stores]). Note: the ``carbs_48h_g``/``glycogen_note`` fields
        declared on ``types.OvernightDriftAssessment`` do not appear to be
        populated by any current production function, so this module
        computes its own trailing-48h carbs sum directly from the grid
        rather than depending on that dataclass;
      - CGM/infusion-site wear and longevity, using the ``cage_hours``/
        ``sage_hours`` columns already present in the grid for per-turn
        site age, plus the per-patient (not per-turn) EXP-2863
        ``p_site_degradation`` estimate from ``WearFactsLoader`` as a
        static covariate.
  * the outcome label is a cheap, rule-based, ADA-threshold proxy for
    "resolved vs abandoned" computed from the *next* turn's realized
    trend, exactly mirroring Candidly's first pipeline stage (a rule
    based ex-post label) before any state model is fit. It is not a
    hidden Markov model and is not intended to be one yet: see
    ``docs/60-research/state-aware-harness-parallels-2026-07-01.md``
    section "Per-Patient Therapy Trajectory" for why unsupervised state
    discovery is deferred (small-n, patient-autocorrelation, and
    leave-patient-out validation requirements) and what would need to be
    true before attempting it.

Continuous features are stored alongside the discrete label so a future
unsupervised-discovery pass can reuse this same harness without
re-deriving emissions from raw grid data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..production_therapy import (
    ADA_TBR_L1_TARGET,
    ADA_TBR_L2_TARGET,
    ADA_TIR_TARGET,
    compute_time_in_ranges,
)
from .clinical_rules import detect_insulin_saturation
from .metabolic_engine import compute_metabolic_state
from .types import MetabolicState, PatientData, PatientProfile, SaturationLevel
from .wear_facts_loader import WearFactsLoader

# Turn geometry. 72h chosen to approximate human metabolic/behavioral
# re-entrainment cycles while giving ~3 repetitions of each daily basal
# segment per turn (see module docstring).
DEFAULT_TURN_HOURS = 72.0
EXPECTED_SAMPLE_INTERVAL_MIN = 5.0
GLYCOGEN_LOOKBACK_HOURS = 48.0

# Outcome-labeling thresholds. Reuses the ADA safety targets already
# defined in production_therapy.py rather than inventing new ones.
TIR_DELTA_THRESHOLD_PP = 5.0          # "meaningfully different" TIR move
MIN_TURN_COMPLETENESS = 0.5           # below this, a turn's features (and
                                       # any label depending on it) are
                                       # considered unreliable.


class TrajectoryState(str, Enum):
    """Rule-based, ex-post proxy label for a turn's realized outcome.

    Deliberately named to parallel (not claim equivalence with) the four
    emergent states Candidly's IO-HMM discovered. These are hand-defined
    from ADA safety/target thresholds, not fit from data — see the
    module docstring for why.
    """

    IMPROVING = "improving"
    STABLE_GOOD = "stable_good"
    STABLE_POOR = "stable_poor"
    WORSENING = "worsening"
    UNKNOWN = "unknown"


@dataclass
class TurnFeatures:
    """Continuous emission features for one 72h turn.

    Kept as plain floats/ints (not derived states) so a future
    unsupervised-discovery pass can build directly on this table.
    """

    patient_id: str
    turn_index: int
    start: pd.Timestamp
    end: pd.Timestamp

    n_readings: int
    expected_readings: int
    data_completeness: float

    tir: float
    tbr_l1: float
    tbr_l2: float
    tar_l1: float
    tar_l2: float
    cv: float
    mean_glucose: float
    overnight_tir: float

    weekend_day_fraction: float
    meal_count: int
    bolus_active_row_count: int
    smb_active_row_count: int
    override_active_fraction: float
    exercise_active_fraction: float
    suspension_active_fraction: float

    # Physiology features (flux/EGP proxy, "overflow" saturation,
    # glycogen-loading proxy, site wear/longevity). See module docstring
    # for provenance and known limitations of each.
    physiology_available: bool = False   # False if PatientProfile/profile
                                          # medians could not be built for
                                          # this patient (flux fields below
                                          # are then 0.0, not missing data)
    mean_hepatic_production: float = 0.0
    mean_carb_supply: float = 0.0
    mean_insulin_demand: float = 0.0
    mean_net_flux: float = 0.0

    saturation_level: str = "insufficient_data"  # SaturationLevel value or
                                                   # "insufficient_data"
    saturation_wall_pct: float = 0.0

    carbs_48h_g: float = 0.0             # trailing 48h carbs before turn start

    mean_cage_hours: float = float("nan")  # cannula/infusion-site age
    mean_sage_hours: float = float("nan")  # sensor age
    site_degradation_p: float | None = None  # EXP-2863 per-patient P(site
                                               # degradation), static across
                                               # all of a patient's turns

    @property
    def meets_ada_tbr(self) -> bool:
        return self.tbr_l1 < ADA_TBR_L1_TARGET and self.tbr_l2 < ADA_TBR_L2_TARGET

    @property
    def meets_ada_tir(self) -> bool:
        return self.tir >= ADA_TIR_TARGET

    @property
    def is_reliable(self) -> bool:
        return self.data_completeness >= MIN_TURN_COMPLETENESS


@dataclass
class TurnLabel:
    state: TrajectoryState
    reason: str


def load_patient_grid(parquet_dir: Path | str, patient_id: str) -> pd.DataFrame:
    """Load and sort one patient's rows from a grid.parquet cohort file."""
    grid_path = Path(parquet_dir) / "grid.parquet"
    df_all = pd.read_parquet(grid_path)
    df = df_all[df_all["patient_id"] == patient_id].copy()
    if df.empty:
        raise ValueError(
            f"No rows for patient_id='{patient_id}' in {grid_path}. "
            f"Available: {sorted(df_all['patient_id'].unique())[:20]}"
        )
    return df.sort_values("time").reset_index(drop=True)


def segment_into_turns(
    df: pd.DataFrame,
    turn_hours: float = DEFAULT_TURN_HOURS,
    time_col: str = "time",
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Sequential, non-overlapping [start, end) turn boundaries.

    Turns start at the first timestamp in ``df`` and tile forward; the
    final partial turn (if any) is dropped so every turn has a full
    window's worth of possible readings.
    """
    if df.empty:
        return []
    start0 = df[time_col].min()
    end_all = df[time_col].max()
    turn_delta = pd.Timedelta(hours=turn_hours)
    boundaries: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = start0
    while cursor + turn_delta <= end_all + pd.Timedelta(minutes=EXPECTED_SAMPLE_INTERVAL_MIN):
        boundaries.append((cursor, cursor + turn_delta))
        cursor += turn_delta
    return boundaries


def _weekend_day_fraction(window_df: pd.DataFrame, time_col: str = "time") -> float:
    if window_df.empty:
        return 0.0
    dates = window_df[time_col].dt.floor("D").unique()
    if len(dates) == 0:
        return 0.0
    weekend = sum(1 for d in dates if pd.Timestamp(d).dayofweek >= 5)
    return float(weekend) / float(len(dates))


def _overnight_tir(window_df: pd.DataFrame, time_col: str = "time",
                    glucose_col: str = "glucose") -> float:
    """Overnight (00:00-06:00) TIR computed from timestamps directly.

    ``compute_time_in_ranges``'s own overnight estimate assumes the input
    array is midnight-aligned at index 0, which does not hold for
    arbitrary 72h turn slices, so it is recomputed here from real
    timestamps instead.
    """
    hours = window_df[time_col].dt.hour
    mask = hours < 6
    seg = window_df.loc[mask, glucose_col].dropna().to_numpy()
    if len(seg) == 0:
        return 0.0
    lo, hi = 70.0, 180.0
    return float(np.mean((seg >= lo) & (seg <= hi)) * 100)


def _mean_or(window_df: pd.DataFrame, col: str, default: float = float("nan")) -> float:
    if col not in window_df or window_df.empty:
        return default
    series = window_df[col].dropna()
    return float(series.mean()) if len(series) else default


def compute_turn_features(
    patient_id: str,
    turn_index: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    window_df: pd.DataFrame,
    turn_hours: float = DEFAULT_TURN_HOURS,
    time_col: str = "time",
    metabolic_slice: MetabolicState | None = None,
    carbs_48h_g: float = 0.0,
    site_degradation_p: float | None = None,
) -> TurnFeatures:
    """Compute continuous emission features for a single turn's rows.

    ``metabolic_slice`` is the whole-patient ``MetabolicState`` (from
    ``metabolic_engine.compute_metabolic_state``) already sliced down to
    this turn's rows by the caller — the physics model needs continuous
    per-patient time context (circadian phase, IOB decay), so it must be
    computed once over the full patient series and sliced afterward
    rather than recomputed per turn.
    """
    expected_readings = int(round(turn_hours * 60.0 / EXPECTED_SAMPLE_INTERVAL_MIN))
    glucose = window_df["glucose"].to_numpy() if "glucose" in window_df else np.array([])
    n_readings = int(np.sum(~np.isnan(glucose))) if len(glucose) else 0
    completeness = min(1.0, n_readings / expected_readings) if expected_readings else 0.0

    tir_data = compute_time_in_ranges(glucose)
    overnight_tir = _overnight_tir(window_df, time_col=time_col)

    def _frac(col: str) -> float:
        if col not in window_df or window_df.empty:
            return 0.0
        series = window_df[col]
        return float(np.nanmean(series.astype(float) > 0)) if len(series) else 0.0

    def _count(col: str) -> int:
        if col not in window_df or window_df.empty:
            return 0
        return int((window_df[col].fillna(0) > 0).sum())

    # ── Insulin "wall"/overflow saturation (EXP-2660/2662) ────────────
    iob_arr = window_df["iob"].to_numpy(dtype=float) if "iob" in window_df else None
    saturation_level = "insufficient_data"
    saturation_wall_pct = 0.0
    if iob_arr is not None and len(glucose) > 0:
        assessment = detect_insulin_saturation(glucose.astype(float), iob_arr)
        if assessment is not None:
            saturation_level = assessment.level.value
            saturation_wall_pct = assessment.wall_pct

    # ── Supply/demand flux (EGP proxy), sliced from the whole-patient
    #    MetabolicState computed once by the caller ────────────────────
    physiology_available = metabolic_slice is not None
    mean_hepatic = float(np.mean(metabolic_slice.hepatic)) if physiology_available else 0.0
    mean_carb_supply = float(np.mean(metabolic_slice.carb_supply)) if physiology_available else 0.0
    mean_demand = float(np.mean(metabolic_slice.demand)) if physiology_available else 0.0
    mean_net_flux = float(np.mean(metabolic_slice.net_flux)) if physiology_available else 0.0

    return TurnFeatures(
        patient_id=patient_id,
        turn_index=turn_index,
        start=start,
        end=end,
        n_readings=n_readings,
        expected_readings=expected_readings,
        data_completeness=completeness,
        tir=tir_data.tir,
        tbr_l1=tir_data.tbr_l1,
        tbr_l2=tir_data.tbr_l2,
        tar_l1=tir_data.tar_l1,
        tar_l2=tir_data.tar_l2,
        cv=tir_data.cv,
        mean_glucose=tir_data.mean_glucose,
        overnight_tir=overnight_tir,
        weekend_day_fraction=_weekend_day_fraction(window_df, time_col=time_col),
        meal_count=_count("carbs"),
        bolus_active_row_count=_count("bolus"),
        smb_active_row_count=_count("bolus_smb"),
        override_active_fraction=_frac("override_active"),
        exercise_active_fraction=_frac("exercise_active"),
        suspension_active_fraction=_frac("suspension_time_min"),
        physiology_available=physiology_available,
        mean_hepatic_production=mean_hepatic,
        mean_carb_supply=mean_carb_supply,
        mean_insulin_demand=mean_demand,
        mean_net_flux=mean_net_flux,
        saturation_level=saturation_level,
        saturation_wall_pct=saturation_wall_pct,
        carbs_48h_g=carbs_48h_g,
        mean_cage_hours=_mean_or(window_df, "cage_hours"),
        mean_sage_hours=_mean_or(window_df, "sage_hours"),
        site_degradation_p=site_degradation_p,
    )


def label_turn_outcome(
    current: TurnFeatures,
    nxt: TurnFeatures | None,
) -> TurnLabel:
    """Ex-post proxy label for ``current`` based on the *next* turn's trend.

    Safety takes priority over glycemic-target movement: a turn whose
    follow-up breaches ADA hypoglycemia safety targets is always
    WORSENING, even if TIR nominally improved (e.g. driven down by more
    severe lows). This mirrors production `ClinicalDecisionPolicy`'s own
    safety-first framing rather than treating TIR as a single scalar
    reward.
    """
    if nxt is None:
        return TurnLabel(TrajectoryState.UNKNOWN, "no follow-up turn available yet")
    if not current.is_reliable or not nxt.is_reliable:
        return TurnLabel(
            TrajectoryState.UNKNOWN,
            f"insufficient data completeness (current={current.data_completeness:.2f}, "
            f"next={nxt.data_completeness:.2f})",
        )

    if not nxt.meets_ada_tbr:
        return TurnLabel(
            TrajectoryState.WORSENING,
            f"follow-up breaches ADA hypo safety targets "
            f"(TBR<70={nxt.tbr_l1:.1f}%, TBR<54={nxt.tbr_l2:.1f}%)",
        )

    delta = nxt.tir - current.tir
    if delta >= TIR_DELTA_THRESHOLD_PP:
        return TurnLabel(TrajectoryState.IMPROVING, f"TIR moved +{delta:.1f}pp next turn")
    if delta <= -TIR_DELTA_THRESHOLD_PP:
        return TurnLabel(TrajectoryState.WORSENING, f"TIR moved {delta:.1f}pp next turn")

    if nxt.meets_ada_tir:
        return TurnLabel(TrajectoryState.STABLE_GOOD, f"TIR stable at/above target ({nxt.tir:.1f}%)")
    return TurnLabel(TrajectoryState.STABLE_POOR, f"TIR stable below target ({nxt.tir:.1f}%)")


def _slice_metabolic_state(state: MetabolicState, mask: np.ndarray) -> MetabolicState:
    return MetabolicState(
        supply=state.supply[mask],
        demand=state.demand[mask],
        hepatic=state.hepatic[mask],
        carb_supply=state.carb_supply[mask],
        net_flux=state.net_flux[mask],
        residual=state.residual[mask],
    )


def _build_patient_metabolic_state(df: pd.DataFrame, patient_id: str) -> MetabolicState | None:
    """Build PatientProfile/PatientData and compute MetabolicState once.

    Uses the same schedule-median pattern as ``analyze_patient.py``
    (median of ``scheduled_isf``/``scheduled_cr``/``scheduled_basal_rate``
    over the patient's full history). Returns ``None`` if the profile
    columns are absent or entirely missing so callers can degrade
    gracefully instead of fabricating a flux signal from defaults.
    """
    required = {"scheduled_isf", "scheduled_cr", "scheduled_basal_rate", "glucose"}
    if not required.issubset(df.columns):
        return None
    isf_median = df["scheduled_isf"].median()
    cr_median = df["scheduled_cr"].median()
    basal_median = df["scheduled_basal_rate"].median()
    if pd.isna(isf_median) or pd.isna(cr_median) or pd.isna(basal_median):
        return None

    profile = PatientProfile(
        isf_schedule=[{"time": "00:00", "value": float(isf_median)}],
        cr_schedule=[{"time": "00:00", "value": float(cr_median)}],
        basal_schedule=[{"time": "00:00", "value": float(basal_median)}],
        dia_hours=5.0,
    )
    patient = PatientData(
        glucose=df["glucose"].to_numpy(dtype=float),
        timestamps=df["time"].astype("int64").to_numpy(),
        profile=profile,
        iob=df["iob"].to_numpy(dtype=float) if "iob" in df else None,
        cob=df["cob"].to_numpy(dtype=float) if "cob" in df else None,
        bolus=df["bolus"].to_numpy(dtype=float) if "bolus" in df else None,
        carbs=df["carbs"].to_numpy(dtype=float) if "carbs" in df else None,
        basal_rate=df["actual_basal_rate"].to_numpy(dtype=float)
        if "actual_basal_rate" in df else None,
        patient_id=patient_id,
    )
    try:
        return compute_metabolic_state(patient)
    except Exception:
        # Physiology features are additive context, not required for the
        # core turn/label harness — degrade gracefully rather than fail
        # the whole trajectory build.
        return None


def _trailing_carbs_g(df: pd.DataFrame, start: pd.Timestamp,
                       lookback_hours: float = GLYCOGEN_LOOKBACK_HOURS) -> float:
    if "carbs" not in df.columns:
        return 0.0
    lo = start - pd.Timedelta(hours=lookback_hours)
    mask = (df["time"] >= lo) & (df["time"] < start)
    return float(df.loc[mask, "carbs"].fillna(0).sum())


def build_patient_trajectory(
    parquet_dir: Path | str,
    patient_id: str,
    turn_hours: float = DEFAULT_TURN_HOURS,
    wear_facts_loader: WearFactsLoader | None = None,
) -> list[dict[str, Any]]:
    """Build the full labeled turn sequence for one patient.

    Returns a list of flat dicts (features + label), one per turn, ready
    to be assembled into a DataFrame or logged as an MLflow artifact.
    """
    df = load_patient_grid(parquet_dir, patient_id)
    boundaries = segment_into_turns(df, turn_hours=turn_hours)

    metabolic_state = _build_patient_metabolic_state(df, patient_id)
    loader = wear_facts_loader or WearFactsLoader()
    site_degradation_p = loader.lookup(patient_id).p_site_degradation

    turns: list[TurnFeatures] = []
    for idx, (start, end) in enumerate(boundaries):
        row_mask = ((df["time"] >= start) & (df["time"] < end)).to_numpy()
        window_df = df.loc[row_mask]
        metabolic_slice = (
            _slice_metabolic_state(metabolic_state, row_mask)
            if metabolic_state is not None else None
        )
        carbs_48h_g = _trailing_carbs_g(df, start)
        turns.append(
            compute_turn_features(
                patient_id, idx, start, end, window_df, turn_hours=turn_hours,
                metabolic_slice=metabolic_slice,
                carbs_48h_g=carbs_48h_g,
                site_degradation_p=site_degradation_p,
            )
        )

    records: list[dict[str, Any]] = []
    for idx, turn in enumerate(turns):
        nxt = turns[idx + 1] if idx + 1 < len(turns) else None
        label = label_turn_outcome(turn, nxt)
        record = asdict(turn)
        record["state"] = label.state.value
        record["state_reason"] = label.reason
        records.append(record)
    return records


def build_cohort_trajectories(
    parquet_dir: Path | str,
    patient_ids: list[str] | None = None,
    turn_hours: float = DEFAULT_TURN_HOURS,
    min_turns: int = 4,
) -> pd.DataFrame:
    """Build labeled turns for every (or a chosen set of) cohort patients.

    ``min_turns`` filters out patients with too little history to be
    useful for trend analysis (e.g. very short onboarding windows).
    """
    grid_path = Path(parquet_dir) / "grid.parquet"
    df_all = pd.read_parquet(grid_path, columns=["patient_id"])
    available = sorted(df_all["patient_id"].unique())
    ids = patient_ids if patient_ids is not None else available

    all_records: list[dict[str, Any]] = []
    for patient_id in ids:
        if patient_id not in available:
            continue
        records = build_patient_trajectory(parquet_dir, patient_id, turn_hours=turn_hours)
        if len(records) < min_turns:
            continue
        all_records.extend(records)
    return pd.DataFrame.from_records(all_records)
