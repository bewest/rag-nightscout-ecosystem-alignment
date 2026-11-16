#!/usr/bin/env python3
"""Run the canonical M7 adapter from one reusable configuration.

Preparation starts no services. Execution uses one finite independent cleanup
process and never retries a failed phase. Raw output and partial adapter results
stay in the private run directory.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter as a
from contract import require


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.partial-' + str(os.getpid()))
    a.write(temp, value)
    os.replace(temp, path)


def code(error):
    value = str(error)
    return value if re.fullmatch(r'M7_[A-Z_]+(?::[A-Za-z0-9_.-]+)?', value) else 'M7_RUNNER_PHASE_FAILED'


def verify_helper(config):
    if 'helperInstrument' in config:
        expected = config['helperInstrument']
        require(isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected) is not None,
                'M7_RUNNER_HELPER_INSTRUMENT')
        require(a.instrument()['sha256'] == expected, 'M7_RUNNER_HELPER_INSTRUMENT')
    else:
        require(a.git(a.ROOT, 'rev-parse', 'HEAD') == config['helperHead'], 'M7_RUNNER_HELPER_HEAD')


def load_config(path):
    return validate_config(a.document(path))


def validate_config(config):
    require(config.get('version') == 1, 'M7_RUNNER_CONFIG_VERSION')
    common = {'version', 'prepare', 'k6Image', 'workSeconds', 'cleanupSeconds'}
    require(set(config) in (common | {'helperHead'}, common | {'helperInstrument'}), 'M7_RUNNER_CONFIG_FIELDS')
    verify_helper(config)
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', config['k6Image']) is not None, 'M7_RUNNER_K6_PIN')
    require(type(config['workSeconds']) is int and 30 <= config['workSeconds'] <= 10800
            and type(config['cleanupSeconds']) is int and 30 <= config['cleanupSeconds'] <= 300, 'M7_RUNNER_FINITE_LIMIT')
    options = config['prepare']
    require(isinstance(options, dict) and 'directory' not in options and 'fixture-project' in options
            and 'backend-subnet' in options and 'edge-subnet' in options, 'M7_RUNNER_PREPARE_CONFIG')
    argv = []
    for key, value in options.items():
        require(re.fullmatch(r'[a-z][a-z0-9-]+', key) and isinstance(value, (str, int, float)) and not isinstance(value, bool), 'M7_RUNNER_PREPARE_OPTION')
        argv.extend(['--' + key, str(value)])
    # The adapter owns supported options and all source/profile admission.
    parsed = a.parser().parse_args(['prepare', '--directory', '/tmp/m7-runner-validation', *argv])
    require(parsed.profile == 'pgstream-sample' and parsed.run_purpose == 'discovery', 'M7_RUNNER_DISCOVERY_ONLY')
    from run_configuration import validate_prepare
    validate_prepare(parsed)
    require(0 <= parsed.quiet_load <= (os.cpu_count() or 1), 'M7_QUIET_BOUND_INVALID')
    require(config['workSeconds'] > sum(a.cadence_options(parsed)[k] for k in ('warmupSeconds', 'idleSeconds', 'loadSeconds')), 'M7_RUNNER_WORK_WINDOW')
    return config, argv


def prepare(config_file, directory):
    config, argv = load_config(config_file)
    # Validate receipt/config mirrors before creating output or arming a guard.
    parsed=a.parser().parse_args(['prepare','--directory','/tmp/m7-runner-validation',*argv])
    receipt=a.document(parsed.freeze)
    if receipt.get('version')==2:
        from run_configuration import from_args, validate_execution
        validate_execution(config,receipt)
        resolved=from_args(parsed,a.instrument()['sha256'])
        a.receipt_scope({**resolved,'instrument':{'sha256':resolved['instrument']},'runConfiguration':resolved},receipt,'deploy')
    root = Path(directory).resolve()
    require(not root.exists(), 'M7_RUNNER_OUTPUT_EXISTS')
    root.mkdir(mode=0o700, parents=True)
    write(root / 'config.json', config)
    write(root / 'result.json', {'version': 1, 'status': 'PREPARING', 'phase': 'prepare', 'capacityAcceptance': 'NOT_GRANTED'})
    arm_window(root,config)
    try:
        stage(root,'prepare',['prepare','--directory',str(root/'fixture'),*argv])
        stage(root,'source-preflight',['source-preflight',str(root/'fixture')])
        write(root / 'result.json', {'version': 1, 'status': 'PREPARED', 'phase': 'prepare', 'runtimeStarted': False, 'configSha256': a.digest(root / 'config.json'), 'capacityAcceptance': 'NOT_GRANTED'})
    except BaseException as error:
        write(root / 'result.json', {'version': 1, 'status': 'FAILED', 'phase': 'prepare', 'code': code(error), 'runtimeStarted': False, 'capacityAcceptance': 'NOT_GRANTED'})
        try:cleanup(root,'PREPARE_FAILURE')
        except BaseException as cleanup_error:write(root/'cleanup-failure.json',{'code':code(cleanup_error)})
        raise
    return root


@contextlib.contextmanager
def custody(root):
    with (root / 'cleanup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def stop_stage(file, owner):
    """Use the adapter's birth/group fence, then verify termination before cleanup."""
    job = a.document(file)
    if job.get('completed'):return
    a.stop_job(file, owner)
    proc = Path('/proc') / str(job['pid']) / 'stat'
    def alive():
        if not proc.exists():return False
        fields = proc.read_text().rsplit(')', 1)[1].split()
        return fields[19] == str(job['startTicks']) and fields[0] != 'Z'
    until = time.monotonic() + 10
    while alive() and time.monotonic() < until:time.sleep(.05)
    if alive():
        require(job['group'] and os.getpgid(job['pid']) == job['pid'], 'M7_HOST_JOB_GROUP_CHANGED')
        # Recheck the same birth immediately before escalation.
        require(alive(), 'M7_HOST_JOB_IDENTITY_CHANGED')
        os.killpg(job['pid'], signal.SIGKILL)
        until = time.monotonic() + 2
        while alive() and time.monotonic() < until:time.sleep(.05)
    require(not alive(), 'M7_RUNNER_STAGE_STILL_LIVE')


