"""One-shard configured driver: retain original bounded files through Pod exec.

An exporter container holds only the test Pod's emptyDir, without an API token.
The owned Pod stays until export acknowledgment or its finite Job deadline.
Raw CSV never traverses Kubernetes container logs (which may rotate).
"""
import copy
import json
import math
from pathlib import Path
import re
import time

import kube_adapter as k
import workload_runtime

FILES = {'k6.log': 8 * 1024**2, 'k6-native.log': 8 * 1024**2,
         'k6-summary.json': 4 * 1024**2, 'file-limits.txt': 16384}


def decorate(c, job, secret, receipt, script, *, exporter_resources, shell_contract):
    import native_load as n
    import driver_vu_diagnostic as driver
    manifest = workload_runtime.driver_manifest(c)
    cfg = driver.configuration(c['workload']['driverPlan'], c['workload'])
    k.need(isinstance(exporter_resources, dict), 'NATIVE_LOAD_EXPORTER_RESOURCES_REQUIRED', 'UNMEASURED')
    k.resource_budget.validate_container({'resources': exporter_resources}, k.resource_accounting(c), k.need)
    container = job['spec']['template']['spec']['containers'][0]
    k.need(isinstance(shell_contract, dict) and shell_contract.get('image') == container['image']
           and shell_contract.get('shell') == '/bin/sh' and shell_contract.get('k6') == '/usr/bin/k6'
           and shell_contract.get('fileLimitBlockBytes') == 512
           and shell_contract.get('classification') == 'reproduced'
           and k.HEX.fullmatch(shell_contract.get('evidenceSha256', '')),
           'NATIVE_LOAD_SHELL_CONTRACT_REQUIRED', 'UNMEASURED')
    # The selected k6 image's Alpine ash uses 512-byte file-limit blocks.
    # The runtime /proc read below independently proves the effective limit.
    maximum = cfg['maxTraceBytes']
    limit = maximum // 512 * 512
    k.need(limit > 0, 'NATIVE_LOAD_TRACE_BOUND')
    wrapper = (k.M7 / driver.SCRIPT).read_bytes()
    files = dict(FILES)
    if cfg['observer'] == 'scheduling-v1':
        files['k6-scheduling.csv.gz'] = maximum
    config = dict(runId=receipt['runId'], sourceSha256=n.sha(script),
                  driverWrapperSha256=n.sha(wrapper), files=files,
                  seconds=receipt['activeDeadlineSeconds'])
    secret['stringData'] = {'tenants.json': secret['stringData']['tenants.json'],
                            'workload.js': script.decode(), driver.SCRIPT: wrapper.decode(),
                            'native-artifacts.cjs': (k.HERE / 'native-artifacts.cjs').read_text(),
                            'export.json': json.dumps(config)}
    env = {row['name']: row['value'] for row in container['env']}
    launch = {name: env.pop(name) for name in ('RUN_START','M7_SETUP_SECONDS','M7_SETUP_UNTIL_MS')}
    secret['stringData']['launch.env'] = ''.join('export '+name+'='+value+'\n' for name,value in sorted(launch.items()))
    env.update(driver.configured_environment(manifest))
    container['env'] = [{'name': name, 'value': value} for name, value in sorted(env.items())]
    output = '--out csv=/out/k6-scheduling.csv.gz ' if cfg['observer'] == 'scheduling-v1' else ''
    # Shell only supervises its own test child; no workload mutation is retried.
    command = ('umask 077\n. /inputs/launch.env || exit 78\n'
               f'ulimit -f {limit // 512} || exit 78\n'
               '/bin/cat /proc/self/limits > /out/file-limits.txt || exit 78\n'
               '/usr/bin/k6 run --quiet --no-usage-report --address=127.0.0.1:0 '
               '--log-output=stderr --summary-export /out/k6-summary.json '
               + output + '/inputs/' + driver.SCRIPT + ' > /out/k6-native.log 2> /out/k6.log\n'
               'result=$?\n'
               'printf "%s\\n" "$result" > /out/exit-code\n'
               'exit "$result"\n')
    container['command'] = ['/bin/sh', '-c', command]
    container.pop('args', None)
    mounts = container.setdefault('volumeMounts', [])
    if not any(v['name'] == 'inputs' for v in mounts):
        mounts.append({'name': 'inputs', 'mountPath': '/inputs', 'readOnly': True})
    mounts.append({'name': 'artifacts', 'mountPath': '/out'})
    exporter = {'name': 'artifact-exporter', 'image': c['pins']['appImage'], 'imagePullPolicy': 'IfNotPresent',
                'command': ['node', '/inputs/native-artifacts.cjs', 'hold'],
                'resources': copy.deepcopy(exporter_resources),
                'securityContext': copy.deepcopy(container['securityContext']),
                'volumeMounts': [{'name': 'inputs', 'mountPath': '/inputs', 'readOnly': True},
                                 {'name': 'artifacts', 'mountPath': '/out'}]}
    pod = job['spec']['template']['spec']
    pod['containers'].append(exporter)
    # This is disposable local Pod storage; requests/limits and the full new Pod
    # must still enter the operating owner's fit/quota admission.
    pod['volumes'].append({'name': 'artifacts', 'emptyDir': {'sizeLimit': str(sum(files.values()) + 4096)}})
    k.need(len(json.dumps(secret).encode()) <= n.MAX_INPUT_BYTES, 'NATIVE_LOAD_INPUT_SECRET_BOUND', 'UNMEASURED')
    receipt.update(captureMode='owned-exec-files', files=files, fileLimitBytes=limit,
                   shellContract=shell_contract, driverWrapperSha256=n.sha(wrapper),
                   adaptedSha256=n.sha(wrapper), jobSha256=k.hashed(job), driverManifest=manifest,
                   artifactExporterSha256=k.digest(k.HERE / 'native-artifacts.cjs'))
    return job, secret, receipt


