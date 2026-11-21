"""Evaluator main-thread CPU per accepted write (Compose).

Sampler: waits for the Compose project's `evaluator` container, then streams one
`docker exec` shell loop that prints, once a second, utime+stime ticks of every
node process in the container (cmdline starts with `node`; node names
its main thread `MainThread`, so `comm` is not used) (`/proc/<pid>/stat`, the whole process) and of its
main thread (`/proc/<pid>/task/<pid>/stat`). Each tick is stamped with the host
monotonic clock on arrival, the clock the runner's SQL snapshot timing uses
(`collector-host-monotonic-v1`). A restarted container is re-attached and its
samples carry the new container id.

Reducer: interpolates the main thread's ticks at the SQL window bounds and divides
by accepted writes. Ticks are converted with the container's CLK_TCK (read once;
100 if unreadable, recorded as `assumed`).
"""
import json
import subprocess
import threading
import time
from pathlib import Path

LOOP = (
    'while :; do echo T; for p in /proc/[0-9]*; do i=${p#/proc/}; '
    'case "$(tr "\\0" " " < $p/cmdline 2>/dev/null)" in node*) ;; *) continue;; esac; '
    'echo "P $i $(cut -d" " -f14,15 $p/stat 2>/dev/null) $(cut -d" " -f14,15 $p/task/$i/stat 2>/dev/null) '
    '$(tr "\\0" " " < $p/cmdline 2>/dev/null | cut -c1-120)"; done; sleep 1; done'
)


def _container(project, service='evaluator'):
    out = subprocess.run(['docker', 'ps', '-q', '--no-trunc', '--filter', f'label=com.docker.compose.project={project}',
                          '--filter', f'label=com.docker.compose.service={service}'],
                         capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def _clk_tck(cid):
    r = subprocess.run(['docker', 'exec', cid, 'getconf', 'CLK_TCK'], capture_output=True, text=True)
    try:
        return int(r.stdout.strip()), 'read'
    except ValueError:
        return 100, 'assumed'


class Sampler:
    """Background sampler; write JSON lines to `path` until stop()."""

    def __init__(self, project, path, service='evaluator'):
        self.project, self.path, self.service = project, Path(path), service
        self._stop = threading.Event()
        self._proc = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
        self.thread.join(timeout=10)

    def _run(self):
        with self.path.open('a') as out:
            while not self._stop.is_set():
                cid = _container(self.project, self.service)
                if not cid:
                    self._stop.wait(2)
                    continue
                hz, origin = _clk_tck(cid)
                out.write(json.dumps({'kind': 'attach', 'container': cid[:12], 'clkTck': hz, 'clkTckOrigin': origin,
                                      'monoNs': time.monotonic_ns()}) + '\n')
                out.flush()
                self._proc = subprocess.Popen(['docker', 'exec', cid, 'sh', '-c', LOOP], stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL, text=True, bufsize=1)
                tick = None
                # readline, not iteration: iteration reads ahead in 8 KiB blocks and would stamp
                # ticks with their late arrival time.
                for line in iter(self._proc.stdout.readline, ''):
                    if self._stop.is_set():
                        break
                    if line.startswith('T'):
                        if tick and tick['procs']:
                            out.write(json.dumps(tick) + '\n')
                            out.flush()
                        tick = {'kind': 'tick', 'container': cid[:12], 'monoNs': time.monotonic_ns(), 'procs': {}}
                    elif line.startswith('P ') and tick is not None:
                        f = line.split(None, 6)
                        if len(f) >= 6 and all(x.isdigit() for x in f[1:6]):
                            tick['procs'][f[1]] = {'proc': int(f[2]) + int(f[3]), 'main': int(f[4]) + int(f[5]),
                                                   'cmd': f[6].strip() if len(f) > 6 else ''}
                if tick and tick['procs']:
                    out.write(json.dumps(tick) + '\n')
                out.flush()
                if self._stop.is_set() and self._proc.poll() is None:
                    self._proc.kill()
                self._proc.wait()
                self._stop.wait(1)


def _at(points, t):
    """Linear interpolation of (t, value) at t; None if t is outside the samples."""
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)
    return None


