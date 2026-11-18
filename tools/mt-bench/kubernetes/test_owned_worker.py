"""Synthetic ownership proofs through the exact private and public read paths."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import kube_adapter as k
import owned_worker as w
from test_adapter import fixture as adapter_fixture
import test_commissioning_accounting as commissioning

HERE = Path(__file__).resolve().parent
CONTEXT = 'do-sfo2-do-helloworld'
RUN = 'synthetic-owned-worker'
NS = 'ns-synth-' + RUN


def uid(number):
    return f'00000000-0000-4000-8000-{number:012d}'


def listing(*rows):
    return {'kind':'List', 'apiVersion':'v1', 'metadata':{}, 'items':list(rows)}


def write(path, value):
    path.write_text(json.dumps(value))
    return {'path':str(path), 'sha256':w.digest_bytes(path.read_bytes())}


def labelled_node(value):
    return {'kind':'Node', 'metadata':{'name':value['nodeName'], 'uid':value['nodeUid'], 'labels':{
        w.LABEL:value['runId'], w.POOL_LABEL:value['poolId'], w.PROVIDER_NODE_LABEL:value['providerNodeId'],
        'doks.digitalocean.com/node-pool':value['poolName'], 'topology.kubernetes.io/region':value['region'],
        'node.kubernetes.io/instance-type':value['size']}},
        'spec':{'providerID':value['providerId'],
                'taints':[{'key':w.LABEL, 'value':value['runId'], 'effect':'NoSchedule'}]},
        'status':{'allocatable':{'cpu':'8', 'memory':'16Gi','ephemeral-storage':'150Gi','pods':'100'},
                  'conditions':[{'type':name, 'status':'True' if name=='Ready' else 'False'}
                      for name in ('Ready','PIDPressure','MemoryPressure','DiskPressure','NetworkUnavailable')]}}


def infra(value, number, namespace='default'):
    return {'kind':'Pod','metadata':{'name':'synthetic-monitor-'+str(number),'uid':uid(number),'namespace':namespace,
                'ownerReferences':[{'controller':True,'kind':'DaemonSet','name':'synthetic-monitor','uid':uid(70)}]},
            'spec':{'nodeName':value['nodeName'],'containers':[{'name':'monitor','resources':{
                    'requests':{'cpu':'10m','memory':'32Mi','ephemeral-storage':'1Mi'},
                    'limits':{'cpu':'100m','memory':'64Mi','ephemeral-storage':'2Mi'}}}]},
            'status':{'phase':'Running'}}


class Proof:
    def __init__(self, base, *, run=RUN, context=CONTEXT, namespace=NS):
        self.base = base
        self.prior, self.after = base/'before', base/'after'
        self.prior.mkdir()
        self.after.mkdir()
        self.environment = {'context':context,'runId':run,'namespace':namespace,
                            'cleanupOwner':'synthetic-owner','targetNode':'synthetic-new'}
        self.value = {'contract':w.CONTRACT,'clusterId':uid(1),'region':'sfo2','poolId':uid(2),
                      'poolName':'synthetic-exclusive', 'size':'s-8vcpu-16gb','nodeName':'synthetic-new',
                      'nodeUid':uid(3),'providerNodeId':uid(4),'providerId':'digitalocean://81234', 'runId':run}
        self.data = labelled_node(self.value)
        self.current_pod = infra(self.value, 8)
        self.now = datetime.now(timezone.utc).timestamp()
        time_iso = lambda t: datetime.fromtimestamp(t,timezone.utc).isoformat()
        original = dict(self.value,nodeName='synthetic-old',poolId=uid(11),nodeUid=uid(12),
                        providerNodeId=uid(13),providerId='digitalocean://1234',poolName='synthetic-old')
        old_node = labelled_node(original)
        old_node['spec'].pop('taints')
        def pool(selection, created):
            return {'id':selection['poolId'],'name':selection['poolName'],'size':selection['size'],
                    'count':1,'auto_scale':False,'nodes':[{'id':selection['providerNodeId'],
                     'name':selection['nodeName'],'droplet_id':int(selection['providerId'].split('//')[1]),
                     'status':{'state':'running'},'created_at':time_iso(created)}]}
        old_pool = pool(original,self.now-7200)
        self.new_pool = pool(self.value,self.now-120)
        self.before = {'nodes':listing(old_node),'pools':[old_pool],
                       'clusters':[{'id':uid(1),'region':'sfo2','node_pools':[old_pool]}],
                       'pods':listing(infra(original, 9))}
        self.current = {'nodes':listing(old_node, copy.deepcopy(self.data)),
                        'clusters':[{'id':uid(1),'region':'sfo2','node_pools':[old_pool,self.new_pool]}],
                        'pools':[old_pool,self.new_pool], 'pods':listing(copy.deepcopy(self.current_pod)),
                        'owned-node':self.data}
        self.current['nodes']['items'][1]['spec']['taints'][0]['key'] = '<redacted>'
        for data, captured in ((self.before,self.now-180),(self.current,self.now-5)):
            data['capture'] = {'capturedAt':time_iso(captured),'context':context,
                               'queries':{name:{'exit':0} for name in data}}
        self.scope = {'contract':w.CONTRACT, **{key:self.environment[key] for key in
                      ('runId','context','namespace','cleanupOwner')},
                      'infrastructure':[w.identity(self.current_pod)]}
        self.freeze()
        write(self.after/'disk.json', [{'node':self.value['nodeName'],'exit':0,
           'filesystemMetrics':['node_filesystem_readonly{} 0','node_filesystem_avail_bytes{} 100000000000']}])
        (self.after/'usage.txt').write_text(self.value['nodeName']+' 100m 1% 128Mi 1%\n')

    def freeze(self):
        self.scope['before'] = {key:write(self.prior/(key+'.json'),raw) for key,raw in self.before.items()}
        self.scope['after'] = {key:write(self.after/(key+'.json'),raw) for key,raw in self.current.items()}
        self.value['proof'] = write(self.base/'ownership.json',self.scope)
        self.environment[w.FIELD] = self.value

    def verify(self, now=None):
        return w.prove(self.value,self.environment,self.after,fresh=True,now=now)

    def bind(self, spec):
        spec.update(nodeName=self.value['nodeName'],nodeSelector={w.LABEL:self.value['runId']},
                    tolerations=[w.expected_toleration(self.value)])


class Ownership(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.proof = Proof(self.root)

    def test_refuses_wrong_live_worker_and_restores(self):
        p = self.proof
        restored = copy.deepcopy(p.current)
        cases = {
            'OWNED_WORKER_NODE_CHANGED':lambda x:x['owned-node']['metadata'].update(uid=uid(55)),
            'OWNED_WORKER_POOL_CHANGED':lambda x:x['owned-node']['metadata']['labels'].update({w.POOL_LABEL:uid(55)}),
            'OWNED_WORKER_LABEL_CHANGED':lambda x:x['owned-node']['metadata']['labels'].pop(w.LABEL),
            'OWNED_WORKER_TAINT_OR_CORDON':lambda x:x['owned-node']['spec']['taints'][0].update(value='foreign'),
        }
        for code, change in cases.items():
            with self.subTest(code=code):
                p.current = copy.deepcopy(restored)
                change(p.current)
                p.freeze()
                with self.assertRaisesRegex(ValueError, code):
                    p.verify()
                p.current = copy.deepcopy(restored)
                p.freeze()
                self.assertEqual(p.verify()['selection'],p.value)
        for change in ('taint','cordon'):
            p.current = copy.deepcopy(restored)
            if change == 'taint':
                p.current['owned-node']['spec']['taints'].append({'key':'extra','effect':'NoSchedule'})
            else:
                p.current['owned-node']['spec']['unschedulable'] = True
            p.freeze()
            with self.assertRaisesRegex(ValueError, 'OWNED_WORKER_TAINT_OR_CORDON'):
                p.verify()
        p.current = copy.deepcopy(restored)
        p.freeze()
        p.verify()

    def test_fresh_exact_custody_and_complete_roster(self):
        p = self.proof
        p.verify()
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_STALE_PROOF'):
            p.verify(now=p.now+301)
        p.current['pods']['items'].append(infra(p.value,10,'foreign'))
        p.freeze()
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_FOREIGN_OR_MISSING_POD'):
            p.verify()
        p.current['pods']['items'].pop()
        p.scope['cleanupOwner']='foreign'
        p.freeze()
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_PROOF_CUSTODY'):
            p.verify()
        p.scope['cleanupOwner']=p.environment['cleanupOwner']
        p.freeze()
        p.verify()
        p.current['pods']['metadata']['continue']='next-page'
        p.freeze()
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_INCOMPLETE_ROSTER'):
            p.verify()
        p.current['pods']['metadata'].clear()
        p.freeze()
        p.verify()

    def test_duplicate_provider_node_and_nonexact_pod_toleration_refuse(self):
        p = self.proof
        duplicate = copy.deepcopy(p.data)
        duplicate['metadata'].update(name='duplicate-node',uid=uid(802))
        p.current['nodes']['items'].append(duplicate)
        p.freeze()
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_PROVIDER_NODE_DUPLICATE'):
            p.verify()
        p.current['nodes']['items'].pop()
        p.freeze()
        p.verify()
        spec = {}
        p.bind(spec)
        w.pod_spec(p.value,spec)
        spec['tolerations'][0]['operator']='Exists'
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_POD_TOLERATION'):
            w.pod_spec(p.value,spec)
        p.bind(spec)
        w.pod_spec(p.value,spec)

    def test_unmeasured_autoscaling_cannot_admit(self):
        p = self.proof
        for entry in (p.current['pools'][-1],p.current['clusters'][0]['node_pools'][-1]):
            entry.pop('auto_scale',None)
        p.freeze()
        with self.assertRaisesRegex(ValueError,'OWNED_WORKER_FIXED_POOL'):
            p.verify()
        for entry in (p.current['pools'][-1],p.current['clusters'][0]['node_pools'][-1]):
            entry['auto_scale']=False
        p.freeze()
        p.verify()


class PrivateBoundary(unittest.TestCase):
    originals = {
        'ops/bin/ro':'224cd73465b72c07255a8a56ca788cbb2bb6dcc4d20aed99c598b8a2ae92eeb9',
        'ops/staging-k8s/bin/preflight.py':'42c1f8c3e6fbd539b166ba82e7fb9eeeb1922cf5221e186429d7ba978513aa68',
        'ops/staging-k8s/bin/collect.py':'d9b339ffb0a0238372738017913d9789bdb2002b3b8905dbc3013d92f3d7ce1b',
        'ops/staging-k8s/overlay.libsonnet':'10b70e4070a20e551025c7f8226f879e0f67465ccd5e106d28590dc3069aeec4',
        'prepare-private-case.py':'5e0a23e4b45f8adbd7d4099215c1df3e8168fe8a840ad05077b9676e8d957c10',
    }
    def setUp(self):
        source = os.environ.get('K8S_OWNED_WORKER_SOURCE')
        if not source:
            self.skipTest('exact private commissioner not supplied')
        original = Path(source)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.private = self.root/'private'
        self.stage = self.private/'ops/staging-k8s'
        for name, sha in self.originals.items():
            path = (original.parent if name=='prepare-private-case.py' else original)/name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sha)
            target = self.private/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)
        for name in ('frozen.py','primer_storage.py','phase_fit.py','resource_budget.py'):
            shutil.copyfile(original/'ops/staging-k8s/bin'/name,self.stage/'bin'/name)
        for name in ('owned_worker.py','owned_worker_view.py'):
            shutil.copyfile(HERE/name,self.stage/'bin'/name)
        subprocess.run(['git','apply',str(HERE/'commissioning-owned-worker.patch')],
                       cwd=self.private,check=True,capture_output=True)
        self.proof = Proof(self.root)

    def test_private_preflight_preserves_reserve_and_breaks_on_real_shortfall(self):
        p = self.proof
        env = {**p.environment,'tenantCount':2,'sourceCommit':'6463f24eea02a9e4355d988b1353f238f21d3609',
               'imageDeployCommit':'89ee1bbb654096970788774fbe8d2b52e0bb27e7',
               'bindingCommit':'a'*40,'packageSha256':'b'*64,'imagePullSecret':'synthetic',
               'workDeadlineSeconds':600,'cleanupDeadlineSeconds':900,'imageCacheReserveBytes':2**31,
               'images':{name:'example.invalid/'+name+'@sha256:'+'b'*64 for name in ('app','postgres','nginx','vault')}}
        tree = commissioning.CommissioningAccounting.fixture(SimpleNamespace(env=env))
        for row in tree:
            if row['kind'] in w.WORKLOADS:
                p.bind(row['spec']['template']['spec'])
        rendered, environment = self.root/'render.json',self.root/'environment.json'
        write(rendered,tree)
        write(environment,env)
        command = [sys.executable,'-B',self.stage/'bin/preflight.py','--environment',environment,
                   '--rendered',rendered,'--snapshot',p.after]
        def run():
            result = subprocess.run(command,capture_output=True,text=True,check=False)
            return result.returncode,json.loads(result.stdout)
        rc, result = run()
        self.assertEqual(rc,0,result)
        good = result['workers'][1]
        self.assertTrue(good['trialFits'])
        self.assertEqual(good['reserve']['memory'],.2*16*1024**3)
        self.assertEqual(result['ownedWorkerAdmission']['proof'],p.verify())
        (p.after/'usage.txt').write_text(p.value['nodeName']+' 7 87% 128Mi 1%\n')
        rc, result = run()
        self.assertEqual(rc,3,result)
        self.assertIn('cpu headroom',result['reason'])
        (p.after/'usage.txt').write_text(p.value['nodeName']+' 100m 1% 128Mi 1%\n')
        self.assertEqual(run()[0],0)
        del env[w.FIELD]
        write(environment,env)
        rc, result = run()
        self.assertEqual(rc,0,result)
        self.assertIn('node health/pressure/taint',result['workers'][1]['refusals'])
        p.current['nodes']['items'][1]['spec'].pop('taints')
        p.freeze()
        self.assertTrue(run()[1]['workers'][1]['trialFits'])

    def test_guard_projection_and_public_observer(self):
        c, inventory, rendered, replies = adapter_fixture()
        path = self.root/'adapter-proof'
        path.mkdir()
        p = Proof(path, run=c['runId'],context=c['context'],namespace=c['namespace'])
        for row in rendered + list(replies.objects.values()):
            if row['kind'] in w.WORKLOADS:
                p.bind(row['spec']['template']['spec'])
        for pod in replies.pods:
            pod['kind']='Pod'
            p.bind(pod['spec'])
        c[w.FIELD] = {**p.verify(),'namespaceUid':replies.objects['Namespace/'+c['namespace']]['metadata']['uid']}
        cfg = {**c,'readonlyGuard':str(self.private/'ops/bin/ro')}
        kubectl = self.root/'kubectl'
        node, pods = self.root/'node.json',self.root/'pods.json'
        write(node,p.data)
        write(pods,listing(p.current_pod,*replies.pods))
        kubectl.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
                           f'if "config" in sys.argv: print("synthetic")\n'
                           f'elif "node" in sys.argv: print(Path({str(node)!r}).read_text())\n'
                           f'elif "pods" in sys.argv: print(Path({str(pods)!r}).read_text())\n'
                           f'else: raise SystemExit(7)\n')
        kubectl.chmod(0o700)
        cfg['kubectl'] = str(kubectl)
        # The ordinary guard intentionally redacts a key field.
        from unittest.mock import patch
        with patch.dict(os.environ,{'RO_NO_LOG':'1'}):
            guarded = k.Client(cfg)
            args = ['get','node',p.value['nodeName'],'-o','json']
            self.assertEqual(json.loads(guarded.call(args))['spec']['taints'][0]['key'],'<redacted>')
            self.assertEqual(json.loads(guarded.call(args,owned_worker_view=True))['spec']['taints'][0]['key'],w.LABEL)
            with self.assertRaisesRegex(k.Refused,'OBSERVATION_LOST'):
                guarded.call(['get','nodes','-o','json'],owned_worker_view=True)
            replies.call=guarded.call
            pods_value = listing(p.current_pod,*replies.pods)
            for row in pods_value['items']:
                row['spec'].setdefault('containers', []).append({'name':'private-control','env':[
                    {'name':'SYNTHETIC_SENTINEL','value':'must-not-leave-projection'}]})
            write(pods,pods_value)
            projected = guarded.call(['get','pods','--all-namespaces',
                '--field-selector=spec.nodeName='+p.value['nodeName'],'--chunk-size=0','-o','json'],
                owned_worker_view=True)
            self.assertNotIn(b'must-not-leave-projection',projected)
            for row in pods_value['items']:
                row['spec']['containers'].pop()
            write(pods,pods_value)
            objects=k.manifests(rendered)
            objects={k.key(row):row for row in objects}
            self.assertEqual(k.observe(cfg,objects,replies)[w.FIELD]['namespacePods'],len(replies.pods))
            for taints in ([], p.data['spec']['taints'] + [{'key':'synthetic.other','effect':'NoSchedule'}]):
                modified = copy.deepcopy(p.data)
                modified['spec']['taints'] = taints
                write(node,modified)
                with self.assertRaisesRegex(k.Refused,'OWNED_WORKER_TAINT_OR_CORDON'):
                    k.observe(cfg,objects,replies)
                write(node,p.data)
                self.assertEqual(k.observe(cfg,objects,replies)[w.FIELD]['nodeUid'],p.value['nodeUid'])
            write(pods,listing(p.current_pod,*replies.pods,infra(p.value,99,'foreign')))
            with self.assertRaisesRegex(k.Refused,'OWNED_WORKER_FOREIGN_OR_MISSING_POD'):
                k.observe(cfg,objects,replies)
            write(pods,listing(p.current_pod,*replies.pods))
            self.assertEqual(k.observe(cfg,objects,replies)[w.FIELD]['nodeUid'],p.value['nodeUid'])
