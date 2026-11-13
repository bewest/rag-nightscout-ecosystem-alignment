import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tagged_admission import fixture
import tagged_capture as C
import tagged_admission as T


class CaptureDriver(unittest.TestCase):
    def test_fixed_observe_and_exact_cid_inspect_keep_raw_without_lifecycle_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);cli=p/'cli.js';cli.write_text('// fixed synthetic recorder\n')
            state=p/'state';(state/'connection-budget').mkdir(parents=True)
            v=fixture();(state/'connection-budget/plan.json').write_text(json.dumps(v['plan']))
            (state/'connection-budget/ledger.json').write_text(json.dumps(v['ledger']))
            raw={'version':1,'kind':'controlled-connection-observation','hostMonotonic':{'startedNs':'1','finishedNs':'2'},'visibility':'PG_STAT_AUTHENTICATED_ONLY','source':v['expected']['source'],'planSha256':v['plan']['sha256'],
                 'expected':{k:v['expected'][k] for k in ('source','project','workingDirectory','imageId')},'ledger':v['ledger'],**v['census']}
            container=v['processes'][0]['container'];labels={'com.docker.compose.project':container['project'],'com.docker.compose.project.working_dir':container['workingDirectory'],
                 'com.docker.compose.service':'api','org.opencontainers.image.revision':T.CORE,'org.nightscout.deploy.revision':T.DEPLOY}
            inspected=[{'Id':container['cid'],'Image':container['imageId'],'State':{'Running':True,'StartedAt':container['startedAt']},'Config':{'Labels':labels}}]
            spec={'kind':T.KIND,'controllerCli':str(cli),'controllerCliSha256':hashlib.sha256(cli.read_bytes()).hexdigest(),'state':str(state),'expected':v['expected']}
            calls=[]
            def run(argv):
                calls.append(argv)
                return subprocess.CompletedProcess(argv,0,json.dumps(raw if argv[0]=='node' else [{'Id':container['imageId'],'Config':{'Labels':labels}}] if argv[1]=='image' else inspected).encode(),b'')
            result=C.capture(spec,p/'out',run)
            self.assertEqual(calls,[['node',str(cli),str(state),'observe'],['docker','image','inspect',container['imageId']],['docker','inspect',container['cid']]])
            self.assertEqual(result['nativeAcceptance'],'UNMEASURED')
            self.assertEqual(json.loads((p/'out/001.stdout').read_bytes()),raw)
            with self.assertRaises(FileExistsError):C.capture(spec,p/'out',run)
            self.assertEqual(len(calls),3)
            def wrong_image(argv):
                if argv[0]=='docker' and argv[1]=='image':
                    return subprocess.CompletedProcess(argv,0,json.dumps([{'Id':container['imageId'],'Config':{'Labels':{}}}]).encode(),b'')
                return run(argv)
            with self.assertRaisesRegex(ValueError,'IMAGE_SOURCE'):C.capture(spec,p/'bad-image-source',wrong_image)
            def missing(argv):
                return run(argv) if argv[0]=='node' or argv[1]=='image' else subprocess.CompletedProcess(argv,1,b'',b'synthetic inspect failure')
            result=C.capture(spec,p/'unknown',missing)
            self.assertEqual(result['generations'][0]['inspection'],'UNKNOWN')
            self.assertEqual(result['generations'][0]['declaredMaximumHeld'],4)
            self.assertEqual(result['nativeAcceptance'],'UNMEASURED')
            # Recording controls prove global guards act before another effect.
            for field,value in [('MAX_COMMANDS',0),('EPISODE_SECONDS',0),('TOTAL_OUTPUT_BYTES',16)]:
                original=getattr(C,field);setattr(C,field,value);before=len(calls)
                try:
                    with self.assertRaisesRegex(ValueError,'GLOBAL_CAPTURE_BUDGET|COMMAND_CAPTURE_INCOMPLETE'):
                        C.capture(spec,p/field,run)
                    self.assertEqual(len(calls)-before,1 if field=='TOTAL_OUTPUT_BYTES' else 0)
                    if field=='TOTAL_OUTPUT_BYTES':
                        self.assertLessEqual((p/field/'001.stdout').stat().st_size,16)
                        self.assertEqual(json.loads((p/field/'001.json').read_text())['operationOutcome'],'UNKNOWN')
                finally:setattr(C,field,original)
            too_many=copy.deepcopy(v['ledger']);too_many['slots']['api']*=129
            (state/'connection-budget/ledger.json').write_text(json.dumps(too_many));before=len(calls)
            with self.assertRaisesRegex(ValueError,'EPISODE_GENERATION_BOUND'):C.capture(spec,p/'too-many',run)
            self.assertEqual(len(calls),before)

