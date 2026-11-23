#!/usr/bin/env python3
"""Cluster-resident capacity campaigns: one command starts it, the cluster runs it, the store holds its evidence.

  campaign.py apply MANIFEST [--context C] [--create-bucket]   one command: store Secret + controller Job (bench-control)
  campaign.py controller /etc/campaign/manifest.json           in the controller Pod (the Job's command)
  campaign.py status CAMPAIGN                                   per-case status.json from the store
  campaign.py collect CAMPAIGN --out DIR [--case C]             fetch, verify (sha256 seal), then delete verified objects
  campaign.py close CAMPAIGN [--context C]                      remove the controller objects, then the (empty) bucket
  campaign.py census CAMPAIGN [--context C] [--doctl-cluster N] every billable thing the campaign created; exit 1 if any
  campaign.py rescore DIR                                       capacity_results.rescore over every collected packet
  campaign.py catalog-import DIGEST [--catalog F] [--context C] put one workstation fixture record into bench-control

The store's credentials and endpoint come from the environment (evidence_store.py). Nothing here pushes images or calls
the DigitalOcean API except `census --doctl-cluster`, which only lists.

Store layout:  <campaign>/campaign.json
               <campaign>/cases/<case>/status.json                        queued|running|scored|failed|UNMEASURED
               <campaign>/cases/<case>/attempt-<n>/files/...              packet, uploaded as it is written
               <campaign>/cases/<case>/attempt-<n>/INDEX.json             what has been uploaded (resume seals from it)
               <campaign>/cases/<case>/attempt-<n>/SEAL.json              written last
Kubernetes:    namespace bench-control; per campaign: ServiceAccount, ClusterRole(+Binding), ValidatingAdmissionPolicy
               (+Binding), ConfigMap campaign-<c> (manifest), Secret campaign-store-<c>, Job campaign-<c>.
Run ids are <campaign>-<case>-a<n>; every case namespace carries nightscout.org/run-id=<run id>, so the census and the
admission policy find them by that prefix with no state from the store.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parent / 'm7-joined'))
import case_supervisor
import evidence_store
import packet_seal
import run_cleanup

CONTROL_NS = 'bench-control'
RUN_LABEL = run_cleanup.LABEL
CAMPAIGN_LABEL = 'nightscout.org/campaign'
FIXTURE_LABEL = 'nightscout.org/fixture'
SUPERVISOR_LABEL = 'nightscout.org/case-supervisor'
FINAL = ('scored', 'failed', 'UNMEASURED')
NAME = re.compile(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?')
STORE_ENV = ('NS_EVIDENCE_ENDPOINT', 'NS_EVIDENCE_BUCKET', 'NS_EVIDENCE_ACCESS_KEY', 'NS_EVIDENCE_SECRET_KEY',
             'NS_EVIDENCE_REGION', 'NS_EVIDENCE_ADDRESSING')


class Refused(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise Refused('CAMPAIGN_' + code)


def jdump(value):
    return json.dumps(value, sort_keys=True, indent=1).encode()


# ---------------------------------------------------------------- manifest

def validate(m):
    need(m.get('version') == 1, 'VERSION')
    c = m.get('campaign', '')
    need(NAME.fullmatch(c) and len(c) <= 20, 'NAME')
    need(m.get('runner') in RUNNERS, 'RUNNER')
    need(re.search(r'@sha256:[0-9a-f]{64}$', m.get('controllerImage', '')) or m.get('controllerImage', '').startswith('kind.local/'),
         'CONTROLLER_IMAGE_DIGEST')
    cases = m.get('cases') or []
    need(cases, 'CASES')
    names = [x.get('name', '') for x in cases]
    need(len(set(names)) == len(names), 'CASE_DUPLICATE')
    for n in names:
        need(NAME.fullmatch(n) and len(c) + len(n) + 5 <= 63, 'CASE_NAME')   # run id <c>-<n>-a<k> is a label value
    need(type(m.get('maxAttempts', 2)) is int and 1 <= m.get('maxAttempts', 2) <= 5, 'MAX_ATTEMPTS')
    need(type(m.get('caseDeadlineSeconds')) is int and m['caseDeadlineSeconds'] > 0, 'CASE_DEADLINE')
    store = m.get('store') or {}
    need(store.get('bucket') and NAME.fullmatch(store['bucket']) and store.get('endpoint'), 'STORE')
    need(not any(k in store for k in ('accessKey', 'secretKey', 'NS_EVIDENCE_ACCESS_KEY', 'NS_EVIDENCE_SECRET_KEY')),
         'STORE_CREDENTIALS_IN_MANIFEST')
    RUNNERS[m['runner']].validate(m)
    return m


def run_id(m, case, attempt):
    return '%s-%s-a%d' % (m['campaign'], case, attempt)


def prefix(campaign):
    return campaign + '/'


def case_prefix(campaign, case):
    return '%s/cases/%s/' % (campaign, case)


def attempt_prefix(campaign, case, attempt):
    return '%sattempt-%d/' % (case_prefix(campaign, case), attempt)


# ---------------------------------------------------------------- kubectl

def kubectl_caller(context=None):
    base = ['kubectl'] + (['--context', context] if context else []) + ['--request-timeout=30s']

    def call(argv, data=None, check=True):
        q = subprocess.run(base + list(argv), input=data if isinstance(data, (bytes, type(None))) else data.encode(),
                           capture_output=True, timeout=180)
        if check and q.returncode:
            raise subprocess.CalledProcessError(q.returncode, argv[:3], q.stdout, q.stderr)
        return q.stdout.decode()
    return call


def kjson(call, argv):
    out = call(argv + ['-o', 'json'])
    return json.loads(out) if out.strip() else None


# ---------------------------------------------------------------- render / apply

def controller_name(m):
    return 'campaign-' + m['campaign']


def render(m):
    """Every Kubernetes object of the campaign's control plane. The store Secret is created by `apply` from the
    environment and never rendered."""
    c, name = m['campaign'], controller_name(m)
    sa = 'system:serviceaccount:%s:%s' % (CONTROL_NS, name)
    labels = {CAMPAIGN_LABEL: c, 'app.kubernetes.io/name': 'campaign-controller'}
    meta = lambda n, ns=CONTROL_NS: {'name': n, **({'namespace': ns} if ns else {}), 'labels': labels}
    run_prefix = c + '-'
    # RBAC grants what lifecycle.py does today; the admission policy below confines every write to objects of this
    # campaign's runs (namespaces, objects inside them, labelled cluster-scoped objects) and to bench-control.
    rules = [{'apiGroups': ['*'], 'resources': ['*'], 'verbs': ['*']}]
    obj = "(request.operation == 'DELETE' ? oldObject : object)"
    run_of = lambda o: "(has(%s.metadata.labels) && '%s' in %s.metadata.labels && %s.metadata.labels['%s'].startsWith('%s'))" % (
        o, RUN_LABEL, o, o, RUN_LABEL, run_prefix)
    label_of = lambda o, key: "(has(%s.metadata.labels) && '%s' in %s.metadata.labels && %s.metadata.labels['%s'].startsWith('%s'))" % (
        o, key, o, o, key, run_prefix)
    expression = ' || '.join([
        # a case namespace: created, labelled (heartbeat/released) and deleted only with this campaign's run label
        "(request.kind.kind == 'Namespace' && %s != null && %s)" % (obj, run_of(obj)),
        # anything inside such a namespace, or inside bench-control
        "(namespaceObject != null && (request.namespace == '%s' || %s))" % (CONTROL_NS, run_of('namespaceObject')),
        # cluster-scoped objects the run labels (Vault TokenReview binding, restore snapshot contents, supervisor RBAC)
        "(namespaceObject == null && request.kind.kind != 'Namespace' && %s != null && (%s || %s || %s))" % (
            obj, run_of(obj), label_of(obj, SUPERVISOR_LABEL), label_of(obj, FIXTURE_LABEL)),
        # a seed's snapshot contents are made by the CSI snapshotter (unlabelled); the seed patches them to Retain
        "(request.kind.kind == 'VolumeSnapshotContent' && request.operation == 'UPDATE' && "
        "oldObject.spec.volumeSnapshotRef.namespace.contains('%s'))" % run_prefix,
    ])
    policy = {'apiVersion': 'admissionregistration.k8s.io/v1', 'kind': 'ValidatingAdmissionPolicy', 'metadata': meta(name, None),
              'spec': {'failurePolicy': 'Fail',
                       'matchConstraints': {'resourceRules': [{'apiGroups': ['*'], 'apiVersions': ['*'], 'resources': ['*'],
                                                               'operations': ['CREATE', 'UPDATE', 'DELETE', 'CONNECT']}]},
                       'matchConditions': [{'name': 'campaign-controller', 'expression': "request.userInfo.username == '%s'" % sa}],
                       'validations': [{'expression': expression, 'reason': 'Forbidden',
                                        'message': 'campaign %s writes only its own run-labelled objects' % c}]}}
    store = m['store']
    env = [{'name': 'NS_EVIDENCE_ENDPOINT', 'value': store['endpoint']},
           {'name': 'NS_EVIDENCE_BUCKET', 'value': store['bucket']},
           {'name': 'NS_EVIDENCE_REGION', 'value': store.get('region', 'us-east-1')},
           {'name': 'NS_EVIDENCE_ADDRESSING', 'value': store.get('addressing', 'virtual')}] + [
        {'name': k, 'valueFrom': {'secretKeyRef': {'name': 'campaign-store-' + c, 'key': k}}}
        for k in ('NS_EVIDENCE_ACCESS_KEY', 'NS_EVIDENCE_SECRET_KEY')]
    volumes = [{'name': 'manifest', 'configMap': {'name': name}}, {'name': 'work', 'emptyDir': {}}]
    mounts = [{'name': 'manifest', 'mountPath': '/etc/campaign', 'readOnly': True}, {'name': 'work', 'mountPath': '/work'}]
    if m.get('pullSecret'):
        volumes.append({'name': 'pull', 'secret': {'secretName': m['pullSecret']}})
        mounts.append({'name': 'pull', 'mountPath': '/var/run/campaign-pull', 'readOnly': True})
    resources = m.get('controllerResources') or {'requests': {'cpu': '500m', 'memory': '1Gi'}, 'limits': {'memory': '3Gi'}}
    job = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': meta(name),
           # A replacement Pod starts only after the old one has terminated: one controller at a time.
           'spec': {'backoffLimit': m.get('controllerRestarts', 6), 'podReplacementPolicy': 'Failed',
                    'activeDeadlineSeconds': m['caseDeadlineSeconds'] * m.get('maxAttempts', 2) * len(m['cases']) + 3600,
                    'template': {'metadata': {'labels': labels}, 'spec': {
                        'serviceAccountName': name, 'restartPolicy': 'Never',
                        **({'nodeSelector': m['controllerNodeSelector']} if m.get('controllerNodeSelector') else {}),
                        'containers': [{'name': 'controller', 'image': m['controllerImage'], 'imagePullPolicy': 'IfNotPresent',
                                        'command': ['python3', '-B', '/app/campaign.py', 'controller', '/etc/campaign/manifest.json'],
                                        'env': env + [{'name': 'NS_CAMPAIGN_POD', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.name'}}}],
                                        'volumeMounts': mounts, 'resources': resources}],
                        'volumes': volumes}}}}
    items = [
        {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': meta(name)},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRole', 'metadata': meta(name, None), 'rules': rules},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRoleBinding', 'metadata': meta(name, None),
         'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': name},
         'subjects': [{'kind': 'ServiceAccount', 'name': name, 'namespace': CONTROL_NS}]},
        policy,
        {'apiVersion': 'admissionregistration.k8s.io/v1', 'kind': 'ValidatingAdmissionPolicyBinding', 'metadata': meta(name, None),
         'spec': {'policyName': name, 'validationActions': ['Deny']}},
        {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': meta(name), 'data': {'manifest.json': json.dumps(m, sort_keys=True, indent=1)}},
        job,
    ]
    return {'apiVersion': 'v1', 'kind': 'List', 'items': items}


def apply(m, call, env=None, create_bucket=False, store=None):
    validate(m)
    env = os.environ if env is None else env
    store = store or evidence_store.Store.from_env(dict(env, NS_EVIDENCE_ENDPOINT=m['store']['endpoint'],
                                                        NS_EVIDENCE_REGION=m['store'].get('region', 'us-east-1'),
                                                        NS_EVIDENCE_ADDRESSING=m['store'].get('addressing', 'virtual')),
                                                   bucket=m['store']['bucket'])
    if create_bucket and not store.bucket_exists():
        store.create_bucket()
    need(store.bucket_exists(), 'BUCKET_ABSENT')
    need(not store.list(prefix(m['campaign'])), 'CAMPAIGN_PREFIX_NOT_EMPTY')   # a campaign name is used once
    store.put(prefix(m['campaign']) + 'campaign.json', jdump(m), 'application/json')
    if not kjson(call, ['get', 'namespace', CONTROL_NS, '--ignore-not-found=true']):
        call(['create', 'namespace', CONTROL_NS])
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
              'metadata': {'name': 'campaign-store-' + m['campaign'], 'namespace': CONTROL_NS, 'labels': {CAMPAIGN_LABEL: m['campaign']}},
              'data': {k: base64.b64encode(env[k].encode()).decode() for k in ('NS_EVIDENCE_ACCESS_KEY', 'NS_EVIDENCE_SECRET_KEY')}}
    call(['apply', '-f', '-'], json.dumps(secret))
    # The policy must be in force before the controller starts writing.
    manifests = render(m)
    first, job = manifests['items'][:-1], manifests['items'][-1]
    call(['apply', '-f', '-'], json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': first}))
    call(['apply', '-f', '-'], json.dumps(job))
    return {'campaign': m['campaign'], 'store': store.describe(), 'job': CONTROL_NS + '/' + controller_name(m)}


# ---------------------------------------------------------------- the controller

class Status:
    def __init__(self, store, m, case):
        self.store, self.key = store, case_prefix(m['campaign'], case) + 'status.json'

    def read(self):
        try:
            return json.loads(self.store.get(self.key))
        except evidence_store.StoreError as error:
            if error.status == 404:
                return None
            raise

    def write(self, doc):
        doc = dict(doc, updatedAt=time.time())
        self.store.put(self.key, jdump(doc), 'application/json')
        return doc


class Progressive(packet_seal.Uploader):
    """Uploads the case directory as it grows and keeps INDEX.json current, so a resumed controller can seal what
    reached the store before the old Pod died."""

    def sync(self, directory):
        sent = super().sync(directory) if Path(directory).is_dir() else 0
        if sent:
            index = {rel: sha for rel, sha in self.sent.items()}
            self.store.put(self.prefix + 'INDEX.json', jdump(index), 'application/json')
        return sent


def seal_from_index(store, pfx, extra):
    """Seal an interrupted attempt from what reached the store. Each uploaded file is fetched and hashed here (an upload
    can land after the last INDEX.json write); INDEX.json entries that never arrived are named in `missingFromStore`.
    `extra` {rel: bytes} is written now (the interruption note)."""
    import hashlib
    try:
        index = json.loads(store.get(pfx + 'INDEX.json'))
    except evidence_store.StoreError as error:
        if error.status != 404:
            raise
        index = {}
    files = {}
    for obj in store.list(pfx + packet_seal.FILES):
        body = store.get(obj['key'])
        files[obj['key'][len(pfx) + len(packet_seal.FILES):]] = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
    for rel, body in extra.items():
        store.put(pfx + packet_seal.FILES + rel, body)
        files[rel] = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
    doc = {'version': 1, 'sealedAt': time.time(), 'status': 'interrupted', 'files': files, 'sealedFrom': 'store',
           'missingFromStore': sorted(set(index) - set(files))}
    store.put(pfx + packet_seal.SEAL, jdump(doc), 'application/json')
    return doc


class Controller:
    def __init__(self, m, store, call, *, workdir=Path('/work'), clock=time.time, sleep=time.sleep, sync_seconds=30,
                 heartbeat_seconds=30, supervisor_wait=900, pod=None):
        self.m, self.store, self.call = validate(m), store, call
        self.workdir, self.clock, self.sleep = Path(workdir), clock, sleep
        self.sync_seconds, self.heartbeat_seconds, self.supervisor_wait = sync_seconds, heartbeat_seconds, supervisor_wait
        self.pod = pod or os.environ.get('NS_CAMPAIGN_POD', 'local')
        self.runner = RUNNERS[m['runner']](m, call)
        self.grace = m.get('heartbeatGraceSeconds', case_supervisor.GRACE_DEFAULT)

    def namespace(self, rid):
        return self.runner.namespace(rid)

    def run(self):
        done = {}
        for case in self.m['cases']:
            done[case['name']] = self.case(case)
        return done

    def case(self, case):
        status = Status(self.store, self.m, case['name'])
        doc = status.read() or {'case': case['name'], 'state': 'queued', 'attempts': []}
        if doc['state'] in FINAL:
            return doc
        if doc['state'] == 'running':
            doc = self.interrupted(case, doc, status)
            if doc['state'] in FINAL:
                return doc
        while True:
            attempt = len(doc['attempts']) + 1
            doc = self.attempt(case, attempt, doc, status)
            if doc['state'] in FINAL:
                return doc

    def interrupted(self, case, doc, status):
        """The controller died during attempt n: its case is cleaned up (by its supervisor, or here when it never got
        one), its uploaded evidence is sealed as interrupted, and the case runs again in a fresh namespace."""
        last = doc['attempts'][-1]
        rid, ns = last['runId'], last['namespace']
        cleanup = self.await_cleanup(rid, ns, released=False)
        note = {'reason': 'controller-interrupted', 'interruptedPod': last.get('controllerPod'), 'resumedBy': self.pod,
                'cleanup': cleanup}
        seal_from_index(self.store, attempt_prefix(self.m['campaign'], case['name'], last['attempt']),
                        {'controller-interrupted.json': jdump(note)})
        last.update(state='UNMEASURED', reason='controller-interrupted', cleanup=cleanup.get('verdict'), sealed=True)
        doc['state'] = 'retry' if len(doc['attempts']) < self.m.get('maxAttempts', 2) else 'UNMEASURED'
        if doc['state'] == 'UNMEASURED':
            doc['reason'] = 'controller-interrupted; attempts exhausted'
        return status.write(doc)

    def attempt(self, case, attempt, doc, status):
        rid = run_id(self.m, case['name'], attempt)
        ns = self.namespace(rid)
        directory = self.workdir / 'cases' / rid
        if directory.exists():
            shutil.rmtree(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        deadline = self.clock() + self.m['caseDeadlineSeconds']
        doc['attempts'].append({'attempt': attempt, 'runId': rid, 'namespace': ns, 'state': 'running',
                                'controllerPod': self.pod, 'startedAt': self.clock(), 'deadline': deadline})
        doc['state'] = 'running'
        status.write(doc)
        uploader = Progressive(self.store, attempt_prefix(self.m['campaign'], case['name'], attempt))
        stop = threading.Event()
        watcher = threading.Thread(target=self.watch, args=(rid, ns, deadline, directory, uploader, stop), daemon=True)
        watcher.start()
        try:
            outcome = self.runner.run(case, rid, ns, directory, deadline)
        except Exception as error:   # the runner's own refusal or a crash: never a pass
            outcome = {'state': 'failed', 'reason': type(error).__name__, 'detail': str(error)[:300]}
        finally:
            stop.set()
            watcher.join(timeout=60)
        cleanup = self.await_cleanup(rid, ns, released=True)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'campaign-cleanup.json').write_bytes(jdump(cleanup))
        (directory / 'campaign-outcome.json').write_bytes(jdump(outcome))
        if cleanup.get('verdict') != 'CLEANED':
            outcome = dict(outcome, state='UNMEASURED' if outcome['state'] == 'scored' else outcome['state'],
                           reason=outcome.get('reason') or 'cleanup unconfirmed')
        uploader.seal(directory, outcome['state'])
        doc['attempts'][-1].update(state=outcome['state'], verdict=outcome.get('verdict'), reason=outcome.get('reason'),
                                   cleanup=cleanup.get('verdict'), endedAt=self.clock(), sealed=True)
        retry = outcome['state'] == 'failed' and outcome.get('retry', False) and attempt < self.m.get('maxAttempts', 2)
        doc['state'] = 'retry' if retry else outcome['state']
        if not retry:
            doc.update(verdict=outcome.get('verdict'), reason=outcome.get('reason'))
        return status.write(doc)

    def watch(self, rid, ns, deadline, directory, uploader, stop):
        """Heartbeat on the case namespace, the supervisor once the namespace exists, and progressive upload."""
        supervised = False
        last_sync = 0
        while not stop.is_set():
            try:
                present = bool(kjson(self.call, ['get', 'namespace', ns, '--ignore-not-found=true']))
                if present:
                    self.call(['annotate', 'namespace', ns, '%s=%d' % (case_supervisor.HEARTBEAT, int(self.clock())), '--overwrite'])
                    if not supervised:
                        self.supervise(rid, ns, deadline)
                        supervised = True
                if self.clock() - last_sync >= self.sync_seconds:
                    uploader.sync(directory)
                    last_sync = self.clock()
            except Exception as error:   # a missed beat or upload is retried; the supervisor bounds the case
                print(json.dumps({'watch': type(error).__name__, 'detail': str(error)[:200]}), file=sys.stderr)
            stop.wait(self.heartbeat_seconds)

    def supervise(self, rid, ns, deadline):
        manifest = case_supervisor.render(ns, rid, self.m['controllerImage'], deadline, CONTROL_NS, grace=self.grace,
                                          cluster_scoped_names=self.runner.cluster_scoped(rid))
        for item in manifest['items']:
            item['metadata'].setdefault('labels', {})[CAMPAIGN_LABEL] = self.m['campaign']
        self.call(['apply', '-f', '-'], json.dumps(manifest))

    def await_cleanup(self, rid, ns, released):
        """The case's cleanup result. With a supervisor: release it (normal end) or let it act on the stale heartbeat
        (interrupted), and read its ConfigMap. Without one (the namespace never appeared, or the controller died before
        applying it): run the one owned delete and absence check here."""
        has_supervisor = bool(kjson(self.call, ['-n', CONTROL_NS, 'get', 'job', 'case-supervisor-' + rid, '--ignore-not-found=true']))
        if not has_supervisor:
            try:
                result = run_cleanup.cleanup(self.call, ns, rid, wait_seconds=120, delete_scoped=True)
                doc = {'verdict': 'CLEANED', 'by': 'controller', **result}
            except run_cleanup.CleanupFailed as error:
                doc = {'verdict': 'FAIL', 'by': 'controller', 'code': 'K8S_CLEANUP_LEFTOVER', 'leftovers': error.leftovers}
            except Exception as error:
                doc = {'verdict': 'FAIL', 'by': 'controller', 'code': str(error)[:120]}
            return doc
        if released and kjson(self.call, ['get', 'namespace', ns, '--ignore-not-found=true']):
            try:
                self.call(['annotate', 'namespace', ns, case_supervisor.RELEASED + '=true', '--overwrite'])
            except subprocess.CalledProcessError:
                pass   # gone meanwhile: the supervisor reads namespace-absent
        end = self.clock() + self.supervisor_wait + (0 if released else self.grace)
        while self.clock() < end:
            cm = kjson(self.call, ['-n', CONTROL_NS, 'get', 'configmap', 'case-cleanup-' + rid, '--ignore-not-found=true'])
            if cm:
                doc = json.loads(cm['data']['result'])
                doc['by'] = 'supervisor'
                self.retire_supervisor(rid)
                return doc
            self.sleep(5)
        return {'verdict': 'UNCONFIRMED', 'by': 'supervisor', 'code': 'SUPERVISOR_RESULT_TIMEOUT'}

    def retire_supervisor(self, rid):
        name = 'case-supervisor-' + rid
        for argv in (['-n', CONTROL_NS, 'delete', 'job', name, '--ignore-not-found=true', '--cascade=foreground'],
                     ['-n', CONTROL_NS, 'delete', 'serviceaccount,role,rolebinding', name, '--ignore-not-found=true'],
                     ['delete', 'clusterrole,clusterrolebinding', name, '--ignore-not-found=true'],
                     ['-n', CONTROL_NS, 'delete', 'configmap', 'case-cleanup-' + rid, '--ignore-not-found=true']):
            self.call(argv)


# ---------------------------------------------------------------- runners

class SyntheticRunner:
    """A stand-in case for kind: a run-labelled namespace, one Pod that works for `seconds`, a small load directory,
    then the runner's own owned cleanup (as lifecycle.py does). `exitCode` != 0 makes the case fail."""

    @staticmethod
    def validate(m):
        need(m.get('synthetic', {}).get('image'), 'SYNTHETIC_IMAGE')

    def __init__(self, m, call):
        self.m, self.call = m, call

    def namespace(self, rid):
        return 'ns-' + rid

    def cluster_scoped(self, rid):
        return ()

    def run(self, case, rid, ns, directory, deadline):
        o = case.get('options', {})
        directory.mkdir(parents=True, exist_ok=True)
        load = directory / 'runtime/packet/load'
        load.mkdir(parents=True)
        self.call(['apply', '-f', '-'], json.dumps({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {
            'name': ns, 'labels': {RUN_LABEL: rid, CAMPAIGN_LABEL: self.m['campaign']}}}))
        seconds, code = int(o.get('seconds', 20)), int(o.get('exitCode', 0))
        script = 'for i in $(seq 1 %d); do echo "{\\"tick\\": $i}"; sleep 1; done; exit %d' % (seconds, code)
        pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'load', 'namespace': ns, 'labels': {RUN_LABEL: rid}},
               'spec': {'restartPolicy': 'Never', 'containers': [{'name': 'load', 'image': self.m['synthetic']['image'],
                        'imagePullPolicy': 'IfNotPresent', 'command': ['sh', '-c', script],
                        'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}}}]}}
        self.call(['apply', '-f', '-'], json.dumps(pod))
        started = time.time()
        (load / 'window.json').write_bytes(jdump({'runId': rid, 'loadStartedAt': started}))
        phase = None
        while time.time() < deadline:
            got = kjson(self.call, ['-n', ns, 'get', 'pod', 'load', '--ignore-not-found=true'])
            phase = (got or {}).get('status', {}).get('phase')
            if phase in ('Succeeded', 'Failed'):
                break
            time.sleep(2)
        (load / 'k6.log').write_text(self.call(['-n', ns, 'logs', 'load'], check=False))
        (load / 'window.json').write_bytes(jdump({'runId': rid, 'loadStartedAt': started, 'loadEndedAt': time.time()}))
        (load / 'k6-summary.json').write_bytes(jdump({'metrics': {'ticks': {'count': len((load / 'k6.log').read_text().splitlines())}}}))
        result = run_cleanup.cleanup(self.call, ns, rid, wait_seconds=120)
        (directory / 'runtime/absence.json').write_bytes(jdump(result))
        if phase == 'Succeeded':
            return {'state': 'scored', 'verdict': 'PASS'}
        return {'state': 'failed', 'reason': 'load-pod-' + str(phase), 'retry': bool(o.get('retryOnFailure'))}


class StandardRunner:
    """The existing path: standard_case (keyed fixture reuse or a fresh case), then `experiment.py launch`, inside the
    controller Pod. Template, deploy and core checkouts are baked into the controller image at the workstation paths
    the template records (controller-image/build.sh), so no case JSON is rewritten except the kube context (in-cluster)
    and the image pull command (a mounted Secret instead of doctl)."""

    @staticmethod
    def validate(m):
        s = m.get('standard') or {}
        need(all(s.get(k) for k in ('template', 'binding', 'core', 'profile')), 'STANDARD_INPUTS')
        for role in ('app', 'postgres'):
            image = (s.get('images') or {}).get(role) or {}
            need(re.search(r'@sha256:[0-9a-f]{64}$', image.get('reference', '')) and
                 re.fullmatch(r'sha256:[0-9a-f]{64}', image.get('imageId', '')), 'STANDARD_IMAGE_' + role.upper())
        need(s.get('fixture', {}).get('action') in (None, 'reuse'), 'STANDARD_FIXTURE_ACTION')

    def __init__(self, m, call):
        self.m, self.call, self.s = m, call, m['standard']

    def namespace(self, rid):
        return self.s.get('namespacePrefix', 'ns-synth-') + rid

    def cluster_scoped(self, rid):
        return ()   # lifecycle's own cleanup deletes the labelled cluster-scoped objects; the supervisor's absence
        # check lists them by label and fails the attempt when any is left

    def inspect(self, reference):
        """docker image inspect, answered from the manifest (the image is not on the controller's node)."""
        for image in self.s['images'].values():
            if image['reference'] == reference:
                return {'Id': image['imageId'], 'Config': {'Labels': {
                    'org.opencontainers.image.revision': image.get('core'), 'org.nightscout.deploy.revision': image.get('deploy')}}}
        raise Refused('CAMPAIGN_IMAGE_NOT_IN_MANIFEST')

    def run(self, case, rid, ns, directory, deadline):
        import standard_case
        o = dict(self.s.get('caseDefaults', {}), **case.get('options', {}))
        inputs = directory.parent / (rid + '.inputs')
        inputs.mkdir(parents=True, exist_ok=True)
        profile = inputs / 'profile.json'
        profile.write_bytes(jdump(o.get('profile') or self.s['profile']))
        extra = None
        if o.get('binding'):
            extra = inputs / 'binding.json'
            extra.write_bytes(jdump(o['binding']))
        options = dict(app_image=self.s['images']['app']['reference'], postgres_image=self.s['images']['postgres']['reference'],
                       namespace_prefix=self.s.get('namespacePrefix', 'ns-synth-'), core=Path(self.s['core']),
                       taint=o.get('taint'), node_name=o.get('nodeName'), node_pool=o.get('nodePool'),
                       binding_extra=extra, inspect=self.inspect)
        fixture = self.s.get('fixture')
        if fixture:
            import fixture_catalog
            catalog = fixture_catalog.Catalog(sync_catalog(self.call, self.workdir_catalog(directory)))
            prepared = standard_case.keyed('reuse', Path(self.s['template']), Path(self.s['binding']), profile, directory,
                                           catalog=catalog, seed=fixture.get('seed', 'default'),
                                           storage_class=fixture.get('storageClass', 'do-block-storage'),
                                           snapshot_class=fixture.get('snapshotClass', 'do-block-storage'),
                                           postgres_size=fixture.get('postgresSize'), launch=self.refuse_seed, **options)
        else:
            prepared = standard_case.prepare(Path(self.s['template']), Path(self.s['binding']), profile, directory, **options)
        (inputs / 'preparation.json').write_bytes(jdump(prepared))
        if o.get('prepareOnly') or self.s.get('prepareOnly'):
            return {'state': 'scored', 'verdict': 'PREPARED', 'reason': 'prepare-only'}
        q = subprocess.run([sys.executable, '-B', str(HERE / 'experiment.py'), 'launch', str(directory / 'lifecycle-bound.json')],
                           timeout=max(60, deadline - time.time()))
        result = directory / 'runtime/packet/experiment/result.json'
        if result.is_file():
            verdict = json.loads(result.read_bytes()).get('verdict')
            if verdict in ('PASS', 'FAIL'):
                return {'state': 'scored', 'verdict': verdict, 'exitCode': q.returncode}
            return {'state': 'UNMEASURED', 'verdict': verdict, 'exitCode': q.returncode,
                    'reason': (json.loads(result.read_bytes()).get('firstFailure') or {}).get('code')}
        return {'state': 'failed', 'exitCode': q.returncode, 'reason': 'no experiment result'}

    def workdir_catalog(self, directory):
        return directory.parent / 'catalog'

    @staticmethod
    def refuse_seed(*args):
        # A campaign restores registered fixtures; a seed is its own reviewed step (catalog-import afterwards).
        raise Refused('CAMPAIGN_FIXTURE_MISS')


RUNNERS = {'synthetic': SyntheticRunner, 'standard': StandardRunner}


# ---------------------------------------------------------------- fixture catalog in bench-control

def catalog_objects(entry_digest, entry, record):
    """A catalog entry as two objects in bench-control: a ConfigMap (key, record, fixture.json) and a Secret
    (secrets.private.json, the seed's Secrets as the seed step captured them from the API)."""
    import fixture_copy
    directory = Path(record['directory'])
    manifest = json.loads((directory / fixture_copy.MANIFEST).read_bytes())
    secrets = (directory / fixture_copy.SECRETS).read_bytes()
    name = 'fixture-' + entry_digest
    labels = {FIXTURE_LABEL: manifest['fixtureId'], 'app.kubernetes.io/name': 'fixture-catalog'}
    cm = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': name, 'namespace': CONTROL_NS, 'labels': labels},
          'data': {'key.json': json.dumps(entry['key'], sort_keys=True),
                   'record.json': json.dumps({k: v for k, v in record.items() if k not in ('directory', 'pid', 'digest')}, sort_keys=True),
                   fixture_copy.MANIFEST: json.dumps(manifest, sort_keys=True, indent=1)}}
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
              'metadata': {'name': name, 'namespace': CONTROL_NS, 'labels': labels},
              'data': {fixture_copy.SECRETS: base64.b64encode(secrets).decode()}}
    return cm, secret


def catalog_import(entry_digest, catalog_path, call):
    import fixture_catalog
    catalog = fixture_catalog.Catalog(catalog_path)
    entry = catalog.entries().get(entry_digest)
    need(entry, 'FIXTURE_NOT_IN_CATALOG')
    record = entry['platforms'].get('kubernetes')
    need(record and record.get('status') == 'ready', 'FIXTURE_NOT_READY')
    for obj in catalog_objects(entry_digest, entry, record):
        call(['apply', '-f', '-'], json.dumps(obj))
    return {'imported': 'fixture-' + entry_digest, 'fixtureId': entry_digest}


def sync_catalog(call, root):
    """Materialize the in-cluster catalog as the ordinary local catalog file + fixture directories, so fixture_catalog
    and fixture_copy run unchanged in the controller Pod. Returns the catalog path."""
    import fixture_catalog
    import fixture_copy
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(mode=0o700, parents=True)
    os.chmod(root, 0o700)
    data = {'version': 1, 'entries': {}}
    cms = kjson(call, ['-n', CONTROL_NS, 'get', 'configmap', '-l', 'app.kubernetes.io/name=fixture-catalog'])['items']
    for cm in cms:
        name = cm['metadata']['name']
        digest = name[len('fixture-'):]
        key = json.loads(cm['data']['key.json'])
        need(fixture_catalog.digest(key) == digest, 'FIXTURE_DIGEST_MISMATCH')
        secret = kjson(call, ['-n', CONTROL_NS, 'get', 'secret', name])
        directory = root / 'kubernetes' / digest
        directory.mkdir(mode=0o700, parents=True)
        for fname, body in ((fixture_copy.MANIFEST, cm['data'][fixture_copy.MANIFEST].encode()),
                            (fixture_copy.SECRETS, base64.b64decode(secret['data'][fixture_copy.SECRETS]))):
            fd = os.open(directory / fname, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(body)
        record = dict(json.loads(cm['data']['record.json']), directory=str(directory), status='ready')
        data['entries'][digest] = {'key': key, 'platforms': {'kubernetes': record}}
    path = root / 'catalog.json'
    path.write_bytes(jdump(data))
    os.chmod(path, 0o600)
    return path


# ---------------------------------------------------------------- collect / close / census

def statuses(store, campaign):
    out = {}
    for obj in store.list(campaign + '/cases/'):
        if obj['key'].endswith('/status.json'):
            out[obj['key'].split('/')[2]] = json.loads(store.get(obj['key']))
    return out


def collect(store, campaign, out, case=None):
    """Fetch every finished case (or one), verify each sealed attempt against its seal locally, then delete exactly the
    verified objects. An object that is not part of a verified seal stays in the store (and in the census)."""
    out = Path(out)
    report = {'campaign': campaign, 'collected': {}, 'pending': [], 'failures': {}, 'kept': []}
    for name, doc in sorted(statuses(store, campaign).items()):
        if case and name != case:
            continue
        if doc['state'] not in FINAL:
            report['pending'].append(name)
            continue
        objects = {o['key'] for o in store.list(case_prefix(campaign, name))}
        verified_keys = set()
        for attempt in doc['attempts']:
            pfx = attempt_prefix(campaign, name, attempt['attempt'])
            if pfx + packet_seal.SEAL not in objects:
                if any(k.startswith(pfx) for k in objects):
                    report['failures'].setdefault(name, []).append({'attempt': attempt['attempt'], 'code': 'ATTEMPT_UNSEALED'})
                continue
            seal = json.loads(store.get(pfx + packet_seal.SEAL))
            target = out / name / ('attempt-%d' % attempt['attempt'])
            staging = target.with_name(target.name + '.partial')
            if staging.exists():
                shutil.rmtree(staging)
            (staging / 'files').mkdir(parents=True)
            for rel in seal['files']:
                key = pfx + packet_seal.FILES + rel
                if key not in objects:
                    continue   # verify() reports it missing
                path = staging / 'files' / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(store.get(key))
            try:
                packet_seal.verify(staging / 'files', seal)
            except packet_seal.SealError as error:
                report['failures'].setdefault(name, []).append({'attempt': attempt['attempt'], 'code': error.code, 'files': error.files})
                continue
            (staging / packet_seal.SEAL).write_bytes(jdump(seal))
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
            verified_keys |= {pfx + packet_seal.FILES + rel for rel in seal['files']} | {pfx + packet_seal.SEAL, pfx + 'INDEX.json'}
        (out / name).mkdir(parents=True, exist_ok=True)
        (out / name / 'status.json').write_bytes(jdump(doc))
        for key in sorted(verified_keys & objects):
            store.delete(key)
        left = sorted(objects - verified_keys - {case_prefix(campaign, name) + 'status.json'})
        if not left and name not in report['failures']:
            store.delete(case_prefix(campaign, name) + 'status.json')
            report['collected'][name] = doc['state']
        else:
            report['kept'] += left
    if not case and not report['pending'] and not report['failures']:
        key = prefix(campaign) + 'campaign.json'
        if any(o['key'] == key for o in store.list(key)):
            (out / 'campaign.json').write_bytes(store.get(key))
            store.delete(key)
    return report


def close(m, store, call):
    """Remove the campaign's controller objects, then delete the bucket, which must be empty (collect first)."""
    c, name = m['campaign'], controller_name(m)
    left = store.list('') if store.bucket_exists() else []
    need(not left, 'BUCKET_NOT_EMPTY:%d' % len(left))
    for argv in (['-n', CONTROL_NS, 'delete', 'job', '-l', CAMPAIGN_LABEL + '=' + c, '--ignore-not-found=true', '--cascade=foreground', '--wait=true'],
                 ['-n', CONTROL_NS, 'delete', 'configmap,secret,serviceaccount,role,rolebinding', '-l', CAMPAIGN_LABEL + '=' + c, '--ignore-not-found=true'],
                 ['delete', 'clusterrolebinding,clusterrole', '-l', CAMPAIGN_LABEL + '=' + c, '--ignore-not-found=true'],
                 ['delete', 'validatingadmissionpolicybinding,validatingadmissionpolicy', name, '--ignore-not-found=true']):
        call(argv)
    if store.bucket_exists():
        # Re-checked after the controller is gone: it could have written between the first check and its deletion.
        left = store.list('')
        need(not left, 'BUCKET_NOT_EMPTY_AFTER_STOP:%d' % len(left))
        store.delete_bucket()
    return census(m, store, call)


def census(m, store, call, doctl=None, doctl_cluster=None):
    """Everything billable or campaign-owned that still exists. Empty means nothing of this campaign keeps billing.
    Fixture snapshots registered in the catalog are listed apart (`retainedByFixture`): they outlive campaigns on
    purpose and end with `fixture_copy.py delete`."""
    c = m['campaign']
    rows = {}
    if store.bucket_exists():
        objects = store.list('')
        rows['bucket'] = [{'bucket': store.bucket, 'objects': len(objects), 'bytes': sum(o['bytes'] for o in objects)}]
    runs = lambda items: [i for i in items if (i['metadata'].get('labels') or {}).get(RUN_LABEL, '').startswith(c + '-')]
    namespaces = runs(kjson(call, ['get', 'namespaces', '-l', RUN_LABEL])['items'])
    names = {n['metadata']['name'] for n in namespaces}
    rows['namespaces'] = sorted(names)
    rows['persistentVolumeClaims'] = sorted('%s/%s' % (p['metadata']['namespace'], p['metadata']['name'])
                                            for p in kjson(call, ['get', 'pvc', '-A'])['items'] if p['metadata']['namespace'] in names)
    rows['persistentVolumes'] = sorted(p['metadata']['name'] for p in kjson(call, ['get', 'pv'])['items']
                                       if ((p['spec'].get('claimRef') or {}).get('namespace') in names)
                                       or (p['metadata'].get('labels') or {}).get(RUN_LABEL, '').startswith(c + '-'))
    rows['loadBalancers'] = sorted('%s/%s' % (s['metadata']['namespace'], s['metadata']['name'])
                                   for s in kjson(call, ['get', 'services', '-A'])['items']
                                   if s['spec'].get('type') == 'LoadBalancer' and
                                   (s['metadata']['namespace'] in names or (s['metadata'].get('labels') or {}).get(CAMPAIGN_LABEL) == c))
    try:
        contents = kjson(call, ['get', 'volumesnapshotcontents'])['items']
    except subprocess.CalledProcessError:
        contents = []   # no snapshot CRD (kind without the snapshotter): nothing to bill
    retained = [x for x in contents if (x['metadata'].get('labels') or {}).get(FIXTURE_LABEL)]
    rows['volumeSnapshotContents'] = sorted(x['metadata']['name'] for x in runs(contents) if x not in retained)
    owned = []
    if kjson(call, ['get', 'namespace', CONTROL_NS, '--ignore-not-found=true']):
        for kind in ('jobs', 'pods', 'configmaps', 'secrets', 'serviceaccounts', 'roles', 'rolebindings'):
            owned += ['%s/%s' % (kind, i['metadata']['name'])
                      for i in kjson(call, ['-n', CONTROL_NS, 'get', kind, '-l', CAMPAIGN_LABEL + '=' + c])['items']]
    for kind in ('clusterroles', 'clusterrolebindings', 'validatingadmissionpolicies', 'validatingadmissionpolicybindings'):
        owned += ['%s/%s' % (kind, i['metadata']['name']) for i in kjson(call, ['get', kind, '-l', CAMPAIGN_LABEL + '=' + c])['items']]
    rows['controlObjects'] = sorted(owned)
    if doctl and doctl_cluster:
        pools = json.loads(doctl(['kubernetes', 'cluster', 'node-pool', 'list', doctl_cluster, '-o', 'json']))
        rows['nodePools'] = sorted(p['name'] for p in pools if p['name'] in set(m.get('nodePools', [])))
        volumes = json.loads(doctl(['compute', 'volume', 'list', '-o', 'json']))
        rows['unattachedVolumes'] = sorted(v['name'] for v in volumes if not v.get('droplet_ids') and v['name'].startswith('pvc-'))
        lbs = json.loads(doctl(['compute', 'load-balancer', 'list', '-o', 'json']))
        rows['providerLoadBalancers'] = sorted(lb['name'] for lb in lbs if lb.get('name', '').startswith(c))
    rows = {k: v for k, v in rows.items() if v}
    return {'campaign': c, 'empty': not rows, 'billable': rows,
            'retainedByFixture': sorted(x['metadata']['name'] for x in retained)}


def rescore(directory):
    import capacity_results
    out = {}
    for packet in sorted(Path(directory).glob('*/attempt-*/files/**/capacity-results')):
        try:
            out[str(packet.relative_to(directory))] = capacity_results.rescore(packet)
        except (OSError, KeyError, ValueError) as error:
            out[str(packet.relative_to(directory))] = {'verdict': 'UNMEASURED', 'reason': str(error)[:200]}
    return out


# ---------------------------------------------------------------- CLI

def store_for(m=None, bucket=None):
    env = dict(os.environ)
    if m:
        env.setdefault('NS_EVIDENCE_ENDPOINT', m['store']['endpoint'])
        env.setdefault('NS_EVIDENCE_REGION', m['store'].get('region', 'us-east-1'))
        env.setdefault('NS_EVIDENCE_ADDRESSING', m['store'].get('addressing', 'virtual'))
    return evidence_store.Store.from_env(env, bucket=bucket or (m['store']['bucket'] if m else None))


def in_cluster_kubeconfig(path, context):
    """kubectl in the Pod with a named context (lifecycle passes --context); the token file is re-read by kubectl."""
    sa = Path('/var/run/secrets/kubernetes.io/serviceaccount')
    host, port = os.environ['KUBERNETES_SERVICE_HOST'], os.environ['KUBERNETES_SERVICE_PORT']
    config = {'apiVersion': 'v1', 'kind': 'Config', 'current-context': context,
              'clusters': [{'name': 'in-cluster', 'cluster': {'server': 'https://%s:%s' % (host, port),
                                                              'certificate-authority': str(sa / 'ca.crt')}}],
              'users': [{'name': 'controller', 'user': {'tokenFile': str(sa / 'token')}}],
              'contexts': [{'name': context, 'context': {'cluster': 'in-cluster', 'user': 'controller'}}]}
    Path(path).write_text(json.dumps(config))
    os.chmod(path, 0o600)
    os.environ['KUBECONFIG'] = str(path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='action', required=True)
    a = s.add_parser('apply'); a.add_argument('manifest', type=Path); a.add_argument('--context'); a.add_argument('--create-bucket', action='store_true')
    a = s.add_parser('render'); a.add_argument('manifest', type=Path)
    a = s.add_parser('controller'); a.add_argument('manifest', type=Path)
    for name in ('status', 'census', 'close'):
        a = s.add_parser(name); a.add_argument('manifest', type=Path, help='the campaign manifest (or the collected campaign.json)')
        a.add_argument('--context')
        if name == 'census':
            a.add_argument('--doctl-cluster', help='also list node pools, unattached pvc volumes and load balancers (read-only doctl)')
    a = s.add_parser('collect'); a.add_argument('manifest', type=Path); a.add_argument('--out', type=Path, required=True); a.add_argument('--case')
    a = s.add_parser('rescore'); a.add_argument('directory', type=Path)
    a = s.add_parser('catalog-import'); a.add_argument('digest'); a.add_argument('--catalog', type=Path); a.add_argument('--context')
    a = p.parse_args(argv)
    if a.action == 'rescore':
        return rescore(a.directory)
    if a.action == 'catalog-import':
        return catalog_import(a.digest, a.catalog, kubectl_caller(a.context))
    m = validate(json.loads(a.manifest.read_bytes()))
    if a.action == 'render':
        return render(m)
    if a.action == 'apply':
        return apply(m, kubectl_caller(a.context), create_bucket=a.create_bucket, store=store_for(m))
    if a.action == 'controller':
        if os.environ.get('KUBERNETES_SERVICE_HOST'):
            in_cluster_kubeconfig('/work/kubeconfig', m.get('standard', {}).get('context', 'in-cluster'))
        return Controller(m, store_for(m), kubectl_caller(), sync_seconds=m.get('syncSeconds', 30),
                          heartbeat_seconds=m.get('heartbeatSeconds', 30)).run()
    store = store_for(m)
    if a.action == 'status':
        return statuses(store, m['campaign'])
    if a.action == 'collect':
        report = collect(store, m['campaign'], a.out, a.case)
        if report['failures']:
            print(json.dumps(report, indent=1, sort_keys=True))
            sys.exit(2)
        return report
    if a.action == 'close':
        return close(m, store, kubectl_caller(a.context))
    doctl = (lambda argv: subprocess.check_output(['doctl', *argv], text=True, timeout=60)) if a.doctl_cluster else None
    result = census(m, store, kubectl_caller(a.context), doctl, a.doctl_cluster)
    print(json.dumps(result, indent=1, sort_keys=True))
    sys.exit(0 if result['empty'] else 1)


if __name__ == '__main__':
    try:
        out = main()
        if out is not None:
            print(json.dumps(out, indent=1, sort_keys=True, default=str))
    except (Refused, evidence_store.StoreError, ValueError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        sys.exit(3)
