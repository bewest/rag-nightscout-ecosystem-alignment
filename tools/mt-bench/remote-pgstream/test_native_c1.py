"""Focused native proof controls with the qualified reader and synthetic rows."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import app
import clinical
import protocol
import transport
from test_discovery_reporting import DiscoveryReporting


class NativeC1(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        data=subprocess.check_output([
            'node','-e',"console.log(JSON.stringify(require(process.argv[1])))",
            app.a.HERE/'native-observation-fixture.cjs'])
        self.fixture=json.loads(data)
        config=self.fixture['config']
        self.manifest={
            'pair':config['binding']['pair'],'imageId':config['binding']['imageId'],
            'instrument':{'sha256':config['binding']['instrument']},
            'completionContract':'evaluator-work-v2','remoteNativeObserver':True,
            'tenants':1,'cadence':{'socketsPerTenant':2},
        }
        (self.root/'load').mkdir()
        (self.root/'load/runid').write_text('synthetic-native')
        protocol.write(self.root/'tenants.private.json',[{'id':self.fixture['row']['tenant']}])
        protocol.write(self.root/'completion-source.json',config)
        protocol.write(self.root/'frozen.compose.json',{'services':{'postgres':{'environment':{'POSTGRES_DB':'native_test'}}}})
        protocol.write(self.root/'load/generator-processes.json',{'k6':0,'probe':0})
        for stage in ('idle','load'):
            (self.root/stage).mkdir(exist_ok=True)
            protocol.write(self.root/stage/'evaluator-progress.json',{'phase':stage,'verdict':'PASS'})

    def completed(self,witness=None,row=None):
        witness=self.fixture['witness'] if witness is None else witness
        row=self.fixture['row'] if row is None else row
        clients=[{**client,'socket':index} for index,client in enumerate(self.fixture['clients'])]
        protocol.write(self.root/'load/probe.json',{'clientWitnesses':[
            {**witness,'acked':True,'clients':clients}]})
        with patch.object(app.a,'psql',return_value=json.dumps(row)) as sql:
            result=clinical.completed(self.root,self.manifest,maximum=0)
            self.assertIn("work_due_at",sql.call_args.args[1])
            self.assertEqual(sql.call_args.args[2],'native_test')
            return result

    def test_native_client_and_source_fail_closed_and_restore(self):
        self.assertEqual(self.completed()['clientFrames']['verdict'],'PASS')
        witness=copy.deepcopy(self.fixture['witness'])
        del witness['sentMono']
        with self.assertRaisesRegex(RuntimeError,'REMOTE_CLINICAL_COMPLETION_UNMEASURED'):
            self.completed(witness=witness)
        detail=app.a.document(self.root/'completed-output.json')
        self.assertEqual(detail['witnesses'][0]['clientFailure'],'M7_CLIENT_CLOCK')
        row=copy.deepcopy(self.fixture['row'])
        del row['native']
        with self.assertRaisesRegex(RuntimeError,'REMOTE_CLINICAL_COMPLETION_UNMEASURED'):
            self.completed(row=row)
        detail=app.a.document(self.root/'completed-output.json')
        self.assertEqual(detail['witnesses'][0]['code'],'M7_COMPLETION_NATIVE_STATE')
        self.assertEqual(self.completed()['verdict'],'PASS')
        file=self.root/'completion-source.json'
        legacy=copy.deepcopy(self.fixture['config'])
        del legacy['native']
        del legacy['binding']['nativeConfigurationSha256']
        protocol.write(file,legacy)
        with patch.object(app.a,'psql') as sql:
            with self.assertRaisesRegex(RuntimeError,'REMOTE_NATIVE_COMPLETION_SOURCE_REQUIRED'):
                self.completed()
            sql.assert_not_called()
        protocol.write(file,self.fixture['config'])
        self.assertEqual(self.completed()['verdict'],'PASS')

    def test_native_reducer_requires_counts_and_clinical_proof(self):
        # Only host readbacks are synthetic here. The reader and SQL row controls
        # above and the retained opportunity verifier exercise their real logic.
        binding=DiscoveryReporting().selected(1)
        binding['helperDependencies']={'profile':protocol.NATIVE_PROFILE}
        observation=dict(verdict='PASS',byTenant={'synthetic':{'nativeInput':{}}},
                         inputCoverage='synthetic',classifications={},writerIntakeCoverage={})
        green={'verdict':'PASS','clientFrames':{'verdict':'PASS'}}
        with ExitStack() as stack:
            for target,name,kwargs in [
                (app.a,'verify',{}),(app,'load',{}),(app.a,'progress_services',{'return_value':['evaluator']}),
                (app.a.evaluator_opportunities,'verify',{'return_value':observation}),
                (clinical,'completed',{'return_value':green}),
            ]:stack.enter_context(patch.object(target,name,**kwargs))
            import discovery
            counts=stack.enter_context(patch.object(discovery,'count_observation',return_value=({'verdict':'GREEN'},True)))
            summary=lambda:app.discovery_summary(self.root,self.manifest,binding,{}, {})
            self.assertEqual(summary()['acceptedWorkAndDue']['load']['verdict'],'PASS')
            counts.return_value=({'verdict':'UNMEASURED'},False)
            with self.assertRaisesRegex(RuntimeError,'REMOTE_NATIVE_WRITER_COUNT_PROOF_REQUIRED'):summary()
            counts.return_value=({'verdict':'GREEN'},True)
            with patch.object(clinical,'completed',side_effect=RuntimeError('REMOTE_CLINICAL_CLIENT_WITNESS_REQUIRED')):
                with self.assertRaisesRegex(RuntimeError,'REMOTE_NATIVE_CLINICAL_PROOF_REQUIRED'):summary()
            (self.root/'load/evaluator-progress.json').unlink()
            with self.assertRaisesRegex(RuntimeError,'REMOTE_NATIVE_OPPORTUNITY_REQUIRED'):summary()
            protocol.write(self.root/'load/evaluator-progress.json',{'phase':'load','verdict':'PASS'})
            self.assertEqual(summary()['verdict'],'PARTIAL')
