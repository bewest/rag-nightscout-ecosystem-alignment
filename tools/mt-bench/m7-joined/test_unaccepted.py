"""Recording-only admission/output controls; no Docker/source serving or cloud."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import adapter,campaign,contract as c
from profile_provenance import selection,identity
PAIR={'core':'a'*40,'deploy':'b'*40};IMAGE='sha256:'+'c'*64;SHA='d'*64
RUN='synthetic-controller-run'
def manifest():return {'measurementMode':'unaccepted','pair':PAIR,'profile':'remote-pilot','tenants':500,'replicas':1,'instrument':{'sha256':SHA},'imageId':IMAGE,'runId':RUN,'maximumRunMinutes':180,'diagnostics':selection()}
def authorization():return {'version':1,'kind':'joined-measurement-authorization','status':'AUTHORIZED_UNACCEPTED_MEASUREMENT','pair':PAIR,'instrument':SHA,'imageId':IMAGE,'runId':RUN,'functionalAcceptanceAtAuthorization':'PENDING','purpose':'PRE_ACCEPTANCE_BASELINE_ONLY','limits':copy.deepcopy(c.MEASUREMENT_LIMITS)}
def topology():return {'services':{**{role:{'command':['node','serve',role]} for role in ('api','realtime','evaluator')},'vault':{'command':['vault','server']}}}
def aggregate():
 p=identity({'schema':1,'sha256':'e'*64,'sourceCommit':'a'*40,'sourceBlobs':{}},selection(),topology())
 m=manifest();row={**c.measurement_output(m),'pair':PAIR,'hostIdentity':'f'*64,'instrument':SHA,'imageId':IMAGE,'verdict':'PASS','measurements':{'complete':True},'profileSelection':p,'settingsFingerprintObservation':{'verdict':'PASS','observations':1,'invalid':0,'mismatch':0},'profile':'remote-pilot','replicas':1,'cadence':c.CADENCE['remote-pilot']}
 return {**c.measurement_output(m,aggregate=True),'version':1,'pair':PAIR,'hostIdentity':'f'*64,'instrument':SHA,'imageId':IMAGE,'verdict':'PASS','profileReplicas':1,'profileSelection':p,'diagnostics':selection(),'cells':[{**row,'tenants':n} for n in c.PILOT_COUNTS]}
class Unaccepted(unittest.TestCase):
 def test_exact_authorization_and_old_accepted_path(self):
  m=manifest()
  for n in c.PILOT_COUNTS:
   for op in ('build','deploy','run'):self.assertEqual(c.receipt_scope({**m,'tenants':n},authorization(),op)['kind'],'unaccepted-measurement')
  accepted={**m,'measurementMode':'accepted'}
  self.assertEqual(c.receipt_scope(accepted,{'kind':'joined-acceptance','status':'PASS','pair':PAIR,'evidenceSha256':'e'*64},'run')['kind'],'accepted-capacity')
  with self.assertRaisesRegex(RuntimeError,'FROZEN_ACCEPTANCE_REQUIRED'):c.receipt_scope(accepted,authorization(),'run')
 def test_unknown_claims_wrong_tuple_image_run_hash_limits_refuse(self):
  mutations=[{'pair':{**PAIR,'core':'b'*40}},{'instrument':'0'*64},{'imageId':'sha256:'+'e'*64},{'runId':'another-run'},{'status':'PASS'},{'functionalAcceptanceAtAuthorization':'PASS'},{'purpose':'CAPACITY'},{'claims':['acceptance']},{'evidenceSha256':'e'*64},{'version':True}]
  for changed in mutations:
   with self.subTest(changed=list(changed)),self.assertRaises(RuntimeError):c.receipt_scope(manifest(),{**authorization(),**changed},'run')
  for key,value in [('tenantCounts',[500,1000]),('apiReplicas',2),('realtimeReplicas',2),('evaluatorReplicas',2),('maximumRunMinutes',181),('apiReplicas',True)]:
   bad=authorization();bad['limits'][key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):c.receipt_scope(manifest(),bad,'run')
 def test_wrong_profile_count_replica_diagnostics_request_refuse(self):
  for changed in [{'profile':'capacity'},{'profile':'fresh-image-diagnostic'},{'tenants':10},{'tenants':750.0},{'replicas':2},{'diagnostics':selection('on')},{'diagnostics':selection('off',1000)},{'imageId':None},{'runId':None},{'maximumRunMinutes':181}]:
   with self.subTest(changed=list(changed)),self.assertRaises(RuntimeError):c.receipt_scope({**manifest(),**changed},authorization(),'deploy')
  with self.assertRaises(RuntimeError):c.receipt_scope(manifest(),authorization(),'diagnose')
 def test_actual_selected_topology_refuses_additional_workers_or_agent(self):
  c.measurement_topology(manifest(),topology())
  for role in ('api','realtime','evaluator'):
   bad=topology();bad['services'][role+'-2']=copy.deepcopy(bad['services'][role])
   with self.assertRaisesRegex(RuntimeError,'ROLE_TOPOLOGY'):c.measurement_topology(manifest(),bad)
  for mutate in [lambda x:x['services'].update({'vault-agent':{}}),lambda x:x['services']['vault'].update(command=['vault','agent'])]:
   bad=topology();mutate(bad)
   with self.assertRaisesRegex(RuntimeError,'VAULT_SERVER'):c.measurement_topology(manifest(),bad)
 def test_separate_output_same_profile_and_accepted_checks_refuse_wrapped_cells(self):
  doc=aggregate();self.assertTrue(c.unaccepted_check(doc));self.assertEqual(c.CADENCE['remote-pilot'],{'accel':1,'hotFactor':10,'socketsPerTenant':2,'idleSeconds':120,'loadSeconds':300})
  with self.assertRaisesRegex(RuntimeError,'NOT_ACCEPTANCE'):c.pilot_check(doc)
  with self.assertRaisesRegex(RuntimeError,'NOT_ACCEPTANCE'):c.campaign_check(doc)
  wrapped={**doc,'kind':'m7-joined-remote-pilot'}
  for k in c.UNACCEPTED_SCOPE:wrapped.pop(k)
  with self.assertRaisesRegex(RuntimeError,'NOT_ACCEPTANCE'):c.pilot_check(wrapped)
  for mutate in [lambda x:x['cells'][0].update(verdict='FAIL'),lambda x:x['cells'][0].update(measurements={'complete':False}),lambda x:x['cells'][0].update(runId='wrong'),lambda x:x.update(collectionStatus='FAILED'),lambda x:x['cells'].pop()]:
   bad=aggregate();mutate(bad)
   with self.assertRaises(RuntimeError):c.unaccepted_check(bad)
 def test_run_failure_retains_unaccepted_scope_and_original_correctness(self):
  with tempfile.TemporaryDirectory(prefix='m7-unaccepted-failure-') as root:
   d=Path(root);adapter.write(d/'summary.json',{'verdict':'FAIL','oracle':{'verdict':'RED'}})
   with patch.object(adapter,'run_cell',side_effect=RuntimeError('M7_ORACLE_TEST_FAILURE')):
    with self.assertRaisesRegex(RuntimeError,'ORACLE'):adapter.run(d,manifest(),'not-run')
   failure=adapter.document(d/'unaccepted-collection-failure.json');self.assertEqual(failure['collectionStatus'],'FAILED');self.assertEqual(failure['correctnessVerdict'],'FAIL');self.assertEqual(failure['functionalAcceptance'],'UNACCEPTED');self.assertEqual(adapter.document(d/'summary.json')['oracle']['verdict'],'RED')
 def test_source_cli_explicit_flags(self):
  args=adapter.parser().parse_args(['prepare','--directory','/private/not-created','--core-repo','/private/core','--core-commit','a'*40,'--deploy-repo','/private/deploy','--deploy-commit','b'*40,'--image','qualified','--freeze','/private/auth','--profile','remote-pilot','--measurement-mode','unaccepted','--run-id',RUN,'--image-id',IMAGE,'--maximum-run-minutes','180','--tenants','500','--replicas','1'])
  self.assertEqual((args.measurement_mode,args.run_id,args.image_id,args.maximum_run_minutes),('unaccepted',RUN,IMAGE,180))
 def test_real_receipt_gate_rejects_unaccepted_cell_even_when_otherwise_valid(self):
  directory=Path(__file__).resolve().parents[2]/'queue/gates';sys.path.insert(0,str(directory))
  try:
   spec=importlib.util.spec_from_file_location('receipt_fixtures',directory/'test_m7_joined_receipt.py');fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
   fixture=fixtures.ReceiptTests();fixture.setUp()
   try:
    doc=fixture.capacity(counts=(500,));cell=doc['cells'][0];gate=fixtures.gate
    def check():
     evidence=gate.Evidence(fixture.root);evidence.allowed=fixture.expected['artifacts'];return gate.cell_measurement(cell,fixture.expected,'capacity',cell['hostIdentity'],evidence)
    check();cell.update(c.UNACCEPTED_SCOPE)
    with self.assertRaisesRegex(ValueError,'NOT_ACCEPTANCE'):check()
    fixture.receipt['kind']='joined-measurement-authorization'
    with self.assertRaisesRegex(ValueError,'NOT_ACCEPTANCE'):fixture.check()
   finally:fixture.doCleanups()
  finally:sys.path.pop(0)
 def test_campaign_recording_preserves_counts_scope_and_functional_stop(self):
  for fail_at in (None,750):
   with self.subTest(fail_at=fail_at),tempfile.TemporaryDirectory(prefix='m7-unaccepted-ladder-') as root:
    folder=Path(root);doc=aggregate();master={**doc,'directory':str(folder),'cells':[],'collectionStatus':'FAILED'};seen=[]
    args=SimpleNamespace(mode='pilot',measurement_mode='unaccepted',run_id=RUN,image_id=IMAGE,maximum_run_minutes=180,ceiling_receipt=None,k6_image='recording-only')
    def prepare(options):
     seen.append((options.tenants,options.replicas,options.profile,options.measurement_mode,options.run_id,options.image_id));d=Path(options.directory);d.mkdir();adapter.write(d/'owner.json',{})
    def run(d,m,k6):
     count=int(d.name.split('-')[0][1:]);row=copy.deepcopy(next(r for r in doc['cells'] if r['tenants']==count))
     if count==fail_at:row.update(verdict='FAIL',oracle={'verdict':'RED'})
     adapter.write(d/'summary.json',row)
     if count==fail_at:raise RuntimeError('M7_ORACLE_SYNTHETIC_FAILURE')
    with patch.object(adapter,'generator_tools',return_value={}),patch.object(adapter,'prepare',prepare),patch.object(adapter,'load',side_effect=lambda d:(Path(d),{})),patch.object(adapter,'deploy'),patch.object(adapter,'run',side_effect=run),patch.object(adapter,'down'):
     if fail_at:
      with self.assertRaisesRegex(RuntimeError,'ORACLE'):campaign.ladder(args,1,folder,master)
     else:campaign.ladder(args,1,folder,master)
    self.assertEqual([r[0] for r in seen],[500,750] if fail_at else [500,750,1000]);self.assertTrue(all(r[1:]==(1,'remote-pilot','unaccepted',RUN,IMAGE) for r in seen))
    if fail_at:self.assertTrue(master['functionalBlock']);self.assertEqual(master['collectionStatus'],'FAILED');self.assertEqual(master['cells'][-1]['verdict'],'FAIL');self.assertEqual(master['cells'][-1]['oracle']['verdict'],'RED')
    else:self.assertEqual(len(master['cells']),3)
if __name__=='__main__':unittest.main()
