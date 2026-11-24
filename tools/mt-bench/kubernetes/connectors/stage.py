"""The vcpool connector stage of a load case (execute.py, when the run carries `connectors`).

start(call, c, tenants, out): before the probe starts, give the connector tenants (connectors.select:
the roster tail, outside the ordinary roster) a connector. It creates three run-labelled Secrets
(ns-upstream-sites, ns-connector-entry, ns-connector-score), applies the upstream and scorer objects,
unsuspends the binding's connector-entry Job and waits for it. Secret contents go only to stdin.
collect(call, c, out): reads the in-cluster scorer's log into connector-poll.private.jsonl and writes
connector-score.json (score.cjs summarize). A collection failure is retained as UNMEASURED.
failure_evidence(call, out): on any failure of either, before the case's cleanup deletes the namespace,
keeps the connector-entry Job status, its Pods and their logs, the connector objects' Pods and the
namespace events under out/connector-failure/ (receipt.json lists what was read and what was refused).

`call` is the adapter's kubectl client: call(argv, data=bytes, read=bool) -> bytes.

enter_in_reader(kubectl, pod, rows, c, directory, cutoff): the launch path. Disposable storage keeps the
primer's roster, with each tenant's root secret, only on the fixture reader Pod's emptyDir, and the
binding renders no connector-entry Job there (nightscout-deploy vcpool.libsonnet). The harness keeps
management credentials inside that Pod (fixture.read_roster), so the entry runs there: the image's
connector-entry.js, its input on stdin, the roster at /results. The plan (site tokens, the connector
group's DATA credentials) is kept privately; start() then reads it (c.connectors.planFile) and creates
only the upstream and scorer, never the entry Secret or Job.
"""
import json
from pathlib import Path
import subprocess
import time

import connectors

SECRETS = ('ns-upstream-sites', 'ns-connector-entry', 'ns-connector-score')
HISTORY_SECONDS = 3 * 3600


def until(call, argv, done, seconds, code, clock=time, failed=lambda text: False, timeout_code=None):
    """Poll a read (`get ... -o jsonpath`) until done(text); the read-only guard admits get, not wait or rollout.
    A failed read raises `code`; running out of time raises `timeout_code` (default `code`)."""
    end = clock.time() + seconds
    while True:
        text = call(argv, read=True).decode().strip()
        if done(text):
            return text
        if failed(text):
            raise RuntimeError(code)
        if clock.time() >= end:
            raise RuntimeError(timeout_code or code)
        clock.sleep(2)


# Reads kept when the connector stage fails. Names and fixed codes only: the entry Job prints counts and
# codes, never ids, hosts or credentials; Secret objects are never read.
EVIDENCE = (
    ('connector-entry-job.json', ['get', 'job', 'connector-entry', '-o', 'json']),
    ('connector-entry-pods.json', ['get', 'pods', '-l', 'job-name=connector-entry', '-o', 'json']),
    ('connector-entry.log', ['logs', '-l', 'job-name=connector-entry', '--all-containers', '--tail=-1', '--limit-bytes=1048576']),
    ('upstream-pods.json', ['get', 'pods', '-l', 'app.kubernetes.io/component=upstream', '-o', 'json']),
    ('connector-score-pods.json', ['get', 'pods', '-l', 'nightscout.org/operator-task=connector-score', '-o', 'json']),
    ('vcpool-pods.json', ['get', 'pods', '-l', 'app.kubernetes.io/component=vcpool', '-o', 'json']),
    ('events.json', ['get', 'events', '-o', 'json']),
)


