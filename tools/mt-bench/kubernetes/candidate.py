"""Downstream proof for a candidate that requires private admin verification."""
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from producer_wire import ACK_BUDGET, WIRE_DIRECTORY, WIRE_NAME, valid_timeout
import primer_storage
import primer_options

ROLES = ['api', 'evaluator', 'realtime']
FIELDS = ('diagnosticSha256', 'producerBinarySha256', 'nativeCatalogueSha256')


def pins(k, c, inventory, objects):
    """Join the render, immutable candidate receipt and commissioned images."""
    selected = inventory.get('candidateContract')
    runtime = c['pins']
    overlay = objects.get('ConfigMap/provision-scripts', {}).get('data', {})
    if selected is None and 'candidate' not in runtime and 'candidate-documents.cjs' not in overlay:
        k.need(primer_options.FIELD not in c, 'PRIMER_OPTION_SOURCE_UNSUPPORTED')
        return
    k.need(selected == runtime.get('candidate') and isinstance(selected, dict), 'CANDIDATE_CONTRACT_CHANGED')
    # Qualification is provenance. A diagnostic runs on the exact admitted bytes.
    k.need(selected.get('imageConfigId') == runtime['appImageId'] and
           all(k.HEX.fullmatch(selected.get(key, '')) for key in FIELDS), 'CANDIDATE_SOURCE_IMAGE_CHANGED')
    try:
        contract = json.loads(overlay['source-contract.json'])
    except (ValueError, KeyError):
        raise k.Refused('K8S_CANDIDATE_CONTRACT_REQUIRED') from None
    k.need(contract.get('coreCommit') == runtime['pair']['core'] and contract.get('deployCommit') == runtime['pair']['deploy'] and
           contract.get('localImageId') == runtime['appImageId'] and all(contract.get(key) == selected[key] for key in FIELDS),
           'CANDIDATE_SOURCE_IMAGE_CHANGED')
    k.need((ACK_BUDGET in contract) == ('producerAckReadback' in c), 'PGSTREAM_ACK_READBACK_SCOPE')
    k.need(contract.get(primer_storage.FIELD)==c.get(primer_storage.FIELD) and
           (primer_storage.FIELD in contract)==('primerStorageReceipt' in c), 'PRIMER_STORAGE_PUBLISH_SCOPE')
    k.need(contract.get(primer_options.FIELD)==c.get(primer_options.FIELD), 'PRIMER_OPTIONS_CHANGED')
    if primer_options.FIELD in c:
        chosen = primer_options.selection(c[primer_options.FIELD], k.need)
        primer_options.require_source(chosen, contract.get(primer_options.PROTOCOL_FIELD), k.need)
    if primer_storage.FIELD in contract:
        primer_storage.verify_receipt(c[primer_storage.FIELD],c['primerStorageReceipt'])
    if ACK_BUDGET in contract:
        receipt = c['producerAckReadback']
        k.need(isinstance(receipt, dict) and valid_timeout(contract[ACK_BUDGET])
               and valid_timeout(receipt.get('sourceTimeoutMs'))
               and receipt.get('sourceContractSha256') == hashlib.sha256(overlay['source-contract.json'].encode()).hexdigest()
               and receipt.get('effectiveTimeoutMs') == contract[ACK_BUDGET]
               and all(isinstance(receipt.get(key), str) and k.HEX.fullmatch(receipt[key])
                       for key in ('sourceWireSha256', 'effectiveWireSha256'))
               and receipt.get('runId') == c['runId'] and receipt.get('namespace') == c['namespace'],
               'PGSTREAM_ACK_READBACK_CHANGED')
    k.need(re.fullmatch(r'sha256:[a-f0-9]{64}', runtime.get('postgresImageId', '')) and
           re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', runtime.get('postgresImage', '')) and
           runtime['postgresImage'] == inventory.get('images', {}).get('postgres'), 'CANDIDATE_POSTGRES_IMAGE_CHANGED')
    app_containers = {'api', 'evaluator', 'realtime', 'tenant-admin', 'pgstream', 'admin', 'ui',
                      'install-config', 'wait-stores', 'bootstrap', 'vault-kubernetes-auth', 'done', 'primer'}
    for obj in objects.values():
        spec = obj.get('spec', {}).get('template', {}).get('spec', {})
        for container in spec.get('containers', []) + spec.get('initContainers', []):
            if container['name'] in app_containers:
                k.need(container['image'] == runtime['appImage'], 'CANDIDATE_SOURCE_IMAGE_CHANGED')
            if container['name'] == 'postgres':
                k.need(container['image'] == runtime['postgresImage'], 'CANDIDATE_POSTGRES_IMAGE_CHANGED')


def images(k, c, observation):
    """Kubelet may report the selected manifest digest or its pinned config ID."""
    p = c['pins']
    if 'candidate' not in p:
        return
    app = p['appImage'].split('@sha256:', 1)[1]
    pg = p['postgresImage'].split('@sha256:', 1)[1]
    for pod in observation['pods'].values():
        for name, image in pod['imageReferences'].items():
            if image not in (p['appImage'], p['postgresImage']):
                continue
            identity = pod['containers'][name]['imageID'].rsplit('sha256:', 1)[-1]
            allowed = (app, p['appImageId'][7:]) if image == p['appImage'] else (pg, p['postgresImageId'][7:])
            k.need(identity in allowed, 'CANDIDATE_ACTUAL_IMAGE_CHANGED')


