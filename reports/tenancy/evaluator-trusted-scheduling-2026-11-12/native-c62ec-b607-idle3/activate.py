import pathlib,subprocess,time,json,os,sys
from owned_process import run
os.umask(0o077);h=pathlib.Path(__file__).parent;freeze=json.loads((h/'freeze.json').read_text());assert freeze['released'] is True and freeze['fileCount']==45;assert sys.argv[1:]==['--release','root-idle3-native-witness'];state=pathlib.Path('/tmp/ns-evaluator-binding-proof-20261112-guard');p=h/'activation-processes.private.json';assert not p.exists();deadline=time.monotonic()+300;(h/'activation-deadline.json').write_text(json.dumps({'deadlineMonotonic':deadline,'actionLimitSeconds':300,'cleanupLimitSeconds':45})+'\n');record={'kind':'direct-settled-activation-processes','startedAtMs':time.time_ns()//1000000,'phases':{}};code=0
try:
 for name,script in [('restart','restart.py'),('sequence','sequence.py')]:
  with(h/('activation-'+name+'.stdout.log')).open('xb')as log:r=run([sys.executable,str(h/script)],log,max(.1,deadline-time.monotonic()+45))
  record['phases'][name]=r;p.write_text(json.dumps(record,indent=2)+'\n')
  if r['returnCode']or r['timedOut']:code=r['returnCode']or 1;break
finally:
 old=json.loads((state/'artifacts/retained-final-stop.private.json').read_text());expected={c['Id']:c for c in old['after']};ids=list(expected);rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True,timeout=5));assert len(rows)==15
 for c in rows:assert c['Image']==expected[c['Id']]['Image']and c['Config']['Labels']==expected[c['Id']]['Config']['Labels']
 if any(c['State']['Running']for c in rows):
  with(h/'fallback-stop-owned15.stdout.log').open('xb')as log:r=run(['docker','stop','--time','20',*ids],log,45)
  record['fallbackStop']=r;assert r['returnCode']==0
 after=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True,timeout=5));assert all(not c['State']['Running']and c['State']['Status']=='exited'for c in after);record.update(returnCode=code,retainedStopped15=True,finishedAtMs=time.time_ns()//1000000);p.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
raise SystemExit(code)
