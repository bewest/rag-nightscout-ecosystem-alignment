"""Portable fixture archive: move a cold fixture between Kubernetes, Compose and the workstation.

A fixture is four parts (fixture_copy.PARTS: PostgreSQL data, Vault storage, provision state, primer
results) plus Secrets. The archive is one private directory (mode 0700, files 0600):

    archive.json            parts, digests, provenance (no secret values)
    postgres.tar.zst        the cold PostgreSQL data directory (PGDATA contents, numeric owners)
    vault.tar.zst           Vault file storage (sealed; useless without the provision state)
    provisionState.tar.zst  bootstrap custody: Vault unseal key and root token        [credential]
    primerResults.tar.zst   the primer roster: tenant hosts, ids and access tokens    [credential]
    secrets.private.json    the Kubernetes Secret rows a restore re-creates            [credential]

PostgreSQL is archived as a cold data-directory copy, not pg_dump: the restore path is a physical
clone, so the copy is byte-for-byte what a CSI snapshot carries (roles and their password
verifiers, grants, row security, ownership, the database oid and system identifier) and needs no
index rebuild. It requires the same PostgreSQL image, which the fixture key already pins
(`postgresImage`); `inspect` opens it locally with that image.

    export-k8s   FIXTURE_DIR ARCHIVE --context C --namespace NS   clone the snapshots into NS, stream tars
    export-compose PROJECT STATE_DIR ARCHIVE --provenance FILE    stopped Compose project volumes
    import-k8s   ARCHIVE FIXTURE_DIR --context C --namespace NS   fill fresh claims, verify readback, snapshot
    inspect      ARCHIVE                                          verify digests, open PostgreSQL locally,
                                                                  run the fixture's readback query
    verify       ARCHIVE                                          digests only

Every command refuses (ARCHIVE_*) rather than continuing past a mismatch: a changed file digest, a
data directory that was not shut down cleanly, a readback whose logical hash differs from the one
recorded at seed time, or an archive directory that is not private.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent/'m7-joined'))
import fixture_copy as fc  # noqa: E402

VERSION = 1
ARCHIVE, SECRETS = 'archive.json', fc.SECRETS
PARTS = fc.PARTS
FILES = {part: part + '.tar.zst' for part in PARTS}
CREDENTIAL_PARTS = ('provisionState', 'primerResults')
PG_UID, APP_UID = 999, 1000          # postgres image user; nightscout.libsonnet uid and fsGroup
MOUNT = '/m'
VOLUME = {'postgres': 'postgres', 'vault': 'vault', 'provisionState': 'provision-state', 'primerResults': 'primer-results'}
PGDATA = {'kubernetes': 'pgdata', 'compose': ''}   # PGDATA below the claim / volume root
DATABASE = 'nightscout_compose_test'
CHUNK = 1 << 20
LABEL = fc.LABEL
TOOL = 'archive-tool'


class Refused(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Refused('ARCHIVE_' + code)


# ------------------------------------------------------------------ private files

def private_directory(path, create=False):
    """The archive directory: owned by this user, mode 0700, never a symlink."""
    path = Path(path)
    if create:
        need(not path.exists() and path.parent.is_dir(), 'DIRECTORY_EXISTS')
        path.mkdir(mode=0o700)
    need(path.is_dir() and not path.is_symlink(), 'DIRECTORY')
    st = path.stat()
    need(st.st_uid == os.getuid() and not st.st_mode & 0o077, 'NOT_PRIVATE')
    return path


def write_private(directory, name, data):
    """Write one new 0600 file inside a private directory (refuses to overwrite)."""
    directory = private_directory(directory)
    need('/' not in name and name not in ('', '.', '..'), 'NAME')
    fd = os.open(directory/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data if isinstance(data, bytes) else data.encode())
    return directory/name


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ streams

def capture_part(producer, directory, part, compressed=False):
    """Stream a tar from `producer` (argv) into DIRECTORY/<part>.tar.zst. A plain producer is
    compressed here; a `compressed` producer already emits zstd (compression in the pod, so the wire
    carries the small stream) and the raw digest is taken locally from the written file."""
    directory = private_directory(directory)
    target = directory/FILES[part]
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    raw, count, started = hashlib.sha256(), 0, time.time()
    with os.fdopen(fd, 'wb') as out:
        z = None if compressed else subprocess.Popen(['zstd', '-q', '-T0', '-3', '-c'], stdin=subprocess.PIPE, stdout=out)
        p = subprocess.Popen(producer, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for chunk in iter(lambda: p.stdout.read(CHUNK), b''):
            if compressed:
                out.write(chunk)
            else:
                raw.update(chunk)
                count += len(chunk)
                z.stdin.write(chunk)
        if z:
            z.stdin.close()
        err = p.stderr.read()
        produced, compressed_ok = p.wait(), (z.wait() if z else 0)
        p.stdout.close()
        p.stderr.close()
    if compressed and not produced:
        d = subprocess.Popen(['zstd', '-q', '-dc', str(target)], stdout=subprocess.PIPE)
        for chunk in iter(lambda: d.stdout.read(CHUNK), b''):
            raw.update(chunk)
            count += len(chunk)
        d.stdout.close()
        compressed_ok = d.wait()
    if produced or compressed_ok or not count:
        target.unlink()
        raise Refused('ARCHIVE_STREAM_' + part.upper() + ':' + err.decode(errors='replace')[-300:])
    return {'file': FILES[part], 'rawBytes': count, 'rawSha256': raw.hexdigest(), 'bytes': target.stat().st_size,
            'sha256': file_sha256(target), 'seconds': round(time.time() - started, 2),
            'credential': part in CREDENTIAL_PARTS}


def replay_part(directory, part, record, sink, compressed=False):
    """Send one verified part into `sink` (argv reading a tar on stdin) and check the raw digest.
    A `compressed` sink receives the .tar.zst bytes unchanged, decompresses them itself and prints
    the sha256 of the raw tar it extracted (pod_untar), so the wire carries the small stream."""
    raw, count, started = hashlib.sha256(), 0, time.time()
    path = str(Path(directory)/record['file'])
    z = subprocess.Popen(['cat', path] if compressed else ['zstd', '-q', '-dc', path], stdout=subprocess.PIPE)
    s = subprocess.Popen(sink, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for chunk in iter(lambda: z.stdout.read(CHUNK), b''):
        if not compressed:
            raw.update(chunk)
            count += len(chunk)
        s.stdin.write(chunk)
    s.stdin.close()
    reported, err = s.stdout.read().decode(), s.stderr.read()
    z.stdout.close()
    s.stdout.close()
    s.stderr.close()
    need(z.wait() == 0 and s.wait() == 0, 'REPLAY_' + part.upper() + ':' + err.decode(errors='replace')[-300:])
    if compressed:
        need(reported.split()[:1] == [record['rawSha256']], 'RAW_DIGEST_' + part.upper())
    else:
        need(count == record['rawBytes'] and raw.hexdigest() == record['rawSha256'], 'RAW_DIGEST_' + part.upper())
    return round(time.time() - started, 2)


def pod_untar(root):
    """Shell for the tool pod: decompress, extract, and report the raw tar's sha256 (POSIX sh)."""
    return ['sh', '-c', 'set -e; f=$(mktemp -u); mkfifo "$f"; sha256sum < "$f" > "$f.sum" & '
            'zstd -q -dc | tee "$f" | tar -C "$0" --numeric-owner -xpf -; wait; cat "$f.sum"; rm -f "$f" "$f.sum"', root]


