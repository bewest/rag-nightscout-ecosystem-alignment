"""Offline actual-row classification; no stack calls or changed progress policy."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path('<alignment>/externals/work/alignment-d6-decisions-20261111')
sys.path.insert(0,str(ROOT/'tools/mt-bench/m7-joined'))
import evaluator_progress as p
r=Path(__file__).parent;value=json.loads((r/'observation.private.json').read_text());proof=value['proof'];services=sorted(value['containers']);manifest=json.loads((r/'instrument-manifest.json').read_text())
assert value['instrumentCommit']==manifest['commit']=='4ddea55301c3d1f95faf25e15a80051bbb122e8b'
assert value['instrumentSha256']==manifest['sha256']=='157d7038c3b5a196e95c766b5777e6686bd1d59a37e3e5772ede4eea2daf6970'
assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in manifest['files'].items())
assert p.verify(proof,2,services,'idle')==value['result'];decoded,ids=p.decode_rounds(proof,2,services)
windows=[]
for index,snapshot in enumerate(proof['rounds']):
 for service in services:
  read=snapshot['sampleWindows'][service];assert len(read['helperObservedAtMs'])==1
  at=read['helperObservedAtMs'][0];assert read['readStartedAtMs']<=at<=read['readEndedAtMs']
  for packed in snapshot['rows']:
   row=dict(zip(p.COLUMNS,packed))
   if row['service']!=service:continue
   due=row['dueAt'];status='observed-null' if due is None else 'future-through-read-end' if due>read['readEndedAtMs'] else 'at-or-before-read-start' if due<=read['readStartedAtMs'] else 'inside-read-window'
   windows.append({'round':index,**row,**read,'dueClassification':status,'dueMinusReadEndMs':None if due is None else due-read['readEndedAtMs']})
per=[]
for tenant in sorted(ids):
 a,b=decoded[0]['owners'][tenant],decoded[-1]['owners'][tenant]
 per.append({'tenant':tenant,'service':a['service'],'runtimeId':a['runtimeId'],'generation':a['generation'],'baseline':{k:a[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles','dueAt','dueReason')},'end':{k:b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles','dueAt','dueReason')},'completedAcquisitionDelta':b['completedAcquisitions']-a['completedAcquisitions'],'completedTimeDelta':b['completedTimeCycles']-a['completedTimeCycles'],'failedDelta':b['failedCompletions']-a['failedCompletions']})
controls=[]
for mode in ('frozen-success','hidden-failure','foreign-work','runtime-reset','missing-foreign-row','boolean-due','missing-due-column'):
 broken=copy.deepcopy(proof)
 if mode=='frozen-success':
  baseline={(x[0],x[1]):x for x in broken['rounds'][0]['rows']}
  for snap in broken['rounds'][1:]:
   for row in snap['rows']:
    for key in ('completedAcquisitions','completedTimeCycles','legacyCycles'):row[p.COLUMNS.index(key)]=baseline[(row[0],row[1])][p.COLUMNS.index(key)]
 elif mode=='runtime-reset':broken['rounds'][-1]['instances'][services[0]]['runtimeId']='99999999-9999-4999-8999-999999999999'
 else:
  rows=broken['rounds'][-1]['rows'];row=next(x for x in rows if x[p.COLUMNS.index('admitted')]) if mode in ('hidden-failure','boolean-due','missing-due-column') else next(x for x in rows if not x[p.COLUMNS.index('admitted')])
  if mode=='missing-foreign-row':rows.remove(row)
  elif mode=='missing-due-column':row.pop()
  elif mode=='boolean-due':row[p.COLUMNS.index('dueAt')]=False
  else:row[p.COLUMNS.index('failedCompletions' if mode=='hidden-failure' else 'completedTimeCycles')]+=1
 try:p.verify(broken,2,services,'idle')
 except p.Refused as error:controls.append({'control':mode,'verdict':error.verdict,'code':str(error)})
 else:raise AssertionError('CONTROL_FALSE_PASS '+mode)
 assert p.verify(proof,2,services,'idle')==value['result']
commands=[json.loads(f.read_text()) for f in r.glob('*.command.json')];raw=(r/'observation.private.json').read_bytes();compressed=(r/'observation.private.json.gz').read_bytes();assert gzip.decompress(compressed)==raw
out={'sequenceScope':'post-EVALUATOR-handoff / BEFORE controlled RT movement or B161 write','verdict':'PASS','source':value['source'],'binding':value['binding'],'imageId':value['imageId'],'instrumentCommit':value['instrumentCommit'],'instrumentSha256':value['instrumentSha256'],'nonce':value['nonce'],'elapsedSeconds':value['elapsedSeconds'],'calls':len(commands),'successfulCalls':sum(x['returncode']==0 for x in commands),'responseBytes':sum(x['bytes'] for x in commands),'collectorParallelWallSeconds':value['result']['collectorWallSeconds'],'sumPerInstanceExecWallSeconds':sum(x['wallSeconds'] for x in commands),'perTenant':per,'sampledRows':windows,'controls':controls,'restored':'PASS','rawSha256':hashlib.sha256(raw).hexdigest(),'gzipSha256':hashlib.sha256(compressed).hexdigest(),'limits':'read-time bracket classifications only; no strict missed-deadline/cold-cohort/capacity/recovery or post-RT-move claim'}
(r/'classification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:x for k,x in out.items() if k!='sampledRows'},indent=2))
