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
        require(value.get('type')=='object' and isinstance(required,list) and len(required)==4 and set(required)=={'receiver','slot','streamRole','bounds'} and value.get('additionalProperties') is False and isinstance(properties,dict) and set(properties)=={'receiver','slot','streamRole','bounds','transactionRows','generation','recovery'},'M7_PGSTREAM_EXTERNAL_SOURCE_REQUIRED')
        # Descriptions are annotations. Unknown validation keywords still refuse.
        def contract(spec):
            return {key:entry for key,entry in spec.items() if key!='description'} if isinstance(spec,dict) else None
        require(contract(properties['transactionRows'])=={'type':'integer','minimum':1,'maximum':1000000} and contract(properties['generation'])=={'type':'string','pattern':'^[a-f0-9]{32}$'},'M7_PGSTREAM_NATIVE_SOURCE_REQUIRED')
        recovery=contract(properties['recovery'])
        require(isinstance(recovery,dict) and set(recovery)=={'type','required','additionalProperties','properties'} and recovery.get('type')=='object' and isinstance(recovery.get('required'),list) and len(recovery['required'])==3 and set(recovery['required'])=={'connectionEnv','timeoutMs','maxQueued'} and recovery.get('additionalProperties') is False and recovery.get('properties')=={'connectionEnv':{'type':'string','pattern':'^[A-Z][A-Z0-9_]{0,127}$'},'timeoutMs':{'type':'integer','minimum':1,'maximum':30000},'maxQueued':{'type':'integer','minimum':1,'maximum':1024}},'M7_PGSTREAM_NATIVE_RECOVERY_REQUIRED')
        require(value.get('dependentRequired')=={'generation':['transactionRows'],'recovery':['transactionRows']},'M7_PGSTREAM_NATIVE_DEPENDENCIES_REQUIRED')


def external_runtime(rows,manifest):
    if selection(manifest)!=EXTERNAL:return
    selected=[r for r in rows if r.get('Config',{}).get('Labels',{}).get('com.docker.compose.service')=='pgstream']
    require(len(selected)==1,'M7_PGSTREAM_RUNTIME_ROSTER')
    row=selected[0];state=row.get('State',{})
    require(row.get('Image')==manifest['imageId'] and row.get('Config',{}).get('Cmd')==EXTERNAL_COMMAND,'M7_PGSTREAM_RUNTIME_IMAGE_COMMAND')
    require(state.get('Running') is True and type(state.get('Pid')) is int and state['Pid']>0 and isinstance(state.get('StartedAt'),str) and bool(state['StartedAt']),'M7_PGSTREAM_RUNTIME_BIRTH')
