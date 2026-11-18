#!/usr/bin/env python3
"""Offline join to an immutable binding export; no Kubernetes command calls."""
import json
from pathlib import Path
import shutil
import sys
import time
from datetime import datetime, timezone

import kube_adapter as k
import application_topology


def check(export, output, environment=None):
    export=Path(export).resolve()
    receipt=k.document(export/'package-receipt.json')
    k.need(k.digest(export/'package.tar')==receipt['archiveSha256'],'BINDING_ARCHIVE_CHANGED')
    inventory_file=export/'fixture-inventory.json'
    render_file=export/'manifests.json'
    environment_receipt=None
    if environment is not None:
        environment=Path(environment).resolve()
        environment_receipt=k.document(environment/'export.json')
        k.need(environment_receipt['bindingCommit']==receipt['bindingCommit'] and environment_receipt['archiveSha256']==receipt['archiveSha256'],'ENVIRONMENT_BINDING_CHANGED')
        for file in ('rendered.json','inventory.json'):
            k.need(k.digest(environment/file)==environment_receipt['artifacts'][file],'ENVIRONMENT_EXPORT_CHANGED')
        inventory_file=environment/'inventory.json'
        render_file=environment/'rendered.json'
    inv=k.document(inventory_file)
    label=inv['ownership']['label']
    k.need(len(label)==1,'OWNER_LABEL')
    key,run=next(iter(label.items()))
    source=receipt['appSourceContract']
    now=time.time()
    iso=lambda value:datetime.fromtimestamp(value,timezone.utc).isoformat().replace('+00:00','Z')
    c={'version':1,'runId':run,'context':'synthetic-offline-context','namespace':inv['namespace'],'ownerLabel':key,
       'kubectl':'/absolute/operator/compatible/bin/kubectl','readonlyGuard':'/absolute/private/ops/bin/ro',
       'pins':{'pair':{'core':source['coreCommit'],'deploy':source['deployCommit']},'bindingCommit':receipt['bindingCommit'],
               'appImage':inv['images']['app'],'appImageId':source['localImageId'],
               'renderSha256':k.digest(render_file),'inventorySha256':k.digest(inventory_file),'instrument':k.instrument()['sha256']},
       'deadlines':{'workUntil':iso(now+1800),'cleanupUntil':iso(now+3600)},'storageMode':inv['storage']['mode'],
       'roles':{},'baseUrl':'http://127.0.0.1:18080','tenants':2,'tenantsFile':'/absolute/private/tenants.json',
       'workload':{'loadSeconds':30,'offeredRps':1,'logicalPollingClients':4,'probeEveryMs':300000},
       'driver':{'hostId':'synthetic-driver-reference','sharedHost':True,'resources':{'millicpus':1000,'memoryBytes':1073741824}},
       'observer':{'hostId':'synthetic-observer-reference','sharedHost':True,'resources':{'millicpus':200,'memoryBytes':268435456}}}
    if 'candidateContract' in inv:
        c['pins'].update(candidate=inv['candidateContract'], postgresImage=inv['images']['postgres'],
                         postgresImageId='sha256:'+'0'*64)  # deliberately held until E supplies the commissioned mapping
    if application_topology.FIELD in inv:
        c[application_topology.FIELD] = application_topology.selection(inv, k.need)
    for name,item in inv['workloads'].items():
        if item['kind']=='Job':continue
        for container in item['containers']:
            if not container['init']:
                c['roles'][container['name']]={'workload':item['kind']+'/'+name,'container':container['name']}
    node=Path(shutil.which('node')).resolve()
    c['driver'].update(node=str(node),nodeSha256=k.digest(node),dependencies='/absolute/operator-owned/qualified-dependencies')
    out=Path(output).resolve()
    k.need(not out.exists(),'NEW_ABSOLUTE_OUTPUT_REQUIRED')
    out.mkdir(mode=0o700,parents=True)
    config=out/'operator-inputs.held.json'
    k.write(config,c)
    packet=k.prepare(config,inventory_file,render_file,out/'packet')
    result={'version':1,'offlineBoundary':'PASS','bindingCommit':receipt['bindingCommit'],'archiveSha256':receipt['archiveSha256'],
            'renderSha256':c['pins']['renderSha256'],'inventorySha256':c['pins']['inventorySha256'],'instrument':packet['instrument']['sha256'],
            'runtimeStatus':'HELD','missingOperatorInputs':['E admitted context/node/storage/access profile','pullable app and PostgreSQL images with source mapping','private primer/role exports','source-matched owned dependency tree/native tools and finite scope','actual actor resource readback'],
            'liveCorrectness':'UNMEASURED','capacityAcceptance':'NOT_GRANTED','syntheticContext':True,
            'environmentExportSha256':k.digest(environment/'export.json') if environment else None,
            'storageMode':inv['storage']['mode']}
    k.write(out/'offline-join.json',result)
    return result


if __name__=='__main__':
    try:print(json.dumps(check(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None),sort_keys=True))
    except Exception as error:
        print(str(error) if str(error).startswith('K8S_') else 'K8S_EXPORT_JOIN_FAILED',file=sys.stderr)
        sys.exit(1)
