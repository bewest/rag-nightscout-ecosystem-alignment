#!/usr/bin/env python3
"""Observe one prepared standard Kubernetes case from outside its controller: figures only.

  case_observer.py run CASE_DIR OUT_DIR        launch the case (experiment.py launch) and observe it
  case_observer.py observe CASE_DIR OUT_DIR    observe a case launched separately
  case_observer.py summarize CASE_DIR OUT_DIR  steady per-Pod usage, nodes and CPU models (stdout JSON)

Reads only; never creates, scales or deletes. Stops at verified absence or the cleanup deadline.

OUT_DIR/samples.jsonl, one row per interval: stage, placement (Pod NODE PHASE), node top for every
node the case uses, `kubectl top pods --containers` (one line per Pod and container, so each
evaluator ordinal is its own row) and, during traffic, the replication slot lag.
OUT_DIR/nodes.json: /proc/cpuinfo `model name` per node, read once from one running case Pod there.
During traffic each row also holds, per evaluator Pod, the CPU ticks of every thread of PID 1
(`threads`, from /proc/1/task, with /proc/uptime as the clock), and five walsender samples from
pg_stat_activity 0.2 s apart (`walsender`). OUT_DIR/pg_stat_statements-{start,latest,end}.json:
pg_stat_statements at the first traffic sample, every fourth traffic sample and the first sample
after traffic (the binding preloads it; the observer creates the extension in database `postgres`,
never in the application database).
OUT_DIR/podlogs/: only when the case's binding input sets `roleEnv` (diagnostics requested), one
`kubectl logs -f --timestamps` follower per Pod and container of each named role, started when the
Pod runs and stopped at teardown, each file bounded by --log-cap-bytes (so container log rotation
loses nothing inside the window).
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from statistics import median

LABEL = 'nightscout.org/run-id'
HERE = Path(__file__).resolve().parent
MODEL = re.compile(r'^model name\s*:\s*(.+)$', re.M)
SLOT_SQL = ("SELECT json_build_object('active',active,'confirmedLagBytes',"
            "pg_wal_lsn_diff(pg_current_wal_lsn(),confirmed_flush_lsn),'retainedWalBytes',"
            "pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn)) FROM pg_replication_slots "
            "WHERE slot_name='nsdemo_pgstream' AND NOT temporary")
TRAFFIC = 'attach released runtime'
WALSENDER_SQL = ("SELECT coalesce(json_agg(json_build_object('pid',pid,'state',state,'waitEventType',wait_event_type,"
                 "'waitEvent',wait_event)),'[]') FROM pg_stat_activity WHERE backend_type='walsender'")
PGSS_SQL = "SELECT json_build_object('at',now(),'rows',coalesce(json_agg(row_to_json(s)),'[]')) FROM pg_stat_statements s"
# PID 1's threads: tid, name, utime and stime ticks (fields 14 and 15 of stat), with /proc/uptime as the clock.
THREADS_JS = ("const fs=require('fs');const tasks=fs.readdirSync('/proc/1/task').map(t=>{const s=fs.readFileSync('/proc/1/task/'+t+'/stat','utf8');"
              "const r=s.slice(s.lastIndexOf(')')+2).split(' ');return [Number(t),s.slice(s.indexOf('(')+1,s.lastIndexOf(')')),Number(r[11]),Number(r[12])];});"
              "process.stdout.write(JSON.stringify({uptime:Number(fs.readFileSync('/proc/uptime','utf8').split(' ')[0]),tasks}))")
CLOCK_TICKS = 100  # Linux USER_HZ on the x86-64 kernels these nodes run
EVALUATOR = {'app.kubernetes.io/component': 'evaluator'}


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_bytes()) if path.is_file() else default


def now():
    return datetime.now(timezone.utc).isoformat()


class Case:
    """The prepared case: identity, pinned node and the roles whose logs were asked for."""

    def __init__(self, directory):
        self.d = Path(directory).resolve()
        e = read(self.d/'environment.json')
        self.context, self.namespace, self.run = e['context'], e['namespace'], e['runId']
        self.cleanup_seconds = e['cleanupDeadlineSeconds']
        self.node = (read(self.d/'native-run-template.json', {}).get('nativeLoad') or {}).get('nodeName')
        self.runtime = self.d/'runtime'
        inputs = read(self.d/'binding-inputs.json', {})
        self.log_roles = sorted(inputs.get('roleEnv') or {})
        workloads = {}
        for obj in manifests(read(self.d/'render.json', [])):
            if obj['kind'] in ('Deployment', 'StatefulSet'):
                spec = obj['spec']
                workloads[obj['metadata']['name']] = (spec['selector']['matchLabels'],
                                                      [c['name'] for c in spec['template']['spec']['containers']])
        self.followed = {}
        for role in self.log_roles:
            selector, containers = workloads[role]
            self.followed[role] = (selector, [role] if role in containers else containers)


def manifests(value):
    if isinstance(value, list):
        return [x for item in value for x in manifests(item)]
    if isinstance(value, dict) and value.get('kind') == 'List':
        return manifests(value['items'])
    if isinstance(value, dict) and 'apiVersion' in value and 'kind' in value:
        return [value]
    return [x for item in value.values() for x in manifests(item)] if isinstance(value, dict) else []


class Kubectl:
    def __init__(self, case, run=subprocess.run, popen=subprocess.Popen):
        self.base = ['kubectl', '--context', case.context, '-n', case.namespace]
        self.run, self.popen = run, popen

    def __call__(self, *args, timeout=12):
        return self.run(self.base + ['--request-timeout=8s', *args], capture_output=True, text=True,
                        check=True, timeout=timeout).stdout

    def follow(self, pod, container, since=None):
        argv = self.base + ['logs', '-f', '--timestamps', pod, '-c', container]
        if since:
            argv.append('--since-time=' + since)
        return self.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def stamp_key(line):
    """RFC3339Nano trims trailing zeros; compare seconds, then the fraction padded to 9 digits."""
    head = line.split(b' ', 1)[0].decode(errors='replace')
    seconds, _, fraction = head.rstrip('Z').partition('.')
    return seconds, fraction.ljust(9, '0')


class Follower:
    """One `kubectl logs -f` per Pod and container, appended to one bounded file. A follower that
    ends while its Pod still runs restarts from the last timestamp written (lines at or before it
    are dropped)."""

    def __init__(self, kubectl, path, pod, container, cap):
        self.kubectl, self.path, self.pod, self.container, self.cap = kubectl, Path(path), pod, container, cap
        self.bytes, self.last, self.starts, self.truncated = 0, None, 0, False
        self.process, self.thread, self.lock = None, None, threading.Lock()

    def alive(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.alive() or self.truncated:
            return
        since = None
        if self.last:
            seconds, fraction = self.last
            since = seconds + '.' + fraction + 'Z'
        self.process = self.kubectl.follow(self.pod, self.container, since)
        self.starts += 1
        self.thread = threading.Thread(target=self.copy, args=(self.process, self.last), daemon=True)
        self.thread.start()

    def copy(self, process, after):
        with self.path.open('ab') as out:
            for line in process.stdout:
                key = stamp_key(line)
                if after is not None and key <= after:
                    continue
                if self.bytes + len(line) > self.cap:
                    self.truncated = True
                    process.terminate()
                    break
                out.write(line)
                self.bytes += len(line)
                self.last = key
        process.wait()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.thread:
            self.thread.join(timeout=10)

    def record(self):
        return {'pod': self.pod, 'container': self.container, 'file': self.path.name, 'bytes': self.bytes,
                'starts': self.starts, 'truncatedAtCap': self.truncated, 'capBytes': self.cap}


def labelled(pod, selector):
    labels = pod['metadata'].get('labels', {})
    return all(labels.get(k) == v for k, v in selector.items())


def cpu_model(kubectl, pods, node):
    """`model name` from one running case Pod on the node; any running container that has `cat`."""
    for pod in pods:
        if pod['spec'].get('nodeName') != node or pod.get('status', {}).get('phase') != 'Running':
            continue
        for row in pod['status'].get('containerStatuses', []):
            if 'running' not in (row.get('state') or {}):
                continue
            try:
                found = MODEL.search(kubectl('exec', pod['metadata']['name'], '-c', row['name'], '--',
                                             'cat', '/proc/cpuinfo', timeout=20))
            except (subprocess.SubprocessError, OSError):
                continue
            if found:
                return {'cpuModel': found[1].strip(), 'readFrom': pod['metadata']['name'] + '/' + row['name'], 'at': now()}
    return None


def sample(case, kubectl, state):
    row = {'at': now()}
    stages = read(case.runtime/'stages.json', [])
    row['stage'] = stages[-1]['stage'] if stages else None
    meta = json.loads(kubectl('get', 'ns', case.namespace, '-o', 'json'))['metadata']
    custody = read(case.runtime/'custody.json', {})
    if meta['uid'] != custody.get('namespaceUid') or meta.get('labels', {}).get(LABEL) != case.run:
        raise LookupError('NAMESPACE_CHANGED')
    terminating = bool(meta.get('deletionTimestamp'))
    pods = json.loads(kubectl('get', 'pods', '-l', LABEL + '=' + case.run, '-o', 'json'))['items']
    row['placement'] = ['%s %s %s' % (p['metadata']['name'], p['spec'].get('nodeName') or '<none>',
                                      p.get('status', {}).get('phase')) for p in pods]
    nodes = sorted({p['spec']['nodeName'] for p in pods if p['spec'].get('nodeName')})
    row['offNode'] = [line for line in row['placement'] if case.node and line.split()[1] not in (case.node, '<none>')]
    row['nodes'] = {}
    for node in nodes:
        try:
            row['nodes'][node] = kubectl('top', 'node', node, '--no-headers').strip()
        except subprocess.SubprocessError:
            row['nodes'][node] = None
    # Lane-compatible field: the pinned node's line (or the only node).
    pinned = case.node or (nodes[0] if len(nodes) == 1 else None)
    if pinned in row['nodes']:
        row['nodeTop'] = row['nodes'][pinned]
    row['podUsage'] = kubectl('top', 'pods', '--containers', '--no-headers', '-l', LABEL + '=' + case.run).splitlines()
    for node in nodes:
        if node not in state['nodes']:
            found = cpu_model(kubectl, pods, node)
            if found:
                state['nodes'][node] = found
                write_json(state['out']/'nodes.json', state['nodes'])
    postgres = any(p['metadata']['name'] == 'postgres-0' and p.get('status', {}).get('phase') == 'Running' for p in pods)
    if row['stage'] == TRAFFIC:
        if postgres:
            raw = kubectl('exec', 'postgres-0', '-c', 'postgres', '--', 'psql', '-X', '-qAt', '-U', 'postgres',
                          '-d', 'postgres', '-c', SLOT_SQL)
            row['slot'] = json.loads(raw) if raw.strip() else 'ABSENT'
            row['walsender'] = measured(lambda: walsender(kubectl))
        row['threads'] = {p['metadata']['name']: measured(lambda p=p: threads(kubectl, p['metadata']['name']))
                          for p in pods if labelled(p, EVALUATOR) and p.get('status', {}).get('phase') == 'Running'}
        state['traffic'] = state.get('traffic', 0) + 1
        if postgres and (state['traffic'] == 1 or state['traffic'] % 4 == 0):
            statements(kubectl, state['out'], 'start' if state['traffic'] == 1 else 'latest')
    elif state.get('traffic') and not state.get('statementsEnd') and postgres:
        state['statementsEnd'] = True
        statements(kubectl, state['out'], 'end')
    follow(case, kubectl, state, pods, terminating)
    return row


def measured(read):
    try:
        return read()
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        return {'error': type(error).__name__}


def threads(kubectl, pod):
    return json.loads(kubectl('exec', pod, '-c', 'evaluator', '--', 'node', '-e', THREADS_JS, timeout=20))


def walsender(kubectl, count=5):
    argv = ['exec', 'postgres-0', '-c', 'postgres', '--', 'psql', '-X', '-qAt', '-U', 'postgres', '-d', 'postgres']
    for i in range(count):
        argv += ['-c', WALSENDER_SQL] + (['-c', 'SELECT pg_sleep(0.2)'] if i < count - 1 else [])
    return [json.loads(line) for line in kubectl(*argv, timeout=20).splitlines() if line.startswith('[')]


def statements(kubectl, out, name):
    """One pg_stat_statements snapshot; a failure is recorded, never raised."""
    try:
        raw = kubectl('exec', 'postgres-0', '-c', 'postgres', '--', 'psql', '-X', '-qAt', '-U', 'postgres', '-d', 'postgres',
                      '-c', 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements', '-c', PGSS_SQL, timeout=60)
        value = json.loads(raw.strip().splitlines()[-1])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError) as error:
        value = {'at': now(), 'error': type(error).__name__, 'verdict': 'UNMEASURED'}
    write_json(Path(out)/('pg_stat_statements-%s.json' % name), value)


def follow(case, kubectl, state, pods, terminating):
    if not case.followed:
        return
    logs = state['out']/'podlogs'
    logs.mkdir(exist_ok=True)
    for role, (selector, containers) in case.followed.items():
        for pod in pods:
            name = pod['metadata']['name']
            running = pod.get('status', {}).get('phase') == 'Running' and not pod['metadata'].get('deletionTimestamp')
            if not labelled(pod, selector) or not running or terminating:
                continue
            for container in containers:
                keyed = (name, container)
                if keyed not in state['followers']:
                    state['followers'][keyed] = Follower(kubectl, logs/('%s.%s.log' % (name, container)), name,
                                                         container, state['cap'])
                state['followers'][keyed].start()
    write_json(logs/'followers.json', [f.record() for f in state['followers'].values()])


def write_json(path, value):
    temp = Path(str(path) + '.partial')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(temp, path)


def observe(case, out, *, interval=15, cap=2 << 30, kubectl=None, stop=None, clock=time):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    kubectl = kubectl or Kubectl(case)
    state = {'out': out, 'nodes': read(out/'nodes.json', {}), 'followers': {}, 'cap': cap}
    cutoff = clock.monotonic() + case.cleanup_seconds
    stop = stop or (lambda: False)
    try:
        with (out/'samples.jsonl').open('a') as rows:
            while clock.monotonic() < cutoff and not (case.runtime/'absence.json').exists() and not stop():
                if not (case.runtime/'custody.json').exists():
                    clock.sleep(2)
                    continue
                started = clock.monotonic()
                try:
                    row = sample(case, kubectl, state)
                except LookupError:
                    break
                except (subprocess.SubprocessError, OSError, KeyError, ValueError) as error:
                    row = {'at': now(), 'error': type(error).__name__}
                row['collectionSeconds'] = round(clock.monotonic() - started, 3)
                rows.write(json.dumps(row) + '\n')
                rows.flush()
                clock.sleep(max(1, interval - row['collectionSeconds']))
    finally:
        for follower in state['followers'].values():
            follower.stop()
        if state['followers']:
            write_json(out/'podlogs'/'followers.json', [f.record() for f in state['followers'].values()])
    return state


def mc(value):
    return float(value[:-1]) if value.endswith('m') else float(value) * 1000


def mib(value):
    for suffix, scale in (('Ki', 1 / 1024), ('Mi', 1), ('Gi', 1024)):
        if value.endswith(suffix):
            return float(value[:-2]) * scale
    return float(value) / (1 << 20)


def distribution(values):
    return {'n': len(values), 'min': min(values), 'median': median(values), 'max': max(values)} if values else None


def window(case):
    """The steady window from the case result's k6 executor windows, else the traffic stage."""
    result = read(case.d/'runtime'/'result.json') or read(case.d/'result.json') or read(case.d.parent.parent/'result.json') or {}
    shards = (result.get('measurements') or {}).get('byShard') or []
    windows = shards[0].get('executorWindows', {}) if len(shards) == 1 else {}
    if windows:
        return ('k6 executor start to steady end',
                min(v['executorStartMs'] for v in windows.values()), max(v['steadyEndMs'] for v in windows.values()))
    return ('stage ' + TRAFFIC, None, None)


