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
from protocol import viewer_total, Channel, binding, need, source_identity, traffic_verdict, server_verdict, TRAFFIC_FILES, write, discovery_mode, topology_dependencies, work_seconds, RESERVE
import traffic_probe
sys.path.insert(0, str(HERE.parent / 'm7-joined'))
import adapter as a
import evaluator_recovery
from reduce import measurements


def load(cell, spec, now=None):
    b = binding(spec, now)
    topology_dependencies(b,HERE.parents[2])
    d, m = a.load(cell)
    from host_binding import preflight
    preflight(d)
    if m.get('orchestrationHome')is not None:
        from host_binding import existing
        existing(d)
    from transport import cell_contract
    cell_contract(m, b)
    a.frozen(m, 'deploy')
    receipt = a.document(m['freeze'])
    need(receipt.get('remoteReportMode','strict') == b.get('reportMode','strict'), 'REMOTE_REPORT_AUTHORIZATION_REQUIRED')
    need(receipt.get('remotePgstreamTopology') == b.get('pgstreamTopology') and receipt.get('remoteDiagnosticResourceProfile') == b.get('diagnosticResourceProfile') and receipt.get('remoteHelperDependencies') == b.get('helperDependencies'),'REMOTE_TOPOLOGY_AUTHORIZATION_REQUIRED')
    need(receipt.get('remoteWorkload') == b.get('workload'), 'REMOTE_WORKLOAD_AUTHORIZATION_REQUIRED')
    need(receipt.get('remoteComponentCases') == b.get('componentCases'), 'REMOTE_COMPONENT_RECEIPT_REQUIRED')
    need(receipt.get('remoteProfile') == b['profile'] and receipt.get('remoteTransport') == b['transport'] and receipt.get('remoteExtensionSha256') == b['sourceSha256'], 'REMOTE_EXTENSION_AUTHORIZATION_REQUIRED')
    need(b['pair'] == m['pair'] and b['tenants'] == m['tenants'] and m['replicas'] == 1
         and b['imageId'] == a.image(m) and b['sourceSha256'] == source_identity(HERE)['sha256'], 'EXTERNAL_APP_IDENTITY')
    if discovery_mode(b):
        a.discovery_source_preflight(d,m)
    if m.get('preparedExternalBinding') is not None:
        need(m['preparedExternalBinding'] == b and b['port'] == m['port'], 'EXTERNAL_PREPARED_BINDING_CHANGED')
    if m.get('externalBinding') is not None:
        from transport import verify_overlay, owned_nic, local_nics, firewall_check
        need(m['externalBinding'] == b, 'EXTERNAL_BINDING_CHANGED')
        verify_overlay(a.document(d / 'frozen.compose.json'), b, a.document(d / 'remote-overlay.json'))
        owned_nic(b, local_nics())
        firewall_check(b)
    return d, m, b


def record_prepared_binding(cell, spec):
    d, m, b = load(cell, spec)
    need(m.get('prepared') is True and not m.get('attached') and
         m.get('preparedExternalBinding') is None and m.get('externalBinding') is None,
         'EXTERNAL_PREPARED_BINDING_ALREADY_SET')
    need(m['project'] == a.fixture_project(argparse.Namespace(tenants=m['tenants'], replicas=m['replicas']), m['owner']), 'EXTERNAL_PREPARED_PROJECT_CHANGED')
    # Canonical prepare selects the port; bind that actual value before ingress.
    prepared = binding({**b, 'port': m['port']})
    m['preparedExternalBinding'] = prepared
    write(d / 'owner.json', m)
    return d, m, prepared


