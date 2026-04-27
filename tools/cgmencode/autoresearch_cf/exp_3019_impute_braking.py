"""EXP-3019 — Impute braking_ratio for unknown-stratum patients.

EXP-3018's stratified safety gate fell back to a generic 'unknown' stratum
for 939 events from 12 patients absent from the EXP-2886 phenotype parquet.
This experiment imputes those patients' braking_ratio for use as a *safety
default* (NOT as a best estimate of their true braking) — see EXP-3027.

Imputation rules (in priority order):

1. If `patient_id` already has a non-null `braking_ratio` in the source
   phenotype parquet, keep it.
2. Else, look up the patient's controller in the ascent events parquet:
   - 'Loop'    → use Loop median (0.057)
   - 'Trio'    → use Trio median (0.052)
   - 'AAPS'    → use AAPS median (0.421)
   - 'OpenAPS' → treat as legacy AAPS (per stored memory: ODC patients run
     AAPS-platform with oref0 algorithm); use AAPS median.
3. Else (controller is also NaN), use overall cohort median (0.058).

**EXP-3027-FIX (2026-04-26): safety-conservative floor.**

EXP-3027 LOO showed median imputation has only 31.6% stratum-agreement
and 2 high→low flips on Trio (under-protective). To prevent unknown new
patients from slipping into the low/mid stratum and bypassing the
cf-replay-score-v3 stratified safety gate, *all imputed values* are
floored at `STRAT_BRAKING_EDGES.upper = 0.10`, forcing them into the
'high' stratum. Combined with `braking_mode='drop'` in the scorer, this
guarantees unknown-controller events are excluded from the candidate
policy by default.

Trades a small composite Δ for a hard safety guarantee. Observed values
are untouched.

Outputs
-------
externals/experiments/exp-3019_phenotype_imputed.parquet
externals/experiments/exp-3019_summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EXP_ID = 'EXP-3019'
PH_SRC = Path('externals/experiments/exp-2886_phenotype.parquet')
ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
OUT = Path('externals/experiments')
# EXP-3027-FIX: safety-conservative floor for any imputed value.
# Coincides with STRAT_BRAKING_EDGES upper boundary (0.10) so imputed
# patients land in the 'high' stratum and are dropped under
# braking_mode='drop'.
SAFETY_FLOOR = 0.10


def _infer_controller_by_prefix(pid: str) -> str | None:
    """Heuristic from known cohort: odc-* → AAPS, ns-* → Trio, single-letter → Loop."""
    if pid.startswith('odc-'):
        return 'AAPS'
    if pid.startswith('ns-'):
        return 'Trio'
    if len(pid) <= 2 and pid.isalpha():
        return 'Loop'
    return None


def main() -> None:
    ph = pd.read_parquet(PH_SRC)
    ev = pd.read_parquet(ASCENT)

    # Per-controller braking medians (from known patients only)
    known = ph.dropna(subset=['braking_ratio'])
    ctrl_median = known.groupby('controller')['braking_ratio'].median().to_dict()
    cohort_median = float(known['braking_ratio'].median())
    ctrl_median['OpenAPS'] = ctrl_median.get('AAPS', cohort_median)

    # Resolve controller per patient: ascent → phenotype → prefix heuristic
    ev_ctrl = (ev.dropna(subset=['controller'])
                 .groupby('patient_id')['controller']
                 .agg(lambda s: s.mode().iat[0] if len(s.mode()) else None)
                 .to_dict())

    all_pids = sorted(set(ev['patient_id'].unique()) | set(ph['patient_id']))
    rows = []
    n_imputed_ctrl = 0
    n_imputed_cohort = 0
    for pid in all_pids:
        existing = ph[ph['patient_id'] == pid]
        if len(existing) and pd.notna(existing.iloc[0]['braking_ratio']):
            r = existing.iloc[0].to_dict()
            r['imputed'] = False
            r['imputation_source'] = 'observed'
            rows.append(r)
            continue
        # Need imputation
        ctrl = (existing.iloc[0]['controller'] if len(existing)
                and pd.notna(existing.iloc[0]['controller'])
                else ev_ctrl.get(pid))
        ctrl_source = 'phenotype/ascent'
        if not ctrl or pd.isna(ctrl):
            ctrl = _infer_controller_by_prefix(pid)
            ctrl_source = 'prefix_heuristic' if ctrl else 'none'
        if ctrl and ctrl in ctrl_median:
            br_raw = float(ctrl_median[ctrl])
            src = f'controller_median:{ctrl}({ctrl_source})'
            n_imputed_ctrl += 1
        else:
            br_raw = cohort_median
            src = 'cohort_median'
            n_imputed_cohort += 1
        # EXP-3027-FIX: apply safety-conservative floor to imputed values.
        br = max(br_raw, SAFETY_FLOOR)
        if br > br_raw:
            src = src + f'+safety_floor({SAFETY_FLOOR})'
        rows.append({
            'patient_id': pid,
            'controller': ctrl,
            'braking_ratio': br,
            'braking_ratio_raw': br_raw,
            'algorithm_mode': (existing.iloc[0]['algorithm_mode'] if len(existing) else 'unknown'),
            'imputed': True,
            'imputation_source': src,
        })
    out_df = pd.DataFrame(rows)
    # Carry over other columns where available
    for col in [c for c in ph.columns
                if c not in {'patient_id', 'controller', 'braking_ratio', 'algorithm_mode'}]:
        if col not in out_df.columns:
            out_df[col] = out_df['patient_id'].map(
                ph.set_index('patient_id')[col].to_dict())

    out_path = OUT / f'{EXP_ID.lower()}_phenotype_imputed.parquet'
    out_df.to_parquet(out_path)

    summary = {
        'n_total': int(len(out_df)),
        'n_observed': int((~out_df['imputed']).sum()),
        'n_imputed_via_controller': int(n_imputed_ctrl),
        'n_imputed_via_cohort': int(n_imputed_cohort),
        'controller_medians': {k: float(v) for k, v in ctrl_median.items()},
        'cohort_median': cohort_median,
        'imputed_patients': out_df.loc[out_df['imputed'],
            ['patient_id', 'controller', 'braking_ratio', 'imputation_source']
        ].to_dict(orient='records'),
        'output': str(out_path),
    }
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))
    print(f"[{EXP_ID}] {summary['n_observed']} observed + "
          f"{n_imputed_ctrl} imputed-by-controller + "
          f"{n_imputed_cohort} imputed-by-cohort = {len(out_df)} total")
    print(f"  Controller medians: {summary['controller_medians']}")
    print(f"  → {out_path}")
    for r in summary['imputed_patients']:
        print(f"    {r['patient_id']:<22}  ctrl={str(r['controller']):<8}  "
              f"br={r['braking_ratio']:.3f}  src={r['imputation_source']}")


if __name__ == '__main__':
    main()
