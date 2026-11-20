"""Actual frozen serving-service roster; never infer processes from CLI counts."""
import json
import re
from contract import OWNER, require

FAMILIES = ('api', 'evaluator', 'realtime')


def instance(service):
    match = re.fullmatch(r'(api|evaluator|realtime)(?:-([2-9]|1[0-6]))?', service)
    require(match is not None, 'M7_INSTANCE_SERVICE_NAME')
    return {'service': service, 'role': match[1], 'ordinal': int(match[2] or 1) - 1}


def assignment(item, env, instances, spec=None):
    # Decision statefulset-ordinal-scaling: an evaluator slice is its hostname ordinal
    # (hostname evaluator-<i>) and K (NS_EVALUATOR_SLICES); the retired JSON form below is
    # still read for retained runs.
    if 'NS_EVALUATOR_SLICES' in env:
        count = sum(i['role'] == 'evaluator' for i in instances.values())
        require(env['NS_EVALUATOR_SLICES'] == str(count) and 'NS_PGSTREAM_EVALUATOR_SLICE' not in env,
                'M7_INSTANCE_DECLARED_ORDINAL')
        if item['role'] == 'evaluator':
            require(spec is None or spec.get('hostname') == 'evaluator-%d' % item['ordinal'], 'M7_INSTANCE_DECLARED_ORDINAL')
        else:
            require(env.get('NS_INPUT_TRANSPORT') == 'writer-driven', 'M7_INSTANCE_DECLARED_ORDINAL')
    if item['role'] == 'realtime' and 'NS_SLICE_ORDINAL' in env:
        count = sum(row['role'] == 'realtime' for row in instances.values())
        require(env['NS_SLICE_ORDINAL'] == str(item['ordinal']) and env.get('NS_SLICE_COUNT') == str(count),
                'M7_INSTANCE_DECLARED_ORDINAL')
    for field, family in (('NS_REALTIME_SLICE', 'realtime'), ('NS_PGSTREAM_EVALUATOR_SLICE', 'evaluator')):
        raw = env.get(field)
        if raw is None:
            continue
        require(item['role'] == family, 'M7_INSTANCE_DECLARED_ORDINAL')
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            raise RuntimeError('M7_INSTANCE_DECLARED_ORDINAL') from None
        count = sum(i['role'] == family for i in instances.values())
        require(isinstance(value, dict) and type(value.get('count')) is int and type(value.get('ordinal')) is int
                and value['count'] == count and value['ordinal'] == item['ordinal'], 'M7_INSTANCE_DECLARED_ORDINAL')
        if field == 'NS_REALTIME_SLICE':
            require(set(value) == {'count', 'ordinal'}, 'M7_INSTANCE_DECLARED_ORDINAL')
        else:
            expected = ['http://' + (family if ordinal == 0 else family + '-' + str(ordinal + 1)) + ':19913/' for ordinal in range(count)]
            require(set(value) == {'count', 'ordinal', 'receivers'} and value['receivers'] == expected,
                    'M7_INSTANCE_DECLARED_RECEIVERS')


def roster(config, replicas=None):
    result = {}
    for service, spec in config.get('services', {}).items():
        serving_name = service in FAMILIES or any(service.startswith(r + '-') for r in FAMILIES)
        argv = spec.get('command') or []
        role = argv[-1] if isinstance(argv, list) and argv else None
        if not serving_name and role not in FAMILIES:
            continue
        item = instance(service)
        require(role == item['role'], 'M7_INSTANCE_COMMAND_ROLE')
        result[service] = item
    for family in FAMILIES:
        values = sorted(i['ordinal'] for i in result.values() if i['role'] == family)
        require(values == list(range(len(values))), 'M7_INSTANCE_ORDINAL_COVERAGE')
    if replicas is not None:
        require(sum(i['role'] == 'api' for i in result.values()) == replicas, 'M7_INSTANCE_API_COVERAGE')
    for service, item in result.items():
        spec = config['services'][service]
        count = sum(i['role'] == item['role'] for i in result.values())
        item['count'] = count
        labels = spec.get('labels') or {}
        for key, value in (('ordinal', item['ordinal']), ('count', count)):
            actual = labels.get('org.nightscout.static-ownership.' + key)
            require(actual is None or actual == str(value), 'M7_INSTANCE_DECLARED_ORDINAL')
        assignment(item, spec.get('environment') or {}, result, spec)
    return dict(sorted(result.items(), key=lambda p: (FAMILIES.index(p[1]['role']), p[1]['ordinal'])))


