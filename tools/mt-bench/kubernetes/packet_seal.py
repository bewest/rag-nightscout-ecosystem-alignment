"""One case packet in the evidence store: progressive upload, a sha256 seal, and local verification.

Layout under the store: `<campaign>/cases/<case>/attempt-<n>/files/<relative path>` for the packet, and
`<campaign>/cases/<case>/attempt-<n>/SEAL.json` written last. A seal lists every file with its sha256 and size; an
attempt without a seal is still being written (or its controller died before sealing it, see campaign.py resume).

`verify(directory, seal)` is the only judge of a fetched packet: a file missing, altered, or present but unlisted is a
failure. collect deletes nothing it has not verified this way.
"""
import hashlib
import json
from pathlib import Path
import time

SEAL = 'SEAL.json'
FILES = 'files/'
# Never uploaded: private material and live-process scratch. A packet holds evidence, not credentials.
EXCLUDE_SUFFIXES = ('.private.json', '.private.jsonl', '.lock')
EXCLUDE_NAMES = {'kubeconfig', '.window', '.restart'}


class SealError(ValueError):
    def __init__(self, code, files=()):
        super().__init__(code)
        self.code, self.files = code, sorted(files)


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def included(rel):
    name = rel.rsplit('/', 1)[-1]
    return name not in EXCLUDE_NAMES and not name.endswith(EXCLUDE_SUFFIXES)


def walk(directory):
    """{relative path: (sha256, bytes)} for every regular, non-excluded file; symlinks are not evidence."""
    directory = Path(directory)
    out = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(directory).as_posix()
        if included(rel):
            out[rel] = (digest(path), path.stat().st_size)
    return out


class Uploader:
    """Uploads new and changed files under `prefix` as they appear (call `sync` periodically), then `seal`."""

    def __init__(self, store, prefix):
        self.store, self.prefix = store, prefix.rstrip('/') + '/'
        self.sent = {}

    def sync(self, directory):
        sent = 0
        for rel, (sha, size) in walk(directory).items():
            if self.sent.get(rel) != sha:
                self.store.put(self.prefix + FILES + rel, (Path(directory) / rel).read_bytes())
                self.sent[rel] = sha
                sent += 1
        return sent

    def seal(self, directory, status):
        """Final sync, then the seal object. The seal lists what was hashed locally, so a later local edit
        (or an upload that silently lost a file) shows up at verification."""
        self.sync(directory)
        files = walk(directory)
        doc = {'version': 1, 'sealedAt': time.time(), 'status': status,
               'files': {rel: {'sha256': sha, 'bytes': size} for rel, (sha, size) in files.items()}}
        self.store.put(self.prefix + SEAL, json.dumps(doc, sort_keys=True, indent=1).encode(), 'application/json')
        return doc


def verify(directory, seal):
    """Raise SealError unless `directory` holds exactly the sealed files with their digests."""
    have = walk(directory)
    want = seal.get('files') or {}
    missing = [rel for rel in want if rel not in have]
    if missing:
        raise SealError('PACKET_FILE_MISSING', missing)
    altered = [rel for rel, row in want.items() if have[rel] != (row['sha256'], row['bytes'])]
    if altered:
        raise SealError('PACKET_FILE_ALTERED', altered)
    extra = [rel for rel in have if rel not in want]
    if extra:
        raise SealError('PACKET_FILE_UNSEALED', extra)
    return {'verified': True, 'files': len(want), 'bytes': sum(r['bytes'] for r in want.values())}
