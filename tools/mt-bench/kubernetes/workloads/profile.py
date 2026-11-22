#!/usr/bin/env python3
"""Explain and bind finite inputs to the existing Kubernetes/M7 adapter; no traffic."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(ROOT / 'tools/mt-bench/m7-joined'))
import workload_runtime
import primer_options
import population_ceiling
import populated_history as history
SHAPES = workload_runtime.SHAPES


def need(value, code):
    if not value:
        raise ValueError('K8S_LOAD_' + code)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def validate(p, *, require_pins=True):
    need(p['version'] == 1 and p['kind'] == 'k8s-m7-workload-profile', 'PROFILE')
    if require_pins or 'referencePins' in p:
        need(all(isinstance(p['referencePins'][k], str) and
                 __import__('re').fullmatch(r'[a-f0-9]{40}', p['referencePins'][k])
                 for k in ('core', 'deploy', 'bindingCommit')), 'SOURCE_PINS')
    n = p['population']['provisionedTenants']
    population_ceiling.from_profile(p,need)
    w = p['workload']
    need(workload_runtime.workload_inputs.tenants(n) and n >= 2, 'TENANTS')
    ordinary = workload_runtime.ordinary_count(n, p['population']['ordinaryRosterTenants'], need)
    workload_runtime.validate(w, need, ordinary)
    if w.get('driverShape') == 'looping-v1':
        need(p['history'].get('mode') == history.MODE_LOOPING and n == ordinary,
             'LOOPING_OFFER_REQUIRES_FULL_FIXTURE_ROSTER')
    need(workload_runtime.workload_inputs.tenants(p['population']['hotFactor']) and
         p['population']['hotFactor'] == w.get('hotFactor', 1),
         'ADAPTER_ROSTER_OR_HOT_FACTOR_UNSUPPORTED')
    try:
        history.validate(p['history'])
    except ValueError as error:
        raise ValueError('K8S_LOAD_HISTORY_UNSUPPORTED') from error
    burst = p['phases'].get('reconnectBurstClients', 0)
    viewer_setup = workload_runtime.viewer_plan.setup(w)
    need(p['phases']['restart'] is False and type(burst) is int and
         (burst == 0 or viewer_setup['scenario'] == 'simultaneous-reconnect' and
          burst == w['logicalPollingClients']), 'RESTART_IS_SEPARATE_SCENARIO')
    if 'cohortReadySeconds' in p['phases']:
        need(workload_runtime.workload_inputs.seconds(p['phases']['cohortReadySeconds']), 'COHORT_READY_WINDOW')
    workload_runtime.workload_inputs.startup_selection(p['phases'],need)
    primer_options.from_profile(p,need)
    work = p['phases']['workSeconds']
    need(workload_runtime.workload_inputs.seconds(work) and
         work >= w.get('setupSeconds', 310) + w['loadSeconds'] + w.get('drainSeconds', 120) + 5,
         'WORK_WINDOW')
    need(workload_runtime.workload_inputs.seconds(p['phases']['cleanupSeconds']), 'CLEANUP_WINDOW')
    need(p['capacityAcceptance'] == 'NOT_GRANTED', 'NO_CAPACITY_GRANT')
    return p


def describe(p):
    validate(p)
    n = p['population']['ordinaryRosterTenants']
    w = p['workload']
    cycles, rates = workload_runtime.rates(w, n, p['history'])
    cycle_ms = cycles['w_sgv']
    inputs=workload_runtime.workload_inputs
    startup=inputs.startup_selection(p['phases'],need)
    return {'version': 1, 'profile': p['name'],
            **({'history': dict(p['history'], rowsPerTenant=history.ROWS if p['history']['mode'] == history.MODE else history.rows_per_tenant(p['history']), stepMs=history.STEP_MS)}
               if p['history'] != history.BASELINE else {}), 'basis': 'read-derived equations from generated M7 workload',
            **({primer_options.FIELD:p['phases'][primer_options.FIELD]} if primer_options.FIELD in p['phases'] else {}),
            **({population_ceiling.FIELD:population_ceiling.from_profile(p,need)} if 'maxTenants' in p['population'] else {}),
            **({'populationCommissioning':population_ceiling.commissioning(p['population']['provisionedTenants'],primer_options.from_profile(p,need))}
               if 'maxTenants' in p['population'] else {}),
            'population': p['population'], 'workload': w, 'arrivalCycleMs': cycle_ms, 'shapeCycleMs': cycles, 'shapeRequestsPerSecond': rates,
            'effectivePhaseWindows': {
                key: {'seconds': w.get(key, default), 'origin': 'authored' if key in w else 'legacy default'}
                for key, default in (('setupSeconds', 310), ('drainSeconds', 120))
            } | {key:{'seconds':p['phases'][key], 'origin':'authored'} for key in
                 ('cohortReadySeconds',) if key in p['phases']},
            'startupWindows':{target:{key:{'seconds':startup.get(target,{}).get(key,value),
                                          'origin':'authored' if key in startup.get(target,{}) else 'reference'}
                                      for key,value in defaults.items()}
                              for target,defaults in (('compose',inputs.COMPOSE_STARTUP_DEFAULTS),
                                                       ('kubernetes',inputs.KUBERNETES_STARTUP_DEFAULTS))},
            'effectiveOrdinaryIngestionCadenceSecondsPerTenant': cycle_ms / 1000,
            'nominalIngestionCadenceSeconds': 300,
            'cadenceMultiplier': 300000 / cycle_ms,
            'nominalScenarioRequests': sum(rates.values()) * w['loadSeconds'],
            'ordinaryWritesPerSecond': sum(v for k, v in rates.items() if k.startswith('w_')),
            'ordinaryReadsPerSecond': sum(v for k, v in rates.items() if k.startswith('r_')),
            'setupJwtExchanges': n, 'stockViewers': w['logicalPollingClients'],
            'viewerSetup': workload_runtime.viewer_plan.setup(w),
            'probeWritesPerSecondWhileOpen': 1000 / w['probeEveryMs'],
            'probeWrites': 'observed independently; initial write and drain can extend the nominal window',
            'limits': ['realistic-v1 uses sensor cadence when both the uniform and write factors are one; aggregate profiles retain their authored rate',
                       'HTTP logical pollers are not a configured population; shape rates define offered REST',
                       'all ordinary roster tenants are eligible; actual changed/witness sets are observed',
                       'hotFactor weights the first roster tenant; viewerSetup.scenario selects any reconnect burst'],
            'capacityAcceptance': 'NOT_GRANTED'}


def bind(p, config):
    """Produce an input for adapter.prepare; existing custody/preflight still applies."""
    validate(p)
    need(config['pins']['pair'] == {k: p['referencePins'][k] for k in ('core', 'deploy')} and
         config['pins']['bindingCommit'] == p['referencePins']['bindingCommit'], 'SOURCE_PROFILE_MISMATCH')
    need(config['tenants'] == p['population']['provisionedTenants'], 'CONFIG_ROSTER')
    from datetime import datetime
    cutoff = lambda v: datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp()
    remaining = cutoff(config['deadlines']['workUntil']) - __import__('time').time()
    need(remaining >= p['phases']['workSeconds'], 'FRESH_WORK_WINDOW_REQUIRED')
    need(cutoff(config['deadlines']['cleanupUntil']) - cutoff(config['deadlines']['workUntil']) >=
         p['phases']['cleanupSeconds'], 'CLEANUP_WINDOW')
    existing = config.get('workload', {})
    need(set(existing) <= set(p['workload']) | {'pointId', 'hotFactor', 'offeredRps', 'workloadMix', 'workloadScale'}, 'UNKNOWN_WORKLOAD_FIELD')
    need(existing.get('hotFactor', 1) == p['population']['hotFactor'], 'PROFILE_HOT_FACTOR')
    need(existing.get('probeLedger',p['workload'].get('probeLedger')) == p['workload'].get('probeLedger'), 'PROBE_LEDGER_CHANGED')
    budget=p['workload'].get('evaluatorProgressBudget')
    need(existing.get('evaluatorProgressBudget',budget)==budget,'EVALUATOR_PROGRESS_BUDGET_CHANGED')
    observation=p['workload'].get('drainObservation')
    need(existing.get('drainObservation',observation)==observation,'DRAIN_OBSERVATION_CHANGED')
    need(config.get('history', p['history']) == p['history'], 'HISTORY_CHANGED')
    result = copy.deepcopy(config)
    if p['history'] != history.BASELINE:
        result['history'] = p['history']
    result.pop('accessSetupSeconds', None)
    data_seconds=workload_runtime.workload_inputs.startup_selection(p['phases'],need).get('kubernetes',{}).get('dataPrimerSeconds')
    need(config.get('dataPrimerSeconds',data_seconds)==data_seconds,'DATA_PRIMER_WINDOW_CHANGED')
    if data_seconds is not None:
        result['dataPrimerSeconds']=data_seconds
    primer = primer_options.from_profile(p,need)
    population=population_ceiling.from_profile(p,need)
    need(config.get(population_ceiling.FIELD,population)==population,'POPULATION_CEILING_CHANGED')
    if population is not None:result[population_ceiling.FIELD]=population
    need(config.get(primer_options.FIELD,primer)==primer,'PRIMER_OPTIONS_CHANGED')
    if primer is not None:
        result[primer_options.FIELD]=primer
    result.pop('preloadConvergence', None)
    # A profile intentionally replaces the old rate selection, but preserves
    # runtime marker identity. Revalidate to refuse incompatible combinations.
    result['workload'] = {k: v for k, v in existing.items() if k in ('pointId', 'hotFactor')}
    result['workload'].update(p['workload'])
    ordinary = p['population']['ordinaryRosterTenants']
    need(config.get('ordinaryRosterTenants', ordinary) == ordinary, 'CONFIG_ORDINARY_ROSTER')
    result['ordinaryRosterTenants'] = ordinary
    workload_runtime.validate(result['workload'], need, ordinary)
    return result


def dry(p, target):
    validate(p)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    sys.path.append(str(ROOT / 'tools/mt-bench/m7-joined'))
    import workload
    receipt = workload.generate(ROOT, target / 'workload.js')
    n = p['population']['ordinaryRosterTenants']
    roster = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'load-{i}.test',
               'token': 'synthetic-loopback-only'} for i in range(n)]
    write(target / 'tenants.json', roster)
    env = {'DURATION': str(p['workload']['loadSeconds']), 'ACCEL': '1', 'HOT_FACTOR': str(p['workload'].get('hotFactor', 1)),
           'SHAPES': ','.join(SHAPES), 'RUN_ID': 'synthetic-profile-dry',
           'RUN_START': '1800000000000', 'TENANTS_FILE': str(target / 'tenants.json')}
    env = workload_runtime.environment(p['workload'], env, need)
    write(target / 'dry.json', {'profile': p, 'model': describe(p), 'environment': env,
                              'generated': receipt, 'profileSha256': hashlib.sha256(
                                  json.dumps(p, sort_keys=True).encode()).hexdigest(),
                              'runtime': 'NOT_RUN', 'capacityAcceptance': 'NOT_GRANTED'})
    return target / 'dry.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('describe', 'dry', 'bind', 'populate'))
    parser.add_argument('profile', type=Path)
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()
    p = read(args.profile)
    if args.action == 'populate':
        if len(args.paths) not in (2, 3):
            parser.error('populate requires ANCHOR_UNIX_MS OUTPUT_PROFILE [MODE]')
        mode = str(args.paths[2]) if len(args.paths) == 3 else history.MODE
        p['history'] = history.default_spec(mode, int(str(args.paths[0])))
        # Standard cases bind source pins from the candidate during their own preparation.
        write(args.paths[1], validate(p, require_pins=False))
    elif args.action == 'describe':
        print(json.dumps(describe(p), indent=2))
    elif args.action == 'dry':
        print(dry(p, args.paths[0].resolve()))
    else:
        write(args.paths[1], bind(p, read(args.paths[0])))


if __name__ == '__main__':
    main()
