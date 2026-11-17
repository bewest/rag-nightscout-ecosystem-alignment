#!/usr/bin/env python3
"""Finite real k6 histogram retention control; synthetic HTTP, no application fixture."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from workload import generate
from http_accounting import assess


def run(output,image):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    image_id=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]['Id']
    owner=uuid.uuid4().hex;name='m7-http-witness-'+owner[:12]
    generate(Path(__file__).resolve().parents[3],output/'workload.js')
    (output/'tenants.json').write_text(json.dumps([{'id':'synthetic-a','host':'a.example.test','token':'synthetic-token'}]))
    observed=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def handle_request(self):
            route=self.path.split('?')[0]
            if route.startswith('/api/v2/authorization/request/'):
                status,body=200,b'{"token":"synthetic-jwt"}'
            else:
                status={'/api/v1/entries':503,'/api/v1/devicestatus':409,'/api/v3/treatments':201,'/api/v1/entries/sgv.json':403,'/api/v1/devicestatus.json':200,'/api/v1/treatments.json':504,'/api/v1/status.json':503}.get(route,404);body=b'{}'
            length=int(self.headers.get('Content-Length','0'));self.rfile.read(length)
            observed.append(status)
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        do_GET=do_POST=handle_request
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    argv=['docker','run','--rm','--name',name,'--label','m7.http.owner='+owner,'--network','host','--cpus','0.5','--memory','512m','--memory-swap','512m','-u',f'{os.getuid()}:{os.getgid()}','-v',str(output)+':/fixture']
    env={'BASE_URL':'http://127.0.0.1:'+str(server.server_port),'TENANTS_FILE':'/fixture/tenants.json','RUN_ID':'synthetic-native-http','RUN_START':'1800000000000','DURATION':'2','ACCEL':'1','HOT_FACTOR':'1','OFFERED_RPS':'11','SHAPES':'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'}
    for key,value in env.items():argv+=['-e',key+'='+value]
    started=time.monotonic_ns()
    try:
        with (output/'k6.private.log').open('wb') as log:
            proc=subprocess.run([*argv,image_id,'--address=127.0.0.1:0','run','--quiet','--summary-export','/fixture/summary.json','/fixture/workload.js'],stdout=log,stderr=subprocess.STDOUT,timeout=35)
        if proc.returncode:raise RuntimeError('M7_HTTP_NATIVE_K6_REFUSED')
        summary=json.loads((output/'summary.json').read_text());result=assess(summary['metrics'])
        (output/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
        assert result['sourceReconciliation']=='PASS','M7_HTTP_NATIVE_RECONCILIATION'
        assert result['httpVerdict']=='FAIL','M7_HTTP_NATIVE_FAULT_CONTROL'
        assert result['shapes']['w_sgv']['statusCodes'].get('503',0)>0
        assert result['shapes']['w_devicestatus']['writeOutcomes']['refused']>0
        assert result['shapes']['w_treatments_v3']['writeOutcomes']['accepted']>0
        assert result['setup']['statusCodes']=={'200':1}
        assert sum(r['completed'] for r in result['shapes'].values())==len(observed)
        proof={'status':'PASS','owner':owner,'imageId':image_id,'sharedHost':True,'limits':'one 0.5 CPU/512MiB k6 process, two-second offered scenario; no capacity or scheduling benchmark','elapsedNs':str(time.monotonic_ns()-started),'sourceResponses':len(observed),'histogramSelectors':sum(k.startswith('m7_http_completed{') and ',status:' in k for k in summary['metrics']),'nativeFaultVerdict':result['httpVerdict']}
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
        ids=subprocess.check_output(['docker','ps','-aq','--filter','name=^/'+name+'$'],text=True).split()
        for cid in ids:
            row=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
            assert row['Config']['Labels'].get('m7.http.owner')==owner,'M7_HTTP_CLEANUP_OWNER'
            subprocess.run(['docker','rm','-f',cid],check=True,stdout=subprocess.DEVNULL)
        assert not subprocess.check_output(['docker','ps','-aq','--filter','name=^/'+name+'$'],text=True).strip()
        (output/'cleanup.json').write_text(json.dumps({'owner':owner,'containerAbsent':True,'listenerClosed':True})+'\n')

if __name__=='__main__':run(*sys.argv[1:])
