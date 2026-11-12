import os, subprocess, pathlib, json, sys
state=pathlib.Path(os.environ['CLINICAL_STATE'])
workspace=pathlib.Path(os.environ['CLINICAL_WORK_ROOT'])
results=[]
for plugins in ['deploy','full']:
 for mode, slow in [('base','1000'),('due','1000'),('due','60000')]:
  case=f'{plugins}-{mode}-{slow}'
  for tree in ['base','candidate']:
   env=dict(os.environ,CRM_ROOT=str(workspace/f'crm-clinical-final-{tree}-20261112'), PLUGINS=plugins,MODE=mode,SLOW_MS=slow,HOURS='12',OUT=str(state/f'{case}-{tree}.trace'))
   with open(state/f'{case}-{tree}.log','w') as log:
    p=subprocess.run(['node','-r',str(state/'instruments/observe-pg.cjs'),str(state/'instruments/trace.cjs')],env=env,stdout=log,stderr=subprocess.STDOUT)
   print(case,tree,'exit',p.returncode,flush=True)
   if p.returncode: sys.exit(p.returncode)
  p=subprocess.run(['node',str(state/'instruments/compare.cjs'),str(state/f'{case}-base.trace'),str(state/f'{case}-candidate.trace')],capture_output=True,text=True)
  (state/f'{case}-compare.log').write_text(p.stdout+p.stderr)
  print(p.stdout,flush=True)
  results.append({'case':case,'exit':p.returncode})
  (state/'results.json').write_text(json.dumps(results,indent=2))
  if p.returncode: sys.exit(p.returncode)
