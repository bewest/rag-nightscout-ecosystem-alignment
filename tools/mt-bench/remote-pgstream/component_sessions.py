"""Bounded case dispatch inside the EXISTING SUT/driver sessions and Channel."""
import json,os,subprocess,threading,time
from pathlib import Path
from protocol import Channel,write
from component_cases import plan,selected,commands,phase_payload,expect_payload,expected_clients,reduce_case,need

def _case_start(channel,c):expect_payload(channel.receive('case-start',600),c)
def _name(b,c):return'nsexternal-'+b['nonce'][:12]+'-'+c['id']+'-k6'
def _remove_k6(g,b,name,d):return g.cleanup_k6(d,b,name)

def generator_session(d,b,descriptor,g):
 cases=plan(b['componentCases'],b['tenants'])['cases'];channel=Channel(b,'generator-0')
 need(time.time()+sum(c['seconds']+600 for c in cases)+540<b['expiresAt'],'PLAN_OUTSIDE_ENVELOPE')
 root=d/'components';root.mkdir(mode=0o750);os.chown(root,0,g.GID);rows=selected(json.loads((d/'tenants.private.json').read_text()));probe=None;thread=None;stop_event=None
 try:
  for c in cases:
   _case_start(channel,c);case=root/c['id'];case.mkdir(mode=0o750);os.chown(case,0,g.GID)
   tenantfile=case/'tenants.private.json';write(tenantfile,rows);os.chown(tenantfile,0,g.GID);tenantfile.chmod(0o440)
   out=case/'load';out.mkdir(mode=0o700);os.chown(out,g.UID,g.GID);name=_name(b,c)
   need(g.subprocess.run(['docker','container','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode!=0,'K6_EXISTS')
   launch=commands(d,b,descriptor,c,name,0);write(out/'component-launch.json',{**launch,'case':c,'pair':b['pair'],'imageId':b['imageId'],'sourceSha256':b['sourceSha256']});os.chown(out/'component-launch.json',g.UID,g.GID)
   stop_event=threading.Event()
   with (case/'probe.private.log').open('wb')as log:
    probe=g.child(launch['probe'],d,g.restricted({'NODE_PATH':str(d/'dependencies/node_modules'),'STOCK_MS':'300000','RECOVERY_MS':'120000'}),log)
    thread=threading.Thread(target=g.sample,args=(probe,b,out/'generator-metrics.json',stop_event,name),daemon=True);thread.start()
    g.wait_file(out/'.window',probe,b);prime=json.loads((out/'prime.json').read_text());need(prime['primed']==expected_clients(c),'PRIME_FAILED')
    channel.send('client-primed',{**phase_payload(c),'primed':prime['primed']});expect_payload(channel.receive('load-start',120),c);(out/'.load-start').touch()
    launch=commands(d,b,descriptor,c,name,int(time.time()*1000))
    if c['kind']=='rest':
     with (case/'k6.private.log').open('wb')as output:q=g.run_k6(launch['k6'],d,b,name,output,min(c['seconds']+600,b['expiresAt']-time.time()-540))
     write(out/'k6-launch.json',{'image':b['k6Image'],'returnCode':q.returncode,'workloadSha256':descriptor['files']['workload.js'],'trafficUid':g.UID,'trustedLauncherUid':os.getuid(),'fixedArguments':True,'case':phase_payload(c)})
     (out/'.restart').touch()
    rc=probe.wait(timeout=min(180 if c['kind']=='evrt'else 1500,b['expiresAt']-time.time()-540));need(rc==0,'PROBE_FAILED')
   stop_event.set();thread.join(timeout=15);need((out/'event-loop.jsonl').is_file(),'EVENT_LOOP_MISSING')
   # Missing/non-k6 headroom remains explicit rather than a false performance green.
   channel.send('load-complete',phase_payload(c));channel.send('client-complete',phase_payload(c));_remove_k6(g,b,name,d);probe=None
  channel.receive('finish',600)
 finally:
  g.stop(probe)
  if stop_event:stop_event.set()
  if thread:thread.join(timeout=15)
  for c in cases:_remove_k6(g,b,_name(b,c),d)

def _view(d,m,c):
 # A read-only metadata view of the same exact fixture, plus fresh per-case outputs.
 root=d/'components';root.mkdir(mode=0o700,exist_ok=True);view=root/c['id'];view.mkdir(mode=0o700)
 for p in d.iterdir():
  if p.name in('components','load','owner.json'):continue
  (view/p.name).symlink_to(p.resolve(),target_is_directory=p.is_dir())
 # Immutable binding/epoch files remain linked to the ORIGINAL home, never re-authored.
 need(m.get('orchestrationHome')==str(d.resolve()),'CANONICAL_BINDING_HOME_REQUIRED')
 cm={**m,'directory':str(view),'cadence':{**m['cadence'],'loadSeconds':c['seconds']}}
 write(view/'owner.json',cm);(view/'load').mkdir();return view,cm

def app_session(d,m,b,app):
 import component_sut
 a=app.a;cases=plan(b['componentCases'],b['tenants'])['cases'];channel=Channel(b,'app-0');views=[]
 a.sample_context(d,m);app.idle(d,m);channel.send('app-ready',{'componentCases':True})
 for c in cases:
  _case_start(channel,c);prime=channel.receive('client-primed',1800);expect_payload(prime,c,{'primed':expected_clients(c)})
  view,cm=_view(d,m,c);out=view/'load';views.append((c,view,cm));marker='m7-'+m['owner'][:12]+'-'+c['id'];(out/'runid').write_text(marker)
  component_sut.snapshot(d,m,c,out/'selected-before.private.json');a.psql(d,'SELECT pg_stat_statements_reset();')
  with a.sampling(d,out):
   a.phase_snapshot(d,out,'before');channel.send('load-ready',phase_payload(c))
   try:expect_payload(channel.receive('load-complete',c['seconds']+600),c)
   finally:a.phase_snapshot(d,out,'after')
  component_sut.snapshot(d,m,c,out/'selected-after.private.json');channel.send('server-recovery-complete',{**phase_payload(c),'measurement':'NOT_RUN'})
 channel.receive('finish',600);results=[]
 # Controller transfers only allowlisted actual DRIVER results, once after every case.
 provenance=a.document(d/'components/generator-provenance.json');need(provenance.get('binding')==b,'DRIVER_PROVENANCE')
 for c,view,cm in views:
  app.load(d,b);a.verify(d,m);completion=component_sut.completed(view,cm,c);oracle=component_sut.counts(view,cm,c);out=view/'load'
  result=reduce_case(c,a.document(out/'probe.json'),completion,oracle,a.document(out/'k6-summary.json')if c['kind']=='rest'else None,cost={'before':a.document(out/'before-cgroups.json'),'after':a.document(out/'after-cgroups.json'),'sqlRoleBefore':'before-pg-role.tsv','sqlRoleAfter':'after-pg-role.tsv','scope':'SUT-local bookends; retained raw SQL rows/statements, not DB CPU or walltime/per-write execution'},progress={'before':a.document(out/'selected-before.private.json'),'after':a.document(out/'selected-after.private.json')})
  result['generatorMetrics']=a.document(out/'generator-metrics.json');result['generatorK6Scope']='NOT_RUN'if c['kind']=='evrt'else'pinned k6 plus stock probe; existing sampler completeness retained'
  a.write(view/'summary.json',result);results.append({'id':c['id'],'kind':c['kind'],'status':result['status']})
 result={'kind':'remote-component-case-batch-v1','binding':b,'pair':m['pair'],'imageId':m['imageId'],'cases':results,'verdict':'PASS'if all(x['status']=='OBSERVED_SELECTED_CHAIN'for x in results)else'PARTIAL','capacityAcceptance':'NOT_GRANTED','placement':'one SUT and one DRIVER; sequential remote windows, independent of local hardware'};a.write(d/'component-summary.json',result);channel.send('cell-complete',{'verdict':result['verdict'],'cases':results})
