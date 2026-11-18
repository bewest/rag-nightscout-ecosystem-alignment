"""Explicit source-bound static branch diagnostics through the ordinary binding."""
import hashlib
import json
import re
from pathlib import Path
from contract import require, discovery_api_replicas, discovery_workers
import workload_inputs
import role_instances

CORE = 'ce96241b390cd5397d808417b353161eed83e564'
DEPLOY = '160ca4d62002746c9b1401dc4784ba30b8543711'
# Legacy diagnostic releases predate the build-receipt option.
# New revisions use verified build receipts; do not extend this legacy set.
E217_CORE = 'e217e7856b0379dd5989992bec106f9c4fd87efb'
STARTUP_STATIC_CORE = '5a94bbaee7f1130b7de8db0f90deae8c4c1e480b'
STARTUP_STATIC_DEPLOY = '49db85682482d5fa8b304a3a9ffaf3cb0980ec05'
SOURCE_PAIRS = frozenset(((CORE, DEPLOY), (E217_CORE, DEPLOY), (STARTUP_STATIC_CORE, STARTUP_STATIC_DEPLOY)))
KIND = 'static-hash-v1'
EDGE_COMMAND = ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/socket-edge.js']


def validate(manifest):
    value = manifest.get('staticTopology')
    build_digest = manifest.get("staticBuildReceiptSha256")
    if value is None:
        require(build_digest is None, "M7_STATIC_SELECTION_REQUIRED")
        return None
    require(isinstance(value, dict) and set(value) == {'kind', 'workers'} and value['kind'] == KIND
            and discovery_workers(value['workers']), 'M7_STATIC_TOPOLOGY')
    pair = manifest.get('pair')
    require(isinstance(pair, dict) and set(pair) == {'core', 'deploy'}
            and all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{40}', v) for v in pair.values())
            and ((build_digest is None and (pair['core'], pair['deploy']) in SOURCE_PAIRS)
                 or (isinstance(build_digest, str) and re.fullmatch(r'[0-9a-f]{64}', build_digest))), 'M7_STATIC_SOURCE_PAIR')
    require(manifest.get('profile') == 'pgstream-sample' and manifest.get('runPurpose') == 'discovery'
            and manifest.get('pgstreamTopology') == 'external-service-v1'
            and manifest.get('completionContract') == 'evaluator-work-v2'
            and discovery_api_replicas(manifest.get('replicas')),
            'M7_STATIC_DIAGNOSTIC_SCOPE')
    return value


def build_receipt(args):
    """Verify the pinned local image-build evidence against both selected Git objects."""
    path = getattr(args, 'static_build_receipt', None)
    digest = getattr(args, 'static_build_receipt_sha256', None)
    if path is None and digest is None:
        return {}
    require(isinstance(path, str) and Path(path).is_absolute()
            and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
            'M7_STATIC_BUILD_RECEIPT_REQUIRED')
    try:
        raw = Path(path).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'M7_STATIC_BUILD_RECEIPT_DIGEST')
        proof = json.loads(raw)
    except (OSError, ValueError) as error:
        raise RuntimeError('M7_STATIC_BUILD_RECEIPT_INVALID') from error
    pair = {'coreCommit': args.core_commit, 'deployCommit': args.deploy_commit}
    require(isinstance(proof, dict) and proof.get('schemaVersion') == 1
            and proof.get('status') == 'BUILT_VERIFIED_LOCAL' and proof.get('basis') == 'reproduced'
            and all(proof.get(k) == v for k, v in pair.items())
            and proof.get('localImageId') == (args.image_id or args.image)
            and re.fullmatch('sha256:[0-9a-f]{64}', proof.get('localImageId') or ''),
            'M7_STATIC_BUILD_IDENTITY')
    labels = proof.get('labels')
    runtime = proof.get('runtime')
    require(isinstance(labels, dict) and labels.get('org.opencontainers.image.revision') == args.core_commit
            and labels.get('org.nightscout.deploy.revision') == args.deploy_commit
            and isinstance(runtime, dict) and runtime.get('source') == {'version': 1, **pair}
            and runtime.get('producerHelpSucceeded') is True, 'M7_STATIC_BUILD_PROVENANCE')
    import adapter as a
    lock = a.command(['git', '-C', args.core_repo, 'show', args.core_commit + ':package-lock.json'], binary=True)
    producer = json.loads(a.git(args.deploy_repo, 'show',
                                args.deploy_commit + ':bindings/compose/multitenant/pgstream-source.json'))
    require(runtime.get('lockSha256') == hashlib.sha256(lock).hexdigest()
            and isinstance(runtime.get('binarySha256'), str)
            and re.fullmatch('[0-9a-f]{64}', runtime['binarySha256'])
            and runtime['binarySha256'] == producer.get('binarySha256'), 'M7_STATIC_BUILD_INPUTS')
    return {'staticBuildReceiptSha256': digest}


