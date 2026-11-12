from pathlib import Path
import subprocess
cases=[
 ('alias-origin','lib/tenant-registry/resolver.js',"if (await active(alias, 'alias') !== tenant) throw refuse('TENANT_ORIGIN_REFUSED');","if (false) throw refuse('TENANT_ORIGIN_REFUSED');",'tests/tenant-registry-resolver.test.js','RR_ORIGIN','Missing expected rejection'),
 ('human-key-refresh','lib/human-session/registry-access.js','if (!hit || hit.entry !== entry) {','if (!hit) {','tests/registry-human-session.test.js','RH_REFRESH','Missing expected rejection'),
 ('origin-binding','lib/human-session/registry-runtime.js',"const key = tenant + ':' + origin;","const key = tenant;",'tests/registry-human-session.test.js','RH_ORIGINS','403 !== 200'),
 ('origin-cache-bound','lib/human-session/registry-runtime.js','if (cache.size >= max) {','if (false && cache.size >= max) {','tests/registry-human-session.test.js','RH_ORIGINS','3 !== 2'),
]
for name,file,old,new,test,grep,symptom in cases:
 p=Path(file);original=p.read_text();assert old in original,name
 try:
  p.write_text(original.replace(old,new,1))
  r=subprocess.run(['node','node_modules/mocha/bin/mocha.js','--fail-zero','--reporter','dot',test,'--grep',grep],text=True,capture_output=True,timeout=30)
  out=r.stdout+r.stderr;Path('/tmp/registry-control-'+name+'.log').write_text(out)
  print(name,'exit',r.returncode,'semantic symptom',symptom in out)
  if r.returncode==0 or symptom not in out:print(out[-2000:]);raise RuntimeError(name)
 finally:p.write_text(original)
p=Path('lib/tenant-registry/provision.js');original=p.read_text();needle="return found.complete ? { outcome: 'existing' }";assert needle in original
try:
 p.write_text(original.replace(needle,"return true ? { outcome: 'existing' }",1))
 r=subprocess.run(['node','/tmp/registry-native-run.cjs','tests/tenant-registry-provision.integration.test.js','--grep','PV_EXISTING_COMPLETE'],text=True,capture_output=True,timeout=90)
 out=r.stdout+r.stderr;Path('/tmp/registry-control-incomplete.log').write_text(out)
 print('incomplete-existing','exit',r.returncode,'all four semantic failures',out.count("+ 'existing'")==4)
 if r.returncode!=4 or out.count("+ 'existing'")!=4:print(out[-4000:]);raise RuntimeError('incomplete-existing')
finally:p.write_text(original)
