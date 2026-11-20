"""Explicit source-bound static branch diagnostics through the ordinary binding."""
import json
import re
from pathlib import Path
from contract import require, discovery_api_replicas, discovery_workers
import workload_inputs
import role_instances
import stream_topology

# Run identity is the image digest (imageId) plus the run configuration; any
# commit pair is accepted and recorded, and no build receipt is required.
KIND = 'static-hash-v1'
EDGE_COMMAND = ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/socket-edge.js']


def validate(manifest):
    value = manifest.get('staticTopology')
    if value is None:
        return None
    require(isinstance(value, dict) and set(value) == {'kind', 'workers'} and value['kind'] == KIND
            and discovery_workers(value['workers']), 'M7_STATIC_TOPOLOGY')
    pair = manifest.get('pair')
    require(isinstance(pair, dict) and set(pair) == {'core', 'deploy'}
            and all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{40}', v) for v in pair.values()), 'M7_STATIC_SOURCE_PAIR')
    require(manifest.get('profile') == 'pgstream-sample' and manifest.get('runPurpose') == 'discovery'
            and stream_topology.selection(manifest) in (stream_topology.EXTERNAL, stream_topology.WRITER)
            and manifest.get('completionContract') == 'evaluator-work-v2'
            and discovery_api_replicas(manifest.get('replicas')),
            'M7_STATIC_DIAGNOSTIC_SCOPE')
    return value


def option(args):
    count = getattr(args, 'static_workers', None)
    if count is None:
        return {}
    manifest = {'staticTopology': {'kind': KIND, 'workers': count},
                'pair': {'core': args.core_commit, 'deploy': args.deploy_commit},
                'profile': args.profile, 'runPurpose': args.run_purpose,
                **stream_topology.options(args), 'completionContract': args.completion_contract,
                'replicas': args.replicas}
    validate(manifest)
    # No explicit allocation selects uncapped Compose services (an explained
    # default reported by `runner.py plan`); it is not a refusal.
    return {'staticTopology': manifest['staticTopology']}


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


def verify_config(manifest, config):
    value = validate(manifest)
    if value is None:
        require('socket-edge' not in config.get('services', {}), 'M7_STATIC_SELECTION_REQUIRED')
        return None
    if 'tenants' in manifest:
        seed_service = 'primer' if 'NS_DEMO_TENANTS' in config['services'].get('primer', {}).get('environment', {}) else 'bootstrap'
        require(workload_inputs.tenants(manifest['tenants'])
                and config['services'].get(seed_service, {}).get('environment', {}).get('NS_DEMO_TENANTS') == str(manifest['tenants']),
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
    require(edge.get('restart') in ('on-failure', 'unless-stopped') and
            all(config['services'][name].get('restart') in ('on-failure', 'unless-stopped') for name in instances if instances[name]['role'] != 'api'),
            'M7_STATIC_PLATFORM_RESTART')
    if stream_topology.selection(manifest) == stream_topology.WRITER:
        verify_writer_targets(config['services'], instances, count)
    return instances


def verify_writer_targets(services, instances, count):
    for role, zone, port in [('evaluator','evaluator',19002), ('realtime','realtime-peers',19003)]:
        addresses = []
        for i in range(count):
            host = f'{role}-{i}'
            alias = f'{host}.{zone}'
            spec = services[service(role,i)]
            require(spec.get('hostname') == host and alias in spec['networks']['backend'].get('aliases', [])
                    and spec['environment'].get('NS_SERVE_INTERNAL_PORT') == str(port)
                    and not spec['environment'].get('NS_SERVE_INTERNAL_SOCKET'), 'M7_WRITER_ORDINAL_ADDRESS')
            addresses.append(f'http://{alias}:{port}/')
        for name in [*instances, 'tenant-admin']:
            env = services[name].get('environment', {})
            prefix = 'NS_' + role.upper()
            require(env.get('NS_INPUT_TRANSPORT') == stream_topology.WRITER, 'M7_WRITER_BINDING_TRANSPORT')
            require(env.get(prefix+'_SLICES') == str(count), 'M7_WRITER_TARGET_COUNT')
            if count == 1:
                require(env.get(prefix+'_INTERNAL_URL') == f'http://{role}:{port}/'
                        and not env.get(prefix+'_INTERNAL_SOCKET'), 'M7_WRITER_TARGET_ADDRESS')
            else:
                template = env.get(prefix+'_SLICE_URL', '')
                require([template.replace('{i}',str(i)) for i in range(count)] == addresses, 'M7_WRITER_TARGET_ADDRESS')
            if role == 'realtime' and env.get('NS_REALTIME_SLICE_PEERS'):
                require(json.loads(env['NS_REALTIME_SLICE_PEERS']) == [{'url':url} for url in addresses],
                        'M7_WRITER_TARGET_ADDRESS')


def writer_seed(directory, config, instances):
    """Read the final bootstrap marker and role-private credential files by name only."""
    state = (Path(directory)/'state').resolve()
    complete = json.loads((state/'bootstrap/complete.json').read_bytes())
    require(complete.get('inputTransport') == stream_topology.WRITER, 'M7_FIXTURE_INPUT_TRANSPORT_CHANGED')
    require(not (state/'credentials/postgres/pgstream').exists() and not (state/'pgstream/pgstream.yaml').exists(),
            'M7_WRITER_UNEXPECTED_STREAM_SEED')
    # Read the role names exported by the exact overlaid binding. It writes one
    # file per connection, with the legacy evaluator recovery connection omitted.
    import subprocess
    render = Path(directory)/'core/deploy/multitenant/render.js'
    code = 'console.log(JSON.stringify(require(process.argv[1]).connections))'
    connections = json.loads(subprocess.check_output(['node','-e',code,render],timeout=10))
    verified = {}
    roles = {name: row['role'] for name, row in instances.items()}
    for name,role in {**roles, 'tenant-admin':'tenant-admin', 'admin':'admin'}.items():
        mounts = [v for v in config['services'][name]['volumes'] if v.get('target') == '/run/ns-config']
        require(len(mounts) == 1 and mounts[0].get('read_only') is True and mounts[0].get('type') == 'bind'
                and Path(mounts[0]['source']).resolve() == state/name, 'M7_STATIC_CONFIG_MOUNT')
        expected = {key.lower() for key in connections[role] if key != 'NS_STREAM_RECOVERY_PG'}
        files = {p.name for p in (state/name).glob('ns_*') if p.is_file() and p.stat().st_size}
        require(files == expected, 'M7_WRITER_ROLE_CREDENTIALS')
        verified[name] = sorted(files)
    return {'inputTransport':stream_topology.WRITER, 'roleCredentialFiles':verified}


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
            hostname = env.get('NS_EVALUATOR_SLICES') == str(value['workers'])  # hostname ordinal form
            require((hostname or 'NS_PGSTREAM_EVALUATOR_SLICE' in env) and json.loads(env.get('NS_REALTIME_SLICE_PEERS', 'null')) == peer_list, 'M7_STATIC_PRIVATE_PEERS')
            stream = conf.get('pgstream', {})
            receiver = f'http://evaluator-{item["ordinal"]}.evaluator:19913/' if hostname else f'http://{name}:19913/'
            require(stream.get('receiver', {}).get('url') in (receiver, None if hostname else receiver), 'M7_STATIC_RECEIVER')
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
