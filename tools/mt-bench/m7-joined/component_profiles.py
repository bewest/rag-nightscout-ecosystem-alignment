"""Pure declarations for source-pinned M7 component profiles; never a runtime proof.

No I/O, environment reads, dependency installation, Compose execution or defaults.
The producer must separately admit the paired shipping plan and actual resources.
"""
import copy
import hashlib
import json
import re

COUNTS = (1, 2, 4)
CLASSES = ('api', 'realtime', 'evaluator', 'postgres', 'vault-server', 'vault-agent')
SHA = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')
MAX_BYTES = 65536


class Refused(ValueError):
    """A bounded declaration is absent, inconsistent or unsupported."""


def need(condition, code):
    if not condition:
        raise Refused('M7_COMPONENT_' + code)


def exact(value, keys, code):
    need(type(value) is dict and set(value) == set(keys), code)


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError):
        raise Refused('M7_COMPONENT_JSON_INVALID') from None
    need(len(raw) <= MAX_BYTES, 'DOCUMENT_BOUND')
    return raw


def hashed(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_selection(value):
    """Validate exact schema; return an independent normalized declaration."""
    canonical(value)
    exact(value, ('version', 'apiReplicas', 'realtime', 'evaluator', 'secrets', 'resources'), 'SELECTION_FIELDS')
    need(type(value['version']) is int and value['version'] == 1, 'VERSION')
    need(type(value['apiReplicas']) is int and value['apiReplicas'] in COUNTS, 'API_COUNT')
    for role in ('realtime', 'evaluator'):
        spec = value[role]
        exact(spec, ('mode', 'workers', 'shards') if role == 'realtime' else ('mode', 'workers'), 'WORKER_FIELDS')
        need(spec['mode'] in ('standalone', 'fixed'), 'WORKER_MODE')
        need(type(spec['workers']) is int and spec['workers'] in COUNTS, 'WORKER_COUNT')
        need(spec['mode'] == 'fixed' or spec['workers'] == 1, 'STANDALONE_COUNT')
        if role == 'realtime':
            need(integer(spec['shards'], 1, 4096), 'SHARDS')
    secrets = value['secrets']
    exact(secrets, ('mode', 'agent'), 'SECRETS_FIELDS')
    need(secrets['mode'] in ('vault-server', 'vault-agent'), 'SECRETS_MODE')
    agent = secrets['agent']
    exact(agent, ('tokenTtlSeconds', 'tokenMaxTtlSeconds', 'policySha256', 'secretIdTtlSeconds', 'secretIdNumUses'), 'AGENT_FIELDS')
    need(integer(agent['tokenTtlSeconds'], 1, 2764800) and integer(agent['tokenMaxTtlSeconds'], agent['tokenTtlSeconds'], 2764800), 'AGENT_TOKEN_BOUND')
    need(type(agent['policySha256']) is str and SHA.fullmatch(agent['policySha256']) is not None, 'AGENT_POLICY')
    need(type(agent['secretIdTtlSeconds']) is int and agent['secretIdTtlSeconds'] == 0 and type(agent['secretIdNumUses']) is int and agent['secretIdNumUses'] == 0, 'AGENT_LIFETIME')
    exact(value['resources'], CLASSES, 'RESOURCE_CLASSES')
    for budget in value['resources'].values():
        need(type(budget) is dict, 'RESOURCE_FIELDS')
        if budget.get('mode') == 'unlimited':
            exact(budget, ('mode',), 'RESOURCE_FIELDS')
        else:
            exact(budget, ('mode', 'cpuNano', 'memoryBytes'), 'RESOURCE_FIELDS')
            need(budget['mode'] == 'finite', 'RESOURCE_MODE')
            need(integer(budget['cpuNano'], 10000000, 128000000000), 'CPU_BOUND')
            need(integer(budget['memoryBytes'], 16777216, 1099511627776), 'MEMORY_BOUND')
    return copy.deepcopy(value)


def prepare_environment(selection):
    """Only the existing shipping selectors. Agent is a separate shipping overlay."""
    s = validate_selection(selection)
    result = {'NS_API_REPLICAS': str(s['apiReplicas'])}
    if s['realtime']['mode'] == 'fixed':
        result.update(NS_REALTIME_WORKERS=str(s['realtime']['workers']), NS_REALTIME_SHARDS=str(s['realtime']['shards']))
    if s['evaluator']['mode'] == 'fixed':
        result['NS_EVALUATOR_WORKERS'] = str(s['evaluator']['workers'])
    return result


def _names(role, count):
    return [role if n == 1 else role + '-' + str(n) for n in range(1, count + 1)]


def _inventory(s):
    serving = {'postgres': 'postgres', 'vault': 'vault-server', 'feed-reader': 'feed-reader', 'admin': 'admin',
               'tenant-admin': 'tenant-admin', 'ui': 'ui', 'nginx': 'nginx'}
    for role, count in [('api', s['apiReplicas']), ('realtime', s['realtime']['workers']), ('evaluator', s['evaluator']['workers'])]:
        serving.update({name: role for name in _names(role, count)})
    if s['realtime']['mode'] == 'fixed':
        serving['socket-edge'] = 'socket-edge'
    one_shot = ['bootstrap', 'primer', 'placement-operator', 'demo']
    if s['secrets']['mode'] == 'vault-agent':
        serving['vault-agent'] = 'vault-agent'
        one_shot.append('vault-agent-bootstrap')
    return {'serving': dict(sorted(serving.items())), 'oneShot': sorted(one_shot),
            'workerMembership': 'all-configured-including-idle; assignment-unmeasured'}


def _command(service, role):
    if role in ('api', 'realtime', 'evaluator', 'admin', 'feed-reader', 'tenant-admin'):
        return ['node', 'deploy/multitenant/entrypoint.js', role]
    if role in ('ui', 'socket-edge'):
        return ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/' + role + '.js']
    return {'vault-server': ['vault', 'server', '-config=/vault/config/demo.hcl'],
            'vault-agent': ['vault', 'agent', '-config=/vault/config/agent.hcl'],
            'bootstrap': ['node', 'deploy/multitenant/bootstrap.js'],
            'primer': ['node', 'deploy/multitenant/prime.js', 'provision'],
            'placement-operator': ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/placement-control.js'],
            'demo': ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/demo.js'],
            'vault-agent-bootstrap': ['node', '/run/ns-overlay/vault-agent-bootstrap.js', 'provision']}.get(role)


def exact_role_inventory(selection, compose):
    """Check complete resolved shipping config, not just running/nonidle services.

    This is structural admission only. Original source/mount/owner identity gates
    remain mandatory; the function cannot attest a Docker object or a tenant map.
    """
    s = validate_selection(selection)
    need(type(compose) is dict and type(compose.get('services')) is dict, 'COMPOSE_FIELDS')
    inventory = _inventory(s)
    specs = compose['services']
    need(set(specs) == set(inventory['serving']) | set(inventory['oneShot']), 'ROSTER_MISMATCH')
    for name, spec in specs.items():
        need(type(spec) is dict, 'SERVICE_FIELDS')
        is_op = name in inventory['oneShot']
        need(spec.get('profiles', []) == (['ops'] if is_op else []), 'SERVICE_PROFILE')
        role = inventory['serving'].get(name, name)
        expected = _command(name, role)
        if role == 'postgres':
            cmd = spec.get('command')
            need(type(cmd) is list and len(cmd) >= 1 and cmd[0] == 'postgres', 'ROLE_COMMAND')
        elif role == 'nginx':
            need('command' not in spec or spec['command'] is None, 'ROLE_COMMAND')
        else:
            need(spec.get('command') == expected, 'ROLE_COMMAND')
    # Reject sink exposure on any ancillary/one-shot role; Agent bootstrap owns
    # /state only and gets no direct serving sink mount. Exact source/UID custody
    # and allowed HCL/bootstrap mounts are separately checked by shipping plan.
    sinks = {}
    for name, spec in specs.items():
        volumes = spec.get('volumes', [])
        need(type(volumes) is list, 'MOUNT_SHAPE')
        for volume in volumes:
            need(type(volume) is dict, 'RESOLVED_MOUNT_REQUIRED')
            target = volume.get('target', '')
            need(type(target) is str, 'MOUNT_SHAPE')
            if target == '/run/ns-vault' or target.startswith('/run/ns-vault/'):
                need(target == '/run/ns-vault' and name not in sinks, 'SINK_CUSTODY')
                sinks[name] = volume
    if s['secrets']['mode'] == 'vault-server':
        need(not sinks, 'SINK_CUSTODY')
    else:
        apis = set(_names('api', s['apiReplicas']))
        need(set(sinks) == apis | {'vault-agent'}, 'SINK_CUSTODY')
        source = sinks['vault-agent'].get('source')
        need(type(source) is str and source.startswith('/') and sinks['vault-agent'].get('type') == 'bind' and sinks['vault-agent'].get('read_only', False) is False, 'SINK_CUSTODY')
        for name in apis:
            need(sinks[name].get('type') == 'bind' and sinks[name].get('source') == source and sinks[name].get('read_only') is True, 'SINK_CUSTODY')
    return inventory


def resource_overlay(selection):
    """Deterministic resource-only Compose override; no source/command/env edits.

    Explicit unlimited emits zero to clear prior limits; it proves no finite
    budget. Ancillary safety budgets (e.g. feed-reader) are never overridden.
    """
    s = validate_selection(selection)
    services = {}
    for name, role in _inventory(s)['serving'].items():
        if role not in CLASSES:
            continue
        budget = s['resources'][role]
        if budget['mode'] == 'unlimited':
            services[name] = {'cpus': '0', 'mem_limit': 0}
        else:
            whole, fraction = divmod(budget['cpuNano'], 1000000000)
            cpu = str(whole) + ('.' + str(fraction).zfill(9).rstrip('0') if fraction else '')
            services[name] = {'cpus': cpu, 'mem_limit': budget['memoryBytes']}
    return {'services': services}


def validate_context(context):
    exact(context, ('coreCommit', 'deployCommit', 'instrumentSha256', 'hostIdentitySha256', 'sourcePlanSha256', 'settingsFingerprintSha256', 'diagnostics', 'custody'), 'CONTEXT_FIELDS')
    for field in ('coreCommit', 'deployCommit'):
        need(type(context[field]) is str and COMMIT.fullmatch(context[field]) is not None, 'SOURCE_IDENTITY')
    for field in ('instrumentSha256', 'hostIdentitySha256', 'sourcePlanSha256', 'settingsFingerprintSha256'):
        need(type(context[field]) is str and SHA.fullmatch(context[field]) is not None, 'CONTEXT_IDENTITY')
    exact(context['diagnostics'], ('mode', 'intervalMs'), 'DIAGNOSTICS_FIELDS')
    need(context['diagnostics']['mode'] in ('off', 'on') and integer(context['diagnostics']['intervalMs'], 1000, 60000), 'DIAGNOSTICS')
    exact(context['custody'], ('kind', 'sha256'), 'CUSTODY_FIELDS')
    need(context['custody']['kind'] == 'paired-compose-plan-v1' and type(context['custody']['sha256']) is str and SHA.fullmatch(context['custody']['sha256']) is not None, 'CUSTODY_UNSUPPORTED')
    return copy.deepcopy(context)


def profile_identity(selection, context):
    """Canonical declaration, never a receipt of observed limits or acceptance."""
    s, c = validate_selection(selection), validate_context(context)
    value = {'version': 1, 'kind': 'm7-component-profile-declaration', 'selection': s, 'context': c,
             'inventory': _inventory(s), 'resourceOverlay': resource_overlay(s),
             'runtimeProof': 'UNMEASURED'}
    return {**value, 'sha256': hashed(value)}


def validate_identity(value, expected_context):
    exact(value, ('version', 'kind', 'selection', 'context', 'inventory', 'resourceOverlay', 'runtimeProof', 'sha256'), 'IDENTITY_FIELDS')
    expected = profile_identity(value['selection'], expected_context)
    need(canonical(value) == canonical(expected), 'IDENTITY_MISMATCH')
    return copy.deepcopy(expected)


def compare_profiles(before, after, axis, expected_context):
    """Exactly one changed scalar, recomputing every derived roster/resource row.

    Worker-count changes inherit an unchanged per-role resource policy. Generated
    rows may change only as that exact derivation dictates; never ignore a row.
    """
    a = validate_identity(before, expected_context)
    b = validate_identity(after, expected_context)
    allowed = {'apiReplicas', 'realtime.mode', 'realtime.workers', 'realtime.shards', 'evaluator.mode', 'evaluator.workers', 'secrets.mode'}
    allowed.update('resources.' + role + '.' + field for role in CLASSES for field in ('cpuNano', 'memoryBytes'))
    need(type(axis) is str and axis in allowed, 'AXIS_UNSUPPORTED')
    def leaves(value, prefix=''):
        if type(value) is dict:
            out = {}
            for key, child in value.items():
                out.update(leaves(child, prefix + '.' + key if prefix else key))
            return out
        return {prefix: value}
    left, right = leaves(a['selection']), leaves(b['selection'])
    changed = {k for k in set(left) | set(right) if k not in left or k not in right or left[k] != right[k]}
    need(changed == {axis}, 'COMPARISON_SECOND_AXIS_OR_UNCHANGED')
    if axis == 'realtime.shards':
        need(a['selection']['realtime']['mode'] == b['selection']['realtime']['mode'] == 'fixed', 'FIXED_SHARDS_REQUIRED')
    if axis.startswith('resources.'):

        role = axis.split('.')[1]
        need(role in a['inventory']['serving'].values() and a['selection']['resources'][role]['mode'] == 'finite' and b['selection']['resources'][role]['mode'] == 'finite', 'FINITE_RESOURCE_REQUIRED')
    return {'version': 1, 'kind': 'm7-single-axis-declaration-comparison', 'axis': axis,
            'beforeSha256': a['sha256'], 'afterSha256': b['sha256'], 'runtimeProof': 'UNMEASURED'}
