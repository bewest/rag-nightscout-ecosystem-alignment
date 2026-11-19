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
    secret['stringData'] = {**secret['stringData'],
                            'workload.js': script.decode(), driver.SCRIPT: wrapper.decode(),
                            'native-artifacts.cjs': (k.HERE / 'native-artifacts.cjs').read_text(),
                            'export.json': json.dumps(config)}
    env = {row['name']: row['value'] for row in container['env']}
    launch = {name: env.pop(name) for name in ('RUN_START','M7_SETUP_SECONDS','M7_SETUP_UNTIL_MS')}
    secret['stringData']['launch.env'] = ''.join('export '+name+'='+value+'\n' for name,value in sorted(launch.items()))
    env.update(driver.configured_environment(manifest))
    # Persisted configuration sorts object keys. Keep this JSON-valued env
    # byte-identical across reloads so exact Job declaration checks remain valid.
    env['M7_DRIVER_PLAN'] = json.dumps(json.loads(env['M7_DRIVER_PLAN']),
                                       sort_keys=True, separators=(',', ':'))
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
    receipt.update(captureMode='owned-exec-files', files=files, fileLimitBytes=limit,
                   shellContract=shell_contract, driverWrapperSha256=n.sha(wrapper),
                   adaptedSha256=n.sha(wrapper), jobSha256=k.hashed(job), driverManifest=manifest,
                   artifactExporterSha256=k.digest(k.HERE / 'native-artifacts.cjs'))
    return job, secret, receipt


def observe_actors(receipt, pod):
    """Track each process lifetime within the admitted Job."""
    uid = pod['metadata']['uid']
    prior_uid = receipt.get('podUid')
    actors = receipt.setdefault('actorContainers', {})
    images = receipt.setdefault('actorImages', {})
    states = pod.get('status', {}).get('containerStatuses', [])
    if prior_uid and prior_uid != uid:
        receipt.setdefault('actorTransitions', []).append({'actor': 'Pod', 'from': prior_uid, 'to': uid})
        if actors.get('k6'):
            receipt['writerContinuity'] = 'UNMEASURED'
        actors.clear()
        images.clear()
    receipt['podUid'] = uid
    for state in states:
        name, identity = state['name'], state.get('containerID')
        prior = actors.get(name)
        if identity and prior and prior != identity:
            receipt.setdefault('actorTransitions', []).append({'actor': name, 'from': prior, 'to': identity})
        if name == 'k6' and (state.get('restartCount', 0) or (identity and prior and identity != prior)):
            receipt['writerContinuity'] = 'UNMEASURED'
        image = state.get('imageID')
        if image and images.get(name) and images[name] != image:
            receipt.setdefault('actorTransitions', []).append({'actor': name, 'fromImage': images[name], 'toImage': image})
        if image:
            images[name] = image
        if identity:
            actors[name] = identity


def terminal_process(c, wanted, job, pod, final_job, final_pod):
    """Verify terminal execution and record lifetime changes under the same Job."""
    import native_load as n
    k.need(final_job['metadata']['uid'] == job['metadata']['uid'], 'NATIVE_LOAD_JOB_CHANGED')
    k.need(final_pod is not None, 'NATIVE_LOAD_TERMINAL_POD_MISSING', 'UNMEASURED')
    _, process = n._terminal(c, wanted, final_job, {'items':[final_pod]})
    # Both sides are server readbacks. Preserve the resources admission actually
    # assigned, including its canonical quantities and LimitRange defaults.
    observed = k.resource_budget.observed
    k.need(observed(pod['spec']) == observed(final_pod['spec']) and
           observed(job['spec']['template']['spec']) == observed(final_job['spec']['template']['spec']),
           'NATIVE_LOAD_RESOURCES_CHANGED')
    final_states = {s['name']: s for s in final_pod.get('status', {}).get('containerStatuses', [])}
    for name in ('k6', 'artifact-exporter'):
        state = final_states.get(name, {})
        k.need(state.get('containerID') and state.get('imageID'), 'NATIVE_LOAD_ACTOR_IDENTITY_UNMEASURED', 'UNMEASURED')
    history = {}
    observe_actors(history, pod)
    observe_actors(history, final_pod)
    process.update(history)
    exporter = final_states.get('artifact-exporter', {})
    k.need(exporter.get('state', {}).get('terminated', {}).get('exitCode') == 0,
           'NATIVE_LOAD_EXPORTER_FAILED', 'UNMEASURED')
    return process


def capture(kube, c, wanted, out, receipt, *, clock=time, failures=None, private_data=None):
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
            pod = row
            states = {s['name']: s for s in row.get('status', {}).get('containerStatuses', [])}
            observe_actors(receipt, row)
            k.write(out/'native-load.json',receipt)
            if private_data is not None and receipt.get('rosterPodUid') != receipt['podUid'] and 'running' in states.get('artifact-exporter', {}).get('state', {}):
                check_namespace()
                # Only stdin carries issued credentials. The receiver checks
                # its downward-API Pod UID and the exact DATA digest.
                raw = kube.call(['exec', '-i', row['metadata']['name'], '-c', 'artifact-exporter',
                                 '--', 'node', '/inputs/native-fixture-data.cjs', receipt['podUid']],
                                data=json.dumps(private_data, separators=(',', ':')).encode(),
                                namespace=ns, timeout=remaining())
                k.need(raw.strip() in (receipt['rosterSha256'], receipt['rosterSha256'].encode()),
                       'NATIVE_LOAD_ROSTER_CHANGED')
                receipt['rosterDelivered'] = True
                receipt['rosterPodUid'] = receipt['podUid']
                k.write(out/'native-load.json', receipt)
            if states.get('k6', {}).get('state', {}).get('terminated') is not None:
                break
        clock.sleep(min(.5, remaining()))
    k.need(private_data is None or receipt.get('rosterPodUid') == receipt['podUid'], 'NATIVE_LOAD_ROSTER_UNDELIVERED', 'UNMEASURED')
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
                   'NATIVE_LOAD_EXPORT_LIFETIME_UNMEASURED', 'UNMEASURED')
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
    current = pod_read()
    k.need(current is not None and current['metadata']['uid'] == pod_uid
           and k.controller(current) == k.controller(pod), 'NATIVE_LOAD_EXPORT_LIFETIME_UNMEASURED', 'UNMEASURED')
    k.need(k.resource_budget.observed(current['spec']) == k.resource_budget.observed(pod['spec']),
           'NATIVE_LOAD_RESOURCES_CHANGED')
    check_namespace()
    kube.call(command + ['ack', n.sha(raw)], namespace=ns, timeout=min(20, remaining()))
    kube.call(['wait', '--for=condition=complete', 'job/k6', '--timeout=%ds' % max(1, math.ceil(remaining()))],
              namespace=ns, timeout=remaining())
    final_job = kube.json(['get', 'job', 'k6'], namespace=ns, timeout=min(20, remaining()))
    # The owned Job census resolves declaration references under the existing
    # guard. A named Pod display can contain masked fields even at completion.
    final_pod = pod_read()
    process = terminal_process(c, wanted, job, current, final_job, final_pod)
    observe_actors(receipt, final_pod)
    check_namespace()
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
