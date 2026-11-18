"""Actual generated options and canonical local command; no runtime actors."""
import json,math,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import adapter,discovery,driver_shards,workload

JS=r'''
const fs=require('fs'),vm=require('vm');const [script,count,mix,scale,offered]=process.argv.slice(1);
const env={ACCEL:'1',HOT_FACTOR:'1',DURATION:'1800',SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'};
if(mix!=='-')env.M7_WORKLOAD_MIX=mix;if(scale!=='-')env.M7_WORKLOAD_SCALE=scale;if(offered!=='-')env.OFFERED_RPS=offered;
const context={__ENV:env,SharedArray:function(_,fn){return fn();},open:()=>JSON.stringify(Array.from({length:Number(count)},(_,id)=>({id}))),Counter:class{}};
const text=fs.readFileSync(script,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
console.log(JSON.stringify(vm.runInNewContext(text+'\noptions.scenarios;',context)));
'''

class WorkloadScale(unittest.TestCase):
 def test_actual_generated_all_shape_options_and_sharded_rates(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'workload.js';workload.generate(adapter.ROOT,p)
   def options(n,scale='-',mix='realistic-v1',offered='-'):
    return json.loads(subprocess.check_output(['node','-e',JS,str(p),str(n),mix,str(scale),str(offered)],text=True))
   self.assertEqual(options(1000),options(1000,1))
   for n in (1000,10000):
    for scale in (.25,.5,1,1.3,2,8):
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
   for scale,mix,offered in [('0','realistic-v1','-'),('8.1','realistic-v1','-'),('NaN','realistic-v1','-'),('Infinity','realistic-v1','-'),('2','-','-'),('2','realistic-v1','180')]:
    bad=subprocess.run(['node','-e',JS,str(p),'1000',mix,scale,offered],capture_output=True,text=True)
    self.assertNotEqual(bad.returncode,0);self.assertRegex(bad.stderr,'M7_(WORKLOAD_SCALE|REALISTIC_MIX)_CONFIGURATION')
   self.assertEqual(options(1000),options(1000,1))

 def test_canonical_cadence_and_local_eight_shard_environment(self):
  args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',workload_mix='realistic-v1',workload_scale=2,driver_shards=8)
  cadence=adapter.cadence_options(args);self.assertEqual(cadence['workloadScale'],2)
  for value in (True,0,.24,8.01,float('nan'),float('inf')):
   args.workload_scale=value
   with self.assertRaisesRegex(RuntimeError,'M7_WORKLOAD_SCALE_CONFIGURATION'):adapter.cadence_options(args)
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