def cleanup(cell, raw):
    # Expired traffic authority must not prevent exact-owned cleanup.
    now = raw['expiresAt'] - 541
    binding(raw, now)
    d=Path(cell).resolve()
    if(d/'orchestration-journal.json').exists():
        from host_binding import cleanup as stop_recorded
        immutable=a.document(d/'orchestration-owner.json')
        need((immutable.get('externalBinding')or immutable.get('preparedExternalBinding'))==raw,'EXTERNAL_BINDING_CHANGED')
        owner=immutable['owner']
        for job in d.glob('**/*-job.json'):a.stop_job(job,owner)
        result=stop_recorded(d);write(d/'exact-cleanup.json',result);return result
    d, m = a.load(cell)
    from transport import cell_contract
    cell_contract(m, raw)
    if m.get('externalBinding') is not None:
        need(m['externalBinding'] == raw, 'EXTERNAL_BINDING_CHANGED')
    else:
        need(m.get('prepared') is True and not m.get('attached') and
             m.get('preparedExternalBinding') == raw and m['port'] == raw['port'],
             'EXTERNAL_PREPARED_BINDING_CHANGED')
        need(m['project'] == a.fixture_project(argparse.Namespace(tenants=m['tenants'], replicas=m['replicas']), m['owner']), 'EXTERNAL_PREPARED_PROJECT_CHANGED')
        # Existing source/receipt, image, host, config and resource ownership
        # guards qualify cleanup even when admission never completed.
        d, m, _ = load(cell, raw, now)
        a.verify(d, m)
        config = a.document(d / 'frozen.compose.json')
        published = [(name, port) for name, service in config['services'].items() for port in service.get('ports', [])]
        need(len(published) == 1 and published[0][0] == 'nginx' and
             published[0][1].get('host_ip') == '127.0.0.1' and
             int(published[0][1]['published']) == raw['port'] and
             int(published[0][1]['target']) == 8080 and
             published[0][1].get('protocol', 'tcp') == 'tcp', 'EXTERNAL_EDGE_BINDING_SHAPE')
        from transport import owned_nic, local_nics
        owned_nic(raw, local_nics())
    a.assert_owned(m)
    if raw.get('componentCases'):
        from component_cases import plan
        for case in plan(raw['componentCases'],raw['tenants'])['cases']:
            folder=d/'components'/case['id']/'load'
            for job in folder.glob('*-job.json'):a.stop_job(job,m['owner'])
    from host_binding import cleanup as stop_recorded
    result=stop_recorded(d)
    write(d/'exact-cleanup.json',result)
    return result


def ingress(cell, spec):
    d, m, b = load(cell, spec)
    need(m.get('preparedExternalBinding') == b, 'EXTERNAL_PREPARED_BINDING_CHANGED')
    need(not a.resources(m), 'EXTERNAL_BIND_BEFORE_DEPLOY_ONLY')
    from host_binding import preflight
    preflight(d)
    config = a.document(d / 'frozen.compose.json')
    published = [(name, p) for name, value in config['services'].items() for p in value.get('ports', [])]
    need(len(published) == 1 and published[0][0] == 'nginx' and published[0][1].get('host_ip') == '127.0.0.1', 'EXTERNAL_EDGE_BINDING_SHAPE')
    name, p = published[0]
    need(int(p['published']) == m['port'] and b['port'] == m['port'] and int(p['target']) == 8080, 'EXTERNAL_EDGE_PORT')
    from transport import overlay, local_nics, firewall_check
    config, evidence = overlay(config, b, local_nics(), firewall_check(b))
    write(d / 'remote-overlay.json', evidence)
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
    (out / 'probe-accounting.cjs').write_bytes((a.HERE / 'probe-accounting.cjs').read_bytes())
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
    from host_binding import restart as restart_recorded
    result=restart_recorded(d,m['restartRoles'],at)
    need(set(result.get('starts', {})) == set(m['restartRoles']), 'EXTERNAL_RESTART_ROSTER')
    return result, at


