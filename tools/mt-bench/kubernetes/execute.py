"""Operator execution of unchanged M7 work/oracles through Kubernetes transport."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading
from urllib.parse import urlparse
from types import SimpleNamespace
import kube_adapter as k
import workload_runtime


def environment(c, d):
    env = {key: value for key, value in os.environ.items() if key not in ('NODE_PATH', 'NODE_OPTIONS', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'M7_PROBE_LEDGER')}
    env.update(M7_RUN_PURPOSE='discovery', M7_GENERATOR_ROOT=c['driver']['dependencies'],
               M7_COMPLETION_SOURCE=json.dumps(c['completion']), K8S_ADAPTER=str(k.HERE / 'adapter.py'),
               K8S_PYTHON=sys.executable, K8S_RUN_DIRECTORY=str(d))
    env.update(workload_runtime.workload_inputs.probe_ledger_env(c.get('workload', {})))
    return env


def actor(c):
    driver = c['driver']
    k.need(driver['hostId'] == c['observer']['hostId'], 'NATIVE_ACTORS_REQUIRE_SAME_HOST')
    k.need(all(key in driver for key in ('node','nodeSha256','dependencies','coreRepository','packageSha256','lockSha256','nodeModules')),'DRIVER_INPUTS_REQUIRED','UNMEASURED')
    for name in ('node', 'k6'):
        if name in driver:
            k.need(Path(driver[name]).is_absolute() and k.digest(driver[name]) == driver[name + 'Sha256'], 'DRIVER_TOOL_CHANGED')
    deps = Path(driver['dependencies'])
    for file,field in [('package.json','packageSha256'),('package-lock.json','lockSha256')]:
        source=subprocess.run(['git','-C',driver['coreRepository'],'show',c['pins']['pair']['core']+':'+file],capture_output=True,timeout=10)
        k.need(source.returncode==0 and k.hashlib.sha256(source.stdout).hexdigest()==driver[field],'SOURCE_DEPENDENCY_LOCK_CHANGED')
    k.need(k.digest(deps / 'package.json') == driver['packageSha256'] and k.digest(deps / 'package-lock.json') == driver['lockSha256'], 'DEPENDENCY_LOCK_CHANGED')
    tree = k.dependency_reuse.tree(deps / 'node_modules')
    k.need(tree == driver['nodeModules'], 'DEPENDENCY_TREE_CHANGED')
    cgroup = Path('/proc/self/cgroup').read_text().strip()
    relative = cgroup.splitlines()[0].split(':', 2)[-1]
    root = Path('/sys/fs/cgroup') / relative.lstrip('/')
    limits = {name: (root / name).read_text().strip() if (root / name).is_file() else 'UNMEASURED' for name in ('cpu.max', 'memory.max', 'memory.swap.max', 'cpu.stat', 'memory.current', 'memory.peak', 'memory.events')}
    scope = finite_scope(c, limits)
    return {'hostId': driver['hostId'], 'sharedHost': True, 'dependencies': str(deps), 'nodeModules': tree,
            'localCgroup': cgroup, 'resourceReadback': limits, 'requestedResources': driver['resources'],
            'budgetEnforcement': scope}


def native_resource_observation(out, initial):
    """Retain combined driver/observer lifetime peaks before their scope exits."""
    current=Path('/proc/self/cgroup').read_text().strip()
    k.need(current==initial['localCgroup'],'NATIVE_CGROUP_CHANGED')
    root=Path('/sys/fs/cgroup')/current.splitlines()[0].split(':',2)[-1].lstrip('/')
    values={}
    for name in ('cpu.stat','cpu.max','memory.current','memory.peak','memory.events','memory.max','memory.swap.max'):
        try:values[name]=(root/name).read_text().strip()
        except OSError:values[name]='UNMEASURED'
    k.write(Path(out)/'native-resources-final.json',dict(localCgroup=current,readback=values,
        scope='combined native driver/controller/observer cgroup lifetime peak; no split or phase peak inferred'))


def finite_scope(c, limits):
    """Native driver/controller/observer children inherit this finite scope."""
    cpu = limits.get('cpu.max','').split()
    memory = limits.get('memory.max','')
    ceiling_cpu = sum(c[name]['resources']['millicpus'] for name in ('driver','observer'))
    ceiling_memory = sum(c[name]['resources']['memoryBytes'] for name in ('driver','observer'))
    k.need(len(cpu)==2 and all(v.isdigit() and int(v)>0 for v in cpu) and memory.isdigit() and int(memory)>0 and limits.get('memory.swap.max')=='0','FINITE_ACTOR_SCOPE_REQUIRED','UNMEASURED')
    k.need(int(cpu[0])*1000<=ceiling_cpu*int(cpu[1]) and int(memory)<=ceiling_memory,'ACTOR_SCOPE_EXCEEDS_BUDGET')
    return {'scope':'combined native driver and observer, inherited by children','cpuMax':limits['cpu.max'],'memoryMax':int(memory),'swapMax':0,
            'declaredCombined':{'millicpus':ceiling_cpu,'memoryBytes':ceiling_memory}}


def wait_observed(process, seconds, failures):
    """Stop waiting for an owned worker as soon as its parallel observation fails."""
    until = time.monotonic() + seconds
    while True:
        if failures:
            raise failures[0]
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, seconds)
        try:
            return process.wait(timeout=min(remaining, .5))
        except subprocess.TimeoutExpired:
            continue


def finite(c, argv, *, env=None, data=None, output=None, error_output=None, seconds=120,
           failures=None, outcome=None, failure_stdout=None):
    """coreutils timeout survives loss of its parent and bounds the native child.

    Only this owned process group is signalled. Cluster cleanup stays HUMAN.
    """
    bound = min(seconds, k.deadline(c))
    argv = ['/usr/bin/timeout', '--signal=TERM', '--kill-after=3s', str(max(.01, bound)) + 's', *map(str, argv)]
    process = subprocess.Popen(argv, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                               stdout=output or subprocess.PIPE, stderr=error_output or output or subprocess.PIPE,
                               env=env, start_new_session=True)
    try:
        if failures is None:
            out, err = process.communicate(input=data, timeout=bound + 5)
        else:
            # Stream both descriptors directly into retained files while polling for failures.
            k.need(output is not None and data is None, 'WORKER_CAPTURE_REQUIRED')
            wait_observed(process, bound + 5, failures)
            out, err = None, None
        if process.returncode != 0:
            code = (err or b'').decode(errors='replace').strip()
            if failure_stdout is not None:
                failure_stdout(code, out or b'')
            if k.re.fullmatch(r'(K8S|M7)_[A-Z_]+', code):
                raise k.Refused(code, 'UNMEASURED' if 'UNMEASURED' in code else 'FAIL')
            raise k.Refused('K8S_NATIVE_PROCESS_FAILED', 'UNMEASURED')
        k.deadline(c)
        return out
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
        if outcome is not None:
            k.write(outcome, {'returncode': process.returncode, 'boundSeconds': bound,
                             'scope': 'owned native process group; no mutation replay'})


def native_k6(c, out, script, *, env, seconds, failures=None, shard=None, options=(), trace_bytes=None):
    suffix = '' if shard is None else f'-{shard}'
    eventlog = out / ('k6.log' if shard is None else f'k6-shard-{shard}.log')
    native = out / f'k6-native{suffix}.log'
    summary = out / f'k6-summary{suffix}.json'
    # k6 buffers the file log backend and can lose it on process-group TERM.
    # Stream the logger to its own descriptor so terminal stdout stays separate.
    argv = [c['driver']['k6'], 'run', '--quiet', '--log-output=stderr',
            '--summary-export', summary, *options, script]
    if trace_bytes is not None:
        argv[:0] = ['/usr/bin/prlimit', f'--fsize={trace_bytes}:{trace_bytes}', '--']
    def private_log_opener(path, flags):
        return os.open(path, flags, 0o600)
    with open(eventlog, 'xb', opener=private_log_opener) as events, open(native, 'xb', opener=private_log_opener) as output:
        finite(c, argv, env=env, output=output, error_output=events, seconds=seconds, failures=failures,
               outcome=out / f'k6-process{suffix}.json')


def configured_load(d, out, c, env, setup):
    """Use the local generator, wrapper, roster splitter and accounting natively."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import driver_shards
    import driver_vu_diagnostic as driver
    m = workload_runtime.driver_manifest(c)
    plans = driver.expected_plans(m)
    cfg = m['cadence']['driverPlan']
    k.need(k.digest(d / driver.SCRIPT) == k.document(d / 'packet.json')['workload']['driverWrapperSha256'],
           'DRIVER_WRAPPER_CHANGED')
    n = len(plans)
    rows = (driver_shards.plan(c['tenants'], m['cadence']['hotFactor'], m['cadence'].get('offeredRps'), n)
            if n > 1 else [dict(index=0, start=0, end=c['tenants'], tenants=c['tenants'],
                               hotFactor=m['cadence']['hotFactor'], offeredRps=m['cadence'].get('offeredRps'))])
    folder = driver_shards.write_rosters(out / 'shards', roster(c), rows)
    if n > 1:
        k.write(out / 'k6-shard-plan.json', {'shards': rows})
    k.write(out / 'driver-plans.json', {'plans': plans, 'transport': 'kubernetes-native',
                                      'manifest': m, 'pooledPercentiles': 'UNMEASURED'})
    errors = []
    def run(row):
        index = row['index']; suffix = '-' + str(index) if n > 1 else ''
        local = dict(env, **driver.configured_environment(m, index),
                     TENANTS_FILE=str(folder / ('tenants-%d.private.json' % index)),
                     HOT_FACTOR=str(row['hotFactor']), SHAPES=','.join(cfg['scenarios']))
        if row['offeredRps'] is not None:
            local['OFFERED_RPS'] = str(row['offeredRps'])
        options = ['--address', '127.0.0.1:0']
        if cfg['observer'] == 'scheduling-v1':
            options += ['--out', 'csv=' + str(out / ('k6-scheduling' + suffix + '.csv.gz'))]
        resultfile = out / ('k6-process' + suffix + '.json')
        try:
            native_k6(c, out, d / driver.SCRIPT, env=local,
                      seconds=c['workload']['loadSeconds'] + setup +
                              max(r['gracefulStopSeconds'] for r in cfg['scenarios'].values()) + 5,
                      shard=index if n > 1 else None, options=options, trace_bytes=cfg['maxTraceBytes'])
        finally:
            rc = k.document(resultfile)['returncode'] if resultfile.exists() else None
            if n > 1:
                (out / ('k6-shard-%d.rc' % index)).write_text(str(rc) + '\n')
    with ThreadPoolExecutor(max_workers=n) as pool:
        for future in as_completed([pool.submit(run, row) for row in rows]):
            try: future.result()
            except Exception as error: errors.append(error)
    if n > 1:
        driver_shards.collect(out, rows)
    try:
        observation = driver.retain(d, m)
    except Exception:
        k.write(out / 'driver-partial.json', driver.partial_configured(d, m))
        if errors: raise errors[0]
        raise
    k.write(out / 'driver-accounting.json', observation)
    if errors: raise errors[0]
    return observation


