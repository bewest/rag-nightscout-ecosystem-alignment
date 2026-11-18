"""Assess scoped smoke correctness and compare available SQL signals."""

import json
import math
from pathlib import Path
import sys

from contract import require

CATALOG = Path(__file__).resolve().parent.parent / 'run-catalog'
sys.path.insert(0, str(CATALOG))
from retained import get, project


def sql_deltas(current, baseline):
    deltas = {}
    for key, signal in current.items():
        if not key.startswith('db.'):
            continue
        previous = get(baseline, key)
        if not isinstance(previous, dict) or signal['status'] != 'MEASURED':
            continue
        if any(previous.get(axis) != signal[axis] for axis in ('unit', 'denominator', 'scope')):
            continue
        old = previous.get('value')
        if type(old) not in (int, float) or not math.isfinite(old) or old < 0:
            continue
        delta = signal['value'] - old
        # Retain timing deviations with relative context. Only a deliberately
        # specified statement-count baseline can demand exactness.
        deltas[key] = {'baseline': old, 'observed': signal['value'], 'delta': delta,
                       'relativeDelta': delta / old if old else None,
                       'denominator': signal['denominator'], 'population': signal['population']}
    return deltas


def assess(root, baseline_file=None):
    from runner import write
    result = project(root, root.name)
    checks = result['oracles']
    exercised = {
        'stored': checks['stored'], 'clinical': checks['clinical'],
        'fixtureOwnership': checks['ownership'], 'viewerTenantBindings': checks['clientFrames'],
    }
    signal_report = {key: signal for key, signal in result['signals'].items() if key.startswith('db.')}
    report = {'verdict': 'PASS' if all(value in ('GREEN', 'PASS') for value in exercised.values()) else 'FAIL',
              'scope': 'retained per-tenant count and selected clinical/client binding observations',
              'oracles': exercised, 'wholePopulationClinicalTails': 'UNMEASURED',
              'restore': 'NOT_EXERCISED', 'capacityAcceptance': 'NOT_GRANTED',
              'sqlSignals': signal_report, 'sqlBaseline': 'UNMEASURED'}
    if baseline_file:
        baseline = json.loads(Path(baseline_file).read_text())
        require(get(baseline, 'version') == 1 and isinstance(get(baseline, 'signals'), dict),
                'M7_SMOKE_BASELINE_SHAPE')
        report['sqlDeltas'] = sql_deltas(signal_report, baseline['signals'])
        report['sqlBaseline'] = 'COMPARED' if report['sqlDeltas'] else 'UNMEASURED'
        expected = baseline.get('exactStatementSignals', [])
        require(isinstance(expected, list) and all(isinstance(key, str) and key.endswith('.statements')
                                                  for key in expected), 'M7_SMOKE_BASELINE_SHAPE')
        report['statementCountControl'] = ('PASS' if all(
            get(report, 'sqlDeltas', key, 'delta') == 0 for key in expected) else 'FAIL') if expected else 'NOT_EXERCISED'
        if report['statementCountControl'] == 'FAIL':
            report['verdict'] = 'FAIL'
    write(root / 'smoke.json', report)
    require(report['verdict'] == 'PASS', 'M7_SMOKE_WITNESS_OR_STATEMENT_COUNT')
