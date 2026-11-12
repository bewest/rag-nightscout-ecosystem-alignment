"""Run only after RT explicitly releases the named window; read-only metadata."""
import argparse,hashlib,json,os,pathlib,subprocess
os.umask(0o077)
p=argparse.ArgumentParser();p.add_argument('--release',required=True);args=p.parse_args()
assert args.release=='rt-explicit-post-clinical-time','EXPLICIT_WINDOW_RELEASE_REQUIRED'
root=pathlib.Path('/home/bewest/src/rag-nightscout-ecosystem-alignment')
state=pathlib.Path('/tmp/ns-evaluator-binding-proof-20261112-ready');core=root/'externals/work/crm-evaluator-readypair-20261112';folder=core/'deploy/multitenant'
source='ff5156b984424f1ef34bcef22d5bfa0071354cfa';binding='cf5bda3f2d189bac5d60269df5644759c40db9e1'
image='sha256:399dea76f971451143b65c02be37c99e76d240d607d1f5b45a35fd564d7e6fd2';nonce='0dc3af55-99df-4fd9-8b1b-8771f68be6f1';project='ns-evaluator-binding-proof-20261112-ready'
marker=state/'artifacts/owned-pair.json';raw=marker.read_bytes();assert json.loads(raw)['nonce']==nonce
complete=json.loads((state/'bootstrap/complete.json').read_bytes());assert complete['sourceCommit']==source and complete['deployCommit']==binding and complete['registryMode'] is True
tenant_ids=json.loads((state/'artifacts/evaluator-progress-tenants.json').read_bytes());ids=sorted(row['id'] for row in tenant_ids['tenants']);assert len(ids)==2 and len(set(ids))==2
files=[folder/'compose.yaml']+[state/name for name in ('compose.replicas.yaml','compose.realtime.yaml','compose.evaluator.yaml')]
assert all(file.is_file() for file in files)
compose=['compose','--project-name',project,'--env-file',str(folder/'.env')]+[value for file in files for value in ('-f',str(file))]
def run(argv):return subprocess.check_output(['docker',*argv],text=True,timeout=10,stderr=subprocess.PIPE).strip()
containers={}
for service in ('evaluator','evaluator-2','evaluator-3'):
 cid=run([*compose,'ps','-q',service]);assert len(cid)==64 and all(c in '0123456789abcdef' for c in cid)
 view=json.loads(run(['inspect','--format','{"image":{{json .Image}},"running":{{json .State.Running}},"startedAt":{{json .State.StartedAt}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}}}',cid]));assert view['image']==image and view['running'] is True
 assert view['project']==project and view['service']==service
 containers[service]={'id':cid,'startedAt':view['startedAt']}
value={'source':source,'binding':binding,'imageId':image,'nonce':nonce,'ownedPairFile':str(marker),'ownedPairSha256':hashlib.sha256(raw).hexdigest(),'project':project,'secondsBetween':10,'ids':ids,'composeArgs':compose,'containers':containers}
file=pathlib.Path(__file__).parent/'strict-time.spec.private.json'
with file.open('x') as out:json.dump(value,out,separators=(',',':'));out.write('\n')
print('Selected exact released window metadata; no private RPC yet.')
