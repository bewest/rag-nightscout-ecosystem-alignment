from pathlib import Path
import subprocess,os,json
core=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-evaluator-readypair-20261112');state=Path('/tmp/ns-evaluator-binding-proof-20261112-ready');log=Path('/tmp/evaluator-ready-controlled-move.log');assert not log.exists();env={k:v for k,v in os.environ.items()if not k.startswith(('NS_','BENCH_','MULTITENANT_'))};env.update(NS_UI_TEST_CORE=str(core),NS_COMPOSE_SHARDING_STATE=str(state),NS_COMPOSE_SHARDING_PROJECT=state.name,NS_COMPOSE_SHARDING_PORT='18383',NS_COMPOSE_REPLACEMENT_PROOF='1')
with open(log,'x')as out:
 os.chmod(log,0o600);r=subprocess.run(['node',str(core/'deploy/multitenant/shipping-replacement.integration.test.js')],env=env,stdout=out,stderr=subprocess.STDOUT)
print(json.dumps({'stage':'controlled-realtime-move','exit':r.returncode,'log':str(log)}));raise SystemExit(r.returncode)
