"""Bound only a freshly spawned owned process group; no process-name matching."""
import subprocess,os,signal,time
from pathlib import Path

def run(argv,output,timeout,grace=1):
    process=subprocess.Popen(argv,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    group=process.pid
    result={'pid':process.pid,'processGroup':group,'startedAtMs':time.time_ns()//1000000,'timedOut':False}
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        result['timedOut']=True
        try:os.killpg(group,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=grace)
        except subprocess.TimeoutExpired:pass
        # The supervisor may exit before a descendant; stop only its new group.
        try:os.killpg(group,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=grace)
        # Wait for the exact owned group's descendants to stop after SIGKILL.
        deadline=time.monotonic()+grace
        while True:
            alive=[]
            for item in Path('/proc').iterdir():
                if not item.name.isdigit():continue
                try:
                    raw=(item/'stat').read_text();tail=raw[raw.rfind(')')+2:].split()
                    if int(tail[2])==group and tail[0]!='Z':alive.append(int(item.name))
                except (FileNotFoundError,ProcessLookupError,PermissionError):pass
            if not alive:break
            if time.monotonic()>=deadline:raise RuntimeError('OWNED_PROCESS_GROUP_CLEANUP_REFUSED')
            time.sleep(.01)
        result['ownedGroupNoLiveMembers']=True
    result.update(returnCode=process.returncode,finishedAtMs=time.time_ns()//1000000)
    return result
