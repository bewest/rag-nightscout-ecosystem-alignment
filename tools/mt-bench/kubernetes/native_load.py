"""Bounded k6 Job evidence transport, reusing lane K's rendered Job and Kube client.

This joins machine-readable k6 evidence, not the clinical/storage/catch-up
collectors. The caller retains namespace/trust cleanup and the full outcome gate.
No actor is created until the exact workload and transport pass preflight.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re

import kube_adapter as k
import workload_runtime

KIND = 'm7-k6-summary-chunk-v1'
MAX_SUMMARY_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_INPUT_BYTES = 900 * 1024  # below the Kubernetes Secret limit, including JSON overhead
CHUNK_CHARS = 8192


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def job_spec_matches(wanted, actual):
    value=copy.deepcopy(actual)
    value['template']['spec']=k.resource_budget.readback_projection(
        wanted['template']['spec'],value['template']['spec'],k.need)
    return k.subset(wanted,value)


def private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)


def selection(c):
    """Unsupported evidence modes refuse before even a Kubernetes read.

    scheduling-v1 uses native_files' bounded raw CSV channel; summary output
    cannot substitute for its per-operation samples. Multiple shards still
    require a separate custody/accounting join and explicitly refuse.
    """
    w = workload_runtime.validate(c['workload'], k.need, workload_runtime.driver_count(c, k.need))
    k.need(w.get('driverShards', 1) == 1, 'NATIVE_LOAD_UNSUPPORTED:driverShards', 'UNMEASURED')
    return w


def summary_script(script, runid):
    """Append an output adapter; preserve every workload function byte-for-byte.

    handleSummary receives k6's own counters/trends. Flatten values into the
    legacy --summary-export shape expected by the unchanged M7 reducers. Never
    include setup_data (JWTs) in the transport. Chunk framing detects truncation,
    duplication, reordering and cross-run/script substitution before import.
    """
    text = script.decode('utf-8')
    k.need('handleSummary' not in text, 'NATIVE_LOAD_SUMMARY_EXPORT_CONFLICT')
    identity = sha(script)
    trailer = r'''
export function handleSummary(data) {
  const metrics = {};
  for (const [name, row] of Object.entries(data.metrics)) {
    metrics[name] = { ...row.values };
    if (row.thresholds) metrics[name].thresholds = Object.fromEntries(
      Object.entries(row.thresholds).map(([name, value]) => [name, !value.ok]));
  }
  const text = JSON.stringify({metrics});
  if (text.length > 4194304) throw Error('K8S_NATIVE_LOAD_SUMMARY_BOUND');
  const total = Math.ceil(text.length / 8192), rows = [];
  for (let index = 0; index < total; index++) rows.push(JSON.stringify({
    kind: 'm7-k6-summary-chunk-v1', runId: RUN_MARKER, sourceSha256: SOURCE_HASH,
    index, total, text: text.slice(index * 8192, (index + 1) * 8192)
  }));
  return {stdout: rows.join('\n') + '\n'};
}
'''.replace('RUN_MARKER', json.dumps(runid)).replace('SOURCE_HASH', json.dumps(identity))
    return script + trailer.encode()


def decode(raw, runid, source_sha):
    """Return exact event lines and a complete summary; never infer missing data."""
    k.need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_LOG_BYTES,
           'NATIVE_LOAD_LOG_BOUND', 'UNMEASURED')
    try:
        lines = raw.decode('utf-8').splitlines(keepends=True)
    except UnicodeError:
        raise k.Refused('K8S_NATIVE_LOAD_LOG_ENCODING', 'UNMEASURED') from None
    frames, events = [], []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            # Native k6 diagnostics remain retained; they cannot become summary.
            events.append(line)
            continue
        if not isinstance(value, dict) or value.get('kind') != KIND:
            events.append(line)
            continue
        k.need(set(value) == {'kind', 'runId', 'sourceSha256', 'index', 'total', 'text'}
               and value['runId'] == runid and value['sourceSha256'] == source_sha,
               'NATIVE_LOAD_SUMMARY_BINDING')
        k.need(type(value['index']) is int and type(value['total']) is int
               and 1 <= value['total'] <= 512 and value['index'] == len(frames)
               and 0 <= value['index'] < value['total']
               and isinstance(value['text'], str) and 0 < len(value['text']) <= CHUNK_CHARS,
               'NATIVE_LOAD_SUMMARY_FRAMING', 'UNMEASURED')
        frames.append(value)
    k.need(frames and all(row['total'] == len(frames) for row in frames),
           'NATIVE_LOAD_SUMMARY_INCOMPLETE', 'UNMEASURED')
    packed = ''.join(row['text'] for row in frames).encode()
    k.need(len(packed) <= MAX_SUMMARY_BYTES, 'NATIVE_LOAD_SUMMARY_BOUND', 'UNMEASURED')
    try:
        summary = json.loads(packed)
    except ValueError:
        raise k.Refused('K8S_NATIVE_LOAD_SUMMARY_INVALID', 'UNMEASURED') from None
    k.need(isinstance(summary, dict) and set(summary) == {'metrics'}
           and isinstance(summary['metrics'], dict) and summary['metrics'],
           'NATIVE_LOAD_SUMMARY_INVALID', 'UNMEASURED')
    return ''.join(events).encode(), summary


def package(c, job, script, tenants, *, runid, seconds, run_start_ms, setup_seconds,
            exporter_resources=None, shell_contract=None, planning=False):
    """Adapt the existing lane K Job. The caller must account the returned Pod.

    This does not render a second deployment or alter application resources.
    Job, image, placement, resource, init-ordering and namespace RBAC come from
    lane K's renderer. Service addressing replaces only the load actor's URL.
    """
    w = selection(c)
    k.need(k.NAME.fullmatch(c['namespace']) and c['namespace'].startswith('ns-synth-')
           and re.fullmatch(r'[a-z0-9-]{1,100}', runid), 'NATIVE_LOAD_SCOPE')
    k.need(type(seconds) is int and seconds > 0 and type(run_start_ms) is int
           and run_start_ms > 0 and type(setup_seconds) is int and setup_seconds > 0,
           'NATIVE_LOAD_WINDOW')
    k.need((planning or seconds <= k.deadline(c)) and setup_seconds < seconds, 'NATIVE_LOAD_WORK_DEADLINE')
    k.need(planning or isinstance(tenants, list) and len(tenants) == workload_runtime.driver_count(c, k.need)
           and len({t['id'] for t in tenants}) == len(tenants)
           and all(isinstance(t.get('host'), str) and t['host'].endswith('.test')
                   and isinstance(t.get('token'), str) and t['token'] for t in tenants),
           'SYNTHETIC_TENANTS_REQUIRED')
    if not planning:
        k.evaluator_progress.validate_ids([t['id'] for t in tenants])
    k.need(job.get('kind') == 'Job' and job.get('apiVersion') == 'batch/v1'
           and job['metadata']['name'] == 'k6' and job['metadata']['namespace'] == c['namespace'],
           'NATIVE_LOAD_JOB_SCOPE')
    k.owned(c, job)
    pod = job['spec']['template']['spec']
    k.need(job['spec'].get('backoffLimit') == 0 and job['spec'].get('parallelism', 1) == 1
           and job['spec'].get('completions', 1) == 1 and not job['spec'].get('suspend')
           and pod.get('restartPolicy') == 'Never' and pod.get('automountServiceAccountToken') is False
           and not any(pod.get(key) for key in ('hostNetwork', 'hostPID', 'hostIPC'))
           and len(pod['containers']) == 1 and pod['containers'][0]['name'] == 'k6',
           'NATIVE_LOAD_JOB_REPLAY_OR_AUTHORITY')
    k.need(job['spec']['template']['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'],
           'POD_TEMPLATE_OWNERSHIP')
    volumes = {v['name']: v for v in pod.get('volumes', [])}
    k.need(len(volumes) == len(pod.get('volumes', [])) and set(volumes) <= {'inputs', 'tmp', 'kube-api'}
           and volumes.get('inputs', {}).get('secret', {}).get('secretName') == 'ns-k6-inputs'
           and 'emptyDir' in volumes.get('tmp', {}), 'NATIVE_LOAD_VOLUME_AUTHORITY')
    init = pod.get('initContainers', [])
    k.need(len(init) <= 1 and all(actor['name'] == 'wait-for-jobs'
           and actor['image'] == c['pins']['appImage'] and actor.get('restartPolicy') != 'Always'
           for actor in init), 'NATIVE_LOAD_INIT_AUTHORITY')
    container = pod['containers'][0]
    k.need(re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', container.get('image', ''))
           and not container.get('command'), 'NATIVE_LOAD_IMAGE_OR_ENTRYPOINT')
    context = container.get('securityContext', {})
    k.need(context.get('runAsNonRoot') is True and context.get('readOnlyRootFilesystem') is True
           and context.get('allowPrivilegeEscalation') is False
           and context.get('capabilities', {}).get('drop') == ['ALL'], 'NATIVE_LOAD_SECURITY_CONTEXT')
    for actor in pod['containers'] + pod.get('initContainers', []):
        k.resource_budget.validate_container(actor, k.resource_accounting(c), k.need)
    original_env = {e['name']: e.get('value') for e in container.get('env', [])}
    base = original_env.get('BASE_URL', '')
    k.need(re.fullmatch(r'http://edge:[1-9][0-9]{0,4}', base) is not None
           and int(base.rsplit(':', 1)[1]) <= 65535, 'NATIVE_LOAD_SERVICE_ADDRESS')
    # No environment from the workstation is copied to the Pod.
    env = workload_runtime.environment(w, {}, k.need)
    env.update(BASE_URL=base, TENANTS_FILE='/inputs/tenants.json', RUN_ID=runid,
               RUN_START=str(run_start_ms), DURATION=str(w['loadSeconds']), ACCEL='1',
               HOT_FACTOR=str(w.get('hotFactor', 1)), JWT_SETUP_CONCURRENCY=str(w.get('jwtSetupConcurrency', 1)),
               M7_SETUP_SECONDS=str(setup_seconds),
               M7_SETUP_UNTIL_MS=str(run_start_ms + setup_seconds * 1000),
               SHAPES=','.join(workload_runtime.SHAPES))
    k.need(all(name in ('BASE_URL', 'TENANTS_FILE', 'RUN_ID') or env.get(name) == value
               for name, value in original_env.items()), 'NATIVE_LOAD_ENVIRONMENT_CONFLICT')
    rendered = copy.deepcopy(job)
    # Test traffic must not inherit the operator label's private control-plane
    # NetworkPolicy access from the original lane K Job template.
    rendered['metadata']['labels']['app.kubernetes.io/component']='load'
    rendered['spec']['template']['metadata']['labels']['app.kubernetes.io/component']='load'
    rendered['spec']['activeDeadlineSeconds'] = seconds
    # Automatic Job TTL would remove the evidence before an interrupted
    # controller collects it. Namespace/trust cleanup belongs to run_cleanup.
    rendered['spec'].pop('ttlSecondsAfterFinished', None)
    selected = rendered['spec']['template']['spec']['containers'][0]
    selected['args'] = ['run', '--quiet', '--no-usage-report', '--address=127.0.0.1:0',
                        '--log-format=json', '--log-output=stdout', '/inputs/workload.js']
    selected['env'] = [{'name': name, 'value': env[name]} for name in sorted(env)]
    script = bytes(script)
    wrapped = summary_script(script, runid)
    tenant_text = json.dumps(tenants, separators=(',', ':'))
    inputs = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque', 'immutable': True,
              'metadata': {'name': 'ns-k6-inputs', 'namespace': c['namespace'],
                           'labels': {c['ownerLabel']: c['runId']}},
              'stringData': {'workload.js': wrapped.decode(), 'tenants.json': tenant_text}}
    k.need(len(json.dumps(inputs).encode()) <= MAX_INPUT_BYTES,
           'NATIVE_LOAD_INPUT_SECRET_BOUND', 'UNMEASURED')
    receipt = {'kind': 'm7-kubernetes-k6-job-v1', 'runId': runid, 'fixtureRunId': c['runId'],
               'namespace': c['namespace'], 'pins': c['pins'], 'sourceSha256': sha(script),
               'adaptedSha256': sha(wrapped), 'rosterSha256': sha(tenant_text.encode()),
               'jobSha256': k.hashed(rendered), 'workload': w,
               'activeDeadlineSeconds': seconds, 'transport': 'in-cluster-k6-service',
               'outcomeGate': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED',
               'remaining': ['local probe/controller/SQL/clinical/frame/native-catch-up collectors',
                             'declared load-actor census and resource-fit integration',
                             'all-writer post-stop WAL/ACK coverage UNMEASURED']}
    if 'driverPlan' in w:
        import native_files
        return native_files.decorate(c, rendered, inputs, receipt, script,
                                     exporter_resources=exporter_resources, shell_contract=shell_contract)
    return rendered, inputs, receipt


def _identity(c, ns, uid=None):
    k.need(ns['metadata']['name'] == c['namespace']
           and ns['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId']
           and not ns['metadata'].get('deletionTimestamp')
           and (uid is None or ns['metadata']['uid'] == uid), 'NATIVE_LOAD_NAMESPACE_CHANGED')
    return ns['metadata']['uid']


def _terminal(c, wanted, job, pods):
    k.owned(c, job)
    k.need(job_spec_matches(wanted['spec'], job['spec']), 'NATIVE_LOAD_JOB_CHANGED')
    rows = pods['items']
    k.need(len(rows) == 1, 'NATIVE_LOAD_POD_CENSUS', 'UNMEASURED')
    pod = rows[0]
    k.owned(c, pod)
    k.need(k.subset(wanted['spec']['template']['metadata']['labels'],pod['metadata'].get('labels',{})),
           'NATIVE_LOAD_POD_LABELS_CHANGED')
    ref = k.controller(pod)
    k.need(ref['kind'] == 'Job' and ref['name'] == 'k6' and ref['uid'] == job['metadata']['uid'],
           'NATIVE_LOAD_POD_CONTROLLER')
    actual, _ = k.admission_projection(wanted['spec']['template']['spec'], pod['spec'])
    k.need(k.subset(wanted['spec']['template']['spec'], actual), 'NATIVE_LOAD_POD_CHANGED')
    terminal = k.job_terminal(job)
    states = {r['name']: r for r in pod.get('status', {}).get('containerStatuses', [])}
    ended = states.get('k6', {}).get('state', {}).get('terminated', {})
    complete = bool(terminal and terminal['condition'] == 'Complete'
                    and pod.get('status', {}).get('phase') == 'Succeeded'
                    and states.get('k6', {}).get('restartCount') == 0
                    and states.get('k6', {}).get('containerID') and states.get('k6', {}).get('imageID')
                    and type(ended.get('exitCode')) is int and ended['exitCode'] == 0)
    return pod, {'jobUid': job['metadata']['uid'], 'podUid': pod['metadata']['uid'],
                 'containerId': states.get('k6', {}).get('containerID'),
                 'imageId': states.get('k6', {}).get('imageID'),
                 'terminal': terminal, 'exitCode': ended.get('exitCode'),
                 'startedAt': ended.get('startedAt'), 'finishedAt': ended.get('finishedAt'),
                 'complete': complete}


def run(kube, c, job, script, tenants, out, *, predeclared=None, failures=None, **options):
    """Use fanout.Kube's existing call/json interface; no parallel orchestrator.

    The caller owns admission, init Job dependencies, readiness and cleanup.
    Only create is used: an existing Job/Secret is an explicit refusal, never
    an apply/replay. Job deadlines bound traffic if the workstation disappears.
    """
    if failures:
        raise failures[0]
    wanted, secret, receipt = package(c, job, script, tenants, **options)
    out = Path(out)
    k.need(out.is_dir() and not any((out / name).exists() for name in
           ('native-load.json', 'k6-native.log', 'k6.log', 'k6-summary.json', 'k6-process.json')),
           'NATIVE_LOAD_OUTPUT_EXISTS')
    k.need('driverPlan' not in c['workload'] or out.name == 'load', 'NATIVE_LOAD_CONFIGURED_OUTPUT_DIRECTORY')
    k.write(out / 'native-load.json', receipt)
    ns = c['namespace']
    uid = _identity(c, kube.json(['get', 'namespace', ns]))
    receipt.update(namespaceUid=uid)
    k.write(out / 'native-load.json', receipt)
    def close_after_failure(error):
        if predeclared is None:
            return
        import native_join
        first=out/'native-first-failure.json'
        if not first.exists():
            k.write(first,{'code':str(error),'verdict':getattr(error,'verdict','UNMEASURED')})
        try:
            native_join.cancel(kube,c,receipt,out)
        except Exception as secondary:
            k.write(out/'native-cancel-failure.json',{'code':str(secondary),
                    'verdict':'UNMEASURED','writersStopped':'UNMEASURED','firstFailure':str(error)})
    # Preflight above has completed before these first actor mutations.
    if failures:
        raise failures[0]
    kube.call(['create', '-f', '-'], data=json.dumps(secret), namespace=ns)
    if predeclared is None:
        created = kube.call(['create', '-f', '-', '-o', 'json'], data=json.dumps(wanted), namespace=ns)
        created = json.loads(created)
    else:
        created = kube.json(['get', 'job', 'k6'], namespace=ns)
        expected = dict(wanted['spec'], suspend=True)
        k.need(created['metadata']['uid'] == predeclared['uid'] and
               job_spec_matches(expected, created['spec']), 'NATIVE_LOAD_PREDECLARATION_CHANGED')
        patch = [{'op':'test','path':'/metadata/uid','value':predeclared['uid']},
                 {'op':'test','path':'/spec/suspend','value':True},
                 {'op':'replace','path':'/spec/suspend','value':False}]
        receipt['jobUid']=predeclared['uid'];k.write(out/'native-load.json',receipt)
        if failures:
            raise failures[0]
        try:
            kube.call(['patch','job','k6','--type=json','-p',json.dumps(patch)], namespace=ns)
        except Exception as error:
            close_after_failure(error)
            raise
        created['spec']['suspend'] = False
    k.owned(c, created)
    k.need(created.get('kind') == 'Job' and created['metadata'].get('name') == 'k6'
           and isinstance(created['metadata'].get('uid'), str) and created['metadata']['uid']
           and job_spec_matches(wanted['spec'], created['spec']), 'NATIVE_LOAD_CREATE_IDENTITY')
    receipt['jobUid'] = created['metadata']['uid']
    k.write(out / 'native-load.json', receipt)
    if receipt.get('captureMode') == 'owned-exec-files':
        import native_files
        try:
            return native_files.capture(kube, c, wanted, out, receipt, failures=failures)
        except Exception as error:
            close_after_failure(error)
            raise
    seconds = options['seconds']
    wait_error = None
    try:
        kube.call(['wait', '--for=condition=complete', 'job/k6', '--timeout=%ds' % seconds],
                  namespace=ns, timeout=seconds + 10)
    except Exception as error:
        # Retain failed/partial native evidence before returning the refusal.
        wait_error = type(error).__name__
    job_readback = kube.json(['get', 'job', 'k6'], namespace=ns)
    k.need(job_readback['metadata']['uid'] == receipt['jobUid'], 'NATIVE_LOAD_ACTOR_REPLACED')
    pod, process = _terminal(c, wanted, job_readback,
                             kube.json(['get', 'pods', '-l', 'job-name=k6'], namespace=ns))
    process['waitError'] = wait_error
    k.write(out / 'k6-process.json', process)
    raw = kube.call(['logs', pod['metadata']['name'], '-c', 'k6'], namespace=ns)
    raw = raw.encode() if isinstance(raw, str) else raw
    # Raw response is retained before framing/semantic decoding.
    k.need(isinstance(raw, bytes) and len(raw) <= MAX_LOG_BYTES, 'NATIVE_LOAD_LOG_BOUND', 'UNMEASURED')
    private(out / 'k6-native.log', raw)
    _identity(c, kube.json(['get', 'namespace', ns]), uid)
    again = kube.json(['get', 'pod', pod['metadata']['name']], namespace=ns)
    k.need(again['metadata']['uid'] == process['podUid'] and k.controller(again) == k.controller(pod),
           'NATIVE_LOAD_POD_REPLACED')
    events, summary = decode(raw, receipt['runId'], receipt['sourceSha256'])
    private(out / 'k6.log', events)
    k.write(out / 'k6-summary.json', summary)
    receipt.update(process=process, eventsSha256=sha(events),
                   summarySha256=k.digest(out / 'k6-summary.json'), capture='CAPTURED')
    k.write(out / 'native-load.json', receipt)
    k.need(process['complete'] and wait_error is None, 'NATIVE_LOAD_JOB_FAILED', 'UNMEASURED')
    return receipt


def assess_join(d, out, c, objects, client):
    """Join only through the existing full assessor; Job completion is no pass.

    Integration must supply the unchanged probe/SQL/progress/catch-up evidence
    and its declared actor census. This function does not synthesize any of it.
    """
    import execute
    d, out = Path(d), Path(out)
    k.need(out == d / 'load', 'NATIVE_LOAD_ASSESSMENT_DIRECTORY')
    receipt = k.document(out / 'native-load.json')
    runid = (out / 'runid').read_text().strip()
    k.need(receipt.get('capture') == 'CAPTURED' and receipt['process']['complete'] is True
           and receipt['runId'] == runid == execute.stage_runid(c, 'load')
           and receipt['pins'] == c['pins'] and receipt['namespace'] == c['namespace']
           and receipt['fixtureRunId'] == c['runId'] and receipt['workload'] == c['workload']
           and receipt['namespaceUid'] == k.active_baseline(d)['namespace']['uid']
           and receipt['eventsSha256'] == k.digest(out / 'k6.log')
           and receipt['summarySha256'] == k.digest(out / 'k6-summary.json'),
           'NATIVE_LOAD_ASSESSMENT_BINDING')
    source = (d / 'workload.js').read_bytes()
    packet = k.document(d / 'packet.json')['workload']
    k.need(receipt['sourceSha256'] == sha(source) == packet['adaptedSha256'],
           'NATIVE_LOAD_ASSESSMENT_SCRIPT_CHANGED')
    if 'driverPlan' in c['workload']:
        import driver_vu_diagnostic as driver
        k.need(receipt.get('captureMode') == 'owned-exec-files'
               and receipt['driverWrapperSha256'] == k.digest(d / driver.SCRIPT) == packet['driverWrapperSha256']
               and receipt['artifactExporterSha256'] == k.digest(k.HERE / 'native-artifacts.cjs')
               and all(k.digest(out / name) == digest for name, digest in receipt['artifactSha256'].items()),
               'NATIVE_LOAD_ASSESSMENT_ARTIFACT_CHANGED')
    else:
        k.need(receipt['adaptedSha256'] == sha(summary_script(source, runid)),
               'NATIVE_LOAD_ASSESSMENT_SCRIPT_CHANGED')
    return execute.assess_stage(d, out, c, objects, client)
