"""Opt-in execution boundary: declaration/census, budget and exact writer stop."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import kube_adapter as k
import execute
import matrix
import native_join as j
import native_load as n
import native_files as f
from test_application_topology import separate_fixture
from test_native_files import configured


def fixture():
    c,inventory,render,client=separate_fixture()
    selected,base,options=configured()
    c.update(tenants=2,workload=selected['workload'],tier='discovery')
    c['namespace']='ns-synth-native-join'
    for obj in render:
        if obj['kind']=='Namespace':obj['metadata']['name']=c['namespace']
        else:obj['metadata']['namespace']=c['namespace']
    client.objects={}
    for obj in render:
        value=copy.deepcopy(obj);value['metadata'].update(uid='uid-'+value['metadata']['name'],resourceVersion='10')
        client.objects[k.key(obj)]=value
    for pod in client.pods:pod['metadata']['namespace']=c['namespace']
    for replica in client.replicas:replica['metadata']['namespace']=c['namespace']
    c[j.FIELD]={'version':1,'mode':'job-v1','image':options['shell_contract']['image'],
        'shellContract':options['shell_contract'],'resources':base['spec']['template']['spec']['containers'][0]['resources'],
        'exporterResources':options['exporter_resources'],'nodeName':'synthetic-node','deadlineSeconds':30,'imagePullSecrets':[]}
    inventory[j.FIELD]=copy.deepcopy(c[j.FIELD])
    extras=j.declarations(c)
    quota={'apiVersion':'v1','kind':'ResourceQuota','metadata':{'name':'run-quota','namespace':c['namespace'],
        'labels':{c['ownerLabel']:c['runId']}},'spec':{'hard':{'requests.cpu':'20','requests.memory':'20Gi','pods':'100'}}}
    render+=extras+[quota]
    for obj in extras+[quota]:
        value=copy.deepcopy(obj);value['metadata'].update(uid='uid-'+value['metadata']['name'],resourceVersion='10')
        client.objects[k.key(obj)]=value
    return c,inventory,render,client


class NativeJoin(unittest.TestCase):
    def test_guarded_native_spec_uses_owned_exact_read_then_rejects_changed_references(self):
        c, inventory, render, client = fixture()
        objects = k.validate(c, inventory, render)
        original_get = client.get
        direct = []
        def mask(value):
            value = copy.deepcopy(value)
            spec = value.get('spec', {})
            if value.get('kind') == 'Job':
                spec = spec['template']['spec']
            for volume in spec.get('volumes', []):
                if 'secret' in volume:
                    volume['secret']['secretName'] = '<redacted>'
                for source in volume.get('projected', {}).get('sources', []):
                    for item in source.get('configMap', {}).get('items', []):
                        item['key'] = '<redacted>'
            return value
        def guarded(kind, name=None, cleanup=False):
            value = original_get(kind, name, cleanup)
            if kind == 'Job' and name == 'k6':
                return mask(value)
            if kind == 'pods':
                return dict(value, items=[mask(p) if p['metadata']['name']=='k6-owned' else p for p in value['items']])
            return value
        def private(args, **kw):
            self.assertFalse(kw['read']); self.assertEqual(kw['output_limit'], 512*1024)
            self.assertIn(args[:3], [['get','Job','k6'], ['get','Pod','k6-owned']])
            direct.append(args)
            value = client.objects[j.JOB] if args[1]=='Job' else client.pods[-1]
            return json.dumps(value).encode()
        client.get = guarded; client.call = private
        # Disabling the exact read reproduces the masked-reference refusal.
        with patch.object(j, 'exact_spec', side_effect=lambda _c,_client,obj,*_,**__:obj):
            with self.assertRaisesRegex(k.Refused, 'NATIVE_LOAD_JOB_CHANGED'):
                k.observe(c, objects, client)
        baseline = k.observe(c, objects, client)
        job = client.objects[j.JOB]
        pod = {'apiVersion':'v1','kind':'Pod','metadata':{'name':'k6-owned','namespace':c['namespace'],
               'uid':'pod-owned','resourceVersion':'12','labels':copy.deepcopy(job['spec']['template']['metadata']['labels']),
               'ownerReferences':[{'kind':'Job','name':'k6','uid':job['metadata']['uid'],'controller':True}]},
               'spec':copy.deepcopy(job['spec']['template']['spec']),'status':{'phase':'Pending'}}
        client.pods.append(pod)
        k.observe(c, objects, client, baseline)
        self.assertTrue(any(args[1]=='Pod' for args in direct))
        # The transport adapter must supply the same exact specs to native_load
        # and native_files, rather than accepting the guard's masked references.
        def guarded_call(args, **kw):
            if kw.get('read') is False:
                return private(args, **kw)
            kind = args[1]; name = args[2] if kind in ('namespace','job') else None
            return json.dumps(guarded('Job' if kind=='job' else kind, name)).encode()
        client.call = guarded_call
        transport = j.Kube(c, client)
        self.assertEqual(transport.json(['get','job','k6'])['spec'], job['spec'])
        self.assertEqual(transport.json(['get','pods','-l','job-name=k6'])['items'][-1]['spec'], pod['spec'])
        for target in (job['spec']['template']['spec'], pod['spec']):
            secret = target['volumes'][0]['secret']
            old = secret['secretName']; secret['secretName'] = 'wrong-inputs'
            with self.assertRaisesRegex(k.Refused, 'NATIVE_LOAD_(JOB|POD)_CHANGED'):
                k.observe(c, objects, client, baseline)
            secret['secretName'] = old
            k.observe(c, objects, client, baseline)
        source = job['spec']['template']['spec']['volumes'][2]['projected']['sources'][1]['configMap']['items'][0]
        old = source['key']; source['key'] = 'wrong-ca'
        with self.assertRaisesRegex(k.Refused, 'NATIVE_LOAD_JOB_CHANGED'):
            k.observe(c, objects, client, baseline)
        source['key'] = old
        k.observe(c, objects, client, baseline)
        # A replacement between guarded and private reads cannot inherit custody.
        masked = mask(job)
        masked['metadata']['uid'] = 'old-job'
        with self.assertRaisesRegex(k.Refused, 'NATIVE_LOAD_ACTOR_REPLACED'):
            j.exact_spec(c, client, masked, baseline['namespace']['uid'])
        original_ns = client.objects['Namespace/'+c['namespace']]['metadata']['uid']
        client.objects['Namespace/'+c['namespace']]['metadata']['uid'] = 'replaced-namespace'
        count = len(direct)
        with self.assertRaisesRegex(k.Refused, 'NATIVE_LOAD_NAMESPACE_CHANGED'):
            j.exact_spec(c, client, mask(job), original_ns)
        self.assertEqual(len(direct), count)

    def test_standalone_waiter_requires_independent_verification_and_scoped_rbac(self):
        c, _, _, _ = fixture()
        legacy = j.declarations(c)
        c['pins']['candidate'] = {'verificationJob': 'verification'}
        standalone = j.declarations(c)
        waiter = standalone[0]['spec']['template']['spec']['initContainers'][0]
        self.assertEqual(waiter['command'][-3:], ['provision', 'verification', 'primer:ready'])
        role = next(row for row in standalone if row['kind'] == 'Role')
        self.assertEqual(role['rules'], [{'apiGroups': ['batch'], 'resources': ['jobs'],
                                         'resourceNames': ['provision', 'verification', 'primer'], 'verbs': ['get']}])
        self.assertEqual(standalone, j.declarations(json.loads(json.dumps(c))))
        del c['pins']['candidate']
        self.assertEqual(j.declarations(c), legacy)

    def test_persisted_configuration_keeps_exact_native_declaration(self):
        c,_,_,_=fixture()
        restored=json.loads(json.dumps(c,sort_keys=True))
        original=j.declarations(c)
        self.assertEqual(original,j.declarations(restored))
        plan=next(row['value'] for row in original[0]['spec']['template']['spec']['containers'][0]['env']
                  if row['name']=='M7_DRIVER_PLAN')
        import driver_vu_diagnostic as driver
        import workload_runtime
        expected=driver.configured_environment(workload_runtime.driver_manifest(c))['M7_DRIVER_PLAN']
        self.assertEqual(json.loads(plan),json.loads(expected))

    @unittest.skipUnless(os.environ.get('NS_NATIVE_QUALIFIED_RENDER'),'qualified binding render required')
    def test_load_label_has_edge_access_without_private_operator_plane_access(self):
        c,_,_,_=fixture()
        render=k.document(os.environ['NS_NATIVE_QUALIFIED_RENDER'])
        objects={k.key(obj):obj for obj in k.manifests(render)}
        namespace=next(obj for obj in objects.values() if obj['kind']=='Namespace')
        owner,= [name for name in namespace['metadata']['labels'] if name.endswith('/run-id')]
        c.update(ownerLabel=owner,runId=namespace['metadata']['labels'][owner],namespace=namespace['metadata']['name'])
        job=j.declarations(c)[0];labels=job['spec']['template']['metadata']['labels']
        policies=[obj for obj in objects.values() if obj['kind']=='NetworkPolicy']
        original=copy.deepcopy(policies)
        policy,= [obj for obj in j.declarations(c) if obj['kind']=='NetworkPolicy']
        policies.append(policy)
        def matches(selector,actor):
            self.assertFalse(selector.get('matchExpressions'),'selector requires additional evidence')
            return all(actor.get(name)==value for name,value in selector.get('matchLabels',{}).items())
        def allowed(source,target,port,source_namespace=None):
            destination=objects[target]['spec']['template']['metadata']['labels']
            for obj in policies:
                if obj['metadata']['namespace']!=c['namespace'] or not matches(obj['spec']['podSelector'],destination):continue
                for rule in obj['spec'].get('ingress',[]):
                    if rule.get('ports') and not any(row.get('port')==port and row.get('protocol','TCP')=='TCP' for row in rule['ports']):continue
                    if not rule.get('from'):return True
                    for peer in rule['from']:
                        # Cilium's default ipBlock excludes Pod identities. A
                        # CIDR match is not evidence of Pod-to-Pod permission.
                        if 'ipBlock' in peer:continue
                        self.assertNotIn('namespaceSelector',peer,'cross-namespace policy requires separate evidence')
                        if source_namespace not in (None,c['namespace']):continue
                        if 'podSelector' in peer and matches(peer['podSelector'],source):return True
            return False
        edge_port,= [row['port'] for row in objects['Service/edge']['spec']['ports']]
        self.assertTrue(allowed(labels,'Deployment/edge',edge_port))
        policies.remove(policy)
        self.assertFalse(allowed(labels,'Deployment/edge',edge_port))
        policies.append(policy)
        self.assertTrue(allowed(labels,'Deployment/edge',edge_port))
        self.assertFalse(allowed(labels,'Deployment/edge',edge_port,'peer-namespace'))
        self.assertFalse(allowed(dict(labels,**{owner:'peer-run'}),'Deployment/edge',edge_port))
        self.assertFalse(allowed(labels,'Deployment/edge',1342))
        operator=dict(labels,**{'app.kubernetes.io/component':'operator'})
        self.assertTrue(allowed(operator,'Deployment/admin',1342),'control must reach the current private policy')
        self.assertEqual(labels['app.kubernetes.io/component'],'load')
        for target,port in [('admin',1342),('api',1337),('api',19001),('evaluator',19002),('evaluator',19913),
                            ('realtime',1339),('realtime',19003),('tenant-admin',19004),('postgres',5432),('vault',8200)]:
            kind='StatefulSet' if target in ('postgres','vault') else 'Deployment'
            self.assertFalse(allowed(labels,kind+'/'+target,port),(target,port))
        self.assertEqual([obj for obj in policies if obj is not policy],original)

    def test_native_edge_policy_is_exact_owned_declaration_and_readback(self):
        c,inventory,render,client=fixture()
        policy,= [obj for obj in render if obj['kind']=='NetworkPolicy']
        objects=k.validate(c,inventory,render)
        baseline=k.observe(c,objects,client)
        self.assertEqual(policy['metadata']['namespace'],c['namespace'])
        self.assertEqual(policy['spec']['ingress'][0]['ports'],[{'port':8080,'protocol':'TCP'}])
        source=policy['spec']['ingress'][0]['from'][0]
        self.assertEqual(set(source),{'podSelector'})
        self.assertEqual(source['podSelector']['matchLabels']['app.kubernetes.io/component'],'load')
        self.assertEqual(source['podSelector']['matchLabels'][c['ownerLabel']],c['runId'])
        self.assertEqual(policy['spec']['podSelector']['matchLabels']['app.kubernetes.io/component'],'edge')
        key=k.key(policy)
        del objects[key]
        with self.assertRaisesRegex(k.Refused,'NATIVE_LOAD_DECLARATION_CHANGED'):j.validate(c,inventory,objects)
        objects[key]=policy;j.validate(c,inventory,objects)
        changes=[lambda p:p['spec']['ingress'][0]['from'][0]['podSelector']['matchLabels'].update({'app.kubernetes.io/component':'operator'}),
                 lambda p:p['spec']['ingress'][0]['ports'][0].update(port=1342),
                 lambda p:p['spec']['ingress'][0]['from'][0].update(namespaceSelector={}),
                 lambda p:p['metadata'].update(namespace='peer-namespace'),
                 lambda p:p['spec']['podSelector']['matchLabels'].update({'app.kubernetes.io/component':'api'})]
        for mutate in changes:
            broken=copy.deepcopy(policy);mutate(broken);objects[key]=broken
            with self.assertRaisesRegex(k.Refused,'NATIVE_LOAD_DECLARATION_CHANGED'):j.validate(c,inventory,objects)
            objects[key]=policy;j.validate(c,inventory,objects)
            live=copy.deepcopy(client.objects[key]);mutate(live);client.objects[key]=live
            with self.assertRaisesRegex(k.Refused,'NATIVE_LOAD_EDGE_POLICY_CHANGED|FOREIGN_NAMESPACE'):
                k.observe(c,objects,client,baseline)
            client.objects[key]=dict(copy.deepcopy(policy),metadata=dict(policy['metadata'],uid='uid-'+policy['metadata']['name'],resourceVersion='10'))
            k.observe(c,objects,client,baseline)
        without=copy.deepcopy(c);without.pop(j.FIELD)
        no_selection=copy.deepcopy(inventory);no_selection.pop(j.FIELD)
        without_job={name:obj for name,obj in objects.items() if name!=j.JOB}
        with self.assertRaisesRegex(k.Refused,'NATIVE_LOAD_UNACCOUNTED_POLICY'):
            j.validate(without,no_selection,without_job)
    def test_declared_suspended_job_rbac_and_full_pod_budget(self):
        c,inventory,render,client=fixture()
        objects=k.validate(c,inventory,render)
        before=k.observe(c,objects,client)
        self.assertTrue(before['nativeLoadSuspended']);self.assertFalse(before['testActors'])
        old=matrix.node_requests({name:obj for name,obj in objects.items() if name!=j.JOB},before,k.resource_accounting(c))
        total=matrix.node_requests(objects,before,k.resource_accounting(c),c)
        node,reserved=j.reserve(c,objects)
        for name,value in reserved.items():self.assertEqual(total[node][name],old.get(node,{}).get(name,0)+value)
        role=objects['Role/'+j.ACCOUNT]
        self.assertEqual(role['rules'],[{'apiGroups':['batch'],'resources':['jobs'],'resourceNames':['provision','primer'],'verbs':['get']}])
        self.assertFalse(objects[j.JOB]['spec']['template']['spec']['automountServiceAccountToken'])

    def test_unaccounted_job_quota_and_changed_declaration_controls_restore(self):
        c,inventory,render,client=fixture();k.validate(c,inventory,render)
        chosen=c.pop(j.FIELD);record=inventory.pop(j.FIELD)
        with self.assertRaisesRegex(k.Refused,'UNACCOUNTED_JOB'):k.validate(c,inventory,render)
        c[j.FIELD]=chosen;inventory[j.FIELD]=record;k.validate(c,inventory,render)
        quota=next(obj for obj in render if obj['kind']=='ResourceQuota')
        old=quota['spec']['hard']['requests.memory'];quota['spec']['hard']['requests.memory']='1Mi'
        with self.assertRaisesRegex(k.Refused,'UNACCOUNTED_QUOTA'):k.validate(c,inventory,render)
        quota['spec']['hard']['requests.memory']=old;k.validate(c,inventory,render)
        job=next(obj for obj in render if k.key(obj)==j.JOB);job['spec']['backoffLimit']=1
        with self.assertRaisesRegex(k.Refused,'DECLARATION_CHANGED'):k.validate(c,inventory,render)
        job['spec']['backoffLimit']=0;k.validate(c,inventory,render)

    def test_dynamic_test_actor_preserves_application_census_and_reports_owned_replacement(self):
        c,inventory,render,client=fixture();objects=k.validate(c,inventory,render)
        baseline=k.observe(c,objects,client)
        job=client.objects[j.JOB];job['spec']['suspend']=False
        pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'k6-owned','namespace':c['namespace'],'uid':'pod-owned',
            'resourceVersion':'12','labels':copy.deepcopy(job['spec']['template']['metadata']['labels']),'ownerReferences':[
                {'kind':'Job','name':'k6','uid':job['metadata']['uid'],'controller':True}]},
            'spec':copy.deepcopy(job['spec']['template']['spec']),'status':{'phase':'Pending'}}
        client.pods.append(pod)
        current=k.observe(c,objects,client,baseline)
        self.assertEqual(current['pods'].keys(),baseline['pods'].keys())
        self.assertEqual(set(current['testActors']),{'k6-owned'})
        pod['metadata']['labels']['app.kubernetes.io/component']='operator'
        with self.assertRaisesRegex(k.Refused,'POD_LABELS_CHANGED'):k.observe(c,objects,client,baseline)
        pod['metadata']['labels']['app.kubernetes.io/component']='load'
        k.observe(c,objects,client,baseline)
        with tempfile.TemporaryDirectory() as scratch:
            custody=Path(scratch)/'native-load.json';c['nativeLoadCustodyFile']=str(custody)
            k.write(custody,{'jobUid':job['metadata']['uid'],'podUid':'original-pod'})
            actor=k.observe(c,objects,client,baseline)['testActors']['k6-owned']
            self.assertEqual(actor['actorTransitions'], [{'actor':'Pod','from':'original-pod','to':'pod-owned'}])
            k.write(custody,{'jobUid':job['metadata']['uid'],'podUid':'pod-owned'})
            k.observe(c,objects,client,baseline)
        role=client.objects['Role/'+j.ACCOUNT];role['rules'][0]['verbs'].append('create')
        with self.assertRaisesRegex(k.Refused,'RBAC_CHANGED'):k.observe(c,objects,client,baseline)
        role['rules'][0]['verbs'].pop();k.observe(c,objects,client,baseline)

    def test_midpoint_failure_suspends_exact_uid_and_waits_for_writer_exit(self):
        c,_,_=configured();c['deadlines']['cleanupUntil']='2099-01-01T00:30:00Z'
        receipt={'jobUid':'owned-job','namespaceUid':'owned-ns','podUid':'owned-pod'}
        seen=[]
        class Kube:
            def __init__(self):self.suspended=False;self.rounds=0
            def call(self,args,**kw):
                seen.append(args)
                patch_=json.loads(args[-1]);self.asserted=patch_[0]
                if self.asserted!={'op':'test','path':'/metadata/uid','value':'owned-job'}:raise AssertionError(patch_)
                self.suspended=True
            def json(self,args,**kw):
                if args[:2]==['get','namespace']:
                    return {'metadata':{'name':c['namespace'],'uid':'owned-ns','labels':{c['ownerLabel']:c['runId']}}}
                if args[:2]==['get','job']:
                    return {'metadata':{'name':'k6','namespace':c['namespace'],'uid':'owned-job','labels':{c['ownerLabel']:c['runId']}},
                            'spec':{'suspend':self.suspended}}
                self.rounds+=1
                return {'items':[{'metadata':{'uid':'owned-pod','namespace':c['namespace'],'labels':{c['ownerLabel']:c['runId']},
                    'ownerReferences':[{'kind':'Job','uid':'owned-job','controller':True}]},'status':{
                    'containerStatuses':[{'name':'k6','state':{'running':{}} if self.rounds==1 else {'terminated':{'exitCode':143}}}]}}]}
        with tempfile.TemporaryDirectory() as scratch:
            cube=Kube();value=j.cancel(cube,c,receipt,scratch)
            self.assertTrue(value['writersStopped']);self.assertEqual(cube.rounds,2)
            self.assertEqual(len(seen),1)
            j.cancel(cube,c,receipt,scratch);self.assertEqual(len(seen),1)
        with tempfile.TemporaryDirectory() as scratch:
            foreign=Kube();count=len(seen)
            with self.assertRaisesRegex(k.Refused,'ACTOR_REPLACED'):
                j.cancel(foreign,c,dict(receipt,jobUid='foreign-job'),scratch)
            self.assertEqual(len(seen),count)
            self.assertFalse(foreign.suspended)
        # The native collector consumes the actual concurrent failure signal;
        # it must never reach artifact or completed-output assessment.
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaisesRegex(k.Refused,'MIDPOINT_HARD'):
                f.capture(SimpleNamespace(json=lambda *_:None),c,{},Path(scratch)/'load',{'namespaceUid':'owned-ns','activeDeadlineSeconds':30},
                          failures=[k.Refused('M7_OUTCOME_MIDPOINT_HARD','FAIL')])

    def test_opt_in_execute_keeps_original_probe_writer_join_and_oracle_order(self):
        # Exercise the real controller flow with admitted synthetic boundaries;
        # clinical correctness itself is covered by the unchanged oracle suite.
        from test_native_load import TENANTS
        c,_,_,_=fixture();c['completion']={};c['baseUrl']='http://127.0.0.1:18080'
        c['tenantsFile']='/synthetic/tenants.json'
        c['driver'].update(node='/synthetic/node',dependencies='/synthetic/deps',
                           k6='/synthetic/k6',k6Sha256='9'*64)
        events=[];midpoints=[];baseline={'namespace':{'uid':'owned-ns'}}
        with tempfile.TemporaryDirectory() as scratch:
            d=Path(scratch);out=d/'load'
            for name in ('probe.cjs','workload.js'):(d/name).write_bytes(b'synthetic-source')
            k.write(d/'packet.json',{'probe':{'kubernetesSha256':k.digest(d/'probe.cjs')},
                                    'workload':{'adaptedSha256':k.digest(d/'workload.js')}})
            def spawn(*_,**__):
                events.append('probe-start');(out/'.window').touch()
                return SimpleNamespace(returncode=0,poll=lambda:0)
            def collect(d,out,c,objects,client,name,**kw):
                k.write(out/(name+'.json'),{});return {}
            def native(*_,**__):
                self.assertTrue((out/'.window').exists());events.append('native-load')
                at=int(time.time()*1000)
                k.write(out/'driver-accounting.json',{'shards':[{'phases':{'scheduleStartMs':at-1,'scheduleEndMs':at}}]})
            def joined(*_):events.append('probe-joined');time.sleep(1.05)
            def assess(*_):events.append('full-assessor');return {'verdict':'OBSERVED'}
            with (patch.object(k.candidate,'require'),patch.object(k,'active_baseline',return_value=baseline),
                  patch.object(k,'observe',return_value=baseline),patch.object(execute,'actor',return_value={}),
                  patch.object(execute,'completion'),patch.object(execute,'roster',return_value=TENANTS),
                  patch('preload.run',return_value=None),patch.object(execute,'retained_progress',side_effect=collect),
                  patch.object(execute,'midpoint_signal',side_effect=lambda *_:midpoints.append('observed') or {'action':'continue'}),
                  patch.object(execute.subprocess,'Popen',side_effect=spawn),patch.object(j,'run',side_effect=native),
                  patch.object(execute,'configured_load') as local,
                  patch.object(execute,'wait_observed',side_effect=joined),patch.object(execute,'stop_process'),
                  patch.object(execute,'stop_evidence'),patch('catchup.run',side_effect=lambda *a,**kw:events.append('catchup')),
                  patch.object(execute,'terminal_progress',side_effect=lambda *_:events.append('terminal-progress')),
                  patch.object(n,'assess_join',side_effect=assess)):
                result=execute.execute(d,c,{},None,load=True)
            self.assertEqual(result['verdict'],'OBSERVED');local.assert_not_called()
            self.assertEqual(events,['probe-start','native-load','probe-joined','catchup','terminal-progress','full-assessor'])
            self.assertEqual(midpoints,['observed'])
            self.assertIn('controller/probe/observer',k.document(out/'driver.json')['localScope'])
            self.assertEqual(k.document(out/'driver.json')['declaredLoadPod']['image'],c['nativeLoad']['image'])
            self.assertEqual(k.document(out/'window.json')['driverTransport'],'in-cluster-k6-service')

    def test_full_native_load_midpoint_path_stops_writer_and_preserves_failure(self):
        from test_native_load import TENANTS, SCRIPT
        c,base,options=configured();c['deadlines']['cleanupUntil']='2099-01-01T00:30:00Z'
        wanted,_,_=n.package(c,base,SCRIPT,TENANTS,**options)
        failures=[]
        class Cube:
            def __init__(self):self.suspended=True;self.patches=[];self.rounds=0
            def call(self,args,**kw):
                if args[0]=='create':return ''  # input Secret only; the Job already exists
                if args[0]=='patch':
                    value=json.loads(args[-1]);self.patches.append(value)
                    self.suspended=value[-1]['value']
                    if not self.suspended:failures.append(k.Refused('M7_OUTCOME_MIDPOINT_HARD','FAIL'))
                    return ''
                raise AssertionError(args)
            def json(self,args,**kw):
                if args[:2]==['get','namespace']:
                    return {'metadata':{'name':c['namespace'],'uid':'owned-ns','labels':{c['ownerLabel']:c['runId']}}}
                if args[:2]==['get','job']:
                    value=copy.deepcopy(wanted);value['spec']['suspend']=self.suspended
                    value['metadata']['uid']='owned-job';return value
                self.rounds+=1
                return {'items':[{'metadata':{'namespace':c['namespace'],'uid':'owned-pod',
                    'labels':{c['ownerLabel']:c['runId']},'ownerReferences':[{'kind':'Job','uid':'owned-job','controller':True}]},
                    'status':{'containerStatuses':[{'name':'k6','state':{'running':{}} if self.rounds==1 else
                        {'terminated':{'exitCode':143}}}]}}]}
        cube=Cube()
        with tempfile.TemporaryDirectory() as scratch:
            out=Path(scratch)/'load';out.mkdir()
            with self.assertRaisesRegex(k.Refused,'MIDPOINT_HARD'):
                n.run(cube,c,base,SCRIPT,TENANTS,out,predeclared={'uid':'owned-job'},
                      failures=failures,**options)
            self.assertEqual(len(cube.patches),2)  # one start, one stop; no replay
            self.assertEqual(cube.patches[-1][0],{'op':'test','path':'/metadata/uid','value':'owned-job'})
            self.assertTrue(k.document(out/'native-cancel.json')['writersStopped'])
            self.assertEqual(k.document(out/'native-first-failure.json')['verdict'],'FAIL')
            self.assertFalse((out/'driver-accounting.json').exists())
            self.assertFalse((out/'outcome-gate.json').exists())
        with tempfile.TemporaryDirectory() as scratch:
            never_started=Cube()
            with self.assertRaisesRegex(k.Refused,'MIDPOINT_HARD'):
                n.run(never_started,c,base,SCRIPT,TENANTS,scratch,predeclared={'uid':'owned-job'},
                      failures=failures,**options)
            self.assertFalse(never_started.patches)

    def test_unpinned_load_job_keeps_requests(self):
        c, inventory, render, client = fixture()
        selected = c['nativeLoad']
        selected.pop('nodeName')
        job = j.base_job(c)
        spec = job['spec']['template']['spec']
        self.assertNotIn('nodeSelector', spec)
        self.assertNotIn('nodeName', spec)
        self.assertEqual(spec['containers'][0]['resources'], selected['resources'])
        selected['tolerations'] = [{'key':'dedicated','value':'nightscout','operator':'Equal','effect':'NoSchedule'}]
        self.assertEqual(j.base_job(c)['spec']['template']['spec']['tolerations'],selected['tolerations'])


if __name__=='__main__':unittest.main()
