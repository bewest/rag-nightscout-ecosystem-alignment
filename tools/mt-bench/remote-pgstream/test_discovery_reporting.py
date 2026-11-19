"""Actual public accounting/config producer; partial reduction never grants acceptance."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import copy,json,sys,tempfile,unittest,types,os,subprocess,shutil
from pathlib import Path
from unittest.mock import patch
import app,cell,generator,protocol,producer,transport as t
import discovery
from test_parameters import extended,prep_args
from test_default_probe_runtime import DefaultProbeRuntime

class DiscoveryReporting(unittest.TestCase):
 def selected(self,n=37):
  b=extended(n,73,45,3);b['reportMode']='discovery'
  b['pair']={'core':t.PERFORMANCE_CORE,'deploy':t.PERFORMANCE_DEPLOY};b['imageId']=t.PERFORMANCE_APP
  b['workload']['cadence'].update(warmupSeconds=3,idleSeconds=4,probeEveryMs=1000,socketsPerTenant=3)
  b['workload']['resourcePlan']['logicalPollingClients']=3*n
  return b
 def args(self,b,d):
  args=prep_args(b,d)
  for flag,key in [('--warmup-seconds','warmupSeconds'),('--idle-seconds','idleSeconds')]:args[args.index(flag)+1]=str(b['workload']['cadence'][key])
  args+=['--probe-every-ms',str(b['workload']['cadence']['probeEveryMs']),'--sockets-per-tenant',str(b['workload']['cadence']['socketsPerTenant'])]
  p=Path(d)/'receipt.json';v=json.loads(p.read_text());v['remoteReportMode']='discovery';p.write_text(json.dumps(v))
  return args
 def test_actual_config_prepare_and_traffic_commands_vary_without_source_edits(self):
  for n in (2,37,3000):
   b=self.selected(n);protocol.binding(b)
   with tempfile.TemporaryDirectory() as d:
    args=self.args(b,d)
    with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare,patch.object(cell.app,'record_prepared_binding'):
     cell.main();parsed=prepare.call_args.args[0]
     self.assertEqual(app.a.cadence_options(parsed),b['workload']['cadence']);self.assertEqual(parsed.tenants,n)
    probe,k6=generator.traffic_commands(d,b,{'trafficRunId':'synthetic','settingsFingerprint':'f'*64},'synthetic-k6',1)
    self.assertEqual(probe[probe.index('--per')+1],'3');self.assertEqual(probe[probe.index('--window')+1],'45');self.assertEqual(probe[probe.index('--probeEvery')+1],'1000');self.assertIn('OFFERED_RPS=73',k6)
    p=Path(d)/'receipt.json';v=json.loads(p.read_text());v['remoteReportMode']='strict';p.write_text(json.dumps(v))
    with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare:
     with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION_REQUIRED'):cell.main()
     prepare.assert_not_called()
    args[args.index('--core-commit')+1]='f'*40
    with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare:
     with self.assertRaisesRegex(RuntimeError,'PREPARE_PROFILE_REQUIRED'):cell.main()
     prepare.assert_not_called()
  for key,bad in [('socketsPerTenant',0),('probeEveryMs',0),('samplerIntervalSeconds',61),('loadSeconds',10801)]:
   b=self.selected();b['workload']['cadence'][key]=bad
   with self.assertRaises(RuntimeError):protocol.binding(b)
  b=self.selected();b.pop('reportMode')
  with self.assertRaises(RuntimeError):protocol.binding(b) # Strict source/preset is unchanged.
 def test_real_generated_ledger_detects_removed_settlement_and_restores(self):
  run=DefaultProbeRuntime();good=run.run_case('write-fail',True);self.assertEqual(good.returncode,0,good.stderr)
  from unittest.mock import patch as patcher
  import traffic_probe
  original=traffic_probe.generate
  def broken(root,target):
   result=original(root,target);p=Path(target);s=p.read_text();self.assertEqual(s.count('if(accounting)accounting.settle(attempt,r.status);'),1);p.write_text(s.replace('if(accounting)accounting.settle(attempt,r.status);',''));return result
  with patcher.object(traffic_probe,'generate',side_effect=broken):bad=run.run_case('write-fail',True)
  self.assertEqual(bad.returncode,0,bad.stderr)
  ledger=json.loads(bad.stdout.splitlines()[-1])['accounting'];self.assertGreater(sum(r['pending'] for r in ledger['byTenant'].values()),0)
  restored=run.run_case('write-fail',True);self.assertEqual(restored.returncode,0,restored.stderr);ledger=json.loads(restored.stdout.splitlines()[-1])['accounting'];self.assertEqual(sum(r['pending'] for r in ledger['byTenant'].values()),0)
 def test_exported_accounting_hash_mismatch_refuses_before_driver_install(self):
  with tempfile.TemporaryDirectory() as root:
   d=Path(root);b={'tenants':1,'pair':{'core':'a'*40,'deploy':'b'*40},'imageId':'sha256:'+'c'*64}
   for name in generator.TRAFFIC_FILES:(d/name).write_bytes(b'[{}]' if name=='tenants.private.json' else b'{}')
   files={name:generator.executable(d/name) for name in generator.TRAFFIC_FILES}
   protocol.write(d/'traffic.json',{'version':1,'binding':b,'files':files,'generator':{'pair':b['pair'],'servingImageId':b['imageId']}})
   (d/'probe-accounting.cjs').write_text('changed accounting')
   with patch.object(generator.os,'geteuid',return_value=0),patch.object(generator.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_name='nsload',pw_gid=generator.GID)),patch.object(generator.subprocess,'check_output',return_value='nsload'),patch.object(generator,'child') as child:
    with self.assertRaisesRegex(RuntimeError,'EXTERNAL_TRAFFIC_EXPORT_CHANGED'):generator.prepare(d,b)
    child.assert_not_called()
 def summary(self,d,counts=None,source_error=None,clinical_error=None,frame_error=None):
  if frame_error:
   (d/'tenants.private.json').write_text('[]')
  m={'pair':{'core':'a'*40,'deploy':'b'*40},'imageId':'sha256:'+'c'*64,'instrument':{},'tenants':2,'cadence':self.selected(2)['workload']['cadence']};out=d/'load';out.mkdir();(out/'runid').write_text('synthetic')
  if frame_error:(out/'fanout.json').write_text(json.dumps({'probeWrites':{'byTenant':{}}}))
  with patch.object(app.a,'verify',side_effect=source_error),patch.object(app,'load'),patch.object(discovery,'count_observation',return_value=({'verdict':'GREEN'},True),side_effect=counts),patch('clinical.completed',return_value={'verdict':'PASS'},side_effect=clinical_error),patch('viewer_plan.check',side_effect=frame_error),patch.object(app,'measurements',side_effect=RuntimeError('missing optional')):
   return app.discovery_summary(d,m,self.selected(2),{'prime':{'primed':0},**({'window':{'writes':1}}if frame_error else{})}, {'metrics':{}})
 def test_hard_clinical_and_frame_errors_remain_fail_and_missing_clinical_stays_unknown(self):
  for kwargs,code in [({'clinical_error':RuntimeError('REMOTE_CLINICAL_WRONG_DATA')},'REMOTE_CLINICAL_WRONG_DATA'),({'frame_error':RuntimeError('M7_VIEWER_FRAME_WRONG_DATA')},'M7_VIEWER_FRAME_WRONG_DATA')]:
   with tempfile.TemporaryDirectory() as root:
    d=Path(root)
    with self.assertRaisesRegex(RuntimeError,code):self.summary(d,**kwargs)
    result=json.loads((d/'summary.json').read_text());self.assertEqual(result['verdict'],'FAIL');self.assertEqual(result['failure']['code'],code)
  with tempfile.TemporaryDirectory() as root:
   result=self.summary(Path(root),clinical_error=RuntimeError('REMOTE_CLINICAL_COMPLETION_UNMEASURED'))
   self.assertEqual(result['verdict'],'PARTIAL');self.assertEqual(result['completedOutput']['verdict'],'UNMEASURED');self.assertEqual(result['capacityAcceptance'],'NOT_GRANTED')
  with tempfile.TemporaryDirectory() as root:
   d=Path(root);(d/'idle').mkdir();(d/'idle/evaluator-progress.json').write_text(json.dumps({'verdict':'FAIL','code':'M7_EVALUATOR_PROGRESS_FOREIGN'}))
   with self.assertRaisesRegex(RuntimeError,'REMOTE_DISCOVERY_CLINICAL_FAILURE'):self.summary(d)
   self.assertEqual(json.loads((d/'summary.json').read_text())['verdict'],'FAIL')

 @unittest.skipUnless(os.environ.get('PGCAL_REPORT_CONTROLLER_ROOT'),'actual paired controller root not selected')
 def test_actual_controller_accepts_partial_reduction_with_unknown_observations(self):
  # The cell protocol is PARTIAL; individual missing observations remain UNMEASURED.
  # Exercise the real controller classifier instead of copying its admission rule.
  with tempfile.TemporaryDirectory() as root:result=self.summary(Path(root))
  module=Path(os.environ['PGCAL_REPORT_CONTROLLER_ROOT'])/'tools/perf-cloud/pgstream-calibration.mjs'
  program="import {coordinateCalibration} from "+json.dumps(module.as_uri())+";const verdict=process.argv[1];const app={next:async name=>name==='server-recovery-complete'?{measurement:'NOT_RUN'}:name==='cell-complete'?{verdict}:{},send:()=>{},finish:async()=>{}};const gen={next:async name=>name==='client-primed'?{primed:0}:{},send:()=>{},finish:async()=>{}};const result=await coordinateCalibration(app,async()=>gen,async()=>{},()=>{},1,()=>1000,'discovery');if(result.verdict!=='PARTIAL')throw Error('PARTIAL_CELL_REQUIRED');let refused=false;try{await coordinateCalibration(app,async()=>gen,async()=>{},()=>{},1,()=>1000,'strict');}catch(error){if(error.message!=='PGCAL_CELL_NONPASS')throw error;refused=true;}if(!refused)throw Error('STRICT_PARTIAL_WAS_ACCEPTED');console.log('ACTUAL_CONTROLLER_PARTIAL_ADMITTED_STRICT_REFUSED');"
  observed=subprocess.run([shutil.which('node'),'--input-type=module','-e',program,result['verdict']],capture_output=True,text=True,timeout=15)
  self.assertEqual(observed.returncode,0,observed.stderr)
  self.assertIn('ACTUAL_CONTROLLER_PARTIAL_ADMITTED',observed.stdout)

 def test_optional_missing_stays_unknown_wrong_source_and_wrong_data_retained_fail(self):
  with tempfile.TemporaryDirectory() as root:
   d=Path(root);result=self.summary(d);self.assertEqual(result['status'],'PARTIAL');self.assertEqual(result['verdict'],'PARTIAL');self.assertEqual(result['capacityAcceptance'],'NOT_GRANTED');self.assertEqual(result['optionalObservations']['measurements']['verdict'],'UNMEASURED');self.assertIsNone(result['optionalObservations'].get('zero'))
  for error in (RuntimeError('M7_SOURCE_MISMATCH'),RuntimeError('M7_DISCOVERY_WRONG_DATA')):
   with tempfile.TemporaryDirectory() as root:
    d=Path(root)
    if 'WRONG_DATA' in str(error):error.oracleFindings={'verdict':'FAIL','failures':['synthetic mismatch']}
    with self.assertRaises(RuntimeError):self.summary(d,counts=error if hasattr(error,'oracleFindings') else None,source_error=None if hasattr(error,'oracleFindings') else error)
    result=json.loads((d/'summary.json').read_text());self.assertEqual(result['verdict'],'FAIL');self.assertEqual(result['failure']['code'],str(error))
    if hasattr(error,'oracleFindings'):self.assertEqual(result['oracleFindings'],error.oracleFindings)

if __name__=='__main__':unittest.main()