def option(args, require_allocation=True):
    count = getattr(args, 'static_workers', None)
    build = build_receipt(args)
    if count is None:
        require(not build, 'M7_STATIC_SELECTION_REQUIRED')
        return {}
    manifest = {'staticTopology': {'kind': KIND, 'workers': count},
                'pair': {'core': args.core_commit, 'deploy': args.deploy_commit},
                'profile': args.profile, 'runPurpose': args.run_purpose,
                'pgstreamTopology': args.pgstream_topology, 'completionContract': args.completion_contract,
                'replicas': args.replicas}
    validate({**manifest, **build})
    needs_selected_allocation = count > 1 or args.replicas > 1
    require(not (require_allocation and needs_selected_allocation) or
            isinstance(getattr(args, 'diagnostic_resource_allocation', None), dict),
            'M7_STATIC_EXPLICIT_ALLOCATION')
    return {'staticTopology': manifest['staticTopology'], **build}


def environment(manifest):
    value = validate(manifest)
    return {} if value is None else {'NS_EVALUATOR_WORKERS': str(value['workers']), 'NS_REALTIME_WORKERS': str(value['workers'])}


def receipt(manifest, proof):
    value = validate(manifest)
    if value is None:
        require('staticWorkers' not in proof.get('limits', {}), 'M7_STATIC_SELECTION_REQUIRED')
        return False
    require(proof.get('version') == 2 and proof.get('limits', {}).get('staticWorkers') == value['workers']
            and type(proof['limits']['staticWorkers']) is int, 'M7_STATIC_RECEIPT')
    return True


def verify_source(a, manifest, core_repo, deploy_repo):
    if validate(manifest) is None:
        return None
    files = {
        'core': ['lib/pgstream/assigned-worker.js', 'lib/realtime-ownership/index.js',
                 'lib/server/serve/evaluator-config.js', 'lib/server/realtime/config.js',
                 'lib/server/serve/plan-contract/schema/evaluator.schema.json'],
        'deploy': ['bindings/compose/multitenant/evaluator-workers.js', 'bindings/compose/multitenant/realtime-workers.js',
                   'bindings/compose/multitenant/config.js', 'bindings/compose/multitenant/prepare.js',
                   'bindings/compose/multitenant/socket-edge.js']}
    # Exact objects, not a closest branch, provide the actual source/parser contract.
    hashes = {}
    import hashlib
    for kind, paths in files.items():
        repo = core_repo if kind == 'core' else deploy_repo
        for file in paths:
            raw = a.command(['git','-C',repo,'show',manifest['pair'][kind]+':'+file],binary=True)
            require(isinstance(raw,bytes) and bool(raw), 'M7_STATIC_SOURCE_CONTRACT')
            hashes[kind + ':' + file] = hashlib.sha256(raw).hexdigest()
    return {'status': 'SOURCE_OBJECTS_VERIFIED', 'pair': manifest['pair'], 'files': hashes,
            'scope': 'Exact static source objects; real generated document/parser check is required separately.'}


