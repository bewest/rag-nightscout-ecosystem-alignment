"""Real finite process cleanup and retained native-summary handling; no app actors."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from contextlib import ExitStack
import adapter
import runner

class Runner(unittest.TestCase):
    def test_execution_reaches_traffic_with_optional_gap_but_not_failed_native_preflight(self):
        for native_failure in (False, True):
            with self.subTest(native_failure=native_failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp);d = root / 'fixture'
                folder = d / 'setup-attempts/one';folder.mkdir(parents=True)
                adapter.write(folder / 'readability-realtime-costs.json', {'status': 'NO-INSTRUMENT'})
                adapter.write(root / 'result.json', {'status': 'PREPARED'})
                calls = []
                def stage(root, name, args):
                    calls.append(name)
                    if native_failure and name == 'preflight':
                        raise RuntimeError('M7_SAMPLE_LOADGEN_CONTEXT')
                def launch(*args, **kwargs):
                    (root / 'guard-ready.json').touch()
                    return Mock(poll=Mock(return_value=None))
                with ExitStack() as stack:
                    stack.enter_context(patch.object(runner, 'load_config', return_value=({'workSeconds': 30, 'cleanupSeconds': 30, 'k6Image': 'synthetic'}, [])))
                    stack.enter_context(patch.object(adapter, 'load', return_value=(d, {'owner': 'synthetic'})))
                    stack.enter_context(patch.object(adapter, 'job_record'))
                    stack.enter_context(patch.object(adapter, 'digest', return_value='synthetic'))
                    stack.enter_context(patch.object(runner.subprocess, 'Popen', side_effect=launch))
                    stack.enter_context(patch.object(runner, 'stage', side_effect=stage))
                    stack.enter_context(patch.object(runner, 'cleanup'))
                    # Preparation arms the bounded guard; isolate optional observations
                    # from the separately exercised finite-window/cleanup contract.
                    stack.enter_context(patch.object(runner, 'execution_window', return_value={}))
                    stack.enter_context(patch.object(runner, 'guard_alive', return_value=False))
                    if native_failure:
                        with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_POINT_INCOMPLETE'):
                            runner.execute(root)
                        self.assertEqual(calls, ['deploy', 'preflight'])
                        self.assertEqual(adapter.document(root / 'result.json')['failure']['code'], 'M7_SAMPLE_LOADGEN_CONTEXT')
                    else:
                        result = runner.execute(root)
                        self.assertEqual(calls, ['deploy', 'preflight', 'run'])
                        self.assertEqual(result['capacityAcceptance'], 'NOT_GRANTED')
                        self.assertEqual(adapter.document(root / 'preflight-observations.json')['realtimeCosts']['status'], 'NO-INSTRUMENT')

    def test_generated_control_preserves_selected_typed_profile(self):
        for selected in (adapter.diagnostic_resources.NAME,adapter.diagnostic_resources.EXTERNAL_NAME):
            with self.subTest(selected=selected),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);manifest={'diagnosticResources':{'profile':selected},'generator':{'tools':{'node':{'path':'node'}}}}
                def node(*args,**kwargs):
                    kwargs['stdout'].write(b'ERR_INVALID_URL');return Mock(returncode=1)
                from contextlib import nullcontext
                with patch.object(adapter.diagnostic_resources,'configure') as configure, patch.object(adapter.diagnostic_resources,'command',return_value=nullcontext((['node'],{}))),patch.object(runner.subprocess,'run',side_effect=node),patch.object(adapter,'digest',return_value='synthetic'):
                    runner.generated_control(root,root,manifest)
                self.assertEqual(configure.call_args_list[0].args,(selected,))
                self.assertEqual(configure.call_args_list[-1].args,())

    def test_optional_counter_gaps_are_retained_without_banning_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);d = root / 'fixture'
            self.assertEqual(runner.optional_preflight(root, d)['realtimeCosts']['status'], 'NO-INSTRUMENT')
            folder = d / 'setup-attempts/one';folder.mkdir(parents=True)
            file = folder / 'readability-realtime-costs.json'
            adapter.write(file, {'status': 'NO-INSTRUMENT'})
            result = runner.optional_preflight(root, d)
            self.assertEqual(result['realtimeCosts']['status'], 'NO-INSTRUMENT')
            self.assertEqual(result['realtimeCosts']['sha256'], adapter.digest(file))
            adapter.write(file, {'status': 'MEASURED'})
            self.assertEqual(runner.optional_preflight(root, d)['realtimeCosts']['status'], 'MEASURED')
            file.write_text('{')
            self.assertEqual(runner.optional_preflight(root, d)['realtimeCosts']['status'], 'NO-INSTRUMENT')

    def test_instrument_survives_document_changes_but_refuses_changed_executable(self):
        # A real scratch Git tree distinguishes source attribution from the
        # bytes executed. Documentation must not invalidate an experiment pin.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'tools/mt-bench/m7-joined'
            folder.mkdir(parents=True)
            for name in ('adapter.py', 'orchestration_binding.py', 'RUNNER.md'):
                (folder / name).write_text('original\n')
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT)
            git('init', '-q')
            git('add', 'tools')
            git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'fixture')
            with patch.object(adapter, 'ROOT', root), patch.object(adapter, 'REUSED', []):
                original = adapter.instrument()
                pin = {'helperInstrument': original['sha256']}
                runner.verify_helper(pin)
                (folder / 'RUNNER.md').write_text('changed documentation\n')
                self.assertEqual(adapter.instrument()['sha256'], original['sha256'])
                git('add', 'tools')
                git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'docs')
                changed = adapter.instrument()
                self.assertNotEqual(changed['commit'], original['commit'])
                self.assertEqual(changed['sha256'], original['sha256'])
                runner.verify_helper(pin)
                (folder / 'adapter.py').write_text('changed executable\n')
                with self.assertRaisesRegex(RuntimeError, 'M7_INSTRUMENT_DIRTY'):
                    adapter.instrument()
                git('add', 'tools')
                git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'code')
                self.assertNotEqual(adapter.instrument()['sha256'], original['sha256'])
                # A changed instrument is recorded, not refused against the pin.
                runner.verify_helper(pin)

    def test_helper_pin_is_not_optional_or_ambiguous(self):
        common = {'version': 1, 'prepare': {}, 'k6Image': '', 'workSeconds': 30, 'cleanupSeconds': 30}
        for pins in ({}, {'helperHead': 'a' * 40, 'helperInstrument': 'b' * 64}):
            with patch.object(adapter, 'document', return_value={**common, **pins}):
                with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_CONFIG_FIELDS'):
                    runner.load_config('synthetic')
        with patch.object(adapter, 'git', return_value='a' * 40):
            runner.verify_helper({'helperHead': 'a' * 40})
            runner.verify_helper({'helperHead': 'b' * 40})
            with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_HELPER_HEAD'):
                runner.verify_helper({'helperHead': 'not-a-commit'})
        for invalid in ('', 'not-a-hash', None, True):
            with self.assertRaisesRegex(RuntimeError, 'M7_RUNNER_HELPER_INSTRUMENT'):
                runner.verify_helper({'helperInstrument': invalid})

    def test_guard_terminates_stage_that_ignores_term_and_removes_no_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready = root / 'stage-ready'
            source = "import pathlib,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(__import__('sys').argv[1]).touch();time.sleep(60)"
            child = subprocess.Popen([sys.executable, '-c', source, str(ready)], start_new_session=True)
            guard = None
            try:
                until = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < until:time.sleep(.01)
                self.assertTrue(ready.exists())
                adapter.job_record(root / 'stage-job.json', child, 'synthetic-owner', group=True)
                adapter.write(root / 'execution.json', {'owner': 'synthetic-owner', 'cleanupAt': time.time() + .1})
                guard = subprocess.Popen([sys.executable, '-B', runner.__file__, '_guard', str(root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, error = guard.communicate(timeout=16)
                self.assertEqual(guard.returncode, 0, error.decode())
                child.wait(timeout=2)
                self.assertEqual(child.returncode, -signal.SIGKILL)
                self.assertEqual(adapter.document(root / 'cleanup.json')['reason'], 'FINITE_DEADLINE')
                self.assertEqual(adapter.document(root / 'guard-result.json')['status'], 'RETURNED')
            finally:
                if guard and guard.poll() is None:guard.kill();guard.wait()
                if child.poll() is None:os.killpg(child.pid, signal.SIGKILL);child.wait()

    def test_native_summary_keeps_missing_counts_unknown_and_setup_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);load = root / 'fixture/load';load.mkdir(parents=True)
            adapter.write(load / 'k6-summary.json', {'metrics': {'http_reqs': {'count': 201}}})
            self.assertIsNone(runner.partial(root)['scenarioAttempts'])
            self.assertEqual(runner.partial(root)['trafficPhase'], 'UNMEASURED')
            adapter.write(load / 'k6-summary.json', {'metrics': {'scenario_request_attempts': {'count': 0}, 'http_reqs': {'count': 201}}})
            adapter.write(root / 'fixture/summary.json', {'status': 'PARTIAL', 'processes': {'k6': {'returncode': 107}}, 'strictChecks': {}})
            value = runner.partial(root)
            self.assertEqual(value['trafficPhase'], 'SETUP_ONLY')
            self.assertEqual(value['processes']['k6']['returncode'], 107)
            self.assertNotIn('writes_ok', value)
            # A killed writer can leave truncated native JSON. Preserve its
            # checksum and report unknown rather than losing the final receipt.
            (root / 'fixture/summary.json').write_text('{')
            value = runner.partial(root)
            self.assertEqual(value['unreadableArtifacts'], ['summary.json'])
            self.assertIn('summary.json', value['artifacts'])
            self.assertEqual(value['adapterStatus'], 'UNMEASURED')

if __name__ == '__main__':unittest.main()
