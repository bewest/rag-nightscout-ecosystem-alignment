"""Synthetic API replies and real finite subprocesses; no kube/cloud/Docker."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import kube_adapter as k
import execute

HERE = Path(__file__).resolve().parent

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace('+00:00', 'Z')


def fixture():
    now = time.time()
    c = {'version':1,'runId':'synthetic-kube-control','context':'synthetic-context','namespace':'synthetic-namespace','ownerLabel':'nightscout.io/run-id',
         'kubectl':'/synthetic/bin/kubectl','readonlyGuard':'/synthetic/ops/bin/ro',
         'pins':{'pair':{'core':'1'*40,'deploy':'2'*40},'bindingCommit':'3'*40,'renderSha256':'4'*64,'inventorySha256':'5'*64,'instrument':'6'*64,
                 'appImage':'example.invalid/synthetic@sha256:'+'7'*64,'appImageId':'sha256:'+'8'*64},
         'deadlines':{'workUntil':iso(now+120),'cleanupUntil':iso(now+240)}, 'storageMode':'disposable',
         'driver':{'hostId':'synthetic-driver','sharedHost':True,'resources':{'millicpus':1000,'memoryBytes':1073741824}},
         'observer':{'hostId':'synthetic-observer','sharedHost':True,'resources':{'millicpus':200,'memoryBytes':268435456}},
         'roles':{r:{'workload':'StatefulSet/'+('postgres' if r=='postgres' else 'cohort'),'container':r} for r in ('api','realtime','evaluator','postgres')}}
    inv = {'sourceCommit':c['pins']['pair']['core'],'imageDeployCommit':c['pins']['pair']['deploy'],'bindingIdentity':c['pins']['bindingCommit'],'runId':c['runId'],'prefix':'nsdemo'}
    labels = {c['ownerLabel']:c['runId']}
    def metadata(name, namespace=True):
        return {'name':name,**({'namespace':c['namespace']} if namespace else {}),'labels':copy.deepcopy(labels)}
    resources={'requests':{'cpu':'100m','memory':'64Mi','ephemeral-storage':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi','ephemeral-storage':'128Mi'}}
    rendered=[{'apiVersion':'v1','kind':'Namespace','metadata':metadata(c['namespace'],False)}]
    for name,roles in [('cohort',['api','realtime','evaluator']),('postgres',['postgres'])]:
        containers=[{'name':r,'image':c['pins']['appImage'] if r!='postgres' else 'example.invalid/postgres@sha256:'+'9'*64,
                     'command':['node','deploy/multitenant/entrypoint.js',r] if r!='postgres' else ['postgres'], 'resources':copy.deepcopy(resources)} for r in roles]
        rendered.append({'apiVersion':'apps/v1','kind':'StatefulSet','metadata':metadata(name),'spec':{'replicas':1,'template':{'metadata':{'labels':copy.deepcopy(labels)},'spec':{'containers':containers}}}})
    actual=copy.deepcopy(rendered)
    for obj in actual:
        obj['metadata'].update(uid='uid-'+obj['metadata']['name'],resourceVersion='10')
    pods=[]
    for parent in actual[1:]:
        pod={'apiVersion':'v1','kind':'Pod','metadata':metadata(parent['metadata']['name']+'-0'),'spec':copy.deepcopy(parent['spec']['template']['spec'])}
        pod['metadata'].update(uid='uid-'+pod['metadata']['name'],resourceVersion='11',ownerReferences=[{'kind':'StatefulSet','name':parent['metadata']['name'],'uid':parent['metadata']['uid'],'controller':True}])
        pod['spec']['nodeName']='synthetic-node'
        pod['status']={'phase':'Running','conditions':[{'type':'Ready','status':'True'}],
                       'containerStatuses':[{'name':r['name'],'containerID':'containerd://'+r['name'],'imageID':'containerd://sha256:'+('8' if r['name']!='postgres' else '9')*64,'restartCount':0,'ready':True,'state':{'running':{'startedAt':'2026-11-17T00:00:00Z'}}} for r in pod['spec']['containers']]}
        pods.append(pod)
    class Replies:
        def __init__(self):
            self.objects={k.key(x):x for x in copy.deepcopy(actual)}
            self.pods=copy.deepcopy(pods)
            self.calls=[]
        def get(self,kind,name=None,cleanup=False):
            self.calls.append((kind,name))
            if kind=='namespace':return copy.deepcopy(self.objects['Namespace/'+name])
            if kind=='replicasets':return {'items':[]}
            if kind=='pods':return {'items':copy.deepcopy(self.pods)}
            return copy.deepcopy(self.objects[kind+'/'+name])
    return c,inv,rendered,Replies()


class Adapter(unittest.TestCase):
    def setUp(self):
        self.c,self.inv,self.render,self.client=fixture()
        self.objects=k.validate(self.c,self.inv,self.render)

    def green(self):
        return k.observe(self.c,self.objects,self.client)

    def red_restored(self,code,mutate,criterion):
        criterion()
        undo=mutate()
        with self.assertRaisesRegex(Exception,code):criterion()
        undo()
        criterion()
        print('RED_RESTORED',code)

    def test_source_image_binding_and_cohort_controls(self):
        for field,code in [('sourceCommit','K8S_SOURCE_CHANGED'),('imageDeployCommit','K8S_SOURCE_CHANGED'),('bindingIdentity','K8S_BINDING_CHANGED')]:
            def mutate(field=field):
                old=self.inv[field];self.inv[field]='a'*40
                return lambda:self.inv.update({field:old})
            self.red_restored(code,mutate,lambda:k.validate(self.c,self.inv,self.render))
        old=self.render[1]['spec']['template']['spec']['containers'][0]['image']
        def image():
            self.render[1]['spec']['template']['spec']['containers'][0]['image']='foreign@sha256:'+'0'*64
            return lambda:self.render[1]['spec']['template']['spec']['containers'][0].update(image=old)
        self.red_restored('K8S_IMAGE_CHANGED',image,lambda:k.validate(self.c,self.inv,self.render))
        self.render[1]['spec']['replicas']=2
        with self.assertRaisesRegex(k.Refused,'ONE_COHORT_REPLICA'):k.validate(self.c,self.inv,self.render)
        self.render[1]['spec']['replicas']=1
        k.validate(self.c,self.inv,self.render)

    def test_namespace_pod_uid_actual_image_and_lost_observation_controls(self):
        baseline=self.green()
        criterion=lambda:k.observe(self.c,self.objects,self.client,baseline)
        for target,field,value,code in [(self.client.objects['Namespace/'+self.c['namespace']]['metadata'],'uid','peer-uid','K8S_NAMESPACE_UID_CHANGED'),
          (self.client.pods[0]['metadata'],'namespace','peer-namespace','K8S_FOREIGN_NAMESPACE'),
          (self.client.pods[0]['metadata'],'uid','peer-pod-uid','K8S_POD_UID_CHANGED'),
          (self.client.pods[0]['status']['containerStatuses'][0],'imageID','foreign-runtime-image','K8S_ACTUAL_IMAGE_CHANGED')]:
            def mutate(target=target,field=field,value=value):
                old=target[field];target[field]=value
                return lambda:target.update({field:old})
            self.red_restored(code,mutate,criterion)
        with patch.object(self.client,'get',side_effect=k.Refused('K8S_OBSERVATION_LOST','UNMEASURED')):
            with self.assertRaisesRegex(k.Refused,'OBSERVATION_LOST'):criterion()
        criterion()

    def test_context_change_and_deadline_refuse_before_child(self):
        baseline=self.green()
        self.c['context']='foreign-context'
        with self.assertRaisesRegex(k.Refused,'SOURCE_IMAGE_BINDING_CHANGED'):k.observe(self.c,self.objects,self.client,baseline)
        self.c['context']='synthetic-context'
        k.observe(self.c,self.objects,self.client,baseline)
        native=lambda *a,**kw:self.fail('deadline must refuse before child')
        with patch.object(k.time,'time',return_value=k.timestamp(self.c['deadlines']['workUntil'])+1):
            with self.assertRaisesRegex(k.Refused,'WORK_DEADLINE'):k.Client(self.c,native).get('pods')
        k.deadline(self.c)
        after_work=k.timestamp(self.c['deadlines']['workUntil'])+1
        with self.assertRaisesRegex(k.Refused,'WORK_DEADLINE'):k.validate(self.c,self.inv,self.render,now=after_work)
        k.validate(self.c,self.inv,self.render,now=after_work,cleanup=True)
        with self.assertRaisesRegex(k.Refused,'CLEANUP_DEADLINE'):
            k.validate(self.c,self.inv,self.render,now=k.timestamp(self.c['deadlines']['cleanupUntil'])+1,cleanup=True)

    def test_process_boundary_preserves_explicit_context_and_guard(self):
        def native(argv,**kw):
            self.assertEqual(argv[:3],[self.c['readonlyGuard'],'kubectl','--context'])
            self.assertIn(self.c['context'],argv);self.assertIn(self.c['namespace'],argv)
            self.assertEqual(kw['env']['RO_ALLOW_SENSITIVE'],'1')
            return SimpleNamespace(returncode=0,stdout=b'{"items":[]}')
        with tempfile.TemporaryDirectory() as name:
            binary=Path(name)/'kubectl';binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o700);self.c['kubectl']=str(binary)
            self.assertEqual(k.Client(self.c,native).get('pods'),{'items':[]})
            for reply in [SimpleNamespace(returncode=1,stdout=b'not absence'),SimpleNamespace(returncode=0,stdout=b'')]:
                with self.assertRaisesRegex(k.Refused,'OBSERVATION_LOST'):k.Client(self.c,lambda *a,**kw:reply).get('pods')
            binary.unlink()
            with self.assertRaisesRegex(k.Refused,'PINNED_KUBECTL_REQUIRED'):k.Client(self.c,native).get('pods')

    def test_peer_cleanup_refuses_and_exact_plan_has_uid_preconditions(self):
        baseline=self.green();current=self.green()
        plan=k.cleanup_plan(self.c,baseline,current)
        self.assertEqual(len(plan['actions']),2)
        self.assertEqual(plan['namespaceDeletion'],'NOT_INCLUDED')
        self.assertTrue(all(a['stdin']['preconditions']['uid'] and '--raw' in a['argv'] and '--all' not in a['argv'] for a in plan['actions']))
        current['objects']['StatefulSet/cohort']['uid']='peer-uid'
        with self.assertRaisesRegex(k.Refused,'PEER_CLEANUP_REFUSED'):k.cleanup_plan(self.c,baseline,current)
        current=self.green();k.cleanup_plan(self.c,baseline,current)
        self.client.pods[0]['metadata']['labels'][self.c['ownerLabel']]='peer'
        with self.assertRaisesRegex(k.Refused,'PEER_RESOURCE_REFUSED'):self.green()
        self.client.pods[0]['metadata']['labels'][self.c['ownerLabel']]=self.c['runId'];self.green()

    def test_observed_container_restart_is_not_pod_or_image_replacement(self):
        initial=self.green();changed=self.client.pods[0]['status']['containerStatuses'][2]
        changed.update(containerID='containerd://new-evaluator',restartCount=1)
        value=k.observe(self.c,self.objects,self.client,initial,restarted_role='evaluator')
        self.assertEqual(value['pods']['cohort-0']['containers']['evaluator']['restartCount'],1)
        with self.assertRaisesRegex(k.Refused,'CONTAINER_INCARNATION_CHANGED'):k.observe(self.c,self.objects,self.client,initial)
        ordinary = k.observe(self.c, self.objects, self.client, initial, measure_actors=True)
        self.assertEqual([(row['container'], row['current']['restartCount'])
                          for row in ordinary['actorTransitions']], [('evaluator', 1)])
        self.client.pods[0]['metadata']['labels'][self.c['ownerLabel']] = 'peer'
        with self.assertRaisesRegex(k.Refused, 'PEER_RESOURCE_REFUSED'):
            k.observe(self.c, self.objects, self.client, initial, measure_actors=True)
        self.client.pods[0]['metadata']['labels'][self.c['ownerLabel']] = self.c['runId']
        changed.update(containerID='containerd://evaluator',restartCount=0)
        self.green()

    def test_pod_budget_changes_by_kubernetes_are_recorded_not_refused(self):
        spec = self.client.pods[0]['spec']
        for name, change in [('overhead', {'cpu': '100m'}), ('resources', {'limits': {'cpu': '1'}})]:
            spec[name] = change
            observed = self.green()['pods']['cohort-0']['observedResources']
            self.assertEqual(observed['overhead' if name == 'overhead' else 'podResources'], change)
            del spec[name]
            self.green()

    def primer_pod(self):
        job = copy.deepcopy(self.objects['StatefulSet/postgres'])
        job.update(kind='Job', apiVersion='batch/v1')
        job['metadata'].update(name='primer', uid='job-id', resourceVersion='4')
        job['spec']['template']['spec']['containers'][0]['name'] = 'done'
        self.objects['Job/primer'] = job
        self.client.objects['Job/primer'] = copy.deepcopy(job)
        pod = copy.deepcopy(self.client.pods[-1])
        pod['spec']['containers'][0]['name'] = 'done'
        pod['status']['containerStatuses'][0].update(name='done', containerID='containerd://done')
        pod['metadata'].update(name='primer-old', uid='primer-pod-id',
                               ownerReferences=[{'kind':'Job','name':'primer','uid':'job-id','controller':True}])
        self.client.pods.append(pod)
        return self.client.objects['Job/primer'], pod

    def test_retired_job_only_allows_independent_stored_seed_observation(self):
        job, pod = self.primer_pod()
        baseline = self.green()
        self.client.pods.pop()
        with self.assertRaisesRegex(k.Refused, 'POD_ROSTER_CHANGED'):
            k.observe(self.c, self.objects, self.client, baseline)
        def inspect():
            return k.observe(self.c, self.objects, self.client, baseline, serving_sql=True)
        with self.assertRaisesRegex(k.Refused, 'POD_RETIREMENT_UNPROVEN'):
            inspect()
        terminal = {'type': 'Failed', 'status': 'True', 'reason': 'DeadlineExceeded',
                    'lastTransitionTime': iso(time.time())}
        job = self.client.objects['Job/primer']
        job['status'] = {'conditions': [terminal], 'failed': 1}
        value = inspect()['retiredJobs']['primer-old']
        self.assertEqual((value['podUid'], value['jobUid'], value['condition'], value['reason']),
                         ('primer-pod-id', 'job-id', 'Failed', 'DeadlineExceeded'))
        self.assertEqual(value['containers']['done']['lastObservedExitCode'], 'UNMEASURED')
        with tempfile.TemporaryDirectory() as name:
            d = Path(name)
            k.write(d/'run.json', self.c)
            k.write(d/'observation.initial.json', baseline)
            def call(argv, **kw):
                self.assertIn('BEGIN READ ONLY;', kw['data'].decode())
                self.assertIn('synthetic-compose-demo', kw['data'].decode())
                return b'1\t1\tnightscout_compose_test\tt\t0\t0\n'
            self.client.call = call
            observed = k.observe_sql(d, self.c, self.objects, d/'independent', self.client)
            self.assertEqual(observed['storedTenants'], 0)
            self.assertEqual(observed['dataCredentials'], 'UNMEASURED')
            self.assertEqual(observed['setupJobs']['Job/primer']['condition'], 'Failed')
            self.assertEqual(k.document(d/'independent/after.json')['retiredJobs']['primer-old'], value)
            # Redispatching an ordinary SQL operation still uses the full baseline.
            with self.assertRaisesRegex(k.Refused, 'POD_ROSTER_CHANGED'):
                k.sql(d, self.c, self.objects, 'SELECT 1;', self.client)
        for field, change in [('condition', 'FailureTarget'), ('reason', 'UnknownFailure'),
                              ('active', 1), ('jobUid', 'replacement-job'), ('podUid', 'other-serving-pod')]:
            target, key, code = {
                'condition': (terminal, 'type', 'POD_RETIREMENT_UNPROVEN'),
                'reason': (terminal, 'reason', 'POD_RETIREMENT_UNPROVEN'),
                'active': (job['status'], 'active', 'POD_RETIREMENT_UNPROVEN'),
                'jobUid': (job['metadata'], 'uid', 'RESOURCE_UID_CHANGED'),
                'podUid': (self.client.pods[0]['metadata'], 'uid', 'POD_UID_CHANGED')}[field]
            old = target.get(key)
            target[key] = change
            with self.assertRaisesRegex(k.Refused, code):
                inspect()
            if old is None:
                del target[key]
            else:
                target[key] = old
            inspect()
        terminal.update(type='Complete', reason='CompletionsReached')
        job['status'].update(failed=0, succeeded=1)
        self.assertEqual(inspect()['retiredJobs']['primer-old']['condition'], 'Complete')
        self.client.pods.append(pod)
        k.observe(self.c, self.objects, self.client, baseline)

    def test_exported_primer_can_finish_and_retire_across_load_and_recovery(self):
        import matrix
        job, pod = self.primer_pod()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            output = d/'primer'
            output.mkdir()
            roster = output/'tenants.json'
            self.c.update(primerOutput=str(output), tenantsFile=str(roster), tenants=2)
            k.write(d/'run.json', self.c)
            initial = self.green()
            k.write(d/'observation.initial.json', initial)
            k.write(roster, [{'id': id, 'host': host, 'token':'synthetic'} for id,host in ((A,'a.test'),(B,'b.test'))])
            receipt = dict(verdict='OBSERVED', runSha256=k.digest(d/'run.json'), namespaceUid=initial['namespace']['uid'],
                           jobUid='job-id', podUid='primer-pod-id', containerId='containerd://done',
                           sourceResult={'state':'synthetic-data-primed','tenants':2},dataTenants=2,rosterSha256=k.digest(roster))
            k.write(output/'result.json', receipt)
            job['status'] = {'conditions':[{'status':'True','type':'Complete','reason':'CompletionsReached',
                                           'lastTransitionTime':iso(time.time())}],'succeeded':1}
            pod['status'].update(phase='Succeeded', conditions=[])
            pod['status']['containerStatuses'][0].update(ready=False,state={'terminated':{'exitCode':0}})
            def observe(baseline=initial):
                point = k.observe(self.c, self.objects, self.client, baseline)
                matrix.identity(self.c, baseline, point)
                return point
            # The kubelet may publish the clean exit ahead of the Job controller.
            with patch.dict(job['status'], {'conditions':[]}):
                present = observe()
                with patch.dict(pod['status']['containerStatuses'][0], {'state':{'terminated':{'exitCode':1}}}):
                    with self.assertRaisesRegex(k.Refused,'PRIMER_POD_EXIT'):
                        observe()
            self.client.pods.pop()
            # The Pod may disappear between the first Job GET and the Pod LIST.
            original_get = self.client.get
            reads = []
            def delayed_condition(kind,name=None,cleanup=False,*,replacement=False):
                reply = original_get(kind,name,cleanup)
                if kind == 'Job' and name == 'primer':
                    reads.append(kind)
                    if len(reads) == 1:
                        reply['status'] = {'active':1}
                    elif replacement:
                        reply['metadata']['uid'] = 'other-job'
                return reply
            with patch.object(self.client,'get',side_effect=delayed_condition):
                retired = observe(present)
            self.assertEqual(len(reads),2)
            reads.clear()
            with patch.object(self.client,'get',side_effect=lambda *args,**kw: delayed_condition(*args,**kw,replacement=True)):
                with self.assertRaisesRegex(k.Refused,'RESOURCE_UID_CHANGED'):
                    observe(present)
            self.assertEqual(len(reads),2)
            self.assertEqual(retired['completedPrimer']['uid'], 'primer-pod-id')
            self.assertNotIn('primer-old',retired['pods'])
            self.assertEqual(matrix.node_requests(self.objects,retired,'limits-v1'),matrix.node_requests(self.objects,initial,'limits-v1'))
            k.write(d/'restart.json',{'status':'OBSERVED','before':initial,'after':retired})
            self.assertEqual(len(execute.roster(self.c)),2)
            observe(k.active_baseline(d))
            with patch.dict(job['status'], {'conditions':[]}):
                with self.assertRaisesRegex(k.Refused,'POD_RETIREMENT_UNPROVEN'):
                    observe(retired)
            k.write(output/'result.json', dict(receipt, podUid='replacement'))
            with self.assertRaisesRegex(k.Refused, 'PRIMER_ROSTER_CHANGED'):
                observe()
            k.write(output/'result.json',receipt)
            with patch.dict(self.client.pods[0]['metadata'], {'uid':'replacement'}):
                with self.assertRaisesRegex(k.Refused,'POD_UID_CHANGED'):
                    observe()
            observe()

    def test_actual_sql_transport_and_readonly_transaction(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name);k.write(d/'observation.initial.json',self.green())
            def call(argv,**kw):
                self.assertEqual(argv[:4],['exec','-i','postgres-0','-c'])
                self.assertIn('ON_ERROR_STOP=1',argv)
                self.assertEqual(kw['data'],b'BEGIN READ ONLY;\nSELECT 1;\nROLLBACK;\n')
                self.assertFalse(kw['read'])
                return b'1\n'
            self.client.call=call
            self.assertEqual(k.sql(d,self.c,self.objects,'SELECT 1;',self.client),'1\n')
            with self.assertRaisesRegex(k.Refused,'SQL_READ_ONLY'):k.sql(d,self.c,self.objects,'DELETE FROM synthetic;',self.client)

    def test_generated_probe_and_workload_actual_callbacks(self):
        with tempfile.TemporaryDirectory() as name:
            target=Path(name)/'probe.cjs';metadata=k.generate_probe(target)
            self.assertEqual(metadata['kubernetesSha256'],k.digest(target))
            subprocess.run(['node','--check',str(target)],check=True,capture_output=True)
            value=subprocess.run(['node',str(k.M7/'probe-accounting-control.cjs'),str(target)],capture_output=True,text=True,timeout=5)
            self.assertEqual(value.returncode,0,value.stderr)
            self.assertEqual(json.loads(value.stdout)['statuses'],[503,0,200,403])
            source=target.read_text();self.assertNotIn("execFile('docker'",source)
            self.assertIn('rawRow:e.rawRow',source)
            native=subprocess.run(['node',str(HERE/'probe.test.cjs'),str(target)],capture_output=True,text=True,timeout=15)
            self.assertEqual(native.returncode,0,native.stderr)
            for mode in ('sql-unavailable', 'restored', 'warm'):
                result = subprocess.run(['node', str(HERE/'probe.test.cjs'), str(target), mode],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
            work=Path(name)/'workload.js';record=k.workload.generate(k.ROOT,work)
            self.assertEqual(record['adaptedSha256'],k.digest(work))

    def test_native_finite_process_control_and_restore(self):
        self.assertEqual(execute.finite(self.c,[sys.executable,'-c',"print('green')"],seconds=2).strip(),b'green')
        start=time.monotonic()
        with self.assertRaisesRegex(k.Refused,'NATIVE_PROCESS_FAILED'):
            execute.finite(self.c,[sys.executable,'-c','import time; time.sleep(5)'],seconds=.08)
        self.assertLess(time.monotonic()-start,2)
        self.assertEqual(execute.finite(self.c,[sys.executable,'-c',"print('restored')"],seconds=2).strip(),b'restored')

    def test_actual_actor_scope_missing_unbounded_excessive_and_restore(self):
        limits={'cpu.max':'100000 100000','memory.max':'1073741824','memory.swap.max':'0'}
        criterion=lambda:execute.finite_scope(self.c,limits)
        criterion()
        for field,value,code in [('cpu.max','max 100000','FINITE_ACTOR_SCOPE_REQUIRED'),('memory.max','UNMEASURED','FINITE_ACTOR_SCOPE_REQUIRED'),('memory.swap.max','max','FINITE_ACTOR_SCOPE_REQUIRED'),('cpu.max','200000 100000','ACTOR_SCOPE_EXCEEDS_BUDGET')]:
            old=limits[field];limits[field]=value
            with self.assertRaisesRegex(k.Refused,code):criterion()
            limits[field]=old;criterion()

    def test_private_admin_policy_allowed_refused_allowed_control(self):
        observations=[{'outcome':'connected'},{'outcome':'timeout'},{'outcome':'connected'}]
        criterion=lambda:execute.policy_assess(observations)
        self.assertEqual(criterion()['verdict'],'PASS')
        observations[1]['outcome']='connected'
        with self.assertRaisesRegex(k.Refused,'OPERATOR_PLANE_EXPOSED'):criterion()
        observations[1]['outcome']='timeout';criterion()
        observations[0]['outcome']='error'
        with self.assertRaisesRegex(k.Refused,'POLICY_POSITIVE_CONTROL_UNMEASURED'):criterion()
        observations[0]['outcome']='connected';criterion()
        observations[1]['outcome']='error'
        with self.assertRaisesRegex(k.Refused,'POLICY_REFUSAL_UNMEASURED'):criterion()
        observations[1]['outcome']='timeout';criterion()

    def test_private_admin_policy_uses_waiting_primer_and_exact_api_container(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name);initial=self.green();k.write(d/'observation.initial.json',initial)
            before=copy.deepcopy(initial)
            before['objects']['Service/admin']={'uid':'uid-admin-service'}
            before['pods']['primer-synthetic']={'name':'primer-synthetic','workload':'Job/primer','uid':'uid-primer','containers':{'done':{'ready':True,'containerID':'containerd://primer'}}}
            cases=iter(('connected','timeout','connected'));calls=[]
            def native(args,**kw):
                calls.append(args)
                self.assertFalse(kw['read'])
                self.assertIn("host:'admin',port:1342",args[-1])
                return json.dumps({'outcome':next(cases)}).encode()
            self.client.call=native
            with patch.object(k,'observe',return_value=before):
                value=execute.policy(d,self.c,self.objects,self.client)
            self.assertEqual(value['verdict'],'PASS')
            self.assertEqual([(a[1],a[3]) for a in calls],[('primer-synthetic','done'),('cohort-0','api'),('primer-synthetic','done')])
            self.assertEqual(value['adminServiceUid'],'uid-admin-service')
            (d/'policy.json').unlink();before['pods']['primer-synthetic']['containers']['done']['ready']=False
            with patch.object(k,'observe',return_value=before):
                with self.assertRaisesRegex(k.Refused,'POLICY_PRIMER_WAITING_REQUIRED'):execute.policy(d,self.c,self.objects,self.client)

    def test_missing_accepted_writes_and_stored_loss_control(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);out=root/'load';out.mkdir();(out/'runid').write_text('synthetic-probe')
            tenants=root/'tenants.json';k.write(tenants,[{'id':A,'host':'a.example.test','token':'synthetic-a'},{'id':B,'host':'b.example.test','token':'synthetic-b'}])
            c={**self.c,'tenants':2,'tenantsFile':str(tenants)}
            metrics={'writes_ok':{'count':2},**{'writes_ok{kind:'+kind+'}':{'count':int(kind=='entries')*2} for kind in ('entries','devicestatus','treatments')},**{key+'{tenant:'+t+'}':{'count':int(key=='writes_ok')} for t in (A,B) for key in ('writes_ok','writes_uncertain')}}
            ledger={'version':2,'kind':'m7-discovery-probe-accounting','runId':'synthetic-probe','roster':[A,B],'admissionsClosed':True,'attempts':2,'byTenant':{t:{'attempts':1,'accepted':1,'uncertain':0,'refused':0,'pending':0} for t in (A,B)}}
            k.write(out/'probe-accounting.json',ledger)
            k.write(out/'fanout.json',{'probeWrites':{'byTenant':{A:1,B:1}}})
            k.write(out/'k6-summary.json',{'metrics':metrics})
            values={t:{'entries':1,'probe':1} for t in (A,B)}
            criterion=lambda:execute.accepted_writes(out,c,values)
            self.assertEqual(criterion()['verdict'],'GREEN')
            changed=copy.deepcopy(metrics);del changed['writes_ok{tenant:'+A+'}'];k.write(out/'k6-summary.json',{'metrics':changed})
            with self.assertRaisesRegex(k.Refused,'ACCEPTED_WRITE_UNMEASURED'):criterion()
            k.write(out/'k6-summary.json',{'metrics':metrics});criterion()
            changed=copy.deepcopy(metrics);changed['writes_uncertain{tenant:'+A+'}']['count']=1
            k.write(out/'k6-summary.json',{'metrics':changed})
            with self.assertRaisesRegex(k.Refused,'WORKLOAD_WRITE_UNCERTAIN'):criterion()
            k.write(out/'k6-summary.json',{'metrics':metrics});criterion()
            print('RED_RESTORED K8S_WORKLOAD_WRITE_UNCERTAIN')
            values[A]['entries']=0
            with self.assertRaisesRegex(RuntimeError,'M7_DISCOVERY_WRONG_DATA'):criterion()
            values[A]['entries']=1;criterion()
            (out/'probe-accounting.json').unlink()
            with self.assertRaisesRegex(k.Refused,'ACCEPTED_WRITE_UNMEASURED'):criterion()
            k.write(out/'probe-accounting.json',ledger);criterion()

    def test_subset_storage_in_stage_and_retained_report(self):
        from workloads.reduce import reduce_stage
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            out = root / 'load'
            out.mkdir()
            run_id = 'synthetic-subset'
            (out / 'runid').write_text(run_id)
            # The first roster entry drives ordinary load even when IDs sort differently.
            roster = [{'id': tenant, 'host':'fixture.test', 'token':'synthetic'} for tenant in (B, A)]
            k.write(root / 'tenants.json', roster)
            config = {'tenantsFile':str(root / 'tenants.json'), 'tenants':2, 'ordinaryRosterTenants':1}
            k.write(root / 'run.json', config)
            metrics = {'writes_ok':{'count':1}, 'writes_ok{kind:entries}':{'count':1},
                       'writes_ok{kind:devicestatus}':{'count':0}, 'writes_ok{kind:treatments}':{'count':0},
                       f'writes_ok{{tenant:{B}}}':{'count':1}, f'writes_uncertain{{tenant:{B}}}':{'count':0}}
            ledger = {'version':2, 'kind':'m7-discovery-probe-accounting', 'runId':run_id, 'roster':[B,A],
                      'admissionsClosed':True, 'attempts':1,
                      'byTenant':{A:{'attempts':1,'accepted':1,'uncertain':0,'refused':0,'pending':0}}}
            k.write(out / 'probe-accounting.json', ledger)
            values = {A:{'probe':1}, B:{'entries':1}}

            def report(case):
                k.write(out / 'k6-summary.json', {'metrics':metrics})
                k.write(out / 'stored-counts.json', values)
                return reduce_stage(out, root / case)['stored']

            self.assertEqual(report('full-read')['verdict'], 'PASS')
            counts = execute.accepted_writes(out, config, values)
            self.assertEqual([(row['tenant'], row['ordinarySelected']) for row in counts['rows']], [(A,False), (B,True)])
            del metrics[f'writes_uncertain{{tenant:{B}}}']
            self.assertEqual(report('missing-selected')['verdict'], 'UNMEASURED')
            with self.assertRaisesRegex(k.Refused, 'ACCEPTED_WRITE_UNMEASURED'):
                execute.accepted_writes(out, config, values)
            values[A]['entries'] = values[B].pop('entries')
            self.assertEqual(report('misplaced')['verdict'], 'FAIL')
            with self.assertRaisesRegex(RuntimeError, 'M7_DISCOVERY_WRONG_DATA') as error:
                execute.accepted_writes(out, config, values)
            self.assertIn({'kind':'unselected-workload-write', 'tenant':A}, error.exception.oracleFindings['failures'])
            values[B]['entries'] = values[A].pop('entries')
            metrics[f'writes_uncertain{{tenant:{B}}}'] = {'count':0}
            metrics['writes_uncertain'] = {'count':1}
            self.assertEqual(report('unattributed-uncertainty')['verdict'], 'FAIL')
            metrics['writes_uncertain'] = {'count':0}
            self.assertEqual(report('restored')['verdict'], 'PASS')
            self.assertEqual(execute.accepted_writes(out, config, values)['verdict'], 'GREEN')

    def test_matrix_collision_headroom_and_restore(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name)
            configs=[]
            for i in range(2):
                c=copy.deepcopy(self.c);c.update(namespace='synthetic-'+str(i),runId='synthetic-'+str(i),baseUrl='http://127.0.0.1:'+str(18080+i),workload={'loadSeconds':30,'offeredRps':1,'logicalPollingClients':4,'probeEveryMs':300000})
                configs.append((d/str(i),c,self.objects))
            def load(path):return configs[int(path)]
            value={'version':1,'fixtures':['0','1'],'aggregateCeiling':{'millicpus':10000,'memoryBytes':10*1024**3,'ephemeralBytes':10*1024**3}}
            with patch.object(k,'load',side_effect=load):
                self.assertEqual(execute.matrix_plan(value)['status'],'PLANNED_ONLY')
                value['aggregateCeiling']['millicpus']=1
                with self.assertRaisesRegex(k.Refused,'AGGREGATE_HEADROOM_EXCEEDED'):execute.matrix_plan(value)
                value['aggregateCeiling']['millicpus']=10000;execute.matrix_plan(value)
                configs[1][1]['namespace']=configs[0][1]['namespace']
                with self.assertRaisesRegex(k.Refused,'FIXTURE_FANOUT_COLLISION'):execute.matrix_plan(value)
                configs[1][1]['namespace']='synthetic-1';execute.matrix_plan(value)

    def test_projection_permits_only_default_service_account_admission(self):
        spec=self.render[1]['spec']['template']['spec'];actual=copy.deepcopy(spec)
        actual['volumes']=[{'name':'kube-api-access-synthetic','projected':{'sources':[{'serviceAccountToken':{'path':'token'}}]}}]
        visible,admitted=k.admission_projection(spec,actual)
        self.assertEqual(admitted,['kube-api-access-synthetic'])
        self.assertTrue(k.subset(spec,visible))
        actual['volumes'][0]['name']='peer-secret-volume'
        with self.assertRaisesRegex(k.Refused,'UNEXPECTED_ADMISSION_VOLUME'):k.admission_projection(spec,actual)

    def test_prepared_inventory_and_render_bytes_cannot_change(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);render=root/'render.json';inventory=root/'inventory.json';config=root/'run.json'
            k.write(render,self.render);k.write(inventory,self.inv)
            c=copy.deepcopy(self.c);c['pins'].update(renderSha256=k.digest(render),inventorySha256=k.digest(inventory),instrument=k.instrument()['sha256'])
            k.write(config,c);out=root/'packet';k.prepare(config,inventory,render,out);k.load(out)
            for file,code in [('render.json','RENDER_CHANGED'),('inventory.json','INVENTORY_CHANGED')]:
                target=out/file;raw=target.read_bytes();target.write_bytes(raw+b'\n')
                with self.assertRaisesRegex(k.Refused,code):k.load(out)
                target.write_bytes(raw);k.load(out)

    def test_guard_masking_is_retained_at_each_exact_object_and_pod(self):
        env=[{'name':'SYNTHETIC_SECRET_FILE','value':'/run/synthetic/reference'}]
        self.render[1]['spec']['template']['spec']['containers'][0]['env']=copy.deepcopy(env)
        masked=[{'name':'SYNTHETIC_SECRET_FILE','value':'<redacted>'}]
        self.client.objects['StatefulSet/cohort']['spec']['template']['spec']['containers'][0]['env']=copy.deepcopy(masked)
        self.client.pods[0]['spec']['containers'][0]['env']=copy.deepcopy(masked)
        value=self.green()
        self.assertEqual(value['objects']['StatefulSet/cohort']['maskedPaths'],['/spec/template/spec/containers/0/env/0/value'])
        self.assertEqual(value['objects']['StatefulSet/postgres']['maskedPaths'],[])
        self.assertEqual(value['pods']['cohort-0']['maskedPaths'],['/containers/0/env/0/value'])
        self.assertEqual(value['pods']['postgres-0']['maskedPaths'],[])


class NativeDriverRecord(unittest.TestCase):
    def test_driver_tools_and_dependencies_are_recorded_not_pinned(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as area:
            root = Path(area); deps = root / 'deps'; (deps / 'node_modules').mkdir(parents=True)
            (deps / 'package.json').write_text('{}'); (deps / 'package-lock.json').write_text('{}')
            node = root / 'node'; node.write_text('synthetic')
            driver = {'hostId': 'h', 'node': str(node), 'nodeSha256': '0'*64, 'dependencies': str(deps),
                      'coreRepository': '/nonexistent', 'packageSha256': '0'*64, 'lockSha256': '0'*64,
                      'nodeModules': 'captured', 'resources': {}}
            c = {'driver': driver, 'observer': {'hostId': 'h'}, 'pins': {'pair': {'core': 'a'*40}}}
            with patch.object(execute.k.dependency_reuse, 'tree', return_value='changed'), \
                 patch.object(execute, 'finite_scope', return_value='scope'):
                value = execute.actor(c)
            self.assertFalse(value['matchesCapture'])
            self.assertEqual(value['observedTools']['nodeSha256'], execute.k.digest(node))
            self.assertEqual(value['nodeModules'], 'changed')
            driver['node'] = 'relative'
            with patch.object(execute.k.dependency_reuse, 'tree', return_value='changed'), \
                 patch.object(execute, 'finite_scope', return_value='scope'):
                with self.assertRaisesRegex(execute.k.Refused, 'DRIVER_TOOL_PATH'):
                    execute.actor(c)


if __name__=='__main__':
    unittest.main()