def read_member(directory, record, name):
    """One small file from a part (the primer roster); read in memory, never written out."""
    data = subprocess.run(['zstd', '-q', '-dc', str(Path(directory)/record['file'])], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as t:
        for member in t.getmembers():
            if member.isfile() and member.name.lstrip('./') == name:
                return t.extractfile(member).read()
    raise Refused('ARCHIVE_MEMBER_MISSING:' + name)


# ------------------------------------------------------------------ manifest

def write_manifest(directory, parts, provenance, secrets_rows, source, postgres):
    """Write the secrets file and archive.json; the manifest carries digests, never secret values."""
    private_directory(directory)
    need(set(parts) == set(PARTS), 'PARTS')
    need(secrets_rows and all(fc.fixture_secret(row['name']) for row in secrets_rows), 'SECRETS')
    secrets = write_private(directory, SECRETS, json.dumps(secrets_rows))
    manifest = {'version': VERSION, 'kind': 'nightscout-fixture-archive', 'source': source, 'parts': parts,
                'postgres': postgres, 'secrets': {'file': SECRETS, 'sha256': file_sha256(secrets),
                                                   'names': sorted(row['name'] for row in secrets_rows)},
                'provenance': provenance, 'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write_private(directory, ARCHIVE, json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def verify(directory):
    """Every file present, private and equal to its recorded digest, before anything uses it."""
    directory = private_directory(directory)
    need((directory/ARCHIVE).is_file(), 'MANIFEST_MISSING')
    manifest = json.loads((directory/ARCHIVE).read_bytes())
    need(manifest.get('version') == VERSION and manifest.get('kind') == 'nightscout-fixture-archive', 'MANIFEST')
    need(set(manifest.get('parts', {})) == set(PARTS), 'PARTS')
    for part, record in [*manifest['parts'].items(), ('secrets', manifest['secrets'])]:
        path = directory/record['file']
        need(path.is_file() and not path.is_symlink() and not path.stat().st_mode & 0o077, 'FILE_' + part.upper())
        need(file_sha256(path) == record['sha256'], 'DIGEST_' + part.upper())
    for key in ('tenants', 'postgresImage', 'history', 'historyLogicalSha256', 'coreCommit', 'inputTransport'):
        need(key in manifest['provenance'], 'PROVENANCE_' + key)
    return manifest


# ------------------------------------------------------------------ readback

def roster(directory, manifest):
    """Tenant id and host only, from the primer roster (tokens are dropped in memory)."""
    data = json.loads(read_member(directory, manifest['parts']['primerResults'], 'tenants.json'))
    rows = [{'id': t['id'], 'host': t['host']} for t in data['tenants']]
    need(len(rows) == manifest['provenance']['tenants'], 'ROSTER_COUNT')
    return rows


def readback(manifest, tenants, sql, now=time.time):
    """The seed's own readback (populated_history.run, verify only) against an opened copy."""
    import populated_history
    spec = manifest['provenance']['history']
    receipt = populated_history.run(spec, tenants, 'http://127.0.0.1:9', sql, None, 0, verify_only=True, now=now)
    need(receipt['logicalSha256'] == manifest['provenance']['historyLogicalSha256'], 'READBACK_MISMATCH')
    return {k: receipt[k] for k in ('logicalSha256', 'rows', 'collections', 'observedUnixMs')}


def psql_command(prefix):
    return prefix + ['gosu', 'postgres', 'psql', '-X', '-q', '-At', '-F', '\t', '-h', '/tmp', '-d', DATABASE,
                     '-v', 'ON_ERROR_STOP=1']


def pg_start(prefix, pgdata):
    subprocess.run(prefix + ['gosu', 'postgres', 'pg_ctl', '-D', pgdata, '-w', '-t', '300', '-l', '/tmp/pg.log', '-o',
                             "-c listen_addresses='' -c unix_socket_directories=/tmp -c shared_preload_libraries=''",
                             'start'], check=True, capture_output=True, timeout=330)


def pg_stop(prefix, pgdata):
    subprocess.run(prefix + ['gosu', 'postgres', 'pg_ctl', '-D', pgdata, '-m', 'fast', '-w', '-t', '300', 'stop'],
                   check=True, capture_output=True, timeout=330)


def sql_through(prefix):
    command = psql_command(prefix)
    return lambda query: subprocess.run(command, input=query, capture_output=True, text=True, check=True,
                                        timeout=600).stdout


# ------------------------------------------------------------------ cold checks

COLD = ('[ ! -e "$D/postmaster.pid" ] || { echo NOT_COLD_PID >&2; exit 3; }; '
        'pg_controldata "$D" | grep -Eq "^Database cluster state: +shut down$" || { echo NOT_COLD_STATE >&2; exit 3; }; ')


def controldata(prefix, pgdata):
    out = subprocess.run(prefix + ['env', 'D=' + pgdata, 'sh', '-c', COLD + 'cat "$D/PG_VERSION"; pg_controldata "$D"'],
                         capture_output=True, text=True, timeout=120)
    need(out.returncode == 0, 'POSTGRES_NOT_COLD:' + out.stderr.strip()[-200:])
    lines = out.stdout.splitlines()
    fields = dict(line.split(':', 1) for line in lines[1:] if ':' in line)
    return {'format': 'cold-data-directory', 'pgMajor': lines[0].strip(),
            'systemIdentifier': fields.get('Database system identifier', '').strip(),
            'checkpointLocation': fields.get('Latest checkpoint location', '').strip()}


# ------------------------------------------------------------------ Kubernetes

def kubectl(context, namespace):
    base = ['kubectl', '--context', context]

    def k(args, body=None):
        return subprocess.run(base + args, input=json.dumps(body).encode() if body is not None else None,
                              capture_output=True, check=True, timeout=300).stdout
    k.base, k.namespace = base, namespace
    return k


def owned_namespace(k, run_id):
    ns = json.loads(k(['get', 'namespace', k.namespace, '-o', 'json']))
    need(ns['metadata'].get('labels', {}).get(LABEL) == run_id, 'NAMESPACE_NOT_OWNED')
    return ns['metadata']['uid']


def tool_pod(namespace, image, pull_secret, run_id, read_only):
    mounts = [{'name': VOLUME[p], 'mountPath': MOUNT + '/' + p, 'readOnly': read_only} for p in PARTS]
    volumes = [{'name': VOLUME[p], 'persistentVolumeClaim': {'claimName': fc.CLAIMS[p], 'readOnly': read_only}}
               for p in PARTS]
    return {'apiVersion': 'v1', 'kind': 'Pod',
            'metadata': {'name': TOOL, 'namespace': namespace, 'labels': {LABEL: run_id}},
            'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False, 'enableServiceLinks': False,
                     'terminationGracePeriodSeconds': 5,
                     **({'imagePullSecrets': [{'name': pull_secret}]} if pull_secret else {}),
                     'containers': [{'name': 'tool', 'image': image, 'command': ['sleep', '10800'],
                                     'securityContext': {'runAsUser': 0},
                                     'resources': {'requests': {'cpu': '500m', 'memory': '1Gi'},
                                                   'limits': {'cpu': '2', 'memory': '2Gi'}},
                                     'volumeMounts': mounts}],
                     'volumes': volumes}}


def wait_pod(k, until):
    while time.time() < until:
        pod = json.loads(k(['get', 'pod', TOOL, '-n', k.namespace, '-o', 'json']))
        if pod['status'].get('phase') == 'Running' and all(c.get('ready') for c in pod['status'].get('containerStatuses', [])):
            return pod['spec']['nodeName']
        need(pod['status'].get('phase') not in ('Failed', 'Succeeded'), 'TOOL_POD_ENDED')
        time.sleep(2)
    raise Refused('ARCHIVE_TOOL_POD_DEADLINE')


def delete_pod(k, until):
    k(['delete', 'pod', TOOL, '-n', k.namespace, '--ignore-not-found=true', '--wait=false'])
    while time.time() < until:
        if not k(['get', 'pods', '-n', k.namespace, '--field-selector', 'metadata.name=' + TOOL, '-o', 'name']).strip():
            return
        time.sleep(2)
    raise Refused('ARCHIVE_TOOL_POD_REMAINS')


def wait_claims(k, until):
    while time.time() < until:
        phases = {c['metadata']['name']: c['status'].get('phase') for c in
                  json.loads(k(['get', 'pvc', '-n', k.namespace, '-o', 'json']))['items']}
        if all(phases.get(name) == 'Bound' for name in fc.CLAIMS.values()):
            return
        time.sleep(2)
    raise Refused('ARCHIVE_CLAIMS_DEADLINE')


def export_k8s(fixture_dir, archive, context, namespace, run_id, jsonnet, library, pull_secret=None, deadline=1800):
    """Clone the fixture's four snapshots into NAMESPACE (the restore path's own render), mount the
    clones read-only in one tool pod and stream each part to the workstation."""
    until = time.time() + deadline
    k = kubectl(context, namespace)
    owned_namespace(k, run_id)
    manifest = fc.read_manifest(fixture_dir)
    need(manifest.get('historyLogicalSha256') and manifest.get('history'), 'FIXTURE_HAS_NO_READBACK')
    directory = private_directory(archive, create=True)
    started = time.time()
    chosen = {**fc.selection('restore', fixture_dir), 'key': manifest.get('key')}
    items = fc.render(jsonnet, library, namespace, run_id, chosen, manifest['tenants'], manifest['postgresImage'],
                      input_transport=manifest.get('inputTransport', 'writer-driven'))['items']
    fc.create(k, namespace, items)
    wait_claims(k, until)
    cloned = time.time()
    k(['create', '-f', '-'], tool_pod(namespace, manifest['postgresImage'], pull_secret, run_id, True))
    node = wait_pod(k, until)
    exec_ = k.base + ['exec', '-n', namespace, TOOL, '-c', 'tool', '--']
    pgdata = MOUNT + '/postgres/' + PGDATA['kubernetes']
    postgres = controldata(exec_, pgdata)
    parts = {}
    for part in PARTS:
        root = pgdata if part == 'postgres' else MOUNT + '/' + part
        parts[part] = capture_part(exec_ + ['sh', '-c', 'tar -C "$0" --numeric-owner --exclude=./lost+found -cf - . '
                                            '| zstd -q -T0 -3 -c', root], directory, part, compressed=True)
    rows = json.loads((Path(fixture_dir)/fc.SECRETS).read_bytes())
    provenance = {key: manifest[key] for key in ('tenants', 'appImage', 'postgresImage', 'coreCommit', 'deployCommit',
                                                 'alignmentCommit', 'history', 'historyLogicalSha256', 'key',
                                                 'inputTransport') if key in manifest}
    source = {'platform': 'kubernetes', 'fixtureId': manifest['fixtureId'], 'pgdata': PGDATA['kubernetes'],
              'node': node}
    result = write_manifest(directory, parts, provenance, rows, source, postgres)
    delete_pod(k, until)
    return {'archive': str(directory), 'cloneSeconds': round(cloned - started, 1),
            'exportSeconds': round(time.time() - started, 1),
            'parts': {p: {x: parts[p][x] for x in ('rawBytes', 'bytes', 'seconds')} for p in PARTS},
            'postgres': result['postgres']}


def import_k8s(archive, fixture_dir, context, namespace, run_id, jsonnet, library, storage_class, snapshot_class,
               postgres_image_ref, pull_secret=None, sizes=None, catalog=None, deadline=3600):
    """Fresh claims in NAMESPACE, filled from the archive through one tool pod, readback verified in
    place, then captured with fixture_copy.capture: the manifest, Secrets file and Retain contents
    the restore path reads. `postgres_image_ref` is the pullable reference of the archive's image."""
    until = time.time() + deadline
    manifest = verify(archive)
    prov = manifest['provenance']
    need(same_postgres_image(postgres_image_ref, prov['postgresImage']), 'POSTGRES_IMAGE_REFERENCE')
    tenants = roster(archive, manifest)
    k = kubectl(context, namespace)
    owned_namespace(k, run_id)
    started = time.time()
    sizes = sizes or claim_sizes(manifest)
    if catalog:
        import fixture_catalog
        need(fixture_dir is None, 'CATALOG_CHOOSES_DIRECTORY')
        fixture_dir = fixture_catalog.Catalog(catalog).reserve(prov['key'], 'kubernetes')
    try:
        return _import(archive, manifest, tenants, k, fixture_dir, namespace, run_id, jsonnet, library, storage_class,
                       snapshot_class, postgres_image_ref, pull_secret, sizes, catalog, started, until)
    except BaseException as error:
        if catalog:
            fixture_catalog.Catalog(catalog).failed(prov['key'], 'kubernetes', error)
        raise


def _import(archive, manifest, tenants, k, fixture_dir, namespace, run_id, jsonnet, library, storage_class,
            snapshot_class, postgres_image_ref, pull_secret, sizes, catalog, started, until):
    prov = manifest['provenance']
    chosen = {'mode': 'seed', 'directory': str(Path(fixture_dir).resolve()), 'storageClass': storage_class,
              'snapshotClass': snapshot_class, 'sizes': sizes}
    need(not Path(fixture_dir).exists() and Path(fixture_dir).parent.is_dir(), 'FIXTURE_DIRECTORY')
    fc.create(k, namespace, fc.render(jsonnet, library, namespace, run_id, chosen)['items'])
    wait_claims(k, until)
    k(['create', '-f', '-'], tool_pod(namespace, postgres_image_ref, pull_secret, run_id, False))
    node = wait_pod(k, until)
    exec_ = k.base + ['exec', '-n', namespace, TOOL, '-c', 'tool', '--']
    exec_in = k.base + ['exec', '-i', '-n', namespace, TOOL, '-c', 'tool', '--']
    pgdata = MOUNT + '/postgres/' + PGDATA['kubernetes']
    filled = {}
    for part in PARTS:
        root = pgdata if part == 'postgres' else MOUNT + '/' + part
        subprocess.run(exec_ + ['sh', '-c', 'mkdir -p "$0" && [ -z "$(ls -A "$0" | grep -v lost+found)" ]', root],
                       check=True, capture_output=True)
        filled[part] = replay_part(archive, part, manifest['parts'][part], exec_in + pod_untar(root), compressed=True)
    # Owners the Kubernetes roles expect: postgres (uid 999, PGDATA 0700); Vault (gid 1000 through
    # fsGroup); provision state and primer results (uid 1000). A claim root that already matches the
    # fsGroup (gid 1000, setgid, group rwx) is not re-chowned by the kubelet (OnRootMismatch), so the
    # 0600 custody files keep their modes.
    subprocess.run(exec_ + ['sh', '-c',
                            'chown -R 999:999 "$0" && chmod 700 "$0" && '
                            'chgrp -R 1000 /m/vault && chmod 2775 /m/vault && '
                            'for d in /m/provisionState /m/primerResults; do chown -R 1000:1000 "$d" && chmod 2770 "$d"; done',
                            pgdata], check=True, capture_output=True)
    pg_start(exec_, pgdata)
    try:
        receipt = readback(manifest, tenants, sql_through(exec_in))
    finally:
        pg_stop(exec_, pgdata)
    postgres = controldata(exec_, pgdata)
    verified = time.time()
    delete_pod(k, until)
    fc.import_secrets(k, namespace, run_id, write_secrets_dir(archive))
    snapshots = fc.snapshot_objects(jsonnet, library, namespace, run_id, chosen)
    provenance = {key: prov[key] for key in ('tenants', 'appImage', 'postgresImage', 'coreCommit', 'deployCommit',
                                             'alignmentCommit', 'history', 'historyLogicalSha256', 'key',
                                             'inputTransport') if key in prov}
    provenance['archive'] = {'sha256': file_sha256(Path(archive)/ARCHIVE), 'source': manifest['source']}
    if provenance.get('postgresImage') != postgres_image_ref:
        # The restore path compares the fixture's image with the pullable reference a case renders; keep
        # the archive's recorded identity (a local image id) beside it.
        provenance['postgresImageId'] = provenance['postgresImage']
        provenance['postgresImage'] = postgres_image_ref
    captured = fc.capture(k, namespace, run_id, chosen, snapshots, provenance, until)
    result = {'fixtureDirectory': chosen['directory'], 'node': node, 'sizes': sizes,
              'fillSeconds': {p: filled[p] for p in PARTS}, 'readback': receipt,
              'importSeconds': round(verified - started, 1), 'totalSeconds': round(time.time() - started, 1),
              'postgresAfterVerify': postgres, 'captured': captured}
    if catalog:
        result['catalog'] = register(catalog, prov['key'], chosen['directory'], run_id, result['totalSeconds'])
    return result


def same_postgres_image(ref, recorded):
    """The pullable reference names the archive's image: the same digest, or (for a provenance that
    records a local image id) a local image with that id whose repository digests include REF."""
    if ref == recorded or ref.endswith('@' + recorded.split('@')[-1]):
        return True
    if '@' in recorded or '@sha256:' not in ref:
        return False
    try:
        spec = json.loads(subprocess.run(['docker', 'image', 'inspect', recorded], check=True,
                                         capture_output=True, text=True).stdout)[0]
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, IndexError):
        return False
    return spec.get('Id') == recorded and ref in (spec.get('RepoDigests') or [])


