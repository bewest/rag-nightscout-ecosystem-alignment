"""Opt-in reuse of an installed generator dependency tree instead of `npm ci`.

The operator selects the source tree explicitly. Its package.json and
package-lock.json must be byte-identical to core's at the pinned commit; the
tree is copied, never linked. Nothing is hashed or re-proved: the run records
which tree it copied (decision four-product-failures: run identity is the
alignment commit, the image digest and the run configuration).
"""
import hashlib
import json
from pathlib import Path
import shutil


def need(ok, code):
    if not ok:
        raise RuntimeError('M7_DEPENDENCY_REUSE_' + code)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def file_sha(path):
    """Digest of one tool binary or lock file (recorded, not compared)."""
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def preflight(*, source, package_bytes, lock_bytes, **_legacy):
    """Read-only selection; errors occur before the caller creates a target."""
    source = Path(source)
    need(source.is_dir() and not source.is_symlink(), 'SOURCE_ROOT')
    source = source.resolve()
    for name, content in (('package.json', package_bytes), ('package-lock.json', lock_bytes)):
        need((source / name).is_file() and (source / name).read_bytes() == content, 'SOURCE_LOCK')
    need((source / 'node_modules').is_dir(), 'INCOMPLETE')
    return {'version': 2, 'source': str(source)}


def copy_owned(*, destination, qualification, package_bytes, lock_bytes, **_legacy):
    """Create a new owned copy; never link or overwrite a peer tree."""
    destination = Path(destination)
    source = Path(qualification['source'])
    need(not destination.exists() and not destination.is_symlink(), 'TARGET_EXISTS')
    need(not destination.resolve().is_relative_to(source), 'TARGET_WITHIN_SOURCE')
    preflight(source=source, package_bytes=package_bytes, lock_bytes=lock_bytes)
    destination.mkdir(mode=0o700)
    (destination / 'package.json').write_bytes(package_bytes)
    (destination / 'package-lock.json').write_bytes(lock_bytes)
    shutil.copytree(source / 'node_modules', destination / 'node_modules', symlinks=True)
    provenance = {'kind': 'owned-qualified-dependency-copy', 'qualification': qualification,
                  'packageSha256': sha(package_bytes), 'lockSha256': sha(lock_bytes),
                  'installFlags': [], 'network': 'NOT_USED'}
    (destination / 'dependency-reuse-ready.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return provenance
