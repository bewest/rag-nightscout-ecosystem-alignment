"""vcpool connector workload: which tenants get a connector, and the objects that serve and score it.

A profile selects `population.connectorShare` (0..1). round(share x provisionedTenants) tenants,
taken from the END of the primer roster, get a tenant-side Nightscout connector that pulls from the
in-cluster synthetic upstream (upstream.cjs). They must lie outside the ordinary roster: the
nightscout-connect output reads its gap as the tenant's newest stored row
(nightscout-connect lib/outputs/nightscout.js gap_for), so an uploader writing the same collections
into a connector tenant moves the gap past upstream rows and they are never copied.

Objects (all in the run namespace, synthetic data only):
  Secret ns-upstream-sites      {"<site>": "<token>"}: the upstream's per-site source tokens
  Deployment/Service nightscout-upstream (port 1337) and a NetworkPolicy admitting vcpool (and operator)
  Secret ns-connector-entry     input.json for the binding's connector-entry Job (deploy vcpool.libsonnet)
  Secret ns-connector-score + Deployment connector-score  the in-cluster poller (score.cjs poll)
The scripts ride a ConfigMap built from this directory; the app image provides node.
"""
import hashlib
import json
import math
import secrets as token_source
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = ('upstream.cjs', 'score.cjs')
SOURCE_ID = 'nightscout'
COLLECTIONS = ['entries', 'treatments', 'devicestatus']
UPSTREAM = 'nightscout-upstream'
PORT = 1337
LABEL = 'app.kubernetes.io/component'


def need(value, code):
    if not value:
        raise ValueError('K8S_CONNECTORS_' + code)


def count(provisioned, share):
    need(isinstance(share, (int, float)) and not isinstance(share, bool) and 0 <= share <= 1, 'CONNECTOR_SHARE')
    return int(math.floor(share * provisioned + 0.5))


def validate(population):
    """Profile check: the connector tenants are outside the ordinary (uploader) roster."""
    share = population.get('connectorShare', 0)
    n, ordinary = population['provisionedTenants'], population['ordinaryRosterTenants']
    k = count(n, share)
    need(n - ordinary >= k, 'CONNECTOR_TENANTS_RECEIVE_ORDINARY_WRITES')
    return k


def select(roster, population):
    """The connector tenants: the last k roster rows, each with its site name."""
    k = validate(population)
    need(len(roster) == population['provisionedTenants'], 'ROSTER')
    return [dict(row, site='s%d' % i) for i, row in enumerate(roster[len(roster) - k:])] if k else []


def sites(selected, token=lambda: token_source.token_hex(16)):
    return {row['site']: token() for row in selected}


def entry_input(selected, site_tokens, upstream=UPSTREAM):
    return {'version': 1, 'sourceId': SOURCE_ID, 'collections': COLLECTIONS,
            'tenants': [{'id': r['id'], 'endpoint': 'http://%s:%d/s/%s' % (upstream, PORT, r['site']),
                         'sourceCredential': site_tokens[r['site']]} for r in selected]}


def score_input(selected, history_start_ms, api_origin='http://api:1337'):
    return {'apiOrigin': api_origin, 'historyStartMs': history_start_ms,
            'tenants': [{'site': r['site'], 'id': r['id'], 'host': r['host'], 'token': r['dataToken']} for r in selected]}


def scripts_digest():
    h = hashlib.sha256()
    for name in SCRIPTS:
        h.update(name.encode() + b'\0' + (HERE / name).read_bytes())
    return h.hexdigest()


def manifests(namespace, image, history_start_ms, run_labels=None):
    """Upstream, its policy and the scorer. Secrets are created separately (kubectl create secret)."""
    labels = dict(run_labels or {})
    meta = lambda name, component: {'name': name, 'namespace': namespace, 'labels': dict(labels, **{LABEL: component})}
    hardened = {'runAsUser': 1000, 'runAsGroup': 1000, 'runAsNonRoot': True, 'readOnlyRootFilesystem': True,
                'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}
    scripts = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': meta('connector-scripts', 'upstream'),
               'data': {name: (HERE / name).read_text() for name in SCRIPTS}}

    def pod(component, args, env, secret, mount):
        return {'metadata': {'labels': dict(labels, **{LABEL: component})}, 'spec': {
            'automountServiceAccountToken': False, 'enableServiceLinks': False,
            'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': component, 'image': image, 'imagePullPolicy': 'IfNotPresent', 'command': ['node', *args],
                            'env': env, 'securityContext': hardened,
                            'resources': {'requests': {'cpu': '20m', 'memory': '64Mi'}},
                            'volumeMounts': [{'name': 'scripts', 'mountPath': '/opt/connectors', 'readOnly': True},
                                             {'name': 'input', 'mountPath': mount, 'readOnly': True}]}],
            'volumes': [{'name': 'scripts', 'configMap': {'name': 'connector-scripts'}},
                        {'name': 'input', 'secret': {'secretName': secret, 'defaultMode': 0o440}}]}}

    up_pod = pod('upstream', ['/opt/connectors/upstream.cjs', 'serve'],
                 [{'name': 'UPSTREAM_SITES_FILE', 'value': '/run/upstream/sites.json'},
                  {'name': 'UPSTREAM_HISTORY_START_MS', 'value': str(history_start_ms)}, {'name': 'PORT', 'value': str(PORT)}],
                 'ns-upstream-sites', '/run/upstream')
    up_pod['spec']['containers'][0]['ports'] = [{'name': 'http', 'containerPort': PORT}]
    up_pod['spec']['containers'][0]['readinessProbe'] = {'httpGet': {'path': '/healthz', 'port': 'http'}, 'periodSeconds': 2}
    score_pod = pod('operator', ['/opt/connectors/score.cjs', 'poll'], [{'name': 'SCORE_INPUT_FILE', 'value': '/run/score/input.json'}],
                    'ns-connector-score', '/run/score')
    # The scorer reads tenants through the api's public port, which admits operator Pods.
    score_pod['metadata']['labels']['nightscout.org/operator-task'] = 'connector-score'
    deployment = lambda name, component, template: {
        'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': meta(name, component),
        'spec': {'replicas': 1, 'strategy': {'type': 'Recreate'},
                 'selector': {'matchLabels': {LABEL: component, **({'nightscout.org/operator-task': 'connector-score'} if name == 'connector-score' else {})}},
                 'template': template}}
    return [scripts,
            deployment(UPSTREAM, 'upstream', up_pod),
            {'apiVersion': 'v1', 'kind': 'Service', 'metadata': meta(UPSTREAM, 'upstream'),
             'spec': {'selector': {LABEL: 'upstream'}, 'ports': [{'name': 'http', 'port': PORT, 'targetPort': 'http'}]}},
            {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': meta('upstream-from-vcpool', 'network'),
             'spec': {'podSelector': {'matchLabels': {LABEL: 'upstream'}}, 'policyTypes': ['Ingress'],
                      'ingress': [{'from': [{'podSelector': {'matchLabels': {LABEL: c}}} for c in ('vcpool', 'operator')],
                                   'ports': [{'protocol': 'TCP', 'port': PORT}]}]}},
            deployment('connector-score', 'operator', score_pod)]


if __name__ == '__main__':
    import sys
    print(json.dumps({'scriptsSha256': scripts_digest(), 'count': count(int(sys.argv[1]), float(sys.argv[2]))} if len(sys.argv) == 3
                     else {'scriptsSha256': scripts_digest()}))
