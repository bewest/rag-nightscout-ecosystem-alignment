"""Reduce load bookend activity snapshots and optional sampled blocker roles."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import re

from contract import require

ROLE = re.compile(r'nsdemo_[a-z0-9_]+|postgres|other')
LABEL = re.compile(r'[a-zA-Z0-9_ -]*')
BLOCKER_HEADER = 't\towner\tkind\tfields...'


def role(name):
    return name if ROLE.fullmatch(name) else 'other'


def in_window(path, start, end):
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter='\t'):
            tick = float(row['t'])
            require(math.isfinite(tick), 'M7_PG_SAMPLE_TIMESTAMP')
            if start <= tick <= end:
                yield row


def blockers(path, owner, expected, lock_rows, activity_ticks, start, end):
    require(re.fullmatch(r'[0-9a-f]{32}', owner or ''), 'M7_PG_SAMPLE_OWNER')
    coverage, seen = {}, set()
    rows, counts = defaultdict(Counter), Counter()
    with path.open() as handle:
        require(handle.readline().rstrip('\n') == BLOCKER_HEADER, 'M7_PG_SAMPLE_HEADER')
        for line in handle:
            tick, sample_owner, kind, *fields = line.rstrip('\n').split('\t')
            when = float(tick)
            require(math.isfinite(when), 'M7_PG_SAMPLE_TIMESTAMP')
            require(sample_owner == owner, 'M7_PG_SAMPLE_FOREIGN_OWNER')
            if not start <= when <= end:
                continue
            require(tick in expected, 'M7_PG_SAMPLE_FOREIGN_TICK')
            if kind == 'sample':
                require(len(fields) == 2 and tick not in coverage, 'M7_PG_SAMPLE_COVERAGE_ROW')
                selected, omitted = map(int, fields)
                require(selected >= 0 and omitted == max(selected - 32, 0), 'M7_PG_SAMPLE_COVERAGE_ROW')
                coverage[tick] = (selected, omitted)
            else:
                require(kind == 'wait' and len(fields) == 7, 'M7_PG_SAMPLE_WAIT_ROW')
                waiter, state, event, queryid, locktype, names, count = fields
                identity = (tick, *fields[:-1])
                require(identity not in seen and int(count) > 0 and ROLE.fullmatch(waiter)
                        and all(LABEL.fullmatch(label) for label in (state, event, locktype))
                        and re.fullmatch(r'-|-?[0-9]+', queryid),
                        'M7_PG_SAMPLE_WAIT_ROW')
                seen.add(identity)
                names = tuple(names.split(','))
                require(names == ('-',) or (names == tuple(sorted(set(names)))
                        and all(name == 'unresolved' or ROLE.fullmatch(name) for name in names)),
                        'M7_PG_SAMPLE_BLOCKER_ROW')
                rows[tick][(waiter, state, event)] += int(count)
                counts[(waiter, event, locktype, names)] += int(count)
    require(set(coverage) == expected and activity_ticks == expected and set(rows) <= expected,
            'M7_PG_SAMPLE_TICK_OMITTED')
    for tick, (selected, omitted) in coverage.items():
        activity = lock_rows.get(tick, Counter())
        captured = rows[tick]
        require(sum(activity.values()) == selected and sum(captured.values()) == selected - omitted
                and all(count <= activity[key] for key, count in captured.items()), 'M7_PG_SAMPLE_WAIT_OMITTED')

    dropped = sum(omitted for _, omitted in coverage.values())
    unresolved = sum(count for (_, _, locktype, names), count in counts.items()
                     if locktype == '-' or any(name in ('-', 'other', 'unresolved') for name in names))
    return {
        'status': 'PARTIAL' if dropped or unresolved else 'OBSERVED',
        'sampleTicks': len(coverage),
        'waiterObservationsOmittedByCap': dropped,
        'unresolvedWaiterObservations': unresolved,
        'roles': [
            {'waitingRole': waiter, 'waitEvent': event, 'lockType': locktype,
             'blockerRoles': list(names) if names != ('-',) else [], 'waiterObservations': count}
            for (waiter, event, locktype, names), count in sorted(counts.items())
        ],
        'scope': 'Sample-time heavyweight-lock edges. A vanished lock, prepared transaction, '
                 'foreign database or unfamiliar role can leave unresolved attribution.',
    }


def reduce_phase(folder, owner, start, end, unit_specs=None, units=None):
    """Keep positive observations when coverage is incomplete. Never infer duration."""
    result = {'activityStatus': 'UNMEASURED', 'blockerAttribution': {'status': 'UNMEASURED'},
              'causalAttribution': 'UNMEASURED', 'waitDurationMs': 'UNMEASURED',
              'scope': 'Point samples of PostgreSQL backends within resource bookends. Counts can '
                       'repeat one wait across ticks or miss waits between ticks. They are not DB '
                       'execution time, CPU, per-statement wait duration or proof of a bottleneck.'}
    lock_counts, lock_ticks, active_counts = Counter(), defaultdict(Counter), Counter()
    observed, seen = set(), set()
    try:
        require(math.isfinite(start) and math.isfinite(end) and start < end, 'M7_PG_SAMPLE_WINDOW')
        expected = {row['t'] for row in in_window(folder / 'host-load.tsv', start, end)}
        for row in in_window(folder / 'pg-activity.tsv', start, end):
            tick, state, wait_type, event = (row[key] for key in ('t', 'state', 'wait_event_type', 'wait_event'))
            identity = (tick, row['role'], state, wait_type, event)
            require(identity not in seen and int(row['n']) > 0 and all(
                    LABEL.fullmatch(label) for label in (state, wait_type, event)), 'M7_PG_SAMPLE_ACTIVITY_ROW')
            seen.add(identity)
            observed.add(tick)
            who = role(row['role'])
            if state == 'active':
                active_counts[who] += int(row['n'])
            if wait_type == 'Lock':
                lock_ticks[tick][(who, state, event)] += int(row['n'])
                lock_counts[(who, state, event)] += int(row['n'])
        require(observed and observed <= expected, 'M7_PG_SAMPLE_ACTIVITY_TICKS')
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        result['reason'] = str(error) if str(error).startswith('M7_') else 'M7_PG_SAMPLE_ACTIVITY_UNAVAILABLE'
        return result

    complete = observed == expected
    result.update(activityStatus='OBSERVED' if complete else 'PARTIAL',
                  sampleTicks=len(observed), expectedTicks=len(expected),
                  ticksWithHeavyweightLockWait=len(lock_ticks),
                  activeBackendObservations=dict(active_counts),
                  lockWaits=[{'role': who, 'state': state, 'event': event, 'backendObservations': n}
                             for (who, state, event), n in sorted(lock_counts.items())])
    try:
        result['blockerAttribution'] = blockers(
            folder / 'pg-blockers.tsv', owner, expected, lock_ticks, observed, start, end)
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        result['blockerAttribution']['reason'] = (
            str(error) if str(error).startswith('M7_') else 'M7_PG_SAMPLE_BLOCKERS_UNAVAILABLE')
    if unit_specs is not None:
        result['perUnit'] = {}
        for service, (unit, roles) in unit_specs.items():
            count = units.get(unit)
            waits = sum(n for (who, _, _), n in lock_counts.items() if who in roles)
            result['perUnit'][service] = {
                'unit': unit, 'units': count, 'roles': list(roles),
                'sampledLockBackendObservationsPerUnit': round(waits / count, 6)
                if complete and count and any(who in roles for _, who, *_ in seen) else 'UNMEASURED',
            }
    return result


def reduce(point, phase='load', unit_specs=None, units=None):
    folder = Path(point) / phase
    manifest = json.loads((Path(point) / 'owner.json').read_text())
    try:
        start, end = [json.loads((folder / f'{boundary}-cgroups.json').read_text())['at']
                      for boundary in ('before', 'after')]
    except (OSError, ValueError, KeyError, TypeError):
        start = end = 0
    return reduce_phase(folder, manifest.get('owner'), start, end, unit_specs, units)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('point', type=Path, help='fixture directory containing owner.json')
    parser.add_argument('--phase', choices=('idle', 'load'), default='load')
    args = parser.parse_args()
    print(json.dumps(reduce(args.point, args.phase), indent=2))
