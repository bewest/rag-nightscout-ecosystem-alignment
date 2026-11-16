"""Synthetic admission and real process/flock controls; no app/provider effects."""
import copy
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import diagnostic_resources as resources
import experiment_batch as b
import runner


def fixture(n=3):
    caps={'maxConcurrent':2,'millicpus':2,'memoryBytes':200,'heapMiB':20,'hourlyMicrousd':20,'totalMicrousd':100,'maxLiveResources':4,'maxOfferedRps':20,'cleanupAt':time.time()+600,
          'workload':{'tenants':[1,100],'offeredRps':[0,20],'durationSeconds':[1,60],'probeEveryMs':[100,5000],'hotFactor':[1,10],'faultCases':[]}}
    cells=[{'id':'c'+str(i),'namespace':'ns-cell-'+str(i),'ports':[19000+i],'subnets':['10.240.'+str(i)+'.0/24'],
            'resources':dict(zip(b.RESOURCE_KEYS,(1,100,10,10,10,2))),'offeredRps':10,'workSeconds':30,'cleanupSeconds':30,'target':{'kind':'local'},'config':{}} for i in range(n)]
    return {'version':1,'id':'synthetic-batch','payload':{'files':[{'path':'fixture','sha256':hashlib.sha256(b'synthetic').hexdigest()}],
              'source':{'core':'a'*40,'deploy':'b'*40},'image':'sha256:'+'c'*64,'helper':'d'*64},'envelope':caps,'cells':cells}


def reserve_process(directory,spec,cell,queue):
    try:queue.put(b.Reservations(directory,spec).reserve(cell))
    except Exception as error:queue.put(str(error))


