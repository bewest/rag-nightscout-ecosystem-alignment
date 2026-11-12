#!/usr/bin/env python3
"""Exercise the deployment edge with disposable mock upstreams, never real tenants."""
import argparse, concurrent.futures, hashlib, json, pathlib, subprocess, tempfile, time, urllib.error, urllib.request, uuid
NGINX='nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10'
NODE='node@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d'
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=60)
 if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1500:])
 return p.stdout.strip()
def main():
 a=argparse.ArgumentParser();a.add_argument('--deploy',required=True);a.add_argument('--out',required=True);a.add_argument('--allow-dirty',action='store_true');args=a.parse_args()
 deploy=pathlib.Path(args.deploy).resolve();out=pathlib.Path(args.out).resolve()
 if out.exists(): raise SystemExit('Refusing to overwrite captured evidence')
 dirty=run('git','-C',str(deploy),'status','--porcelain')
 if dirty and not args.allow_dirty: raise SystemExit('Deployment tree must be clean')
 result={'deploy_head':run('git','-C',str(deploy),'rev-parse','HEAD'),'dirty_prototype':bool(dirty),'scope':'edge boundary with mock upstreams; not application/client/capacity acceptance','images':[NGINX,NODE],'checks':{},'harness_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
 name='ns-m7-edge-'+uuid.uuid4().hex[:10];created=[];networks=[]
 scratch=pathlib.Path(tempfile.mkdtemp(prefix='ns-m7-edge-'));config=scratch/'nginx.conf'
 (scratch/'mock.js').write_text("const http=require('node:http');for(const port of [1337,1339,1340])http.createServer((q,s)=>setTimeout(()=>{s.writeHead(200);s.end('synthetic\\n')},new URL(q.url,'http://mock').searchParams.has('hold')?700:0)).listen(port,'0.0.0.0');")
 def render(low,omit_rate=False):
  script="const fs=require('node:fs'),path=require('node:path');const base=process.argv[1],low=process.argv[2]==='1';const source=low?{NS_EDGE_CONNECTIONS_PER_IP:'2',NS_EDGE_HANDSHAKES_PER_SECOND:'1',NS_EDGE_HANDSHAKE_BURST:'1'}:{};process.stdout.write(require(path.join(base,'edge')).render(fs.readFileSync(path.join(base,'nginx.compose.conf'),'utf8'),{replicas:2,source}));"
  text=run('node','-e',script,str(deploy/'bindings/compose/multitenant'),'1' if low else '0')
  if omit_rate: text='\n'.join(x for x in text.splitlines() if 'limit_req zone=socket_handshakes' not in x)
  config.write_text(text+'\n')
 def request(path):
  try:
   with urllib.request.urlopen(origin+path,timeout=5) as r:return r.status
  except urllib.error.HTTPError as e:return e.code
 def wave(paths):
  with concurrent.futures.ThreadPoolExecutor(max_workers=len(paths)) as pool:return list(pool.map(request,paths))
 def reload():
  run('docker','exec',name+'-edge','nginx','-s','reload');time.sleep(.3)
 try:
  render(False);run('docker','network','create','--internal',name);networks.append(name)
  run('docker','network','create',name+'-ingress');networks.append(name+'-ingress')
  run('docker','run','-d','--name',name+'-mock','--network',name,'--network-alias','api','--network-alias','api-internal','--network-alias','realtime','--network-alias','ui','-v',str(scratch/'mock.js')+':/mock.js:ro',NODE,'node','/mock.js');created.append(name+'-mock')
  run('docker','run','-d','--name',name+'-edge','--network',name+'-ingress','--network',name,'-p','127.0.0.1::8080','-v',str(config)+':/etc/nginx/nginx.conf:ro',NGINX);created.append(name+'-edge')
  port=run('docker','port',name+'-edge','8080/tcp').rsplit(':',1)[1];origin='http://127.0.0.1:'+port
  for _ in range(40):
   try:
    if request('/api/v1/status.json')==200:break
   except Exception:pass
   time.sleep(.2)
  else:raise RuntimeError('Mock edge did not become ready')
  result['checks']['baseline_healthy']=request('/api/v1/status.json')==200
  render(True);reload()
  handshakes=[request('/socket.io/?EIO=4&transport=polling') for _ in range(6)]
  result['handshake_statuses']=handshakes;result['checks']['handshake_budget_refuses']=429 in handshakes and 200 in handshakes
  existing=[request('/socket.io/?EIO=4&transport=polling&sid=established') for _ in range(6)]
  result['existing_statuses']=existing;result['checks']['existing_sessions_skip_handshake_budget']=existing==[200]*6
  held=wave(['/socket.io/?sid=existing&hold=1']*3);result['held_statuses']=held;result['checks']['per_ip_concurrency_refuses']=sorted(held)==[200,200,429]
  render(True,omit_rate=True);reload();unlimited=[request('/socket.io/?EIO=4&transport=polling') for _ in range(6)]
  result['mutant_statuses']=unlimited;result['checks']['removed_rate_control_is_red']=429 not in unlimited
  render(False);reload();restored=wave(['/socket.io/?sid=existing&hold=1']*3)
  result['restored_statuses']=restored;result['checks']['restored_default_budget_serves']=restored==[200]*3
  result['verdict']='PASS' if all(result['checks'].values()) else 'FAIL'
 except Exception as error:
  result['verdict']='NO-MEASUREMENT' if not result['checks'] else 'FAIL';result['failure']=str(error)[-1500:]
  raise
 finally:
  result['cleanup']={}
  for item in reversed(created):
   p=subprocess.run(['docker','rm','-f','-v',item],capture_output=True,text=True);result['cleanup'][item]=p.returncode
  for net in reversed(networks):
   p=subprocess.run(['docker','network','rm',net],capture_output=True,text=True);result['cleanup'][net]=p.returncode
  out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'verdict':result.get('verdict'),'checks':result['checks'],'cleanup':result['cleanup']}))
 if result.get('verdict')!='PASS' or any(result['cleanup'].values()):raise SystemExit(1)
if __name__=='__main__':main()
