"""The vcpool connector stage of a load case (execute.py, when the run carries `connectors`).

start(call, c, tenants, out): before the probe starts, give the connector tenants (connectors.select:
the roster tail, outside the ordinary roster) a connector. It creates three run-labelled Secrets
(ns-upstream-sites, ns-connector-entry, ns-connector-score), applies the upstream and scorer objects,
unsuspends the binding's connector-entry Job and waits for it. Secret contents go only to stdin.
collect(call, c, out): reads the in-cluster scorer's log into connector-poll.private.jsonl and writes
connector-score.json (score.cjs summarize). A collection failure is retained as UNMEASURED.

`call` is the adapter's kubectl client: call(argv, data=bytes, read=bool) -> bytes.
"""
import json
from pathlib import Path
import subprocess
import time

import connectors

SECRETS = ('ns-upstream-sites', 'ns-connector-entry', 'ns-connector-score')
HISTORY_SECONDS = 3 * 3600


def until(call, argv, done, seconds, code, clock=time, failed=lambda text: False):
    """Poll a read (`get ... -o jsonpath`) until done(text); the read-only guard admits get, not wait or rollout."""
    end = clock.time() + seconds
    while True:
        text = call(argv, read=True).decode().strip()
        if done(text):
            return text
        if failed(text) or clock.time() >= end:
            raise RuntimeError(code)
        clock.sleep(2)


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
    chosen = connectors.select(rows, population)
    connectors.need(chosen, 'NO_CONNECTOR_TENANTS')
    history = int(((now or time.time()) - HISTORY_SECONDS) * 1000)
    sites = connectors.sites(chosen)
    return {'tenants': chosen, 'historyStartMs': history,
            'secrets': {'ns-upstream-sites': sites, 'ns-connector-entry': connectors.entry_input(chosen, sites),
                        'ns-connector-score': connectors.score_input(chosen, history)}}


def start(call, c, tenants, out, now=None):
    p = plan(c, tenants, now)
    labels = {'nightscout.org/run-id': c['runId']}
    for name in SECRETS:
        key = 'sites.json' if name == 'ns-upstream-sites' else 'input.json'
        call(['create', 'secret', 'generic', name, '--from-file=' + key + '=/dev/stdin', '-o', 'name'],
             data=json.dumps(p['secrets'][name]).encode(), read=False)
        call(['label', 'secret', name, 'nightscout.org/run-id=' + c['runId']], read=False)
    objects = connectors.manifests(c['namespace'], c['connectors']['image'], p['historyStartMs'], labels)
    call(['apply', '-f', '-', '-o', 'name'], data=json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': objects}).encode(), read=False)
    ready(call, connectors.UPSTREAM)
    node = claim_node(call)
    if node:
        # A suspended, never-started Job admits a scheduling change: pin it beside the claim's holder.
        call(['patch', 'job', 'connector-entry', '--type=merge', '-p',
              json.dumps({'spec': {'template': {'spec': {'nodeSelector': {'kubernetes.io/hostname': node}}}}})], read=False)
    call(['patch', 'job', 'connector-entry', '--type=merge', '-p', '{"spec":{"suspend":false}}'], read=False)
    until(call, ['get', 'job', 'connector-entry', '-o', 'jsonpath={.status.succeeded}:{.status.failed}'],
          lambda t: t.startswith('1:'), 600, 'K8S_CONNECTOR_ENTRY_FAILED', failed=lambda t: t.endswith(':1'))
    entered = int(time.time() * 1000)
    ready(call, 'connector-score')
    record = {'version': 1, 'tenants': len(p['tenants']), 'entryNode': node, 'share': c['connectors']['share'], 'historyStartMs': p['historyStartMs'],
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
    (out / 'connector-score.json').write_text(json.dumps(score, indent=2) + '\n')
    return score