def proof(k, c, value, now=None):
    p = c['pins']
    selected = p['candidate']
    k.need(isinstance(value, dict) and value.get('version') == 1 and
           value.get('credentialBoundary') == 'admin-private-api', 'CANDIDATE_ADMIN_PROOF_REQUIRED')
    k.need(value.get('fixture') == {'namespace': c['namespace'], 'runId': c['runId']}, 'CANDIDATE_FIXTURE_CHANGED')
    k.need(value.get('diagnosticSha256') == selected['diagnosticSha256'] and
           value.get('coreCommit') == p['pair']['core'] and value.get('deployCommit') == p['pair']['deploy'],
           'CANDIDATE_SOURCE_IMAGE_CHANGED')
    k.need(k.HEX.fullmatch(value.get('nativeSelectionSha256', '')) and
           k.HEX.fullmatch(value.get('selectionSha256', '')), 'CANDIDATE_GENERATION_CHANGED')
    native = value.get('nativeSource')
    k.need(isinstance(native, dict) and set(native) == {'system_id', 'timeline', 'database', 'slot'} and
           re.fullmatch(r'[0-9]{1,20}', native.get('system_id', '')) and type(native.get('timeline')) is int and
           native['timeline'] > 0 and native.get('database') == 'nightscout_compose_test' and
           native.get('slot') == 'nsdemo_pgstream' and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value.get('nativeGeneration', '')),
           'CANDIDATE_NATIVE_SOURCE_CHANGED')
    roster = value.get('roles')
    k.need(isinstance(roster, list) and all(isinstance(row, dict) for row in roster) and
           [row.get('role') for row in roster] == ROLES, 'CANDIDATE_VERIFICATION_CHANGED')
    for row in roster:
        k.need(k.HEX.fullmatch(row.get('generation', '')), 'CANDIDATE_GENERATION_CHANGED')
        if now is not None:
            k.need(k.timestamp(row.get('expiresAt', '')) > now, 'CANDIDATE_VERIFICATION_EXPIRED')


def observe(k, d, c, objects, client):
    file = d / 'candidate-verification.json'
    k.need('candidate' in c['pins'] and not file.exists(), 'CANDIDATE_PROOF_CAPTURE_REQUIRED')
    before = k.observe(c, objects, client, k.active_baseline(d))
    if 'producerAckReadback' in c:
        name, container = verify_ack_owner(k, c, before)
        wire = WIRE_DIRECTORY + '/' + WIRE_NAME
        digest = client.call(['exec', name, '-c', container, '--', 'sha256sum', wire], read=False)
        expected = [c['producerAckReadback']['effectiveWireSha256'].encode(), wire.encode()]
        k.need(digest.split() == expected, 'PGSTREAM_ACK_WIRE_CHANGED')
    primer = [p for p in before['pods'].values() if p['workload'] == 'Job/primer' and p['containers'].get('done', {}).get('ready')]
    k.need(len(primer) == 1, 'CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED')
    pod = primer[0]
    raw = client.call(['exec', pod['name'], '-c', 'done', '--', 'cat', '/run/ns-primer/verified.json'], read=False)
    try:
        value = json.loads(raw)
    except ValueError:
        raise k.Refused('K8S_CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED') from None
    checked_at = time.time()
    proof(k, c, value, now=checked_at)
    source = k.sql(d, c, objects, '''SELECT s.system_identifier::text,c.timeline_id::integer,current_database(),
      EXISTS(SELECT 1 FROM pg_catalog.pg_replication_slots WHERE slot_name='nsdemo_pgstream' AND slot_type='logical' AND database=current_database())
      FROM pg_catalog.pg_control_system() s CROSS JOIN pg_catalog.pg_control_checkpoint() c;''', client).strip().split('	')
    native = value['nativeSource']
    k.need(source == [native['system_id'], str(native['timeline']), native['database'], 't'], 'CANDIDATE_NATIVE_SOURCE_CHANGED')
    k.observe(c, objects, client, before)
    row = {'version': 1, 'proof': value, 'capturedAt': datetime.fromtimestamp(checked_at, timezone.utc).isoformat().replace('+00:00', 'Z'),
           'runSha256': k.digest(d / 'run.json'), 'namespaceUid': before['namespace']['uid'], 'primerPodUid': pod['uid'],
           'primerContainerId': pod['containers']['done']['containerID'], 'adminServiceUid': before['objects']['Service/admin']['uid']}
    k.write(file, row)
    return row


def require(k, d, c):
    if 'candidate' not in c['pins']:
        return
    file = d / 'candidate-verification.json'
    k.need(file.is_file(), 'CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED')
    value = k.document(file)
    baseline = k.active_baseline(d)
    verify_ack_owner(k, c, baseline)
    prim = [p for p in baseline['pods'].values() if p['workload'] == 'Job/primer']
    k.need(len(prim) == 1 and value.get('namespaceUid') == baseline['namespace']['uid'] and
           value.get('runSha256') == k.digest(d / 'run.json') and value.get('primerPodUid') == prim[0]['uid'] and
           value.get('primerContainerId') == prim[0]['containers']['done']['containerID'] and
           value.get('adminServiceUid') == baseline['objects']['Service/admin']['uid'], 'CANDIDATE_FIXTURE_CHANGED')
    proof(k, c, value.get('proof'), now=k.timestamp(value.get('capturedAt', '')))


def verify_ack_owner(k, c, observed):
    receipt = c.get('producerAckReadback')
    if receipt is None:
        return
    name, container = k.selected_pod(c, observed, 'pgstream')
    pod = observed['pods'][name]
    k.need(receipt['namespaceUid'] == observed['namespace']['uid'] and receipt['podUid'] == pod['uid']
           and receipt['containerId'] == pod['containers'][container]['containerID'], 'PGSTREAM_ACK_OWNER_CHANGED')
    return name, container
