"""Known-bad collector stages keep completed evidence and original failures."""
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import adapter as a
import collection_segments as c
import discovery

class Segments(unittest.TestCase):
    def setup_dir(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);return Path(tmp.name)
    def test_late_optional_failure_retains_sql_source_and_failure(self):
        d=self.setup_dir();out=d/'load';out.mkdir()
        owner={'owner':'a'*32,'hostIdentity':'b'*64,'pair':{'core':'c'*40,'deploy':'d'*40},'instrument':{'sha256':'e'*64},'imageId':'sha256:'+'f'*64}
        a.write(d/'owner.json',owner);a.write(d/'frozen.compose.json',{'services':{}})
        failure=RuntimeError('M7_SYNTHETIC_OPTIONAL_FAILURE')
        with patch.object(a,'resources',return_value=[]),patch.object(a,'psql',return_value='synthetic\t1\n'),patch.object(a.cost_companion,'capture',side_effect=failure):a.phase_snapshot(d,out,'after')
        receipt=a.document(out/'after-collection.json');self.assertEqual(receipt['owner'],owner['owner']);self.assertEqual(receipt['pair'],owner['pair']);self.assertEqual(receipt['instrument'],owner['instrument']['sha256'])
        rows={row['kind']:row for row in receipt['segments']}
        self.assertEqual(rows['pg-statements']['status'],'CAPTURED');self.assertIn('after-pg-statements.tsv',rows['pg-statements']['files'])
        self.assertEqual(rows['pg-costs']['status'],'FAILED');self.assertEqual(rows['pg-costs']['code'],'M7_SYNTHETIC_OPTIONAL_FAILURE')
        self.assertTrue((out/'after-realtime-costs.json').is_file());self.assertEqual(a.document(out/'after-pg-costs-failure.json')['status'],'UNMEASURED')
        for row in receipt['segments']:self.assertLessEqual(row['monotonicStartedAtNs'],row['monotonicFinishedAtNs'])
    def test_mandatory_sql_failure_still_raises_exact_object_and_keeps_first_sql(self):
        d=self.setup_dir();out=d/'load';out.mkdir();a.write(d/'owner.json',{})
        failure=RuntimeError('DO_NOT_RETAIN_URL_TOKEN_OR_BODY')
        with patch.object(a,'resources',return_value=[]),patch.object(a,'psql',side_effect=['first-sql\n',failure]):
            with self.assertRaises(RuntimeError) as raised:a.phase_snapshot(d,out,'before')
        self.assertIs(raised.exception,failure);text=(out/'before-collection.json').read_text();self.assertNotIn('DO_NOT_RETAIN',text)
        rows=a.document(out/'before-collection.json')['segments'];self.assertEqual([r['status'] for r in rows],['CAPTURED','CAPTURED','FAILED']);self.assertEqual((out/'before-pg-role.tsv').read_text(),'first-sql\n')
    def test_http_and_probe_published_before_optional_collection(self):
        d=self.setup_dir();out=d/'load';out.mkdir();a.write(out/'k6-summary.json',{'metrics':{'http_reqs':{'count':3},'writes_uncertain':{'count':1}}});a.write(out/'probe.json',{'window':{'deliveredFrames':1}})
        record=types.SimpleNamespace(value={},save=lambda:None);discovery.retain_load(a,d,{},record)
        self.assertEqual(record.value['metrics']['writes_uncertain']['count'],1);self.assertEqual(record.value['probe']['window']['deliveredFrames'],1)
        self.assertEqual(record.value['httpAccounting']['httpVerdict'],'UNMEASURED');self.assertTrue((out/'http-accounting.json').is_file())
        with self.assertRaisesRegex(RuntimeError,'OPTIONAL'):raise RuntimeError('M7_OPTIONAL_FAILURE')
        self.assertEqual(record.value['metrics']['http_reqs']['count'],3)
    def test_actual_pipeline_primary_secondary_and_retention_ablation(self):
        import contextlib
        import test_discovery
        def run(broken=False):
            fixture=test_discovery.Discovery();self.addCleanup(fixture.doCleanups)
            root,m=fixture.setup();m.update(project='synthetic-owned',port=1234,restartRoles=['api'],generator={'tools':{'node':{'path':'node'}}})
            record=discovery.Record(a,root,m)
            primary=RuntimeError('M7_SYNTHETIC_PRIMARY_FAILURE')
            secondary=RuntimeError('M7_SYNTHETIC_SNAPSHOT_FAILURE')
            class Process:
                pid=12345;returncode=0
                def poll(self):return None
                def wait(self,timeout):return 0
            def popen(*args,**kwargs):
                (root/'load/.window').touch();return Process()
            @contextlib.contextmanager
            def context(*args):yield
            def observed(*args):
                a.write(root/'load/k6-summary.json',{'metrics':{'http_reqs':{'count':3},'writes_uncertain':{'count':1}}})
                a.write(root/'load/probe.json',{'window':{'deliveredFrames':1}})
                raise primary
            def snapshot(d,out,name):
                if name in ('after','after-reconnect'):raise secondary
            with contextlib.ExitStack() as stack:
                for name in ('psql','job_record','stop_job','quiet','assert_owned'):stack.enter_context(patch.object(a,name))
                stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']));stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
                stack.enter_context(patch.object(a,'sampling',context));stack.enter_context(patch.object(a,'loadgen_process',context))
                stack.enter_context(patch.object(a,'phase_snapshot',side_effect=snapshot));stack.enter_context(patch.object(a.subprocess,'Popen',side_effect=popen));stack.enter_context(patch.object(discovery,'observed_load',side_effect=observed))
                if broken:stack.enter_context(patch.object(discovery,'retain_load',return_value=None))
                with self.assertRaises(RuntimeError) as raised:discovery.discovery_load(a,root,m,'synthetic',record)
            self.assertIs(raised.exception,primary)
            value=a.document(root/'summary.json')
            self.assertIn('M7_SYNTHETIC_PRIMARY_FAILURE',[row['code'] for row in value['hardFailures']])
            self.assertIn('M7_SYNTHETIC_SNAPSHOT_FAILURE',[row['code'] for row in value['hardFailures']])
            return value
        def criterion(value):
            self.assertEqual(value['metrics']['writes_uncertain']['count'],1)
            self.assertEqual(value['probe']['window']['deliveredFrames'],1)
            self.assertEqual(value['httpAccounting']['httpVerdict'],'UNMEASURED')
        criterion(run())
        with self.assertRaises(KeyError):criterion(run(broken=True))
        criterion(run())

    def test_exact_cleanup_negative_then_restored(self):
        m={'project':'synthetic-owned-project'}
        for kind in ('container','network','volume'):
            with self.subTest(kind=kind),patch.object(a,'resources',return_value=[{'Id':'synthetic'}] if kind=='container' else []),patch.object(a,'command',side_effect=lambda argv:'retained-resource' if argv[1]==kind else ''):
                with self.assertRaisesRegex(RuntimeError,'M7_CLEANUP_'+kind.upper()+'_REMAINS'):a.assert_absent(m)
        with patch.object(a,'resources',return_value=[]),patch.object(a,'command',return_value='') as command:
            self.assertEqual(a.assert_absent(m)['status'],'ABSENT');self.assertEqual(command.call_count,2)
            self.assertTrue(all('label=com.docker.compose.project=synthetic-owned-project' in row.args[0] for row in command.call_args_list))
        with patch.object(a,'resources',return_value=[]),patch.object(a,'command',side_effect=RuntimeError('lowercase no such resource')):
            with self.assertRaisesRegex(RuntimeError,'lowercase'):a.assert_absent(m)
    def test_actual_preflight_format_companion_and_write_cleanup(self):
        d=self.setup_dir();m={'owner':'a'*32,'pair':{'core':'b'*40,'deploy':'c'*40},'instrument':{'sha256':'d'*64},'tenants':2}
        files=['env','probe.js','restart.cjs','k6/workload.js','tenants.private.json','dependencies/package.json','dependencies/package-lock.json']
        for name in files:
            p=d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic')
        a.write(d/'owner.json',m);a.write(d/'frozen.compose.json',{'services':{'synthetic':{}}});(d/'dependencies/node_modules').mkdir()
        self.assertEqual(c.preflight(d,m)['status'],'CHECKED');self.assertEqual(list(d.glob('.collector-write-*')),[])
        (d/'frozen.compose.json').write_text('services:\n  synthetic: {}\n')
        with self.assertRaisesRegex(RuntimeError,'M7_COLLECTION_CONFIG_FORMAT'):c.preflight(d,m)
        a.write(d/'frozen.compose.json',{'services':{'synthetic':{}}});(d/'restart.cjs').unlink()
        with self.assertRaisesRegex(RuntimeError,'M7_COLLECTION_COMPANION_REQUIRED'):c.preflight(d,m)
        (d/'restart.cjs').write_text('synthetic');self.assertEqual(c.preflight(d,m)['status'],'CHECKED')
        # Only the array representation bound remains; exact owner/source and
        # output checks apply equally above the former reference population.
        self.assertEqual(c.preflight(d,{**m,'tenants':12001})['status'],'CHECKED')
        for changed,code in (({**m,'owner':'b'*32},'M7_COLLECTION_OWNER_SOURCE_CHANGED'),({**m,'tenants':2**32},'M7_COLLECTION_ACTOR_BOUND')):
            with self.assertRaisesRegex(RuntimeError,code):c.preflight(d,changed)
        original=Path.open
        def refuse_output(path,*args,**kwargs):
            if path.name.startswith('.collector-write-'):raise PermissionError('private output path')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',refuse_output):
            with self.assertRaises(PermissionError):c.preflight(d,m)
        self.assertEqual(c.preflight(d,m)['status'],'CHECKED')

if __name__=='__main__':unittest.main()