def reduce(path, window, writes):
    """window: (startNs, endNs) host monotonic. Returns the main-thread CPU of the busiest node process."""
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    attach = [r for r in rows if r['kind'] == 'attach']
    ticks = [r for r in rows if r['kind'] == 'tick']
    start, end = window
    inside = [r for r in ticks if start <= r['monoNs'] <= end]
    out = {'status': 'UNMEASURED', 'samples': len(inside), 'scope':
           'utime+stime of the evaluator main thread (/proc/<pid>/task/<pid>/stat) between the SQL statement reads; '
           '1 s sampling, linear interpolation at the bounds'}
    if not attach or not ticks:
        out['reason'] = 'NO_SAMPLES'
        return out
    if len({r['container'] for r in ticks if start - 5e9 <= r['monoNs'] <= end + 5e9}) != 1:
        out['reason'] = 'CONTAINER_CHANGED_IN_WINDOW'
        return out
    cid = next(r['container'] for r in ticks if start - 5e9 <= r['monoNs'] <= end + 5e9)
    hz, origin = next((a['clkTck'], a['clkTckOrigin']) for a in attach if a['container'] == cid)
    series = [r for r in ticks if r['container'] == cid]
    pids = {}
    for r in series:
        for pid, v in r['procs'].items():
            pids.setdefault(pid, []).append((r['monoNs'], v))
    best = None
    for pid, pts in pids.items():
        main = [(t, v['main']) for t, v in pts]
        proc = [(t, v['proc']) for t, v in pts]
        m0, m1 = _at(main, start), _at(main, end)
        p0, p1 = _at(proc, start), _at(proc, end)
        if None in (m0, m1, p0, p1):
            continue
        row = {'pid': pid, 'cmd': pts[-1][1]['cmd'], 'mainSeconds': (m1 - m0) / hz, 'processSeconds': (p1 - p0) / hz}
        if best is None or row['mainSeconds'] > best['mainSeconds']:
            best = row
    if best is None:
        out['reason'] = 'WINDOW_NOT_COVERED'
        return out
    seconds = (end - start) / 1e9
    out.update({'status': 'MEASURED', 'container': cid, 'clkTck': hz, 'clkTckOrigin': origin, 'pid': best['pid'],
                'cmd': best['cmd'], 'windowSeconds': round(seconds, 1),
                'mainThreadSeconds': round(best['mainSeconds'], 2),
                'processSeconds': round(best['processSeconds'], 2),
                'mainThreadBusyShare': round(best['mainSeconds'] / seconds, 4) if seconds else None,
                'mainThreadMsPerWrite': round(1000 * best['mainSeconds'] / writes, 3) if writes else None,
                'processMsPerWrite': round(1000 * best['processSeconds'] / writes, 3) if writes else None})
    return out


def sample_paths(run, workers):
    """One independent sample stream per evaluator; the first retains its original filename."""
    return {('evaluator' if i == 1 else f'evaluator-{i}'):
            run.parent / (run.name + ('' if i == 1 else f'-evaluator-{i}') + '-main-thread.jsonl')
            for i in range(1, workers + 1)}


def reduce_services(run, workers, window, writes):
    by_service = {}
    for service, path in sample_paths(run, workers).items():
        by_service[service] = reduce(path, window, writes) if path.is_file() else {
            'status': 'UNMEASURED', 'reason': 'NO_SAMPLER_FILE'}
    if workers == 1:
        return by_service['evaluator']
    total = {'status': 'UNMEASURED', 'byService': by_service,
             'scope': 'Summed evaluator CPU across slices per fleet write; busy share is the mean across slices.'}
    if any(row['status'] != 'MEASURED' for row in by_service.values()):
        total['reason'] = 'INCOMPLETE_EVALUATOR_SLICES'
        return total
    total['status'] = 'MEASURED'
    for key in ('mainThreadMsPerWrite', 'processMsPerWrite'):
        total[key] = round(sum(row[key] for row in by_service.values()), 3) if writes else None
    shares = [row['mainThreadBusyShare'] for row in by_service.values()]
    total['mainThreadBusyShare'] = round(sum(shares) / workers, 4) if None not in shares else None
    return total
