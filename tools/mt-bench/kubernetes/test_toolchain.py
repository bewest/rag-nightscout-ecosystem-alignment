import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import toolchain as t
import jobs

class Toolchain(unittest.TestCase):
    def manifest(self):
        p=json.loads((t.k.HERE/'workloads/realistic-500.json').read_bytes());p.pop('referencePins')
        return dict(version=1,kind='multitenant-experiment',application=dict(sourceReceipt={},buildReceipt={},bindingCommit='3'*40,postgresImageId='sha256:'+'4'*64),
                    profile=p,topology=dict(apiReplicas=1,evaluatorWorkers=1,pgstreamTopology='external'),
                    local=dict(k6Image='sha256:'+'5'*64,prepare=dict(profile='pgstream-sample',**{'run-purpose':'discovery','completion-contract':'evaluator-work-v2'})))
    def test_one_intent_projects_scales_and_refuses_topology_or_second_fact(self):
        selected=dict(coreCommit='1'*40,deployCommit='2'*40,localImageId='sha256:'+'6'*64,sourceAcceptance='PENDING')
        with patch.object(t.frozen,'source',return_value=selected):
            for n in (500,1000,3000,10000):
                m=self.manifest();m['profile']['population'].update(provisionedTenants=n,ordinaryRosterTenants=n)
                m['profile']['workload']['logicalPollingClients']=n
                local=t.local(m,dict(prepare={}));remote=t.legacy(m)
                self.assertEqual(local['prepare']['tenants'],remote['profile']['population']['provisionedTenants'])
                self.assertEqual(local['prepare']['logical-polling-clients'],n)
                self.assertEqual(local['prepare']['pgstream-topology'],'external-service-v1')
            m=self.manifest();m['topology']['evaluatorWorkers']=2
            with self.assertRaisesRegex(ValueError,'KUBERNETES_TOPOLOGY_UNSUPPORTED'):t.legacy(m)
            print('RED_RESTORED unsupported K2; K1 restored')
            m=self.manifest();m['local']['prepare']['tenants']=2
            with self.assertRaisesRegex(ValueError,'DUPLICATE_LOCAL_FACT'):t.local(m,dict(prepare={}))
            print('RED_RESTORED duplicate workload fact')
            m=self.manifest();m['application']['bootstrapHelper']={}
            with self.assertRaisesRegex(ValueError,'LOCAL_BOOTSTRAP_HELPER_UNSUPPORTED'):t.local(m,dict(prepare={}))
            self.assertNotIn('bootstrapHelper',t.local(self.manifest(),dict(prepare={}))['prepare'])
            print('RED_RESTORED transport-specific helper scope')

    def test_discovery_api_topology_semantics_preserve_native_execution_boundary(self):
        selected=dict(coreCommit='1'*40,deployCommit='2'*40,localImageId='sha256:'+'6'*64,sourceAcceptance='PENDING')
        with patch.object(t.frozen,'source',return_value=selected):
            for count in (3,16):
                m=self.manifest();m['topology']['apiReplicas']=count
                m['application']['buildReceipt']={'path':'/synthetic/build.json','sha256':'a'*64}
                local=t.local(m,dict(prepare={}))
                self.assertEqual(local['prepare']['replicas'],count)
                self.assertEqual(local['prepare']['static-workers'],1)
                with self.assertRaisesRegex(ValueError,'KUBERNETES_TOPOLOGY_UNSUPPORTED'):t.legacy(m)
            for count in (0,17,True):
                m=self.manifest();m['topology']['apiReplicas']=count
                with self.assertRaisesRegex(ValueError,'TOPOLOGY'):t.legacy(m,'compose')

    def test_shared_primer_selections_project_once(self):
        selected=dict(coreCommit='1'*40,deployCommit='2'*40,localImageId='sha256:'+'6'*64,sourceAcceptance='PENDING')
        m=self.manifest()
        selection={'concurrency':64,'maxTenants':20000}
        m['profile']['phases']['primerOptions']=selection
        with patch.object(t.frozen,'source',return_value=selected):
            projected=t.local(m,dict(prepare={}))['prepare']
            self.assertEqual((projected['primer-concurrency'],projected['primer-max-tenants']),(64,20000))
            self.assertEqual(t.legacy(m)['profile']['phases']['primerOptions'],selection)
            m['local']['prepare']['primer-concurrency']=64
            with self.assertRaisesRegex(ValueError,'DUPLICATE_LOCAL_FACT'):t.local(m,dict(prepare={}))
    def test_job_actual_tool_identity_and_changed_projection_refuse_then_restore(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'ns-job-offline-config').mkdir();(p/'ns-job-offline-request').mkdir()
            def put(n,v):(p/n).write_text(json.dumps(v))
            cfg=dict(adminOrigin='http://admin:1342',platformVerification=dict(namespace='synthetic',roles=['api','evaluator','realtime']))
            put('ns-job-offline-config/config.json',cfg);put('ns-job-offline-request/request.json',{});put('render.json',{})
            r=dict(toolCommit='1'*40,applicationImageId='sha256:'+'2'*64,coreCommit='3'*40,applicationDeploy='4'*40,lockSha256='5'*64,producerSha256='6'*64,localImageId='sha256:'+'7'*64)
            put('tool.json',r);ref={'path':str(p/'tool.json'),'sha256':jobs.sha(p/'tool.json')}
            plan=dict(command='verification-plan',target='compose',tools=r,toolReceipt=ref,renderSha256=jobs.sha(p/'render.json'),requestSha256=jobs.sha(p/'ns-job-offline-request/request.json'),configSha256=jobs.sha(p/'ns-job-offline-config/config.json'));put('plan.json',plan)
            src={k:r[k] for k in ('toolCommit','applicationImageId','coreCommit','applicationDeploy','lockSha256','producerSha256')}
            caps=dict(result='ok',operations=jobs.OPERATIONS,source=src)
            result=dict(result='ok',source=src,namespace='synthetic',roles=cfg['platformVerification']['roles'])
            with patch.object(jobs.subprocess,'check_output',return_value=json.dumps({**caps,'source':{**src,'coreCommit':'9'*40}}).encode()):
                with self.assertRaisesRegex(ValueError,'ACTUAL_TOOL_IMAGE_CHANGED'):jobs.offline(p)
            print('RED_RESTORED actual wrong tool source')
            put('ns-job-offline-config/config.json',{**cfg,'adminOrigin':'http://changed:1342'})
            with patch.object(jobs.subprocess,'check_output') as run:
                with self.assertRaisesRegex(ValueError,'PLAN_CHANGED'):jobs.offline(p)
                run.assert_not_called()
            put('ns-job-offline-config/config.json',cfg)
            with patch.object(jobs.subprocess,'check_output',side_effect=[json.dumps(caps).encode(),json.dumps(result).encode()]):
                self.assertEqual(jobs.offline(p)['result'],'ok')
            print('RED_RESTORED changed job config')

if __name__=='__main__':unittest.main()
