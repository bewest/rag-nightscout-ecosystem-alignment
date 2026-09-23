#!/usr/bin/env python3
"""connstats.py - mongod connection counts and process fd counts over time.

    connstats.py <state-dir> [--series NAME]

From <state>/out/*/samples.jsonl (sampler.js, `conn` from serverStatus) and
<state>/out/stats.jsonl (lab.sh stats-loop, `fds` = entries in /proc/1/fd of
the Nightscout process; `rss_kb` = VmRSS of that process), print per server: samples, first/min/max/last of
`current`, `totalCreated` growth per hour, and per container the same for
fds. A leak shows as `current` or fds rising without returning; churn without
a leak shows as `totalCreated` rising while `current` stays flat.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

state = sys.argv[1]
series = sys.argv[sys.argv.index('--series') + 1] if '--series' in sys.argv else None


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def summary(points):
    vals = [v for _, v in points]
    hours = (points[-1][0] - points[0][0]) / 3600 if len(points) > 1 else 0
    return {'n': len(points), 'from': datetime.fromtimestamp(points[0][0], timezone.utc).strftime('%H:%M'),
            'to': datetime.fromtimestamp(points[-1][0], timezone.utc).strftime('%H:%M'),
            'first': vals[0], 'min': min(vals), 'max': max(vals), 'last': vals[-1], 'hours': round(hours, 2)}


conn = {}
for f in sorted(glob.glob(os.path.join(state, 'out', '*', 'samples.jsonl'))):
    lab = os.path.basename(os.path.dirname(f))
    for line in open(f):
        r = json.loads(line)
        for s in r['samples']:
            if 'conn' in s:
                conn.setdefault(f'{lab}/{s["name"]}', []).append((ts(r['t']), s['conn']))

out = {'mongod_connections': {}, 'process_fds': {}}
for k, pts in sorted(conn.items()):
    cur = summary([(t, c['current']) for t, c in pts])
    tc = [(t, c['totalCreated']) for t, c in pts]
    cur['totalCreated_per_hour'] = round((tc[-1][1] - tc[0][1]) / max(cur['hours'], 1e-9), 1) if cur['hours'] else None
    out['mongod_connections'][k] = cur
    if series == k:
        out['series'] = [(datetime.fromtimestamp(t, timezone.utc).strftime('%H:%M'), c['current'], c['totalCreated']) for t, c in pts]

fds = {}
rss = {}
statsf = os.path.join(state, 'out', 'stats.jsonl')
if os.path.exists(statsf):
    for line in open(statsf):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('fds', '').isdigit():
            fds.setdefault(r['name'], []).append((ts(r['t']), int(r['fds'])))
        if r.get('rss_kb', '').isdigit():
            rss.setdefault(r['name'], []).append((ts(r['t']), round(int(r['rss_kb']) / 1024)))
for k, pts in sorted(fds.items()):
    if k.endswith(('-sampler', '-writer', '-proxy')) or k in ('cksoak-sampler', 'cksoak-writer', 'cksoak-proxy'):
        continue
    out['process_fds'][k] = summary(pts)
    if series == k:
        out['series'] = [(datetime.fromtimestamp(t, timezone.utc).strftime('%H:%M'), v) for t, v in pts]
out['process_rss_mib'] = {k: summary(p) for k, p in sorted(rss.items())
                          if not k.endswith(('-sampler', '-writer', '-proxy')) and k not in ('cksoak-sampler', 'cksoak-writer', 'cksoak-proxy')}
print(json.dumps(out, indent=1))
