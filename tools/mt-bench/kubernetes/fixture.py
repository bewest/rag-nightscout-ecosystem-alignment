"""Collect synthetic DATA credentials using the rendered deployment and its private Services."""
import json
import math
from pathlib import Path
import subprocess
import time


def reader_pod(job, inventory, location, seconds):
    template = job['spec']['template']
    spec = template['spec']
    primer, = spec['containers']
    state = next(v for v in spec['volumes'] if v['name'] == 'client-state')
    results = inventory['results']['primer']
    if results['file'] != 'tenants.json' or primer['name'] != 'primer':
        raise RuntimeError('K8S_FIXTURE_RESULTS_CHANGED')
    reader = {key: primer[key] for key in ('image', 'imagePullPolicy', 'securityContext', 'resources')}
    reader.update(name='reader', command=['node', '-e', 'setTimeout(() => {}, %d)' % (max(120, seconds) * 1000)],
                  volumeMounts=[{'name': 'client-state', 'mountPath': '/results', 'readOnly': True}])
    pod = {'apiVersion': 'v1', 'kind': 'Pod',
           'metadata': {**template['metadata'], 'generateName': 'fixture-reader-', 'namespace': inventory['namespace']},
           'spec': {**spec, 'containers': [reader], 'activeDeadlineSeconds': seconds}}
    if location == 'claim':
        claim = results.get('claim')
        if not claim or state.get('persistentVolumeClaim', {}).get('claimName') != claim:
            raise RuntimeError('K8S_FIXTURE_CLAIM_REQUIRED')
        # Restores read the already commissioned roster without seeding again.
        pod['spec'].pop('initContainers', None)
        pod['spec']['volumes'] = [{'name': 'client-state', 'persistentVolumeClaim': {'claimName': claim, 'readOnly': True}}]
    elif location == 'pod' and 'emptyDir' in state and not results.get('claim'):
        # A disposable results volume lives for one Pod. Kubernetes orders the
        # shipping primer before the DATA reader and owns both containers' cleanup.
        pod['spec']['initContainers'] = [*spec.get('initContainers', []), primer]
    else:
        raise RuntimeError('K8S_FIXTURE_STORAGE_MISMATCH')
    return pod


DETACH_SECONDS = 90


def wait_detached(run, claim, cutoff, seconds=DETACH_SECONDS, clock=time):
    """Before a second Pod mounts an RWO claim the primer just released: wait (bounded) until no
    VolumeAttachment names its volume. A reader attached during the primer's detach can be
    reported attached without a device and stall in FailedMount (fixture-restore fault 2)."""
    volume = run(['get', 'pvc', claim, '-o', 'jsonpath={.spec.volumeName}']).stdout.decode().strip()
    started = clock.time()
    until = min(cutoff, started + seconds)
    while True:
        rows = json.loads(run(['get', 'volumeattachments', '-o', 'json']).stdout)['items']
        held = sorted(r['metadata']['name'] for r in rows
                      if (r.get('spec', {}).get('source') or {}).get('persistentVolumeName') == volume)
        if not held or clock.time() >= until:
            # A figure, not a stop: past the bound the reader is created as before.
            return {'volume': volume, 'waitedSeconds': round(clock.time() - started, 3), 'attachedAtCreate': held}
        clock.sleep(2)


def runner(kubectl, cutoff):
    def run(args, **kwargs):
        remaining = cutoff - time.time()
        if remaining <= 0:
            raise RuntimeError('K8S_FIXTURE_DEADLINE')
        return subprocess.run([*kubectl, *args], check=True, capture_output=True, timeout=min(remaining, 30), **kwargs)
    return run


def hold_reader(run, job, inventory, cutoff, clock=time):
    """Create the claim's reader on the primer Pod's node while the primer still uses the volume,
    so the RWO volume stays attached from primer to reader. Readers created after the primer's
    detach took 14 min from creation to roster read although no VolumeAttachment remained
    (fixture-restore fault 2: 2 of 4 keyed restores on CSI v4.20.0, 2026-11-20); one attachment
    avoids the handoff."""
    while True:
        rows = json.loads(run(['get', 'pods', '-l', 'job-name=' + job['metadata']['name'], '-o', 'json']).stdout)['items']
        nodes = sorted({p['spec']['nodeName'] for p in rows if p['spec'].get('nodeName')})
        if nodes:
            break
        if clock.time() >= cutoff:
            raise RuntimeError('K8S_FIXTURE_PRIMER_UNSCHEDULED')
        clock.sleep(1)
    seconds = min(job['spec']['activeDeadlineSeconds'], max(1, math.ceil(cutoff - clock.time())))
    pod = reader_pod(job, inventory, 'claim', seconds)
    # Bound to the node directly: the attach/detach controller then keeps the volume attached.
    pod['spec']['nodeName'] = nodes[0]
    created = json.loads(run(['create', '-f', '-', '-o', 'json'], input=json.dumps(pod).encode()).stdout)
    return {'name': created['metadata']['name'], 'uid': created['metadata']['uid'], 'node': nodes[0],
            'primerPods': len(rows), 'createdAt': clock.time()}


