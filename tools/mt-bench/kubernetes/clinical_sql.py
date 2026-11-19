"""PostgreSQL process and ownership bracket for clinical and accepted-input SQL.

The run is fully loaded/validated by adapter.main before entry. The selected
PostgreSQL Pod is selected from the campaign baseline; its UID, placement, image
and restart count are not re-compared (decision four-product-failures).
Unrelated roles/setup/native-input objects are observed at campaign boundaries.
The unchanged clinical SELECT carries actual DB/system/timeline, native source
and restore fields into the unchanged strict clinical oracle.
"""
import time

import kube_adapter as k


def observe(c, objects, client, baseline, *, continuity_verdict='FAIL'):
    k.need(all(baseline[key] == c[key] for key in ('context','runId','pins')), 'SOURCE_IMAGE_BINDING_CHANGED')
    selection = c['roles']['postgres']
    workload = selection['workload']
    expected = objects[workload]
    pod_name, container = k.selected_pod(c, baseline, 'postgres')
    ns = client.get('namespace', c['namespace'])
    k.need(ns['metadata']['name'] == c['namespace'] and
           ns['metadata'].get('labels', {}).get(c['ownerLabel']) == c['runId'], 'FOREIGN_NAMESPACE')
    k.need(not ns['metadata'].get('deletionTimestamp'), 'NAMESPACE_TERMINATING')
    parent = client.get(expected['kind'], expected['metadata']['name'])
    k.owned(c, parent)
    k.need(k.key(parent) == workload and not parent['metadata'].get('deletionTimestamp'), 'RESOURCE_TERMINATING')
    k.replica_scope(parent)
    pod = client.get('pod', pod_name)
    k.owned(c, pod)
    k.need(pod['kind'] == 'Pod' and pod['metadata']['name'] == pod_name and
           not pod['metadata'].get('deletionTimestamp'), 'POD_TERMINATING', continuity_verdict)
    owner = k.controller(pod)
    if owner['kind'] == 'ReplicaSet':
        replica = client.get('ReplicaSet', owner['name'])
        k.owned(c, replica)
        k.need(replica['metadata']['uid'] == owner['uid'] and not replica['metadata'].get('deletionTimestamp'), 'POD_CONTROLLER')
        owner = k.controller(replica)
    k.need(owner['kind']+'/'+owner['name'] == workload and
           owner['uid'] == parent['metadata']['uid'], 'POD_CONTROLLER')
    rows = [row for row in pod.get('status', {}).get('containerStatuses', []) if row['name'] == container]
    k.need(len(rows) == 1, 'CONTAINER_IDENTITY_UNMEASURED', 'UNMEASURED')
    row = rows[0]
    k.need(row.get('ready') is True and 'running' in (row.get('state') or {}) and
           pod.get('status', {}).get('phase') == 'Running' and
           any(value.get('type') == 'Ready' and value.get('status') == 'True'
               for value in pod.get('status', {}).get('conditions', [])), 'ROLE_NOT_READY', 'UNMEASURED')
    return pod_name, container


def read(d, c, objects, query, client):
    k.need(isinstance(query, str) and query.strip().startswith('SELECT ') and len(query.encode()) < 131072, 'SQL_READ_ONLY')
    # This can shorten the original work cutoff. The probe still owns the
    # unchanged 60-second child timeout and independent 120-second witness clock.
    with k.observation_deadline(time.time()+60):
        k.deadline(c)
        baseline = k.active_baseline(d)
        pod, container = observe(c, objects, client, baseline)
        raw = k.postgres_read(client, pod, container, query)
        observe(c, objects, client, baseline)
        k.deadline(c)
        return raw
