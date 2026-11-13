"""App-local SQL, sampling, restart and evaluator proof; no private RPC to traffic."""
import argparse
import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from protocol import Channel, binding, need, source_identity, traffic_verdict, server_verdict, TRAFFIC_FILES, write
import traffic_probe
sys.path.insert(0, str(HERE.parent / 'm7-joined'))
import adapter as a
import evaluator_recovery
from reduce import measurements


def load(cell, spec):
    b = binding(spec)
    d, m = a.load(cell)
    need(b['pair'] == m['pair'] and b['tenants'] == m['tenants'] and m['replicas'] == 1
         and b['imageId'] == a.image(m) and b['sourceSha256'] == source_identity(HERE)['sha256'], 'EXTERNAL_APP_IDENTITY')
    return d, m, b


def ingress(cell, spec):
    d, m, b = load(cell, spec)
    need(not a.resources(m), 'EXTERNAL_BIND_BEFORE_DEPLOY_ONLY')
    config = a.document(d / 'frozen.compose.json')
    published = [(name, p) for name, value in config['services'].items() for p in value.get('ports', [])]
    need(len(published) == 1 and published[0][0] == 'nginx' and published[0][1].get('host_ip') == '127.0.0.1', 'EXTERNAL_EDGE_BINDING_SHAPE')
    name, p = published[0]
    need(int(p['published']) == m['port'] and b['port'] == m['port'] and int(p['target']) == 8080, 'EXTERNAL_EDGE_PORT')
    p['host_ip'], p['published'] = b['appAddress'], str(b['port'])
    # Loopback is not retained as an unmeasured second edge. App-side public
    # readiness/oracles use the explicitly bound private address in this profile.
    m['externalBinding'] = b
    write(d / 'frozen.compose.json', config)
    m['composeSha256'] = a.digest(d / 'frozen.compose.json')
    write(d / 'owner.json', m)
    write(d / 'external-binding.json', b)


def export_traffic(cell, spec):
    d, m, b = load(cell, spec)
    need(m.get('externalBinding') == b, 'EXTERNAL_BINDING_CHANGED')
    out = d / 'traffic-export'
    out.mkdir(mode=0o700)
    # Explicit allowlist only: never export state, env, SQL/provider credentials
    # or private evaluator proof to the traffic host.
    for name in ('package.json', 'package-lock.json'):
        (out / name).write_bytes((d / 'dependencies' / name).read_bytes())
        (out / name).chmod(0o600)
    write(out / 'tenants.private.json', a.document(d / 'tenants.private.json'))
    generated = traffic_probe.generate(a.ROOT, out / 'probe.js')
    (out / 'recovery.cjs').write_bytes((HERE / 'recovery.cjs').read_bytes())
    (out / 'workload.js').write_bytes((d / 'k6/workload.js').read_bytes())
    need({f.name for f in out.iterdir() if f.is_file()} == set(TRAFFIC_FILES), 'EXTERNAL_TRAFFIC_EXPORT_ALLOWLIST')
    descriptor = {'version': 1, 'profile': b['profile'], 'binding': b, 'generator': m['generator'],
                  'evaluatorIdleSafety':a.evaluator_idle.POLICY,'evaluatorIdleArtifact':a.evaluator_idle.ARTIFACT_KIND,'sqlSnapshotTiming':'existing-query-request-brackets-v1',
                  'settingsFingerprint': m['settingsFingerprint']['sha256'], 'trafficRunId': 'm7-' + m['owner'][:12], 'probe': generated,
                  'files': {f.name: a.digest(f) for f in out.iterdir() if f.is_file()}}
    write(out / 'traffic.json', descriptor)
    return descriptor


def recovery(d, m, mode, baseline=None, deadline=None):
    spec = {'mode': mode, 'path': str(d / 'load' / ('evaluator-recovery-baseline.private.json' if mode == 'baseline' else 'evaluator-recovery.private.json')),
            'composeArgs': ['compose', '-p', m['project'], '--env-file', str(d / 'env'), '-f', str(d / 'frozen.compose.json')],
            'services': a.progress_services(d), 'ids': [row['id'] for row in a.document(d / 'tenants.private.json')],
            'attribution': a.progress_attribution(m)}
    if baseline is not None:
        spec.update(baseline=str(baseline), deadlineMs=deadline)
    with a.private_commands(d / 'external-recovery-commands' / mode):
        output = a.command([sys.executable, a.HERE / 'evaluator_recovery.py'], input=json.dumps(spec).encode(), timeout=920)
    return json.loads(output)