def capture(kube, c, wanted, out, receipt, *, clock=time, failures=None):
    """Writer exit -> bounded exec read/hash -> ack -> Job completion.

    No terminal-log artifact fallback, upload service or indefinitely waiting
    sidecar. The Job deadline also fences an interrupted controller's exporter.
    """
    import native_load as n
    import driver_vu_diagnostic as driver
    out = Path(out)
    k.need(out.name == 'load', 'NATIVE_LOAD_CONFIGURED_OUTPUT_DIRECTORY')
    ns, uid = c['namespace'], receipt['namespaceUid']
    until = clock.monotonic() + min(receipt['activeDeadlineSeconds'], k.deadline(c))
    def remaining():
        if failures:
            raise failures[0]
        seconds = min(until - clock.monotonic(), k.deadline(c))
        k.need(seconds > 0, 'NATIVE_LOAD_EXPORT_DEADLINE', 'UNMEASURED')
        return seconds
    def check_namespace():
        n._identity(c, kube.json(['get', 'namespace', ns], timeout=min(20, remaining())), uid)
    def pod_read():
        current = kube.json(['get', 'pods', '-l', 'job-name=k6'], namespace=ns, timeout=min(20, remaining()))
        k.need(len(current['items']) <= 1, 'NATIVE_LOAD_POD_CENSUS')
        return current['items'][0] if current['items'] else None
    job = kube.json(['get', 'job', 'k6'], namespace=ns, timeout=min(20, remaining()))
    k.owned(c, job)
    k.need(job['metadata']['uid'] == receipt['jobUid'] and n.job_spec_matches(wanted['spec'], job['spec']),
           'NATIVE_LOAD_JOB_CHANGED')
    pod = None
    while True:
        remaining()
        row = pod_read()
        if row is not None:
            k.owned(c, row)
            k.need(k.subset(wanted['spec']['template']['metadata']['labels'],row['metadata'].get('labels',{})),
                   'NATIVE_LOAD_POD_LABELS_CHANGED')
            ref = k.controller(row)
            k.need(ref.get('uid') == job['metadata']['uid'] and ref.get('kind') == 'Job'
                   and ref.get('name') == 'k6', 'NATIVE_LOAD_POD_CONTROLLER')
            actual, _ = k.admission_projection(wanted['spec']['template']['spec'], row['spec'])
            k.need(k.subset(wanted['spec']['template']['spec'], actual), 'NATIVE_LOAD_POD_CHANGED')
            if pod is not None:
                k.need(row['metadata']['uid'] == pod['metadata']['uid'], 'NATIVE_LOAD_POD_REPLACED')
            pod = row
            states = {s['name']: s for s in row.get('status', {}).get('containerStatuses', [])}
            k.need(all(s.get('restartCount', 0) == 0 for s in states.values()), 'NATIVE_LOAD_ACTOR_RESTARTED')
            known=receipt.setdefault('actorContainers',{})
            for actor,state in states.items():
                identity=state.get('containerID')
                if identity:
                    k.need(actor not in known or known[actor]==identity,'NATIVE_LOAD_ACTOR_REPLACED')
                    known[actor]=identity
            receipt['podUid']=row['metadata']['uid']
            k.write(out/'native-load.json',receipt)
            if states.get('k6', {}).get('state', {}).get('terminated') is not None:
                break
        clock.sleep(min(.5, remaining()))
    check_namespace()
    name, pod_uid = pod['metadata']['name'], pod['metadata']['uid']
    command = ['exec', name, '-c', 'artifact-exporter', '--', 'node', '/inputs/native-artifacts.cjs']
    raw = None
    while raw is None:
        remaining()
        # File hashing finishes after the k6 child exits. Missing manifest is
        # a bounded wait, never a substitution from container logs.
        try:
            raw = kube.call(command + ['manifest'], namespace=ns, timeout=min(20, remaining()))
        except Exception:
            current = pod_read()
            k.need(current is not None and current['metadata']['uid'] == pod['metadata']['uid'],
                   'NATIVE_LOAD_POD_REPLACED')
            states = {s['name']: s for s in current.get('status', {}).get('containerStatuses', [])}
            k.need('terminated' not in states.get('artifact-exporter', {}).get('state', {}),
                   'NATIVE_LOAD_EXPORTER_FAILED', 'UNMEASURED')
            clock.sleep(min(.5, remaining()))
    raw = raw.encode() if isinstance(raw, str) else raw
    k.need(len(raw) <= 16384, 'NATIVE_LOAD_MANIFEST_BOUND', 'UNMEASURED')
    n.private(out / 'native-artifacts.json', raw)
    meta = json.loads(raw)
    k.need(meta.get('kind') == 'm7-native-artifacts-v1' and meta.get('runId') == receipt['runId']
           and meta.get('sourceSha256') == receipt['sourceSha256']
           and meta.get('driverWrapperSha256') == receipt['driverWrapperSha256']
           and set(meta.get('files', {})) == set(receipt['files']), 'NATIVE_LOAD_MANIFEST_BINDING')
    for filename, maximum in receipt['files'].items():
        expected = meta['files'][filename]
        k.need(type(expected.get('bytes')) is int and 0 < expected['bytes'] <= maximum
               and k.HEX.fullmatch(expected.get('sha256', '')), 'NATIVE_LOAD_ARTIFACT_BOUND', 'UNMEASURED')
        data = kube.call(command + ['read', filename], data=b'', namespace=ns, timeout=min(120, remaining()))
        # fanout.Kube.call uses text when no data is supplied. Force its binary
        # mode with bytes input, including for compressed scheduling CSV.
        if isinstance(data, str):
            k.need(filename != 'k6-scheduling.csv.gz', 'NATIVE_LOAD_BINARY_TRANSPORT_REQUIRED', 'UNMEASURED')
            data = data.encode()
        k.need(isinstance(data, bytes) and len(data) <= maximum, 'NATIVE_LOAD_ARTIFACT_BOUND', 'UNMEASURED')
        n.private(out / filename, data)  # raw first, including a mismatched response
        k.need(len(data) == expected['bytes'] and n.sha(data) == expected['sha256'], 'NATIVE_LOAD_ARTIFACT_CHANGED')
    limits = (out / 'file-limits.txt').read_text()
    match = re.search(r'^Max file size\s+([0-9]+)\s+([0-9]+)\s+bytes\s*$', limits, re.M)
    k.need(match and int(match[1]) == int(match[2]) == receipt['fileLimitBytes'], 'NATIVE_LOAD_FILE_LIMIT_UNPROVEN')
    current = kube.json(['get', 'pod', name], namespace=ns, timeout=min(20, remaining()))
    k.need(current['metadata']['uid'] == pod_uid and k.controller(current) == k.controller(pod), 'NATIVE_LOAD_POD_REPLACED')
    check_namespace()
    kube.call(command + ['ack', n.sha(raw)], namespace=ns, timeout=min(20, remaining()))
    kube.call(['wait', '--for=condition=complete', 'job/k6', '--timeout=%ds' % max(1, math.ceil(remaining()))],
              namespace=ns, timeout=remaining())
    final_job = kube.json(['get', 'job', 'k6'], namespace=ns, timeout=min(20, remaining()))
    final_pod = kube.json(['get', 'pod', name], namespace=ns, timeout=min(20, remaining()))
    k.need(final_job['metadata']['uid'] == job['metadata']['uid'] and final_pod['metadata']['uid'] == pod_uid,
           'NATIVE_LOAD_ACTOR_REPLACED')
    _, process = n._terminal(c, wanted, final_job, {'items': [final_pod]})
    states = {s['name']: s for s in final_pod.get('status', {}).get('containerStatuses', [])}
    k.need(states.get('artifact-exporter', {}).get('state', {}).get('terminated', {}).get('exitCode') == 0
           and states.get('artifact-exporter', {}).get('restartCount') == 0,
           'NATIVE_LOAD_EXPORTER_FAILED', 'UNMEASURED')
    k.write(out / 'k6-process.json', process)
    k.need(process['complete'] and meta.get('exitCode') == 0, 'NATIVE_LOAD_JOB_FAILED', 'UNMEASURED')
    manifest = receipt['driverManifest']
    k.write(out / 'driver-plans.json', {'plans': driver.expected_plans(manifest), 'transport': 'in-cluster-k6-service',
                                      'manifest': manifest, 'pooledPercentiles': 'UNMEASURED'})
    accounting = driver.retain(out.parent, manifest)
    k.write(out / 'driver-accounting.json', accounting)
    receipt.update(capture='CAPTURED', process=process,
                   eventsSha256=k.digest(out / 'k6.log'), summarySha256=k.digest(out / 'k6-summary.json'),
                   artifactSha256={name: row['sha256'] for name, row in meta['files'].items()})
    k.write(out / 'native-load.json', receipt)
    return receipt
