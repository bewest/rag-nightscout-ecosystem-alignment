#!/usr/bin/env python3
"""Re-reduce a retained run under the outcome evaluator gate.

Read-only toward the run: the only write into the run directory is one new
verdict file, created exclusively (an existing file is never replaced). Every
original file is hashed before and after; any difference refuses the result.

usage: outcome_rereduce.py kubernetes|compose RUN_DIR OUT_NAME [--copy-to DIR]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import outcome_gate as g


def tree_digest(root, skip):
    rows = {}
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and not path.is_symlink() and path.name != skip:
            rows[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return rows


def roster_kubernetes(load, packet):
    run = json.loads((packet / 'run.json').read_text())
    path = Path(run.get('tenantsFile', ''))
    if path.is_file():
        ids = sorted(row['id'] for row in json.loads(path.read_text()))
        return ids, 'run.json tenantsFile'
    return None, 'UNMEASURED'


def roster_compose(fixture, outcome):
    value = json.loads((fixture / 'load' / 'evaluator-progress.json').read_text())
    columns = value['columns']
    ids = sorted({row[0] for r in value['rounds'] for row in r['rows']
                  if dict(zip(columns, row)).get('admitted') is True})
    expected = (outcome.get('configuration') or {}).get('tenants')
    return ids, 'admitted owners in load evaluator-progress capture (tenants.private.json not retained); count %s configured %s' % (
        len(ids), expected)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('path', choices=('kubernetes', 'compose'))
    parser.add_argument('run')
    parser.add_argument('name')
    parser.add_argument('--copy-to')
    args = parser.parse_args(argv)
    run = Path(args.run).resolve()
    target = run / args.name
    if target.exists():
        raise SystemExit('M7_OUTCOME_REREDUCTION_EXISTS')
    before = tree_digest(run, args.name)
    if args.path == 'kubernetes':
        packet = run / 'runtime' / 'packet'
        load = packet / 'load'
        ids, roster = roster_kubernetes(load, packet)
        original = {name: hashlib.sha256((load / name).read_bytes()).hexdigest()
                    for name in ('failure.json', 'result.json') if (load / name).is_file()}
        verdict = g.judge_kubernetes_load(load, ids or [], attribution={'run': run.name, 'stage': 'load'})
        verdict['httpLatencyAllShards'] = g.http_latency(load)
    else:
        fixture = run / 'fixture'
        outcome = json.loads((run / 'operating-outcome.json').read_text())
        ids, roster = roster_compose(fixture, outcome)
        original = {name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                    for name in ('operating-outcome.json', 'result.json', 'run-result.json') if (run / name).is_file()}
        verdict = g.judge_compose_run(fixture, ids, attribution={'run': run.name})
        verdict['httpLatencyAllShards'] = g.http_latency(fixture / 'load')
    verdict.update(kind='outcome-evaluator-gate-rereduction', roster={'tenants': len(ids or []), 'source': roster},
                   originalVerdictFiles=original,
                   originalVerdictsUnchanged='original verdict files are not edited; this file is separate',
                   basis='reproduced re-reduction of retained evidence')
    after = tree_digest(run, args.name)
    if before != after:
        raise SystemExit('M7_OUTCOME_REREDUCTION_SOURCE_CHANGED')
    verdict['retainedTree'] = {'files': len(before),
                               'manifestSha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
                               'unchangedDuringReduction': True}
    data = (json.dumps(verdict, indent=1, sort_keys=True) + '\n').encode()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    if args.copy_to:
        copy = Path(args.copy_to) / (run.name + '-' + args.name)
        fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
    summary = {'run': run.name, 'verdict': verdict['verdict'],
               'components': {k: {'verdict': v['verdict'], 'codes': v.get('codes', [])}
                              for k, v in verdict['components'].items()},
               'failedByClass': verdict['components']['failedCompletions'].get('classes'),
               'roster': verdict['roster'], 'originalVerdictFiles': original,
               'sha256': hashlib.sha256(data).hexdigest()}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
