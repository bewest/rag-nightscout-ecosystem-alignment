#!/usr/bin/env python3
"""Make prospective scale/runtime inputs from selected receipts and resource data."""
import argparse
import copy
import json
from pathlib import Path
import kube_adapter as k
import toolchain
import workload_runtime
from workloads import profile

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('application','local-config','envelope','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--population',action='append',type=int)
    p.add_argument('--duration',type=int,default=1800);p.add_argument('--setup',type=int,default=900);p.add_argument('--drain',type=int,default=300)
    p.add_argument('--work',type=int,default=7200);p.add_argument('--cleanup',type=int,default=900)
    p.add_argument('--scale',type=float,default=1);p.add_argument('--full-viewers',action='store_true')
    p.add_argument('--driver-shards',type=int,default=1);p.add_argument('--preallocated-vus',type=int,default=2);p.add_argument('--max-vus',type=int,default=16)
    p.add_argument('--api-replicas',type=int,default=1);p.add_argument('--workers',type=int,default=1)
    a=p.parse_args();out=a.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    source=k.document(a.application);app=source.get('application',source)
    app={n:app[n] for n in ('sourceReceipt','buildReceipt','bindingCommit','postgresImageId','bootstrapHelper') if n in app}
    local=k.document(a.local_config);envelope=k.document(a.envelope)
    local=dict(k6Image=local['k6Image'],prepare={n:v for n,v in local['prepare'].items() if n not in toolchain.FRESH|toolchain.DERIVED})
    for n in a.population or (500,1000,3000,10000):
        base=k.document(k.HERE/'workloads/realistic-500.json');base.pop('referencePins')
        base['name']='configured-'+str(n)
        base['population'].update(provisionedTenants=n,ordinaryRosterTenants=n)
        base['phases'].update(workSeconds=a.work,cleanupSeconds=a.cleanup)
        base['proposedEnvelope']=copy.deepcopy(envelope)
        base['workload'].update(loadSeconds=a.duration,setupSeconds=a.setup,drainSeconds=a.drain,workloadScale=a.scale,
            logicalPollingClients=n if a.full_viewers else n//10,driverShards=a.driver_shards,
            driverPlan=dict(version=1,observer='scheduling-v1',maxAggregateVUs=7*a.max_vus*a.driver_shards,
                scenarios={name:dict(preAllocatedVUs=a.preallocated_vus,maxVUs=a.max_vus,gracefulStopSeconds=30) for name in workload_runtime.SHAPES}))
        m=dict(version=1,kind='multitenant-experiment',application=app,profile=base,local=local,
               topology=dict(apiReplicas=a.api_replicas,evaluatorWorkers=a.workers,pgstreamTopology='external'))
        legacy=toolchain.legacy(m,'compose');selected=toolchain.frozen.source(legacy)
        profile.validate(dict(base,referencePins=dict(core=selected['coreCommit'],deploy=selected['deployCommit'],bindingCommit=app['bindingCommit'])))
        k.write(out/('experiment-'+str(n)+'.json'),m)
    print(json.dumps(dict(output=str(out),execution='NOT_RUN',capacityAcceptance='NOT_GRANTED')))

if __name__=='__main__':main()
