"""Select the existing M7 generator inputs, independently of roster and viewers."""
import math
from workload import REALISTIC_MIX, REALISTIC_CADENCE_MS
import workload_inputs

SHAPES = dict(w_sgv=1, w_devicestatus=1, w_treatments_v3=1,
              r_sgv=5, r_devicestatus=1, r_treatments=1, r_status=1)
SELECTORS = ('OFFERED_RPS', 'M7_WORKLOAD_MIX', 'M7_WORKLOAD_SCALE')


def validate(w, need, tenants=None):
    need(isinstance(w, dict) and set(w) <= {'loadSeconds', 'offeredRps', 'workloadMix',
         'workloadScale', 'logicalPollingClients', 'probeEveryMs', 'hotFactor', 'pointId', 'setupSeconds', 'drainSeconds',
         'driverPlan', 'driverShards'}, 'WORKLOAD_FIELDS')
    need(workload_inputs.seconds(w.get('loadSeconds')), 'WORKLOAD_LOAD_SECONDS')
    need(workload_inputs.polling_clients(w.get('logicalPollingClients')), 'WORKLOAD_VIEWERS')
    need(workload_inputs.probe_interval(w.get('probeEveryMs')), 'WORKLOAD_PROBE_INTERVAL')
    need(workload_inputs.probe_fits_ledger(w['probeEveryMs'], w['loadSeconds']), 'WORKLOAD_PROBE_LEDGER_WINDOW')
    need(type(w.get('hotFactor', 1)) is int and 1 <= w.get('hotFactor', 1) <= 10, 'WORKLOAD_HOT_FACTOR')
    for key, default in (('setupSeconds', 310), ('drainSeconds', 120)):
        need(workload_inputs.seconds(w.get(key, default)), 'PHASE_WINDOW:' + key)
    if 'workloadMix' in w:
        need(w['workloadMix'] == REALISTIC_MIX and 'offeredRps' not in w and w.get('hotFactor', 1) == 1,
             'REALISTIC_MIX_CONFIGURATION')
        scale = w.get('workloadScale', 1)
        need(type(scale) in (int, float) and math.isfinite(scale) and .25 <= scale <= 8,
             'WORKLOAD_SCALE_CONFIGURATION')
    else:
        need('workloadScale' not in w, 'WORKLOAD_SCALE_CONFIGURATION')
        need(workload_inputs.offered_rate(w.get('offeredRps')), 'WORKLOAD_OFFERED_RPS')
        if tenants is not None:
            need(workload_inputs.aggregate_cycle_ms(tenants, w.get('hotFactor', 1), w['offeredRps']) is not None,
                 'WORKLOAD_OFFERED_TIME_UNIT')
    need('driverShards' not in w or 'driverPlan' in w, 'DRIVER_PLAN_REQUIRED')
    if 'driverPlan' in w:
        import driver_vu_diagnostic as driver
        need(type(w.get('driverShards', 1)) is int and 1 <= w.get('driverShards', 1) <= 16, 'DRIVER_SHARDS')
        driver.configuration(w['driverPlan'], w)
        need(set(w['driverPlan']['scenarios']) == set(SHAPES), 'DRIVER_SEVEN_SHAPES_REQUIRED')
    return w


def driver_manifest(c):
    """Project the same measured driver contract used by local Compose."""
    import driver_vu_diagnostic as driver
    cadence = dict(c['workload'], accel=1, hotFactor=c['workload'].get('hotFactor', 1),
                   driverVuDiagnostic=driver.CONFIGURED)
    cadence['driverPlan'] = driver.configuration(cadence['driverPlan'], cadence)
    m = dict(tenants=c['tenants'], replicas=sum(r == 'api' or r.startswith('api-') for r in c['roles']),
             cadence=cadence, pair=c['pins']['pair'], imageId=c['pins']['appImageId'],
             instrument=c['pins']['instrument'], runPurpose='discovery', transport='kubernetes-native')
    driver.expected_plans(m)
    return m


def environment(w, inherited, need):
    validate(w, need)
    # An ambient aggregate override must fail before any actors start. Never
    # silently inherit, round or substitute a different workload selection.
    selected = ({'M7_WORKLOAD_MIX': w['workloadMix'], 'M7_WORKLOAD_SCALE': str(w.get('workloadScale', 1))}
                if 'workloadMix' in w else {'OFFERED_RPS': str(w['offeredRps'])})
    for key in SELECTORS:
        need(key not in inherited or key in selected and inherited[key] == selected[key],
             'WORKLOAD_ENVIRONMENT_CONFLICT')
    env = {key: value for key, value in inherited.items() if key not in SELECTORS}
    env.update(selected)
    return env


def rates(w, n):
    if 'workloadMix' in w:
        cycles = {shape: math.floor(REALISTIC_CADENCE_MS[shape] * weight / w.get('workloadScale', 1) + .5)
                  for shape, weight in SHAPES.items()}
    else:
        cycle = workload_inputs.aggregate_cycle_ms(n, w.get('hotFactor', 1), w['offeredRps'])
        cycles = dict.fromkeys(SHAPES, cycle)
        n += w.get('hotFactor', 1) - 1
    return cycles, {shape: weight * n * 1000 / cycles[shape] for shape, weight in SHAPES.items()}
