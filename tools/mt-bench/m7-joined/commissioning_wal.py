"""Explicit finite WAL retention for a fresh local commissioning diagnostic."""
import copy
import hashlib
import json
import re
from pathlib import Path
from contract import require

FIELD = 'commissioningSlotWalMiB'
VALUES = (256, 1024)
SETTING = 'max_slot_wal_keep_size'


def value(selected):
    require(type(selected) is int and selected in VALUES, 'M7_COMMISSIONING_SLOT_WAL_INVALID')
    return selected


def scope(profile, purpose, attached=False):
    require(profile == 'pgstream-sample' and purpose == 'discovery' and not attached,
            'M7_COMMISSIONING_SLOT_WAL_LOCAL_DIAGNOSTIC_ONLY')


def option(args):
    selected = getattr(args, 'commissioning_slot_wal_mib', None)
    if selected is None:
        return {}
    selected = value(selected)
    scope(args.profile, getattr(args, 'run_purpose', 'acceptance'))
    return {FIELD: selected}


STARTUP_FIELDS = (FIELD, 'tenantReadiness', 'platformStartup')


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _runtime(manifest):
    record = manifest.get('startupRuntimeOwner')
    require(isinstance(record, dict) and set(record) == {'path', 'sha256', 'owner'},
            'M7_COMMISSIONING_SLOT_WAL_LOCAL_DIAGNOSTIC_ONLY')
    require(isinstance(record['path'], str) and isinstance(record['sha256'], str)
            and re.fullmatch('[a-f0-9]{64}', record['sha256']), 'M7_STARTUP_RUNTIME_OWNER_CHANGED')
    path = Path(record['path'])
    require(path.is_absolute() and str(path.resolve()) == str(path)
            and path.is_file() and _digest(path) == record['sha256'], 'M7_STARTUP_RUNTIME_OWNER_CHANGED')
    runtime = json.loads(path.read_text())
    root = Path(runtime.get('directory', '')).resolve()
    require(path == root / 'owner.json' and re.fullmatch('[a-f0-9]{32}', runtime.get('owner', ''))
            and runtime['owner'] == record['owner'] and runtime.get('prepared') is True
            and not runtime.get('attached') and all(runtime.get(k) == manifest.get(k)
                for k in ('project', 'pair', 'imageId', 'profile', 'runPurpose', 'tenants', 'replicas'))
            and runtime.get('instrument', {}).get('sha256') == manifest.get('instrument', {}).get('sha256'),
            'M7_STARTUP_RUNTIME_OWNER_MISMATCH')
    require(_digest(root / 'frozen.compose.json') == runtime.get('composeSha256')
            and _digest(root / 'env') == runtime.get('environmentSha256'), 'M7_STARTUP_RUNTIME_BINDING')
    require(all((k in runtime) == (k in manifest) and runtime.get(k) == manifest.get(k)
                for k in STARTUP_FIELDS), 'M7_STARTUP_RUNTIME_SELECTION_MISMATCH')
    return runtime


def inherit(args, manifest, runtime, root):
    """Copy immutable startup facts from the exact owner, never request changes."""
    require(getattr(args, 'commissioning_slot_wal_mib', None) is None
            and getattr(args, 'tenant_readiness', None) is None,
            'M7_DIAGNOSTIC_OPTIONS_FRESH_PREPARE_ONLY')
    if not any(k in runtime for k in STARTUP_FIELDS):
        return
    root = Path(root).resolve()
    owner = Path(args.runtime_owner).resolve()
    require(owner == root / 'owner.json' and Path(args.state).resolve() == root / 'state'
            and [Path(p).resolve() for p in args.compose] == [root / 'frozen.compose.json']
            and Path(args.env_file).resolve() == root / 'env'
            and _digest(root / 'frozen.compose.json') == runtime.get('composeSha256')
            and _digest(root / 'env') == runtime.get('environmentSha256'),
            'M7_STARTUP_RUNTIME_BINDING')
    for key in STARTUP_FIELDS:
        if key in runtime:
            manifest[key] = copy.deepcopy(runtime[key])
    manifest['startupRuntimeOwner'] = {'path': str(owner), 'sha256': _digest(owner), 'owner': runtime['owner']}
    _runtime(manifest)
    from_manifest(manifest)


def from_manifest(manifest):
    if manifest.get('attached') and (FIELD in manifest or 'tenantReadiness' in manifest
                                    or 'startupRuntimeOwner' in manifest):
        runtime = _runtime(manifest)
        return from_manifest(runtime)
    if FIELD not in manifest:
        return {}
    selected = value(manifest[FIELD])
    scope(manifest.get('profile'), manifest.get('runPurpose'), manifest.get('attached', False))
    return {FIELD: selected}


