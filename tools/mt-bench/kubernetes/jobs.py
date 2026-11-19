#!/usr/bin/env python3
"""Consume the registered deployment-job contract; rendering never executes a job."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import io

import frozen

OPERATIONS={'bootstrap':'infrastructure','provision':'provisioner','prime':'primer',
            'platform-verify':'verifier','verification-plan':'offline'}

def need(ok,code):
    if not ok:raise ValueError('K8S_JOB_'+code)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with Path(p).open('x') as s:
        __import__('os').chmod(p,0o600);json.dump(v,s,indent=2);s.write('\n')

def selection(manifest):
    s=manifest['deploymentJobs']
    need(set(s)=={'receipt','requestVersion','topology'} and s['requestVersion']==1,'CAPABILITY_UNSUPPORTED')
    need(s['topology']=='source-default','TOPOLOGY_UNSUPPORTED')
    r=frozen.read_ref(s['receipt']);app=frozen.source(manifest)
    need(r['coreCommit']==app['coreCommit'] and r['applicationDeploy']==app['deployCommit'],
         'APPLICATION_COMPATIBILITY')
    need(re.fullmatch(r'sha256:[a-f0-9]{64}',r['localImageId']) and
         re.fullmatch(r'[a-f0-9]{40}',r['toolCommit']),'IMAGE_IDENTITY')
    return r

def plan(m,repo,command,config,out,*,target='compose',namespace='synthetic-jobs',image=None,seconds=60,resources=None):
    r=selection(m)
    need(command in OPERATIONS and type(seconds)is int and 1<=seconds<=1800,'REQUEST_UNSUPPORTED')
    # The bootstrap CLI embeds its donor's source-generation contract. API jobs
    # declare the independently observed target image and may use another build
    # of the same compatible source/runtime tuple.
    need(command!='bootstrap' or r['applicationImageId']==frozen.source(m)['localImageId'],
         'BOOTSTRAP_IMAGE_COMPATIBILITY')
    out=Path(out);need(out.is_absolute() and not out.exists(),'NEW_OUTPUT_REQUIRED');out.mkdir(mode=0o700,parents=True)
    # Render the selected committed contract, never a working-tree approximation.
    raw=subprocess.check_output(['git','-C',repo,'archive',r['toolCommit'],'bindings/jobs/render.js','bindings/jobs/operations.js'])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:archive.extractall(out/'contract',filter='data')
    selected_image=r['localImageId'] if image is None else image
    need(target=='compose' and selected_image==r['localImageId'] or target=='kubernetes' and
         re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}',selected_image),'TRANSPORT_IMAGE')
    renderer=out/'contract/bindings/jobs/render.js'
    render=json.loads(subprocess.check_output(['node',renderer,target,command,selected_image,namespace]))
    scope=OPERATIONS[command];prefix='ns-job-'+scope
    for name in (prefix+'-request',prefix+'-config'):(out/name).mkdir(mode=0o700)
    request=dict(version=1,command=command,applicationImageId=frozen.source(m)['localImageId'],deadlineSeconds=seconds)
    write(out/(prefix+'-request/request.json'),request)
    if command!='bootstrap':
        cfg=json.loads(Path(config).read_bytes())
        if command in ('verification-plan','platform-verify'):
            cfg={k:cfg[k] for k in ('adminOrigin','platformVerification')}
        write(out/(prefix+'-config/config.json'),cfg)
    if resources is not None:
        need(set(resources)=={'millicpus','memoryBytes'} and all(type(v)is int and v>0 for v in resources.values()),'FINITE_RESOURCES')
        if target=='compose':
            render['services'][scope].update(cpus=resources['millicpus']/1000,mem_limit=resources['memoryBytes'],memswap_limit=resources['memoryBytes'])
        else:
            render['items'][1]['spec']['template']['spec']['containers'][0]['resources']={
                'requests':{'cpu':str(resources['millicpus'])+'m','memory':str(resources['memoryBytes'])},
                'limits':{'cpu':str(resources['millicpus'])+'m','memory':str(resources['memoryBytes'])}}
    write(out/'render.json',render)
    value=dict(version=1,command=command,target=target,tools=r,application=frozen.source(m),
               toolReceipt=m['deploymentJobs']['receipt'],
               requestSha256=sha(out/(prefix+'-request/request.json')),renderSha256=sha(out/'render.json'),
               configSha256=None if command=='bootstrap' else sha(out/(prefix+'-config/config.json')),
               rendererSha256=sha(renderer),resources=resources,execution='NOT_RUN',
               authority='Fresh instance/UID/allocation and observed image mapping required for networked jobs',
               capacityAcceptance='NOT_GRANTED')
    write(out/'plan.json',value)
    return value

def offline(out,*,millicpus=1000,memory_bytes=402653184):
    """Only the no-network verification-plan command is executable by this helper."""
    out=Path(out);p=json.loads((out/'plan.json').read_bytes());r=p['tools']
    need(p['command']=='verification-plan' and p['target']=='compose','OFFLINE_SCOPE')
    need(type(millicpus)is int and millicpus>0 and type(memory_bytes)is int and memory_bytes>0,'FINITE_RESOURCES')
    need(r==frozen.read_ref(p['toolReceipt']),'TOOL_RECEIPT_CHANGED')
    need(sha(out/'ns-job-offline-config/config.json')==p['configSha256'],'PLAN_CHANGED')
    expected={key:r[key] for key in ('toolCommit','applicationImageId','coreCommit','applicationDeploy','lockSha256','producerSha256')}
    base=['docker','run','--rm','--pull=never','--network','none','--read-only','--user','1000:1000',
          '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
          '--cpus',str(millicpus/1000),'--memory',str(memory_bytes),'--memory-swap',str(memory_bytes)]
    caps=json.loads(subprocess.check_output([*base,r['localImageId'],'capabilities'],timeout=35))
    need(caps['result']=='ok' and caps['operations']==OPERATIONS and caps['source']==expected,'ACTUAL_TOOL_IMAGE_CHANGED')
    need(sha(out/'render.json')==p['renderSha256'] and
         sha(out/'ns-job-offline-request/request.json')==p['requestSha256'],'PLAN_CHANGED')
    args=[*base,'-e','JOB_SCOPE=offline']
    for part in ('request','config'):
        args += ['--mount','type=bind,source='+str(out/('ns-job-offline-'+part))+',target=/job/'+part+',readonly']
    result=json.loads(subprocess.check_output([*args,r['localImageId'],'verification-plan'],timeout=35))
    cfg=json.loads((out/'ns-job-offline-config/config.json').read_bytes())
    need(result['result']=='ok' and result['source']==expected and
         result['namespace']==cfg['platformVerification']['namespace'] and
         result['roles']==cfg['platformVerification']['roles'],'OFFLINE_RESULT_CHANGED')
    write(out/'offline-result.json',dict(result=result,capabilities=caps,
          observedToolsImageId=r['localImageId'],resources=dict(millicpus=millicpus,memoryBytes=memory_bytes),
          compatibility='source-pinned job contract; networked operations UNMEASURED',capacityAcceptance='NOT_GRANTED'))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('plan')
    for n in ('manifest','repository','command','config','output'):q.add_argument(n)
    q.add_argument('--target',choices=('compose','kubernetes'),default='compose');q.add_argument('--namespace',default='synthetic-jobs');q.add_argument('--image');q.add_argument('--seconds',type=int,default=60)
    q=s.add_parser('offline');q.add_argument('output');q.add_argument('--millicpus',type=int,default=1000);q.add_argument('--memory-bytes',type=int,default=402653184)
    a=p.parse_args()
    if a.action=='plan':v=plan(json.loads(Path(a.manifest).read_bytes()),a.repository,a.command,a.config,Path(a.output).resolve(),target=a.target,namespace=a.namespace,image=a.image,seconds=a.seconds)
    else:v=offline(Path(a.output).resolve(),millicpus=a.millicpus,memory_bytes=a.memory_bytes)
    print(json.dumps(v,indent=2))
