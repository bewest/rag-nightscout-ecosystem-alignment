#!/usr/bin/env python3
"""Project one stable experiment into existing Compose or Kubernetes contracts."""
import argparse
import copy
import json
from pathlib import Path
import sys

import kube_adapter as k
import frozen
import edge_configuration
import primer_options
import population_ceiling
import application_topology
from workloads import profile
from contract import discovery_api_replicas, discovery_workers

FRESH={'core-repo','deploy-repo','generator-dependencies','generator-dependency-receipt',
       'generator-dependency-receipt-sha256','fixture-project','backend-subnet','edge-subnet','port','receipt','freeze'}
DERIVED={'core-commit','deploy-commit','image','image-id','postgres-image','tenants','replicas',
         'load-seconds','hot-factor','accel','offered-rps','workload-mix','workload-scale',
         'logical-polling-clients','viewer-setup','probe-every-ms','probe-ledger','evaluator-progress-budget','drain-observation','startup-windows','setup-seconds','drain-seconds','jwt-setup-concurrency','driver-plan','driver-headroom','driver-shards',
         'static-workers','input-transport'}

def legacy(m,target='kubernetes'):
    if m.get('kind')=='k8s-frozen-experiment':
        application_topology.selection(m,frozen.require)
        return copy.deepcopy(m)
    frozen.require(m.get('kind')=='multitenant-experiment' and m.get('version')==1 and
        set(m)<= {'version','kind','application','profile','topology','deploymentJobs','local','kubernetes','tier',
                  frozen.PRIMER_STORAGE},'MANIFEST')
    transport=m.get('kubernetes',{})
    frozen.require(isinstance(transport,dict) and set(transport)<={'edge',application_topology.FIELD},'KUBERNETES_FIELDS')
    application_topology.selection(transport,frozen.require)
    edge=edge_configuration.selection(transport.get('edge'),frozen.require)
    app=m['application']
    frozen.require(set(app)<= {'candidate','alignmentCommit','bindingCommit','bootstrapHelper'},'APPLICATION_FIELDS')
    topology=m['topology']
    frozen.require(topology.get('inputTransport') == 'writer-driven'
                   and set(topology) == {'apiReplicas', 'evaluatorWorkers', 'inputTransport'} and
                   discovery_api_replicas(topology['apiReplicas']) and discovery_workers(topology['evaluatorWorkers']), 'TOPOLOGY')
    # This legacy manifest reached Kubernetes only through the external pgstream service.
    frozen.require(target != 'kubernetes', 'KUBERNETES_TOPOLOGY_UNSUPPORTED')
    return dict(version=1,kind='k8s-frozen-experiment',**copy.deepcopy(app),profile=copy.deepcopy(m['profile']),
                **({'tier': m['tier']} if 'tier' in m else {}),
                **({'edge':edge} if target=='kubernetes' and edge is not None else {}),
                **({application_topology.FIELD:transport[application_topology.FIELD]}
                   if target=='kubernetes' and application_topology.FIELD in transport else {}),
                **({frozen.PRIMER_STORAGE: m[frozen.PRIMER_STORAGE]} if frozen.PRIMER_STORAGE in m else {}),
                **({'deploymentJobs':copy.deepcopy(m['deploymentJobs'])} if 'deploymentJobs'in m else {}))

