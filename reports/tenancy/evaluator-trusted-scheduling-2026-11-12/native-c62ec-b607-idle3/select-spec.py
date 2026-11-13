"""No use before explicit RT release; read only fresh selected project metadata."""
import argparse,hashlib,json,os,pathlib,subprocess,re
os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('--release',required=True);a=p.parse_args();assert a.release=='root-final-collector-fresh-ingestion-time','EXPLICIT_WINDOW_RELEASE_REQUIRED'
here=pathlib.Path(__file__).parent;pins=json.loads((here/'expected-release-pins.json').read_bytes());assert pins['phase']=='ROOT_FINAL_COLLECTOR_FRESH_RELEASED','RT_IDENTITY_NOT_RELEASED'
assert pins['source']=='9db0ce94f072c8f34aab889f0181afa4269a6758' and pins['binding']=='d76ef17878edb610cdeae75aeef9c07f94b60753'
assert re.fullmatch(r'sha256:[0-9a-f]{64}',pins['imageId']) and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',pins['nonce'])
assert pins['project']=='ns-evaluator-binding-proof-20261112-guard' and pins['port'] is not None
core=pathlib.Path(pins['coreOverlay']);assert core.is_absolute() and core.parent==pathlib.Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work')
folder=core/'deploy/multitenant';state=pathlib.Path('/tmp/ns-evaluator-binding-proof-20261112-guard');marker=state/'artifacts/owned-pair.json';raw=marker.read_bytes();assert json.loads(raw)['nonce']==pins['nonce'];assert hashlib.sha256(raw).hexdigest()==pins['ownedPairSha256']
complete=json.loads((state/'bootstrap/complete.json').read_bytes());assert complete['sourceCommit']==pins['source'] and complete['deployCommit']==pins['binding'] and complete['registryMode'] is True
rows=json.loads((state/'artifacts/evaluator-progress-tenants.json').read_bytes());ids=sorted(row['id'] for row in rows['tenants']);assert len(ids)==2 and len(set(ids))==2
files=[folder/'compose.yaml']+[state/name for name in ('compose.replicas.yaml','compose.realtime.yaml','compose.evaluator.yaml')];assert all(f.is_file() for f in files)
compose=['compose','--project-name',pins['project'],'--env-file',str(folder/'.env')]+[v for f in files for v in ('-f',str(f))]
def run(argv):return subprocess.check_output(['docker',*argv],text=True,timeout=10,stderr=subprocess.PIPE).strip()
containers={}
for service in ('evaluator','evaluator-2','evaluator-3'):
 cid=run([*compose,'ps','-q',service]);assert re.fullmatch('[a-f0-9]{64}',cid)
 view=json.loads(run(['inspect','--format','{"image":{{json .Image}},"running":{{json .State.Running}},"startedAt":{{json .State.StartedAt}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}}}',cid]));assert view['image']==pins['imageId'] and view['running'] is True and view['project']==pins['project'] and view['service']==service
 containers[service]={'id':cid,'startedAt':view['startedAt']}
spec={k:pins[k] for k in ['source','binding','imageId','nonce','project']};spec.update(ownedPairFile=str(marker),ownedPairSha256=hashlib.sha256(raw).hexdigest(),secondsBetween=10,ids=ids,composeArgs=compose,containers=containers)
with (here/'strict-time.spec.private.json').open('x') as out:json.dump(spec,out,separators=(',',':'));out.write('\n')
print('Selected exact released fresh-project post-clinical metadata; no private RPC yet.')
