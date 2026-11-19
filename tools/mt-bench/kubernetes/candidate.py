"""Downstream proof for a candidate that requires private admin verification."""
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from producer_wire import ACK_BUDGET, WIRE_DIRECTORY, WIRE_NAME, valid_timeout
import primer_storage
import primer_options
import population_ceiling

ROLES = ['api', 'evaluator', 'realtime']
FIELDS = ('diagnosticSha256', 'producerBinarySha256', 'nativeCatalogueSha256')
# v4 extends source-owned role digests with presentation catalogues and tenant
# floor proof authority. Its admin client still emits the same closed version-1
# startup receipt; no tenant backfill or structural verification runs here.
STARTUP_PROTOCOLS = ('startup-v2', 'startup-v3', 'startup-v4')
NATIVE_RECEIPT_PROTOCOLS = ('startup-v3', 'startup-v4')
VERIFICATION_JOB = 'Job/verification'


def verified_serving(c):
    return c['pins'].get('candidate', {}).get('verificationJob') == 'verification'


def job_condition(job):
    terminal = {row['type'] for row in job.get('status', {}).get('conditions', [])
                if row.get('status') == 'True'}
    if terminal & {'Failed', 'FailureTarget'}:
        return 'Failed'
    if 'Complete' in terminal:
        return 'Complete'
    return None


def verification_log(k, c, raw):
    try:
        value = json.loads(raw)
    except ValueError:
        raise k.Refused('K8S_CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED') from None
    k.need(isinstance(value, dict) and value.get('status') == 'verified', 'CANDIDATE_ADMIN_PROOF_REQUIRED')
    proof(k, c, value)
    return value


