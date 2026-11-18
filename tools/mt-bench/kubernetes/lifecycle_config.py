#!/usr/bin/env python3
"""Bind local lifecycle custody without creating any cluster object."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

FIELDS = {'version','caseDirectory','instrumentDirectory','instrumentSha256','bindingDirectory',
          'toolsDirectory','snapshotDirectory','cacheAbsence','runTemplate','delivery','coreRepository',
          'k6','readonlyGuard','observerScript','nativeLimits','primerConcurrency','edgePort','pullSecretCommand','inputs'}
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
    if 'pgstreamNotifierAckTimeoutMs' in m:
        files.append(package/'binding.json')
    for name,expected in binding['files'].items():
        p=package/'bindings/kubernetes'/name
        need(p.is_relative_to(package) and sha(p)==expected,'BINDING_CHANGED');files.append(p)
    files += [d/(name+'.json') for name in ('environment','intent','inventory','render','preflight')]
    for stage in STAGES:
        p=d/'stages'/(stage+'.json');files.append(p)
        for obj in read(p)['items']:
            kind=obj['kind'];meta=obj['metadata']
            need(kind in ('Namespace','ClusterRoleBinding','ConfigMap','Service','Secret','ServiceAccount','Role','RoleBinding','NetworkPolicy','ResourceQuota','LimitRange','Deployment','StatefulSet','Job'),'RESOURCE_UNSUPPORTED')
            need(kind in ('Namespace','ClusterRoleBinding') or meta['namespace']==e['namespace'],'STAGE_NAMESPACE')
            need(kind!='Service' or obj['spec'].get('type','ClusterIP')=='ClusterIP','NEW_BILLABLE_RESOURCE')
    files += [Path(c[key]) for key in ('k6','readonlyGuard','observerScript')]
    files += [Path(c['toolsDirectory'])/'kubectl']
    files += [Path(__file__).with_name(n) for n in ('lifecycle_config.py','lifecycle.py','attach.py')]
    expected={str(p.resolve()):sha(p) for p in files}
    if capture:
        c['inputs']=expected
    else:
        need(c.get('inputs')==expected,'INPUT_CHANGED')
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