def thread_shares(samples):
    """Per Pod: share of one core used by PID 1's main thread (tid 1 in the Pod's PID namespace) and
    by its other threads, between consecutive samples of the same process."""
    result = {}
    for pod, series in samples.items():
        main, other, names = [], [], {}
        for a, b in zip(series, series[1:]):
            seconds = b['uptime'] - a['uptime']
            before = {t[0]: t for t in a['tasks']}
            if seconds <= 0 or 1 not in before:
                continue
            busy = {tid: (u + s - before[tid][2] - before[tid][3]) / CLOCK_TICKS / seconds
                    for tid, name, u, s in b['tasks'] if tid in before}
            main.append(round(busy.get(1, 0), 4))
            other.append(round(sum(v for tid, v in busy.items() if tid != 1), 4))
            for tid, name, _, _ in b['tasks']:
                if tid != 1 and tid in busy:
                    names.setdefault(name, []).append(busy[tid])
        result[pod] = {'mainThreadCores': distribution(main), 'otherThreadsCores': distribution(other),
                       'busiestOtherThreads': sorted(((n, round(median(v), 4)) for n, v in names.items()), key=lambda x: -x[1])[:5]}
    return result


def walsender_waits(rows):
    counts = {}
    for row in rows:
        for snapshot in row:
            for sender in snapshot if isinstance(snapshot, list) else []:
                key = '%s:%s' % (sender.get('waitEventType'), sender.get('waitEvent'))
                counts[key] = counts.get(key, 0) + 1
    return {'samples': sum(len(r) for r in rows if isinstance(r, list)), 'byWaitEvent': dict(sorted(counts.items(), key=lambda x: -x[1]))}