def verify_config(manifest, config):
    value = validate(manifest)
    if value is None:
        require('socket-edge' not in config.get('services', {}), 'M7_STATIC_SELECTION_REQUIRED')
        return None
    if 'tenants' in manifest:
        require(workload_inputs.tenants(manifest['tenants'])
                and config.get('services', {}).get('bootstrap', {}).get('environment', {}).get('NS_DEMO_TENANTS') == str(manifest['tenants']),
                'M7_STATIC_SEED_COUNT')
    count = value['workers']; instances = role_instances.roster(config, manifest['replicas'])
    require(all(sum(v['role'] == role for v in instances.values()) == count for role in ('evaluator', 'realtime')),
            'M7_STATIC_SERVICE_COVERAGE')
    edge = config['services'].get('socket-edge', {})
    require(edge.get('command') == EDGE_COMMAND, 'M7_STATIC_EDGE_COMMAND')
    env = edge.get('environment', {})
    expected = {'version': 1, 'rule': 'sha256-modulo-v1', 'count': count,
                'upstreams': [f'http://{service("realtime", i)}:1339/' for i in range(count)]}
    try:
        route = json.loads(env.get('NS_REALTIME_STATIC_ROUTE_MAP', ''))
    except (ValueError, TypeError):
        raise RuntimeError('M7_STATIC_EDGE_ROUTES') from None
    require(env.get('NS_REALTIME_STATIC_COUNT') == str(count) and route == expected, 'M7_STATIC_EDGE_ROUTES')
    require(edge.get('restart') == 'unless-stopped' and
            all(config['services'][name].get('restart') == 'unless-stopped' for name in instances if instances[name]['role'] != 'api'),
            'M7_STATIC_PLATFORM_RESTART')
    return instances


def service(role, ordinal):
    return role if ordinal == 0 else role + '-' + str(ordinal + 1)


