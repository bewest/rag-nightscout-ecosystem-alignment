from pathlib import Path
import subprocess,json,os,time
ledger=Path('/tmp/evaluator-source-phase-processes.json');identity=Path('/tmp/evaluator-source-qualification-identity.json')
def run(name,args,cwd=None,env=None):
 data=json.loads(ledger.read_text())if ledger.exists()else{'version':1,'source':{k:v for k,v in json.loads(identity.read_text()).items()if k in ['core','deploy','alignment','nonce','project']},'phases':{}}
 assert name not in data['phases'];log=Path('/tmp/evaluator-source-process-'+name+'.log');assert not log.exists();row={'argv':args,'log':str(log),'startedAtMs':time.time_ns()//1000000,'state':'running'};data['phases'][name]=row
 def save():
  ledger.write_text(json.dumps(data,indent=2)+'\n');os.chmod(ledger,0o600);state=Path(json.loads(identity.read_text())['state'])
  if(state/'artifacts').exists():(state/'artifacts/phase-processes.json').write_text(ledger.read_text());os.chmod(state/'artifacts/phase-processes.json',0o600)
 save()
 with open(log,'x')as out:
  os.chmod(log,0o600);result=subprocess.run(args,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT)
 row.update(returnCode=result.returncode,finishedAtMs=time.time_ns()//1000000,state='completed');save();print(json.dumps({'phase':name,'returnCode':result.returncode,'log':str(log)}),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
 return result
