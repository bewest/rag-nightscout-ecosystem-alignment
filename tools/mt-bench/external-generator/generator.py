"""Trusted phase supervisor; traffic children have neither sudo nor Docker access."""
import argparse
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

from protocol import Channel, binding, need, source_identity, TRAFFIC_FILES, write

UID = 1001
GID = 1001
HERE = Path(__file__).resolve().parent


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
    until = min(time.monotonic() + seconds, time.monotonic() + b['expiresAt'] - time.time() - 540)
    while not path.exists():
        need(process.poll() is None, 'EXTERNAL_TRAFFIC_CHILD_FAILED')
        need(time.monotonic() < until, 'EXTERNAL_TRAFFIC_PHASE_TIMEOUT')
        time.sleep(.1)
    need(path.is_file() and not path.is_symlink(), 'EXTERNAL_TRAFFIC_PHASE_FILE')


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
    with (d / 'npm.log').open('wb') as output:
        p = child(['/usr/local/bin/npm', 'ci', '--include=dev', '--omit=optional', '--ignore-scripts', '--force'], dependencies,
                  restricted({'NPM_CONFIG_USERCONFIG': '/dev/null', 'NPM_CONFIG_GLOBALCONFIG': '/dev/null', 'NPM_CONFIG_CACHE': str(dependencies / '.npm-cache')}), output)
        try:
            need(p.wait(timeout=min(1200, b['expiresAt'] - time.time() - 540)) == 0, 'EXTERNAL_CLIENT_INSTALL_FAILED')
        finally:
            stop(p)
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
          'trafficUid': UID, 'trafficGroups': ['nsload'], 'dockerAuthority': False,
          'k6Execution': 'fixed pinned container launched by trusted root supervisor; no Docker socket mount'})
    return descriptor


def sample(process, b, output, stop_event, k6_name):
    samples, complete, refusal = [], True, None
    interval = 2
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


def session(directory, spec):
    b = binding(spec)
    need(source_identity(HERE)['sha256'] == b['sourceSha256'], 'EXTERNAL_SOURCE_CHANGED')
    d = Path(directory)
    descriptor = prepare(d, b)
    channel = Channel(b, 'generator-0')
    out = d / 'load'
    control = d / 'control';control.mkdir(mode=0o700)
    probe = None
    metrics_stop = threading.Event()
    metrics_thread = None
    k6_name = 'nsexternal-' + b['nonce'][:12] + '-k6'
    need(not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + k6_name + '$'], text=True, timeout=10).strip(), 'EXTERNAL_K6_EXISTS')
    try:
        with (d / 'probe.log').open('wb') as log:
            probe = child(['/usr/local/bin/node', d / 'probe.js', '--base', 'http://' + b['appAddress'] + ':' + str(b['port']),
                '--tenants', d / 'tenants.private.json', '--runid', descriptor['trafficRunId'], '--per', '2', '--open', '5', '--window', '300',
                '--probeEvery', '3000', '--restart', '1', '--evalTimeout', '900', '--out', out / 'probe.json', '--signal', out / '.window'], d,
                restricted({'NODE_PATH': str(d / 'dependencies/node_modules'), 'STOCK_MS': '300000', 'RECOVERY_MS': '120000'}), log)
            metrics_thread = threading.Thread(target=sample, args=(probe, b, control / 'generator-metrics.json', metrics_stop, k6_name), daemon=True)
            metrics_thread.start()
            wait_file(out / '.window', probe, b)
            primed = json.loads((out / 'prime.json').read_text())
            need(primed['primed'] == 2 * b['tenants'], 'EXTERNAL_PRIME_FAILED')
            channel.send('client-primed', {'primed': primed['primed']})
            channel.receive('load-start', 120)
            k6 = ['docker', 'run', '--rm', '--name', k6_name, '--label', 'org.nightscout.external.owner=' + b['nonce'],
                '--network', 'host', '--user', str(UID) + ':' + str(GID), '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '-v', str(d / 'workload.js') + ':/scripts/workload.js:ro', '-v', str(d / 'tenants.private.json') + ':/tenants.private.json:ro', '-v', str(out) + ':/out',
                '-e', 'BASE_URL=http://' + b['appAddress'] + ':' + str(b['port']), '-e', 'TENANTS_FILE=/tenants.private.json',
                '-e', 'RUN_ID=' + descriptor['trafficRunId'], '-e', 'SETTINGS_FINGERPRINT=' + descriptor['settingsFingerprint'],
                '-e', 'RUN_START=' + str(int(time.time() * 1000)), '-e', 'DURATION=300', '-e', 'ACCEL=1', '-e', 'HOT_FACTOR=10',
                '-e', 'SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status',
                b['k6Image'], 'run', '--quiet', '--summary-export', '/out/k6-summary.json', '/scripts/workload.js']
            with (out / 'k6.log').open('wb') as output:
                subprocess.run(k6, stdout=output, stderr=subprocess.STDOUT, timeout=min(900, b['expiresAt'] - time.time() - 540), check=True)
            write(control / 'k6-launch.json', {'image': b['k6Image'], 'workloadSha256': descriptor['files']['workload.js'], 'trafficUid': UID, 'trustedLauncherUid': os.getuid(), 'returnCode': 0, 'fixedArguments': True})
            channel.send('load-complete')
            channel.receive('restart-prepare', 120)
            (out / '.restart').touch()
            wait_file(out / '.restart-ready', probe, b, 180)
            (out / '.restart-begin').touch()
            wait_file(out / '.restart-armed', probe, b, 30)
            channel.send('restart-armed')
            done = channel.receive('restart-done', 180)
            need(set(done) == {'status', 'commandMs'} and done['status'] == 'PASS' and type(done['commandMs']) in (int, float) and done['commandMs'] >= 0, 'EXTERNAL_RESTART_REFUSED')
            write(out / '.restart-command', done)
            os.chown(out / '.restart-command', 0, GID);(out / '.restart-command').chmod(0o440)
            need(probe.wait(timeout=min(1500, b['expiresAt'] - time.time() - 540)) == 0, 'EXTERNAL_PROBE_FAILED')
        metrics_stop.set()
        metrics_thread.join(timeout=15)
        need((out / 'event-loop.jsonl').is_file(), 'EXTERNAL_EVENT_LOOP_METRICS_MISSING')
        need(json.loads((control / 'generator-metrics.json').read_text()).get('complete') is True, 'EXTERNAL_GENERATOR_METRICS_MISSING')
        channel.send('client-complete')
        channel.receive('finish', 600)
    finally:
        stop(probe)
        metrics_stop.set()
        if metrics_thread:
            metrics_thread.join(timeout=15)
        # The only container this supervisor may remove is its exact owned name.
        existing = subprocess.check_output(['docker', 'inspect', '--format', '{{json .Config.Labels}}', k6_name], text=True, stderr=subprocess.DEVNULL, timeout=10) if subprocess.run(['docker', 'container', 'inspect', k6_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0 else None
        if existing is not None:
            need(json.loads(existing).get('org.nightscout.external.owner') == b['nonce'], 'EXTERNAL_FOREIGN_K6_REFUSED')
            subprocess.run(['docker', 'rm', '--force', k6_name], check=True, timeout=30, stdout=subprocess.DEVNULL)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--directory', required=True)
    p.add_argument('--binding', required=True)
    args = p.parse_args()
    session(args.directory, json.loads(Path(args.binding).read_text()))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if re.fullmatch('EXTERNAL_[A-Z_]+', str(error)) else 'EXTERNAL_GENERATOR_REFUSED', file=sys.stderr)
        sys.exit(1)
