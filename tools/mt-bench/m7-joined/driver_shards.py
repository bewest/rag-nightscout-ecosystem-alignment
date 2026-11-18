"""Opt-in split of one k6 driver into N k6 processes in the same container.

The existing admitted k6 container, its native CPU/memory/no-swap limits, owner
labels and cleanup stay unchanged. Each process gets one contiguous roster slice
and the share of the offered rate that its slice weight carries, so the summed
arrival rate and the shape mix equal the unsharded plan. Only the hot tenant
(roster index 0, shard 0) keeps the hot factor.

Merged summary: counters/rates are sums; min/max and count-weighted means
reduce the retained fields. Percentiles cannot be pooled from these summaries.
The merged percentile remains the largest shard statistic. The legacy
m7DriverShards.quantileBounds field retains the range of shard statistics,
not a pooled-percentile bound. Gauge extrema are sums of per-shard extrema,
not a synchronized peak.
"""
import json
import shlex
from pathlib import Path

from contract import require

MAX_SHARDS = 16
QUANTILES = ('med', 'p(90)', 'p(95)', 'p(99)')


def plan(count, hot, offered, shards):
    require(type(shards) is int and 2 <= shards <= MAX_SHARDS and type(count) is int and count >= shards, 'M7_DRIVER_SHARDS_RANGE')
    require(type(hot) is int and hot >= 1, 'M7_DRIVER_SHARDS_HOT')
    require(offered is None or (isinstance(offered, (int, float)) and offered > 0), 'M7_DRIVER_SHARDS_RATE')
    total = count - 1 + hot
    rows, start = [], 0
    for index in range(shards):
        end = start + count // shards + (1 if index < count % shards else 0)
        size = end - start
        factor = hot if index == 0 else 1
        weight = size - 1 + factor
        rows.append({'index': index, 'start': start, 'end': end, 'tenants': size, 'hotFactor': factor, 'weight': weight,
                     'offeredRps': None if offered is None else offered * weight / total})
        start = end
    require(start == count and sum(r['weight'] for r in rows) == total, 'M7_DRIVER_SHARDS_PLAN')
    # The generated workload refuses an offered rate below 1 request/s.
    require(offered is None or all(r['offeredRps'] >= 1 for r in rows), 'M7_DRIVER_SHARDS_RATE')
    return rows


def write_rosters(folder, tenants, rows):
    folder = Path(folder)
    folder.mkdir(mode=0o700, exist_ok=False)
    for row in rows:
        path = folder / ('tenants-%d.private.json' % row['index'])
        path.write_text(json.dumps(tenants[row['start']:row['end']]))
        path.chmod(0o600)
    return folder


def script(rows, driver=None):
    """POSIX sh for the k6 image: start N processes, forward TERM, keep each exit code."""
    lines = ['set -u', 'pids=""']
    for row in rows:
        env = 'TENANTS_FILE=/shards/tenants-%d.private.json HOT_FACTOR=%d' % (row['index'], row['hotFactor'])
        if row['offeredRps'] is not None:
            env += ' OFFERED_RPS=' + shlex.quote(repr(row['offeredRps']))
        if driver:
            require(len(driver['environment']) == len(rows), 'M7_DRIVER_SHARDS_PLAN')
            env += ' ' + ' '.join(key + '=' + shlex.quote(value) for key,value in driver['environment'][row['index']].items())
            output = ' --out csv=/out/k6-scheduling-%d.csv.gz' % row['index'] if driver['observer']=='scheduling-v1' else ''
            lines.append('env %s k6 run --quiet --address 127.0.0.1:0 --summary-export /out/k6-summary-%d.json%s /scripts/k6-vu-driver.js > /out/k6-shard-%d.log 2>&1 &' % (env,row['index'],output,row['index']))
        else:
            lines.append('env %s k6 run --quiet --summary-export /out/k6-summary-%d.json /scripts/workload.js > /out/k6-shard-%d.log 2>&1 &'
                     % (env, row['index'], row['index']))
        lines.append('pids="$pids $!"')
    lines.append("trap 'kill -TERM $pids 2>/dev/null' TERM INT")
    lines.append('rc=0; i=0')
    lines.append('for p in $pids; do wait "$p"; c=$?; echo "$c" > /out/k6-shard-$i.rc; [ "$c" -ne 0 ] && rc=$c; i=$((i+1)); done')
    lines.append('exit $rc')
    return '\n'.join(lines)


