"""Scenario `looping-backlog-v1`: a network-restored backlog (D6 of the AID client model). Lane
mt-plannable-scale-20261121. Synthetic data only.

A separate scenario, selectable on its own and never part of steady load: the steady driver shapes
(looping-v1, looping-v2 in looping_driver.py and capacity/k6/workload.js) carry no backlog, and this
scenario runs its own k6 script (looping-backlog.js). 0.5-1 % of tenants (looping ones, chosen by the
rank of sha256(seed:host:backlog)) each replay a 12 h gap in their controller's shape:

    AAPS  about 400 API v3 single-document POSTs back to back (144 SGV, the boluses and temp basals, 144
          devicestatus), 10 ms apart
    Loop  10 v1 array POSTs of 25-50 KB (144 SGV, about 115 doses, about 195 statuses in 8 of 25)
    Trio  5 v1 POSTs (SGV and treatments in chunks of 100, the latest devicestatus only)

Use: `plan()` selects the tenants and states the expected requests; `environment()` is the k6 environment
for looping-backlog.js; the CLI prints both, or runs k6 locally with `run`.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

import looping_driver

SCENARIO = 'looping-backlog-v1'
SCRIPT = Path(__file__).resolve().with_name('looping-backlog.js')
GAP_CYCLES = 144                    # 12 h at 5 min
PERCENT_RANGE = (0.5, 1.0)          # of all tenants, per the model; wider values are refused
TB_PER_DAY = dict(loop=226, trio=176, aaps=147)
SMB_PER_DAY = dict(loop=0, trio=50, aaps=60)


def select(spec, rows, percent=1.0):
    """Indices into `rows` (the k6 roster, annotated with loopKind) of the backlog tenants."""
    looping_driver.history_module(spec).validate(spec)
    looping_driver.lh.require(PERCENT_RANGE[0] <= percent <= PERCENT_RANGE[1], 'BACKLOG_PERCENT')
    looping_driver.lh.require(all('loopKind' in r for r in rows), 'BACKLOG_ROLES')
    count = max(1, math.floor(len(rows) * percent / 100 + .5))
    loopers = [i for i, r in enumerate(rows) if r['loopKind'] is not None]
    loopers.sort(key=lambda i: hashlib.sha256(f"{spec['seed']}:{rows[i]['host']}:backlog".encode()).hexdigest())
    looping_driver.lh.require(len(loopers) >= count, 'BACKLOG_ROSTER')
    return sorted(loopers[:count])


def expected_requests(kind, gap=GAP_CYCLES):
    """Requests one tenant of `kind` sends (read-derived from looping-backlog.js; doses are the expected count)."""
    doses = gap * (TB_PER_DAY[kind] + SMB_PER_DAY[kind]) / 288
    if kind == 'aaps':
        return dict(requests=round(2 * gap + doses), documents=round(2 * gap + doses), route='v3 single documents')
    if kind == 'loop':
        statuses = gap + sum((k * 7) % 20 < 7 for k in range(gap))
        return dict(requests=2 + math.ceil(statuses / 25), documents=round(gap + doses + statuses), route='v1 arrays')
    return dict(requests=math.ceil(gap / 100) + math.ceil(doses / 100) + 1, documents=round(gap + doses + 1), route='v1 arrays')


def plan(spec, rows, percent=1.0):
    chosen = select(spec, rows, percent)
    kinds = {k: sum(rows[i]['loopKind'] == k for i in chosen) for k in looping_driver.lh.KINDS}
    per_kind = {k: expected_requests(k) for k in looping_driver.lh.KINDS}
    return dict(scenario=SCENARIO, tenants=len(rows), percent=percent, selected=chosen, selectedByKind=kinds,
                perTenant=per_kind, requests=sum(kinds[k] * per_kind[k]['requests'] for k in kinds),
                documents=sum(kinds[k] * per_kind[k]['documents'] for k in kinds), gapCycles=GAP_CYCLES,
                basis='read-derived: the controllers\' replay rules (aid-model section 1) as looping-backlog.js sends them')


def environment(selected, max_seconds=900):
    return {'M7_BACKLOG_TENANTS': json.dumps(selected), 'M7_BACKLOG_GAP_CYCLES': str(GAP_CYCLES),
            'M7_BACKLOG_MAX_SECONDS': str(max_seconds),
            'M7_LOOPING_TEMPLATES': looping_driver.environment_v2()['M7_LOOPING_TEMPLATES']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=('plan', 'run'))
    p.add_argument('--history', type=Path, required=True, help='the fixture history spec (JSON)')
    p.add_argument('--tenants-file', type=Path, required=True, help='k6 roster with loopKind (looping_driver.annotate)')
    p.add_argument('--percent', type=float, default=1.0)
    p.add_argument('--base-url')
    p.add_argument('--run-id')
    a = p.parse_args(argv)
    spec, rows = json.loads(a.history.read_text()), json.loads(a.tenants_file.read_text())
    out = plan(spec, rows, a.percent)
    if a.action == 'plan':
        print(json.dumps(out, indent=1))
        return
    import time
    env = dict(os.environ, BASE_URL=a.base_url, RUN_ID=a.run_id, RUN_START=str(int(time.time() * 1000)),
               TENANTS_FILE=str(a.tenants_file), **environment(out['selected']))
    subprocess.run(['k6', 'run', '--quiet', str(SCRIPT)], env=env, check=True)


if __name__ == '__main__':
    main()