def statement_delta(out, top=25):
    first = read(out/'pg_stat_statements-start.json')
    last = read(out/'pg_stat_statements-end.json')
    if not last or 'rows' not in last:
        last = read(out/'pg_stat_statements-latest.json')
    if not first or not last or 'rows' not in first or 'rows' not in last:
        return {'verdict': 'UNMEASURED', 'start': (first or {}).get('error'), 'end': (last or {}).get('error')}
    total = next((k for k in ('total_exec_time', 'total_time') if last['rows'] and k in last['rows'][0]), 'total_exec_time')
    key = lambda r: (r.get('queryid'), r.get('dbid'), r.get('userid'), r.get('toplevel'))
    before = {key(r): r for r in first['rows']}
    deltas = []
    for r in last['rows']:
        b = before.get(key(r), {})
        calls = r.get('calls', 0) - b.get('calls', 0)
        if calls > 0:
            deltas.append({'queryid': r.get('queryid'), 'calls': calls, 'totalMs': round(r.get(total, 0) - b.get(total, 0), 3),
                           'rows': r.get('rows', 0) - b.get('rows', 0), 'query': (r.get('query') or '')[:160]})
    deltas.sort(key=lambda d: -d['totalMs'])
    return {'from': first['at'], 'to': last['at'], 'statements': len(deltas), 'calls': sum(d['calls'] for d in deltas),
            'totalMs': round(sum(d['totalMs'] for d in deltas), 3), 'top': deltas[:top],
            'scope': 'all databases; snapshots bracket the traffic stage, not the k6 steady window exactly'}


