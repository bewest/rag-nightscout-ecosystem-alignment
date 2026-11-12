#!/usr/bin/env python3
"""Reproduce guard ablations in disposable copies of the selected binding tree."""
import argparse, os, pathlib, shutil, subprocess, tempfile
p=argparse.ArgumentParser();p.add_argument('binding',type=pathlib.Path);args=p.parse_args()
source=args.binding/'bindings/compose/multitenant'
variants=[
 ('late-200','fixtures/api-readiness-observation.cjs','if(now()>=deadline){','if(false){','api-readiness-observation.test.js'),
 ('invalid-200','fixtures/api-readiness-observation.cjs','result.status===200&&!result.code','result.status===200','api-readiness-observation.test.js'),
 ('measured-warming','fixtures/api-readiness-observation.cjs','if(seen.status!==200)throw','if(false)throw','api-readiness-observation.test.js'),
 ('setup-order','shipping-sharding.integration.test.js',"const readiness=await require('./fixtures/api-readiness-host.cjs').prepare({core,state,project,tenants:credentials});",'const readiness={matrix:[]};','api-readiness-sequence.test.js'),
 ('missing-tuple','fixtures/api-readiness-host.cjs',None,None,'api-readiness-host.test.js')]
with tempfile.TemporaryDirectory(prefix='readiness-controls-') as scratch:
 for name,file,old,new,test in variants:
  lane=pathlib.Path(scratch)/name;shutil.copytree(source,lane);target=lane/file;text=target.read_text()
  if name=='missing-tuple':
   start=text.index('if(!result?.passed||!Array.isArray(result.matrix)');end=text.index("throw fail('API_READINESS_PRECONDITION_FAILED'",start);text=text[:start]+'if(!result?.passed)'+text[end:]
  else:
   assert old in text;text=text.replace(old,new,1)
  target.write_text(text);result=subprocess.run(['node',str(lane/test)],capture_output=True,text=True,timeout=5)
  print(name, result.returncode);assert result.returncode!=0 and 'not ok ' in result.stdout,(name,result.stdout,result.stderr)

# Failed-repair controls use exact original module bytes with the repaired tests.
with tempfile.TemporaryDirectory(prefix='readiness-originals-') as scratch:
 for name,commit,module,test,symptom in [
  ('original917-shape','91781fe14626c419f30c601fb2fa48e81fe388d6','api-readiness-private.cjs','api-readiness-carrier.test.js','API_READINESS_INVALID_200_FALSE_PASS'),
  ('original85-identity','85cc1732972369aaccd34bc85187a44d5a6add59','api-readiness-host.cjs','api-readiness-host.test.js','Missing expected rejection.'),
  ('original323-transport','3235c287fdec49e669242da56c92ddbcf7f738fb','api-readiness-observation.cjs','api-readiness-observation.test.js','MISSING_TYPED_MEASURED_REQUEST')]:
  lane=pathlib.Path(scratch)/name;shutil.copytree(source,lane)
  original=subprocess.check_output(['git','show',commit+':bindings/compose/multitenant/fixtures/'+module],cwd=args.binding)
  (lane/'fixtures'/module).write_bytes(original);env=dict(os.environ);env.pop('NS_UI_TEST_CORE',None)
  result=subprocess.run(['node',str(lane/test)],capture_output=True,text=True,env=env,timeout=5)
  print(name,result.returncode);assert result.returncode!=0 and symptom in result.stdout,(name,result.stdout,result.stderr)