def verify_documents(manifest, documents):
    """Check actual generated role documents before the real published plan parser."""
    value = validate(manifest)
    require(value is not None, 'M7_STATIC_SELECTION_REQUIRED')
    processes = documents.get('processes', [])
    selected = {}
    for process in processes:
        name = process.get('name', '')
        if name in role_instances.FAMILIES or any(name.startswith(r + '-') for r in role_instances.FAMILIES):
            require(name not in selected, 'M7_STATIC_DOCUMENT_COVERAGE')
            selected[name] = process
    expected = {service(role, i): {'service': service(role, i), 'role': role, 'ordinal': i,
                                 'count': count} for role, count in (('api', manifest['replicas']), ('evaluator', value['workers']), ('realtime', value['workers'])) for i in range(count)}
    require(set(selected) == set(expected), 'M7_STATIC_DOCUMENT_COVERAGE')
    signatures = []
    peer_list = [{'socket': f'/run/ns-ipc/realtime-{i+1}.sock'} for i in range(value['workers'])]
    for name, item in expected.items():
        process = selected[name]; env = process.get('environment', {}); files = process.get('files', {})
        require(process.get('roles') == [item['role']], 'M7_STATIC_DOCUMENT_ROLE')
        role_instances.assignment(item, env, expected)
        for legacy in ('NS_REALTIME_SHARDS', 'NS_PGSTREAM_EVALUATOR_PROCESSES'):
            require(legacy not in env, 'M7_STATIC_RETIRED_SELECTOR')
        if manifest['replicas']==1:
            require(env.get('NS_API_INTERNAL_SOCKET')=='/run/ns-ipc/api.sock','M7_STATIC_PRIVATE_ADDRESS')
        else:
            require(env.get('NS_API_INTERNAL_URL')=='http://api-internal:7001' and 'NS_API_INTERNAL_SOCKET' not in env,'M7_STATIC_PRIVATE_ADDRESS')
        conf = files.get('/run/ns-config/config.json', {}); operation = files.get('/run/ns-config/operation.json', {})
        participant = item['role'] if item['role'] == 'api' and manifest['replicas'] == 1 else item['role'] + '-' + str(item['ordinal'] + 1)
        require(operation.get('participantId') == participant, 'M7_STATIC_PARTICIPANT')
        if item['role'] != 'api' or manifest['replicas'] == 1:
            require(env.get('NS_SERVE_INTERNAL_SOCKET') == f'/run/ns-ipc/{participant}.sock', 'M7_STATIC_PRIVATE_ADDRESS')
        else:
            require(env.get('NS_SERVE_INTERNAL_HOST') == '0.0.0.0' and env.get('NS_SERVE_INTERNAL_PORT') == '7001'
                    and 'NS_SERVE_INTERNAL_SOCKET' not in env, 'M7_STATIC_PRIVATE_ADDRESS')
        participants=operation.get('participants', [])
        serving=[row for row in participants if any(role in role_instances.FAMILIES for role in row.get('roles', []))]
        participant_map={row.get('id'):row for row in serving}
        expected_ids={('api' if part['role']=='api' and manifest['replicas']==1 else part['role']+'-'+str(part['ordinal']+1)):part for part in expected.values()}
        require(len(participant_map)==len(serving) and set(participant_map)==set(expected_ids), 'M7_STATIC_PARTICIPANT_COVERAGE')
        for peer_id,part in expected_ids.items():
            address=({'url':f'http://{part["service"]}:7001'} if part['role']=='api' and manifest['replicas']>1 else {'socket':f'/run/ns-ipc/{peer_id}.sock'})
            actual_address=participant_map[peer_id].get('address')
            address_ok=(actual_address is None or actual_address==address) if part['role']=='api' and manifest['replicas']==1 else actual_address==address
            require(participant_map[peer_id].get('roles')==[part['role']] and address_ok, 'M7_STATIC_PRIVATE_ADDRESS')
        peers = [row for row in participants if 'realtime' in row.get('roles', [])]
        require(len(peers) == value['workers'] and
                {row.get('id') for row in peers} == {f'realtime-{i+1}' for i in range(value['workers'])}, 'M7_STATIC_PARTICIPANT_COVERAGE')
        for row in peers:
            ordinal = int(row['id'].split('-')[-1]) - 1
            require(row.get('slice') == {'count': value['workers'], 'ordinal': ordinal}, 'M7_STATIC_PARTICIPANT_COVERAGE')
        if item['role'] == 'evaluator':
            require('NS_PGSTREAM_EVALUATOR_SLICE' in env and json.loads(env.get('NS_REALTIME_SLICE_PEERS', 'null')) == peer_list, 'M7_STATIC_PRIVATE_PEERS')
            stream = conf.get('pgstream', {})
            require(stream.get('receiver', {}).get('url') == f'http://{name}:19913/', 'M7_STATIC_RECEIVER')
            signatures.append({'postgres': conf.get('postgres'), 'datastore': conf.get('datastore'), 'consumer': conf.get('consumer'),
                               **{key: stream.get(key) for key in ('slot', 'generation', 'streamRole', 'transactionRows')}})
        elif item['role'] == 'realtime':
            require('NS_REALTIME_SLICE' in env, 'M7_STATIC_DOCUMENT_ORDINAL')
    require(signatures and all(v == signatures[0] for v in signatures) and all(signatures[0].get(k) for k in ('slot', 'generation', 'streamRole', 'consumer')),
            'M7_STATIC_SHARED_SOURCE')
    base = selected['evaluator']['files']['/run/ns-config/config.json']
    for name, item in expected.items():
        if item['role'] == 'realtime':
            completed = selected[name]['files']['/run/ns-config/config.json'].get('completedOutput')
            require(completed == {'namespace': base['postgres']['namespaces']['checkpoint'], 'consumer': base['consumer']}, 'M7_STATIC_COMPLETED_SOURCE')
    return {'status': 'VERIFIED', 'instances': expected, 'source': signatures[0],
            'scope': 'Actual role documents, static participants, private peers and shared source identity. Configured census is not peer liveness.'}


