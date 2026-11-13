"""Bounded host commands; retain leader PID until exact process-group cleanup.

Uses the reviewed waitid(WNOWAIT) pattern from nightscout-deploy's idp-worker.
This supervises host CLI processes, never claims cancellation of Docker daemon work.
"""
import os,signal,subprocess,time,resource
from pathlib import Path

def run(argv,environment,directory,seconds=30,byte_limit=4*1024*1024):
    directory=Path(directory);directory.mkdir(mode=0o700)
    paths=[directory/'stdout.log',directory/'stderr.log'];p=None;failure=None;signals=[];drained=False;code=None
    start=time.monotonic_ns()
    with open(paths[0],'xb',opener=lambda p,f:os.open(p,f,0o600))as out,open(paths[1],'xb',opener=lambda p,f:os.open(p,f,0o600))as err:
        try:
            def child_limit():resource.setrlimit(resource.RLIMIT_FSIZE,(byte_limit//2,byte_limit//2))
            p=subprocess.Popen(argv,preexec_fn=child_limit,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=environment,start_new_session=True)
            deadline=time.monotonic()+seconds
            while os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)is None:
                if time.monotonic()>=deadline:failure='COMMAND_TIMEOUT';break
                if sum(x.stat().st_size for x in paths)>byte_limit:failure='COMMAND_OUTPUT_BOUND';break
                time.sleep(.02)
        finally:
            if p is not None:
                for sig in (signal.SIGTERM,signal.SIGKILL):
                    try:os.killpg(p.pid,sig);signals.append({'signal':sig.name,'sent':True})
                    except ProcessLookupError:signals.append({'signal':sig.name,'sent':False})
                    except OSError:failure=failure or 'GROUP_SIGNAL_UNKNOWN'
                    if sig==signal.SIGTERM:time.sleep(.05)
                deadline=time.monotonic()+2
                while True:
                    live=[]
                    for entry in Path('/proc').iterdir():
                        if not entry.name.isdigit():continue
                        try:fields=(entry/'stat').read_text().rsplit(') ',1)[1].split()
                        except (OSError,IndexError):continue
                        if int(fields[2])==p.pid and fields[0]not in ('Z','X'):live.append(int(entry.name))
                    if not live:drained=True;break
                    if time.monotonic()>=deadline:failure=failure or 'GROUP_DRAIN_UNKNOWN';break
                    time.sleep(.01)
                try:code=p.wait(timeout=2)
                except subprocess.TimeoutExpired:failure=failure or 'LEADER_EXIT_UNKNOWN'
    size=sum(x.stat().st_size for x in paths)
    if size>byte_limit or any(x.stat().st_size>=byte_limit//2 for x in paths):failure=failure or 'COMMAND_OUTPUT_BOUND'
    return {'argv':argv,'returnCode':code,'failure':failure,'operationOutcome':'UNKNOWN'if failure else'EXITED','resourceOutcome':'NOT_PROVEN_BY_PROCESS_EXIT','stdout':str(paths[0]),'stderr':str(paths[1]),'bytes':size,'pid':p.pid if p else None,'groupDrained':drained,'signals':signals,'startedMonotonicNs':start,'finishedMonotonicNs':time.monotonic_ns()}