def cleanup(root,reason):
    state=a.document(root/'execution.json') if (root/'execution.json').exists() else {}
    with a.command_deadline(state.get('cleanupAt')):
        return _cleanup(root,reason)


def _cleanup(root, reason):
    with custody(root):
        if (root / 'cleanup.json').exists():
            return a.document(root / 'cleanup.json')
        job = root / 'stage-job.json'
        if job.exists():
            value = a.document(job)
            if not value.get('completed'):
                stop_stage(job, value['owner'])
        state=a.document(root/'execution.json') if (root/'execution.json').exists() else {}
        if state.get('producer')=='vault-component-v1':
            import vault_component
            vault_component.cleanup_resources(root)
        fixture = root / 'fixture'
        if (fixture / 'owner.json').exists():
            d, m = a.load(fixture,resource_limits=False)
            with a.private_commands(root / 'cleanup-commands'):
                a.down(d, m)
            require(not a.resources(m), 'M7_RUNNER_RESOURCES_REMAIN')
            config = a.document(d / 'frozen.compose.json') if (d / 'frozen.compose.json').exists() else {}
            for kind, flag in (('networks', 'network'), ('volumes', 'volume')):
                for spec in config.get(kind, {}).values():
                    ids = a.command(['docker', flag, 'ls', '-q', '--filter', 'name=' + spec['name']]).splitlines()
                    require(not ids, 'M7_RUNNER_' + kind.upper() + '_REMAIN')
        result = {'status': 'ABSENT', 'reason': reason, 'at': time.time()}
        write(root / 'cleanup.json', result)
        return result


def guard(root):
    state = a.document(root / 'execution.json')
    write(root / 'guard-ready.json', {'pid': os.getpid(), 'owner': state['owner'], 'cleanupAt': state['cleanupAt']})
    while time.time() < state.get('stopWorkAt',state['cleanupAt']) and not (root / 'cleanup.json').exists():
        time.sleep(.2)
    if not (root / 'cleanup.json').exists():
        cleanup(root, 'FINITE_DEADLINE')
    write(root / 'guard-result.json', {'status': 'RETURNED', 'at': time.time()})


