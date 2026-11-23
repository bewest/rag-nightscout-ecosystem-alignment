"""Bind consecutive workload packets to the same claims and to distinct native writers."""
import json
import time

import kube_adapter as k


def owned_uid(run, kind, name, run_id):
    # Restrict the readback to metadata, including for the private input Secret.
    result = run(['get', kind, name, '-o',
                  r'jsonpath={.metadata.uid}{" "}{.metadata.labels.nightscout\.org/run-id}'])
    uid, _, owner = result.stdout.decode().partition(' ')
    k.need(bool(uid) and owner == run_id, 'POINT_RESOURCE_OWNERSHIP:' + kind)
    return uid


def storage_identity(run, namespace, namespace_uid, run_id, claim):
    k.need(owned_uid(run, 'namespace', namespace, run_id) == namespace_uid, 'POINT_NAMESPACE_CHANGED')
    return {'namespaceUid': namespace_uid, 'postgresClaim': claim,
            'postgresClaimUid': owned_uid(run, 'pvc', claim, run_id)}


def scored_failure(packet):
    """Distinguish a measured, completed product failure from an interrupted collection."""
    stage = packet/'load/result.json'
    experiment = packet/'experiment/result.json'
    return (stage.is_file() and experiment.is_file() and k.document(stage).get('verdict') == 'FAIL'
            and k.document(experiment).get('verdict') == 'FAIL')


def new_job(run, namespace, run_id, storage, prior, job, cutoff):
    """Retire one terminal point with UID preconditions; keep its scored artifacts on disk."""
    k.need(all(prior.get(key) == value for key, value in storage.items()), 'POINT_RESTORE_CHANGED')
    k.need(job['kind'] == 'Job' and job['metadata']['name'] == 'k6' and
           job['metadata']['namespace'] == namespace and job['metadata']['labels']['nightscout.org/run-id'] == run_id
           and job['spec']['suspend'] is True, 'POINT_JOB_DECLARATION')
    resources = [('job', 'k6', prior['jobUid'], 'apis/batch/v1', 'jobs'),
                 ('secret', 'ns-k6-inputs', prior['inputSecretUid'], 'api/v1', 'secrets')]
    for kind, name, uid, _, _ in resources:
        k.need(owned_uid(run, kind, name, run_id) == uid, 'POINT_ACTOR_CHANGED:' + kind)
    for kind, name, uid, api, plural in resources:
        # kubectl's raw DELETE sends the resource UID and cascading policy in a DeleteOptions body.
        path = f'/{api}/namespaces/{namespace}/{plural}/{name}'
        options = {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'preconditions': {'uid': uid},
                   'propagationPolicy': 'Foreground'}
        run(['delete', '--raw', path, '-f', '-'], input=json.dumps(options).encode())
        while run(['get', kind, name, '--ignore-not-found', '-o', 'name']).stdout.strip():
            k.need(time.time() < cutoff, 'POINT_ACTOR_RETIRE_DEADLINE')
            time.sleep(.5)
    storage_identity_now = storage_identity(run, namespace, storage['namespaceUid'], run_id, storage['postgresClaim'])
    k.need(storage_identity_now == storage, 'POINT_RESTORE_CHANGED')
    uid = run(['create', '-f', '-', '-o', 'jsonpath={.metadata.uid}'],
              input=json.dumps(job).encode()).stdout.decode()
    k.need(bool(uid) and uid != prior['jobUid'], 'POINT_JOB_REUSED')
    return uid
