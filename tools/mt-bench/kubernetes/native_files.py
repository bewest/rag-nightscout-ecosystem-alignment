"""One-shard configured driver: retain original bounded files through Pod exec.

An exporter holds the test Pod's emptyDir and can publish to a prebound retained volume.
The owned Pod stays until export acknowledgment or its finite Job deadline.
Raw CSV never traverses Kubernetes container logs (which may rotate).
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import kube_adapter as k
import scheduling
import workload_runtime

FILES = {'k6.log': 64 * 1024**2, 'k6-native.log': 64 * 1024**2,
         'k6-summary.json': 4 * 1024**2, 'file-limits.txt': 16384}


PUBLICATION_CLAIM = 'writer-publication'
TRACE_FILE = 'k6-scheduling.csv.gz'
TRACE_CHUNK_BYTES = 8 * 1024**2
# Retained 1k writes used 295–312 bytes per accepted line with a 27-byte
# marker. Allow the full 100-byte run marker and space for diagnostics.
BYTES_PER_WRITE = 512
EVENT_LOG_OVERHEAD = 64 * 1024


def publication_selection(selection):
    k.need(isinstance(selection, dict) and set(selection) == {'volumeName', 'storageClassName', 'storage'}
           and isinstance(selection['volumeName'], str) and k.NAME.fullmatch(selection['volumeName'])
           and isinstance(selection['storageClassName'], str)
           and (not selection['storageClassName'] or k.NAME.fullmatch(selection['storageClassName']))
           and isinstance(selection['storage'], str)
           and k.resource_budget.quantity(selection['storage'], False, k.need) > 0,
           'WRITER_PUBLICATION_SELECTION')
    return selection


def publication_claim(selection, namespace, run_id, pv):
    """Bind one already reserved, retained PV. Never request dynamic provisioning."""
    publication_selection(selection)
    spec = (pv or {}).get('spec', {})
    metadata = (pv or {}).get('metadata', {})
    ref = spec.get('claimRef') or {}
    k.need(metadata.get('name') == selection['volumeName'] and not metadata.get('deletionTimestamp')
           and (pv or {}).get('status', {}).get('phase') == 'Available'
           and spec.get('persistentVolumeReclaimPolicy') == 'Retain'
           and spec.get('volumeMode', 'Filesystem') == 'Filesystem'
           and spec.get('storageClassName', '') == selection['storageClassName']
           and ref.get('name') == PUBLICATION_CLAIM and ref.get('namespace') == namespace and not ref.get('uid')
           and k.resource_budget.quantity(spec.get('capacity', {}).get('storage', 0), False, k.need)
               >= k.resource_budget.quantity(selection['storage'], False, k.need),
           'WRITER_PUBLICATION_RETAINED_VOLUME_REQUIRED')
    access = next((mode for mode in ('ReadWriteOnce', 'ReadWriteMany', 'ReadWriteOncePod')
                   if mode in spec.get('accessModes', [])), None)
    k.need(access, 'WRITER_PUBLICATION_WRITABLE_VOLUME_REQUIRED')
    return {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
            'metadata': {'namespace': namespace, 'name': PUBLICATION_CLAIM,
                         'labels': {'nightscout.org/run-id': run_id}},
            'spec': {**{key: selection[key] for key in ('volumeName', 'storageClassName')},
                     'accessModes': [access], 'volumeMode': 'Filesystem',
                     'resources': {'requests': {'storage': selection['storage']}}}}


def decorate(c, job, secret, receipt, script, *, exporter_resources, shell_contract):
    import native_load as n
    import driver_accounting as driver
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
    maximum = cfg['maxTraceBytes']
    trace_limit = maximum // 512 * 512
    k.need(trace_limit > 0, 'NATIVE_LOAD_TRACE_BOUND')
    scenarios = driver.expected_plans(manifest)[0]['scenarios']
    writes = sum(row['plannedMaximum'] for name, row in scenarios.items() if name.startswith('w_'))
    estimated_bytes = writes * BYTES_PER_WRITE + EVENT_LOG_OVERHEAD
    mib = 1024**2
    event_limit = max(min(FILES['k6.log'], trace_limit), ((estimated_bytes + mib - 1) // mib) * mib)
    # The shell has one file-size limit for both outputs. The exporter checks
    # each file independently; /proc proves the image's 512-byte block limit.
    limit = max(trace_limit, event_limit)
    wrapper = (k.M7 / driver.SCRIPT).read_bytes()
    files = dict(FILES)
    files['k6.log'] = event_limit
    if cfg['observer'] == 'scheduling-v1':
        files[TRACE_FILE] = maximum
    config = dict(runId=receipt['runId'], files=files, seconds=receipt['activeDeadlineSeconds'],
                  rangeBytes=TRACE_CHUNK_BYTES)
    publication = (c.get('nativeLoad') or {}).get('writerPublication')
    if publication is not None:
        receipt['writerPublication'] = publication_selection(publication)
        config['writerPublication'] = True
        secret['stringData']['native-publication.cjs'] = (k.HERE / 'native-publication.cjs').read_text()
    secret['stringData'] = {**secret['stringData'],
                            'workload.js': script.decode(), driver.SCRIPT: wrapper.decode(),
                            'native-artifacts.cjs': (k.HERE / 'native-artifacts.cjs').read_text(),
                            'export.json': json.dumps(config)}
    env = {row['name']: row['value'] for row in container['env']}
    secret['stringData']['launch.env'] = 'export RUN_START='+env.pop('RUN_START')+'\n'
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
    if publication is not None:
        pod['volumes'].append({'name': PUBLICATION_CLAIM, 'persistentVolumeClaim': {'claimName': PUBLICATION_CLAIM}})
        exporter['volumeMounts'].append({'name': PUBLICATION_CLAIM, 'mountPath': '/publication'})
        exporter['env'] = [{'name': 'NS_PUBLICATION_ROOT', 'value': '/publication'},
                           {'name': 'NS_PUBLICATION_POD_UID', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.uid'}}}]
    pod['containers'].append(exporter)
    # This is disposable local Pod storage; requests/limits and the full new Pod
    # must still enter the operating owner's fit/quota admission.
    pod['volumes'].append({'name': 'artifacts', 'emptyDir': {'sizeLimit': str(sum(files.values()) + 4096)}})
    receipt.update(captureMode='owned-exec-files', files=files, fileLimitBytes=limit, rangeBytes=TRACE_CHUNK_BYTES,
                   shellContract=shell_contract, jobSha256=k.hashed(job), driverManifest=manifest)
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


def artifact_source(pod):
    states = {row['name']: row for row in pod.get('status', {}).get('containerStatuses', [])}
    def identity(name):
        row = states.get(name, {})
        return {'containerId': row.get('containerID'), 'imageId': row.get('imageID'),
                'restartCount': row.get('restartCount')}
    return {'podUid': pod['metadata']['uid'], 'writer': identity('k6'),
            'exporter': identity('artifact-exporter')}


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
    process.update(history, artifactSource=artifact_source(pod))
    exporter = final_states.get('artifact-exporter', {})
    k.need(exporter.get('state', {}).get('terminated', {}).get('exitCode') == 0,
           'NATIVE_LOAD_EXPORTER_FAILED', 'UNMEASURED')
    return process


def copy_artifact(kube, command, target, size, namespace, remaining, range_bytes):
    """Transfer large artifacts in bounded ranges when the exporter supports them."""
    import native_load as n
    if range_bytes is None or (target.name != TRACE_FILE and size <= range_bytes):
        data = kube.call(command + ['read', target.name], data=b'', namespace=namespace, timeout=min(120, remaining()))
        if isinstance(data, str):
            data = data.encode()
        k.need(isinstance(data, bytes) and len(data) == size, 'NATIVE_LOAD_ARTIFACT_BOUND', 'UNMEASURED')
        n.private(target, data)
        return
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.' + target.name + '.') as stream:
        for offset in range(0, size, range_bytes):
            length = min(range_bytes, size - offset)
            data = kube.call(command + ['read-range', target.name, str(offset), str(length)],
                             data=b'', namespace=namespace, timeout=min(120, remaining()),
                             output_limit=length)
            k.need(isinstance(data, bytes) and len(data) == length, 'NATIVE_LOAD_ARTIFACT_BOUND', 'UNMEASURED')
            stream.write(data)
        stream.flush()
        # Publish only a complete file, with the temporary file's private mode.
        os.link(stream.name, target)


def capture(kube, c, wanted, out, receipt, *, clock=time, failures=None, private_data=None):
    """Writer exit -> bounded exec read -> ack -> Job completion.

    No terminal-log artifact fallback, upload service or indefinitely waiting
    sidecar. The Job deadline also fences an interrupted controller's exporter.
    """
    import native_load as n
    import driver_accounting as driver
    out = Path(out)
    k.need(out.name == 'load', 'NATIVE_LOAD_CONFIGURED_OUTPUT_DIRECTORY')
    ns, uid = c['namespace'], receipt['namespaceUid']
    until = clock.monotonic() + min(receipt['activeDeadlineSeconds'], k.deadline(c))
    last_placement = None
    next_event_read = 0
    def remaining():
        if failures:
            raise failures[0]
        try:
            seconds = min(until - clock.monotonic(), k.deadline(c))
            k.need(seconds > 0, 'NATIVE_LOAD_EXPORT_DEADLINE', 'UNMEASURED')
        except k.Refused:
            if last_placement == 'Unschedulable':
                raise k.Refused('K8S_POD_UNSCHEDULABLE', 'UNMEASURED') from None
            raise
        return seconds
    def check_namespace():
        n._identity(c, kube.json(['get', 'namespace', ns], timeout=min(20, remaining())), uid)
    def pod_read():
        current = kube.json(['get', 'pods', '-l', 'job-name=k6'], namespace=ns, timeout=min(20, remaining()))
        k.need(len(current['items']) <= 1, 'NATIVE_LOAD_POD_CENSUS', 'UNMEASURED')
        return current['items'][0] if current['items'] else None
    job = kube.json(['get', 'job', 'k6'], namespace=ns, timeout=min(20, remaining()))
    k.owned(c, job)
    k.need(job['metadata']['uid'] == receipt['jobUid'], 'NATIVE_LOAD_JOB_CHANGED')
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
            pod = row
            placement = scheduling.outcome(row)
            retry_event = placement['placement'] == 'Unschedulable' and clock.monotonic() >= next_event_read
            if placement['placement'] != last_placement or retry_event:
                last_placement = placement['placement']
                if last_placement == 'Unschedulable':
                    try:
                        events = kube.json(['get','events','--field-selector','involvedObject.uid='+placement['uid']+',reason=FailedScheduling'],
                                           namespace=ns, timeout=min(5,remaining()))
                        placement['events'] = scheduling.failed_events(row, events)
                    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
                        placement['events'] = None
                    next_event_read = math.inf if placement['events'] else clock.monotonic()+5
                else:
                    next_event_read = 0
                k.write(out/'k6-scheduling.json', placement)
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
        # The manifest is written after the k6 child exits. Missing manifest is
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
           and set(meta.get('files', {})) == set(receipt['files']), 'NATIVE_LOAD_MANIFEST_BINDING')
    # Older scheduling exporters already supported ranges. Legacy summary-only
    # exporters must continue to use the single-read protocol.
    range_bytes = TRACE_CHUNK_BYTES if TRACE_FILE in receipt['files'] or receipt.get('rangeBytes') == TRACE_CHUNK_BYTES else None
    for filename, maximum in receipt['files'].items():
        expected = meta['files'][filename]
        k.need(type(expected.get('bytes')) is int and 0 < expected['bytes'] <= maximum,
               'NATIVE_LOAD_ARTIFACT_BOUND', 'UNMEASURED')
        copy_artifact(kube, command, out / filename, expected['bytes'], ns, remaining, range_bytes)
    limits = (out / 'file-limits.txt').read_text()
    match = re.search(r'^Max file size\s+([0-9]+)\s+([0-9]+)\s+bytes\s*$', limits, re.M)
    k.need(match and int(match[1]) == int(match[2]) == receipt['fileLimitBytes'], 'NATIVE_LOAD_FILE_LIMIT_UNPROVEN')
    current = pod_read()
    if current is None or current['metadata']['uid'] != pod_uid:
        receipt.update(writerContinuity='UNMEASURED', artifactSource='UNMEASURED')
        k.write(out/'native-load.json', receipt)
        raise k.Refused('K8S_NATIVE_LOAD_EXPORT_LIFETIME_UNMEASURED', 'UNMEASURED')
    k.owned(c, current)
    k.need(k.controller(current) == k.controller(pod), 'NATIVE_LOAD_POD_CONTROLLER')
    k.need(k.resource_budget.observed(current['spec']) == k.resource_budget.observed(pod['spec']),
           'NATIVE_LOAD_RESOURCES_CHANGED')
    source = artifact_source(pod)
    after_export = artifact_source(current)
    if not source['writer']['containerId'] or source['writer'] != after_export['writer']:
        receipt.update(writerContinuity='UNMEASURED', artifactSource='UNMEASURED')
        k.write(out/'native-load.json', receipt)
        raise k.Refused('K8S_NATIVE_LOAD_EXPORT_LIFETIME_UNMEASURED', 'UNMEASURED')
    if source['exporter'] != after_export['exporter']:
        source['exporter'] = {'before': source['exporter'], 'after': after_export['exporter']}
    receipt['artifactSource'] = source
    k.write(out/'native-load.json', receipt)
    check_namespace()
    kube.call(command + ['ack', receipt['runId']], namespace=ns, timeout=min(20, remaining()))
    kube.call(['wait', '--for=condition=complete', 'job/k6', '--timeout=%ds' % max(1, math.ceil(remaining()))],
              namespace=ns, timeout=remaining())
    final_job = kube.json(['get', 'job', 'k6'], namespace=ns, timeout=min(20, remaining()))
    # The owned Job census resolves declaration references under the existing
    # guard. A named Pod display can contain masked fields even at completion.
    final_pod = pod_read()
    process = terminal_process(c, wanted, job, current, final_job, final_pod)
    process['artifactSource'] = source
    observe_actors(receipt, final_pod)
    receipt['process'] = process
    k.write(out/'native-load.json', receipt)
    check_namespace()
    k.write(out / 'k6-process.json', process)
    k.need(process['complete'] and meta.get('exitCode') == 0, 'NATIVE_LOAD_JOB_FAILED', 'UNMEASURED')
    manifest = receipt['driverManifest']
    k.write(out / 'driver-plans.json', {'plans': driver.expected_plans(manifest), 'transport': 'in-cluster-k6-service',
                                      'manifest': manifest, 'pooledPercentiles': 'UNMEASURED'})
    accounting = driver.retain(out.parent, manifest)
    k.write(out / 'driver-accounting.json', accounting)
    receipt.update(capture='CAPTURED', process=process)
    k.write(out / 'native-load.json', receipt)
    return receipt