def partial(root):
    """References remain private; missing instruments are never invented zeros."""
    d = root / 'fixture'
    artifacts = {}
    for name in ('summary.json', 'runtime-readiness.json', 'deployment.json', 'role-logs/manifest.json', 'load/probe.json', 'load/k6-summary.json'):
        file = d / name
        if file.is_file():
            artifacts[name] = {'sha256': a.digest(file), 'path': str(file)}
    unreadable = []
    def retained(name):
        file = d / name
        if not file.is_file():return {}
        try:
            value = a.document(file)
            if not isinstance(value, dict):raise ValueError('not an object')
            return value
        except (OSError, ValueError):
            unreadable.append(name)
            return {}
    phase = 'NOT_STARTED'
    summary = retained('load/k6-summary.json')
    metrics = summary.get('metrics') or {}
    if not isinstance(metrics, dict):metrics = {}
    attempts = metrics.get('scenario_request_attempts') or {}
    if not isinstance(attempts, dict):attempts = {}
    count = attempts.get('count', attempts.get('values', {}).get('count'))
    if metrics:
        phase = 'SCENARIO' if isinstance(count, (int, float)) and count > 0 else 'SETUP_ONLY' if count == 0 else 'UNMEASURED'
    events = []
    log = d / 'load/k6.log'
    if log.is_file():
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 65536))
            recent = stream.read(65536).decode(errors='replace')
        for line in recent.splitlines():
            match = re.search(r'msg="((?:[^"\\]|\\.)*)"', line)
            if not match:continue
            try:
                event = json.loads(json.loads('"' + match.group(1) + '"'))
                if event.get('event') in ('jwt-setup-start', 'jwt-setup-end', 'scenario-first-iteration', 'scenario-phase-end'):
                    events.append({k: event[k] for k in ('event', 'atMs', 'tenants', 'concurrency') if k in event})
            except (ValueError, TypeError):pass
    names = {event['event'] for event in events}
    if 'scenario-first-iteration' in names:phase = 'SCENARIO'
    elif 'jwt-setup-start' in names and 'jwt-setup-end' not in names:phase = 'JWT_SETUP_INCOMPLETE'
    native = retained('summary.json')
    probe = retained('load/probe.json')
    return {'artifacts': artifacts, 'trafficPhase': phase, 'scenarioAttempts': count,
            'workloadEvents': events, 'adapterStatus': native.get('status', 'UNMEASURED'),
            'processes': native.get('processes', {}), 'strictChecks': native.get('strictChecks', {}),
            'durableOutputObservation': probe.get('durableOutputObservation', {'status':'UNMEASURED'}),
            'unreadableArtifacts': unreadable, 'optionalMetrics': 'UNMEASURED unless present in retained artifacts'}


def optional_preflight(root, directory):
    """Optional cost counters qualify their own measurements, not discovery admission."""
    captures = list(directory.glob('setup-attempts/*/readability-realtime-costs.json'))
    value = {'status': 'NO-INSTRUMENT', 'reason': 'M7_REALTIME_COST_BOOKEND_UNAVAILABLE'}
    if captures:
        latest = max(captures, key=lambda p: p.stat().st_mtime)
        try:
            observed = a.document(latest)
            value = {'status': observed.get('status', 'NO-INSTRUMENT'),
                     'artifact': str(latest), 'sha256': a.digest(latest)}
        except (OSError, ValueError, AttributeError):
            value = {'status': 'NO-INSTRUMENT', 'reason': 'M7_REALTIME_COST_UNREADABLE'}
    result = {'realtimeCosts': value, 'scope': 'discovery observation only; no acceptance granted'}
    write(root / 'preflight-observations.json', result)
    return result


