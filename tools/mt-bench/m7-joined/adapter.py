#!/usr/bin/env python3
"""Joined M7 instrument. No operation attaches to or tears down an existing stack."""
import argparse
import gzip
import contextlib
import contextvars
import hashlib
import json
import viewer_plan
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
import threading
import resource
import math

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from contract import (COUNTS, REPLICAS, DISCOVERY_MAX_WORKERS, discovery_api_replicas, PILOT_COUNTS, CADENCE, OWNER, SHA, require, digest, labels_match, owned,
                      tenant_projection, metric, oracle, serving_mounts, campaign_check, pilot_check, host_identity, receipt_scope, diagnostic_check, measurement_request, measurement_topology, measurement_output, unaccepted_check, MEASUREMENT_AUTHORIZATION)
from probe import generate
from workload import REALISTIC_CADENCE_MS, REALISTIC_MIX, realistic_cycle_ms, generate as generate_workload
import profile_provenance
import orchestration_binding
import evaluator_progress
import clinical_timeline
import revision_witness
import api_cause
import driver_vu_diagnostic
import api_warm_cause
import commissioning_wal
import node_observation
import source_access
import discovery_rest
import evaluator_idle
import evaluator_opportunities
import evaluator_catchup
import preload_convergence
import sql_attribution
import cost_companion
import realtime_costs
import diagnostic_resources
import stream_topology
import role_instances
import static_topology
import dependency_reuse
import collection_segments
import vault_refusal
import workload_inputs
import phase_windows
BASE = ROOT / "tools/mt-bench/compose-baseline"
REUSED = ["tools/mt-bench/capacity/probe.js", "tools/mt-bench/capacity/k6/workload.js",
          "tools/mt-bench/compose-baseline/probes/sample.sh", "tools/mt-bench/compose-baseline/oracle/disk.sh",
          "tools/mt-bench/run-catalog/retained.py", "tools/mt-bench/run-catalog/latency.py"]


def jwt_setup_concurrency(value, discovery=False):
    require(workload_inputs.concurrency(value) and (discovery or value <= 64), "M7_JWT_SETUP_CONCURRENCY_INVALID")
    return value


def jwt_setup_env(manifest):
    return "JWT_SETUP_CONCURRENCY=" + str(jwt_setup_concurrency(manifest.get("jwtSetupConcurrency", 1), manifest.get('runPurpose') == 'discovery'))


def runtime_env(extra=None):
    # Ambient NS_*/NODE_OPTIONS/BENCH_* must not silently alter a paired run.
    names=("PATH","HOME","USER","LANG","XDG_RUNTIME_DIR","DOCKER_HOST","DOCKER_CONTEXT","DOCKER_CONFIG","SSH_AUTH_SOCK")
    return {**{key:os.environ[key] for key in names if key in os.environ}, **(extra or {})}


_COMMAND_DEADLINE=contextvars.ContextVar('m7_command_deadline',default=None)
_CLEANUP_NODE_LIMIT=contextvars.ContextVar('m7_cleanup_node_limit',default=False)
_PRIVATE_COMMANDS=contextvars.ContextVar('m7_private_commands',default=None)


@contextlib.contextmanager
def private_commands(directory, *, max_output_bytes=None):
    require(max_output_bytes is None or type(max_output_bytes) is int and 1 <= max_output_bytes <= 1048576, 'M7_PRIVATE_CAPTURE_LIMIT')
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True);directory.chmod(0o700)
    token=_PRIVATE_COMMANDS.set({'directory':directory,'sequence':0,'maxOutputBytes':max_output_bytes})
    try:yield
    finally:_PRIVATE_COMMANDS.reset(token)


@contextlib.contextmanager
def command_deadline(until):
    previous=_COMMAND_DEADLINE.get()
    if previous is not None:until=previous if until is None else min(previous,until)
    token=_COMMAND_DEADLINE.set(until)
    try:yield
    finally:_COMMAND_DEADLINE.reset(token)


def remaining_seconds(default):
    deadline=_COMMAND_DEADLINE.get()
    if deadline is None:return default
    remaining=deadline-time.time()
    require(remaining>0,'M7_COMMAND_DEADLINE')
    return min(default,remaining)


def discovery_seconds(m, default):
    # Only an existing discovery cutoff can replace a legacy stage duration.
    if m.get('runPurpose')=='discovery' and m.get('profile')=='pgstream-sample' and _COMMAND_DEADLINE.get() is not None:
        return remaining_seconds(float('inf'))
    return remaining_seconds(default)


def private_output(path, limit):
    """Bound retained tail bytes, including failed/timed-out trusted commands."""
    size=path.stat().st_size
    with path.open('r+b') as stream:
        if limit is not None and size > limit:
            stream.seek(size-limit);data=stream.read(limit)
            stream.seek(0);stream.write(data);stream.truncate()
        else:data=stream.read()
    return data, {'observedBytes':size,'retainedBytes':len(data),'truncated':size>len(data),'retention':'tail' if size>len(data) else 'complete'}


def _command(argv, *, cwd=None, env=None, input=None, file=None, timeout=120, binary=False, phase=None):
    # Raw output belongs only in private phase artifacts; never argv/env in
    # public exceptions. Capture begins before prepared=true or state exists.
    timeout=remaining_seconds(timeout)
    cwd=ROOT if cwd is None else cwd
    capture=_PRIVATE_COMMANDS.get();prefix=None;started=time.time()
    if capture is not None:
        capture['sequence']+=1
        prefix=capture['directory']/(str(capture['sequence']).zfill(4)+'-'+Path(str(argv[0])).name)
    result=None;failure=None;stdout=b'';stderr=b'';output_counts={}
    try:
        if prefix is None:
            result=subprocess.run([str(a) for a in argv],cwd=cwd,env=runtime_env() if env is None else env,input=input,
                                  stdout=file or subprocess.PIPE,stderr=subprocess.STDOUT if file else subprocess.PIPE,timeout=timeout)
            stdout=result.stdout or b'';stderr=result.stderr or b''
        else:
            with prefix.with_suffix('.stdout').open('wb') as out,prefix.with_suffix('.stderr').open('wb') as err:
                prefix.with_suffix('.stdout').chmod(0o600);prefix.with_suffix('.stderr').chmod(0o600)
                result=subprocess.run([str(a) for a in argv],cwd=cwd,env=runtime_env() if env is None else env,input=input,stdout=out,stderr=err,timeout=timeout)
            stdout,output_counts['stdout']=private_output(prefix.with_suffix('.stdout'),capture.get('maxOutputBytes'))
            stderr,output_counts['stderr']=private_output(prefix.with_suffix('.stderr'),capture.get('maxOutputBytes'))
            if file:file.write(stdout);file.write(stderr)
        if result.returncode:
            error=RuntimeError('M7_COMMAND_FAILED:'+Path(str(argv[0])).name);error.stderr=stderr;error.returncode=result.returncode
            raise error
        require(not any(value['truncated'] for value in output_counts.values()), 'M7_PRIVATE_OUTPUT_TRUNCATED')
        return None if file else stdout if binary else stdout.decode()
    except Exception as error:
        failure=type(error).__name__
        raise
    finally:
        if prefix is not None:
            for stream in ('stdout','stderr'):
                path=prefix.with_suffix('.'+stream)
                if stream not in output_counts and path.exists():
                    _,output_counts[stream]=private_output(path,capture.get('maxOutputBytes'))
            write(prefix.with_suffix('.json'),{'program':Path(str(argv[0])).name,'phase':phase or Path(str(argv[0])).name,
                  'startedAt':started,'elapsedSeconds':time.time()-started,'returncode':result.returncode if result else None,
                  'timeoutSeconds':timeout,'failureType':failure,'stdout':prefix.with_suffix('.stdout').name,'stderr':prefix.with_suffix('.stderr').name,
                  **({'outputRetention':{'maximumBytesPerStream':capture['maxOutputBytes'],'streams':output_counts,
                      'scope':'Retained tail bound; transient command output files may be larger before command completion/timeout.'}} if capture.get('maxOutputBytes') is not None else {}),
                  'scope':'PRIVATE; raw output may contain credentials; do not publish'})


def diagnostic_resource_rows(m):
    rows = resources(m)
    for row in rows:
        prior = m.get('attachedResources', {}).get(row['Id'])
        if prior is not None:
            require(attached_identity(row) == prior, 'M7_ATTACHED_RESOURCE_CHANGED')
        else:
            owned(row, m['owner'])
    return rows


def command(argv, *, cwd=None, env=None, input=None, file=None, timeout=120, binary=False, phase=None):
    selected_env = runtime_env() if env is None else env
    if _CLEANUP_NODE_LIMIT.get() and argv and Path(str(argv[0])).name=='node':
        # Teardown must not acquire the diagnostic driver lock or a new actor
        # quota lease. Its source verifier still gets a fixed small V8 heap cap.
        bounded=[argv[0],'--max-heap-size=128',*argv[1:]]
        return _command(bounded,cwd=cwd,env=selected_env,input=input,file=file,timeout=timeout,binary=binary,phase=phase)
    role = 'generator' if phase in ('product-prepare', 'settings-fingerprint', 'generator-client-preflight','completed-oracle') else 'helper'
    if diagnostic_resources._ACTIVE is not None and list(map(str,argv[:2]))==['docker','run']:argv=bounded_k6_argv(argv)
    with diagnostic_resources.command(argv, selected_env, role) as (bounded_argv, bounded_env):
        return _command(bounded_argv, cwd=cwd, env=bounded_env, input=input, file=file, timeout=timeout, binary=binary, phase=phase)


def bounded_k6_argv(argv):
    value=diagnostic_resources.bounded_standalone(argv)
    if diagnostic_resources._ACTIVE is not None:
        value=list(value)
        require(not any(str(x).startswith('--pull=') for x in value),'M7_DIAGNOSTIC_PULL_POLICY_CHANGED')
        if '--pull' in value:
            i=value.index('--pull');require(value.count('--pull')==1 and value[i+1:i+2]==['never'],'M7_DIAGNOSTIC_PULL_POLICY_CHANGED')
        else:value[9:9]=['--pull','never']
    return value


def seal_diagnostic_images(config,m):
    # Selected preparation uses cached images only. Strip build recipes from
    # this new frozen declaration so Compose cannot implicitly build on a miss.
    pin_service_images(config,m['imageId'])
    for role,spec in config['services'].items():
        ref=spec.get('image');require(isinstance(ref,str) and ref,'M7_DIAGNOSTIC_CACHED_IMAGE_REQUIRED')
        found=json.loads(command(['docker','image','inspect',ref]))
        require(len(found)==1 and re.fullmatch('sha256:[a-f0-9]{64}',found[0].get('Id','')),'M7_DIAGNOSTIC_CACHED_IMAGE_REQUIRED')
        spec['image']=found[0]['Id'];spec.pop('build',None)
    return config



