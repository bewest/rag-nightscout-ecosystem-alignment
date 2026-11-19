"""Opt-in execution boundary: declaration/census, budget and exact writer stop."""
import copy
import json
import os
import ipaddress
from pathlib import Path
import tempfile
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
    @unittest.skipUnless(os.environ.get('NS_NATIVE_QUALIFIED_RENDER'),'qualified binding render required')
    def test_load_label_has_edge_access_without_private_operator_plane_access(self):
        c,_,_,_=fixture();job=j.declarations(c)[0]
        labels=job['spec']['template']['metadata']['labels']
        render=k.document(os.environ['NS_NATIVE_QUALIFIED_RENDER'])
        policies=[obj for obj in k.manifests(render) if obj['kind']=='NetworkPolicy']
        private={1342,19001,19002,19003,19004}
        def matches(selector,actor):
            self.assertFalse(selector.get('matchExpressions'),'selector requires additional evidence')
            return all(actor.get(name)==value for name,value in selector.get('matchLabels',{}).items())
        def sources(rule,actor):
            return not rule.get('from') or any('podSelector' in row and 'namespaceSelector' not in row
                and matches(row['podSelector'],actor) or 'ipBlock' in row
                and ipaddress.ip_address('192.0.2.10') in ipaddress.ip_network(row['ipBlock']['cidr'])
                and not any(ipaddress.ip_address('192.0.2.10') in ipaddress.ip_network(net)
                            for net in row['ipBlock'].get('except',[])) for row in rule['from'])
        def exposed(actor):
            found=[]
            for obj in policies:
                for rule in obj['spec'].get('ingress',[]):
                    ports={row.get('port') for row in rule.get('ports',[])}
                    if ports & private:
                        self.assertFalse(any('namespaceSelector' in row or 'ipBlock' in row for row in rule.get('from',[])),
                                         'private policy requires additional namespace/IP evidence')
                    if ports & private and sources(rule,actor):found.append(obj['metadata']['name'])
            return found
        operator=dict(labels,**{'app.kubernetes.io/component':'operator'})
        self.assertTrue(exposed(operator),'the control never reached the current private-plane policies')
        self.assertEqual(labels['app.kubernetes.io/component'],'load')
        self.assertFalse(exposed(labels),exposed(labels))
        edge=[obj for obj in policies if obj['spec'].get('podSelector',{}).get('matchLabels',{}).get('app.kubernetes.io/component')=='edge']
        self.assertTrue(edge)
        self.assertTrue(any((not rule.get('ports') or any(row.get('port')==8080 for row in rule['ports']))
                            and sources(rule,labels) for obj in edge for rule in obj['spec'].get('ingress',[])))
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

    def test_dynamic_test_actor_preserves_application_census_and_rejects_replacement(self):
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
            with self.assertRaisesRegex(k.Refused,'ACTOR_REPLACED'):k.observe(c,objects,client,baseline)
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
        import ast
        source=(k.HERE/'execute.py').read_text();tree=ast.parse(source)
        node=next(row for row in tree.body if isinstance(row,ast.FunctionDef) and row.name=='execute')
        calls=[(row.lineno,ast.unparse(row.func)) for row in ast.walk(node) if isinstance(row,ast.Call)]
        line=lambda name:min(row[0] for row in calls if row[1]==name)
        self.assertLess(line('subprocess.Popen'),line('native_join.run'))
        self.assertLess(line('native_join.run'),line('wait_observed'))
        self.assertLess(line('wait_observed'),line('catchup.run'))
        self.assertLess(line('catchup.run'),line('native_load.assess_join'))

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

    def test_scheduler_fit_adds_suspended_test_pod_before_any_actor_starts(self):
        import scheduler_placement as placement
        from types import SimpleNamespace
        c,inventory,render,client=fixture();objects=k.validate(c,inventory,render)
        c['driver']['node']='/synthetic/node'
        before=k.observe(c,objects,client)
        node,need=j.reserve(c,objects)
        responses=iter([b'{"items":[]}',json.dumps({'items':[{'metadata':{'name':node,
                          'labels':{'kubernetes.io/hostname':node}}}]}).encode(),
                        (node+' 10m 1% 50Mi 1%\n').encode()])
        native=SimpleNamespace(call=lambda _:next(responses))
        with patch.object(placement.k,'load',return_value=('packet',c,objects)), \
             patch.object(placement.k,'active_baseline',return_value=before), \
             patch.object(placement.k,'observe',return_value=before), \
             patch.object(placement.matrix,'identity'), \
             patch.object(placement.matrix,'node_requests',return_value={node:need}), \
             patch.object(placement.subprocess,'run') as run:
            # Remove bound application Pods only from this mocked fit snapshot;
            # the actual census test above independently preserves them.
            run.return_value.stdout='[{"fits":false}]'
            current=dict(before,pods={})
            placement.k.observe.return_value=current
            result=placement.confirm('packet','/binding',native)
        value=json.loads(run.call_args.kwargs['input'])
        self.assertEqual(value['incremental'][node],{'cpu':need['millicpus']/1000,'memory':need['memoryBytes']})
        self.assertFalse(result['fits'])
        self.assertEqual(result['nodeCeilings'],{node:need})


if __name__=='__main__':unittest.main()
