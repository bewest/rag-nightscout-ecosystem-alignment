from pathlib import Path
import subprocess,os,time,json
root=Path(__file__).parent;record=root/'process.json';assert not record.exists();env={k:v for k,v in os.environ.items()if not k.startswith(('NS_','BENCH_','MULTITENANT_'))};start=time.time_ns()//1000000
with open(root/'driver.log','x')as out:
 os.chmod(root/'driver.log',0o600);r=subprocess.run(['node',str(root/'episode.cjs')],env=env,stdout=out,stderr=subprocess.STDOUT)
result={'experiment':'separate-fresh-clinical-ingestion','returnCode':r.returncode,'startedAtMs':start,'finishedAtMs':time.time_ns()//1000000};record.write_text(json.dumps(result,indent=2)+'\n');os.chmod(record,0o600);print(json.dumps(result));raise SystemExit(r.returncode)
