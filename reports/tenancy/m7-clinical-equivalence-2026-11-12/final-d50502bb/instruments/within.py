import os, subprocess, pathlib, json, sys
state=pathlib.Path(os.environ['CLINICAL_STATE'])
workspace=pathlib.Path(os.environ['CLINICAL_WORK_ROOT'])
for plugins in ['deploy','full']:
 for tree in ['base','candidate']:
  drop='' if plugins=='full' else 'rawbg,timeago,ar2,errorcodes,cage,sage,iage,bage,pump,loop,upbat,iob,cob,bwp,basal,profile,devicestatus'
  env=dict(os.environ,CRM_ROOT=str(workspace/f'crm-clinical-final-{tree}-20261112'),SLOWS='1000,60000',HOURS='12',DROP_PLUGINS=drop,OUT=str(state/f'within-{plugins}-{tree}.json'))
  with open(state/f'within-{plugins}-{tree}.log','w') as log:
   p=subprocess.run(['node','-r',str(state/'instruments/observe-pg.cjs'),str(state/'instruments/equivalence.cjs')],env=env,stdout=log,stderr=subprocess.STDOUT)
  print('within',plugins,tree,'exit',p.returncode,flush=True)
  if p.returncode: sys.exit(p.returncode)
  lines=(state/f'within-{plugins}-{tree}.log').read_text().splitlines()
  print('\n'.join(x for x in lines if 'EQUIVALENT' in x),flush=True)
