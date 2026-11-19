#!/usr/bin/env python3
"""Kubernetes transport for the existing M7 synthetic workload and oracles.

No apply, cloud provisioning, image publication, or implicit current context.
Execution requires isolated synthetic custody and current finite admission.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from types import SimpleNamespace
import traceback
import contextlib
import contextvars
import math

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
M7 = HERE.parent / 'm7-joined'
sys.modules.setdefault('kube_adapter', sys.modules[__name__])
sys.path.insert(0, str(M7))
import candidate
import frozen
import discovery_counts
import evaluator_progress
import dependency_reuse
import probe
import viewer_plan
import workload
import workload_inputs
import resource_budget
import primer_storage
import edge_configuration
import application_topology

SHA = re.compile(r'[a-f0-9]{40}')
HEX = re.compile(r'[a-f0-9]{64}')
_OBSERVATION_DEADLINE = contextvars.ContextVar('k8s_observation_deadline', default=None)
NAME = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')
WORKLOADS = {'StatefulSet', 'Deployment', 'Job'}
PLURALS = {'StatefulSet': ('apps/v1', 'statefulsets'), 'Deployment': ('apps/v1', 'deployments'),
           'Job': ('batch/v1', 'jobs'), 'Service': ('v1', 'services'),
           'ConfigMap': ('v1', 'configmaps'), 'ServiceAccount': ('v1', 'serviceaccounts'),
           'NetworkPolicy': ('networking.k8s.io/v1', 'networkpolicies'),
           'Role': ('rbac.authorization.k8s.io/v1', 'roles'),
           'RoleBinding': ('rbac.authorization.k8s.io/v1', 'rolebindings'),
           'ResourceQuota': ('v1', 'resourcequotas'), 'LimitRange': ('v1', 'limitranges')}


class Refused(RuntimeError):
    def __init__(self, code, verdict='FAIL'):
        super().__init__(code)
        self.verdict = verdict


def need(ok, code, verdict='FAIL'):
    if not ok:
        raise Refused('K8S_' + code, verdict)


def document(path, *, max_bytes=32 * 1024 * 1024):
    p = Path(path)
    need(p.is_file() and not p.is_symlink() and (max_bytes is None or p.stat().st_size <= max_bytes), 'INPUT_FILE')
    return json.loads(p.read_text())


def write(path, value):
    p = Path(path)
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n'
    temp = p.with_name(p.name + '.partial-' + str(os.getpid()))
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(raw)
    os.replace(temp, p)


def digest(path):
    return dependency_reuse.file_sha(Path(path))


def hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def instrument():
    """Run identity for the harness: the alignment commit (decision `brittle-check-removal`).
    No file hashing; ``sha256`` is the digest of the commit id so existing pins keep their shape."""
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True, timeout=20).strip()
    return {'commit': head, 'sha256': hashlib.sha256(head.encode()).hexdigest()}


def timestamp(value):
    need(isinstance(value, str) and value.endswith('Z'), 'DEADLINE_FORMAT')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        raise Refused('K8S_DEADLINE_FORMAT')


def deadline(c, cleanup=False, now=None):
    until = timestamp(c['deadlines']['cleanupUntil' if cleanup else 'workUntil'])
    observation = None if cleanup else _OBSERVATION_DEADLINE.get()
    phase_clipped = observation is not None and observation < until
    if observation is not None:
        until = min(until, observation)
    remaining = until - (time.time() if now is None else now)
    need(remaining > 0, 'CLEANUP_DEADLINE' if cleanup else
         'OBSERVATION_DEADLINE' if phase_clipped else 'WORK_DEADLINE', 'UNMEASURED')
    return remaining


@contextlib.contextmanager
def observation_deadline(until):
    """A read-only phase can shorten, never extend, existing work custody."""
    previous = _OBSERVATION_DEADLINE.get()
    if until is not None:
        need(type(until) in (int, float) and math.isfinite(until), 'OBSERVATION_DEADLINE_INPUT')
        until = min(previous, until) if previous is not None else until
    else:
        until = previous
    token = _OBSERVATION_DEADLINE.set(until)
    try:
        yield
    finally:
        _OBSERVATION_DEADLINE.reset(token)


def manifests(value):
    if isinstance(value, list):
        result = []
        for item in value:
            result += manifests(item)
        return result
    if isinstance(value, dict) and value.get('kind') == 'List':
        return manifests(value['items'])
    if isinstance(value, dict) and 'apiVersion' in value and 'kind' in value:
        return [value]
    need(isinstance(value, dict), 'RENDER_SHAPE')
    return manifests(list(value.values()))


def key(obj):
    return obj['kind'] + '/' + obj['metadata']['name']


def template(obj):
    return obj['spec']['template']


def resource_accounting(c):
    return resource_budget.selection(c, need)


def replica_scope(obj):
    count = obj['spec'].get('replicas', 1)
    if obj['metadata']['name'] == 'cohort':
        need(obj['kind'] == 'StatefulSet' and count == 1, 'ONE_COHORT_REPLICA')
    else:
        # Role selection and the Pod census still require one Pod per workload.
        # This is an instrument capability, not a shared-socket cohort rule.
        need(count == 1, 'WORKLOAD_REPLICA_CENSUS_UNSUPPORTED:' + key(obj))


def subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(subset(a, b) for a, b in zip(expected, actual))
    return type(expected) is type(actual) and expected == actual


def validate(c, inventory, rendered, now=None, cleanup=False):
    need(c.get('version') == 1 and NAME.fullmatch(c.get('runId', '')) and NAME.fullmatch(c.get('namespace', '')), 'CONFIG')
    need(isinstance(c.get('context'), str) and c['context'] and not c['context'].startswith('-'), 'CONTEXT_REQUIRED')
    need(isinstance(c.get('ownerLabel'), str) and '/' in c['ownerLabel'], 'OWNER_LABEL')
    p = c['pins']
    need(all(SHA.fullmatch(p['pair'].get(k, '')) for k in ('core', 'deploy')) and SHA.fullmatch(p.get('bindingCommit', '')), 'SOURCE_PIN')
    need(all(HEX.fullmatch(p.get(k, '')) for k in ('renderSha256', 'inventorySha256', 'instrument')), 'INPUT_PIN')
    need(re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', p.get('appImage', '')) and re.fullmatch(r'sha256:[a-f0-9]{64}', p.get('appImageId', '')), 'PULLABLE_IMAGE_REQUIRED')
    # Inventory is a separate renderer output, never a source acceptance receipt.
    need(inventory.get('sourceCommit') == p['pair']['core'] and inventory.get('imageDeployCommit') == p['pair']['deploy'], 'SOURCE_CHANGED')
    need(inventory.get('bindingIdentity') == p['bindingCommit'], 'BINDING_CHANGED')
    need(inventory.get('runId') == c['runId'], 'INVENTORY_RUN_CHANGED')
    need(inventory.get('namespace', c['namespace']) == c['namespace'] and inventory.get('ownership', {}).get('label', {c['ownerLabel']: c['runId']}) == {c['ownerLabel']: c['runId']}, 'INVENTORY_OWNERSHIP')
    accounting = resource_accounting(c)
    need(resource_accounting(inventory) == accounting, 'RESOURCE_ACCOUNTING_MISMATCH')
    need(inventory.get('prefix') == 'nsdemo', 'SOURCE_SCHEMA_UNSUPPORTED')
    need(timestamp(c['deadlines']['workUntil']) < timestamp(c['deadlines']['cleanupUntil']) <= timestamp(c['deadlines']['workUntil']) + workload_inputs.MAX_SECONDS, 'CLEANUP_WINDOW')
    deadline(c, cleanup=cleanup, now=now)
    need(isinstance(c.get('roles'), dict) and {'postgres', 'api', 'realtime', 'evaluator'} <= set(c['roles']), 'ROLE_ROSTER')
    if 'workload' in c:
        from workload_runtime import driver_count, validate as validate_workload
        validate_workload(c['workload'], need, driver_count(c, need))
        need('probeLedger' not in c['workload'] or c.get('tier','discovery')=='discovery', 'PROBE_LEDGER_DISCOVERY_ONLY')
        need('evaluatorProgressBudget' not in c['workload'] or c.get('tier','discovery')=='discovery', 'EVALUATOR_PROGRESS_BUDGET_DISCOVERY_ONLY')
    if 'dataPrimerSeconds' in c:
        need(workload_inputs.seconds(c['dataPrimerSeconds']), 'DATA_PRIMER_WINDOW')
    objs = manifests(rendered)
    primer_storage.check_render(c, objs)
    if 'edgeConfiguration' in inventory or 'edgeConfiguration' in c:
        need(isinstance(c.get('edgeConfiguration'),dict),'EDGE_CONFIGURATION_CHANGED')
        edge=edge_configuration.check({'edge':c['edgeConfiguration'].get('requested')},inventory,objs,need)
        need(c.get('edgeConfiguration')==edge,'EDGE_CONFIGURATION_CHANGED')
    by_key = {key(x): x for x in objs}
    need(len(by_key) == len(objs), 'DUPLICATE_RESOURCE')
    import native_join
    native_join.validate(c, inventory, by_key)
    application_topology.validate(c, inventory, by_key, need)
    ns = by_key.get('Namespace/' + c['namespace'])
    need(ns is not None and ns['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'], 'NAMESPACE_OWNERSHIP')
    for obj in objs:
        if obj['kind'] == 'Namespace':
            continue
        # Cluster-scoped Vault auth is Lane E custody, never our cleanup target.
        if obj['kind'] not in PLURALS:
            continue
        need(obj['metadata'].get('namespace') == c['namespace'], 'FOREIGN_NAMESPACE')
        need(obj['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'], 'RESOURCE_OWNERSHIP')
        if obj['kind'] in WORKLOADS:
            t = template(obj)
            need(t['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'], 'POD_TEMPLATE_OWNERSHIP')
            replica_scope(obj)
            need(not t['spec'].get('resources'), 'POD_LEVEL_RESOURCE_ACCOUNTING_UNSUPPORTED')
            for container in t['spec'].get('containers', []) + t['spec'].get('initContainers', []):
                resource_budget.validate_container(container, accounting, need)
    need(workload_inputs.tenants(c.get('tenants', 2)) and c.get('tenants', 2) >= 2, 'DIAGNOSTIC_TENANT_ROSTER')
    if 'Job/verification' in by_key:
        actors = template(by_key['Job/primer'])['spec'].get('initContainers', [])
        primer = [actor for actor in actors if actor['name'] == 'primer']
        need(len(primer) == 1 and primer[0].get('args') == ['--tenant-count', str(c.get('tenants', 2))],
             'DIAGNOSTIC_TENANTS_CHANGED')
    elif 'seed' not in inventory and c.get('tenants', 2) != 2:
        count = c['tenants']
        provision = by_key.get('Job/provision')
        need(workload_inputs.tenants(count) and count >= 2 and provision is not None, 'DIAGNOSTIC_TENANT_ROSTER')
        bootstrap = [x for x in template(provision)['spec'].get('initContainers', []) if x['name'] == 'bootstrap']
        need(len(bootstrap) == 1 and
             [e.get('value') for e in bootstrap[0].get('env', []) if e['name'] == 'NS_DEMO_TENANTS'] == [str(count)],
             'DIAGNOSTIC_TENANTS_CHANGED')
    for role, selection in c['roles'].items():
        obj = by_key.get(selection.get('workload'))
        need(obj is not None and obj['kind'] in WORKLOADS, 'ROLE_WORKLOAD:' + role)
        matches = [x for x in template(obj)['spec']['containers'] if x['name'] == selection.get('container')]
        need(len(matches) == 1, 'ROLE_CONTAINER:' + role)
        if role in ('api', 'evaluator', 'realtime'):
            need(matches[0]['image'] == p['appImage'], 'IMAGE_CHANGED')
    need(c.get('storageMode') in ('disposable', 'existing-claim'), 'STORAGE_PROFILE')
    need(inventory.get('storage', {}).get('mode', c['storageMode']) == c['storageMode'], 'STORAGE_PROFILE_CHANGED')
    need(not any(x['kind'] == 'PersistentVolumeClaim' or x['kind'] == 'Service' and x['spec'].get('type', 'ClusterIP') != 'ClusterIP' for x in objs), 'NEW_BILLABLE_RESOURCE')
    for actor in ('driver', 'observer'):
        item = c.get(actor, {})
        need(isinstance(item.get('hostId'), str) and item['hostId'] and item.get('sharedHost') is True, 'ACTOR_ATTRIBUTION')
        need(all(type(item.get('resources', {}).get(k)) is int and item['resources'][k] > 0 for k in ('millicpus', 'memoryBytes')), 'ACTOR_BUDGET')
    selected = p.get('candidate', {})
    helper = selected.get('runtimeBootstrapHelper')
    visible_helper = by_key.get('ConfigMap/' + BOOTSTRAP_MAP)
    need(bool(visible_helper) == bool(helper), 'BOOTSTRAP_HELPER_SCOPE')
    if helper:
        annotations = visible_helper['metadata'].get('annotations', {})
        need(selected.get('sourceAcceptance') == 'PENDING' and
             helper.get('baseSha256') == frozen.BOOTSTRAP_ORIGINAL and
             all(helper.get(key) == val for key, val in frozen.BOOTSTRAP_HELPER.items()) and
             selected.get('imageSourceAcceptance') in ('PASS', 'PENDING') and
             all(annotations.get(key) == val for key, val in frozen.HELPER_ANNOTATIONS.items()) and
             hashlib.sha256(visible_helper['data']['bootstrap.js'].encode()).hexdigest() == helper['sha256'],
             'BOOTSTRAP_HELPER_SCOPE')
    if 'seed' not in inventory:
        candidate.pins(sys.modules[__name__], c, inventory, by_key)
    return by_key


class Client:
    def __init__(self, c, run=subprocess.run):
        self.c, self.run = c, run

    def call(self, args, *, data=None, read=True, cleanup=False, output_limit=32*1024*1024,
             response_sink=None, timeout=None, rows=None):
        c = self.c
        deadline(c, cleanup)
        prefix = [c['readonlyGuard']] if read else []
        # The existing guard accepts the literal tool name. Select the pinned
        # compatible binary through PATH rather than bypassing that guard.
        binary = 'kubectl' if read else c['kubectl']
        read_seconds = getattr(self, 'request_seconds', None)
        limit = min(timeout if timeout is not None else read_seconds or 20, deadline(c, cleanup))
        if read_seconds is not None and rows is None:
            limit = min(limit, read_seconds)
        request_timeout = str(max(1, math.ceil(1000 * limit)))+'ms' if rows or read_seconds else '15s'
        argv = prefix + [binary, '--context', c['context'], '--namespace', c['namespace'], '--request-timeout='+request_timeout, *args]
        env = dict(os.environ, PATH=str(Path(c['kubectl']).parent) + os.pathsep + os.environ.get('PATH', ''), RO_ALLOW_SENSITIVE='1')
        env.pop('RO_OWNED_WORKER_VIEW', None)
        try:
            if rows and self.run is subprocess.run:
                result = rows.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=limit, env=env)
            else:
                result = self.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=limit, check=False, env=env)
        except (OSError, subprocess.TimeoutExpired):
            raise Refused('K8S_OBSERVATION_LOST', 'UNMEASURED')
        def bounded_response():
            raw = result.stdout
            if isinstance(raw, str):
                raw = raw.encode()
            need(isinstance(raw, bytes) and (rows is not None or len(raw) <= output_limit), 'OBSERVATION_BOUND', 'UNMEASURED')
            return raw
        # Only an explicit private observer sink receives bounded returned bytes
        # before the original deadline/exit refusal. Partial timeout output and
        # oversized output are never presented as a complete returned response.
        raw = None
        if response_sink is not None:
            raw = bounded_response()
            response_sink(raw, result.returncode)
        deadline(c, cleanup)
        if result.returncode and re.search(rb'(?<![A-Z_])EVALUATOR_SCOPE_UNSAFE(?![A-Z_])', getattr(result, 'stderr', b'') or b''):
            raise Refused('EVALUATOR_SCOPE_UNSAFE', 'FAIL')
        need(result.returncode == 0, 'OBSERVATION_LOST', 'UNMEASURED')
        return bounded_response() if raw is None else raw

    def get(self, kind, name=None, cleanup=False):
        argv = ['get', kind] + ([name] if name else []) + ['-o', 'json']
        try:
            return json.loads(self.call(argv, cleanup=cleanup))
        except ValueError:
            raise Refused('K8S_OBSERVATION_LOST', 'UNMEASURED')


def meta(obj):
    m = obj['metadata']
    need(isinstance(m.get('uid'), str) and m['uid'] and isinstance(m.get('resourceVersion'), str), 'OBJECT_IDENTITY_UNMEASURED', 'UNMEASURED')
    return {'kind': obj['kind'], 'name': m['name'], 'namespace': m.get('namespace'), 'uid': m['uid'], 'resourceVersion': m['resourceVersion']}


def owned(c, obj):
    m = obj['metadata']
    need(m.get('namespace') == c['namespace'], 'FOREIGN_NAMESPACE')
    need(m.get('labels', {}).get(c['ownerLabel']) == c['runId'], 'PEER_RESOURCE_REFUSED')


def controller(obj):
    refs = [r for r in obj['metadata'].get('ownerReferences', []) if r.get('controller') is True]
    need(len(refs) == 1, 'POD_CONTROLLER')
    return refs[0]


SETUP_JOBS = {'Job/primer', 'Job/provision', 'Job/verification'}


def job_terminal(job):
    """Keep controller-authored terminal status. A failed Job proves no Pod exit code."""
    status = job.get('status', {})
    terminal = [r for r in status.get('conditions', []) if
                r.get('type') in ('Failed', 'Complete') and r.get('status') == 'True']
    if len(terminal) != 1:
        return None
    condition = terminal[0]
    failed = condition['type'] == 'Failed'
    if (status.get('failed' if failed else 'succeeded') != 1 or
        any(status.get(key, 0) != 0 for key in
            ('active', 'ready', 'terminating', 'succeeded' if failed else 'failed')) or
        any(status.get('uncountedTerminatedPods', {}).values())):
        return None
    reason = condition.get('reason')
    reasons = {'DeadlineExceeded', 'BackoffLimitExceeded'} if failed else {'CompletionsReached', None}
    if reason not in reasons or not condition.get('lastTransitionTime'):
        return None
    return {'condition': condition['type'], 'reason': reason,
            'at': condition['lastTransitionTime'], 'jobUid': job['metadata']['uid']}


def check_retired_jobs(c, current, baseline):
    current_names, old_names = current['pods'].keys(), baseline['pods'].keys()
    need(current_names <= old_names, 'POD_ROSTER_CHANGED')
    retired = {}
    for name in sorted(old_names - current_names):
        old = baseline['pods'][name]
        job = old['workload']
        terminal = current['setupJobs'].get(job)
        need(job in SETUP_JOBS and job not in {r['workload'] for r in c['roles'].values()}
             and terminal and old.get('controllerUid') == terminal['jobUid'] == baseline['objects'][job]['uid']
             and sum(p['workload'] == job for p in baseline['pods'].values()) == 1, 'POD_RETIREMENT_UNPROVEN')
        states = {}
        for container, row in old['containers'].items():
            ended = (row.get('state') or {}).get('terminated', {})
            states[container] = {'containerId': row['containerID'],
                                 'lastObservedExitCode': ended.get('exitCode', 'UNMEASURED')}
        retired[name] = {'job': job, 'podUid': old['uid'], **terminal, 'containers': states}
    return retired


def completed_primer(c, baseline, job_uid):
    """Bind successful setup to the original Pod and its exported DATA credentials."""
    import primer
    directory = Path(c['primerOutput']).parent
    original = primer.require_roster(directory, c, baseline)
    need(original.get('controllerUid') == job_uid, 'POD_RETIREMENT_UNPROVEN')
    return {field: original[field] for field in ('name', 'uid', 'workload', 'nodeName')}


BOOTSTRAP_MAP = frozen.HELPER_MAP
BOOTSTRAP_TARGET = frozen.BOOTSTRAP_TARGET
BOOTSTRAP_ANNOTATIONS = frozen.HELPER_ANNOTATIONS


def helper_annotations(want, actual):
    for key in BOOTSTRAP_ANNOTATIONS:
        need(actual.get('annotations', {}).get(key) == want.get('annotations', {}).get(key),
             'BOOTSTRAP_HELPER_ANNOTATION_CHANGED')


def helper_map(c, expected, actual, client):
    """Positive equality for one public source blob. Guarded output contains only a boolean."""
    owned(c, actual)
    identity = meta(actual)
    need(key(actual) == 'ConfigMap/' + BOOTSTRAP_MAP and actual.get('immutable') is True
         and not actual['metadata'].get('deletionTimestamp') and not actual.get('binaryData') and
         set(actual.get('data', {})) == {'bootstrap.js'}, 'BOOTSTRAP_HELPER_MAP_CHANGED')
    helper_annotations(expected['metadata'], actual['metadata'])
    source = expected['data']['bootstrap.js']
    digest = hashlib.sha256(source.encode()).hexdigest()
    need(actual['metadata']['annotations']['nightscout.org/bootstrap-helper-sha256'] == digest, 'BOOTSTRAP_HELPER_SOURCE_CHANGED')
    if actual['data']['bootstrap.js'] != source:
        # The existing read guard redacts some field-like words even in public
        # JavaScript source. Compare the known Git blob inside kubectl and only
        # return whether this exact UID, resource version and data key match.
        quote = json.dumps
        predicate = ('{{and (eq .metadata.uid ' + quote(identity['uid']) +
                     ') (eq .metadata.resourceVersion ' + quote(identity['resourceVersion']) +
                     ') (eq (index .data "bootstrap.js") ' + quote(source) + ')}}')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gotmpl') as file:
            file.write(predicate)
            file.flush()
            answer = client.call(['get', 'configmap', BOOTSTRAP_MAP, '-o', 'go-template-file=' + file.name])
        need(answer.strip() == b'true', 'BOOTSTRAP_HELPER_SOURCE_CHANGED')
    return {'configMapUid': identity['uid'], 'sha256': digest, 'instanceAcceptance': 'PENDING'}


def capture_bootstrap_map(d, c, objects, namespace_uid, client):
    contract = objects.get('ConfigMap/' + BOOTSTRAP_MAP)
    need(contract and c['pins'].get('candidate', {}).get('sourceAcceptance') == 'PENDING', 'BOOTSTRAP_HELPER_SCOPE')
    output = d / 'bootstrap-map.json'
    need(not output.exists(), 'BOOTSTRAP_HELPER_PROOF_EXISTS')
    def namespace():
        obj = client.get('namespace', c['namespace'])
        need(obj['metadata']['name'] == c['namespace'] and obj['metadata']['uid'] == namespace_uid and
             obj['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'] and
             not obj['metadata'].get('deletionTimestamp'), 'NAMESPACE_UID_CHANGED')
    namespace()
    live = client.get('ConfigMap', BOOTSTRAP_MAP)
    receipt = helper_map(c, contract, live, client)
    namespace()
    receipt.update(namespaceUid=namespace_uid, runSha256=digest(d / 'run.json'))
    write(output, receipt)
    return receipt


def observe(c, by_key, client, baseline=None, *, cleanup=False, restarted_role=None, serving_sql=False, measure_actors=False):
    import native_join
    ns = client.get('namespace', c['namespace'], cleanup)
    need(ns['metadata']['name'] == c['namespace'] and ns['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'], 'FOREIGN_NAMESPACE')
    result = {'context': c['context'], 'runId': c['runId'], 'namespace': meta(ns), 'pins': copy.deepcopy(c['pins']),
              'observedAt': time.time(), 'objects': {}, 'pods': {}, 'driver': c['driver'], 'observer': c['observer'],
              'storageMode': c['storageMode'], 'capacityAcceptance': 'NOT_GRANTED'}
    if native_join.selected(c) is not None:
        result['testActors'] = {}
    if serving_sql:
        need(baseline is not None and not cleanup and restarted_role is None, 'SERVING_BASELINE_REQUIRED')
        need(not ns['metadata'].get('deletionTimestamp'), 'NAMESPACE_TERMINATING')
        result['setupJobs'] = {}
    primer_terminal = None
    for name, expected in by_key.items():
        if expected['kind'] not in PLURALS:
            continue
        actual = client.get(expected['kind'], expected['metadata']['name'], cleanup)
        owned(c, actual)
        if name == native_join.JOB:
            actual = native_join.exact_spec(c, client, actual, ns['metadata']['uid'], cleanup=cleanup)
        if serving_sql:
            need(not actual['metadata'].get('deletionTimestamp'), 'RESOURCE_TERMINATING')
            if name in SETUP_JOBS:
                result['setupJobs'][name] = job_terminal(actual)
        need(key(actual) == name, 'RESOURCE_NAME_CHANGED')
        if name == 'ConfigMap/' + BOOTSTRAP_MAP:
            result['bootstrapHelper'] = helper_map(c, expected, actual, client)
        # Kubernetes holds the applied spec; it is recorded, not re-compared
        # (decision four-product-failures: nothing the platform guarantees is re-proved).
        if actual['kind'] in WORKLOADS:
            if name == native_join.JOB:
                result['nativeLoadSuspended'] = actual['spec'].get('suspend')
            replica_scope(actual)
        result['objects'][name] = meta(actual)
        if actual['kind'] == 'Job':
            result['objects'][name]['suspend'] = actual['spec'].get('suspend', False)
        if name == 'Job/primer':
            result['objects'][name]['activeDeadlineSeconds'] = actual['spec'].get('activeDeadlineSeconds')
            primer_terminal = job_terminal(actual)
        if name=='ConfigMap/edge-nginx' and c.get('edgeConfiguration'):
            result['edgeConfiguration']={**c['edgeConfiguration'],'configurationSha256':edge_configuration.readback(expected,actual,need)}
    replicas = client.get('replicasets', cleanup=cleanup)['items']
    rs_by_uid = {x['metadata']['uid']: x for x in replicas}
    pods = client.get('pods', cleanup=cleanup)['items']
    for pod in pods:
        owned(c, pod)
        if serving_sql:
            need(not pod['metadata'].get('deletionTimestamp'), 'POD_TERMINATING')
        ref = controller(pod)
        if ref['kind'] == 'ReplicaSet':
            rs = rs_by_uid.get(ref['uid'])
            need(rs is not None, 'POD_CONTROLLER')
            owned(c, rs)
            ref = controller(rs)
        name = ref['kind'] + '/' + ref['name']
        parent = result['objects'].get(name)
        need(parent is not None and parent['uid'] == ref['uid'], 'POD_CONTROLLER')
        expected = template(by_key[name])['spec']
        if name == native_join.JOB:
            pod = native_join.exact_spec(c, client, pod, ns['metadata']['uid'], cleanup=cleanup)
            result['testActors'][pod['metadata']['name']] = native_join.test_pod(c, by_key[name], pod, parent['uid'])
            need(len(result['testActors']) <= 1, 'NATIVE_LOAD_POD_CENSUS', 'UNMEASURED')
            continue
        statuses = pod.get('status', {})
        containers = {}
        for section in ('containerStatuses', 'initContainerStatuses'):
            for row in statuses.get(section, []):
                need(row['name'] not in containers, 'CONTAINER_DUPLICATE')
                need(all(k in row for k in ('containerID', 'imageID', 'restartCount')) and type(row['restartCount']) is int, 'CONTAINER_IDENTITY_UNMEASURED', 'UNMEASURED')
                containers[row['name']] = {k: row[k] for k in ('containerID', 'imageID', 'restartCount', 'ready')}
                containers[row['name']]['state'] = row.get('state')
        declared = expected.get('containers', []) + expected.get('initContainers', [])
        need(set(containers) == {r['name'] for r in declared}, 'CONTAINER_IDENTITY_UNMEASURED', 'UNMEASURED')
        result['pods'][pod['metadata']['name']] = {**meta(pod), 'workload': name, 'controllerUid': parent['uid'], 'nodeName': pod['spec'].get('nodeName'),
            'resources': {r['name']: r.get('resources', {}) for r in pod['spec'].get('containers', []) + pod['spec'].get('initContainers', [])},
            # Recorded as Kubernetes holds them; quota, LimitRange and the scheduler enforce budgets.
            'observedResources': resource_budget.observed(pod['spec']),
            'imageReferences': {r['name']: r['image'] for r in declared}, 'containers': containers,
            'ready': any(r.get('type') == 'Ready' and r.get('status') == 'True' for r in statuses.get('conditions', [])),
            'phase': statuses.get('phase')}
    if 'bootstrapHelper' in result:
        target = [p for p in result['pods'].values() if p['workload'] == 'Job/provision']
        need(len(target) == 1 or serving_sql and baseline is not None, 'BOOTSTRAP_HELPER_POD_REQUIRED')
        if target:
            state = target[0]['containers']['bootstrap']
            result['bootstrapHelper'].update(jobUid=result['objects']['Job/provision']['uid'],
                podUid=target[0]['uid'], containerId=state['containerID'],
                lastObservedExitCode=(state.get('state') or {}).get('terminated', {}).get('exitCode', 'UNMEASURED'))
        if baseline is not None:
            need(baseline.get('bootstrapHelper', {}).get('configMapUid') == result['bootstrapHelper']['configMapUid'],
                 'BOOTSTRAP_HELPER_UID_CHANGED')
    candidate.images(sys.modules[__name__], c, result)
    for role, selection in c['roles'].items():
        selected = [r for r in result['pods'].values() if r['workload'] == selection['workload']]
        need(len(selected) == 1, 'ROLE_POD_UNMEASURED:' + role, 'UNMEASURED')
        need(selected[0]['nodeName'], 'NODE_UNMEASURED', 'UNMEASURED')
    if measure_actors and baseline is not None:
        # Ordinary window bookends compare the same owned workload across
        # pods. SQL/observer reads and intentional restart controls still bind
        # the exact actor they sampled.
        baseline = {**baseline, 'pods': dict(baseline['pods'])}
        result['actorTransitions'] = []
        for name, pod in result['pods'].items():
            workload = pod['workload']
            if not workload.startswith(('Deployment/', 'StatefulSet/')):
                continue
            old = baseline['pods'].get(name)
            if old is None:
                candidates = [(key, row) for key, row in baseline['pods'].items() if row['workload'] == workload
                              and key not in result['pods']]
                need(len(candidates) == 1, 'POD_TRANSITION_UNATTRIBUTABLE', 'UNMEASURED')
                old_name, old = candidates[0]
                del baseline['pods'][old_name]
            need(old['workload'] == workload and old['controllerUid'] == pod['controllerUid'], 'POD_CONTROLLER')
            for container, current in pod['containers'].items():
                previous = old['containers'][container]
                fields = ('containerID', 'imageID', 'restartCount')
                if old['uid'] != pod['uid'] or any(current[key] != previous[key] for key in fields):
                    result['actorTransitions'].append({'workload': workload, 'container': container,
                        'fromPodUid': old['uid'], 'toPodUid': pod['uid'],
                        'previous': {key: previous[key] for key in fields}, 'current': {key: current[key] for key in fields}})
            baseline['pods'][name] = pod
    if baseline is not None:
        need(all(result[k] == baseline[k] for k in ('context', 'runId', 'pins')), 'SOURCE_IMAGE_BINDING_CHANGED')
        need(result['namespace']['uid'] == baseline['namespace']['uid'], 'NAMESPACE_UID_CHANGED')
        need(result['objects'].keys() == baseline['objects'].keys() and all(result['objects'][k]['uid'] == baseline['objects'][k]['uid'] for k in result['objects']), 'RESOURCE_UID_CHANGED')
        previous_primer = next((pod for pod in baseline['pods'].values() if pod['workload'] == 'Job/primer'),
                               baseline.get('completedPrimer'))
        current_primer = result['pods'].get(previous_primer['name']) if previous_primer else None
        if previous_primer and current_primer is None and primer_terminal is None and (serving_sql or 'primerOutput' in c):
            # The Pod list is newer than the original Job GET. Read its controller
            # once more to resolve retirement, under the same observation deadline.
            job = client.get('Job', 'primer', cleanup)
            owned(c, job)
            need(key(job) == 'Job/primer' and job['metadata']['uid'] == result['objects']['Job/primer']['uid'],
                 'RESOURCE_UID_CHANGED')
            primer_terminal = job_terminal(job)
            if serving_sql:
                need(not job['metadata'].get('deletionTimestamp'), 'RESOURCE_TERMINATING')
                result['setupJobs']['Job/primer'] = primer_terminal
        if serving_sql:
            result['retiredJobs'] = check_retired_jobs(c, result, baseline)
        else:
            expected_pods = set(baseline['pods'])
            job_complete = primer_terminal and primer_terminal['condition'] == 'Complete'
            pod_succeeded = current_primer and current_primer['phase'] == 'Succeeded'
            if baseline.get('completedPrimer'):
                need(job_complete or pod_succeeded, 'POD_RETIREMENT_UNPROVEN')
            if 'primerOutput' in c and primer_terminal and not job_complete and not cleanup:
                raise Refused('K8S_PRIMER_JOB_FAILED')
            if 'primerOutput' in c and (job_complete or pod_succeeded):
                if pod_succeeded:
                    need(all((r.get('state') or {}).get('terminated', {}).get('exitCode') == 0
                             for r in current_primer['containers'].values()), 'PRIMER_POD_EXIT')
                finished = completed_primer(c, baseline, result['objects']['Job/primer']['uid'])
                result['completedPrimer'] = finished
                if finished['name'] not in result['pods']:
                    expected_pods.discard(finished['name'])
            need(set(result['pods']) == expected_pods, 'POD_ROSTER_CHANGED')
        target = c['roles'].get(restarted_role)
        for name, current in result['pods'].items():
            old = baseline['pods'][name]
            # Pod UID, placement, image and restart counts are recorded figures, not refusals.
            for container, row in current['containers'].items():
                previous = old['containers'].get(container)
                if previous and target and current['workload'] == target['workload'] and container == target['container']:
                    need(row['containerID'] != previous['containerID'] and row['restartCount'] == previous['restartCount'] + 1 and row['ready'], 'RESTART_NOT_OBSERVED', 'UNMEASURED')
    return result


def selected_pod(c, observation, role):
    selection = c['roles'][role]
    found = [v for v in observation['pods'].values() if v['workload'] == selection['workload']]
    need(len(found) == 1 and found[0]['containers'][selection['container']]['ready'], 'ROLE_NOT_READY', 'UNMEASURED')
    return found[0]['name'], selection['container']


def load(directory, cleanup=False):
    d = Path(directory).resolve()
    c = document(d / 'run.json')
    need(digest(d / 'render.json') == c['pins']['renderSha256'], 'RENDER_CHANGED')
    need(digest(d / 'inventory.json') == c['pins']['inventorySha256'], 'INVENTORY_CHANGED')
    by_key = validate(c, document(d / 'inventory.json'), document(d / 'render.json'), cleanup=cleanup)
    need(document(d / 'packet.json')['runSha256'] == digest(d / 'run.json'), 'RUN_CONFIG_CHANGED')
    return d, c, by_key


def active_baseline(d):
    initial = document(d / 'observation.initial.json')
    if (d / 'restart.json').is_file():
        value = document(d / 'restart.json')
        if value.get('status') == 'OBSERVED':
            need(value['before']['pins'] == initial['pins'] and value['after']['namespace']['uid'] == initial['namespace']['uid'], 'RESTART_BASELINE_CHANGED')
            return value['after']
    return initial


def sql(d, c, objects, query, client=None):
    need(isinstance(query, str) and query.strip().startswith('SELECT ') and len(query.encode()) < 131072, 'SQL_READ_ONLY')
    client = client or Client(c)
    baseline = active_baseline(d)
    before = observe(c, objects, client, baseline)
    pod, container = selected_pod(c, before, 'postgres')
    raw = postgres_read(client, pod, container, query)
    observe(c, objects, client, baseline)
    return raw


def postgres_read(client, pod, container, query, **options):
    data = ('BEGIN READ ONLY;\n' + query + '\nROLLBACK;\n').encode()
    fetch = ['-v', 'FETCH_COUNT=128'] if options.get('rows') else []
    raw = client.call(['exec', '-i', pod, '-c', container, '--', 'psql', '-X', *fetch, '-qAt', '-F', '\t', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'nightscout_compose_test'], data=data, read=False, **options)
    return raw.decode()


def observe_sql(d, c, objects, output, client):
    """Fixed source seed aggregate, with separate terminal Job and serving evidence."""
    baseline = active_baseline(d)
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    candidate.require(sys.modules[__name__], d, c)
    def capture():
        point = observe(c, objects, client, baseline, serving_sql=True)
        pod, container = selected_pod(c, point, 'postgres')
        need(point['pods'][pod]['ready'] and point['pods'][pod]['phase'] == 'Running',
             'ROLE_NOT_READY', 'UNMEASURED')
        evidence = {k: point[k] for k in ('observedAt', 'setupJobs', 'retiredJobs')}
        evidence.update(namespaceUid=point['namespace']['uid'], postgresPodUid=point['pods'][pod]['uid'],
                        podUids={n: p['uid'] for n, p in point['pods'].items()})
        return pod, container, evidence
    pod, container, before = capture()
    write(output / 'before.json', before)
    query = """SELECT s.system_identifier::text, c.timeline_id, current_database(),
      EXISTS(SELECT 1 FROM pg_catalog.pg_replication_slots WHERE slot_name='nsdemo_pgstream'
             AND slot_type='logical' AND database=current_database()),
      count(e.tenant_id), count(DISTINCT e.tenant_id)
      FROM pg_catalog.pg_control_system() s CROSS JOIN pg_catalog.pg_control_checkpoint() c
      LEFT JOIN nsdemo_entries.entries e ON e.doc->>'device'='synthetic-compose-demo'
      GROUP BY s.system_identifier,c.timeline_id;"""
    fields = postgres_read(client, pod, container, query).strip().split('\t')
    need(len(fields) == 6 and re.fullmatch('[0-9]{1,20}', fields[0]) and
         fields[1].isdigit() and int(fields[1]) > 0 and fields[2] == 'nightscout_compose_test'
         and fields[3] in ('t', 'f') and all(n.isdigit() for n in fields[4:]), 'SQL_OBSERVATION_UNMEASURED', 'UNMEASURED')
    _, _, after = capture()
    write(output / 'after.json', after)
    epoch = {'system_id': fields[0], 'timeline': int(fields[1]), 'database': fields[2]}
    if 'candidate' in c['pins']:
        expected = document(d / 'candidate-verification.json')['proof']['nativeSource']
        need(all(epoch[key] == expected[key] for key in epoch) and fields[3] == 't' and
             expected['slot'] == 'nsdemo_pgstream', 'CANDIDATE_NATIVE_SOURCE_CHANGED')
    row = {'verdict': 'OBSERVED', 'scope': 'stored source-primer seed rows in the fixture database',
           'runSha256': digest(d / 'run.json'), 'source': c['pins']['pair'], 'nativeSource': epoch,
           'logicalSlotPresent': fields[3] == 't', 'storedRows': int(fields[4]), 'storedTenants': int(fields[5]),
           'setupJobs': after['setupJobs'], 'dataCredentials': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED'}
    write(output / 'result.json', row)
    return row


def stored(d, c, objects, runid, client=None):
    need(re.fullmatch('[a-z0-9-]{1,100}', runid) is not None, 'RUN_MARKER')
    selects = [(kind, kind, field, suffix) for kind, field, suffix in [('entries', 'device', ''), ('devicestatus', 'device', ''), ('treatments', 'enteredBy', '')]]
    selects += [('entries', 'probe', 'device', '-probe')]
    query = '\nUNION ALL\n'.join("SELECT tenant_id::text,'" + result + "',count(*) FROM nsdemo_" + domain + '.' + domain + " WHERE doc->>'" + field + "'='" + runid + suffix + "' GROUP BY 1" for domain, result, field, suffix in selects) + ';'
    values = {}
    for line in sql(d, c, objects, query, client).splitlines():
        tenant, kind, count = line.split('\t')
        need(kind not in values.setdefault(tenant, {}), 'SQL_DUPLICATE_GROUP')
        values[tenant][kind] = int(count)
    return values


def generate_probe(target):
    result = probe.generate(ROOT, target, transport=HERE/'probe-kubernetes.cjs')
    return {**result, 'kubernetesSha256': digest(target), 'restart': 'external role restart'}


def prepare(config, inventory_file, render_file, directory):
    c = document(config)
    need(digest(inventory_file) == c['pins']['inventorySha256'] and digest(render_file) == c['pins']['renderSha256'], 'RENDER_INVENTORY_PIN')
    identity = instrument()
    need(c['pins']['instrument'] == identity['sha256'], 'INSTRUMENT_CHANGED')
    validate(c, document(inventory_file), document(render_file))
    d = Path(directory)
    need(d.is_absolute() and not d.exists(), 'NEW_ABSOLUTE_OUTPUT_REQUIRED')
    d.mkdir(mode=0o700, parents=True)
    write(d / 'run.json', c)
    for name, source in [('inventory.json', inventory_file), ('render.json', render_file)]:
        (d / name).write_bytes(Path(source).read_bytes())
        os.chmod(d / name, 0o600)
    generated = generate_probe(d / 'probe.cjs')
    work = workload.generate(ROOT, d / 'workload.js')
    if 'driverPlan' in c.get('workload', {}):
        import workload_runtime
        import driver_vu_diagnostic as driver
        workload_runtime.driver_manifest(c)
        need((d / 'workload.js').stat().st_size <= driver.MAX_GENERATED_BYTES, 'GENERATED_WORKLOAD_BOUND')
        (d / driver.SCRIPT).write_bytes((M7 / driver.SCRIPT).read_bytes())
        work['driverWrapperSha256'] = digest(d / driver.SCRIPT)
    packet = {'version': 1, 'runSha256': digest(d / 'run.json'), 'instrument': identity, 'probe': generated,
              'workload': work, 'clusterStarted': False, 'liveCorrectness': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED',
              'deadlines': c['deadlines'], 'commands': {phase: [sys.executable, str(HERE / 'adapter.py'), phase, str(d)] for phase in ('observe', 'forward-plan', 'policy', 'commission', 'access', 'assess', 'recovery', 'load', 'cleanup-plan')}}
    if 'experimentSha256' in c:
        packet['commands']['load'] = [sys.executable, str(HERE/'experiment.py'), 'run', str(d),
                                      '<released-allocation.json>', '<owner-supplied-sha256>']
    if 'candidate' in c['pins']:
        packet['commands']['candidate-proof'] = [sys.executable, str(HERE / 'adapter.py'), 'candidate-proof', str(d)]
    packet['commands']['restart-evaluator'] = [sys.executable, str(HERE / 'adapter.py'), 'restart', str(d), 'evaluator']
    write(d / 'packet.json', packet)
    return packet


def cleanup_plan(c, observation, current):
    need(current['context'] == c['context'] and current['namespace']['uid'] == observation['namespace']['uid'] and current['runId'] == c['runId'], 'PEER_CLEANUP_REFUSED')
    need(current['objects'].keys() == observation['objects'].keys(), 'PEER_CLEANUP_REFUSED')
    actions = []
    for name, row in current['objects'].items():
        need(row['uid'] == observation['objects'][name]['uid'] and row['namespace'] == c['namespace'], 'PEER_CLEANUP_REFUSED')
        version, plural = PLURALS[row['kind']]
        prefix = '/api/v1' if version == 'v1' else '/apis/' + version
        uri = prefix + '/namespaces/' + c['namespace'] + '/' + plural + '/' + row['name']
        actions.append({'object': row, 'argv': [c['kubectl'], '--context', c['context'], '--namespace', c['namespace'], 'delete', '--raw', uri, '-f', '-'],
                        'stdin': {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'propagationPolicy': 'Foreground', 'preconditions': {'uid': row['uid']}}})
    actions.sort(key=lambda a: a['object']['kind'] not in WORKLOADS)
    return {'version': 1, 'actions': actions, 'namespaceDeletion': 'NOT_INCLUDED', 'secretsClaimsClusterBindings': 'Lane E operator custody; never inferred owned',
            'absence': 'Read exact target; only Kubernetes Status reason=NotFound/code=404 proves absence. Command errors and Terminating do not.', 'cleanupUntil': c['deadlines']['cleanupUntil']}


def completion_source(c, evaluator_config, realtime_config, native_receipt=None):
    binding = {'kind': 'evaluator-work-v2', 'pair': c['pins']['pair'], 'imageId': c['pins']['appImageId'], 'instrument': c['pins']['instrument']}
    need(native_receipt is not None or c['pins'].get('candidate',{}).get('platformVerification') not in candidate.NATIVE_RECEIPT_PROTOCOLS,
         'COMPLETION_RECEIPT_REQUIRED')
    code = "const fs=require('fs'),o=require(process.argv[1]);const v=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(o.source(v.evaluator,v.realtime,v.binding,v.receipt)));"
    result = subprocess.run([c['driver']['node'], '-e', code, str(M7 / 'completed-oracle.cjs')], input=json.dumps({'evaluator': document(evaluator_config), 'realtime': document(realtime_config), 'binding': binding, **({'receipt':document(native_receipt)} if native_receipt is not None else {})}).encode(), capture_output=True, timeout=10)
    need(result.returncode == 0, 'COMPLETION_SOURCE_REFUSED')
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('identity')
    p = sub.add_parser('completion-source')
    for arg in ('config', 'evaluator_config', 'realtime_config'):
        p.add_argument(arg)
    p.add_argument('--native-receipt')
    p = sub.add_parser('tenant-projection')
    p.add_argument('primer_result')
    p.add_argument('count', type=int)
    p = sub.add_parser('prepare')
    for arg in ('config', 'inventory', 'render', 'directory'):
        p.add_argument(arg)
    for name in ('observe', 'sql', 'clinical-sql', 'commission', 'recovery', 'access', 'policy', 'load', 'cleanup-plan', 'assess', 'candidate-proof'):
        p = sub.add_parser(name)
        p.add_argument('directory')
    p = sub.add_parser('bootstrap-map')
    p.add_argument('directory')
    p.add_argument('namespace_uid')
    p = sub.add_parser('observe-sql')
    p.add_argument('directory')
    p.add_argument('output')
    p = sub.add_parser('forward-plan')
    p.add_argument('directory')
    p = sub.add_parser('matrix-plan')
    p.add_argument('matrix')
    p = sub.add_parser('matrix-run')
    p.add_argument('matrix')
    p.add_argument('output')
    p = sub.add_parser('continuity')
    p.add_argument('directory')
    p.add_argument('independent_directory')
    p = sub.add_parser('restart')
    p.add_argument('directory')
    p.add_argument('role', choices=('api', 'realtime', 'evaluator'))
    args = parser.parse_args()
    if args.command == 'identity':
        return instrument()
    if args.command == 'tenant-projection':
        from contract import tenant_projection
        return tenant_projection(document(args.primer_result), args.count)
    if args.command == 'completion-source':
        c = document(args.config)
        return completion_source(c, args.evaluator_config, args.realtime_config, native_receipt=args.native_receipt)
    if args.command == 'prepare':
        return prepare(args.config, args.inventory, args.render, args.directory)
    if args.command == 'matrix-plan':
        from execute import matrix_plan
        return matrix_plan(document(args.matrix))
    if args.command == 'matrix-run':
        from matrix import run
        result = run(document(args.matrix), args.output)
        if result['verdict'] != 'OBSERVED_CONCURRENT_FIXTURES':
            raise Refused(result.get('code', 'K8S_MATRIX_INCOMPLETE'), result['verdict'])
        return result
    d, c, objects = load(args.directory, cleanup=args.command == 'cleanup-plan')
    client = Client(c)
    if args.command == 'bootstrap-map':
        return capture_bootstrap_map(d, c, objects, args.namespace_uid, client)
    if args.command == 'observe-sql':
        return observe_sql(d, c, objects, args.output, client)
    if args.command == 'forward-plan':
        from urllib.parse import urlparse
        url = urlparse(c['baseUrl'])
        need(url.scheme == 'http' and url.hostname == '127.0.0.1' and url.port is not None, 'LOOPBACK_FORWARD_REQUIRED')
        value = observe(c, objects, client, active_baseline(d))
        pod, _ = selected_pod(c, value, 'nginx')
        return {'operatorStep': True, 'context': c['context'], 'namespaceUid': value['namespace']['uid'], 'podUid': value['pods'][pod]['uid'],
                'argv': ['/usr/bin/timeout', '--signal=TERM', '--kill-after=3s', str(deadline(c))+'s', c['kubectl'], '--context', c['context'], '--namespace', c['namespace'], 'port-forward', 'pod/'+pod, '--address=127.0.0.1', str(url.port)+':8080'],
                'identityLimit': 'port-forward has no UID precondition; stop if either UID changes', 'capacityAcceptance': 'NOT_GRANTED'}
    if args.command == 'observe':
        file = d / 'observation.initial.json'
        observation = observe(c, objects, client, document(file) if file.exists() else None)
        if (d / 'bootstrap-map.json').exists():
            earlier = document(d / 'bootstrap-map.json')
            need(earlier['runSha256'] == digest(d / 'run.json') and
                 earlier['namespaceUid'] == observation['namespace']['uid'] and
                 all(earlier[key] == observation['bootstrapHelper'][key] for key in
                     ('sha256','instanceAcceptance','configMapUid')), 'BOOTSTRAP_HELPER_UID_CHANGED')
        need(not file.exists(), 'INITIAL_OBSERVATION_EXISTS')
        write(file, observation)
        return observation
    if args.command == 'sql':
        sys.stdout.write(sql(d, c, objects, sys.stdin.read(131073), client))
        return None
    if args.command == 'clinical-sql':
        import clinical_sql
        sys.stdout.write(clinical_sql.read(d, c, objects, sys.stdin.read(131073), client))
        return None
    if args.command == 'cleanup-plan':
        initial = document(d / 'observation.initial.json')
        current = observe(c, objects, client, active_baseline(d), cleanup=True)
        value = cleanup_plan(c, initial, current)
        write(d / 'cleanup-plan.json', value)
        return value
    if args.command == 'candidate-proof':
        return candidate.observe(sys.modules[__name__], d, c, objects, client)
    if args.command == 'restart':
        candidate.require(sys.modules[__name__], d, c)
    from execute import execute, access, assess, restart, continuity, policy
    if args.command == 'continuity':
        return continuity(d, c, args.independent_directory)
    if args.command == 'access':
        return access(d, c, objects, client)
    if args.command == 'policy':
        return policy(d, c, objects, client)
    if args.command == 'assess':
        return assess(d, c, objects, client)
    if args.command == 'restart':
        return restart(d, c, objects, client, args.role)
    need(args.command != 'load' or 'experimentSha256' not in c, 'EXPERIMENT_ALLOCATION_REQUIRED')
    return execute(d, c, objects, client, load=args.command == 'load', recovery=args.command == 'recovery')



def failure_evidence(error):
    code = str(error)
    if code != 'EVALUATOR_SCOPE_UNSAFE' and not re.fullmatch(r'(?:K8S|M7)_[A-Z_]+(?::[A-Za-z0-9_.-]+)?', code):
        code = 'K8S_ADAPTER_ERROR'
    result = {'verdict': getattr(error, 'verdict', 'UNMEASURED'), 'code': code,
              'capacityAcceptance': 'NOT_GRANTED'}
    if code == 'K8S_ADAPTER_ERROR':
        # Only static source locations and exception class are retained.
        frames = []
        for frame in traceback.extract_tb(error.__traceback__):
            path = Path(frame.filename)
            if path.parent in (HERE, M7):
                frames.append({'file': path.name, 'function': frame.name, 'line': frame.lineno})
        result.update(errorType=type(error).__name__, frames=frames[-8:])
    return result


if __name__ == '__main__':
    try:
        result = main()
        if result is not None:
            print(json.dumps(result, sort_keys=True, allow_nan=False))
    except Exception as error:
        print(json.dumps(failure_evidence(error)), file=sys.stderr)
        sys.exit(1)