def pins(k, c, inventory, objects):
    """Join the render, immutable candidate receipt and commissioned images."""
    selected = inventory.get('candidateContract')
    runtime = c['pins']
    overlay = objects.get('ConfigMap/provision-scripts', {}).get('data', {})
    split = verified_serving(c)
    k.need(split == (VERIFICATION_JOB in objects), 'CANDIDATE_VERIFICATION_JOB_CHANGED')
    if selected is None and 'candidate' not in runtime and 'candidate-documents.cjs' not in overlay:
        k.need(primer_options.FIELD not in c, 'PRIMER_OPTION_SOURCE_UNSUPPORTED')
        k.need(population_ceiling.FIELD not in c, 'POPULATION_SOURCE_UNSUPPORTED')
        return
    if split:
        k.need(selected is None and objects[VERIFICATION_JOB]['spec'].get('suspend') is True,
               'CANDIDATE_CONTRACT_CHANGED')
        selected = runtime['candidate']
    k.need(selected == runtime.get('candidate') and isinstance(selected, dict), 'CANDIDATE_CONTRACT_CHANGED')
    # Identity is the image digest. Source commits and helper hashes are
    # recorded provenance, not per-run refusals.
    k.need(selected.get('imageConfigId') == runtime['appImageId'], 'CANDIDATE_SOURCE_IMAGE_CHANGED')
    try:
        contract = json.loads(overlay['source-contract.json'])
    except (ValueError, KeyError):
        raise k.Refused('K8S_CANDIDATE_CONTRACT_REQUIRED') from None
    if split:
        k.need(contract == {'coreCommit':runtime['pair']['core'], 'deployCommit':runtime['pair']['deploy']} and
               selected.get('platformVerification') in STARTUP_PROTOCOLS, 'CANDIDATE_PLATFORM_VERIFICATION_CHANGED')
        contract = selected
    else:
        k.need(selected.get('platformVerification') in (None, *STARTUP_PROTOCOLS) and
               selected.get('platformVerification') == contract.get('platformVerification'),
               'CANDIDATE_PLATFORM_VERIFICATION_CHANGED')
    k.need((ACK_BUDGET in contract) == ('producerAckReadback' in c), 'PGSTREAM_ACK_READBACK_SCOPE')
    k.need(contract.get(primer_storage.FIELD)==c.get(primer_storage.FIELD) and
           (primer_storage.FIELD in contract)==('primerStorageReceipt' in c), 'PRIMER_STORAGE_PUBLISH_SCOPE')
    k.need(contract.get(primer_options.FIELD)==c.get(primer_options.FIELD), 'PRIMER_OPTIONS_CHANGED')
    k.need(contract.get(population_ceiling.FIELD)==c.get(population_ceiling.FIELD), 'POPULATION_CEILING_CHANGED')
    if population_ceiling.FIELD in c:
        k.need(contract.get(population_ceiling.PROTOCOL_FIELD)==population_ceiling.PROTOCOL and
               contract.get('populationSource',{}).get(population_ceiling.FIELD)==c[population_ceiling.FIELD] and
               contract.get('populationSource',{}).get('protocol')==population_ceiling.PROTOCOL and
               contract.get('populationSource',{}).get('overSeedRefused') is True and
               contract.get('populationSource',{}).get('protocolRefused') is True and
               contract.get('populationSource',{}).get('sourceFilesSha256')=={
                   name:contract.get('sourceFilesSha256',{}).get(name) for name in population_ceiling.SOURCE_FILES},
               'POPULATION_SOURCE_UNSUPPORTED')
    if primer_options.FIELD in c:
        chosen = primer_options.selection(c[primer_options.FIELD], k.need)
        primer_options.require_source(chosen, contract.get(primer_options.PROTOCOL_FIELD), k.need)
    if primer_storage.FIELD in contract:
        primer_storage.verify_receipt(c[primer_storage.FIELD],c['primerStorageReceipt'])
    if ACK_BUDGET in contract:
        receipt = c['producerAckReadback']
        k.need(isinstance(receipt, dict) and valid_timeout(contract[ACK_BUDGET])
               and valid_timeout(receipt.get('sourceTimeoutMs'))
               and receipt.get('sourceContractSha256') == (selected['sourceContractSha256'] if split else hashlib.sha256(overlay['source-contract.json'].encode()).hexdigest())
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
    k.need(selected.get('platformVerification') in (None, *STARTUP_PROTOCOLS),
           'CANDIDATE_PLATFORM_VERIFICATION_CHANGED')
    k.need(isinstance(value, dict) and value.get('version') == 1 and
           value.get('credentialBoundary') == 'admin-private-api', 'CANDIDATE_ADMIN_PROOF_REQUIRED')
    if verified_serving(c):
        k.need(value.get('status') == 'verified', 'CANDIDATE_ADMIN_PROOF_REQUIRED')
    k.need(value.get('fixture') == {'namespace': c['namespace'], 'runId': c['runId']}, 'CANDIDATE_FIXTURE_CHANGED')
    k.need(k.HEX.fullmatch(value.get('nativeSelectionSha256', '')) and
           k.HEX.fullmatch(value.get('selectionSha256', '')), 'CANDIDATE_GENERATION_CHANGED')
    native = value.get('nativeSource')
    k.need(isinstance(native, dict) and set(native) == {'system_id', 'timeline', 'database', 'slot'} and
           re.fullmatch(r'[0-9]{1,20}', native.get('system_id', '')) and type(native.get('timeline')) is int and
           native['timeline'] > 0 and native.get('database') == 'nightscout_compose_test' and
           native.get('slot') == 'nsdemo_pgstream' and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value.get('nativeGeneration', '')),
           'CANDIDATE_NATIVE_SOURCE_CHANGED')
    roster = value.get('roles')
    # The serving roles this run uses must be verified; the platform may verify
    # more roles (for example vcpool) without changing the run.
    names = [row.get('role') for row in roster] if isinstance(roster, list) else []
    k.need(isinstance(roster, list) and all(isinstance(row, dict) for row in roster) and
           len(names) == len(set(names)) and set(ROLES) <= set(names), 'CANDIDATE_VERIFICATION_CHANGED')
    for row in roster:
        k.need(k.HEX.fullmatch(row.get('generation', '')), 'CANDIDATE_GENERATION_CHANGED')
        startup = selected.get('platformVerification') in STARTUP_PROTOCOLS
        if startup:
            k.need(set(row) == {'role', 'generation'}, 'CANDIDATE_VERIFICATION_CHANGED')
        elif now is not None:
            k.need(k.timestamp(row.get('expiresAt', '')) > now, 'CANDIDATE_VERIFICATION_EXPIRED')