def restart(d, m):
    at = int(time.time() * 1000)
    compose_args = ['compose', '-p', m['project'], '--env-file', str(d / 'env'), '-f', str(d / 'frozen.compose.json')]
    script = "const s=JSON.parse(require('fs').readFileSync(0));require(process.argv[1]).restart(s).then(x=>console.log(JSON.stringify(x))).catch(e=>{console.error(e.code||'RESTART_FAILED');process.exitCode=1;})"
    output = a.command(['node', '-e', script, d / 'restart.cjs'], input=json.dumps({'composeArgs': compose_args, 'roles': m['restartRoles'], 'at': at}).encode(), timeout=150)
    result = json.loads(output)
    need(set(result.get('starts', {})) == set(m['restartRoles']), 'EXTERNAL_RESTART_ROSTER')
    return result, at


def idle(d, m):
    a.frozen(m, 'run')
    a.quiet(d, m, 'run-before', check_load=False)
    a.verify(d, m)
    a.readiness(d, m)
    for name, seconds in (('idle-disabled', 60), ('idle', 120)):
        out = d / name
        out.mkdir()
        a.psql(d, 'SELECT pg_stat_statements_reset();')
        if name == 'idle':
            observed = a.enabled_idle(d, m, out, seconds)
            need(observed.result['verdict'] == 'PASS', 'EXTERNAL_IDLE_FAILED')
        else:
            a.phase_snapshot(d, out, 'before')
            time.sleep(seconds)
            a.phase_snapshot(d, out, 'after')


def health(d, m, deadline):
    start = time.monotonic()
    pending = set(m['restartRoles'])
    rows = {}
    while pending and int(time.time() * 1000) < deadline:
        for role in list(pending):
            raw = a.compose(d, 'ps', '-q', role).strip()
            need(raw and '\n' not in raw, 'EXTERNAL_RESTART_INSTANCE_MISSING')
            state = json.loads(a.command(['docker', 'inspect', '--format', '{{json .State}}', raw]))
            if state.get('Running') and state.get('Health', {}).get('Status') == 'healthy':
                rows[role] = {'healthyMs': (time.monotonic() - start) * 1000}
                pending.remove(role)
        if pending:
            time.sleep(.25)
    need(not pending, 'EXTERNAL_HEALTH_UNMEASURED')
    return rows


def summarize(d, m, b, idle_result, load_result, recovered, health_result, restart_result):
    out = d / 'load'
    probe, k6 = a.document(out / 'probe.json'), a.document(out / 'k6-summary.json')
    traffic_verdict(probe, k6['metrics'], m['tenants'])
    fingerprint = a.profile_provenance.fingerprint_check(k6['metrics'])
    need(fingerprint['verdict'] == 'PASS', 'EXTERNAL_SETTINGS_FINGERPRINT')
    oracle = a.count_oracle(d)
    a.control(d, m)
    need(not any(not row['owned'] for row in a.inventory(m['owner'])['containers']), 'EXTERNAL_FOREIGN_ACTIVE_CONTAINERS')
    a.verify(d, m)
    measurement = measurements(d, m)
    generator = a.document(out / 'generator-metrics.json')
    server_verdict(oracle, recovered, measurement, generator, b)
    result = {'version': 1, 'kind': 'm7-external-generator-cell', 'profile': b['profile'], 'binding': b,
              'pair': m['pair'], 'imageId': m['imageId'], 'baseInstrument': m['instrument'],
              'externalInstrument': source_identity(HERE), 'profileSelection': m['profileSelection'],
              'settingsFingerprintObservation': fingerprint, 'tenants': m['tenants'], 'verdict': 'PASS',
              'capacityAcceptance': 'NOT_GRANTED', 'topologyQualification': 'REQUIRES_REVIEWED_LIVE_SMOKE',
              'observerProfile': {'evaluatorIdleSafety':a.evaluator_idle.POLICY,'evaluatorIdleArtifact':a.evaluator_idle.ARTIFACT_KIND,'sqlSnapshotTiming':'existing-query-request-brackets-v1','idleTailScope':'point completion outside original metric window; no global tail quiescence', 'perWriteSqlLatencyPolling': 'NOT_RUN', 'strictServerProgress': 'UNCHANGED', 'loadQueryCostComparison': 'placement and observer changes; not placement-only'},
              'metricsAvailability': {'writeToFrameMs': 'generator-monotonic-clock', 'writeToEvaluationMs': 'UNMEASURED',
                                      'restartCommandMs': 'app-clock', 'crossHostClockSubtraction': False},
              'probe': probe, 'oracle': oracle, 'measurements': measurement, 'generatorMetrics': generator,
              'idleTailPublication':a.document(d/'idle/evaluator-tail-publication.json')if(d/'idle/evaluator-tail-publication.json').is_file()else None,
              'evaluatorProgress': {'idle': idle_result, 'load': load_result, 'recovery': recovered},
              'restart': {'command': restart_result, 'health': health_result}}
    write(d / 'summary.json', result)
    return result


