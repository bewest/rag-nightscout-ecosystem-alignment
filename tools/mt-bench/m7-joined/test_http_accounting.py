"""Fault-inject actual generated functions, not a second HTTP implementation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter
from workload import generate
from http_accounting import assess

JS=r'''const fs=require('node:fs'),vm=require('node:vm');
const [file,mode]=process.argv.slice(1),samples=[],counters=[],wire=[],privateValue='DO_NOT_RETAIN_TOKEN_URL_BODY';
let answer={status:200,body:'{"token":"synthetic-jwt"}'};
const c={__VU:0,__ENV:{BASE_URL:'http://synthetic.invalid',TENANTS_FILE:'unused',RUN_ID:'synthetic-http',RUN_START:'1800000000000',DURATION:'1',ACCEL:'1',HOT_FACTOR:'1',JWT_SETUP_CONCURRENCY:'2',SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'},
 console:{log(){},error(){}},sha256:()=>'',SharedArray:function(n,f){return f()},open:()=>JSON.stringify([{id:'synthetic-a',host:'a.example.test',token:privateValue},{id:'synthetic-b',host:'b.example.test',token:privateValue}]),exec:{scenario:{iterationInTest:1}},Counter:class{constructor(name){this.name=name;counters.push(name)}add(value,tags={}){samples.push({name:this.name,value,tags})}},
 http:{expectedStatuses:()=>null,get(){wire.push(answer.status);return answer},post(){wire.push(answer.status);return answer},batch(requests){return requests.map((r,i)=>{const a={status:i===0?503:200,body:'{"token":"synthetic-jwt"}'};wire.push(a.status);return a})}}};
vm.createContext(c);let source=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
if(mode==='missing-status')source=source.replace('status:String(value.status)','status:"200"');
if(mode==='missing-category')source=source.replace('category:value.category','category:"http_expected"');
if(mode==='per-vu')source=source.replace("typeof __VU === 'undefined' || __VU === 0",'true');
if(mode==='vu'||mode==='per-vu')c.__VU=1;
const started=performance.now();vm.runInContext(source,c);const elapsedMs=performance.now()-started;
if(mode==='batch'){try{vm.runInContext('setup()',c)}catch{}}
else for(const [status,error_code]of [[200,0],[201,0],[204,0],[301,0],[400,0],[401,0],[403,0],[404,0],[409,0],[429,0],[500,0],[502,0],[503,0],[504,0],[599,0],[0,1050],[0,1210]]){
 answer={status,error_code,body:privateValue,error:privateValue,url:privateValue};
 vm.runInContext('w_sgv();w_devicestatus();w_treatments_v3({jwts:["synthetic","synthetic"]});r_sgv();r_devicestatus();r_treatments();r_status();',c);
}
const thresholds=vm.runInContext('options.thresholds',c),metrics={};
for(const sample of samples){metrics[sample.name]||={count:0};metrics[sample.name].count+=sample.value}
for(const key of Object.keys(thresholds)){
 const match=/^([^{}]+)\{(.+)\}$/.exec(key);if(!match)continue;
 const tags=Object.fromEntries(match[2].split(',').map(x=>x.split(':')));
 metrics[key]={count:samples.filter(s=>s.name===match[1]&&Object.entries(tags).every(([k,v])=>s.tags[k]===v)).reduce((n,s)=>n+s.value,0)};
}
metrics.http_reqs={count:wire.length};metrics.dropped_iterations={count:mode==='dropped'?7:0};
process.stdout.write(JSON.stringify({metrics,thresholds:Object.keys(thresholds).filter(x=>x.startsWith('m7_http_')).length,metadataBytes:Buffer.byteLength(JSON.stringify(thresholds)),elapsedMs,counterObjects:counters.length,wireCalls:wire.length}));'''

class HttpAccounting(unittest.TestCase):
    def observe(self,mode='normal'):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'workload.js';generate(adapter.ROOT,file)
            return json.loads(subprocess.check_output(['node','-e',JS,str(file),mode],text=True,timeout=10))

    def test_exact_histogram_reconciles_observed_status_and_transport(self):
        observed=self.observe();value=assess(observed['metrics'])
        self.assertEqual(value['sourceReconciliation'],'PASS')
        self.assertEqual(value['scenario'],{'attempts':119,'completed':119})
        self.assertEqual(observed['wireCalls'],119)
        for shape,row in value['shapes'].items():
            if shape=='jwt_setup':continue
            self.assertEqual(row['statusCodes'],{'200':1,'201':1,'204':1,'301':1,'400':1,'401':1,'403':1,'404':1,'409':1,'429':1,'500':1,'502':1,'503':1,'504':1,'599':1,'0':2})
            self.assertEqual((row['responses'],row['noResponse'],row['pending']),(15,2,0))
            self.assertEqual(row['categories']['timeout'],1)
            self.assertEqual(row['categories']['transport'],1)
            self.assertTrue(row['reconciled']);self.assertEqual(row['httpVerdict'],'FAIL')
        self.assertEqual(value['shapes']['w_sgv']['writeOutcomes'],{'accepted':1,'refused':6,'uncertain':10})
        self.assertEqual(value['shapes']['w_treatments_v3']['writeOutcomes'],{'accepted':2,'refused':6,'uncertain':9})
        self.assertEqual(value['storage'],'UNMEASURED')
        self.assertNotIn('DO_NOT_RETAIN',json.dumps(observed))

    def test_iterations_and_drops_are_figures_without_an_offered_work_verdict(self):
        metrics = self.observe()['metrics']
        metrics['iterations'] = {'count':119}
        result = assess(metrics)
        self.assertNotIn('offeredWorkVerdict', result)
        self.assertEqual(result['sourceCounts']['iterations'], 119)
        del metrics['scenario_transport_failures']
        result = assess(metrics)
        self.assertEqual(result['sourceReconciliation'], 'UNMEASURED')
        self.assertEqual(result['sourceCounts']['scenario_transport_failures'], 'UNMEASURED')

    def test_missing_or_tampered_data_cannot_pass(self):
        self.assertEqual(assess({})['httpVerdict'],'UNMEASURED')
        for mode in ('missing-status','missing-category'):
            broken=assess(self.observe(mode)['metrics'])
            self.assertEqual(broken['httpVerdict'],'FAIL')
            self.assertFalse(broken['shapes']['w_sgv']['reconciled'])
        normal=self.observe()['metrics']
        normal['m7_http_attempts{http_shape:w_sgv}']['count']+=1
        value=assess(normal)
        self.assertEqual(value['shapes']['w_sgv']['pending'],1)
        self.assertEqual(value['sourceReconciliation'],'FAIL')
        normal['m7_http_attempts{http_shape:w_sgv}']['count']=float('nan')
        with self.assertRaisesRegex(ValueError,'M7_HTTP_COUNT_INVALID'):assess(normal)

    def test_histogram_metadata_has_no_per_vu_or_tenant_product(self):
        normal=self.observe();vu=self.observe('vu');broken=self.observe('per-vu')
        self.assertEqual(normal['thresholds'],3565)
        self.assertEqual(vu['thresholds'],0)
        self.assertEqual(normal['counterObjects'],vu['counterObjects'])
        self.assertLess(normal['counterObjects'],20)
        self.assertEqual(broken['thresholds'],normal['thresholds'])
        self.assertGreater(broken['metadataBytes'],vu['metadataBytes'])
        self.assertLess(normal['metadataBytes'],400000)

if __name__=='__main__':unittest.main()