def roster(c):
    if 'primerOutput' in c:
        import primer
        d = Path(c['primerOutput']).parent
        primer.require_roster(d, c, k.active_baseline(d))
    tenants = k.document(c['tenantsFile'])
    k.need(isinstance(tenants, list) and len(tenants) == c['tenants'] and len({r['id'] for r in tenants}) == len(tenants), 'TENANT_ROSTER')
    k.evaluator_progress.validate_ids([r['id'] for r in tenants])
    k.need(all(isinstance(r.get('token'), str) and r['token'] and isinstance(r.get('host'), str) and r['host'].endswith('.test') for r in tenants), 'SYNTHETIC_TENANTS_REQUIRED')
    return tenants


def completion(c):
    b = c.get('completion', {}).get('binding', {})
    k.need(b.get('kind') == 'evaluator-work-v2' and b.get('pair') == c['pins']['pair'] and b.get('imageId') == c['pins']['appImageId'] and b.get('instrument') == c['pins']['instrument'], 'COMPLETION_SOURCE_CHANGED')


def progress_refusal(error):
    code = str(error)
    result = {'verdict':getattr(error, 'verdict', 'UNMEASURED'),
              'code':code if code == 'EVALUATOR_SCOPE_UNSAFE' or
                     k.re.fullmatch(r'(?:K8S|M7)_[A-Z0-9_]+', code) else 'K8S_PROGRESS_CAPTURE_FAILED',
              'errorType':type(error).__name__}
    if isinstance(error, k.evaluator_progress.Refused) and getattr(error, 'diagnostic', None):
        # The actual strict reader owns this bounded, allowlisted projection.
        result['diagnostic'] = error.diagnostic
    return result


