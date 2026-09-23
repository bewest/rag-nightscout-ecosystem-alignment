#!/usr/bin/env python3
"""pollstats.py - connector request cadence, from a proxy's log.

    pollstats.py <proxy-container> [--since ISO] [--until ISO] [--series]

Maps client addresses to container names on cksoak-net, then for each client:
  * groups GET /api/v1/entries.json into CYCLES (a request more than 60 s after
    the previous one starts a new cycle; a frame's retries land 10 s apart),
  * reports attempts per cycle, the interval between cycle starts, status
    counts, and the peak number of requests in any 60 s window (a tight retry
    loop shows here).
Nothing from request headers or bodies is in the proxy log to begin with.
"""
import collections
import json
import subprocess
import sys
from datetime import datetime, timezone

args = sys.argv[1:]
proxy = args[0]
since = args[args.index('--since') + 1] if '--since' in args else None
until = args[args.index('--until') + 1] if '--until' in args else None
series = '--series' in args


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


net = json.loads(subprocess.run(['docker', 'network', 'inspect', 'cksoak-net'], capture_output=True, text=True).stdout)[0]
ipname = {v['IPv4Address'].split('/')[0]: v['Name'] for v in net['Containers'].values()}
logs = subprocess.run(['docker', 'logs', proxy], capture_output=True, text=True, errors='replace')
rows = []
for line in (logs.stdout + logs.stderr).splitlines():
    try:
        j = json.loads(line)
    except ValueError:
        continue
    if 'path' not in j:
        continue
    if since and j['t'] < since or until and j['t'] > until:
        continue
    j['client'] = ipname.get(j['client'].replace('::ffff:', ''), j['client'])
    rows.append(j)

out = {}
for client in sorted({r['client'] for r in rows}):
    mine = [r for r in rows if r['client'] == client]
    ent = sorted(ts(r['t']) for r in mine if r['path'] == '/api/v1/entries.json')
    cycles = []
    for t in ent:
        if not cycles or t - cycles[-1][-1] > 60:
            cycles.append([t])
        else:
            cycles[-1].append(t)
    starts = [c[0] for c in cycles]
    gaps = [round((b - a) / 60, 1) for a, b in zip(starts, starts[1:])]
    all_t = sorted(ts(r['t']) for r in mine)
    peak, j = 0, 0
    for i in range(len(all_t)):
        while all_t[i] - all_t[j] > 60:
            j += 1
        peak = max(peak, i - j + 1)
    status = collections.Counter(f"{r['path'].replace('/api/v1/', '').replace('/api/v2/authorization/', 'auth/')} {r['status'] or r.get('error')}" for r in mine)
    rec = {'requests': len(mine), 'cycles': len(cycles),
           'attempts_per_cycle': dict(collections.Counter(len(c) for c in cycles)),
           'interval_min': {'min': min(gaps) if gaps else None, 'max': max(gaps) if gaps else None,
                            'median': sorted(gaps)[len(gaps) // 2] if gaps else None},
           'peak_requests_per_60s': peak, 'status': dict(status)}
    if series:
        rec['cycle_starts'] = [datetime.fromtimestamp(s, timezone.utc).strftime('%H:%M:%S') for s in starts]
        rec['intervals'] = gaps
    out[client] = rec
print(json.dumps(out, indent=1))
