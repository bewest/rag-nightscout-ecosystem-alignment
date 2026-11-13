#!/usr/bin/env python3
"""Tiny owned adapter smoke. No application/capacity deployment or borrowed state."""
import collections
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
from contract import OWNER, require, oracle, digest

IMAGE='postgres@sha256:5db6dac2ef5dcff512f4f00a009c3c332b9f2f28f24277175bf3e4a3d02ef83a'


def main():
    require(len(sys.argv)==2,'M7_SMOKE_OUTPUT_REQUIRED')
    output=Path(sys.argv[1]).resolve();require(not output.exists(),'M7_SMOKE_OUTPUT_EXISTS');output.mkdir(mode=0o700,parents=True)
    captured_instrument=adapter.instrument()
    scratch=Path(tempfile.mkdtemp(prefix='m7-adapter-smoke-'));nonce=uuid.uuid4().hex
    m={'directory':str(scratch),'project':'nsm7-smoke-'+nonce[:12],'owner':nonce}
    adapter.write(scratch/'owner.json',m)
    (scratch/'env').write_text('')
    config={'services':{'postgres':{'image':IMAGE,'environment':{'POSTGRES_HOST_AUTH_METHOD':'trust','POSTGRES_DB':'nightscout_compose_test'},'labels':{OWNER:nonce}}},'networks':{'default':{'labels':{OWNER:nonce}}}}
    adapter.write(scratch/'frozen.compose.json',config)
    server=None
    try:
        host=adapter.inventory(nonce)
        adapter.write(scratch/'host-inventory.private.json',host)
        adapter.write(output/'host-inventory.private.json',host)
        # Foreign work is recorded, never stopped or treated as a quiet-host
        # capacity measurement. One PG container, six synthetic accepted writes.
        adapter.compose(scratch,'up','-d','--no-build','--pull','never','postgres',timeout=30)
        deadline=time.monotonic()+15
        while True:
            try:adapter.compose(scratch,'exec','-T','postgres','psql','-h','127.0.0.1','-U','postgres','-d','nightscout_compose_test','-c','SELECT 1;');break
            except RuntimeError:
                require(time.monotonic()<deadline,'M7_SMOKE_PG_NOT_READY');time.sleep(.1)
        adapter.assert_owned(m)
        sql=';'.join('CREATE SCHEMA nsdemo_'+kind+';CREATE TABLE nsdemo_'+kind+'.'+kind+'(tenant_id uuid NOT NULL,_id text NOT NULL,doc jsonb NOT NULL)' for kind in ('entries','devicestatus','treatments'))+';'
        adapter.psql(scratch,sql,'nightscout_compose_test')
        tenants=[{'id':str(uuid.uuid4()),'host':letter+'.example.test','token':uuid.uuid4().hex} for letter in ('a','b')]
        adapter.write(scratch/'tenants.private.json',tenants)
        metrics=collections.Counter()
        by_host={row['host']:row['id'] for row in tenants}
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                route=urllib.parse.urlsplit(self.path).path
                kind='entries' if route=='/api/v1/entries' else 'devicestatus' if route=='/api/v1/devicestatus' else 'treatments' if route=='/api/v3/treatments' else None
                tenant=by_host.get(self.headers.get('Host'))
                if not kind or not tenant:self.send_error(400);return
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                row=body[0] if isinstance(body,list) else body
                encoded=json.dumps(row).replace("'","''")
                adapter.psql(scratch,"INSERT INTO nsdemo_"+kind+'.'+kind+" VALUES ('"+tenant+"','"+uuid.uuid4().hex+"','"+encoded+"'::jsonb);",'nightscout_compose_test')
                self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}')
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        workload_record=adapter.generate_workload(adapter.ROOT,scratch/'k6/workload.js')
        calls=json.loads(adapter.command(['node',adapter.HERE/'workload-shapes.cjs',scratch/'k6/workload.js',scratch/'tenants.private.json']))
        posts=[row for row in calls if row.get('method')=='POST'];require(len(posts)==6,'M7_SMOKE_WORKLOAD_SHAPES_MISSING')
        for call in posts:
            url=urllib.parse.urlsplit(call['url']);kind=url.path.split('/')[-1]
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+url.path,data=json.dumps(call['body']).encode(),headers={'Host':call['options']['headers']['Host'],'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(request,timeout=5) as response:
                require(response.status==200,'M7_SMOKE_WRITE_NOT_ACCEPTED')
                tenant=by_host[call['options']['headers']['Host']]
                metrics['writes_ok']+=1;metrics['writes_ok{tenant:'+tenant+'}']+=1;metrics['writes_ok{kind:'+kind+'}']+=1
        load=scratch/'load';load.mkdir();(load/'runid').write_text('m7-smoke-run')
        adapter.write(load/'k6-summary.json',{'metrics':{key:{'count':value} for key,value in metrics.items()}})
        adapter.write(load/'fanout.json',{'probeWrites':{'byTenant':{}}})
        baseline=adapter.count_oracle(scratch)
        require(baseline['verdict']=='GREEN','M7_SMOKE_ORACLE_BASELINE')
        adapter.oracle_control(scratch)
        actual=adapter.document(load/'oracle-control.json')
        require(actual=={'baseline':'GREEN','broken':'RED','restored':'GREEN'},'M7_SMOKE_CONTROL_FAILED')
        compose_args=['compose','-p',m['project'],'--env-file',str(scratch/'env'),'-f',str(scratch/'frozen.compose.json')]
        script="const h=require(process.argv[1]),args=JSON.parse(process.argv[2]);(async()=>{const first=await h.restart({composeArgs:args,roles:['postgres']});let refused=false;try{await h.restart({composeArgs:args,roles:['postgres'],run:a=>a.includes('restart')?Promise.resolve(''):h.execute(a)});}catch(error){if(error.code!=='M7_RESTART_NOT_OBSERVED')throw error;refused=true;}if(!refused)throw new Error('M7_RESTART_CONTROL_VACUOUS');const restored=await h.restart({composeArgs:args,roles:['postgres']});console.log(JSON.stringify({baseline:'observed',broken:'M7_RESTART_NOT_OBSERVED',restored:'observed'}));})().catch(e=>{console.error(e.code||e.message);process.exitCode=1;});"
        restart_control=json.loads(adapter.command(['node','-e',script,adapter.HERE/'restart.cjs',json.dumps(compose_args)],timeout=30))
        adapter.write(output/'restart-control.json',restart_control)
        shutil.copyfile(load/'oracle-control.json',output/'oracle-control.json')
        adapter.write(output/'proof.json',{'kind':'instrument-smoke-only','acceptedWrites':sum(metrics[k] for k in ['writes_ok']),'tenants':2,'domains':3,'sourceOwnedPayloadFunctions':True,
            'instrument':captured_instrument,'workload':workload_record,'foreignActiveContainers':sum(not row['owned'] for row in host['containers']),
            'privateHostInventorySha256':digest(scratch/'host-inventory.private.json'),'capacity':'NO-MEASUREMENT','applicationAuthorizationClinicalRestore':'NO-MEASUREMENT',
            'limits':'HTTP fixture and direct PG storage validate instrumentation, not shipping application behavior; no k6 scheduling or sockets run'})
        print(json.dumps({'instrumentSmoke':'PASS','acceptedWrites':6,'oracle':['GREEN','RED','GREEN'],'capacity':'NO-MEASUREMENT'}))
    finally:
        if server:server.shutdown();server.server_close()
        adapter.assert_owned(m)
        adapter.compose(scratch,'down','--volumes','--remove-orphans',timeout=30)
        shutil.rmtree(scratch)

if __name__=='__main__':
    try:main()
    except Exception as error:
        if getattr(error,'stderr',None):print(error.stderr.decode()[:4000],file=sys.stderr)
        raise