def session(cell, spec):
    d, m, b = load(cell, spec)
    need(m.get('externalBinding') == b, 'EXTERNAL_BINDING_CHANGED')
    channel = Channel(b, 'app-0')
    idle(d, m)
    channel.send('app-ready')
    primed = channel.receive('client-primed', 1800)
    need(primed == {'primed': 2 * m['tenants']}, 'EXTERNAL_PRIME_FAILED')
    out = d / 'load'
    out.mkdir()
    runid = 'm7-' + m['owner'][:12]
    (out / 'runid').write_text(runid)
    with a.sampling(d, out):
        a.phase_snapshot(d, out, 'after-prime')
        a.psql(d, 'SELECT pg_stat_statements_reset();')
        a.phase_snapshot(d, out, 'before')
        with a.observe_progress(d, m, out, 'load') as load_progress:
            channel.send('load-ready')
            channel.receive('load-complete', 900)
        a.phase_snapshot(d, out, 'after')
        need(load_progress.result['verdict'] == 'PASS', 'EXTERNAL_LOAD_PROGRESS_FAILED')
        baseline = recovery(d, m, 'baseline')
        channel.send('restart-ready')
        channel.receive('restart-armed', 180)
        restarted, at = restart(d, m)
        channel.send('restart-done', {'status': 'PASS', 'commandMs': restarted['commandMs']})
        deadline = min(at + 900000, int((b['expiresAt'] - 540) * 1000))
        ready = health(d, m, deadline)
        recovered = recovery(d, m, 'recovery', out / 'evaluator-recovery-baseline.private.json', deadline)
        need(recovered.get('verdict') == 'PASS' and recovered.get('missing') == 0, 'EXTERNAL_RECOVERY_FAILED')
        channel.send('server-recovery-complete')
        channel.receive('finish', 600)
    a.phase_snapshot(d, out, 'after-reconnect')
    idle_result = a.progress_summary(d / 'idle')
    result = summarize(d, m, b, idle_result, a.progress_summary(out), recovered, ready, restarted)
    channel.send('cell-complete', {'verdict': result['verdict']})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('descriptor', 'ingress', 'export', 'session'))
    parser.add_argument('--cell')
    parser.add_argument('--binding')
    args = parser.parse_args()
    if args.command == 'descriptor':
        return print(json.dumps(source_identity(HERE), sort_keys=True))
    need(args.cell is not None and args.binding is not None, 'EXTERNAL_INPUT_REQUIRED')
    spec = json.loads(Path(args.binding).read_text())
    if args.command == 'ingress':
        ingress(args.cell, spec)
    elif args.command == 'export':
        print(json.dumps(export_traffic(args.cell, spec), sort_keys=True))
    else:
        with a.private_commands(Path(args.cell) / 'external-session-commands'):
            session(args.cell, spec)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if re.fullmatch('(?:EXTERNAL|M7)_[A-Z_]+(?::[A-Za-z0-9_.-]+)?', str(error)) else 'EXTERNAL_APP_REFUSED', file=sys.stderr)
        sys.exit(1)
