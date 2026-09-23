#!/usr/bin/env python3
"""staleness.py - how far behind the source each sink's newest sgv was, over time.

    staleness.py <samples.jsonl> [--since ISO] [--until ISO]

For each sample in which the source AND the sink were live (authenticated
status read returned 200), staleness = source newest sgv time - sink newest
sgv time, in minutes. Samples where either side was not live are counted and
excluded, because a dead server's numbers are not evidence. Prints, per sink:
live samples, max and median staleness, minutes spent more than 10 and more
than 20 minutes behind, and the longest continuous run more than 10 behind.
"""
import json
import sys
from datetime import datetime, timezone

f = sys.argv[1]
args = sys.argv[2:]
since = args[args.index('--since') + 1] if '--since' in args else ''
until = args[args.index('--until') + 1] if '--until' in args else '9'


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


rows = [json.loads(l) for l in open(f)]
rows = [r for r in rows if since <= r['t'] <= until]
out = {}
for r in rows:
    s = {x['name']: x for x in r['samples']}
    src = s.get('s')
    for name, k in s.items():
        if name == 's':
            continue
        o = out.setdefault(name, {'pts': [], 'not_live': 0})
        if not (src and src['live'].get('ok') and k['live'].get('ok') and src.get('newest_sgv') and k.get('newest_sgv')):
            o['not_live'] += 1
            continue
        o['pts'].append((ts(r['t']), (ts(src['newest_sgv']) - ts(k['newest_sgv'])) / 60))
res = {}
for name, o in out.items():
    pts = o['pts']
    if not pts:
        res[name] = {'live_samples': 0, 'not_live': o['not_live']}
        continue
    vals = sorted(v for _, v in pts)
    step = [(pts[i + 1][0] - pts[i][0]) / 60 for i in range(len(pts) - 1)] + [1]
    over10 = sum(st for (t, v), st in zip(pts, step) if v > 10)
    over20 = sum(st for (t, v), st in zip(pts, step) if v > 20)
    run = best = 0
    best_end = None
    for (t, v), st in zip(pts, step):
        run = run + st if v > 10 else 0
        if run > best:
            best, best_end = run, t
    res[name] = {'live_samples': len(pts), 'not_live': o['not_live'],
                 'max_min': round(vals[-1], 1), 'median_min': round(vals[len(vals) // 2], 1),
                 'minutes_over_10': round(over10), 'minutes_over_20': round(over20),
                 'longest_run_over_10_min': round(best),
                 'longest_run_ended': datetime.fromtimestamp(best_end, timezone.utc).strftime('%H:%M') if best_end else None}
print(json.dumps(res, indent=1))
