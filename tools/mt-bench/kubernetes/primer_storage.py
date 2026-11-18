"""Prepare the private primer Secret and validate its fresh state volume."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys


FIELD = 'primerStorage'
MIB = 1024 * 1024
SECRET_LIMIT = MIB
ROLES = ('api', 'realtime', 'evaluator', 'tenant-admin', 'ui', 'admin')


def volume_size(mib):
    for unit in ('Mi', 'Gi', 'Ti', 'Pi'):
        if mib % 1024:
            return str(mib) + unit
        mib //= 1024
    return str(mib) + 'Ei'


def require(ok, code):
    if not ok:
        raise ValueError('K8S_PRIMER_STORAGE_' + code)


def publish(contract, directory):
    selected = json.loads(contract.read_bytes())[FIELD]
    files = {p.name: p for p in directory.iterdir()}
    require({'config.json', 'expected-verification.json'} <= files.keys() and
            all(p.is_file() and not p.is_symlink() for p in files.values()), 'SOURCE_FILES')
    require(not {'config.json.gz', 'config.digest.json'} & files.keys(), 'SOURCE_FILES')
    raw_bytes = sum(p.stat().st_size for name,p in files.items() if name!='complete.json')
    require(raw_bytes < selected['stateMiB'] * MIB, 'INITIAL_FILES_EXCEED_VOLUME')
    config = files['config.json']
    raw = config.read_bytes()
    size = len(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if selected['secretCodec'] == 'gzip-v1':
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        metadata = json.dumps({'bytes': size, 'sha256': digest},
                              separators=(',', ':')).encode() + b'\n'
        secret_bytes = raw_bytes - size + len(packed) + len(metadata)
        require(secret_bytes <= SECRET_LIMIT, 'SECRET_TOO_LARGE')
        for name, value in (('config.json.gz', packed), ('config.digest.json', metadata)):
            with (directory/name).open('xb') as file:
                file.write(value)
        config.unlink()  # Owned temporary export. The original provision state is separate.
    else:
        secret_bytes = raw_bytes
        require(secret_bytes <= SECRET_LIMIT, 'SECRET_TOO_LARGE')
    return {'codec': selected['secretCodec'], 'stateMiB': selected['stateMiB'],
            'configBytes': size, 'configSha256': digest, 'initialRoleBytes': raw_bytes, 'secretBytes': secret_bytes}


def verify_receipt(selected, receipt):
    require(isinstance(receipt,dict) and receipt.get('codec')==selected['secretCodec'] and
            receipt.get('stateMiB')==selected['stateMiB'] and
            re.fullmatch('[0-9a-f]{64}',receipt.get('configSha256','')) is not None and
            all(type(receipt.get(key)) is int for key in ('configBytes','initialRoleBytes','secretBytes')) and
            0<receipt['configBytes']<=receipt['initialRoleBytes']<selected['stateMiB']*MIB and
            0<receipt['secretBytes']<=SECRET_LIMIT,'PUBLISH_PROOF_CHANGED')
    sizes = receipt.get('roleSecretBytes')
    require(isinstance(sizes,dict) and set(sizes)=={*ROLES,'primer','pgstream'} and
            all(type(size) is int and 0<size<=SECRET_LIMIT for size in sizes.values()) and
            sizes['primer']==receipt['secretBytes'], 'PUBLISH_PROOF_CHANGED')


def whole_bundle(root, primer_bytes):
    """Size the same data values as the bound publisher before creating Secrets."""
    sizes = {'primer': primer_bytes}
    for role in ROLES:
        directory = root/role
        sizes[role] = sum(p.stat().st_size for p in directory.iterdir() if p.is_file() and p.name!='complete.json')
    for role in ('api', 'evaluator', 'realtime'):
        for kind in ('config', 'env', 'operation'):
            sizes['admin']+=(root/'admin/verification'/f'{role}.{kind}.json').stat().st_size
    effective = root/'pgstream/pgstream.effective.yaml'
    sizes['pgstream']=(effective if effective.is_file() else root/'pgstream/pgstream.yaml').stat().st_size
    for role, value in sizes.items():
        require(0 < value <= SECRET_LIMIT, 'ROLE_SECRET_SIZE:'+role)
    return sizes


def check_render(selected, objects):
    if FIELD not in selected:
        return
    import resource_budget
    jobs = [row for row in objects if row['kind']=='Job' and row['metadata']['name']=='primer']
    require(len(jobs)==1, 'JOB_MISSING')
    pod = jobs[0]['spec']['template']['spec']
    mount = [volume for volume in pod['volumes'] if volume['name']=='config-primer']
    limit = selected[FIELD]['stateMiB'] * MIB
    require(len(mount)==1 and mount[0].get('emptyDir', {}).get('medium')=='Memory' and
            resource_budget.exact_quantity(mount[0]['emptyDir'].get('sizeLimit'),False,require)==limit,
            'RENDER_CHANGED')
    actors = [c for c in pod['initContainers']+pod['containers'] if c['name'] in ('primer','done')]
    require({c['name'] for c in actors}=={'primer','done'} and len(actors)==2, 'ACTORS_CHANGED')
    for actor in actors:
        require(sum(v['name']=='config-primer' and v.get('mountPath')=='/run/ns-primer' and v.get('subPath')=='d'
                    and not v.get('readOnly',False) for v in actor['volumeMounts'])==1, 'MOUNT_CHANGED')
        require(resource_budget.exact_quantity(actor['resources']['requests']['memory'],False,require)>=limit,
                'EXCEEDS_ACTOR_MEMORY_REQUEST')


if __name__=='__main__':
    import os
    os.umask(0o077)
    try:
        contract, directory = (Path(value) for value in sys.argv[1:])
        receipt = publish(contract, directory)
        receipt['roleSecretBytes'] = whole_bundle(directory.parent, receipt['secretBytes'])
        print(json.dumps(receipt))
    except (ValueError, OSError, TypeError, KeyError) as error:
        code = str(error)
        print(code if code.startswith('K8S_PRIMER_STORAGE_') else 'K8S_PRIMER_STORAGE_PUBLISH_FAILED', file=sys.stderr)
        sys.exit(1)
