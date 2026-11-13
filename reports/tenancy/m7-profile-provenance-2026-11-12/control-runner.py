from pathlib import Path
import json,os,shutil,subprocess,tempfile
owned=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/alignment-m7-profile-provenance-owned-20261112')
base=Path(tempfile.mkdtemp(prefix='m7-profile-controls-20261112-'));here=base/'tools/mt-bench/m7-joined';shutil.copytree(owned/'tools/mt-bench/m7-joined',here,ignore=shutil.ignore_patterns('__pycache__'))
file=base/'tools/mt-bench/capacity/k6/workload.js';file.parent.mkdir(parents=True);shutil.copyfile(owned/'tools/mt-bench/capacity/k6/workload.js',file)
env={**os.environ,'M7_PROFILE_TEST_CORE':'/tmp/ns-m7-profile-core-d8-20261112','M7_PROFILE_TEST_COMMIT':'d8d6b547bb17fc91e440bcab48f323a81a6cd66c','PYTHONDONTWRITEBYTECODE':'1'}
results=[]
def check(label,test,expected):
 result=subprocess.run(['python','-m','unittest','-v','test_profile.Profile.'+test],cwd=here,env=env,capture_output=True,text=True)
 log=Path('/tmp/m7-profile-'+label+'-20261112.log');log.write_text(result.stdout+result.stderr)
 assert (result.returncode==0)==expected,(label,result.returncode,result.stderr)
 results.append({'control':label,'returnCode':result.returncode,'expected':'GREEN' if expected else 'RED','log':str(log)})
file=here/'workload.py';original=file.read_text();needle="if (sha256(encoded, 'hex') !== __ENV.SETTINGS_FINGERPRINT) fingerprintMismatch.add(1);";assert original.count(needle)==1
file.write_text(original.replace(needle,'if (false) fingerprintMismatch.add(1);'))
check('fingerprint-ablation-red','test_actual_source_defaults_real_status_and_generated_k6_plugin_control',False)
file.write_text(original);check('fingerprint-restored-green','test_actual_source_defaults_real_status_and_generated_k6_plugin_control',True)
file=here/'profile_provenance.py';original=file.read_text();needle="require(all(spec.get('environment',{}).get(k)==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_ENV_MISMATCH')";assert original.count(needle)==1
file.write_text(original.replace(needle,"require(True,'M7_DIAGNOSTICS_ENV_MISMATCH')"))
check('diagnostics-ablation-red','test_diagnostics_default_bounds_and_composed_dropped_or_changed_flags',False)
file.write_text(original);check('diagnostics-restored-green','test_diagnostics_default_bounds_and_composed_dropped_or_changed_flags',True)
file=here/'reduce.py';original=file.read_text();old=subprocess.check_output(['git','-C',str(owned),'show','08bce37e9b275f5f43dbb29118b2149c7efb4576:tools/mt-bench/m7-joined/reduce.py'],text=True);file.write_text(old)
check('reducer-original-red','test_stats_only_exited_k6_separate_and_unknown_serving_missing_fail',False)
file.write_text(original);check('reducer-restored-green','test_stats_only_exited_k6_separate_and_unknown_serving_missing_fail',True)
Path('/tmp/m7-profile-controls-20261112.json').write_text(json.dumps({'scratch':str(base),'controls':results},indent=2)+'\n')
print(json.dumps(results,indent=2))
