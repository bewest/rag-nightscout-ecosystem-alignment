"""Actual retained raw pair/redactor through Client+observe, with inert API GETs.

K8S_PHASE_PRIVATE_CASE is a closed case containing provision-native-api/job.json,
pod.json, render.json, environment.json and runtime/provision-retirement.json.
K8S_PHASE_PRIVATE_GUARD selects the exact retained read-only guard. Missing
private fixtures explicitly skip; they do not qualify this runtime capability.
"""
import copy
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import kube_adapter as k
import phase_fit as p
import phase_source_private as private

HERE=Path(__file__).resolve().parent


class PrivateSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case=os.environ.get('K8S_PHASE_PRIVATE_CASE');guard=os.environ.get('K8S_PHASE_PRIVATE_GUARD')
        if not case or not guard:raise unittest.SkipTest('retained private source/redactor fixtures absent')
        cls.original=Path(case);cls.guard=Path(guard)
        source=cls.guard.read_text();cls.redactor='redact() {'+source.split('redact() {',1)[1].split('\n}\n\nctx=',1)[0]+'\n}\nredact\n'

    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        read=lambda path:json.loads(path.read_bytes())
        self.environment=read(self.original/'environment.json')
        self.render=list(p.objects(read(self.original/'render.json')))
        self.expected=next(o for o in self.render if p.key(o)==p.PROVISION)
        self.job=read(self.original/'provision-native-api/job.json')
        self.pod=read(self.original/'provision-native-api/pod.json')
        self.retirement=read(self.original/'runtime/provision-retirement.json')
        self.config=read(self.original/'runtime/packet/run.json')
        # Other roles use synthetic API replies; only the provision raw pair is retained.
        self.config['pins'].pop('candidate',None)
        self.config['pins']['instrument']=k.instrument()['sha256']
        now=time.time();until=now+600
        iso=lambda value:datetime.fromtimestamp(value,timezone.utc).isoformat().replace('+00:00','Z')
        self.config['deadlines']={'workUntil':iso(until),'cleanupUntil':iso(until+600)}
        self.objects={p.key(o):o for o in self.render}
        self.api={};self.pods=[]
        for name,obj in self.objects.items():
            actual=copy.deepcopy(obj);actual['metadata'].update(uid='synthetic-'+obj['metadata']['name'],resourceVersion='1')
            if obj['kind']=='Namespace':actual['metadata']['uid']=self.retirement['namespaceUid']
            if name==p.PROVISION:actual=copy.deepcopy(self.job)
            self.api[name]=actual
            if obj['kind'] not in k.WORKLOADS:continue
            if name==p.PROVISION:self.pods.append(copy.deepcopy(self.pod));continue
            spec=copy.deepcopy(p.template(obj));metadata=copy.deepcopy(obj['spec']['template']['metadata'])
            metadata.update(name=obj['metadata']['name']+'-fixture',namespace=self.config['namespace'],
                            uid='synthetic-pod-'+obj['metadata']['name'],resourceVersion='1',
                            ownerReferences=[{'kind':obj['kind'],'name':obj['metadata']['name'],
                                              'uid':actual['metadata']['uid'],'controller':True}])
            def status(c,init=False):
                return {'name':c['name'],'containerID':'containerd://synthetic-'+c['name'],
                        'imageID':'containerd://'+self.config['pins']['appImageId'],'restartCount':0,'ready':True,
                        'state':{'terminated':{'exitCode':0,'finishedAt':'2026-11-18T00:00:00Z'}} if init else
                                {'running':{'startedAt':'2026-11-18T00:00:00Z'}}}
            self.pods.append({'apiVersion':'v1','kind':'Pod','metadata':metadata,'spec':spec,
                              'status':{'phase':'Running','conditions':[{'type':'Ready','status':'True'}],
                                        'containerStatuses':[status(c) for c in spec['containers']],
                                        'initContainerStatuses':[status(c,True) for c in spec.get('initContainers',[])]}})
        self.bin=self.root/'bin';self.bin.mkdir();self.binary=self.bin/'kubectl'
        self.binary.write_text('''#!'''+sys.executable+'''
import json,os,sys
from pathlib import Path
args=sys.argv[1:];data=json.loads(Path(os.environ['PHASE_TEST_API']).read_text())
if data.get('fail'):
 sys.stderr.write('SYNTHETIC-CREDENTIAL-MUST-STAY-PRIVATE');sys.exit(3)
i=args.index('get');kind,name=args[i+1:i+3]
allowed={('namespace',data['namespace']['metadata']['name']):data['namespace'],('job','provision'):data['job'],('pod',data['podName']):data['pod']}
if (kind,name) not in allowed:sys.stderr.write('FIXED_GET_REFUSED');sys.exit(3)
with open(os.environ['PHASE_TEST_QUERIES'],'a') as out:out.write(json.dumps({'kind':kind,'name':name})+'\\n')
value=allowed[(kind,name)]
if value is None:
 if '--ignore-not-found' not in args:sys.exit(3)
else:sys.stdout.write(json.dumps(value))
''');self.binary.chmod(0o700)
        self.config.update(kubectl=str(self.binary),readonlyGuard=str(self.guard))
        self.scopefile=self.root/'scope.private.json';self.prooffile=self.root/'retirement.private.json'
        self.prooffile.write_text(json.dumps(self.retirement));self.prooffile.chmod(0o600)
        self.config[p.FIELD]['retirement']={'path':str(self.prooffile),'sha256':private.sha(self.prooffile)}
        self.api_file=self.root/'api.private.json';self.queries=self.root/'queries.jsonl'
        self.refresh_scope()
        self.write_api()
        self.calls=[];self.private_calls=0;self.private_output=[];self.post_mutation=None;self.forge=None
        self.client=k.Client(self.config,run=self.transport)

    def refresh_scope(self):
        self.scope={'version':1,'kind':private.KIND,'context':self.config['context'],
                    'namespace':self.config['namespace'],'runId':self.config['runId'],
                    'namespaceUid':self.retirement['namespaceUid'],'expectedJob':self.expected,
                    'retirement':self.retirement,'planSha256':p.digest(self.config[p.FIELD]['plan']),
                    'instrument':self.config['pins']['instrument'],
                    'source':{name:self.config['pins'][name] for name in ('pair','bindingCommit','appImage')},
                    'tools':{'files':private.identity(),'kubectl':{'path':str(self.binary),'sha256':private.sha(self.binary)},
                             'guard':{'path':str(self.guard),'sha256':private.sha(self.guard)}},
                    'workUntil':k.timestamp(self.config['deadlines']['workUntil'])}
        self.scopefile.write_text(json.dumps(self.scope));self.scopefile.chmod(0o600)
        self.config[p.FIELD]['privateSource']={'path':str(self.scopefile),'sha256':private.sha(self.scopefile)}

    def write_api(self):
        pod=next((v for v in self.pods if v['metadata']['name']==self.retirement['pod']['name']),None)
        self.api_file.write_text(json.dumps({'namespace':self.api['Namespace/'+self.config['namespace']],
                                            'job':self.api[p.PROVISION],'pod':pod,'podName':self.retirement['pod']['name']}))
        self.api_file.chmod(0o600)

    def redact(self,value):
        raw=json.dumps(value,indent=2).encode()
        result=subprocess.run(['bash','-c',self.redactor],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
        return result.stdout

    def transport(self,argv,**kwargs):
        self.calls.append(list(argv))
        if argv[0]==sys.executable:
            self.private_calls+=1
            child={**kwargs['env'],'PHASE_TEST_API':str(self.api_file),'PHASE_TEST_QUERIES':str(self.queries)}
            result=subprocess.run(argv,**{**kwargs,'env':child})
            self.private_output.append(result.stdout+result.stderr)
            if self.post_mutation:self.post_mutation()
            if self.forge and result.returncode==0:
                value=json.loads(result.stdout);self.forge(value)
                return SimpleNamespace(returncode=0,stdout=json.dumps(value).encode(),stderr=b'')
            return result
        if argv[0]==self.config['readonlyGuard']:
            i=argv.index('get');kind=argv[i+1];name=argv[i+2] if argv[i+2]!='-o' else None
            if kind=='namespace':value=self.api['Namespace/'+name]
            elif kind=='replicasets':value={'items':[]}
            elif kind=='pods':value={'items':self.pods}
            else:value=self.api[kind+'/'+name]
            return SimpleNamespace(returncode=0,stdout=self.redact(value),stderr=b'')
        if argv[0]==self.config['kubectl'] and 'exec' in argv:
            return SimpleNamespace(returncode=0,stdout=b'1\n',stderr=b'')
        raise AssertionError('Unexpected transport class')

    def observe(self):return k.observe(self.config,self.objects,self.client)

    def test_actual_raw_pair_and_exact_redactor_through_client_observe(self):
        old={name:value for name,value in self.retirement.items() if name!='planSha256'}
        p.terminal(self.expected,self.job,[self.pod],self.retirement['namespaceUid'],self.config['runId'],old)
        with self.assertRaisesRegex(ValueError,'JOB_SOURCE_CHANGED'):
            p.terminal(self.expected,json.loads(self.redact(self.job)),[self.pod],
                       self.retirement['namespaceUid'],self.config['runId'],old)
        point=self.observe()
        self.assertEqual(point[p.FIELD]['sourceEquality'],'VERIFIED_PRIVATE')
        self.assertTrue(any(row['maskedPaths'] for row in point['objects'].values()))
        self.assertEqual(self.private_calls,1)
        queries=[json.loads(line) for line in self.queries.read_text().splitlines()]
        self.assertEqual(len(queries),6)
        self.assertEqual({r['kind'] for r in queries},{'namespace','job','pod'})

    def test_private_success_and_failure_do_not_emit_sensitive_source_values(self):
        self.observe()
        values=[row['value'] for c in p.template(self.job).get('initContainers',[])+p.template(self.job)['containers']
                for row in c.get('env',[]) if 'value' in row and
                re.search('PASSWORD|TOKEN|SECRET|KEY',row.get('name','')) and len(row['value'])>=8]
        values += [v['secret']['secretName'] for v in self.pod['spec'].get('volumes',[]) if 'secret' in v]
        for value in values:self.assertTrue(all(value.encode() not in output for output in self.private_output))
        snapshot,roster=private.guarded_scope(self.config,self.api['Namespace/'+self.config['namespace']],self.api[p.PROVISION],self.pods,self.scope)
        request={'version':1,'scope':self.config[p.FIELD]['privateSource'],'nonce':'a'*64,'until':time.time()+30,
                 'identity':snapshot,'rosterSha256':roster,'secret':'SYNTHETIC-CREDENTIAL-MUST-STAY-PRIVATE'}
        with self.assertRaises(k.Refused) as found:self.client.phase_source_proof(request)
        self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('PRIVATE_REQUEST',str(found.exception))
        self.assertTrue(all(b'SYNTHETIC-CREDENTIAL-MUST-STAY-PRIVATE' not in output for output in self.private_output))

    def test_true_hidden_env_volume_image_and_command_mutations_remain_fail(self):
        changes=[(lambda spec:spec['initContainers'][1]['env'][11].update(value='synthetic-private-change'),'K8S_PHASE_JOB_SOURCE_CHANGED'),
                 (lambda spec:spec['volumes'][1]['secret'].update(secretName='synthetic-private-change'),'K8S_PHASE_JOB_SOURCE_CHANGED'),
                 (lambda spec:spec['containers'][0].update(image='synthetic.invalid/changed@sha256:'+'0'*64),'K8S_BINDING_READBACK_CHANGED'),
                 (lambda spec:spec['containers'][0].update(command=['changed-command']),'K8S_BINDING_READBACK_CHANGED')]
        for change,code in changes:
            original=copy.deepcopy(self.api[p.PROVISION]);change(p.template(self.api[p.PROVISION]));self.write_api()
            with self.assertRaises(k.Refused) as found:self.observe()
            self.assertEqual(found.exception.verdict,'FAIL')
            # Visible mutations keep their existing earlier readback refusal;
            # mutations hidden by display redaction reach the private proof.
            self.assertEqual(str(found.exception),code)
            self.api[p.PROVISION]=original;self.write_api()
        self.assertEqual(self.observe()[p.FIELD]['sourceEquality'],'VERIFIED_PRIVATE')

    def test_forged_proof_challenge_and_hashes_refuse(self):
        for field in ('nonce','requestSha256','scopeSha256','instrument','terminalSha256','sourceTemplateSha256','rosterSha256'):
            self.forge=lambda value,field=field:value.update({field:'0'*64})
            with self.assertRaises(k.Refused) as found:self.observe()
            self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('PROOF_CHANGED',str(found.exception))
        self.forge=None;self.assertEqual(self.observe()[p.FIELD]['sourceEquality'],'VERIFIED_PRIVATE')

    def test_whole_roster_status_refresh_is_allowed_but_incarnation_change_refuses(self):
        other=next(v for v in self.pods if v['metadata']['name']!=self.retirement['pod']['name'])
        def refresh():
            other['metadata'].update(resourceVersion='ordinary-status-refresh')
            other['status']['containerStatuses'][0]['ready']=False
        self.post_mutation=refresh
        self.assertEqual(self.observe()[p.FIELD]['sourceEquality'],'VERIFIED_PRIVATE')
        for change in (lambda:other['status']['containerStatuses'][0].update(containerID='containerd://changed'),
                       lambda:other['metadata'].update(uid='changed-uid'),
                       lambda:other['metadata']['ownerReferences'][0].update(uid='changed-owner'),
                       lambda:other['spec']['containers'][0]['resources']['requests'].update(cpu='999m')):
            before=copy.deepcopy(other);self.post_mutation=change
            with self.assertRaises(k.Refused) as found:self.observe()
            self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('POST_IDENTITY_CHANGED',str(found.exception))
            other.clear();other.update(before)

    def test_namespace_job_pod_versions_and_extra_owner_drift_refuse(self):
        provision=next(v for v in self.pods if v['metadata']['name']==self.retirement['pod']['name'])
        for target in (self.api['Namespace/'+self.config['namespace']],self.api[p.PROVISION],provision):
            before=copy.deepcopy(target);self.post_mutation=lambda target=target:target['metadata'].update(resourceVersion='changed')
            with self.assertRaises(k.Refused) as found:self.observe()
            self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('POST_IDENTITY_CHANGED',str(found.exception))
            target.clear();target.update(before)
        def overlap():
            extra=copy.deepcopy(provision);extra['metadata'].update(name='unlabelled-overlap',uid='new-owner-pod')
            extra['metadata']['labels'].pop('job-name',None);self.pods.append(extra)
        self.post_mutation=overlap
        with self.assertRaises(k.Refused) as found:self.observe()
        self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('POD_ROSTER',str(found.exception))

    def test_retired_pod_absence_is_positive_only_with_current_job_and_bound_proof(self):
        self.pods=[v for v in self.pods if v['metadata']['name']!=self.retirement['pod']['name']];self.write_api()
        self.assertFalse(self.observe()[p.FIELD]['podPresent'])
        self.api[p.PROVISION]['metadata']['uid']='synthetic-replacement';self.write_api()
        with self.assertRaises(k.Refused) as found:self.observe()
        self.assertEqual(found.exception.verdict,'FAIL')

    def test_unknown_absence_missing_api_and_reforged_receipt_never_pass(self):
        payload=json.loads(self.api_file.read_text());payload['pod']=None;self.api_file.write_text(json.dumps(payload))
        with self.assertRaises(k.Refused) as found:self.observe()
        self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('IDENTITY_CHANGED',str(found.exception))
        self.write_api();payload=json.loads(self.api_file.read_text());payload['fail']=True;self.api_file.write_text(json.dumps(payload))
        with self.assertRaises(k.Refused) as found:self.observe()
        self.assertEqual(found.exception.verdict,'UNMEASURED');self.assertIn('API_UNAVAILABLE',str(found.exception))
        self.assertTrue(all(b'SYNTHETIC-CREDENTIAL-MUST-STAY-PRIVATE' not in output for output in self.private_output))
        self.write_api();changed=copy.deepcopy(self.retirement);changed['jobUid']='forged-job'
        self.prooffile.write_text(json.dumps(changed));self.config[p.FIELD]['retirement']['sha256']=private.sha(self.prooffile)
        self.scope['retirement']=changed;self.scopefile.write_text(json.dumps(self.scope));self.config[p.FIELD]['privateSource']['sha256']=private.sha(self.scopefile)
        with self.assertRaises(k.Refused) as found:self.observe()
        self.assertEqual(found.exception.verdict,'FAIL');self.assertIn('TERMINAL_PROOF_CHANGED',str(found.exception))

    def test_foreign_scope_arbitrary_query_and_missing_helper_are_cheap_refusals(self):
        private.binding(self.config,self.objects)
        changed=copy.deepcopy(self.config);changed['namespace']='ns-synth-foreign'
        with self.assertRaisesRegex(private.Refused,'SCOPE_CHANGED'):private.binding(changed,self.objects)
        point,roster=private.guarded_scope(self.config,self.api['Namespace/'+self.config['namespace']],self.api[p.PROVISION],self.pods,self.scope)
        request={'version':1,'scope':self.config[p.FIELD]['privateSource'],'nonce':'a'*64,
                 'until':time.time()+30,'identity':point,'rosterSha256':roster,'argv':['get','secret','foreign']}
        with self.assertRaisesRegex(private.Refused,'REQUEST'):private.prove(request,get=lambda *a:self.fail('query must not execute'))
        self.scope['tools']['files']['phase_source_private.py']='0'*64
        self.scopefile.write_text(json.dumps(self.scope));self.config[p.FIELD]['privateSource']['sha256']=private.sha(self.scopefile)
        with self.assertRaisesRegex(private.Refused,'TOOL_CHANGED'):private.binding(self.config,self.objects)

    def test_deadline_and_post_fetch_identity_are_checked_inside_private_helper(self):
        snapshot,roster=private.guarded_scope(self.config,self.api['Namespace/'+self.config['namespace']],self.api[p.PROVISION],self.pods,self.scope)
        start=time.time()
        clock=SimpleNamespace(now=start);clock.time=lambda:clock.now
        request={'version':1,'scope':self.config[p.FIELD]['privateSource'],'nonce':'a'*64,
                 'until':start+1,'identity':snapshot,'rosterSha256':roster}
        count=[]
        def slow(kind,name,optional):
            count.append(kind);clock.now+=.4
            return self.api['Namespace/'+name] if kind=='namespace' else self.api[p.PROVISION] if kind=='job' else self.pod
        with self.assertRaisesRegex(private.Refused,'DEADLINE') as found:private.prove(request,get=slow,clock=clock)
        self.assertEqual(found.exception.verdict,'UNMEASURED');self.assertEqual(len(count),3)
        clock.now=start;request['until']=start+30;count=[]
        def drift(kind,name,optional):
            count.append(kind)
            value=copy.deepcopy(self.api['Namespace/'+name] if kind=='namespace' else self.api[p.PROVISION] if kind=='job' else self.pod)
            if len(count)>3 and kind=='job':value['metadata']['resourceVersion']='changed'
            return value
        with self.assertRaisesRegex(private.Refused,'IDENTITY_CHANGED') as found:private.prove(request,get=drift,clock=clock)
        self.assertEqual(found.exception.verdict,'FAIL')

    def test_actual_attach_gate_stops_before_candidate_data_or_ordinary_work(self):
        tree=ast.parse((HERE/'attach.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='observe_selected_bootstrap')
        packet=self.root/'gate-packet';runtime=self.root/'gate-runtime';packet.mkdir();runtime.mkdir()
        (packet/'run.json').write_text(json.dumps({'pins':{'candidate':{'sourceAcceptance':'PENDING'}}}))
        (runtime/'bootstrap-helper-readback.json').write_text(json.dumps({'effectiveInstanceAcceptance':'PENDING','mode':'embedded-image'}))
        self.api[p.PROVISION]['spec']['template']['spec']['initContainers'][1]['env'][11]['value']='hidden-change';self.write_api()
        stages=[]
        def execute(label,argv):
            stages.append(label)
            if label=='observe':return self.observe()
            self.fail('dependent candidate/data/ordinary entry must not run')
        scope={'read':lambda path:json.loads(path.read_text())}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(HERE/'attach.py'),'exec'),scope)
        with self.assertRaises(k.Refused) as found:scope['observe_selected_bootstrap'](packet,runtime,self.retirement['namespaceUid'],[],execute)
        self.assertEqual(found.exception.verdict,'FAIL');self.assertEqual(str(found.exception),'K8S_PHASE_JOB_SOURCE_CHANGED')
        self.assertEqual(stages,['observe'])

    def test_actual_sql_entry_command_count_and_inert_timing(self):
        baseline=self.observe();out=self.root/'packet';out.mkdir();(out/'observation.initial.json').write_text(json.dumps(baseline))
        self.calls=[];self.private_calls=0;self.queries.write_text('')
        started=time.monotonic();value=k.sql(out,self.config,self.objects,'SELECT 1;',self.client);elapsed=time.monotonic()-started
        self.assertEqual(value,'1\n');self.assertEqual(self.private_calls,2)
        self.assertEqual(len(self.queries.read_text().splitlines()),12)
        capture=os.environ.get('K8S_PHASE_COST_OUTPUT')
        if capture:Path(capture).write_text(json.dumps({'basis':'actual SQL entry with exact redactor, real private-helper subprocess and inert API fixtures; not cluster latency',
                                                     'privateHelperCalls':self.private_calls,'privateGETs':12,'guardedCommands':sum(a[0]==self.config['readonlyGuard'] for a in self.calls),
                                                     'seconds':elapsed},indent=2)+'\n')


if __name__=='__main__':unittest.main()