def write_secrets_dir(archive):
    """fixture_copy.import_secrets reads <dir>/secrets.private.json from a private directory: the archive."""
    return str(private_directory(archive))


def claim_sizes(manifest, minimum=fc.SEED_SIZES):
    """Room for the data plus PostgreSQL's WAL between checkpoints (fixture_copy.SEED_SIZES)."""
    gib = 1 << 30
    sizes = {}
    for part in PARTS:
        floor = int(minimum[part].rstrip('Gi'))
        need_gib = -(-manifest['parts'][part]['rawBytes'] * 3 // 2 // gib) + (1 if part == 'postgres' else 0)
        sizes[part] = '%dGi' % max(floor, need_gib)
    return sizes


def register(catalog_path, key, directory, run_id, seconds):
    """Mark the reserved catalog entry ready, with the identity shape seeds record."""
    import fixture_catalog
    manifest = fc.read_manifest(directory)
    return fixture_catalog.Catalog(catalog_path).register(key, 'kubernetes', {
        'fixtureId': run_id, 'providerSnapshots': manifest['handles'], 'volumeSnapshotContents': manifest['seedContents'],
        'importedFromArchive': manifest['archive']['sha256']})


# ------------------------------------------------------------------ Compose

def docker_helper(image, mounts, command):
    return ['docker', 'run', '--rm', '-i', '--network', 'none', '--user', '0', '--entrypoint', 'sh',
            *[x for m in mounts for x in ('-v', m)], image, '-c', command]


def export_compose(project, state, archive, provenance_file, k8s_secret_rows, postgres_image):
    """A stopped Compose project: its two volumes and the parts of its private state directory that
    Kubernetes keeps on claims. `k8s_secret_rows` are the Secret rows for Kubernetes, prepared from the
    same state (compose_secrets); the Compose role documents themselves are not carried."""
    need(not subprocess.run(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + project,
                             '--filter', 'status=running'], capture_output=True, text=True, check=True).stdout.strip(),
         'COMPOSE_RUNNING')
    provenance = json.loads(Path(provenance_file).read_bytes())
    directory = private_directory(archive, create=True)
    volume = lambda name: project + '_' + name
    pg = [volume('postgres-data') + ':/v:ro']
    started = time.time()
    check = subprocess.run(docker_helper(postgres_image, pg, 'export D=/v; ' + COLD + 'cat /v/PG_VERSION; pg_controldata /v'),
                           capture_output=True, text=True)
    need(check.returncode == 0, 'POSTGRES_NOT_COLD:' + check.stderr.strip()[-200:])
    lines = check.stdout.splitlines()
    fields = dict(line.split(':', 1) for line in lines[1:] if ':' in line)
    postgres = {'format': 'cold-data-directory', 'pgMajor': lines[0].strip(),
                'systemIdentifier': fields.get('Database system identifier', '').strip(),
                'checkpointLocation': fields.get('Latest checkpoint location', '').strip()}
    tar = 'tar -C /v --numeric-owner --exclude=./lost+found -cf - '
    producers = {
        'postgres': docker_helper(postgres_image, pg, tar + '.'),
        'vault': docker_helper(postgres_image, [volume('vault-data') + ':/v:ro'], tar + '.'),
        # Kubernetes: the provision Job's /state holds bootstrap/ (NS_BOOTSTRAP_OUTPUT=/state).
        'provisionState': docker_helper(postgres_image, [state + ':/v:ro'], tar + './bootstrap'),
        # Kubernetes: the primer claim holds the roster only; Compose keeps its config beside it.
        'primerResults': docker_helper(postgres_image, [state + '/primer:/v:ro'], tar + './tenants.json'),
    }
    parts = {part: capture_part(argv, directory, part) for part, argv in producers.items()}
    source = {'platform': 'compose', 'project': project, 'pgdata': PGDATA['compose']}
    manifest = write_manifest(directory, parts, provenance, k8s_secret_rows, source, postgres)
    return {'archive': str(directory), 'exportSeconds': round(time.time() - started, 1),
            'parts': {p: {x: parts[p][x] for x in ('rawBytes', 'bytes', 'seconds')} for p in PARTS},
            'postgres': manifest['postgres']}


