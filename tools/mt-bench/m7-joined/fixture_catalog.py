"""Synthetic fixtures found by key (decision one-call-usable-provisioning).

A fixture is the cold copy of a seeded installation (PostgreSQL, Vault and primer state). Its key
is what decides whether a restore can stand in for a fresh seed:

    tenants          provisioned tenant count
    seed             fixture seed name (default "default"); a new name forces an independent copy
    schema           git tree id of the core `migrations/` directory at the image's core commit
    image            application image id (the config digest, the same on Compose and Kubernetes)
    postgresImage    PostgreSQL image id (the data directory format)
    transport        input transport, "pgstream" or "writer-driven" (legacy snapshots: pgstream)
    history          populated-history spec, or null for the ordinary seed
    evaluatorSlices  evaluator K, only for a transport whose restored state depends on K

One local catalog (JSON, outside Git) maps the key's digest to each platform's snapshot identity
(Compose: the copy directory; Kubernetes: the fixture directory with its retained
VolumeSnapshotContents and provider handles), the build time and a status. Harnesses look the key
up: a hit restores, a miss builds then registers. `python3 fixture_catalog.py list` shows it.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

DEFAULT = Path('/mnt/data/nightscout-workspace/artifacts/fixtures/catalog.json')
PLATFORMS = ('compose', 'kubernetes')
TRANSPORTS = ('pgstream', 'writer-driven')
# Transports whose restored state is independent of evaluator K. None yet: at deploy 086669a
# bootstrap still refuses a restore at another K for every transport (bootstrap.js
# BOOTSTRAP_EVALUATOR_ROSTER_CHANGED_RECREATE_DEMO, complete.json records the K) and Compose copies
# NS_EVALUATOR_WORKERS with the snapshot's settings. Add 'writer-driven' once that check is scoped to pgstream.
K_FREE_TRANSPORTS = frozenset()
IMAGE_ID = re.compile(r'sha256:[0-9a-f]{64}')
SEED = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')


class Refused(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Refused('FIXTURE_KEY_' + code)


def schema(core_repository, core_commit):
    """The migration catalogue identity: one git tree id covers every catalogue file and checksum."""
    return 'migrations-tree:' + subprocess.check_output(
        ['git', '-C', str(core_repository), 'rev-parse', '--verify', core_commit + '^{commit}:migrations'],
        text=True, timeout=15).strip()


def key(*, tenants, image, postgres_image, schema, transport='pgstream', seed='default', history=None,
        evaluator_slices=1):
    need(type(tenants) is int and tenants > 0, 'TENANTS')
    need(IMAGE_ID.fullmatch(image or '') and IMAGE_ID.fullmatch(postgres_image or ''), 'IMAGE_ID')
    need(isinstance(schema, str) and schema.startswith('migrations-tree:'), 'SCHEMA')
    need(transport in TRANSPORTS, 'TRANSPORT')
    need(isinstance(seed, str) and SEED.fullmatch(seed), 'SEED')
    need(type(evaluator_slices) is int and evaluator_slices >= 1, 'EVALUATOR_SLICES')
    # The ordinary seed writes no extra rows; only a populated history changes the stored data.
    if isinstance(history, dict) and history.get('mode') in (None, 'existing-provisioner-only') \
            and not history.get('additionalSeedRows'):
        history = None
    need(history is None or isinstance(history, dict), 'HISTORY')
    value = {'tenants': tenants, 'seed': seed, 'schema': schema, 'image': image, 'postgresImage': postgres_image,
             'transport': transport, 'history': history}
    if transport not in K_FREE_TRANSPORTS:
        value['evaluatorSlices'] = evaluator_slices
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Catalog:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('NS_FIXTURE_CATALOG') or DEFAULT).resolve()

    @contextlib.contextmanager
    def _locked(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(str(self.path) + '.lock', 'a', opener=lambda p, f: os.open(p, f, 0o600)) as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_bytes()) if self.path.exists() else {'version': 1, 'entries': {}}
            need(data.get('version') == 1, 'CATALOG_VERSION')
            before = json.dumps(data, sort_keys=True)
            yield data
            if json.dumps(data, sort_keys=True) != before:
                temporary = self.path.with_name(self.path.name + '.tmp')
                with open(temporary, 'w', opener=lambda p, f: os.open(p, f, 0o600)) as out:
                    json.dump(data, out, indent=2, sort_keys=True)
                os.replace(temporary, self.path)

    def entries(self):
        with self._locked() as data:
            return data['entries']

    def lookup(self, value, platform):
        """The ready record for this key on this platform, or None (a miss)."""
        need(platform in PLATFORMS, 'PLATFORM')
        with self._locked() as data:
            record = data['entries'].get(digest(value), {}).get('platforms', {}).get(platform)
        if record and record.get('status') == 'ready' and Path(record['directory']).is_dir():
            return {**record, 'digest': digest(value)}
        return None

    def reserve(self, value, platform):
        """Record a build in progress and return its new fixture directory (not yet created)."""
        need(platform in PLATFORMS, 'PLATFORM')
        name = digest(value)
        with self._locked() as data:
            entry = data['entries'].setdefault(name, {'key': value, 'platforms': {}})
            need(entry['key'] == value, 'DIGEST_COLLISION')
            current = entry['platforms'].get(platform, {})
            need(current.get('status') != 'ready' or not Path(current['directory']).is_dir(), 'ALREADY_BUILT')
            need(current.get('status') != 'building' or not _alive(current.get('pid', 0)), 'BUILD_IN_PROGRESS')
            parent = self.path.parent/platform
            parent.mkdir(mode=0o700, exist_ok=True)
            directory = parent/(name + '-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + os.urandom(3).hex())
            need(not directory.exists(), 'DIRECTORY_EXISTS')
            entry['platforms'][platform] = {'status': 'building', 'directory': str(directory), 'pid': os.getpid(),
                                            'startedAt': time.time()}
        return directory

    def _finish(self, value, platform, **fields):
        with self._locked() as data:
            record = data['entries'][digest(value)]['platforms'][platform]
            record.pop('pid', None)
            record.update(fields)
            return {**record, 'digest': digest(value)}

    def register(self, value, platform, identity):
        """The build finished: the fixture is ready for restores."""
        with self._locked() as data:
            record = data['entries'][digest(value)]['platforms'][platform]
            need(record['status'] == 'building' and Path(record['directory']).is_dir(), 'NOT_BUILDING')
        now = time.time()
        return self._finish(value, platform, status='ready', identity=identity,
                            builtAt=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
                            buildSeconds=round(now - record['startedAt'], 1))

    def failed(self, value, platform, code):
        return self._finish(value, platform, status='failed', failure=str(code)[:200], failedAt=time.time())

    def retire(self, directory):
        """The fixture's copies were deleted; later lookups miss and build again."""
        directory = str(Path(directory).resolve())
        with self._locked() as data:
            for entry in data['entries'].values():
                for record in entry['platforms'].values():
                    if record['directory'] == directory:
                        record.update(status='deleted', deletedAt=time.time())
                        return True
        return False


def main(argv):
    if argv[:1] != ['list'] or len(argv) > 2:
        raise SystemExit('list [CATALOG]  (default $NS_FIXTURE_CATALOG or ' + str(DEFAULT) + ')')
    catalog = Catalog(argv[1] if len(argv) == 2 else None)
    rows = [{'digest': name, 'platform': platform, 'status': record['status'], 'tenants': entry['key']['tenants'],
             'transport': entry['key']['transport'], 'seed': entry['key']['seed'], 'builtAt': record.get('builtAt'),
             'directory': record['directory']}
            for name, entry in sorted(catalog.entries().items()) for platform, record in sorted(entry['platforms'].items())]
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main(sys.argv[1:])
