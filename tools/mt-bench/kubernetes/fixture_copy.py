"""Kubernetes fixture reuse through CSI VolumeSnapshots, restored into fresh run namespaces.

Mirrors the Compose cold copy (`demo.sh snapshot` / `restore-fixture`). A seed run uses claims
instead of disposable storage, completes provisioning and the primer, stops every role including
PostgreSQL and Vault, and snapshots the four claims (PostgreSQL data, Vault storage, provision
state, primer results). The seed's VolumeSnapshotContents are set to Retain and labelled with the
fixture id so the seed namespace delete keeps the provider snapshots. The original Secrets, the
snapshot handles, the PostgreSQL image digest and the source commits go to a private directory.

A restore run creates those Secrets, binds the handles statically in its own namespace (one
Retain VolumeSnapshotContent and one VolumeSnapshot per part, labelled with the run id), clones
four claims from them, then runs the ordinary provision Job (unseal, migrate up, Vault auth
rebind), role startup and a primer that finds its roster complete. The run cleanup deletes the
namespace and the run's labelled contents; the fixture's provider snapshots remain.

`delete DIR CONTEXT` ends the fixture: it sets the seed contents to Delete and deletes them; the
CSI driver deletes the provider snapshots. Disposable storage is replaced only when reuse is selected.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

PARTS = ('postgres', 'vault', 'provisionState', 'primerResults')
CLAIMS = {'postgres': 'fixture-postgres', 'vault': 'fixture-vault',
          'provisionState': 'fixture-provision-state', 'primerResults': 'fixture-primer-results'}
SNAPSHOTS = {part: 'snap-' + name for part, name in CLAIMS.items()}
SEED_SIZES = dict.fromkeys(PARTS, '1Gi')
SECRET_PREFIXES = ('ns-config-', 'ns-credentials-')
SECRET_NAMES = ('ns-postgres-password', 'ns-ca', 'ns-vault-tls')
MANIFEST, SECRETS = 'fixture.json', 'secrets.private.json'
LABEL, FIXTURE_LABEL = 'nightscout.org/run-id', 'nightscout.org/fixture'
CONTENTS = 'volumesnapshotcontents.snapshot.storage.k8s.io'


class Refused(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Refused('K8S_FIXTURE_' + code)


def selection(mode, directory, storage_class=None, snapshot_class=None, postgres_size=None):
    """The run parameter recorded in the lifecycle input."""
    need(mode in ('seed', 'restore'), 'MODE')
    directory = Path(directory).resolve()
    if mode == 'seed':
        need(not directory.exists() and directory.parent.is_dir(), 'SEED_DIRECTORY')
        need(storage_class and snapshot_class, 'STORAGE_CLASSES')
        sizes = {**SEED_SIZES, **({'postgres': postgres_size} if postgres_size else {})}
        return {'mode': mode, 'directory': str(directory), 'storageClass': storage_class,
                'snapshotClass': snapshot_class, 'sizes': sizes}
    manifest = read_manifest(directory)
    return {'mode': mode, 'directory': str(directory), 'storageClass': manifest['storageClass'],
            'snapshotClass': manifest['snapshotClass']}


def read_manifest(directory):
    directory = Path(directory)
    need((directory/MANIFEST).is_file() and (directory/SECRETS).is_file(), 'RESTORE_DIRECTORY')
    need(not (directory.stat().st_mode & 0o077) and not ((directory/SECRETS).stat().st_mode & 0o077), 'PRIVATE')
    manifest = json.loads((directory/MANIFEST).read_bytes())
    need(manifest.get('version') == 1 and set(manifest.get('handles', {})) == set(PARTS) and
         set(manifest.get('sizes', {})) == set(PARTS) and manifest.get('driver'), 'MANIFEST')
    return manifest


def evaluator_slices(inventory):
    return inventory.get('slices', {}).get('evaluator', 1)


def seed_environment(inventory):
    """The seed environment the binding records (`NS_EVALUATOR_WORKERS` for evaluator K>1)."""
    value = dict(inventory.get('seed', {}).get('environment', {}))
    need(value.get('NS_EVALUATOR_WORKERS', '1') == str(evaluator_slices(inventory)), 'SEED_EVALUATOR_SLICES')
    need(value.get('NS_INPUT_TRANSPORT') == inventory.get('inputTransport') == 'writer-driven', 'SEED_INPUT_TRANSPORT')
    return value


def slices_record(inventory):
    """Recorded in the fixture manifest only for K>1, so K=1 manifests are unchanged."""
    count = evaluator_slices(inventory)
    record = {'evaluatorSlices': count} if count != 1 else {}
    record['inputTransport'] = inventory['inputTransport']
    return record


def check_restore(manifest, tenants, postgres_image, slices=1, input_transport='writer-driven'):
    """A restore never grows or shrinks the roster and keeps the PostgreSQL data format.
    Its Secrets carry the seed's evaluator K, so K must match too."""
    need(manifest.get('inputTransport') == input_transport, 'INPUT_TRANSPORT_CHANGED')
    need(manifest['tenants'] == tenants, 'TENANTS_CHANGED')
    need(manifest['postgresImage'] == postgres_image, 'POSTGRES_IMAGE_CHANGED')
    need(manifest.get('evaluatorSlices', 1) == slices, 'EVALUATOR_SLICES_CHANGED')


