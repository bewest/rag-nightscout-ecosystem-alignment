"""One bounded actual capture through the selected controller's locked observer.

No starts/stops, SQL, direct observer-port calls, retries or cleanup. The owner
runs a new capture directory at each controller-owned lifecycle boundary.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import selectors
import signal
import time
import tagged_admission as T

MAX_HELD_GENERATIONS = 128
MAX_COMMANDS = 131
TOTAL_OUTPUT_BYTES = 16*1024*1024
EPISODE_SECONDS = 120
CLEANUP_RESERVE_SECONDS = 4


def instrument_identity():
    directory=Path(T.__file__).resolve().parent
    names=('tagged_admission.py','tagged_capture.py','test_tagged_admission.py','test_tagged_capture.py','tagged-admission.md')
    files={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in names}
    value={'kind':T.KIND,'files':files}
    return {**value,'sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def write(path, value):
    with open(path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as output:
        json.dump(value, output, indent=2)
        output.write('\n')


def bounded_execute(argv, environment, *, deadline_seconds=90, exit_wait_seconds=2, output_bytes=4*1024*1024):
    process = None
    selector = selectors.DefaultSelector()
    stdout, stderr = bytearray(), bytearray()
    failure = None
    original_failure = None
    code = None
    try:
        process = subprocess.Popen(argv, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        outputs = {process.stdout:stdout, process.stderr:stderr}
        for stream in outputs:selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic()+deadline_seconds
        remaining = output_bytes
        while selector.get_map():
            if time.monotonic() >= deadline:failure='TIMEOUT';break
            for key,_ in selector.select(min(.1,max(0,deadline-time.monotonic()))):
                data=os.read(key.fileobj.fileno(),min(65536,remaining+1))
                if not data:selector.unregister(key.fileobj);continue
                outputs[key.fileobj].extend(data[:remaining]);remaining-=min(len(data),remaining)
                if not remaining:failure='OUTPUT_BOUND';break
            if failure:break
        if failure is None:
            try:code=process.wait(timeout=exit_wait_seconds)
            except subprocess.TimeoutExpired as error:
                failure='WAIT_EXIT_TIMEOUT';original_failure=type(error).__name__
    except Exception as error:
        failure='COMMAND_EXCEPTION';original_failure=type(error).__name__
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                except Exception as error:
                    failure=failure or 'CLEANUP_UNCONFIRMED';original_failure=original_failure or type(error).__name__
            try:code=process.wait(timeout=exit_wait_seconds)
            except Exception as error:
                failure=failure or 'EXIT_UNKNOWN';original_failure=original_failure or type(error).__name__
            for stream in (process.stdout,process.stderr):
                if stream is not None:stream.close()
    result=subprocess.CompletedProcess(argv,code,bytes(stdout),bytes(stderr))
    result.captureFailure=failure
    result.originalFailure=original_failure
    result.operationOutcome='UNKNOWN' if failure else 'EXITED'
    return result


def capture(spec, output, run=None):
    T.need(spec.get('kind') == T.KIND, 'EXPLICIT_INSTRUMENT_REQUIRED')
    collector=instrument_identity()
    T.need(spec.get('collectorSha256') == collector['sha256'], 'COLLECTOR_IDENTITY')
    cli, state = Path(spec['controllerCli']), Path(spec['state'])
    T.need(cli.is_absolute() and state.is_absolute() and not cli.is_symlink(), 'CAPTURE_PATH')
    T.need(hashlib.sha256(cli.read_bytes()).hexdigest() == spec['controllerCliSha256'], 'CONTROLLER_BYTES')
    ledger_file=state/'connection-budget/ledger.json'
    if ledger_file.exists():
        T.need(ledger_file.stat().st_size <= 1048576, 'LEDGER_BOUND')
        preflight=json.loads(ledger_file.read_text())
        T.need(sum(r['state'] != 'RETIRED' for rows in preflight['slots'].values() for r in rows) <= MAX_HELD_GENERATIONS, 'EPISODE_GENERATION_BOUND')
    output = Path(output)
    output.mkdir(mode=0o700)  # no overwrite/retry of an episode
    write(output/'capture-spec.private.json',spec)
    write(output/'collector-identity.json',collector)
    write(output/'capture-once.json', {'startedMonotonicNs':time.monotonic_ns(), 'kind':T.KIND})
    environment = {key:os.environ[key] for key in ('PATH','HOME','USER','LANG') if key in os.environ}
    episode_deadline=time.monotonic()+EPISODE_SECONDS
    output_bytes=0
    def execute(argv):
        remaining=episode_deadline-time.monotonic()-CLEANUP_RESERVE_SECONDS
        return bounded_execute(argv, environment,deadline_seconds=min(90,remaining),output_bytes=min(4*1024*1024,TOTAL_OUTPUT_BYTES-output_bytes))
    invoke = run or execute
    sequence = 0
    def command(argv):
        nonlocal sequence, output_bytes
        T.need(sequence < MAX_COMMANDS and time.monotonic()+CLEANUP_RESERVE_SECONDS < episode_deadline
               and output_bytes < TOTAL_OUTPUT_BYTES, 'GLOBAL_CAPTURE_BUDGET')
        sequence += 1
        started_ns=time.monotonic_ns()
        result = invoke(argv)
        finished_ns=time.monotonic_ns()
        remaining=TOTAL_OUTPUT_BYTES-output_bytes
        if len(result.stdout)+len(result.stderr) > remaining:
            kept_stdout=result.stdout[:remaining];remaining-=len(kept_stdout)
            result.stdout=kept_stdout;result.stderr=result.stderr[:remaining]
            result.captureFailure='GLOBAL_OUTPUT_BOUND';result.operationOutcome='UNKNOWN'
        output_bytes+=len(result.stdout)+len(result.stderr)
        prefix = output/str(sequence).zfill(3)
        # Capture every direct code and original output before checking it.
        for suffix, data in [('.stdout',result.stdout),('.stderr',result.stderr)]:
            with open(Path(str(prefix)+suffix), 'xb', opener=lambda p,f:os.open(p,f,0o600)) as stream:stream.write(data)
        write(Path(str(prefix)+'.json'), {'program':argv[0], 'startedMonotonicNs':str(started_ns),'finishedMonotonicNs':str(finished_ns),'returnCode':result.returncode,'captureFailure':getattr(result,'captureFailure',None),'originalFailure':getattr(result,'originalFailure',None),'operationOutcome':getattr(result,'operationOutcome','EXITED' if result.returncode is not None else 'UNKNOWN')})
        T.need(not getattr(result,'captureFailure',None), 'COMMAND_CAPTURE_INCOMPLETE')
        return result
    observed = command(['node',str(cli),str(state),'observe'])
    T.need(observed.returncode == 0, 'OBSERVER_FAILED')
    raw = json.loads(observed.stdout)
    T.need(raw.get('version') == 1 and raw.get('kind') == 'controlled-connection-observation'
           and raw.get('visibility') == 'PG_STAT_AUTHENTICATED_ONLY', 'VISIBILITY')
    brackets=raw.get('hostMonotonic',{})
    T.need(all(isinstance(brackets.get(k),str) and brackets[k].isdigit() for k in ('startedNs','finishedNs'))
           and int(brackets['finishedNs']) >= int(brackets['startedNs']), 'OBSERVER_BRACKETS')
    T.need(raw.get('source') == spec['expected']['source'] and raw.get('planSha256') == spec['expected']['planSha256']
           and raw.get('expected') == {k:spec['expected'][k] for k in ('source','project','workingDirectory','imageId')}, 'OBSERVE_IDENTITY')
    plan = json.loads((state/'connection-budget/plan.json').read_text())
    ledger = raw['ledger']  # atomically captured under the same controller lock
    T.need(sum(r['state'] != 'RETIRED' for rows in ledger['slots'].values() for r in rows) <= MAX_HELD_GENERATIONS, 'EPISODE_GENERATION_BOUND')
    image_result=command(['docker','image','inspect',spec['expected']['imageId']])
    T.need(image_result.returncode == 0, 'IMAGE_INSPECTION_FAILED')
    images=json.loads(image_result.stdout)
    T.need(isinstance(images,list) and len(images)==1 and images[0].get('Id') == spec['expected']['imageId'], 'IMAGE_IDENTITY')
    labels=images[0].get('Config',{}).get('Labels',{}) or {}
    image_source={'coreCommit':labels.get('org.opencontainers.image.revision'),'deployCommit':labels.get('org.nightscout.deploy.revision')}
    T.need(image_source == spec['expected']['source'], 'IMAGE_SOURCE')
    processes = []
    for sid, rows in ledger['slots'].items():
        for row in rows:
            if row['state'] == 'RETIRED':continue
            original = row.get('container')
            capture = {'processInstanceId':sid,'incarnation':row['incarnation'],'container':None,'inspection':'UNBOUND'}
            if original:
                cid = original['cid']
                T.need(T.hexid(cid,64), 'INSPECTION_CUSTODY')
                actual = command(['docker','inspect',cid])
                capture.update(inspectedCid=cid,inspection='UNKNOWN')
                if actual.returncode == 0:
                    values=json.loads(actual.stdout)
                    T.need(isinstance(values,list) and len(values)==1,'INSPECT_RESULT')
                    value=values[0];labels=value.get('Config',{}).get('Labels',{}) or {};status=value.get('State',{})
                    capture.update(inspection='RUNNING' if status.get('Running') is True else 'STOPPED',container={
                        'cid':value['Id'],'startedAt':status.get('StartedAt'),'running':status.get('Running'),
                        'project':labels.get('com.docker.compose.project'),'workingDirectory':labels.get('com.docker.compose.project.working_dir'),
                        'service':labels.get('com.docker.compose.service'),'imageId':value.get('Image'),
                        'source':image_source})
                # Nonzero inspection remains UNKNOWN, including missing; no
                # parse of free-form stderr can establish physical retirement.
            processes.append(capture)
    ledger_file=state/'connection-budget/ledger.json'
    T.need((ledger_file.exists() and json.loads(ledger_file.read_text()) == ledger)
           or (not ledger_file.exists() and not processes), 'LEDGER_CHANGED_DURING_INSPECTION')
    value={'expected':spec['expected'],'plan':plan,'ledger':ledger,'processes':processes,'census':{'resource':raw['resource'],'tags':raw['tags']}}
    write(output/'intake.private.json',value)
    T.need(instrument_identity() == collector, 'COLLECTOR_CHANGED')
    result=T.observe(**value)
    result['collector']=collector
    result['collectorBudget']={'maximumHeldGenerations':MAX_HELD_GENERATIONS,'maximumCommands':MAX_COMMANDS,'maximumRawCommandBytes':TOTAL_OUTPUT_BYTES,'maximumWallSeconds':EPISODE_SECONDS,'commands':sequence,'rawCommandBytes':output_bytes}
    write(output/'result.private.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    T.need(not args.spec.is_symlink() and args.spec.stat().st_mode & 0o077 == 0 and args.spec.stat().st_size <= 1048576,'PRIVATE_INPUT')
    capture(json.loads(args.spec.read_text()),args.output)


if __name__=='__main__':main()