def compose_secrets(state, app_image, evaluator_workers=None):
    """Kubernetes Secret rows from a Compose state directory.

    Carried unchanged (they are bound into the stored data): the PostgreSQL superuser password
    (pg_authid), the per-role PostgreSQL passwords and Vault token ids (credentials/), and the
    deployment signing secret (public keys in PostgreSQL derive from it). Rendered for Kubernetes
    from those same credentials, as scripts/secrets.sh does: the role documents (the api reads its
    Vault token from the Agent sink, not a seeded file). Regenerated: the CA and Vault server
    certificate (Compose names only `vault`; the Kubernetes provision Job calls `vault-bootstrap`)."""
    state = Path(state)
    rows = []

    def secret(name, files):
        rows.append({'name': name, 'type': 'Opaque',
                     'data': {k: base64.b64encode(v).decode() for k, v in sorted(files.items())}})

    def folder(path):
        return {p.name: p.read_bytes() for p in sorted(Path(path).iterdir()) if p.is_file()}

    secret('ns-postgres-password', {'postgres-password': (state/'bootstrap/postgres-password').read_bytes()})
    secret('ns-credentials-postgres', folder(state/'credentials/postgres'))
    secret('ns-credentials-vault', folder(state/'credentials/vault'))
    secret('ns-signing-secret', {'signing-secret': (state/'credentials/signing-secret').read_bytes()})
    with tempfile.TemporaryDirectory(prefix='archive-secrets-') as work:
        work = Path(work)
        os.chmod(work, 0o700)
        subprocess.run(['sh', '-c', '''set -e; umask 077; cd "$0"
            openssl req -x509 -newkey rsa:3072 -nodes -keyout ca.key -out ca.crt -days 30 -subj '/CN=Nightscout synthetic Kubernetes CA' 2>/dev/null
            openssl req -newkey rsa:3072 -nodes -keyout server.key -out server.csr -subj '/CN=vault' 2>/dev/null
            printf 'subjectAltName=DNS:vault,DNS:vault-bootstrap\\nextendedKeyUsage=serverAuth\\n' > server.ext
            openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 30 -extfile server.ext 2>/dev/null
            rm -f ca.key ca.srl server.csr server.ext''', str(work)], check=True)
        secret('ns-vault-tls', {'server.crt': (work/'server.crt').read_bytes(), 'server.key': (work/'server.key').read_bytes()})
        secret('ns-ca', {'ca.crt': (work/'ca.crt').read_bytes()})
        (work/'seed').mkdir(mode=0o700)
        shutil.copytree(state/'credentials', work/'seed/credentials')
        env = ['-e', 'NS_EVALUATOR_WORKERS=' + str(evaluator_workers)] if evaluator_workers and evaluator_workers > 1 else []
        script = ("const path=require('node:path');process.umask(0o077);"
                  "const render=require(path.join(process.cwd(),'deploy/multitenant/render'));"
                  "console.log(JSON.stringify(render.render(render.input({...process.env,NS_CREDENTIALS_DIR:'/seed/credentials',"
                  "NS_RENDER_OUTPUT:'/seed/roles',NS_API_VAULT_TOKEN_FILE:'/run/ns-vault/token'}))));")
        subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp',
                        '--user', '%d:%d' % (os.getuid(), os.getgid()), '-w', '/opt/app', '-v', str(work/'seed') + ':/seed',
                        *env, '--entrypoint', 'node', app_image, '-e', script], check=True, capture_output=True)
        for role in ('api', 'realtime', 'evaluator', 'tenant-admin', 'ui', 'admin', 'primer'):
            secret('ns-config-' + role, folder(work/'seed/roles'/role))
    return rows