def runtime(rows, expected, manifest):
    """Bind each expected service to one physical container, with no replacement."""
    result = {}
    ids = set()
    static = manifest.get('staticTopology')
    if static is not None:
        require(isinstance(static, dict) and type(static.get('workers')) is int
                and static['workers'] > 0 and all(sum(item['role'] == role for item in expected.values()) == static['workers']
                                                for role in ('evaluator', 'realtime')), 'M7_INSTANCE_RUNTIME_TOPOLOGY')
    for row in rows:
        labels = row.get('Config', {}).get('Labels', {})
        service = labels.get('com.docker.compose.service', '')
        if not (service in FAMILIES or any(service.startswith(r + '-') for r in FAMILIES)):
            continue
        require(service in expected and service not in result, 'M7_INSTANCE_RUNTIME_ROSTER')
        item = expected[service]
        state = row.get('State', {})
        allowed_owners=manifest.get('runtimeOwnerLabels',[]) if manifest.get('attached') else [manifest['owner']]
        require(labels.get(OWNER) in allowed_owners and labels.get('com.docker.compose.project') == manifest['project']
                and row.get('Image') == manifest['imageId'], 'M7_INSTANCE_RUNTIME_IDENTITY')
        require(state.get('Running') is True and isinstance(state.get('StartedAt'), str) and state['StartedAt']
                and type(state.get('Pid')) is int and state['Pid'] > 0, 'M7_INSTANCE_RUNTIME_BIRTH')
        require(row.get('Id') and row['Id'] not in ids and row.get('Config', {}).get('Cmd', [])[-1:] == [item['role']],
                'M7_INSTANCE_RUNTIME_IDENTITY')
        for key in ('ordinal', 'count'):
            actual = labels.get('org.nightscout.static-ownership.' + key)
            require(actual is None or actual == str(item[key]), 'M7_INSTANCE_DECLARED_ORDINAL')
        env = dict(value.split('=', 1) for value in row.get('Config', {}).get('Env', []) if '=' in value)
        # The ordinary binding loads env.json inside the process. Inspect Env
        # can expose a conflicting selector, but absence does not prove it is unloaded.
        spec = {'hostname':row['Config'].get('Hostname')} if manifest.get('inputTransport') == 'writer-driven' else None
        assignment(item, env, expected, spec)
        ids.add(row['Id'])
        result[service] = row
    require(set(result) == set(expected), 'M7_INSTANCE_RUNTIME_ROSTER')
    return result


def sql_coverage(config, expected, state):
    """Declared SQL identities only; shared users are never per-process cost."""
    from pathlib import Path
    from sql_attribution import _postgres_identity
    services = {}
    users = {}
    for service in expected:
        mounts = [v for v in config['services'][service].get('volumes', []) if v.get('target') == '/run/ns-config']
        require(len(mounts) == 1 and mounts[0].get('type') == 'bind' and mounts[0].get('read_only') is True,
                'M7_INSTANCE_SQL_CONFIG_MOUNT')
        source = Path(mounts[0]['source']).resolve()
        require(source.is_relative_to(Path(state).resolve()), 'M7_INSTANCE_SQL_FOREIGN_CONFIG')
        env = json.loads((source / 'env.json').read_text())
        assignment(expected[service], env, expected)
        roles = sorted({_postgres_identity(value)[0] for value in env.values()
                        if isinstance(value, str) and value.startswith(('postgres:', 'postgresql:'))})
        require(roles, 'M7_INSTANCE_SQL_IDENTITY_MISSING')
        services[service] = {'sqlRoles': roles, 'processCost': 'UNMEASURED'}
        for role in roles:
            users.setdefault(role, []).append(service)
    return {'status': 'MAPPED', 'services': services, 'sqlRoleConsumers': users,
            'sharedSqlRoles': sorted(role for role, consumers in users.items() if len(consumers) > 1),
            'processAttribution': 'UNMEASURED',
            'scope': 'Configured SQL identities by actual service; pg_stat_statements remains per SQL user. Shared identity totals are counted once and cannot be split by ordinal. A configured connection does not prove active use.'}


def effective_limits(a, row):
    if 'HostConfig' not in row:
        return {'status': 'UNMEASURED', 'reason': 'M7_INSTANCE_LIMITS_NO_INSPECT'}
    declared = {k: row['HostConfig'].get(k) for k in ('NanoCpus', 'CpuQuota', 'CpuPeriod', 'Memory', 'MemorySwap')}
    try:
        lines = a.command(['docker', 'exec', row['Id'], 'cat', '/sys/fs/cgroup/cpu.max',
                           '/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.swap.max']).splitlines()
        require(len(lines) == 3, 'M7_INSTANCE_EFFECTIVE_LIMITS')
        quota, period = lines[0].split()
        require(period.isdigit() and int(period) > 0 and (quota == 'max' or quota.isdigit())
                and all(v == 'max' or v.isdigit() for v in lines[1:]), 'M7_INSTANCE_EFFECTIVE_LIMITS')
        return {'status': 'MEASURED', 'declared': declared,
                'millicpus': None if quota == 'max' else int(quota) * 1000 / int(period),
                'memoryBytes': None if lines[1] == 'max' else int(lines[1]),
                'swapBytes': None if lines[2] == 'max' else int(lines[2]),
                'scope': 'Effective cgroup v2 limits at this read; null means unlimited, not zero.'}
    except (RuntimeError, ValueError, KeyError, TypeError):
        return {'status': 'UNMEASURED', 'reason': 'M7_INSTANCE_EFFECTIVE_LIMITS', 'declared': declared}
