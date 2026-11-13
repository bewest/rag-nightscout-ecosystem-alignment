"""Own supervisor: directly retain actual collector process exit, never infer it."""
import hashlib,json,os,pathlib,subprocess,sys,time
os.umask(0o077);here=pathlib.Path(__file__).parent
if __name__=='__main__':
 spec=here/'strict-time.spec.private.json';assert spec.is_file()
 with (here/'launch.once').open('x') as out:out.write('exactly-once supervisor launched\n')
 started=time.time_ns()//1000000
 with (here/'strict-time.stdout.log').open('xb') as log:
  result=subprocess.run([sys.executable,str(here/'capture.py'),str(spec)],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
 record={'kind':'native-collector-process-exit','returnCode':result.returncode,'startedAtMs':started,'finishedAtMs':time.time_ns()//1000000,'driverSha256':hashlib.sha256((here/'capture.py').read_bytes()).hexdigest(),'specSha256':hashlib.sha256(spec.read_bytes()).hexdigest(),'stdoutSha256':hashlib.sha256((here/'strict-time.stdout.log').read_bytes()).hexdigest()}
 raw=here/'strict-time/observation.private.json'
 if raw.is_file():record['rawProofSha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
 with (here/'process-result.private.json').open('x') as out:json.dump(record,out,separators=(',',':'));out.write('\n')
 print(json.dumps(record));raise SystemExit(result.returncode)
