import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
import profile_provenance as profile
from workload import generate
from reduce import measurements

HERE=Path(__file__).resolve().parent
CORE=os.environ.get('M7_PROFILE_TEST_CORE')
COMMIT=os.environ.get('M7_PROFILE_TEST_COMMIT')
A='11111111-1111-4111-8111-111111111111'

class Profile(unittest.TestCase):
    def test_diagnostics_default_bounds_and_composed_dropped_or_changed_flags(self):
        self.assertEqual(profile.selection()['mode'],'off')
        for value in (999,60001,True):
            with self.assertRaisesRegex(RuntimeError,'SELECTION_INVALID'):profile.selection('on',value)
        config={'services':{'api':{'environment':{'UNCHANGED':'kept'}},'api-2':{},'realtime':{},'evaluator':{},'vault':{'command':['vault','server']}}}
        chosen=profile.selection('on',1000);profile.select_environment(config,chosen)
        self.assertEqual(config['services']['api']['environment']['UNCHANGED'],'kept')
        for mode in ('drop','mismatch'):
            broken=copy.deepcopy(config)
            if mode=='drop':broken['services']['api']['environment'].pop('NS_M7_DIAGNOSTICS')
            else:broken['services']['api']['environment']['NS_M7_DIAGNOSTICS']='0'
            with self.assertRaisesRegex(RuntimeError,'ENV_MISMATCH'):profile.verify_environment(broken,chosen)
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'api/env.json';file.parent.mkdir();file.write_text(json.dumps({'NS_M7_DIAGNOSTICS':'0'}))
            with self.assertRaisesRegex(RuntimeError,'STATE_OVERRIDE'):profile.state_environment(d,config,chosen)
        row={'Config':{'Labels':{'com.docker.compose.service':'api'},'Env':['NS_M7_DIAGNOSTICS=1','NS_M7_DIAGNOSTICS_INTERVAL_MS=1000']},'State':{'Running':True}}
        profile.runtime_environment([row],chosen);row['Config']['Env'].pop()
        with self.assertRaisesRegex(RuntimeError,'RUNTIME_MISMATCH'):profile.runtime_environment([row],chosen)
    def test_private_logs_actual_timeout_truncation_global_budget(self):
        with tempfile.TemporaryDirectory() as d:
            config={'services':{'api':{},'api-2':{},'vault':{'command':['vault','server']}}}
            value=profile.capture_logs(d,config,lambda role:[sys.executable,'-c',"import os,time;os.write(1,b'x'*1000);time.sleep(2)"],seconds=.1,per_role=100,total=150)
            self.assertEqual(sum(row['bytes'] for row in value['roles']),150)
            self.assertTrue(all(row['truncated'] for row in value['roles']))
            self.assertEqual((Path(d)/'api.log').stat().st_mode & 0o777,0o600)
            value=profile.capture_logs(d,{'services':{'api':{}}},lambda role:[sys.executable,'-c','import time;time.sleep(2)'],seconds=.05)
            self.assertTrue(value['roles'][0]['timeout']);self.assertEqual(value['roles'][0]['bytes'],0)
    def test_private_logs_keep_recent_tail_and_earlier_disconnect_causes(self):
        with tempfile.TemporaryDirectory() as d:
            cause=b'2026-11-15T19:20:00.000Z realtime server disconnects in the last 60 s: {"REALTIME_FANOUT_SEND_FAILED":3}\n'
            recent=b'2026-11-15T19:24:00.000Z LATEST_LOAD_EVIDENCE\n'
            payload=b'EARLY_STARTUP\n'+cause+b'noisy diagnostic\n'*10000+recent
            code='import os;os.write(1,b\'EARLY_STARTUP\\n\'+'+repr(cause)+"+b'noisy diagnostic\\n'*10000+"+repr(recent)+')'
            value=profile.capture_logs(d,{'services':{'realtime':{}}},lambda role:[sys.executable,'-c',code],seconds=2,per_role=512,total=512)
            row=value['roles'][0];tail=(Path(d)/'realtime.log').read_bytes();causes=(Path(d)/'realtime.disconnects.log').read_bytes()
            self.assertTrue(row['streamComplete']);self.assertEqual(row['returncode'],0)
            self.assertTrue(row['truncated']);self.assertEqual(row['observedBytes'],len(payload))
            self.assertLessEqual(len(tail)+len(causes),512);self.assertEqual(row['bytes'],len(tail)+len(causes))
            self.assertIn(recent,tail);self.assertNotIn(b'EARLY_STARTUP',tail);self.assertIn(cause,causes)
            self.assertEqual(row['sourceTimes']['last'],'2026-11-15T19:24:00.000Z')
            self.assertEqual(row['causeSourceTimes']['last'],'2026-11-15T19:20:00.000Z')
            self.assertEqual(row['causeLinesObserved'],1);self.assertEqual(row['causeLinesRetained'],1)
            self.assertLess(row['captureStartedAtNs'],row['captureFinishedAtNs'])
            self.assertEqual((Path(d)/'realtime.disconnects.log').stat().st_mode & 0o777,0o600)

    def test_private_logs_surface_scan_limit_instead_of_claiming_source_end(self):
        with tempfile.TemporaryDirectory() as d:
            code="import os;[os.write(1,b'x'*8192) for _ in range(600)]"
            row=profile.capture_logs(d,{'services':{'api':{}}},lambda role:[sys.executable,'-c',code],seconds=2,per_role=128,total=128)['roles'][0]
            self.assertEqual(row['reason'],'scan-byte-cap');self.assertFalse(row['streamComplete']);self.assertTrue(row['truncated'])
            self.assertEqual(row['bytes'],128);self.assertLessEqual(row['observedBytes'],row['scanLimitBytes']+1)

    def test_topology_and_diagnostics_are_comparison_identity(self):
        config={'services':{'api':{},'realtime':{},'evaluator':{},'vault':{'command':['vault','server']}}}
        base=profile.identity(profile.selection(),config)
        self.assertEqual(base['topology']['secretsBackend'],'vault-server')
        self.assertNotEqual(base['sha256'],profile.identity(profile.selection('on'),config)['sha256'])
        config['services']['api-2']={}
        self.assertEqual(base,profile.identity(profile.selection(),config))
        config['services']['vault-agent']={}
        with self.assertRaisesRegex(RuntimeError,'AGENT_OVERLAY_UNSUPPORTED'):profile.identity(profile.selection(),config)

    def test_stats_only_exited_k6_separate_and_unknown_serving_missing_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            d=Path(temporary)
            for name in ('idle-disabled','idle','load'):
                folder=d/name;folder.mkdir()
                for edge,at,cpu in [('before',1,1000000),('after',3,2000000)]:
                    (folder/(edge+'-cgroups.json')).write_text(json.dumps({'at':at,'roles':{'api':{'id':'same','cgroup':'usage_usec '+str(cpu)+'\n1024\nanon 512\n','processRssKiB':'PID COMMAND RSS\n1 node 100'}}}))
                    (folder/(edge+'-pg-role.tsv')).write_text('role\t1\t10\n')
                if name!='idle-disabled':
                    (folder/'docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n2\towned-api-1\t50%\t1MiB / 1GiB\n'+('2\towned-k6\t10%\t2MiB / 1GiB\n' if name=='load' else ''))
                    (folder/'pg-activity.tsv').write_text('t\trole\tstate\twait_event_type\twait_event\tn\n2\trole\tidle\tClient\tClientRead\t1\n')
            shapes=('w_sgv','w_devicestatus','w_treatments_v3','r_sgv','r_devicestatus','r_treatments','r_status')
            (d/'load/k6-summary.json').write_text(json.dumps({'metrics':{'http_req_duration{shape:'+k+'}':{'values':{'med':1,'p(95)':2,'p(99)':3,'count':1}} for k in shapes}}))
            value=measurements(d,{'project':'owned','tenants':2});self.assertTrue(value['complete'])
            self.assertEqual(set(value['windows']['load']['roles']),{'api'})
            # Retained legacy metadata must not turn a shard statistic into a
            # claimed pooled percentile in the downstream report.
            summary_file=d/'load/k6-summary.json';original=summary_file.read_text();legacy=json.loads(original)
            legacy['m7DriverShards']={'version':1,'scope':'upper bound of pooled quantile',
                'quantileBounds':{'http_req_duration{shape:r_sgv}':{'p(95)':[1,2]}}}
            summary_file.write_text(json.dumps(legacy));qualified=measurements(d,{'project':'owned','tenants':2})
            self.assertEqual(qualified['httpShapes']['r_sgv']['p95'],2)
            self.assertEqual(qualified['httpShapes']['r_sgv']['pooledPercentiles'],'UNMEASURED')
            self.assertEqual(qualified['httpShapes']['r_sgv']['shardPercentileRange']['p(95)'],[1,2])
            legacy['m7DriverShards']['quantileBounds']=None;summary_file.write_text(json.dumps(legacy))
            missing=measurements(d,{'project':'owned','tenants':2});self.assertEqual(missing['httpShapes']['r_sgv']['pooledPercentiles'],'UNMEASURED');self.assertIsNone(missing['httpShapes']['r_sgv']['shardPercentileRange'])
            summary_file.write_text(original)

            k6=value['windows']['load']['loadGenerators']['k6'];self.assertEqual(k6['sampleCount'],1);self.assertEqual(k6['processRssKiBAfter'],'UNMEASURED')
            missing=d/'load/after-cgroups.json';saved=missing.read_text();value=json.loads(saved);value['roles']['api'].pop('processRssKiB');missing.write_text(json.dumps(value))
            self.assertFalse(measurements(d,{'project':'owned','tenants':2})['complete']);missing.write_text(saved)
            file=d/'load/docker-stats.tsv';file.write_text(file.read_text()+'2\towned-missing-1\t10%\t1MiB / 1GiB\n')
            value=measurements(d,{'project':'owned','tenants':2});self.assertFalse(value['complete']);self.assertEqual(value['windows']['load']['roles']['missing']['measurement'],'NO-MEASUREMENT')

if __name__=='__main__':unittest.main()
