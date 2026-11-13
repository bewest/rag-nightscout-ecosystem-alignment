from pathlib import Path
import subprocess
cases=[
 ('credential-reread','lib/tenant-connector/runtime.js','if (row.connector && !config.currentTenants) return row.connector;','if (row.connector) return row.connector;',['node','node_modules/mocha/bin/mocha.js','--fail-zero','--reporter','dot','tests/connector-sources.test.js','--grep','CS_DYNAMIC'],'0 failing',False),
 ('request-admission','lib/tenant-connector/frame.js','if (beforeRequest) instance.interceptors.request.use','if (false && beforeRequest) instance.interceptors.request.use',['node','node_modules/mocha/bin/mocha.js','--fail-zero','--reporter','dot','tests/connector-sources.test.js','--grep','CS_REQUEST_GATE'],'Missing expected rejection',True),
 ('source-generation','lib/tenant-connector/runtime.js',"if (config.currentTenants().get(id) !== tenant) throw Object.assign", "if (false && config.currentTenants().get(id) !== tenant) throw Object.assign",['node','node_modules/mocha/bin/mocha.js','--fail-zero','--reporter','dot','tests/connector-sources.test.js','--grep','CS_DYNAMIC'],'Missing expected rejection',True),
 ('generation-cas','lib/tenant-connector/postgres-sources.js',"if ((previous?.generation || 0) !== spec.ifGeneration || remove && !previous) throw fail('CONNECTOR_GENERATION_CONFLICT');","if (false) throw fail('CONNECTOR_GENERATION_CONFLICT');",['node','/tmp/registry-native-run.cjs','tests/connector-sources.integration.test.js','--grep','CS_CAS'],'Missing expected rejection',True),
 ('maintenance-lock','lib/tenant-connector/postgres-sources.js',"if (lock?.held !== true) throw fail('LIFECYCLE_WINDOW_SUSPENDED');","if (false) throw fail('LIFECYCLE_WINDOW_SUSPENDED');",['node','/tmp/registry-native-run.cjs','tests/connector-sources.integration.test.js','--grep','CS_MAINTENANCE'],'Missing expected rejection',True),
 ('normal-revision-cost','lib/tenant-connector/registry-view.js','if (usable && current === revision) {','if (false && usable && current === revision) {',['node','/tmp/registry-native-run.cjs','tests/connector-sources.integration.test.js','--grep','CS_REFRESH'],'CS_NORMAL_COST',True),
 ('constant-rt-settings','lib/server/serve/preview-realtime.js','return base ? settingsOf.applySettings(base, await display.read(tenant)) : null;','return base;',['node','/tmp/registry-native-run.cjs','tests/registry-realtime-settings.integration.test.js'],"'mg/dl' !== 'mmol'",True),
]
for name,file,old,new,cmd,symptom,positive in cases:
 p=Path(file);original=p.read_text();assert old in original,name
 try:
  p.write_text(original.replace(old,new,1))
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=90);out=r.stdout+r.stderr
  Path('/tmp/connector-control-'+name+'.log').write_text(out)
  matched=(symptom in out) if positive else ('AssertionError' in out and 'CS_DYNAMIC' in out)
  print(name,'exit',r.returncode,'semantic symptom',matched,flush=True)
  if r.returncode==0 or not matched:print(out[-3000:]);raise RuntimeError(name)
 finally:p.write_text(original)