TRACE = b'PGSTREAM_RECEIVER_TRACE '


def delivery(out):
    """Per pgstream transaction batch (commit position), from the evaluator receivers' own trace
    (NS_PGSTREAM_RECEIVER_TRACE=1 in roleEnv): first receipt to last response across the slices that
    received it, and the gap from one batch's last response to the next batch's first receipt.
    Receiver wall clocks on different nodes are not aligned; the trace drops lines above 100/s."""
    logs = out/'podlogs'
    batches, dropped = {}, 0
    for path in sorted(logs.glob('*.evaluator.log')) if logs.is_dir() else []:
        pod = path.name.split('.')[0]
        for line in path.read_bytes().splitlines():
            at = line.find(TRACE)
            if at < 0:
                continue
            try:
                row = json.loads(line[at + len(TRACE):])
            except ValueError:
                continue
            dropped += row.get('dropped', 0) or 0
            if row.get('event') != 'response-finished' or not row.get('position') or row.get('status') != 200:
                continue
            cell = batches.setdefault(row['position'], {})
            cell[pod] = (row['at'] - row['elapsedMs'], row['at'], row.get('rows'))
    if not batches:
        return {'verdict': 'UNMEASURED', 'reason': 'no receiver trace in podlogs (roleEnv NS_PGSTREAM_RECEIVER_TRACE=1)'}
    ordered = sorted(batches.values(), key=lambda c: min(v[0] for v in c.values()))
    spans = [max(v[1] for v in c.values()) - min(v[0] for v in c.values()) for c in ordered]
    gaps = [min(v[0] for v in b.values()) - max(v[1] for v in a.values()) for a, b in zip(ordered, ordered[1:])]
    return {'batches': len(ordered), 'slicesPerBatch': distribution([len(c) for c in ordered]),
            'deliverySpanMs': distribution(spans), 'interBatchGapMs': distribution(gaps), 'droppedTraceLines': dropped,
            'scope': 'read-derived from receiver timestamps; includes evaluator receipt time; clocks unaligned across nodes'}


