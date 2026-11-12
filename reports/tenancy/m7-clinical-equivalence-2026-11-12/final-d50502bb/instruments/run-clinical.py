from pathlib import Path
import json,os,subprocess,hashlib,tarfile
s=Path('<private-state>/clinical');e=json.loads((s/'environment.private.json').read_text())
env={k:os.environ[k] for k in ('PATH','HOME','LANG') if k in os.environ};env.update(e,TZ='UTC')
base=Path(e['CLINICAL_WORK_ROOT'])/'crm-clinical-final-base-20261112';candidate=Path(e['CLINICAL_WORK_ROOT'])/'crm-clinical-final-candidate-20261112'
for root,commit in [(base,'5c60aec669362b032a10d6dd7ac368e9c61e8003'),(candidate,'d50502bb6126bda2bb0af384569e1d95de114f2f')]:
 assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==commit
 assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).strip()
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((s/'instruments').iterdir()) if p.is_file()};(s/'execution-instruments.json').write_text(json.dumps(manifest,indent=2)+'\n')
def run(argv,name,extra=None,expected=0):
 with (s/name).open('w') as out:r=subprocess.run(argv,env={**env,**(extra or {})},stdout=out,stderr=subprocess.STDOUT)
 print(name,'exit',r.returncode,flush=True)
 assert r.returncode==expected,(name,r.returncode,expected)
run(['node','-r',str(s/'instruments/observe-pg.cjs'),'-e',"const {Pool}=require(process.env.CRM_ROOT+'/node_modules/pg');const p=new Pool({connectionString:process.env.NS_TEST_POSTGRES_ADMIN_URI});p.query('SELECT 1 AS synthetic_control').then(r=>{if(r.rows[0].synthetic_control!==1)throw Error('PG_CONTROL');return p.end()}).catch(e=>{console.error(e.code||'PG_CONTROL_FAILED');process.exitCode=1})"],'pg-positive-control.log',{'CRM_ROOT':str(candidate)})
run(['python',str(s/'instruments/run.py')],'cross-tree-driver.log')
control=s/'control-core';control.mkdir();archive=s/'control-core.tar'
subprocess.run(['git','-C',str(candidate),'archive','--format=tar','--output',str(archive),'d50502bb6126bda2bb0af384569e1d95de114f2f'],check=True)
with tarfile.open(archive) as tf:tf.extractall(control,filter='data')
(control/'node_modules').symlink_to('<private-state>/deps/node_modules',target_is_directory=True)
plugin=control/'lib/plugins/bgnow.js';original=plugin.read_bytes();before=b'details.mean = mean;';assert original.count(before)==1
mutant=original.replace(before,b'details.mean = mean + 1;');plugin.write_bytes(mutant)
metadata={'source':'d50502bb6126bda2bb0af384569e1d95de114f2f','originalSha256':hashlib.sha256(original).hexdigest(),'mutantSha256':hashlib.sha256(mutant).hexdigest()}
try:
 run(['node','-r',str(s/'instruments/observe-pg.cjs'),str(s/'instruments/trace.cjs')],'control-mutant.log',{'CRM_ROOT':str(control),'PLUGINS':'deploy','MODE':'due','SLOW_MS':'60000','HOURS':'12','OUT':str(s/'control-mutant.trace')})
 run(['node',str(s/'instruments/compare.cjs'),str(s/'deploy-due-60000-candidate.trace'),str(s/'control-mutant.trace')],'control-red.log',expected=1)
finally:plugin.write_bytes(original)
assert plugin.read_bytes()==original
run(['node','-r',str(s/'instruments/observe-pg.cjs'),str(s/'instruments/trace.cjs')],'control-restored.log',{'CRM_ROOT':str(control),'PLUGINS':'deploy','MODE':'due','SLOW_MS':'60000','HOURS':'12','OUT':str(s/'control-restored.trace')})
run(['node',str(s/'instruments/compare.cjs'),str(s/'deploy-due-60000-candidate.trace'),str(s/'control-restored.trace')],'control-green.log')
metadata['restoredSha256']=hashlib.sha256(plugin.read_bytes()).hexdigest();(s/'control-source.json').write_text(json.dumps(metadata,indent=2)+'\n')
run(['python',str(s/'instruments/check-control.py')],'control-summary.json')
run(['python',str(s/'instruments/within.py')],'within-driver.log')
run(['python',str(s/'instruments/check-within.py')],'within-summary.json')
for root in (base,candidate):assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).strip()
print('FINAL_CLINICAL_FOCUSED_COMPLETE',flush=True)
