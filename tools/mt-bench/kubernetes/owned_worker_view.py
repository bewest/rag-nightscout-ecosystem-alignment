"""Private guard projection for the exact placement reads. Never print raw inputs."""
import json
import re
import subprocess
import sys

from owned_worker import LABEL, NAME, POOL_LABEL, PROVIDER_NODE_LABEL

NODE_LABELS = (LABEL, POOL_LABEL, PROVIDER_NODE_LABEL, 'doks.digitalocean.com/node-pool',
               'topology.kubernetes.io/region', 'node.kubernetes.io/instance-type')
STANDARD_KEYS = ('node.kubernetes.io/not-ready', 'node.kubernetes.io/unreachable')


def operation(argv):
    flags = list(argv)
    context = namespace = None
    while flags and flags[0].startswith('--'):
        flag = flags.pop(0)
        if flag == '--context' and context is None:
            context = flags.pop(0)
        elif flag == '--namespace' and namespace is None:
            namespace = flags.pop(0)
        elif not re.fullmatch(r'--request-timeout=[1-9][0-9]*s', flag):
            raise ValueError('flag')
    if (not context or not re.fullmatch(r'[a-zA-Z0-9_.:@/-]+', context) or context.startswith('-')
            or (namespace is not None and not NAME.fullmatch(namespace)) or flags[-2:] != ['-o','json']):
        raise ValueError('scope')
    command = flags[:-2]
    if len(command) == 3 and command[:2] == ['get','node'] and NAME.fullmatch(command[2]):
        return 'node'
    if (len(command) == 5 and command[:3] == ['get','pods','--all-namespaces']
            and re.fullmatch(r'--field-selector=spec\.nodeName=[a-z0-9][a-z0-9-]{0,62}', command[3])
            and command[4] == '--chunk-size=0'):
        return 'pods'
    raise ValueError('operation')


def projected_taint(row):
    if row.get('key') != LABEL or set(row) != {'key','value','effect'}:
        return {}
    return {key: row[key] for key in ('key','value','effect')}


def projected_toleration(row):
    if row.get('key') not in (LABEL, *STANDARD_KEYS) or not set(row) <= {
            'key','value','operator','effect','tolerationSeconds'}:
        return {}
    return row


def node(row):
    meta, spec, status = (row[key] for key in ('metadata','spec','status'))
    return {'kind':row.get('kind'), 'metadata':{**{key:meta.get(key) for key in ('name','uid','deletionTimestamp')},
        'labels':{key:meta.get('labels', {}).get(key) for key in NODE_LABELS}},
        'spec':{'providerID':spec.get('providerID'), 'unschedulable':spec.get('unschedulable',False),
                'taints':[projected_taint(taint) for taint in spec.get('taints',[])]},
        'status':{'conditions':[{key:cond.get(key) for key in ('type','status')} for cond in status.get('conditions',[])]}}


def pod(row):
    meta, spec = row['metadata'], row['spec']
    selector = spec.get('nodeSelector', {})
    return {'kind':row.get('kind'), 'metadata':{**{key:meta.get(key) for key in
            ('namespace','name','uid','deletionTimestamp')}, 'ownerReferences':[
            {key:ref.get(key) for key in ('kind','name','uid','controller')}
            for ref in meta.get('ownerReferences',[])]},
            'spec':{'nodeName':spec.get('nodeName'),
                    'nodeSelector':selector if set(selector) <= {LABEL} else {},
                    'tolerations':[projected_toleration(tol) for tol in spec.get('tolerations',[])]}}


def main(argv):
    try:
        kind = operation(argv)
        value = subprocess.run(['kubectl', *argv], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        observed = json.loads(value.stdout)
        if kind == 'node':
            print(json.dumps(node(observed)))
        else:
            items = observed['items']
            if not isinstance(items,list):
                raise ValueError('items')
            meta = observed['metadata']
            print(json.dumps({'kind':observed['kind'], 'apiVersion':observed['apiVersion'],
                  'metadata':{key:meta[key] for key in ('continue','remainingItemCount') if key in meta},
                  'items':[pod(row) for row in items]}))
    except (ValueError, IndexError, TypeError, KeyError, OSError, subprocess.SubprocessError):
        print('K8S_OWNED_WORKER_VIEW_REFUSED', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
