"""Explicit K=1 placement profiles for the existing Kubernetes instrument."""

FIELD = 'applicationTopology'
COHORT = 'cohort'
SEPARATE = 'separate-k1'
ROLES = ('api', 'evaluator', 'realtime', 'tenant-admin')
SEPARATE_WORKLOADS = {
    **{role: 'Deployment' for role in ROLES},
    **{name: 'Deployment' for name in ('pgstream', 'admin', 'ui', 'edge')},
    'postgres': 'StatefulSet', 'vault': 'StatefulSet',
    'provision': 'Job', 'primer': 'Job',
}


def selection(document, need):
    value = document.get(FIELD, COHORT)
    need(isinstance(value, str) and value in (COHORT, SEPARATE), 'APPLICATION_TOPOLOGY_UNSUPPORTED')
    return value


def bind(manifest, config, inventory, need):
    """Derive the run selection once from intent; require the renderer to agree."""
    selected = selection(manifest, need)
    need(selection(inventory, need) == selected, 'APPLICATION_TOPOLOGY_CHANGED')
    need(config.get(FIELD, selected) == selected, 'APPLICATION_TOPOLOGY_CHANGED')
    return {FIELD: selected} if FIELD in manifest or selected != COHORT else {}


def role_mapping(profile):
    return {role: {'workload': ('Deployment/' + role if profile == SEPARATE else 'StatefulSet/cohort'),
                   'container': role} for role in ROLES}


def validate(config, inventory, objects, need):
    profile = selection(config, need)
    need(selection(inventory, need) == profile, 'APPLICATION_TOPOLOGY_CHANGED')
    if profile == COHORT:
        return
    for role, target in role_mapping(profile).items():
        need(config['roles'].get(role) == target, 'APPLICATION_ROLE_TOPOLOGY:' + role)
    need(config['roles'].get('pgstream') == {'workload': 'Deployment/pgstream', 'container': 'pgstream'},
         'APPLICATION_ROLE_TOPOLOGY:pgstream')
    rendered = [obj for obj in objects.values() if obj['kind'] in ('Deployment', 'StatefulSet', 'Job')]
    workloads = {obj['metadata']['name']: obj for obj in rendered}
    need(len(rendered) == len(SEPARATE_WORKLOADS) and set(workloads) == set(SEPARATE_WORKLOADS),
         'APPLICATION_WORKLOAD_ROSTER')
    for name, kind in SEPARATE_WORKLOADS.items():
        obj = workloads[name]
        need(obj['kind'] == kind, 'APPLICATION_WORKLOAD_KIND:' + name)
        if name not in ROLES:
            continue
        need(obj['spec'].get('replicas', 1) == 1 and
             obj['spec'].get('strategy', {}).get('type') == 'Recreate', 'APPLICATION_WORKLOAD_REPLACEMENT:' + name)
        pod = obj['spec']['template']['spec']
        need([actor['name'] for actor in pod['containers']] == [name], 'APPLICATION_PROCESS_ROSTER:' + name)
        need(not any(volume['name'] == 'ns-ipc' for volume in pod.get('volumes', [])),
             'APPLICATION_SOCKET_VOLUME:' + name)


def serving_workload(document, stage, obj, need):
    if stage != 'serving':
        return False
    profile = selection(document, need)
    name = obj['metadata']['name']
    return (obj['kind'] == 'Deployment' and name in ROLES if profile == SEPARATE else
            obj['kind'] == 'StatefulSet' and name == 'cohort')


def readiness_signal(document, name, need):
    return name in ROLES if selection(document, need) == SEPARATE else name == 'cohort'
