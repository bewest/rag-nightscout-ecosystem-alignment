"""Actual runner stage -> fresh adapter entrypoint; inert application ports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import adapter as a
import runner
import workload_inputs


class ProcessDeadline(unittest.TestCase):
    def entry(self, directory):
        entry = directory/'adapter.py'
        entry.write_text('import sys,json\n'
                         'from pathlib import Path\n'
                         f'sys.path.insert(0,{str(Path(a.__file__).parent)!r})\n'
                         'import adapter as a\n'
                         'a.load=lambda *args,**kwargs:(Path(args[0]),{"runPurpose":"discovery","evaluatorCatchup":"fixed-target-v1"})\n'
                         'a.run=lambda *args,**kwargs:print(json.dumps({"childDeadline":a._COMMAND_DEADLINE.get()}))\n'
                         'a.deploy=a.run; a.preflight=a.run\n'
                         'try:a.main()\n'
                         'except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)\n')
        return entry

    def test_real_stage_transmits_original_deadline_to_fresh_adapter_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);self.entry(directory)
            deadline=time.time()+10
            a.write(directory/'execution.json',{'owner':'synthetic-owner','stopWorkAt':deadline,'cleanupAt':deadline+60})
            with mock.patch.object(runner,'HERE',directory):
                runner.stage(directory,'run',['run',str(directory/'fixture'),'--k6-image','synthetic'])
            value=json.loads((directory/'run.private.log').read_text())
            self.assertEqual(value['childDeadline'],deadline)
            self.assertEqual(a.document(directory/'stage-job.json')['returncode'],0)
            self.assertIsNone(a._COMMAND_DEADLINE.get(),'child context must not mutate parent')

    def test_deploy_and_preflight_children_receive_aged_original_cutoff(self):
        for name in ('deploy','preflight'):
            with self.subTest(stage=name),tempfile.TemporaryDirectory() as temporary:
                directory=Path(temporary);self.entry(directory)
                cutoff=time.time()+7
                a.write(directory/'execution.json',{'owner':'synthetic-owner','stopWorkAt':cutoff,'cleanupAt':cutoff+60})
                args=[name,str(directory/'fixture')]+(['--k6-image','synthetic'] if name=='preflight' else [])
                with mock.patch.object(runner,'HERE',directory):runner.stage(directory,name,args)
                value=json.loads((directory/(name+'.private.log')).read_text().splitlines()[0])
                self.assertEqual(value['childDeadline'],cutoff)

    def test_deploy_and_preflight_refuse_expired_nonfinite_and_overglobal_cutoffs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);entry=self.entry(directory)
            for stage in ('deploy','preflight'):
                argv=[sys.executable,'-B',str(entry),stage,str(directory/'fixture')]
                if stage=='preflight':argv+=['--k6-image','synthetic']
                original=time.time()+11000
                accepted=subprocess.run([*argv,'--work-deadline',str(original)],capture_output=True,text=True,timeout=5,check=True)
                self.assertEqual(json.loads(accepted.stdout.splitlines()[0])['childDeadline'],original)
                for until in ('0','nan','inf',str(time.time()+workload_inputs.MAX_SECONDS+60)):
                    result=subprocess.run([*argv,'--work-deadline',until],capture_output=True,text=True,timeout=5)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('M7_COMMAND_DEADLINE',result.stderr)
                    self.assertNotIn('childDeadline',result.stdout)

    def test_missing_false_and_nonfinite_deadlines_refuse_before_application_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);entry=self.entry(directory)
            for suffix,code in [([], 'M7_DRAIN_WORK_DEADLINE_REQUIRED'),
                                (['--work-deadline','0'], 'M7_COMMAND_DEADLINE'),
                                (['--work-deadline','nan'], 'M7_COMMAND_DEADLINE')]:
                result=subprocess.run([sys.executable,str(entry),'run',str(directory/'fixture'),'--k6-image','synthetic',*suffix],capture_output=True,text=True,timeout=5)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(code,result.stderr)
                self.assertNotIn('childDeadline',result.stdout)


if __name__=='__main__':unittest.main()
