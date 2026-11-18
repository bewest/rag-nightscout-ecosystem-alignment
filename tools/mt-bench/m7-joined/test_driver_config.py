"""Pure input and launch controls complement the native loopback qualification."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import adapter
import discovery
import driver_vu_diagnostic as d
import workload


class DriverConfiguration(unittest.TestCase):
    def configuration(self):
        return {'version':1,'observer':'summary-v1','maxAggregateVUs':16,
                'scenarios':{'r_sgv':{'preAllocatedVUs':2,'maxVUs':4}}}

    def test_population_rate_window_topology_and_observer_are_not_a_fixed_case(self):
        for count, rate, seconds, replicas in ((500,120,1800,2),(10000,180,310,4)):
            args=SimpleNamespace(driver_plan=self.configuration(),driver_vu_diagnostic=None,
                profile='pgstream-sample',run_purpose='discovery',tenants=count,replicas=replicas)
            c={'offeredRps':rate,'loadSeconds':seconds,'hotFactor':1}
            selected=d.selection(args,c);self.assertEqual(selected['driverVuDiagnostic'],'configured-v1')
            plans=d.expected_plans({'tenants':count,'cadence':c|selected})
            self.assertEqual(plans[0]['population'],count)
            self.assertEqual(plans[0]['scenarios']['r_sgv']['durationSeconds'],seconds)
            self.assertAlmostEqual(plans[0]['scenarios']['r_sgv']['perSecond'],rate,delta=.01)

    def test_large_population_low_rate_time_unit_is_not_a_case_filter(self):
        cfg={'version':1,'observer':'summary-v1','maxAggregateVUs':7,
             'scenarios':{name:{'preAllocatedVUs':1,'maxVUs':1} for name in d.SHAPES}}
        c={'loadSeconds':1800,'offeredRps':1,'hotFactor':1,'driverPlan':cfg}
        plan=d.expected_plans({'tenants':10000,'cadence':c})[0]
        self.assertEqual(plan['scenarios']['w_sgv']['timeUnit'],'110000000ms')
        self.assertAlmostEqual(sum(r['perSecond'] for r in plan['scenarios'].values()),1)

    def test_rejects_unbounded_unknown_and_inconsistent_configuration_then_restores(self):
        # maxTraceRows is an authored finite budget; its old default is no
        # longer the invalid case. Nonrepresentable integer budgets still fail.
        c={'loadSeconds':30}
        good=self.configuration()
        for mutate in (lambda x:x.update(observer='unknown'),lambda x:x.update(maxAggregateVUs=True),
            lambda x:x.update(extra='ignored?'),lambda x:x['scenarios']['r_sgv'].update(maxVUs=1),
            lambda x:x['scenarios']['r_sgv'].update(durationSeconds=31),
            lambda x:x['scenarios']['r_sgv'].update(executor='ramping-vus'),
            lambda x:x.update(maxTraceBytes=0),lambda x:x.update(maxTraceRows=2**53)):
            bad=copy.deepcopy(good);mutate(bad)
            with self.assertRaises(RuntimeError):d.configuration(bad,c)
            self.assertEqual(d.configuration(good,c)['scenarios']['r_sgv']['maxVUs'],4)
        with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_VU_LIMIT'):
            d.expected_plans({'tenants':8,'cadence':c|{'driverShards':8,'driverPlan':good}})
        with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_REALISTIC_SHAPES'):
            d.configuration(good,c|{'workloadMix':'realistic-v1'})

    def test_existing_parser_accepts_json_string_no_runner_schema_fork(self):
        args=adapter.parser().parse_args(['prepare','--directory','/tmp/synthetic',
            '--core-repo','/tmp/core','--core-commit','a'*40,'--deploy-repo','/tmp/deploy',
            '--deploy-commit','b'*40,'--image','synthetic','--freeze','/tmp/synthetic-receipt',
            '--profile','pgstream-sample','--run-purpose','discovery','--tenants','500','--replicas','1',
            '--offered-rps','120','--load-seconds','1800','--driver-plan',json.dumps(self.configuration())])
        self.assertEqual(adapter.cadence_options(args)['driverPlan']['observer'],'summary-v1')
        args.run_purpose='acceptance'
        with self.assertRaises(RuntimeError):adapter.cadence_options(args)

    def test_runner_receipt_binds_driver_plan_and_remote_projection_refuses(self):
        import run_configuration as rc
        import runner
        cfg=json.loads((Path(adapter.HERE)/'examples/local-rehearsal.json').read_text())
        cfg.pop('helperHead');cfg['helperInstrument']='d'*64
        cfg['prepare']['driver-plan']=json.dumps(self.configuration())
        with patch.object(adapter,'instrument',return_value={'sha256':'d'*64}):
            _,argv=runner.validate_config(cfg)
            projected=rc.resolve(cfg)
            selected=projected['configuration']['cadence']['driverPlan']
            self.assertEqual(selected['scenarios']['r_sgv']['maxVUs'],4)
            first=projected['configurationSha256']
            changed=self.configuration();changed['scenarios']['r_sgv']['maxVUs']=5
            cfg['prepare']['driver-plan']=json.dumps(changed)
            self.assertNotEqual(rc.resolve(cfg)['configurationSha256'],first)
            with self.assertRaisesRegex(RuntimeError,'M7_LOCAL_OBSERVER_LOCAL_ONLY'):
                rc.remote_projection(cfg,{})

    def test_unsupported_target_and_command_refuse_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'k6').mkdir();workload.generate(adapter.ROOT,path/'k6/workload.js')
            c={'loadSeconds':4,'driverPlan':d.configuration(self.configuration(),{'loadSeconds':4}),
               'driverVuDiagnostic':'configured-v1'}
            m={'tenants':12,'runPurpose':'discovery','cadence':c}
            a=SimpleNamespace(assert_owned=Mock())
            base=['docker','run','--cpus','1','--memory','512m','image','run','--quiet',
                  '--summary-export','/out/k6-summary.json','/scripts/workload.js']
            with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_TARGET_UNSUPPORTED'):
                d.select_command(a,path,m|{'remoteTransport':True},base)
            with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_LAUNCH_UNSUPPORTED'):
                d.select_command(a,path,m,base[:-1])
            self.assertFalse((path/'k6'/d.SCRIPT).exists());a.assert_owned.assert_not_called()
            cmd=d.select_command(a,path,m,base)
            self.assertIn('fsize=536870912:536870912',cmd)
            self.assertEqual(cmd[:6],base[:6]);self.assertNotIn('--out',cmd)
            self.assertIn('--address',cmd);self.assertIn('127.0.0.1:0',cmd)


if __name__=='__main__':unittest.main()
