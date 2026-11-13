"""Evidence gates only. None performs HTTP, SQL, lifecycle effects or retries."""
import hashlib,json,re
UUID=re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
FIELDS=('entries','devicestatus','treatments','probe')
class Refused(RuntimeError):pass
def need(value,code):
    if not value:raise Refused('NATIVE_CLINICAL_'+code)
def roster(ids):
    need(isinstance(ids,list)and len(ids)==16 and len(set(ids))==16 and all(isinstance(x,str)and UUID.fullmatch(x)for x in ids),'COMPLETE_SIXTEEN_ROSTER_REQUIRED')
    return ids
def selector(ids,run_id):
    roster(ids);need(isinstance(run_id,str)and re.fullmatch(r'm7-native-[a-f0-9]{16,32}',run_id),'MARKER')
    return {'version':1,'kind':'native-synthetic-stored-counts','runId':run_id,'tenants':ids}
def canonical_hash(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
def counts(expected,selected,observation,ledgers):
    """Whole roster and source fixed before count effect; independently compare SQL.

    Ledgers are the source probe-accounting snapshots for four collections. Raw
    HTTP status and the explicit 201->accepted classification remain in producer
    receipts. Missing/uncertain/pending evidence cannot earn exact equality.
    """
    selector(selected['tenants'],selected['runId']);ids=selected['tenants'];need(set(ledgers)==set(FIELDS),'LEDGER_COLLECTIONS')
    need(observation.get('kind')=='controlled-native-stored-counts'and observation.get('source')==expected['source']and observation.get('expected')==expected['custody']and observation.get('planSha256')==expected['planSha256'],'COUNT_CUSTODY')
    need(observation.get('selector')==selected and observation.get('selectorSha256')==canonical_hash(selected),'COUNT_SELECTOR')
    foreign=observation.get('foreign');need(isinstance(foreign,dict)and set(foreign)==set(FIELDS)and all(type(v)is int and v>=0 for v in foreign.values()),'FOREIGN_CONTRACT');need(not any(foreign.values()),'FOREIGN_MARKED_WRITES')
    rows=observation.get('counts');need(isinstance(rows,list)and len(rows)==16 and {x.get('tenant')for x in rows}==set(ids),'COUNT_ROSTER')
    actual={row['tenant']:row for row in rows};accepted={x:{}for x in ids}
    for field,ledger in ledgers.items():
        need(ledger.get('version')==2 and ledger.get('kind')=='m7-discovery-probe-accounting'and ledger.get('runId')==selected['runId']and ledger.get('roster')==ids and ledger.get('admissionsClosed')is True,'LEDGER_IDENTITY')
        by=ledger.get('byTenant');need(isinstance(by,dict)and set(by)<=set(ids),'LEDGER_ROSTER');total=0
        for tenant in ids:
            row=by.get(tenant,{'attempts':0,'accepted':0,'uncertain':0,'refused':0,'pending':0})
            need(set(row)=={'attempts','accepted','uncertain','refused','pending'}and all(type(n)is int and n>=0 for n in row.values()),'LEDGER_CONTRACT')
            need(row['attempts']==sum(row[k]for k in ('accepted','uncertain','refused','pending')),'LEDGER_CONSERVATION');total+=row['attempts']
            need(row['uncertain']==row['pending']==0,'HTTP_OUTCOME_UNMEASURED');accepted[tenant][field]=row['accepted']
        need(type(ledger.get('attempts'))is int and total==ledger['attempts'],'LEDGER_CONSERVATION')
    for tenant in ids:
        row=actual[tenant];need(set(row)=={'tenant','entriesTotal',*FIELDS}and all(type(row[k])is int and row[k]>=0 for k in ('entriesTotal',*FIELDS)),'COUNT_CONTRACT')
        need(all(row[k]==accepted[tenant][k]for k in FIELDS),'PER_TENANT_STORED_MISMATCH')
        need(row['entriesTotal']==1+row['entries']+row['probe'],'UNMARKED_SEED_OR_EXTRA_ENTRY')
    return {'criterion':'independent-stored-counts','result':'PASS','tenants':16,'foreign':foreign,'scope':'exact closed client outcomes and one source-primer seed per selected synthetic tenant'}
def restarted(before,after,participants):
    need(set(before)==set(after)==set(participants),'RESTART_ROSTER')
    for slot in participants:
        a,b=before[slot],after[slot];need(a['cid']!=b['cid']and a['startedAt']!=b['startedAt']and a['source']==b['source']and a['imageId']==b['imageId'],'OLD_OR_FOREIGN_RESTART')
    return {'criterion':'controlled-cohort-restart','result':'PASS','processes':len(participants)}
def healthy_b(value):
    need(value.get('apiA')=='api'and value.get('apiB')=='api-2'and value.get('tenantA')!=value.get('tenantB'),'HEALTHY_B_SELECTION')
    need(value.get('ownerA')!=value.get('ownerB'),'HEALTHY_B_OWNER')
    before,during,after=[value.get(k)for k in ('before','during','after')]
    need(all(isinstance(x,dict)for x in (before,during,after)),'HEALTHY_B_EVIDENCE')
    for key in ('apiCid','apiIncarnation','evaluatorRuntimeId','evaluatorGeneration','realtimeCid','realtimeIncarnation','socketId'):
        need(before.get(key)and before[key]==during.get(key)==after.get(key),'HEALTHY_B_REBOUND')
    need(value.get('stopAckBeforeOutageCommand')is True and value.get('outageReplyBeforeStart')is True,'HEALTHY_B_CAUSAL_BRACKETS')
    need(during.get('readStatus')==200 and during.get('writeStatus')in(200,201)and during.get('ownFrameAfterWrite')is True and during.get('foreignFrames')==0,'HEALTHY_B_DATA_FRAME')
    need(type(during.get('completedTimeCycles'))is int and during['completedTimeCycles']>before.get('completedTimeCycles',-1)and during.get('failedCompletions')==0,'HEALTHY_B_TIME')
    return {'criterion':'healthy-B-during-A-outage','result':'PASS','scope':'causally bracketed successful DATA/frame/TIME with unchanged independent identities'}
def cold_ack(ack,limits):
    # Candidate79d31's observed v1 schema, inherited by exact-incarnation ACK.
    # Current d003 ACKs lack it and refuse; source join must be pinned before run.
    need(ack.get('cleanShutdown')is True and ack.get('unconfirmedCleanup')is False,'COLD_ACK_UNCONFIRMED')
    cold=ack.get('cold');need(isinstance(cold,dict),'COLD_HIGH_WATER_NO_INSTRUMENT')
    observed=cold.get('observed');fields={'version','peakActive','peakQueued','accepted','started','completed','failed','duplicates','deferred','overloaded','schedulerRefused','cancelled','closeCancelled','closedRefused','invalidRefused'}
    need(isinstance(observed,dict)and set(observed)==fields and observed.get('version')==1,'COLD_HIGH_WATER_NO_INSTRUMENT')
    need(all(type(x)is int and 0<=x<=9007199254740991 for x in observed.values()),'COLD_COUNTER_CONTRACT')
    need(cold.get('activeLimit')==limits['activeLimit']and cold.get('pendingLimit')==limits['pendingLimit']and cold.get('closed')is True and all(cold.get(k)==0 for k in ('queued','delaying','running')),'COLD_DRAIN')
    need(1<=observed['peakActive']<=limits['activeLimit']and observed['peakQueued']<=limits['pendingLimit'],'COLD_BOUND')
    need(observed['accepted']>0 and observed['started']==observed['completed']+observed['failed']and observed['accepted']==sum(observed[k]for k in ('completed','failed','schedulerRefused','cancelled','closeCancelled')),'COLD_ACCOUNTING')
    need(observed['failed']==observed['schedulerRefused']==observed['cancelled']==observed['closeCancelled']==0,'COLD_FAILED_OR_CANCELLED_WORK')
    return {'criterion':'cold-high-water','result':'PASS','observed':observed,'scope':'lifetime delaying+running peak and stable post-pump queued peak, not timestamped live occupancy'}

def isolation(value):
    need(value.get('tenantA')!=value.get('tenantB')and value.get('crossAuthorizationRefused')is True,'ISOLATION_DATA')
    need(value.get('socketConnectedBeforeRefusal')is True and value.get('socketExplicitRefusal')is True and value.get('foreignFrames')==0 and value.get('positiveOwnFrame')is True,'ISOLATION_SOCKET')
    return {'criterion':'cross-tenant-isolation','result':'PASS','scope':'observed explicit DATA/socket refusal with independent authorized progression'}

def evaluation_metadata(view,ids):
    import math
    roster(ids);need(view.get('kind')=='evaluator'and isinstance(view.get('tenants'),list)and {x.get('tenant')for x in view['tenants']}==set(ids),'EVALUATION_ROSTER')
    owners=[]
    for row in view['tenants']:
        if not row.get('admitted'):continue
        evaluation=row.get('evaluation',{});age=evaluation.get('ageMs')
        need(type(age)in(int,float)and math.isfinite(age)and 0<=age<=60000 and evaluation.get('alert')is None,'EVALUATION_CONFIRMATION_AGE_OR_ALERT')
        need(type(row.get('outputRevision'))is int and row['outputRevision']>0 and type(row.get('inputCheckpoint'))is int and row['inputCheckpoint']>=0,'EVALUATION_OUTPUT_NOT_PUBLISHED')
        owners.append({'tenant':row['tenant'],'outputRevision':row['outputRevision'],'inputCheckpoint':row['inputCheckpoint'],'confirmationOrCreatedAgeMs':age,'alert':evaluation.get('alert'),'clinicalAvailability':'NO_INSTRUMENT'})
    return {'owners':owners,'scope':'current source output/confirmation metadata; age is not request latency; evaluator-specific property availability remains unmeasured'}

def clinical_http(rows,ids):
    import math
    roster(ids);need(isinstance(rows,list)and len(rows)==16 and {x.get('tenant')for x in rows}==set(ids),'CLINICAL_HTTP_ROSTER')
    for row in rows:
        need(row.get('status')==200 and all(type(row.get(k))in(int,float)and math.isfinite(row[k])for k in ('bgnowMean','bgnowMills','deltaMgdl','deltaRecent','deltaPrevious','observedAt')),'CLINICAL_HTTP_UNAVAILABLE')
        need(40<=row['bgnowMean']<=400 and row['deltaRecent']>row['deltaPrevious']and row['bgnowMills']<=row['observedAt'],'CLINICAL_HTTP_TIMING')
    return {'criterion':'actual-clinical-HTTP-properties','result':'PASS','tenants':16,'scope':'source-enabled bgnow/delta with timestamped synthetic history; not evaluator-specific property availability'}

def cached_clinical(view,ids):
    import math
    base=evaluation_metadata(view,ids);diagnostic=view.get('diagnostics',{}).get('clinicalResults')
    need(isinstance(diagnostic,dict)and diagnostic.get('authority')=='cached-result-only'and isinstance(diagnostic.get('tenants'),list)and len(diagnostic['tenants'])==16 and {x.get('tenant')for x in diagnostic['tenants']}==set(ids),'CACHED_CLINICAL_CONTRACT')
    by={x['tenant']:x for x in diagnostic['tenants']};observed=[]
    for row in view['tenants']:
        if not row['admitted']:continue
        selected=by[row['tenant']];need(selected.get('status')=='eligible-model'and selected.get('generation')==row['progress']['generation']and selected.get('outputRevision')==row['outputRevision']and selected.get('inputCheckpoint')==row['inputCheckpoint'],'CACHED_MODEL_IDENTITY')
        age=selected.get('lastCompletedAgeMs');at=selected.get('retainedModelAt');bg=selected.get('bgNow')
        need(type(age)in(int,float)and math.isfinite(age)and 0<=age<=60000 and type(at)in(int,float)and math.isfinite(at)and at>=0,'CACHED_MODEL_TIMING')
        need(isinstance(bg,dict)and bg.get('meanPresent')is True and bg.get('meanFinite')is True and type(bg.get('mills'))in(int,float)and math.isfinite(bg['mills'])and bg['mills']>=0,'CACHED_BG_NOW_UNAVAILABLE')
        observed.append({'tenant':row['tenant'],'generation':selected['generation'],'outputRevision':selected['outputRevision'],'inputCheckpoint':selected['inputCheckpoint'],'retainedModelAt':at,'lastCompletedAgeMs':age,'bgNowMills':bg['mills']})
    return {'criterion':'cached-evaluator-BG-now-observation','result':'PASS','owners':observed,'controlAuthority':'NONE','scope':'cached BG-now existence/finite metadata correlated with ordinary owner/progress/checkpoint; not universal clinical availability; retained timestamp need not advance on identical TIME output'}

def feed_delivery(before,after,heartbeat_bound):
    import math
    need(type(heartbeat_bound)is int and heartbeat_bound>0,'FEED_CONFIG_UNKNOWN');need(set(before)==set(after)and len(before)==2,'FEED_INSTANCE_ROSTER');result={}
    for service in before:
        need(isinstance(before[service].get('runtimeId'),str)and before[service]['runtimeId']==after[service].get('runtimeId')and type(before[service].get('configured',{}).get('ordinal'))is int and before[service]['configured']['ordinal']==after[service].get('configured',{}).get('ordinal'),'FEED_RUNTIME_CHANGED')
        a=before[service].get('diagnostics',{}).get('changeFeed',{});b=after[service].get('diagnostics',{}).get('changeFeed',{})
        need(a.get('status')==b.get('status')=='observed','FEED_UNOBSERVED');a=a['health'];b=b['health']
        need(all(b.get(k)is v for k,v in {'live':True,'connected':True,'degraded':False}.items())and b.get('refusal')is None and b.get('recoveryRemaining')==0,'FEED_UNHEALTHY')
        age=b.get('heartbeatAgeMs');need(type(age)in(int,float)and math.isfinite(age)and 0<=age<=heartbeat_bound,'FEED_HEARTBEAT')
        need(all(type(a.get(k))is int and type(b.get(k))is int and b[k]>=a[k]for k in ('pages','checks','hints','refused','reconnects','sweeps','rotated')),'FEED_RESET')
        need(b['hints']>a['hints']and b['checks']>a['checks']and b['refused']==a['refused'],'FEED_DOWNSTREAM_NOT_OBSERVED')
        result[service]={'hintDelta':b['hints']-a['hints'],'checkDelta':b['checks']-a['checks'],'refusalBefore':a['refused'],'refusalAfter':b['refused'],'heartbeatAgeMs':age}
    return {'criterion':'feed-downstream-delivery','result':'PASS','instances':result,'scope':'exact feed process liveness plus actual evaluator-consumer heartbeat/hint/check observations; no feed-exclusive clinical causality or zero lifetime-refusal claim'}

def raw_http_ledgers(closed,directory):
    from pathlib import Path
    need(closed.get('socketBudgetRefused')is False and type(closed.get('socketBytes'))is int and 0<=closed['socketBytes']<=268435456,'SOCKET_INPUT_BUDGET_UNCONFIRMED')
    evidence=closed.get('httpEvidence',{});need(evidence.get('complete')is True and type(evidence.get('requestsBegun'))is int and evidence['requestsBegun']==evidence.get('responsesRecorded')and 0<evidence['requestsBegun']<=8192,'RAW_HTTP_INCOMPLETE')
    need(type(evidence.get('pages'))is int and evidence['pages']==(evidence['requestsBegun']+63)//64,'RAW_HTTP_PAGE_BOUND')
    seen=set();attempts={field:{}for field in FIELDS}
    for index in range(1,evidence['pages']+1):
        file=Path(directory)/('http-receipts-%04d.json'%index)
        need(file.is_file()and not file.is_symlink()and file.stat().st_size<=65536,'RAW_HTTP_PAGE_CUSTODY')
        rows=json.loads(file.read_bytes());need(isinstance(rows,list)and len(rows)<=64,'RAW_HTTP_PAGE_BOUND')
        for row in rows:
            seq=row.get('sequence');need(type(seq)is int and 1<=seq<=evidence['requestsBegun']and seq not in seen,'RAW_HTTP_SEQUENCE');seen.add(seq)
            a=row.get('accounting')
            if a is None:continue
            need(set(a)=={'collection','attempt'}and a['collection']in FIELDS and type(a['attempt'])is int and a['attempt']>0 and row.get('method')=='POST','RAW_HTTP_ACCOUNTING')
            key=(row.get('tenant'),a['attempt']);field=a['collection'];need(key not in attempts[field],'RAW_HTTP_ATTEMPT_DUPLICATE');status=row.get('status');need(type(status)is int and(status==0 or 100<=status<=599),'RAW_HTTP_STATUS')
            attempts[field][key]='accepted'if status in(200,201)else'uncertain'if status==0 or status>=500 else'refused'
    need(len(seen)==evidence['requestsBegun'],'RAW_HTTP_INCOMPLETE')
    for field,ledger in closed['ledgers'].items():
        need(field in FIELDS and ledger.get('admissionsClosed')is True,'RAW_LEDGER_OPEN')
        for tenant in ledger['roster']:
            rows=[outcome for(key,_),outcome in attempts[field].items()if key==tenant];expected=ledger['byTenant'].get(tenant,{'attempts':0,'accepted':0,'uncertain':0,'refused':0,'pending':0})
            need(expected['attempts']==len(rows)and expected['pending']==0 and all(expected[k]==rows.count(k)for k in ('accepted','uncertain','refused')),'RAW_HTTP_LEDGER_MISMATCH')
    return {'criterion':'raw-status-to-request-accounting','result':'PASS','requests':len(seen),'classification':'200/201 accepted;0/5xx uncertain; remaining HTTP statuses refused; raw status retained'}
