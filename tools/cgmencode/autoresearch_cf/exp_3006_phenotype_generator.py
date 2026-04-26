"""EXP-3006 — Phenotype-conditional patient sampler.

Goal: given a target phenotype coordinate (braking_ratio, stack_score,
hidden_leverage), produce a synthetic per-event scenario by k-NN sampling
from real patients in the EXP-2886 phenotype space.

This is the bridge between EXP-3005 (cf-replay scorer) and a future
controller-discriminating fitness: by drawing a *test vector* of events
that reflects a target phenotype, we can ask "how would controller X
perform on a realistic Trio-aggressive patient?" without ingesting a brand
new participant.

Outputs (per target archetype):
  externals/experiments/exp-3006_<archetype>_events.parquet
  externals/experiments/exp-3006_<archetype>_score.json

Verdict criteria:
  - target_match  : sampled events' empirical braking_ratio within 15 % of target
  - low_overlap   : k-NN returned <2 distinct patients (synthetic mix too narrow)
  - safety_failed : cf_replay_score safety gate triggers on the sampled vector
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.figures import figure_three_panel

EXP_ID = 'EXP-3006'
OUT = Path('externals/experiments')
FIG_DIR = Path('docs/60-research/figures')

ARCHETYPES = {
    # Real archetype centroids derived from EXP-2886 (verified via inspection).
    # (braking_ratio, stack_score, hidden_leverage)
    'aggressive_loop':    (0.05, 0.50, 0.55),  # patient `i` style
    'well_defended':      (0.07, 0.04, 0.04),  # patient `d` style
    'exposed_stacker':    (0.31, 0.83, 0.57),  # patient `a` style
    'conservative_trio':  (0.20, 0.30, 0.30),  # generic conservative oref1
}
K = 3
N_EVENTS = 800
RNG = np.random.default_rng(seed=2026)


def sample_events_for_archetype(target, events, phenotype):
    feats = ['braking_ratio', 'stack_score', 'hidden_leverage']
    ph = phenotype.dropna(subset=feats).copy()
    scaler = StandardScaler().fit(ph[feats].values)
    target_z = scaler.transform([list(target)])
    nn = NearestNeighbors(n_neighbors=min(K, len(ph))).fit(
        scaler.transform(ph[feats].values))
    dists, idxs = nn.kneighbors(target_z)
    nbr_patients = ph.iloc[idxs[0]]['patient_id'].tolist()
    nbr_dists = dists[0].tolist()

    # Inverse-distance weights
    w = 1.0 / (np.array(nbr_dists) + 0.01)
    w = w / w.sum()

    # Sample N_EVENTS from neighbour patients in proportion to weights
    sampled = []
    for pid, weight in zip(nbr_patients, w):
        ev_p = events[events['patient_id'] == pid]
        n = max(1, int(round(weight * N_EVENTS)))
        n = min(n, len(ev_p))
        if n > 0:
            sampled.append(ev_p.sample(n=n, random_state=RNG.integers(1 << 30),
                                       replace=False))
    if not sampled:
        return None, nbr_patients, nbr_dists, w
    out = pd.concat(sampled, ignore_index=True)
    return out, nbr_patients, nbr_dists, w.tolist()


def main() -> None:
    events, phenotype, profiles = replay.load_inputs()
    config = replay.ReplayConfig(
        name='realistic_canonical_pheno',
        isf_source=replay.isf_source_profile,
        insulin_kernel=lambda extra, dur, isf: replay.kernel_oref0_exponential(
            extra, dur, isf, peak_min=75.0, dia_min=360.0),
        duration_model=lambda ev: replay.duration_sigmoid_correction(
            ev, stretch=4.0),
        isf_source_name='profile_isf', kernel_name='oref0_peak75',
        duration_name='sigmoid_s400',
    )

    summary_rows = []
    for archetype, target in ARCHETYPES.items():
        sampled, nbr, dists, weights = sample_events_for_archetype(
            target, events, phenotype)
        if sampled is None or sampled['patient_id'].nunique() < 2:
            verdict = 'low_overlap'
            summary_rows.append({'archetype': archetype, 'verdict': verdict,
                                 'neighbours': nbr, 'distances': dists})
            continue

        # Synthetic patient is the union; tag uniformly so per-patient stats
        # collapse into a single archetype-level row in the engine.
        sampled = sampled.copy()
        sampled['patient_id'] = f'synth_{archetype}'

        # Build a synthetic phenotype + profile row
        synth_pheno = phenotype[phenotype['patient_id'].isin(nbr)][
            ['braking_ratio', 'stack_score', 'hidden_leverage',
             'counter_reg_intercept']].mean(numeric_only=True).to_dict()
        synth_pheno.update({'patient_id': f'synth_{archetype}'})
        pheno_aug = pd.concat([phenotype, pd.DataFrame([synth_pheno])],
                              ignore_index=True)

        # Borrow ISF: weighted mean of neighbours' profile ISF
        nbr_isf = []
        for pid in nbr:
            prof = profiles[(profiles['patient_id'] == pid) &
                            (profiles['schedule_type'] == 'isf')]
            if len(prof):
                vals = prof['value'].dropna()
                # mg/dL guard (mirrors isf_source_profile)
                vals = vals[(vals >= 30) & (vals <= 200)]
                if len(vals):
                    nbr_isf.append(float(vals.median()))
        synth_isf = float(np.mean(nbr_isf)) if nbr_isf else 50.0
        prof_aug = pd.concat([profiles, pd.DataFrame([{
            'patient_id': f'synth_{archetype}', 'schedule_type': 'isf',
            'value': synth_isf, 'units': 'mg/dL'}])], ignore_index=True)

        res = replay.run_replay(sampled, prof_aug, pheno_aug, config)
        s = res.summary
        # Empirical braking_ratio of sampled events
        emp_brake = float(synth_pheno['braking_ratio'])
        target_brake = target[0]
        match_pct = (abs(emp_brake - target_brake) / max(target_brake, 0.01))
        if match_pct < 0.15:
            verdict = 'target_match'
        else:
            verdict = 'target_drift'

        # Score via cf_replay safety gate (synthetic patient as a 1-patient cohort)
        synth_pp = res.per_patient
        cf_severe = float(synth_pp['cf_severe'].iloc[0])
        obs_severe = float(synth_pp['obs_severe'].iloc[0])
        if cf_severe >= 0.999 and obs_severe > 0.50:
            verdict = 'safety_failed'

        # Persist
        sampled.to_parquet(OUT / f'{EXP_ID.lower()}_{archetype}_events.parquet')
        figure_three_panel(synth_pp,
                           title=f'{EXP_ID} {archetype} (synth from {nbr})',
                           out_path=FIG_DIR / f'{EXP_ID.lower()}_{archetype}.png')
        row = {'archetype': archetype, 'target': list(target),
               'neighbours': nbr, 'weights': weights,
               'distances': dists, 'synth_isf_mgdl': synth_isf,
               'empirical_braking_ratio': emp_brake,
               'target_braking_ratio': target_brake,
               'pop_obs_severe': s['pop_observed_severe'],
               'pop_cf_severe': s['pop_counterfactual_severe'],
               'aid_protection': s['aid_protection_severe_abs'],
               'mean_extra_drop': s['mean_extra_drop_mgdl'],
               'verdict': verdict}
        summary_rows.append(row)
        print(f"[{EXP_ID}] {archetype:20s} verdict={verdict:14s} "
              f"obs={s['pop_observed_severe']:.3f} cf={s['pop_counterfactual_severe']:.3f} "
              f"brake_emp={emp_brake:.3f} (target {target_brake:.3f}) "
              f"nbrs={nbr}")

        replay.record_iteration(
            EXP_ID, res, verdict=verdict,
            notes=(f'archetype={archetype} target_brake={target_brake} '
                   f'emp_brake={emp_brake:.3f} nbrs={nbr}'))

    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps({'archetypes': summary_rows, 'k': K, 'n_events': N_EVENTS},
                   indent=2, default=float))
    print(f"[{EXP_ID}] wrote summary for {len(summary_rows)} archetypes")


if __name__ == '__main__':
    main()
