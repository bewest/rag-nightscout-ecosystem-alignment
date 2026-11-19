"""Receipt-bound component inputs/argv/reduction; no actors start on import."""
import copy,hashlib,json,math,re
from pathlib import Path

def need(ok,code):
 if not ok:raise RuntimeError('REMOTE_COMPONENT_'+code)
def plan(value,cohort):
 need(type(cohort)is int and cohort>=16,'COHORT')
 need(isinstance(value,dict)and set(value)=={'version','cases'}and type(value['version'])is int and value['version']==1,'PLAN_SHAPE')
 cases=value['cases'];need(isinstance(cases,list)and 1<=len(cases)<=6,'CASE_BOUND');ids=[]
 for c in cases:
  need(isinstance(c,dict)and set(c)=={'id','kind','rate','seconds','sampleTenants','viewers','probeEveryMs','maxWrites'},'CASE_SHAPE')
  need(isinstance(c['id'],str)and re.fullmatch('[a-z][a-z0-9-]{1,31}',c['id']),'CASE_ID');ids.append(c['id'])
  need(all(type(c[k])is int for k in ('seconds','sampleTenants','viewers','probeEveryMs','maxWrites'))and c['sampleTenants']==16,'SAMPLE')
  if c['kind']=='rest':
   need(type(c['rate'])in(int,float)and math.isfinite(c['rate'])and 1<=c['rate']<=10000 and c['seconds']==310 and c['viewers']==2 and c['probeEveryMs']==300000 and c['maxWrites']==2,'REST_CASE')
  elif c['kind']=='evrt':
   need(c['rate']==0 and type(c['rate'])is int and c['seconds']==32 and c['viewers']in(1,2,4)and c['probeEveryMs']==1000 and c['maxWrites']==32,'EVRT_CASE')
  else:need(False,'KIND')
 need(len(set(ids))==len(ids),'DUPLICATE_CASE');return value

def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def selected(rows):
 need(isinstance(rows,list)and len(rows)>=16 and len({x['id']for x in rows})==len(rows),'ROSTER');return[rows[math.floor(i*len(rows)/16)]for i in range(16)]
def expected_clients(c):return c['sampleTenants']*c['viewers']
def phase_payload(c):return{'caseId':c['id'],'caseSha256':identity(c)}
def expect_payload(value,c,extra=None):need(value=={**phase_payload(c),**(extra or{})},'PHASE_BINDING')

def commands(directory,b,descriptor,c,k6_name,start_ms):
 # The actual existing remote builder supplies public-only probe and exact seven-shape k6 argv.
 import generator
 plan({'version':1,'cases':[c]},b['tenants']);d=Path(directory);out=d/'components'/c['id']/'load'
 probe,k6=generator.traffic_commands(d,b,descriptor,k6_name,start_ms)
 runid=descriptor['trafficRunId']+'-'+c['id'];need(re.fullmatch('[a-z0-9-]{1,120}',runid),'MARKER')
 def setarg(argv,flag,value):
  need(argv.count(flag)==1,'ARGV_SEAM');argv[argv.index(flag)+1]=str(value)
 for flag,value in {'--tenants':out.parent/'tenants.private.json','--runid':runid,'--per':c['viewers'],'--window':c['seconds'],'--probeEvery':c['probeEveryMs'],'--out':out/'probe.json','--signal':out/'.window'}.items():setarg(probe,flag,value)
 probe+=['--maxWrites',str(c['maxWrites'])]
 if c['kind']=='evrt':k6=None
 else:
  replacements={str(d/'load')+':/out':str(out)+':/out','RUN_ID='+descriptor['trafficRunId']:'RUN_ID='+runid}
  k6=[replacements.get(str(x),str(x))for x in k6]
  for key,value in [('DURATION',c['seconds']),('OFFERED_RPS',c['rate'])]:
   matches=[i for i,x in enumerate(k6)if x.startswith(key+'=')]
   if matches:need(len(matches)==1,'K6_ENV');k6[matches[0]]=key+'='+str(value)
   else:i=k6.index(b['k6Image']);k6[i:i]=['-e',key+'='+str(value)]
 return{'probe':list(map(str,probe)),'k6':k6,'output':str(out),'runId':runid,'inputScope':{'rosterTenants':b['tenants'],'sampleTenants':16,'stockClients':expected_clients(c),'viewersPerSampleTenant':c['viewers'],'ordinaryRestOfferedRps':c['rate'],'controlledProbeWritesMaximum':c['maxWrites']},'placement':{'probe':'DRIVER UID1001 public-only HTTP/polling; no Docker/SSH/privateRPC','k6':'DRIVER trusted supervisor starts pinned exact container'if k6 else'NOT_RUN','SQLPrivateInspectAndCompletionOracle':'SUT UID1000 only','crossHostClockSubtraction':False}}

