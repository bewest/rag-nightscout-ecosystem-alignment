"""Launch dispatch and ordinary k6 input projection without cluster resources."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execute
import kube_adapter as k
import native_load
from test_native_files import configured
from workloads import profile
import workload_runtime


class ExperimentLaunch(unittest.TestCase):
    def test_launch_uses_case_helper_for_capture_and_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = root/'selected/tools/mt-bench/kubernetes'
            helper.mkdir(parents=True)
            case = root/'case'
            case.mkdir()
            control = case/'lifecycle-input.json'
            k.write(control, {'caseDirectory': str(case), 'instrumentDirectory': str(root/'selected')})
            # Only the selected checkout provides these two inert entry points.
            (helper/'lifecycle_config.py').write_text(
                "import sys, shutil\nassert sys.argv[1] == 'capture'\nshutil.copyfile(sys.argv[2],sys.argv[3])\n")
            (helper/'lifecycle.py').write_text(
                "from pathlib import Path\nimport sys\nPath(sys.argv[1]).with_suffix('.entered').touch()\n")
            subprocess.run([sys.executable, '-B', k.HERE/'experiment.py', 'launch', control], check=True, cwd=root)
            self.assertTrue((case/'lifecycle-bound.entered').is_file())

    def test_packet_identity_is_the_alignment_commit(self):
        # brittle-check-removal: no file hashing; editing a tracked file does not change identity.
        identity = k.instrument()
        self.assertRegex(identity['commit'], '^[0-9a-f]{40}$')
        self.assertEqual(identity['sha256'], k.hashlib.sha256(identity['commit'].encode()).hexdigest())

    def test_configured_shards_split_the_ordinary_population_and_rate(self):
        import driver_vu_diagnostic as driver
        c, _, _ = configured()
        c.update(tenants=1000, ordinaryRosterTenants=100)
        c['workload'].update(driverShards=3, offeredRps=100)
        c['workload']['driverPlan']['maxAggregateVUs'] *= 3
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root/'load'
            out.mkdir()
            wrapper = root/driver.SCRIPT
            wrapper.write_bytes((k.M7/driver.SCRIPT).read_bytes())
            k.write(root/'packet.json', {'workload': {'driverWrapperSha256': k.digest(wrapper)}})
            full = list(range(1000))
            selected = execute.ordinary_driver_inputs(c, full, out, {})
            observed = {}

            def driver_entry(config, stage, script, *, env, shard, **kwargs):
                k.write(stage/f'k6-process-{shard}.json', {'returncode': 0})
                observed[shard] = (k.document(env['TENANTS_FILE']), float(env['OFFERED_RPS']),
                                   json.loads(env['M7_DRIVER_CONTEXT'])['population'])

            with patch.object(execute, 'native_k6', driver_entry), patch.object(driver, 'retain', return_value={}):
                execute.configured_load(root, out, c, {}, 10, selected)
            self.assertEqual([observed[i] for i in range(3)],
                             [(full[:34], 34, 100), (full[34:67], 33, 100), (full[67:100], 33, 100)])

    def test_selected_roster_reaches_host_and_job_inputs(self):
        c, job, options = configured()
        p = k.document(k.HERE/'workloads/small.json')
        p['population'].update(provisionedTenants=1000, ordinaryRosterTenants=100)
        p['workload'].update(offeredRps=22, logicalPollingClients=137)
        c['tenants'] = 1000
        p['referencePins'] = {**c['pins']['pair'], 'bindingCommit': c['pins']['bindingCommit']}
        c['deadlines']['cleanupUntil'] = '2099-01-01T00:30:00Z'
        c.pop('workload')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            full = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f't{i}.test',
                     'token': 'synthetic'} for i in range(1000)]
            k.write(out/'tenants.json', full)
            c['tenantsFile'] = str(out/'tenants.json')
            for offered in (22, 44, 11):
                p['workload']['offeredRps'] = offered
                config = profile.bind(p, c)
                tenants = execute.roster(config)
                env = workload_runtime.environment(config['workload'], {'TENANTS_FILE': c['tenantsFile']}, k.need)
                ordinary = execute.ordinary_driver_inputs(config, tenants, out, env)
                self.assertEqual(k.document(env['TENANTS_FILE']), full[:100])
                self.assertEqual(env['OFFERED_RPS'], str(offered))
                self.assertEqual(tenants, full)
                self.assertEqual(sum(k.viewer_plan.counts(
                    {'tenants': len(tenants), 'cadence': config['workload']}, tenants).values()), 137)
                rendered, inputs, _ = native_load.package(config, job, b'// synthetic', ordinary, **options)
                job_env = {r['name']: r['value'] for r in k.template(rendered)['spec']['containers'][0]['env']}
                self.assertEqual(json.loads(inputs['stringData']['tenants.json']), full[:100])
                self.assertEqual(job_env['OFFERED_RPS'], str(offered))
            for invalid in (0, True, 1001, 1.5):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'ORDINARY_ROSTER_TENANTS'):
                    profile.validate({**p, 'population': {**p['population'], 'ordinaryRosterTenants': invalid}})
            self.assertEqual(execute.ordinary_driver_inputs(dict(c, workload={}), full, out, {}), full)
