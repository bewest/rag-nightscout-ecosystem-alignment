"""Immutable startup selections an attached session inherits from its exact runtime owner."""
import copy
import hashlib
import json
import re
from pathlib import Path
from contract import require

STARTUP_FIELDS = ('tenantReadiness', 'platformStartup')


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _runtime(manifest):
    record = manifest.get('startupRuntimeOwner')
    require(isinstance(record, dict) and set(record) == {'path', 'sha256', 'owner'},
            'M7_STARTUP_RUNTIME_OWNER_REQUIRED')
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
    require(getattr(args, 'tenant_readiness', None) is None,
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
    if manifest.get('attached') and ('tenantReadiness' in manifest or 'startupRuntimeOwner' in manifest):
        _runtime(manifest)
    return {}
