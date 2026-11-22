"""Storage-path history seeder: a fixture's history through the product's own storage write functions.

Synthetic data only. The generator is the history spec's own module (looping_history for
synthetic-history-looping-2d-v1, looping_history_v2 for -v2, or any module with the same
`seed_roles`, `tenant_factory`, `seed_requests` interface), so the rows are exactly the rows the API
seed sends, in the same per-tenant order (v2: profile first) and, by default, the same request
boundaries (one batch = one storage transaction, as one POST is). history-loader.cjs writes them
inside an api container of the deployment through the shipping v1 domain functions (see its header).

Selected by S4_HISTORY_SEEDER=storage-loader (default `api`, the HTTP seed). Like the other seed
knobs it changes how rows are sent, never which rows, so it is not part of the fixture key.
Knobs: S4_HISTORY_LOADER_WORKERS (tenants at once in the loader, default 8),
S4_HISTORY_LOADER_GENERATORS (generator processes, default min(8, cpus)),
S4_HISTORY_LOADER_PROCESSES (loader processes in the api container, tenants dealt round-robin, default 1),
S4_HISTORY_LOADER_BATCH (rows per transaction; default: the API seed's request boundaries).
"""
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import collections
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import populated_history as h

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'history-loader.cjs'
SEEDERS = ('api', 'storage-loader')


def require(ok, code):
    if not ok:
        raise ValueError('M7_HISTORY_LOADER_' + code)


def seeder_name(environ=os.environ):
    name = environ.get('S4_HISTORY_SEEDER', 'api') or 'api'
    require(name in SEEDERS, 'SEEDER')
    return name


def limits(environ=os.environ):
    workers = int(environ.get('S4_HISTORY_LOADER_WORKERS', 8))
    generators = int(environ.get('S4_HISTORY_LOADER_GENERATORS', min(8, os.cpu_count() or 1)))
    batch = environ.get('S4_HISTORY_LOADER_BATCH')
    batch = int(batch) if batch else None
    require(1 <= workers <= 64 and 1 <= generators <= 64 and (batch is None or 1 <= batch <= 10_000), 'LIMITS')
    return workers, generators, batch


def batches(g, t, transaction=None, environ=os.environ):
    """(collection, docs) per storage transaction, in the API seed's order. Default boundaries are the
    API seed's requests (looping_history.seed_and_verify): batch rows, treatments at the treatment batch,
    bodies under the module's SEED_BODY_MAX_BYTES, one profile per request."""
    import looping_history as v1
    _, batch = h.seed_limits(environ)
    treatment_batch = int(environ.get('S4_HISTORY_SEED_TREATMENT_BATCH', batch))
    require(1 <= treatment_batch <= h.SGV_BATCH, 'SEED_LIMITS')
    for path, docs in g.seed_requests(t):
        collection = path.rsplit('/', 1)[1]
        require(collection in ('entries', 'devicestatus', 'treatments', 'profile'), 'PATH')
        if collection == 'profile':
            for doc in docs:
                yield collection, [doc]
            continue
        if transaction is not None:
            parts = [docs[k:k+transaction] for k in range(0, len(docs), transaction)]
        else:
            size = min(batch, treatment_batch) if collection == 'treatments' else batch
            parts = v1._batches(docs, size, getattr(g, 'SEED_BODY_MAX_BYTES', None))
        for part in parts:
            yield collection, part


def _module(mode):
    return h._looping(mode)


def _tenant_lines(args):
    """Worker process: one tenant's NDJSON batches (bytes) and row count."""
    mode, spec, n, ordinal, tenant_id, transaction, environ = args
    g = _module(mode)
    t = g.tenant_factory(spec, n)(ordinal)
    out, rows = [], collections.Counter()
    for collection, docs in batches(g, t, transaction, environ):
        out.append(json.dumps({'t': tenant_id, 'c': collection, 'd': docs}, separators=(',', ':')))
        rows[collection] += len(docs)
    return ('\n'.join(out) + '\n').encode(), dict(rows)


def api_container(project):
    ids = subprocess.run(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + project,
                          '--filter', 'label=com.docker.compose.service=api', '--filter', 'status=running'],
                         capture_output=True, text=True, check=True).stdout.split()
    require(len(ids) == 1, 'API_CONTAINER')
    return ids[0]


