from pathlib import Path
import subprocess,os,sys,time
core=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-evaluator-readypair-20261112');state=Path('/tmp/ns-evaluator-binding-proof-20261112-ready');cwd=core/'deploy/multitenant';project=state.name
compose=['docker','compose','-p',project,'--env-file','.env','-f','compose.yaml','-f',str(state/'compose.replicas.yaml'),'-f',str(state/'compose.realtime.yaml'),'-f',str(state/'compose.evaluator.yaml')]
commands=[('image-check',['node','build.js','--check-image']),('infrastructure',compose+['--profile','ops','run','--rm','bootstrap']),('private-admin-feed',compose+['up','-d','--no-build','--pull','never','--wait','--wait-timeout','90','admin','feed-reader']),('registry-provision',compose+['--profile','ops','run','--rm','--no-deps','primer','node','deploy/multitenant/prime.js','provision']),('restore-commission',compose+['--profile','ops','run','--rm','--no-deps','bootstrap','node','deploy/multitenant/commission-restore.js']),('pool-initial-two',compose+['--profile','ops','run','--rm','--no-deps','primer','node','deploy/multitenant/evaluator-pool.js','set','2']),('fixed-api-start',compose+['up','-d','--no-build','--pull','never','--wait','--wait-timeout','180','api','api-2']),('api-lab-prime',compose+['--profile','ops','run','--rm','--no-deps','primer','node','deploy/multitenant/prime.js','prime']),('private-primer-publish',['node','publish-primer.js',str(state)]),('remaining-fixed-roles',compose+['up','-d','--no-build','--pull','never','--wait','--wait-timeout','180','realtime','realtime-2','socket-edge','evaluator','evaluator-2','evaluator-3','tenant-admin','ui','nginx'])]
env={k:v for k,v in os.environ.items() if not k.startswith('NS_')}
with open('/tmp/evaluator-ready-start.log','w')as log:
 os.chmod('/tmp/evaluator-ready-start.log',0o600)
 for phase,args in commands:
  print('FRESH_START_PHASE',phase,flush=True);log.write('\nPHASE '+phase+'\n');log.flush()
  r=subprocess.run(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
  print('FRESH_START_EXIT',phase,r.returncode,flush=True)
  if r.returncode:raise SystemExit(r.returncode)
print('FRESH_FIXED_ROSTER_STARTED',flush=True)
