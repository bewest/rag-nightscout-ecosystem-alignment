from pathlib import Path
import subprocess,json,os
core=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-evaluator-readypair-20261112');deploy=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-evaluator-readypair-20261112');state=Path('/tmp/ns-evaluator-binding-proof-20261112-ready');project=state.name;image='ns-evaluator-binding:ff515-cf5-final';fixture=deploy/'deploy/multitenant/fixtures';opts={'core':str(core),'state':str(state),'project':project}
script="const m=require(process.argv[1]);const o=JSON.parse(process.argv[2]);const r=m.setup(o);console.log(JSON.stringify({outcome:'synthetic-authority-ready',tenants:r.actors.length,boundary:'fixture metadata only'}));"
with open('/tmp/evaluator-ready-settings.log','w')as out:
 os.chmod('/tmp/evaluator-ready-settings.log',0o600)
 r=subprocess.run(['node','-e',script,str(fixture/'evaluator-settings-setup.cjs'),json.dumps(opts)],stdout=out,stderr=subprocess.STDOUT);assert r.returncode==0,'SETTINGS_FIXTURE_SETUP_FAILED'
 def child(mode):
  args=['docker','run','--rm','--network',project+'_backend','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=16m','--cap-drop','ALL','--security-opt','no-new-privileges','-v',str(fixture/'evaluator-settings-control.cjs')+':/opt/evaluator-settings-control.cjs:ro','-v',str(state/'bootstrap/evaluator-settings-control.json')+':/run/ns-settings-control.json:ro',image,'node','/opt/evaluator-settings-control.cjs',mode]
  r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);out.write(r.stdout+r.stderr);out.flush();return r
 r=child('enable');assert r.returncode==0,'SOURCE_SETTINGS_ENABLE_FAILED'
 # Only synthetic configuration-authority metadata is bootstrapped/revoked by
 # this host fixture. Settings values are never sent to SQL.
 control="const m=require(process.argv[1]),o=JSON.parse(process.argv[2]),fs=require('node:fs');const s=JSON.parse(fs.readFileSync(o.state+'/bootstrap/evaluator-settings-control.json'));m.authority(o,s.actors[0],process.argv[3]==='true');"
 subprocess.run(['node','-e',control,str(fixture/'evaluator-settings-setup.cjs'),json.dumps(opts),'false'],check=True,stdout=out,stderr=subprocess.STDOUT)
 try:r=child('revoked');assert r.returncode==0,'REVOKED_AUTHORITY_NOT_REFUSED'
 finally:subprocess.run(['node','-e',control,str(fixture/'evaluator-settings-setup.cjs'),json.dumps(opts),'true'],check=True,stdout=out,stderr=subprocess.STDOUT)
 grant="const m=require(process.argv[1]),o=JSON.parse(process.argv[2]),fs=require('node:fs');const s=JSON.parse(fs.readFileSync(o.state+'/bootstrap/evaluator-settings-control.json')),q=n=>'\"'+n+'\"';m.command(o,process.argv[3]+' UPDATE(can_configure) ON '+q(s.namespaces.authority)+'.tenant_owner_configuration_authority '+(process.argv[3]==='GRANT'?'TO ':'FROM ')+q('nsdemo_evaluator_fixture')+';');"
 subprocess.run(['node','-e',grant,str(fixture/'evaluator-settings-setup.cjs'),json.dumps(opts),'GRANT'],check=True,stdout=out,stderr=subprocess.STDOUT)
 try:
  r=child('admit');assert r.returncode!=0,'EXCESS_WRITER_GRANT_NOT_REFUSED';last=json.loads((r.stdout+r.stderr).strip().splitlines()[-1]);assert last.get('code')=='SETTINGS_STORE_UNSAFE',last.get('code')
 finally:subprocess.run(['node','-e',grant,str(fixture/'evaluator-settings-setup.cjs'),json.dumps(opts),'REVOKE'],check=True,stdout=out,stderr=subprocess.STDOUT)
 r=child('admit');assert r.returncode==0,'RESTORED_WRITER_SCOPE_REFUSED'
print('LOWER_PORT_SETTINGS_AND_AUTHORITY_CONTROLS_PASS')