def stage(root, name, args):
    state = a.document(root / 'execution.json')
    with custody(root):
        require(time.time() < state['stopWorkAt'] and not (root / 'cleanup.json').exists(), 'M7_RUNNER_WORK_DEADLINE')
        write(root / 'phase.json', {'phase': name, 'startedAt': time.time()})
        with (root / (name + '.private.log')).open('xb') as output:
            child_args = [*args]
            if child_args[:1] in (['deploy'],['preflight'],['run']):
                child_args += ['--work-deadline', str(state['stopWorkAt'])]
            child = subprocess.Popen([sys.executable, '-B', str(HERE / 'adapter.py'), *child_args], stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        a.job_record(root / 'stage-job.json', child, state['owner'], group=True)
    try:
        rc = child.wait(timeout=max(.1, state['stopWorkAt'] - time.time()))
        write(root / 'stage-job.json', {**a.document(root / 'stage-job.json'), 'completed': True, 'returncode': rc})
        write(root / (name + '-result.json'), {'phase': name, 'returncode': rc, 'endedAt': time.time()})
        require(rc == 0, 'M7_RUNNER_' + name.upper() + '_FAILED')
    finally:
        if child.poll() is None:
            stop_stage(root / 'stage-job.json', state['owner'])
            child.wait(timeout=12)


def generated_control(root, d, m):
    """Execute the generated program with a deliberately absent required input.

    This is a real Node execution, before I/O; the normal run then exercises
    the same bytes with the canonical caller/environment.
    """
    a.diagnostic_resources.configure(m.get('diagnosticResources',{}).get('profile'))
    try:
        with a.diagnostic_resources.command([m['generator']['tools']['node']['path'],str(d/'probe.js')],a.runtime_env({'M7_GENERATOR_ROOT':str(d/'dependencies')})) as (argv,env):
            with (root/'generated-control.private.log').open('xb') as output:
                result=subprocess.run(argv,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=10)
    finally:a.diagnostic_resources.configure()
    text = (root / 'generated-control.private.log').read_text()
    require(result.returncode != 0 and 'ERR_INVALID_URL' in text, 'M7_RUNNER_GENERATED_CONTROL_VACUOUS')
    write(root / 'generated-control.json', {'status': 'EXPECTED_FAILURE', 'returncode': result.returncode,
        'symptom': 'ERR_INVALID_URL', 'probeSha256': a.digest(d / 'probe.js'),
        'break': 'required --base absent; generated bytes unchanged; failure occurs before network I/O'})


def guard_alive(root):
    job=a.document(root/'guard-job.json')
    stat=Path('/proc')/str(job['pid'])/'stat'
    if not stat.exists():return False
    fields=stat.read_text().rsplit(')',1)[1].split()
    require(fields[19]==str(job['startTicks']),'M7_RUNNER_GUARD_BIRTH_CHANGED')
    return fields[0]!='Z'


def arm_window(root,config):
    require(not (root/'execution.json').exists(),'M7_RUNNER_WINDOW_EXISTS')
    start=time.time()
    state={'owner':uuid.uuid4().hex,'startedAt':start,'stopWorkAt':start+config['workSeconds'],
           'cleanupAt':start+config['workSeconds']+config['cleanupSeconds'],
           'configSha256':a.digest(root/'config.json'),'includesPreparation':True}
    if config.get('producer')=='vault-component-v1':state['producer']=config['producer']
    if os.environ.get('M7_BATCH_RESERVATION'):
        require(state['cleanupAt']<=a.document(os.environ['M7_BATCH_RESERVATION'])['cleanupAt'],'M7_BATCH_CELL_DEADLINE')
    write(root/'execution.json',state)
    with (root/'guard.private.log').open('xb') as output:
        guardian=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'_guard',str(root)],stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    a.job_record(root/'guard-job.json',guardian,state['owner'],group=True)
    deadline=time.monotonic()+5
    while not (root/'guard-ready.json').exists() and guardian.poll() is None and time.monotonic()<deadline:time.sleep(.05)
    require((root/'guard-ready.json').exists() and guardian.poll() is None,'M7_RUNNER_GUARD_NOT_READY')
    return state


def execution_window(root,config):
    state=a.document(root/'execution.json')
    require(state.get('includesPreparation') is True and state['configSha256']==a.digest(root/'config.json'), 'M7_RUNNER_WINDOW_CHANGED')
    require(state['stopWorkAt']==state['startedAt']+config['workSeconds'] and state['cleanupAt']==state['stopWorkAt']+config['cleanupSeconds'],'M7_RUNNER_WINDOW_CHANGED')
    require(time.time()<state['stopWorkAt'] and not (root/'cleanup.json').exists(),'M7_RUNNER_WORK_DEADLINE')
    require(guard_alive(root) and a.document(root/'guard-ready.json')['owner']==state['owner'],'M7_RUNNER_GUARD_NOT_READY')
    return state