# ------------------------------------------------------------------ local inspection

def inspect(archive, keep=False, image_ref=None):
    """Open the PostgreSQL part with the archive's own PostgreSQL image and run the fixture's readback."""
    manifest = verify(archive)
    tenants = roster(archive, manifest)
    image = image_ref or manifest['provenance']['postgresImage']
    name = 'archive-inspect-' + os.urandom(4).hex()
    volume = name + '-pgdata'
    started = time.time()
    subprocess.run(['docker', 'volume', 'create', '--label', 'org.nightscout.archive-inspect=1', volume],
                   check=True, capture_output=True)
    try:
        replay_part(archive, 'postgres', manifest['parts']['postgres'],
                    docker_helper(image, [volume + ':/v'], 'tar -C /v --numeric-owner -xpf - && chown 999:999 /v && chmod 700 /v'))
        extracted = time.time()
        subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none', '--entrypoint', 'sleep',
                        '-v', volume + ':/var/lib/postgresql/data', image, '7200'], check=True, capture_output=True)
        prefix = ['docker', 'exec', '-i', name]
        pgdata = '/var/lib/postgresql/data'
        identity = controldata(prefix, pgdata)
        need(identity['systemIdentifier'] == manifest['postgres']['systemIdentifier'], 'SYSTEM_IDENTIFIER')
        pg_start(prefix, pgdata)
        receipt = readback(manifest, tenants, sql_through(prefix))
        result = {'archive': str(archive), 'image': image, 'extractSeconds': round(extracted - started, 1),
                  'totalSeconds': round(time.time() - started, 1), 'postgres': identity, 'readback': receipt,
                  'container': name if keep else None}
        if keep:
            result['psql'] = 'docker exec -it %s gosu postgres psql -h /tmp -d %s' % (name, DATABASE)
        return result
    finally:
        if not keep:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


