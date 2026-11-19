"""Workload constants shared with capacity/k6/workload.js and the copy step."""
import hashlib
import json
import math
from pathlib import Path
from contract import require


REALISTIC_MIX = 'realistic-v1'
# k6 durations use Go's signed int64 nanoseconds; this is representability,
# rather than a reference workload rate or population ceiling.
MAX_TIME_UNIT_MS = (2**63 - 1) // 1000000
REALISTIC_CADENCE_MS = {
    'w_sgv': 300000,
    'w_devicestatus': 300000,
    'w_treatments_v3': 1800000,
    'r_sgv': 300000,
    'r_devicestatus': 900000,
    'r_treatments': 900000,
    'r_status': 900000,
}


def realistic_cycle_ms(scale, write_scale=1):
    """Resolve finite k6 time units without a reference multiplier ceiling."""
    try:
        positive = all(type(factor) in (int, float) and factor > 0 and math.isfinite(factor)
                       for factor in (scale, write_scale))
    except OverflowError:
        positive=False
    require(positive,'M7_WORKLOAD_SCALE_CONFIGURATION')
    result={}
    for shape,interval in REALISTIC_CADENCE_MS.items():
        value=interval*(5 if shape=='r_sgv' else 1)/scale
        if shape.startswith('w_'):
            value /= write_scale
        require(math.isfinite(value),'M7_WORKLOAD_SCALE_TIME_UNIT')
        unit=math.floor(value+.5)
        require(1<=unit<=MAX_TIME_UNIT_MS,'M7_WORKLOAD_SCALE_TIME_UNIT')
        result[shape]=unit
    return result


def generate(root, target):
    """Copy the shared workload. Options are environment parameters; nothing is patched."""
    baseline=Path(root)/'tools/mt-bench/capacity/k6/workload.js'
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(baseline.read_bytes())
    return {'baseline':'tools/mt-bench/capacity/k6/workload.js','adaptedSha256':hashlib.sha256(target.read_bytes()).hexdigest()}
