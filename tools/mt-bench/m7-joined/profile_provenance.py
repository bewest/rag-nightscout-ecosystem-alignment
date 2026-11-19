"""Fixed safe profile identity and bounded private evidence collection."""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
from contract import require
from role_instances import FAMILIES

FLAGS = ('NS_M7_DIAGNOSTICS', 'NS_M7_DIAGNOSTICS_INTERVAL_MS')
LOG_ROLES = ('api','api-2','api-3','api-4','realtime','realtime-2','evaluator','pgstream','admin','feed-reader','tenant-admin','postgres','vault','nginx','socket-edge')

def log_roles(config):
    # Every actual fixed-roster instance participates; no guessed CLI count.
    selected=list(LOG_ROLES)
    for name in config['services']:
        if re.fullmatch(r'(?:api|realtime|evaluator)-(?:[2-9]|1[0-6])', name):
            if name not in selected:selected.append(name)
        elif any(name.startswith(role+'-') for role in FAMILIES):raise RuntimeError('M7_PROFILE_ROLE_UNSUPPORTED')
    return tuple(name for name in selected if name in config['services'])

def selection(mode='off', interval=5000):
    require(mode in ('off','on') and type(interval) is int and 1000 <= interval <= 60000, 'M7_DIAGNOSTICS_SELECTION_INVALID')
    return {'mode':mode,'intervalMs':interval,'environment':{FLAGS[0]:'1' if mode=='on' else '0',FLAGS[1]:str(interval)}}

def select_environment(config, chosen):
    log_roles(config)
    for role, spec in config['services'].items():
        if role in log_roles(config) and role not in ('postgres','vault','nginx','pgstream'):
            environment = spec.setdefault('environment',{})
            require(isinstance(environment,dict),'M7_DIAGNOSTICS_ENV_INVALID')
            require(not any(k.startswith('NS_M7_DIAGNOSTICS') and k not in FLAGS for k in environment),'M7_DIAGNOSTICS_ENV_INVALID')
            environment.update(chosen['environment'])
    verify_environment(config,chosen)