def argv(base, image, rows, shard_folder, driver=None):
    """Rewrite one unsharded k6 docker argv; refuse any other shape."""
    base = list(base)
    require(image in base and base[-5:] == ['run', '--quiet', '--summary-export', '/out/k6-summary.json', '/scripts/workload.js'], 'M7_DRIVER_SHARDS_ARGV')
    at = base.index(image)
    head = base[:at]
    for name in ('TENANTS_FILE', 'HOT_FACTOR', 'OFFERED_RPS'):
        hits = [i for i in range(len(head) - 1) if head[i] == '-e' and str(head[i + 1]).startswith(name + '=')]
        require(len(hits) <= 1 and (hits or name == 'OFFERED_RPS'), 'M7_DRIVER_SHARDS_ARGV')
        if hits:
            del head[hits[0]:hits[0] + 2]
    return head + ['-v', str(shard_folder) + ':/shards:ro', '--entrypoint', 'sh', image, '-c', script(rows, driver)]


def _kind(value):
    if 'passes' in value or 'fails' in value:
        return 'rate'
    if any(k in value for k in ('avg', 'med', 'p(95)')):
        return 'trend'
    if 'count' in value:
        return 'counter'
    if 'value' in value:
        return 'gauge'
    return 'unknown'


def merge(summaries, rows):
    require(len(summaries) == len(rows) >= 2, 'M7_DRIVER_SHARDS_MERGE')
    names = sorted({k for s in summaries for k in s['metrics']})
    metrics, bounds = {}, {}
    for name in names:
        parts = [s['metrics'][name] for s in summaries if name in s['metrics']]
        kinds = {_kind(p) for p in parts}
        require(len(kinds) == 1 and 'unknown' not in kinds, 'M7_DRIVER_SHARDS_METRIC_KIND')
        kind = kinds.pop()
        out = {}
        if kind == 'rate':
            passes, fails = sum(p.get('passes', 0) for p in parts), sum(p.get('fails', 0) for p in parts)
            out = {'passes': passes, 'fails': fails, 'value': passes / (passes + fails) if passes + fails else 0}
        elif kind == 'counter':
            out = {'count': sum(p['count'] for p in parts), 'rate': sum(p.get('rate', 0) for p in parts)}
        elif kind == 'gauge':
            out = {k: sum(p[k] for p in parts) for k in ('value', 'min', 'max') if all(k in p for p in parts)}
        else:
            counted = [p for p in parts if p.get('count')]
            require(all('count' in p for p in parts), 'M7_DRIVER_SHARDS_TREND_COUNT')
            total = sum(p['count'] for p in parts)
            out = {'count': total}
            if counted:
                out['min'] = min(p['min'] for p in counted)
                out['max'] = max(p['max'] for p in counted)
                out['avg'] = sum(p['avg'] * p['count'] for p in counted) / total
                for q in QUANTILES:
                    values = [p[q] for p in counted if q in p]
                    if values:
                        out[q] = max(values)
                        if len(values) > 1:
                            bounds.setdefault(name, {})[q] = [min(values), max(values)]
        thresholds = {}
        for p in parts:
            for expr, failed in (p.get('thresholds') or {}).items():
                thresholds[expr] = bool(thresholds.get(expr, False) or failed)
        if thresholds:
            out['thresholds'] = thresholds
        metrics[name] = out
    return {'metrics': metrics, 'm7DriverShards': {
        'version': 1, 'shards': [{k: r[k] for k in ('index', 'tenants', 'hotFactor', 'weight', 'offeredRps')} for r in rows],
        'quantileBounds': bounds,  # Legacy field: range across shard statistics.
        'percentileMethod': 'largest-shard-statistic', 'pooledPercentiles': 'UNMEASURED',
        'scope': 'counter/rate sums, min/max and count-weighted means reduce available shard fields; '
                 'percentiles are largest-shard statistics and quantileBounds is their observed shard range, not a pooled bound; '
                 'pooled percentiles UNMEASURED without raw samples and a verified definition; '
                 'gauge extrema sum shard extrema, not synchronized peaks; setup_data omitted'}}


def collect(out, rows):
    """Merge shard summaries into k6-summary.json only when every shard exited 0 with a summary."""
    out = Path(out)
    status = []
    for row in rows:
        rc_path, summary_path = out / ('k6-shard-%d.rc' % row['index']), out / ('k6-summary-%d.json' % row['index'])
        rc = int(rc_path.read_text().strip()) if rc_path.is_file() else None
        status.append({'index': row['index'], 'returncode': rc, 'summary': summary_path.is_file()})
    record = {'version': 1, 'shards': status}
    if all(s['returncode'] == 0 and s['summary'] for s in status):
        merged = merge([json.loads((out / ('k6-summary-%d.json' % r['index'])).read_text()) for r in rows], rows)
        path = out / 'k6-summary.json'
        require(not path.exists(), 'M7_DRIVER_SHARDS_SUMMARY_EXISTS')
        path.write_text(json.dumps(merged, indent=2) + '\n')
        path.chmod(0o600)
        record['merged'] = True
    else:
        record['merged'] = False
    (out / 'k6-shards.json').write_text(json.dumps(record, indent=2) + '\n')
    return record
