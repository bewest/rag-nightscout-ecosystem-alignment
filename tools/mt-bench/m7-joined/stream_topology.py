"""Explicit source-bound pgstream process topology; no runtime substitution."""
from contract import require

COLOCATED = 'colocated-v1'
EXTERNAL = 'external-service-v1'
EXTERNAL_COMMAND = ['/usr/local/bin/pgstream','run','-c','/run/ns-stream/pgstream.yaml','--log-level','info']


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
    if selection(manifest)==EXTERNAL:return {'evaluator':('node',),'pgstream':('pgstream',)}
    return {'evaluator':('node','pgstream')}


def readable_processes(snapshots,manifest):
    for role,names in expected_processes(manifest).items():
        values=snapshots.get(role,{}).get('hostProcesses',{}).values()
        require(all(any(p.get('component',p.get('name'))==name and not p.get('unavailable') for p in values) for name in names),'M7_SAMPLE_PROCESS_INSTRUMENT')


def verify_source(manifest,schema):
    if selection(manifest)==EXTERNAL:
        value=schema.get('properties',{}).get('pgstream',{})
        require(set(value.get('required',[]))=={'receiver','slot','streamRole','bounds'} and value.get('additionalProperties') is False and set(value.get('properties',{}))=={'receiver','slot','streamRole','bounds'},'M7_PGSTREAM_EXTERNAL_SOURCE_REQUIRED')


def external_runtime(rows,manifest):
    if selection(manifest)!=EXTERNAL:return
    selected=[r for r in rows if r.get('Config',{}).get('Labels',{}).get('com.docker.compose.service')=='pgstream']
    require(len(selected)==1,'M7_PGSTREAM_RUNTIME_ROSTER')
    row=selected[0];state=row.get('State',{})
    require(row.get('Image')==manifest['imageId'] and row.get('Config',{}).get('Cmd')==EXTERNAL_COMMAND,'M7_PGSTREAM_RUNTIME_IMAGE_COMMAND')
    require(state.get('Running') is True and type(state.get('Pid')) is int and state['Pid']>0 and isinstance(state.get('StartedAt'),str) and bool(state['StartedAt']),'M7_PGSTREAM_RUNTIME_BIRTH')
