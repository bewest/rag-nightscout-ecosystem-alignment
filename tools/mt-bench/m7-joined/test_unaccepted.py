"""Recording-only admission/output controls; no Docker/source serving or cloud."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import adapter,contract as c
from profile_provenance import selection,identity
PAIR={'core':'a'*40,'deploy':'b'*40};IMAGE='sha256:'+'c'*64;SHA='d'*64
RUN='synthetic-controller-run'
def manifest():return {'measurementMode':'unaccepted','pair':PAIR,'profile':'remote-pilot','tenants':500,'replicas':1,'instrument':{'sha256':SHA},'imageId':IMAGE,'runId':RUN,'maximumRunMinutes':180,'diagnostics':selection()}
def authorization():return {'version':1,'kind':'joined-measurement-authorization','status':'AUTHORIZED_UNACCEPTED_MEASUREMENT','pair':PAIR,'instrument':SHA,'imageId':IMAGE,'runId':RUN,'functionalAcceptanceAtAuthorization':'PENDING','purpose':'PRE_ACCEPTANCE_BASELINE_ONLY','limits':copy.deepcopy(c.MEASUREMENT_LIMITS)}
def topology():return {'services':{**{role:{'command':['node','serve',role]} for role in ('api','realtime','evaluator')},'vault':{'command':['vault','server']}}}
def aggregate():
 p=identity(selection(),topology())
 m=manifest();row={**c.measurement_output(m),'pair':PAIR,'hostIdentity':'f'*64,'instrument':SHA,'imageId':IMAGE,'verdict':'PASS','measurements':{'complete':True},'profileSelection':p,'profile':'remote-pilot','replicas':1,'cadence':c.CADENCE['remote-pilot']}
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
   d=Path(root)
   def failed_run(*args):
    adapter.write(d/'summary.json',{'verdict':'FAIL','oracle':{'verdict':'RED'}})
    raise RuntimeError('M7_ORACLE_TEST_FAILURE')
   with patch.object(adapter,'run_cell',side_effect=failed_run):
    with self.assertRaisesRegex(RuntimeError,'ORACLE'):adapter.run(d,manifest(),'not-run')
   failure=adapter.document(d/'unaccepted-collection-failure.json');self.assertEqual(failure['collectionStatus'],'FAILED');self.assertEqual(failure['correctnessVerdict'],'FAIL');self.assertEqual(failure['functionalAcceptance'],'UNACCEPTED');self.assertEqual(adapter.document(d/'summary.json')['oracle']['verdict'],'RED')
 def test_source_cli_explicit_flags(self):
  args=adapter.parser().parse_args(['prepare','--directory','/private/not-created','--core-repo','/private/core','--core-commit','a'*40,'--deploy-repo','/private/deploy','--deploy-commit','b'*40,'--image','qualified','--freeze','/private/auth','--profile','remote-pilot','--measurement-mode','unaccepted','--run-id',RUN,'--image-id',IMAGE,'--maximum-run-minutes','180','--tenants','500','--replicas','1'])
  self.assertEqual((args.measurement_mode,args.run_id,args.image_id,args.maximum_run_minutes),('unaccepted',RUN,IMAGE,180))
if __name__=='__main__':unittest.main()
