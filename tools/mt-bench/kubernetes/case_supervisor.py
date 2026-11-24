#!/usr/bin/env python3
"""In-cluster case supervisor: a workstation outage cannot lose a case or leave its namespace behind.

The controller (lifecycle.py) runs on a workstation; at 00:32Z on 2026-11-22 kubectl lost the network and cases went
UNMEASURED with their namespace left behind (OWNED_CLEANUP_UNCONFIRMED). The supervisor is a Job in its own namespace
that outlives the controller:

  * it waits for the case deadline (cleanup-until), or for the controller's heartbeat to go stale, or for the namespace
    to carry `nightscout.org/case-released=true` (the controller finished and is cleaning up itself);
  * then it runs run_cleanup.cleanup: one owned delete (the namespace, only when it carries this run's label, plus the
    named cluster-scoped objects) and one absence check; a leftover is a failure (non-zero exit, the Job retries);
  * the result is one ConfigMap `case-cleanup-<run-id>` in the supervisor's namespace, readable by the controller or an
    operator when the workstation returns (kubectl get configmap -n <supervisor-ns> case-cleanup-<run-id>).

The controller sets the heartbeat with `kubectl annotate namespace NS nightscout.org/controller-heartbeat=<epoch> --overwrite`.
Its RBAC is scoped to this one namespace by resourceNames.

  case_supervisor.py run --namespace NS --run-id ID --deadline EPOCH --supervisor-namespace SNS [--heartbeat-grace S] [--poll S]
"""
import argparse
import json
import subprocess
import sys
import time

import run_cleanup

HEARTBEAT = 'nightscout.org/controller-heartbeat'
RELEASED = 'nightscout.org/case-released'
GRACE_DEFAULT = 600


def decide(now, deadline, annotations, grace, present=True):
    """Why to clean up now, or None to keep waiting. A heartbeat that was never set does not count as stale: the
    controller may not have started yet, and the deadline still bounds the case."""
    if not present:
        return 'namespace-absent'
    if annotations.get(RELEASED) == 'true':
        return 'released'
    if now >= deadline:
        return 'deadline'
    beat = annotations.get(HEARTBEAT)
    if beat and now - float(beat) > grace:
        return 'heartbeat-stale'
    return None


def kubectl(argv):
    return subprocess.run(['kubectl', *argv], capture_output=True, text=True, timeout=170, check=True).stdout


def annotations(namespace, call=kubectl):
    out = call(['get', 'namespace', namespace, '--ignore-not-found=true', '-o', 'json'])
    if not out.strip():
        return None
    return json.loads(out)['metadata'].get('annotations') or {}


def supervise(namespace, run_id, deadline, supervisor_namespace, *, grace=GRACE_DEFAULT, poll=5, call=kubectl,
              clock=time.time, sleep=time.sleep, wait_seconds=120, cluster_scoped_names=()):
    """Wait for the reason to clean up, clean up once, record the result. Returns the result document."""
    while True:
        notes = annotations(namespace, call)
        reason = decide(clock(), deadline, notes or {}, grace, present=notes is not None)
        if reason:
            break
        sleep(poll)
    try:
        named = [['delete', *item.split('/', 1), '--ignore-not-found=true'] for item in cluster_scoped_names]   # 'clusterrolebinding/NAME'
        def tolerant(argv):
            # A delete that times out (a slow Terminating namespace) is not the verdict; the absence check is. A leftover
            # fails the attempt and the Job retries.
            try:
                return call(argv)
            except subprocess.CalledProcessError:
                if argv[0] != 'delete':
                    raise
                return ''
        result = run_cleanup.cleanup(tolerant, namespace, run_id, wait_seconds=wait_seconds,
                                     delete_scoped=False, extra_deletes=named)
        doc = {'verdict': 'CLEANED', 'reason': reason, **result}
    except run_cleanup.CleanupFailed as error:
        doc = {'verdict': 'FAIL', 'reason': reason, 'code': 'K8S_CLEANUP_LEFTOVER', 'leftovers': error.leftovers}
    except Exception as error:
        doc = {'verdict': 'FAIL', 'reason': reason, 'code': str(error) if str(error).startswith('K8S_') else type(error).__name__}
    doc.update(namespace=namespace, runId=run_id, at=int(clock()))
    record(supervisor_namespace, run_id, doc, call)
    return doc


