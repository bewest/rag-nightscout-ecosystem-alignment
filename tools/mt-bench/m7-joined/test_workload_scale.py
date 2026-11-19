"""Actual generated options and canonical local command; no runtime actors."""
import json,math,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import adapter,discovery,driver_shards,workload

JS=r'''
const fs=require('fs'),vm=require('vm');const [script,count,mix,scale,offered,plan]=process.argv.slice(1);
const env={ACCEL:'1',HOT_FACTOR:'1',DURATION:'1800',SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'};
if(mix!=='-')env.M7_WORKLOAD_MIX=mix;if(scale!=='-')env.M7_WORKLOAD_SCALE=scale;if(offered!=='-')env.OFFERED_RPS=offered;
if (plan) Object.assign(env,{M7_DRIVER_VU_DIAGNOSTIC:'configured-v1',M7_DRIVER_PLAN:plan,RUN_START:'0'});
const context={__ENV:env,exec:{scenario:{iterationInTest:Number(count)}},console:{log(){}}, SharedArray:function(_,fn){return fn();},open:()=>JSON.stringify(Array.from({length:Number(count)},(_,id)=>({id}))),Counter:class{}};
const text=fs.readFileSync(script,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
const result = plan ? `({scenarios:options.scenarios, stamps:Object.fromEntries(
  Object.keys(options.scenarios).map(name=>{exec.scenario.name=name; return [name,stamp()];}))})` : 'options.scenarios';
console.log(JSON.stringify(vm.runInNewContext(text+'\n'+result,context)));
'''

