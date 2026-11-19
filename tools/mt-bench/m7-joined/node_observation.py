"""Read bounded k6 phase markers from a k6 log (the CPU/ELU profiler was removed 2026-11-19)."""
import json
import re


def log_events(path, tail=False, *,
               names=('scenario-first-iteration', 'scenario-phase-end')):
    """Read bounded k6 phase markers. Ignore response/request detail."""
    try:
        with path.open('rb') as stream:
            if tail:
                stream.seek(max(0, path.stat().st_size - 65536))
            text = stream.read(65536).decode(errors='replace')
    except FileNotFoundError:
        return {}
    result = {}
    for encoded in re.findall(r'\bmsg=("(?:[^"\\]|\\.)*")', text):
        try:
            value = json.loads(json.loads(encoded))
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and type(value.get('atMs')) is int and value.get('event') in names:
            result.setdefault(value['event'], value['atMs'])
    return result


def phase_end(path):
    # k6 prints its end summary after teardown. A large per-tenant summary
    # pushes the marker out of the tail while it remains in the event prefix.
    event = 'scenario-phase-end'
    return log_events(path).get(event) or log_events(path, tail=True).get(event)
