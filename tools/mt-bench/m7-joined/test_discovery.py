"""Recording controls: observational overload cannot become acceptance."""
import contextlib
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import adapter as a
import discovery as d
import evaluator_progress as p
from contract import oracle

class Discovery(unittest.TestCase):
    def setup(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);folder=Path(t.name)
        m={'pair':{'core':'a'*40,'deploy':'b'*40},'hostIdentity':'c'*64,'instrument':{'sha256':'d'*64},'imageId':'sha256:'+'e'*64,'owner':'f'*32,'tenants':2,'replicas':1,'profile':'remote-pilot','cadence':{'idleSeconds':120,'loadSeconds':300},'generator':{},'profileSelection':__import__('test_contract').PROFILE,'settingsFingerprint':{'schema':1,'sha256':'f'*64,'sourceCommit':'a'*40,'sourceBlobs':{}}}
        return folder,m
    def test_purpose_defaults_and_strict_path_do_not_route_discovery(self):
        args=a.parser().parse_args(['prepare','--directory','/tmp/new','--core-repo','/tmp/core','--core-commit','a'*40,'--deploy-repo','/tmp/deploy','--deploy-commit','b'*40,'--image','image','--freeze','/tmp/freeze','--tenants','500','--replicas','1'])
        self.assertEqual(args.run_purpose,'acceptance')
        with patch.object(a,'run_cell',side_effect=p.Refused('M7_EVALUATOR_IDLE_JOB_PENDING')) as strict,patch.object(d,'run_discovery') as discovery:
            with self.assertRaisesRegex(p.Refused,'JOB_PENDING'):a.run(Path('/tmp/synthetic'),{},'k6')
            strict.assert_called_once();discovery.assert_not_called()
    def run_recording(self,error):
        folder,m=self.setup();(folder/'deploy-before-host.json').write_text('{}');calls=[]
        def load(*args):
            calls.append('load');r=args[-1];r.value.update(oracle={'verdict':'GREEN'},probe={'restart':{},'window':{'deliveredFrames':0,'expectedFrames':100}},settingsFingerprintObservation={'verdict':'PASS'},processes={'k6':{'returncode':0},'probe':{'returncode':0}})
            r.value['strictChecks']['httpErrors']={'verdict':'FAIL','hardFailure':False};r.save()
        with contextlib.ExitStack() as stack:
            for key in ('frozen','quiet','verify','image','verify_generator','readiness','psql','phase_snapshot'):stack.enter_context(patch.object(a,key))
            stack.enter_context(patch.object(a.time,'sleep'));stack.enter_context(patch.object(a,'command',return_value='[{"Id":"sha256:synthetic"}]'))
            stack.enter_context(patch.object(a,'enabled_idle',side_effect=error));stack.enter_context(patch.object(d,'discovery_load',side_effect=load));stack.enter_context(patch('reduce.measurements',return_value={'complete':True}))
            if d.incomplete(error):result=d.run_discovery(a,folder,m,'k6')
            else:
                with self.assertRaises(type(error)):d.run_discovery(a,folder,m,'k6')
                result=a.document(folder/'summary.json')
        return result,calls,folder
    def test_idle_unmeasured_still_invokes_load_and_cannot_claim_acceptance(self):
        result,calls,_=self.run_recording(p.Refused('M7_EVALUATOR_IDLE_JOB_PENDING'))
        self.assertEqual(calls,['load']);self.assertEqual(result['status'],'MEASURED');self.assertEqual(result['strictChecks']['idle']['verdict'],'UNMEASURED');self.assertEqual(result['capacityAcceptance'],'NOT_GRANTED');self.assertNotIn('verdict',result);d.check_discovery(result)
    def test_known_foreign_reset_and_clinical_fail_refuse_before_load(self):
        for code in ('M7_EVALUATOR_PROGRESS_FOREIGN','M7_EVALUATOR_PROGRESS_RESET','M7_EXPLICIT_UNSAFE_CLINICAL_OUTPUT'):
            result,calls,_=self.run_recording(p.Refused(code,'FAIL'));self.assertEqual(calls,[]);self.assertEqual(result['hardFailures'][0]['code'],code)
            with self.assertRaisesRegex(RuntimeError,'HARD_FAILURE'):d.check_discovery(result)
    def test_failed_completion_counter_is_preserved_but_not_unsafe_output_claim(self):
        result,calls,_=self.run_recording(p.Refused('M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE','FAIL'))
        self.assertEqual(calls,['load']);self.assertEqual(result['strictChecks']['idle']['verdict'],'FAIL');self.assertFalse(result['strictChecks']['idle']['hardFailure']);d.check_discovery(result)

    def test_count_bounds_preserve_ambiguous_writes_but_reject_corruption(self):
        metrics={'writes_ok':{'count':1},'writes_ok{tenant:a}':{'count':1},'writes_uncertain{tenant:a}':{'count':1},'writes_ok{kind:entries}':{'count':1}}
        self.assertEqual(oracle({'a':{'entries':2}},metrics,{},[{'id':'a'}],allow_empty=True)['verdict'],'GREEN')
        self.assertEqual(oracle({'a':{'entries':3}},metrics,{},[{'id':'a'}],allow_empty=True)['verdict'],'RED')
        with self.assertRaisesRegex(RuntimeError,'TENANT_SCOPE'):oracle({'foreign':{}},metrics,{},[{'id':'a'}],allow_empty=True)
        self.assertEqual(oracle({}, {}, {}, [{'id':'a'}],allow_empty=True)['verdict'],'GREEN')
        with self.assertRaisesRegex(RuntimeError,'NO_ACCEPTED_WRITES'):oracle({}, {}, {}, [{'id':'a'}])
    def test_actual_k6_crash_records_direct_nonzero_and_partial(self):
        folder,m=self.setup();r=d.Record(a,folder,m)
        error=RuntimeError('M7_COMMAND_FAILED:docker');error.returncode=139
        self.assertIsNone(r.process('k6',lambda:(_ for _ in ()).throw(error)))
        value=a.document(folder/'summary.json');self.assertEqual(value['processes']['k6']['returncode'],139);self.assertEqual(value['status'],'PARTIAL');self.assertEqual(value['strictChecks']['k6']['verdict'],'UNMEASURED')
    def test_entering_load_observer_unavailable_does_not_skip_load(self):
        events=[]
        class Observe:
            def __enter__(self):raise p.Refused('M7_EVALUATOR_PROGRESS_UNAVAILABLE')
        with patch.object(a,'observe_progress',return_value=Observe()):
            with self.assertRaisesRegex(p.Refused,'UNAVAILABLE'):d.observed_load(a,None,None,None,lambda:events.append('load'))
        self.assertEqual(events,['load'])
    def test_after_bookend_and_recovery_on_nonobserved_load_are_preserved(self):
        folder,m=self.setup();m.update(project='owned',port=1234,restartRoles=['api'],settingsFingerprint={'sha256':'a'*64},generator={'tools':{'node':{'path':'node'}}})
        record=d.Record(a,folder,m);events=[]
        class Process:
            pid=12345;returncode=0
            def poll(self):return None
            def wait(self,timeout):events.append('wait');return 0
        def popen(*args,**kwargs):
            self.assertIs(kwargs['start_new_session'],True);(folder/'load/.window').touch();return Process()
        @contextlib.contextmanager
        def ctx(*args):yield
        def observed(*args):events.append('load');raise p.Refused('M7_EVALUATOR_PROGRESS_NOT_OBSERVED')
        with contextlib.ExitStack() as stack:
            for name in ('psql','job_record','stop_job'):stack.enter_context(patch.object(a,name))
            stack.enter_context(patch.object(a,'quiet'));stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']));stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
            stack.enter_context(patch.object(a,'sampling',ctx));stack.enter_context(patch.object(a,'loadgen_process',ctx));stack.enter_context(patch.object(a,'assert_owned',side_effect=lambda *args:events.append('custody')))
            stack.enter_context(patch.object(a,'phase_snapshot',side_effect=lambda d,o,name:events.append(name)));stack.enter_context(patch.object(a.subprocess,'Popen',side_effect=popen));stack.enter_context(patch.object(d,'observed_load',side_effect=observed))
            d.discovery_load(a,folder,m,'k6',record)
        self.assertLess(events.index('load'),events.index('after'));self.assertLess(events.index('after'),events.index('custody'));self.assertIn('wait',events);self.assertIn('after-reconnect',events)
    def test_probe_ends_without_window_still_runs_http_and_keeps_probe_counts_unknown(self):
        folder,m=self.setup();m.update(project='owned',port=1234,restartRoles=['api'],settingsFingerprint={'sha256':'a'*64},generator={'tools':{'node':{'path':'node'}}})
        a.write(folder/'tenants.private.json',[{'id':'a'},{'id':'b'}]);record=d.Record(a,folder,m);events=[]
        class Process:
            pid=12345;returncode=7
            def poll(self):return 7
            def wait(self,timeout):return 7
        @contextlib.contextmanager
        def ctx(*args):yield
        def command(argv,**kwargs):
            events.append('k6');a.write(folder/'load/k6-summary.json',{'metrics':{}})
        with contextlib.ExitStack() as stack:
            for name in ('psql','job_record','stop_job','quiet','assert_owned','phase_snapshot'):stack.enter_context(patch.object(a,name))
            stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']));stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
            for name in ('sampling','loadgen_process','observe_progress'):stack.enter_context(patch.object(a,name,ctx))
            stack.enter_context(patch.object(a.subprocess,'Popen',return_value=Process()));stack.enter_context(patch.object(a,'command',side_effect=command));stack.enter_context(patch.object(a,'stored',return_value={}))
            d.discovery_load(a,folder,m,'k6',record)
        self.assertEqual(events,['k6']);self.assertFalse((folder/'load/.restart').exists());self.assertEqual(record.value['processes']['probe']['returncode'],7)
        self.assertIsNone(record.value['oracle']);self.assertEqual(record.value['oracleFindings']['probeCountProof'],'UNMEASURED');self.assertEqual(record.value['status'],'PARTIAL');self.assertEqual(record.value['capacityAcceptance'],'NOT_GRANTED')

    def fingerprint_collection(self,kind,corrupt=False):
        folder,m=self.setup();m.update(project='owned',port=1234,restartRoles=['api'],generator={'tools':{'node':{'path':'node'}}})
        a.write(folder/'deploy-before-host.json',{});a.write(folder/'tenants.private.json',[{'id':'a'},{'id':'b'}]);events=[]
        metrics={'writes_ok':{'count':2},'writes_ok{tenant:a}':{'count':1},'writes_ok{tenant:b}':{'count':1},'writes_uncertain{tenant:a}':{'count':0},'writes_uncertain{tenant:b}':{'count':0},'writes_ok{kind:entries}':{'count':2},'writes_ok{kind:devicestatus}':{'count':0},'writes_ok{kind:treatments}':{'count':0},'settings_fingerprint_observed':{'count':1 if kind=='mismatch' else 0},'settings_fingerprint_'+kind:{'count':1}}
        class Process:
            pid=12345;returncode=0
            def poll(self):return None
            def wait(self,timeout):return 0
        def popen(*args,**kwargs):
            out=folder/'load';(out/'.window').touch();a.write(out/'probe.json',{'restart':{'runtimeAcquisitionObservation':{'verdict':'PASS'}}});return Process()
        def command(argv,**kwargs):
            if argv[:3]==['docker','image','inspect']:return '[{"Id":"sha256:recording"}]'
            a.write(folder/'load/k6-summary.json',{'metrics':metrics});a.write(folder/'load/fanout.json',{'probeWrites':{'byTenant':{}}});a.write(folder/'load/probe-accounting.json',{'version':2,'kind':'m7-discovery-probe-accounting','runId':'m7-'+m['owner'][:12],'roster':['a','b'],'admissionsClosed':True,'attempts':0,'byTenant':{}});events.append('k6')
        def stored(*args):events.append('counts');return {'a':{'entries':2 if corrupt else 1},'b':{'entries':1}}
        def reduced(*args):events.append('measurements');return {'complete':True,'scope':'recording-only'}
        @contextlib.contextmanager
        def ctx(*args):yield
        with contextlib.ExitStack() as stack:
            for name in ('frozen','quiet','verify','image','verify_generator','readiness','psql','phase_snapshot','enabled_idle','job_record','stop_job','assert_owned'):stack.enter_context(patch.object(a,name))
            stack.enter_context(patch.object(a.time,'sleep'));stack.enter_context(patch.object(a,'command',side_effect=command));stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']));stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
            for name in ('sampling','loadgen_process','observe_progress'):stack.enter_context(patch.object(a,name,ctx))
            stack.enter_context(patch.object(a.subprocess,'Popen',side_effect=popen));stack.enter_context(patch.object(a,'stored',side_effect=stored));stack.enter_context(patch('reduce.measurements',side_effect=reduced))
            with self.assertRaisesRegex(RuntimeError,'M7_DISCOVERY_WRONG_DATA' if corrupt else 'M7_FUNCTIONAL_SETTINGS_FINGERPRINT'):d.run_discovery(a,folder,m,'k6')
        value=a.document(folder/'summary.json');self.assertEqual(events,['k6','counts','measurements']);self.assertTrue(value['measurements']['complete']);self.assertTrue((folder/'load/stored-counts.json').is_file())
        if corrupt:
            self.assertIsNone(value['oracle']);self.assertEqual(value['oracleFindings']['verdict'],'RED');self.assertEqual(value['strictChecks']['collection']['verdict'],'FAIL');self.assertGreater(value['countDiagnostics']['failureCount'],0);self.assertLessEqual(len(value['countDiagnostics']['failures']),64);self.assertEqual(value['hardFailures'][-1]['code'],'M7_DISCOVERY_WRONG_DATA')
        else:
            self.assertEqual(value['oracle']['verdict'],'GREEN');self.assertEqual(value['settingsFingerprintObservation']['verdict'],'FAIL');self.assertEqual(value['hardFailures'][-1]['code'],'M7_FUNCTIONAL_SETTINGS_FINGERPRINT')
    def test_count_failure_retains_actual_findings_and_existing_resource_reducer(self):self.fingerprint_collection('invalid',corrupt=True)
    def test_fingerprint_invalid_retains_existing_counts_and_measurements_before_refusal(self):self.fingerprint_collection('invalid')
    def test_fingerprint_mismatch_retains_existing_counts_and_measurements_before_refusal(self):self.fingerprint_collection('mismatch')

    def test_timeout_stops_only_exact_owned_k6_before_recovery(self):
        folder,m=self.setup();record=d.Record(a,folder,m);record.value['processes']['k6']={'timeout':True,'returncode':None}
        row={'Id':'1'*64,'Config':{'Labels':{a.OWNER:m['owner'],'com.docker.compose.service':'k6'}}}
        with patch.object(a,'assert_owned'),patch.object(a,'resources',return_value=[row]),patch.object(a,'command') as command:
            d.stop_k6(a,m,record);self.assertEqual(command.call_args.args[0],['docker','stop','--time','10','1'*64])
            row['Config']['Labels'][a.OWNER]='0'*32;command.reset_mock()
            with self.assertRaisesRegex(RuntimeError,'RESOURCE_NOT_OWNED'):d.stop_k6(a,m,record)
            command.assert_not_called()

    def test_actual_generated_probe_recording_ports_and_prime_guard_ablation(self):
        from probe import generate
        folder,_=self.setup();file=folder/'probe.js';generate(a.ROOT,file)
        control=a.HERE/'discovery-probe-control.cjs'
        result=subprocess.run(['node',str(control),str(file)],capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['controls'],6)
        original=file.read_text();self.assertEqual(original.count('!discovery&&out.prime.primed'),1)
        try:
            file.write_text(original.replace('!discovery&&out.prime.primed','out.prime.primed'))
            broken=subprocess.run(['node',str(control),str(file)],capture_output=True,text=True,timeout=5)
            self.assertNotEqual(broken.returncode,0);self.assertIn('AssertionError',broken.stderr)
        finally:file.write_text(original)
        self.assertEqual(subprocess.run(['node',str(control),str(file)],capture_output=True,timeout=5).returncode,0)
    def test_missing_ack_fields_are_unmeasured_known_wrong_rows_still_refuse(self):
        folder,_=self.setup();out=folder/'load';out.mkdir();a.write(folder/'tenants.private.json',[{'id':'a'}])
        with patch.object(a,'stored',return_value={'a':{'entries':5}}):
            value,known=d.count_observation(a,folder,out,'synthetic',{})
            self.assertFalse(known);self.assertEqual(value['verdict'],'UNMEASURED')
            with self.assertRaisesRegex(RuntimeError,'WRONG_DATA'):d.count_observation(a,folder,out,'synthetic',{'writes_ok{tenant:a}':{'count':1},'writes_uncertain{tenant:a}':{'count':0}})
        with patch.object(a,'stored',return_value={'foreign':{'entries':1}}):
            with self.assertRaisesRegex(RuntimeError,'TENANT_SCOPE'):d.count_observation(a,folder,out,'synthetic',{})

    def test_aggregate_requires_matching_identity_and_no_acceptance_label(self):
        result,_,_=self.run_recording(p.Refused('M7_EVALUATOR_IDLE_JOB_PENDING'));aggregate={**{k:result[k] for k in ('version','pair','hostIdentity','instrument','imageId','runPurpose','status','capacityAcceptance','profileSelection')},'kind':'m7-joined-discovery','cells':[result]};d.check_discovery(aggregate)
        broken=copy.deepcopy(aggregate);broken['cells'][0]['instrument']='0'*64
        with self.assertRaisesRegex(RuntimeError,'MIXED_IDENTITY'):d.check_discovery(broken)
        broken=copy.deepcopy(aggregate);broken['capacityAcceptance']='PASS'
        with self.assertRaisesRegex(RuntimeError,'SHAPE'):d.check_discovery(broken)

if __name__=='__main__':unittest.main()