def record(supervisor_namespace, run_id, doc, call=kubectl):
    name = 'case-cleanup-' + run_id
    call(['-n', supervisor_namespace, 'delete', 'configmap', name, '--ignore-not-found=true'])
    call(['-n', supervisor_namespace, 'create', 'configmap', name, '--from-literal=result=' + json.dumps(doc, sort_keys=True)])


def render(namespace, run_id, image, deadline, supervisor_namespace, *, grace=GRACE_DEFAULT, cluster_scoped_names=()):
    """Manifests (a List) for the supervisor of one case. RBAC is narrowed to the one namespace by resourceNames; the
    labelled cluster-scoped objects are deleted only by the names the case's render declared ('clusterrolebinding/NAME')."""
    name = 'case-supervisor-' + run_id
    # Not the case's run-id label: the absence check lists objects by that label and must not find the supervisor itself.
    labels = {'nightscout.org/case-supervisor': run_id, 'app.kubernetes.io/name': 'case-supervisor'}
    rules = [{'apiGroups': [''], 'resources': ['namespaces'], 'resourceNames': [namespace], 'verbs': ['get', 'delete']},
             {'apiGroups': ['rbac.authorization.k8s.io'], 'resources': ['clusterrolebindings', 'clusterroles'], 'verbs': ['list']}]
    for kind in ('clusterrolebinding', 'clusterrole'):
        names = sorted(n.split('/', 1)[1] for n in cluster_scoped_names if n.startswith(kind + '/'))
        if names:
            rules.append({'apiGroups': ['rbac.authorization.k8s.io'], 'resources': [kind + 's'], 'resourceNames': names, 'verbs': ['delete']})
    items = [
        {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': name, 'namespace': supervisor_namespace, 'labels': labels}},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRole', 'metadata': {'name': name, 'labels': labels}, 'rules': rules},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRoleBinding', 'metadata': {'name': name, 'labels': labels},
         'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': name},
         'subjects': [{'kind': 'ServiceAccount', 'name': name, 'namespace': supervisor_namespace}]},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role', 'metadata': {'name': name, 'namespace': supervisor_namespace, 'labels': labels},
         'rules': [{'apiGroups': [''], 'resources': ['configmaps'], 'verbs': ['create', 'delete', 'get']}]},
        {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding', 'metadata': {'name': name, 'namespace': supervisor_namespace, 'labels': labels},
         'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': name},
         'subjects': [{'kind': 'ServiceAccount', 'name': name, 'namespace': supervisor_namespace}]},
        {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name, 'namespace': supervisor_namespace, 'labels': labels},
         'spec': {'backoffLimit': 6, 'activeDeadlineSeconds': max(60, int(deadline - time.time())) + 3600,
                  'template': {'metadata': {'labels': labels}, 'spec': {
                      'serviceAccountName': name, 'restartPolicy': 'OnFailure',
                      'containers': [{'name': 'supervisor', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                                      'command': ['python3', '-B', '/app/case_supervisor.py', 'run', '--namespace', namespace,
                                                  '--run-id', run_id, '--deadline', str(int(deadline)),
                                                  '--supervisor-namespace', supervisor_namespace, '--heartbeat-grace', str(grace),
                                                  '--cluster-scoped', ','.join(sorted(cluster_scoped_names))],
                                      'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '128Mi'}}}]}}}},
    ]
    return {'apiVersion': 'v1', 'kind': 'List', 'items': items}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='action', required=True)
    r = s.add_parser('run')
    r.add_argument('--namespace', required=True)
    r.add_argument('--run-id', required=True)
    r.add_argument('--deadline', type=float, required=True)
    r.add_argument('--supervisor-namespace', required=True)
    r.add_argument('--heartbeat-grace', type=int, default=GRACE_DEFAULT)
    r.add_argument('--poll', type=int, default=5)
    r.add_argument('--cluster-scoped', default='', help='comma list of clusterrolebinding/NAME or clusterrole/NAME to delete')
    a = p.parse_args(argv)
    doc = supervise(a.namespace, a.run_id, a.deadline, a.supervisor_namespace, grace=a.heartbeat_grace, poll=a.poll,
                    cluster_scoped_names=[x for x in a.cluster_scoped.split(',') if x])
    print(json.dumps(doc, sort_keys=True))
    return 0 if doc['verdict'] == 'CLEANED' else 1


if __name__ == '__main__':
    sys.exit(main())
