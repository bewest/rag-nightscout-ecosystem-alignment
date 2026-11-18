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
from workloads import profile
from contract import discovery_api_replicas, discovery_workers

FRESH={'core-repo','deploy-repo','generator-dependencies','generator-dependency-receipt',
       'generator-dependency-receipt-sha256','fixture-project','backend-subnet','edge-subnet','port','receipt','freeze'}
DERIVED={'core-commit','deploy-commit','image','image-id','postgres-image','tenants','replicas',
         'load-seconds','hot-factor','accel','offered-rps','workload-mix','workload-scale',
         'logical-polling-clients','probe-every-ms','probe-ledger','setup-seconds','drain-seconds','jwt-setup-concurrency','driver-plan','driver-vu-diagnostic','driver-shards',
         'static-workers','static-build-receipt','static-build-receipt-sha256','pgstream-topology'}

def legacy(m,target='kubernetes'):
    if m.get('kind')=='k8s-frozen-experiment':return copy.deepcopy(m)
    frozen.require(m.get('kind')=='multitenant-experiment' and m.get('version')==1 and
        set(m)<= {'version','kind','application','profile','topology','deploymentJobs','local','kubernetes','tier',
                  frozen.ACK_BUDGET,frozen.PRIMER_STORAGE},'MANIFEST')
    transport=m.get('kubernetes',{})
    frozen.require(isinstance(transport,dict) and set(transport)<={'edge'},'KUBERNETES_FIELDS')
    edge=edge_configuration.selection(transport.get('edge'),frozen.require)
    app=m['application']
    frozen.require(set(app)<= {'sourceReceipt','buildReceipt','bindingCommit','postgresImageId','bootstrapHelper'},'APPLICATION_FIELDS')
    topology=m['topology']
    frozen.require(set(topology)=={'apiReplicas','evaluatorWorkers','pgstreamTopology'} and
        discovery_api_replicas(topology['apiReplicas']) and
        discovery_workers(topology['evaluatorWorkers']) and
        topology['pgstreamTopology'] in ('colocated','external'),'TOPOLOGY')
    if target=='kubernetes':
        frozen.require(topology=={'apiReplicas':1,'evaluatorWorkers':1,'pgstreamTopology':'external'},'KUBERNETES_TOPOLOGY_UNSUPPORTED')
    return dict(version=1,kind='k8s-frozen-experiment',**copy.deepcopy(app),profile=copy.deepcopy(m['profile']),
                **({'tier': m['tier']} if 'tier' in m else {}),
                **({'edge':edge} if target=='kubernetes' and edge is not None else {}),
                **({frozen.ACK_BUDGET: m[frozen.ACK_BUDGET]} if frozen.ACK_BUDGET in m else {}),
                **({frozen.PRIMER_STORAGE: m[frozen.PRIMER_STORAGE]} if frozen.PRIMER_STORAGE in m else {}),
                **({'deploymentJobs':copy.deepcopy(m['deploymentJobs'])} if 'deploymentJobs'in m else {}))

def local(m,instance):
    original=legacy(m,'compose');selected=frozen.source(original)
    frozen.require('bootstrapHelper' not in original,'LOCAL_BOOTSTRAP_HELPER_UNSUPPORTED')
    defaults=m['local'];options=copy.deepcopy(defaults['prepare'])
    frozen.require(not (set(options)&(DERIVED|FRESH)),'DUPLICATE_LOCAL_FACT')
    fresh=instance['prepare'];frozen.require(set(fresh)<=FRESH,'INSTANCE_FIELDS')
    options.update(fresh)
    if frozen.ACK_BUDGET in selected:
        frozen.require(m['topology']['pgstreamTopology']=='external', 'PGSTREAM_ACK_TOPOLOGY')
        frozen.require('pgstream-notifier-ack-timeout-ms' not in options, 'DUPLICATE_LOCAL_FACT')
        options['pgstream-notifier-ack-timeout-ms'] = selected[frozen.ACK_BUDGET]
    p=profile.validate(dict(original['profile'],referencePins=dict(core=selected['coreCommit'],deploy=selected['deployCommit'],bindingCommit=original['bindingCommit'])))
    w=p['workload'];t=m['topology']
    options.update({'core-commit':selected['coreCommit'],'deploy-commit':selected['deployCommit'],
        'image':selected['localImageId'],'image-id':selected['localImageId'],'postgres-image':original['postgresImageId'],
        'tenants':p['population']['provisionedTenants'],'replicas':t['apiReplicas'],
        'load-seconds':w['loadSeconds'],'hot-factor':w.get('hotFactor',1),'accel':1,'logical-polling-clients':w['logicalPollingClients'],
        'probe-every-ms':w['probeEveryMs'],
        'pgstream-topology':{'external':'external-service-v1','colocated':'colocated-v1'}[t['pgstreamTopology']]})
    options.update({('workload-mix' if key=='workloadMix' else 'workload-scale' if key=='workloadScale' else 'offered-rps'):w[key]
                    for key in ('workloadMix','workloadScale','offeredRps') if key in w})
    for field, option in (('setupSeconds', 'setup-seconds'), ('drainSeconds', 'drain-seconds'), ('jwtSetupConcurrency', 'jwt-setup-concurrency')):
        if field in w:
            options[option] = w[field]
    if 'probeLedger' in w:
        options['probe-ledger'] = json.dumps(w['probeLedger'])
    if 'driverPlan'in w:
        options.update({'driver-plan':json.dumps(w['driverPlan']),'driver-shards':w.get('driverShards',1)})
    if t['evaluatorWorkers']>1 or t['apiReplicas']>1:
        options.update({'static-workers':t['evaluatorWorkers'],'static-build-receipt':original['buildReceipt']['path'],
                        'static-build-receipt-sha256':original['buildReceipt']['sha256']})
    # Import the existing local adapter under its expected name in an isolated
    # subprocess. Both historical modules are called adapter.py; never let the
    # Python module cache silently select the other transport.
    config=dict(version=1,helperInstrument=None,k6Image=defaults['k6Image'],
                workSeconds=p['phases']['workSeconds'],cleanupSeconds=p['phases']['cleanupSeconds'],prepare=options,
                **({'tier': original['tier']} if 'tier' in original else {}))
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
        if 'edge'in result:k.write(out/'binding-inputs.json',{'edge':result['edge']})
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
