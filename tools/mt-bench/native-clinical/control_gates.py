"""Private scratch semantic ablations, never edits source/product/retained runs."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
CASES=[
 ('foreign-count','gates.py',"need(not any(foreign.values()),'FOREIGN_MARKED_WRITES')","need(True,'FOREIGN_MARKED_WRITES')"),
 ('healthy-B-rebound','gates.py',"before[key]==during.get(key)==after.get(key)","True"),
 ('cached-nonfinite','gates.py',"bg.get('meanFinite')is True","True"),
 ('cold-peak','gates.py',"observed['peakActive']<=limits['activeLimit']","True"),
 ('final-source-guard','runtime.py',"need(D.SOURCE_JOIN=='REVIEWED_FINAL_SOURCE'and plan.get('runtimeReady')is True,'FINAL_SOURCE_JOIN_REQUIRED_BEFORE_EFFECTS')","need(True,'FINAL_SOURCE_JOIN_REQUIRED_BEFORE_EFFECTS')"),
 ('cold-zero-active','gates.py',"1<=observed['peakActive']","0<=observed['peakActive']"),
 ('feed-runtime','gates.py',"before[service]['runtimeId']==after[service].get('runtimeId')","True"),
 ('producer-cancel','producer_process.py',"                if cancel_event is not None and cancel_event.is_set():failure='COMMAND_CANCELLED';break\n",''),
]
def main(output):
 output=Path(output);output.mkdir(mode=0o700);tree=output/'tools/mt-bench/native-clinical';tree.parent.mkdir(parents=True);shutil.copytree(HERE,tree,ignore=shutil.ignore_patterns('__pycache__'))
 for name in ('native-admission','m7-joined'):os.symlink(HERE.parent/name,tree.parent/name,target_is_directory=True)
 results=[]
 def check(label,expected):
  run=subprocess.run(['python3','-B','test_gates.py'],cwd=tree,capture_output=True,timeout=15);(output/(label+'.stdout.log')).write_bytes(run.stdout);(output/(label+'.stderr.log')).write_bytes(run.stderr);results.append({'case':label,'returnCode':run.returncode,'expectedSuccess':expected});assert(run.returncode==0)==expected
 check('fixed',True)
 for name,file,before,after in CASES:
  p=tree/file;original=p.read_text();assert original.count(before)==1,(name,'anchor changed');p.write_text(original.replace(before,after));check(name,False);p.write_text(original);check(name+'-restored',True)
 # Real reused accountant classification and raw HTTP status, recording ports.
 p=tree/'client.cjs';source=p.read_text();before='status===201?200:status';assert source.count(before)==1
 for label,body,expected in [('client-fixed',source,True),('client-201-ablation',source.replace(before,'status'),False),('client-restored',source,True)]:
  p.write_text(body);run=subprocess.run(['node','test_client.cjs'],cwd=tree,capture_output=True,timeout=10);(output/(label+'.stdout.log')).write_bytes(run.stdout);(output/(label+'.stderr.log')).write_bytes(run.stderr);results.append({'case':label,'returnCode':run.returncode,'expectedSuccess':expected});assert(run.returncode==0)==expected
 (output/'results.private.json').write_text(json.dumps({'scope':'source/model/owned harmless process controls only; no network/PG/Docker','cases':results},indent=2)+'\n')
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output');args=parser.parse_args();os.umask(0o077);main(args.output)
