"""Fixed safe profile identity and bounded private evidence collection."""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
from contract import require, metric

FLAGS = ('NS_M7_DIAGNOSTICS', 'NS_M7_DIAGNOSTICS_INTERVAL_MS')
LOG_ROLES = ('api','api-2','api-3','api-4','realtime','realtime-2','evaluator','admin','feed-reader','tenant-admin','postgres','vault','nginx')

def selection(mode='off', interval=5000):
    require(mode in ('off','on') and type(interval) is int and 1000 <= interval <= 60000, 'M7_DIAGNOSTICS_SELECTION_INVALID')
    return {'mode':mode,'intervalMs':interval,'environment':{FLAGS[0]:'1' if mode=='on' else '0',FLAGS[1]:str(interval)}}

def select_environment(config, chosen):
    require(not any(re.fullmatch(r'(?:api|realtime|evaluator)-\d+', role) and role not in LOG_ROLES for role in config['services']),'M7_PROFILE_ROLE_UNSUPPORTED')
    for role, spec in config['services'].items():
        if role in LOG_ROLES and role not in ('postgres','vault','nginx'):
            environment = spec.setdefault('environment',{})
            require(isinstance(environment,dict),'M7_DIAGNOSTICS_ENV_INVALID')
            require(not any(k.startswith('NS_M7_DIAGNOSTICS') and k not in FLAGS for k in environment),'M7_DIAGNOSTICS_ENV_INVALID')
            environment.update(chosen['environment'])
    verify_environment(config,chosen)

