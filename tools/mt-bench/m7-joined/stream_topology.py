"""Explicit source-bound pgstream process topology; no runtime substitution."""
import json
import os
from pathlib import Path
import stat
import tempfile

from contract import digest, require
from producer_wire import ACK_BUDGET, WIRE_DIRECTORY, WIRE_NAME, load_wire, valid_timeout

COLOCATED = 'colocated-v1'
EXTERNAL = 'external-service-v1'
EXTERNAL_COMMAND = ['/usr/local/bin/pgstream','run','-c','/run/ns-stream/pgstream.yaml','--log-level','info']
SOURCE_ACK_TIMEOUT_MS = 2000


def ack_selection(manifest):
    if ACK_BUDGET not in manifest:
        return {}
    value = manifest[ACK_BUDGET]
    require(manifest.get('profile') == 'pgstream-sample' and manifest.get('runPurpose') == 'discovery'
            and selection(manifest) == EXTERNAL, 'M7_PGSTREAM_ACK_LOCAL_EXTERNAL_DISCOVERY_REQUIRED')
    require(valid_timeout(value), 'M7_PGSTREAM_ACK_BUDGET_INVALID')
    return {ACK_BUDGET: value}


def ack_option(args):
    value = getattr(args, 'pgstream_notifier_ack_timeout_ms', None)
    if value is None:
        return {}
    require(getattr(args, 'command', 'prepare') == 'prepare', 'M7_PGSTREAM_ACK_FRESH_PREPARE_REQUIRED')
    return ack_selection({ACK_BUDGET: value, 'profile': args.profile, 'runPurpose': args.run_purpose,
                          'pgstreamTopology': args.pgstream_topology})


def wire_path(directory, mounts):
    root = directory/'state/pgstream'
    selected = [mount for mount in mounts if mount.get('target', mount.get('Destination')) == WIRE_DIRECTORY]
    require(len(selected) == 1, 'M7_PGSTREAM_ACK_WIRE_MOUNT')
    mount = selected[0]
    require(mount.get('type', mount.get('Type')) == 'bind'
            and mount.get('source', mount.get('Source')) == str(root)
            and (mount.get('read_only') is True or mount.get('RW') is False), 'M7_PGSTREAM_ACK_WIRE_MOUNT')
    path = root/WIRE_NAME
    require(path.resolve() == path and path.is_file(), 'M7_PGSTREAM_ACK_WIRE_PATH')
    return path


def install_ack_budget(directory, manifest, compose):
    options = ack_selection(manifest)
    if not options:
        return None
    path = wire_path(directory, compose['services']['pgstream']['volumes'])
    config, notifier = load_wire(path.read_bytes())
    require(notifier.get('client_timeout') == SOURCE_ACK_TIMEOUT_MS, 'M7_PGSTREAM_ACK_SOURCE_DEFAULT_CHANGED')
    original = digest(path)
    ownership = path.stat()
    notifier['client_timeout'] = options[ACK_BUDGET]
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as staged:
        temporary = Path(staged.name)
        try:
            own = os.fstat(staged.fileno())
            require((own.st_uid, own.st_gid) == (ownership.st_uid, ownership.st_gid), 'M7_PGSTREAM_ACK_WIRE_OWNER')
            os.fchmod(staged.fileno(), stat.S_IMODE(ownership.st_mode))
            json.dump(config, staged, indent=2)
            staged.write('\n')
            staged.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'sourceTimeoutMs': SOURCE_ACK_TIMEOUT_MS, 'effectiveTimeoutMs': options[ACK_BUDGET],
            'sourceWireSha256': original, 'effectiveWireSha256': digest(path)}


def verify_ack_budget(directory, manifest, mounts):
    path = wire_path(directory, mounts)
    _, notifier = load_wire(path.read_bytes())
    record = manifest.get('pgstreamNotifierAckWire', {})
    require(record.get('effectiveTimeoutMs') == manifest[ACK_BUDGET] == notifier.get('client_timeout')
            and record.get('effectiveWireSha256') == digest(path), 'M7_PGSTREAM_ACK_WIRE_CHANGED')


def selection(manifest):
    value=manifest.get('pgstreamTopology',COLOCATED)
    require(value in (COLOCATED,EXTERNAL),'M7_PGSTREAM_TOPOLOGY_INVALID')
    return value


def verify_config(manifest,config):
    selected=selection(manifest);service=config.get('services',{}).get('pgstream')
    if selected==EXTERNAL:
        require(manifest.get('profile')=='pgstream-sample' and service is not None and service.get('command')==EXTERNAL_COMMAND,'M7_PGSTREAM_EXTERNAL_SERVICE_REQUIRED')
        require(config['services'].get('evaluator',{}).get('command',[])[-1:]==['evaluator'],'M7_PGSTREAM_EVALUATOR_REQUIRED')
    else:
        require(service is None,'M7_PGSTREAM_TOPOLOGY_SELECTION_REQUIRED')
    return selected


