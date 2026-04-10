#!/usr/bin/env python3
"""
Rerun key experiments with parquet terrarium data (oref0 IOB/COB fix).

Prior experiments used real_data_adapter.build_nightscout_grid() which only
read Loop devicestatus — oref0 records were silently dropped.  Patient b
(98% oref0) had ~0 IOB/COB as a result.

The parquet terrarium (ns2parquet/grid.py) correctly reads both Loop and
oref0 devicestatus, giving patient b real IOB (mean=1.8U) and COB (mean=27g).

This script re-runs EXP-2051 (circadian ISF), EXP-2071 (therapy optimization),
and EXP-2091 (insulin pharmacokinetics) using the fixed data path, then
compares results for patient b against the original JSON-path results.
"""

import sys
import os
import json
import time
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# Must be run from repo root
REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
os.chdir(REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'tools', 'cgmencode'))

# ── Monkey-patch: replace load_patients with parquet version ──────────
from cgmencode.real_data_adapter import load_parquet_patients

TERRARIUM = 'externals/ns-parquet/training'


def _parquet_load_patients(patients_dir=None, max_patients=None,
                           patient_filter=None, verbose=True):
    """Drop-in replacement using terrarium parquet."""
    return load_parquet_patients(TERRARIUM, max_patients=max_patients,
                                 patient_filter=patient_filter, verbose=verbose)


# Patch at the source so all importers pick it up
import cgmencode.exp_metabolic_flux as emf
_original_load = emf.load_patients
emf.load_patients = _parquet_load_patients

# Also patch exp_metabolic_441 which re-exports
import cgmencode.exp_metabolic_441 as em441
em441.load_patients = _parquet_load_patients


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def run_experiment(name, func):
    """Run a single experiment function, capturing results."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = func()
        elapsed = time.time() - t0
        print(f"\n  ✓ {name} completed in {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  ✗ {name} failed in {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    os.makedirs('externals/experiments', exist_ok=True)
    results = {}
    t_total = time.time()

    # Import experiment modules (they call load_patients at module level)
    print("Loading patients via parquet terrarium...")
    t0 = time.time()
    import exp_circadian_2051 as circ
    import exp_optimization_2071 as opt
    import exp_pharmacokinetics_2091 as pk
    print(f"  Loaded all patients in {time.time()-t0:.1f}s (vs ~180s JSON)\n")

    # ── EXP-2051: Circadian ISF ──
    results['EXP-2051'] = run_experiment('EXP-2051: Circadian ISF', circ.exp_2051_circadian_isf)
    results['EXP-2052'] = run_experiment('EXP-2052: Circadian Basal', circ.exp_2052_circadian_basal)
    results['EXP-2053'] = run_experiment('EXP-2053: Dawn Phenomenon', circ.exp_2053_dawn_phenomenon)
    results['EXP-2056'] = run_experiment('EXP-2056: IOB Sensitivity', circ.exp_2056_iob_sensitivity)
    results['EXP-2057'] = run_experiment('EXP-2057: Counter-Regulatory', circ.exp_2057_counter_regulatory)

    # ── EXP-2071: Therapy Optimization ──
    results['EXP-2071'] = run_experiment('EXP-2071: Optimal ISF', opt.exp_2071_optimal_isf)
    results['EXP-2072'] = run_experiment('EXP-2072: Optimal CR', opt.exp_2072_optimal_cr)
    results['EXP-2073'] = run_experiment('EXP-2073: Optimal Basal', opt.exp_2073_optimal_basal)

    # ── EXP-2091: Insulin Pharmacokinetics ──
    results['EXP-2091'] = run_experiment('EXP-2091: Insulin PK', pk.exp_2091_insulin_pk)
    results['EXP-2092'] = run_experiment('EXP-2092: Dose-Response', pk.exp_2092_dose_response)
    results['EXP-2096'] = run_experiment('EXP-2096: Stacking', pk.exp_2096_stacking)
    results['EXP-2097'] = run_experiment('EXP-2097: IOB Accuracy', pk.exp_2097_iob_accuracy)

    elapsed_total = time.time() - t_total
    n_ok = sum(1 for v in results.values() if v is not None)
    n_fail = sum(1 for v in results.values() if v is None)

    print(f"\n{'='*60}")
    print(f"  Rerun complete: {n_ok} passed, {n_fail} failed, {elapsed_total:.0f}s total")
    print(f"{'='*60}")

    # Save summary
    summary = {
        'data_source': 'parquet_terrarium',
        'terrarium_path': TERRARIUM,
        'fix_description': 'oref0 IOB/COB now included via ns2parquet grid (was Loop-only)',
        'affected_patients': ['b (98% oref0, was getting ~0 IOB/COB)'],
        'experiments_rerun': list(results.keys()),
        'passed': n_ok,
        'failed': n_fail,
        'total_time_s': round(elapsed_total, 1),
    }

    with open('externals/experiments/rerun-parquet-summary.json', 'w') as f:
        json.dump(summary, f, indent=2, cls=NumpyEncoder)
    print(f"\n  Summary → externals/experiments/rerun-parquet-summary.json")


if __name__ == '__main__':
    main()