class Batch(unittest.TestCase):
    def ledger(self,tmp,spec):
        ledger=b.Reservations(tmp,spec);ledger.create();return ledger

    def test_digest_matches_shared_json_number_and_key_domain(self):
        self.assertEqual(b.digest({'cost':1.0}),b.digest({'cost':1}))
        vectors=json.loads((Path(__file__).parent/'examples/batch-digest-vectors.json').read_text())
        for row in vectors['vectors']:
            self.assertEqual(b.canonical(row['value']),row['canonical'])
            self.assertEqual(b.digest(row['value']),hashlib.sha256(row['canonical'].encode()).hexdigest())
        for value in (float('nan'),float('inf'),9007199254740992,1e20,1e21):
            with self.assertRaises(RuntimeError):b.digest(value)
        self.assertEqual(b.canonical({'z':1,'a':2}),'{"a":2,"z":1}')

    def test_payload_and_plan_bind_whole_spec(self):
        spec=fixture();original=b.plan(spec,now=1)
        self.assertEqual(original['specSha256'],b.digest(spec))
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'fixture';file.write_bytes(b'synthetic');b.verify_payload(spec,tmp)
            file.write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError,'PAYLOAD_CHANGED'):b.verify_payload(spec,tmp)
            file.unlink();file.symlink_to('/etc/hosts')
            with self.assertRaisesRegex(RuntimeError,'PAYLOAD_SYMLINK'):b.verify_payload(spec,tmp)
        for key in ('image','helper','source'):
            changed=copy.deepcopy(spec);changed['payload'][key]='unpinned'
            with self.assertRaises((RuntimeError,TypeError)):b.plan(changed)
        changed=copy.deepcopy(spec);changed['cells'][0]['config']['tenants']=9
        self.assertNotEqual(b.plan(changed)['specSha256'],original['specSha256'])

    def test_isolation_cost_deadline_and_per_cell_overcommit_refuse(self):
        for field in ('namespace','ports','subnets'):
            spec=fixture();spec['cells'][1][field]=spec['cells'][0][field]
            with self.assertRaises(RuntimeError):b.plan(spec)
        for key in b.RESOURCE_KEYS:
            spec=fixture();spec['cells'][0]['resources'][key]=spec['envelope'][b.CAP_KEYS[key]]+1
            with self.assertRaisesRegex(RuntimeError,'CELL_OVERCOMMIT'):b.plan(spec)
        spec=fixture();spec['envelope']['totalMicrousd']=20
        with self.assertRaisesRegex(RuntimeError,'TOTAL_COST'):b.plan(spec)
        spec=fixture();spec['envelope']['cleanupAt']=time.time()+10
        with self.assertRaisesRegex(RuntimeError,'CELL_DEADLINE'):b.plan(spec)

    def test_long_declared_window_still_requires_remaining_batch_lifetime(self):
        spec=fixture(1);cell=spec['cells'][0]
        cell.update(workSeconds=3600,cleanupSeconds=300)
        spec['envelope']['cleanupAt']=5000
        b.plan(spec,now=1000)
        with self.assertRaisesRegex(RuntimeError,'CELL_DEADLINE'):b.plan(spec,now=1101)
        with tempfile.TemporaryDirectory() as tmp:
            ledger=self.ledger(tmp,spec)
            with self.assertRaisesRegex(RuntimeError,'CELL_DEADLINE'):ledger.reserve(cell,now=1101)
            self.assertEqual(b.read(ledger.file)['cells'],{})
            self.assertIsNotNone(ledger.reserve(cell,now=1000))

    def test_every_aggregate_dimension(self):
        for key in b.RESOURCE_KEYS:
            if key=='totalMicrousd':continue
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                spec=fixture();spec['envelope']['maxConcurrent']=9
                for cap in b.CAP_KEYS.values():spec['envelope'][cap]=100000
                spec['envelope'][b.CAP_KEYS[key]]=spec['cells'][0]['resources'][key]
                ledger=self.ledger(tmp,spec)
                self.assertIsNotNone(ledger.reserve(spec['cells'][0]));self.assertIsNone(ledger.reserve(spec['cells'][1]))

    def test_multiprocess_atomic_race_never_overcommits(self):
        spec=fixture(12)
        with tempfile.TemporaryDirectory() as tmp:
            ledger=self.ledger(tmp,spec);context=multiprocessing.get_context('fork');queue=context.Queue()
            actors=[context.Process(target=reserve_process,args=(tmp,spec,c,queue)) for c in spec['cells']]
            for actor in actors:actor.start()
            answers=[queue.get(timeout=5) for _ in actors]
            for actor in actors:actor.join(5);self.assertEqual(actor.exitcode,0)
            self.assertEqual(sum(type(x) is dict for x in answers),2)
            rows=b.read(ledger.file)['cells'];self.assertEqual(len(rows),2)
            self.assertEqual(sum(x['resources']['millicpus'] for x in rows.values()),2)

    def test_exact_release_and_stale_birth_refusal(self):
        spec=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            ledger=self.ledger(tmp,spec);one=ledger.reserve(spec['cells'][0]);two=ledger.reserve(spec['cells'][1])
            with self.assertRaisesRegex(RuntimeError,'FOREIGN_RELEASE'):ledger.release({**one,'nonce':'foreign'}, {'status':'ABSENT','id':one['id'],'nonce':'foreign'})
            with self.assertRaisesRegex(RuntimeError,'ABSENCE_REQUIRED'):ledger.release(one,{'status':'ABSENT'})
            ledger.release(one,{'status':'ABSENT','id':one['id'],'nonce':one['nonce']})
            self.assertEqual(b.read(ledger.file)['cells'][two['id']]['status'],'RESERVED')
            ledger.reserve(spec['cells'][2])
            value=b.read(ledger.file);value['startTicks']='foreign';b.write(ledger.file,value)
            with self.assertRaisesRegex(RuntimeError,'STALE_OWNER'):ledger.release(two,{})

    def test_peer_results_and_cancel(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel),tempfile.TemporaryDirectory() as tmp:
                spec=fixture(4);ledger=self.ledger(tmp,spec);flag=threading.Event();entered=[];barrier=threading.Barrier(2)
                def execute(cell,ticket):
                    entered.append(cell['id']);barrier.wait(2)
                    if cancel:flag.set()
                    time.sleep(.03)
                    return {'status':'FAILED_PARTIAL' if cell['id']=='c0' else 'MEASURED','oracle':'UNMEASURED' if cell['id']=='c0' else 'PASS'}, {'status':'ABSENT','id':ticket['id'],'nonce':ticket['nonce']}
                result=b.schedule(spec,ledger,execute,flag.is_set)
                self.assertEqual(result['cells']['c1']['status'],'MEASURED');self.assertEqual(result['cells']['c0']['oracle'],'UNMEASURED')
                self.assertEqual(len(entered),2 if cancel else 4)
                self.assertTrue(all(v['status']=='ABSENT' for v in b.read(ledger.file)['cells'].values()))

    def test_unconfirmed_cleanup_retains_reservation(self):
        spec=fixture();spec['envelope']['maxConcurrent']=1
        with tempfile.TemporaryDirectory() as tmp:
            ledger=self.ledger(tmp,spec)
            result=b.schedule(spec,ledger,lambda cell,ticket:({'status':'PARTIAL'},{'status':'UNMEASURED'}))
            self.assertEqual(result['cells']['c0']['cleanup'],'UNCONFIRMED');self.assertEqual(result['cells']['c1']['status'],'BLOCKED_RESERVATION_RETAINED')
            self.assertEqual(b.read(ledger.file)['cells']['c0']['status'],'RESERVED')

    def test_payload_change_stops_new_admission_preserves_entered(self):
        spec=fixture();calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            ledger=self.ledger(tmp,spec)
            def changed():
                calls.append(1)
                if len(calls)>1:raise RuntimeError('M7_BATCH_PAYLOAD_CHANGED')
            result=b.schedule(spec,ledger,lambda cell,ticket:({'status':'MEASURED'},{'status':'ABSENT','id':ticket['id'],'nonce':ticket['nonce']}),changed=changed)
            self.assertEqual(result['cells']['c0']['status'],'MEASURED');self.assertEqual(result['cells']['c1']['status'],'REFUSED_NOT_STARTED')

    def test_batch_preparation_rechecks_actual_source_before_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'cell';calls=[]
            with patch.dict(os.environ,{'M7_BATCH_RESERVATION':'synthetic'}), patch.object(runner,'load_config',return_value=({},[])), patch.object(runner,'arm_window'), patch.object(runner,'stage',side_effect=lambda root,name,args:calls.append((name,args))):
                runner.prepare('synthetic',root)
            self.assertEqual([c[0] for c in calls],['prepare','source-preflight'])
            self.assertEqual(calls[1][1],['source-preflight',str(root/'fixture')])

    def test_local_whole_cell_limits_and_configurable_aggregate(self):
        spec=fixture(1)
        with tempfile.TemporaryDirectory() as tmp,patch.object(runner,'validate_config'):
            (Path(tmp)/'fixture').write_bytes(b'synthetic')
            spec['envelope'].update({k:v for k,v in b.LOCAL_RESOURCES.items() if k in spec['envelope']})
            spec['envelope']['hourlyMicrousd']=spec['envelope']['totalMicrousd']=0;spec['envelope']['maxLiveResources']=64
            cell=spec['cells'][0];cell['resources']=dict(b.LOCAL_RESOURCES);cell['ports']=[]
            cell['config']={'helperInstrument':spec['payload']['helper'],'workSeconds':30,'cleanupSeconds':30,'prepare':{'receipt':str(Path(tmp)/'fixture'),'core-commit':'a'*40,'deploy-commit':'b'*40,'image-id':spec['payload']['image'],'image':spec['payload']['image'],'diagnostic-resource-profile':resources.NAME,'fixture-project':cell['namespace'],'backend-subnet':cell['subnets'][0],'edge-subnet':'10.241.0.0/24','offered-rps':10,'tenants':3,'load-seconds':10}}
            cell['subnets'].append('10.241.0.0/24');runner.local_batch_plan(spec,tmp)
            options=cell['config']['prepare']
            options['diagnostic-resource-profile']=resources.EXTERNAL_NAME
            with self.assertRaisesRegex(RuntimeError,'LOCAL_TOPOLOGY_PROFILE'):runner.local_batch_plan(spec,tmp)
            options['pgstream-topology']='external-service-v1';runner.local_batch_plan(spec,tmp)
            options['diagnostic-resource-profile']=resources.EVALUATOR250_NAME
            runner.local_batch_plan(spec,tmp)
            options['diagnostic-resource-profile']=resources.EVALUATOR250_MEMORY512_NAME
            with self.assertRaisesRegex(RuntimeError,'LOCAL_PROFILE_RESERVATION_UNSUPPORTED'):runner.local_batch_plan(spec,tmp)
            options['diagnostic-resource-profile']=resources.EVALUATOR250_NAME
            runner.local_batch_plan(spec,tmp)
            cell['resources']['millicpus']=3999
            with self.assertRaisesRegex(RuntimeError,'LOCAL_RESERVATION_CHANGED'):runner.local_batch_plan(spec,tmp)
            cell['resources']['millicpus']=4000;spec['envelope']['millicpus']=8000
            runner.local_batch_plan(spec,tmp)
            spec['envelope']['millicpus']=3999
            with self.assertRaisesRegex(RuntimeError,'CELL_OVERCOMMIT'):runner.local_batch_plan(spec,tmp)

    def test_real_legacy_lock_and_stale_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'legacy.lock';one=resources.Runtime();one.acquire(file)
            try:
                with self.assertRaisesRegex(RuntimeError,'OTHER_DRIVER_ACTIVE'):resources.Runtime().acquire(file)
            finally:one.close()
            file.write_text('stale evidence')
            with self.assertRaisesRegex(RuntimeError,'STALE_HOST_LEASES'):resources.Runtime().acquire(file)
            self.assertEqual(file.read_text(),'stale evidence')

    def test_real_batch_custody_and_child_driver_use_exact_aggregate_ticket(self):
        spec=fixture(1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'global.lock';folder=Path(tmp)/'batch'
            original_acquire=resources.Runtime.acquire
            def acquire(runtime,lock_file=None):return original_acquire(runtime,lock_file or path)
            # Keep this real cross-process custody test independent of a suite's
            # private default-lock wrapper while retaining the actual flock path.
            with patch.object(resources.Runtime,'acquire',acquire), patch.object(b,'global_lock_path',return_value=path), b.local_custody(folder,spec) as ledger:
                ticket=ledger.reserve(spec['cells'][0]);file=folder/'c0.ticket.json';b.write(file,ticket)
                source="import experiment_batch as b,diagnostic_resources as r;from pathlib import Path;b.global_lock_path=lambda:Path(__import__('sys').argv[1]);x=r.Runtime();x.acquire();x.close()"
                child=subprocess.run([sys.executable,'-B','-c',source,str(path)],env={**os.environ,'M7_BATCH_RESERVATION':str(file)},capture_output=True,text=True,timeout=5,cwd=Path(__file__).resolve().parent)
                self.assertEqual(child.returncode,0,child.stderr)
                self.assertTrue((folder/'c0.heap.lock').exists())
                ledger.release(ticket,{'status':'ABSENT','id':ticket['id'],'nonce':ticket['nonce']})
            self.assertEqual(path.read_bytes(),b'')
            # A second synthetic batch with unresolved cleanup keeps the marker.
            with patch.object(resources.Runtime,'acquire',acquire), patch.object(b,'global_lock_path',return_value=path), b.local_custody(Path(tmp)/'unclosed',spec) as ledger:
                ledger.reserve(spec['cells'][0])
            with self.assertRaisesRegex(RuntimeError,'STALE_HOST_LEASES'):resources.Runtime().acquire(path)
            self.assertTrue(path.read_bytes())

    def test_actual_batch_caller_overlaps_processes_and_preserves_ticket_inputs(self):
        # Real batch_run -> exec -> batch_cell -> ticket/flock. Only synthetic
        # prepare/execute replace app actors; native SUT/provider is unmeasured.
        spec=fixture(2)
        spec['envelope'].update({b.CAP_KEYS[k]:v*2 for k,v in b.LOCAL_RESOURCES.items()})
        for cell in spec['cells']:
            cell['resources']=dict(b.LOCAL_RESOURCES)
            cell['config']={'workSeconds':30,'cleanupSeconds':30,'source':spec['payload']['source']}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);shim=folder/'shim';shim.mkdir();out=folder/'output';lock=folder/'global.lock'
            (shim/'runner.py').write_text("""
import sys,os,time,json
from pathlib import Path
sys.path.insert(0,os.environ['TEST_RUNNER_SOURCE'])
import runner,experiment_batch as b,diagnostic_resources as resources
b.global_lock_path=lambda:Path(os.environ['TEST_RUNNER_LOCK'])
def prepare(config,root):
    root.mkdir();cfg=b.read(config);ticket=b.read(os.environ['M7_BATCH_RESERVATION'])
    lease=resources.Runtime();lease.acquire()
    start=time.time();(root.parent/(root.name+'.started')).touch()
    until=time.monotonic()+3
    while len(list(root.parent.glob('*.started')))<2 and time.monotonic()<until:time.sleep(.01)
    assert len(list(root.parent.glob('*.started')))==2,'processes did not overlap'
    time.sleep(.03)
    b.write(root/'witness.json',{'source':cfg['source'],'cleanupAt':ticket['cleanupAt'],'start':start,'end':time.time(),'pid':os.getpid()})
    lease.close()
def execute(root):
    b.write(root/'cleanup.json',{'status':'ABSENT'})
    b.write(root/'result.json',{'status':'FAILED_PARTIAL' if root.name=='c0' else 'MEASURED'})
runner.prepare=prepare;runner.execute=execute
runner.batch_cell(sys.argv[2],sys.argv[3])
""")
            file=folder/'spec.json';b.write(file,spec)
            original=resources.Runtime.acquire
            def acquire(runtime,lock_file=None):return original(runtime,lock_file or lock)
            with patch.object(runner,'HERE',shim),patch.object(runner,'local_batch_plan',side_effect=lambda s,p:b.plan(s)),patch.object(runner,'guard_alive',return_value=False),patch.object(resources.Runtime,'acquire',acquire),patch.object(b,'global_lock_path',return_value=lock),patch.dict(os.environ,{'TEST_RUNNER_SOURCE':str(Path(__file__).resolve().parent),'TEST_RUNNER_LOCK':str(lock)}):
                result=runner.batch_run(file,out,folder)
            self.assertEqual(result['cells']['c0']['status'],'FAILED_PARTIAL')
            self.assertEqual(result['cells']['c1']['status'],'MEASURED')
            one=b.read(out/'c0/witness.json');two=b.read(out/'c1/witness.json')
            self.assertNotEqual(one['pid'],two['pid'])
            self.assertLess(max(one['start'],two['start']),min(one['end'],two['end']))
            for witness in (one,two):
                self.assertEqual(witness['source'],spec['payload']['source'])
                self.assertEqual(witness['cleanupAt'],spec['envelope']['cleanupAt'])
            self.assertTrue(all(row['status']=='ABSENT' for row in b.read(out/'reservations.json')['cells'].values()))

    def test_delayed_batch_child_refuses_before_preparation(self):
        spec=fixture(1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);ledger=self.ledger(tmp,spec);ticket=ledger.reserve(spec['cells'][0]);ticket['cleanupAt']=time.time()+1
            file=path/'ticket.json';b.write(file,ticket);config=path/'config.json';b.write(config,{'workSeconds':3600,'cleanupSeconds':300})
            with patch.dict(os.environ,{'M7_BATCH_RESERVATION':str(file)}),patch.object(b,'child_lock',return_value=path/'heap.lock'),patch.object(runner,'prepare') as prepare:
                with self.assertRaisesRegex(RuntimeError,'M7_BATCH_CELL_DEADLINE'):runner.batch_cell(config,path/'point')
            prepare.assert_not_called()

    def test_child_stale_birth_and_foreign_nonce(self):
        spec=fixture(1)
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp,0o700);ledger=self.ledger(tmp,spec);ticket=ledger.reserve(spec['cells'][0]);file=Path(tmp)/'c0.ticket.json';b.write(file,ticket)
            with patch.dict(os.environ,{'M7_BATCH_RESERVATION':str(file)}):
                value=b.read(ledger.file);value['startTicks']='wrong';b.write(ledger.file,value)
                with self.assertRaisesRegex(RuntimeError,'STALE_OWNER'):b.child_lock()
                value['startTicks']=b.birth(os.getpid());value['cells']['c0']['nonce']='wrong';b.write(ledger.file,value)
                with self.assertRaisesRegex(RuntimeError,'FOREIGN_TICKET'):b.child_lock()

if __name__=='__main__':unittest.main()
