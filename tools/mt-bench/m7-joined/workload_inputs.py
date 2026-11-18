"""Numeric workload inputs shared by the Compose and Kubernetes projections."""

import math

MAX_SECONDS = 86400
# Node timers use a signed 32-bit millisecond delay. k6 timeUnit is a
# positive Go duration, represented in nanoseconds by a signed 64-bit value.
MAX_PROBE_INTERVAL_MS = 2**31 - 1
MAX_ARRIVAL_CYCLE_MS = (2**63 - 1) // 1000000
MAX_PROBE_WRITES = 100000
MAX_VIEWERS = 80000


def seconds(value):
    return type(value) is int and 1 <= value <= MAX_SECONDS


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


def probe_fits_ledger(interval_ms, load_seconds):
    return (load_seconds * 1000 + interval_ms - 1) // interval_ms < MAX_PROBE_WRITES


def aggregate_cycle_ms(tenants, hot_factor, requested_rate):
    effective_population = tenants - 1 + hot_factor
    cycle = 11000 * effective_population / requested_rate
    if not math.isfinite(cycle):
        return None
    rounded = math.floor(cycle + .5)
    return rounded if 1 <= rounded <= MAX_ARRIVAL_CYCLE_MS else None
