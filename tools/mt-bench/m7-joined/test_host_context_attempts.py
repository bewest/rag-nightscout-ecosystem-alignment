import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import adapter as a
import discovery


class ContextAttempts(unittest.TestCase):
    def test_caller_relative_repository_is_resolved_before_safe_command_cwd(self):
        before=Path.cwd()
        with tempfile.TemporaryDirectory() as name:
            try:
                os.chdir(name)
                with patch.object(a,'command',return_value='synthetic\n') as command:
                    self.assertEqual(a.git('caller-repo','rev-parse','HEAD'),'synthetic')
                    self.assertEqual(command.call_args.args[0][2],Path(name)/'caller-repo')
            finally:os.chdir(before)

    def test_command_has_accessible_deterministic_cwd_and_keeps_explicit_context(self):
        before=Path.cwd()
        with tempfile.TemporaryDirectory() as name:
            p=Path(name)
            try:
                os.chdir(p);p.chmod(0)
                value=a.command([sys.executable,'-c','import os;print(os.getcwd())']).strip()
                self.assertEqual(value,str(a.ROOT))
            finally:
                p.chmod(0o700);os.chdir(before)
            self.assertEqual(a.command([sys.executable,'-c','import os;print(os.getcwd())'],cwd=p).strip(),str(p))
            with self.assertRaises(FileNotFoundError):a.command([sys.executable,'-c','pass'],cwd=p/'missing')

    def test_run_failure_is_preserved_and_retry_refuses_before_work(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);m={'runPurpose':'discovery'}
            def failure(*args):
                a.write(p/'summary.json',{'failure':'synthetic first failure'})
                a.write(p/'run-before-host.json',{'original':'synthetic snapshot'})
                raise RuntimeError('M7_SYNTHETIC_FIRST_FAILURE')
            with patch.object(discovery,'run_discovery',side_effect=failure) as run:
                with self.assertRaisesRegex(RuntimeError,'FIRST_FAILURE'):a.run(p,m,'not-run')
                original={f.name:f.read_bytes() for f in p.iterdir() if f.is_file()}
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError,'RUN_OUTPUT_EXISTS'):a.run(p,m,'not-run')
                self.assertEqual(run.call_count,1)
            self.assertEqual({k:(p/k).read_bytes() for k in original},original)
            self.assertEqual(len(list((p/'attempt-refusals').glob('*/refusal.json'))),2)

    def test_removed_preservation_guard_goes_red_and_restore_green(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);m={'runPurpose':'discovery'};f=p/'summary.json';a.write(f,{'original':True});original=f.read_bytes()
            def overwrite(*args):a.write(f,{'overwritten':True})
            def check():
                try:a.run(p,m,'not-run')
                except RuntimeError as e:self.assertEqual(str(e),'M7_RUN_OUTPUT_EXISTS')
                self.assertEqual(f.read_bytes(),original)
            with patch.object(discovery,'run_discovery',side_effect=overwrite):
                check()
                with patch.object(a,'reserve_output'):
                    with self.assertRaises(AssertionError):check()
                f.write_bytes(original);check()

    def test_repeated_readiness_refuses_without_query_or_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);a.write(p/'runtime-readiness.json',{'verdict':'FAIL','original':True});original=(p/'runtime-readiness.json').read_bytes()
            with patch.object(a,'progress_fetch') as fetch:
                with self.assertRaisesRegex(RuntimeError,'READINESS_OUTPUT_EXISTS'):a.readiness(p,{})
                fetch.assert_not_called()
            self.assertEqual((p/'runtime-readiness.json').read_bytes(),original)

    def test_sampler_uses_absolute_inputs_safe_cwd_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name);out=d/'one attempt';a.write(d/'owner.json',{'project':'synthetic','owner':'a'*32})
            process=SimpleNamespace(pid=123456,wait=lambda **kwargs:0)
            with patch.object(a.subprocess,'Popen',return_value=process) as spawn,patch.object(a,'job_record'),patch.object(a,'stop_job'):
                with a.sampling(d,out):pass
                argv=spawn.call_args.args[0];options=spawn.call_args.kwargs
                self.assertEqual(options['cwd'],d.resolve())
                self.assertEqual(options['env'],a.runtime_env())
                self.assertTrue(all(Path(v).is_absolute() for v in argv[2:6]))
                original=(out/'sampler.log').read_bytes()
                with self.assertRaisesRegex(RuntimeError,'SAMPLER_OUTPUT_EXISTS'):
                    with a.sampling(d,out):pass
                self.assertEqual(spawn.call_count,1)
                self.assertEqual((out/'sampler.log').read_bytes(),original)


if __name__=='__main__':unittest.main()
