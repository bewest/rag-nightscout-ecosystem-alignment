from pathlib import Path
import subprocess,json,os
work=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work');deploy=work/'deploy-m7-join-20261112';source=work/'crm-m7-join-20261111';record=Path('/tmp/evaluator-source-qualification-identity.json');pair=json.loads(record.read_text());core=Path(pair['coreWorktree']);state=Path(pair['state']);assert not core.exists()and not state.exists();assert json.loads(Path('/tmp/evaluator-source-canonical-custody.json').read_text())['verified']
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=deploy,text=True).strip()==pair['deploy']and subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==pair['core']
env={k:v for k,v in os.environ.items()if not k.startswith(('NS_','BENCH_','MULTITENANT_'))};env.update(NS_API_REPLICAS='2',NS_REALTIME_WORKERS='2',NS_REALTIME_SHARDS='2',NS_EVALUATOR_WORKERS='3',NS_M7_DIAGNOSTICS='0')
with open('/tmp/evaluator-source-overlay.log','w')as out:subprocess.run(['bash','tools/compose-overlay.sh',str(source),str(core)],cwd=deploy,env=env,check=True,stdout=out,stderr=subprocess.STDOUT)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=core,text=True).strip()==pair['core'];folder=core/'deploy/multitenant'
with open('/tmp/evaluator-source-prepare.log','w')as out:subprocess.run(['node','prepare.js','--state',str(state),'--port',str(pair['port'])],cwd=folder,env=env,check=True,stdout=out,stderr=subprocess.STDOUT)
with open(folder/'.env','a')as out:out.write('NS_DEMO_IMAGE='+pair['imageTag']+'\n')
# Only existing compatible host test dependencies; not copied into the image/context.
assert (core/'package-lock.json').read_bytes()==(source/'package-lock.json').read_bytes();assert not(core/'node_modules').exists();os.symlink((source/'node_modules').resolve(),core/'node_modules')
(state/'artifacts/owned-pair.json').write_text(json.dumps(pair,indent=2)+'\n');os.chmod(state/'artifacts/owned-pair.json',0o600)
with open('/tmp/evaluator-source-build.log','w')as out:subprocess.run(['node','build.js'],cwd=folder,env=env,check=True,stdout=out,stderr=subprocess.STDOUT)
image=json.loads(subprocess.check_output(['docker','image','inspect',pair['imageTag']],text=True))[0];labels=image['Config']['Labels'];assert labels['org.opencontainers.image.revision']==pair['core']and labels['org.nightscout.deploy.revision']==pair['deploy'];pair.update(imageId=image['Id'],imageLabels={k:labels[k]for k in ['org.opencontainers.image.revision','org.nightscout.deploy.revision']});record.write_text(json.dumps(pair,indent=2)+'\n');(state/'artifacts/owned-pair.json').write_text(json.dumps(pair,indent=2)+'\n');print(json.dumps({'built':True,'nonce':pair['nonce'],'imageId':pair['imageId'],'labels':pair['imageLabels'],'project':pair['project']}))
