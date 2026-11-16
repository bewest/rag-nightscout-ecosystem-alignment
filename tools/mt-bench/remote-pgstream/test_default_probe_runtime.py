"""Execute actual generated public probe with in-memory HTTP/socket/files only."""
import copy,json,os,subprocess,tempfile,unittest
from pathlib import Path
import traffic_probe,protocol
FIXTURE="const vm=require('node:vm'),fs=require('node:fs');\nconst source=fs.readFileSync(process.argv[2],'utf8');let clock=1000000,posts=0;const sockets=[],files=new Map();\nconst roster=[{id:'00000000-0000-0000-0000-000000000001',host:'tenant.synthetic',token:'synthetic'}];\nconst cfg=JSON.stringify({version:1,sampleCount:64,cadenceMs:100,timeoutMs:30000,drainMs:10000,maxSamples:10000,seed:0,hot:[],cold:[]});\nconst argv=['node','probe.js','--base','http://synthetic:18080','--tenants','/roster','--runid','synthetic','--per','2','--open','5','--window','1','--probeEvery','100','--restart','0','--out','/out/probe.json','--signal','/out/.window'];\nconst mode=process.argv[3]||'off';\nif(mode==='on')argv.push('--rotatingCapture',cfg);\nconst io=()=>{const handlers={};const socket={on:(name,fn)=>{handlers[name]=fn;return socket;},emit:()=>queueMicrotask(()=>handlers.dataUpdate({sgvs:[]})),close:()=>{},connect:()=>{}};sockets.push(handlers);queueMicrotask(()=>handlers.connect());return socket;};\nconst http={Agent:class{},request:(options,callback)=>{\n  const handlers={};const req={on:(n,fn)=>{handlers[n]=fn;return req;},destroy:()=>{},end:body=>queueMicrotask(()=>{\n    let result;\n    if(options.method==='POST'){\n      posts++;const doc={...JSON.parse(body)[0],_id:posts.toString(16).padStart(24,'0')};\n      result=options.path.includes('results=items')?{items:[{index:0,outcome:'inserted',_id:doc._id}],documents:[doc]}:[doc];\n      if(!['no-frame','write-fail'].includes(mode))queueMicrotask(()=>{for(const socket of sockets)socket.dataUpdate({sgvs:[{_id:doc._id,mills:doc.date,mgdl:doc.sgv}]});});\n    }else result={token:'synthetic-jwt'};\n    const events={};const response={statusCode:options.method==='POST'&&mode==='write-fail'?503:200,on:(n,fn)=>{events[n]=fn;return response;}};\n    callback(response);events.data(JSON.stringify(result));events.end();\n  })};return req;\n}};\nconst mockfs={readFileSync:()=>JSON.stringify(roster),existsSync:name=>name==='/out/.load-start'||name==='/out/.restart'&&posts>=4,\n  appendFileSync:()=>{},writeFileSync:(name,value)=>{files.set(name,value);if(name==='/out/probe.json'&&files.has('/out/fanout.json'))console.log(JSON.stringify({probe:JSON.parse(value),fanout:JSON.parse(files.get('/out/fanout.json')),accounting:files.has('/out/probe-accounting.json')?JSON.parse(files.get('/out/probe-accounting.json')):null}));}};\nclass ClockDate extends Date{static now(){return clock;}}\nconst context={require:name=>({'node:fs':mockfs,'node:path':require('node:path'),'node:http':http,'socket.io-client':{io},'./recovery.cjs':{recoveredAfterRestart:()=>false},'./probe-accounting.cjs':require(process.argv[4])}[name]||(()=>{throw Error('unexpected module '+name);})()),\n  process:{argv,env:{},exit:code=>{if(code)throw Error('probe exit '+code);}},console:{log:()=>{},error:console.error},Date:ClockDate,performance:{now:()=>clock},Buffer,URL,Promise,Map,Set,JSON,\n  setTimeout:(fn,ms)=>{clock+=ms;queueMicrotask(fn);},setInterval:()=>({unref:()=>{}})};\nvm.runInNewContext(source,context);\n"
ROOT=Path(__file__).resolve().parents[3]
class DefaultProbeRuntime(unittest.TestCase):
 def run_case(self,mode,discovery=False,tenants=1,clients=None,ablate=False):
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);target=d/'probe.js';traffic_probe.generate(ROOT,target);
   if ablate:target.write_text(target.read_text().replace('k < viewers[i];','k < PER;'))
   fixture=d/'fixture.cjs';source=FIXTURE.replace('env:{},',"env:{M7_RUN_PURPOSE:'discovery'},")if discovery else FIXTURE;source=source.replace("const roster=[{id:'00000000-0000-0000-0000-000000000001',host:'tenant.synthetic',token:'synthetic'}];","const roster=Array.from({length:"+str(tenants)+"},(_,i)=>({id:'00000000-0000-0000-0000-'+String(i+1).padStart(12,'0'),host:'tenant'+i+'.synthetic',token:'synthetic'}));")
   source=source.replace('const io=()=>','const io=(url)=>').replace('sockets.push(handlers);',"handlers.host=new URL(url).hostname;sockets.push(handlers);").replace('for(const socket of sockets)socket.dataUpdate',"for(const socket of sockets)if(socket.host===options.headers.host)socket.dataUpdate")
   if clients is not None:source=source.replace("const mode=process.argv[3]||'off';","argv.push('--clients','"+str(clients)+"');const mode=process.argv[3]||'off';")
   fixture.write_text(source)
   return subprocess.run([os.environ.get('NODE_BINARY','node'),str(fixture),str(target),mode,str(ROOT/'tools/mt-bench/m7-joined/probe-accounting.cjs')],capture_output=True,text=True,timeout=10)
 def metrics(self):return {**{k:{'values':{'count':0}}for k in ['writes_refused','responses_refused','dropped_iterations']},'http_req_failed':{'values':{'rate':0}}}
 def test_actual_default_generated_ordinary_path_and_required_public_witnesses(self):
  x=self.run_case('off');self.assertEqual(x.returncode,0,x.stderr);v=json.loads(x.stdout);p=v['probe'];self.assertEqual(p['prime']['primed'],2);self.assertEqual(p['window']['writes'],{'ok':4,'failed':0});self.assertEqual(p['window']['deliveredFrames'],8);self.assertEqual(p['window']['expectedFrames'],8);self.assertEqual(sum(v['fanout']['probeWrites']['byTenant'].values()),4);self.assertTrue(protocol.traffic_verdict(p,self.metrics(),1))
 def test_missing_frames_and_failed_http_still_refuse_actual_traffic_gate(self):
  for mode in ('no-frame','write-fail'):
   with self.subTest(mode=mode):
    x=self.run_case(mode);self.assertEqual(x.returncode,0,x.stderr);p=json.loads(x.stdout)['probe'];self.assertEqual(p['window']['deliveredFrames'],0)
    with self.assertRaisesRegex(RuntimeError,'FRAMES_OR_WRITES_FAILED'):protocol.traffic_verdict(p,self.metrics(),1)
 def test_discovery_actual_accounting_retains_refusals_and_strict_gate_stays_red(self):
  for mode,field in [('off','accepted'),('write-fail','uncertain')]:
   with self.subTest(mode=mode):
    x=self.run_case(mode,True);self.assertEqual(x.returncode,0,x.stderr);v=json.loads(x.stdout.splitlines()[-1]);ledger=v['accounting'];self.assertTrue(ledger['admissionsClosed']);self.assertEqual(ledger['attempts'],4);row=ledger['byTenant'][ledger['roster'][0]];self.assertEqual(row[field],4);self.assertEqual(row['pending'],0)
    if mode=='write-fail':
     with self.assertRaisesRegex(RuntimeError,'FRAMES_OR_WRITES_FAILED'):protocol.traffic_verdict(v['probe'],self.metrics(),1)
 def test_sparse_dense_and_zero_totals_execute_actual_probe_and_independent_reducer(self):
  from viewer_plan import check
  for tenants,clients in [(5,2),(5,7),(5,0),(3,17),(10000,1)]:
   with self.subTest(tenants=tenants,clients=clients):
    x=self.run_case('off',True,tenants,clients);self.assertEqual(x.returncode,0,x.stderr)
    v=json.loads(x.stdout.splitlines()[-1]);probe=v['probe'];roster=[{'id':'00000000-0000-0000-0000-'+str(i+1).zfill(12)} for i in range(tenants)]
    m={'tenants':tenants,'cadence':{'logicalPollingClients':clients}}
    result=check(m,roster,probe,v['fanout']['probeWrites']['byTenant'])
    self.assertEqual(probe['prime']['sockets'],clients)
    self.assertEqual(probe['window']['connectedAtEnd'],clients)
    self.assertEqual(len(probe['viewerBindings']),clients)
    expected=sum(count*(clients//tenants+(next(i for i,r in enumerate(roster) if r['id']==tenant)<clients%tenants)) for tenant,count in v['fanout']['probeWrites']['byTenant'].items())
    self.assertEqual(probe['window']['deliveredFrames'],expected)
    self.assertEqual(result['verdict'],'PASS' if expected else 'NOT_EXERCISED')
 def test_binding_and_frame_breaks_cannot_self_report_a_pass(self):
  from viewer_plan import check
  v=json.loads(self.run_case('off',True,5,7).stdout.splitlines()[-1]);roster=[{'id':'00000000-0000-0000-0000-'+str(i+1).zfill(12)} for i in range(5)]
  m={'tenants':5,'cadence':{'logicalPollingClients':7}};by=v['fanout']['probeWrites']['byTenant']
  mutations=[lambda p:p['viewerBindings'].pop(),lambda p:p['viewerBindings'].append(p['viewerBindings'][0]),lambda p:p['viewerBindings'][0].update(tenant='foreign'),lambda p:p['viewerBindings'][0].update(tenant=roster[-1]['id']),lambda p:p['viewerBindings'][1].update(socket=0),lambda p:p['window'].update(expectedFrames=1,deliveredFrames=1),lambda p:p['prime'].update(primed=6),lambda p:p['window'].update(connectedAtEnd=6)]
  for mutate in mutations:
   p=copy.deepcopy(v['probe']);mutate(p)
   with self.assertRaisesRegex(RuntimeError,'M7_VIEWER_'):check(m,roster,p,by)
  check(m,roster,v['probe'],by)
 def test_actual_emitter_per_tenant_ablation_is_red_and_restored_plan_is_green(self):
  from viewer_plan import check
  roster=[{'id':'00000000-0000-0000-0000-'+str(i+1).zfill(12)} for i in range(5)]
  m={'tenants':5,'cadence':{'logicalPollingClients':7}}
  broken=self.run_case('off',True,5,7,True);self.assertEqual(broken.returncode,0,broken.stderr);v=json.loads(broken.stdout.splitlines()[-1])
  self.assertEqual(v['probe']['prime']['sockets'],10)
  with self.assertRaisesRegex(RuntimeError,'M7_VIEWER_BINDINGS'):check(m,roster,v['probe'],v['fanout']['probeWrites']['byTenant'])
  restored=self.run_case('off',True,5,7);self.assertEqual(restored.returncode,0,restored.stderr);v=json.loads(restored.stdout.splitlines()[-1]);check(m,roster,v['probe'],v['fanout']['probeWrites']['byTenant'])
if __name__=='__main__':unittest.main()
