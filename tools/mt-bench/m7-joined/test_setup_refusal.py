"""Actual generated k6 setup, with HTTP/log seams under Node's vm."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter
from workload import generate
JS=r'''const fs=require('node:fs'),vm=require('node:vm');
const [file,kind,concurrency]=process.argv.slice(1),logs=[],requests=[];
const privateValue='DO_NOT_RETAIN_CREDENTIAL_OR_BODY';
const tenantRows=Array.from({length:3},(_,i)=>({id:'synthetic-'+i,host:'t'+i+'.example.test',token:privateValue+i}));
const env={JWT_SETUP_CONCURRENCY:concurrency,BASE_URL:'http://example.test',TENANTS_FILE:'unused',SHAPES:'w_treatments_v3',DURATION:'310',ACCEL:'1',HOT_FACTOR:'1'};
let now=1000;
const c={logs,requests,__ENV:env,open:()=>JSON.stringify(tenantRows),exec:{},sha256:()=>'',Counter:class{add(){}},Date:{now:()=>++now},console:{error:s=>logs.push(s)},http:{get:(url,options)=>{
 requests.push({ordinal:requests.length+1,timeout:options.timeout,name:options.tags.name});
 if(kind==='success'||requests.length===1)return {status:200,body:JSON.stringify({token:privateValue})};
 const value={status:503,body:JSON.stringify({error:'AUTHORITY_UNAVAILABLE',token:privateValue,detail:privateValue}),headers:{'Content-Type':'application/json','Retry-After':'5'}};
 if(kind==='unknown')value.body=JSON.stringify({error:privateValue});
 if(kind==='invalid')value.body='{'+privateValue;
 if(kind==='large')value.body=JSON.stringify({error:'AUTHORITY_UNAVAILABLE',detail:privateValue.repeat(500)});
 if(kind==='html'){value.body='<html>'+privateValue+'</html>';value.headers['Content-Type']='text/html';}
 if(kind==='retry-secret')value.headers['Retry-After']=privateValue;
 return value;
}}};
c.SharedArray=function(name,factory){return factory();};c.console.log=()=>{};c.http.batch=rows=>rows.map(r=>c.http.get(r.url,r.params));
vm.createContext(c);let code=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
code+='\nlet result=null,error=null;try{result=setup()}catch(e){error=e.message};JSON.stringify({jwtCount:result?result.jwts.length:null,error,logs,requests});';
console.log(vm.runInContext(code,c,{timeout:2000}));'''
class SetupRefusal(unittest.TestCase):
 def observe(self,kind,concurrency=1):
  with tempfile.TemporaryDirectory() as tmp:
   output=Path(tmp)/'workload.js';generate(adapter.ROOT,output)
   return json.loads(subprocess.check_output(['node','-e',JS,str(output),kind,str(concurrency)],text=True))
 def test_success_keeps_serial_exchange_and_no_refusal_output(self):
  result=self.observe('success');self.assertEqual(result['jwtCount'],3);self.assertEqual(result['logs'],[]);self.assertIsNone(result['error']);self.assertEqual(len(result['requests']),3)
 def test_failure_records_safe_phase_index_clock_and_still_aborts(self):
  result=self.observe('allowed');self.assertEqual(result['error'],'exchange refused 503');self.assertEqual(len(result['requests']),2)
  self.assertEqual(result['requests'],[{'ordinal':1,'timeout':'60000ms','name':'exchange'},{'ordinal':2,'timeout':'60000ms','name':'exchange'}])
  self.assertEqual(len(result['logs']),1);event=json.loads(result['logs'][0].split(' ',1)[1]);self.assertEqual(event,{'phase':'jwt-setup','tenantIndex':1,'requestOrdinal':2,'status':503,'errorCode':'AUTHORITY_UNAVAILABLE','bodyObservation':'ALLOWLISTED_ERROR_CODE','retryAfterSeconds':5,'startedAtMs':1003,'finishedAtMs':1004,'elapsedMs':1})
  self.assertNotIn('DO_NOT_RETAIN',json.dumps(result));self.assertNotIn('example.test',json.dumps(event));self.assertNotIn('token',json.dumps(event))
 def test_batch_refusal_keeps_roster_index_safe_envelope_and_aborts(self):
  for concurrency in (2,16,64):
   result=self.observe('allowed',concurrency);self.assertEqual(result['error'],'exchange refused 503');self.assertIsNone(result['jwtCount'])
   event=json.loads(result['logs'][0].split(' ',1)[1]);self.assertEqual(event['tenantIndex'],1);self.assertEqual(event['requestOrdinal'],2)
   self.assertEqual(event['errorCode'],'AUTHORITY_UNAVAILABLE');self.assertEqual(event['retryAfterSeconds'],5)
   self.assertEqual((event['startedAtMs'],event['finishedAtMs'],event['elapsedMs']),(1002,1003,1))
   self.assertNotIn('DO_NOT_RETAIN',json.dumps(result));self.assertNotIn('example.test',json.dumps(event))
 def test_unknown_invalid_large_and_nonjson_bodies_never_escape(self):
  for kind,observation in [('unknown','UNRECOGNIZED_ERROR_CODE'),('invalid','INVALID_JSON'),('large','BODY_OUTSIDE_BOUND'),('html','NOT_JSON')]:
   with self.subTest(kind=kind):
    result=self.observe(kind);self.assertNotIn('DO_NOT_RETAIN',json.dumps(result));event=json.loads(result['logs'][0].split(' ',1)[1]);self.assertIsNone(event['errorCode']);self.assertEqual(event['bodyObservation'],observation);self.assertEqual(result['error'],'exchange refused 503')
 def test_untrusted_retry_header_never_escapes(self):
  result=self.observe('retry-secret');self.assertNotIn('DO_NOT_RETAIN',json.dumps(result));self.assertIsNone(json.loads(result['logs'][0].split(' ',1)[1])['retryAfterSeconds'])
if __name__=='__main__':unittest.main()
