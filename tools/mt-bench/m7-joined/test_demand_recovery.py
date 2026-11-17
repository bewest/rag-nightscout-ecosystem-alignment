"""Actual scheduling caller; mocked service effects, no native actors."""
import copy,contextlib,json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import adapter as a
import demand_recovery as r
from test_evaluator_progress import A,B
import test_evaluator_opportunities as opportunity_fixtures
BINDING=opportunity_fixtures.BINDING

class DemandRecovery(unittest.TestCase):
 def auth(self):return [{'tenant':t,'state':'active','phase':'active','generation':'1','claim':None,'artifact':None} for t in (A,B)]
 def captures(self):
  values=opportunity_fixtures.Opportunities().captures()
  for v in values:
   for row in v['rows']:row['restoreGeneration']='1'
  return values
 def manifest(self):return {'profile':'pgstream-sample','runPurpose':'discovery','completionContract':'evaluator-work-v2','cadence':{'restartDuringLoadAfterSeconds':1,'loadSeconds':120,'probeEveryMs':1000},'generator':{'tools':{'node':{'path':'node'}}}}
 def marker(self,path,event='scenario-first-iteration'):
  path.write_text('time="fixture" msg='+json.dumps(json.dumps({'event':event,'atMs':int(time.time()*1000)}))+' source=console\n')
 def test_marker_rejects_setup_and_truncated_events(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'log'
   for event in ('jwt-setup-start','jwt-setup-end'):
    self.marker(p,event);self.assertIsNone(r.active_marker(p))
   self.marker(p);self.assertIsInstance(r.active_marker(p),int)
   p.write_text('scenario-first-iteration');self.assertIsNone(r.active_marker(p))
 def test_scope_window_and_defaults(self):
  m=self.manifest();r.validate(m)
  for change in ({'runPurpose':'acceptance'},{'profile':'capacity'},{'completionContract':'evaluator-work-v1'}):
   with self.assertRaisesRegex(RuntimeError,'SCOPE'):r.validate({**m,**change})
  for c in ({'restartDuringLoadAfterSeconds':True},{'loadSeconds':60},{'probeEveryMs':300000}):
   with self.assertRaisesRegex(RuntimeError,'WINDOW'):r.validate({**m,'cadence':{**m['cadence'],**c}})
  self.assertIsNone(r.selected({'cadence':{}}))
 def test_durable_authority_restore_controls(self):
  b,_,c=self.captures();auth=self.auth();r.assess_bracket(b,c,[A,B],BINDING,auth,auth)
  for key,value in [('generation','2'),('state','suspended'),('claim','foreign'),('artifact','f'*64)]:
   bad=copy.deepcopy(auth);bad[0][key]=value
   with self.assertRaisesRegex(RuntimeError,'AUTHORITY'):r.assess_bracket(b,c,[A,B],BINDING,auth,bad)
  bad=copy.deepcopy(c);bad['rows'][0]['restoreGeneration']='2'
  with self.assertRaisesRegex(RuntimeError,'RESET|RESTORE'):r.assess_bracket(b,bad,[A,B],BINDING,auth,auth)
  pending=copy.deepcopy(c);pending['rows'][0]['completed']['clock']='9';pending['rows'][0]['observed']['clock']='12'
  with self.assertRaisesRegex(RuntimeError,'RESET|PENDING'):r.assess_bracket(b,pending,[A,B],BINDING,auth,auth)
  bad=copy.deepcopy(c);bad['rows'][0]['completed']['clock']='10000'
  with self.assertRaisesRegex(RuntimeError,'VECTOR'):r.assess_bracket(b,bad,[A,B],BINDING,auth,auth)
 def test_postrestart_viewed_output_frame_controls(self):
  receipt={'restartEndedAtMs':10000};probe={'viewerBindings':[{'tenant':A}],'completedOutput':{'verdict':'PASS','witnesses':[{'tenant':A,'requestStartedAt':12000,'ready':True}]},'window':{'expectedFrames':1,'deliveredFrames':1}}
  self.assertEqual(r.verify_probe(probe,receipt)['postRestartViewedWitnesses'],1)
  for field,value in [('ready',False),('tenant',B),('requestStartedAt',9000)]:
   bad=copy.deepcopy(probe);bad['completedOutput']['witnesses'][0][field]=value
   with self.assertRaisesRegex(RuntimeError,'POST_OUTPUT'):r.verify_probe(bad,receipt)
  bad=copy.deepcopy(probe);bad['window']['deliveredFrames']=0
  with self.assertRaisesRegex(RuntimeError,'POST_FRAME'):r.verify_probe(bad,receipt)
 def test_actual_config_receipt_and_remote_projection_bind_selection(self):
  import test_run_configuration as f
  cfg=f.config();cfg['prepare'].update({'restart-during-load-after-seconds':10,'load-seconds':120,'probe-every-ms':1000,'completion-contract':'evaluator-work-v2'})
  with patch.object(a,'instrument',return_value={'sha256':'d'*64}):
   m,receipt=f.packet(cfg)
   self.assertEqual(m['cadence']['restartDuringLoadAfterSeconds'],10)
   f.c.receipt_scope(m,receipt,'run')
   legacy={**receipt,'version':1}
   with self.assertRaisesRegex(RuntimeError,'V2_RECEIPT'):f.c.receipt_scope(m,legacy,'run')
   changed=copy.deepcopy(m);changed['cadence']['restartDuringLoadAfterSeconds']=11
   with self.assertRaisesRegex(RuntimeError,'CONFIGURATION'):f.c.receipt_scope(changed,receipt,'run')
   with self.assertRaisesRegex(RuntimeError,'REMOTE_DEMAND_RECOVERY_LOCAL_ONLY'):
    f.rc.remote_projection(cfg,f.overlay())
 def baseline_error(self,kind='warming'):
  import evaluator_progress as p
  error=p.Refused('M7_EVALUATOR_PROGRESS_ERROR','UNMEASURED' if kind=='warming' else 'FAIL')
  row={'tenant':A,'admitted':True,'ready':False,'code':'EVALUATOR_ACQUISITION_REQUIRED','alert':None,'progress':{'generation':3,'completedAcquisitions':2,'completedTimeCycles':0,'failedCompletions':0}}
  if kind=='failed':row['progress']['failedCompletions']=1;error.verdict='UNMEASURED'
  if kind=='foreign':row['admitted']=False;error.verdict='UNMEASURED'
  if kind=='clinical':row['code']='EVALUATOR_CLINICAL_PROGRESS_STALLED'
  error.diagnostic={'predicate':'OWNER_READY_REQUIRED','field':'ready','warming':True,'failedRow':row}
  error.collection={'queries':1,'bytes':100,'wallSeconds':.1,'completeResponses':True,'diagnostic':error.diagnostic}
  return error
 def test_baseline_discriminator_retains_real_semantic_failures(self):
  self.assertTrue(r.observational_baseline(self.baseline_error()))
  self.assertTrue(r.observational_baseline(self.baseline_error('failed')))
  with self.assertRaisesRegex(RuntimeError,'FOREIGN'):r.observational_baseline(self.baseline_error('foreign'))
  self.assertFalse(r.observational_baseline(self.baseline_error('clinical')))
  for code in ('M7_EVALUATOR_PROGRESS_RESET','M7_COMPLETION_TYPED_STATE','M7_EVALUATOR_PROGRESS_COVERAGE'):
   self.assertFalse(r.observational_baseline(r.p.Refused(code,'UNMEASURED')))
 def test_refusal_diagnostic_is_bounded_without_raw_error_text(self):
  error=self.baseline_error();evidence=r.refusal_evidence(error)
  self.assertEqual(evidence['collection']['queries'],1);self.assertEqual(evidence['diagnostic']['failedRow']['tenant'],A)
  error.diagnostic['huge']='synthetic'*100000
  evidence=r.refusal_evidence(error)
  self.assertLessEqual(len(json.dumps(evidence).encode()),16384);self.assertNotIn('synthetic',json.dumps(evidence))
 def test_unexercised_fault_cannot_claim_recovery_or_require_restart_timestamp(self):
  v=r.verify_probe({}, {'verdict':'UNMEASURED','faultExercised':False})
  self.assertEqual(v['verdict'],'UNMEASURED')
  with self.assertRaisesRegex(RuntimeError,'SKIP_RECEIPT'):r.verify_probe({}, {'verdict':'PASS','faultExercised':False})
 def caller(self,broken=None):
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   d=Path(tmp);out=d/'load';out.mkdir();a.write(d/'tenants.private.json',[{'id':A},{'id':B}]);finished=threading.Event();events=[]
   m=self.manifest();b,_,c=self.captures();captures=iter([b,c]);n=[0]
   def collect():
    n[0]+=1;events.append('capture'+str(n[0]))
    if n[0]==2:finished.set()
    return next(captures),{}
   collect.binding=BINDING
   fake=SimpleNamespace(document=a.document,write=a.write,progress_services=Mock(side_effect=[['evaluator'],['foreign']] if broken=='roles' else None,return_value=['evaluator']),opportunity_collector=lambda *args:collect,progress_attribution=lambda m:{},_COMMAND_DEADLINE=a._COMMAND_DEADLINE,assert_owned=Mock(),progress_fetch=Mock(),orchestration_binding=SimpleNamespace(fixture_argv=lambda *args:['docker','compose','-p','owned'],fixture_mutation_preflight=Mock()),HERE=Path(tmp),remaining_seconds=a.remaining_seconds)
   def command(*args,**kw):
    events.append('restart');self.assertFalse(finished.is_set());self.assertIn('scenario-first-iteration',(out/'k6.log').read_text())
    if broken=='no-change':raise RuntimeError('M7_RESTART_NOT_OBSERVED')
    return json.dumps({'starts':{'evaluator':{'pid':7}},'commandMs':1})
   fake.command=command
   def work():
    events.append('load');self.marker(out/'k6.log','jwt-setup-start' if broken=='setup' else 'scenario-first-iteration')
    if broken=='setup':return
    if broken in ('baseline-unmeasured','baseline-failed','unknown-recovery'):finished.wait(1.4)
    elif not finished.wait(5):raise RuntimeError('TEST_LOAD_JOIN_TIMEOUT')
    events.append('load-ended')
   def proof(*args):events.append('recovery');return {'verdict':'UNMEASURED','code':'M7_EVALUATOR_RECOVERY_NOT_OBSERVED'} if broken=='unknown-recovery' else {'verdict':'PASS'}
   auth=self.auth();after=copy.deepcopy(auth)
   if broken=='authority':after[0]['generation']='2'
   stack.enter_context(patch.object(r,'authority',side_effect=[auth,auth,after]));from test_evaluator_progress import Progress
   baseline=stack.enter_context(patch.object(r.p,'round_view',return_value=Progress().round(1)))
   if broken and broken.startswith('baseline-'):
    kind={'baseline-unmeasured':'warming','baseline-failed':'failed','baseline-foreign':'foreign','baseline-clinical':'clinical'}[broken]
    baseline.side_effect=self.baseline_error(kind)
   stack.enter_context(patch.object(r.recovery,'main',side_effect=proof))
   stack.enter_context(patch.object(r.recovery.subprocess,'run',side_effect=AssertionError('NATIVE_SUBPROCESS_FORBIDDEN_IN_FIXTURE')))
   record=SimpleNamespace(value={},save=Mock());stop=Mock(side_effect=finished.set)
   with a.command_deadline(time.time()+20):
    if broken and broken not in ('baseline-unmeasured','baseline-failed','unknown-recovery'):
     with self.assertRaises(RuntimeError):r.run(fake,d,m,out,work,record,stop)
    else:r.run(fake,d,m,out,work,record,stop)
   result=a.document(out/'demand-recovery.json')
   if broken in ('setup','roles') or broken and broken.startswith('baseline-'):self.assertNotIn('restart',events)
   if broken=='no-change':self.assertNotIn('recovery',events)
   if not broken:
    self.assertEqual(result['verdict'],'PASS');self.assertLess(events.index('restart'),events.index('load-ended'));self.assertLess(events.index('recovery'),events.index('load-ended'))
   elif broken=='unknown-recovery':
    self.assertEqual(result['verdict'],'UNMEASURED');self.assertTrue(result['faultExercised']);stop.assert_not_called();self.assertIn('load-ended',events)
   elif broken in ('baseline-unmeasured','baseline-failed'):
    self.assertEqual(result['verdict'],'UNMEASURED');self.assertFalse(result['faultExercised']);stop.assert_not_called();self.assertIn('load-ended',events)
    self.assertEqual(result['baselineObservation']['collection']['queries'],1);self.assertTrue(baseline.call_args.kwargs['warming'])
   else:self.assertEqual(result['verdict'],'FAIL')
 def test_actual_caller_recovers_while_load_is_live(self):self.caller()
 def test_unknown_runtime_recovery_keeps_ordinary_rest_running(self):self.caller('unknown-recovery')
 def test_restart_before_scenario_refuses(self):self.caller('setup')
 def test_changed_role_roster_refuses_before_effect(self):self.caller('roles')
 def test_no_actual_role_change_refuses_recovery(self):self.caller('no-change')
 def test_changed_authority_refuses(self):self.caller('authority')
 def test_observational_baseline_does_not_cancel_ordinary_work(self):self.caller('baseline-unmeasured')
 def test_warming_unknown_uncredited_attempts_skip_fault_and_keep_traffic(self):self.caller('baseline-failed')
 def test_actual_foreign_baseline_still_stops(self):self.caller('baseline-foreign')
 def test_actual_clinical_stall_baseline_still_stops(self):self.caller('baseline-clinical')

if __name__=='__main__':unittest.main()
