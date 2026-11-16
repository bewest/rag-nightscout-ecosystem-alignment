"""Typed local Vault component cell on the existing batch/window/cleanup path.

Only the pinned six-purpose client and synthetic root envelope execute. This is
not an application receipt or a remote allocator. RSS is not a V8/VM limit.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import shutil
import subprocess
import sys
import time
import urllib.request

import experiment_batch as batch
from dependency_reuse import file_sha

PRODUCER = 'vault-component-v1'
CORE = '3b2cec6405451d0aff103f5d21f4312606d4295b'
IMAGE = 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2'
IMAGE_ID = 'sha256:8794a735d581b92ae3d138e677fc79b5722749ce53674334507f2141e35da8c8'
SOURCE_FILES = {
 'lib/tenant-registry/vault-keys.js':'6d06602b4060b85a2e6f52ca45f12c622a699bd0481583120d3f1d79ccce5df1',
 'lib/tenant-registry/rules.js':'b918e5b60cc5911949bc746d4b15646f9ef9c34fa6dad1e8d51a1d4c5cbf5b20',
 'lib/secrets/vault-transit.js':'30db01cf4f94ae9bff12ac357e9886b4dd12115787a9a99fd9490f80a780bcf2',
 'lib/secrets/component.js':'2bdfc24721e85b56fe56fe20d527ec35084464c46656758f6e832b6bb68e8858'}
MIB=1024**2
PARENT_VM=512*MIB
NATIVE_VM=16*1024**3
NODE_VM=128*1024**3
HOST_CPU=1000
WORKER=Path(__file__).with_name('vault-component-worker.cjs')
ENV={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8'}
NODE_CHECK='console.log(JSON.stringify({version:process.version,heapLimit:require("node:v8").getHeapStatistics().heap_size_limit,affinity:require("node:fs").readFileSync("/proc/self/status","utf8").split("\\n").find(x=>x.startsWith("Cpus_allowed_list:"))}))'


def need(ok,code):batch.need(ok,'VAULT_'+code)


def selected(config):return isinstance(config,dict) and config.get('producer')==PRODUCER


def claim(config):
    validate_config(config)
    # One shared (not reserved) allowed logical CPU bounds all inherited host
    # processes; Docker's effective Vault quota rounds125m to130m.
    return {'millicpus':HOST_CPU+130,'memoryBytes':config['vaultMemoryMiB']*MIB,
            'heapMiB':128,'hourlyMicrousd':0,'totalMicrousd':0,'liveResources':7}


def validate_config(config):
    need(type(config)is dict and set(config)=={'version','producer','capsule','helperInstrument','workSeconds','cleanupSeconds','targetSets','vaultMemoryMiB'},'CONFIG_FIELDS')
    need(type(config['version'])is int and config['version']==1 and config['producer']==PRODUCER,'CONFIG_VERSION')
    for key,low,high in [('workSeconds',30,3600),('cleanupSeconds',30,180),('targetSets',1,10000)]:
        need(type(config[key])is int and low<=config[key]<=high,'FINITE_BOUND')
    need(type(config['vaultMemoryMiB'])is int and config['vaultMemoryMiB']in(256,512,1024),'MEMORY_PROFILE')
    need(type(config['helperInstrument'])is str and len(config['helperInstrument'])==64,'HELPER_PIN')
    need(type(config['capsule'])is str and Path(config['capsule']).is_absolute(),'CAPSULE_PATH')


def capsule(config,payload,root,allowlist):
    validate_config(config);root=Path(root).resolve();file=Path(config['capsule'])
    need(file.is_relative_to(root) and str(file.relative_to(root))in allowlist,'CAPSULE_ALLOWLIST')
    need(file.stat().st_size<=65536,'CAPSULE_SIZE')
    value=batch.read(file)
    need(set(value)=={'version','producer','source','image','imageId','helper','files','workerSha256','tools'},'CAPSULE_FIELDS')
    need(value['version']==1 and value['producer']==PRODUCER,'CAPSULE_VERSION')
    need(value['source']==payload['source'] and value['source']['core']==CORE,'SOURCE_PIN')
    need(value['image']==IMAGE and value['imageId']==payload['image']==IMAGE_ID,'IMAGE_PIN')
    need(value['helper']==config['helperInstrument']==payload['helper'],'HELPER_CHANGED')
    need(value['files']==SOURCE_FILES,'SOURCE_FILES')
    for name,sha in SOURCE_FILES.items():
        rel='source/'+name;need(rel in allowlist and file_sha(root/rel)==sha,'SOURCE_BYTES')
    need(value['workerSha256']==file_sha(WORKER),'WORKER_CHANGED')
    need(set(value['tools'])=={'node','docker'},'TOOL_FIELDS')
    for name,tool in value['tools'].items():
        need(type(tool)is dict and set(tool)=={'path','sha256','version'},'TOOL_FIELDS')
        path=Path(tool['path']);need(path.is_absolute() and path.name==name and path.resolve()==path and path.is_file(),'TOOL_PATH')
        need(file_sha(path)==tool['sha256'],'TOOL_BYTES')
    need(value['tools']['node']['version']=='v24.22.1','NODE_VERSION')
    return value


def plan(cell,spec,payload_root,allowlist):
    config=cell['config'];validate_config(config)
    need(cell['target']=={'kind':'local'} and cell['subnets']==[] and len(cell['ports'])==1,'LOCAL_ISOLATION')
    need(cell['resources']==claim(config),'RESERVATION_CHANGED')
    need(cell['offeredRps']==0 and config['workSeconds']==cell['workSeconds'] and config['cleanupSeconds']==cell['cleanupSeconds'],'WORKLOAD_CHANGED')
    axes=spec['envelope']['workload']
    for key,value in {'tenants':config['targetSets'],'offeredRps':0,'durationSeconds':config['workSeconds'],'probeEveryMs':0,'hotFactor':1}.items():
        need(axes[key][0]<=value<=axes[key][1],'WORKLOAD_OUTSIDE_ENVELOPE')
    need(axes['faultCases']==[],'FAULT_UNSUPPORTED')
    capsule(config,spec['payload'],payload_root,allowlist)
    return {'vault':{'requestedMillicpus':125,'effectiveMillicpus':130,'memoryBytes':config['vaultMemoryMiB']*MIB,'maximumContainers':1,'maximumVolumes':1},
            'host':{'sharedLogicalCpuMaximum':1,'millicpus':HOST_CPU,'heapMiB':128,'parentVirtualBytes':PARENT_VM,'nativeChildVirtualBytes':NATIVE_VM,'nodeVirtualBytes':NODE_VM,
                    'logicalManagedActors':{'cell':1,'guard':1,'node':1,'nativeCommandSlots':2,'container':1,'volume':1},
                    'processCount':'NOT_AN_OS_PID_OR_THREAD_LIMIT; in-container descendants share Vault cgroup', 'rss':'SEPARATELY_OBSERVED_NOT_HEAP_OR_VM_BOUNDED'},
            'scope':'SYNTHETIC_VAULT_COMPONENT_NOT_APPLICATION_OR_CAPACITY'}


def pin_host(parent_pid):
    need(type(parent_pid)is int and parent_pid!=os.getpid() and os.getppid()==parent_pid,'AFFINITY_NOT_CELL')
    try:
        allowed=os.sched_getaffinity(0);need(bool(allowed),'AFFINITY_UNSUPPORTED')
        selected={min(allowed)};os.sched_setaffinity(0,selected)
        need(os.sched_getaffinity(0)==selected,'AFFINITY_CHANGED')
    except (AttributeError,OSError):raise RuntimeError('M7_BATCH_VAULT_AFFINITY_UNSUPPORTED')from None
    return {'beforeAllowed':sorted(allowed),'selected':sorted(selected),'exclusiveReservation':False}


def verify_completion(config,record,returncode):
    need(returncode==0 and isinstance(record,dict) and record.get('status')=='COMPLETE' and
         type(record.get('completed'))is int and record['completed']==record.get('target')==config['targetSets'],'WORKER_PARTIAL')


def verify_node_receipt(observed,tools,affinity):
    need(observed.get('version')==tools['node']['version'] and observed.get('heapLimit')==128*MIB,'NODE_HEAP_RECEIPT')
    need(observed.get('affinity','').split(':')[-1].strip()==str(affinity['selected'][0]),'AFFINITY_INHERITANCE')


def limits(value):
    def apply():resource.setrlimit(resource.RLIMIT_AS,(value,value))
    return apply


def command(tools,*args,timeout=10):
    # All argv are constructed here; never shell/caller-supplied programs.
    import adapter
    return subprocess.check_output([tools['docker']['path'],'--host=unix:///var/run/docker.sock',*args],env=ENV,text=True,timeout=adapter.remaining_seconds(timeout),stderr=subprocess.DEVNULL,preexec_fn=limits(NATIVE_VM))


def inspect(tools,cid):
    x=json.loads(command(tools,'inspect',cid))[0]
    return {'id':x['Id'],'name':x['Name'],'created':x['Created'],'image':x['Image'],
            'state':{k:x['State'].get(k)for k in ['Status','Running','OOMKilled','ExitCode','Pid','StartedAt','FinishedAt']},
            'limits':{k:x['HostConfig'].get(k)for k in ['Memory','MemorySwap','NanoCpus']},
            'owner':x['Config'].get('Labels',{}).get('org.nightscout.vault-component')}


def checked(row,inventory):
    need(row['id']==inventory['container']['id'] and row['created']==inventory['container']['created'] and row['name']==inventory['container']['name'],'INCARNATION_CHANGED')
    need(row['owner']==inventory['owner'] and row['image']==IMAGE_ID,'OWNERSHIP_CHANGED')
    need(row['limits']=={'Memory':inventory['memoryBytes'],'MemorySwap':inventory['memoryBytes'],'NanoCpus':125000000},'QUOTA_CHANGED')


def server_identity(tools,cid):
    matches=[]
    for line in command(tools,'top',cid,'-eo','pid,ppid,comm,args').splitlines()[1:]:
        fields=line.split(None,3)
        if len(fields)!=4 or fields[2]!='vault':continue
        base=Path('/proc',fields[0]);argv=base.joinpath('cmdline').read_bytes().split(b'\0')
        if b'server'not in argv or b'-config=/vault/config/probe.hcl'not in argv:continue
        raw=base.joinpath('stat').read_text().split(')',1)[1].split();status=base.joinpath('status').read_text()
        cgroup=base.joinpath('cgroup').read_text();need(cid in cgroup,'SERVER_CGROUP')
        matches.append({'hostPID':int(fields[0]),'startTicks':raw[19],'namespacePID':int(next(x for x in status.splitlines()if x.startswith('NSpid:')).split()[-1]),'cgroup':cgroup,'command':['vault','server','-config=/vault/config/probe.hcl']})
    need(len(matches)==1,'SERVER_IDENTITY');return matches[0]


def sample(tools,cid,server):
    script='for f in memory.current memory.peak memory.max memory.events memory.stat cpu.stat cpu.max; do echo FILE:$f; cat /sys/fs/cgroup/$f 2>/dev/null; done; echo FILE:process; sed -n "/^VmRSS:/p;/^VmHWM:/p" /proc/'+str(server['namespacePID'])+'/status; echo FILE:storage; du -sk /vault/file'
    raw=command(tools,'exec',cid,'sh','-c',script);fields={};key=None
    for line in raw.splitlines():
        if line.startswith('FILE:'):key=line[5:];fields[key]=[]
        elif key:fields[key].append(line)
    return {'at':time.time(),'monoNs':time.monotonic_ns(),'cgroupAndProcess':fields}


def cleanup_resources(root):
    """Called under the EXISTING runner cleanup lock after stop_stage."""
    import runner
    file=root/'vault-inventory.json'
    if not file.exists():return  # no effect can precede this owned inventory
    inventory=batch.read(file);tools=inventory['tools']
    need(file_sha(tools['docker']['path'])==tools['docker']['sha256'],'TOOL_BYTES')
    state=batch.read(root/'execution.json');need(inventory['owner']==state['owner'],'OWNERSHIP_CHANGED')
    if inventory.get('container'):
        cid=inventory['container']['id']
        if command(tools,'ps','-aq','--no-trunc','--filter','id='+cid).split():
            row=inspect(tools,cid);checked(row,inventory);batch.write(root/'container-after.json',row)
            try:batch.write(root/'server-after.json',server_identity(tools,cid))
            except Exception:batch.write(root/'server-after.json',{'status':'UNMEASURED_SERVER_IDENTITY'})
            command(tools,'rm','-f',cid,timeout=15)
    if inventory.get('volume'):
        bound=inventory['volume'];name=bound['name']
        if name in command(tools,'volume','ls','-q','--filter','name=^'+name+'$').split():
            v=json.loads(command(tools,'volume','inspect',name))[0]
            need(v['Name']==name and v.get('CreatedAt')==bound['created'] and v.get('Labels',{}).get('org.nightscout.vault-component')==state['owner'],'VOLUME_CHANGED')
            command(tools,'volume','rm',name,timeout=15)
    containers=command(tools,'ps','-aq','--no-trunc','--filter','label=org.nightscout.vault-component='+state['owner']).split()
    volumes=command(tools,'volume','ls','-q','--filter','label=org.nightscout.vault-component='+state['owner']).split()
    need(not containers and not volumes,'RESOURCES_REMAIN')
    job=root/'stage-job.json'
    if job.exists():
        j=batch.read(job);need(batch.birth(j['pid'])!=j['startTicks'],'WORKER_REMAINS')
        need(not batch.group_members(j['pid']),'WORKER_GROUP_REMAINS')
    batch.write(root/'vault-absence.json',{'status':'ABSENT','owner':state['owner'],'containers':containers,'volumes':volumes,'at':time.time()})


def execute(config,root):
    import runner
    import diagnostic_resources as resources
    config=batch.read(config);cell,spec,payload_root=batch.reserved_cell(config)
    allowlist=batch.verify_payload(spec,payload_root);plan(cell,spec,payload_root,allowlist);frozen=capsule(config,spec['payload'],payload_root,allowlist)
    need(config['helperInstrument']==runner.a.instrument()['sha256'],'HELPER_CHANGED')
    need(not any(os.environ.get(k)for k in ['NODE_OPTIONS','NODE_PATH','LD_PRELOAD']),'PRELOAD')
    ledger=batch.read(Path(os.environ['M7_BATCH_RESERVATION']).parent/'reservations.json')
    affinity=pin_host(ledger['pid'])
    resource.setrlimit(resource.RLIMIT_AS,(PARENT_VM,NODE_VM))
    lease=resources.Runtime();lease.acquire()
    root=Path(root).resolve();need(not root.exists(),'OUTPUT_EXISTS');root.mkdir(mode=0o700,parents=True)
    runner.write(root/'config.json',config);state=runner.arm_window(root,config)
    inventory={'owner':state['owner'],'memoryBytes':config['vaultMemoryMiB']*MIB,'tools':frozen['tools'],'container':None,'volume':None}
    failure=None;worker=None;last=None;tools=frozen['tools'];start=time.time()
    try:
        with runner.a.command_deadline(state['stopWorkAt']):
            batch.write(root/'host-affinity.json',affinity)
            need(sorted(os.sched_getaffinity(batch.read(root/'guard-job.json')['pid']))==affinity['selected'],'AFFINITY_INHERITANCE')
            childmask=json.loads(subprocess.check_output([sys.executable,'-B','-c','import os,json;print(json.dumps(sorted(os.sched_getaffinity(0))))'],env=ENV,text=True,timeout=runner.a.remaining_seconds(5),preexec_fn=limits(NATIVE_VM)))
            need(childmask==affinity['selected'],'AFFINITY_INHERITANCE')
            observed=json.loads(subprocess.check_output([tools['node']['path'],'--max-heap-size=128','-e',NODE_CHECK],env=ENV,text=True,timeout=runner.a.remaining_seconds(10),preexec_fn=limits(NODE_VM)))
            verify_node_receipt(observed,tools,affinity)
            need(subprocess.check_output([tools['docker']['path'],'--version'],env=ENV,text=True,timeout=runner.a.remaining_seconds(10),preexec_fn=limits(NATIVE_VM)).strip()==tools['docker']['version'],'TOOL_VERSION')
            batch.write(root/'tool-preflight.json',observed)
            image=json.loads(command(tools,'image','inspect',IMAGE))[0];need(image['Id']==IMAGE_ID,'IMAGE_CHANGED')
            source=root/'source'
            for name,sha in SOURCE_FILES.items():
                file=source/name;file.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(payload_root)/'source'/name,file);need(file_sha(file)==sha,'SOURCE_BYTES')
            batch.write(root/'source-capsule.json',frozen)
            name=cell['namespace'];volume=name+'-data'
            with runner.custody(root):
                runner.execution_window(root,config);batch.write(root/'vault-inventory.json',inventory)
                need(not command(tools,'ps','-aq','--filter','name=^/'+name+'$').strip(),'NAME_CONFLICT')
                need(not command(tools,'volume','ls','-q','--filter','name=^'+volume+'$').strip(),'VOLUME_CONFLICT')
                command(tools,'volume','create','--label','org.nightscout.vault-component='+state['owner'],volume)
                v=json.loads(command(tools,'volume','inspect',volume))[0];inventory['volume']={'name':volume,'created':v.get('CreatedAt')};batch.write(root/'vault-inventory.json',inventory)
                (root/'vault.hcl').write_text('disable_mlock = true\nui = false\napi_addr = "http://127.0.0.1:8200"\nstorage "file" { path = "/vault/file" }\nlistener "tcp" { address = "0.0.0.0:8200" tls_disable = 1 }\n');(root/'vault.hcl').chmod(0o644)
                cid=command(tools,'create','--pull','never','--name',name,'--label','org.nightscout.vault-component='+state['owner'],'--cpus','.125','--memory',str(inventory['memoryBytes']),'--memory-swap',str(inventory['memoryBytes']),'-p','127.0.0.1:'+str(cell['ports'][0])+':8200','-v',volume+':/vault/file','-v',str(root/'vault.hcl')+':/vault/config/probe.hcl:ro',IMAGE,'vault','server','-config=/vault/config/probe.hcl').strip()
                row=inspect(tools,cid);inventory['container']={k:row[k]for k in ['id','name','created']};checked(row,inventory);batch.write(root/'vault-inventory.json',inventory)
                runner.execution_window(root,config);command(tools,'start',cid);batch.write(root/'container-before.json',inspect(tools,cid))
            origin='http://127.0.0.1:'+str(cell['ports'][0]);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def request(route,body=None,token=None):
                runner.execution_window(root,config);headers={'Content-Type':'application/json'}
                if token:headers['X-Vault-Token']=token
                data=None if body is None else json.dumps(body).encode()
                with opener.open(urllib.request.Request(origin+'/v1/'+route,data=data,headers=headers),timeout=min(10,max(.1,state['stopWorkAt']-time.time())))as r:return json.load(r)if r.status!=204 else{}
            ready=False
            for _ in range(60):
                try:request('sys/init');ready=True;break
                except Exception:
                    if time.time()+.5>=state['stopWorkAt']:break
                    time.sleep(.5)
            need(ready,'STARTUP_UNAVAILABLE')
            server=server_identity(tools,cid);batch.write(root/'server-before.json',server)
            init=request('sys/init',{'secret_shares':1,'secret_threshold':1});request('sys/unseal',{'key':init['keys_base64'][0]});token=init['root_token'];del init
            request('sys/mounts/transit',{'type':'transit'},token)
            request('sys/policies/acl/probe',{'policy':'path "transit/keys/tenant-*" { capabilities = ["create", "read", "update"] }\npath "transit/encrypt/tenant-data-*" { capabilities = ["update"] }'},token)
            scoped=request('auth/token/create',{'policies':['probe'],'no_default_policy':True,'renewable':True,'ttl':'24h'},token)['auth']['client_token'];del token
            baseline=sample(tools,cid,server);batch.write(root/'baseline.json',baseline)
            need(baseline['cgroupAndProcess'].get('cpu.max')==['13000 100000'] and baseline['cgroupAndProcess'].get('memory.max')==[str(inventory['memoryBytes'])],'NATIVE_QUOTA_CHANGED')
            with lease.host_lease('helper'):
                with runner.custody(root):
                    runner.execution_window(root,config)
                    worker=subprocess.Popen([tools['node']['path'],'--max-heap-size=128',str(WORKER)],env=ENV,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True,preexec_fn=limits(NODE_VM))
                    runner.a.job_record(root/'stage-job.json',worker,state['owner'],group=True)
                    mask=sorted(os.sched_getaffinity(worker.pid));need(mask==affinity['selected'],'AFFINITY_INHERITANCE')
                    batch.write(root/'worker-start.json',{'at':time.time(),'pid':worker.pid,'affinity':mask})
                worker.stdin.write(json.dumps({'source':str(source),'address':origin,'token':scoped,'targetSets':config['targetSets'],'allow10000':True,'stopWorkAtMs':int((state['stopWorkAt']-1)*1000),'firstFailurePath':str(root/'first-failure.json'),'runtimeReceiptPath':str(root/'runtime-receipt.json')}));worker.stdin.close();del scoped
                with(root/'checkpoints.jsonl').open('x')as log,selectors.DefaultSelector()as pipe:
                    pipe.register(worker.stdout,selectors.EVENT_READ)
                    while True:
                        if not pipe.select(runner.a.remaining_seconds(1)):continue
                        line=worker.stdout.readline()
                        if not line:break
                        value=json.loads(line);last=value;value['parentObservedAt']=time.time();log.write(json.dumps(value)+'\n');log.flush();os.fsync(log.fileno())
                        try:metrics=sample(tools,cid,server)
                        except Exception:metrics={'status':'UNMEASURED_COUNTERS','at':time.time()}
                        with(root/'samples.jsonl').open('a')as samples:samples.write(json.dumps({'workload':value,'metrics':metrics})+'\n')
                worker.wait(timeout=runner.a.remaining_seconds(15));batch.write(root/'stage-job.json',{**batch.read(root/'stage-job.json'),'completed':True,'returncode':worker.returncode})
                batch.write(root/'worker-exit.json',{'at':time.time(),'returncode':worker.returncode})
                verify_completion(config,last,worker.returncode)
    except BaseException as error:failure={'code':runner.code(error),'type':type(error).__name__}
    finally:
        try:runner.cleanup(root,'VAULT_COMPONENT_FINISHED'if failure is None else'VAULT_COMPONENT_FAILED')
        except BaseException as error:failure={**(failure or{}),'cleanup':runner.code(error)}
        until=time.monotonic()+10
        while runner.guard_alive(root) and time.monotonic()<until:time.sleep(.05)
        if runner.guard_alive(root):failure={**(failure or{}),'guard':'UNCONFIRMED'}
        try:lease.close()
        except BaseException:failure={**(failure or{}),'heap':'UNCONFIRMED'}
        result={'version':1,'producer':PRODUCER,'status':'COMPLETED'if failure is None else'FAILED_PARTIAL','failure':failure,'targetSets':config['targetSets'],'acknowledgedSets':last.get('completed')if last else None,'startedAt':start,'finishedAt':time.time(),'capacityAcceptance':'NOT_GRANTED'}
        batch.write(root/'result.json',result)
    return result
