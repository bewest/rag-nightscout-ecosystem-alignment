"""Size each scheduling trace from the busiest shard's offered iterations."""
import math

ROWS_PER_ITERATION = 22
# Retained 10k and native two-shard traces used up to 158 gzip bytes and 2,334
# decoded bytes per issued iteration. Allow 25% over the rounded rates.
GZIP_BYTES_PER_ITERATION = 160
DECODED_BYTES_PER_ITERATION = 2400
MARGIN = 1.25
ROW_STEP = 500_000
BYTE_STEP = 1024**2


def bound_plan(traffic, ordinary, provisioned, history):
    """Raise per-file budgets as needed, keeping authored and runtime floors."""
    import driver_accounting as driver

    plan = traffic['driverPlan']
    cadence = dict(traffic, hotFactor=traffic.get('hotFactor', 1))
    shards = driver.expected_plans(dict(cadence=cadence, tenants=ordinary,
                                       provisionedTenants=provisioned, history=history))
    # Each shard writes a separate file; scenarios can use shorter windows than the whole load.
    iterations = max(sum(shape['offeredIterations'] for shape in shard['scenarios'].values()) for shard in shards)
    rows = plan.get('maxTraceRows', driver.MAX_TRACE_ROWS)
    compressed = plan.get('maxTraceBytes', driver.MAX_TRACE_BYTES)
    decoded = driver.decoded_trace_bytes(dict(plan, maxTraceBytes=compressed))
    bounds = dict(plan)
    for name, old, unit, step in (
        ('maxTraceRows', rows, ROWS_PER_ITERATION, ROW_STEP),
        ('maxTraceBytes', compressed, GZIP_BYTES_PER_ITERATION, BYTE_STEP),
        ('maxDecodedTraceBytes', decoded, DECODED_BYTES_PER_ITERATION, BYTE_STEP),
    ):
        size = max(old, math.ceil(MARGIN * unit * iterations / step) * step)
        if size > old:
            bounds[name] = size
    # Preserve the old decoded floor independently if the gzip budget grew.
    if bounds.get('maxTraceBytes', compressed) != compressed:
        bounds.setdefault('maxDecodedTraceBytes', decoded)
    return bounds
