"""Shared counterfactual AID-off replay engine.

Generalises ``exp_counterfactual_replay_2889.py`` into composable pieces so
follow-on experiments can swap one factor at a time (per-patient ISF,
PK-delayed insulin, sigmoidal nadir, ascent-direction cf, …).

Public API
----------
- ``ReplayConfig``  — names the (isf_source, kernel, duration_model) triple.
- ``run_replay(events, profiles, phenotype, config)`` — returns a per-event
  DataFrame with cf_nadir / cf_severe / cf_hypo and a per-patient rollup.
- ``record_iteration(...)`` — append a row to the autoresearch ledger.

The engine never reads or writes paths directly; callers pass DataFrames in
and persist outputs themselves. This keeps the engine importable from inside
``tools/aid-autoresearch/`` later for the autoresearch-fitness wrapper.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np
import pandas as pd

ISF_POP_DEFAULT = 50.0  # mg/dL/U, EXP-2756 population median


# ---------------------------------------------------------------------------
# ISF sources
# ---------------------------------------------------------------------------
def isf_source_population(_profiles: Optional[pd.DataFrame],
                          patient_ids: pd.Series,
                          fallback: float = ISF_POP_DEFAULT) -> pd.Series:
    """Uniform population ISF for every patient (the EXP-2889 baseline)."""
    return pd.Series(fallback, index=patient_ids.index, name='isf_used')


def isf_source_profile(profiles: pd.DataFrame,
                       patient_ids: pd.Series,
                       fallback: float = ISF_POP_DEFAULT) -> pd.Series:
    """Per-patient profile ISF (median of mg/dL ``isf`` schedule rows).

    Values <30 mg/dL/U are flagged suspect (likely mmol/L mis-tag) and fall
    back to ``fallback``. Patients with no rows likewise fall back.
    """
    if profiles is None or profiles.empty:
        return isf_source_population(profiles, patient_ids, fallback)
    isf = profiles[(profiles['schedule_type'] == 'isf') &
                   (profiles['units'] == 'mg/dL')]
    per_pt = isf.groupby('patient_id')['value'].median()
    per_pt = per_pt.where(per_pt >= 30.0, other=fallback)
    return patient_ids.map(per_pt).fillna(fallback).rename('isf_used')


# ---------------------------------------------------------------------------
# Insulin kernels (extra_drop given extra_insulin and duration_min)
# ---------------------------------------------------------------------------
def kernel_instantaneous(extra_insulin: pd.Series,
                         duration_min: pd.Series,
                         isf_used: pd.Series) -> pd.Series:
    """EXP-2889 baseline: drop = extra_insulin × ISF, no PK delay."""
    return extra_insulin * isf_used


def kernel_oref0_exponential(extra_insulin: pd.Series,
                             duration_min: pd.Series,
                             isf_used: pd.Series,
                             dia_min: float = 360.0,
                             peak_min: float = 75.0) -> pd.Series:
    """oref0 exponential PK kernel: fraction of effect realised over the
    descent window. Default DIA=6h, peak=75min (oref0 ultra-rapid default).

    The realised fraction at time ``t`` is ``1 - (1+(t/τ))·exp(-t/τ)`` for the
    exponential approximation; we evaluate it at the midpoint of each event's
    duration so the basal deficit's *average* PK weight applies.
    """
    # τ chosen so action peaks near peak_min for the bi-exponential
    # approximation; for the simple form below τ ≈ peak_min works well.
    tau = peak_min / 1.0
    t_mid = (duration_min / 2.0).clip(lower=1.0).to_numpy()
    frac = 1.0 - (1.0 + t_mid / tau) * np.exp(-t_mid / tau)
    # Cap at 1.0 (cannot deliver more effect than the insulin contains)
    frac = np.clip(frac, 0.0, 1.0)
    return extra_insulin * isf_used * pd.Series(frac, index=extra_insulin.index)


# ---------------------------------------------------------------------------
# Duration models
# ---------------------------------------------------------------------------
def duration_linear(events: pd.DataFrame) -> pd.Series:
    """EXP-2889 baseline: (bg_start − bg_nadir) / (−descent_slope)."""
    return ((events['bg_start'] - events['bg_nadir']) /
            (-events['descent_slope'])).clip(lower=5, upper=240)


def duration_sigmoid_correction(events: pd.DataFrame,
                                stretch: float = 1.25) -> pd.Series:
    """Sigmoidal descents are slower near the nadir; multiplying linear
    duration by ``stretch`` (default 25%) approximates the integral of a
    sigmoid divided by its mid-slope. Conservative — does not change rank
    order; tightens magnitudes."""
    return (duration_linear(events) * stretch).clip(lower=5, upper=300)


# ---------------------------------------------------------------------------
# Replay engine
# ---------------------------------------------------------------------------
IsfSource = Callable[[Optional[pd.DataFrame], pd.Series], pd.Series]
InsulinKernel = Callable[[pd.Series, pd.Series, pd.Series], pd.Series]
DurationModel = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class ReplayConfig:
    name: str
    isf_source: IsfSource = field(default=isf_source_population, repr=False)
    insulin_kernel: InsulinKernel = field(default=kernel_instantaneous,
                                          repr=False)
    duration_model: DurationModel = field(default=duration_linear, repr=False)
    isf_source_name: str = 'population'
    kernel_name: str = 'instantaneous'
    duration_name: str = 'linear'


@dataclass
class ReplayResult:
    config: ReplayConfig
    events: pd.DataFrame      # per-event with cf_nadir, cf_severe, cf_hypo
    per_patient: pd.DataFrame  # rollup with obs_severe, cf_severe, protection
    summary: Dict[str, float]  # population aggregates + correlation block


def run_replay(events: pd.DataFrame,
               profiles: Optional[pd.DataFrame],
               phenotype: Optional[pd.DataFrame],
               config: ReplayConfig) -> ReplayResult:
    """Run cf-replay with the supplied (isf_source, kernel, duration) triple.

    ``events`` must contain: patient_id, bg_start, bg_nadir, descent_slope,
    sched_basal, actual_basal. Filter for descent events upstream.
    """
    ev = events.copy()

    duration_min = config.duration_model(ev)
    isf_used = config.isf_source(profiles, ev['patient_id'])
    basal_deficit_uh = (ev['sched_basal'] - ev['actual_basal']).clip(lower=0)
    extra_insulin_u = basal_deficit_uh * duration_min / 60.0
    extra_drop_mgdl = config.insulin_kernel(extra_insulin_u, duration_min,
                                            isf_used)

    ev['duration_min'] = duration_min
    ev['isf_used'] = isf_used.to_numpy()
    ev['basal_deficit_uh'] = basal_deficit_uh
    ev['extra_insulin_u'] = extra_insulin_u
    ev['extra_drop_mgdl'] = extra_drop_mgdl
    ev['cf_nadir'] = ev['bg_nadir'] - extra_drop_mgdl
    ev['cf_severe'] = (ev['cf_nadir'] < 54).astype(int)
    ev['cf_hypo'] = (ev['cf_nadir'] < 70).astype(int)
    ev['obs_severe'] = (ev['bg_nadir'] < 54).astype(int)
    ev['obs_hypo'] = (ev['bg_nadir'] < 70).astype(int)

    per_patient = (
        ev.groupby('patient_id')
          .agg(n_events=('bg_start', 'size'),
               mean_duration=('duration_min', 'mean'),
               mean_deficit_uh=('basal_deficit_uh', 'mean'),
               mean_extra_drop=('extra_drop_mgdl', 'mean'),
               isf_used=('isf_used', 'first'),
               obs_severe=('obs_severe', 'mean'),
               cf_severe=('cf_severe', 'mean'),
               obs_hypo=('obs_hypo', 'mean'),
               cf_hypo=('cf_hypo', 'mean'))
          .reset_index())
    per_patient['aid_protection_severe'] = (
        per_patient['cf_severe'] - per_patient['obs_severe'])
    per_patient['aid_protection_hypo'] = (
        per_patient['cf_hypo'] - per_patient['obs_hypo'])

    if phenotype is not None and not phenotype.empty:
        keep = [c for c in [
            'patient_id', 'controller', 'lineage', 'stack_score',
            'braking_ratio', 'counter_reg_intercept', 'hidden_leverage',
            'archetype'] if c in phenotype.columns]
        per_patient = per_patient.merge(phenotype[keep], on='patient_id',
                                        how='left')

    summary = {
        'config_name': config.name,
        'isf_source': config.isf_source_name,
        'kernel': config.kernel_name,
        'duration_model': config.duration_name,
        'n_patients': int(per_patient.shape[0]),
        'n_events': int(ev.shape[0]),
        'pop_observed_severe': float(ev['obs_severe'].mean()),
        'pop_counterfactual_severe': float(ev['cf_severe'].mean()),
        'pop_observed_hypo': float(ev['obs_hypo'].mean()),
        'pop_counterfactual_hypo': float(ev['cf_hypo'].mean()),
        'aid_protection_severe_abs': float(
            ev['cf_severe'].mean() - ev['obs_severe'].mean()),
        'aid_protection_hypo_abs': float(
            ev['cf_hypo'].mean() - ev['obs_hypo'].mean()),
        'mean_duration_min': float(ev['duration_min'].mean()),
        'mean_extra_drop_mgdl': float(ev['extra_drop_mgdl'].mean()),
        'mean_isf_used': float(ev['isf_used'].mean()),
    }
    return ReplayResult(config=config, events=ev, per_patient=per_patient,
                        summary=summary)


# ---------------------------------------------------------------------------
# Iteration ledger
# ---------------------------------------------------------------------------
LEDGER_PATH = Path('tools/aid-autoresearch/autoresearch_cf_results.tsv')
LEDGER_HEADER = (
    'timestamp\texp_id\tconfig_name\tisf_source\tkernel\tduration_model\t'
    'n_patients\tn_events\tpop_obs_severe\tpop_cf_severe\t'
    'aid_protection_severe\tmean_duration_min\tmean_extra_drop_mgdl\t'
    'verdict\tnotes\n')


def record_iteration(exp_id: str, result: ReplayResult, verdict: str,
                     notes: str = '',
                     ledger: Path = LEDGER_PATH) -> None:
    """Append a row to the autoresearch ledger."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists() or ledger.stat().st_size == 0:
        ledger.write_text(LEDGER_HEADER)
    s = result.summary
    row = (f"{datetime.now(timezone.utc).isoformat()}\t{exp_id}\t"
           f"{s['config_name']}\t{s['isf_source']}\t{s['kernel']}\t"
           f"{s['duration_model']}\t{s['n_patients']}\t{s['n_events']}\t"
           f"{s['pop_observed_severe']:.4f}\t"
           f"{s['pop_counterfactual_severe']:.4f}\t"
           f"{s['aid_protection_severe_abs']:.4f}\t"
           f"{s['mean_duration_min']:.2f}\t"
           f"{s['mean_extra_drop_mgdl']:.2f}\t"
           f"{verdict}\t{notes.replace(chr(9), ' ').replace(chr(10), ' ')}\n")
    with ledger.open('a') as fh:
        fh.write(row)


# ---------------------------------------------------------------------------
# Data loaders (paths centralised so experiments stay short)
# ---------------------------------------------------------------------------
EVENTS_PATH = Path('externals/experiments/exp-2881_evening_drivers.parquet')
PHENO_PATH = Path('externals/experiments/exp-2886_phenotype.parquet')
PROFILES_PATH = Path('externals/ns-parquet/training/profiles.parquet')


def load_inputs():
    """Load (descent-filtered events, phenotype, profiles)."""
    events = pd.read_parquet(EVENTS_PATH)
    descent = events[(events['descent_slope'] < -0.05) &
                     (events['bg_nadir'] < events['bg_start'])].copy()
    phenotype = pd.read_parquet(PHENO_PATH) if PHENO_PATH.exists() else None
    profiles = pd.read_parquet(PROFILES_PATH) if PROFILES_PATH.exists() else None
    return descent, phenotype, profiles
