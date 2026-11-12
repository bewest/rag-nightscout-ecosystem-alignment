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
    def test_missing_observation_not_green_and_invalid_mismatch_fail(self):
        self.assertEqual(profile.fingerprint_check({})['verdict'],'UNMEASURED')
        good={'settings_fingerprint_observed':{'count':1}}
        self.assertEqual(profile.fingerprint_check(good)['verdict'],'PASS')
        for key in ('invalid','mismatch'):
            self.assertEqual(profile.fingerprint_check({**good,'settings_fingerprint_'+key:{'count':1}})['verdict'],'FAIL')
    def test_private_logs_actual_timeout_truncation_global_budget(self):
        with tempfile.TemporaryDirectory() as d:
            config={'services':{'api':{},'api-2':{},'vault':{'command':['vault','server']}}}
            value=profile.capture_logs(d,config,lambda role:[sys.executable,'-c',"import os,time;os.write(1,b'x'*1000);time.sleep(2)"],seconds=.1,per_role=100,total=150)
            self.assertEqual(sum(row['bytes'] for row in value['roles']),150)
            self.assertTrue(all(row['truncated'] for row in value['roles']))
            self.assertEqual((Path(d)/'api.log').stat().st_mode & 0o777,0o600)
            value=profile.capture_logs(d,{'services':{'api':{}}},lambda role:[sys.executable,'-c','import time;time.sleep(2)'],seconds=.05)
            self.assertTrue(value['roles'][0]['timeout']);self.assertEqual(value['roles'][0]['bytes'],0)
    def test_topology_diagnostics_and_settings_are_comparison_identity(self):
        f={'schema':1,'sha256':'a'*64,'sourceCommit':'b'*40,'sourceBlobs':{'file':'c'*40}}
        config={'services':{'api':{},'realtime':{},'evaluator':{},'vault':{'command':['vault','server']}}}
        base=profile.identity(f,profile.selection(),config)
        self.assertEqual(base['topology']['secretsBackend'],'vault-server')
        self.assertNotEqual(base['sha256'],profile.identity(f,profile.selection('on'),config)['sha256'])
        config['services']['api-2']={}
        self.assertEqual(base,profile.identity(f,profile.selection(),config))
        config['services']['vault-agent']={}
        with self.assertRaisesRegex(RuntimeError,'AGENT_OVERLAY_UNSUPPORTED'):profile.identity(f,profile.selection(),config)
    @unittest.skipUnless(CORE and COMMIT,'explicit owned pinned core fixture required')
    def test_actual_source_defaults_real_status_and_generated_k6_plugin_control(self):
        with tempfile.TemporaryDirectory(prefix='m7-status-profile-') as d:
            d=Path(d);seed=d/'primer.json';status=d/'status.json';work=d/'workload.js';tenants=d/'tenants.json'
            seed_value={'version':1,'seed':[{'id':A,'hosts':['a.example.test'],'issueRootSecret':True}]};seed.write_text(json.dumps(seed_value))
            command=['node',str(HERE/'fingerprint.cjs'),CORE,COMMIT,str(seed),'1']
            expected=json.loads(subprocess.check_output(command,text=True))
            self.assertEqual(len(expected['transit']['purposes']),6);self.assertEqual(expected['transit']['keyCountObservation'],'UNMEASURED')
            self.assertNotIn('enable',expected);self.assertNotIn('hosts',json.dumps(expected))
            subprocess.run(['node',str(HERE/'status-fixture.cjs'),CORE,str(status)],check=True,timeout=20)
            original=status.read_text();raw=json.loads(original);self.assertIn('careportal',raw['settings']['enable'])
            generate(adapter.ROOT,work);tenants.write_text(json.dumps([{'id':A,'host':'a.example.test','token':'fixture-only'}]))
            env={**os.environ,'M7_FIXTURE_STATUS':str(status),'M7_FIXTURE_FINGERPRINT':expected['sha256']}
            def calls():return json.loads(subprocess.check_output(['node',str(HERE/'workload-shapes.cjs'),str(work),str(tenants)],env=env,text=True))
            baseline=calls();self.assertEqual(sum(c.get('value',0) for c in baseline if c.get('counter')=='settings_fingerprint_observed'),1)
            self.assertFalse(any(c.get('counter') in ('settings_fingerprint_invalid','settings_fingerprint_mismatch') for c in baseline))
            # No added status request; exactly one existing status shape.
            self.assertEqual(sum(c.get('method')=='GET' and '/status.json' in c.get('url','') for c in baseline),1)
            raw['settings']['enable']=['bgnow'];status.write_text(json.dumps(raw))
            self.assertTrue(any(c.get('counter')=='settings_fingerprint_mismatch' for c in calls()))
            del raw['settings'];status.write_text(json.dumps(raw))
            self.assertTrue(any(c.get('counter')=='settings_fingerprint_invalid' for c in calls()))
            seed_value['seed'][0]['settings']={};seed.write_text(json.dumps(seed_value))
            denied=subprocess.run(command,text=True,capture_output=True);self.assertNotEqual(denied.returncode,0);self.assertIn('SEED_INVALID',denied.stderr)
            seed_value['seed'][0].pop('settings');seed.write_text(json.dumps(seed_value))
            self.assertEqual(json.loads(subprocess.check_output(command,text=True))['sha256'],expected['sha256'])
            status.write_text(original)
            self.assertFalse(any(c.get('counter') in ('settings_fingerprint_invalid','settings_fingerprint_mismatch') for c in calls()))

    def test_comparison_refuses_same_source_but_changed_diagnostics_settings_and_missing_observation(self):
        import contract
        f={'schema':1,'sha256':'a'*64,'sourceCommit':'b'*40,'sourceBlobs':{}}
        config={'services':{'api':{},'realtime':{},'evaluator':{},'vault':{'command':['vault','server']}}}
        chosen=profile.identity(f,profile.selection(),config)
        pair={'core':'b'*40,'deploy':'c'*40}
        row={'pair':pair,'hostIdentity':'d'*64,'instrument':'e'*64,'imageId':'sha256:'+'f'*64,'verdict':'PASS','profile':'remote-pilot','replicas':2,'measurements':{'complete':True},'profileSelection':chosen,'settingsFingerprintObservation':{'verdict':'PASS','observations':1,'invalid':0,'mismatch':0}}
        doc={'kind':'m7-joined-remote-pilot','pair':pair,'hostIdentity':'d'*64,'instrument':'e'*64,'imageId':row['imageId'],'profileSelection':chosen,'profileReplicas':2,'cells':[{**row,'tenants':n} for n in contract.PILOT_COUNTS]}
        self.assertTrue(contract.pilot_check(doc))
        for replacement in (profile.identity(f,profile.selection('on'),config),profile.identity({**f,'sha256':'0'*64},profile.selection(),config)):
            broken=copy.deepcopy(doc);broken['cells'][1]['profileSelection']=replacement
            with self.assertRaisesRegex(RuntimeError,'PROFILE_SELECTION_MISMATCH'):contract.pilot_check(broken)
        broken=copy.deepcopy(doc);broken['cells'][1]['settingsFingerprintObservation']['observations']=0
        with self.assertRaisesRegex(RuntimeError,'FUNCTIONAL_SETTINGS_FINGERPRINT'):contract.pilot_check(broken)

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
            k6=value['windows']['load']['loadGenerators']['k6'];self.assertEqual(k6['sampleCount'],1);self.assertEqual(k6['processRssKiBAfter'],'UNMEASURED')
            missing=d/'load/after-cgroups.json';saved=missing.read_text();value=json.loads(saved);value['roles']['api'].pop('processRssKiB');missing.write_text(json.dumps(value))
            self.assertFalse(measurements(d,{'project':'owned','tenants':2})['complete']);missing.write_text(saved)
            file=d/'load/docker-stats.tsv';file.write_text(file.read_text()+'2\towned-missing-1\t10%\t1MiB / 1GiB\n')
            value=measurements(d,{'project':'owned','tenants':2});self.assertFalse(value['complete']);self.assertEqual(value['windows']['load']['roles']['missing']['measurement'],'NO-MEASUREMENT')

if __name__=='__main__':unittest.main()