def verify_environment(config, chosen):
    seen = 0
    for role,spec in config['services'].items():
        if role in LOG_ROLES and role not in ('postgres','vault','nginx'):
            seen += 1
            require(all(spec.get('environment',{}).get(k)==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_ENV_MISMATCH')
    require(seen > 0,'M7_DIAGNOSTICS_ENV_UNMEASURED')

def fingerprint_check(metrics):
    import math
    for name in ('observed','invalid','mismatch'):
        value=metric(metrics,'settings_fingerprint_'+name)
        require(type(value) in (int,float) and math.isfinite(value) and value==int(value),'M7_FINGERPRINT_COUNT_INVALID')
    observed=metric(metrics,'settings_fingerprint_observed')
    invalid=metric(metrics,'settings_fingerprint_invalid')
    mismatch=metric(metrics,'settings_fingerprint_mismatch')
    return {'observations':observed,'invalid':invalid,'mismatch':mismatch,
            'verdict':'FAIL' if invalid or mismatch else 'PASS' if observed > 0 else 'UNMEASURED'}

def capture_logs(directory, config, argv, *, seconds=5, per_role=65536, total=524288):
    """Kill bounded producers on timeout/limit; never buffer unbounded logs.

    argv(role) is the already-owned fixed Compose command. No user supplied
    service names, extra environment or public output. A failure is evidence
    incompleteness and must not prevent the existing teardown operation.
    """
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True);directory.chmod(0o700)
    rows=[];remaining=total
    for role in LOG_ROLES:
        if role not in config['services']:continue
        row={'role':role,'bytes':0,'truncated':False,'timeout':False,'returncode':None}
        budget=min(per_role,remaining)
        if not budget:
            row.update(truncated=True,reason='global-byte-cap');rows.append(row);continue
        process=None;selector=selectors.DefaultSelector()
        try:
            process=subprocess.Popen(argv(role),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            selector.register(process.stdout,selectors.EVENT_READ)
            deadline=time.monotonic()+seconds
            target=directory/(role+'.log')
            with target.open('wb') as output:
                target.chmod(0o600)
                while selector.get_map():
                    wait=deadline-time.monotonic()
                    if wait <= 0:row['timeout']=True;row['truncated']=True;break
                    for key,_ in selector.select(min(wait,.1)):
                        data=os.read(key.fileobj.fileno(),min(8192,budget-row['bytes']+1))
                        if not data:selector.unregister(key.fileobj);continue
                        kept=data[:budget-row['bytes']];output.write(kept);row['bytes']+=len(kept)
                        if len(data)>len(kept) or row['bytes']==budget:row['truncated']=True;break
                    if row['truncated']:break
            remaining-=row['bytes']
        except Exception:
            row['error']='capture-failed';row['truncated']=True
        finally:
            selector.close()
            if process:
                if process.poll() is None:
                    import signal
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                row['returncode']=process.wait(timeout=2)
                process.stdout.close()
        rows.append(row)
    return {'version':1,'scope':'PRIVATE fixed role tails; truncation/failure never proves absence','secondsPerRole':seconds,'perRoleBytes':per_role,'globalBytes':total,'roles':rows}

def state_environment(state, config, chosen):
    for role in LOG_ROLES:
        file=Path(state)/role/'env.json'
        if role in config['services'] and file.exists():
            values=json.loads(file.read_text())
            require(all(k not in values or values[k]==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_STATE_OVERRIDE')
            require(not any(k.startswith('NS_M7_DIAGNOSTICS') and k not in FLAGS for k in values),'M7_DIAGNOSTICS_ENV_INVALID')

def runtime_environment(containers, chosen, config=None):
    seen=set()
    for row in containers:
        role=row['Config']['Labels'].get('com.docker.compose.service')
        if role in LOG_ROLES and role not in ('postgres','vault','nginx') and row.get('State',{}).get('Running'):
            seen.add(role)
            env=dict(value.split('=',1) for value in row['Config'].get('Env',[]) if '=' in value)
            require(all(env.get(k)==v for k,v in chosen['environment'].items()),'M7_DIAGNOSTICS_RUNTIME_MISMATCH')
    require(bool(seen),'M7_DIAGNOSTICS_RUNTIME_UNMEASURED')
    if config is not None:
        expected={role for role in config['services'] if role in LOG_ROLES and role not in ('postgres','vault','nginx')}
        require(seen==expected,'M7_DIAGNOSTICS_RUNTIME_ROSTER_MISMATCH')

def identity(fingerprint, diagnostics, config):
    import hashlib
    roles=config['services']
    # Agent overlay is not supported by this default-topology producer; refuse
    # it rather than report server samples as an Agent profile.
    require(not any('vault-agent' in name for name in roles),'M7_AGENT_OVERLAY_UNSUPPORTED')
    require(roles.get('vault',{}).get('command',[])[:2]==['vault','server'],'M7_VAULT_SERVER_TOPOLOGY_UNCONFIRMED')
    from evaluator_progress import POLICY
    from evaluator_idle import POLICY as IDLE_POLICY
    value={'version':3,'evaluatorProgress':POLICY,'evaluatorIdleSafety':IDLE_POLICY,'settings':{k:fingerprint[k] for k in ('schema','sha256','sourceCommit','sourceBlobs')},
           'diagnostics':diagnostics,'topology':{'binding':'registry-default','secretsBackend':'vault-server','vaultAgentOverlay':False,
           'realtimeWorkers':sum(name=='realtime' or re.fullmatch(r'realtime-\d+',name) is not None for name in roles),
           'evaluatorWorkers':sum(name=='evaluator' or re.fullmatch(r'evaluator-\d+',name) is not None for name in roles)}}
    return {**value,'sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()}

def check_identity(value):
    import hashlib
    require(isinstance(value,dict) and value.get('version')==3,'M7_PROFILE_SELECTION_REQUIRED')
    expected=hashlib.sha256(json.dumps({k:v for k,v in value.items() if k!='sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(value.get('sha256')==expected,'M7_PROFILE_SELECTION_HASH_INVALID')
    from evaluator_progress import POLICY
    from evaluator_idle import POLICY as IDLE_POLICY
    require(value.get('evaluatorProgress')==POLICY and value.get('evaluatorIdleSafety')==IDLE_POLICY,'M7_PROFILE_EVALUATOR_PROGRESS_INVALID')
    chosen=value.get('diagnostics',{})
    require(chosen==selection(chosen.get('mode'),chosen.get('intervalMs')),'M7_PROFILE_DIAGNOSTICS_INVALID')
    require(re.fullmatch(r'[a-f0-9]{64}',value.get('settings',{}).get('sha256','')) is not None,'M7_PROFILE_SETTINGS_INVALID')
    require(value.get('topology',{}).get('secretsBackend')=='vault-server' and value['topology'].get('vaultAgentOverlay') is False,'M7_PROFILE_TOPOLOGY_INVALID')
    return value


def observation_check(value):
    require(isinstance(value,dict),'M7_FUNCTIONAL_SETTINGS_FINGERPRINT')
    result=fingerprint_check({'settings_fingerprint_'+name:{'count':value.get(field,0)} for name,field in [('observed','observations'),('invalid','invalid'),('mismatch','mismatch')]})
    require(result==value and result['verdict']=='PASS','M7_FUNCTIONAL_SETTINGS_FINGERPRINT')
    return value