# ------------------------------------------------------------------ command line

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='action', required=True)
    for name in ('export-k8s', 'import-k8s'):
        s = sub.add_parser(name)
        s.add_argument('source')
        s.add_argument('target')
        s.add_argument('--context', required=True)
        s.add_argument('--namespace', required=True)
        s.add_argument('--run-id', required=True)
        s.add_argument('--jsonnet', default='jsonnet')
        s.add_argument('--library', required=True, help='bindings/kubernetes/lib of the deploy checkout')
        s.add_argument('--pull-secret')
        if name == 'import-k8s':
            s.add_argument('--storage-class', default='do-block-storage')
            s.add_argument('--snapshot-class', default='do-block-storage')
            s.add_argument('--postgres-image-ref', required=True)
            s.add_argument('--catalog', help='own catalog file; it then chooses the fixture directory (pass - as target)')
            s.add_argument('--postgres-size', help='PostgreSQL claim (e.g. 100Gi); never below the size the archive needs')
    s = sub.add_parser('export-compose')
    s.add_argument('project')
    s.add_argument('state')
    s.add_argument('target')
    s.add_argument('--provenance', required=True)
    s.add_argument('--app-image', required=True)
    s.add_argument('--postgres-image', required=True)
    s.add_argument('--evaluator-workers', type=int)
    s = sub.add_parser('inspect')
    s.add_argument('archive')
    s.add_argument('--keep', action='store_true')
    s.add_argument('--image')
    s = sub.add_parser('verify')
    s.add_argument('archive')
    a = p.parse_args(argv)
    if a.action == 'export-k8s':
        out = export_k8s(a.source, a.target, a.context, a.namespace, a.run_id, a.jsonnet, a.library, a.pull_secret)
    elif a.action == 'import-k8s':
        sizes = None
        if a.postgres_size:
            need(re.fullmatch(r'[1-9][0-9]*Gi', a.postgres_size), 'POSTGRES_SIZE')
            sizes = claim_sizes(verify(a.source))
            need(int(a.postgres_size[:-2]) >= int(sizes['postgres'][:-2]), 'POSTGRES_SIZE_BELOW_ARCHIVE')
            sizes['postgres'] = a.postgres_size
        out = import_k8s(a.source, None if a.target == '-' else a.target, a.context, a.namespace, a.run_id, a.jsonnet, a.library, a.storage_class,
                         a.snapshot_class, a.postgres_image_ref, a.pull_secret, sizes=sizes, catalog=a.catalog)
    elif a.action == 'export-compose':
        rows = compose_secrets(a.state, a.app_image, a.evaluator_workers)
        out = export_compose(a.project, a.state, a.target, a.provenance, rows, a.postgres_image)
    elif a.action == 'inspect':
        out = inspect(a.archive, a.keep, a.image)
    else:
        m = verify(a.archive)
        out = {'verified': True, 'parts': {k: v['bytes'] for k, v in m['parts'].items()}}
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Refused as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        sys.exit(2)