def execute(directory, rehearsal=False):
    root = Path(directory).resolve()
    config, _ = load_config(root / 'config.json')
    require(a.document(root / 'result.json')['status'] == 'PREPARED' and not (root / 'deploy-result.json').exists(), 'M7_RUNNER_ALREADY_EXECUTED')
    d, m = a.load(root / 'fixture',resource_limits=False)
    state=execution_window(root,config)
    failure = None
    try:
        if rehearsal:
            generated_control(root, d, m)
        stage(root, 'deploy', ['deploy', str(d)])
        stage(root, 'preflight', ['preflight', str(d), '--k6-image', config['k6Image']])
        # Essential source/runtime/instrument checks stay in adapter preflight.
        optional_preflight(root, d)
        stage(root, 'run', ['run', str(d), '--k6-image', config['k6Image']])
        if m.get('vaultRefusalControl'):stage(root,'vault-check',['vault-check',str(d)])
    except BaseException as error:
        failure = {'code': code(error), 'errorType': type(error).__name__}
    finally:
        phase = a.document(root / 'phase.json')['phase'] if (root / 'phase.json').exists() else 'guard'
        try:
            cleanup(root, 'POINT_FINISHED' if failure is None else 'PHASE_FAILURE')
        except BaseException as error:
            write(root / 'cleanup-failure.json', {'code': code(error), 'errorType': type(error).__name__})
            failure = {**(failure or {}), 'cleanupCode': code(error)}
        until=time.monotonic()+10
        while guard_alive(root) and time.monotonic()<until:time.sleep(.05)
        if guard_alive(root):failure={**(failure or {}),'guardCode':'M7_RUNNER_GUARD_PENDING'}
        result = {'version': 1, 'status': ('COMPLETED' if partial(root)['adapterStatus'] == 'MEASURED' else 'COMPLETED_PARTIAL') if failure is None else 'FAILED_PARTIAL', 'phase': phase, 'failure': failure, 'partial': partial(root), 'cleanup': a.document(root / 'cleanup.json') if (root / 'cleanup.json').exists() else {'status': 'UNMEASURED'}, 'capacityAcceptance': 'NOT_GRANTED', 'finishedAt': time.time()}
        write(root / 'result.json', result)
    require(failure is None, 'M7_RUNNER_POINT_INCOMPLETE')
    return result



def local_batch_plan(spec, payload_root):
    import experiment_batch as batch
    planned=batch.plan(spec)
    allowlist=batch.verify_payload(spec,payload_root)
    env=spec['envelope']
    # The envelope is the caller's explicit aggregate allocation. Each cell
    # still reserves its complete enforced producer maximum below.
    batch.need(env['hourlyMicrousd']==env['totalMicrousd']==0,'LOCAL_MONEY')
    axes=env['workload']
    for cell in spec['cells']:
        batch.need(cell['target']=={'kind':'local'},'LOCAL_TARGET')
        if cell['config'].get('producer')=='vault-component-v1':
            import vault_component
            cell_plan=vault_component.plan(cell,spec,payload_root,allowlist)
            next(c for c in planned['cells'] if c['id']==cell['id'])['allocationBreakdown']=cell_plan
            batch.need(cell['config']['helperInstrument']==a.instrument()['sha256'],'VAULT_HELPER_CHANGED')
            continue
        # The current typed producer reserves its complete maximum, including
        # oneoffs/k6 and host heaps. Smaller policies need producer controls.
        batch.need(cell['resources']==batch.LOCAL_RESOURCES,'LOCAL_RESERVATION_CHANGED')
        config=cell['config'];validate_config(config);options=config['prepare']
        receipt=Path(options.get('receipt',''))
        batch.need(receipt.is_absolute() and receipt.is_relative_to(Path(payload_root).resolve()),'RECEIPT_ALLOWLIST')
        batch.need(str(receipt.relative_to(Path(payload_root).resolve())) in allowlist,'RECEIPT_ALLOWLIST')
        batch.need(config.get('helperInstrument')==spec['payload']['helper'],'HELPER_CHANGED')
        batch.need(options.get('core-commit')==spec['payload']['source']['core'] and
                   options.get('deploy-commit')==spec['payload']['source']['deploy'],'SOURCE_CHANGED')
        batch.need(options.get('image-id')==options.get('image')==spec['payload']['image'],'IMAGE_CHANGED')
        selected=options.get('diagnostic-resource-profile')
        batch.need(selected in a.diagnostic_resources.PROFILES,'LOCAL_PROFILE_REQUIRED')
        batch.need(a.diagnostic_resources.memory_ceiling(selected)<=batch.LOCAL_RESOURCES['memoryBytes'],'LOCAL_PROFILE_RESERVATION_UNSUPPORTED')
        external=options.get('pgstream-topology','colocated-v1')=='external-service-v1'
        batch.need(external==(selected in a.diagnostic_resources.EXTERNAL_PROFILES),'LOCAL_TOPOLOGY_PROFILE')
        batch.need(options.get('fixture-project')==cell['namespace'] and cell['subnets']==[options.get('backend-subnet'),options.get('edge-subnet')], 'ISOLATION_CHANGED')
        batch.need(cell['ports']==[], 'LOCAL_PORTS_UNSUPPORTED')
        batch.need(config['workSeconds']==cell['workSeconds'] and config['cleanupSeconds']==cell['cleanupSeconds'] and options.get('offered-rps')==cell['offeredRps'],'WORKLOAD_CHANGED')
        values={'tenants':options.get('tenants'),'offeredRps':cell['offeredRps'],
                'durationSeconds':options.get('load-seconds'),'probeEveryMs':options.get('probe-every-ms',1000),
                'hotFactor':options.get('hot-factor',1)}
        for key,value in values.items():
            batch.need(batch.number(value) and axes[key][0]<=value<=axes[key][1],'WORKLOAD_OUTSIDE_ENVELOPE')
        # Ordinary runner only; fault profiles must first gain a typed adapter.
        batch.need(not axes['faultCases'], 'LOCAL_FAULT_UNSUPPORTED')
    for cell in planned['cells']:
        if cell['config'].get('producer')=='vault-component-v1':continue
        cell['allocationBreakdown']={'sutAndOneoffs':{'millicpus':3500,'memoryBytes':7*1024**3},
            'driverK6':{'millicpus':500,'memoryBytes':1024**3},'hostV8':{'heapMiB':1024},
            'hostRss':'SEPARATELY_OBSERVED_NOT_HEAP_BOUNDED','generatorHeadroom':'UNMEASURED_UNLESS_RETAINED'}
    return planned


