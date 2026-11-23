"""Driver trace bounds derived from the run's scale (lane harness-reliability, 2026-11-23).

A 1k profile authors maxTraceRows 5,000,000 and maxTraceBytes 64 MiB. The k6 scheduling trace grows with the
iterations of the run (about 22 rows per iteration, measured at 10k x 1,800 s: 6,354,900 rows for 288,597 iterations,
45.5 MB gzip, 673 MB decoded), so a 10k x 1,800 s run overran the row bound after the load had finished
(M7_DRIVER_TRACE_BOUND, r10k-w7-k20). The bound is set per profile from the planned iterations, never lowered below the
profile's own value, and never written into the 1k base.
"""
import math

ROWS_PER_ITERATION = 22          # measured, r10k-w7-k20
ROW_MARGIN = 1.25
ROW_STEP = 500000
LONG_RUN_SECONDS = 1800
LONG_RUN_BYTES = 128 * 1024 ** 2


def scaled_bounds(total_rps, load_seconds, base_rows=5000000, base_bytes=64 * 1024 ** 2):
    """{'maxTraceRows', 'maxTraceBytes'} for TOTAL_RPS iterations per second over LOAD_SECONDS: planned rows with 25 %
    margin rounded up to 500,000, and 128 MiB of trace file for runs over 1,800 s; never below the base."""
    rows = math.ceil(ROW_MARGIN * ROWS_PER_ITERATION * total_rps * load_seconds / ROW_STEP) * ROW_STEP
    size = LONG_RUN_BYTES if load_seconds > LONG_RUN_SECONDS else base_bytes
    return {'maxTraceRows': max(base_rows, rows), 'maxTraceBytes': max(base_bytes, size)}


def apply(profile, total_rps, load_seconds):
    """Set the bounds in PROFILE's workload.driverPlan (the per-run copy, never the base file). Returns the bounds."""
    plan = profile['workload']['driverPlan']
    bounds = scaled_bounds(total_rps, load_seconds, plan.get('maxTraceRows', 5000000), plan.get('maxTraceBytes', 64 * 1024 ** 2))
    plan.update(bounds)
    return bounds
