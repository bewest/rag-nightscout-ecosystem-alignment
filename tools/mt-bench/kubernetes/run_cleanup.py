"""Kubernetes run cleanup: one owned delete and one absence check.

Decision simple-run-cleanup. A run owns a uniquely named Namespace and the cluster-scoped objects
(for example the Vault TokenReview ClusterRoleBinding) that carry its `nightscout.org/run-id`
label. Cleanup deletes the Namespace and waits, deletes the labelled cluster-scoped objects, then
checks absence once. A leftover object is a failure, never a pass. There is no UID census,
guard process or cleanup lock: a Namespace is deleted only when it carries this run's label.
"""
import json

LABEL = 'nightscout.org/run-id'
CLUSTER_SCOPED = 'clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io'


class CleanupFailed(RuntimeError):
    def __init__(self, leftovers):
        super().__init__('K8S_CLEANUP_LEFTOVER')
        self.leftovers = leftovers


def delete_commands(namespace, run_id, wait_seconds):
    selector = LABEL + '=' + run_id
    return [['delete', 'namespace', namespace, '--wait=true', '--ignore-not-found=true', '--timeout=%ds' % wait_seconds],
            ['delete', CLUSTER_SCOPED, '-l', selector, '--ignore-not-found=true', '--wait=true']]


def owner_command(namespace):
    return ['get', 'namespace', namespace, '--ignore-not-found=true', '-o', 'jsonpath={.metadata.labels.nightscout\\.org/run-id}']


def absence_commands(namespace, run_id):
    return [['get', 'namespace', namespace, '--ignore-not-found=true', '-o', 'name'],
            ['get', CLUSTER_SCOPED, '-l', LABEL + '=' + run_id, '-o', 'name']]


def cleanup(call, namespace, run_id, *, wait_seconds=120):
    """`call(argv)` runs kubectl with the run's context and returns stdout text, or raises."""
    # Ownership is the run label; the namespace name carries no required prefix.
    if not (namespace and run_id):
        raise RuntimeError('K8S_CLEANUP_UNOWNED_NAME')
    owner = call(owner_command(namespace)).strip()
    if owner and owner != run_id or not owner and call(absence_commands(namespace, run_id)[0]).strip():
        raise RuntimeError('K8S_CLEANUP_UNOWNED_NAME')
    for argv in delete_commands(namespace, run_id, wait_seconds):
        call(argv)
    leftovers = []
    for argv in absence_commands(namespace, run_id):
        leftovers += [line for line in call(argv).splitlines() if line.strip()]
    if leftovers:
        raise CleanupFailed(sorted(leftovers))
    return {'namespace': namespace, 'runId': run_id, 'absent': True, 'method': 'delete namespace --wait, delete by label, one absence check'}