class ActualBoundedChild(unittest.TestCase):
    def test_closed_output_pipes_live_child_keeps_raw_and_unknown_outcome(self):
        import sys
        import time
        started=time.monotonic()
        result=C.bounded_execute([sys.executable,'-c',"import os,time;os.write(1,b'original-out');os.write(2,b'original-err');os.close(1);os.close(2);time.sleep(60)"],{},deadline_seconds=1,exit_wait_seconds=.1)
        self.assertLess(time.monotonic()-started,3)
        self.assertEqual(result.stdout,b'original-out');self.assertEqual(result.stderr,b'original-err')
        self.assertEqual(result.captureFailure,'WAIT_EXIT_TIMEOUT');self.assertEqual(result.operationOutcome,'UNKNOWN')
        self.assertEqual(result.originalFailure,'TimeoutExpired');self.assertEqual(result.returncode,-9)

    def test_capture_persists_failed_actual_child_and_leaves_controller_marker(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);cli=p/'cli.js';cli.write_text('// synthetic pinned child\n')
            state=p/'state';state.mkdir();marker=state/'observer-claim.json';marker.write_text('UNCERTAIN')
            spec={'kind':T.KIND,'controllerCli':str(cli),'controllerCliSha256':hashlib.sha256(cli.read_bytes()).hexdigest(),'state':str(state)}
            def run(argv):
                return C.bounded_execute([sys.executable,'-c',"import os,time;os.write(1,b'original-out');os.write(2,b'original-err');os.close(1);os.close(2);time.sleep(60)"],{},deadline_seconds=1,exit_wait_seconds=.1)
            with self.assertRaisesRegex(ValueError,'COMMAND_CAPTURE_INCOMPLETE'):C.capture(spec,p/'failed',run)
            self.assertEqual((p/'failed/001.stdout').read_bytes(),b'original-out')
            self.assertEqual((p/'failed/001.stderr').read_bytes(),b'original-err')
            record=json.loads((p/'failed/001.json').read_text())
            self.assertEqual(record['captureFailure'],'WAIT_EXIT_TIMEOUT');self.assertEqual(record['operationOutcome'],'UNKNOWN')
            self.assertEqual(record['returnCode'],-9);self.assertEqual(marker.read_text(),'UNCERTAIN')

    def test_actual_output_and_wall_limits_retain_incomplete_captures(self):
        import sys
        cases=[("import os,time;os.write(1,b'x'*65536);time.sleep(60)",'OUTPUT_BOUND',1024,.5),
               ("import time;time.sleep(60)",'TIMEOUT',1024,.1)]
        for script,reason,budget,deadline in cases:
            result=C.bounded_execute([sys.executable,'-c',script],{},deadline_seconds=deadline,exit_wait_seconds=.1,output_bytes=budget)
            self.assertEqual(result.captureFailure,reason);self.assertEqual(result.operationOutcome,'UNKNOWN')
            self.assertLessEqual(len(result.stdout)+len(result.stderr),budget)
            self.assertEqual(result.returncode,-9)

    def test_failed_spawn_has_unknown_direct_exit_and_explicit_failure(self):
        result=C.bounded_execute(['/nonexistent/synthetic-program'],{})
        self.assertIsNone(result.returncode);self.assertEqual(result.operationOutcome,'UNKNOWN')
        self.assertEqual(result.captureFailure,'COMMAND_EXCEPTION');self.assertEqual(result.originalFailure,'FileNotFoundError')


if __name__=='__main__':unittest.main()
