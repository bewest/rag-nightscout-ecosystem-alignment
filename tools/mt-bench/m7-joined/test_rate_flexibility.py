"""Actual generated options accept positive representable rates across shards."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter
import driver_shards
import driver_vu_diagnostic as driver
import workload

PORT=r"""
const fs=require('node:fs'),vm=require('node:vm');
const [file,count,offered,hot]=process.argv.slice(1);
const c={__ENV:{ACCEL:'1',HOT_FACTOR:hot,DURATION:'600',OFFERED_RPS:offered,
 SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'},
 SharedArray:function(n,f){return f();},open:()=>JSON.stringify(Array.from({length:Number(count)},(_,id)=>({id}))),Counter:class{}};
const source=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
console.log(JSON.stringify(vm.runInNewContext(source+'\noptions.scenarios;',c)));
"""


class RateFlexibility(unittest.TestCase):
    def test_generated_rates_and_shards_with_representability_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'workload.js';workload.generate(adapter.ROOT,path);source=path.read_text()
            def options(count,rate,hot=1):
                result=subprocess.run(['node','-e',PORT,str(path),str(count),str(rate),str(hot)],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                return json.loads(result.stdout)
            def criterion():
                for rate in (.25,12000):
                    rows=options(1000,rate)
                    self.assertEqual({r['timeUnit'] for r in rows.values()}, {str(int(11000000/rate+.5))+'ms'})
                aggregate=0
                for shard in driver_shards.plan(1000,4,.25,8):
                    rows=options(shard['tenants'],shard['offeredRps'],shard['hotFactor'])
                    aggregate+=sum(r['rate']*1000/int(r['timeUnit'][:-2]) for r in rows.values())
                self.assertAlmostEqual(aggregate,.25)
            criterion()
            path.write_text(source.replace('offered <= 0','offered < 1 || offered > 10000'))
            with self.assertRaises(AssertionError):criterion()
            path.write_text(source);criterion()
            for rate,code in [('0','RPS_RANGE'),('-1','RPS_RANGE'),('NaN','RPS_RANGE'),('Infinity','RPS_RANGE'),('1e-9','RPS_TIME_UNIT'),('1e20','RPS_TIME_UNIT')]:
                result=subprocess.run(['node','-e',PORT,str(path),'1000',rate,'1'],capture_output=True,text=True,timeout=5)
                self.assertNotEqual(result.returncode,0);self.assertIn(code,result.stderr)

    def test_configured_plan_uses_same_fractional_schedule_and_duration_boundary(self):
        plan={'version':1,'observer':'summary-v1','maxAggregateVUs':56,
              'scenarios':{name:{'preAllocatedVUs':1,'maxVUs':1} for name in driver.SHAPES}}
        m={'tenants':1000,'cadence':{'loadSeconds':600,'hotFactor':1,'driverShards':8,'offeredRps':.25,'driverPlan':plan}}
        rows=driver.expected_plans(m)
        self.assertAlmostEqual(sum(s['perSecond'] for r in rows for s in r['scenarios'].values()),.25)
        self.assertTrue(all(r['scenarios']['w_sgv']['plannedIterations']>=1 for r in rows))
        m['cadence']['offeredRps']=1e-9
        with self.assertRaisesRegex(RuntimeError,'M7_DRIVER_PLAN_RATE'):driver.expected_plans(m)


if __name__=='__main__':unittest.main()
