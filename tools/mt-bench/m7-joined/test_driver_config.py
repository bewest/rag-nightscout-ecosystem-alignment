"""Pure input and launch controls complement the native loopback qualification."""
import copy
import csv
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import adapter
import discovery
import driver_accounting as d
import workload


class DriverConfiguration(unittest.TestCase):
    def configuration(self):
        return {'version':1,'observer':'summary-v1',
                'scenarios':{'r_sgv':{'gracefulStopSeconds':10}}}

    def test_population_rate_window_topology_and_observer_are_not_a_fixed_case(self):
        for count, rate, seconds, replicas in ((500,120,1800,2),(10000,180,310,4)):
            args=SimpleNamespace(driver_plan=self.configuration(),
                profile='pgstream-sample',run_purpose='discovery',tenants=count,replicas=replicas)
            c={'offeredRps':rate,'loadSeconds':seconds,'hotFactor':1}
            selected=d.selection(args,c);self.assertEqual(set(selected),{'driverPlan'})
            plans=d.expected_plans({'tenants':count,'cadence':c|selected})
            self.assertEqual(plans[0]['population'],count)
            self.assertEqual(plans[0]['scenarios']['r_sgv']['durationSeconds'],seconds)
            self.assertAlmostEqual(plans[0]['scenarios']['r_sgv']['perSecond'],rate,delta=.01)

    def test_executor_windows_use_the_actual_start_of_each_scenario(self):
        row = {'startTimeSeconds': 0, 'durationSeconds': 120, 'gracefulStopSeconds': 30,
               'rate': 10, 'timeUnit': '3000ms'}
        plans = {'read': row, 'write': row, 'later': row | {'startTimeSeconds': 5, 'durationSeconds': 1}}
        starts = {'read': 10012, 'write': 10030, 'later': 15020}
        got = d.executor_windows(starts, plans, setup_end=10000, end=130195)
        self.assertEqual((got['scheduleStartMs'], got['scheduleEndMs'], got['drainMs']),
                         (10012, 130030, 165))
        self.assertEqual(got['executorWindows']['later']['steadyEndMs'], 16020)
        self.assertEqual(got['executorWindows']['write']['launchLagFromEarliestOriginMs'], 18)

        for changed, teardown in [(starts | {'later': 14020}, 130195),
                                  (starts, 129990), (starts, 163100)]:
            with self.subTest(starts=changed, teardown=teardown):
                with self.assertRaisesRegex(RuntimeError, 'M7_DRIVER_PHASE'):
                    d.executor_windows(changed, plans, setup_end=10000, end=teardown)

    def test_planned_extent_for_an_executor_with_no_observed_start(self):
        row = {'startTimeSeconds': 2, 'durationSeconds': 1, 'gracefulStopSeconds': 0,
               'rate': 1, 'timeUnit': '5000ms'}
        plans = {'late': row, 'unobserved': row | {'startTimeSeconds': 4}}
        got = d.executor_windows({'late': 12007}, plans, setup_end=10000, end=15040)
        self.assertEqual(got['scheduleEndMs'], 15007)
        self.assertEqual(set(got['executorWindows']), {'late'})
        delayed = d.executor_windows({'late': 12007, 'unobserved': 15007}, plans, 10000, 16040)
        self.assertEqual(delayed['executorWindows']['unobserved']['launchLagFromEarliestOriginMs'], 1000)

    def test_high_rate_dispatch_lag_preserves_traffic_and_measures_common_window(self):
        row = {'startTimeSeconds': 0, 'durationSeconds': 1, 'gracefulStopSeconds': 0,
               'rate': 1000, 'timeUnit': '1000ms'}
        scenarios = {'baseline': row | {'rate': 1}, 'busy': row}
        starts = {'baseline': 1000, 'busy': 1018}
        phases = d.executor_windows(starts, scenarios, setup_end=990, end=2023)
        counts = {}
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / 'trace.csv.gz'
            with gzip.open(trace, 'wt', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['metric_name', 'timestamp', 'metric_value', 'scenario', 'driver_phase'])
                for name, start in starts.items():
                    n = scenarios[name]['rate']
                    counts[name] = dict(planned=n, issued=n, responses=n, completed=n, dropped=0,
                                        transportFailures=0, steadyStarts=n, steadyCompletions=n,
                                        drainStarts=0, drainCompletions=0)
                    for i in range(n):
                        for metric in ('m7_driver_started', 'scenario_request_attempts',
                                       'scenario_http_responses', 'm7_driver_finished'):
                            writer.writerow([metric, start+i, 1, name, 'steady'])
            bins = d.trace_assess(trace, counts, starts, {'scenarios': scenarios},
                                  {'maxTraceBytes': 1000000, 'maxTraceRows': 5000}, phases['scheduleStartMs'])
        self.assertEqual(phases['scheduleEndMs'], 2018)
        self.assertEqual(bins['busy'], {'before': 0, 'during': 982, 'after': 18, 'minimumStartShortfall': 18})

    def test_trace_compressed_decoded_and_row_limits_are_independent(self):
        raw = b'metric_name,timestamp,metric_value,scenario\nignored,0,1,read\n'
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / 'trace.csv.gz'
            trace.write_bytes(gzip.compress(raw))
            bounds = {'maxTraceBytes': trace.stat().st_size, 'maxDecodedTraceBytes': len(raw), 'maxTraceRows': 1}
            self.assertEqual(d.trace_assess(trace, {}, {}, {}, bounds, None), {})
            for field in bounds:
                with self.subTest(field=field):
                    with self.assertRaisesRegex(RuntimeError, 'M7_DRIVER_TRACE_BOUND'):
                        d.trace_assess(trace, {}, {}, {}, bounds | {field: bounds[field] - 1}, None)
        value = self.configuration() | {'maxTraceBytes': 65536, 'maxDecodedTraceBytes': len(raw)}
        self.assertEqual(d.configuration(value, {'loadSeconds': 30})['maxDecodedTraceBytes'], len(raw))

    def test_large_population_low_rate_time_unit_is_not_a_case_filter(self):
        cfg={'version':1,'observer':'summary-v1','scenarios':{name:{} for name in d.SHAPES}}
        c={'loadSeconds':1800,'offeredRps':1,'hotFactor':1,'driverPlan':cfg}
        plan=d.expected_plans({'tenants':10000,'cadence':c})[0]
        self.assertEqual(plan['scenarios']['w_sgv']['timeUnit'],'110000000ms')
        self.assertAlmostEqual(sum(r['perSecond'] for r in plan['scenarios'].values()),1)

    def test_rejects_unbounded_unknown_and_inconsistent_configuration_then_restores(self):
        # maxTraceRows is an authored finite budget; its old default is no
        # longer the invalid case. Nonrepresentable integer budgets still fail.
        c={'loadSeconds':30}
        good=self.configuration()
        for mutate in (lambda x:x.update(observer='unknown'),lambda x:x.update(maxAggregateVUs=28),
            lambda x:x.update(extra='ignored?'),lambda x:x['scenarios']['r_sgv'].update(maxVUs=4),
            lambda x:x['scenarios']['r_sgv'].update(preAllocatedVUs=2),
            lambda x:x['scenarios']['r_sgv'].update(durationSeconds=31),
            lambda x:x['scenarios']['r_sgv'].update(executor='ramping-vus'),
            lambda x:x.update(maxTraceBytes=0),lambda x:x.update(maxTraceRows=2**53),
            lambda x:x.update(maxDecodedTraceBytes=0),lambda x:x.update(maxDecodedTraceBytes=True),
            lambda x:x.update(maxDecodedTraceBytes=2**53)):
            bad=copy.deepcopy(good);mutate(bad)
            with self.assertRaises(RuntimeError):d.configuration(bad,c)
            self.assertEqual(d.configuration(good,c)['scenarios']['r_sgv']['gracefulStopSeconds'],10)
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

    def test_runner_receipt_binds_driver_plan(self):
        import run_configuration as rc
        import runner
        cfg=json.loads((Path(adapter.HERE)/'examples/local-rehearsal.json').read_text())
        cfg.pop('helperHead');cfg['helperInstrument']='d'*64
        cfg['prepare']['driver-plan']=json.dumps(self.configuration())
        with patch.object(adapter,'instrument',return_value={'sha256':'d'*64}):
            _,argv=runner.validate_config(cfg)
            projected=rc.resolve(cfg)
            selected=projected['configuration']['cadence']['driverPlan']
            self.assertEqual(selected['scenarios']['r_sgv']['gracefulStopSeconds'],10)
            first=projected['configurationSha256']
            changed=self.configuration();changed['scenarios']['r_sgv']['gracefulStopSeconds']=5
            cfg['prepare']['driver-plan']=json.dumps(changed)
            self.assertNotEqual(rc.resolve(cfg)['configurationSha256'],first)

    def test_unsupported_target_and_command_refuse_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'k6').mkdir();workload.generate(adapter.ROOT,path/'k6/workload.js')
            c={'loadSeconds':4,'driverPlan':d.configuration(self.configuration(),{'loadSeconds':4})}
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
