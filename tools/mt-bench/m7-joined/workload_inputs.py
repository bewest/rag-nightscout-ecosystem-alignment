"""Numeric workload inputs shared by the Compose and Kubernetes projections."""

import math

# Ordinary duration strings are parsed by k6 as Go int64 nanoseconds. Roster,
# viewer and weighted-wheel storage use JavaScript arrays (uint32 length).
# These are representation limits, not reference experiment populations.
MAX_SECONDS = (2**63 - 1) // 1000000000
MAX_SAFE_INTEGER = 2**53 - 1
MAX_ARRAY_LENGTH = 2**32 - 1
# Node timers use a signed 32-bit millisecond delay. k6 timeUnit is a
# positive Go duration, represented in nanoseconds by a signed 64-bit value.
MAX_PROBE_INTERVAL_MS = 2**31 - 1
MAX_ARRIVAL_CYCLE_MS = (2**63 - 1) // 1000000
DEFAULT_PROBE_LEDGER = {'maxWrites': 100000, 'maxBytes': 4 * 1024 * 1024}
COMPOSE_STARTUP_DEFAULTS = {'composeReadySeconds':1200, 'stageSeconds':1800, 'evaluatorReadySeconds':1200}
KUBERNETES_STARTUP_DEFAULTS = {'workloadReadySeconds':300, 'primerReadySeconds':3600, 'roleExportSeconds':70,
                              'platformVerifySeconds':150, 'secretSeedSeconds':90, 'secretPublishSeconds':185,
                              'jobCompleteSeconds':30, 'requestSeconds':14, 'commandSeconds':18, 'execSeconds':35,
                              'dataPrimerSeconds':3600}
MAX_VIEWERS = MAX_ARRAY_LENGTH


def seconds(value):
    return type(value) is int and 1 <= value <= MAX_SECONDS


def tenants(value):
    return type(value) is int and 1 <= value <= MAX_ARRAY_LENGTH


def concurrency(value):
    return type(value) is int and 1 <= value <= MAX_SAFE_INTEGER


def shard_count(value, tenant_count=None):
    return tenants(value) and (tenant_count is None or
                              tenants(tenant_count) and value <= tenant_count)


def population_fits(tenant_count, hot_factor):
    return (tenants(tenant_count) and tenants(hot_factor)
            and tenant_count - 1 + hot_factor <= MAX_ARRAY_LENGTH)


def offered_rate(value):
    if type(value) not in (int, float) or value <= 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def polling_clients(value):
    return type(value) is int and 0 <= value <= MAX_VIEWERS


def probe_interval(value):
    return type(value) is int and 1 <= value <= MAX_PROBE_INTERVAL_MS


def probe_ledger(value):
    return (isinstance(value, dict) and set(value) == DEFAULT_PROBE_LEDGER.keys()
            and tenants(value['maxWrites']) and concurrency(value['maxBytes']))


def probe_fits_ledger(interval_ms, load_seconds, selected=None):
    budget = DEFAULT_PROBE_LEDGER if selected is None else selected
    return (load_seconds * 1000 + interval_ms - 1) // interval_ms < budget['maxWrites']


def probe_ledger_env(workload):
    if 'probeLedger' not in workload:
        return {}
    import json
    return {'M7_PROBE_LEDGER': json.dumps(workload['probeLedger'], separators=(',', ':'))}


def startup_windows(value, defaults, require):
    require(isinstance(value,dict) and set(value)<=defaults.keys() and all(seconds(v) for v in value.values()),
            'M7_STARTUP_WINDOWS_INVALID')
    return {**defaults,**value}


def startup_selection(phases, require):
    selected = phases.get('startupWindows',{})
    require(isinstance(selected,dict) and set(selected)<={'compose','kubernetes'},'M7_STARTUP_WINDOWS_INVALID')
    startup_windows(selected.get('compose',{}),COMPOSE_STARTUP_DEFAULTS,require)
    startup_windows(selected.get('kubernetes',{}),KUBERNETES_STARTUP_DEFAULTS,require)
    return selected


def aggregate_cycle_ms(tenants, hot_factor, requested_rate):
    if not population_fits(tenants, hot_factor) or not offered_rate(requested_rate):
        return None
    effective_population = tenants - 1 + hot_factor
    cycle = 11000 * effective_population / requested_rate
    if not math.isfinite(cycle):
        return None
    rounded = math.floor(cycle + .5)
    return rounded if 1 <= rounded <= MAX_ARRIVAL_CYCLE_MS else None
