"""Select the existing M7 generator inputs, independently of roster and viewers."""
from workload import REALISTIC_MIX, realistic_cycle_ms
import workload_inputs
import viewer_plan

SHAPES = dict(w_sgv=1, w_devicestatus=1, w_treatments_v3=1,
              r_sgv=5, r_devicestatus=1, r_treatments=1, r_status=1)
SELECTORS = ('OFFERED_RPS', 'M7_WORKLOAD_MIX', 'M7_WORKLOAD_SCALE')


def ordinary_count(provisioned, selected, need):
    need(workload_inputs.tenants(provisioned) and workload_inputs.tenants(selected)
         and selected <= provisioned, 'ORDINARY_ROSTER_TENANTS')
    return selected


def driver_count(c, need):
    return ordinary_count(c['tenants'], c.get('ordinaryRosterTenants', c['tenants']), need)


def ordinary_roster(c, tenants, need):
    """Select the same verified roster prefix for ordinary traffic and its ACKs."""
    need(c.get('tenants') == len(tenants), 'TENANT_ROSTER')
    return tenants[:driver_count(c, need)]


def validate(w, need, tenants=None):
    need(isinstance(w, dict) and set(w) <= {'loadSeconds', 'offeredRps', 'workloadMix',
         'workloadScale', 'logicalPollingClients', 'viewerSetup', 'probeEveryMs', 'hotFactor', 'pointId', 'setupSeconds', 'drainSeconds',
         'driverPlan', 'driverShards', 'driverHeadroom', 'jwtSetupConcurrency', 'probeLedger','evaluatorProgressBudget','drainObservation','latencyObservation'}, 'WORKLOAD_FIELDS')
    need(w.get('latencyObservation', 'polling-sql-v1') in ('polling-sql-v1', 'offline-v1'), 'WORKLOAD_LATENCY_OBSERVATION')
    viewer_plan.setup(w, need)
    need(workload_inputs.seconds(w.get('loadSeconds')), 'WORKLOAD_LOAD_SECONDS')
    need(workload_inputs.polling_clients(w.get('logicalPollingClients')), 'WORKLOAD_VIEWERS')
    need(workload_inputs.probe_interval(w.get('probeEveryMs')), 'WORKLOAD_PROBE_INTERVAL')
    need('probeLedger' not in w or workload_inputs.probe_ledger(w['probeLedger']), 'WORKLOAD_PROBE_LEDGER_BUDGET')
    need(workload_inputs.probe_fits_ledger(w['probeEveryMs'], w['loadSeconds'], w.get('probeLedger')), 'WORKLOAD_PROBE_LEDGER_WINDOW')
    if 'evaluatorProgressBudget' in w:
        import evaluator_progress as progress
        need(w['evaluatorProgressBudget'] is not None,'WORKLOAD_EVALUATOR_PROGRESS_BUDGET')
        try:progress.capture_policy(w['evaluatorProgressBudget'])
        except progress.Refused:need(False,'WORKLOAD_EVALUATOR_PROGRESS_BUDGET')
    need(workload_inputs.tenants(w.get('hotFactor', 1)), 'WORKLOAD_HOT_FACTOR')
    need(tenants is None or workload_inputs.population_fits(tenants, w.get('hotFactor', 1)),
         'WORKLOAD_POPULATION_ARRAY_LIMIT')
    need(workload_inputs.concurrency(w.get('jwtSetupConcurrency', 1)), 'WORKLOAD_JWT_SETUP_CONCURRENCY')
    for key, default in (('setupSeconds', 310), ('drainSeconds', 120)):
        need(workload_inputs.seconds(w.get(key, default)), 'PHASE_WINDOW:' + key)
    if 'drainObservation' in w:
        import phase_windows
        try:phase_windows.observation_override(w['drainObservation'])
        except (RuntimeError,ValueError):need(False,'WORKLOAD_DRAIN_OBSERVATION')
    if 'workloadMix' in w:
        need(w['workloadMix'] == REALISTIC_MIX and 'offeredRps' not in w and w.get('hotFactor', 1) == 1,
             'REALISTIC_MIX_CONFIGURATION')
        scale = w.get('workloadScale', 1)
        try:realistic_cycle_ms(scale)
        except RuntimeError as error:
            need(False,'WORKLOAD_SCALE_TIME_UNIT' if str(error)=='M7_WORKLOAD_SCALE_TIME_UNIT' else 'WORKLOAD_SCALE_CONFIGURATION')
    else:
        need('workloadScale' not in w, 'WORKLOAD_SCALE_CONFIGURATION')
        need(workload_inputs.offered_rate(w.get('offeredRps')), 'WORKLOAD_OFFERED_RPS')
        if tenants is not None:
            need(workload_inputs.aggregate_cycle_ms(tenants, w.get('hotFactor', 1), w['offeredRps']) is not None,
                 'WORKLOAD_OFFERED_TIME_UNIT')
    need('driverHeadroom' not in w or workload_inputs.driver_headroom(w['driverHeadroom']), 'DRIVER_HEADROOM')
    need('driverShards' not in w or 'driverPlan' in w, 'DRIVER_PLAN_REQUIRED')
    if 'driverPlan' in w:
        import driver_accounting as driver
        need(workload_inputs.shard_count(w.get('driverShards', 1), tenants), 'DRIVER_SHARDS')
        driver.configuration(w['driverPlan'], w)
        need(set(w['driverPlan']['scenarios']) == set(SHAPES), 'DRIVER_SEVEN_SHAPES_REQUIRED')
    return w