def document(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def reserve_output(d,m,kind,existing):
    """One attempt per metadata directory; retry through a new attachment."""
    d=Path(d);marker=d/(kind+'-attempt.json')
    def refuse():
        folder=d/'attempt-refusals'/uuid.uuid4().hex
        write(folder/'refusal.json',{'kind':kind,'code':'M7_'+kind.upper()+'_OUTPUT_EXISTS',
                                    'existing':[name for name in existing if (d/name).exists()],
                                    'action':'use a new metadata attachment; originals unchanged'})
        raise RuntimeError('M7_'+kind.upper()+'_OUTPUT_EXISTS')
    if any((d/name).exists() for name in existing):refuse()
    try:
        with marker.open('x') as output:
            json.dump({'attemptId':uuid.uuid4().hex,'kind':kind,'startedAt':time.time(),
                       'owner':m.get('owner'),'pair':m.get('pair'),'workingDirectory':str(ROOT)},output,indent=2)
            output.write('\n')
        marker.chmod(0o600)
    except FileExistsError:refuse()


def git(repo, *args):
    return command(["git", "-C", Path(repo).resolve(), *args]).strip()


def commit(repo, value):
    require(SHA.fullmatch(value or ""), "M7_FULL_COMMIT_REQUIRED")
    require(git(repo, "rev-parse", "--verify", value + "^{commit}") == value, "M7_COMMIT_UNAVAILABLE")
    return value


def instrument():
    head = git(ROOT, "rev-parse", "HEAD")
    # Prose is provenance, not executed instrument input. Keep recording HEAD,
    # but do not invalidate byte-identical tools after a documentation edit.
    paths = [p for p in git(ROOT, "ls-files", "tools/mt-bench/m7-joined").splitlines()
             if not p.endswith('.md')] + REUSED
    require(paths and "tools/mt-bench/m7-joined/adapter.py" in paths, "M7_INSTRUMENT_NOT_COMMITTED")
    require("tools/mt-bench/m7-joined/orchestration_binding.py" in paths,"M7_ORCHESTRATION_BINDING_NOT_COMMITTED")
    require(not git(ROOT, "diff", "HEAD", "--", *paths), "M7_INSTRUMENT_DIRTY")
    hashes = {p: digest(ROOT / p) for p in sorted(set(paths))}
    return {"commit": head, "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), "files": hashes}


def load(directory, *, resource_limits=True):
    d = Path(directory).resolve()
    m = document(d / "owner.json")
    require(m.get("directory") == str(d) and re.fullmatch(r"[0-9a-f]{32}", m.get("owner", "")), "M7_OWNER_MANIFEST_INVALID")
    require(m.get("instrument", {}).get("sha256") == instrument()["sha256"], "M7_INSTRUMENT_CHANGED")
    if resource_limits:
        if 'dependencyReuse' in m:require(isinstance(m['dependencyReuse'],dict),'M7_DEPENDENCY_REUSE_RECORD_REQUIRED')
        record=m.get('diagnosticResources')
        if 'diagnosticResources' in m:require(isinstance(record,dict) and diagnostic_resources.selection(record.get('profile')) is not None,'M7_DIAGNOSTIC_RESOURCE_RECORD_REQUIRED')
        diagnostic_resources.configure(record.get('profile') if record is not None else None,
            document(d/'frozen.compose.json') if record is not None else None,record,
            observe=lambda:diagnostic_resource_rows(m))
    elif diagnostic_resources._ACTIVE is None or not any(diagnostic_resources._ACTIVE.host.values()):
        # Down retains ownership/source guards but must not acquire a diagnostic
        # driver lock or validate corrupt quotas before exact-owned cleanup.
        diagnostic_resources.configure()
    return d, m


def compose(d, *args, file=None, input=None, timeout=120):
    if diagnostic_resources._ACTIVE is not None:
        args=list(args);i=0
        while i<len(args) and args[i]=='--profile':i+=2
        if args[i:i+1] in (['up'],['run'],['create']):
            require(not any(str(x).startswith('--pull=') or x=='--build' for x in args),'M7_DIAGNOSTIC_PULL_POLICY_CHANGED')
            if '--pull' in args:
                n=args.index('--pull');require(args.count('--pull')==1 and args[n+1:n+2]==['never'],'M7_DIAGNOSTIC_PULL_POLICY_CHANGED')
            else:args[i+1:i+1]=['--pull','never']
    argv=orchestration_binding.fixture_argv(d,args)
    if orchestration_binding.mutation(args):
        clinical_timeline.before_sender_effect(Path(d),args,document(Path(d)/'frozen.compose.json'),document(Path(d)/'owner.json'))
        orchestration_binding.fixture_mutation_preflight(d,argv,command)
    if diagnostic_resources._ACTIVE is not None:
        try:
            diagnostic_resources.before_compose(args, document(Path(d)/'frozen.compose.json'),
                document(Path(d)/'owner.json').get('cpuPrecisionPreflight'))
        except RuntimeError as error:
            resource_cpu_failure(error)
            raise
    return command(argv, file=file, input=input, timeout=timeout)


def resources(m, all_containers=True):
    flag = "-aq" if all_containers else "-q"
    ids = command(["docker", "ps", flag, "--filter", "label=com.docker.compose.project=" + m["project"]]).split()
    return json.loads(command(["docker", "inspect", *ids])) if ids else []



def assert_absent(m):
    """Exact project inventories; stderr wording never counts as absence."""
    require(not resources(m),'M7_CLEANUP_CONTAINER_REMAINS')
    for kind in ('network','volume'):
        ids=command(['docker',kind,'ls','-q','--filter','label=com.docker.compose.project='+m['project']]).split()
        require(not ids,'M7_CLEANUP_'+kind.upper()+'_REMAINS')
    return {'status':'ABSENT','scope':'exact compose-project container/network/volume inventories'}


def attached_identity(row):
    return {'imageId':row['Image'],'startedAt':row['State']['StartedAt'],'service':row['Config']['Labels'].get('com.docker.compose.service')}


def fixture_inventory(m):
    value=inventory(m['owner'])
    if m.get('attached'):
        for row in value['containers']:
            expected=m['attachedResources'].get(row['id'])
            if expected and expected['imageId']==row['image'] and row['project']==m['project']:row['owned']=True
    return value


def assert_owned(m):
    if m.get('attached'):
        current={}
        for row in resources(m):
            if row['Config']['Labels'].get(OWNER)==m['owner']:continue
            require(row['Config']['Labels'].get('com.docker.compose.project')==m['project'],'M7_ATTACHED_PROJECT_CHANGED')
            current[row['Id']]=attached_identity(row)
        require(current==m['attachedResources'],'M7_ATTACHED_RESOURCE_CHANGED')
        return
    for row in resources(m):
        owned(row, m["owner"])
    for kind in ("volume", "network"):
        ids = command(["docker", kind, "ls", "-q", "--filter", "label=com.docker.compose.project=" + m["project"]]).split()
        if ids:
            for row in json.loads(command(["docker", kind, "inspect", *ids])):
                owned(row, m["owner"])


def inventory(owner):
    endpoint = os.environ.get("DOCKER_HOST") or command(["docker","context","inspect","--format",'{{(index .Endpoints "docker").Host}}']).strip()
    require(endpoint.startswith("unix://"), "M7_LOCAL_DOCKER_REQUIRED")
    ids = command(["docker", "ps", "-q"]).split()
    containers = []
    if ids:
        for row in json.loads(command(["docker", "inspect", *ids])):
            labels = row.get("Config", {}).get("Labels", {}) or {}
            containers.append({"id": row["Id"], "name": row["Name"].lstrip("/"), "image": row["Image"],
                               "project": labels.get("com.docker.compose.project"), "owned": labels.get(OWNER) == owner})
    return {"at": time.time(), "load": list(os.getloadavg()), "cores": os.cpu_count(),
            "memory": dict(re.findall(r"^(MemTotal|MemAvailable):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)),
            "cpuModel":re.search(r"^model name\s+: (.+)$",Path("/proc/cpuinfo").read_text(),re.M)[1],
            "dockerDaemonId":command(["docker","info","--format","{{.ID}}"]).strip(),
            "kernel": os.uname().release, "dockerContext":command(["docker","context","show"]).strip(), "docker": command(["docker", "version", "--format", "{{.Server.Version}} "]).strip(),
            "compose": command(["docker", "compose", "version", "--short"]).strip(), "containers": containers,
            # Record process names/counters, never command arguments or environments.
            "processes": command(["ps", "-eo", "pid,ppid,comm,pcpu,rss"])}


def quiet(d, m, phase, check_load=True):
    host = fixture_inventory(m)
    if m.get("profile")=="pgstream-sample" and m.get("runPurpose")=="discovery":
        host["scope"]="shared-host diagnostic; contention recorded, no capacity acceptance"
        write(d / (phase + "-host.json"),host);return
    write(d / (phase + "-host.json"), host)
    require(not any(not row["owned"] for row in host["containers"]), "M7_FOREIGN_ACTIVE_CONTAINERS:see_host_inventory")
    if check_load:
        require(host["load"][0] <= m["quietLoad"], "M7_HOST_NOT_QUIET")


SERIAL_EXCHANGE_DIAGNOSTIC = {'tenants':64, 'phaseSeconds':120, 'requestSeconds':60}

def serial_exchange_selection(args):
    if not getattr(args, 'serial_exchange_diagnostic', False):return None
    require(args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery' and args.tenants==3000,
            'M7_SERIAL_EXCHANGE_DIAGNOSTIC_SCOPE')
    return dict(SERIAL_EXCHANGE_DIAGNOSTIC)

def serial_exchange_receipt(m, value):
    require(m.get('serialExchangeDiagnostic') == value.get('serialExchangeDiagnostic'), 'M7_SERIAL_EXCHANGE_DIAGNOSTIC_RECEIPT')
    if m.get('serialExchangeDiagnostic') is not None:
        require(m['serialExchangeDiagnostic']==SERIAL_EXCHANGE_DIAGNOSTIC and m.get('profile')=='pgstream-sample' and
                m.get('runPurpose')=='discovery' and m.get('tenants')==3000 and value.get('status')=='AUTHORIZED_DIAGNOSTIC',
                'M7_SERIAL_EXCHANGE_DIAGNOSTIC_SCOPE')

def frozen(m,operation):
    require(Path(m["freeze"]).is_file(),"M7_FROZEN_OR_DIAGNOSTIC_RECEIPT_REQUIRED")
    value=document(m["freeze"]);serial_exchange_receipt(m,value)
    if value.get('version')==2 and value.get('kind')=='joined-diagnostic' and m.get('profile')=='pgstream-sample' and m.get('runPurpose')=='discovery' and m.get('prepared'):
        from run_configuration import from_manifest
        require(from_manifest(m)==m.get('runConfiguration'),'M7_DIAGNOSTIC_CONFIGURATION_MISMATCH')
    result=receipt_scope(m,value,operation)
    if value.get('version')==2 and result['kind']=='diagnostic-discovery':
        m['discoveryAuthorization']={k:v for k,v in result.items() if k!='kind'}
    return result


def experiment_host(d,m,phase):
    if m.get("profile")=="fresh-image-diagnostic":
        host=fixture_inventory(m);host["scope"]="diagnostic-only; not quiet-host capacity"
        write(d/(phase+"-host.json"),host)
    else:quiet(d,m,phase)


def image(m):
    spec = json.loads(command(["docker", "image", "inspect", m["image"]]))[0]
    labels_match(spec.get("Config", {}).get("Labels", {}) or {}, **m["pair"])
    if m.get("imageId"):
        require(spec["Id"] == m["imageId"], "M7_IMAGE_ID_CHANGED")
    return spec["Id"]


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def cadence_options(args):
    value=dict(CADENCE[args.profile])
    discovery_inputs=getattr(args,'run_purpose','acceptance')=='discovery'
    phase_limit=workload_inputs.MAX_SECONDS if discovery_inputs else 86400
    limits={'sockets_per_tenant':workload_inputs.MAX_ARRAY_LENGTH if discovery_inputs else 8,
            'driver_shards':workload_inputs.MAX_ARRAY_LENGTH if discovery_inputs else 16,
            'hot_factor':workload_inputs.MAX_ARRAY_LENGTH if discovery_inputs else 86400}
    knobs={'warmup_seconds':'warmupSeconds','idle_seconds':'idleSeconds','load_seconds':'loadSeconds','setup_seconds':'setupSeconds','drain_seconds':'drainSeconds','accel':'accel','hot_factor':'hotFactor','sampler_interval':'samplerIntervalSeconds','probe_every_ms':'probeEveryMs','sockets_per_tenant':'socketsPerTenant','driver_shards':'driverShards'}
    changed={key:getattr(args,key,None) for key in knobs if getattr(args,key,None) is not None}
    require(not changed or args.profile=='pgstream-sample','M7_SAMPLE_KNOB_PROFILE')
    selected_ledger=getattr(args,'probe_ledger',None)
    if selected_ledger is not None:
        require(args.profile=='pgstream-sample' and discovery_inputs and workload_inputs.probe_ledger(selected_ledger),
                'M7_PROBE_LEDGER_BUDGET')
        value['probeLedger']=selected_ledger
    if args.profile=='pgstream-sample':
        value.update(warmupSeconds=60,samplerIntervalSeconds=2)
        for key,number in changed.items():
            if key == 'probe_every_ms':
                require(workload_inputs.probe_interval(number), 'M7_PROBE_INTERVAL_RANGE')
            else:
                require(type(number) is int and 1 <= number <= limits.get(key,phase_limit),
                        'M7_SAMPLE_KNOB_RANGE:' + knobs[key])
            value[knobs[key]] = number
        require(value['samplerIntervalSeconds'] <= 60 and sum(value.get(key, 0) for key in
                ('warmupSeconds','idleSeconds','loadSeconds','setupSeconds','drainSeconds')) <=
                phase_limit, 'M7_SAMPLE_DURATION_RANGE')
        require(workload_inputs.population_fits(getattr(args,'tenants',1), value['hotFactor']),
                'M7_WORKLOAD_POPULATION_ARRAY_LIMIT')
        require(workload_inputs.probe_fits_ledger(value['probeEveryMs'], value['loadSeconds'], selected_ledger),
                'M7_PROBE_LEDGER_WINDOW')
    offered=getattr(args,'offered_rps',None)
    if offered is not None:
        require(args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery','M7_OFFERED_RPS_DISCOVERY_ONLY')
        require(workload_inputs.offered_rate(offered), 'M7_OFFERED_RPS_RANGE')
        require(workload_inputs.aggregate_cycle_ms(args.tenants, value['hotFactor'], offered) is not None,
                'M7_OFFERED_RPS_TIME_UNIT')
        value['offeredRps']=offered
    clients=getattr(args,'logical_polling_clients',None)
    if clients is not None:
        require(args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery','M7_VIEWER_DISCOVERY_ONLY')
        require(workload_inputs.polling_clients(clients), 'M7_VIEWER_TOTAL_RANGE')
        value['logicalPollingClients']=clients
    if args.profile=='pgstream-sample' and discovery_inputs:
        require(workload_inputs.shard_count(value.get('driverShards',1),getattr(args,'tenants',1)), 'M7_DRIVER_SHARDS_RANGE')
        require(workload_inputs.polling_clients(value.get('logicalPollingClients',getattr(args,'tenants',1)*value['socketsPerTenant'])), 'M7_VIEWER_TOTAL_RANGE')
    restart=getattr(args,'restart_during_load_after_seconds',None)
    if restart is not None:
        value['restartDuringLoadAfterSeconds']=restart
        import demand_recovery
        demand_recovery.validate({'profile':args.profile,'runPurpose':getattr(args,'run_purpose',None),
                                  'completionContract':getattr(args,'completion_contract',None),'cadence':value})
    mix = getattr(args, 'workload_mix', None)
    if mix is not None:
        require(mix == REALISTIC_MIX and args.profile == 'pgstream-sample'
                and getattr(args, 'run_purpose', 'acceptance') == 'discovery'
                and value['accel'] == value['hotFactor'] == 1 and offered is None,
                'M7_REALISTIC_MIX_CONFIGURATION')
        value['workloadMix'] = mix
    scale = getattr(args, 'workload_scale', None)
    if scale is not None:
        require(mix == REALISTIC_MIX, 'M7_WORKLOAD_SCALE_CONFIGURATION')
        realistic_cycle_ms(scale)
        value['workloadScale'] = scale
    observation = getattr(args, 'drain_observation', None)
    if observation is not None:
        require(args.profile == 'pgstream-sample' and args.run_purpose == 'discovery'
                and 'drainSeconds' in value and args.evaluator_catchup == 'fixed-target-v1',
                'M7_DRAIN_OBSERVATION_SCOPE')
        value['drainObservation'] = observation
    phase_windows.selection(value)
    value.update(driver_vu_diagnostic.selection(args, value))
    return value


def rate_offer(m):
    if m['cadence'].get('workloadMix') == REALISTIC_MIX:
        scale = m['cadence'].get('workloadScale', 1)
        weights = {shape: 5 if shape == 'r_sgv' else 1 for shape in REALISTIC_CADENCE_MS}
        units = realistic_cycle_ms(scale)
        rates = {shape: m['tenants'] * weights[shape] * 1000 / units[shape] for shape in units}
        return {'workloadMix': REALISTIC_MIX, 'workloadScale': scale,
                'workloadInterpretation': 'sensor-cadence' if scale == 1 else 'uniform-rate-bracket',
                'sensorCadence': scale == 1, 'requestedScenarioRps': None,
                'effectiveScenarioRps': sum(rates.values()),
                'perTenantIntervalMs': {shape: units[shape] / weights[shape] for shape in units},
                'scenarioTimeUnitMs': units, 'scenarioRpsByShape': rates,
                'scope': 'Nominal scenario attempts. JWT setup and realtime probes are separate traffic.'}
    # Seven selected scenario weights sum to eleven; credential setup and the
    # stock-client probe are separate traffic, not part of this arrival target.
    weight=m['tenants']-1+m['cadence'].get('hotFactor',10)
    nominal=11000*weight/(300000/m['cadence'].get('accel',1))
    requested=m['cadence'].get('offeredRps')
    cycle = (workload_inputs.aggregate_cycle_ms(m['tenants'], m['cadence'].get('hotFactor', 10), requested)
             if requested is not None else math.floor(300000 / m['cadence'].get('accel', 1) + .5))
    require(cycle is not None and cycle >= 1, 'M7_OFFERED_RPS_TIME_UNIT')
    return {'requestedScenarioRps':requested,'nominalScenarioRps':nominal,'effectiveScenarioRps':11000*weight/cycle,
            'arrivalCycleMs':cycle,'scope':'scenario HTTP attempts only; credential exchanges and stock-client probes are separate; attempts do not prove bytes reached server'}


def attach(args):
    static_selection=static_topology.option(args,require_allocation=False)
    require(not static_selection or getattr(args,'runtime_owner',None),'M7_STATIC_ATTACH_OWNER_REQUIRED')
    require(not commissioning_wal.option(args) and getattr(args,'tenant_readiness',None) is None,'M7_DIAGNOSTIC_OPTIONS_FRESH_PREPARE_ONLY')
    stream_topology.ack_option(args)
    preload_convergence.option(args)
    require(not api_warm_cause.option(args),'M7_DIAGNOSTIC_OPTIONS_FRESH_PREPARE_ONLY')
    require(not selected_resources_profile(args) and not getattr(args,'revision_witness_targets',None) and getattr(args,'api_cause_observation','off')=='off' and not getattr(args,'generator_dependencies',None) and not getattr(args,'vault_refusal_control',None),'M7_DIAGNOSTIC_OPTIONS_FRESH_PREPARE_ONLY')
    diagnostic_resources.configure()
    # Bind only instrumentation metadata to the runtime owner's exact existing
    # fixture. Never deploy, restart, install, relabel or assume cleanup custody.
    require(not getattr(args,'fixture_project',None),'M7_ATTACH_USE_EXISTING_PROJECT')
    require(args.profile=='pgstream-sample' and args.run_purpose=='discovery','M7_ATTACH_DIAGNOSTIC_ONLY')
    pinned=instrument();pair={'core':commit(args.core_repo,args.core_commit),'deploy':commit(args.deploy_repo,args.deploy_commit)}
    source=Path(args.source_root).resolve();state=Path(args.state).resolve();target=Path(args.directory).resolve()
    dependencies=Path(args.dependencies_root).resolve() if getattr(args,'dependencies_root',None) else source
    require(not target.exists() and source.is_dir() and state.is_dir(),'M7_ATTACH_PATH')
    require(git(source,'rev-parse','HEAD')==pair['core'],'M7_OWN_CORE_HEAD_CHANGED')
    m={'version':1,'directory':str(target),'owner':uuid.uuid4().hex,'project':args.project,'pair':pair,'instrument':pinned,'image':args.image,'imageId':args.image_id or args.image,'profile':'pgstream-sample','runPurpose':'discovery','measurementMode':'accepted','cadence':cadence_options(args),'tenants':args.tenants,'replicas':args.replicas,'freeze':str(Path(args.freeze).resolve()),'diagnostics':profile_provenance.selection(getattr(args,'diagnostics','off'),getattr(args,'diagnostics_interval_ms',5000)),'coreRepository':str(Path(args.core_repo).resolve()),'attached':True,'completionContract':getattr(args,'completion_contract',None),'jwtSetupConcurrency':jwt_setup_concurrency(getattr(args,'jwt_setup_concurrency',1), args.run_purpose=='discovery')}
    if getattr(args,'pgstream_topology',stream_topology.COLOCATED)!=stream_topology.COLOCATED:m['pgstreamTopology']=args.pgstream_topology
    m.update(static_selection)
    selection=serial_exchange_selection(args)
    if selection is not None:m['serialExchangeDiagnostic']=selection
    select_opportunities(args,m)
    evaluator_catchup.select(args,m)
    require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}',args.project) and workload_inputs.tenants(args.tenants) and (args.replicas==1 or static_selection),'M7_ATTACH_SCOPE')
    # Current receipts bind semantic configuration before attachment admission.
    # This is provisional read-only metadata; canonical owner/dependency/resource
    # validation below remains mandatory before a usable attachment is written.
    m['postgresImageId']=getattr(args,'postgres_image',None)
    m['primerConcurrency']=primer_concurrency(getattr(args,'primer_concurrency',1))
    if getattr(args,'runtime_owner',None):
        runtime=document(args.runtime_owner)
        owner_path=Path(args.runtime_owner).resolve()
        runtime_directory=Path(runtime.get('directory','')).resolve()
        require(owner_path==runtime_directory/'owner.json' and runtime.get('prepared') is True
                and runtime.get('project')==m['project'] and runtime.get('pair')==m['pair']
                and runtime.get('imageId')==m['imageId'], 'M7_ATTACH_RUNTIME_OWNER_MISMATCH')
        if static_selection or runtime.get('staticTopology'):
            require(runtime.get('staticTopology')==m.get('staticTopology') and runtime.get('replicas')==m['replicas'],'M7_STATIC_ATTACH_RUNTIME_MISMATCH')
        if static_selection:
            require(m.get('staticBuildReceiptSha256') == runtime.get('staticBuildReceiptSha256'),
                    'M7_STATIC_ATTACH_RUNTIME_MISMATCH')
            topology = static_selection['staticTopology']
            if topology['workers'] > 1 or m['replicas'] > 1:
                require(isinstance(runtime.get('diagnosticResources',{}).get('profile'),dict),
                        'M7_STATIC_EXPLICIT_ALLOCATION')
        if 'diagnosticResources' in runtime:m['diagnosticResources']=runtime['diagnosticResources']
        commissioning_wal.inherit(args,m,runtime,runtime_directory)
        node_observation.inherit(args,m,runtime,runtime_directory)
    else:
        require(not node_observation.option(args),'M7_NODE_OBSERVATION_ATTACH_BINDING')
    from run_configuration import from_manifest
    m['runConfiguration']=from_manifest(m)
    frozen(m,'deploy');image(m)
    target.mkdir(parents=True,mode=0o700)
    try:
        with private_commands(target/'attach-commands'):
            for name,root in [('core',source),('state',state),('dependencies',dependencies)]: (target/name).symlink_to(root,target_is_directory=True)
            shutil.copyfile(args.env_file,target/'env');(target/'env').chmod(0o600)
            files=[Path(f).resolve() for f in args.compose]
            argv=['docker','compose','-p',args.project,'--env-file',target/'env']
            for file in files:argv.extend(['-f',file])
            config=json.loads(command([*argv,'--profile','ops','config','--format','json']))
            serving_mounts(config)
            if m.get('staticTopology'):
                m['servingInstances']=static_topology.verify_config(m,config)
                require(m['servingInstances']==runtime.get('servingInstances'),'M7_STATIC_ATTACH_RUNTIME_MISMATCH')
            for spec in config['services'].values():
                for volume in spec.get('volumes',[]):
                    if volume.get('type')=='bind':require(Path(volume['source']).resolve().is_relative_to(state),'M7_FOREIGN_STATE_MOUNT_REFUSED')
            ports=config['services']['nginx'].get('ports',[])
            require(len(ports)==1 and ports[0].get('host_ip')=='127.0.0.1','M7_ATTACH_LOOPBACK_PORT')
            m['port']=int(ports[0]['published']);m['quietLoad']=args.quiet_load
            rows=resources(m);require(rows,'M7_ATTACHED_RESOURCES_MISSING')
            m['attachedResources']={row['Id']:attached_identity(row) for row in rows}
            m['runtimeOwnerLabels']=sorted({row['Config']['Labels'].get(OWNER,'') for row in rows})
            for row in rows:
                role=row['Config']['Labels'].get('com.docker.compose.service')
                if role in service_roster(config) or role in ('admin','ui'):require(row['Image']==m['imageId'],'M7_IMAGE_ID_CHANGED')
            m['hostIdentity']=host_identity(fixture_inventory(m));m['prepared']=True
            m['sourceCompose']={str(file):digest(file) for file in [*files,Path(args.env_file).resolve()]}
            m['environmentSha256']=digest(target/'env');write(target/'frozen.compose.json',config);m['composeSha256']=digest(target/'frozen.compose.json')
            shutil.copyfile(HERE/'restart.cjs',target/'restart.cjs');m['restartHelperSha256']=digest(target/'restart.cjs')
            m['probe']=generate(ROOT,target/'probe.js',serial_exchange=bool(m.get('serialExchangeDiagnostic')));m['workload']=generate_workload(ROOT,target/'k6/workload.js')
            m['generator']=attachment_generator(target,source,dependencies,m,getattr(args,'runtime_owner',None))
            if m['generator'].get('runtimeOwner'):
                runtime=document(args.runtime_owner)
                if 'diagnosticResources' in runtime:m['diagnosticResources']=runtime['diagnosticResources']
                if 'edgeWorkerBudget' in runtime:m['edgeWorkerBudget']=runtime['edgeWorkerBudget']
            require(from_manifest(m)==m['runConfiguration'],'M7_DIAGNOSTIC_CONFIGURATION_MISMATCH')
            candidates=[file for file in (state/'primer/tenants.json',state/'ops/tenants.json') if file.exists()]
            projections=[tenant_projection(document(file),m['tenants']) for file in candidates]
            require(projections and all(value==projections[0] for value in projections),'M7_PRIMER_OUTPUT_CONFLICT');write(target/'tenants.private.json',projections[0])
            fingerprint=json.loads(command(['node',HERE/'fingerprint.cjs',source,pair['core'],state/'primer/config.json',str(m['tenants'])]))
            m['settingsFingerprint']=fingerprint;m['profileSelection']=profile_provenance.identity(fingerprint,m['diagnostics'],config);m['restartRoles']=service_roster(config)
            write(target/'owner.json',m);write(target/'generator-provenance.json',m['generator']);write(target/'deploy-before-host.json',fixture_inventory(m));verify(target,m)
            print('M7_EXISTING_FIXTURE_BOUND_NO_RESOURCE_CHANGE')
    except Exception as error:
        write(target/'attach-failure.json',{'status':'FAILED','code':str(error) if re.fullmatch(r'M7_[A-Z_]+',str(error)) else 'M7_ATTACH_REFUSED','resourcesChanged':False});raise


def prepare_image_inputs(args):
    # Source-driven discovery uses existing immutable images. Refuse stale
    # candidates before creating a worktree or installing its dependencies.
    # Build-after-prepare profiles retain their existing admission at deploy.
    if args.profile!='pgstream-sample' or getattr(args,'run_purpose','acceptance')!='discovery':return None
    selected=image({'pair':{'core':args.core_commit,'deploy':args.deploy_commit},'image':args.image,
                    'imageId':getattr(args,'image_id',None) or args.image})
    postgres=json.loads(command(['docker','image','inspect',args.postgres_image]))[0]
    require(postgres['Id']==args.postgres_image,'M7_POSTGRES_IMAGE_CHANGED')
    return {'appImageId':selected,'postgresImageId':postgres['Id'],'scope':'existing image identity and source labels only; runtime preflight still required'}


def discovery_source_features(repo, core_commit, static=False):
    commit(repo,core_commit)
    progress_contract=json.loads(git(repo,"show",core_commit+":lib/server/internal-api/contracts/evaluator-inspection.json"))
    require(progress_contract.get("version")== (3 if static else 2),"M7_EVALUATOR_PROGRESS_SOURCE_REQUIRED")
    due=progress_contract['operations']['inspectEvaluator']['response']['properties']['tenants']['items']
    require(all(key in due.get('properties',{}) and key in due.get('required',[]) for key in ('dueAt','dueReason')),'M7_EVALUATOR_DUE_SOURCE_REQUIRED')
    require('jobs' in due.get('properties',{}) and 'jobs' in due.get('required',[]),'M7_EVALUATOR_IDLE_SOURCE_REQUIRED')


def discovery_source_preflight(d,m):
    """Execute the paired producer and core's published loaders; no services start.

    This is deliberately rechecked, not a reusable admission receipt. Existing
    authorization, build verification and dependency custody remain authoritative.
    Historical attachment manifests may obtain deployRepository only from the
    build verifier's checked overlay marker; original captures remain unchanged.
    """
    verify(d,m)
    core_repo=m.get('coreRepository') or d/'core'
    marker=document(d/'core/deploy/multitenant/.overlay.json')
    deploy_repo=m.get('deployRepository') or marker.get('deployRepository')
    require(deploy_repo and marker.get('deployCommit')==m['pair']['deploy'] and
            str(Path(deploy_repo).resolve())==str(Path(marker['deployRepository']).resolve()),'M7_DEPLOY_SOURCE_REQUIRED')
    commit(core_repo,m['pair']['core']);commit(deploy_repo,m['pair']['deploy'])
    discovery_source_features(core_repo,m['pair']['core'],static=bool(m.get('staticTopology')))
    if m.get('staticTopology'):static_topology.verify_source(sys.modules[__name__],m,core_repo,deploy_repo)
    if m.get('pgstreamTopology')==stream_topology.EXTERNAL:
        stream_topology.verify_source(m,json.loads(git(core_repo,'show',m['pair']['core']+':lib/server/serve/plan-contract/schema/evaluator.schema.json')))
    image(m)
    pg=json.loads(command(['docker','image','inspect',m['postgresImageId']]))[0]
    require(pg['Id']==m['postgresImageId'],'M7_POSTGRES_IMAGE_CHANGED')
    verify_generator(d,m)
    with private_commands(d/'source-contract-checks'/uuid.uuid4().hex):
        with command_deadline(min(time.time()+120,_COMMAND_DEADLINE.get() or float('inf'))):
            return discovery_source_contract(d,m,core_repo,deploy_repo)


def preparation_environment(m):
    # Static overlays pin seed counts during prepare, before .env is appended.
    return {'NS_API_REPLICAS': str(m['replicas']), 'NS_DEMO_TENANTS': str(m['tenants']),
            **static_topology.environment(m)}


def discovery_source_contract(d,m,core_repo,deploy_repo):
    """Paired deployment generator to published core schema and real loaders."""
    import tempfile
    # Archive the actual Git objects, never an unchecked worktree or an edited
    # copy of the plan. Both executables come from the exact configured pair.
    commissioning_wal.verify_source(sys.modules[__name__],m,core_repo,deploy_repo)
    with tempfile.TemporaryDirectory(prefix='m7-source-contract-') as temporary:
        scratch=Path(temporary);core=scratch/'core';core.mkdir()
        command(['tar','-x','-C',core],input=command(['git','-C',core_repo,'archive',m['pair']['core'],'bin','lib','migrations','package.json'],binary=True))
        overlay=core/'deploy/multitenant';overlay.mkdir(parents=True,exist_ok=True)
        command(['tar','-x','-C',overlay],input=command(['git','-C',deploy_repo,'archive',m['pair']['deploy']+':bindings/compose/multitenant'],binary=True))
        tools=core/'tools';tools.mkdir(exist_ok=True)
        producer=tools/'prospective-plan-documents.js'
        producer.write_text(git(deploy_repo,'show',m['pair']['deploy']+':tools/prospective-plan-documents.js'))
        (core/'node_modules').symlink_to(d/'dependencies/node_modules',target_is_directory=True)
        env=runtime_env({'NS_PGSTREAM':'1',**preparation_environment(m)})
        if m.get('staticTopology'):
            static_topology.verify_source(sys.modules[__name__],m,core_repo,deploy_repo)
            # Use the ordinary product generator; the historical convenience
            # generated() wrapper explicitly refuses static realtime.
            code = "const p=require('./deploy/multitenant/config'),l=p.layout();const urls=Object.fromEntries(Object.keys(l.roles).map(k=>[k,'postgres://'+l.roles[k]+':placeholder@postgres:5432/nightscout_compose_test']));const docs=p.documents({layout:l,urls,tokens:[],publicKeys:[],managementKeys:[],vaultAddress:'https://vault:8200',registryMode:true,realtimeOwnership:require('./deploy/multitenant/realtime-workers').initial(require('./deploy/multitenant/realtime-workers').selection())});console.log(JSON.stringify(require('./tools/prospective-plan-documents').documentSet(docs)));"
            documents=command(['node','-e',code],cwd=core,env=env,timeout=30)
            static_topology.verify_documents(m,json.loads(documents))
        else:documents=command(['node',producer],cwd=core,env=env,timeout=30)
        source=scratch/'documents.json';source.write_text(documents)
        result=json.loads(command(['node',core/'bin/nightscout.js','plan','check',source],cwd=core,env=env,timeout=30))
        require(result.get('ok') is True,'M7_DISCOVERY_SOURCE_CONTRACT_REFUSED')
    return result


def fixture_project(args,nonce):
    selected=getattr(args,'fixture_project',None)
    require(selected is None or isinstance(selected,str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}',selected),'M7_FIXTURE_PROJECT_INVALID')
    return selected or 'nsm7-'+nonce[:12]+'-n'+str(args.tenants)+'-a'+str(args.replicas)


def unused_project_namespace(project):
    # Explicit fixture names must not adopt an orphaned peer volume/network.
    for kind in ('network','volume'):
        names=command(['docker',kind,'ls','--format','{{.Name}}']).splitlines()
        require(not any(name.startswith(project+'_') for name in names),'M7_PROJECT_NAMESPACE_EXISTS')


def resource_cpu_failure(error):
    if re.fullmatch(r'M7_DIAGNOSTIC_RESOURCE_CPU_UNREPRESENTABLE:services\.[a-z0-9-]+\.millicpus',str(error)):
        print(json.dumps({'kind':'resource-cpu-preflight','verdict':'FAIL','code':str(error),
                          'diagnostic':error.diagnostic},sort_keys=True,allow_nan=False),flush=True)


def resource_cpu_preflight(selected, read=None, *, roles=None, observation=None):
    try:
        return diagnostic_resources.fresh_cpu_preflight(selected,read,roles=roles,observation=observation)
    except RuntimeError as error:
        resource_cpu_failure(error)
        raise


def selected_resources_profile(args, *, inspect_runtime=False):
    named=getattr(args,'diagnostic_resource_profile',None)
    explicit=getattr(args,'diagnostic_resource_allocation',None)
    require(named is None or explicit is None,'M7_DIAGNOSTIC_RESOURCE_SELECTION_AMBIGUOUS')
    selected=diagnostic_resources.selection(explicit if explicit is not None else named)
    if inspect_runtime:
        # Observe early; the rendered deployment plan later binds the actual
        # actor scope. Merely carrying an ops template does not execute it.
        args.diagnostic_cpu_preflight=resource_cpu_preflight(selected,
            lambda argv:command(argv,phase='resource-cpu-preflight'),roles=())
    return selected


def prepare(args):
    if args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery' and getattr(args,'backend_subnet',None) and getattr(args,'edge_subnet',None):
        from run_configuration import validate_prepare
        validate_prepare(args)
    selected=selected_resources_profile(args,inspect_runtime=True)
    require(not selected or args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery','M7_DIAGNOSTIC_RESOURCE_DISCOVERY_ONLY')
    require(not selected or getattr(args,'generator_dependencies',None),'M7_DIAGNOSTIC_DEPENDENCIES_REQUIRED')
    require(not getattr(args,'vault_refusal_control',None) or selected,'M7_VAULT_CONTROL_RESOURCE_PROFILE_REQUIRED')
    local_observer = bool(node_observation.option(args) or api_warm_cause.option(args))
    require(not local_observer or (selected and document(args.freeze).get('version')==2),
            'M7_LOCAL_OBSERVER_RECEIPT')
    diagnostic_resources.configure(selected)
    primer_concurrency(getattr(args,"primer_concurrency",1))
    commissioning_wal.option(args)
    fixture_project(args,'0'*32)
    ack_budget=stream_topology.ack_option(args)
    preload=preload_convergence.option(args)
    profile_provenance.selection(getattr(args,'diagnostics','off'),getattr(args,'diagnostics_interval_ms',5000))
    require(bool(getattr(args,"backend_subnet",None))==bool(getattr(args,"edge_subnet",None)),"M7_EXPLICIT_SUBNET_PAIR_REQUIRED")
    require(os.getuid()==1000 and os.getgid()==1000,"M7_HOST_RUNTIME_UID_REQUIRED")
    if args.profile=="pgstream-sample":
        require((workload_inputs.tenants(args.tenants) if args.run_purpose=="discovery" else type(args.tenants) is int and 1<=args.tenants<=10000) and (args.replicas==1 or static_topology.option(args)),"M7_SMALL_SAMPLE_LIMIT")
        require(re.fullmatch(r"sha256:[a-f0-9]{64}",getattr(args,"postgres_image",None) or ""),"M7_PGSTREAM_POSTGRES_IMAGE_REQUIRED")
    if args.profile=="fresh-image-diagnostic":require(1<=args.tenants<=10 and 1<=args.replicas<=2,"M7_DIAGNOSTIC_LIMIT_INVALID")
    require((workload_inputs.tenants(args.tenants) if args.profile=="pgstream-sample" and args.run_purpose=="discovery" else type(args.tenants) is int and 1<=args.tenants<=10000) and (discovery_api_replicas(args.replicas) if args.profile=="pgstream-sample" and args.run_purpose=="discovery" else type(args.replicas) is int and args.replicas in REPLICAS) and args.profile in CADENCE, "M7_CAPACITY_CELL_INVALID")
    require(math.isfinite(args.quiet_load) and 0 <= args.quiet_load <= (os.cpu_count() or 1), "M7_QUIET_BOUND_INVALID")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{1,255}", args.image), "M7_IMAGE_REFERENCE_INVALID")
    target = Path(args.directory).resolve()
    require(re.fullmatch(r"/[A-Za-z0-9_./-]+", str(target)), "M7_PRIVATE_PATH_INVALID")
    require(not target.exists() and not any(p in (".git", "node_modules") for p in target.parts), "M7_TARGET_MUST_BE_NEW")
    for repo in (args.core_repo, args.deploy_repo):
        commit(repo, args.core_commit if repo == args.core_repo else args.deploy_commit)
    discovery_source_features(args.core_repo,args.core_commit,static=bool(static_topology.option(args)))
    if getattr(args,'pgstream_topology',stream_topology.COLOCATED)==stream_topology.EXTERNAL:
        stream_topology.verify_source({'pgstreamTopology':args.pgstream_topology},json.loads(git(args.core_repo,'show',args.core_commit+':lib/server/serve/plan-contract/schema/evaluator.schema.json')))
    static_selection=static_topology.option(args)
    if static_selection:
        static_topology.verify_source(sys.modules[__name__],{**static_selection,'pair':{'core':args.core_commit,'deploy':args.deploy_commit},'profile':args.profile,'runPurpose':args.run_purpose,'pgstreamTopology':args.pgstream_topology,'completionContract':args.completion_contract,'replicas':args.replicas},args.core_repo,args.deploy_repo)
    pinned = instrument()
    if getattr(args,'measurement_mode','accepted')=='unaccepted' or (args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery'):
        candidate={'profile':args.profile,'tenants':args.tenants,'replicas':args.replicas,'pair':{'core':args.core_commit,'deploy':args.deploy_commit},'instrument':pinned,
                   'cadence':cadence_options(args),'runPurpose':getattr(args,'run_purpose','acceptance'),'measurementMode':args.measurement_mode,'runId':getattr(args,'run_id',None),'imageId':getattr(args,'image_id',None) or args.image,'maximumRunMinutes':getattr(args,'maximum_run_minutes',180),
                   'diagnostics':profile_provenance.selection(getattr(args,'diagnostics','off'),getattr(args,'diagnostics_interval_ms',5000)),**static_selection,**({'pgstreamTopology':args.pgstream_topology,'completionContract':args.completion_contract} if static_selection else {})}
        candidate.update(commissioning_wal.option(args))
        candidate.update(ack_budget)
        candidate.update(preload)
        if preload:
            candidate['completionContract'] = args.completion_contract
        if ack_budget:
            candidate['pgstreamTopology']=args.pgstream_topology
        selection=serial_exchange_selection(args)
        if selection is not None:candidate['serialExchangeDiagnostic']=selection
        serial_exchange_receipt(candidate,document(args.freeze))
        if document(args.freeze).get('version')==2:
            from run_configuration import from_args
            candidate['runConfiguration']=from_args(args,pinned['sha256'])
            args.resolved_configuration=candidate['runConfiguration']
        receipt_scope(candidate,document(args.freeze),'deploy')
        if document(args.freeze).get('version')==2:
            from run_configuration import namespace_preflight
            args.namespace_preflight=namespace_preflight(args)
    args.dependency_qualification=qualified_dependencies(args)
    args.image_input_preflight=prepare_image_inputs(args)
    target.mkdir(parents=True, mode=0o700)
    try:
        with private_commands(target/'prepare-commands'):
            return prepare_staged(args,target,pinned)
    except Exception as error:
        text=str(error)
        write(target/'prepare-failure.json',{'kind':'source-preparation-failure','prepared':False,'pair':{'core':args.core_commit,'deploy':args.deploy_commit},
              'instrument':pinned['sha256'],'publicCode':text if re.fullmatch(r'M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?',text) else 'M7_PREPARE_REFUSED',
              'privateArtifacts':'prepare-commands','fullAcceptance':'NOT_RUN','capacity':'NO-MEASUREMENT'})
        raise


def prepare_staged(args,target,pinned):
    nonce = uuid.uuid4().hex
    m = {"version": 1, "directory": str(target), "owner": nonce, "project": fixture_project(args,nonce),
         "pair": {"core": args.core_commit, "deploy": args.deploy_commit}, "coreRepository": str(Path(args.core_repo).resolve()),
         "deployRepository": str(Path(args.deploy_repo).resolve()), "instrument": pinned, "image": args.image,
         "tenants": args.tenants, "replicas": args.replicas, "port": port(), "quietLoad": args.quiet_load,
         "freeze": str(Path(args.freeze).resolve()), "profile":args.profile,"cadence":cadence_options(args),"completionContract":getattr(args,"completion_contract",None),"jwtSetupConcurrency":jwt_setup_concurrency(getattr(args,"jwt_setup_concurrency",1), getattr(args,"run_purpose","acceptance")=="discovery")}
    cpu_preflight=getattr(args,'diagnostic_cpu_preflight',None)
    if cpu_preflight and cpu_preflight.get('verdict')!='NOT_APPLICABLE':m['cpuPrecisionPreflight']=cpu_preflight
    m.update(static_topology.option(args))
    if getattr(args,'namespace_preflight',None):m['namespacePreflight']=args.namespace_preflight
    if getattr(args,'vault_refusal_control',None):m['vaultRefusalControl']=args.vault_refusal_control
    if getattr(args,'dependency_qualification',None) is not None:m['dependencyReuse']=args.dependency_qualification
    selection=serial_exchange_selection(args)
    if selection is not None:m['serialExchangeDiagnostic']=selection
    if getattr(args,'pgstream_topology',stream_topology.COLOCATED)!=stream_topology.COLOCATED:m['pgstreamTopology']=args.pgstream_topology
    m["primerConcurrency"]=primer_concurrency(getattr(args,"primer_concurrency",1))
    m.update(commissioning_wal.option(args))
    m.update(stream_topology.ack_option(args))
    m.update(preload_convergence.option(args))
    if getattr(args,'image_input_preflight',None):m['imageInputPreflight']=args.image_input_preflight
    if getattr(args,"run_purpose","acceptance")=="discovery":m["runPurpose"]="discovery"
    select_opportunities(args,m)
    evaluator_catchup.select(args,m)
    m["diagnostics"]=profile_provenance.selection(getattr(args,"diagnostics","off"),getattr(args,"diagnostics_interval_ms",5000))
    m['measurementMode']=getattr(args,'measurement_mode','accepted')
    if args.profile=='pgstream-sample' and m.get('runPurpose')=='discovery':
        m['imageId']=getattr(args,'image_id',None) or args.image
        if getattr(args,'resolved_configuration',None) is not None:
            m['runConfiguration']=args.resolved_configuration
        frozen(m,'deploy')
    if m['measurementMode']=='unaccepted':
        m.update(runId=args.run_id,imageId=args.image_id,maximumRunMinutes=args.maximum_run_minutes)
        frozen(m,'deploy')
    m["hostIdentity"]=host_identity(inventory(nonce))
    write(target / "owner.json", m)
    # Refuse preexisting project resources; no broad cleanup/nearest substitute.
    require(not resources(m), "M7_PROJECT_EXISTS")
    if getattr(args,'fixture_project',None):unused_project_namespace(m['project'])
    core = target / "core"
    git(args.core_repo, "worktree", "add", "--detach", str(core), args.core_commit)
    overlay = core / "deploy/multitenant"
    require(not overlay.is_symlink() and (not overlay.exists() or overlay.is_dir()),'M7_DEPLOY_OVERLAY_PATH_REFUSED')
    if overlay.exists():shutil.rmtree(overlay)
    overlay.mkdir(parents=True)
    archive = command(["git", "-C", m['deployRepository'], "archive", args.deploy_commit + ":bindings/compose/multitenant"],binary=True,phase="deploy-archive")
    command(["tar", "-x", "-C", overlay], input=archive)
    write(overlay / ".overlay.json", {"version": 1, "deployRepository": m["deployRepository"], "deployCommit": args.deploy_commit})
    for name in ("commission-restore.js","publish-primer.js"):
        require((overlay/name).is_file(),"M7_BINDING_COMMISSION_CAPABILITY_MISSING")
    # Binding preparation imports source modules (including js-yaml). Install
    # the owned lockfile context before invoking it, not after bootstrap.
    setup_generator(target,m)
    env = runtime_env({**preparation_environment(m),**({"NS_PGSTREAM":"1","NS_POSTGRES_IMAGE":args.postgres_image} if args.profile=="pgstream-sample" else {})})
    edge_budget=diagnostic_resources.edge_worker_budget(selected_resources_profile(args))
    if edge_budget is not None:
        explicit_edge=edge_budget['source']=='explicit-resource-allocation-v1'
        # The source renderer keeps its reference validation. An authored
        # allocation projects only the two existing mounted numeric fields.
        env['NS_EDGE_WORKER_PROCESSES']='1' if explicit_edge else str(edge_budget['workerProcesses'])
        if explicit_edge:env['NS_EDGE_WORKER_CONNECTIONS']='16384'
    networks=["--backend-subnet",args.backend_subnet,"--edge-subnet",args.edge_subnet] if getattr(args,"backend_subnet",None) else []
    command(["node", overlay / "prepare.js", "--state", target / "state", "--port", str(m["port"]), "--project", m["project"],*networks], cwd=overlay,env=env,phase="product-prepare")
    if edge_budget is not None:
        edge_file=target/'state/edge/nginx.conf'
        if explicit_edge:edge_file.write_text(project_edge_workers(edge_file.read_text(),edge_budget))
        verify_edge_workers(edge_file.read_text(),edge_budget)
        m['edgeWorkerBudget']={**edge_budget,'configurationSha256':digest(edge_file)}
    # Keep the source binding path stable: guards and optional controller digests
    # refer to this exact .env. Compose also reads the private cell copy.
    shutil.copyfile(overlay / ".env", target / "env")
    with (target / "env").open("a") as output:
        output.write("NS_DEMO_IMAGE=" + args.image + "\nNS_DEMO_TENANTS=" + str(args.tenants) + "\nNS_API_REPLICAS=" + str(args.replicas) + "\n")
    if args.profile=="pgstream-sample":
        with (target/"env").open("a") as output:output.write("NS_POSTGRES_IMAGE="+args.postgres_image+"\n")
        m["postgresImageId"]=args.postgres_image
    shutil.copyfile(target / "env", overlay / ".env")
    source_files = [overlay / "compose.yaml", *sorted((target / "state").glob("compose.*.yaml"))]
    base_args = ["docker", "compose", "-p", m["project"], "--env-file", target / "env"]
    for file in source_files:
        base_args.extend(["-f", file])
    config = json.loads(command([*base_args, "--profile", "ops", "config", "--format", "json"],phase="compose-config"))
    serving_mounts(config)
    stream_topology.verify_config(m,config)
    static_topology.verify_config(m,config)
    measurement_topology(m,config)
    profile_provenance.select_environment(config,m["diagnostics"])
    platform_startup_config(config,target,m,getattr(args,"tenant_readiness",None))
    for spec in config["services"].values():
        for volume in spec.get("volumes", []):
            if volume.get("type")=="bind":
                require(Path(volume["source"]).resolve().is_relative_to(target / "state"), "M7_FOREIGN_STATE_MOUNT_REFUSED")
    required=("postgres","vault","admin","primer","api","realtime","evaluator","tenant-admin","ui","nginx")+(() if args.profile=="pgstream-sample" else ("feed-reader",))
    require(all(name in config["services"] for name in required),"M7_BINDING_CAPABILITY_MISSING")
    # Ordinary runtime source stays in its paired image. The explicit clinical
    # diagnostic may later stage one separately attested sender executable;
    # bootstrap and application libraries never receive source overlays.
    for name, spec in config["services"].items():
        spec.setdefault("labels", {})[OWNER] = nonce
    for kind in ("volumes", "networks"):
        for spec in config.get(kind, {}).values():
            require(not spec.get("external") and spec.get("name", "").startswith(m["project"]+"_"), "M7_EXTERNAL_OR_SHARED_RESOURCE_REFUSED")
            spec.setdefault("labels", {})[OWNER] = nonce
    pg = config["services"]["postgres"]
    require(isinstance(pg.get("command"), list) and pg["command"][0] == "postgres", "M7_POSTGRES_COMMAND_SHAPE_CHANGED")
    commissioning_wal.install(config,m)
    pg["command"].extend(["-c", "shared_preload_libraries=pg_stat_statements", "-c", "pg_stat_statements.track=top", "-c", "track_io_timing=on"])
    require(not any("shared_preload_libraries" in str(x) for x in pg["command"][:-6]), "M7_POSTGRES_PRELOAD_ALREADY_SELECTED")
    selected_resources=selected_resources_profile(args)
    config=diagnostic_resources.overlay(config,selected_resources)
    if isinstance(selected_resources,dict):
        observation=resource_cpu_preflight(selected_resources,roles=(),
            observation=getattr(args,'diagnostic_cpu_preflight',None))
        if observation.get('runtimePrecision')=='runc-systemd-whole-percent-v1':
            planned=deployment_plan(config,pgstream=m.get('profile')=='pgstream-sample',
                primer_concurrency_value=m.get('primerConcurrency',1),platform_verification=bool(m.get('platformStartup')))
            roles=set().union(*(diagnostic_resources.compose_actor_roles(argv,config)
                                for _,kind,argv in planned if kind=='compose'))
            observation=resource_cpu_preflight(selected_resources,roles=roles,observation=observation)
        m['cpuPrecisionPreflight']=observation
    clinical_timeline.install(config,target,m,getattr(args,'clinical_intake_timeline','off'),getattr(args,'clinical_sender_binary',None),getattr(args,'clinical_sender_receipt',None),getattr(args,'clinical_intake_targets',None))
    revision_witness.install(config,target,m,getattr(args,'revision_witness_targets',None))
    api_cause.install(config,target,m,getattr(args,'api_cause_observation','off')=='on')
    api_warm_cause.install(config,target,m,api_warm_cause.option(args).get('apiWarmCauseMode','off'))
    m['servingInstances'] = role_instances.roster(config,m['replicas'])
    node_observation.install(config,target,m,node_observation.option(args).get('nodeObservationMode','off'))
    if m.get('runPurpose') == 'discovery':
        if selected_resources is None:
            config, removed = diagnostic_resources.uncapped_compose(config)
            write(target/'compose-limits-projection.json', {'removedReferenceFields': removed})
        m['composeLimitMode'] = diagnostic_resources.compose_limit_mode(config, selected_resources)
    if selected_resources is not None or m.get('runPurpose') == 'discovery':
        config=seal_diagnostic_images(config,m)
    record=diagnostic_resources.selected_record(config,selected_resources)
    if record is not None:
        m['diagnosticResources']=record
        diagnostic_resources._ACTIVE.observe=lambda:diagnostic_resource_rows(m)
    write(target / "frozen.compose.json", config)
    m["prepared"] = True
    m['environmentSha256']=digest(target/'env')
    m["sourceCompose"] = {str(f.relative_to(target)): digest(f) for f in source_files}
    m["composeSha256"] = digest(target / "frozen.compose.json")
    shutil.copyfile(HERE / "restart.cjs", target / "restart.cjs")
    m["restartHelperSha256"]=digest(target / "restart.cjs")
    m["probe"] = generate(ROOT, target / "probe.js",serial_exchange=bool(m.get("serialExchangeDiagnostic")))
    m["workload"] = generate_workload(ROOT, target / "k6/workload.js")
    write(target / "owner.json", m)
    print(json.dumps({"prepared": m["project"], "pair": m["pair"], "tenants": args.tenants, "replicas": args.replicas}))


def verify(d, m, teardown=False):
    require(host_identity(fixture_inventory(m))==m["hostIdentity"],"M7_HOST_IDENTITY_CHANGED")
    require(git(d / "core", "rev-parse", "HEAD") == m["pair"]["core"], "M7_OWN_CORE_HEAD_CHANGED")
    require(digest(d / "frozen.compose.json") == m["composeSha256"], "M7_COMPOSE_CHANGED")
    if m.get('composeLimitMode') == 'uncapped-services':
        diagnostic_resources.compose_limit_mode(document(d/'frozen.compose.json'), None)
    if m.get("environmentSha256"):
        require(digest(d/"env")==m["environmentSha256"] and digest(d/"core/deploy/multitenant/.env")==m["environmentSha256"],"M7_ENVIRONMENT_CHANGED")
    if m.get('edgeWorkerBudget'):
        edge_file=d/'state/edge/nginx.conf'
        require(digest(edge_file)==m['edgeWorkerBudget']['configurationSha256'],'M7_EDGE_CONFIGURATION_CHANGED')
        verify_edge_workers(edge_file.read_text(),m['edgeWorkerBudget'])
    stream_topology.verify_config(m,document(d/"frozen.compose.json"))
    if m.get('pgstreamNotifierAckWire') and not teardown:
        stream_topology.verify_ack_budget(d,m,document(d/'frozen.compose.json')['services']['pgstream']['volumes'])
    commissioning_wal.verify(document(d/"frozen.compose.json"),m)
    platform_startup_config(document(d/"frozen.compose.json"),d,m,verify=True)
    clinical_timeline.verify(document(d/"frozen.compose.json"),d,m,teardown=teardown)
    revision_witness.verify(document(d/"frozen.compose.json"),d,m)
    api_cause.verify(document(d/"frozen.compose.json"),d,m)
    api_warm_cause.verify(document(d/"frozen.compose.json"),d,m)
    node_observation.verify(document(d/"frozen.compose.json"),d,m)
    static_topology.verify_config(m,document(d/"frozen.compose.json"))
    measurement_topology(m,document(d/"frozen.compose.json"))
    profile_provenance.verify_environment(document(d/"frozen.compose.json"),m["diagnostics"])
    if 'servingInstances' in m:
        require(role_instances.roster(document(d/'frozen.compose.json'),m['replicas']) == m['servingInstances'], 'M7_INSTANCE_FROZEN_ROSTER_CHANGED')
    profile_provenance.state_environment(d/"state",document(d/"frozen.compose.json"),m["diagnostics"])
    require(digest(d / "restart.cjs")==m["restartHelperSha256"], "M7_RESTART_HELPER_CHANGED")
    require(digest(d / "probe.js") == m["probe"]["adaptedSha256"], "M7_PROBE_CHANGED")
    require(m['probe'].get('recoveryHelpers') and all(digest(d/name)==sha for name,sha in m['probe']['recoveryHelpers'].items()),'M7_RECOVERY_HELPER_CHANGED')
    require(digest(d / "k6/workload.js") == m["workload"]["adaptedSha256"], "M7_WORKLOAD_CHANGED")
    for file, sha in m["sourceCompose"].items():
        require(digest(d / file) == sha, "M7_SOURCE_COMPOSE_CHANGED")
    # Shipping build admission checks every input against the two commits.
    code = "require('./deploy/multitenant/build').assertCleanSource(process.cwd(),process.argv[1])"
    command(["node", "-e", code, m["pair"]["core"]], cwd=d / "core")
    assert_owned(m)


def psql(d, sql, database="postgres", *, timeout=None):
    return compose(d, "exec", "-T", "postgres", "psql", "-X", "-q", "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database, input=sql.encode(),**({'timeout':timeout} if timeout is not None else {}))


def service_roster(config):
    return [name for name, spec in config["services"].items()
            if isinstance(spec.get("command"), list) and spec["command"][-1:] and (spec["command"][-1] in ("api", "realtime", "evaluator", "tenant-admin") or name=="pgstream" and spec["command"]==stream_topology.EXTERNAL_COMMAND or name=="socket-edge" and spec["command"]==static_topology.EDGE_COMMAND)]


def primer_concurrency(value):
    require(type(value) is int and 1<=value<=32,"M7_PRIMER_CONCURRENCY_INVALID")
    return value


def application_database(d):
    # The frozen canonical Compose contract selects the application's database.
    # psql's postgres default is only suitable for server-level instrumentation.
    value=document(d/"frozen.compose.json")["services"]["postgres"].get("environment",{}).get("POSTGRES_DB")
    require(isinstance(value,str) and re.fullmatch(r"[a-z][a-z0-9_]{0,62}",value),"M7_APPLICATION_DATABASE_REQUIRED")
    return value


def primer_counts(d,m):
    """Read independent custody and database counts before workers or load start."""
    state=d/"state/primer"
    seed=document(state/"config.json")["seed"]
    expected={row["id"] for row in seed}
    require(len(seed)==len(expected)==m["tenants"],"M7_PRIMER_SEED_COUNT")
    issued=document(state/"provisioned.json")
    accepted=document(state/"tenants.json")
    tenant_projection(accepted,m["tenants"])
    complete=document(state/"primed.json")
    uncertain=state/"entry-requests.json"
    require(not uncertain.exists() or document(uncertain)=={"version":1,"tenants":{}},"M7_PRIMER_ENTRY_UNCERTAIN")
    require(len(issued)==len(expected) and {row["id"] for row in issued}==expected and
            {row["id"] for row in accepted["tenants"]}==expected and
            complete=={"state":"synthetic-data-primed","tenants":len(expected)},"M7_PRIMER_CUSTODY_COUNT")
    raw=psql(d,"SELECT tenant_id::text,count(*) FROM nsdemo_entries.entries WHERE doc->>'device'='synthetic-compose-demo' GROUP BY 1;",application_database(d))
    stored={}
    for line in raw.splitlines():
        tenant,count=line.split("\t")
        require(tenant not in stored,"M7_PRIMER_DATABASE_DUPLICATE_GROUP")
        stored[tenant]=int(count)
    ok=set(stored)==expected and all(count==1 for count in stored.values())
    result={"verdict":"PASS" if ok else "FAIL","requestedTenants":len(seed),"provisionedTenants":len(issued),
            "acceptedAndSavedTenants":len(accepted["tenants"]),"persistedTenants":len(stored),
            "persistedEntries":sum(stored.values()),"perTenantEntries":stored,
            "scope":"PRIVATE synthetic commissioning only; accepted means HTTP success plus saved custody; SQL is independent"}
    write(d/"primer-counts.private.json",result)
    require(ok,"M7_PRIMER_DATABASE_COUNT_MISMATCH")
    return result


def platform_startup_config(config,d,m,readiness=None,verify=False):
    helper=Path(d)/'core/deploy/multitenant/platform-startup.js'
    record=m.get('platformStartup')
    if verify:
        if record is None:
            require(not helper.is_file(),'M7_PLATFORM_STARTUP_UNBOUND')
            return
        require(helper.is_file() and digest(helper)==record['helperSha256']
                and record['readiness'] in ('serve','all'),'M7_PLATFORM_STARTUP_CHANGED')
        readiness=record['readiness']
    elif not helper.is_file():
        require(readiness is None,'M7_PLATFORM_STARTUP_CAPABILITY_MISSING')
        return
    else:
        require(readiness in ('serve','all'),'M7_PLATFORM_STARTUP_READINESS_REQUIRED')
        m['platformStartup']={'kind':'admin-verification-v1','readiness':readiness,'helperSha256':digest(helper)}
        m['tenantReadiness']=readiness
    roles=[]
    for role,spec in config['services'].items():
        if role in role_instances.FAMILIES or any(role.startswith(family+'-') for family in role_instances.FAMILIES):
            roles.append(role_instances.instance(role)['role'])
            env=spec.setdefault('environment',{})
            if verify:require(env.get('NS_TENANT_READINESS')==readiness,'M7_PLATFORM_STARTUP_READINESS_CHANGED')
            else:env['NS_TENANT_READINESS']=readiness
    require(set(roles)=={'api','evaluator','realtime'},'M7_PLATFORM_STARTUP_ROLES_REQUIRED')


def deployment_plan(config,pgstream=False,primer_concurrency_value=1,platform_verification=False):
    concurrency=primer_concurrency(primer_concurrency_value)
    prime_options=["--concurrency",str(concurrency)] if concurrency!=1 else []
    roster=service_roster(config)
    apis=[name for name in roster if config["services"][name]["command"][-1]=="api"]
    remaining=[name for name in roster if name not in apis]
    start=["up","-d","--no-build","--pull","never","--wait","--wait-timeout","1200"]
    return [
        ("infrastructure","compose",[*start,"postgres","vault"]),
        ("bootstrap","compose",["--profile","ops","run","--rm","bootstrap"]),
        ("admin-feed","compose",[*start,"admin",*(["feed-reader"] if not pgstream else [])]),
        ("provision","compose",["--profile","ops","run","--rm","primer","node","deploy/multitenant/prime.js","provision"]),
        ("commission","compose",["--profile","ops","run","--rm","--no-deps","bootstrap","node","deploy/multitenant/commission-restore.js"]),
        *(([("platform-verify","compose",["--profile","ops","run","--rm","--no-deps","primer","node","deploy/multitenant/platform-verify.js"])]) if platform_verification else []),
        ("apis","compose",[*start,*apis]),
        ("prime","compose",["--profile","ops","run","--rm","--no-deps","primer","node","deploy/multitenant/prime.js","prime",*prime_options]),
        ("publish-primer","local",["publish-primer.js"]),
        ("remaining-roles","compose",[*start,*remaining,"ui","nginx"])]


def generator_tools():
    result={}
    for name in ("node","npm"):
        found=shutil.which(name);require(found,"M7_GENERATOR_TOOL_MISSING:"+name)
        executable=Path(found).resolve()
        result[name]={"path":str(executable),"sha256":digest(executable),"version":command([executable,"--version"]).strip()}
    return result


def generator_client(d,tools):
    # createRequire bypasses ambient NODE_PATH and proves the actual stock SDK
    # resolves inside this cell, rather than a peer checkout or fixture factory.
    script="""const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=fs.realpathSync(process.argv[1]),r=createRequire(path.join(root,'package.json'));
const entry=fs.realpathSync(r.resolve('socket.io-client'));
if(!entry.startsWith(path.join(root,'node_modules')+path.sep))throw Error('M7_GENERATOR_CLIENT_OUTSIDE_OWN_TREE');
const client=r('socket.io-client');if(typeof client.io!=='function')throw Error('M7_GENERATOR_CLIENT_INVALID');
console.log(JSON.stringify({entry,version:r('socket.io-client/package.json').version}));"""
    value=json.loads(command([tools['node']['path'],'-e',script,d/'dependencies'],phase='generator-client-preflight'))
    value['entrySha256']=digest(value['entry'])
    return value


def dependency_context(root, dependencies, names):
    code=(HERE/'execution-context.cjs').read_text()+"\nconsole.log(JSON.stringify(module.exports.inspect(process.argv[1],process.argv[2],JSON.parse(process.argv[3]))));"
    return json.loads(command(['node','-e',code,root,dependencies,json.dumps(names)]))


def attachment_generator(d,source,root,m,owner_file=None):
    # The runtime owner selects the dependency root explicitly. A prepared
    # canonical source may link node_modules to its owned sibling install;
    # never infer that root or relax the stock-client realpath check.
    source=Path(source).resolve();root=Path(root).resolve()
    require(root.is_dir(),'M7_ATTACH_DEPENDENCIES_REQUIRED')
    hashes={}
    for name in ('package.json','package-lock.json'):
        expected=hashlib.sha256(command(['git','-C',source,'show',m['pair']['core']+':'+name],binary=True)).hexdigest()
        require(digest(source/name)==expected,'M7_ATTACH_SOURCE_LOCK_CHANGED')
        require((root/name).is_file() and digest(root/name)==expected,'M7_ATTACH_DEPENDENCY_LOCK_CHANGED')
        hashes[name]=expected
    runtime=None;binding=None
    if owner_file:
        owner_file=Path(owner_file)
        require(owner_file.is_file() and not owner_file.is_symlink(),'M7_ATTACH_RUNTIME_OWNER_REQUIRED')
        runtime=document(owner_file)
        require(isinstance(runtime,dict) and isinstance(runtime.get('directory'),str) and Path(runtime['directory']).is_absolute(),
                'M7_ATTACH_RUNTIME_OWNER_MISMATCH')
        directory=Path(runtime['directory']).resolve()
        require(owner_file.resolve()==directory/'owner.json' and runtime.get('prepared') is True
                and runtime.get('project')==m['project'] and runtime.get('pair')==m['pair']
                and runtime.get('imageId')==m['imageId'] and m.get('runtimeOwnerLabels')==[runtime.get('owner')],
                'M7_ATTACH_RUNTIME_OWNER_MISMATCH')
        require(source==(directory/'core').resolve() and root==(directory/'dependencies').resolve(),'M7_ATTACH_RUNTIME_DEPENDENCY_ROOT')
        prior=runtime.get('generator',{});provenance=directory/'generator-provenance.json'
        require(prior.get('kind') in ('owned-lockfile-install','owned-qualified-dependency-copy') and provenance.is_file() and document(provenance)==prior
                and prior.get('pair')==m['pair'] and prior.get('servingImageId')==m['imageId']
                and prior.get('packageSha256')==hashes['package.json'] and prior.get('lockSha256')==hashes['package-lock.json'],
                'M7_ATTACH_RUNTIME_GENERATOR_CHANGED')
        if prior['kind']=='owned-qualified-dependency-copy':
            qualification=runtime.get('dependencyReuse');ready=root/'dependency-reuse-ready.json'
            require(isinstance(qualification,dict) and prior.get('reuseProvenance',{}).get('qualification')==qualification
                    and ready.is_file() and not ready.is_symlink() and document(ready)==prior['reuseProvenance']
                    and dependency_reuse.tree(root/'node_modules')==qualification.get('tree'),
                    'M7_ATTACH_RUNTIME_DEPENDENCY_COPY_CHANGED')
        binding={'ownerFile':str(owner_file.resolve()),'ownerFileSha256':digest(owner_file),'owner':runtime['owner'],
                 'instrument':runtime['instrument'],'generatorProvenanceSha256':digest(provenance)}
    if runtime and runtime.get('diagnosticResources'):
        require(m.get('diagnosticResources')==runtime['diagnosticResources'],'M7_DIAGNOSTIC_CONFIGURATION_MISMATCH')
        diagnostic_resources.configure(runtime['diagnosticResources']['profile'],document(d/'frozen.compose.json'),
            runtime['diagnosticResources'],observe=lambda:diagnostic_resource_rows(m))
    tools=generator_tools();client=generator_client(d,tools)
    contexts={'generator':dependency_context(root,root/'node_modules',['socket.io-client','pg','js-yaml']),
              'source':dependency_context(source,root/'node_modules',['pg','js-yaml'])}
    if runtime:
        prior=runtime['generator']
        # cwd describes each instrument invocation; retain both observations.
        # Installed roots, tools, package/lock and resolved module bytes must
        # match the runtime owner's original provenance exactly.
        identity=lambda context:{key:value for key,value in context.items() if key!='cwd'}
        require(tools==prior['tools'] and client==prior['client'] and
                all(identity(contexts[kind])==identity(prior['contexts'][kind]) for kind in contexts),
                'M7_ATTACH_RUNTIME_DEPENDENCY_CONTEXT_CHANGED')
    value={'kind':'existing-runtime-owner-lockfile-tree','tools':tools,'pair':m['pair'],
           'packageSha256':hashes['package.json'],'lockSha256':hashes['package-lock.json'],'client':client,
           'contexts':contexts,'servingImageId':m['imageId']}
    if binding:value['runtimeOwner']=binding
    return value


def dependency_run(argv):
    # The reuse module always requests its fixed 128MiB helper cap. The selected
    # resource wrapper owns that identical helper lease/cap; avoid a second flag.
    argv=list(argv)
    if diagnostic_resources._ACTIVE is not None:
        require(len(argv)>1 and argv[1]=='--max-old-space-size=128','M7_DEPENDENCY_REUSE_NODE_CAP_REQUIRED')
        argv.pop(1)
    return command(argv,phase='dependency-reuse-preflight')


def qualified_dependencies(args):
    fields=('generator_dependencies','generator_dependency_receipt','generator_dependency_receipt_sha256')
    values=[getattr(args,key,None) for key in fields]
    preparation=[getattr(args,'generator_dependency_preparation'+suffix,None) for suffix in ('','_sha256','_head')]
    if not any(values) and not any(preparation):return None
    require(all(values) and (not any(preparation) or all(preparation)),'M7_DEPENDENCY_REUSE_SELECTION_INCOMPLETE')
    require(args.profile=='pgstream-sample' and getattr(args,'run_purpose','acceptance')=='discovery','M7_DEPENDENCY_REUSE_DISCOVERY_ONLY')
    for value in [values[2],*([preparation[1]] if any(preparation) else [])]:
        require(re.fullmatch('[a-f0-9]{64}',value or ''),'M7_DEPENDENCY_REUSE_RECEIPT_HASH_REQUIRED')
    if any(preparation):require(SHA.fullmatch(preparation[2] or ''),'M7_DEPENDENCY_REUSE_SOURCE_HEAD_REQUIRED')
    package=command(['git','-C',args.core_repo,'show',args.core_commit+':package.json'],binary=True)
    lock=command(['git','-C',args.core_repo,'show',args.core_commit+':package-lock.json'],binary=True)
    return dependency_reuse.preflight(source=values[0],receipt_path=values[1],receipt_sha256=values[2],
        package_bytes=package,lock_bytes=lock,tools=generator_tools(),run=dependency_run,
        source_preparation={'path':preparation[0],'sha256':preparation[1],'head':preparation[2]} if any(preparation) else None)



def setup_generator(d,m):
    root=d/'dependencies'
    package=command(['git','-C',d/'core','show',m['pair']['core']+':package.json'],binary=True)
    lock_bytes=command(['git','-C',d/'core','show',m['pair']['core']+':package-lock.json'],binary=True)
    if 'dependencyReuse' in m:require(isinstance(m['dependencyReuse'],dict),'M7_DEPENDENCY_REUSE_RECORD_REQUIRED')
    tools=generator_tools();reuse=m.get('dependencyReuse');reuse_provenance=None
    if reuse is not None:
        require(tools==reuse['tools'],'M7_DEPENDENCY_REUSE_TOOL_CHANGED')
        with private_commands(d/'generator-commands'):
            reuse_provenance=dependency_reuse.copy_owned(destination=root,qualification=reuse,
                package_bytes=package,lock_bytes=lock_bytes,run=dependency_run)
            client=generator_client(d,tools)
    else:
        require(diagnostic_resources._ACTIVE is None,'M7_DIAGNOSTIC_DEPENDENCIES_REQUIRED')
        root.mkdir(mode=0o700)
        (root/'package.json').write_bytes(package);(root/'package-lock.json').write_bytes(lock_bytes)
        (root/'.npmrc').write_text('');(root/'.npmrc').chmod(0o600)
        npm_env=runtime_env({'NPM_CONFIG_USERCONFIG':str(root/'.npmrc'),'NPM_CONFIG_GLOBALCONFIG':'/dev/null','NPM_CONFIG_CACHE':str(root/'.npm-cache')})
        with private_commands(d/'generator-commands'):
            command([tools['npm']['path'],'ci','--include=dev','--omit=optional','--ignore-scripts','--force'],cwd=root,env=npm_env,timeout=1200,phase='generator-npm-ci')
            client=generator_client(d,tools)
    lock=dependency_reuse.sha(lock_bytes)
    # Source-side helpers load the same lockfile dependencies as this cell, not
    # a peer's modules or ambient NODE_PATH. The source worktree is ours.
    link=d/'core/node_modules'
    require(not link.exists() and not link.is_symlink(),'M7_SOURCE_DEPENDENCIES_EXIST')
    link.symlink_to(root/'node_modules',target_is_directory=True)
    contexts={'generator':dependency_context(root,root/'node_modules',['socket.io-client','pg','js-yaml']),
              'source':dependency_context(d/'core',root/'node_modules',['pg','js-yaml'])}
    require(digest(root/'package-lock.json')==lock,'M7_GENERATOR_LOCK_CHANGED')
    m['generator']={'kind':'owned-lockfile-install','tools':tools,'pair':m['pair'],'packageSha256':digest(root/'package.json'),'lockSha256':lock,'client':client,'contexts':contexts,
                    'installFlags':['ci','--include=dev','--omit=optional','--ignore-scripts','--force'],'servingImageId':m.get('imageId')}
    if reuse_provenance is not None:
        m['generator'].update(kind='owned-qualified-dependency-copy',installFlags=[],reuseProvenance=reuse_provenance)
    write(d/'generator-provenance.json',m['generator']);write(d/'owner.json',m)


def verify_generator(d,m):
    expected=m.get('generator');require(expected,'M7_GENERATOR_PROVENANCE_REQUIRED')
    if 'dependencyReuse' in m:
        require(expected.get('kind')=='owned-qualified-dependency-copy' and expected.get('reuseProvenance',{}).get('qualification')==m['dependencyReuse'],'M7_DEPENDENCY_REUSE_PROVENANCE_CHANGED')
        require(document(d/'dependencies/dependency-reuse-ready.json')==expected['reuseProvenance'] and dependency_reuse.tree(d/'dependencies/node_modules')==m['dependencyReuse']['tree'],'M7_DEPENDENCY_REUSE_COPY_CHANGED')
    require(generator_tools()==expected['tools'],'M7_GENERATOR_TOOL_CHANGED')
    require(digest(d/'dependencies/package.json')==expected['packageSha256'] and digest(d/'dependencies/package-lock.json')==expected['lockSha256'],'M7_DEPENDENCIES_CHANGED')
    if m['generator'].get('contexts'):
        require(dependency_context(d/'dependencies',d/'dependencies/node_modules',['socket.io-client','pg','js-yaml'])==expected['contexts']['generator'] and dependency_context(d/'core',d/'dependencies/node_modules',['pg','js-yaml'])==expected['contexts']['source'],'M7_DEPENDENCY_CONTEXT_CHANGED')
    with private_commands(d/'generator-verifications'/uuid.uuid4().hex):
        require(generator_client(d,expected['tools'])==expected['client'],'M7_GENERATOR_CLIENT_CHANGED')


def pin_service_images(config, app_image):
    for name,spec in config['services'].items():
        if 'build' in spec and name!='postgres':spec['image']=app_image


def vault_control(d,m,action):
    require(m.get('vaultRefusalControl')=='api-policy-deny-v1' and not m.get('attached'),'M7_VAULT_CONTROL_NOT_SELECTED')
    verify(d,m)
    config=document(d/'frozen.compose.json')
    rows=diagnostic_resource_rows(m)
    diagnostic_resources._ACTIVE.containers() if diagnostic_resources._ACTIVE is not None else None
    vault=[row for row in rows if row['Config']['Labels'].get('com.docker.compose.service')=='vault']
    require(len(vault)==1 and vault[0]['Image']==config['services']['vault']['image'] and vault[0]['State'].get('Running') is True,'M7_VAULT_CONTROL_NATIVE_CUSTODY')
    if action=='deny':
        require(not any(row['Config']['Labels'].get('com.docker.compose.service','').startswith('api') for row in rows),'M7_VAULT_CONTROL_API_ALREADY_BORN')
        write(d/'vault-refusal/intent.json',{'owner':m['owner'],'project':m['project'],'pair':m['pair'],'beforeFirstApi':True})
    value=vault_refusal.apply(d,m,action,lambda argv,**kw:compose(d,*argv,**kw))
    write(d/('vault-refusal/'+action+'.json'),value)
    original=d/'state/bootstrap/m7-api-vault-policy.original.private.json'
    retained=d/'vault-refusal/original.private.json'
    if original.is_file():
        if retained.exists():require(retained.read_bytes()==original.read_bytes(),'M7_VAULT_CONTROL_ORIGINAL_CHANGED')
        else:shutil.copyfile(original,retained);retained.chmod(0o600)
    return value



def platform_failure_observation(d):
    # The GET reads the admin operation's durable last_diagnostic. It runs once
    # on failure, within the current work deadline and without retrying the POST.
    try:
        raw = compose(d, 'exec', '-T', '--workdir', '/opt/app', 'admin', 'node', '-',
                      input=(HERE/'platform-verification-observation.cjs').read_bytes(), timeout=5)
        result = json.loads(raw)
        if isinstance(result, dict):
            if result.get('status') == 'OBSERVED' and set(result) == {'status','targetRole','checkPhase','causeCode'}:
                return result
            if (set(result) == {'status','reason'} and result['status'] == 'UNMEASURED' and
                    result['reason'] in ('NO_FAILED_OPERATION','NO_CLASSIFIED_DIAGNOSTIC','ADMIN_READ_REFUSED')):
                return result
    except Exception:
        pass
    return {'status': 'UNMEASURED', 'reason': 'DIAGNOSTIC_READ_FAILED'}


@contextlib.contextmanager
def deployment_stage(d, stages, name):
    """Persist entry before effects; preserve the first failure through cleanup."""
    before=time.monotonic()
    row={"name":name,"status":"STARTED","startedAt":time.time()}
    stages.append(row)
    write(d/"deployment-stages.json",stages)
    primary=None
    try:
        yield row
        row["status"]="SUCCEEDED"
    except BaseException as error:
        primary=error
        # Exception messages may contain argv, URLs or credentials. Retain only
        # this instrument's fixed code class and the typed process outcome.
        code=str(error).split(":",1)[0]
        row.update(status="FAILED",firstError={
            "code":code if re.fullmatch(r"M7_[A-Z0-9_]+",code) else "M7_DEPLOYMENT_STAGE_FAILED",
            "failureType":type(error).__name__,
            "returncode":getattr(error,"returncode",None)})
        if name == 'platform-verify':
            row['verificationDiagnostic'] = platform_failure_observation(d)
        try:
            terminal_snapshot(d,document(d/'owner.json'),'terminal-'+name+'.json')
            row['terminalObservation']='terminal-'+name+'.json'
        except Exception:
            row['terminalObservation']='UNMEASURED; cleanup makes an independent bounded capture'
        raise
    finally:
        row.update(seconds=time.monotonic()-before,finishedAt=time.time())
        try:write(d/"deployment-stages.json",stages)
        except Exception:
            if primary is None:raise


def deploy(d, m):
    frozen(m,"deploy");experiment_host(d,m,"deploy-before");verify(d,m)
    m["imageId"] = image(m)
    if not m.get('generator'):setup_generator(d,m)
    else:verify_generator(d,m)
    m['generator']['servingImageId']=m['imageId'];write(d/'generator-provenance.json',m['generator'])
    config = document(d / "frozen.compose.json")
    pin_service_images(config,m["imageId"])
    if m.get("postgresImageId"):
        pg=json.loads(command(["docker","image","inspect",m["postgresImageId"]]))[0]
        require(pg["Id"]==m["postgresImageId"] and config["services"]["postgres"]["image"]==pg["Id"],"M7_POSTGRES_IMAGE_CHANGED")
    write(d / "frozen.compose.json", config);m["composeSha256"] = digest(d / "frozen.compose.json");write(d / "owner.json", m)
    stages=[]
    for name,scope,args in deployment_plan(config,pgstream=m.get("profile")=="pgstream-sample",primer_concurrency_value=m.get("primerConcurrency",1),platform_verification=bool(m.get("platformStartup"))):
        with deployment_stage(d, stages, name):
            timeout = discovery_seconds(m, 1800)
            if (name in ("provision", "prime") and
                    m.get('discoveryAuthorization', {}).get('executionScope') == 'LOCAL_OWNED_TO_COMPLETION'):
                timeout = None
            if name=="prime":
                prior=d/"state/primer/tenants.json"
                write(d/"primer-start.json",{"concurrency":m.get("primerConcurrency",1),"reusedTenants":len(document(prior)["tenants"]) if prior.exists() else 0,"requestedTenants":m["tenants"],"stageTimeoutSeconds":timeout})
            observer=(api_warm_cause.observe(sys.modules[__name__],d,m) if name=='prime'
                      else contextlib.nullcontext())
            with observer, (d/(name+".log")).open("wb") as output:
                if scope=="local":command(["node",d/"core/deploy/multitenant"/args[0],d/"state"],file=output)
                else:compose(d,*args,file=output,timeout=timeout)
            if name=="commission" and m.get("vaultRefusalControl"):vault_control(d,m,"deny")
            if name=="prime" and m.get("primerConcurrency",1)!=1:primer_counts(d,m)
            if name=="publish-primer" and m.get("clinicalTimeline"):
                clinical_timeline.publish(d,m,tenant_projection(document(d/"state/primer/tenants.json"),m["tenants"]))
                write(d/"owner.json",m)
            if name=="infrastructure":psql(d,"CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
            if name=="bootstrap":
                ack_wire=stream_topology.install_ack_budget(d,m,config)
                if ack_wire is not None:
                    m['pgstreamNotifierAckWire']=ack_wire
                    write(d/'producer-ack-budget.json',ack_wire)
                if m.get('staticTopology'):static_runtime_contract(d,m)
                fingerprint=settings_fingerprint(d,m)
                m["settingsFingerprint"]=fingerprint
                m["profileSelection"]=profile_provenance.identity(fingerprint,m["diagnostics"],config)
                profile_provenance.state_environment(d/"state",config,m["diagnostics"])
                write(d/"owner.json",m)
                layout=document(d/"state/bootstrap/layout.json")
                require(all(layout.get("namespaces",{}).get(kind)=="nsdemo_"+kind for kind in ("entries","devicestatus","treatments","clock","eval_checkpoint")),"M7_ORACLE_SCHEMA_CONTRACT_CHANGED")
                # Raw restart is not a valid controlled-placement replacement.
                # The coordinator must supply the committed sharding helper seam.
                for name in service_roster(config):
                    file=d/"state"/name/"env.json"
                    if file.exists():require(not document(file).get("MULTITENANT_REALTIME_PLACEMENT"),"M7_SHARDED_RESTART_HELPER_REQUIRED")
    if m.get("vaultRefusalControl"):vault_control(d,m,"auth-check")
    candidates=[file for file in (d/"state/primer/tenants.json",d/"state/ops/tenants.json") if file.exists()]
    require(candidates,"M7_PRIMER_OUTPUT_MISSING")
    projections=[tenant_projection(document(file),m["tenants"]) for file in candidates]
    require(all(value==projections[0] for value in projections),"M7_PRIMER_OUTPUT_CONFLICT")
    write(d/"tenants.private.json",projections[0])
    if stream_topology.ACK_BUDGET in m:
        streams=[row for row in resources(m) if row['Config']['Labels'].get('com.docker.compose.service')=='pgstream']
        require(len(streams)==1 and streams[0]['Config']['Labels'].get(OWNER)==m['owner'], 'M7_PGSTREAM_ACK_RUNTIME_OWNER')
        stream_topology.verify_ack_budget(d,m,streams[0]['Mounts'])
        write(d/'producer-ack-budget.json',{**m['pgstreamNotifierAckWire'], 'ownedMountVerified': True})
    profile_provenance.runtime_environment(resources(m),m["diagnostics"],config,pgstream=m.get("profile")=="pgstream-sample")
    if m.get('composeLimitMode') == 'uncapped-services':
        rows = diagnostic_resources.uncapped_readback(diagnostic_resource_rows(m), config['services'])
        write(d/'compose-limits-readback.json', {'mode': m['composeLimitMode'], 'services': rows,
              'scope': 'owned Compose services; host-level constraints and contention may still apply'})
    m["restartRoles"]=service_roster(config)
    write(d/"owner.json",m);write(d/"deployment.json",{"stages":stages,"pair":m["pair"],"imageId":m["imageId"]})


def process_counters(text):
    result={}
    for line in text.splitlines()[1:]:
        pid,name,rss=line.split()
        try:
            raw=Path('/proc/'+pid+'/stat').read_text().rsplit(')',1)[1].split()
            executable=os.readlink('/proc/'+pid+'/exe')
            result[pid]={'name':name,'component':Path(executable).name,'executable':executable,'rssKiB':int(rss),'startTicks':int(raw[19]),'cpuTicks':int(raw[11])+int(raw[12]),'clockTicksPerSecond':os.sysconf('SC_CLK_TCK')}
        except (OSError,ValueError,IndexError):result[pid]={'name':name,'unavailable':True}
    return result


def memory_observation(container_id, started_at=None):
    # Separate reads preserve the legacy concatenated cgroup parser exactly.
    result={'status':'UNMEASURED','scope':'container-cgroup lifetime since birth or last external reset; not phase peak'}
    try:
        raw=command(['docker','exec',container_id,'cat','/sys/fs/cgroup/memory.peak']).strip()
        if re.fullmatch(r'[0-9]+',raw):result.update(status='MEASURED',memoryPeakBytes=int(raw))
        else:result['reason']='invalid-memory-peak'
    except RuntimeError:result['reason']='memory-peak-unavailable'
    try:
        raw=command(['docker','exec',container_id,'cat','/sys/fs/cgroup/memory.events'])
        events={}
        for line in raw.splitlines():
            key,value=line.split()
            require(key not in events and re.fullmatch(r'[a-z_]+',key) and re.fullmatch(r'[0-9]+',value),'M7_MEMORY_EVENTS_INVALID')
            events[key]=int(value)
        require(bool(events),'M7_MEMORY_EVENTS_INVALID')
        result['memoryEvents']=events
    except (RuntimeError,ValueError):result['memoryEvents']='UNMEASURED'
    if isinstance(started_at,str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z',started_at):
        try:
            inspected=json.loads(command(['docker','inspect','--format','{{json .}}',container_id]))
            require(inspected.get('Id')==container_id and inspected.get('State',{}).get('StartedAt')==started_at,'M7_MEMORY_BIRTH_CHANGED_DURING_READ')
            result['birth']={'containerId':container_id,'startedAt':started_at,'source':'docker-inspect-state-started-at-v1','stableRead':True}
        except (ValueError,RuntimeError):
            # An optional counter cannot describe a lifetime that changed while
            # it was read. Preserve other phase observations without continuity.
            result.update(status='UNMEASURED',reason='container-birth-unverified');result.pop('memoryPeakBytes',None)
    return result


def terminal_snapshot(d, m, filename='terminal-before-cleanup.json', seconds=20):
    """Sanitized owned census before teardown, including stopped containers.

    Host cgroup files are optional. A stopped actor often has no cgroup left;
    its observed exit/OOM/restart evidence still survives independently.
    """
    target=Path(d)/filename
    if target.exists():return document(target)
    started=time.time();cpu_started=time.process_time();result={'basis':'reproduced','at':started,'containers':[],
        'scope':'container lifetime peaks when readable; no phase-peak or missing-role inference'}
    with command_deadline(started+seconds):
        assert_owned(m)
        rows=resources(m)
        require(len(rows)<=64,'M7_TERMINAL_CENSUS_BOUND')
        config=document(Path(d)/'frozen.compose.json') if (Path(d)/'frozen.compose.json').exists() else {}
        for row in rows:
            labels=row.get('Config',{}).get('Labels',{});service=labels.get('com.docker.compose.service')
            require(labels.get('com.docker.compose.project')==m['project'],'M7_TERMINAL_PROJECT_CHANGED')
            spec=config.get('services',{}).get(service,{})
            expected=spec.get('image','')
            require(not expected.startswith('sha256:') or row['Image']==expected,'M7_TERMINAL_IMAGE_CHANGED')
            state=row.get('State',{});pid=state.get('Pid',0)
            item={'id':row['Id'],'service':service,'imageId':row['Image'],
                  'restartCount':row.get('RestartCount','UNMEASURED'),
                  'state':{key:state.get(key,'UNMEASURED') for key in
                           ('Status','Running','Paused','Restarting','OOMKilled','Dead','Pid','ExitCode','StartedAt','FinishedAt')},
                  'limits':{key:row.get('HostConfig',{}).get(key,'UNMEASURED') for key in
                            ('NanoCpus','CpuQuota','CpuPeriod','CpuShares','Memory','MemorySwap','PidsLimit')},
                  'cgroup':{'status':'UNMEASURED','reason':'exited-or-unavailable'}}
            if state.get('Running') and type(pid)is int and pid>0 and time.time()<started+seconds:
                try:
                    proc=Path('/proc')/str(pid)
                    birth=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
                    line=(proc/'cgroup').read_text().splitlines()
                    paths=[x[3:] for x in line if x.startswith('0::')]
                    require(len(paths)==1,'M7_TERMINAL_CGROUP_PATH')
                    cg=Path('/sys/fs/cgroup')/paths[0].lstrip('/')
                    require(cg.resolve().is_relative_to(Path('/sys/fs/cgroup')),'M7_TERMINAL_CGROUP_PATH')
                    values={}
                    for key in ('cpu.stat','cpu.max','memory.current','memory.peak','memory.events','memory.max','memory.swap.max'):
                        try:
                            raw=(cg/key).read_text();require(len(raw)<=65536,'M7_TERMINAL_CGROUP_BOUND');values[key]=raw
                        except OSError:values[key]='UNMEASURED'
                    require((proc/'stat').read_text().rsplit(')',1)[1].split()[19]==birth,'M7_TERMINAL_PID_BIRTH_CHANGED')
                    item['cgroup']={'status':'OBSERVED','files':values,'pidStartTicks':birth}
                except (OSError,IndexError,ValueError,RuntimeError):pass
            try:
                after=json.loads(command(['docker','inspect','--format','{{json .}}',row['Id']],timeout=3))
                require(after['Id']==row['Id'] and after['State'].get('StartedAt')==state.get('StartedAt') and
                        after['State'].get('Pid')==pid,'M7_TERMINAL_BIRTH_CHANGED')
            except (RuntimeError,ValueError,KeyError):
                item['cgroup']={'status':'UNMEASURED','reason':'birth-changed-or-unverified'}
            result['containers'].append(item)
        assert_owned(m)
    result['observer']={'wallSeconds':time.time()-started,'cpuSeconds':time.process_time()-cpu_started,
                        'memoryPeakKiB':__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss,
                        'scope':'runner process lifetime RSS peak and collection CPU delta'}
    write(target,result)
    return result


def phase_snapshot(d, out, name):
    snapshot_owner=document(d/"owner.json")
    segments=collection_segments.Segments(out,name,snapshot_owner)
    rows = resources(snapshot_owner, False)
    result = {}
    coverage = {'status':'UNMEASURED','reason':'M7_INSTANCE_FROZEN_ROSTER_UNAVAILABLE'}
    expected = {}
    config_path = d/'frozen.compose.json'
    if config_path.is_file():
        try:
            config = document(config_path)
            expected = role_instances.roster(config, snapshot_owner.get('replicas'))
            if expected:
                role_instances.runtime(rows, expected, snapshot_owner)
                coverage = {'status':'MEASURED','instances':expected}
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            coverage = {'status':'UNMEASURED','reason':collection_segments.code(error),'instances':expected}
    for row in rows:
        role = row["Config"]["Labels"].get("com.docker.compose.service", row["Name"])
        if role in result:
            result[role] = {'unavailable':True,'reason':'M7_INSTANCE_RUNTIME_ROSTER'}
            continue
        try:
            raw = command(["docker", "exec", row["Id"], "cat", "/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.stat"])
            processes = command(["docker", "top", row["Id"], "-eo", "pid,comm,rss"])
            result[role] = {"id": row["Id"], "cgroup": raw, "processRssKiB": processes,"hostProcesses":process_counters(processes),"containerStartedAt":row.get("State",{}).get("StartedAt"),"memoryObservation":memory_observation(row["Id"],row.get("State",{}).get("StartedAt")),"resourceLimits":role_instances.effective_limits(sys.modules[__name__],row),**({"instance":expected[role]} if role in expected else {})}
        except RuntimeError:
            result[role] = {"id": row["Id"], "unavailable": True}
    with segments.capture("cgroups",[name+"-cgroups.json"]):
        write(out / (name + "-cgroups.json"), {"at": time.time(), "roles": result, "serviceCoverage":coverage})
    timings={'version':1,'collectorOwner':snapshot_owner.get('owner'),'hostIdentity':snapshot_owner.get('hostIdentity'),'clockDomain':'collector-host-monotonic-v1','scope':'existing SQL snapshot request bounds; not exact query instants or database-role CPU','reads':{}}
    sql="SELECT r.rolname,sum(s.calls),sum(s.total_exec_time) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid GROUP BY 1 ORDER BY 1;"
    statements="SELECT r.rolname,s.calls,s.total_exec_time,s.queryid,s.dbid,encode(convert_to(s.query,'UTF8'),'hex') FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid ORDER BY r.rolname,s.queryid;"
    for kind,query in [('pg-role',sql),('pg-statements',statements)]:
        row={'wallStartedAtNs':time.time_ns(),'monotonicStartedAtNs':time.monotonic_ns()};timings['reads'][kind]=row
        try:
            with segments.capture(kind,[name+'-'+kind+'.tsv']):
                (out/(name+'-'+kind+'.tsv')).write_text(psql(d,query));row['status']='PASS'
        except BaseException:
            row['status']='FAILED';raise
        finally:
            row.update(wallFinishedAtNs=time.time_ns(),monotonicFinishedAtNs=time.monotonic_ns())
            # Timing publication never conceals the original SQL failure.
            try:write(out/(name+'-sql-snapshot-timing.json'),timings)
            except Exception:
                if row['status']=='PASS':raise

    if expected:
        try:
            with segments.capture('sql-service-coverage',[name+'-sql-service-coverage.json']):
                write(out/(name+'-sql-service-coverage.json'),role_instances.sql_coverage(config,expected,d/'state'))
        except Exception as error:
            write(out/(name+'-sql-service-coverage-failure.json'),{'status':'UNMEASURED','code':collection_segments.code(error)})

    # Optional stages retain their refusal without erasing mandatory SQL/cgroups.
    for kind,collect in [('pg-costs',lambda:cost_companion.capture(out,name,snapshot_owner,lambda query:psql(d,query))),
        ('realtime-costs',lambda:realtime_costs.capture(out,name,snapshot_owner,
            sorted(role for role,spec in document(d/'frozen.compose.json')['services'].items() if isinstance(spec.get('command'),list) and spec['command'][-1:]==['realtime']),
            lambda service:compose(d,'exec','-T',service,'node','-',input=(HERE/'realtime-costs.cjs').read_bytes(),timeout=7)))]:
        try:
            with segments.capture(kind,[name+'-'+kind+'.json']):collect()
        except Exception as error:
            write(out/(name+'-'+kind+'-failure.json'),{'status':'UNMEASURED','code':collection_segments.code(error),'failureType':type(error).__name__})


    # Exact new native configurations expose a runtime source-access census.
    # Optional observation is independent of mandatory SQL/cgroup captures.
    completion_path=d/'completion-source.json'
    if completion_path.is_file() and document(completion_path).get('native'):
        try:
            with segments.capture('source-access',[name+'-source-access.json']):
                ids=sorted(row['id'] for row in document(d/'tenants.private.json'))[:128]
                write(out/(name+'-source-access.json'),source_access.collect(sys.modules[__name__],d,snapshot_owner,ids))
        except Exception as error:
            write(out/(name+'-source-access-failure.json'),{'status':'UNMEASURED','code':collection_segments.code(error),'failureType':type(error).__name__})


def sql_counter_rate_bounds(before,after,delta,kind='pg-role'):
    require(type(delta)is int and delta>=0,'M7_SQL_COUNTER_RESET')
    try:
        require(before['version']==after['version']==1 and before['clockDomain']==after['clockDomain']=='collector-host-monotonic-v1','M7_SQL_SNAPSHOT_TIMING_REQUIRED')
        require(isinstance(before['collectorOwner'],str) and re.fullmatch('[a-f0-9]{32}',before['collectorOwner']) and before['collectorOwner']==after['collectorOwner'] and isinstance(before['hostIdentity'],str) and re.fullmatch('[a-f0-9]{64}',before['hostIdentity']) and before['hostIdentity']==after['hostIdentity'],'M7_SQL_SNAPSHOT_TIMING_REQUIRED')
        a,b=before['reads'][kind],after['reads'][kind]
        require(a['status']==b['status']=='PASS','M7_SQL_SNAPSHOT_TIMING_REQUIRED')
        points=[a['monotonicStartedAtNs'],a['monotonicFinishedAtNs'],b['monotonicStartedAtNs'],b['monotonicFinishedAtNs']]
        require(all(type(v)is int and v>=0 for v in points) and points[0]<=points[1]<points[2]<=points[3],'M7_SQL_SNAPSHOT_TIMING_REQUIRED')
    except (KeyError,TypeError):raise RuntimeError('M7_SQL_SNAPSHOT_TIMING_REQUIRED')
    low=(points[2]-points[1])/1e9;high=(points[3]-points[0])/1e9
    return {'kind':'bounded-counter-rate','elapsedLowerSeconds':low,'elapsedUpperSeconds':high,'minimumPerSecond':delta/high,'maximumPerSecond':delta/low,'scope':'request-bracket bounds, not exact QPS or database-role CPU'}


def job_record(file,process,owner,group=False):
    raw=Path('/proc/'+str(process.pid)+'/stat').read_text().split(')',1)[1].split()
    write(file,{'owner':owner,'pid':process.pid,'startTicks':raw[19],'group':group,'completed':False})


def stop_job(file,owner):
    if not file.exists():return
    job=document(file)
    require(job.get('owner')==owner and isinstance(job.get('pid'),int) and job['pid']>1,'M7_HOST_JOB_NOT_OWNED')
    if job.get('completed'):return
    proc=Path('/proc/'+str(job['pid'])+'/stat')
    if proc.exists():
        raw=proc.read_text().split(')',1)[1].split()
        require(raw[19]==job['startTicks'],'M7_HOST_JOB_IDENTITY_CHANGED')
        if raw[0]!='Z':
            if job['group']:
                require(os.getpgid(job['pid'])==job['pid'],'M7_HOST_JOB_GROUP_CHANGED')
                os.killpg(job['pid'],signal.SIGTERM)
            else:os.kill(job['pid'],signal.SIGTERM)
    job['completed']=True;write(file,job)


@contextlib.contextmanager
def sampling(d, out):
    m = document(d / "owner.json")
    out.mkdir(parents=True, exist_ok=True)
    reserve_output(out,m,'sampler',('sampler-attempt.json','sampler.log','sampler-job.json','docker-stats.tsv','host-io.jsonl'))
    # Reuse source-owned sampler with the already frozen merged Compose file;
    # empty second file replaces the old bootstrap source-mount overlay.
    empty = d / "empty.compose.json";write(empty, {"services": {}})
    log = (out / "sampler.log").open("wb")
    env = runtime_env({"M7_SAMPLE_OWNER": m["owner"]}) if (
        m.get("profile") == "pgstream-sample" and m.get("runPurpose") == "discovery") else runtime_env()
    process = subprocess.Popen([str(BASE / "probes/sample.sh"), m["project"], str((d / "env").resolve()), str((d / "frozen.compose.json").resolve()), str(empty.resolve()), str(out.resolve()),str(m.get("cadence",{}).get("samplerIntervalSeconds",2))], cwd=d.resolve(),env=env, stdout=log, stderr=log, start_new_session=True)
    job=out/"sampler-job.json";job_record(job,process,m["owner"],group=True)
    before = time.monotonic()
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    try:
        yield
    finally:
        stop_job(job,m["owner"])
        process.wait(timeout=10)
        log.close()
        write(out / "sampler.json", {"cadenceSeconds":m.get("cadence",{}).get("samplerIntervalSeconds",2), "wallSeconds": time.monotonic()-before, "pid": process.pid,
                                    "source": "compose-baseline/probes/sample.sh", "controllerCpuSeconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime - cpu_before.ru_utime - cpu_before.ru_stime,
                                    "overhead": "included in host/PG cgroup figures; compare sampler-disabled idle control"})


def enabled_idle(d,m,out,seconds):
    """Existing two bookends, including AFTER when the observer refuses."""
    phase_snapshot(d,out,'before')
    phase_failure=None
    try:
        with sampling(d,out), observe_progress(d,m,out,'idle') as progress:time.sleep(seconds)
    except BaseException as error:
        phase_failure=error
        raise
    finally:
        try:phase_snapshot(d,out,'after')
        except BaseException as error:
            detail={'version':1,'phase':'idle','snapshot':'after','status':'FAILED',
                    'code':'M7_IDLE_AFTER_SNAPSHOT_REFUSED','originalPhaseFailurePreserved':phase_failure is not None,
                    'partialFiles':{name:(out/name).is_file() for name in ('after-cgroups.json','after-pg-role.tsv','after-pg-statements.tsv')}}
            # Raw exception messages may contain SQL/URLs/data. Persist only fixed
            # metadata; publication failure must not replace the phase failure.
            try:write(out/'after-snapshot-failure.json',detail)
            except Exception:detail['publicationFailed']=True
            if phase_failure is None:
                if hasattr(progress,'failed'):
                    try:progress.failed(evaluator_progress.Refused('M7_IDLE_AFTER_SNAPSHOT_REFUSED'),{'afterSnapshotFailure':detail})
                    except Exception:detail['observerPublicationFailed']=True
                raise
            try:phase_failure.afterSnapshotFailure=detail
            except Exception:pass
    if isinstance(progress,evaluator_idle.Observer):progress.complete_after_cost_window()
    return progress


def stored(d, runid):
    require(re.fullmatch(r"[a-z0-9-]{1,120}", runid), "M7_RUN_ID_INVALID")
    sql = "\nUNION ALL\n".join("SELECT tenant_id::text,'" + kind + "',count(*) FROM nsdemo_" + kind + "." + kind + " WHERE doc->>'" + field + "'='" + runid + suffix + "' GROUP BY 1" for kind, field, suffix in [("entries","device",""),("devicestatus","device",""),("treatments","enteredBy",""),("entries","device","-probe")]) + ";"
    # Distinguish probe rows without changing the SQL's independent role.
    sql = sql.rsplit("'entries'", 1)[0] + "'probe'" + sql.rsplit("'entries'", 1)[1]
    rows = {}
    for line in psql(d, sql, "nightscout_compose_test").splitlines():
        tenant, kind, count = line.split("\t");rows.setdefault(tenant, {})[kind] = int(count)
    return rows


def count_oracle(d, strict=True, allow_empty=False):
    out = d / "load";metrics = document(out / ("client-acks.json" if document(d/"owner.json").get("profile")=="fresh-image-diagnostic" else "k6-summary.json"))["metrics"]
    probes = document(out / "fanout.json")["probeWrites"]["byTenant"]
    values = stored(d, (out / "runid").read_text().strip())
    write(out / "stored-counts.json", values)
    result = oracle(values, metrics, probes, document(d / "tenants.private.json"), strict=strict,allow_empty=allow_empty)
    write(out / "oracle.json", result)
    return result


def control(d, m):
    verify(d, m)
    if m.get('profile')=='pgstream-sample' and m.get('runPurpose')=='discovery':
        return discovery_oracle_control(d)
    return oracle_control(d)


def oracle_control(d):
    assert_owned(document(d / "owner.json"))
    require(count_oracle(d)["verdict"] == "GREEN", "M7_CONTROL_BASELINE_NOT_GREEN")
    marker = (d / "load/runid").read_text().strip()
    require(re.fullmatch(r"[a-z0-9-]{1,120}", marker), "M7_RUN_ID_INVALID")
    mutate = "BEGIN; SELECT set_config('app.current_tenant_id',(SELECT tenant_id::text FROM nsdemo_entries.entries WHERE doc->>'device'='{old}' LIMIT 1),true); UPDATE nsdemo_entries.entries SET doc=jsonb_set(doc,'{{device}}',to_jsonb('{new}'::text)) WHERE ctid=(SELECT ctid FROM nsdemo_entries.entries WHERE doc->>'device'='{old}' AND tenant_id=current_setting('app.current_tenant_id')::uuid LIMIT 1) RETURNING _id;COMMIT;"
    baseline = count_oracle(d)
    changed = False
    try:
        result = psql(d, mutate.format(old=marker, new=marker + "-control"), "nightscout_compose_test")
        require(result.strip(), "M7_CONTROL_NO_VICTIM")
        changed = True
        broken = count_oracle(d)
        require(broken["verdict"] == "RED", "M7_CONTROL_DID_NOT_FAIL")
    finally:
        if changed:
            psql(d, mutate.format(old=marker + "-control", new=marker), "nightscout_compose_test")
    restored = count_oracle(d)
    require(restored["verdict"] == "GREEN", "M7_CONTROL_NOT_RESTORED")
    write(d / "load/oracle-control.json", {"baseline": baseline["verdict"], "broken": broken["verdict"], "restored": restored["verdict"]})


def discovery_oracle_control(d):
    """Sparse discovery witness; never changes default acceptance admission."""
    from discovery_counts import observe, control_domain
    m=document(d/'owner.json');assert_owned(m)
    require(m.get('profile')=='pgstream-sample' and m.get('runPurpose')=='discovery','M7_DISCOVERY_CONTROL_SCOPE')
    out=d/'load';marker=(out/'runid').read_text().strip()
    require(re.fullmatch(r'[a-z0-9-]{1,120}',marker),'M7_RUN_ID_INVALID')
    metrics=document(out/'k6-summary.json')['metrics']
    def snapshot(stage):
        assert_owned(m)
        try:value,_=observe(sys.modules[__name__],d,out,marker,metrics,probe_ledger=m['cadence'].get('probeLedger'))
        except RuntimeError as error:
            if str(error)!='M7_DISCOVERY_WRONG_DATA' or not hasattr(error,'oracleFindings'):raise
            value=error.oracleFindings
        write(out/('oracle-control-'+stage+'.json'),value)
        return value
    baseline=snapshot('baseline')
    domain=control_domain(baseline,len(document(d/'tenants.private.json')))
    require(domain is not None,'M7_CONTROL_BASELINE_NOT_EXACT')
    field='enteredBy' if domain=='treatments' else 'device'
    # Domain/field are fixed above; the marker is validated, never arbitrary SQL.
    mutate="BEGIN; SELECT set_config('app.current_tenant_id',(SELECT tenant_id::text FROM nsdemo_{domain}.{domain} WHERE doc->>'{field}'='{old}' LIMIT 1),true); UPDATE nsdemo_{domain}.{domain} SET doc=jsonb_set(doc,'{{{field}}}',to_jsonb('{new}'::text)) WHERE tenant_id=current_setting('app.current_tenant_id')::uuid AND ctid=(SELECT ctid FROM nsdemo_{domain}.{domain} WHERE doc->>'{field}'='{old}' AND tenant_id=current_setting('app.current_tenant_id')::uuid LIMIT 1) RETURNING 'm7-count-control-victim';COMMIT;"
    changed=False
    try:
        assert_owned(m);changed=True
        result=psql(d,mutate.format(domain=domain,field=field,old=marker,new=marker+'-control'),'nightscout_compose_test')
        require(result.splitlines().count('m7-count-control-victim')==1,'M7_CONTROL_NO_VICTIM')
        broken=snapshot('broken')
        require(broken.get('verdict')=='RED' and broken.get('code')=='M7_DISCOVERY_WRONG_DATA','M7_CONTROL_DID_NOT_FAIL')
    finally:
        if changed:
            assert_owned(m)
            psql(d,mutate.format(domain=domain,field=field,old=marker+'-control',new=marker),'nightscout_compose_test')
    restored=snapshot('restored')
    require(control_domain(restored,len(document(d/'tenants.private.json')))==domain,'M7_CONTROL_NOT_RESTORED')
    write(out/'oracle-control.json',{'baseline':baseline['verdict'],'broken':broken['verdict'],'restored':restored['verdict']})


def progress_services(d):
    config=document(d/"frozen.compose.json")
    services=sorted(name for name,spec in config["services"].items() if isinstance(spec.get("command"),list) and spec["command"][-1:]==["evaluator"])
    evaluator_progress.need(1<=len(services)<=evaluator_progress.POLICY['maxInstances'],"M7_EVALUATOR_PROGRESS_INSTANCE_BOUND")
    return services


def progress_fetch(d,service,ids,queries,budget,timeout=20):
    prefix="const M7_PROGRESS_IDS="+json.dumps(ids)+";const M7_PROGRESS_QUERY_BUDGET="+str(queries)+";const M7_PROGRESS_BYTE_BUDGET="+str(budget)+";\n"
    code=prefix+(HERE/"evaluator-progress.cjs").read_text()
    try:return compose(d,"exec","-T",service,"node","-",input=code.encode(),timeout=timeout)
    except Exception:raise evaluator_progress.Refused("M7_EVALUATOR_PROGRESS_UNAVAILABLE")


def progress_attribution(m):
    return {**({"staticTopology":m["staticTopology"]} if m.get("staticTopology") else {}),"pair":m["pair"],"imageId":m["imageId"],"instrument":m["instrument"]["sha256"],"profileSelection":m["profileSelection"]["sha256"],"tenants":m["tenants"],"replicas":m["replicas"],"profile":m["profile"],"hostIdentity":m["hostIdentity"]}


def write_progress(out,value,m):
    before=time.monotonic();cpu=time.process_time()
    packed={**(evaluator_opportunities.pack(value) if value.get('opportunityContract') else evaluator_idle.pack(value) if value.get("policy")==evaluator_idle.POLICY else evaluator_progress.pack(value)),"attribution":{**({"staticTopology":m["staticTopology"]} if m.get("staticTopology") else {}),"pair":m["pair"],"imageId":m["imageId"],"instrument":m["instrument"]["sha256"],"profileSelection":m["profileSelection"]["sha256"],"tenants":m["tenants"],"replicas":m["replicas"],"profile":m["profile"],"hostIdentity":m["hostIdentity"]}};raw=json.dumps(packed,separators=(',',':')).encode()+b'\n'
    file=out/'evaluator-progress.json';file.write_bytes(raw);file.chmod(0o600)
    compressed=out/'evaluator-progress.json.gz';compressed.write_bytes(gzip.compress(raw,mtime=0));compressed.chmod(0o600)
    tail_publication=value.get('tailRound') is not None or value.get('tailAttempted') is True
    write(out/('evaluator-tail-publication.json'if tail_publication else'evaluator-progress-publication.json'),{'wallSeconds':time.monotonic()-before,'processCpuSeconds':time.process_time()-cpu,'rawBytes':len(raw),'gzipBytes':compressed.stat().st_size,'scope':'post-window tail publication; excluded from original metric window'if tail_publication else'original-window serialization, gzip and primary-file writes; sidecar publication excluded'})


def progress_summary(out):
    value=document(out/'evaluator-progress.json');result={k:v for k,v in value.items() if k not in ('kind','columns','rounds','attribution','tailRound','durable','durableBinding','captureWindows','byTenant')}
    return {**result,'rawSha256':digest(out/'evaluator-progress.json'),'gzipSha256':digest(out/'evaluator-progress.json.gz')}


def observe_progress(d,m,out,phase):
    ids=sorted(row['id'] for row in document(d/'tenants.private.json'))
    until=_COMMAND_DEADLINE.get()
    def fetch(*args):
        # Executor threads do not inherit ContextVars. Keep the original cutoff.
        with command_deadline(until):return progress_fetch(d,*args)
    args=(progress_services(d),ids,fetch,m['cadence'][phase+'Seconds'],phase,lambda value:write_progress(out,value,m))
    if 'evaluatorOpportunities' in m:
        opportunity_contract(m)
        if phase in ('idle','load'):
            collector=opportunity_collector(d,m,ids)
            observer=evaluator_opportunities.Observer(*args,durable_fetch=collector,binding=collector.binding,preparation_cost=collector.preparation_cost,source_sha256=collector.source_sha256,query_sha256=collector.query_sha256)
            observer.rest_only=discovery_rest.permitted(sys.modules[__name__],d,m)
            return observer
    return evaluator_idle.Observer(*args,tail_fetch=lambda *args:progress_fetch(d,*args)) if phase=='idle' else evaluator_progress.Observer(*args)


def opportunity_contract(m):
    require(m.get('evaluatorOpportunities')=='received-input-v1' and m.get('profile')=='pgstream-sample' and m.get('completionContract')=='evaluator-work-v2' and m.get('runPurpose')=='discovery','M7_OPPORTUNITY_PROFILE_UNSUPPORTED')


def select_opportunities(args,m):
    selected=getattr(args,'evaluator_opportunities',None)
    if selected is None and m.get('runPurpose')=='discovery' and m.get('profile')=='pgstream-sample' and m.get('completionContract')=='evaluator-work-v2':
        selected='received-input-v1'
    if selected is not None:m['evaluatorOpportunities']=selected;opportunity_contract(m)


def opportunity_collector(d,m,ids):
    """Existing private SQL executor; no public-driver SQL or new connection."""
    opportunity_contract(m);evaluator_progress.validate_ids(ids)
    config_path=d/'completion-source.json'
    require(config_path.is_file(),'M7_OPPORTUNITY_SOURCE_REQUIRED')
    config=document(config_path);source_sha=digest(config_path)
    expected={'kind':'evaluator-work-v2','pair':m['pair'],'imageId':m['imageId'],'instrument':m['instrument']['sha256']}
    if config.get('native') is not None:expected['nativeConfigurationSha256']=hashlib.sha256(json.dumps(config['native'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(config.get('binding')==expected and config.get('kind')==expected['kind'],'M7_OPPORTUNITY_BINDING')
    require('selection' not in config,'M7_OPPORTUNITY_SELECTED_PROFILE_UNSUPPORTED')
    until=_COMMAND_DEADLINE.get()
    database=application_database(d);node=m['generator']['tools']['node']['path']
    script="try{const o=require(process.argv[1]),x=JSON.parse(require('fs').readFileSync(0)),c=o.prepare(x.config);console.log(JSON.stringify(x.mode==='queries'?x.batches.map(ids=>o.progressQuery(c,ids)):o.progressSnapshot(x.rows,c,x.ids)));}catch(e){console.log(JSON.stringify({refused:/^[A-Z][A-Z0-9_]{1,100}$/.test(e.message)?e.message:'M7_OPPORTUNITY_READER_REFUSED',...(e.completionDiagnostic?{completionDiagnostic:e.completionDiagnostic}:{})}));}"
    def invoke(value,timeout):
        if until is not None:
            require(until>time.time(),'M7_COMMAND_DEADLINE');timeout=min(timeout,until-time.time())
        raw=command([node,*([] if diagnostic_resources._ACTIVE is not None else ['--max-old-space-size=256']),'-e',script,HERE/'completed-oracle.cjs'],input=json.dumps({'config':config,**value}).encode(),timeout=timeout,phase='completed-oracle')
        evaluator_progress.need(len(raw.encode())<=evaluator_opportunities.ROUND_BYTES,'M7_OPPORTUNITY_BYTE_BOUND')
        value=json.loads(raw)
        if isinstance(value,dict) and 'refused' in value:
            code=value['refused'];error=evaluator_progress.Refused(code,'UNMEASURED' if code in ('M7_OPPORTUNITY_COVERAGE','M7_COMPLETION_NATIVE_INVALIDATED') else 'FAIL')
            if 'completionDiagnostic' in value:error.collection={'completionReader':value['completionDiagnostic']}
            raise error
        return value
    batches=[ids[offset:offset+64] for offset in range(0,len(ids),64)]
    start=time.monotonic();cpu=time.process_time();queries=invoke({'mode':'queries','batches':batches},10)
    evaluator_progress.need(isinstance(queries,list) and len(queries)==len(batches) and all(isinstance(q,str) and q.startswith('SELECT ') for q in queries),'M7_OPPORTUNITY_QUERY_BINDING')
    preparation={'wallSeconds':time.monotonic()-start,'observerProcessCpuSeconds':time.process_time()-cpu,'nodeCalls':1,'sqlQueries':0}
    def capture(timeout=None):
        if timeout is None:timeout=evaluator_opportunities.ROUND_SECONDS
        evaluator_progress.need(type(timeout) in (int,float) and math.isfinite(timeout) and timeout>0,'M7_OPPORTUNITY_DEADLINE')
        require(digest(config_path)==source_sha,'M7_OPPORTUNITY_SOURCE_CHANGED')
        start=time.monotonic();cpu=time.process_time();deadline=start+min(timeout,evaluator_opportunities.ROUND_SECONDS);rows=[];used=0;count=0
        cost={'sqlQueries':0,'rawSqlBytes':0,'nodeCalls':0}
        try:
            for query in queries:
                remaining=min(deadline-time.monotonic(),until-time.time() if until is not None else float('inf'));evaluator_progress.need(remaining>0,'M7_OPPORTUNITY_DEADLINE')
                ms=max(1,min(4000,int(remaining*1000)-100))
                raw=psql(d,"BEGIN; SET LOCAL statement_timeout='"+str(ms)+"ms';\n"+query+"\nCOMMIT;",database,timeout=min(5,remaining))
                count+=1;used+=len(raw.encode());cost.update(sqlQueries=count,rawSqlBytes=used)
                evaluator_progress.need(used<=evaluator_opportunities.ROUND_BYTES,'M7_OPPORTUNITY_BYTE_BOUND')
                rows.extend(json.loads(line) for line in raw.splitlines() if line)
            remaining=deadline-time.monotonic();evaluator_progress.need(remaining>0,'M7_OPPORTUNITY_DEADLINE')
            cost['nodeCalls']=1;snapshot=invoke({'mode':'snapshot','rows':rows,'ids':ids},remaining)
            evaluator_progress.need(time.monotonic()<=deadline,'M7_OPPORTUNITY_DEADLINE')
            return snapshot,{**cost,'wallSeconds':time.monotonic()-start,'observerProcessCpuSeconds':time.process_time()-cpu}
        except Exception as error:
            error.opportunityCost={**cost,'wallSeconds':time.monotonic()-start,'observerProcessCpuSeconds':time.process_time()-cpu};raise
    capture.binding=expected;capture.preparation_cost=preparation;capture.source_sha256=source_sha
    capture.query_sha256=hashlib.sha256(json.dumps(queries,separators=(',',':')).encode()).hexdigest()
    return capture


def readiness(d, m):
    reserve_output(d,m,'readiness',('readiness-attempt.json','runtime-readiness.json'))
    ids=sorted(row['id'] for row in document(d/'tenants.private.json'));services=progress_services(d)
    deadline=time.monotonic()+1200;observations=[];queries=0;bytes_seen=0
    while time.monotonic()<deadline and len(observations)<evaluator_progress.POLICY['readinessMaxRounds']:
        value=None
        try:
            value=evaluator_progress.round_view(services,ids,lambda *args:progress_fetch(d,*args),warming=True,allow_unavailable=m.get('runPurpose')=='discovery',allow_clinical_stall=discovery_rest.selected(m))
            queries+=value['queries'];bytes_seen+=value['bytes']
            evaluator_progress.need(queries<=evaluator_progress.POLICY['readinessMaxQueries'] and bytes_seen<=evaluator_progress.POLICY['readinessMaxBytes'],'M7_EVALUATOR_PROGRESS_READINESS_BUDGET')
            if m.get('runPurpose')!='discovery':evaluator_progress.need(all(row['completedAcquisitions']>0 for row in value['owners'].values()),'M7_EVALUATOR_PROGRESS_WARMING')
            if m.get('runPurpose')=='discovery':
                time.sleep(.25)
                confirmed=evaluator_progress.round_view(services,ids,lambda *args:progress_fetch(d,*args),warming=True,allow_unavailable=True,allow_clinical_stall=discovery_rest.selected(m))
                queries+=confirmed['queries'];bytes_seen+=confirmed['bytes']
                evaluator_progress.need(queries<=evaluator_progress.POLICY['readinessMaxQueries'] and bytes_seen<=evaluator_progress.POLICY['readinessMaxBytes'],'M7_EVALUATOR_PROGRESS_READINESS_BUDGET')
                admission=evaluator_progress.stable_discovery_baseline(value,confirmed,ids,allow_clinical_stall=discovery_rest.selected(m))
                write(d/'readiness-stable-baseline.private.json',evaluator_progress.pack({'rounds':[value,confirmed]}))
                observations.append({'verdict':admission['availability']['verdict'],**admission})
            else:
                evaluator_progress.need(all(row['failedCompletions']==0 for row in value['owners'].values()),'M7_EVALUATOR_PROGRESS_ERROR','FAIL')
            observations.append({'verdict':'PASS','queries':value['queries'],'bytes':value['bytes'],'wallSeconds':value['wallSeconds']})
            result={'verdict':admission['availability']['verdict'] if m.get('runPurpose')=='discovery' else 'PASS','policy':evaluator_progress.POLICY,'observations':observations,'meaning':'sampled evaluator availability; UNMEASURED availability does not stop discovery REST; durable completion is separate'}
            if result['verdict']=='FAIL' and discovery_rest.selected(m):
                result.update(clinicalVerdict='FAIL',clinicalCode=discovery_rest.CODE,restCollectionPermitted=True,capacityAcceptance='NOT_GRANTED',sourceBinding=discovery_rest.binding(m))
            write(d/'runtime-readiness.json',result)
            return result
        except evaluator_progress.Refused as error:
            cost=getattr(error,'collection',{})
            if value is None:queries+=cost.get('queries',0);bytes_seen+=cost.get('bytes',0)
            else:cost={k:value[k] for k in ('queries','bytes','wallSeconds')}
            observations.append({'verdict':error.verdict,'code':str(error),'collection':cost,
                                 'diagnostic':getattr(error,'diagnostic',None) or ({'predicate':'COMPLETED_ACQUISITION_REQUIRED','field':'completedAcquisitions'} if str(error)=='M7_EVALUATOR_PROGRESS_WARMING' else None)})
            if queries>evaluator_progress.POLICY['readinessMaxQueries'] or bytes_seen>evaluator_progress.POLICY['readinessMaxBytes']:
                error=evaluator_progress.Refused('M7_EVALUATOR_PROGRESS_READINESS_BUDGET')
            write(d/'runtime-readiness.json',{'verdict':error.verdict,'policy':evaluator_progress.POLICY,'observations':observations})
            if error.verdict=='FAIL' or str(error) not in ('M7_EVALUATOR_PROGRESS_WARMING','M7_EVALUATOR_PROGRESS_ERROR','M7_EVALUATOR_PROGRESS_GATE','M7_EVALUATOR_PROGRESS_COVERAGE'):raise
        time.sleep(15)
    raise evaluator_progress.Refused('M7_RUNTIME_NOT_READY')


@contextlib.contextmanager
def loadgen_process(d, process):
    stopped = threading.Event()
    def observe():
        with (d / "load/loadgen.jsonl").open("w") as output:
            while not stopped.is_set() and process.poll() is None:
                try:
                    raw = Path("/proc/"+str(process.pid)+"/stat").read_text().split(")",1)[1].split()
                    status = Path("/proc/"+str(process.pid)+"/status").read_text()
                    rss = re.search(r"^VmRSS:\s+(\d+)",status,re.M)
                    output.write(json.dumps({"at":time.time(),"pid":process.pid,"cpuTicks":int(raw[11])+int(raw[12]),"clockTicksPerSecond":os.sysconf('SC_CLK_TCK'),"rssKiB":int(rss[1]) if rss else None})+"\n")
                    output.flush()
                except (OSError,IndexError):break
                stopped.wait(2)
    thread=threading.Thread(target=observe,daemon=True);thread.start()
    try:yield
    finally:stopped.set();thread.join(timeout=3)


def run(d,m,k6_image,oneoff=None):
    reserve_output(d,m,'run',('run-attempt.json','summary.json','run-before-host.json','runtime-readiness.json','idle-disabled','idle','load'))
    if m.get('runPurpose','acceptance')=='discovery':
        from discovery import run_discovery
        return run_discovery(sys.modules[__name__],d,m,k6_image,**({'oneoff':oneoff}if oneoff else{}))
    try:return run_cell(d,m,k6_image)
    except Exception as error:
        if m.get('measurementMode')=='unaccepted':
            prior=document(d/'summary.json') if (d/'summary.json').exists() else {}
            write(d/'unaccepted-collection-failure.json',{**measurement_output(m,complete=False),'pair':m['pair'],'instrument':m['instrument']['sha256'],'imageId':m['imageId'],
                  'correctnessVerdict':prior.get('verdict','UNMEASURED'),'publicCode':str(error) if re.fullmatch(r'M7_[A-Z_]+',str(error)) else 'M7_UNACCEPTED_COLLECTION_REFUSED'})
        raise


def settings_fingerprint(d,m):
    with private_commands(d/'source-node-checks'/'settings-fingerprint'/uuid.uuid4().hex, max_output_bytes=262144):
        return json.loads(command(['node',HERE/'fingerprint.cjs',d/'core',m['pair']['core'],d/'state/primer/config.json',str(m['tenants'])],phase='settings-fingerprint'))


def static_runtime_contract(d,m):
    import yaml
    config=document(d/'frozen.compose.json')
    state_docs=static_topology.state_documents(m,config,d/'state')
    state_result=static_topology.verify_documents(m,state_docs)
    producer=yaml.safe_load((d/'state/pgstream/pgstream.yaml').read_text())
    state_result['producer']=static_topology.verify_producer(m,state_docs,producer)
    write(d/'static-runtime-documents.json',state_result)
    state_path=d/'static-runtime-plan.private.json';write(state_path,state_docs)
    with private_commands(d/'source-node-checks'/'static-runtime-plan'/uuid.uuid4().hex, max_output_bytes=262144):
        parsed=json.loads(command(['node',d/'core/bin/nightscout.js','plan','check',state_path],cwd=d/'core',phase='static-runtime-plan'))
    require(parsed.get('ok') is True,'M7_STATIC_RUNTIME_PLAN_REFUSED')
    return state_result


def sample_context(d,m):
    code=(HERE/'execution-context.cjs').read_text()+"\nconst context=module.exports.inspect('/opt/app','/opt/app/node_modules',['pg']);const values=require('/opt/app/deploy/multitenant/service-environment').read();const key=process.argv[2]==='evaluator'?'MULTITENANT_EVALUATOR_CONFIG':'MULTITENANT_REALTIME_CONFIG';const file=values[key];const bytes=require('/opt/app/lib/server/serve/config-file').read(file,{source:process.env,label:key,Type:Error});context.privateConfig={path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};console.log(JSON.stringify(context));"
    config=document(d/'frozen.compose.json')
    if m.get('staticTopology'):
        code=(HERE/'execution-context.cjs').read_text()+"\nconst context=module.exports.inspect('/opt/app','/opt/app/node_modules',['pg']);const values={...process.env,...require('/opt/app/deploy/multitenant/service-environment').read()};const key={api:'MULTITENANT_PREVIEW_CONFIG',evaluator:'MULTITENANT_EVALUATOR_CONFIG',realtime:'MULTITENANT_REALTIME_CONFIG','socket-edge':'UI_PUBLIC_CONFIG'}[process.argv[2]];const file=values[key];const bytes=require('/opt/app/lib/server/serve/config-file').read(file,{source:process.env,label:key,Type:Error});context.privateConfig={path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};console.log(JSON.stringify(context));"
        targets=list(m['servingInstances'])+['socket-edge']
        contexts={name:json.loads(compose(d,'exec','-T','--workdir','/opt/app',name,'node','-',('socket-edge' if name=='socket-edge' else m['servingInstances'][name]['role']),input=code.encode())) for name in targets}
        expected={}
        for name in targets:
            mounts=[v for v in config['services'][name].get('volumes',[]) if v.get('target')=='/run/ns-config']
            require(len(mounts)==1 and mounts[0].get('type')=='bind' and mounts[0].get('read_only') is True,'M7_STATIC_CONFIG_MOUNT')
            source=Path(mounts[0]['source']).resolve();require(source.is_relative_to((d/'state').resolve()),'M7_STATIC_CONFIG_MOUNT')
            expected[name]=digest(source/'config.json')
        require(all(value['privateConfig']['sha256']==expected[name] for name,value in contexts.items()),'M7_SAMPLE_PRIVATE_CONFIG_MISMATCH')
    else:
        contexts={role:json.loads(compose(d,'exec','-T','--workdir','/opt/app',role,'node','-',config['services'][role]['command'][-1],input=code.encode())) for role in service_roster(config) if config['services'][role]['command'][-1] in ('evaluator','realtime')}
        require(all(value['privateConfig']['sha256']==digest(d/'state'/role/'config.json') for role,value in contexts.items()),'M7_SAMPLE_PRIVATE_CONFIG_MISMATCH')
    write(d/'image-dependency-contexts.json',contexts)
    if m.get('staticTopology'):static_runtime_contract(d,m)
    evaluator=document(d/'state/evaluator/config.json');realtime=document(d/'state/realtime/config.json')
    code="const o=require(process.argv[1]);const fs=require('fs');console.log(JSON.stringify(o.source(JSON.parse(fs.readFileSync(process.argv[2])),JSON.parse(fs.readFileSync(process.argv[3])),JSON.parse(process.argv[4]))));"
    completion=json.loads(command(['node','-e',code,HERE/'completed-oracle.cjs',d/'state/evaluator/config.json',d/'state/realtime/config.json',json.dumps({'kind':m.get('completionContract'),'pair':m['pair'],'imageId':m['imageId'],'instrument':m['instrument']['sha256']})]))
    sql_roles=sql_attribution.identities(evaluator,[document(d/'state'/role/'env.json') for role in ('evaluator','realtime')])
    observed_roles=psql(d,'SELECT rolname FROM pg_roles;').splitlines()
    require({role for values in sql_roles.values() for role in values}<=set(observed_roles),'M7_SQL_ROLE_MISSING')
    write(d/'completion-source.json',completion);write(d/'sql-identities.json',sql_roles)
    return completion,sql_roles


def preflight(d,m,k6_image,oneoff=None):
    require(m['profile']=='pgstream-sample','M7_SAMPLE_PREFLIGHT_PROFILE')
    frozen(m,'run');verify(d,m);image(m);verify_generator(d,m)
    k6_id=json.loads(command(['docker','image','inspect',k6_image]))[0]['Id']
    return sample_preflight(d,m,k6_id,**({'oneoff':oneoff}if oneoff else{}))


def verify_edge_workers(text, budget):
    workers=re.findall(r'^\s*worker_processes\s+([^;]+);',text,re.M)
    connections=re.findall(r'worker_connections\s+([^;]+);',text)
    nofile=re.findall(r'^\s*worker_rlimit_nofile\s+([^;]+);',text,re.M)
    require(workers==[str(budget['workerProcesses'])] and connections==[str(budget['workerConnections'])] and nofile==[str(diagnostic_resources.EDGE_NOFILE)],'M7_EDGE_WORKER_CONFIGURATION')
    return {'workerProcesses':int(workers[0]),'workerConnections':int(connections[0])}


def project_edge_workers(text, budget):
    """Project an explicit allocation into exact source-rendered numeric fields.

    The known source-rendered baseline and descriptor budget must match before
    replacement. All admission, trust and route bytes remain source output.
    """
    require(budget.get('source')=='explicit-resource-allocation-v1','M7_EDGE_PROJECTION_SELECTION')
    verify_edge_workers(text,{'workerProcesses':1,'workerConnections':16384})
    text=re.sub(r'(^\s*worker_processes\s+)[^;]+;',lambda match:match[1]+str(budget['workerProcesses'])+';',text,flags=re.M)
    text=re.sub(r'(worker_connections\s+)[^;]+;',lambda match:match[1]+str(budget['workerConnections'])+';',text)
    verify_edge_workers(text,budget)
    return text


def edge_runtime(d,m):
    budget=m.get('edgeWorkerBudget')
    if budget is None:return None
    require({key:budget[key] for key in ('workerProcesses','workerConnections','nginxMillicpus','source')}==diagnostic_resources.edge_worker_budget(m['diagnosticResources']['profile']),'M7_EDGE_WORKER_BUDGET_CHANGED')
    rows=[row for row in resources(m,False) if row['Config']['Labels'].get('com.docker.compose.service')=='nginx']
    require(len(rows)==1,'M7_EDGE_RUNTIME_ROSTER')
    row=rows[0]
    text=command(['docker','exec',row['Id'],'nginx','-T'])
    observed=verify_edge_workers(text,budget)
    return {'status':'PASS','containerId':row['Id'],'source':'exact-owned-nginx-T','configurationSha256':hashlib.sha256(text.encode()).hexdigest(),**observed}


def sample_preflight(d,m,k6_id,oneoff=None):
    # New setup attempts preserve deployment and all failed collector artifacts.
    # No timed phase or counter reset exists until these reads succeed.
    attempt=d/'setup-attempts'/uuid.uuid4().hex;attempt.mkdir(parents=True,mode=0o700)
    status={'status':'UNMEASURED','scope':'instrument setup only; no capacity acceptance'}
    with private_commands(attempt/'commands'):
        try:
            status['collectorFiles']=collection_segments.preflight(d,m)
            edge=edge_runtime(d,m)
            if edge is not None:write(attempt/'edge-worker-runtime.json',edge)
            if m.get('pgstreamTopology')==stream_topology.EXTERNAL:
                stream_topology.verify_config(m,document(d/'frozen.compose.json'))
                stream_topology.external_runtime(diagnostic_resource_rows(m),m)
            if m.get('staticTopology'):
                write(attempt/'static-runtime-roster.json',static_topology.verify_runtime(m,document(d/'frozen.compose.json'),resources(m,False)))
            completion,roles=sample_context(d,m)
            phase_snapshot(d,attempt,'readability')
            sql_attribution.statements(attempt/'readability-pg-statements.tsv')
            snapshots=document(attempt/'readability-cgroups.json')['roles']
            stream_topology.readable_processes(snapshots,m)
            sender=clinical_timeline.sender_runtime(d,m,diagnostic_resource_rows(m),snapshots.get('pgstream',{})) if m.get('clinicalSender') else None
            if sender is not None:write(attempt/'clinical-sender-runtime.json',sender)
            version=(lambda argv,**kw:oneoff('k6-version',argv,**kw)if oneoff else command(argv,**kw))(bounded_k6_argv(['docker','run','--rm','--network','none','--label',OWNER+'='+m['owner'],'--label','com.docker.compose.project='+m['project'],k6_id,'version']),timeout=30)
            require('k6' in version.lower(),'M7_SAMPLE_LOADGEN_CONTEXT')
            help_text=(lambda argv,**kw:oneoff('k6-help',argv,**kw)if oneoff else command(argv,**kw))(bounded_k6_argv(['docker','run','--rm','--network','none','--label',OWNER+'='+m['owner'],'--label','com.docker.compose.project='+m['project'],k6_id,'run','--help']),timeout=30)
            require('--summary-export' in help_text,'M7_SAMPLE_LOADGEN_EXPORT')
            write(attempt/'loadgen.json',{'imageId':k6_id,'version':version})
            with sampling(d,attempt):time.sleep(2*m['cadence'].get('samplerIntervalSeconds',2)+2)
            import csv
            from reduce import memory
            with (attempt/'docker-stats.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
            require(rows,'M7_SAMPLE_SAMPLER_EMPTY')
            for row in rows:
                require(math.isfinite(float(row['cpu_pct'].rstrip('%'))),'M7_SAMPLE_SAMPLER_CPU')
                memory(row['mem'].split('/')[0])
            seen={row['container'].removeprefix(m['project']+'-').removesuffix('-1') for row in rows}
            require(set(snapshots)<=seen,'M7_SAMPLE_SAMPLER_ROSTER')
            status.update(status='CHECKED',samplerIntervalSeconds=m['cadence'].get('samplerIntervalSeconds',2))
            return completion,roles
        except Exception as error:
            status.update(status='FAILED',code=str(error) if re.fullmatch(r'M7_[A-Z_]+',str(error)) else 'M7_SAMPLE_SETUP_REFUSED');raise
        finally:
            for name in ('image-dependency-contexts.json','completion-source.json','sql-identities.json'):
                if (d/name).is_file():shutil.copyfile(d/name,attempt/name)
            write(attempt/'setup.json',status)


def sample_results(d,probe,sql_roles):
    require(probe.get('completedOutput',{}).get('verdict')=='PASS','M7_COMPLETED_OUTPUT_ORACLE')
    result={name:sql_attribution.assess(sql_attribution.statements(d/name/'before-pg-statements.tsv'),sql_attribution.statements(d/name/'after-pg-statements.tsv'),sql_roles) for name in ('idle-disabled','idle','load')}
    write(d/'sql-attribution.json',result)
    companion={}
    for phase in ('idle-disabled','idle','load'):
        sql=[d/phase/(side+'-pg-costs.json') for side in ('before','after')]
        rt=[d/phase/(side+'-realtime-costs.json') for side in ('before','after')]
        companion[phase]={'sql':cost_companion.assess(*(document(p) for p in sql)) if all(p.is_file() for p in sql) else {'status':'NO-INSTRUMENT','reason':'M7_COST_BOOKEND_UNAVAILABLE'},
                          'realtime':realtime_costs.assess(*(document(p) for p in rt)) if all(p.is_file() for p in rt) else {'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_BOOKEND_UNAVAILABLE'}}
    write(d/'cost-companion-assessment.json',{'version':1,'scope':'next pinned instrument only; raw snapshots unchanged; shared SQL-role costs remain combined','phases':companion})
    return result


def run_cell(d, m, k6_image):
    require(m.get("profile")!="fresh-image-diagnostic","M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY")
    frozen(m,"run");quiet(d,m,"run-before",check_load=False);verify(d,m);image(m)
    require((d / "deploy-before-host.json").exists(), "M7_DEPLOY_QUIET_RECORD_REQUIRED")
    verify_generator(d,m)
    readiness(d, m)
    k6_id = json.loads(command(["docker", "image", "inspect", k6_image]))[0]["Id"]
    write(d / "loadgen-image.json", {"k6": k6_id, "generator": m["generator"]})
    completion,sql_roles=sample_preflight(d,m,k6_id) if m['profile']=='pgstream-sample' else ({},None)
    # Sparse once-per-phase cgroups/PG snapshots plus a sampler-disabled idle
    # window make collection overhead observable independently of tenant work.
    out = d / "idle-disabled";out.mkdir()
    psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before");time.sleep(m["cadence"].get("warmupSeconds",60));phase_snapshot(d, out, "after")
    for name, seconds in (("idle", m["cadence"]["idleSeconds"]),):
        out = d / name;out.mkdir();quiet(d, m, name + "-before", check_load=False)
        psql(d, "SELECT pg_stat_statements_reset();")
        idle_progress=enabled_idle(d,m,out,seconds)
    out = d / "load";out.mkdir()
    runid = "m7-" + m["owner"][:12];(out / "runid").write_text(runid)
    spec = m["project"] + "|" + str(d / "env") + "|" + str(d / "frozen.compose.json")
    probe_env = runtime_env({"M7_GENERATOR_ROOT": str(d / "dependencies"), "M7_RESTART_ROLES": json.dumps(m["restartRoles"]), "M7_EVALUATOR_SERVICES": json.dumps(progress_services(d)), "M7_PROGRESS_PYTHON": sys.executable, "M7_PROGRESS_ATTRIBUTION":json.dumps(progress_attribution(m)), "STOCK_MS": "300000", "RECOVERY_MS": "120000", **({"M7_COMPLETION_SOURCE":json.dumps(completion)} if completion else {})})
    probe_env.update(clinical_timeline.probe_environment(m))
    probe_env.update(revision_witness.probe_environment(d,m))
    psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before-prime")
    probe_log = (out / "probe.log").open("wb")
    with sampling(d, out):
        probe_process = diagnostic_resources.popen(subprocess.Popen, [m["generator"]["tools"]["node"]["path"], str(d / "probe.js"), "--base", "http://127.0.0.1:" + str(m["port"]), "--tenants", str(d / "tenants.private.json"), "--compose", spec,
            "--runid", runid, "--clients", str(viewer_plan.total(m)), "--per", str(m["cadence"].get("socketsPerTenant",2)), "--open", "5", "--window", str(m["cadence"]["loadSeconds"]), "--probeEvery", str(m["cadence"].get("probeEveryMs",3000)), "--restart", "1" if m["cadence"].get("restart",True) else "0", "--evalTimeout", "900", "--out", str(out / "probe.json"), "--signal", str(out / ".window")], env=probe_env, stdout=probe_log, stderr=subprocess.STDOUT)
        job_record(out/"probe-job.json",probe_process,m["owner"])
        try:
            deadline = time.monotonic() + 600
            while not (out / ".window").exists():
                require(probe_process.poll() is None and time.monotonic() < deadline, "M7_PROBE_NOT_PRIMED")
                time.sleep(1)
            quiet(d, m, "load-before", check_load=False)
            phase_snapshot(d, out, "after-prime")
            psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before")
            monitor = loadgen_process(d, probe_process);monitor.__enter__()
            with observe_progress(d,m,out,'load') as load_progress, (out / "k6.log").open("wb") as output:
                command(["docker", "run", "--rm", "--name", m["project"] + "-k6", "--label", OWNER + "=" + m["owner"], "--label", "com.docker.compose.project=" + m["project"], "--label", "com.docker.compose.service=k6",
                    "--network", "host", "-u", str(os.getuid()) + ":" + str(os.getgid()), "-v", str(d / "k6") + ":/scripts:ro", "-v", str(out) + ":/out", "-v", str(d / "tenants.private.json") + ":/tenants.private.json:ro",
                    "-e", "BASE_URL=http://127.0.0.1:" + str(m["port"]), "-e", "TENANTS_FILE=/tenants.private.json", "-e", "RUN_ID=" + runid,
                    "-e", "SETTINGS_FINGERPRINT=" + m["settingsFingerprint"]["sha256"],
                    "-e", "RUN_START=" + str(int(time.time()*1000)), "-e", "DURATION=" + str(m["cadence"]["loadSeconds"]), "-e", "ACCEL="+str(m["cadence"]["accel"]), "-e", "HOT_FACTOR="+str(m["cadence"]["hotFactor"]), "-e", jwt_setup_env(m),
                    *(["-e","OFFERED_RPS="+str(m["cadence"]["offeredRps"])] if "offeredRps" in m["cadence"] else []), "-e", "SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status", k6_id, "run", "--quiet", "--summary-export", "/out/k6-summary.json", "/scripts/workload.js"], file=output, timeout=m["cadence"]["loadSeconds"]+600)
            phase_snapshot(d, out, "after")
            (out / ".restart").touch()
            require(probe_process.wait(timeout=1500) == 0, "M7_PROBE_FAILED")
        finally:
            stop_job(out/"probe-job.json",m["owner"])
            probe_process.wait(timeout=10)
            if "monitor" in locals():monitor.__exit__(None,None,None)
            probe_log.close()
    phase_snapshot(d, out, "after-reconnect")
    result = count_oracle(d)
    control(d, m)
    host = fixture_inventory(m);write(d / "run-after-host.json", host)
    result_probe = document(out / "probe.json")
    fingerprint_result=profile_provenance.fingerprint_check(document(out/"k6-summary.json")["metrics"])
    completed_output=result_probe.get('completedOutput')
    if completion:
        attributed=sample_results(d,result_probe,sql_roles)
    from viewer_plan import check as check_viewers, total as viewer_total
    viewer_result=check_viewers(m,document(d/'tenants.private.json'),result_probe,document(out/'fanout.json')['probeWrites']['byTenant'])
    correctness = [result["verdict"] == "GREEN", result["uncertain"] == 0, not any(not r["owned"] for r in host["containers"]),
                   result_probe["prime"]["primed"] == viewer_total(m), result_probe["window"]["deliveredFrames"] == result_probe["window"]["expectedFrames"],
                   (not m["cadence"].get("restart",True) or result_probe["restart"]["stockRecovered"] == viewer_total(m)), (not m["cadence"].get("restart",True) or result_probe["restart"]["runtimeAcquisitionObservation"].get("verdict") == "PASS" and result_probe["restart"]["runtimeAcquisitionObservation"]["missing"] == 0),
                   metric(document(out / "k6-summary.json")["metrics"], "writes_refused") == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "http_req_failed", "rate") == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "dropped_iterations") == 0,
                   result_probe["window"]["writes"]["failed"] == 0, fingerprint_result["verdict"]=="PASS", idle_progress.result["verdict"]=="PASS", load_progress.result["verdict"]=="PASS"]
    summary = {"pair": m["pair"], "hostIdentity":m["hostIdentity"], "profile":m["profile"], "instrument": m["instrument"]["sha256"], "tenants": m["tenants"], "replicas": m["replicas"],
               "imageId":m["imageId"], "verdict": "PASS" if all(correctness) else "FAIL", "correctness": correctness, "cadence": m["cadence"],
               "viewerFrames":viewer_result, "completedOutput":completed_output or "NOT_SELECTED", "sqlAttribution":attributed if completion else "NOT_SELECTED",
               "oracle": {key: value for key, value in result.items() if key != "rows"}, "probe": result_probe,
               "profileSelection":m["profileSelection"],"settingsFingerprint":m["settingsFingerprint"],"settingsFingerprintObservation":fingerprint_result,
               "evaluatorProgressCollectionCosts":{**{phase:document(d/phase/"evaluator-progress-publication.json") for phase in ("idle","load")},"idleTail":document(d/"idle/evaluator-tail-publication.json") if (d/"idle/evaluator-tail-publication.json").is_file() else None,"recovery":document(out/"evaluator-recovery.private.json.publication.json") if m["cadence"].get("restart",True) else "NOT_RUN"},
               "evaluatorProgress":{**{phase:progress_summary(d/phase) for phase in ("idle","load")},"recovery":{**{k:v for k,v in result_probe["restart"]["runtimeAcquisitionObservation"].items() if k not in ("baselineObservation","evidence")},**result_probe["restart"]["runtimeAcquisitionObservation"]["evidence"]} if m["cadence"].get("restart",True) else "NOT_RUN"},
               "performanceThresholds": "none invented; raw latency/CPU/RSS/PG metrics are measurements, not predeclared capacity limits"}
    from reduce import measurements
    summary["measurements"] = measurements(d, m)
    require(summary["measurements"]["complete"], "M7_NO_MEASUREMENT")
    summary.update(measurement_output(m))
    write(d / "summary.json", summary)
    metrics = document(out / "k6-summary.json")["metrics"]
    require(metric(metrics,"writes_refused")==0 and metric(metrics,"responses_refused")==0,"M7_FUNCTIONAL_REQUEST_REFUSAL")
    require(fingerprint_result["verdict"]=="PASS","M7_FUNCTIONAL_SETTINGS_FINGERPRINT")
    require(summary["verdict"] == "PASS", "M7_CORRECTNESS_GROWTH_GATE_FAILED")


def diagnostic_observed_code(out):
    try:
        file=out/'diagnostic-observations.json'
        if file.stat().st_size>1048576:return 'M7_DIAGNOSTIC_CLIENT_REFUSED'
        value=document(file);code=value.get('failureCode') if isinstance(value,dict) else None
        if isinstance(code,str) and re.fullmatch(r'M7_DIAGNOSTIC_[A-Z_]{1,64}',code):return code
    except (OSError,ValueError):pass
    return 'M7_DIAGNOSTIC_CLIENT_REFUSED'


def diagnose(d,m):
    require(m.get("profile")=="fresh-image-diagnostic","M7_DIAGNOSTIC_PROFILE_REQUIRED")
    scope=frozen(m,"diagnose");experiment_host(d,m,"diagnostic-before");verify(d,m);image(m)
    verify_generator(d,m)
    out=d/"load";out.mkdir()
    marker="diagnostic-"+m["owner"][:12];(out/"runid").write_text(marker)
    env=runtime_env({"NODE_PATH":str(d/"dependencies/node_modules")})
    failure=None;client_exit=None
    try:
        with (out/"diagnostic.log").open("wb") as log:
            process=diagnostic_resources.popen(subprocess.Popen, [m["generator"]["tools"]["node"]["path"],str(HERE/"diagnostic.cjs"),str(d),str(scope["trafficSeconds"])],env=env,stdout=log,stderr=subprocess.STDOUT)
            job=out/"diagnostic-job.json";job_record(job,process,m["owner"])
            try:
                try:client_exit=process.wait(timeout=scope["trafficSeconds"]+15)
                except subprocess.TimeoutExpired:raise RuntimeError('M7_DIAGNOSTIC_CLIENT_EXIT_TIMEOUT')
                require(client_exit>=0,'M7_DIAGNOSTIC_CLIENT_TERMINATED')
                require(client_exit==0,diagnostic_observed_code(out))
            finally:stop_job(job,m["owner"]);process.wait(timeout=10)
        counted=count_oracle(d)
        require(counted["verdict"]=="GREEN","M7_ORACLE_DIAGNOSTIC_RED")
        oracle_control(d)
        outcome=document(out/"diagnostic-observations.json")
        result={"kind":"m7-joined-fresh-image-diagnostic","profile":m["profile"],"pair":m["pair"],"instrument":m["instrument"]["sha256"],
                "hostIdentity":m["hostIdentity"],"imageId":m["imageId"],"tenants":m["tenants"],"replicas":m["replicas"],"verdict":"PASS",
                "profileSelection":m["profileSelection"],"settingsFingerprintObservation":"UNMEASURED; diagnostic is not k6 capacity",
                "checks":outcome["checks"],"acceptedWrites":outcome["acceptedWrites"],"dataHttpRequests":outcome["dataHttpRequests"],**{key:outcome[key] for key in ("httpAccountingVersion","criterionHttpRequests","physicalHttpRequests","warmProbeHttpRequests","trailRecords","trailBytes")},"oracle":counted["verdict"],"oracleControl":document(out/"oracle-control.json"),
                "fullAcceptance":"NOT_RUN","capacity":"NO-MEASUREMENT","trafficDeadlineSeconds":scope["trafficSeconds"]}
        diagnostic_check(result);write(d/"diagnostic.json",result)
        print("M7_DIAGNOSTIC_PASS_ONLY")
    except Exception as error:
        failure=str(error) if str(error).startswith("M7_") else "M7_DIAGNOSTIC_REFUSED"
        write(d/"diagnostic.json",{"kind":"m7-joined-fresh-image-diagnostic","pair":m["pair"],"instrument":m["instrument"]["sha256"],"imageId":m["imageId"],"hostIdentity":m["hostIdentity"],"verdict":"FAIL","error":failure,"clientExitCode":client_exit,"observedFailureCode":diagnostic_observed_code(out),"requestTrail":"load/diagnostic-http.json" if (out/"diagnostic-http.json").exists() else None,"fullAcceptance":"NOT_RUN","capacity":"NO-MEASUREMENT"})
        raise


def down(d,m):
    token=_CLEANUP_NODE_LIMIT.set('diagnosticResources' in m)
    restore_error=None
    try:
        if m.get('vaultRefusalControl') and (d/'state/bootstrap/m7-api-vault-policy.original.private.json').is_file():
            try:vault_control(d,m,'restore')
            except BaseException as error:
                restore_error=error
                write(d/'vault-refusal/restore-failure.json',{'code':'M7_VAULT_CONTROL_RESTORE_FAILED','type':type(error).__name__})
        try:return _down(d,m)
        finally:
            if restore_error is not None and sys.exc_info()[0] is None:raise restore_error
    finally:_CLEANUP_NODE_LIMIT.reset(token)



def _down(d, m):
    for file in list(d.glob("*/sampler-job.json"))+list(d.glob("*/probe-job.json"))+list(d.glob("*/diagnostic-job.json")):stop_job(file,m["owner"])
    assert_owned(m)
    try:terminal_snapshot(d,m)
    except Exception as error:
        write(d/'terminal-capture-unavailable.json',{'status':'UNMEASURED','type':type(error).__name__})
    if m.get('attached'):
        write(d/'instrument-jobs-stopped.json',{'runtimeResources':'UNCHANGED','cleanupOwner':'runtime owner'});return
    if m.get("prepared"):
        verify(d, m, teardown=True)
        config=document(d/"frozen.compose.json")
        sender_cleanup=clinical_timeline.sender_cleanup_observation(config,d,m)
        if sender_cleanup is not None:write(d/("clinical-sender-cleanup-observation-"+uuid.uuid4().hex+".json"),sender_cleanup)
        try:captured=profile_provenance.capture_logs(d/"role-logs",config,lambda role:["docker","compose","-p",m["project"],"--env-file",str(d/"env"),"-f",str(d/"frozen.compose.json"),"logs","--no-color","--no-log-prefix","--timestamps","--tail","1000",role],seconds=remaining_seconds(5*len(config['services']))/max(1,len(config['services'])))
        except Exception:captured={"version":1,"scope":"PRIVATE","error":"capture-failed","complete":False}
        write(d/"role-logs/manifest.json",captured)
        compose(d, "--profile", "ops", "down", "--volumes", "--remove-orphans", timeout=120)
        for row in resources(m):
            owned(row,m["owner"]);command(["docker","rm","--force","--volumes",row["Id"]])
    else:
        require(not resources(m), "M7_PARTIAL_PREPARE_HAS_RESOURCES")
    write(d/'cleanup-absence.json',assert_absent(m))
    if m.get('clinicalTimeline'):
        try:clinical_timeline.retain(d,m)
        except Exception as error:write(d/'clinical-timeline-retain-refusal.json',{'status':'UNMEASURED','type':type(error).__name__,'code':'M7_CLINICAL_TIMELINE_RETAIN_REFUSED'})
    core = d / "core"
    if core.exists():
        require(git(core,"rev-parse","HEAD") == m["pair"]["core"], "M7_OWN_CORE_HEAD_CHANGED")
        git(m["coreRepository"], "worktree", "remove", "--force", str(core))
    for file in (d / "state", d / "dependencies"):
        if file.exists():shutil.rmtree(file)
    (d / "tenants.private.json").unlink(missing_ok=True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("directory", "core-repo", "core-commit", "deploy-repo", "deploy-commit", "image"):prep.add_argument("--"+name, required=True)
    prep.add_argument('--static-workers',type=int,choices=range(1,DISCOVERY_MAX_WORKERS+1),help='Explicit selected static evaluator/realtime process count for bounded branch diagnostics')
    prep.add_argument('--static-build-receipt', help='Verified local image-build receipt for a frozen static diagnostic pair')
    prep.add_argument('--static-build-receipt-sha256', help='Exact SHA-256 from the selected diagnostic publication')
    prep.add_argument('--pgstream-topology',choices=(stream_topology.COLOCATED,stream_topology.EXTERNAL),default=stream_topology.COLOCATED)
    prep.add_argument('--node-observation',choices=('off',node_observation.MODE),default='off',
                      help='Bound private ELU and CPU profiles inside each serving Node role during ordinary local demand')
    prep.add_argument('--api-warm-cause',choices=('off',api_warm_cause.MODE,api_warm_cause.STARTUP_MODE),default='off',
                      help='Private correlated warm refusal class for the owned 10000-tenant primer')
    prep.add_argument('--api-cause-observation',choices=('off','on'),default='off',help='Source-pinned private setup-diagnostic observer; file-I/O overhead is separate')
    prep.add_argument('--completion-contract',choices=('evaluator-work-v1','evaluator-work-v2'),help='Explicit source-bound pgstream completion reader; mandatory at sample preflight')
    prep.add_argument('--drain-observation', type=json.loads, help='Optional bounded post-writer catchup observer budget')
    prep.add_argument('--probe-ledger', type=json.loads, help='Discovery probe accounting budgets maxWrites and maxBytes')
    prep.add_argument('--evaluator-catchup',choices=('fixed-target-v1',),help='Read-only post-write drain within existing work deadline; discovery without restart only')
    prep.add_argument('--evaluator-opportunities',choices=('received-input-v1',),help='NEXT explicit trusted SQL opportunity observer; unselected pgstream v2 discovery idle/load')
    prep.add_argument('--fixture-project',help='Owner-selected new Compose project; existing containers, volumes or networks refuse')
    for knob in ('warmup-seconds','idle-seconds','load-seconds','setup-seconds','drain-seconds','accel','hot-factor','sampler-interval'):
        prep.add_argument('--'+knob,type=int,help='Explicit pgstream-sample workload knob; retained in manifest')
    prep.add_argument("--backend-subnet",help="Owner-selected explicit private backend CIDR; pass together with --edge-subnet")
    prep.add_argument("--edge-subnet",help="Owner-selected explicit private edge CIDR")
    prep.add_argument("--postgres-image",help="Existing immutable wal2json PostgreSQL image ID, required for pgstream-sample")
    prep.add_argument("--freeze","--receipt",dest="freeze",required=True)
    prep.add_argument("--run-purpose",choices=("acceptance","discovery"),default="acceptance")
    prep.add_argument("--diagnostics",choices=("off","on"),default="off")
    prep.add_argument("--diagnostics-interval-ms",type=int,default=5000)
    prep.add_argument('--measurement-mode',choices=('accepted','unaccepted'),default='accepted')
    prep.add_argument('--run-id');prep.add_argument('--image-id');prep.add_argument('--maximum-run-minutes',type=int,default=180)
    prep.add_argument('--vault-refusal-control',choices=('api-policy-deny-v1',))
    prep.add_argument('--diagnostic-resource-profile',choices=diagnostic_resources.PROFILES)
    prep.add_argument('--diagnostic-resource-allocation',type=json.loads,help='Explicit finite JSON service/driver allocation and ceiling; exclusive with named profile')
    prep.add_argument('--clinical-sender-binary',help='Explicit reviewed sender binary staged only for the opt-in raw external diagnostic')
    prep.add_argument('--clinical-sender-receipt',help='Immutable reviewed twin CLI build receipt; no command or version fallback')
    prep.add_argument('--revision-witness-targets',help='Private JSON list of one or two synthetic tenant/storedId targets; discovery sample only')
    prep.add_argument('--clinical-intake-targets',help='Private JSON list of one or two synthetic roster tenant IDs for the selected timeline')
    prep.add_argument('--clinical-intake-timeline',choices=('off',clinical_timeline.NAME,clinical_timeline.RAW_NAME),default='off')
    prep.add_argument('--generator-dependencies')
    prep.add_argument('--generator-dependency-receipt')
    prep.add_argument('--generator-dependency-receipt-sha256')
    prep.add_argument('--generator-dependency-preparation')
    prep.add_argument('--generator-dependency-preparation-sha256')
    prep.add_argument('--generator-dependency-preparation-head')
    prep.add_argument("--serial-exchange-diagnostic",action="store_true",help="Receipt-selected3k diagnostic only:64 serial exchanges before/after stock priming; no ordinary traffic")
    prep.add_argument("--profile",choices=tuple(CADENCE),default="capacity")
    prep.add_argument('--sockets-per-tenant',type=int)
    prep.add_argument('--logical-polling-clients',type=int)
    prep.add_argument('--probe-every-ms',type=int)
    prep.add_argument('--driver-shards',type=int)
    prep.add_argument('--driver-vu-diagnostic',choices=driver_vu_diagnostic.MODES,
                      help='Historical matched diagnostic, or configured-v1 with --driver-plan')
    prep.add_argument('--driver-plan',type=json.loads,help='Finite JSON scheduling/VU/observer configuration; selects configured-v1')
    prep.add_argument('--workload-mix', choices=(REALISTIC_MIX,))
    prep.add_argument('--workload-scale', type=float, help='Positive representable realistic-v1 rate multiplier; default1 preserves sensor cadence')
    prep.add_argument("--restart-during-load-after-seconds",type=int,help="Discovery-only planned evaluator restart after actual ordinary scenario demand begins; requires v2 receipt")
    prep.add_argument("--offered-rps",type=float,help="Explicit scenario HTTP arrival rate for pgstream discovery only; preserves mix")
    prep.add_argument("--jwt-setup-concurrency",type=int,default=1,help="Positive integer; discovery batches may exceed the legacy64 reference")
    prep.add_argument("--commissioning-slot-wal-mib",type=int,choices=commissioning_wal.VALUES,help="Explicit finite local commissioning WAL retention; omitted keeps deployment default")
    prep.add_argument('--pgstream-notifier-ack-timeout-ms', type=int,
                      help='Explicit acknowledgment budget for a fresh external pgstream Compose discovery run')
    prep.add_argument('--preload-convergence-seconds', type=int,
                      help='Opt-in finite pre-load source convergence before unchanged normal readiness; local owned-to-completion discovery only')
    prep.add_argument('--preload-convergence-interval-seconds', type=int,
                      help='Interval between original strict pre-load source snapshots')
    prep.add_argument("--tenant-readiness",choices=("serve","all"),help="Explicit selected platform startup readiness, bound into the receipt and serving environment")
    prep.add_argument("--primer-concurrency",type=int,choices=range(1,33),default=1,help="Bounded commissioning workers on a qualified NEXT image; default serial")
    prep.add_argument("--tenants", type=int, required=True);prep.add_argument("--replicas", type=int, required=True, help="Discovery API count 1..16; acceptance retains its fixed grid");prep.add_argument("--quiet-load", type=float, default=3)
    attached=sub.add_parser('attach',parents=[prep],add_help=False)
    for name in ('project','source-root','state','env-file'):attached.add_argument('--'+name,required=True)
    attached.add_argument('--compose',action='append',required=True,help='Existing source Compose files, in original order')
    attached.add_argument('--dependencies-root',help='Explicit runtime-owned lockfile installation root; defaults to the source root')
    attached.add_argument('--runtime-owner',help='Canonical preparation owner.json to bind the explicit source/dependency roots and generator provenance')
    for cmd in ("verify", "build", "deploy", "run", "preflight", "diagnose", "control", "down", "host-identity", "vault-check", "source-preflight"):
        own = sub.add_parser(cmd);own.add_argument("directory")
        if cmd in ("run","preflight"):own.add_argument("--k6-image", required=True)
        if cmd in ("deploy","preflight","run"):own.add_argument("--work-deadline",type=float,help="Existing runner absolute work cutoff; never starts a new window")
    check = sub.add_parser("check-campaign");check.add_argument("summary")
    check = sub.add_parser("check-pilot");check.add_argument("summary")
    check = sub.add_parser("check-discovery");check.add_argument("summary")
    check = sub.add_parser("check-unaccepted-measurement");check.add_argument("summary")
    check = sub.add_parser("check-diagnostic");check.add_argument("summary")
    sub.add_parser("manifest")
    sub.add_parser("capabilities")
    sub.add_parser("measurement-capabilities")
    return p


def main():
    args = parser().parse_args()
    if args.command == "measurement-capabilities":return print(json.dumps(MEASUREMENT_AUTHORIZATION,sort_keys=True))
    if args.command == "capabilities":return print(json.dumps(document(HERE/"capabilities.json"),sort_keys=True))
    if args.command == "manifest":return print(json.dumps(instrument(),indent=2))
    if args.command == "prepare":return prepare(args)
    if args.command == "attach":return attach(args)
    if args.command == "check-campaign":campaign_check(document(args.summary));return print("M7_CAMPAIGN_COMPLETE")
    if args.command == "check-discovery":
        from discovery import check_discovery
        check_discovery(document(args.summary));return print("M7_DISCOVERY_RECORDED_NOT_CAPACITY_ACCEPTANCE")
    if args.command == "check-pilot":pilot_check(document(args.summary));return print("M7_REMOTE_PILOT_COMPLETE")
    if args.command == "check-unaccepted-measurement":unaccepted_check(document(args.summary));return print("M7_UNACCEPTED_COLLECTION_COMPLETE_NOT_ACCEPTANCE")
    if args.command == "check-diagnostic":diagnostic_check(document(args.summary));return print("M7_DIAGNOSTIC_PASS_ONLY")
    d, m = load(args.directory,resource_limits=args.command!="down")
    if m.get('attached'):require(args.command not in ('deploy','build','diagnose'),'M7_ATTACHED_RUNTIME_OWNER_ONLY')
    deadline_limit = workload_inputs.MAX_SECONDS if m.get('runPurpose')=='discovery' else 86400
    if args.command == "host-identity":
        observed=fixture_inventory(m);write(d/"host-identity-inventory.json",observed)
        require(host_identity(observed)==m["hostIdentity"],"M7_HOST_IDENTITY_CHANGED")
        return print(json.dumps({"hostIdentity":m["hostIdentity"],"pair":m["pair"],"instrument":m["instrument"]["sha256"]}))
    if args.command == "verify":verify(d, m);image(m);print("M7_PAIR_AND_INSTRUMENT_PINNED")
    elif args.command == "build":
        require(not m.get("diagnosticResources"),"M7_DIAGNOSTIC_RESOURCE_BUILD_REFUSED")
        frozen(m,"build");experiment_host(d,m,"build-before");verify(d,m)
        overlay = d / "core/deploy/multitenant"
        command(["node", overlay / "build.js"], cwd=overlay, timeout=1800)
    elif args.command == "source-preflight":discovery_source_preflight(d,m)
    elif args.command == "deploy":
        with command_deadline(args.work_deadline):
            if args.work_deadline is not None:require(math.isfinite(args.work_deadline) and 0<args.work_deadline-time.time()<=deadline_limit,'M7_COMMAND_DEADLINE')
            deploy(d, m)
    elif args.command == "preflight":
        with command_deadline(args.work_deadline):
            if args.work_deadline is not None:require(math.isfinite(args.work_deadline) and 0<args.work_deadline-time.time()<=deadline_limit,'M7_COMMAND_DEADLINE')
            preflight(d,m,args.k6_image);print('M7_SAMPLE_INSTRUMENTS_CHECKED_NOT_ACCEPTANCE')
    elif args.command == "run":
        until = args.work_deadline
        if m.get('evaluatorCatchup') is not None:
            require(until is not None or 'drainSeconds' in phase_windows.selection(m.get('cadence', {})),
                    'M7_DRAIN_WORK_DEADLINE_REQUIRED')
        if until is not None:require(math.isfinite(until) and 0<until-time.time()<=deadline_limit,'M7_COMMAND_DEADLINE')
        with command_deadline(until):run(d,m,args.k6_image)
    elif args.command == "diagnose":diagnose(d,m)
    elif args.command == "control":control(d, m)
    elif args.command == "vault-check":vault_control(d,m,"auth-check")
    elif args.command == "down":down(d, m)

if __name__ == "__main__":
    try:main()
    except Exception as error:
        message = str(error)
        print(message if re.fullmatch(r"M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?", message) else "M7_ADAPTER_REFUSED", file=sys.stderr)
        sys.exit(1)