def observe(k, d, c, objects, client):
    file = d / 'candidate-verification.json'
    k.need('candidate' in c['pins'] and not file.exists(), 'CANDIDATE_PROOF_CAPTURE_REQUIRED')
    baseline = k.active_baseline(d)
    reused = verified_serving(c) and c.get('verificationProof') is not None
    before = baseline if reused else k.observe(c, objects, client, baseline)
    if 'producerAckReadback' in c:
        name, container = verify_ack_owner(k, c, before)
        wire = WIRE_DIRECTORY + '/' + WIRE_NAME
        digest = client.call(['exec', name, '-c', container, '--', 'sha256sum', wire], read=False)
        expected = [c['producerAckReadback']['effectiveWireSha256'].encode(), wire.encode()]
        k.need(digest.split() == expected, 'PGSTREAM_ACK_WIRE_CHANGED')
    split = verified_serving(c)
    workload = VERIFICATION_JOB if split else 'Job/primer'
    witnesses = [p for p in before['pods'].values() if p['workload'] == workload]
    k.need(len(witnesses) == 1, 'CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED')
    pod = witnesses[0]
    if split:
        done = pod['containers']['done']
        k.need((done.get('state') or {}).get('terminated', {}).get('exitCode') == 0,
               'CANDIDATE_ADMIN_PROOF_REQUIRED')
        captured = c.get('verificationProof')
        if captured is None:
            job = client.get('Job', 'verification')
            k.need(job['metadata']['uid'] == before['objects'][workload]['uid'] and job_condition(job) == 'Complete',
                   'CANDIDATE_ADMIN_PROOF_REQUIRED')
            raw = client.call(['logs', pod['name'], '-c', 'done', '--limit-bytes=65536'], read=False)
            value = verification_log(k, c, raw)
        else:
            k.need(captured['jobUid'] == before['objects'][workload]['uid'] and captured['podUid'] == pod['uid']
                   and captured['containerId'] == done['containerID'], 'CANDIDATE_FIXTURE_CHANGED')
            value = captured['proof']
    else:
        k.need(pod['containers'].get('done', {}).get('ready'), 'CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED')
        raw = client.call(['exec', pod['name'], '-c', 'done', '--', 'cat', '/run/ns-primer/verified.json'], read=False)
        try:
            value = json.loads(raw)
        except ValueError:
            raise k.Refused('K8S_CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED') from None
    checked_at = time.time()
    proof(k, c, value, now=checked_at)
    population_readback=population_ceiling.capture(k,c,before,client)
    source = k.sql(d, c, objects, '''SELECT s.system_identifier::text,c.timeline_id::integer,current_database(),
      EXISTS(SELECT 1 FROM pg_catalog.pg_replication_slots WHERE slot_name='nsdemo_pgstream' AND slot_type='logical' AND database=current_database())
      FROM pg_catalog.pg_control_system() s CROSS JOIN pg_catalog.pg_control_checkpoint() c;''', client).strip().split('	')
    native = value['nativeSource']
    k.need(source == [native['system_id'], str(native['timeline']), native['database'], 't'], 'CANDIDATE_NATIVE_SOURCE_CHANGED')
    if not reused:
        k.observe(c, objects, client, before)
    row = {'version': 1, 'proof': value, 'capturedAt': datetime.fromtimestamp(checked_at, timezone.utc).isoformat().replace('+00:00', 'Z'),
           'runSha256': k.digest(d / 'run.json'), 'namespaceUid': before['namespace']['uid'], 'adminServiceUid': before['objects']['Service/admin']['uid']}
    if split:
        row.update(verificationJobUid=before['objects'][workload]['uid'], verificationPodUid=pod['uid'],
                   verificationContainerId=pod['containers']['done']['containerID'])
    else:
        row.update(primerPodUid=pod['uid'], primerContainerId=pod['containers']['done']['containerID'])
    if population_readback is not None:row['populationCeilingReadback']=population_readback
    k.write(file, row)
    return row


def require(k, d, c):
    if 'candidate' not in c['pins']:
        return
    file = d / 'candidate-verification.json'
    k.need(file.is_file(), 'CANDIDATE_ADMIN_PROOF_REQUIRED', 'UNMEASURED')
    value = k.document(file)
    baseline = k.active_baseline(d)
    population_ceiling.verify_capture(k,c,baseline,value.get('populationCeilingReadback'))
    verify_ack_owner(k, c, baseline)
    split = verified_serving(c)
    workload = VERIFICATION_JOB if split else 'Job/primer'
    prefix = 'verification' if split else 'primer'
    witnesses = [p for p in baseline['pods'].values() if p['workload'] == workload]
    if not split and not witnesses and baseline.get('completedPrimer'):
        initial = k.document(d/'observation.initial.json')
        witnesses = [p for p in initial['pods'].values() if p['workload'] == workload and
                     p['uid'] == baseline['completedPrimer']['uid']]
    if split:
        k.need(value.get('verificationJobUid') == baseline['objects'][workload]['uid'], 'CANDIDATE_FIXTURE_CHANGED')
    k.need(len(witnesses) == 1 and value.get('namespaceUid') == baseline['namespace']['uid'] and
           value.get('runSha256') == k.digest(d / 'run.json') and value.get(prefix+'PodUid') == witnesses[0]['uid'] and
           value.get(prefix+'ContainerId') == witnesses[0]['containers']['done']['containerID'] and
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