def read_roster(kubectl, job, inventory, directory, count, cutoff, location, held=None):
    from contract import tenant_projection
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = runner(kubectl, cutoff)
    if held:
        (directory/'reader-held.json').write_text(json.dumps(held) + '\n')
        created = {'metadata': {'name': held['name'], 'uid': held['uid']}}
    else:
        seconds = min(job['spec']['activeDeadlineSeconds'], max(1, math.ceil(cutoff - time.time())))
        pod = reader_pod(job, inventory, location, seconds)
        if location == 'claim':
            detach = wait_detached(run, inventory['results']['primer']['claim'], cutoff)
            (directory/'reader-detach.json').write_text(json.dumps(detach) + '\n')
        created = json.loads(run(['create', '-f', '-', '-o', 'json'], input=json.dumps(pod).encode()).stdout)
    name = created['metadata']['name']
    try:
        while True:
            observed = json.loads(run(['get', 'pod', name, '-o', 'json']).stdout)
            if observed['metadata']['uid'] != created['metadata']['uid']:
                raise RuntimeError('K8S_FIXTURE_POD_CHANGED')
            status = observed.get('status', {})
            if any(c['type'] == 'Ready' and c['status'] == 'True' for c in status.get('conditions', [])):
                break
            if status.get('phase') in ('Failed', 'Succeeded'):
                raise RuntimeError('K8S_FIXTURE_POD_TERMINATED')
            time.sleep(1)
        # Keep management credentials inside the Pod, including on failure.
        project = """const r = require('/results/tenants.json');
const tenants = r.tenants.map(({id, host, dataToken}) => ({id, host, dataToken}));
process.stdout.write(JSON.stringify({version: r.version, tenants}));"""
        result = run(['exec', name, '-c', 'reader', '--', 'node', '-e', project])
        rows = tenant_projection(json.loads(result.stdout), count)
        if location == 'pod':
            return rows, 'fresh'
        claims = inventory['storage'].get('claims', {})
        parts = ('postgres', 'vault', 'provisionState', 'primerResults')
        reuse = 'UNMEASURED'
        if all(claims.get(part) for part in parts):
            response = json.loads(run(['get', 'pvc', *(claims[part] for part in parts), '-o', 'json']).stdout)
            volumes = response['items']
            if len(volumes) == len(parts) and all(v.get('status', {}).get('phase') == 'Bound' and
                    (v['spec'].get('dataSource') or {}).get('kind') in ('VolumeSnapshot', 'PersistentVolumeClaim') for v in volumes):
                reuse = 'reused'
        return rows, reuse
    finally:
        # Kubernetes allocated this name for this reader. The owned namespace
        # cleanup remains the backstop if the API is unavailable.
        subprocess.run([*kubectl, 'delete', 'pod', name, '--ignore-not-found', '--wait', '--timeout=15s'],
                       timeout=18, capture_output=True)


def completion(kubectl, roles, pair, image, instrument):
    import commissioning_context
    script = (Path(__file__).resolve().parents[1]/'m7-joined/settings-context.cjs').read_bytes()
    def sample(role):
        target = roles[role]
        return json.loads(subprocess.check_output(
            [*kubectl, 'exec', '-i', target['workload'], '-c', target['container'], '--', 'node', '-', role],
            input=script, timeout=30))
    return commissioning_context.completion(sample('evaluator'),sample('realtime'),pair,image,instrument)


def existing(c, inventory, objects, directory, cutoff):
    """Read a commissioned fixture supplied by the operator without owning its lifecycle."""
    import kube_adapter as k
    kubectl = [c['kubectl'], '--context', c['context'], '-n', c['namespace']]
    def namespace():
        raw = subprocess.check_output([*kubectl,'get','namespace',c['namespace'],'-o','json'],timeout=15)
        ns = json.loads(raw)['metadata']
        k.need(ns.get('labels',{}).get('nightscout.org/run-id') == c['runId'], 'FIXTURE_NAMESPACE_OWNER')
        return ns['uid']
    uid = namespace()
    primer = objects['Job/primer']
    rows, reuse = read_roster(kubectl, primer, inventory, directory, c['tenants'], cutoff, location='claim')
    observed = completion(kubectl,c['roles'],c['pins']['pair'],c['pins']['appImageId'],c['pins']['instrument'])
    k.need(namespace() == uid, 'FIXTURE_NAMESPACE_CHANGED')
    path = directory/'data-roster.private.json'
    k.write(path,rows)
    k.write(directory/'fixture.json',{'namespaceUid':uid,'location':'claim','reuse':reuse,'tenants':len(rows)})
    c.update(tenantsFile=str(path),completion=observed,primerLocation='claim')