def storage(binding_storage):
    return {**binding_storage, 'mode': 'existing-claim', 'claims': dict(CLAIMS)}


def _jsonnet(jsonnet, library, code):
    return json.loads(subprocess.check_output([jsonnet, '-J', str(library), '-e',
                                               'local f=import "ns/fixture.libsonnet";' + code], timeout=30))


def render(jsonnet, library, namespace, run_id, chosen, tenants=None, postgres_image=None, slices=1, input_transport='writer-driven'):
    """Objects created before the stores, from the deploy binding's fixture.libsonnet: empty
    claims (seed) or Retain contents, VolumeSnapshots and clones (restore)."""
    a = json.dumps
    labels = {LABEL: run_id}
    if chosen['mode'] == 'seed':
        items = _jsonnet(jsonnet, library, 'std.objectValues(f.volumes(%s,%s,%s,%s,%s))' % (
            a(namespace), a(CLAIMS), a(chosen['sizes']), a(chosen['storageClass']), a(labels)))
    else:
        manifest = read_manifest(chosen['directory'])
        check_restore(manifest, tenants, postgres_image, slices, input_transport)
        items = _jsonnet(jsonnet, library,
            'std.flattenArrays(std.objectValues(f.imported(%s,%s,%s,%s,%s,%s))) + '
            'std.objectValues(f.claims(%s,"VolumeSnapshot",%s,%s,%s,%s,%s))' % (
            a(namespace), a(manifest['driver']), a(manifest['snapshotClass']), a(manifest['handles']), a(SNAPSHOTS),
            a(labels), a(namespace), a(SNAPSHOTS), a(CLAIMS), a(manifest['sizes']), a(manifest['storageClass']), a(labels)))
    return {'apiVersion': 'v1', 'kind': 'List', 'items': items}


def snapshot_objects(jsonnet, library, namespace, run_id, chosen):
    items = _jsonnet(jsonnet, library, 'std.objectValues(f.snapshots(%s,%s,%s,%s,%s))' % tuple(
        json.dumps(v) for v in (namespace, chosen['snapshotClass'], CLAIMS, SNAPSHOTS, {LABEL: run_id})))
    return {'apiVersion': 'v1', 'kind': 'List', 'items': items}


def fixture_secret(name):
    return name in SECRET_NAMES or name.startswith(SECRET_PREFIXES)


# Live steps. `k(args, body=None)` runs kubectl with the run's context and returns stdout bytes.

def import_secrets(k, namespace, run_id, directory):
    rows = json.loads((Path(directory)/SECRETS).read_bytes())
    need(rows and all(fixture_secret(row['name']) for row in rows), 'SECRETS')
    for row in rows:
        k(['create', '-f', '-', '-o', 'name'], {'apiVersion': 'v1', 'kind': 'Secret', 'type': row['type'],
          'metadata': {'name': row['name'], 'namespace': namespace, 'labels': {LABEL: run_id}}, 'data': row['data']})
    return [row['name'] for row in rows]


def create(k, namespace, items):
    made = []
    for obj in items:
        need(obj['kind'] == 'VolumeSnapshotContent' or obj['metadata'].get('namespace') == namespace, 'NAMESPACE')
        made.append(json.loads(k(['create', '-f', '-', '-o', 'json'], obj)))
    return [{'kind': m['kind'], 'name': m['metadata']['name'], 'uid': m['metadata']['uid']} for m in made]


def quiesce(k, namespace, run_id, until):
    """Stop every writer of the four claims, PostgreSQL and Vault included."""
    k(['scale', 'deployment,statefulset', '--all', '--replicas=0', '-n', namespace])
    k(['delete', 'job', '--all', '-n', namespace, '--wait=false'])
    while time.time() < until:
        if not k(['get', 'pods', '-n', namespace, '-l', LABEL + '=' + run_id, '-o', 'name']).strip():
            return
        time.sleep(2)
    raise Refused('K8S_FIXTURE_QUIESCE_DEADLINE')