def batch_run(spec_file, directory, payload_root):
    import experiment_batch as batch
    spec=a.document(spec_file);planned=local_batch_plan(spec,payload_root)
    cancelled=False
    def cancel(signum, frame):
        nonlocal cancelled
        cancelled=True
    old={s:signal.signal(s,cancel) for s in (signal.SIGINT,signal.SIGTERM)}
    try:
        with batch.local_custody(directory,spec) as ledger:
            root=ledger.directory
            write(root/'batch.json',spec)
            write(root/'batch-payload.json',{'root':str(Path(payload_root).resolve()),'specSha256':batch.digest(spec)})
            write(root/'batch-plan.json',planned)
            def perform(cell,ticket):
                # Each cell is a process. Adapter process-global state is never
                # shared by concurrent cells in coordinator threads.
                ticket_file=root/(cell['id']+'.ticket.json');batch.write(ticket_file,ticket)
                config_file=root/(cell['id']+'.config.json');write(config_file,cell['config'])
                child_env={**os.environ,'M7_BATCH_RESERVATION':str(ticket_file)}
                point=root/cell['id']
                with (root/(cell['id']+'.private.log')).open('xb') as output:
                    child=subprocess.Popen([sys.executable,'-B',str(HERE/'runner.py'),'_batch-cell',str(config_file),str(point)],env=child_env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                    a.job_record(root/(cell['id']+'.job.json'),child,ticket['nonce'],group=True)
                    # Existing independent guard owns finite effects/cleanup.
                    # Reserve remains if child or guard cannot prove absence.
                    try:child.wait(timeout=cell['workSeconds']+cell['cleanupSeconds']+20)
                    except subprocess.TimeoutExpired:
                        stop_stage(root/(cell['id']+'.job.json'),ticket['nonce'])
                        child.wait(timeout=12)
                result=a.document(point/'result.json') if (point/'result.json').exists() else {'status':'FAILED_PARTIAL'}
                require((point/'cleanup.json').exists() and a.document(point/'cleanup.json')['status']=='ABSENT','M7_BATCH_ABSENCE_REQUIRED')
                until=time.monotonic()+10
                while guard_alive(point) and time.monotonic()<until:time.sleep(.05)
                require(not guard_alive(point),'M7_BATCH_GUARD_PENDING')
                require(not batch.group_members(child.pid),'M7_BATCH_CELL_GROUP_REMAINS')
                if (point/'guard-job.json').exists():
                    require(not batch.group_members(a.document(point/'guard-job.json')['pid']),'M7_BATCH_GUARD_GROUP_REMAINS')
                lock=root/(cell['id']+'.heap.lock')
                if lock.exists():
                    with lock.open('r+') as stream:
                        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        require(not stream.read(),'M7_BATCH_HEAP_STALE')
                return result,{'status':'ABSENT','id':ticket['id'],'nonce':ticket['nonce']}
            result=batch.schedule(spec,ledger,perform,lambda:cancelled,
                changed=lambda:local_batch_plan(spec,payload_root))
            write(root/'batch-result.json',result)
            return result
    finally:
        for signum,handler in old.items():signal.signal(signum,handler)


def batch_cell(config, directory):
    # Private entrypoint: no arbitrary lock bypass without aggregate custody.
    from experiment_batch import child_lock, read
    require(child_lock() is not None,'M7_BATCH_TICKET_REQUIRED')
    ticket=read(os.environ['M7_BATCH_RESERVATION'])
    limits=a.document(config)
    require(time.time()+limits['workSeconds']+limits['cleanupSeconds']<=ticket['cleanupAt'],
            'M7_BATCH_CELL_DEADLINE')
    root=Path(directory).resolve()
    try:
        if limits.get('producer')=='vault-component-v1':
            import vault_component
            return vault_component.execute(config,root)
        prepare(config,root)
        return execute(root)
    finally:
        if (root/'execution.json').exists() and not (root/'cleanup.json').exists():
            cleanup(root,'BATCH_CELL_EXIT')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('identity')
    project=sub.add_parser('project');project.add_argument('config');project.add_argument('--remote-overlay');project.add_argument('--source-acceptance')
    for mode in ('batch-plan','batch-run'):
        command=sub.add_parser(mode);command.add_argument('config');command.add_argument('--payload-root',required=True)
        if mode=='batch-run':command.add_argument('directory')
    cell=sub.add_parser('_batch-cell');cell.add_argument('config');cell.add_argument('directory')
    prep = sub.add_parser('prepare');prep.add_argument('config');prep.add_argument('directory')
    for name in ('execute', 'rehearse', 'result', 'down', '_guard', 'batch-result'):
        sub.add_parser(name).add_argument('directory')
    args = parser.parse_args()
    if args.action == 'project':
        import run_configuration as rc
        config=a.document(args.config)
        acceptance=a.document(args.source_acceptance) if args.source_acceptance else None
        value=rc.remote_projection(config,a.document(args.remote_overlay),acceptance) if args.remote_overlay else rc.resolve(config,acceptance)
        return print(json.dumps(value,indent=2))
    if args.action == 'batch-result':
        root=Path(args.directory).resolve();spec=a.document(root/'batch.json')
        retained=a.document(root/'batch-result.json') if (root/'batch-result.json').exists() else {'batch':spec['id'],'cells':{},'capacityAcceptance':'NOT_GRANTED'}
        for cell in spec['cells']:
            file=root/cell['id']/'result.json'
            if file.exists():retained['cells'][cell['id']]=a.document(file)
            elif cell['id'] not in retained['cells']:retained['cells'][cell['id']]={'status':'UNMEASURED'}
        return print(json.dumps(retained,indent=2))
    if args.action == '_batch-cell':return batch_cell(args.config,args.directory)
    if args.action == 'batch-plan':
        return print(json.dumps(local_batch_plan(a.document(args.config),args.payload_root),indent=2))
    if args.action == 'batch-run':return batch_run(args.config,args.directory,args.payload_root)
    if args.action == 'identity':
        identity = a.instrument()
        return print(json.dumps({'helperHead': identity['commit'], 'helperInstrument': identity['sha256']}, indent=2))
    if args.action == 'prepare':
        return prepare(args.config, args.directory)
    root = Path(args.directory).resolve()
    if args.action in ('execute', 'rehearse'):return execute(root, args.action == 'rehearse')
    if args.action == '_guard':return guard(root)
    if args.action == 'down':return cleanup(root, 'EXPLICIT_CLEANUP')
    print(json.dumps({**a.document(root / 'result.json'), 'partial': partial(root)}, indent=2))


if __name__ == '__main__':
    os.umask(0o077)
    try:main()
    except Exception as error:
        print(code(error), file=sys.stderr)
        sys.exit(1)
