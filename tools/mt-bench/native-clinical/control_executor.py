"""Actual executor and stock recording-port controls, never resource effects."""
import argparse,json,os,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main(output):
    output=Path(output);output.mkdir(mode=0o700);tree=output/'tools/mt-bench/native-clinical';tree.parent.mkdir(parents=True);shutil.copytree(HERE,tree,ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('native-admission','m7-joined'):os.symlink(HERE.parent/name,tree.parent/name,target_is_directory=True)
    results=[]
    def check(name,cmd,expected):
        r=subprocess.run(cmd,cwd=tree,capture_output=True,timeout=30);(output/(name+'.stdout.log')).write_bytes(r.stdout);(output/(name+'.stderr.log')).write_bytes(r.stderr);results.append({'case':name,'returnCode':r.returncode,'expectedSuccess':expected});assert(r.returncode==0)==expected,name
    check('executor-fixed',['python3','-B','test_runtime.py'],True)
    runtime=tree/'runtime.py';fixed=runtime.read_bytes();original=subprocess.run(['git','show','10421bcbdec3624e312b063ec84e6346fae2ef9b:tools/mt-bench/native-clinical/runtime.py'],cwd=HERE,capture_output=True,check=True).stdout
    runtime.write_bytes(original);check('original-executor',['python3','-B','test_runtime.py'],False);runtime.write_bytes(fixed);check('executor-restored',['python3','-B','test_runtime.py'],True)
    producer=tree/'clinical.py';fixed_producer=producer.read_bytes();old_producer=subprocess.run(['git','show','0390341166706d3214e22eed215c9d97765a6e57:tools/mt-bench/native-clinical/clinical.py'],cwd=HERE,capture_output=True,check=True).stdout
    producer.write_bytes(old_producer);check('terminal-thread-not-drained',['python3','-B','test_runtime.py'],False);producer.write_bytes(fixed_producer);check('producer-custody-restored',['python3','-B','test_runtime.py'],True)
    client=tree/'client.cjs';fixed=client.read_text();check('stock-fixed',['node','test_stock_client.cjs'],True)
    for name,before,after in [('frame-day','frame.sgvs.length>512','frame.sgvs.length>128'),('unrelated-later','x.mills===writeResult.date','x.mills>=writeResult.date'),('packet-bound','size>1048576||socketBytes>268435456','false'),('late-close-budget',"need(!socketBudgetRefused,'CLIENT_SOCKET_BYTE_BUDGET');",''),('stock-reserved-event','socketBudgetRefused=true;socket.close();',"socketBudgetRefused=true;socket.emit('connect_error',Error('CLIENT_SOCKET_BYTE_BUDGET'));socket.close();")]:
        assert before in fixed;client.write_text(fixed.replace(before,after));check(name,['node','test_stock_client.cjs'],False);client.write_text(fixed);check(name+'-restored',['node','test_stock_client.cjs'],True)
    (output/'results.private.json').write_text(json.dumps({'scope':'actual executor/finally and stock recording API controls; no HTTP/socket/PG/Docker/native acceptance','cases':results},indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');a=p.parse_args();os.umask(0o077);main(a.output)
