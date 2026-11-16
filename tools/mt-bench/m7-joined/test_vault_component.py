"""Typed source/reservation/finite cleanup controls; no Docker effects."""
import copy
import hashlib
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import experiment_batch as b
import diagnostic_resources as resources
import runner
import vault_component as v


class Vault(unittest.TestCase):
    def fixture(self,folder):
        root=Path(folder);source={name:hashlib.sha256(name.encode()).hexdigest()for name in v.SOURCE_FILES}
        for name in source:
            file=root/'source'/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(name.encode())
        tools={}
        for name in ('node','docker'):
            file=root/name;file.write_bytes(('synthetic-'+name).encode())
            tools[name]={'path':str(file),'sha256':v.file_sha(file),'version':'v24.22.1'if name=='node'else'synthetic'}
        helper='d'*64;payload={'source':{'core':v.CORE,'deploy':'b'*40},'image':v.IMAGE_ID,'helper':helper,'files':[]}
        capsule={'version':1,'producer':v.PRODUCER,'source':payload['source'],'image':v.IMAGE,'imageId':v.IMAGE_ID,'helper':helper,'files':source,'workerSha256':v.file_sha(v.WORKER),'tools':tools}
        b.write(root/'capsule.json',capsule)
        payload['files']=[{'path':str(p.relative_to(root)),'sha256':v.file_sha(p)}for p in root.rglob('*')if p.is_file()]
        cfg={'version':1,'producer':v.PRODUCER,'capsule':str(root/'capsule.json'),'helperInstrument':helper,'workSeconds':30,'cleanupSeconds':30,'targetSets':16,'vaultMemoryMiB':256}
        cells=[{'id':'v'+str(i),'namespace':'ns-vault-test-'+str(i),'ports':[21740+i],'subnets':[],'target':{'kind':'local'},'resources':v.claim(cfg),'offeredRps':0,'workSeconds':30,'cleanupSeconds':30,'config':copy.deepcopy(cfg)}for i in range(2)]
        envelope={b.CAP_KEYS[k]:val*2 for k,val in v.claim(cfg).items()};envelope.update(maxConcurrent=2,maxOfferedRps=0,cleanupAt=time.time()+180,workload={'tenants':[1,32],'offeredRps':[0,0],'durationSeconds':[30,90],'probeEveryMs':[0,0],'hotFactor':[1,1],'faultCases':[]})
        return {'version':1,'id':'vault-unit','payload':payload,'envelope':envelope,'cells':cells},source

    def test_local_planner_derives_whole_claim_and_refuses_underclaims(self):
        with tempfile.TemporaryDirectory()as tmp:
            spec,source=self.fixture(tmp)
            with patch.object(v,'SOURCE_FILES',source),patch.object(runner.a,'instrument',return_value={'sha256':'d'*64}):
                result=runner.local_batch_plan(spec,tmp)
                self.assertEqual(result['cells'][0]['allocationBreakdown']['vault']['effectiveMillicpus'],130)
                self.assertEqual(result['cells'][0]['resources']['heapMiB'],128)
                remote=copy.deepcopy(spec);remote['cells'][0]['target']={'kind':'remote'}
                with self.assertRaisesRegex(RuntimeError,'LOCAL_TARGET'):runner.local_batch_plan(remote,tmp)
                for key in b.RESOURCE_KEYS:
                    bad=copy.deepcopy(spec)
                    if key in ('hourlyMicrousd','totalMicrousd'):bad['cells'][0]['resources'][key]=1;bad['envelope'][b.CAP_KEYS[key]]=2
                    else:bad['cells'][0]['resources'][key]-=1
                    with self.assertRaisesRegex(RuntimeError,'LOCAL_MONEY'if key in ('hourlyMicrousd','totalMicrousd')else'VAULT_RESERVATION_CHANGED'):runner.local_batch_plan(bad,tmp)
                for key in b.RESOURCE_KEYS:
                    if spec['cells'][0]['resources'][key]==0:continue
                    bad=copy.deepcopy(spec);bad['envelope'][b.CAP_KEYS[key]]=spec['cells'][0]['resources'][key]-1
                    with self.assertRaisesRegex(RuntimeError,'CELL_OVERCOMMIT'):runner.local_batch_plan(bad,tmp)

    def test_source_capsule_quota_envelope_and_tools_are_not_advisory(self):
        with tempfile.TemporaryDirectory()as tmp:
            spec,source=self.fixture(tmp);cell=spec['cells'][0]
            with patch.object(v,'SOURCE_FILES',source):
                allowed=b.verify_payload(spec,tmp);v.plan(cell,spec,tmp,allowed)
                for key,value in [('targetSets',10001),('vaultMemoryMiB',2048),('workSeconds',3601),('cleanupSeconds',181)]:
                    bad=copy.deepcopy(cell);bad['config'][key]=value
                    with self.assertRaisesRegex(RuntimeError,'FINITE_BOUND|MEMORY_PROFILE'):v.plan(bad,spec,tmp,allowed)
                bad=copy.deepcopy(cell);bad['config']['vaultMemoryMiB']=512
                with self.assertRaisesRegex(RuntimeError,'RESERVATION_CHANGED'):v.plan(bad,spec,tmp,allowed)
                bad=copy.deepcopy(spec);bad['envelope']['workload']['tenants']=[1,8]
                with self.assertRaisesRegex(RuntimeError,'WORKLOAD_OUTSIDE_ENVELOPE'):v.plan(cell,bad,tmp,allowed)
                file=Path(tmp)/'source'/next(iter(source));file.write_text('BROKEN_SOURCE')
                with self.assertRaisesRegex(RuntimeError,'SOURCE_BYTES'):v.plan(cell,spec,tmp,allowed)
                file.write_bytes(next(iter(source)).encode());v.plan(cell,spec,tmp,allowed)
                capsule=b.read(Path(tmp)/'capsule.json');capsule['source']['core']='0'*40;b.write(Path(tmp)/'capsule.json',capsule)
                with self.assertRaisesRegex(RuntimeError,'SOURCE_PIN'):v.plan(cell,spec,tmp,allowed)

    def test_ticket_parent_and_config_change_refuse_before_actor(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);payload=root/'payload';payload.mkdir();spec,source=self.fixture(payload);lock=root/'global.lock'
            original=resources.Runtime.acquire
            def acquire(runtime,lock_file=None):return original(runtime,lock_file or lock)
            with patch.object(resources.Runtime,'acquire',acquire),patch.object(b,'global_lock_path',return_value=lock),b.local_custody(root/'batch',spec)as ledger:
                b.write(ledger.directory/'batch.json',spec);b.write(ledger.directory/'batch-payload.json',{'root':str(payload),'specSha256':b.digest(spec)})
                ticket=ledger.reserve(spec['cells'][0]);file=ledger.directory/'v0.ticket.json';b.write(file,ticket)
                cfg=spec['cells'][0]['config'];configfile=ledger.directory/'config.json';b.write(configfile,cfg)
                with patch.dict(os.environ,{'M7_BATCH_RESERVATION':str(file)}),patch.object(v,'command')as effect,patch.object(runner,'arm_window')as guard:
                    value=b.read(ledger.file);valid=copy.deepcopy(value);value['startTicks']='wrong';b.write(ledger.file,value)
                    with self.assertRaisesRegex(RuntimeError,'STALE_OWNER'):v.execute(configfile,root/'point')
                    b.write(ledger.file,valid);b.write(file,{**ticket,'nonce':'foreign'})
                    with self.assertRaisesRegex(RuntimeError,'FOREIGN_TICKET'):v.execute(configfile,root/'point')
                    b.write(file,ticket);b.write(configfile,{**cfg,'vaultMemoryMiB':512})
                    with self.assertRaisesRegex(RuntimeError,'CELL_CONFIG_CHANGED'):b.reserved_cell({**cfg,'vaultMemoryMiB':512})
                    with self.assertRaisesRegex(RuntimeError,'CELL_CONFIG_CHANGED'):v.execute(configfile,root/'point')
                    b.write(configfile,cfg);self.assertEqual(b.reserved_cell(cfg)[0],spec['cells'][0]);effect.assert_not_called();guard.assert_not_called()
                ledger.release(ticket,{'status':'ABSENT','id':ticket['id'],'nonce':ticket['nonce']})

    def test_cleanup_requires_exact_identity_limits_and_absence(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);state={'owner':'a'*32,'producer':v.PRODUCER};b.write(root/'execution.json',state)
            inv={'owner':state['owner'],'memoryBytes':256*v.MIB,'tools':{'docker':{'path':'unused','sha256':'safe'}},'container':{'id':'c'*64,'created':'birth','name':'/owned'},'volume':None};b.write(root/'vault-inventory.json',inv)
            row={**inv['container'],'owner':state['owner'],'image':v.IMAGE_ID,'limits':{'Memory':256*v.MIB,'MemorySwap':256*v.MIB,'NanoCpus':125000000}}
            for key in ('id','created','name'):
                with self.assertRaisesRegex(RuntimeError,'INCARNATION_CHANGED'):v.checked({**row,key:'foreign'},inv)
            for field in ('Memory','MemorySwap','NanoCpus'):
                bad=copy.deepcopy(row);bad['limits'][field]+=1
                with self.assertRaisesRegex(RuntimeError,'QUOTA_CHANGED'):v.checked(bad,inv)
            v.checked(row,inv)
            def census(tools,*args,**kwargs):return 'owned'if args[:2]==('ps','-aq')else''
            with patch.object(v,'file_sha',return_value='safe'),patch.object(v,'command',side_effect=census),patch.object(v,'inspect',return_value={**row,'created':'foreign'}):
                with self.assertRaisesRegex(RuntimeError,'INCARNATION_CHANGED'):runner.cleanup(root,'TEST')
            self.assertFalse((root/'cleanup.json').exists())

    def test_real_typed_process_dispatch_overlaps_and_retains_uncertain_cleanup(self):
        for uncertain in (False,True,'residual'):
            with self.subTest(uncertain=uncertain),tempfile.TemporaryDirectory()as tmp:
                root=Path(tmp);payload=root/'payload';payload.mkdir();spec,_=self.fixture(payload)
                third=copy.deepcopy(spec['cells'][1]);third.update(id='v2',namespace='ns-vault-test-2',ports=[21742]);spec['cells'].append(third)
                shim=root/'shim';shim.mkdir();lock=root/'global.lock';file=root/'spec.json';b.write(file,spec)
                (shim/'runner.py').write_text("""
import os,sys,time,subprocess
from pathlib import Path
sys.path.insert(0,os.environ['TEST_VAULT_SOURCE'])
import runner,experiment_batch as b,diagnostic_resources as r,vault_component as v
b.global_lock_path=lambda:Path(os.environ['TEST_VAULT_LOCK'])
def execute(config,root):
    cfg=b.read(config);cell,spec,payload=b.reserved_cell(cfg);lease=r.Runtime();lease.acquire()
    root.mkdir();start=time.time();(root.parent/(root.name+'.started')).touch()
    until=time.monotonic()+3
    while len(list(root.parent.glob('*.started')))<2 and time.monotonic()<until:time.sleep(.01)
    assert len(list(root.parent.glob('*.started')))>=2,'TYPED_OVERLAP_REQUIRED'
    time.sleep(.04)
    b.write(root/'witness.json',{'start':start,'end':time.time(),'pid':os.getpid(),'claim':cell['resources']})
    if root.name=='v0'and os.environ['TEST_VAULT_UNCERTAIN']=='residual':
        child=subprocess.Popen(['sleep','20']);b.write(root/'orphan.json',{'pid':child.pid,'startTicks':b.birth(child.pid)})
    b.write(root/'cleanup.json',{'status':'UNMEASURED'if root.name=='v0'and os.environ['TEST_VAULT_UNCERTAIN']=='1'else'ABSENT'})
    result={'status':'FAILED_PARTIAL'if root.name=='v0'else'MEASURED'};b.write(root/'result.json',result);lease.close();return result
v.execute=execute
runner.batch_cell(sys.argv[2],sys.argv[3])
""")
                original=resources.Runtime.acquire
                def acquire(runtime,lock_file=None):return original(runtime,lock_file or lock)
                with patch.object(runner,'HERE',shim),patch.object(runner,'local_batch_plan',side_effect=lambda spec,root:b.plan(spec)),patch.object(runner,'guard_alive',return_value=False),patch.object(resources.Runtime,'acquire',acquire),patch.object(b,'global_lock_path',return_value=lock),patch.dict(os.environ,{'TEST_VAULT_SOURCE':str(Path(__file__).resolve().parent),'TEST_VAULT_LOCK':str(lock),'TEST_VAULT_UNCERTAIN':'residual'if uncertain=='residual'else'1'if uncertain else'0'}):
                    result=runner.batch_run(file,root/'out',payload)
                try:
                    self.assertEqual(result['cells']['v1']['status'],'MEASURED');self.assertEqual(result['cells']['v2']['status'],'MEASURED')
                    one=b.read(root/'out/v0/witness.json');two=b.read(root/'out/v1/witness.json')
                    self.assertNotEqual(one['pid'],two['pid']);self.assertLess(max(one['start'],two['start']),min(one['end'],two['end']))
                    rows=b.read(root/'out/reservations.json')['cells'];self.assertEqual(rows['v0']['status'],'RESERVED'if uncertain else'ABSENT')
                    self.assertEqual(bool(lock.read_bytes()),bool(uncertain))
                    if uncertain=='residual':self.assertIn('M7_BATCH_CELL_GROUP_REMAINS',result['cells']['v0']['error'])
                finally:
                    file=root/'out/v0/orphan.json'
                    if file.exists():
                        job=b.read(file)
                        if b.birth(job['pid'])==job['startTicks']:os.kill(job['pid'],15)
                        until=time.monotonic()+3
                        while b.birth(job['pid'])==job['startTicks']and time.monotonic()<until:time.sleep(.01)
                        self.assertNotEqual(b.birth(job['pid']),job['startTicks'])


    def test_affinity_controls_are_confined_to_a_harmless_child(self):
        before=os.sched_getaffinity(0)
        code="""
import os,json,vault_component as v
before=sorted(os.sched_getaffinity(0))
try:v.pin_host(os.getpid());raise AssertionError('coordinator accepted')
except RuntimeError as e:assert str(e)=='M7_BATCH_VAULT_AFFINITY_NOT_CELL'
assert sorted(os.sched_getaffinity(0))==before
realget=v.os.sched_getaffinity;realset=v.os.sched_setaffinity
v.os.sched_getaffinity=lambda pid:{1,2};v.os.sched_setaffinity=lambda pid,mask:None
try:v.pin_host(os.getppid());raise AssertionError('wrong affinity accepted')
except RuntimeError as e:assert str(e)=='M7_BATCH_VAULT_AFFINITY_CHANGED'
v.os.sched_getaffinity=realget;v.os.sched_setaffinity=realset
record=v.pin_host(os.getppid());assert len(os.sched_getaffinity(0))==1
print(json.dumps(record))
"""
        child=subprocess.run([sys.executable,'-B','-c',code],cwd=Path(__file__).parent,capture_output=True,text=True,timeout=5)
        self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(os.sched_getaffinity(0),before)

    def test_guard_cannot_arm_a_fresh_window_past_the_parent_cutoff(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);cfg={'producer':v.PRODUCER,'workSeconds':30,'cleanupSeconds':30};b.write(root/'config.json',cfg)
            ticket=root/'ticket';b.write(ticket,{'cleanupAt':time.time()+59})
            with patch.dict(os.environ,{'M7_BATCH_RESERVATION':str(ticket)}),patch.object(runner.subprocess,'Popen',side_effect=AssertionError('WINDOW_EFFECT_AFTER_CUTOFF'))as effect:
                with self.assertRaisesRegex(RuntimeError,'M7_BATCH_CELL_DEADLINE'):runner.arm_window(root,cfg)
                effect.assert_not_called();self.assertFalse((root/'execution.json').exists())

    def test_native_commands_share_the_existing_absolute_deadline(self):
        with runner.a.command_deadline(time.time()-1),patch.object(v.subprocess,'check_output')as effect:
            with self.assertRaisesRegex(RuntimeError,'M7_COMMAND_DEADLINE'):v.command({'docker':{'path':'not-run'}},'ps')
            effect.assert_not_called()

    def test_completed_prefix_is_not_the_requested_full_target(self):
        cfg={'targetSets':10000}
        for record,rc in [(None,0),({'status':'COMPLETE','completed':6000,'target':6000},0),({'status':'PARTIAL','completed':10000,'target':10000},1)]:
            with self.assertRaisesRegex(RuntimeError,'WORKER_PARTIAL'):v.verify_completion(cfg,record,rc)
        v.verify_completion(cfg,{'status':'COMPLETE','completed':10000,'target':10000},0)

    def test_actual_old_space_receipt_cannot_satisfy_total_heap_claim(self):
        receipt={'version':'v24.22.1','heapLimit':335544320,'affinity':'Cpus_allowed_list:\t0'}
        tools={'node':{'version':'v24.22.1'}};mask={'selected':[0]}
        with self.assertRaisesRegex(RuntimeError,'NODE_HEAP_RECEIPT'):v.verify_node_receipt(receipt,tools,mask)
        receipt['heapLimit']=134217728;v.verify_node_receipt(receipt,tools,mask)
        receipt['affinity']='Cpus_allowed_list:\t0-1'
        with self.assertRaisesRegex(RuntimeError,'AFFINITY_INHERITANCE'):v.verify_node_receipt(receipt,tools,mask)

    def test_runner_routes_typed_cell_on_existing_window(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);cfg={'producer':v.PRODUCER,'workSeconds':30,'cleanupSeconds':30};file=root/'config';b.write(file,cfg);ticket=root/'ticket';b.write(ticket,{'cleanupAt':time.time()+90})
            with patch.dict(os.environ,{'M7_BATCH_RESERVATION':str(ticket)}),patch.object(b,'child_lock',return_value=root/'heap.lock'),patch.object(v,'execute',return_value={'status':'MEASURED'})as execute,patch.object(runner,'prepare',side_effect=AssertionError('VAULT_TYPED_DISPATCH_REQUIRED'))as ordinary:
                self.assertEqual(runner.batch_cell(file,root/'point')['status'],'MEASURED');execute.assert_called_once();ordinary.assert_not_called()

if __name__=='__main__':unittest.main()
