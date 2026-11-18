"""Validate one explicitly acquired worker. No provider or cluster mutations."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import time

FIELD = 'ownedWorkerPlacement'
CONTRACT = 'doks-owned-worker-v1'
LABEL = 'nightscout.org/staging-run'
POOL_LABEL = 'doks.digitalocean.com/node-pool-id'
PROVIDER_NODE_LABEL = 'doks.digitalocean.com/node-id'
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
NAME = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')
PLACEMENT_FIELDS = {'contract', 'clusterId', 'region', 'poolId', 'poolName', 'size',
                    'nodeName', 'nodeUid', 'providerNodeId', 'providerId', 'runId', 'proof'}
WORKLOADS = {'Job', 'Deployment', 'StatefulSet'}


def require(ok, code):
    if not ok:
        raise ValueError('K8S_' + code)


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def document_ref(value, need=require):
    need(isinstance(value, dict) and set(value) == {'path', 'sha256'}, 'OWNED_WORKER_REFERENCE')
    path = Path(value['path'])
    need(path.is_absolute() and path.is_file() and not path.is_symlink(), 'OWNED_WORKER_REFERENCE')
    data = path.read_bytes()
    need(digest_bytes(data) == value['sha256'], 'OWNED_WORKER_INPUT_CHANGED')
    return json.loads(data)


def placement(value, run_id, need=require):
    need(isinstance(value, dict) and set(value) == PLACEMENT_FIELDS
         and value.get('contract') == CONTRACT and value.get('runId') == run_id, 'OWNED_WORKER_SELECTION')
    need(all(isinstance(value[key], str) and UUID.fullmatch(value[key])
             for key in ('clusterId', 'poolId', 'nodeUid', 'providerNodeId')), 'OWNED_WORKER_IDENTITY')
    need(all(isinstance(value[key], str) and NAME.fullmatch(value[key])
             for key in ('region', 'poolName', 'size', 'nodeName', 'runId')), 'OWNED_WORKER_NAMES')
    need(isinstance(value['providerId'], str) and re.fullmatch(r'digitalocean://[1-9][0-9]*', value['providerId']),
         'OWNED_WORKER_PROVIDER_ID')
    return value


def expected_toleration(value):
    return {'key': LABEL, 'operator': 'Equal', 'value': value['runId'], 'effect': 'NoSchedule'}


def pod_spec(value, spec, need=require, *, runtime=False):
    allowed = [expected_toleration(value)]
    if runtime:
        # These two default admission tolerations carry no NoSchedule authority.
        allowed += [{'key': 'node.kubernetes.io/' + reason, 'operator': 'Exists',
                     'effect': 'NoExecute', 'tolerationSeconds': 300}
                    for reason in ('not-ready', 'unreachable')]
    tolerations = spec.get('tolerations', [])
    need(spec.get('nodeName') == value['nodeName'] and spec.get('nodeSelector') == {LABEL: value['runId']},
         'OWNED_WORKER_POD_BINDING')
    need(isinstance(tolerations, list) and tolerations.count(allowed[0]) == 1
         and all(tolerations.count(row) == 1 and row in allowed for row in tolerations),
         'OWNED_WORKER_POD_TOLERATION')


def render(value, objects, need=require):
    workloads = [row for row in objects if row['kind'] in WORKLOADS]
    need(bool(workloads), 'OWNED_WORKER_WORKLOADS')
    for row in workloads:
        pod_spec(value, row['spec']['template']['spec'], need)


def listed(value, need=require):
    need(isinstance(value, dict) and value.get('kind') in ('List', 'NodeList', 'PodList', 'ReplicaSetList')
         and value.get('apiVersion') in ('v1', 'apps/v1')
         and isinstance(value.get('metadata'), dict) and not value['metadata'].get('continue')
         and not value['metadata'].get('remainingItemCount') and isinstance(value.get('items'), list),
         'OWNED_WORKER_INCOMPLETE_ROSTER')
    return value['items']


def unique(rows, key, need=require):
    result = {key(row): row for row in rows}
    need(len(result) == len(rows), 'OWNED_WORKER_DUPLICATE_ROSTER')
    return result


def node(value, row, need=require):
    meta, spec = row['metadata'], row['spec']
    labels = meta.get('labels', {})
    need(row.get('kind') == 'Node' and meta['name'] == value['nodeName'] and meta['uid'] == value['nodeUid']
         and spec.get('providerID') == value['providerId'] and not meta.get('deletionTimestamp'),
         'OWNED_WORKER_NODE_CHANGED')
    need(labels.get(POOL_LABEL) == value['poolId']
         and labels.get('doks.digitalocean.com/node-pool') == value['poolName']
         and labels.get(PROVIDER_NODE_LABEL) == value['providerNodeId'], 'OWNED_WORKER_POOL_CHANGED')
    need(labels.get(LABEL) == value['runId']
         and labels.get('topology.kubernetes.io/region') == value['region']
         and labels.get('node.kubernetes.io/instance-type') == value['size'], 'OWNED_WORKER_LABEL_CHANGED')
    want = [{'key': LABEL, 'value': value['runId'], 'effect': 'NoSchedule'}]
    need(spec.get('taints') == want and spec.get('unschedulable', False) is False, 'OWNED_WORKER_TAINT_OR_CORDON')
    conditions = unique(row['status']['conditions'], lambda condition: condition['type'], need)
    health = {'Ready':'True', 'MemoryPressure':'False', 'DiskPressure':'False',
              'PIDPressure':'False', 'NetworkUnavailable':'False'}
    need(all(conditions.get(key, {}).get('status') == status for key, status in health.items()),
         'OWNED_WORKER_NODE_HEALTH')


def ref_owner(row, need=require):
    refs = [ref for ref in row['metadata'].get('ownerReferences', []) if ref.get('controller') is True]
    need(len(refs) == 1 and all(isinstance(refs[0].get(key), str) and refs[0][key]
                                for key in ('kind', 'name', 'uid')), 'OWNED_WORKER_POD_OWNER')
    return refs[0]


def identity(row, need=require):
    meta = row['metadata']
    need(all(isinstance(meta.get(key), str) and meta[key] for key in ('namespace', 'name', 'uid'))
         and not meta.get('deletionTimestamp'), 'OWNED_WORKER_POD_CUSTODY')
    ref = ref_owner(row, need)
    return {**{key: meta[key] for key in ('namespace', 'name', 'uid')},
            'controller': {key: ref[key] for key in ('kind', 'name', 'uid')}}


def exact_roster(value, pod_list, infrastructure, fixture, need=require):
    rows = listed(pod_list, need)
    need(all(row.get('kind') == 'Pod' and row['spec'].get('nodeName') == value['nodeName'] for row in rows),
         'OWNED_WORKER_NODE_POD_SCOPE')
    owned_ids = {item['uid'] for item in fixture}
    for row in rows:
        if row['metadata']['uid'] in owned_ids:
            pod_spec(value, row['spec'], need, runtime=True)
    actual = unique([identity(row, need) for row in rows], lambda row: row['uid'], need)
    expected = unique(infrastructure + fixture, lambda row: row['uid'], need)
    need(actual == expected, 'OWNED_WORKER_FOREIGN_OR_MISSING_POD')
    return len(actual)


def timestamp(stamp, need=require):
    value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    need(value.utcoffset() is not None, 'OWNED_WORKER_TIME')
    return value.timestamp()


def snapshot(refs, context, need=require, *, acquired=False):
    names = {'capture', 'clusters', 'pools', 'nodes', 'pods'} | ({'owned-node'} if acquired else set())
    need(isinstance(refs, dict) and set(refs) == names, 'OWNED_WORKER_SNAPSHOT_FILES')
    values = {name: document_ref(refs[name], need) for name in names}
    capture = values['capture']
    need(capture.get('context') == context and all(capture['queries'].get(name, {}).get('exit') == 0
         for name in names - {'capture'}), 'OWNED_WORKER_SNAPSHOT_SCOPE')
    return values


def provider_cluster(values, value, need=require):
    rows = values['clusters']
    need(isinstance(rows, list) and len(rows) == 1 and rows[0].get('id') == value['clusterId']
         and rows[0].get('region') == value['region'], 'OWNED_WORKER_CLUSTER_CHANGED')
    pool_list = values['pools']
    need(isinstance(pool_list, list) and isinstance(rows[0].get('node_pools'), list), 'OWNED_WORKER_PROVIDER_ROSTER')
    pools = unique(pool_list, lambda row: row['id'], need)
    embedded = unique(rows[0]['node_pools'], lambda row: row['id'], need)
    def membership(roster):
        return {key: (row['name'], row['size'], row['count'], row.get('auto_scale'),
                      sorted((n['id'], n['name'], n['droplet_id']) for n in row['nodes']))
                for key, row in roster.items()}
    need(membership(embedded) == membership(pools), 'OWNED_WORKER_PROVIDER_ROSTER')
    return list(pools.values())


def prove(value, environment, directory, need=require, *, fresh=False, now=None):
    """Verify the independent provider/API captures and exact pre-entry roster."""
    chosen = placement(value, environment['runId'], need)
    need(environment['targetNode'] == chosen['nodeName'] and not environment.get('placementByWorkload'),
         'OWNED_WORKER_SINGLE_NODE')
    proof = document_ref(chosen['proof'], need)
    fields = {'contract','context','namespace','runId','cleanupOwner','before','after','infrastructure'}
    need(set(proof) == fields and proof['contract'] == CONTRACT
         and all(proof[key] == environment[key] for key in ('context', 'namespace', 'runId', 'cleanupOwner')),
         'OWNED_WORKER_PROOF_CUSTODY')
    after_paths = proof['after']
    need(all(Path(ref['path']).resolve() == Path(directory).resolve() / (name + '.json')
             for name, ref in after_paths.items()), 'OWNED_WORKER_SNAPSHOT_CHANGED')
    before = snapshot(proof['before'], proof['context'], need)
    after = snapshot(after_paths, proof['context'], need, acquired=True)
    before_time = timestamp(before['capture']['capturedAt'], need)
    captured = timestamp(after['capture']['capturedAt'], need)
    if fresh:
        need(0 <= (time.time() if now is None else now) - captured <= 300, 'OWNED_WORKER_STALE_PROOF')
    previous = provider_cluster(before, chosen, need)
    current = provider_cluster(after, chosen, need)
    need(all(row['id'] != chosen['poolId'] and row['name'] != chosen['poolName'] for row in previous),
         'OWNED_WORKER_POOL_PREEXISTED')
    matches = [row for row in current if row['id'] == chosen['poolId']]
    need(len(matches) == 1, 'OWNED_WORKER_POOL_MISSING')
    pool = matches[0]
    need(pool['name'] == chosen['poolName'] and pool['size'] == chosen['size']
         and pool.get('auto_scale') is False and type(pool.get('count')) is int and pool['count'] == 1
         and isinstance(pool.get('nodes'), list) and len(pool['nodes']) == 1, 'OWNED_WORKER_FIXED_POOL')
    provider = pool['nodes'][0]
    need(provider['id'] == chosen['providerNodeId'] and provider['name'] == chosen['nodeName']
         and f"digitalocean://{provider['droplet_id']}" == chosen['providerId']
         and provider['status']['state'] == 'running'
         and before_time < timestamp(provider['created_at'], need) <= captured, 'OWNED_WORKER_PROVIDER_NODE')
    need(all(old['id'] != provider['id'] and str(old['droplet_id']) != str(provider['droplet_id'])
             for row in previous for old in row['nodes']), 'OWNED_WORKER_PROVIDER_NODE_PREEXISTED')
    def in_scope(row):
        meta = row['metadata']
        labels = meta.get('labels', {})
        return (meta['name'] == chosen['nodeName'] or meta['uid'] == chosen['nodeUid']
                or row['spec'].get('providerID') == chosen['providerId']
                or labels.get(POOL_LABEL) == chosen['poolId']
                or labels.get(PROVIDER_NODE_LABEL) == chosen['providerNodeId'])
    prior_nodes = listed(before['nodes'], need)
    need(not any(in_scope(row) for row in prior_nodes), 'OWNED_WORKER_NODE_PREEXISTED')
    nodes = unique(listed(after['nodes'], need), lambda row: row['metadata']['name'], need)
    unique(nodes.values(), lambda row: row['metadata']['uid'], need)
    need(chosen['nodeName'] in nodes, 'OWNED_WORKER_NODE_MISSING')
    need(sum(in_scope(row) for row in nodes.values()) == 1, 'OWNED_WORKER_PROVIDER_NODE_DUPLICATE')
    node(chosen, after['owned-node'], need)
    census_node = deepcopy(nodes[chosen['nodeName']])
    taints = census_node['spec'].get('taints')
    # The ordinary census display masks JSON key fields. The independent
    # guarded named read above attests this one exact key for the same UID.
    masked = [{'key':'<redacted>', 'value':chosen['runId'], 'effect':'NoSchedule'}]
    if taints == masked:
        census_node['spec']['taints'] = after['owned-node']['spec']['taints']
    node(chosen, census_node, need)
    infrastructure = proof['infrastructure']
    original_controllers = {
        (row['metadata']['namespace'], ref['name'], ref['uid'])
        for row in listed(before['pods'], need)
        for ref in (row['metadata'].get('ownerReferences') or [])
        if ref.get('controller') is True and ref.get('kind') == 'DaemonSet'
    }
    need(isinstance(infrastructure, list) and all(
        set(row) == {'namespace', 'name', 'uid', 'controller'}
        and set(row['controller']) == {'kind', 'name', 'uid'} and row['controller']['kind'] == 'DaemonSet'
        and all(isinstance(item, str) and item for item in (row['name'], row['uid']))
        and (row['namespace'], row['controller']['name'], row['controller']['uid']) in original_controllers
        for row in infrastructure), 'OWNED_WORKER_INFRASTRUCTURE_CUSTODY')
    target = [row for row in listed(after['pods'], need) if row['spec'].get('nodeName') == chosen['nodeName']]
    exact_roster(chosen, {**after['pods'], 'items': target}, infrastructure, [], need)
    return {'selection': chosen, 'infrastructure': infrastructure,
            'capturedAt': after['capture']['capturedAt'], 'proofSha256': chosen['proof']['sha256']}


def live(value, infrastructure, fixture, get, need=require):
    """Check both sides of the complete Pod census, including the exact Kube UID."""
    node_name = value['nodeName']
    node(value, get(['get','node',node_name,'-o','json']), need)
    pods = get(['get','pods','--all-namespaces','--field-selector=spec.nodeName='+node_name,
                '--chunk-size=0','-o','json'])
    count = exact_roster(value, pods, infrastructure, fixture, need)
    node(value, get(['get','node',node_name,'-o','json']), need)
    return {'nodeUid': value['nodeUid'], 'poolId': value['poolId'], 'providerId': value['providerId'],
            'podCount': count, 'namespacePods': len(fixture)}


def stage_pods(value, namespace, pod_list, replicas, created, need=require):
    """Resolve owned Pods to the actual startup controller UIDs."""
    parents = {(row['kind'], row['name']): row['uid'] for row in created}
    by_uid = unique(listed(replicas, need), lambda row: row['metadata']['uid'], need)
    result = []
    for pod in listed(pod_list, need):
        observed = identity(pod, need)
        meta = pod['metadata']
        need(observed['namespace'] == namespace and meta.get('labels', {}).get('nightscout.org/run-id')
             == value['runId'], 'OWNED_WORKER_FIXTURE_POD_CUSTODY')
        ref = observed['controller']
        if ref['kind'] == 'ReplicaSet':
            replica = by_uid.get(ref['uid'])
            need(replica is not None and replica['metadata']['name'] == ref['name']
                 and replica['metadata']['namespace'] == namespace
                 and replica['metadata'].get('labels', {}).get('nightscout.org/run-id') == value['runId']
                 and not replica['metadata'].get('deletionTimestamp'), 'OWNED_WORKER_REPLICASET_CUSTODY')
            ref = ref_owner(replica, need)
        need(ref['kind'] in WORKLOADS and parents.get((ref['kind'], ref['name'])) == ref['uid'],
             'OWNED_WORKER_FIXTURE_CONTROLLER_CUSTODY')
        result.append(observed)
    return result


def source_pins(guard, preflight, overlay, module, view):
    return {name+'Sha256': digest_bytes(Path(path).read_bytes())
            for name, path in (('guard',guard), ('preflight',preflight), ('overlay',overlay),
                               ('module',module), ('view',view))}


def packet(config, inventory, objects, need=require, *, cleanup=False):
    selected = config.get(FIELD)
    if FIELD not in config and FIELD not in inventory:
        return
    need(isinstance(selected, dict) and set(selected) == {'selection', 'infrastructure', 'capturedAt',
                                                          'proofSha256', 'namespaceUid'},
         'OWNED_WORKER_RUNTIME_SCOPE')
    value = placement(selected['selection'], config['runId'], need)
    need(value == inventory.get(FIELD) and inventory.get('targetNode') == value['nodeName']
         and selected['proofSha256'] == value['proof']['sha256']
         and isinstance(selected['namespaceUid'], str) and UUID.fullmatch(selected['namespaceUid']),
         'OWNED_WORKER_RUNTIME_BINDING')
    if not cleanup:
        proof = document_ref(value['proof'], need)
        need(all(proof.get(key) == config[key] for key in ('runId', 'namespace', 'context'))
             and proof.get('infrastructure') == selected['infrastructure']
             and proof.get('cleanupOwner') == inventory.get('cleanupOwner'), 'OWNED_WORKER_RUNTIME_CUSTODY')
    render(value, objects, need)
