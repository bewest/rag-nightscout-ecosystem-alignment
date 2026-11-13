"""Record the real bounded readiness child outcome before evaluating its verdict."""
import subprocess,json,time,hashlib,pathlib

def execute(argv,payload,folder,timeout=25,runner=subprocess.run):
    folder=pathlib.Path(folder);row={'startedAtMs':time.time_ns()//1000000,'timedOut':False};result=None
    try:
        result=runner(argv,input=payload,capture_output=True,text=True,timeout=timeout);row['returnCode']=result.returncode;stdout=result.stdout;stderr=result.stderr
    except subprocess.TimeoutExpired as error:
        row.update(timedOut=True,returnCode=None);stdout=error.stdout or b'';stderr=error.stderr or b''
    row.update(endedAtMs=time.time_ns()//1000000,stdoutSha256=hashlib.sha256(stdout.encode()if isinstance(stdout,str)else stdout).hexdigest(),stderrSha256=hashlib.sha256(stderr.encode()if isinstance(stderr,str)else stderr).hexdigest())
    (folder/'api-readiness-process.json').write_text(json.dumps(row,indent=2)+'\n');(folder/'api-readiness.log').write_text(stdout if isinstance(stdout,str)else stdout.decode(errors='replace'))
    return result