def summarize(case, out):
    out = Path(out)
    label, start, end = window(case)
    pods, roles, nodes, placement = {}, {}, {}, {}
    thread_samples, walsender_rows = {}, []
    used = 0
    for line in (out/'samples.jsonl').read_text().splitlines():
        row = json.loads(line)
        if 'podUsage' not in row:
            continue
        at = datetime.fromisoformat(row['at']).timestamp() * 1000
        if start is not None and not (start <= at < end) or start is None and row.get('stage') != TRAFFIC:
            continue
        used += 1
        for pod, value in (row.get('threads') or {}).items():
            if isinstance(value, dict) and 'tasks' in value:
                thread_samples.setdefault(pod, []).append(value)
        if isinstance(row.get('walsender'), list):
            walsender_rows.append(row['walsender'])
        for entry in row.get('placement', []):
            name, node, _ = entry.split()
            placement[name] = node
        total = {}
        for entry in row['podUsage']:
            fields = entry.split()
            if len(fields) < 4:
                continue
            pod, container, cpu, memory = fields[:4]
            cell = pods.setdefault(pod, {}).setdefault(container, {'cpuMillicores': [], 'workingSetMiB': []})
            cell['cpuMillicores'].append(mc(cpu))
            cell['workingSetMiB'].append(mib(memory))
            sums = total.setdefault(container, [0.0, 0.0, 0])
            sums[0] += mc(cpu)
            sums[1] += mib(memory)
            sums[2] += 1
        for container, (cpu, memory, count) in total.items():
            cell = roles.setdefault(container, {'cpuMillicores': [], 'workingSetMiB': [], 'pods': []})
            cell['cpuMillicores'].append(cpu)
            cell['workingSetMiB'].append(memory)
            cell['pods'].append(count)
        for node, top in (row.get('nodes') or {}).items():
            fields = (top or '').split()
            if len(fields) >= 4:
                cell = nodes.setdefault(node, {'cpuMillicores': [], 'cpuPercent': [], 'memoryMiB': []})
                cell['cpuMillicores'].append(mc(fields[1]))
                cell['cpuPercent'].append(float(fields[2].rstrip('%')))
                cell['memoryMiB'].append(mib(fields[3]))
    models = read(out/'nodes.json', {})
    every = sorted(set(nodes) | set(models) | set(placement.values()) - {'<none>'})
    return {
        'run': case.run, 'window': label, 'samples': used,
        'nodes': [{'name': node, 'cpuModel': (models.get(node) or {}).get('cpuModel', 'UNMEASURED'),
                   **{k: distribution(v) for k, v in nodes.get(node, {}).items()}} for node in every],
        # Per Pod: each evaluator ordinal separately, with the node it ran on.
        'steadyPodUsage': {pod: {'node': placement.get(pod), **{c: {k: distribution(v) for k, v in cell.items()}
                                                                for c, cell in containers.items()}}
                           for pod, containers in sorted(pods.items())},
        # Per container name, summed over its Pods in each sample (K=1: the one Pod).
        'steadyContainerUsage': {c: {'pods': max(cell['pods']), 'cpuMillicores': distribution(cell['cpuMillicores']),
                                     'workingSetMiB': distribution(cell['workingSetMiB'])}
                                 for c, cell in sorted(roles.items())},
        'podLogs': read(out/'podlogs'/'followers.json'),
        'evaluatorThreads': thread_shares(thread_samples),
        'walsender': walsender_waits(walsender_rows),
        'pgStatStatements': statement_delta(out),
        'pgstreamDelivery': delivery(out),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=('run', 'observe', 'summarize'))
    parser.add_argument('case', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--interval', type=float, default=15)
    parser.add_argument('--log-cap-bytes', type=int, default=2 << 30, help='per Pod and container (default 2 GiB)')
    a = parser.parse_args(argv)
    os.umask(0o077)
    case = Case(a.case)
    if a.action == 'summarize':
        print(json.dumps(summarize(case, a.out), indent=2))
        return 0
    if a.action == 'observe':
        observe(case, a.out, interval=a.interval, cap=a.log_cap_bytes)
        return 0
    a.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (a.out/'launch.log').open('x') as log:
        controller = subprocess.Popen([sys.executable, '-B', str(HERE/'experiment.py'), 'launch',
                                       str(case.d/'lifecycle-bound.json')], stdout=log, stderr=subprocess.STDOUT)
        observe(case, a.out, interval=a.interval, cap=a.log_cap_bytes,
                stop=lambda: controller.poll() is not None)
        rc = controller.wait()
    print(json.dumps({'case': case.run, 'controllerExit': rc}))
    return rc


if __name__ == '__main__':
    sys.exit(main())