def progress(d, c, objects, client, *, raw_output=None, until=None, warming=False):
    with k.observation_deadline(until):
        k.deadline(c)
        ids = [r['id'] for r in roster(c)]
        baseline = k.active_baseline(d)
        before = k.observe(c, objects, client, baseline)
        k.deadline(c)
        pod, container = k.selected_pod(c, before, 'evaluator')
        selected=c.get('workload',{}).get('evaluatorProgressBudget')
        policy=k.evaluator_progress.capture_policy(selected)
        helper = (k.M7 / 'evaluator-progress.cjs').read_text()
        response, response_path = {'captureStatus':'UNAVAILABLE'}, None
        if raw_output is not None:
            response_path = raw_output.with_name(raw_output.name.removesuffix('.private.jsonl')+'-response.json')
        def fetch(role, selected, queries, budget):
            prefix = 'const M7_PROGRESS_IDS=' + json.dumps(selected) + ';const M7_PROGRESS_QUERY_BUDGET=' + str(queries) + ';const M7_PROGRESS_BYTE_BUDGET=' + str(budget) + ';\n'
            def retain(raw, returncode, boundary='client-response-sink'):
                fd = os.open(raw_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                identity = before['pods'][pod]
                response.update(observedAt=time.time(), bytes=len(raw), sha256=k.digest(raw_output),
                    namespaceUid=before['namespace']['uid'], podUid=identity['uid'],
                    containerId=identity['containers'][container]['containerID'], pins=c['pins'], capturePolicy=policy,
                    captureStatus='BOUNDED_RETURNED_STDOUT', captureBoundary=boundary,
                    processReturnCode=returncode, transportSucceeded=returncode == 0)
                k.write(response_path, response)
            # ThreadPoolExecutor does not inherit the caller's ContextVars.
            with k.observation_deadline(until):
                k.deadline(c)
                raw = client.call(['exec', '-i', pod, '-c', container, '--', 'node', '-'],
                                  data=(prefix + helper).encode(), read=False, output_limit=budget,
                                  response_sink=retain if raw_output is not None else None)
                if raw_output is not None and response['captureStatus'] == 'UNAVAILABLE':
                    # Inert test transports can return without calling the sink.
                    k.need(isinstance(raw, bytes) and len(raw) <= budget, 'OBSERVATION_BOUND', 'UNMEASURED')
                    retain(raw, 0, boundary='caller-return')
                k.deadline(c)  # A late successful fetch cannot become a pass.
                return raw
        value, primary, post = None, None, None
        try:
            value = k.evaluator_progress.round_view(['evaluator'], ids, fetch, warming=warming, policy=policy)
        except BaseException as error:
            primary = error
        try:
            # Verify UID/container/source binding even when decoding refused.
            k.observe(c, objects, client, baseline)
            k.deadline(c)
        except BaseException as error:
            post = error
        if response_path is not None:
            response.update(postObservation='VERIFIED' if post is None else 'REFUSED',
                            responseRetained=raw_output.is_file(), sourceDecode='REFUSED' if
                            isinstance(primary, k.evaluator_progress.Refused) else 'UNMEASURED' if primary else 'PASS')
            if primary is not None: response['sourceRefusal'] = progress_refusal(primary)
            if post is not None: response['postRefusal'] = progress_refusal(post)
            k.write(response_path, response)
        if post is not None:
            if primary is not None: post.source_refusal = progress_refusal(primary)
            raise post
        if primary is not None: raise primary
        if selected is not None:value['capturePolicy']=policy
        return value


def retained_progress(d, out, c, objects, client, name, *, until=None, warming=False):
    raw = out/(name+'.private.jsonl')
    try:
        value = progress(d, c, objects, client, raw_output=raw, until=until, warming=warming)
    except Exception as error:
        evidence = {**progress_refusal(error), 'responseRetained':raw.is_file(), 'pins':c['pins']}
        if getattr(error, 'source_refusal', None): evidence['sourceRefusal'] = error.source_refusal
        k.write(out/(name+'-failure.json'), evidence)
        raise
    k.write(out/(name+'.json'), value)
    return value


def midpoint_signal(out, c, ids, refusal):
    """Midpoint is a recorded signal; only a hard outcome reason stops the driver."""
    import outcome_gate
    raw = out/'progress-midpoint.private.jsonl'
    try:
        point = outcome_gate.from_pages({'evaluator':raw.read_bytes()}) if raw.is_file() else None
        classification = outcome_gate.classify_point(point, ids, final=False, config=gate_config(c)) if point else None
    except Exception:
        classification = None
    decision = outcome_gate.midpoint_decision(classification)
    if gate_mode(c)['midpointStop'] == 'never' and decision['action'] == 'stop':
        decision = {**decision, 'action':'continue', 'configured':'midpointStop=never'}
    decision.update(rawRetained=raw.is_file(), instrument=outcome_gate.instrument(),
                    strictRefusal=None if refusal is None else progress_refusal(refusal),
                    classification=classification)
    k.write(out/'progress-midpoint-signal.json', decision)
    return decision


def gate_mode(c):
    value = dict(c.get('outcomeGate') or {})
    value.setdefault('midpointStop', 'hard')
    value.setdefault('catchup', True)
    k.need(set(value) <= {'midpointStop', 'deadlineMs', 'catchup'} and value['midpointStop'] in ('hard', 'never')
           and type(value['catchup']) is bool, 'OUTCOME_GATE_CONFIGURATION')
    return value


def gate_config(c):
    mode = gate_mode(c)
    return {'deadlineMs':mode['deadlineMs']} if 'deadlineMs' in mode else None



def stop_process(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)


def stop_evidence(d, out, c, objects, client, namespace_uid):
    """Early stop: retain raw final progress, then storage counts, before decoding."""
    receipt = {'version':1, 'scope':'raw-first capture after an early load stop; each step best effort and recorded'}
    if not (out/'progress-after.private.jsonl').exists():
        raw = out/'progress-stop.private.jsonl'
        try:
            k.write(out/'progress-stop.json', progress(d, c, objects, client, raw_output=raw))
            receipt['progress'] = {'verdict':'DECODED'}
        except Exception as error:
            receipt['progress'] = progress_refusal(error)
        receipt['progressRetained'] = raw.is_file()
    else:
        receipt['progress'] = 'TERMINAL_CAPTURE_PRESENT'
    if (out/'runid').is_file() and not (out/'storage-readback.json').exists():
        storage_after_progress_failure(d, out, c, objects, client, (out/'runid').read_text().strip(), namespace_uid)
    receipt['storage'] = k.document(out/'storage-readback.json').get('verdict') if (out/'storage-readback.json').is_file() else 'NOT_CAPTURED'
    k.write(out/'stop-evidence.json', receipt)
    return receipt


def warmup_counts(row):
    return (isinstance(row,dict) and type(row.get('attempts')) is type(row.get('refused403')) is type(row.get('elapsedMs')) is int
            and 0 <= row['refused403'] <= row['attempts'] and row['elapsedMs'] >= 0)


def access(d, c, objects, client):
    k.need(not (d / 'access.json').exists() and not (d / 'access-failure.json').exists(),
           'ACCESS_OUTPUT_EXISTS')
    phase = 'candidate-receipt'
    try:
        k.candidate.require(k, d, c)
        phase = 'verified-roster'
        tenants = roster(c)
        baseline = k.active_baseline(d)
        phase = 'before-observe'
        k.observe(c, objects, client, baseline)
        phase = 'native-actor-readback'
        actor(c)
        phase = 'node-witness'
        setup = c.get('accessSetupSeconds')
        raw = finite(c, [c['driver']['node'], k.HERE / 'access.cjs', c['tenantsFile'],
                        c['baseUrl'], c['driver']['dependencies'], *([setup] if setup else [])],
                     env=environment(c, d), seconds=60+(setup or 0))
        phase = 'witness-document'
        value = json.loads(raw)
        k.need(isinstance(value, dict), 'ACCESS_REPORT_INVALID', 'UNMEASURED')
        if setup is not None:
            warmup = value.get('warmup', {})
            witnesses = warmup.get('observations',[])
            # A socket that did not warm in the window is a recorded UNMEASURED
            # signal (the witness reports it per tenant); the report shape is still required.
            k.need(warmup.get('budgetMs') == setup*1000 and len(witnesses)==2 and
                   all(warmup_counts(row) and row.get('tenantIndex')==index and row.get('verdict') in ('CONNECTED','UNMEASURED')
                       for index,row in enumerate(witnesses)), 'ACCESS_REPORT_INVALID', 'UNMEASURED')
        phase = 'after-observe'
        k.observe(c, objects, client, baseline)
        phase = 'witness-roster'
        k.need(value.get('tenantRosterSize') == len(tenants) and
               value.get('witnessTenants') == [tenants[0]['id'], tenants[-1]['id']],
               'ACCESS_WITNESS_ROSTER_CHANGED')
        value.update(pins=c['pins'], namespaceUid=baseline['namespace']['uid'], context=c['context'])
        phase = 'publish'
        k.write(d / 'access.json', value)
        return value
    except Exception as error:
        try:
            k.write(d / 'access-failure.json', {'phase': phase, **k.failure_evidence(error)})
        except OSError:
            pass
        raise


def policy_assess(observations):
    k.need(isinstance(observations,list) and len(observations)==3,'POLICY_OBSERVATION_UNMEASURED','UNMEASURED')
    k.need(observations[0].get('outcome')==observations[2].get('outcome')=='connected','POLICY_POSITIVE_CONTROL_UNMEASURED','UNMEASURED')
    k.need(observations[1].get('outcome')!='connected','OPERATOR_PLANE_EXPOSED')
    k.need(observations[1].get('outcome')=='timeout','POLICY_REFUSAL_UNMEASURED','UNMEASURED')
    return {'verdict':'PASS','scope':'private admin TCP allowed/refused/allowed control on unchanged endpoints; no private admin API mutation'}


def policy(d, c, objects, client):
    k.candidate.require(k, d, c)
    k.need(not (d/'policy.json').exists(),'POLICY_OUTPUT_EXISTS')
    initial=k.active_baseline(d)
    before=k.observe(c,objects,client,initial)
    primer=[p for p in before['pods'].values() if p['workload']=='Job/primer' and p['containers'].get('done',{}).get('ready')]
    k.need(len(primer)==1,'POLICY_PRIMER_WAITING_REQUIRED','UNMEASURED')
    denied_pod,denied_container=k.selected_pod(c,before,'api')
    targets=[(primer[0]['name'],'done'),(denied_pod,denied_container),(primer[0]['name'],'done')]
    script="const net=require('node:net');let done=false;const finish=outcome=>{if(done)return;done=true;socket.destroy();console.log(JSON.stringify({outcome}));};const socket=net.connect({host:'admin',port:1342});socket.setTimeout(2000);socket.once('connect',()=>finish('connected'));socket.once('timeout',()=>finish('timeout'));socket.once('error',()=>finish('error'));"
    samples=[]
    for pod,container in targets:
        raw=client.call(['exec',pod,'-c',container,'--','node','-e',script],read=False)
        try:sample=json.loads(raw)
        except ValueError:raise k.Refused('K8S_POLICY_OBSERVATION_UNMEASURED','UNMEASURED')
        k.need(set(sample)=={'outcome'} and sample['outcome'] in ('connected','timeout','error'),'POLICY_OBSERVATION_UNMEASURED','UNMEASURED')
        samples.append({**sample,'podUid':before['pods'][pod]['uid'],'containerId':before['pods'][pod]['containers'][container]['containerID']})
    k.observe(c,objects,client,initial)
    result={**policy_assess(samples),'pins':c['pins'],'context':c['context'],'namespaceUid':initial['namespace']['uid'],'observations':samples,
            'adminServiceUid':before['objects'].get('Service/admin',{}).get('uid'),'capacityAcceptance':'NOT_GRANTED'}
    k.need(result['adminServiceUid'],'POLICY_TARGET_UNMEASURED','UNMEASURED')
    k.write(d/'policy.json',result)
    return result


def ordinary_load_window(c, log, started, ended):
    from demand_recovery import active_marker
    marker = active_marker(log)
    k.need(marker is not None and started <= marker / 1000 < ended,
           'SCENARIO_DEMAND_UNMEASURED', 'UNMEASURED')
    # Existing first-ordinary-request witness plus configured scenario duration;
    # never count JWT setup or graceful final drain as concurrent demand.
    return marker / 1000, min(ended, marker / 1000 + c['workload']['loadSeconds'])


def stage_runid(c, name):
    point = c.get('workload', {}).get('pointId')
    k.need(point is None or isinstance(point, str) and 1 <= len(point) <= 31 and k.NAME.fullmatch(point), 'WORKLOAD_POINT_ID')
    value = c['runId'] + ('-' + point if point else '') + '-' + name
    k.need(len(value) <= 100, 'RUN_MARKER')
    return value


def execute(d, c, objects, client, load=False, recovery=False):
    k.candidate.require(k, d, c)
    name = 'load' if load else 'recovery' if recovery else 'commission'
    out = d / name
    k.need(not out.exists(), 'STAGE_OUTPUT_EXISTS')
    if load:
        k.need('k6' in c['driver'] and 'k6Sha256' in c['driver'],'LOAD_INPUTS_REQUIRED','UNMEASURED')
    settings = workload_runtime.validate(c['workload'], k.need, c['tenants'])
    env = workload_runtime.environment(settings, environment(c, d), k.need)
    completion(c)
    tenants = roster(c)
    k.need(load or len(tenants) == 2, 'TINY_TWO_TENANTS')
    k.need(k.digest(d / 'probe.cjs') == k.document(d / 'packet.json')['probe']['kubernetesSha256'] and k.digest(d / 'workload.js') == k.document(d / 'packet.json')['workload']['adaptedSha256'], 'GENERATED_INPUT_CHANGED')
    if recovery:
        k.need(k.document(d / 'restart.json').get('status') == 'OBSERVED', 'RESTART_FIRST')
    baseline = k.active_baseline(d)
    before = k.observe(c, objects, client, baseline)
    readback = actor(c)
    out.mkdir(mode=0o700)
    k.write(out / 'before.json', before)
    k.write(out / 'driver.json', readback)
    import preload
    convergence = preload.run(d, out, c, objects, client, ids=[row['id'] for row in tenants],
                              collect=retained_progress) if load else None
    # preload-is-a-signal: a roster still warming at the end of the phase starts traffic. The
    # starting read keeps its strict decode; its typed warming refusal is retained as evidence
    # (progress-before-failure.json) and is not an entry condition. The outcome gate judges the
    # midpoint and the end of drain.
    warming_start = convergence is not None and convergence.get('status') == 'NOT_CONVERGED'
    try:
        initial = retained_progress(d, out, c, objects, client, 'progress-before', warming=warming_start,
                                    until=convergence['until'] if convergence is not None else None)
    except k.evaluator_progress.Refused as refused:
        if not warming_start or str(refused) not in ('M7_EVALUATOR_PROGRESS_ERROR', 'M7_EVALUATOR_PROGRESS_WARMING'):
            raise
        initial = None
    if convergence is not None:
        preload.fresh(out, c, initial, convergence)
    runid = stage_runid(c, name)
    (out / 'runid').write_text(runid)
    node = c['driver']['node']
    argv = [node, str(d / 'probe.cjs'), '--base', c['baseUrl'], '--tenants', c['tenantsFile'], '--runid', runid,
            '--per', '2', '--clients', str(settings['logicalPollingClients']), '--open', '5', '--window', str(settings['loadSeconds']),
            '--probeEvery', str(settings['probeEveryMs'] if load else 1000), '--restart', '0', '--evalTimeout', '120',
            '--out', str(out / 'probe.json'), '--signal', str(out / '.window')]
    setup = settings.get('setupSeconds', 310)
    if 'setupSeconds' in settings:
        argv += ['--setupSeconds', str(setup)]
    if not load:
        argv += ['--maxWrites', '2']
    # Unchanged stock probe, with only SQL transport and external restart changed.
    started = time.time()
    process = None
    load_started = load_ended = load_process_started = load_process_ended = None
    drain_started = None
    midpoint = None
    cancel = threading.Event()
    midpoint_failure = []
    def capture_midpoint():
        while not cancel.wait(.1):
            if (out / '.window').exists():
                break
        if cancel.wait(settings['loadSeconds'] / 2 if load else .5):
            return
        refusal = None
        try:
            retained_progress(d, out, c, objects, client, 'progress-midpoint')
        except Exception as error:
            refusal = error
        try:
            decision = midpoint_signal(out, c, [row['id'] for row in tenants], refusal)
        except Exception as error:
            midpoint_failure.append(refusal or error)
            return
        if decision['action'] == 'stop':
            midpoint_failure.append(refusal or k.Refused('M7_OUTCOME_MIDPOINT_HARD', 'FAIL'))
    log = (out / 'probe.log').open('xb')
    try:
        bound = k.deadline(c)
        process = subprocess.Popen(['/usr/bin/timeout', '--signal=TERM', '--kill-after=3s', str(bound) + 's', *argv],
                                   stdout=log, stderr=log, env=env, start_new_session=True)
        midpoint = threading.Thread(target=capture_midpoint, daemon=True)
        midpoint.start()
        if load:
            prime_until = min(started + setup, k.timestamp(c['deadlines']['workUntil']))
            while not (out / '.window').exists():
                k.need(process.poll() is None and time.time() < prime_until, 'PROBE_NOT_PRIMED', 'UNMEASURED')
                time.sleep(.2)
            # A native k6 already in an operator-owned finite resource scope.
            # No Docker network/volume assumption or new driver Pod is introduced.
            env.update(BASE_URL=c['baseUrl'], TENANTS_FILE=c['tenantsFile'], RUN_ID=runid, RUN_START=str(int(time.time() * 1000)),
                       DURATION=str(settings['loadSeconds']), ACCEL='1', HOT_FACTOR=str(settings.get('hotFactor', 1)), JWT_SETUP_CONCURRENCY=str(settings.get('jwtSetupConcurrency', 1)),
                       SHAPES='w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status')
            if 'setupSeconds' in settings:
                setup = int(prime_until - time.time())
                k.need(setup > 0, 'SETUP_WINDOW_EXHAUSTED', 'UNMEASURED')
                env['M7_SETUP_SECONDS'] = str(setup)
                env['M7_SETUP_UNTIL_MS'] = str(int(prime_until * 1000))
                k.write(out/'setup-window.json', {'configuredSeconds': settings['setupSeconds'],
                        'remainingSecondsAtDriverLaunch': setup, 'setupUntilUnixMs': int(prime_until * 1000)})
            load_process_started = time.time()
            if 'driverPlan' in settings:
                accounting = configured_load(d, out, c, env, setup)
                load_process_ended = time.time()
                phases = [s['phases'] for s in accounting['shards']]
                k.need(all('scheduleStartMs' in p and 'scheduleEndMs' in p for p in phases),
                       'SCENARIO_DEMAND_UNMEASURED', 'UNMEASURED')
                load_started = min(p['scheduleStartMs'] for p in phases) / 1000
                load_ended = min(load_process_ended, max(p['scheduleEndMs'] for p in phases) / 1000)
            else:
                native_k6(c, out, d / 'workload.js', env=env,
                          seconds=settings['loadSeconds'] + setup + 5, failures=midpoint_failure)
                load_process_ended = time.time()
                load_started, load_ended = ordinary_load_window(c, out / 'k6.log', load_process_started, load_process_ended)
            (out / '.restart').touch()
            drain_started = time.time()
        if load and 'drainSeconds' in settings:
            # The inherited oracle has a 120 s per-write lookback. Keep that scope explicit.
            requested = settings['drainSeconds']
            k.write(out / 'drain.json', {'requestedSeconds': requested, 'perWriteCollectorLimitSeconds': 120,
                    'maximumObservableSeconds': min(requested, 120),
                    'scope': 'PARTIAL' if requested > 120 else 'BOUNDED', 'allWriterDrain': 'UNMEASURED'})
            try:
                wait_observed(process, min(requested, k.deadline(c)), midpoint_failure)
            except subprocess.TimeoutExpired:
                raise k.Refused('K8S_PROBE_DRAIN_WINDOW_EXHAUSTED', 'UNMEASURED') from None
        else:
            wait_observed(process, k.deadline(c), midpoint_failure)
        k.need(process.returncode == 0, 'PROBE_FAILED', 'UNMEASURED')
        writers_joined_ns = time.monotonic_ns()  # driver and probe have both exited
        midpoint.join(timeout=min(60, k.deadline(c)))
        if midpoint_failure:
            raise midpoint_failure[0]
        k.need(not midpoint.is_alive() and ((out / 'progress-midpoint.json').is_file() or
               (out / 'progress-midpoint-signal.json').is_file()), 'MIDPOINT_UNMEASURED', 'UNMEASURED')
        k.write(out / 'after.json', k.observe(c, objects, client, baseline))
        k.write(out / 'window.json', {'startedAt': started, 'endedAt': time.time(), 'loadStartedAt': load_started,
                                     'loadEndedAt': load_ended, 'loadProcessStartedAt': load_process_started,
                                     'loadProcessEndedAt': load_process_ended,
                                     'loadWindowBasis': 'first ordinary scenario request through configured duration capped at native exit; JWT setup and final drain excluded',
                                     'runId': runid, 'pins': c['pins'],
                                     'context': c['context'], 'namespaceUid': baseline['namespace']['uid']})
        if load and 'drainSeconds' in settings and gate_mode(c)['catchup']:
            # All-tenant fixed-floor catch-up: storage floor vs completed evaluation.
            import catchup
            catchup.run(d, out, c, objects, client, [row['id'] for row in tenants],
                        writers_joined_ns=writers_joined_ns, drain_started=drain_started)
        terminal_progress(d, out, c, objects, client, runid, load, baseline['namespace']['uid'])
        return assess_stage(d, out, c, objects, client)
    except Exception as error:
        k.write(out / 'failure.json', {'verdict': getattr(error, 'verdict', 'UNMEASURED'), 'code': str(error) if str(error) == 'EVALUATOR_SCOPE_UNSAFE' or str(error).startswith(('K8S_', 'M7_')) else 'K8S_STAGE_FAILED', 'capacityAcceptance': 'NOT_GRANTED'})
        if load and not (out / 'result.json').exists():
            cancel.set()
            stop_process(process)
            try:
                stop_evidence(d, out, c, objects, client, baseline['namespace']['uid'])
            except Exception as secondary:
                k.write(out / 'stop-evidence.json', {'version':1, 'code':'K8S_STOP_EVIDENCE_REFUSED',
                        'errorType':type(secondary).__name__})
        raise
    finally:
        cancel.set()
        stop_process(process)
        log.close()


def terminal_progress(d, out, c, objects, client, runid, load, namespace_uid):
    raw = out / 'progress-after.private.jsonl'
    try:
        k.write(out / 'progress-after.json', progress(d, c, objects, client, raw_output=raw))
    except (k.Refused, k.evaluator_progress.Refused) as error:
        evidence = {'verdict':error.verdict, 'code':str(error), 'responseRetained':raw.is_file(),
                    'namespaceUid':namespace_uid, 'pins':c['pins']}
        if diagnostic := getattr(error,'diagnostic',None):
            evidence['diagnostic'] = diagnostic  # Bounded, allowlisted row projection from round_view.
        if getattr(error, 'source_refusal', None):
            evidence['sourceRefusal'] = error.source_refusal
        k.write(out / 'progress-after-failure.json', evidence)
        if load:
            storage_after_progress_failure(d, out, c, objects, client, runid, namespace_uid)
        raise


def storage_after_progress_failure(d, out, c, objects, client, runid, namespace_uid):
    receipt = {'verdict':'UNMEASURED', 'runId':runid, 'namespaceUid':namespace_uid, 'pins':c['pins']}
    try:
        k.deadline(c)
        values = k.stored(d, c, objects, runid, client)
        tenants = {row['id'] for row in roster(c)}
        k.need(set(values)<=tenants and all(set(rows)<={'entries','devicestatus','treatments','probe'} and
               all(type(n) is int and n>=0 for n in rows.values()) for rows in values.values()), 'STORAGE_ROSTER_CHANGED')
        counts = out / 'stored-counts.json'
        k.write(counts, values)
        receipt.update(verdict='OBSERVED', countsSha256=k.digest(counts))
    except Exception as error:
        code = str(error)
        receipt['code'] = code if isinstance(error,k.Refused) else 'K8S_STORAGE_OBSERVATION_UNMEASURED'
    k.write(out / 'storage-readback.json', receipt)


def semantic(c, out, *, run=finite):
    tenants = roster(c)
    value = json.loads(run(c, [c['driver']['node'], k.HERE / 'claims.cjs', str(k.M7 / 'completed-oracle.cjs')],
                           data=json.dumps({'completion': c['completion'], 'probe': k.document(out / 'probe.json'),
                                            'tenants': [{'id': r['id']} for r in tenants], 'clients': c['workload']['logicalPollingClients']}).encode(), seconds=30))
    k.need(value.get('verdict') == 'PASS', 'CLINICAL_UNMEASURED', 'UNMEASURED')
    return value


def accepted_writes(out, c, values, metrics=None):
    tenants = roster(c)
    runid = (out / 'runid').read_text().strip()
    # Use the original count reducer, including missing ACK and uncertainty rules.
    if out.name in ('commission', 'recovery'):
        metrics = {'writes_ok': {'count': 0}}
        metrics.update({'writes_ok{kind:' + kind + '}': {'count': 0} for kind in ('entries', 'devicestatus', 'treatments')})
        metrics.update({name + '{tenant:' + t['id'] + '}': {'count': 0} for t in tenants for name in ('writes_ok', 'writes_uncertain')})
    else:
        k.need((out / 'k6-summary.json').is_file(), 'ACCEPTED_WRITE_UNMEASURED', 'UNMEASURED')
        if metrics is None:
            metrics = k.document(out / 'k6-summary.json').get('metrics', {})
    # discovery_counts requires the canonical private roster path. A private,
    # temporary view supplies this path without changing the runner's files.
    view = out / 'oracle-input'
    view.mkdir(mode=0o700, exist_ok=True)
    k.write(view / 'tenants.private.json', tenants)
    facade = SimpleNamespace(document=k.document, write=k.write, stored=lambda *_: values)
    counts, known = k.discovery_counts.observe(facade, view, out, runid, metrics,
                                               probe_ledger=c.get('workload', {}).get('probeLedger'))
    k.need(known, 'ACCEPTED_WRITE_UNMEASURED', 'UNMEASURED')
    k.need(counts.get('uncertain') == 0 and all(row['accepted'] == row['stored'] for row in counts['rows']),
           'WORKLOAD_WRITE_UNCERTAIN', 'UNMEASURED')
    ledger = k.document(out / 'probe-accounting.json')
    k.need(sum(r['accepted'] for r in ledger['byTenant'].values()) > 0 and all(r['uncertain'] == r['refused'] == r['pending'] == 0 for r in ledger['byTenant'].values()), 'ACCEPTED_WRITE_UNMEASURED', 'UNMEASURED')
    return counts


def load_checks(out, c=None):
    """Join the original M7 HTTP/offered-work reducers."""
    import http_accounting
    metrics = k.document(out / 'k6-summary.json').get('metrics', {})
    http = http_accounting.assess(metrics)
    value = {'http': http}
    if c and 'driverPlan' in c.get('workload', {}):
        import driver_vu_diagnostic as driver
        measured = driver.retain(out.parent, workload_runtime.driver_manifest(c))
        value['configuredDriver'] = measured
        k.need(measured['offeredWorkVerdict'] == 'PASS', 'DRIVER_OFFERED_WORK_INCOMPLETE',
               'FAIL' if measured['offeredWorkVerdict'] == 'FAIL' else 'UNMEASURED')
    k.write(out / 'load-functional.json', value)
    k.need(all(http['shapes'][shape]['attempts'] > 0 for shape in ('jwt_setup', *http_accounting.SHAPES)),
           'SCENARIO_SHAPE_UNMEASURED', 'UNMEASURED')
    k.need(http['httpVerdict'] == 'PASS' and all(row['httpVerdict'] == 'PASS' for row in http['shapes'].values()),
           'SCENARIO_HTTP_FAILED', 'FAIL' if http['httpVerdict'] == 'FAIL' else 'UNMEASURED')
    k.need(http['offeredWorkVerdict'] == 'PASS', 'OFFERED_WORK_INCOMPLETE',
           'FAIL' if http['offeredWorkVerdict'] == 'FAIL' else 'UNMEASURED')
    return value


def assess_stage(d, out, c, objects, client):
    completion(c)
    tenants = roster(c)
    probe = k.document(out / 'probe.json')
    k.need('completedOutput' in probe and probe['completedOutput'].get('witnesses'), 'CLINICAL_UNMEASURED', 'UNMEASURED')
    runid = (out / 'runid').read_text().strip()
    values = k.stored(d, c, objects, runid, client)
    # The original count reducer validates the entire probe ledger/roster first.
    counts = accepted_writes(out, c, values)
    from workloads.reduce import witness_coverage
    coverage = witness_coverage(probe, k.document(out / 'probe-accounting.json'))
    k.need(coverage['verdict'] == 'PASS', 'CLINICAL_WITNESS_COVERAGE',
           'FAIL' if coverage['verdict'] == 'FAIL' else 'UNMEASURED')
    clinical = {**semantic(c, out), 'coverage': coverage}
    frames = k.viewer_plan.check({'tenants': len(tenants), 'cadence': {'logicalPollingClients': c['workload']['logicalPollingClients']}}, tenants, probe,
                                 k.document(out / 'fanout.json')['probeWrites']['byTenant'])
    k.need(frames['verdict'] == 'PASS' or c['workload']['logicalPollingClients'] == 0 and
           frames['verdict'] == 'NOT_EXERCISED', 'CLIENT_FRAME_UNMEASURED', 'UNMEASURED')
    names = [name for name in ('progress-before', 'progress-midpoint', 'progress-after') if (out / (name + '.json')).is_file()]
    k.need(names[0] == 'progress-before' and names[-1] == 'progress-after', 'EVALUATOR_PROGRESS_BOOKENDS', 'UNMEASURED')
    rounds = [k.document(out / (name + '.json')) for name in names]
    # Keep existing progress assessment separate from durable clinical proof.
    selected=c.get('workload',{}).get('evaluatorProgressBudget')
    policy=k.evaluator_progress.capture_policy(selected)
    k.need(all(row.get('capturePolicy')==(policy if selected is not None else None) for row in rounds),
           'EVALUATOR_PROGRESS_BUDGET_CHANGED')
    # A midpoint is a signal: when only its signal was retained, the strict
    # counter/foreign/reset/work checks run over the two bookends.
    strict = rounds if len(rounds) == 3 else [rounds[0], rounds[-1], rounds[-1]]
    progress = k.evaluator_progress.assess(strict, [r['id'] for r in tenants], 'load',policy=policy,
                                           failure_policy=k.evaluator_progress.OUTCOME_FAILURE_POLICY)
    import outcome_gate
    outcome = outcome_gate.judge_kubernetes_load(out, [r['id'] for r in tenants], config=gate_config(c),
                                                 attribution={'pins':c['pins'], 'runId':runid})
    k.write(out / 'outcome-gate.json', outcome)
    functional = load_checks(out, c) if out.name == 'load' else 'NOT_SELECTED'
    summary = {'version': 1, 'verdict': 'OBSERVED', 'runId': runid, 'pins': c['pins'], 'storedWrites': counts,
               'clinical': clinical, 'frames': frames, 'evaluatorProgress': progress,
               'outcomeGate': {'verdict':outcome['verdict'], 'instrument':outcome['instrument'],
                               'components':{name:{'verdict':row['verdict'], 'codes':row.get('codes', [])}
                                             for name, row in outcome['components'].items()}},
               'httpLatencyAllShards': outcome_gate.http_latency(out) if out.name == 'load' else 'NOT_SELECTED',
               'loadFunctionalChecks': functional,
               'authority': 'UNMEASURED until access.json', 'performance': 'signals only; no promotion threshold', 'capacityAcceptance': 'NOT_GRANTED'}
    k.write(out / 'result.json', summary)
    k.need(outcome['verdict'] != 'FAIL', 'OUTCOME_GATE_FAIL', 'FAIL')
    return summary


def assess(d, c, objects, client):
    k.candidate.require(k, d, c)
    result = {name: assess_stage(d, d / name, c, objects, client) for name in ('commission','recovery','load') if (d / name).is_dir()}
    k.need(result, 'AUTHORITY_UNMEASURED', 'UNMEASURED')
    access_result, policy_result = authority(d, c)
    value = {'version': 1, 'verdict': 'OBSERVED_COMMISSIONING', 'stages': result, 'authority': access_result,
             'privateAdminPolicy':policy_result,
             'restart': 'UNMEASURED until separate owned role restart and independent fixture continuity', 'persistentRecovery': 'UNMEASURED',
             'capacityAcceptance': 'NOT_GRANTED', 'pins': c['pins']}
    k.write(d / 'qualification.json', value)
    return value


def authority(d, c):
    access_file = d / 'access.json'
    k.need(access_file.is_file(), 'AUTHORITY_UNMEASURED', 'UNMEASURED')
    access_result = k.document(access_file)
    # UNMEASURED (socket not observable) continues with the signal recorded; only a
    # measured isolation or authorization failure refuses here.
    k.need(access_result.get('verdict') in ('PASS', 'UNMEASURED') and access_result.get('crossTenantChecks') == 2, 'AUTHORITY_REFUSED')
    k.need(access_result.get('pins')==c['pins'] and access_result.get('context')==c['context'] and access_result.get('namespaceUid')==k.active_baseline(d)['namespace']['uid'],'AUTHORITY_SOURCE_CHANGED')
    k.need((d/'policy.json').is_file(),'POLICY_UNMEASURED','UNMEASURED')
    policy_result=k.document(d/'policy.json')
    k.need(policy_result.get('pins')==c['pins'] and policy_result.get('context')==c['context'] and policy_result.get('namespaceUid')==k.active_baseline(d)['namespace']['uid'],'POLICY_SOURCE_CHANGED')
    policy_assess(policy_result.get('observations'))
    return access_result, policy_result


def restart(d, c, objects, client, role):
    k.need(not (d / 'restart.json').exists(), 'RESTART_OUTPUT_EXISTS')
    k.need((d / 'commission/result.json').is_file() and (d / 'access.json').is_file(), 'COMMISSION_FIRST')
    initial = k.document(d / 'observation.initial.json')
    before = k.observe(c, objects, client, initial)
    pod, container = k.selected_pod(c, before, role)
    # The main source-owned Node role must be PID1. Refuse a changed entrypoint;
    # never select a process by substring or kill the whole cohort Pod.
    script = "const fs=require('fs');const a=fs.readFileSync('/proc/1/cmdline','utf8').split('\\0').filter(Boolean);if(a.length!==3||!a[1].endsWith('deploy/multitenant/entrypoint.js')||a[2]!==process.argv[1])throw Error('K8S_ROLE_PID1_MISMATCH');process.kill(1,'SIGTERM');"
    record = {'role': role, 'pod': pod, 'container': container, 'before': before, 'startedAt': time.time(), 'status': 'ATTEMPTED',
              'independentTenantContinuity': 'UNMEASURED; use a separately owned fixture probe spanning this window', 'persistentRecovery': 'NOT_EXERCISED'}
    k.write(d / 'restart.json', record)
    client.call(['exec', pod, '-c', container, '--', 'node', '-e', script, role], read=False)
    # Observe one exact restart. Temporary non-readiness is retained, never a
    # hidden transport retry or application write retry.
    until = min(time.time() + 90, k.timestamp(c['deadlines']['workUntil']))
    refusals = []
    while time.time() < until:
        try:
            after = k.observe(c, objects, client, initial, restarted_role=role)
            record.update(after=after, endedAt=time.time(), status='OBSERVED', readinessSamples=refusals)
            k.write(d / 'restart.json', record)
            return record
        except k.Refused as error:
            if str(error) not in ('K8S_RESTART_NOT_OBSERVED', 'K8S_CONTAINER_IDENTITY_UNMEASURED'):
                record.update(status='REFUSED', code=str(error))
                k.write(d / 'restart.json', record)
                raise
            refusals.append({'at': time.time(), 'code': str(error)})
            time.sleep(min(1, max(0, until - time.time())))
    record.update(status='UNMEASURED', endedAt=time.time(), readinessSamples=refusals)
    k.write(d / 'restart.json', record)
    raise k.Refused('K8S_RESTART_NOT_OBSERVED', 'UNMEASURED')


def continuity(d, c, independent_directory):
    peer, other, _ = k.load(independent_directory)
    restart = k.document(d / 'restart.json')
    k.need(restart.get('status') == 'OBSERVED', 'RESTART_NOT_OBSERVED', 'UNMEASURED')
    first = k.document(d / 'observation.initial.json')
    second = k.document(peer / 'observation.initial.json')
    k.need(c['context'] == other['context'] and c['namespace'] != other['namespace'] and c['runId'] != other['runId'] and first['namespace']['uid'] != second['namespace']['uid'], 'INDEPENDENT_FIXTURE_REQUIRED')
    k.need(all(c['pins'][field] == other['pins'][field] for field in ('pair','appImage','appImageId','bindingCommit','instrument')), 'CONTINUITY_SOURCE_CHANGED')
    window = k.document(peer / 'load/window.json')
    result = k.document(peer / 'load/result.json')
    capture = k.document(peer / 'load/probe.json')
    k.need(type(window.get('loadStartedAt')) in (int,float) and type(window.get('loadEndedAt')) in (int,float) and
           window['loadStartedAt'] < restart['startedAt'] < restart['endedAt'] < window['loadEndedAt'] and
           result.get('verdict') == 'OBSERVED', 'CONTINUITY_WINDOW_UNMEASURED', 'UNMEASURED')
    k.need(window.get('pins')==other['pins'] and result.get('pins')==other['pins'] and window.get('namespaceUid')==second['namespace']['uid'],'CONTINUITY_SOURCE_CHANGED')
    k.need(k.document(d / 'recovery/result.json').get('verdict') == 'OBSERVED', 'RECOVERY_UNMEASURED', 'UNMEASURED')
    from matrix import identity
    identity(other, second, k.document(peer / 'load/before.json'))
    identity(other, second, k.document(peer / 'load/after.json'))
    frames = capture.get('kubernetesFrames', {})
    k.need(frames.get('overflow') is False, 'CONTINUITY_FRAME_UNMEASURED', 'UNMEASURED')
    observations = []
    for tenant in roster(other):
        at = sorted(row['at'] / 1000 for row in frames['rows'] if row['tenant'] == tenant['id'])
        k.need(any(t < restart['startedAt'] for t in at) and any(t > restart['endedAt'] for t in at), 'CONTINUITY_FRAME_UNMEASURED', 'UNMEASURED')
        gaps = [b-a for a,b in zip(at, at[1:]) if a <= restart['endedAt'] and b >= restart['startedAt']]
        observations.append({'tenant':tenant['id'],'frames':len(at),'maximumObservedFrameGapSeconds':max(gaps) if gaps else None})
    value = {'version':1,'verdict':'OBSERVED','scope':'sampled independent-fixture frames across exact owned role restart; no continuous availability SLO',
             'restartWindow':{'startedAt':restart['startedAt'],'endedAt':restart['endedAt'],'role':restart['role']},
             'independentRunId':other['runId'],'independentNamespaceUid':second['namespace']['uid'],'frames':observations,
             'sharedCluster':True,'sharedDriverHost':c['driver']['hostId']==other['driver']['hostId'],'capacityAcceptance':'NOT_GRANTED'}
    k.write(d / 'continuity.json',value)
    return value


def quantity(value, cpu=False):
    return k.resource_budget.quantity(value, cpu, k.need)


def pod_limits(spec):
    """Per-resource upper bound across init phases and steady state."""
    return k.resource_budget.pod_budget(spec, k.resource_budget.LIMITS, k.need)


def matrix_plan(value):
    k.need(value.get('version')==1 and isinstance(value.get('fixtures'),list) and 1<=len(value['fixtures'])<=4,'MATRIX_BOUND')
    configs=[];names=set();owners=set();ports=set();claims=set();total={'millicpus':0,'memoryBytes':0,'ephemeralBytes':0}
    accounting = k.resource_accounting(value)
    commands=[]
    for directory in value['fixtures']:
        d,c,objects=k.load(directory)
        k.need(k.resource_accounting(c) == accounting, 'RESOURCE_ACCOUNTING_MISMATCH')
        url=urlparse(c['baseUrl'])
        k.need(url.scheme=='http' and url.hostname=='127.0.0.1' and url.port is not None and
               url.username is None and url.password is None and url.path in ('','/') and not url.query and not url.fragment,'LOOPBACK_FORWARD_REQUIRED')
        port=(c['driver']['hostId'],url.port)
        k.need((c['context'],c['namespace']) not in names and c['runId'] not in owners and port not in ports,'FIXTURE_FANOUT_COLLISION')
        names.add((c['context'],c['namespace']));owners.add(c['runId']);ports.add(port)
        if configs:
            k.need(c['context']==configs[0]['context'],'MATRIX_CONTEXT_CHANGED')
            k.need(all(c['pins'][field]==configs[0]['pins'][field] for field in ('pair','appImage','appImageId','bindingCommit','instrument')),'MATRIX_MIXED_SOURCE')
        configs.append(c)
        for obj in objects.values():
            if obj['kind'] not in k.WORKLOADS:continue
            pod=k.template(obj)['spec']
            for volume in pod.get('volumes',[]):
                if 'persistentVolumeClaim' in volume:
                    claim=(c['context'],c['namespace'],volume['persistentVolumeClaim']['claimName'])
                    # Repeated use within one fixture is legitimate; another
                    # fixture cannot share a namespaced claim with unique ns.
                    claims.add(claim)
            for dimension, amount in k.resource_budget.pod_budget(pod, accounting, k.need).items():
                total[dimension] += amount
        for actor_name in ('driver','observer'):
            for field in ('millicpus','memoryBytes'):total[field]+=c[actor_name]['resources'][field]
        placement = ({'applicationTopology':'separate-k1','applicationReplicas':{role:1 for role in k.application_topology.ROLES}}
                     if k.application_topology.selection(c,k.need)==k.application_topology.SEPARATE else {'cohortReplicas':1})
        commands.append({'runId':c['runId'],'namespace':c['namespace'],**placement,
                         'argv':[sys.executable,'-B',str(k.HERE/'adapter.py'),'load',str(d)],'workload':c['workload'],'deadlines':c['deadlines']})
    ceiling=value.get('aggregateCeiling',{})
    k.need(set(ceiling)==set(total) and all(type(ceiling[key]) is int and total[key]<=ceiling[key] for key in total),'AGGREGATE_HEADROOM_EXCEEDED')
    return {'version':1,'status':'PLANNED_ONLY','commands':commands,
            'resourceAccounting':accounting, 'accounting':k.resource_budget.scope(accounting),
            ('aggregateRequests' if accounting == k.resource_budget.REQUESTS else 'conservativeAggregateLimits'):total,'aggregateCeiling':ceiling,
            'admission':'Lane E current per-node and driver headroom still required; this plan reserves nothing',
            'contention':'shared nodes, disk, PostgreSQL, network/control plane and driver/observer costs remain attributed',
            'capacityAcceptance':'NOT_GRANTED'}