def local(m,instance):
    original=legacy(m,'compose');selected=frozen.source(original)
    frozen.require('bootstrapHelper' not in original,'LOCAL_BOOTSTRAP_HELPER_UNSUPPORTED')
    defaults=m['local'];options=copy.deepcopy(defaults['prepare'])
    frozen.require(not (set(options)&(DERIVED|FRESH)),'DUPLICATE_LOCAL_FACT')
    fresh=instance['prepare'];frozen.require(set(fresh)<=FRESH,'INSTANCE_FIELDS')
    options.update(fresh)
    p=profile.validate(dict(original['profile'],referencePins=dict(core=selected['coreCommit'],deploy=selected['deployCommit'],bindingCommit=original['bindingCommit'])))
    frozen.require(p['population']['ordinaryRosterTenants'] == p['population']['provisionedTenants'],
                   'COMPOSE_ORDINARY_ROSTER_SUBSET_UNSUPPORTED')
    w=p['workload'];t=m['topology']
    primer=primer_options.from_profile(p,frozen.require)
    population=population_ceiling.from_profile(p,frozen.require)
    if population is not None:
        frozen.require('population-ceiling' not in options,'DUPLICATE_LOCAL_FACT')
        options['population-ceiling']=population
    if primer is not None:
        frozen.require(not {'primer-concurrency','primer-max-tenants'} & options.keys(), 'DUPLICATE_LOCAL_FACT')
        names={'concurrency':'primer-concurrency','maxTenants':'primer-max-tenants'}
        options.update({names[key]:value for key,value in primer.items()})
    options.update({'core-commit':selected['coreCommit'],'deploy-commit':selected['deployCommit'],
        'image':selected['localImageId'],'image-id':selected['localImageId'],'postgres-image':original['candidate']['postgresImageId'],
        'tenants':p['population']['provisionedTenants'],'replicas':t['apiReplicas'],
        'load-seconds':w['loadSeconds'],'hot-factor':w.get('hotFactor',1),'accel':1,'logical-polling-clients':w['logicalPollingClients'],
        'probe-every-ms':w['probeEveryMs']})
    options['input-transport'] = 'writer-driven'
    options.update({('workload-mix' if key=='workloadMix' else 'workload-scale' if key=='workloadScale' else 'offered-rps'):w[key]
                    for key in ('workloadMix','workloadScale','offeredRps') if key in w})
    for field, option in (('setupSeconds', 'setup-seconds'), ('drainSeconds', 'drain-seconds'), ('jwtSetupConcurrency', 'jwt-setup-concurrency')):
        if field in w:
            options[option] = w[field]
    if 'viewerSetup' in w:
        options['viewer-setup'] = json.dumps(w['viewerSetup'])
    if 'probeLedger' in w:
        options['probe-ledger'] = json.dumps(w['probeLedger'])
    if 'evaluatorProgressBudget' in w:
        options['evaluator-progress-budget'] = json.dumps(w['evaluatorProgressBudget'])
    if 'drainObservation' in w:
        options['drain-observation'] = json.dumps(w['drainObservation'])
    startup=profile.workload_runtime.workload_inputs.startup_selection(p['phases'],frozen.require)
    if 'compose' in startup:
        options['startup-windows'] = json.dumps(startup['compose'])
    if 'driverPlan'in w:
        options.update({'driver-plan':json.dumps(w['driverPlan']),'driver-shards':w.get('driverShards',1)})
    if 'driverHeadroom' in w:
        options['driver-headroom'] = w['driverHeadroom']
    options['static-workers']=t['evaluatorWorkers']
    # Import the existing local adapter under its expected name in an isolated
    # subprocess. Both historical modules are called adapter.py; never let the
    # Python module cache silently select the other transport.
    config=dict(version=1,helperInstrument=None,k6Image=defaults['k6Image'],
                workSeconds=p['phases']['workSeconds'],cleanupSeconds=p['phases']['cleanupSeconds'],prepare=options,
                **({'tier': original['tier']} if 'tier' in original else {}))
    if p['history'] != profile.history.BASELINE:
        config['history'] = p['history']
    return config

def project(m,instance,target,out):
    out=Path(out);frozen.require(out.is_absolute() and not out.exists(),'NEW_OUTPUT_REQUIRED');out.mkdir(mode=0o700,parents=True)
    if 'deploymentJobs' in m:
        import jobs
        jobs.selection(legacy(m,target))
    if target=='kubernetes':
        result=legacy(m);profile.validate(dict(result['profile'],referencePins=dict(
            core=frozen.source(result)['coreCommit'],deploy=frozen.source(result)['deployCommit'],bindingCommit=result['bindingCommit'])))
        k.write(out/'manifest.json',result)
        inputs={**({'edge':result['edge']} if 'edge' in result else {})}
        if application_topology.FIELD in result:inputs[application_topology.FIELD]=result[application_topology.FIELD]
        population=population_ceiling.from_profile(result['profile'],frozen.require)
        if population is not None:inputs[population_ceiling.FIELD]=population
        if inputs:k.write(out/'binding-inputs.json',inputs)
    else:
        result=local(m,instance)
        import subprocess
        code="""import adapter,json,sys;from run_configuration import resolve
c=json.load(open(sys.argv[1]));c['helperInstrument']=adapter.instrument()['sha256'];v=resolve(c,json.loads(sys.argv[3]));
json.dump(c,open(sys.argv[2]+'/config.json','w'),indent=2);json.dump(v,open(sys.argv[2]+'/projection.json','w'),indent=2)
"""
        k.write(out/'unbound.json',result)
        selected=frozen.source(legacy(m,'compose'))
        subprocess.run([sys.executable,'-B','-c',code,str(out/'unbound.json'),str(out),json.dumps({'status':selected['sourceAcceptance']})],cwd=k.M7,check=True)
    k.write(out/'intent.json',m)
    return dict(target=target,output=str(out),execution='NOT_RUN',capacityAcceptance='NOT_GRANTED',
                **({'notApplicable':['kubernetes.edge']} if target=='compose' and m.get('kubernetes',{}).get('edge') is not None else {}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('target',choices=('compose','kubernetes'));p.add_argument('manifest',type=Path);p.add_argument('instance',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(project(k.document(a.manifest),k.document(a.instance),a.target,a.output.resolve()),indent=2))