def failure_evidence(call, out, error=None):
    """Best effort, never a stop: each read that fails is listed in the receipt with its error type."""
    directory = out / 'connector-failure'
    directory.mkdir(mode=0o700, exist_ok=True)
    receipt = {'version': 1, 'code': str(error) if error is not None else None,
               'errorType': type(error).__name__ if error is not None else None, 'observedAt': time.time(), 'files': {}}
    for name, argv in EVIDENCE:
        try:
            raw = call(argv, read=True)
            path = directory / name
            path.write_bytes(raw if isinstance(raw, bytes) else str(raw).encode()); path.chmod(0o600)
            receipt['files'][name] = {'bytes': path.stat().st_size}
        except Exception as failure:  # retained, never a stop
            receipt['files'][name] = {'refused': type(failure).__name__, 'detail': str(failure)[:200]}
    (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def ready(call, deployment, seconds=300, clock=time):
    return until(call, ['get', 'deployment', deployment, '-o', 'jsonpath={.status.readyReplicas}'], lambda t: t not in ('', '0'),
                 seconds, 'K8S_CONNECTOR_' + deployment.upper().replace('-', '_') + '_NOT_READY', clock)


def claim_node(call, claim='primer-results'):
    """The node of a live Pod that mounts the RWO roster claim (the lifecycle's fixture reader holds it on
    the primer's node), or None. The connector-entry Job reads the same claim, so it must run there."""
    pods = json.loads(call(['get', 'pods', '-o', 'json'], read=True))['items']
    nodes = sorted({p['spec'].get('nodeName') for p in pods
                    if p['status'].get('phase') in ('Running', 'Pending') and p['spec'].get('nodeName') and
                    any((v.get('persistentVolumeClaim') or {}).get('claimName') == claim for v in p['spec'].get('volumes', []))})
    connectors.need(len(nodes) <= 1, 'ROSTER_CLAIM_ON_SEVERAL_NODES')
    return nodes[0] if nodes else None


def plan(c, tenants, now=None):
    """The connector tenants and the three Secret payloads (private) for this run."""
    selected = c['connectors']
    population = {'provisionedTenants': len(tenants), 'ordinaryRosterTenants': selected['ordinaryRosterTenants'],
                  'connectorShare': selected['share']}
    rows = [dict(r, dataToken=r.get('dataToken') or r['token']) for r in tenants]
    chosen = connectors.select(rows, population, selected.get('order'))
    connectors.need(chosen, 'NO_CONNECTOR_TENANTS')
    history = int(((now or time.time()) - HISTORY_SECONDS) * 1000)
    sites = connectors.sites(chosen)
    return {'tenants': chosen, 'historyStartMs': history,
            'secrets': {'ns-upstream-sites': sites, 'ns-connector-entry': connectors.entry_input(chosen, sites),
                        'ns-connector-score': connectors.score_input(chosen, history)}}


ENTRY_SCRIPT = 'deploy/multitenant/connector-entry.js'
ENTRY_SECONDS = 600


def kubectl_call(kubectl, run=subprocess.run):
    """A read client over a kubectl prefix, for evidence outside the adapter (the fixture stage)."""
    def call(argv, data=None, read=True, timeout=None):
        result = run([*kubectl, *argv], input=data, capture_output=True, timeout=timeout or 30)
        if result.returncode:
            raise RuntimeError(' '.join(argv[:3]) + ': ' + result.stderr.decode(errors='replace')[-300:])
        return result.stdout
    return call


def enter_in_reader(kubectl, pod, rows, c, directory, cutoff, now=None, run=subprocess.run, clock=time):
    p = plan(c, rows, now)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    argv = [*kubectl, 'exec', '-i', pod, '-c', 'reader', '--', 'env', 'NS_CONNECTOR_ENTRY_INPUT=/dev/stdin', 'NS_PRIMER_STATE=/results',
            'NS_CONNECTOR_API_ORIGIN=http://api:1337', 'NS_CONNECTOR_ADMIN_ORIGIN=http://admin:1342', 'node', ENTRY_SCRIPT]
    started = clock.time()
    receipt = {'version': 1, 'where': 'fixture-reader', 'tenants': len(p['tenants']), 'startedAt': started}
    try:
        seconds = min(ENTRY_SECONDS, cutoff - started)
        connectors.need(seconds > 0, 'CONNECTOR_ENTRY_DEADLINE')
        result = run(argv, input=json.dumps(p['secrets']['ns-connector-entry']).encode(), capture_output=True, timeout=seconds)
        # connector-entry.js prints counts and fixed codes only (never ids, hosts or credentials).
        receipt.update(exit=result.returncode, seconds=round(clock.time() - started, 3),
                       stdout=result.stdout.decode(errors='replace')[-2000:], stderr=result.stderr.decode(errors='replace')[-2000:])
        if result.returncode:
            raise RuntimeError('K8S_CONNECTOR_ENTRY_FAILED')
        outcome = json.loads(result.stdout.decode().strip().splitlines()[-1])
        connectors.need(outcome.get('state') == 'connectors-entered' and outcome.get('tenants') == len(p['tenants']), 'CONNECTOR_ENTRY_INCOMPLETE')
        receipt['result'] = outcome
    except Exception as error:
        receipt.setdefault('code', str(error) if str(error).startswith(('K8S_', 'CONNECTOR_')) else 'K8S_CONNECTOR_ENTRY_FAILED')
        (directory / 'connector-entry.json').write_text(json.dumps(receipt, indent=2) + '\n')
        failure_evidence(kubectl_call(kubectl, run), directory, error)
        raise
    entered = int(clock.time() * 1000)
    path = directory / 'connector-plan.private.json'
    path.write_text(json.dumps({**p, 'enteredAt': entered}) + '\n'); path.chmod(0o600)
    (directory / 'connector-entry.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return path


def start(call, c, tenants, out, now=None):
    try:
        return _start(call, c, tenants, out, now)
    except Exception as error:
        failure_evidence(call, out, error)
        raise


def _start(call, c, tenants, out, now=None):
    entered_in_reader = bool(c['connectors'].get('planFile'))
    if entered_in_reader:
        p = json.loads(Path(c['connectors']['planFile']).read_text())
        connectors.need({r['id'] for r in p['tenants']} <= {r['id'] for r in tenants}, 'CONNECTOR_PLAN_ROSTER_CHANGED')
    else:
        p = plan(c, tenants, now)
    labels = {'nightscout.org/run-id': c['runId']}
    for name in SECRETS:
        if entered_in_reader and name == 'ns-connector-entry':
            continue
        key = 'sites.json' if name == 'ns-upstream-sites' else 'input.json'
        call(['create', 'secret', 'generic', name, '--from-file=' + key + '=/dev/stdin', '-o', 'name'],
             data=json.dumps(p['secrets'][name]).encode(), read=False)
        call(['label', 'secret', name, 'nightscout.org/run-id=' + c['runId']], read=False)
    objects = connectors.manifests(c['namespace'], c['connectors']['image'], p['historyStartMs'], labels)
    call(['apply', '-f', '-', '-o', 'name'], data=json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': objects}).encode(), read=False)
    ready(call, connectors.UPSTREAM)
    if entered_in_reader:
        return _record(call, c, p, out, None)
    node = claim_node(call)
    if node:
        # A suspended, never-started Job admits a scheduling change: pin it beside the claim's holder.
        call(['patch', 'job', 'connector-entry', '--type=merge', '-p',
              json.dumps({'spec': {'template': {'spec': {'nodeSelector': {'kubernetes.io/hostname': node}}}}})], read=False)
    call(['patch', 'job', 'connector-entry', '--type=merge', '-p', '{"spec":{"suspend":false}}'], read=False)
    until(call, ['get', 'job', 'connector-entry', '-o', 'jsonpath={.status.succeeded}:{.status.failed}'],
          lambda t: t.startswith('1:'), 600, 'K8S_CONNECTOR_ENTRY_FAILED', failed=lambda t: t.endswith(':1'),
          timeout_code='K8S_CONNECTOR_ENTRY_TIMEOUT')
    return _record(call, c, p, out, node)


def _record(call, c, p, out, node):
    # Scored from here: the upstream serves and the scorer is ready.
    ready(call, 'connector-score')
    entered = int(time.time() * 1000)
    record = {'version': 1, 'tenants': len(p['tenants']), 'entryNode': node, 'entry': 'fixture-reader' if c['connectors'].get('planFile') else 'job',
              'share': c['connectors']['share'], 'historyStartMs': p['historyStartMs'],
              'enteredAt': entered, 'scriptsSha256': connectors.scripts_digest()}
    (out / 'connectors.json').write_text(json.dumps(record, indent=2) + '\n')
    private = {'historyStartMs': p['historyStartMs'], 'tenants': [{'site': r['site'], 'enteredAt': entered} for r in p['tenants']]}
    path = out / 'connector-score-input.private.json'
    path.write_text(json.dumps(private) + '\n'); path.chmod(0o600)
    return record


def collect(call, c, out, until=None, miss_after_seconds=360):
    try:
        raw = call(['logs', 'deployment/connector-score', '--limit-bytes=67108864'], read=True)
        log = out / 'connector-poll.private.jsonl'
        log.write_bytes(raw); log.chmod(0o600)
        record = json.loads((out / 'connectors.json').read_text())
        until = until or int(time.time() * 1000)
        result = subprocess.run(['node', str(connectors.HERE / 'score.cjs'), 'summarize', str(out / 'connector-score-input.private.json'), str(log),
                                 '--from', str(record['enteredAt']), '--until', str(until), '--miss-after-seconds', str(miss_after_seconds)],
                                capture_output=True, text=True, timeout=120)
        score = json.loads(result.stdout)
    except Exception as error:  # retained, never a pass
        score = {'verdict': 'UNMEASURED', 'code': 'K8S_CONNECTOR_SCORE_UNAVAILABLE', 'errorType': type(error).__name__}
        failure_evidence(call, out, error)
    (out / 'connector-score.json').write_text(json.dumps(score, indent=2) + '\n')
    return score
