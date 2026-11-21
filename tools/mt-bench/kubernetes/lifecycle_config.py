#!/usr/bin/env python3
"""Bind local lifecycle custody without creating any cluster object."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from producer_startup import cohort_ready_seconds
sys.path.insert(1, str(Path(__file__).resolve().parent.parent/'m7-joined'))
import workload_inputs
import primer_options
import population_ceiling
import application_topology

FIELDS = {'version','caseDirectory','instrumentDirectory','alignmentCommit','candidate','bindingDirectory',
          'toolsDirectory','snapshotDirectory','cacheAbsence','runTemplate','coreRepository',
          'k6','readonlyGuard','observerScript','nativeLimits','primerConcurrency','edgePort','pullSecretCommand','inputs',
          'startupWindowPreflight','primerOptionsPreflight',
          'populationCeilingPreflight','schedulerPlacement','capturedSourceCommit','fixture'}
STAGES = ('namespace','cluster-trust','foundation','stores','provision','private-admin','primer','serving')

def need(ok, code):
    if not ok: raise ValueError('K8S_LIFECYCLE_' + code)

def read(p): return json.loads(Path(p).read_bytes())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p): return {'path':str(Path(p).resolve()), 'sha256':sha(p)}

def reference(value):
    # A recorded path; no file hashing (decision `brittle-check-removal`).
    need(isinstance(value,dict) and 'path' in value and set(value)<={'path','sha256'}, 'REFERENCE')
    p=Path(value['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink(), 'REFERENCE_FILE')
    return p


def startup_preflight(intent, environment, objects):
    phases=intent['profile'].get('phases',{})
    authored=workload_inputs.startup_selection(phases,need).get('kubernetes',{})
    defaults={**workload_inputs.KUBERNETES_STARTUP_DEFAULTS}
    defaults['primerReadySeconds']=min(defaults['primerReadySeconds'],environment['provisionDeadlineSeconds'])
    selected=workload_inputs.startup_windows(authored,defaults,need)
    selected['cohortReadySeconds']=cohort_ready_seconds(phases,environment['workDeadlineSeconds'])
    selected['provisionReadySeconds']=environment['provisionDeadlineSeconds']
    probe_fields=('initialDelaySeconds','periodSeconds','failureThreshold','timeoutSeconds','successThreshold')
    native={}
    for obj in objects:
        kind=obj['kind'];name=obj['metadata']['name']
        if kind not in ('Job','Deployment','StatefulSet'):
            continue
        spec=obj['spec'];pod=spec['template']['spec']
        if 'primerLocation' not in intent and kind=='Job' and name=='primer' and 'primerReadySeconds' in authored:
            values=[env.get('value') for actor in pod.get('initContainers',[]) if actor['name']=='primer'
                    for env in actor.get('env',[]) if env['name']=='NS_PRIMER_STALL_SECONDS']
            need(values==[str(selected['primerReadySeconds'])], 'PRIMER_STALL_WINDOW_CHANGED')
        native[kind+'/'+name]={'activeDeadlineSeconds':spec.get('activeDeadlineSeconds'),
            'containers':{actor['name']:{probe:{key:actor[probe][key] for key in probe_fields if key in actor[probe]}
                                         for probe in ('startupProbe','readinessProbe') if probe in actor}
                          for actor in pod.get('initContainers',[])+pod['containers']}}
    return {**({application_topology.FIELD:application_topology.selection(intent,need)}
               if application_topology.FIELD in intent else {}),
            'selectedSeconds':selected,'authoredFields':sorted(set(authored)|({'cohortReadySeconds'} if 'cohortReadySeconds' in phases else set())),
            'workDeadlineSeconds':environment['workDeadlineSeconds'],'native':native}

def helper_directory(config):
    root = Path(config['instrumentDirectory'])
    need(root.is_absolute(), 'INSTRUMENT_DIRECTORY')
    return root.resolve() / 'tools/mt-bench/kubernetes'


def fixture_config(path, capture=False):
    c=read(path)
    need(c.get('version')==1 and set(c)<=FIELDS, 'CONFIGURATION')
    for key in ('caseDirectory','instrumentDirectory','bindingDirectory','toolsDirectory','coreRepository'):
        need(Path(c[key]).is_absolute() and Path(c[key]).is_dir(), 'DIRECTORY')
    for key in ('k6','readonlyGuard'):
        need(Path(c[key]).is_absolute() and Path(c[key]).is_file(), 'TOOL')
    need(helper_directory(c) == Path(__file__).resolve().parent, 'INSTRUMENT_DIRECTORY_MISMATCH')
    if capture:
        from kube_adapter import instrument
        c['alignmentCommit'] = instrument()['commit']  # recorded run identity, never compared
    limits=c['nativeLimits'];need(set(limits)=={'millicpus','memoryBytes'} and all(type(x)is int and x>0 for x in limits.values()), 'FINITE_NATIVE_LIMITS')
    need(type(c.get('edgePort',8080))is int and 1<=c.get('edgePort',8080)<=65535,'EDGE_PORT')
    if c.get('pullSecretCommand') is not None:
        need(isinstance(c['pullSecretCommand'],list) and c['pullSecretCommand'] and
             all(isinstance(x,str) and x and '\x00' not in x for x in c['pullSecretCommand']), 'PULL_COMMAND')
    scheduler = c.get('schedulerPlacement', False)
    need(type(scheduler) is bool, 'SCHEDULER_PLACEMENT')
    if 'fixture' in c:
        reuse = c['fixture']
        need(isinstance(reuse,dict) and reuse.get('mode') in ('seed','restore') and Path(reuse.get('directory','')).is_absolute()
             and (Path(c['caseDirectory'])/'stages/fixture-claims.json').is_file(), 'FIXTURE')
    files=[reference(c['runTemplate'])]
    if not scheduler:
        files.append(reference(c['cacheAbsence']))
    d=Path(c['caseDirectory']);e=read(d/'environment.json');m=read(d/'intent.json');pre=read(d/'preflight.json')
    if c.get('fixture', {}).get('mode') == 'restore':
        import fixture_copy
        import populated_history as history
        history.check_snapshot(m['profile']['history'], fixture_copy.read_manifest(c['fixture']['directory']))
    primer = primer_options.from_profile(m['profile'],need)
    population=population_ceiling.from_profile(m['profile'],need)
    need(e.get(population_ceiling.FIELD)==population,'POPULATION_CEILING_CHANGED')
    if primer is None:
        legacy = primer_options.selection({'concurrency':c.get('primerConcurrency')},need)
        primer_options.require_source(legacy, None, need)
    else:
        concurrency = primer.get('concurrency',primer_options.DEFAULT_CONCURRENCY)
        need(type(c.get('primerConcurrency',concurrency)) is int and c.get('primerConcurrency',concurrency)==concurrency,
             'PRIMER_OPTIONS_CHANGED')
    need(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}',e['runId']) and e['runId']==d.name and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}',e['namespace']), 'INSTANCE_IDENTITY')
    need(e['tenantCount']==m['profile']['population']['provisionedTenants'], 'POPULATION')
    need(pre.get('commissioning')=='PREFLIGHT_ONLY', 'PREFLIGHT')
    need(scheduler == (pre.get('trialEnvelope', {}).get('placementMode') == 'scheduler'),
         'SCHEDULER_PREFLIGHT_CHANGED')
    template=read(c['runTemplate']['path'])
    inventory=read(d/'inventory.json')
    need(m.get('nativeLoad') == template.get('nativeLoad') == inventory.get('nativeLoad'),
         'NATIVE_LOAD_SELECTION_CHANGED')
    application_topology.bind(m,template,inventory,need)
    mode=template.get('resourceAccounting','limits-v1')
    need(mode in ('limits-v1','requests-v1') and mode==e.get('resourceAccounting','limits-v1') and
         mode==pre.get('trialEnvelope',{}).get('resourceAccounting','limits-v1') and
         mode==read(d/'inventory.json').get('resourceAccounting','limits-v1'),'RESOURCE_ACCOUNTING_MISMATCH')
    need(all(sum(template[a]['resources'][k] for a in ('driver','observer'))<=limits[k] for k in limits),'ALLOCATION_EXCEEDED')
    need(template['driver']['hostId']==template['observer']['hostId'], 'NATIVE_HOST')
    need(e['workDeadlineSeconds']>0 and e['cleanupDeadlineSeconds']>e['workDeadlineSeconds'] and e['provisionDeadlineSeconds']>0,'DEADLINES')
    # Run identity is the alignment commit, the candidate image digests and this
    # configuration. The binding directory is used as selected; nothing is hashed.
    package=Path(c['bindingDirectory'])
    files += [d/(name+'.json') for name in ('environment','intent','inventory','render','preflight')]
    rendered=[]; stage_objects={}
    for stage in STAGES:
        p=d/'stages'/(stage+'.json');files.append(p)
        stage_objects[stage]=read(p)['items']
        for obj in stage_objects[stage]:
            rendered.append(obj)
            kind=obj['kind'];meta=obj['metadata']
            need(kind in ('Namespace','ClusterRoleBinding','ConfigMap','Service','Secret','ServiceAccount','Role','RoleBinding','NetworkPolicy','ResourceQuota','LimitRange','Deployment','StatefulSet','Job'),'RESOURCE_UNSUPPORTED')
            need(kind in ('Namespace','ClusterRoleBinding') or meta['namespace']==e['namespace'],'STAGE_NAMESPACE')
            need(kind!='Service' or obj['spec'].get('type','ClusterIP')=='ClusterIP','NEW_BILLABLE_RESOURCE')
            if scheduler and kind in ('Deployment','StatefulSet','Job'):
                need(not obj['spec']['template']['spec'].get('nodeName'), 'SCHEDULER_BYPASSED')
    startup=startup_preflight(m,e,rendered)
    primer_preflight=None
    if primer is not None and 'seed' in inventory:
        primer_preflight = {'selection': primer}
    elif primer is not None:
        contract_path=package/'bindings/kubernetes/assets/source-contract.json'
        data=contract_path.read_bytes()
        contract=json.loads(data)
        rendered_proof=[obj['data']['source-contract.json'].encode() for obj in stage_objects['foundation']
                        if obj['kind']=='ConfigMap' and obj['metadata']['name']=='provision-scripts']
        need(rendered_proof==[data] and contract.get(primer_options.FIELD)==primer,'PRIMER_OPTIONS_BINDING_CHANGED')
        protocol=contract.get(primer_options.PROTOCOL_FIELD)
        primer_options.require_source(primer,protocol,need)
        primer_preflight={'selection':primer,'sourceProtocol':protocol}
    population_preflight=None
    if population is not None:
        contract_path=package/'bindings/kubernetes/assets/source-contract.json'
        data=contract_path.read_bytes();contract=json.loads(data)
        rendered_proof=[obj['data']['source-contract.json'].encode() for obj in stage_objects['foundation']
                        if obj['kind']=='ConfigMap' and obj['metadata']['name']=='provision-scripts']
        need(rendered_proof==[data] and contract.get(population_ceiling.FIELD)==population and
             contract.get(population_ceiling.PROTOCOL_FIELD)==population_ceiling.PROTOCOL,
             'POPULATION_BINDING_CHANGED')
        population_preflight={'selection':population,'sourceProtocol':population_ceiling.PROTOCOL}
    files += [Path(c[key]) for key in ('k6','readonlyGuard')]
    files += [Path(c['toolsDirectory'])/'kubectl']
    files += [Path(__file__).with_name(n) for n in ('lifecycle_config.py','lifecycle.py','attach.py')]
    if capture:
        from experiment import workload
        workload(m)
        c['inputs']=sorted(str(p.resolve()) for p in files)  # recorded paths; capture marker
        c['capturedSourceCommit']=subprocess.check_output(['git','-C',c['coreRepository'],'rev-parse','HEAD'],text=True).strip()
        c['startupWindowPreflight']=startup
        if primer_preflight is not None:c['primerOptionsPreflight']=primer_preflight
        if population_preflight is not None:c['populationCeilingPreflight']=population_preflight
    else:
        need(c.get('startupWindowPreflight')==startup or
             'startupWindowPreflight' not in c and not startup['authoredFields'],'STARTUP_PREFLIGHT_CHANGED')
        need(c.get('primerOptionsPreflight')==primer_preflight,'PRIMER_OPTIONS_PREFLIGHT_CHANGED')
        need(c.get('populationCeilingPreflight')==population_preflight,'POPULATION_PREFLIGHT_CHANGED')
    return c

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='capture':
        value=fixture_config(sys.argv[2],capture=True)
        with Path(sys.argv[3]).open('x') as stream:
            __import__('os').chmod(sys.argv[3],0o600);json.dump(value,stream,indent=2);stream.write('\n')
        print('K8S_LIFECYCLE_CONFIGURATION_CAPTURED')
    elif len(sys.argv)==3 and sys.argv[1]=='check':
        fixture_config(sys.argv[2]);print('K8S_LIFECYCLE_CONFIGURATION_VERIFIED')
    else:raise SystemExit('capture INPUT NEW_CONFIG | check CONFIG')