def idle(d, m):
    a.frozen(m, 'run')
    a.quiet(d, m, 'run-before', check_load=False)
    a.verify(d, m)
    a.readiness(d, m)
    for name, seconds in (('idle-disabled', m['cadence']['warmupSeconds']), ('idle', m['cadence']['idleSeconds'])):
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
    if discovery_mode(b):
        probe=a.document(out/'probe.json') if (out/'probe.json').is_file() else {}
        k6=a.document(out/'k6-summary.json') if (out/'k6-summary.json').is_file() else {}
        return discovery_summary(d,m,b,probe,k6)
    probe, k6 = a.document(out / 'probe.json'), a.document(out / 'k6-summary.json')
    traffic_verdict(probe, k6['metrics'], m['tenants'],viewer_total(b))
    from viewer_plan import check
    check(m,a.document(d/'tenants.private.json'),probe,a.document(out/'fanout.json')['probeWrites']['byTenant'])
    from clinical import completed
    clinical = completed(d, m)
    load(d, b)  # Recheck actual NIC and admission before final qualification.
    fingerprint = a.profile_provenance.fingerprint_check(k6['metrics'])
    need(fingerprint['verdict'] == 'PASS', 'EXTERNAL_SETTINGS_FINGERPRINT')
    oracle = a.count_oracle(d)
    a.control(d, m)
    need(not any(not row['owned'] for row in a.inventory(m['owner'])['containers']), 'EXTERNAL_FOREIGN_ACTIVE_CONTAINERS')
    a.verify(d, m)
    measurement = measurements(d, m)
    generator = a.document(out / 'generator-metrics.json')
    server_verdict(oracle, recovered, measurement, generator, b)
    result = {'version': 1, 'kind': 'remote-pgstream-calibration-cell', 'profile': b['profile'], 'binding': b,
              'pair': m['pair'], 'imageId': m['imageId'], 'baseInstrument': m['instrument'],
              'externalInstrument': source_identity(HERE), 'profileSelection': m['profileSelection'],
              'settingsFingerprintObservation': fingerprint, 'tenants': m['tenants'], 'verdict': 'PASS',
              'capacityAcceptance': 'NOT_GRANTED', 'topologyQualification': 'REQUIRES_REVIEWED_LIVE_SMOKE',
              'observerProfile': {'evaluatorIdleSafety':a.evaluator_idle.POLICY,'evaluatorIdleArtifact':a.evaluator_idle.ARTIFACT_KIND,'sqlSnapshotTiming':'existing-query-request-brackets-v1','idleTailScope':'point completion outside original metric window; no global tail quiescence', 'perWriteSqlLatencyPolling': 'NOT_RUN', 'strictServerProgress': 'UNCHANGED', 'loadQueryCostComparison': 'placement and observer changes; not placement-only'},
              'metricsAvailability': {'writeToFrameMs': 'generator-monotonic-clock', 'writeToEvaluationMs': 'UNMEASURED',
                                      'restartCommandMs': 'NOT_RUN', 'crossHostClockSubtraction': False},
              'scopeAvailability': {'startup': 'deployment-stages.json', 'readiness': 'runtime-readiness.json', 'steady': 'measured bookends', 'dueOpportunity': 'UNMEASURED', 'reconnect': 'UNMEASURED'},
              'completedOutput': clinical, 'probe': probe, 'oracle': oracle, 'measurements': measurement, 'generatorMetrics': generator,
              'idleTailPublication':a.document(d/'idle/evaluator-tail-publication.json')if(d/'idle/evaluator-tail-publication.json').is_file()else None,
              'evaluatorProgress': {'idle': idle_result, 'load': load_result, 'recovery': recovered},
              'restart': {'command': restart_result, 'health': health_result}}
    write(d / 'summary.json', result)
    return result



def discovery_summary(d,m,b,probe,k6):
    """Retain observations; missing proof never becomes strict acceptance."""
    import discovery
    out=d/'load'
    result={'version':1,'kind':'remote-pgstream-discovery-cell','status':'PARTIAL','verdict':'UNMEASURED',
            'runPurpose':'discovery','capacityAcceptance':'NOT_GRANTED',**m.get('discoveryAuthorization',{}),'binding':b,'pair':m['pair'],
            'imageId':m['imageId'],'baseInstrument':m['instrument'],'externalInstrument':source_identity(HERE),
            'tenants':m['tenants'],'cadence':m['cadence'],'probe':probe,'metrics':k6.get('metrics',{}),
            'strictChecks':{},'optionalObservations':{},'crossHostClockSubtraction':False,
            'writeToEvaluationMs':'UNMEASURED','durableOutputTiming':'UNMEASURED; SUT completion is checked separately',
            'oracle':None,'completedOutput':None,
            'processes':a.document(out/'generator-processes.json') if (out/'generator-processes.json').is_file() else {'verdict':'UNMEASURED'},
            'publicResult':a.document(out/'generator-public-result.json') if (out/'generator-public-result.json').is_file() else {'verdict':'UNMEASURED'}}
    def save():
        result['artifacts']={str(p.relative_to(d)):a.digest(p) for p in out.iterdir() if p.is_file()}
        write(d/'summary.json',result)
    save()
    try:
        a.verify(d,m);load(d,b)
        need(not probe.get('hardFailure'),'REMOTE_DISCOVERY_PROBE_HARD_FAILURE')
        result['strictChecks']['sourceOwnership']={'verdict':'PASS'}
        for stage in ('idle','load'):
            file=d/stage/'evaluator-progress.json'
            observed=a.document(file) if file.is_file() else {'verdict':'UNMEASURED','code':'M7_EVALUATOR_PROGRESS_UNAVAILABLE'}
            need(not discovery.hard_recovery(observed),'REMOTE_DISCOVERY_CLINICAL_FAILURE')
            result['strictChecks'][stage]={k:observed[k] for k in ('verdict','code') if k in observed}
        metrics=k6.get('metrics',{})
        result['settingsFingerprintObservation']=a.profile_provenance.fingerprint_check(metrics)
        need(result['settingsFingerprintObservation']['verdict']!='FAIL','EXTERNAL_SETTINGS_FINGERPRINT')
        try:
            counts,known=discovery.count_observation(a,d,out,(out/'runid').read_text().strip(),metrics)
            result['oracleFindings']=counts;result['oracle']=counts if known else None
        except Exception as error:
            if hasattr(error,'oracleFindings'):result['oracleFindings']=error.oracleFindings
            raise
        if probe.get('window') and (out/'fanout.json').is_file():
            from viewer_plan import check
            result['viewerFrames']=check(m,a.document(d/'tenants.private.json'),probe,a.document(out/'fanout.json')['probeWrites']['byTenant'])
        from clinical import completed
        try:result['completedOutput']=completed(d,m)
        except RuntimeError as error:
            if str(error) not in ('REMOTE_CLINICAL_CLIENT_WITNESS_REQUIRED','REMOTE_CLINICAL_COMPLETION_UNMEASURED'):raise
            result['completedOutput']={'verdict':'UNMEASURED','code':str(error)}
        for name,collect in (('measurements',lambda:measurements(d,m)),('generatorMetrics',lambda:a.document(out/'generator-metrics.json'))):
            try:result['optionalObservations'][name]=collect()
            except Exception:result['optionalObservations'][name]={'verdict':'UNMEASURED','code':'REMOTE_OPTIONAL_OBSERVATION_UNAVAILABLE'}
        save();return result
    except Exception as error:
        result['verdict']='FAIL';result['failure']={'code':str(error) if re.fullmatch(r'(?:M7|REMOTE|EXTERNAL)_[A-Z_]+',str(error)) else 'REMOTE_DISCOVERY_INSTRUMENT_ERROR'}
        save();raise


