"""Select the existing M7 generator inputs, independently of roster and viewers."""
from workload import REALISTIC_MIX, realistic_cycle_ms
from pathlib import Path
import sys
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


def partial_looping(c):
    return (c.get('workload', {}).get('driverShape') in ('looping-v1', 'looping-v2')
            and c.get('ordinaryRosterTenants', c['tenants']) < c['tenants'])


def ordinary_roster(c, tenants, need):
    """Select the same verified roster prefix for ordinary traffic and its ACKs."""
    need(c.get('tenants') == len(tenants), 'TENANT_ROSTER')
    count = driver_count(c, need)
    if partial_looping(c):
        # The seed assigns roles by sorted host ordinal over the full fixture.
        tenants = sorted(tenants, key=lambda row: row['host'])
    return tenants[:count]


def connector_ids(c, tenants):
    """The vcpool connector group's tenant ids (connectors/stage.py): from the plan kept at entry, else
    selected as the stage selects them. Empty without connectors."""
    if not c.get('connectors'):
        return set()
    import json
    if c['connectors'].get('planFile'):
        return {row['id'] for row in json.loads(Path(c['connectors']['planFile']).read_text())['tenants']}
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'connectors'))
    import connectors
    population = {'provisionedTenants': len(tenants), 'ordinaryRosterTenants': c['connectors']['ordinaryRosterTenants'],
                  'connectorShare': c['connectors']['share']}
    return {row['id'] for row in connectors.select(tenants, population, c['connectors'].get('order'))}


def check_probe_roster(c, rows, tenants, need):
    """The probe writes entries to every tenant it is given. A probe write into a connector tenant moves the
    connector's entries gap past older upstream rows (measured on kind 2026-11-23, lanev-conn-05), and an
    ordinary upload does the same: both rosters must exclude the connector group, by tenant id."""
    ids = connector_ids(c, tenants)
    need(not ids & {row['id'] for row in rows}, 'CONNECTOR_TENANT_IN_PROBE_ROSTER')
    need(not ids & {row['id'] for row in ordinary_roster(c, tenants, need)}, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES')
    return rows


def oracle_scope(c, tenants, values, load, need):
    """The write-count oracle's roster (discovery_counts): the probe's roster scope. In a load stage with vcpool
    connectors that is every tenant except the connector group, whose rows vcpool writes and the connector score
    judges; probe and k6 writes never reach it, so a run-marked stored row there is refused."""
    if not (load and c.get('connectors')):
        return tenants
    ids = connector_ids(c, tenants)
    need(not ids & set(values or {}), 'CONNECTOR_TENANT_RECEIVED_RUN_WRITES')
    return [row for row in tenants if row['id'] not in ids]


def viewer_roster(c, tenants, need):
    rows = ordinary_roster(c, tenants, need) if partial_looping(c) else tenants
    ids = connector_ids(c, tenants)
    rows = [row for row in rows if row['id'] not in ids]
    need(bool(rows), 'VIEWER_ROSTER_EMPTY')
    return rows


def validate(w, need, tenants=None):
    need(isinstance(w, dict) and set(w) <= {'loadSeconds', 'offeredRps', 'workloadMix',
         'workloadScale', 'logicalPollingClients', 'viewerSetup', 'probeEveryMs', 'hotFactor', 'pointId', 'setupSeconds', 'drainSeconds',
         'driverPlan', 'driverShards', 'driverHeadroom', 'jwtSetupConcurrency', 'probeLedger','evaluatorProgressBudget','drainObservation','latencyObservation','driverShape'}, 'WORKLOAD_FIELDS')
    # looping-v1/looping-v2 (m7-joined/looping_driver.py): realistic-v1 cadence, writes shaped like the looping
    # fixture (v1) or the AID client model (v2).
    need('driverShape' not in w or (w['driverShape'] in ('looping-v1', 'looping-v2') and w.get('workloadMix') == REALISTIC_MIX
         and w.get('driverShards', 1) == 1), 'WORKLOAD_DRIVER_SHAPE')
    need(w.get('latencyObservation', 'polling-sql-v1') in
         ('polling-sql-v1', 'offline-v1', 'offline-with-witness-sql-v1'), 'WORKLOAD_LATENCY_OBSERVATION')
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
    if 'driverShape' in cadence:
        if not c.get('history'):
            raise ValueError('K8S_DRIVER_SHAPE_REQUIRES_LOOPING_FIXTURE')
        m['history'] = c['history']
        if partial_looping(c):
            m['provisionedTenants'] = c['tenants']
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
    if 'driverShape' in w:
        import looping_driver
        env.update(looping_driver.environment(w['driverShape']))
    return env


def rates(w, n, history=None, *, provisioned=None):
    if 'workloadMix' in w:
        cycles = realistic_cycle_ms(w.get('workloadScale', 1), w.get('driverPlan', {}).get('writeRateScale', 1))
    else:
        cycle = workload_inputs.aggregate_cycle_ms(n, w.get('hotFactor', 1), w['offeredRps'])
        cycles = dict.fromkeys(SHAPES, cycle)
        n += w.get('hotFactor', 1) - 1
    offer = {shape: weight * n * 1000 / cycles[shape] for shape, weight in SHAPES.items()}
    if w.get('driverShape') in ('looping-v1', 'looping-v2'):
        import looping_driver
        for shape, (tenants, unit) in looping_driver.write_offers(history, n, w.get('workloadScale', 1),
                w.get('driverPlan', {}).get('writeRateScale', 1), cycles['w_devicestatus'], w['driverShape'],
                provisioned=provisioned).items():
            cycles[shape] = unit
            offer[shape] = tenants * 1000 / unit
    return cycles, offer