def command_setting(config):
    command = config.get('services', {}).get('postgres', {}).get('command')
    require(isinstance(command, list) and command and command[0] == 'postgres'
            and all(type(item) is str for item in command), 'M7_COMMISSIONING_SLOT_WAL_COMMAND_SHAPE')
    matches = [index for index, item in enumerate(command) if SETTING in item]
    require(len(matches) == 1 and matches[0] > 0 and command[matches[0]-1] == '-c',
            'M7_COMMISSIONING_SLOT_WAL_COMMAND_SHAPE')
    return command, matches[0]


def install(config, manifest):
    selected = from_manifest(manifest)
    if not selected:
        return
    require(not manifest.get('attached'), 'M7_COMMISSIONING_SLOT_WAL_LOCAL_DIAGNOSTIC_ONLY')
    command, index = command_setting(config)
    require(command[index] == SETTING + '=256MB', 'M7_COMMISSIONING_SLOT_WAL_BASELINE_CHANGED')
    command[index] = SETTING + '=' + str(selected[FIELD]) + 'MB'
    verify(config, manifest)


def verify(config, manifest):
    selected = from_manifest(manifest)
    if not selected:
        return
    command, index = command_setting(config)
    require(command[index] == SETTING + '=' + str(selected[FIELD]) + 'MB',
            'M7_COMMISSIONING_SLOT_WAL_CHANGED')


def remote_selection(value):
    selected=value.get(FIELD);readiness=value.get('tenantReadiness')
    if selected is None and readiness is None:return {}
    require(type(selected) is int and selected==1024 and readiness in ('serve','all'),
            'REMOTE_STARTUP_SELECTION')
    require(value.get('reportMode')=='discovery' and
            (value.get('helperDependencies')or{}).get('profile')=='external-service-native-v1' and
            value.get('pgstreamTopology')=='external-service-v1', 'REMOTE_STARTUP_NATIVE_DISCOVERY_ONLY')
    allocation=value.get('diagnosticResourceAllocation')
    require(isinstance(allocation,dict) and all(allocation.get('services',{}).get(role,{}).get('millicpus')==1000
            for role in ('admin','primer')), 'REMOTE_STARTUP_ADMIN_PRIMER_CPU')
    return {FIELD:selected,'tenantReadiness':readiness}


SOURCE_FILES=('bindings/compose/multitenant/platform-startup.js',
              'bindings/compose/multitenant/platform-verify.js',
              'bindings/compose/multitenant/compose.yaml')

def verify_source(a,manifest,core_repo,deploy_repo):
    selection=from_manifest(manifest)
    if not selection or manifest.get('tenantReadiness')is None:return None
    require(manifest.get('tenantReadiness') in ('serve','all'),'M7_PLATFORM_STARTUP_READINESS_REQUIRED')
    import hashlib
    files={name:a.command(['git','-C',deploy_repo,'show',manifest['pair']['deploy']+':'+name],binary=True)for name in SOURCE_FILES}
    require(b'max_slot_wal_keep_size=256MB' in files[SOURCE_FILES[-1]],'M7_COMMISSIONING_SLOT_WAL_BASELINE_CHANGED')
    return {'selection':{**selection,'tenantReadiness':manifest['tenantReadiness']},
            'files':{name:hashlib.sha256(text).hexdigest()for name,text in files.items()}}


def runtime(a,d,manifest,phase):
    selected=from_manifest(manifest)
    if not selected:return None
    raw=a.psql(d,"SELECT name,setting,unit,pending_restart FROM pg_settings WHERE name='max_slot_wal_keep_size'")
    if isinstance(raw,bytes):raw=raw.decode()
    require(raw.strip().splitlines()==[SETTING+'\t'+str(selected[FIELD])+'\tMB\tf'],
            'M7_COMMISSIONING_SLOT_WAL_RUNTIME')
    import time
    result={'version':1,'kind':'commissioning-slot-wal-readback-v1','status':'PASS','basis':'reproduced',
            'phase':phase,'at':time.time(),'pair':manifest['pair'],'imageId':manifest['imageId'],
            FIELD:selected[FIELD],'setting':SETTING,'unit':'MB','pendingRestart':False,
            'scope':'actual selected PostgreSQL setting only; finite slot allowance is not a total WAL/disk quota'}
    a.write(d/('commissioning-wal-'+phase+'.json'),result)
    return result