class WorkloadScale(unittest.TestCase):
 def test_actual_generated_all_shape_options_and_sharded_rates(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'workload.js';workload.generate(adapter.ROOT,p)
   def options(n,scale='-',mix='realistic-v1',offered='-'):
    return json.loads(subprocess.check_output(['node','-e',JS,str(p),str(n),mix,str(scale),str(offered)],text=True))
   self.assertEqual(options(1000),options(1000,1))
   for n in (1000,10000):
    for scale in (.1,.25,.5,1,1.3,2,8,16):
     rates={shape:0 for shape in workload.REALISTIC_CADENCE_MS}
     for part in driver_shards.plan(n,1,None,8):
      for shape,row in options(part['tenants'],scale).items():
       weight=5 if shape=='r_sgv' else 1
       expected=math.floor(workload.REALISTIC_CADENCE_MS[shape]*weight/scale+.5)
       self.assertEqual(row['timeUnit'],str(expected)+'ms')
       rates[shape]+=row['rate']*1000/expected
     offer=adapter.rate_offer({'tenants':n,'cadence':{'workloadMix':'realistic-v1','workloadScale':scale}})
     self.assertEqual(offer['sensorCadence'],scale==1)
     self.assertEqual(offer['workloadInterpretation'],'sensor-cadence' if scale==1 else 'uniform-rate-bracket')
     for shape,value in rates.items():self.assertAlmostEqual(value,offer['scenarioRpsByShape'][shape])
   for scale,mix,offered in [('0','realistic-v1','-'),('-1','realistic-v1','-'),('NaN','realistic-v1','-'),('Infinity','realistic-v1','-'),('2','-','-'),('2','realistic-v1','180'),('1e20','realistic-v1','-'),('1e-20','realistic-v1','-')]:
    bad=subprocess.run(['node','-e',JS,str(p),'1000',mix,scale,offered],capture_output=True,text=True)
    self.assertNotEqual(bad.returncode,0);self.assertRegex(bad.stderr,'M7_((WORKLOAD_SCALE|REALISTIC_MIX)_CONFIGURATION|OFFERED_RPS_TIME_UNIT)')
   original=p.read_text()
   p.write_text(original.replace('workloadScale <= 0','workloadScale < 0.25 || workloadScale > 8'))
   old=subprocess.run(['node','-e',JS,str(p),'1000','realistic-v1','.1','-'],capture_output=True,text=True)
   self.assertNotEqual(old.returncode,0);self.assertIn('M7_WORKLOAD_SCALE_CONFIGURATION',old.stderr)
   p.write_text(original);self.assertEqual(options(1000,.1)['w_sgv']['timeUnit'],'3000000ms')
   self.assertEqual(options(1000),options(1000,1))

 def test_configured_write_scale_matches_actual_k6_options_and_payload_clock(self):
  import sys
  sys.path.append(str(adapter.HERE.parent/'kubernetes'))
  import workload_runtime as kube
  import driver_vu_diagnostic as driver

  shapes=workload.REALISTIC_CADENCE_MS
  plan={'version':1, 'observer':'summary-v1','maxAggregateVUs':28,
        'scenarios':{shape:{'preAllocatedVUs':2,'maxVUs':4} for shape in shapes}}
  w={'loadSeconds':120,'workloadMix':'realistic-v1','workloadScale':1,
     'logicalPollingClients':16,'probeEveryMs':30000}
  with tempfile.TemporaryDirectory() as tmp:
   script=Path(tmp)/'workload.js'
   workload.generate(adapter.ROOT,script)
   for n in (1000,3000):
    for uniform,write in ((1,1),(1,2),(2,.5),(.5,3)):
     cadence=w | {'workloadScale':uniform,'driverPlan':plan | {'writeRateScale':write}}
     kube.validate(cadence,adapter.require,tenants=n)
     manifest={'tenants':n,'cadence':cadence}
     environment=driver.configured_environment(manifest)
     received=json.loads(subprocess.check_output(['node','-e',JS,str(script),str(n),'realistic-v1',
                   str(uniform),'-',environment['M7_DRIVER_PLAN']],text=True))
     cycles,rates=kube.rates(cadence,n)
     offer=adapter.rate_offer(manifest)
     self.assertEqual(offer['sensorCadence'],uniform==1 and write==1)
     self.assertEqual(rates,offer['scenarioRpsByShape'])
     projected,=driver.expected_plans(manifest)
     for shape,interval in shapes.items():
      factor=write if shape.startswith('w_') else 1
      weight=driver.WEIGHTS[shape]
      expected=math.floor(interval*weight/uniform/factor+.5)
      self.assertEqual(cycles[shape],expected)
      self.assertEqual(received['stamps'][shape],expected)
      self.assertEqual(received['scenarios'][shape]['timeUnit'],str(expected)+'ms')
      self.assertEqual(projected['scenarios'][shape]['timeUnit'],str(expected)+'ms')
   for bad in [0,-1,False,'2',float('inf'),1e-20,1e20]:
    with self.assertRaises(RuntimeError):
     kube.validate(w | {'driverPlan':plan | {'writeRateScale':bad}},adapter.require,tenants=1000)
   with self.assertRaises(RuntimeError):
    kube.validate({'loadSeconds':120,'offeredRps':10,'logicalPollingClients':16,'probeEveryMs':30000,
                   'driverPlan':plan | {'writeRateScale':2}},adapter.require,tenants=1000)

 def test_local_and_kubernetes_share_multiplier_units_and_refuse_true_bounds(self):
  import sys
  sys.path.append(str(adapter.HERE.parent/'kubernetes'))
  import workload_runtime as kube
  for scale in (.1,1,16):
   w={'loadSeconds':1800,'workloadMix':'realistic-v1','workloadScale':scale,
      'logicalPollingClients':100,'probeEveryMs':5000,'setupSeconds':1800,'drainSeconds':600}
   kube.validate(w,adapter.require,tenants=1000)
   cycles,rates=kube.rates(w,1000)
   local=adapter.rate_offer({'tenants':1000,'cadence':w})
   self.assertEqual(cycles,local['scenarioTimeUnitMs'])
   self.assertAlmostEqual(sum(rates.values()),local['effectiveScenarioRps'])
  for scale in (0,True,float('nan'),float('inf'),1e-20,1e20):
   w['workloadScale']=scale
   with self.assertRaisesRegex(RuntimeError,'WORKLOAD_SCALE_(CONFIGURATION|TIME_UNIT)'):
    kube.validate(w,adapter.require,tenants=1000)

 def test_canonical_cadence_and_local_eight_shard_environment(self):
  # Partition validation uses the actual 1000-tenant roster constructed below.
  args=SimpleNamespace(tenants=1000,profile='pgstream-sample',run_purpose='discovery',workload_mix='realistic-v1',workload_scale=2,driver_shards=8)
  cadence=adapter.cadence_options(args);self.assertEqual(cadence['workloadScale'],2)
  for value in (True,0,-1,float('nan'),float('inf')):
   args.workload_scale=value
   with self.assertRaisesRegex(RuntimeError,'M7_WORKLOAD_SCALE_CONFIGURATION'):adapter.cadence_options(args)
  for value in (.1,.24,8.01,16):
   args.workload_scale=value
   self.assertEqual(adapter.cadence_options(args)['workloadScale'],value)
  for value in (1e-20,1e20):
   args.workload_scale=value
   with self.assertRaisesRegex(RuntimeError,'M7_WORKLOAD_SCALE_TIME_UNIT'):adapter.cadence_options(args)
  args.workload_scale=2;args.workload_mix=None
  with self.assertRaisesRegex(RuntimeError,'M7_WORKLOAD_SCALE_CONFIGURATION'):adapter.cadence_options(args)
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);(d/'load').mkdir();(d/'tenants.private.json').write_text(json.dumps([{'id':i} for i in range(1000)]))
   m={'cadence':cadence,'project':'synthetic-scale','owner':'a'*32,'port':1,'settingsFingerprint':{'sha256':'e'*64}}
   cmd=discovery.k6_command(adapter,d,m,'sha256:'+'f'*64,'synthetic')
   self.assertIn('M7_WORKLOAD_SCALE=2',cmd);self.assertIn('M7_WORKLOAD_MIX=realistic-v1',cmd)
   self.assertEqual(cmd[-1].count('k6 run --quiet'),8)
   self.assertFalse(any(str(v).startswith('OFFERED_RPS=')for v in cmd))

if __name__=='__main__':unittest.main()
