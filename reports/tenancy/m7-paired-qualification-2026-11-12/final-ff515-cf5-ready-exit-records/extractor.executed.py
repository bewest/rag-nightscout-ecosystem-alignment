from pathlib import Path
import json,re,hashlib
repo=Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/alignment-cohort-snapshot-proof-20261112');home=repo/'reports/tenancy/m7-paired-qualification-2026-11-12/final-ff515-cf5-ready/observed-exit-codes';assert not home.exists();raw=home/'raw';raw.mkdir(parents=True)
files=[Path('/home/bewest/.codex/sessions/2026/11/12')/name for name in ['rollout-2026-11-12T10-36-41-01a1d10c-39fd-73e2-b51b-e9b1b3ad7b5b.jsonl','rollout-2026-11-12T10-43-40-01a1d112-9d6b-74c0-8f3b-503668c66f11.jsonl','rollout-2026-11-12T10-46-28-01a1d115-2c0e-7f70-b8b2-5e84a90d14ec.jsonl','rollout-2026-11-12T10-56-08-01a1d11e-07e4-7cc1-92e7-3b88f0a064c7.jsonl']]
phases={'stock':{'launchCall':478,'pollCall':481,'launchChunk':'e7b9a1','finalChunk':'574329'},'settings':{'launchCall':485,'pollCall':488,'launchChunk':'864543','finalChunk':'eb4238'},'clinical':{'launchCall':491,'pollCall':495,'launchChunk':'993ab2','finalChunk':'a5e40c'},'realtimeMove':{'launchCall':515,'pollCall':520,'launchChunk':'3ca775','finalChunk':'faa421'}}
callOrders={v[k]for v in phases.values()for k in ['launchCall','pollCall']};chunks={v[k]for v in phases.values()for k in ['launchChunk','finalChunk']};calls={};outputs={}
for file in files:
 for line_number,line in enumerate(file.read_bytes().splitlines(keepends=True),1):
  event=json.loads(line);payload=event.get('payload',{})
  if payload.get('type')!='message':continue
  for index,block in enumerate(payload.get('content',[])):
   text=block.get('text','');match=re.match(r'\s*\[(\d+)\] tool exec (call|result):',text)
   if not match:continue
   order=int(match[1]);reference={'localSourceFile':file.name,'jsonlLine':line_number,'contentBlockIndex':index,'messageId':payload.get('id'),'sourceRecordSha256':hashlib.sha256(line).hexdigest(),'rawBlockSha256':hashlib.sha256(text.encode()).hexdigest(),'retainedOrderLabel':order,'sourceKind':'host-retained agent-history block in local review transcript'}
   if match[2]=='call'and order in callOrders and order not in calls:calls[order]={'raw':text,'reference':reference}
   if match[2]=='result':
    try:data=json.JSONDecoder().raw_decode(text.split('Output:\n\n',1)[1].lstrip())[0]
    except (ValueError,IndexError):continue
    chunk=data.get('chunk_id')
    if chunk in chunks and chunk not in outputs:outputs[chunk]={'raw':text,'reference':reference,'parsed':data}
identity=json.loads((home.parent/'captures/identity.json').read_text());records={'version':1,'derivativeOfEvidenceCommit':'e17f4f5f83bd2610be12fb4712398306dd94defd','source':{k:identity[k]for k in ['core','deploy','imageId','nonce','project']},'origin':'Verbatim original tool-call/result entries retained in host review agent-history snapshots; not a new execution and not reconstructed from TAP. Primary Exec datastore availability is not asserted.','phases':{}};provenance={}
for phase,spec in phases.items():
 entries={'launch-call':calls[spec['launchCall']],'launch-result':outputs[spec['launchChunk']],'final-poll-call':calls[spec['pollCall']],'final-result':outputs[spec['finalChunk']]}
 for name,entry in entries.items():
  relative='raw/'+phase+'.'+name+'.txt';(home/relative).write_text(entry['raw']);provenance[relative]=entry['reference']
 launch=entries['launch-result']['parsed'];final=entries['final-result']['parsed'];session=launch['session_id'];assert 'session_id:'+str(session)in entries['final-poll-call']['raw'];assert type(final['exit_code'])is int
 row={'observedProcessReturnCode':final['exit_code'],'observedReturnCodeScope':'original tool-managed outer process, after completion','execSessionId':session,'launchChunk':spec['launchChunk'],'finalChunk':spec['finalChunk'],'verbatimResult':'raw/'+phase+'.final-result.txt','provenanceKey':'raw/'+phase+'.final-result.txt'}
 try:printed=json.loads(final['output'].strip())
 except ValueError:printed=None
 if isinstance(printed,dict)and type(printed.get('exit'))is int:row.update(observedFixtureReturnCode=printed['exit'],observedFixtureStage=printed.get('stage'),observedFixtureLog=printed.get('log'),fixtureCodeOrigin='literal exit field printed from subprocess returncode in original phase stdout')
 else:row.update(observedFixtureReturnCode=None,fixtureCodeOrigin='No numeric child-code stdout was printed. Settings outer process status is directly retained; individual inner controls include expected refusals and their codes are not asserted.')
 records['phases'][phase]=row
(home/'records.json').write_text(json.dumps(records,indent=2)+'\n');(home/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(json.dumps({phase:{k:v for k,v in row.items()if k in ['observedProcessReturnCode','observedFixtureReturnCode','execSessionId']}for phase,row in records['phases'].items()},indent=2))