class StorageLoader:
    """The `bulk` seeder for populated_history.run: (g, spec, missing, n, until) -> receipt.

    `commands`: one argv per loader process; tenants are dealt round-robin to the processes, each
    tenant whole and in generator order."""

    def __init__(self, commands, receipt_path=None, environ=os.environ, log=sys.stderr):
        if commands and isinstance(commands[0], str):
            commands = [commands]
        self.commands, self.receipt_path, self.environ, self.log = commands, receipt_path, environ, log
        self.receipt = None

    @classmethod
    def compose(cls, project, receipt_path=None, environ=os.environ):
        workers, _, _ = limits(environ)
        processes = int(environ.get('S4_HISTORY_LOADER_PROCESSES', 1))
        require(1 <= processes <= 16, 'LIMITS')
        container = api_container(project)
        script = SCRIPT.read_text()
        commands = [['docker', 'exec', '-i', '-w', '/opt/app', '-e', 'NS_LOADER_WORKERS=' + str(workers),
                     '-e', 'NS_LOADER_API_PORT=' + str(18337 + k), '-e', 'NS_LOADER_INTERNAL_PORT=' + str(17101 + k),
                     container, 'node', '-e', script] for k in range(processes)]
        return cls(commands, receipt_path, environ)

    def __call__(self, g, spec, missing, n, until):
        workers, generators, transaction = limits(self.environ)
        started = time.time()
        shards = []
        for argv in self.commands:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            shard = {'proc': proc, 'lines': [], 'errors': [], 'queue': queue.Queue(maxsize=2 * generators),
                     'broken': False, 'tenants': 0}

            def read(shard=shard):
                shard['lines'].extend(shard['proc'].stdout)

            def drain(shard=shard):
                shard['errors'].extend(shard['proc'].stderr)

            def write(shard=shard):
                while True:
                    data = shard['queue'].get()
                    if data is None:
                        break
                    if shard['broken']:
                        continue
                    try:
                        shard['proc'].stdin.write(data)
                    except (BrokenPipeError, ValueError):
                        shard['broken'] = True
                try:
                    shard['proc'].stdin.close()
                except BrokenPipeError:
                    shard['broken'] = True
            shard['threads'] = [threading.Thread(target=f, daemon=True) for f in (read, drain, write)]
            for t in shard['threads']:
                t.start()
            shards.append(shard)
        sent = collections.Counter()
        env = {k: v for k, v in self.environ.items() if k.startswith('S4_HISTORY_')}
        jobs = [(spec['mode'], spec, n, i, tenant['id'], transaction, env) for i, tenant in missing]
        try:
            with ProcessPoolExecutor(max_workers=generators, mp_context=multiprocessing.get_context('forkserver')) as pool:
                window = collections.deque()
                it = iter(jobs)
                for job in it:
                    window.append(pool.submit(_tenant_lines, job))
                    if len(window) >= 4 * generators:
                        break
                k = 0
                while window:
                    data, rows = window.popleft().result()
                    nxt = next(it, None)
                    if nxt is not None:
                        window.append(pool.submit(_tenant_lines, nxt))
                    sent.update(rows)
                    shard = shards[k % len(shards)]
                    k += 1
                    if any(s['broken'] for s in shards):
                        break
                    shard['tenants'] += 1
                    shard['queue'].put(data)
        finally:
            for shard in shards:
                shard['queue'].put(None)
            for shard in shards:
                shard['threads'][2].join()
                shard['code'] = shard['proc'].wait()
                shard['threads'][0].join(); shard['threads'][1].join()
        dones = []
        for shard in shards:
            events = [json.loads(line) for line in shard['lines'] if line.strip().startswith(b'{')]
            done = next((e['done'] for e in events if 'done' in e), None)
            error = next((e for e in events if 'error' in e), None)
            if shard['code'] != 0 or done is None or shard['broken']:
                # stderr can hold product log lines; keep only the loader's own codes.
                require(False, 'FAILED:' + (error['error'] if error else 'EXIT_%d' % shard['code']))
            require(done['tenants'] == shard['tenants'], 'COUNT_MISMATCH')
            shard['progress'] = [e['progress'] for e in events if 'progress' in e]
            dones.append(done)
        rows = sum(d['rows'] for d in dones)
        require(rows == sum(sent.values()) and sum(d['tenants'] for d in dones) == len(missing), 'COUNT_MISMATCH')
        wall = round(time.time() - started, 1)
        self.receipt = dict(version=1, seeder='storage-loader', mode=spec['mode'], tenants=len(missing),
                            rows=rows, rowsByCollection=dict(sent), batches=sum(d['batches'] for d in dones),
                            loaderSeconds=max(d['seconds'] for d in dones), wallSeconds=wall,
                            rowsPerSecond=round(rows / max(max(d['seconds'] for d in dones), 0.001)),
                            processes=len(shards), workers=workers, generators=generators,
                            transactionRows=transaction or 'api-request-boundaries',
                            bindings=dones[0].get('bindings'),
                            progress=[s['progress'] for s in shards])
        if self.receipt_path:
            Path(self.receipt_path).write_text(json.dumps(self.receipt, indent=1) + '\n')
        return self.receipt


def for_runner(environ, project, output):
    """The bulk seeder the runner passes to populated_history.run, or None for the HTTP seed."""
    if seeder_name(environ) == 'api':
        return None
    return StorageLoader.compose(project, Path(output) / 'history-seeder.json', environ)
