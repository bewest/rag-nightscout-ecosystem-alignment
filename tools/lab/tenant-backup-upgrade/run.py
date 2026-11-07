#!/usr/bin/env python3
"""Focused native proof from immutable application archives; no broad acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import signal
from datetime import datetime, timezone

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worktree', required=True)
parser.add_argument('--deps', required=True, help='Private node_modules with matching .codex-source-package-lock.json')
parser.add_argument('--out', required=True, help='New immutable capture directory')
parser.add_argument('--grant', required=True, help='Coordinator grant reference; does not acquire a slot')
parser.add_argument('--stages', default='initial,controls,restored')
args = parser.parse_args()
worktree = Path(args.worktree).resolve()
deps = Path(args.deps).resolve()
out = Path(args.out).resolve()
out.mkdir(parents=True, exist_ok=False)

def run(command, cwd=None, env=None, check=True, timeout=30):
    child = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        start = Path(f'/proc/{child.pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]
    except FileNotFoundError:
        start = None
    try:
        stdout, stderr = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        stdout, stderr = child.communicate()
        raise subprocess.TimeoutExpired(command[0], timeout, stdout, stderr)
    with (out / 'children.jsonl').open('a') as stream:
        stream.write(json.dumps({'pid': child.pid, 'birth': start, 'exit': child.returncode, 'program': Path(command[0]).name}) + '\n')
    result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
    if check and result.returncode:
        # Commands can carry environment-only credentials in internal diagnostics.
        raise RuntimeError(f'{command[0]} {command[1]} exited {result.returncode}')
    return result

def git(*options):
    return run(['git', '-C', str(worktree), *options]).stdout.decode().strip()

def docker(*options):
    return run(['docker', *options]).stdout.decode().strip()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2) + '\n')

def inventory():
    return {'containers': sorted(docker('ps', '-aq', '--no-trunc').splitlines()),
            'volumes': sorted(docker('volume', 'ls', '-q').splitlines()),
            'networks': sorted(docker('network', 'ls', '-q', '--no-trunc').splitlines())}

stages = args.stages.split(',')
assert stages and all(stage in ['initial', 'controls', 'restored'] for stage in stages)
assert not git('status', '--porcelain', '--untracked-files=no'), 'Source must be committed and clean'
head = git('rev-parse', 'HEAD')
lock = (worktree / 'package-lock.json').read_bytes()
assert lock == (deps / '.codex-source-package-lock.json').read_bytes(), 'Dependency source lock mismatch'
assert deps.is_dir() and deps != (worktree / 'node_modules').resolve(), 'Use private dependencies'
node = run(['node', '-p', 'process.execPath']).stdout.decode().strip()
report = {'head': head, 'grant': args.grant, 'startedAt': datetime.now(timezone.utc).isoformat(),
          'worktree': str(worktree), 'dependencyLockSha256': digest(lock),
          'node': run([node, '--version']).stdout.decode().strip(), 'stages': []}
write('manifest.json', report)
# No mutation of existing databases, daemon configuration, images or volumes.
report['baseline'] = inventory()
report['image'] = json.loads(docker('image', 'inspect', 'postgres:16'))[0]
# Remove credential-bearing image metadata, retain only immutable identity.
report['image'] = {key: report['image'][key] for key in ['Id', 'RepoDigests']}
write('manifest.json', report)

controls = [
    ('digest', 'lib/tenant-operations/restore.js', 'if (common.sha256(text) !== entry.digest)', 'if (false)',
     'refuses damaged files', 'RESTORE_DIGEST_MISMATCH'),
    ('oracle', 'lib/tenant-operations/restore.js',
     "common.assertSameSummary(common.summaryOfManifest(artifact.manifest), oracle, 'RESTORE_ORACLE_MISMATCH');",
     '// deliberately removed restored-row oracle', 'rolls back lying successful', 'Missing expected rejection'),
    ('interruption', 'lib/tenant-operations/common.js', "await connection.query('ROLLBACK');", "await connection.query('COMMIT');",
     'rolls back lying successful', 'Expected values to be strictly deep-equal'),
    ('independent-oracle', 'lib/tenant-operations/common.js', 'return differences;', 'return [];',
     'distinguishes self-consistent row loss', 'differences.some')
]

def absent(kind, identifier):
    result = run(['docker', kind, 'inspect', identifier], check=False)
    return result.returncode != 0 and b'no such' in result.stderr.lower()

def capture(label, control=None, grep=None):
    entry = {'label': label, 'head': head, 'control': control[0] if control else None}
    # Preserve the exact archive and patch, not just a moving-worktree pointer.
    with tempfile.TemporaryDirectory(prefix='tenant-backup-native-') as scratch:
        archive = run(['git', '-C', str(worktree), 'archive', head]).stdout
        (out / (label + '.tar')).write_bytes(archive)
        subprocess.run(['tar', '-x', '-C', scratch], input=archive, check=True)
        root = Path(scratch)
        (root / 'node_modules').symlink_to(deps, target_is_directory=True)
        private_bin = root / '.native-proof-bin'
        private_bin.mkdir()
        wrapper = private_bin / 'docker'
        wrapper.write_bytes((Path(__file__).parent / 'docker-audit.py').read_bytes())
        wrapper.chmod(0o700)
        if control:
            name, file, before, after, pattern, marker = control
            path = root / file
            source = path.read_text()
            assert source.count(before) == 1, 'Mutation must match exact source once'
            path.write_text(source.replace(before, after))
            entry['mutation'] = {'file': file, 'before': before, 'after': after,
                                 'beforeSha256': digest(source.encode()), 'afterSha256': digest(path.read_bytes())}
        audit_path = out / (label + '.audit.jsonl')
        command = [node, str(deps / 'mocha/bin/mocha.js'), '--no-config', '--no-package', '--fail-zero',
                   '--reporter', 'json', 'tests/tenant-operations.integration.test.js']
        if control or grep:
            command.extend(['--grep', control[4] if control else grep])
        env = {**{key: os.environ[key] for key in ['PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'XDG_RUNTIME_DIR'] if key in os.environ},
               'NS_TENANT_OPERATIONS_PG_TEST': '1', 'NS_TENANT_OPERATIONS_AUDIT': str(audit_path),
               'TZ': 'UTC', 'NODE_ENV': 'test'}
        env['NS_BACKUP_DOCKER_REAL'] = shutil.which('docker')
        env['NS_BACKUP_DOCKER_AUDIT'] = str(out / (label + '.docker.jsonl'))
        env['PATH'] = str(private_bin) + os.pathsep + env['PATH']
        completed = None
        cleanup = []
        try:
            try:
                completed = run(command, cwd=root, env=env, check=False, timeout=180)
            except subprocess.TimeoutExpired as error:
                (out / (label + '.stdout.json')).write_bytes(error.stdout or b'')
                (out / (label + '.stderr.txt')).write_bytes(error.stderr or b'')
                raise
            (out / (label + '.stdout.json')).write_bytes(completed.stdout)
            (out / (label + '.stderr.txt')).write_bytes(completed.stderr)
        finally:
            audit = [json.loads(line) for line in audit_path.read_text().splitlines()] if audit_path.exists() else []
            # Independently inspect physical absence even if Mocha said cleanup passed.
            for created in [event for event in audit if event['phase'] == 'created']:
                container = created['container']
                if not absent('container', container):
                    # Remove only the exact created ID; never a container selected by prefix.
                    docker('rm', '-f', '-v', container)
                    cleanup.append({'emergencyRemoved': container})
                assert absent('container', container), 'Owned container remains'
                for volume in created['mounts']:
                    assert absent('volume', volume), 'Owned mounted volume remains'
                cleanup.append({'container': container, 'mounts': created['mounts'], 'absent': True})
            entry['cleanup'] = cleanup
            entry['afterInventory'] = inventory()
            report['stages'].append(entry)
            write('manifest.json', report)
        assert completed is not None
        entry['exit'] = completed.returncode
        result = json.loads(completed.stdout)
        entry['stats'] = result['stats']
        failures = result['failures']
        entry['failures'] = [{'title': failure.get('fullTitle'), 'code': failure['err'].get('code'),
                              'message': failure['err'].get('message')} for failure in failures]
        write('manifest.json', report)
        assert any(event['phase'] == 'created' for event in audit), 'No native fixture created'
        assert len(cleanup) == 1 and cleanup[0].get('absent'), 'Fixture cleanup failed or required emergency removal'
        assert entry['afterInventory'] == report['baseline'], 'Resource inventory changed outside owned fixture'
        if control:
            assert completed.returncode == 1 and result['stats']['failures'] == 1 and result['stats']['pending'] == 0, 'Invalid red control outcome'
            assert failures[0]['err'].get('code') == 'ERR_ASSERTION', 'Setup/SQL/type errors are not semantic red'
            assert control[5] in failures[0]['err'].get('message', ''), 'Expected semantic symptom missing'
            entry['classification'] = 'semantic-red'
        else:
            expected = 1 if label.endswith('-restored') else 5
            assert completed.returncode == 0 and result['stats']['passes'] == expected and result['stats']['pending'] == 0, 'Native positive failed'
            entry['classification'] = 'restored-green' if label.endswith('-restored') else 'positive-green'
        write('manifest.json', report)
        print(label, entry['classification'], flush=True)

try:
    if 'initial' in stages:
        capture('initial')
    if 'controls' in stages:
        for control in controls:
            capture(control[0] + '-red', control)
            capture(control[0] + '-restored', grep=control[4])
    if 'restored' in stages:
        capture('restored')
    assert git('rev-parse', 'HEAD') == head, 'Source head moved during capture'
    assert not git('status', '--porcelain', '--untracked-files=no'), 'Source changed during capture'
    report['result'] = 'passed'
except Exception as error:
    report['result'] = 'stopped'
    report['error'] = str(error)
    raise
finally:
    report['finishedAt'] = datetime.now(timezone.utc).isoformat()
    write('manifest.json', report)
    hashes = {str(path.relative_to(out)): digest(path.read_bytes()) for path in out.iterdir() if path.is_file()}
    write('sha256.json', hashes)