def verify_environment(config, chosen):
    seen = 0
    for role,spec in config['services'].items():
        if role in log_roles(config) and role not in ('postgres','vault','nginx','pgstream'):
            seen += 1
            require(all(spec.get('environment',{}).get(k)==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_ENV_MISMATCH')
    require(seen > 0,'M7_DIAGNOSTICS_ENV_UNMEASURED')

def _log_times(data):
    # Docker --timestamps prefixes are UTC. Partial retained lines are ignored.
    values=re.findall(rb'(?m)^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z) ',data)
    return {'first':values[0].decode() if values else None,'last':values[-1].decode() if values else None}

def capture_logs(directory, config, argv, *, seconds=5, per_role=65536, total=524288):
    """Keep recent bytes and existing disconnect summaries, within fixed budgets.

    The finite producer supplies a fixed Docker tail. Read it to EOF (or the
    time/scan bound), rather than killing it after the first output budget.
    Incomplete streams explicitly describe the most recent OBSERVED bytes,
    not the true source tail. No capture failure prevents owned teardown.
    """
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True);directory.chmod(0o700)
    rows=[];remaining=total
    for role in log_roles(config):
        if role not in config['services']:continue
        row={'role':role,'bytes':0,'truncated':False,'timeout':False,'returncode':None,
             'retention':'recent-observed-tail','observedBytes':0,'omittedBytes':0,'streamComplete':False,
             'captureStartedAtNs':time.time_ns()}
        budget=min(per_role,remaining)
        if not budget:
            row.update(truncated=True,reason='global-byte-cap',captureFinishedAtNs=time.time_ns());rows.append(row);continue
        cause_budget=min(8192,budget//4) if role.startswith('realtime') else 0
        tail_budget=budget-cause_budget
        tail=bytearray();causes=bytearray();pending=bytearray();cause_seen=0
        process=None;selector=selectors.DefaultSelector();scan_limit=max(4194304,budget*64)
        row['scanLimitBytes']=scan_limit
        def cause_line(line):
            nonlocal cause_seen
            if cause_budget and re.match(rb'^(?:\d{4}-\d\d-\d\dT[^ ]+ )?realtime server disconnects in the last \d+ s: ',line):
                cause_seen+=1;causes.extend(line+b'\n')
                if len(causes)>cause_budget:del causes[:-cause_budget]
        try:
            process=subprocess.Popen(argv(role),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            selector.register(process.stdout,selectors.EVENT_READ)
            deadline=time.monotonic()+seconds
            while selector.get_map():
                wait=deadline-time.monotonic()
                if wait <= 0:row['timeout']=True;row['truncated']=True;break
                for key,_ in selector.select(min(wait,.1)):
                    data=os.read(key.fileobj.fileno(),min(8192,scan_limit-row['observedBytes']+1))
                    if not data:selector.unregister(key.fileobj);row['streamComplete']=True;continue
                    row['observedBytes']+=len(data);tail.extend(data)
                    if len(tail)>tail_budget:del tail[:-tail_budget]
                    if cause_budget:
                        pending.extend(data)
                        while b'\n' in pending:
                            line,_,rest=pending.partition(b'\n');pending[:]=rest;cause_line(bytes(line))
                        # Diagnostic lines are bounded; don't retain huge partial lines.
                        if len(pending)>8192:pending[:]=pending[-8192:]
                    if row['observedBytes']>scan_limit:
                        row.update(truncated=True,reason='scan-byte-cap');break
                if row.get('reason')=='scan-byte-cap':break
            if pending:cause_line(bytes(pending))
        except Exception:
            row.update(error='capture-failed',truncated=True)
        finally:
            selector.close()
            if process:
                if row['streamComplete'] and process.poll() is None:
                    try:process.wait(timeout=.1)
                    except subprocess.TimeoutExpired:pass
                if process.poll() is None:
                    import signal
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                row['returncode']=process.wait(timeout=2);process.stdout.close()
            target=directory/(role+'.log');target.write_bytes(tail);target.chmod(0o600)
            if cause_budget:
                target=directory/(role+'.disconnects.log');target.write_bytes(causes);target.chmod(0o600)
            row.update(bytes=len(tail)+len(causes),tailBytes=len(tail),causeBytes=len(causes),
                       omittedBytes=max(0,row['observedBytes']-len(tail)),
                       sourceTimes=_log_times(tail),causeSourceTimes=_log_times(causes),
                       causeLinesObserved=cause_seen,causeLinesRetained=len(re.findall(rb'(?m)^(?:\d{4}-\d\d-\d\dT[^ ]+ )?realtime server disconnects in the last ',causes)),captureFinishedAtNs=time.time_ns())
            row['truncated']=row['truncated'] or row['omittedBytes']>0
            remaining-=row['bytes']
        rows.append(row)
    return {'version':1,'scope':'PRIVATE recent observed tails and bounded disconnect summaries; incomplete streams never prove absence',
            'secondsPerRole':seconds,'perRoleBytes':per_role,'globalBytes':total,'roles':rows}

def state_environment(state, config, chosen):
    for role in log_roles(config):
        file=Path(state)/role/'env.json'
        if role in config['services'] and file.exists():
            values=json.loads(file.read_text())
            require(all(k not in values or values[k]==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_STATE_OVERRIDE')
            require(not any(k.startswith('NS_M7_DIAGNOSTICS') and k not in FLAGS for k in values),'M7_DIAGNOSTICS_ENV_INVALID')

def runtime_environment(containers, chosen, config=None,pgstream=False):
    seen=set()
    for row in containers:
        role=row['Config']['Labels'].get('com.docker.compose.service')
        if (role in log_roles(config) if config is not None else role in LOG_ROLES) and role not in ('postgres','vault','nginx','pgstream') and row.get('State',{}).get('Running'):
            require(role not in seen,'M7_DIAGNOSTICS_RUNTIME_ROSTER_MISMATCH')
            seen.add(role)
            env=dict(value.split('=',1) for value in row['Config'].get('Env',[]) if '=' in value)
            require(all(env.get(k)==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_RUNTIME_MISMATCH')
    require(bool(seen),'M7_DIAGNOSTICS_RUNTIME_UNMEASURED')
    if config is not None:
        expected={role for role in config['services'] if role in log_roles(config) and role not in ('postgres','vault','nginx','pgstream') and not(pgstream and role=='feed-reader')}
        require(seen==expected,'M7_DIAGNOSTICS_RUNTIME_ROSTER_MISMATCH')

def identity(diagnostics, config):
    # Run identity is the image digest plus the run configuration; no source
    # settings projection is re-derived per run.
    import hashlib
    roles=config['services']
    # Agent overlay is not supported by this default-topology producer; refuse
    # it rather than report server samples as an Agent profile.
    require(not any('vault-agent' in name for name in roles),'M7_AGENT_OVERLAY_UNSUPPORTED')
    require(roles.get('vault',{}).get('command',[])[:2]==['vault','server'],'M7_VAULT_SERVER_TOPOLOGY_UNCONFIRMED')
    from evaluator_progress import POLICY
    value={'version':5,'evaluatorProgress':POLICY,
           'diagnostics':diagnostics,'topology':{'binding':'registry-default','secretsBackend':'vault-server','vaultAgentOverlay':False,
           'realtimeWorkers':sum(name=='realtime' or re.fullmatch(r'realtime-\d+',name) is not None for name in roles),
           'evaluatorWorkers':sum(name=='evaluator' or re.fullmatch(r'evaluator-\d+',name) is not None for name in roles)}}
    return {**value,'sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
