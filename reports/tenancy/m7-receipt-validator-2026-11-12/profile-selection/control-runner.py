from pathlib import Path
import json,os,shutil,subprocess,tempfile
owned=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/alignment-m7-receipt-validator-20261112')
base=Path(tempfile.mkdtemp(prefix='m7-receipt-profile-controls-'));here=base/'tools/queue/gates';here.mkdir(parents=True)
for name in ('m7_joined_receipt.py','test_m7_joined_receipt.py'):shutil.copyfile(owned/'tools/queue/gates'/name,here/name)
bench=base/'tools/mt-bench/m7-joined';bench.mkdir(parents=True)
for name in ('contract.py','profile_provenance.py'):shutil.copyfile(owned/'tools/mt-bench/m7-joined'/name,bench/name)
file=here/'m7_joined_receipt.py';original=file.read_text();rows=[]
controls=[('selection',"need(cell.get('profileSelection')==chosen,'M7_PROFILE_SELECTION_MISMATCH')","need(True,'M7_PROFILE_SELECTION_MISMATCH')",'test_api_comparison_requires_exact_real_settings_diagnostics_topology_selection'),('observation',"need(isinstance(observed,dict) and observed.get('verdict')=='PASS' and integer(observed.get('observations'),1) and type(observed.get('invalid')) is int and observed['invalid']==0 and type(observed.get('mismatch')) is int and observed['mismatch']==0,'M7_FINGERPRINT_UNMEASURED')","need(True,'M7_FINGERPRINT_UNMEASURED')",'test_fingerprint_no_observation_or_failed_observation_never_capacity_passes'),('functional-core',"need(functional_pair['core']==pair['core'],'M7_FUNCTIONAL_CORE_MISMATCH')","need(True,'M7_FUNCTIONAL_CORE_MISMATCH')",'test_core_only_campaign_approved_deployment_pin_and_final_image_proof_stay_distinct')]
for label,needle,replacement,test in controls:
 assert original.count(needle)==1
 for phase,source in [('red',original.replace(needle,replacement)),('restored',original)]:
  file.write_text(source)
  r=subprocess.run(['python','-m','unittest','-v','test_m7_joined_receipt.ReceiptTests.'+test],cwd=here,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True)
  log=Path('/tmp/m7-receipt-profile-'+label+'-'+phase+'-20261112.log');log.write_text(r.stdout+r.stderr)
  assert (r.returncode==0)==(phase=='restored'),(label,phase,r.returncode,r.stderr)
  rows.append({'control':label,'phase':phase,'returnCode':r.returncode,'log':str(log)})
Path('/tmp/m7-receipt-profile-controls-20261112.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
