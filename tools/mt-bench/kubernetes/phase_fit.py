"""Explicit provision-before-serving request peaks and positive retirement proof.

This module has no cluster mutation path. Full namespace requests, quotas and
native grants remain separate from the per-node peak used for admission.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

import resource_budget

CONTRACT = 'provision-before-serving-v1'
FIELD = 'resourcePhasePlan'
STORES = ('StatefulSet/postgres', 'StatefulSet/vault')
PROVISION = 'Job/provision'
LATER = ('Deployment/admin', 'Job/primer', 'StatefulSet/cohort',
         'Deployment/edge', 'Deployment/pgstream', 'Deployment/ui')
PARTITION = {'stores': STORES, 'provision': (PROVISION,),
             'private-admin': ('Deployment/admin',), 'primer': ('Job/primer',),
             'serving': ('StatefulSet/cohort', 'Deployment/edge', 'Deployment/pgstream', 'Deployment/ui')}
DIMS = ('millicpus', 'memoryBytes', 'ephemeralBytes')


def require(ok, code):
    if not ok:
        raise ValueError('K8S_PHASE_' + code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def selection(value, need=require):
    if FIELD not in value:
        return None
    chosen = value[FIELD]
    need(chosen == {'contract': CONTRACT}, 'SELECTION')
    return copy.deepcopy(chosen)


def key(obj):
    return obj['kind'] + '/' + obj['metadata']['name']


def objects(tree):
    if isinstance(tree, list):
        for value in tree:
            yield from objects(value)
    elif isinstance(tree, dict):
        if tree.get('kind') == 'List':
            yield from objects(tree.get('items', []))
        elif 'kind' in tree and 'apiVersion' in tree:
            yield tree
        else:
            for value in tree.values():
                yield from objects(value)


def template(obj):
    return obj['spec']['template']['spec']


def job_policy(job, need=require):
    spec = job['spec']; pod = template(job)
    need(job['kind'] == 'Job' and job['metadata']['name'] == 'provision', 'PROVISION_KIND')
    need(not pod.get('ephemeralContainers'), 'PROVISION_EXTRA_CONTAINER')
    need(spec.get('parallelism', 1) == spec.get('completions', 1) == 1
         and type(spec.get('parallelism', 1)) is int and type(spec.get('completions', 1)) is int
         and spec.get('backoffLimit') == 0 and type(spec.get('backoffLimit')) is int
         and not spec.get('suspend', False) and not spec.get('manualSelector', False)
         and spec.get('managedBy') in (None, 'kubernetes.io/job-controller')
         and spec.get('completionMode', 'NonIndexed') == 'NonIndexed'
         and pod.get('restartPolicy') == 'Never', 'PROVISION_POLICY')
    containers = pod.get('initContainers', []) + pod.get('containers', [])
    names = [c['name'] for c in containers]
    need(containers and len(names) == len(set(names)) and
         all(c.get('restartPolicy') is None for c in containers), 'PROVISION_CONTAINERS')
    return {'parallelism': 1, 'completions': 1, 'backoffLimit': 0,
            'restartPolicy': 'Never', 'containers': names}


def retained_volumes(spec, need=require):
    """Keep tmpfs/local disk distinct; file-cache residency is a sensitivity."""
    volumes = {}
    for volume in spec.get('volumes', []):
        if 'emptyDir' not in volume:
            continue
        selected = volume['emptyDir']
        need(selected.get('medium', '') in ('', 'Memory') and 'sizeLimit' in selected,
             'RETAINED_VOLUME_BOUND')
        size = resource_budget.quantity(selected['sizeLimit'], False, need)
        need(size > 0 and volume['name'] not in volumes, 'RETAINED_VOLUME_BOUND')
        volumes[volume['name']] = {'medium': selected.get('medium', ''), 'bytes': size}
    disk = sum(v['bytes'] for v in volumes.values() if v['medium'] != 'Memory')
    return {'volumes': volumes, 'diskCacheSensitivityBytes': disk,
            'allowance': {'millicpus': 0,
            'memoryBytes': sum(v['bytes'] for v in volumes.values() if v['medium'] == 'Memory'),
            'ephemeralBytes': disk}}


def _default(path, name, value):
    """Only explicit API defaults may disappear from a live source comparison."""
    pod = {'dnsPolicy': 'ClusterFirst', 'schedulerName': 'default-scheduler',
           'terminationGracePeriodSeconds': 30, 'enableServiceLinks': True,
           'priority': 0, 'preemptionPolicy': 'PreemptLowerPriority',
           'securityContext': {}, 'hostNetwork': False, 'hostPID': False, 'hostIPC': False}
    container = {'terminationMessagePath': '/dev/termination-log', 'terminationMessagePolicy': 'File',
                 'imagePullPolicy': 'IfNotPresent', 'stdin': False, 'stdinOnce': False, 'tty': False,
                 'command': [], 'args': [], 'securityContext': {}}
    probe = {'failureThreshold': 3, 'successThreshold': 1, 'timeoutSeconds': 1,
             'periodSeconds': 10, 'initialDelaySeconds': 0}
    defaults = pod if not path else container if path in (('containers', '*'), ('initContainers', '*')) else {}
    if path and path[-1] in ('startupProbe', 'readinessProbe', 'livenessProbe'):defaults = probe
    if path and path[-1] == 'fieldRef':defaults = {'apiVersion': 'v1'}
    if path and path[-1] in ('secretKeyRef', 'configMapKeyRef', 'secretRef', 'configMapRef'):
        defaults = {'optional': False}
    if path and path[-1] in ('secret', 'configMap'):defaults = {'optional': False, 'defaultMode': 420}
    if path and path[-1] == 'projected':defaults = {'defaultMode': 420}
    if path and path[-1] == 'emptyDir':defaults = {'medium': ''}
    if len(path) >= 2 and path[-2:] == ('ports', '*'):defaults = {'protocol': 'TCP'}
    if len(path) >= 2 and path[-2:] == ('volumeMounts', '*'):
        defaults = {'readOnly': False, 'mountPropagation': 'None'}
    if len(path) >= 2 and path[-2:] == ('env', '*'):defaults = {'value': ''}
    if path and path[-1] == 'httpGet':defaults = {'scheme': 'HTTP'}
    return name in defaults and type(value) is type(defaults[name]) and value == defaults[name]


def _normalize_defaults(expected, actual, path=()):
    if isinstance(expected, dict) and isinstance(actual, dict):
        value = copy.deepcopy(actual)
        for name in list(value):
            if name in expected:
                value[name] = _normalize_defaults(expected[name], value[name], path + (name,))
            elif _default(path, name, value[name]):
                del value[name]
        return value
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [_normalize_defaults(a, b, path + ('*',)) for a, b in zip(expected, actual)]
    return copy.deepcopy(actual)


def source_projection(expected, actual, need=require):
    """Normalize API additions, then leave all executable and source facts visible."""
    value = resource_budget.readback_projection(expected, actual, need)
    # Match the existing adapter's narrowly permitted service-account projection.
    declared = {v['name'] for v in expected.get('volumes', [])}
    extra = [v for v in value.get('volumes', []) if v['name'] not in declared]
    admitted = set()
    for volume in extra:
        sources = volume.get('projected', {}).get('sources', [])
        need(expected.get('automountServiceAccountToken') is not False and
             volume['name'].startswith('kube-api-access-') and sources and
             all(set(s) <= {'serviceAccountToken', 'configMap', 'downwardAPI'} for s in sources),
             'UNEXPECTED_ADMISSION_VOLUME')
        admitted.add(volume['name'])
    if admitted:
        value['volumes'] = [v for v in value['volumes'] if v['name'] not in admitted]
        for container in value.get('containers', []) + value.get('initContainers', []):
            mounts = container.get('volumeMounts', [])
            removed = [v for v in mounts if v['name'] in admitted]
            need(all(v.get('mountPath') == '/var/run/secrets/kubernetes.io/serviceaccount' and
                     v.get('readOnly') is True for v in removed), 'UNEXPECTED_ADMISSION_VOLUME')
            if removed:
                container['volumeMounts'] = [v for v in mounts if v['name'] not in admitted]
                if not container['volumeMounts']:container.pop('volumeMounts')
    # Kubernetes retains the deprecated serviceAccount alias on a live Pod.
    account = expected.get('serviceAccountName', 'default')
    if 'serviceAccount' not in expected and value.get('serviceAccount') == account:value.pop('serviceAccount')
    if 'serviceAccountName' not in expected and value.get('serviceAccountName') == 'default':value.pop('serviceAccountName')
    # The two default admission tolerations are mutable scheduling metadata.
    authored = expected.get('tolerations', [])
    if 'tolerations' in value:
        def standard(row):
            return row in ({'key': 'node.kubernetes.io/'+reason, 'operator': 'Exists',
                            'effect': 'NoExecute', 'tolerationSeconds': 300} for reason in ('not-ready', 'unreachable'))
        value['tolerations'] = [r for r in value['tolerations'] if r in authored or not standard(r)]
        if not value['tolerations'] and 'tolerations' not in expected:value.pop('tolerations')
    for left, right in zip(expected.get('volumes', []), value.get('volumes', [])):
        if 'emptyDir' in left and 'emptyDir' in right and 'sizeLimit' in left['emptyDir']:
            want = left['emptyDir']['sizeLimit'];got = right['emptyDir'].get('sizeLimit')
            if got is not None and resource_budget.quantity(want, False, need) == resource_budget.quantity(got, False, need):
                right['emptyDir']['sizeLimit'] = want
    return _normalize_defaults(expected, value)


def source_metadata(expected, actual, need=require):
    # UID/resourceVersion/generated names and extra controller metadata are not source.
    for field in ('labels', 'annotations'):
        need(isinstance(actual.get(field, {}), dict) and
             all(actual.get(field, {}).get(k) == v for k, v in expected.get(field, {}).items()),
             'SOURCE_METADATA_CHANGED')


def projection(environment, objects, need=require):
    chosen = selection(environment, need)
    if chosen is None:
        return None
    mode = resource_budget.selection(environment, need)
    workloads = [o for o in objects if o['kind'] in ('Job', 'Deployment', 'StatefulSet')]
    by_key = {key(o): o for o in workloads}
    need(len(by_key) == len(workloads) and set(by_key) == set(STORES + (PROVISION,) + LATER),
         'WORKLOAD_PARTITION')
    job_policy(by_key[PROVISION], need)
    facts = {}; phases = {'provision': STORES + (PROVISION,), 'serving': STORES + LATER}
    for name, obj in by_key.items():
        spec = template(obj)
        need(isinstance(spec.get('nodeName'), str) and spec['nodeName'], 'PLACEMENT')
        if obj['kind'] != 'Job':
            need(obj['spec'].get('replicas') == 1, 'REPLICAS')
        facts[name] = {'node': spec['nodeName'],
                       'budget': resource_budget.pod_budget(spec, mode, need),
                       'resources': {c['name']: c.get('resources', {}) for c in
                                     spec.get('initContainers', []) + spec['containers']},
                       'authoredTemplate': copy.deepcopy(obj['spec']['template']),
                       'overhead': spec.get('overhead', {}),
                       **({'policy': job_policy(obj, need), 'retained': retained_volumes(spec, need)}
                          if name == PROVISION else {})}
    nodes = {}
    for node in sorted({v['node'] for v in facts.values()}):
        members = sorted(k for k, v in facts.items() if v['node'] == node)
        total = lambda names: {d: sum(facts[n]['budget'][d] for n in names) for d in DIMS}
        selected = {phase: [n for n in names if n in members] for phase, names in phases.items()}
        budgets = {phase: total(names) for phase, names in selected.items()}
        retained = {phase: dict.fromkeys(DIMS, 0) for phase in phases}
        if PROVISION in members:
            retained['serving'] = facts[PROVISION]['retained']['allowance']
        nodes[node] = {'workloads': members, 'full': total(members), 'phases': budgets,
                       'phaseWorkloads': selected, 'retained': retained,
                       'diskCacheSensitivityBytes': facts[PROVISION]['retained']['diskCacheSensitivityBytes']
                           if PROVISION in members else 0,
                       'peak': {d: max(b[d] + retained[p][d] for p, b in budgets.items()) for d in DIMS}}
    return {'contract': CONTRACT, 'resourceAccounting': mode, 'workloadSha256': digest(facts),
            'nodes': nodes, 'partition': {k: list(v) for k, v in PARTITION.items()},
            'scope': 'Declared phase request/limit peaks plus retained bounded tmpfs/local-disk allowances; disk file-cache residency is a separate sensitivity, not an added pinned-memory quota. Not observed use, reservation or capacity acceptance.'}


def staged_projection(environment, rendered, stages, need=require):
    plan = projection(environment, rendered, need)
    if plan is None:
        return None
    for stage, docs in stages.items():
        actual = [key(o) for o in docs if o['kind'] in ('Job', 'Deployment', 'StatefulSet')]
        need(len(actual) == len(set(actual)) and set(actual) == set(PARTITION.get(stage, ())),
             'STAGE_PARTITION')
    all_objects = [o for docs in stages.values() for o in docs]
    staged = projection(environment, all_objects, need)
    need(staged['nodes'] == plan['nodes'], 'STAGE_RESOURCES_CHANGED')
    need(staged == plan, 'STAGE_SOURCE_CHANGED')
    return plan


def native_budget(value):
    return {'cpu': value['millicpus'] / 1000, 'memory': value['memoryBytes'],
            'ephemeral-storage': value['ephemeralBytes']}


def equivalent(left, right):
    return set(left) == set(right) and all(type(left[k]) in (int, float)
        and type(right[k]) in (int, float) and math.isfinite(left[k]) and math.isfinite(right[k])
        and math.isclose(left[k], right[k], rel_tol=1e-12, abs_tol=1e-9) for k in left)


def decorate(trial, environment, objects, need=require):
    """Keep the full grant and add separately computed fit peaks."""
    plan = projection(environment, objects, need)
    if plan is None:
        return trial
    group = 'requests' if plan['resourceAccounting'] == 'requests-v1' else 'limits'
    need(set(trial['placementEnvelopes']) == set(plan['nodes']), 'PLACEMENT_CHANGED')
    trial[FIELD] = plan
    for node, row in plan['nodes'].items():
        full = trial['placementEnvelopes'][node]
        need(equivalent(full[group], native_budget(row['full'])), 'FULL_GRANT_CHANGED')
        full['phaseAdmission'] = {'contract': CONTRACT, 'workloadSha256': plan['workloadSha256'],
                                  'full': copy.deepcopy(full[group]),
                                  'phases': {p: native_budget(v) for p, v in row['phases'].items()},
                                  'retained': {p: native_budget(v) for p, v in row['retained'].items()},
                                  'peak': native_budget(row['peak'])}
    if len(plan['nodes']) == 1:
        trial['phaseAdmission'] = copy.deepcopy(next(iter(trial['placementEnvelopes'].values()))['phaseAdmission'])
    return trial


def fit_budget(trial, full, need=require):
    chosen = trial.get('phaseAdmission')
    if chosen is None:
        return full
    need(isinstance(chosen, dict) and chosen.get('contract') == CONTRACT and
         isinstance(chosen.get('workloadSha256'), str) and len(chosen['workloadSha256']) == 64,
         'FIT_PLAN')
    need(equivalent(chosen['full'], full) and set(chosen['phases']) == {'provision', 'serving'},
         'FIT_FULL_GRANT_CHANGED')
    phases = chosen['phases']; peak = chosen['peak']; retained = chosen.get('retained')
    need(set(peak) == set(full) and all(set(v) == set(full) for v in phases.values()) and
         all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= full[d]
             for row in phases.values() for d, v in row.items()), 'FIT_PHASE_BUDGET')
    need(isinstance(retained, dict) and set(retained) == set(phases)
         and all(set(v) == set(full) for v in retained.values())
         and all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                 for row in retained.values() for v in row.values()), 'FIT_RETAINED_BOUND')
    need(equivalent(peak, {d: max(v[d] + retained[p][d] for p, v in phases.items()) for d in full}),
         'FIT_PEAK_CHANGED')
    return copy.deepcopy(peak)


def terminal(expected, job, pods, namespace_uid, run_id, previous=None, need=require):
    """Absence alone never establishes retirement; an exact proof may outlive a Pod."""
    policy = job_policy(expected, need)
    need(isinstance(namespace_uid, str) and namespace_uid, 'NAMESPACE_UID')
    need(job is not None and job_policy(job, need) == policy, 'JOB_POLICY_CHANGED')
    need(source_projection(template(expected), template(job), need) == template(expected), 'JOB_SOURCE_CHANGED')
    source_metadata(expected['spec']['template'].get('metadata', {}),
                    job['spec']['template'].get('metadata', {}), need)
    need(template(job).get('nodeName') == template(expected).get('nodeName') and
         retained_volumes(template(job), need) == retained_volumes(template(expected), need),
         'JOB_RESOURCES_CHANGED')
    metadata = job['metadata']; namespace = expected['metadata']['namespace']
    need(metadata.get('namespace') == namespace and metadata.get('uid') and
         metadata.get('labels', {}).get('nightscout.org/run-id') == run_id and
         not metadata.get('deletionTimestamp'), 'JOB_OWNERSHIP')
    status = job.get('status', {})
    conditions = [r for r in status.get('conditions', []) if r.get('type') == 'Complete' and r.get('status') == 'True']
    need(len(conditions) == 1 and conditions[0].get('lastTransitionTime') and status.get('completionTime')
         and status.get('succeeded') == 1 and type(status.get('succeeded')) is int
         and all(status.get(n, 0) == 0 for n in ('active', 'failed', 'terminating'))
         and not any(status.get('uncountedTerminatedPods', {}).values())
         and not any(r.get('type') == 'Failed' and r.get('status') == 'True' for r in status.get('conditions', [])),
         'JOB_NOT_COMPLETE')
    owned = [p for p in pods if p['metadata'].get('labels', {}).get('job-name') == 'provision' or
             any(r.get('kind') == 'Job' and (r.get('uid') == metadata['uid'] or r.get('name') == 'provision')
                 for r in p['metadata'].get('ownerReferences', []))]
    need(len(owned) <= 1, 'PROVISION_POD_ROSTER')
    proof = {'version': 1, 'contract': CONTRACT, 'namespaceUid': namespace_uid, 'jobUid': metadata['uid'],
             'completionTime': status['completionTime'], 'completeTransitionTime': conditions[0]['lastTransitionTime'],
             'policy': policy, 'sourceTemplateSha256': digest(expected['spec']['template'])}
    if owned:
        pod = owned[0]; meta = pod['metadata']
        need(not pod['spec'].get('ephemeralContainers') and
             not pod.get('status', {}).get('ephemeralContainerStatuses'), 'PROVISION_EXTRA_CONTAINER')
        refs = [r for r in meta.get('ownerReferences', []) if r.get('controller') is True]
        need(meta.get('namespace') == namespace and meta.get('uid') and not meta.get('deletionTimestamp')
             and meta.get('labels', {}).get('nightscout.org/run-id') == run_id
             and len(refs) == 1 and refs[0].get('kind') == 'Job' and refs[0].get('name') == 'provision'
             and refs[0].get('uid') == metadata['uid'] and pod.get('status', {}).get('phase') == 'Succeeded',
             'POD_NOT_TERMINAL')
        need(source_projection(template(expected), pod['spec'], need) == template(expected), 'POD_SOURCE_CHANGED')
        source_metadata(expected['spec']['template'].get('metadata', {}), meta, need)
        need(pod['spec'].get('nodeName') == template(expected).get('nodeName') and
             retained_volumes(pod['spec'], need) == retained_volumes(template(expected), need),
             'POD_RESOURCES_CHANGED')
        states = pod['status'].get('initContainerStatuses', []) + pod['status'].get('containerStatuses', [])
        need(len(states) == len(policy['containers']) and {r['name'] for r in states} == set(policy['containers']),
             'CONTAINER_ROSTER')
        containers = {}
        for state in states:
            ended = state.get('state', {}).get('terminated', {})
            need(set(state.get('state', {})) == {'terminated'} and state.get('containerID')
                 and type(state.get('restartCount')) is int and state['restartCount'] == 0
                 and type(ended.get('exitCode')) is int and ended['exitCode'] == 0 and ended.get('finishedAt')
                 and not state.get('lastState', {}).get('terminated'), 'CONTAINER_NOT_TERMINAL')
            containers[state['name']] = {'containerId': state['containerID'], 'restartCount': 0,
                                         'exitCode': 0, 'finishedAt': ended['finishedAt']}
        proof['pod'] = {'name': meta['name'], 'uid': meta['uid'], 'containers': containers}
    else:
        need(previous is not None, 'TERMINAL_PROOF_MISSING')
        proof['pod'] = copy.deepcopy(previous['pod'])
    if previous is not None:
        need(proof == previous, 'TERMINAL_PROOF_CHANGED')
    return proof


def reference(value, need=require):
    need(isinstance(value, dict) and set(value) == {'path', 'sha256'}, 'RECEIPT_REFERENCE')
    path = Path(value['path'])
    need(path.is_absolute() and path.is_file() and not path.is_symlink()
         and hashlib.sha256(path.read_bytes()).hexdigest() == value['sha256'], 'RECEIPT_CHANGED')
    return json.loads(path.read_bytes())


def runtime_binding(c, docs, need=require):
    if FIELD not in c:
        return None
    binding = c[FIELD]
    need(isinstance(binding, dict) and set(binding) == {'plan', 'retirement'}, 'RUNTIME_BINDING')
    environment = {FIELD: {'contract': CONTRACT}, 'resourceAccounting': c.get('resourceAccounting', 'limits-v1')}
    plan = projection(environment, docs, need)
    need(binding['plan'] == plan, 'RUNTIME_PLAN_CHANGED')
    proof = reference(binding['retirement'], need)
    need(proof.get('planSha256') == digest(plan), 'RUNTIME_RECEIPT_PLAN_CHANGED')
    return plan, proof


def runtime(c, objects, namespace_uid, job, pods, need=require):
    checked_binding = runtime_binding(c, list(objects.values()), need)
    if checked_binding is None:
        return None
    plan, proof = checked_binding
    old = {k: v for k, v in proof.items() if k != 'planSha256'}
    checked = terminal(objects[PROVISION], job, pods, namespace_uid, c['runId'], old, need)
    return {'contract': CONTRACT, 'jobUid': checked['jobUid'], 'podUid': checked['pod']['uid'],
            'retirement': 'VERIFIED', 'podPresent': any(p['metadata']['uid'] == checked['pod']['uid'] for p in pods),
            'planSha256': digest(plan)}
