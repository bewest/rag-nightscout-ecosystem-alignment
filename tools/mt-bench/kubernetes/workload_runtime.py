"""Select the existing M7 generator inputs, independently of roster and viewers."""
import math
from workload import REALISTIC_MIX, REALISTIC_CADENCE_MS

SHAPES = dict(w_sgv=1, w_devicestatus=1, w_treatments_v3=1,
              r_sgv=5, r_devicestatus=1, r_treatments=1, r_status=1)
# The stock probe ledger bounds attempts to 100000, at >= 1 second cadence.
MAX_SECONDS = 86400
SELECTORS = ('OFFERED_RPS', 'M7_WORKLOAD_MIX', 'M7_WORKLOAD_SCALE')


def validate(w, need):
    need(isinstance(w, dict) and set(w) <= {'loadSeconds', 'offeredRps', 'workloadMix',
         'workloadScale', 'logicalPollingClients', 'probeEveryMs', 'hotFactor', 'pointId', 'setupSeconds', 'drainSeconds',
         'driverPlan', 'driverShards'}, 'WORKLOAD_FIELDS')
    need(type(w.get('loadSeconds')) is int and 1 <= w['loadSeconds'] <= MAX_SECONDS, 'WORKLOAD_BOUND')
    need(type(w.get('logicalPollingClients')) is int and 0 <= w['logicalPollingClients'] <= 80000, 'WORKLOAD_VIEWERS')
    need(type(w.get('probeEveryMs')) is int and 1000 <= w['probeEveryMs'] <= 300000 and
         type(w.get('hotFactor', 1)) is int and 1 <= w.get('hotFactor', 1) <= 10, 'WORKLOAD_BOUND')
    for key, default in (('setupSeconds', 310), ('drainSeconds', 120)):
        need(type(w.get(key, default)) is int and 1 <= w.get(key, default) <= MAX_SECONDS, 'PHASE_WINDOW')
    if 'workloadMix' in w:
        need(w['workloadMix'] == REALISTIC_MIX and 'offeredRps' not in w and w.get('hotFactor', 1) == 1,
             'REALISTIC_MIX_CONFIGURATION')
        scale = w.get('workloadScale', 1)
        need(type(scale) in (int, float) and math.isfinite(scale) and .25 <= scale <= 8,
             'WORKLOAD_SCALE_CONFIGURATION')
    else:
        need('workloadScale' not in w, 'WORKLOAD_SCALE_CONFIGURATION')
        need(type(w.get('offeredRps')) is int and 1 <= w['offeredRps'] <= 10000, 'WORKLOAD_BOUND')
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
        cycle = math.floor(sum(SHAPES.values()) * n * 1000 / w['offeredRps'] + .5)
        cycles = dict.fromkeys(SHAPES, cycle)
    return cycles, {shape: weight * n * 1000 / cycles[shape] for shape, weight in SHAPES.items()}
