"""Actual Node helper and authored process/sample boundary refusals."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import adapter
import api_warm_cause as warm


class StartupObservation(unittest.TestCase):
    def fixture(self,root):
        (root/'state/api-warm-out').mkdir(parents=True)
        manifest={'owner':'1'*32,'pair':{'core':'2'*40,'deploy':'3'*40},'imageId':'synthetic-image',
                  'instrument':{'sha256':'4'*64},'apiWarmCause':{'binding':{'owner':'1'*32,'sourceSha256':'5'*64}}}
        birth={'id':'6'*64,'startedAt':'synthetic-birth','pid':123}
        sample={'atMs':1500,'heapUsed':100,'rss':200,'heapSizeLimit':1024,'components':[]}
        data={**manifest['apiWarmCause']['binding'],'pid':7,'sampleCount':1,'first':[sample],'samples':[sample]}
        adapter.write(root/'state/api-warm-out/startup-samples.json',data)
        row={'Id':birth['id'],'Image':manifest['imageId'],'Config':{'Labels':{warm.OWNER:manifest['owner']}},
             'State':{'Running':False,'ExitCode':134,'OOMKilled':False,'StartedAt':birth['startedAt'],'Health':{'Status':'unhealthy'}},
             'HostConfig':{'Memory':2048}}
        return manifest,birth,data,row

    def test_actual_node_sampler_keeps_only_counts_and_actual_heap_ceiling(self):
        code="const h=require('./api-warm-cause-preload.cjs');const row=h.startupSample([{health:()=>({readiness:'serve',ready:true,configured:3,warming:1,cold:0,deferred:0,failed:1,alerts:[{tenant:'PRIVATE_TENANT',cause:'PRIVATE_CAUSE'}]})}]);console.log(JSON.stringify(row))"
        raw=subprocess.check_output(['node','-e',code],text=True,cwd=Path(__file__).parent)
        value=json.loads(raw)
        self.assertGreater(value['heapSizeLimit'],value['heapUsed'])
        self.assertEqual(value['components'][0],{'readiness':'serve','ready':True,'configured':3,'warming':1,'cold':0,'deferred':0,'failed':1,'initialized':1})
        self.assertNotIn('PRIVATE_',raw)

    def test_failed_primer_keeps_process_exit_samples_typed_error_before_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,birth,data,row=self.fixture(root)
            (root/'prime.log').write_text(json.dumps({'error':'PRIMER_CONNECTION_FAILED','requestClass':'roles-ready','connectionCause':'ECONNRESET','host':'PRIVATE_HOST'})+'\n')
            fake=types.SimpleNamespace(resources=lambda m:[row],write=adapter.write)
            with patch.object(warm.profile_provenance,'capture_logs',return_value={'rows':[]}):
                warm.collect_startup(fake,root,m,birth,1000,2000,True)
            value=adapter.document(root/'startup-primer-boundary.json')
            self.assertEqual(value['status'],'CAPTURED');self.assertTrue(value['beforeCleanup'])
            self.assertEqual(value['process']['ExitCode'],134);self.assertFalse(value['process']['Running'])
            self.assertEqual(value['containerHealth']['Status'],'unhealthy')
            self.assertEqual(value['primerFailure'],{'error':'PRIMER_CONNECTION_FAILED','requestClass':'roles-ready','connectionCause':'ECONNRESET'})
            self.assertNotIn('PRIVATE_',json.dumps(value))

    def test_foreign_replaced_stale_and_missing_are_unmeasured_then_restored(self):
        for broken in ('foreign','replaced','stale','missing'):
            with self.subTest(broken=broken),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);m,birth,data,row=self.fixture(root)
                data['samples'][0]['atMs']=19500
                original=deepcopy(data);file=root/'state/api-warm-out/startup-samples.json'
                if broken=='foreign':data['owner']='0'*32
                if broken=='replaced':row['State']['StartedAt']='other-birth'
                if broken=='stale':data['samples'][0]['atMs']=1
                adapter.write(file,data)
                if broken=='missing':file.unlink()
                fake=types.SimpleNamespace(resources=lambda m:[row],write=adapter.write)
                warm.collect_startup(fake,root,m,birth,19000,20000,False)
                value=adapter.document(root/'startup-primer-boundary.json')
                self.assertEqual(value['status'],'UNMEASURED')
                self.assertEqual(value['code'],{'foreign':'M7_STARTUP_SAMPLES_FOREIGN','replaced':'M7_API_WARM_RUNTIME_CHANGED','stale':'M7_STARTUP_SAMPLES_STALE','missing':'M7_STARTUP_SAMPLES_REQUIRED'}[broken])
                row['State']['StartedAt']=birth['startedAt'];adapter.write(file,original)
                warm.collect_startup(fake,root,m,birth,19000,20000,False)
                self.assertEqual(adapter.document(root/'startup-primer-boundary.json')['status'],'CAPTURED')

    def test_capture_failure_does_not_replace_primary_primer_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,birth,data,row=self.fixture(root)
            m['apiWarmCause']['mode']=warm.STARTUP_MODE
            row['State'].update(Running=True,Pid=123)
            row['Config']['Cmd']=warm.COMMAND
            row['Config']['Labels']['com.docker.compose.service']='api'
            fake=types.SimpleNamespace(resources=lambda *a,**k:[row],write=adapter.write)
            primary=RuntimeError('M7_PRIMARY_PRIMER')
            with patch.object(warm,'collect_startup',side_effect=OSError('capture unavailable')):
                with self.assertRaisesRegex(RuntimeError,'M7_PRIMARY_PRIMER') as refused:
                    with warm.observe(fake,root,m):raise primary
            self.assertIs(refused.exception,primary)
            self.assertEqual(adapter.document(root/'api-warm-cause.json')['startupCaptureCode'],'M7_STARTUP_CAPTURE_WRITE_FAILED')

    def test_explicit_startup_mode_supports_tiny_fixture_and_bound_config(self):
        args=types.SimpleNamespace(api_warm_cause=warm.STARTUP_MODE,profile='pgstream-sample',run_purpose='discovery',tenants=2,
                                   replicas=1,pgstream_topology='external-service-v1')
        self.assertEqual(warm.option(args),{'apiWarmCauseMode':warm.STARTUP_MODE})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'core'/warm.SOURCE;source.parent.mkdir(parents=True);source.write_text('synthetic source')
            (root/'state').mkdir();m={'owner':'1'*32,'pair':{'core':'2'*40,'deploy':'3'*40},'profile':args.profile,'runPurpose':'discovery','tenants':2}
            config={'services':{'api':{'command':['node','deploy/multitenant/entrypoint.js','api']}}}
            warm.install(config,root,m,warm.STARTUP_MODE)
            self.assertTrue(m['apiWarmCause']['binding']['startupObservation'])
            warm.verify(config,root,m)
            m['apiWarmCause']['binding']['startupObservation']=False
            with self.assertRaisesRegex(RuntimeError,'M7_API_WARM_BINDING'):warm.verify(config,root,m)


if __name__=='__main__':unittest.main()