def capture(k, namespace, run_id, chosen, snapshots, provenance, until):
    """After quiesce: snapshot the claims, keep the provider snapshots and the original Secrets."""
    create(k, namespace, snapshots['items'])
    ready = {}
    while time.time() < until and len(ready) < len(PARTS):
        for part, name in SNAPSHOTS.items():
            if part not in ready:
                status = json.loads(k(['get', 'volumesnapshot', name, '-n', namespace, '-o', 'json'])).get('status', {})
                need(not status.get('error'), 'SNAPSHOT_ERROR')
                if status.get('readyToUse') is True:
                    ready[part] = status
        if len(ready) < len(PARTS):
            time.sleep(2)
    need(len(ready) == len(PARTS), 'SNAPSHOT_DEADLINE')
    handles, contents, sizes, drivers = {}, {}, {}, set()
    for part, status in ready.items():
        name = status['boundVolumeSnapshotContentName']
        # Retain before the seed namespace is deleted; the fixture label lets `delete` find it.
        k(['patch', 'volumesnapshotcontent', name, '--type=merge', '-p',
           json.dumps({'spec': {'deletionPolicy': 'Retain'}, 'metadata': {'labels': {FIXTURE_LABEL: run_id}}})])
        content = json.loads(k(['get', 'volumesnapshotcontent', name, '-o', 'json']))
        need(content['spec']['deletionPolicy'] == 'Retain' and content.get('status', {}).get('snapshotHandle'), 'RETAIN')
        handles[part], contents[part] = content['status']['snapshotHandle'], name
        sizes[part] = status.get('restoreSize') or chosen['sizes'][part]
        drivers.add(content['spec']['driver'])
    need(len(drivers) == 1, 'DRIVER')
    rows = [{'name': s['metadata']['name'], 'type': s['type'], 'data': s['data']}
            for s in json.loads(k(['get', 'secrets', '-n', namespace, '-o', 'json']))['items']
            if fixture_secret(s['metadata']['name'])]
    directory = Path(chosen['directory'])
    directory.mkdir(mode=0o700)
    with (directory/SECRETS).open('x') as out:
        (directory/SECRETS).chmod(0o600)
        json.dump(rows, out)
    manifest = {'version': 1, 'fixtureId': run_id, 'driver': drivers.pop(), 'snapshotClass': chosen['snapshotClass'],
                'storageClass': chosen['storageClass'], 'handles': handles, 'seedContents': contents, 'sizes': sizes,
                'secrets': sorted(r['name'] for r in rows),
                'capturedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **provenance}
    with (directory/MANIFEST).open('x') as out:
        (directory/MANIFEST).chmod(0o600)
        json.dump(manifest, out, indent=2)
    return {key: manifest[key] for key in ('fixtureId', 'driver', 'sizes', 'secrets', 'tenants', 'postgresImage',
                                           'evaluatorSlices', 'inputTransport') if key in manifest}


def delete(k, directory, until):
    """End the fixture: Delete policy on the seed contents, delete them, confirm they are gone.
    The CSI driver then deletes the provider snapshots (confirm with the provider separately)."""
    manifest = read_manifest(directory)
    selector = FIXTURE_LABEL + '=' + manifest['fixtureId']
    for name in manifest['seedContents'].values():
        k(['patch', 'volumesnapshotcontent', name, '--type=merge', '-p', json.dumps({'spec': {'deletionPolicy': 'Delete'}})])
    k(['delete', CONTENTS, '-l', selector, '--wait=true', '--ignore-not-found=true'])
    while time.time() < until:
        if not k(['get', CONTENTS, '-l', selector, '-o', 'name']).strip():
            return {'fixtureId': manifest['fixtureId'], 'contentsAbsent': True,
                    'providerSnapshots': sorted(manifest['handles'].values())}
        time.sleep(2)
    raise Refused('K8S_FIXTURE_CONTENTS_REMAIN')


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != 'delete':
        raise SystemExit('delete FIXTURE_DIR KUBE_CONTEXT')
    run = lambda args, body=None: subprocess.run(['kubectl', '--context', sys.argv[3], *args], check=True,
                                                 capture_output=True, timeout=180).stdout
    print(json.dumps(delete(run, sys.argv[2], time.time() + 300), indent=2))