def state_documents(manifest, config, state):
    """Read every actual mounted role file; never fabricate another ordinal."""
    instances = verify_config(manifest, config)
    require(instances is not None, 'M7_STATIC_SELECTION_REQUIRED')
    state = Path(state).resolve(); processes = []
    for name, item in {**instances, 'tenant-admin':{'role':'tenant-admin'}, 'admin':{'role':'admin'}}.items():
        mounts = [v for v in config['services'][name].get('volumes', []) if v.get('target') == '/run/ns-config']
        require(len(mounts) == 1 and mounts[0].get('type') == 'bind' and mounts[0].get('read_only') is True, 'M7_STATIC_CONFIG_MOUNT')
        source = Path(mounts[0]['source']).resolve()
        require(source.is_relative_to(state), 'M7_STATIC_CONFIG_MOUNT')
        names=('config.json',) if item['role']=='admin' else ('config.json','operation.json')
        if item['role']=='api':names=(*names,'evaluator-metadata.json')
        files = {f'/run/ns-config/{file}': json.loads((source/file).read_text()) for file in names}
        processes.append({'name': name, 'roles': [item['role']], 'environment': json.loads((source/'env.json').read_text()), 'files': files})
    return {'contract': 1, 'processes': processes}


def verify_producer(manifest, documents, data):
    from urllib.parse import urlsplit
    value = validate(manifest)
    require(value is not None, 'M7_STATIC_SELECTION_REQUIRED')
    evaluator = next(p for p in documents['processes'] if p['name'] == 'evaluator')['files']['/run/ns-config/config.json']
    try:
        replica = data['source']['postgres']['replication']
        database = urlsplit(data['source']['postgres']['url'])
        batch = data['target']['webhooks']['notifier']['transaction_batch']
        receivers = [f'http://{service("evaluator", i)}:19913/pgstream' for i in range(value['workers'])]
        require(batch['slice_receivers'] == receivers and replica['replication_slot'] == evaluator['pgstream']['slot']
                and replica['plugin']['include_transactions'] is True
                and database.path[1:] == evaluator['datastore']['database']
                and database.hostname == evaluator['datastore']['hostname'], 'M7_STATIC_PRODUCER_SOURCE')
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('M7_STATIC_PRODUCER_SOURCE') from None
    return {'status': 'VERIFIED', 'receivers': receivers, 'slot': replica['replication_slot'],
            'scope': 'Actual configured producer source/targets. Subscription effects and physical source identity retain their native runtime checks.'}


def verify_runtime(manifest, config, rows):
    from contract import OWNER
    instances = verify_config(manifest, config)
    role_instances.runtime(rows, instances, manifest)
    edges=[row for row in rows if row.get('Config',{}).get('Labels',{}).get('com.docker.compose.service')=='socket-edge']
    require(len(edges)==1,'M7_STATIC_EDGE_RUNTIME')
    edge=edges[0];labels=edge['Config']['Labels'];state=edge.get('State',{})
    allowed=manifest.get('runtimeOwnerLabels',[]) if manifest.get('attached') else [manifest['owner']]
    require(labels.get(OWNER) in allowed and labels.get('com.docker.compose.project')==manifest['project']
            and edge.get('Image')==manifest['imageId'] and edge['Config'].get('Cmd')==EDGE_COMMAND
            and state.get('Running') is True and type(state.get('Pid')) is int and state['Pid']>0
            and isinstance(state.get('StartedAt'),str) and state['StartedAt'], 'M7_STATIC_EDGE_RUNTIME')
    return {'status':'VERIFIED','instances':instances,'socketEdge':{'containerId':edge['Id'],'startedAt':state['StartedAt']},
            'scope':'Actual fixed service identities and local running containers, not remote owner eligibility or tenant readiness.'}
