"""Run only after RT explicitly releases the named window; read-only metadata."""
import argparse,hashlib,json,os,pathlib,subprocess
os.umask(0o077)
p=argparse.ArgumentParser();p.add_argument('window',choices=['default-idle','post-clinical-time']);p.add_argument('--release',required=True);args=p.parse_args()
assert args.release=='rt-explicit-'+args.window,'EXPLICIT_WINDOW_RELEASE_REQUIRED'
root=pathlib.Path('<workspace>')
state=pathlib.Path('/tmp/ns-evaluator-binding-proof-20261112-idle');core=root/'externals/work/crm-evaluator-idlepair-20261112';folder=core/'deploy/multitenant'
source='2d0ae0354a38b4a88f43bc2ae5ec60c085058f64';binding='dcc4a70bafd4edf31c5cab4bf3099883bd7e37f9'
image='sha256:b16e338214d19a409333a079a3950cb97eed9cd7cc00b5eacbff28e4bd72054d';nonce='a8d9cc6f-2c1a-4749-8bf4-b350cc39a4bf';project='ns-evaluator-binding-proof-20261112-idle'
marker=state/'artifacts/owned-pair.json';raw=marker.read_bytes();assert json.loads(raw)['nonce']==nonce
complete=json.loads((state/'bootstrap/complete.json').read_bytes());assert complete['sourceCommit']==source and complete['deployCommit']==binding and complete['registryMode'] is True
primer=json.loads((state/'primer/tenants.json').read_bytes());ids=sorted(row['id'] for row in primer['tenants']);assert primer['version']==1 and len(ids)==2 and len(set(ids))==2
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
value={'source':source,'binding':binding,'imageId':image,'nonce':nonce,'ownedPairFile':str(marker),'ownedPairSha256':hashlib.sha256(raw).hexdigest(),'project':project,'secondsBetween':10,'ids':ids,'composeArgs':compose,'containers':containers,'window':args.window}
file=pathlib.Path(__file__).parent/(args.window+'.spec.private.json')
with file.open('x') as out:json.dump(value,out,separators=(',',':'));out.write('\n')
print('Selected exact released window metadata; no private RPC yet.')
