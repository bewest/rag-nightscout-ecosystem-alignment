import sys
from pathlib import Path
import subprocess,os,hashlib,json
root=Path(sys.argv[1]).resolve()
p=root/'lib/server/internal-api/transport.js';original=p.read_bytes();text=original.decode()
env={'PATH':os.environ['PATH'],'HOME':'/tmp','NODE_ENV':'test','CI':'true','TZ':'UTC'}
args=['node','bin/with-env.js','./tests/ci.test.env','node_modules/mocha/bin/mocha.js','--fail-zero','--timeout','10000','--require','./tests/hooks.js','--exit','tests/internal-api-composition.test.js','--reporter','spec','--grep','refuses a request naming a foreign or unregistered service before dispatch']
results=[]
try:
 for name,needle,label in [('owner',"req.headers['x-nightscout-internal-service'] !== route.service.id || ",'foreign co-resident service'),('version',"req.headers['x-nightscout-internal-version'] !== route.service.version ||",'old lifecycle wire version')]:
  assert text.count(needle)==1,(name,text.count(needle))
  p.write_text(text.replace(needle,''))
  run=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True)
  output=run.stdout+run.stderr
  Path('/tmp/internal-composition-control-'+name+'-red.log').write_text(output)
  assert run.returncode==2 and '2 failing' in output and label in output and '200 !== 503' in output,(name,run.returncode,output)
  results.append({'control':name,'exit':run.returncode,'symptom':label+': actual200 expected503','mutatedSourceSha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  p.write_bytes(original)
finally:p.write_bytes(original)
assert p.read_bytes()==original
print(json.dumps({'originalTransportSha256':hashlib.sha256(original).hexdigest(),'restoredByteIdentical':True,'controls':results},indent=2))
