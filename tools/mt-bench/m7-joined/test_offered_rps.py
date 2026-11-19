import math
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import adapter
import discovery
from workload import generate
JS=r'''const fs=require('node:fs'),vm=require('node:vm');
const [file,n,rate,status]=process.argv.slice(1),calls=[],counts={};
const tenants=Array.from({length:Number(n)},(_,i)=>({id:'synthetic-'+i,host:'t'+i+'.example.test',token:'synthetic-token'}));
const env={BASE_URL:'http://example.test',RUN_ID:'synthetic-rate',DURATION:'310',ACCEL:'1',HOT_FACTOR:'1',TENANTS_FILE:'unused',RUN_START:'1800000000000',SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'};
if(rate!=='default')env.OFFERED_RPS=rate;
const c={counts,calls,__ENV:env,SharedArray:function(name,factory){return factory();},open:()=>JSON.stringify(tenants),exec:{scenario:{iterationInTest:Number(n)}},sha256:()=>'',Counter:class{constructor(name){this.name=name}add(x){counts[this.name]=(counts[this.name]||0)+x}},http:{expectedStatuses:()=>null,get:()=>({status:Number(status)}),post:(url,body)=>{calls.push(JSON.parse(body));return{status:Number(status)}}}};
vm.createContext(c);let code=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
code+='\nw_sgv();r_sgv();JSON.stringify({options,counts,calls});';console.log(vm.runInContext(code,c,{timeout:2000}));'''
class OfferedRate(unittest.TestCase):
 def observe(self,n,rate='default',status=200):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'workload.js';generate(adapter.ROOT,p)
   return json.loads(subprocess.check_output(['node','-e',JS,str(p),str(n),str(rate),str(status)],text=True))
 def test_nominal_and_explicit_rates_keep_mix_and_clock(self):
  for target in ('default',120,180,240):
   r=self.observe(3000,target);scenarios=r['options']['scenarios'];total=sum(v['rate']/float(v['timeUnit'][:-2])*1000 for v in scenarios.values())
   self.assertAlmostEqual(total,110 if target=='default' else target,delta=.001)
   self.assertEqual(scenarios['r_sgv']['rate'],5*scenarios['w_sgv']['rate'])
   self.assertEqual(len(scenarios),7)
   for v in scenarios.values():  # driver-sized-from-offer, default H=1.5
    per=v['rate']*1000/float(v['timeUnit'][:-2])
    self.assertEqual((v['preAllocatedVUs'],v['maxVUs']),(max(2,math.ceil(per*.25*1.5)),max(4,math.ceil(per*5*1.5))))
   period=float(scenarios['w_sgv']['timeUnit'][:-2]);self.assertEqual(r['calls'][0][0]['date'],1800000000000+period)
   self.assertEqual(r['counts']['scenario_request_attempts'],2);self.assertEqual(r['counts']['scenario_http_responses'],2)
 def test_transport_failure_is_attempt_without_http_response(self):
  r=self.observe(3000,120,0)
  self.assertEqual(r['counts']['scenario_request_attempts'],2);self.assertEqual(r['counts']['scenario_transport_failures'],2)
  self.assertNotIn('scenario_http_responses',r['counts']);self.assertEqual(r['counts']['writes_uncertain'],1)
 def test_discovery_only_binding_and_forwarding(self):
  args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',offered_rps=180,tenants=3000)
  cadence=adapter.cadence_options(args);self.assertEqual(cadence['offeredRps'],180)
  m={'cadence':{**cadence,'hotFactor':1},'tenants':3000,'project':'synthetic','owner':'a'*32,'port':1234,'settingsFingerprint':{'sha256':'b'*64}}
  self.assertIn('OFFERED_RPS=180',discovery.k6_command(adapter,Path('/synthetic'),m,'image','run'))
  self.assertAlmostEqual(adapter.rate_offer(m)['effectiveScenarioRps'],180,delta=.001)
  for value in (0,float('inf'),float('nan'),True):
   args.offered_rps=value
   with self.assertRaisesRegex(RuntimeError,'RPS_RANGE'):adapter.cadence_options(args)
  args.offered_rps=12000;self.assertEqual(adapter.cadence_options(args)['offeredRps'],12000)
  args.offered_rps=180;args.run_purpose='acceptance'
  with self.assertRaisesRegex(RuntimeError,'DISCOVERY_ONLY'):adapter.cadence_options(args)
if __name__=='__main__':unittest.main()
