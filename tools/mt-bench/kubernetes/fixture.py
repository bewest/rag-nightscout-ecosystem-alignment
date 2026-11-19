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
                  '--entrypoint', 'node', image, 'deploy/multitenant/prime.js']
        for args in (['provision', '--tenant-count', str(count)], ['prime', '--concurrency', str(concurrency)]):
            seconds = cutoff - time.time()
            if seconds <= 0:
                raise RuntimeError('K8S_FIXTURE_DEADLINE')
            with (state/(args[0]+'.log')).open('xb') as log:
                subprocess.run([*client, *args], stdout=log, stderr=log, check=True, timeout=seconds)
    return tenant_projection(json.loads((state/'tenants.json').read_bytes()), count)


def claim_roster(kubectl, spec, inventory, state, count, cutoff):
    """Mount the existing results claim read-only. Transfer only DATA projection through exec."""
    import adapter
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
        return rows
    finally:
        # The ordinary namespace cleanup also owns this read-only client.
        subprocess.run([*kubectl,'delete','pod','fixture-reader','--ignore-not-found','--wait=false'],
                       timeout=10, capture_output=True)
