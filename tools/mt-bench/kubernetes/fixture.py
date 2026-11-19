"""Prepare disposable synthetic DATA credentials through the deployment's own lab client."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import time


@contextmanager
def forward(kubectl, target, port, log, deadline):
    with Path(log).open('xb') as stream:
        process = subprocess.Popen([*kubectl, 'port-forward', '--address', '127.0.0.1',
                                    target, ':' + str(port)], stdout=stream, stderr=subprocess.STDOUT)
        try:
            while time.time() < deadline and process.poll() is None:
                match = re.search(r'Forwarding from 127\.0\.0\.1:(\d+) -> ' + str(port),
                                  Path(log).read_text(errors='replace'))
                if match:
                    yield 'http://127.0.0.1:' + match[1]
                    return
                time.sleep(.1)
            raise RuntimeError('K8S_FIXTURE_FORWARD_UNAVAILABLE')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def controller_roster(kubectl, image, core, state, count, concurrency, cutoff):
    from contract import tenant_projection
    import adapter
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    with forward(kubectl, 'service/admin', 1342, state/'admin-forward.log', cutoff) as admin, \
         forward(kubectl, 'service/api', 1337, state/'api-forward.log', cutoff) as api:
        # The public owner consumer id is part of the shipping role contract.
        consumer = subprocess.check_output(
            ['node', '-p', "require('./lib/server/serve/deployment-settings').IDENTITY.managementConsumer"],
            cwd=core, text=True, timeout=10).strip()
        config = state/'config.json'
        adapter.write(config, dict(version=1, adminOrigin=admin, apiOrigin=api, ownerConsumer=consumer))
        client = ['docker', 'run', '--rm', '--pull=never', '--network=host', '--user', f'{os.getuid()}:{os.getgid()}',
                  '--mount', 'type=bind,src='+str(state)+',dst=/run/ns-primer', '--workdir', '/opt/app',
                  '--entrypoint', 'node']
        for args in (['provision', '--tenant-count', str(count)], ['prime', '--concurrency', str(concurrency)]):
            seconds = cutoff - time.time()
            if seconds <= 0:
                raise RuntimeError('K8S_FIXTURE_DEADLINE')
            cidfile = state/(args[0]+'.cid')
            try:
                with (state/(args[0]+'.log')).open('xb') as log:
                    subprocess.run([*client,'--cidfile',cidfile,image,'deploy/multitenant/prime.js',*args],
                                   stdout=log, stderr=log, check=True, timeout=seconds)
            finally:
                if cidfile.is_file():
                    cid = cidfile.read_text().strip()
                    if re.fullmatch('[0-9a-f]{64}', cid):
                        subprocess.run(['docker','rm','--force',cid], capture_output=True, timeout=12)
    return tenant_projection(json.loads((state/'tenants.json').read_bytes()), count)


def claim_roster(kubectl, spec, inventory, state, count, cutoff):
    """Mount the existing results claim read-only. Transfer only DATA projection through exec."""
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    info = inventory['results']['primer']
    claim = info.get('claim')
    if not claim or info['file'] != 'tenants.json':
        raise RuntimeError('K8S_FIXTURE_CLAIM_REQUIRED')
    actor = {'name':'reader', 'image':inventory['images']['app'],
             'command':['node','-e','setTimeout(() => {}, 120000)'],
             'volumeMounts':[{'name':'results','mountPath':'/results','readOnly':True}],
             'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,
                                'capabilities':{'drop':['ALL']}}}
    # Reuse the lab client's scheduling and resource settings.
    primer = spec['spec']['template']['spec']
    actor['resources'] = next(c['resources'] for c in primer['containers'] if c['name']=='primer')
    pod = {'apiVersion':'v1','kind':'Pod',
           'metadata':{'name':'fixture-reader','namespace':inventory['namespace'],'labels':inventory['ownership']['label']},
           'spec':{key:primer[key] for key in ('imagePullSecrets','tolerations','securityContext') if key in primer}}
    pod['spec'].update(restartPolicy='Never',automountServiceAccountToken=False,activeDeadlineSeconds=120,
                       containers=[actor],volumes=[{'name':'results','persistentVolumeClaim':{'claimName':claim,'readOnly':True}}])
    def run(args, **kwargs):
        remaining = cutoff - time.time()
        if remaining <= 0:
            raise RuntimeError('K8S_FIXTURE_DEADLINE')
        return subprocess.run([*kubectl,*args], check=True, timeout=min(remaining, 125), capture_output=True, **kwargs)
    run(['create','-f','-'], input=json.dumps(pod).encode())
    try:
        run(['wait','--for=condition=Ready','--timeout=110s','pod/fixture-reader'])
        js = "const r=require('/results/tenants.json');console.log(JSON.stringify(r.tenants.map(t=>({id:t.id,host:t.host,token:t.dataToken}))));"
        rows = json.loads(run(['exec','fixture-reader','--','node','-e',js]).stdout)
        if len(rows) != count:
            raise RuntimeError('K8S_FIXTURE_ROSTER_CHANGED')
        claims = inventory['storage'].get('claims', {})
        parts = ('postgres','vault','provisionState','primerResults')
        reuse = 'UNMEASURED'
        if all(claims.get(part) for part in parts):
            response = json.loads(run(['get','pvc',*(claims[part] for part in parts),'-o','json']).stdout)
            volumes = response['items']
            if len(volumes) == len(parts) and all(v.get('status',{}).get('phase') == 'Bound' and
                    (v['spec'].get('dataSource') or {}).get('kind') in ('VolumeSnapshot','PersistentVolumeClaim') for v in volumes):
                reuse = 'reused'
        return rows, reuse
    finally:
        # The ordinary namespace cleanup also owns this read-only client.
        subprocess.run([*kubectl,'delete','pod','fixture-reader','--ignore-not-found','--wait','--timeout=15s'],
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
    rows, reuse = claim_roster(kubectl,primer,inventory,directory,c['tenants'],cutoff)
    observed = completion(kubectl,c['roles'],c['pins']['pair'],c['pins']['appImageId'],c['pins']['instrument'])
    k.need(namespace() == uid, 'FIXTURE_NAMESPACE_CHANGED')
    path = directory/'data-roster.private.json'
    k.write(path,rows)
    k.write(directory/'fixture.json',{'namespaceUid':uid,'location':'claim','reuse':reuse,'tenants':len(rows)})
    c.update(tenantsFile=str(path),completion=observed,primerLocation='claim')