def expected_processes(manifest):
    instances=manifest.get('servingInstances')
    if instances is not None:
        require(isinstance(instances,dict) and instances,'M7_INSTANCE_FROZEN_ROSTER_CHANGED')
        result={service:('node',) for service in instances}
        if selection(manifest)==EXTERNAL:result['pgstream']=('pgstream',)
        else:
            for service,item in instances.items():
                if item['role']=='evaluator':result[service]=('node','pgstream')
        return result
    if selection(manifest)==EXTERNAL:return {'evaluator':('node',),'pgstream':('pgstream',)}
    return {'evaluator':('node','pgstream')}


def readable_processes(snapshots,manifest):
    for role,names in expected_processes(manifest).items():
        values=snapshots.get(role,{}).get('hostProcesses',{}).values()
        require(all(any(p.get('component',p.get('name'))==name and not p.get('unavailable') for p in values) for name in names),'M7_SAMPLE_PROCESS_INSTRUMENT')


def verify_source(manifest,schema):
    if selection(manifest)==EXTERNAL:
        value=schema.get('properties',{}).get('pgstream',{}) if isinstance(schema,dict) else {}
        require(isinstance(value,dict),'M7_PGSTREAM_EXTERNAL_SOURCE_REQUIRED')
        properties=value.get('properties',{});required=value.get('required',[])
        # The selected native source adds complete-cohort bounds, a deployment
        # stream incarnation and bounded recovery. This replaces the historical
        # four-property schema assertion; frozen baseline helpers retain it.
        native_properties={'receiver','slot','streamRole','bounds','transactionRows','generation','recovery'}
        require(value.get('type')=='object' and isinstance(required,list) and len(required)==4 and set(required)=={'receiver','slot','streamRole','bounds'} and value.get('additionalProperties') is False and isinstance(properties,dict) and set(properties) in (native_properties,native_properties|{'startupTransport'}),'M7_PGSTREAM_EXTERNAL_SOURCE_REQUIRED')
        # Descriptions are annotations. Unknown validation keywords still refuse.
        def contract(spec):
            return {key:entry for key,entry in spec.items() if key!='description'} if isinstance(spec,dict) else None
        require(contract(properties['transactionRows'])=={'type':'integer','minimum':1,'maximum':1000000} and contract(properties['generation'])=={'type':'string','pattern':'^[a-f0-9]{32}$'},'M7_PGSTREAM_NATIVE_SOURCE_REQUIRED')
        recovery=contract(properties['recovery'])
        require(isinstance(recovery,dict) and set(recovery)=={'type','required','additionalProperties','properties'} and recovery.get('type')=='object' and isinstance(recovery.get('required'),list) and len(recovery['required'])==3 and set(recovery['required'])=={'connectionEnv','timeoutMs','maxQueued'} and recovery.get('additionalProperties') is False and recovery.get('properties')=={'connectionEnv':{'type':'string','pattern':'^[A-Z][A-Z0-9_]{0,127}$'},'timeoutMs':{'type':'integer','minimum':1,'maximum':30000},'maxQueued':{'type':'integer','minimum':1,'maximum':1024}},'M7_PGSTREAM_NATIVE_RECOVERY_REQUIRED')
        # Startup rendezvous is optional in historical native source. When the
        # source publishes it, preserve both finite clock-safe bounds and its
        # closed object contract; accepting an extra name alone is insufficient.
        if 'startupTransport' in properties:
            startup=contract(properties['startupTransport'])
            timeout={'type':'integer','minimum':1,'maximum':9223372036854}
            require(isinstance(startup,dict) and set(startup)=={'type','required','additionalProperties','properties'} and startup.get('type')=='object' and isinstance(startup.get('required'),list) and len(startup['required'])==2 and set(startup['required'])=={'timeoutMs','retryIntervalMs'} and startup.get('additionalProperties') is False and startup.get('properties')=={'timeoutMs':timeout,'retryIntervalMs':timeout},'M7_PGSTREAM_STARTUP_TRANSPORT_REQUIRED')
        require(value.get('dependentRequired')=={'generation':['transactionRows'],'recovery':['transactionRows']},'M7_PGSTREAM_NATIVE_DEPENDENCIES_REQUIRED')


def external_runtime(rows,manifest):
    if selection(manifest)!=EXTERNAL:return
    selected=[r for r in rows if r.get('Config',{}).get('Labels',{}).get('com.docker.compose.service')=='pgstream']
    require(len(selected)==1,'M7_PGSTREAM_RUNTIME_ROSTER')
    row=selected[0];state=row.get('State',{})
    require(row.get('Image')==manifest['imageId'] and row.get('Config',{}).get('Cmd')==EXTERNAL_COMMAND,'M7_PGSTREAM_RUNTIME_IMAGE_COMMAND')
    require(state.get('Running') is True and type(state.get('Pid')) is int and state['Pid']>0 and isinstance(state.get('StartedAt'),str) and bool(state['StartedAt']),'M7_PGSTREAM_RUNTIME_BIRTH')
