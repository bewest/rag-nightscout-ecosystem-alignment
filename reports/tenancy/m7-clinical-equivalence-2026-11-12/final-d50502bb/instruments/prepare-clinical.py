from pathlib import Path
import subprocess,json,uuid,secrets,os,time
state=Path('<private-state>/clinical');state.mkdir(mode=0o700);(state/'instruments').mkdir()
repo=Path('<workspace>/externals/work/alignment-final-native-clinical-20261112')
rev='275b3bb4b0b0f67d7b0552ef00a90420b6e6a73a'
paths={'trace.cjs':'tools/tenancy/eval-cost/trace.cjs','compare.cjs':'tools/tenancy/eval-cost/compare.cjs','equivalence.cjs':'tools/tenancy/perf-evaluator/equivalence.cjs'}
for name in ('observe-pg.cjs','run.py','within.py','check-within.py','check-control.py','bgnow-control.patch'):paths[name]='reports/tenancy/m7-clinical-equivalence-2026-11-12/instruments/'+name
for name,path in paths.items():
 data=subprocess.check_output(['git','-C',str(repo),'show',rev+':'+path])
 if name in ('run.py','within.py'):data=data.replace(b'crm-clinical-{tree}-20261112',b'crm-clinical-final-{tree}-20261112')
 (state/'instruments'/name).write_bytes(data)
owner=uuid.uuid4().hex;name='ns-api-final-clinical-'+owner[:12]
private=state/'pg.env';private.write_text('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\nPOSTGRES_DB=clinical_final\n');private.chmod(0o600)
image='postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea'
id=subprocess.check_output(['docker','run','--detach','--name',name,'--label','ns.api.final-clinical.owner='+owner,'--publish','127.0.0.1::5432','--env-file',str(private),'--tmpfs','/var/lib/postgresql/data',image],text=True).strip()
row={'owner':owner,'name':name,'id':id,'image':image};(state/'owner.json').write_text(json.dumps(row));(state/'owner.json').chmod(0o600)
for i in range(60):
 if subprocess.run(['docker','exec',id,'pg_isready','-U','postgres','-d','clinical_final'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
 time.sleep(.25)
else:raise RuntimeError('OWN_CLINICAL_PG_NOT_READY')
inspected=json.loads(subprocess.check_output(['docker','inspect',id],text=True))[0]
assert inspected['Config']['Labels']['ns.api.final-clinical.owner']==owner
port=inspected['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort']
password=private.read_text().splitlines()[0].split('=',1)[1]
env={'NS_TEST_POSTGRES_ADMIN_URI':'postgresql://postgres:'+password+'@127.0.0.1:'+port+'/clinical_final','CLINICAL_STATE':str(state),'CLINICAL_WORK_ROOT':'<workspace>/externals/work'}
(state/'environment.private.json').write_text(json.dumps(env));(state/'environment.private.json').chmod(0o600)
facts={'id':id,'imageId':inspected['Image'],'image':image,'serverVersion':subprocess.check_output(['docker','exec',id,'psql','-U','postgres','-d','clinical_final','-Atc','SHOW server_version'],text=True).strip(),'owner':owner,'boundLoopback':inspected['NetworkSettings']['Ports']['5432/tcp'][0]['HostIp']=='127.0.0.1'}
(state/'pg-facts.json').write_text(json.dumps(facts,indent=2)+'\n')
print(json.dumps(facts))