def result_names(cases):
 names=['generator-provenance.json']
 for c in cases:
  files=['probe.json','fanout.json','event-loop.jsonl','generator-metrics.json','component-launch.json']
  if c['kind']=='rest':files+=['k6-summary.json','k6-launch.json']
  names+=['components/'+c['id']+'/'+name for name in files]
 return names

def metric(metrics,key,field='count'):
 v=metrics.get(key);v=v.get('values',v)if isinstance(v,dict)else{}
 x=v.get(field,'UNMEASURED');return x if type(x)in(int,float)and math.isfinite(x)and x>=0 else'UNMEASURED'
def reduce_case(c,probe,completion,oracle=None,k6=None,cost=None,progress=None):
 w=probe.get('window',{});metrics=(k6 or{}).get('metrics',{})
 complete=completion.get('verdict')=='PASS'and len(completion.get('witnesses',[]))==c['maxWrites']and w.get('writes',{}).get('ok')==c['maxWrites']and w.get('expectedFrames')==c['maxWrites']*c['viewers']and w.get('writes',{}).get('failed')==0 and w.get('deliveredFrames')==w.get('expectedFrames')and w.get('sockets')==expected_clients(c)and w.get('connectedAtEnd')==expected_clients(c)
 progress_summary={'measurement':'UNMEASURED'}
 if progress is not None:
  before=progress.get('before',{}).get('progress');after=progress.get('after',{}).get('progress')
  if before and after and before['instances']==after['instances']:
   deltas=[]
   for tenant,x in before['owners'].items():
    y=after['owners'].get(tenant,{});delta={k:y.get(k,-1)-x[k]for k in('completedAcquisitions','completedTimeCycles','failedCompletions')};valid=all(v>=0 for v in delta.values());deltas.append({'tenant':tenant,'status':'OBSERVED'if valid else'UNMEASURED_RESET','deltas':delta})
   progress_summary={'measurement':'SELECTED_BOOKEND_PROGRESS','tenants':deltas,'scope':'acquisition/time completions and failed releases separate; no executor duration or per-write latency'};complete=complete and all(x['status']=='OBSERVED'and x['deltas']['failedCompletions']==0 for x in deltas)
  else:complete=False
 if c['kind']=='rest':complete=complete and oracle is not None and oracle.get('verdict')=='GREEN'and oracle.get('uncertain')==0 and all(metric(metrics,k,f)==0 for k,f in [('http_req_failed','rate'),('writes_refused','count'),('responses_refused','count'),('dropped_iterations','count')])
 return{'kind':'remote-component-observation-v1','case':c,'status':'OBSERVED_SELECTED_CHAIN'if complete else'PARTIAL','capacityAcceptance':'NOT_GRANTED','clientSendToFrameMs':w.get('writeToFrameMs'),'probeWrites':w.get('writes'),'expectedFrames':w.get('expectedFrames'),'deliveredFrames':w.get('deliveredFrames'),'completedOutput':completion,'ordinaryREST':{'measurement':'NOT_RUN'}if c['kind']=='evrt'else{'httpDurationGlobal':metrics.get('http_req_duration','UNMEASURED'),'httpFailureRate':metric(metrics,'http_req_failed','rate'),'drops':metric(metrics,'dropped_iterations'),'writesAccepted':metric(metrics,'writes_ok'),'writesUncertain':metric(metrics,'writes_uncertain'),'writesRefused':metric(metrics,'writes_refused'),'responsesRefused':metric(metrics,'responses_refused'),'shapeTails':{k:v for k,v in metrics.items()if k.startswith('http_req_duration{shape:')},'storedOracle':oracle,'tailScope':'k6 global HTTP includes its serial JWTsetup; selected probe JWT/stock traffic is separate'},'sutBookends':cost or{'measurement':'UNMEASURED'},'selectedEVRTProgress':{'summary':progress_summary,'rawBookends':progress or{'measurement':'UNMEASURED'}},'clocks':{'driver':'performance.now send-to-client-frame','sut':'local query/request monotonic brackets and progress/due ages','writeToEvaluationMs':'UNMEASURED','outputCommitToClientMs':'UNMEASURED','evaluatorExecutionMs':'UNMEASURED','crossHostSubtraction':False},'scope':'REST logical curve uses32declared sampled client background; EVRT is low-load16tenant/32write selected fanout, not saturation or full-roster clinical equivalence; timers/recovery NOT_RUN'}