def session(cell, spec):
    d, m, b = load(cell, spec)
    with a.command_deadline(b['expiresAt']-RESERVE if discovery_mode(b) else None):
        return _session(d,m,b)

def _session(d,m,b):
    if b.get('componentCases') is not None:
        from component_sessions import app_session
        return app_session(d,m,b,sys.modules[__name__])
    need(m.get('externalBinding') == b, 'EXTERNAL_BINDING_CHANGED')
    channel = Channel(b, 'app-0')
    a.sample_context(d, m)  # Actual evaluator/RT configs, dependencies and SQL identities on SUT.
    if discovery_mode(b):
        import discovery
        record=discovery.Record(a,d,m)
        record.observe('idle',lambda:idle(d,m))
    else:idle(d, m)
    channel.send('app-ready')
    primed = channel.receive('client-primed', work_seconds(b,1800))
    need(set(primed)=={'primed'} and type(primed['primed']) is int and 0<=primed['primed']<=viewer_total(b),'EXTERNAL_PRIME_INVALID')
    need(discovery_mode(b) or primed == {'primed': viewer_total(b)}, 'EXTERNAL_PRIME_FAILED')
    out = d / 'load'
    out.mkdir()
    runid = 'm7-' + m['owner'][:12]
    (out / 'runid').write_text(runid)
    with a.sampling(d, out):
        a.phase_snapshot(d, out, 'after-prime')
        a.psql(d, 'SELECT pg_stat_statements_reset();')
        a.phase_snapshot(d, out, 'before')
        try:
            def work():
                channel.send('load-ready')
                channel.receive('load-complete', work_seconds(b,m['cadence']['loadSeconds'] + 600))
            if discovery_mode(b):record.observe('load',lambda:discovery.observed_load(a,d,m,out,work))
            else:
                with a.observe_progress(d,m,out,'load') as load_progress:work()
        finally:
            a.phase_snapshot(d, out, 'after')
        if not discovery_mode(b):need(load_progress.result['verdict'] == 'PASS', 'EXTERNAL_LOAD_PROGRESS_FAILED')
        channel.send('server-recovery-complete', {'measurement': 'NOT_RUN'})
        ready, restarted = {}, {'measurement': 'NOT_RUN'}
        recovered = {'measurement': 'NOT_RUN', 'reason': 'noRestart diagnostic profile'}
        channel.receive('finish', work_seconds(b,600))
    a.phase_snapshot(d, out, 'after-load')
    idle_result = {} if discovery_mode(b) else a.progress_summary(d / 'idle')
    result = summarize(d, m, b, idle_result, {} if discovery_mode(b) else a.progress_summary(out), recovered, ready, restarted)
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
