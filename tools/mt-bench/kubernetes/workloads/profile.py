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
import preload
import primer_options
import population_ceiling
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


def validate(p):
    need(p['version'] == 1 and p['kind'] == 'k8s-m7-workload-profile', 'PROFILE')
    need(all(isinstance(p['referencePins'][k], str) and
             __import__('re').fullmatch(r'[a-f0-9]{40}', p['referencePins'][k])
             for k in ('core', 'deploy', 'bindingCommit')), 'SOURCE_PINS')
    n = p['population']['provisionedTenants']
    population_ceiling.from_profile(p,need)
    w = p['workload']
    need(workload_runtime.workload_inputs.tenants(n) and n >= 2, 'TENANTS')
    ordinary = workload_runtime.ordinary_count(n, p['population']['ordinaryRosterTenants'], need)
    workload_runtime.validate(w, need, ordinary)
    need(workload_runtime.workload_inputs.tenants(p['population']['hotFactor']) and
         p['population']['hotFactor'] == w.get('hotFactor', 1),
         'ADAPTER_ROSTER_OR_HOT_FACTOR_UNSUPPORTED')
    need(p['history'] == {'mode': 'existing-provisioner-only', 'additionalSeedRows': 0,
                          'retention': 'UNMEASURED'}, 'HISTORY_UNSUPPORTED')
    need(p['phases']['restart'] is False and p['phases']['reconnectBurstClients'] == 0,
         'RESTART_IS_SEPARATE_SCENARIO')
    access_setup = p['phases'].get('accessSetupSeconds')
    if 'accessSetupSeconds' in p['phases']:
        need(workload_runtime.workload_inputs.seconds(access_setup), 'ACCESS_SETUP_WINDOW')
    if 'cohortReadySeconds' in p['phases']:
        need(workload_runtime.workload_inputs.seconds(p['phases']['cohortReadySeconds']), 'COHORT_READY_WINDOW')
    workload_runtime.workload_inputs.startup_selection(p['phases'],need)
    primer_options.from_profile(p,need)
    pre_load = preload.selection(p['phases'].get('preloadConvergence'))
    access_window = access_setup + 60 if access_setup is not None else 0
    work = p['phases']['workSeconds']
    need(workload_runtime.workload_inputs.seconds(work) and
         work >= w.get('setupSeconds', 310) + w['loadSeconds'] + w.get('drainSeconds', 120) + access_window
                 + (pre_load['seconds'] if pre_load else 0) + 5,
         'WORK_WINDOW')
    need(workload_runtime.workload_inputs.seconds(p['phases']['cleanupSeconds']), 'CLEANUP_WINDOW')
    for group in ('clusterLimits', 'nativeLimits'):
        need(all(type(x) is int and x > 0 for x in p['proposedEnvelope'][group].values()), 'RESOURCE_ENVELOPE')
    need(p['capacityAcceptance'] == 'NOT_GRANTED', 'NO_CAPACITY_GRANT')
    return p


def describe(p):
    validate(p)
    n = p['population']['ordinaryRosterTenants']
    w = p['workload']
    cycles, rates = workload_runtime.rates(w, n)
    cycle_ms = cycles['w_sgv']
    inputs=workload_runtime.workload_inputs
    startup=inputs.startup_selection(p['phases'],need)
    return {'version': 1, 'profile': p['name'], 'basis': 'read-derived equations from generated M7 workload',
            'preloadConvergence':preload.selection(p['phases'].get('preloadConvergence')),
            **({primer_options.FIELD:p['phases'][primer_options.FIELD]} if primer_options.FIELD in p['phases'] else {}),
            **({population_ceiling.FIELD:population_ceiling.from_profile(p,need)} if 'maxTenants' in p['population'] else {}),
            **({'populationCommissioning':population_ceiling.commissioning(p['population']['provisionedTenants'],primer_options.from_profile(p,need))}
               if 'maxTenants' in p['population'] else {}),
            'population': p['population'], 'workload': w, 'arrivalCycleMs': cycle_ms, 'shapeCycleMs': cycles, 'shapeRequestsPerSecond': rates,
            'effectivePhaseWindows': {
                key: {'seconds': w.get(key, default), 'origin': 'authored' if key in w else 'legacy default'}
                for key, default in (('setupSeconds', 310), ('drainSeconds', 120))
            } | {key:{'seconds':p['phases'][key], 'origin':'authored'} for key in
                 ('accessSetupSeconds','cohortReadySeconds') if key in p['phases']},
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
            'probeWritesPerSecondWhileOpen': 1000 / w['probeEveryMs'],
            'probeWrites': 'observed independently; initial write and drain can extend the nominal window',
            'limits': ['realistic-v1 scale1 preserves per-shape sensor cadence; aggregate profiles retain their authored rate',
                       'HTTP logical pollers are not a configured population; shape rates define offered REST',
                       'all ordinary roster tenants are eligible; actual changed/witness sets are observed',
                       'hotFactor weights the first roster tenant; no extra history seeding, alarm synthesis or reconnect burst is executed'],
            'capacityAcceptance': 'NOT_GRANTED'}


def bind(p, config):
    """Produce an input for adapter.prepare; existing custody/preflight still applies."""
    validate(p)
    need(config['pins']['pair'] == {k: p['referencePins'][k] for k in ('core', 'deploy')} and
         config['pins']['bindingCommit'] == p['referencePins']['bindingCommit'], 'SOURCE_PROFILE_MISMATCH')
    need(config['tenants'] == p['population']['provisionedTenants'], 'CONFIG_ROSTER')
    # This does not acquire resources. Compare the existing planned actor envelope.
    native = p['proposedEnvelope']['nativeLimits']
    actors = [config[k]['resources'] for k in ('driver', 'observer')]
    need(all(type(r[k]) is int and r[k] > 0 for r in actors for k in ('millicpus', 'memoryBytes')) and
         sum(r['millicpus'] for r in actors) <= native['millicpus'] and
         sum(r['memoryBytes'] for r in actors) <= native['memoryBytes'], 'ACTOR_PLAN_EXCEEDS_PROFILE')
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
    result = copy.deepcopy(config)
    access_setup = p['phases'].get('accessSetupSeconds')
    need(config.get('accessSetupSeconds', access_setup) == access_setup, 'ACCESS_SETUP_WINDOW_CHANGED')
    if access_setup is not None:
        result['accessSetupSeconds'] = access_setup
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
    pre_load = preload.selection(p['phases'].get('preloadConvergence'))
    need(config.get('preloadConvergence', pre_load) == pre_load, 'PRELOAD_CONVERGENCE_CHANGED')
    if pre_load is not None:
        result['preloadConvergence'] = pre_load
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
           'JWT_SETUP_CONCURRENCY': str(p['workload'].get('jwtSetupConcurrency', 1)),
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
    parser.add_argument('action', choices=('describe', 'dry', 'bind'))
    parser.add_argument('profile', type=Path)
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()
    p = read(args.profile)
    if args.action == 'describe':
        print(json.dumps(describe(p), indent=2))
    elif args.action == 'dry':
        print(dry(p, args.paths[0].resolve()))
    else:
        write(args.paths[1], bind(p, read(args.paths[0])))


if __name__ == '__main__':
    main()
