"""Trusted phase supervisor; traffic children have neither sudo nor Docker access."""
import argparse
import datetime
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import threading
import time

from protocol import allocation_boundary, viewer_total, Channel, binding, need, source_identity, TRAFFIC_FILES, write, workload, discovery_mode, work_seconds

UID = 1001
GID = 1001
HERE = Path(__file__).resolve().parent


@contextmanager
def termination_guard():
    # SSH loss and controller abort must unwind the exact-owned cleanup. Ignore
    # later termination signals while it runs so cleanup cannot be reentered.
    watched = (signal.SIGHUP, signal.SIGTERM)
    previous = {kind: signal.getsignal(kind) for kind in watched}
    def interrupted(kind, frame):
        for watched_kind in watched:
            signal.signal(watched_kind, signal.SIG_IGN)
        raise RuntimeError('EXTERNAL_CONTROLLER_LOST')
    try:
        for kind in watched:
            signal.signal(kind, interrupted)
        yield
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)


def executable(path):
    return hashlib.sha256(Path(path).resolve().read_bytes()).hexdigest()


def restricted(extra=None):
    return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C.UTF-8', **(extra or {})}


def child(command, cwd, env, output):
    return subprocess.Popen(['setpriv', '--reuid', str(UID), '--regid', str(GID), '--clear-groups', '--no-new-privs', *map(str, command)],
                            cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def wait_file(path, process, b, seconds=600):
    until = time.monotonic()+work_seconds(b,seconds)
    while not path.exists():
        need(process.poll() is None, 'EXTERNAL_TRAFFIC_CHILD_FAILED')
        need(time.monotonic() < until, 'EXTERNAL_TRAFFIC_PHASE_TIMEOUT')
        time.sleep(.1)
    need(path.is_file() and not path.is_symlink(), 'EXTERNAL_TRAFFIC_PHASE_FILE')


def npm_configs(directory, create=False):
    """Two immutable empty files isolate npm's global and user config layers."""
    root = Path(directory) / 'npm-config'
    files = {'NPM_CONFIG_USERCONFIG': root / 'user.rc', 'NPM_CONFIG_GLOBALCONFIG': root / 'global.rc'}
    if create:
        root.mkdir(mode=0o750)
        os.chown(root, 0, GID)
        root.chmod(0o750)
        for path in files.values():
            with path.open('xb'):
                pass
            os.chown(path, 0, GID)
            path.chmod(0o440)
    need(not root.is_symlink() and root.is_dir() and root.stat().st_uid == 0
         and root.stat().st_gid == GID and root.stat().st_mode & 0o777 == 0o750, 'EXTERNAL_NPM_CONFIG_DIRECTORY')
    need(len({str(path.resolve()) for path in files.values()}) == 2, 'EXTERNAL_NPM_CONFIG_DISTINCT')
    for path in files.values():
        info = path.lstat()
        need(not path.is_symlink() and path.is_file() and info.st_uid == 0 and info.st_gid == GID
             and info.st_mode & 0o777 == 0o440 and path.read_bytes() == b'', 'EXTERNAL_NPM_CONFIG_CHANGED')
    return {key: str(path) for key, path in files.items()}


def prepare(directory, b):
    need(os.geteuid() == 0, 'EXTERNAL_TRUSTED_SUPERVISOR_REQUIRED')
    account = pwd.getpwuid(UID)
    need(account.pw_name == 'nsload' and account.pw_gid == GID, 'EXTERNAL_TRAFFIC_UID')
    groups = subprocess.check_output(['id', '-Gn', 'nsload'], text=True, timeout=10).split()
    need(groups == ['nsload'], 'EXTERNAL_TRAFFIC_PRIVILEGE')
    d = Path(directory)
    descriptor = json.loads((d / 'traffic.json').read_text())
    need(descriptor.get('binding') == b and descriptor.get('version') == 1, 'EXTERNAL_TRAFFIC_BINDING')
    required = set(TRAFFIC_FILES)
    need(set(descriptor.get('files', {})) == required, 'EXTERNAL_TRAFFIC_EXPORT_ALLOWLIST')
    need(all(not (d / name).is_symlink() and executable(d / name) == digest for name, digest in descriptor['files'].items()), 'EXTERNAL_TRAFFIC_EXPORT_CHANGED')
    need(len(json.loads((d / 'tenants.private.json').read_text())) == b['tenants'], 'EXTERNAL_TRAFFIC_COHORT')
    need(descriptor['generator']['pair'] == b['pair'] and descriptor['generator']['servingImageId'] == b['imageId'], 'EXTERNAL_CLIENT_SOURCE')
    # Scripts and input are root-owned after exact-lock installation. Only outputs
    # are writable to the traffic identity. No app state or shell arguments cross.
    d.chmod(0o750)
    os.chown(d, 0, GID)
    dependencies = d / 'dependencies'
    dependencies.mkdir(mode=0o700)
    for name in ('package.json', 'package-lock.json'):
        (dependencies / name).write_bytes((d / name).read_bytes())
    os.chown(dependencies, UID, GID)
    for p in dependencies.iterdir():
        os.chown(p, UID, GID)
    npm_config = npm_configs(d, create=True)
    with (d / 'npm.log').open('wb') as output:
        p = child(['/usr/local/bin/npm', 'ci', '--include=dev', '--omit=optional', '--ignore-scripts', '--force'], dependencies,
                  restricted({**npm_config, 'NPM_CONFIG_CACHE': str(dependencies / '.npm-cache')}), output)
        try:
            need(p.wait(timeout=min(1200, b['expiresAt'] - time.time() - 540)) == 0, 'EXTERNAL_CLIENT_INSTALL_FAILED')
        finally:
            stop(p)
    need(npm_configs(d) == npm_config, 'EXTERNAL_NPM_CONFIG_BINDING_CHANGED')
    expected = descriptor['generator']
    need(executable(dependencies / 'package-lock.json') == expected['lockSha256']
         and executable(dependencies / 'package.json') == expected['packageSha256'], 'EXTERNAL_CLIENT_LOCK_CHANGED')
    for name, tool in expected['tools'].items():
        need(executable(tool['path']) == tool['sha256'] and subprocess.check_output([tool['path'], '--version'], env=restricted(), text=True, timeout=10).strip() == tool['version'], 'EXTERNAL_CLIENT_TOOL_CHANGED')
    script = "const fs=require('fs'),p=require('path'),{createRequire}=require('module');const root=fs.realpathSync(process.argv[1]),r=createRequire(p.join(root,'package.json'));const entry=fs.realpathSync(r.resolve('socket.io-client'));if(!entry.startsWith(root+p.sep+'node_modules'+p.sep))throw Error('OUTSIDE');console.log(JSON.stringify({entry,version:r('socket.io-client/package.json').version}));"
    client = json.loads(subprocess.check_output(['/usr/local/bin/node', '-e', script, dependencies], env=restricted(), text=True, timeout=10))
    need(client['version'] == expected['client']['version'] and executable(client['entry']) == expected['client']['entrySha256'], 'EXTERNAL_STOCK_CLIENT_CHANGED')
    for root, dirs, files in os.walk(dependencies):
        for name in dirs + files:
            entry = Path(root) / name
            need(entry.resolve().is_relative_to(dependencies.resolve()), 'EXTERNAL_CLIENT_SYMLINK_ESCAPE')
            if not entry.is_symlink():
                os.chown(entry, 0, GID)
                entry.chmod(0o550 if entry.is_dir() else 0o440)
    os.chown(dependencies, 0, GID)
    dependencies.chmod(0o550)
    outputs = d / 'load'
    outputs.mkdir(mode=0o700)
    os.chown(outputs, UID, GID)
    for name in required:
        os.chown(d / name, 0, GID)
        (d / name).chmod(0o440)
    d.chmod(0o750)
    os.chown(d, 0, GID)
    dependencies.chmod(0o750)
    write(d / 'generator-provenance.json', {'kind': 'external-owned-lockfile-install', 'binding': b,
          'tools': expected['tools'], 'packageSha256': expected['packageSha256'], 'lockSha256': expected['lockSha256'],
          'client': {'version': client['version'], 'entrySha256': executable(client['entry'])},
          'npmConfig': {'user': npm_config['NPM_CONFIG_USERCONFIG'], 'global': npm_config['NPM_CONFIG_GLOBALCONFIG'], 'emptySha256': hashlib.sha256(b'').hexdigest()},
          'trafficUid': UID, 'trafficGroups': ['nsload'], 'dockerAuthority': False,
          'k6Execution': 'fixed pinned container launched by trusted root supervisor; no Docker socket mount'})
    return descriptor


def sample(process, b, output, stop_event, k6_name):
    samples, complete, refusal = [], True, None
    interval = workload(b)['cadence']['samplerIntervalSeconds']
    try:
        while not stop_event.is_set():
            if process.poll() is not None:
                break
            raw = Path('/proc/' + str(process.pid) + '/stat').read_text().split(')', 1)[1].split()
            status = Path('/proc/' + str(process.pid) + '/status').read_text()
            rss = re.search(r'^VmRSS:\s+(\d+)', status, re.M)
            network = sum(int(value.split()[0]) + int(value.split()[8]) for line in Path('/proc/net/dev').read_text().splitlines()[2:] for _, value in [line.split(':', 1)])
            # CPU belongs to the traffic child; host network includes explicitly
            # recorded controller transfer/SSH, never a per-tenant attribution.
            host_cpu = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
            k6 = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', k6_name], capture_output=True, text=True, timeout=10)
            k6_stats = json.loads(k6.stdout) if k6.returncode == 0 and k6.stdout.strip() else None
            samples.append({'hostCpuTicks': host_cpu, 'k6': k6_stats, 'at': time.time(), 'cpuUsec': int((int(raw[11]) + int(raw[12])) / os.sysconf('SC_CLK_TCK') * 1e6),
                            'rssBytes': int(rss[1]) * 1024 if rss else 0, 'networkBytes': network})
            if len(samples) > 5400:
                raise RuntimeError('EXTERNAL_METRICS_BOUND')
            stop_event.wait(interval)
    except BaseException as error:
        complete = False
        refusal = str(error) if re.fullmatch('EXTERNAL_[A-Z_]+', str(error)) else 'EXTERNAL_GENERATOR_METRICS_REFUSED'
    finally:
        write(output, {'version': 1, 'runId': b['runId'], 'nonce': b['nonce'], 'complete': complete and bool(samples) and any(row.get('k6') is not None for row in samples),
              'refusal': refusal, 'cadenceSeconds': interval, 'networkScope': 'generator-host cumulative receive+transmit, including SSH/control', 'samples': samples})


def driver_resources(b):
    value=b.get('diagnosticResourceAllocation')
    if value is None:return None
    need(b.get('diagnosticResourceProfile') is None,'EXTERNAL_K6_RESOURCE_SELECTION')
    allocation_boundary(value)
    return dict(value['driver'])


def driver_flags(limits):
    if limits is None:return []
    cpu=str(limits['millicpus']//1000) if limits['millicpus']%1000==0 else ('%.3f'%(limits['millicpus']/1000)).rstrip('0')
    return ['--cpus',cpu,'--memory',str(limits['memoryBytes']),'--memory-swap',str(limits['memoryBytes'])]


def verify_driver_flags(argv,b):
    limits=driver_resources(b)
    if limits is None:return None  # Historical launch/qualification remains unchanged.
    expected=driver_flags(limits)
    for flag,value in zip(expected[::2],expected[1::2]):
        need(argv.count(flag)==1 and argv.index(flag)+1<len(argv) and argv[argv.index(flag)+1]==value,'EXTERNAL_K6_RESOURCE_FLAGS')
    allowed=set(expected[::2])
    need(not any((v.startswith(('--cpu','--memory','--cpuset')) and v not in allowed) or v=='-m' for v in argv),'EXTERNAL_K6_RESOURCE_FLAGS')
    return limits


def traffic_commands(directory, b, descriptor, k6_name, run_start_ms):
    """The existing launch commands, bound to the validated workload."""
    selected = workload(b); cadence = selected['cadence']; d = Path(directory); out = d / 'load'
    probe = ['/usr/local/bin/node', d / 'probe.js', '--base', 'http://' + b['appAddress'] + ':' + str(b['port']),
             '--tenants', d / 'tenants.private.json', '--runid', descriptor['trafficRunId'], '--clients', str(viewer_total(b)), '--per', str(cadence['socketsPerTenant']),
             '--open', '5', '--window', str(cadence['loadSeconds']), '--probeEvery', str(cadence['probeEveryMs']),
             '--restart', '0', '--evalTimeout', '900', '--out', out / 'probe.json', '--signal', out / '.window']
    k6 = ['docker', 'run', '--rm', '--name', k6_name, '--label', 'org.nightscout.external.owner=' + b['nonce'],
          '--network', 'host', '--user', str(UID) + ':' + str(GID), '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
          '-v', str(d / 'workload.js') + ':/scripts/workload.js:ro', '-v', str(d / 'tenants.private.json') + ':/tenants.private.json:ro', '-v', str(out) + ':/out',
          '-e', 'BASE_URL=http://' + b['appAddress'] + ':' + str(b['port']), '-e', 'TENANTS_FILE=/tenants.private.json',
          '-e', 'RUN_ID=' + descriptor['trafficRunId'], '-e', 'SETTINGS_FINGERPRINT=' + descriptor['settingsFingerprint'],
          '-e', 'RUN_START=' + str(run_start_ms), '-e', 'DURATION=' + str(cadence['loadSeconds']), '-e', 'ACCEL=' + str(cadence['accel']), '-e', 'HOT_FACTOR=' + str(cadence['hotFactor']),
          '-e', 'SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status']
    k6 += ['-e', 'JWT_SETUP_CONCURRENCY=' + str(selected.get('jwtSetupConcurrency', 1))]
    if 'offeredRps' in cadence:k6 += ['-e', 'OFFERED_RPS=' + str(cadence['offeredRps'])]
    k6 += [b['k6Image'], 'run', '--quiet', '--summary-export', '/out/k6-summary.json', '/scripts/workload.js']
    limits=driver_resources(b)
    if limits is not None:k6=k6[:3]+driver_flags(limits)+k6[3:]
    return probe, k6

def actor_files(directory,name):
    need(re.fullmatch(r'nsexternal-[a-f0-9]{12}(?:-[a-z][a-z0-9-]{1,31})?-k6',name)is not None,'EXTERNAL_K6_NAME')
    root=Path(directory)/'control/actors';root.mkdir(mode=0o700,parents=True,exist_ok=True)
    need(not root.is_symlink()and root.resolve().is_relative_to(Path(directory).resolve()),'EXTERNAL_K6_INTENT_PATH')
    return root/(name+'.json'),root/(name+'.cid'),root/(name+'.captured.json')

def _inspect_actor(reference):
    by_id=re.fullmatch('[a-f0-9]{64}',reference)is not None
    selector='id='+reference if by_id else'name=^/'+reference+'$'
    ids=subprocess.check_output(['docker','ps','-aq','--no-trunc','--filter',selector],text=True,timeout=10).split()
    if not ids:return None
    need(len(ids)==1 and re.fullmatch('[a-f0-9]{64}',ids[0])is not None and(not by_id or ids[0]==reference),'EXTERNAL_K6_FULL_CID')
    rows=json.loads(subprocess.check_output(['docker','inspect',ids[0]],text=True,timeout=10));need(len(rows)==1 and rows[0].get('Id')==ids[0],'EXTERNAL_K6_INSPECT_COUNT');return rows[0]


def plan_k6(argv,d,b,name):
    intent,cid,captured=actor_files(d,name)
    need(not intent.exists()and not cid.exists()and not captured.exists(),'EXTERNAL_K6_ATTEMPT_EXISTS')
    need(_inspect_actor(name)is None,'EXTERNAL_K6_NAME_EXISTS')
    argv=list(map(str,argv));need(argv[:2]==['docker','run']and argv[argv.index('--name')+1]==name and argv.count(b['k6Image'])==1,'EXTERNAL_K6_FIXED_ARGV')
    i=argv.index(b['k6Image']);need(argv[i+1:i+3]==['run','--quiet']and'--rm'in argv and'--cidfile'not in argv,'EXTERNAL_K6_FIXED_ARGV')
    need(argv[argv.index('--label')+1]=='org.nightscout.external.owner='+b['nonce']and argv[argv.index('--user')+1]=='1001:1001'and argv[argv.index('--network')+1]=='host'and'--read-only'in argv and argv[argv.index('--cap-drop')+1]=='ALL'and argv[argv.index('--security-opt')+1]=='no-new-privileges','EXTERNAL_K6_FIXED_SECURITY')
    # The owned launcher emits only canonical -e and -v short options.
    # Reject attached/clustered short forms (including -e=KEY=VALUE) and all
    # long env forms before they can bypass the parsed environment intent.
    need(not any(v.startswith('--env') or (v.startswith('-') and not v.startswith('--') and v not in ('-e','-v')) for v in argv[:i]),'EXTERNAL_K6_JWT_SETUP_CHANGED')
    jwt_flags=[argv[n+1] for n,v in enumerate(argv[:-1]) if v=='-e' and argv[n+1].split('=',1)[0]=='JWT_SETUP_CONCURRENCY']
    need(jwt_flags==['JWT_SETUP_CONCURRENCY='+str(workload(b).get('jwtSetupConcurrency',1))],'EXTERNAL_K6_JWT_SETUP_CHANGED')
    limits=verify_driver_flags(argv[:i],b)
    metadata=json.loads(subprocess.check_output(['docker','image','inspect',b['k6Image']],text=True,timeout=10));need(len(metadata)==1 and re.fullmatch('sha256:[a-f0-9]{64}',metadata[0]['Id']),'EXTERNAL_K6_IMAGE_ID')
    mounts=[];env=dict(v.split('=',1)for v in metadata[0]['Config'].get('Env',[])if'='in v)
    for n,v in enumerate(argv):
        if v=='-v':
            source,target,*opts=argv[n+1].split(':');need(opts in([],['ro'])and Path(source).is_absolute(),'EXTERNAL_K6_MOUNT');mounts.append([str(Path(source).resolve()),target,not opts])
        if v=='-e':key,value=argv[n+1].split('=',1);env[key]=value
    need(len(mounts)==3 and{v[1]for v in mounts}=={'/scripts/workload.js','/tenants.private.json','/out'}and all(Path(v[0]).is_relative_to(Path(d).resolve())for v in mounts),'EXTERNAL_K6_MOUNT')
    value={'name':name,'nonce':b['nonce'],'sourceSha256':b['sourceSha256'],'image':b['k6Image'],'imageId':metadata[0]['Id'],'command':argv[i+1:],'entrypoint':metadata[0]['Config'].get('Entrypoint'),'mounts':sorted(mounts),'environment':env,'notBefore':time.time(),'argv':argv}
    if limits is not None:value['resourceLimits']=limits
    write(intent,value);return argv[:i]+['--cidfile',str(cid)]+argv[i:]

def qualify_k6(row,intent,*,check_resources=True):
    need(re.fullmatch('[a-f0-9]{64}',row.get('Id',''))is not None,'EXTERNAL_K6_FULL_CID');cfg=row['Config'];host=row['HostConfig']
    need(row.get('Name')=='/'+intent['name']and(cfg.get('Labels')or{}).get('org.nightscout.external.owner')==intent['nonce'],'EXTERNAL_K6_OWNER_NAME')
    need(row['Image']==intent['imageId']and cfg.get('Image')==intent['image']and cfg.get('Cmd')==intent['command']and cfg.get('Entrypoint')==intent['entrypoint'],'EXTERNAL_K6_IMAGE_COMMAND')
    need(datetime.datetime.fromisoformat(row['Created'].replace('Z','+00:00')).timestamp()>=intent['notBefore'],'EXTERNAL_K6_STALE_CREATED')
    actual=sorted([str(Path(v['Source']).resolve()),v['Destination'],v['RW']]for v in row.get('Mounts',[])if v['Type']=='bind')
    need(len(actual)==len(row.get('Mounts',[]))and actual==intent['mounts'],'EXTERNAL_K6_MOUNTS')
    need(cfg.get('User')=='1001:1001'and host.get('ReadonlyRootfs')is True and host.get('Privileged')is False and host.get('NetworkMode')=='host'and host.get('CapDrop')==['ALL']and host.get('CapAdd')in(None,[])and host.get('Devices')in(None,[])and host.get('PidMode')==''and host.get('IpcMode')=='private'and host.get('AutoRemove')is True and host.get('SecurityOpt')==['no-new-privileges'],'EXTERNAL_K6_SECURITY')
    environment=dict(v.split('=',1)for v in cfg.get('Env',[])if'='in v);need(environment==intent['environment']and len(environment)==len(cfg.get('Env',[])),'EXTERNAL_K6_ENVIRONMENT')
    if check_resources and intent.get('resourceLimits') is not None:
        limits=intent['resourceLimits']
        need(host.get('NanoCpus')==limits['millicpus']*1000000 and host.get('Memory')==limits['memoryBytes'] and host.get('MemorySwap')==limits['memoryBytes'],'EXTERNAL_K6_RESOURCE_LIMITS')
    return row['Id']

def cleanup_k6(directory,b,name):
    intent_file,cid_file,record=actor_files(directory,name)
    if not intent_file.exists():return{'status':'NO_CREATION_INTENT'}
    intent=json.loads(intent_file.read_text());need(intent['nonce']==b['nonce']and intent['sourceSha256']==b['sourceSha256']and intent['name']==name and intent['image']==b['k6Image'],'EXTERNAL_K6_INTENT_BINDING')
    capture_issue=None
    try:cid=cid_file.read_text().strip()if cid_file.exists()else None
    except OSError:cid=None;capture_issue='CIDFILE_UNAVAILABLE'
    if cid is not None and re.fullmatch('[a-f0-9]{64}',cid)is None:cid=None;capture_issue='CIDFILE_INVALID'
    previous=json.loads(record.read_text())if record.exists()else{}
    refusals=list(previous.get('refusals',[]));owned={};candidates={}
    if capture_issue:refusals.append(capture_issue)
    # The planned name is checked independently even if a valid captured CID is absent or foreign.
    for reference in list(dict.fromkeys([*([cid]if cid else[]),name])):
        try:candidates[reference]=_inspect_actor(reference)
        except Exception:refusals.append('INSPECT_UNAVAILABLE');continue
        row=candidates[reference]
        if row is None:continue
        try:actual=qualify_k6(row,intent);owned[actual]=row
        except (RuntimeError,KeyError,TypeError,ValueError)as error:
            if str(error)=='EXTERNAL_K6_RESOURCE_LIMITS':
                # Wrong native limits are still a failure. All original owner,
                # image, creation, mount and security checks must pass to clean.
                actual=qualify_k6(row,intent,check_resources=False);owned[actual]=row
            refusals.append(str(error)if str(error).startswith('EXTERNAL_K6_')else'LAYOUT_UNAVAILABLE')
    planned=candidates.get(name)
    if cid and planned is not None and planned.get('Id')!=cid:refusals.append('CAPTURED_CID_DIFFERS_FROM_PLANNED_NAME')
    # Never remove a foreign captured ID. Qualified owned rows are cleaned even when capture/reporting failed.
    if owned:
        report={'status':'FULL_INSPECTED_CID_QUALIFIED','ids':sorted(owned),'id':next(iter(owned)),'name':name,'capturedCid':cid,'refusals':sorted(set(refusals))}
        try:write(record,report)
        except OSError:refusals.append('RECORD_FAILED_AFTER_EXACT_CLEANUP')
        for actual in owned:subprocess.run(['docker','rm','--force',actual],check=True,timeout=30,stdout=subprocess.DEVNULL)
    elif not refusals and cid and not record.exists():
        write(record,{'status':'CAPTURED_CID_ALREADY_ABSENT','id':cid,'liveLayout':'UNMEASURED','name':name})
    need(not refusals,'EXTERNAL_K6_CUSTODY_REFUSED_AFTER_OWNED_CLEANUP')
    return{'status':'EXACT_K6_CID_REMOVED'if owned else'ALREADY_ABSENT','id':next(iter(owned))if owned else cid}


def run_k6(argv,d,b,name,output,timeout):
    command=plan_k6(argv,d,b,name);process=None;deadline=time.monotonic()+timeout
    try:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        if driver_resources(b) is not None:
            intent_file,_,captured=actor_files(d,name);intent=json.loads(intent_file.read_text())
            until=min(deadline,time.monotonic()+5)
            while True:
                row=_inspect_actor(name)
                if row is not None:
                    try:actual=qualify_k6(row,intent)
                    except RuntimeError as error:
                        native={key:row.get('HostConfig',{}).get(key) for key in ('NanoCpus','Memory','MemorySwap')}
                        try:write(captured.with_suffix('.native.json'),{'status':'FAIL','code':str(error) if str(error).startswith('EXTERNAL_K6_') else 'EXTERNAL_K6_QUALIFICATION_REFUSED','resourceLimits':intent['resourceLimits'],'native':native})
                        except OSError:error.publicationFailed=True
                        raise
                    native={key:row['HostConfig'][key] for key in ('NanoCpus','Memory','MemorySwap')}
                    write(captured.with_suffix('.native.json'),{'status':'PASS','id':actual,'resourceLimits':intent['resourceLimits'],'native':native,'qualifiedAt':time.time()})
                    break
                if process.poll() is not None or time.monotonic()>=until:
                    write(captured.with_suffix('.native.json'),{'status':'UNMEASURED','code':'EXTERNAL_K6_RESOURCE_READBACK_UNAVAILABLE','returncode':process.poll()})
                    raise RuntimeError('EXTERNAL_K6_RESOURCE_READBACK_UNAVAILABLE')
                time.sleep(.05)
        return subprocess.CompletedProcess(command,process.wait(timeout=max(.01,deadline-time.monotonic())))
    finally:
        primary=sys.exc_info()[1]
        try:stop(process) # CLI failure cannot skip exact owned cleanup.
        except BaseException as error:
            if primary is None:
                primary=error;raise
            primary.stopFailure='EXTERNAL_K6_CLI_STOP_REFUSED'
        finally:
            try:cleanup_k6(d,b,name)
            except BaseException as error:
                if primary is None:raise
                primary.cleanupFailure=str(error) if str(error).startswith('EXTERNAL_K6_') else 'EXTERNAL_K6_CLEANUP_REFUSED'

def cleanup_actors(directory,b):
    names=['nsexternal-'+b['nonce'][:12]+'-k6']
    if b.get('componentCases'):
        from component_cases import plan
        names+=['nsexternal-'+b['nonce'][:12]+'-'+c['id']+'-k6'for c in plan(b['componentCases'],b['tenants'])['cases']if c['kind']=='rest']
    results=[];errors=[]
    for name in names:
        try:results.append(cleanup_k6(directory,b,name))
        except Exception as error:errors.append(str(error))
    need(not errors,'EXTERNAL_K6_CLEANUP_REFUSED');return results


def session(directory, spec):
    b = binding(spec)
    if b.get('workload') is not None:
        need(time.time() + workload(b)['cadence']['loadSeconds'] + 540 < b['expiresAt'], 'REMOTE_DURATION_OUTSIDE_ENVELOPE')
    need(source_identity(HERE)['sha256'] == b['sourceSha256'], 'EXTERNAL_SOURCE_CHANGED')
    d = Path(directory)
    descriptor = prepare(d, b)
    if b.get('componentCases') is not None:
        from component_sessions import generator_session
        return generator_session(d,b,descriptor,sys.modules[__name__])
    channel = Channel(b, 'generator-0')
    out = d / 'load'
    control = d / 'control';control.mkdir(mode=0o700)
    probe = None
    result=None;probe_code=None;failure=None
    metrics_stop = threading.Event()
    metrics_thread = None
    k6_name = 'nsexternal-' + b['nonce'][:12] + '-k6'
    need(not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + k6_name + '$'], text=True, timeout=10).strip(), 'EXTERNAL_K6_EXISTS')
    def public_result():
        return write(control/'public-result.json',{'version':1,'runId':b['runId'],'nonce':b['nonce'],'sourceSha256':b['sourceSha256'],
             'reportMode':b.get('reportMode','strict'),'status':'PARTIAL' if discovery_mode(b) or failure else 'COMPLETED',
             'capacityAcceptance':'NOT_GRANTED','failure':failure,
             'processes':{'k6':None if result is None else result.returncode,'probe':probe_code},
             'artifacts':{p.name:executable(p) for p in out.iterdir() if p.is_file()}})
    try:
        with (d / 'probe.log').open('wb') as log:
            probe_args, _ = traffic_commands(d, b, descriptor, k6_name, 0)
            probe = child(probe_args, d,
                restricted({'NODE_PATH': str(d / 'dependencies/node_modules'), 'STOCK_MS': '300000', 'RECOVERY_MS': '120000', **({'M7_RUN_PURPOSE':'discovery'} if discovery_mode(b) else {})}), log)
            metrics_thread = threading.Thread(target=sample, args=(probe, b, control / 'generator-metrics.json', metrics_stop, k6_name), daemon=True)
            metrics_thread.start()
            wait_file(out / '.window', probe, b)
            primed = json.loads((out / 'prime.json').read_text())
            need(type(primed.get('primed')) is int and 0<=primed['primed']<=viewer_total(b),'EXTERNAL_PRIME_INVALID')
            need(discovery_mode(b) or primed['primed'] == 2 * b['tenants'], 'EXTERNAL_PRIME_FAILED')
            channel.send('client-primed', {'primed': primed['primed']})
            channel.receive('load-start', 120)
            (out / '.load-start').touch()
            _, k6 = traffic_commands(d, b, descriptor, k6_name, int(time.time() * 1000))
            with (out / 'k6.log').open('wb') as output:
                result=run_k6(k6,d,b,k6_name,output,work_seconds(b,workload(b)['cadence']['loadSeconds']+600))
                need(discovery_mode(b) or result.returncode==0,'EXTERNAL_K6_FAILED')
            write(control / 'k6-launch.json', {'image': b['k6Image'], 'workloadSha256': descriptor['files']['workload.js'], 'trafficUid': UID, 'trustedLauncherUid': os.getuid(), 'returnCode': result.returncode, 'fixedArguments': True, 'jwtSetupConcurrency':workload(b).get('jwtSetupConcurrency',1)})
            channel.send('load-complete')
            # End the write window; no service is restarted in calibration.
            (out / '.restart').touch()
            probe_code=probe.wait(timeout=work_seconds(b,1500))
            write(control/'processes.json',{'k6':result.returncode,'probe':probe_code})
            need(discovery_mode(b) or probe_code == 0, 'EXTERNAL_PROBE_FAILED')
        metrics_stop.set()
        metrics_thread.join(timeout=15)
        need(discovery_mode(b) or (out / 'event-loop.jsonl').is_file(), 'EXTERNAL_EVENT_LOOP_METRICS_MISSING')
        need(discovery_mode(b) or json.loads((control / 'generator-metrics.json').read_text()).get('complete') is True, 'EXTERNAL_GENERATOR_METRICS_MISSING')
        public_result()
        channel.send('client-complete')
        channel.receive('finish', work_seconds(b,600))
    except BaseException as error:
        failure=str(error) if re.fullmatch(r'(?:M7|REMOTE|EXTERNAL)_[A-Z_]+',str(error)) else 'EXTERNAL_GENERATOR_INCOMPLETE'
        raise
    finally:
        try:public_result()
        finally:
            try:
                stop(probe)
                metrics_stop.set()
                if metrics_thread:metrics_thread.join(timeout=15)
            finally:cleanup_k6(d,b,k6_name)



def main():
    p = argparse.ArgumentParser()
    p.add_argument('--directory', required=True)
    p.add_argument('--binding', required=True)
    args = p.parse_args()
    with termination_guard():
        session(args.directory, json.loads(Path(args.binding).read_text()))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if re.fullmatch('EXTERNAL_[A-Z_]+', str(error)) else 'EXTERNAL_GENERATOR_REFUSED', file=sys.stderr)
        sys.exit(1)
