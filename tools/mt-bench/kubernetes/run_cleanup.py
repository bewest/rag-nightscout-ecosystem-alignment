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
# A fixture restore also owns labelled Retain snapshot contents; deleting them keeps the fixture.
FIXTURE_SCOPED = CLUSTER_SCOPED + ',volumesnapshotcontents.snapshot.storage.k8s.io'


class CleanupFailed(RuntimeError):
    def __init__(self, leftovers):
        super().__init__('K8S_CLEANUP_LEFTOVER')
        self.leftovers = leftovers


def delete_commands(namespace, run_id, wait_seconds, scoped=CLUSTER_SCOPED, delete_scoped=True):
    selector = LABEL + '=' + run_id
    deletes = [['delete', 'namespace', namespace, '--wait=true', '--ignore-not-found=true', '--timeout=%ds' % wait_seconds]]
    if delete_scoped:   # the in-cluster supervisor's RBAC cannot delete by selector; it names the objects itself
        deletes.append(['delete', scoped, '-l', selector, '--ignore-not-found=true', '--wait=true'])
    return deletes


def owner_command(namespace):
    return ['get', 'namespace', namespace, '--ignore-not-found=true', '-o', 'jsonpath={.metadata.labels.nightscout\\.org/run-id}']


def absence_commands(namespace, run_id, scoped=CLUSTER_SCOPED):
    return [['get', 'namespace', namespace, '--ignore-not-found=true', '-o', 'name'],
            ['get', scoped, '-l', LABEL + '=' + run_id, '-o', 'name']]


def cleanup(call, namespace, run_id, *, wait_seconds=120, scoped=CLUSTER_SCOPED, delete_scoped=True, extra_deletes=()):
    """`call(argv)` runs kubectl with the run's context and returns stdout text, or raises."""
    # Ownership is the run label; the namespace name carries no required prefix.
    if not (namespace and run_id):
        raise RuntimeError('K8S_CLEANUP_UNOWNED_NAME')
    owner = call(owner_command(namespace)).strip()
    if owner and owner != run_id or not owner and call(absence_commands(namespace, run_id)[0]).strip():
        raise RuntimeError('K8S_CLEANUP_UNOWNED_NAME')
    for argv in [*delete_commands(namespace, run_id, wait_seconds, scoped, delete_scoped), *extra_deletes]:
        call(argv)
    leftovers = []
    for argv in absence_commands(namespace, run_id, scoped):
        leftovers += [line for line in call(argv).splitlines() if line.strip()]
    if leftovers:
        raise CleanupFailed(sorted(leftovers))
    return {'namespace': namespace, 'runId': run_id, 'absent': True, 'method': 'delete namespace --wait, delete by label, one absence check'}
