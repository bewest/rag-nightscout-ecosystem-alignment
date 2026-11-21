"""Explicit source-bound input transport: writer-driven is the only one."""
from pathlib import Path

from contract import require

WRITER = 'writer-driven'


def options(args):
    require(getattr(args, 'input_transport', WRITER) == WRITER, 'M7_INPUT_TRANSPORT')
    require(args.profile == 'pgstream-sample' and args.run_purpose == 'discovery'
            and args.completion_contract == 'evaluator-work-v2' and getattr(args, 'static_workers', None) is not None,
            'M7_WRITER_DISCOVERY_TOPOLOGY')
    return {'inputTransport': WRITER}


def selection(manifest):
    require(manifest.get('inputTransport') == WRITER, 'M7_INPUT_TRANSPORT')
    require('pgstreamTopology' not in manifest and 'pgstreamNotifierAckTimeoutMs' not in manifest
            and 'commissioningSlotWalMiB' not in manifest, 'M7_WRITER_CDC_OPTION_CONFLICT')
    return WRITER


def verify_config(manifest,config):
    selected=selection(manifest)
    require(config.get('services',{}).get('pgstream') is None
            and config['services'].get('bootstrap', {}).get('environment', {}).get('NS_INPUT_TRANSPORT') == WRITER,
            'M7_WRITER_BINDING_TRANSPORT')
    return selected


def require_snapshot(directory, manifest):
    # The snapshot carries the original deploy .env alongside the archived state.
    # Refuse before fixture.js creates or restores any project volumes.
    path = Path(directory) / 'deployment.env'
    values = dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)
    selection(manifest)
    # Older fixtures recorded NS_INPUT_TRANSPORT; a pgstream fixture recorded NS_PGSTREAM=1.
    require(values.get('NS_INPUT_TRANSPORT', WRITER) == WRITER and 'NS_PGSTREAM' not in values,
            'M7_FIXTURE_INPUT_TRANSPORT_CHANGED')
    workers = str(manifest['staticTopology']['workers'])
    require(values.get('NS_API_REPLICAS','1') == str(manifest['replicas'])
            and values.get('NS_REALTIME_WORKERS','1') == workers
            and values.get('NS_EVALUATOR_WORKERS','1') == workers, 'M7_FIXTURE_TOPOLOGY_CHANGED')


def expected_processes(manifest):
    selection(manifest)
    instances=manifest.get('servingInstances')
    if instances is not None:
        require(isinstance(instances,dict) and instances,'M7_INSTANCE_FROZEN_ROSTER_CHANGED')
        return {service:('node',) for service in instances}
    return {'evaluator':('node',)}


def readable_processes(snapshots,manifest):
    require(not any(p.get('component',p.get('name')) == 'pgstream'
                    for snapshot in snapshots.values() for p in snapshot.get('hostProcesses',{}).values()),
            'M7_WRITER_UNEXPECTED_PGSTREAM')
    for role,names in expected_processes(manifest).items():
        values=snapshots.get(role,{}).get('hostProcesses',{}).values()
        require(all(any(p.get('component',p.get('name'))==name and not p.get('unavailable') for p in values) for name in names),'M7_SAMPLE_PROCESS_INSTRUMENT')


def external_runtime(rows,manifest):
    selection(manifest)
    require(not any(r.get('Config',{}).get('Labels',{}).get('com.docker.compose.service')=='pgstream'
                    for r in rows), 'M7_WRITER_UNEXPECTED_PGSTREAM')
