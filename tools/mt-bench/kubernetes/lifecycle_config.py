#!/usr/bin/env python3
"""Bind local lifecycle custody without creating any cluster object."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from producer_startup import cohort_ready_seconds
sys.path.append(str(Path(__file__).resolve().parent.parent/'m7-joined'))
import workload_inputs
import phase_fit

FIELDS = {'version','caseDirectory','instrumentDirectory','instrumentSha256','bindingDirectory',
          'toolsDirectory','snapshotDirectory','cacheAbsence','runTemplate','delivery','coreRepository',
          'k6','readonlyGuard','observerScript','nativeLimits','primerConcurrency','edgePort','pullSecretCommand','inputs',
          'startupWindowPreflight','resourcePhasePreflight'}
STAGES = ('namespace','cluster-trust','foundation','stores','provision','private-admin','primer','serving')

def need(ok, code):
    if not ok: raise ValueError('K8S_LIFECYCLE_' + code)

def read(p): return json.loads(Path(p).read_bytes())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p): return {'path':str(Path(p).resolve()), 'sha256':sha(p)}

def reference(value):
    need(isinstance(value,dict) and set(value)=={'path','sha256'}, 'REFERENCE')
    p=Path(value['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink(), 'REFERENCE_FILE')
    need(sha(p)==value['sha256'], 'INPUT_CHANGED')
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
        native[kind+'/'+name]={'activeDeadlineSeconds':spec.get('activeDeadlineSeconds'),
            'containers':{actor['name']:{probe:{key:actor[probe][key] for key in probe_fields if key in actor[probe]}
                                         for probe in ('startupProbe','readinessProbe') if probe in actor}
                          for actor in pod.get('initContainers',[])+pod['containers']}}
    return {'selectedSeconds':selected,'authoredFields':sorted(set(authored)|({'cohortReadySeconds'} if 'cohortReadySeconds' in phases else set())),
            'workDeadlineSeconds':environment['workDeadlineSeconds'],'native':native}

def fixture_config(path, capture=False):
    c=read(path)
    need(c.get('version')==1 and set(c)<=FIELDS, 'CONFIGURATION')
    for key in ('caseDirectory','instrumentDirectory','bindingDirectory','toolsDirectory','snapshotDirectory','coreRepository'):
        need(Path(c[key]).is_absolute() and Path(c[key]).is_dir(), 'DIRECTORY')
    for key in ('k6','readonlyGuard','observerScript'):
        need(Path(c[key]).is_absolute() and Path(c[key]).is_file(), 'TOOL')
    need(type(c['primerConcurrency']) is int and 1<=c['primerConcurrency']<=32, 'PRIMER_CONCURRENCY')
    limits=c['nativeLimits'];need(set(limits)=={'millicpus','memoryBytes'} and all(type(x)is int and x>0 for x in limits.values()), 'FINITE_NATIVE_LIMITS')
    need(type(c.get('edgePort',8080))is int and 1<=c.get('edgePort',8080)<=65535,'EDGE_PORT')
    if c.get('pullSecretCommand') is not None:
        need(isinstance(c['pullSecretCommand'],list) and c['pullSecretCommand'] and
             all(isinstance(x,str) and x and '\x00' not in x for x in c['pullSecretCommand']), 'PULL_COMMAND')
    files=[reference(c[key]) for key in ('runTemplate','delivery','cacheAbsence')]
    d=Path(c['caseDirectory']);e=read(d/'environment.json');m=read(d/'intent.json');pre=read(d/'preflight.json')
    need(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}',e['runId']) and e['runId']==d.name and e['namespace'].startswith('ns-synth-'), 'INSTANCE_IDENTITY')
    need(e['tenantCount']==m['profile']['population']['provisionedTenants'], 'POPULATION')
    need(pre.get('commissioning')=='PREFLIGHT_ONLY' and pre['experiment']['renderSha256']==sha(d/'render.json'), 'PREFLIGHT')
    need(all(limits[k]<=m['profile']['proposedEnvelope']['nativeLimits'][k] for k in limits), 'ALLOCATION_EXCEEDED')
    template=read(c['runTemplate']['path'])
    mode=template.get('resourceAccounting','limits-v1')
    need(mode in ('limits-v1','requests-v1') and mode==e.get('resourceAccounting','limits-v1') and
         mode==pre.get('trialEnvelope',{}).get('resourceAccounting','limits-v1') and
         mode==read(d/'inventory.json').get('resourceAccounting','limits-v1'),'RESOURCE_ACCOUNTING_MISMATCH')
    need(all(sum(template[a]['resources'][k] for a in ('driver','observer'))<=limits[k] for k in limits),'ALLOCATION_EXCEEDED')
    need(template['driver']['hostId']==template['observer']['hostId'], 'NATIVE_HOST')
    need(e['workDeadlineSeconds']>0 and e['cleanupDeadlineSeconds']>e['workDeadlineSeconds'] and e['provisionDeadlineSeconds']>0,'DEADLINES')
    core=subprocess.check_output(['git','-C',c['coreRepository'],'rev-parse','HEAD'],text=True).strip()
    need(core==e['sourceCommit'],'SOURCE_CHANGED')
    instrument=Path(c['instrumentDirectory'])/'tools/mt-bench/kubernetes/adapter.py'
    identity=json.loads(subprocess.check_output([sys.executable,'-B',instrument,'identity']))
    need(identity['sha256']==c['instrumentSha256'],'INSTRUMENT_CHANGED')
    package=Path(c['bindingDirectory']);binding=read(package/'binding.json')
    authored_startup=m['profile'].get('phases',{}).get('startupWindows',{}).get('kubernetes',{})
    if 'pgstreamNotifierAckTimeoutMs' in m or 'primerStorage' in m or 'jobCompleteSeconds' in authored_startup:
        files.append(package/'binding.json')
    for name,expected in binding['files'].items():
        p=package/'bindings/kubernetes'/name
        need(p.is_relative_to(package) and sha(p)==expected,'BINDING_CHANGED');files.append(p)
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
    startup=startup_preflight(m,e,rendered)
    phase=phase_fit.staged_projection(e,list(phase_fit.objects(read(d/'render.json'))),stage_objects,need)
    phase_preflight=None
    if phase is not None:
        need(pre.get('trialEnvelope',{}).get(phase_fit.FIELD)==phase,'RESOURCE_PHASE_PREFLIGHT_CHANGED')
        publisher=package/'bindings/kubernetes/scripts/secrets.sh'
        phase_preflight={'plan':phase,'publisherSha256':sha(publisher),
                         'lifecycleSha256':sha(Path(__file__).with_name('lifecycle.py')),
                         'moduleSha256':sha(Path(phase_fit.__file__))}
        files += [publisher,Path(phase_fit.__file__),Path(phase_fit.resource_budget.__file__)]
    files += [Path(c[key]) for key in ('k6','readonlyGuard','observerScript')]
    files += [Path(c['toolsDirectory'])/'kubectl']
    files += [Path(__file__).with_name(n) for n in ('lifecycle_config.py','lifecycle.py','attach.py')]
    expected={str(p.resolve()):sha(p) for p in files}
    if capture:
        c['inputs']=expected
        c['startupWindowPreflight']=startup
        if phase_preflight is not None:c['resourcePhasePreflight']=phase_preflight
    else:
        need(c.get('inputs')==expected,'INPUT_CHANGED')
        need(c.get('startupWindowPreflight')==startup or
             'startupWindowPreflight' not in c and not startup['authoredFields'],'STARTUP_PREFLIGHT_CHANGED')
        need(c.get('resourcePhasePreflight')==phase_preflight,'RESOURCE_PHASE_PREFLIGHT_CHANGED')
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
