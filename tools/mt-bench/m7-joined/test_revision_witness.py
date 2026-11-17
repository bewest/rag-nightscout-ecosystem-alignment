import copy
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
import revision_witness as w

class RevisionWitness(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);d=Path(tmp.name)
        for file in w.FILES:
            target=d/'core'/file;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('synthetic source\n')
        (d/'state').mkdir();(d/'load').mkdir()
        targets=d/'targets.json';targets.write_text(json.dumps([{'tenant':'11111111-1111-4111-8111-111111111111','storedId':'synthetic-a'}]))
        config={'services':{role:{'command':['node','deploy/multitenant/entrypoint.js',role]} for role in ('evaluator','realtime')}}
        m={'runPurpose':'discovery','profile':'pgstream-sample','owner':'a'*32,'pair':{'core':'b'*40}}
        return d,targets,config,m
    def test_install_real_files_and_refuse_source_config_mount_or_unrecorded_changes(self):
        d,targets,config,m=self.fixture();w.install(config,d,m,targets);w.verify(config,d,m)
        self.assertEqual(w.probe_environment(d,m),{'M7_REVISION_WITNESS_CONFIG':str(d/'state/revision-witness/client.json')})
        for change in (lambda c:c['services']['realtime']['command'].pop(),lambda c:c['services']['evaluator']['volumes'][0].update(read_only=False)):
            broken=copy.deepcopy(config);change(broken)
            with self.assertRaisesRegex(RuntimeError,'M7_REVISION_'):w.verify(broken,d,m)
        file=d/'core'/w.FILES[0];file.write_text('changed source')
        with self.assertRaisesRegex(RuntimeError,'M7_REVISION_SOURCE_BYTES'):w.verify(config,d,m)
        file.write_text('synthetic source\n');w.verify(config,d,m)
        with self.assertRaisesRegex(RuntimeError,'M7_REVISION_RECORD_REQUIRED'):w.verify(config,d,{})
    def test_actual_preload_rejects_hash_mismatch_before_creating_output(self):
        d,targets,config,m=self.fixture();w.install(config,d,m,targets)
        file=d/'state/revision-witness/client.json';value=json.loads(file.read_text());value['sourceFiles'][w.FILES[0]]='0'*64;file.write_text(json.dumps(value))
        helper=Path(__file__).with_name('revision-witness-preload.cjs')
        result=subprocess.run([shutil.which('node'),'--require',str(helper),'-e','throw Error("MUST_NOT_START")'],env={'M7_REVISION_WITNESS_CONFIG':str(file)},text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('M7_REVISION_SOURCE_BYTES',result.stderr);self.assertNotIn('MUST_NOT_START',result.stderr)
        self.assertEqual(list((d/'load').iterdir()),[])
    def test_preload_restart_produces_distinct_capture_files_without_clobber(self):
        d,targets,config,m=self.fixture();w.install(config,d,m,targets);file=d/'state/revision-witness/client.json';helper=Path(__file__).with_name('revision-witness-preload.cjs')
        for _ in range(2):subprocess.run([shutil.which('node'),'--require',str(helper),'-e','void 0'],env={'M7_REVISION_WITNESS_CONFIG':str(file)},capture_output=True,check=True)
        captures=list((d/'load').glob('revision-witness-client.json.*.json'));self.assertEqual(len(captures),2)
        self.assertEqual(len({json.loads(file.read_text())['instance'] for file in captures}),2)
    def test_target_scope_and_missing_capture_refuse(self):
        d,targets,config,m=self.fixture();m['runPurpose']='capacity'
        with self.assertRaisesRegex(RuntimeError,'M7_REVISION_SCOPE'):w.install(config,d,m,targets)
        m['runPurpose']='discovery';w.install(config,d,m,targets)
        self.assertEqual(w.retain(d,m)['verdict'],'UNMEASURED')

if __name__=='__main__':unittest.main()
