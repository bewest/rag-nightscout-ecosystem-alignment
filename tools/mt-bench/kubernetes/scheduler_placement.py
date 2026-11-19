"""Observe Kubernetes-selected placement and reuse deploy's node fit check."""
import json
from pathlib import Path
import subprocess

import kube_adapter as k
import matrix


def confirm(packet, binding, client=None):
    """Check already-bound Pods immediately before ordinary traffic."""
    directory, config, objects = k.load(packet)
    client = client or k.Client(config)
    baseline = k.active_baseline(directory)
    current = k.observe(config, objects, client, baseline)
    matrix.identity(config, baseline, current)
    requests = matrix.node_requests(objects, current, k.resource_accounting(config), config)
    incremental = {}
    if config.get('nativeLoad') is not None:
        import native_join
        k.need(current.get('nativeLoadSuspended') is True and not current.get('testActors'),
               'NATIVE_LOAD_EARLY_STARTED')
        node, amount = native_join.reserve(config, objects)
        incremental[node] = {'cpu':amount['millicpus']/1000,'memory':amount['memoryBytes']}
    pods = json.loads(client.call(['get', 'pods', '--all-namespaces', '-o', 'json']))
    live = {pod['metadata']['uid']: pod for pod in pods['items']
            if pod['metadata']['namespace'] == config['namespace']}
    for pod in current['pods'].values():
        actual = live.get(pod['uid'])
        k.need(actual and actual['spec'].get('nodeName') == pod['nodeName'],
               'SCHEDULER_POD_CENSUS_CHANGED', 'UNMEASURED')

    nodes = json.loads(client.call(['get', 'nodes', '-o', 'json']))
    if config.get('nativeLoad') is not None:
        target=config['nativeLoad']['nodeName']
        matches=[node for node in nodes['items'] if node['metadata']['name']==target]
        k.need(len(matches)==1 and matches[0]['metadata'].get('labels',{}).get('kubernetes.io/hostname')==target,
               'NATIVE_LOAD_NODE_SELECTOR_MISMATCH')
    usage = {}
    for line in client.call(['top', 'nodes', '--no-headers']).decode().splitlines():
        node, cpu, _, memory, *_ = line.split()
        usage[node] = {'cpu': cpu, 'memory': memory}
    k.need(requests.keys() <= usage.keys(), 'SCHEDULER_NODE_USAGE_UNMEASURED', 'UNMEASURED')

    # Pass the complete current Pod list. Those requests already include the
    # fixture's bound Pods. Strip peer metadata and container environment.
    pod_fields = ('nodeName', 'overhead')
    container_fields = ('resources', 'restartPolicy')
    projected = []
    for pod in pods['items']:
        spec = pod['spec']
        if spec.get('nodeName') not in requests:
            continue
        data = {key: spec[key] for key in pod_fields if key in spec}
        for group in ('containers', 'initContainers'):
            data[group] = [{key: container[key] for key in container_fields if key in container}
                           for container in spec.get(group, ())]
        projected.append({'spec': data, 'status': {'phase': pod['status'].get('phase')}})
    tool = Path(binding) / 'bindings/kubernetes/ops/fit-check.js'
    script = """const {check} = require(process.argv[1]);
      const {nodes,pods,usage,selected,incremental} = JSON.parse(require('node:fs').readFileSync(0,'utf8'));
      process.stdout.write(JSON.stringify(selected.map(node => check({nodes,pods,node,request:incremental[node]||{cpu:0,memory:0},usage:usage[node]}))));"""
    fit = subprocess.run([config['driver']['node'], '-e', script, str(tool)], check=True,
                         input=json.dumps({'nodes': nodes, 'pods': {'items': projected},
                                           'usage': usage, 'selected': list(requests),'incremental':incremental}),
                         capture_output=True, text=True, timeout=min(20, k.deadline(config)))
    results = json.loads(fit.stdout)
    return {
        'fits': all(row['fits'] for row in results),
        'namespaceUid': current['namespace']['uid'],
        'pods': {name: {key: pod[key] for key in ('uid', 'workload', 'nodeName')}
                 for name, pod in current['pods'].items()},
        'incrementalRequests': incremental if incremental else {'cpu': 0, 'memory': 0},
        'fit': results,
        'nodeCeilings': requests,
    }
