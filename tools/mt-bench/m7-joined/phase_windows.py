"""Configured discovery clocks; the existing outer work cutoff always wins.

Setup includes stock-client priming and the ordinary driver's JWT exchanges.
Drain includes probe completion and the accepted-input observation. The
selected clinical witness keeps its independent strict 120-second deadline.
"""
import math
from contract import require
import workload_inputs

# k6 parses setupTimeout as a signed64-bit Go nanosecond duration. This is
# a representation boundary, not a reference workload or application limit.
MAX_SECONDS = workload_inputs.MAX_SECONDS
OBSERVER_KEYS = frozenset(('maxRounds','maxQueries','maxBytes','roundSeconds','intervalSeconds','sqlMaxBytes'))


def selection(cadence):
    result = {}
    for key in ('setupSeconds', 'drainSeconds'):
        if key in cadence:
            value = cadence[key]
            require(type(value) is int and 1 <= value <= MAX_SECONDS,
                    'M7_PHASE_WINDOW_INVALID:' + key)
            result[key] = value
    observation_override(cadence.get('drainObservation',{}))
    return result


def observation_override(value):
    require(isinstance(value,dict) and set(value)<=OBSERVER_KEYS,'M7_DRAIN_OBSERVER_FIELDS')
    for key,limit in value.items():
        require(type(limit) is int and 1<=limit<=2**53-1,'M7_DRAIN_OBSERVER_INVALID:'+key)
    return value


def observation_policy(cadence, seconds, round_queries, round_bytes, defaults):
    """Reserve enough observations for the selected clock and population.

    Byte/query figures are conservative capture budgets, not reservations or
    measured use. Explicit observer overrides replace these starting values.
    """
    override=observation_override(cadence.get('drainObservation',{}))
    policy=dict(defaults)
    interval=override.get('intervalSeconds',5)
    if 'drainSeconds' in cadence or override:
        rounds=max(policy['maxRounds'],math.ceil(seconds/interval)+2)
        policy.update(maxRounds=rounds,maxQueries=max(policy['maxQueries'],rounds*round_queries),
                      maxBytes=max(policy['maxBytes'],rounds*round_bytes))
    policy.update({key:value for key,value in override.items() if key not in ('intervalSeconds','sqlMaxBytes')})
    return policy,min(interval,seconds)


def observation_sql_bytes(cadence, default):
    return observation_override(cadence.get('drainObservation',{})).get('sqlMaxBytes',default)


def start(manifest, now_ns, now_ms):
    values = selection(manifest.get('cadence', {}))
    return ({'version': 1, 'owner': manifest['owner'], **values,
             'setupStartedMonoNs': now_ns,
             **({'setupUntilUnixMs':now_ms+values['setupSeconds']*1000} if 'setupSeconds' in values else {}),
             'selectedClinicalDeadlineSeconds': 120,
             'allWriterDrain': 'accepted-input observation; no clinical deadline extension'}
            if values else {})


def remaining(window, phase, now_ns):
    key = phase + 'Seconds'
    require(key in window and type(window.get(phase + 'StartedMonoNs')) is int,
            'M7_PHASE_WINDOW_NOT_STARTED:' + phase)
    left = window[key] - (now_ns - window[phase + 'StartedMonoNs']) / 1e9
    require(math.isfinite(left) and left > 0, 'M7_PHASE_WINDOW_EXHAUSTED:' + phase)
    return left


def drain_seconds(manifest, window, now_ns, default=60):
    values = selection(manifest.get('cadence', {}))
    if 'drainSeconds' not in values:
        return default
    require(window.get('owner') == manifest['owner'] and
            window.get('drainSeconds') == values['drainSeconds'],
            'M7_PHASE_WINDOW_DRAIN_IDENTITY')
    return remaining(window, 'drain', now_ns)