def driver_manifest(c):
    """Project the same measured driver contract used by local Compose."""
    import driver_accounting as driver
    cadence = dict(c['workload'], accel=1, hotFactor=c['workload'].get('hotFactor', 1),
                   driverHeadroom=headroom(c['workload']))
    cadence['driverPlan'] = driver.configuration(cadence['driverPlan'], cadence)
    m = dict(tenants=c.get('ordinaryRosterTenants', c['tenants']), replicas=sum(r == 'api' or r.startswith('api-') for r in c['roles']),
             cadence=cadence, pair=c['pins']['pair'], imageId=c['pins']['appImageId'],
             instrument=c['pins']['instrument'], runPurpose='discovery', transport='kubernetes-native')
    driver.expected_plans(m)
    return m


def headroom(w):
    """Kubernetes default H=2 (decision driver-sized-from-offer); driverHeadroom overrides it."""
    return w.get('driverHeadroom', workload_inputs.DRIVER_HEADROOM['kubernetes'])


def environment(w, inherited, need):
    validate(w, need)
    # An ambient aggregate override must fail before any actors start. Never
    # silently inherit, round or substitute a different workload selection.
    selected = ({'M7_WORKLOAD_MIX': w['workloadMix'], 'M7_WORKLOAD_SCALE': str(w.get('workloadScale', 1))}
                if 'workloadMix' in w else {'OFFERED_RPS': str(w['offeredRps'])})
    for key in SELECTORS:
        need(key not in inherited or key in selected and inherited[key] == selected[key],
             'WORKLOAD_ENVIRONMENT_CONFLICT')
    env = {key: value for key, value in inherited.items() if key not in SELECTORS and key != 'JWT_SETUP_CONCURRENCY'}
    env.update(selected, DRIVER_HEADROOM=repr(float(headroom(w))))
    return env


def rates(w, n):
    if 'workloadMix' in w:
        cycles = realistic_cycle_ms(w.get('workloadScale', 1), w.get('driverPlan', {}).get('writeRateScale', 1))
    else:
        cycle = workload_inputs.aggregate_cycle_ms(n, w.get('hotFactor', 1), w['offeredRps'])
        cycles = dict.fromkeys(SHAPES, cycle)
        n += w.get('hotFactor', 1) - 1
    return cycles, {shape: weight * n * 1000 / cycles[shape] for shape, weight in SHAPES.items()}
