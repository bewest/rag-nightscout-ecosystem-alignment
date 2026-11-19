"""Bounded lossless synthetic roster transport; no actor or workload replay."""
import base64
import copy
import gzip
import hashlib
import json

import kube_adapter as k
import workload_runtime

PRIVATE = 'fixture-data-v1'
CODECS = ('raw-v1', 'gzip-v1', PRIVATE)
MAX_TENANTS = 10000
MAX_RAW_BYTES = 4 * 1024**2
MAX_GZIP_BYTES = 600 * 1024
MIN_MEMORY_BYTES = 64 * 1024**2


def fixture_data(c, job, secret, receipt):
    pod = job['spec']['template']['spec']
    main, exporter = pod['containers']
    script = k.HERE / 'native-fixture-data.cjs'
    secret['stringData'][script.name] = script.read_text()
    count = workload_runtime.driver_count(c, k.need)
    meta = {'codec': PRIVATE, 'fixtureTenants': c['tenants'], 'tenants': count,
            'sha256': receipt['rosterSha256']}
    secret['stringData']['fixture-data.json'] = json.dumps(meta)
    for entry in main['env']:
        if entry['name'] == 'TENANTS_FILE':
            entry['value'] = '/roster/tenants.json'
    main['command'][2] = 'while [ ! -f /roster/tenants.json ]; do sleep 0.1; done\n' + main['command'][2]
    pod['volumes'].append({'name': 'roster', 'emptyDir': {}})
    main['volumeMounts'].append({'name': 'roster', 'mountPath': '/roster', 'readOnly': True})
    exporter['volumeMounts'].append({'name': 'roster', 'mountPath': '/roster'})
    exporter.setdefault('env', []).append({'name': 'NS_ROSTER_POD_UID', 'valueFrom': {
        'fieldRef': {'fieldPath': 'metadata.uid'}}})
    receipt.update(inputTransport=meta, jobSha256=k.hashed(job))
    return job, secret, receipt


def decorate(c, job, secret, receipt, *, codec, resources):
    k.need(codec in CODECS, 'NATIVE_LOAD_INPUT_CODEC')
    if codec == PRIVATE:
        return fixture_data(c, job, secret, receipt)
    raw = secret['stringData']['tenants.json'].encode()
    transport = {'codec': codec, 'bytes': len(raw), 'tenants': c['tenants'],
                 'sha256': hashlib.sha256(raw).hexdigest()}
    receipt['inputTransport'] = transport
    if codec == 'raw-v1':
        return job, secret, receipt
    k.need(type(c['tenants']) is int and 1 <= c['tenants'] <= MAX_TENANTS,
           'NATIVE_LOAD_INPUT_TENANT_BOUND', 'UNMEASURED')
    k.need(0 < len(raw) <= MAX_RAW_BYTES, 'NATIVE_LOAD_INPUT_RAW_BOUND', 'UNMEASURED')
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    k.need(0 < len(packed) <= MAX_GZIP_BYTES, 'NATIVE_LOAD_INPUT_GZIP_BOUND', 'UNMEASURED')
    k.need(isinstance(resources, dict), 'NATIVE_LOAD_INPUT_RESOURCES_REQUIRED', 'UNMEASURED')
    k.resource_budget.validate_container({'resources': resources}, k.resource_accounting(c), k.need)
    request = resources['requests']
    k.need(k.resource_budget.quantity(request['memory'], False, k.need) >= MIN_MEMORY_BYTES
           and k.resource_budget.quantity(request['ephemeral-storage'], False, k.need) >= MAX_RAW_BYTES,
           'NATIVE_LOAD_INPUT_UNPACK_BUDGET', 'UNMEASURED')
    transport.update(gzipBytes=len(packed), gzipSha256=hashlib.sha256(packed).hexdigest())
    secret['stringData'].pop('tenants.json')
    secret['data'] = {'tenants.json.gz': base64.b64encode(packed).decode('ascii')}
    secret['stringData']['tenants.digest.json'] = json.dumps(transport, separators=(',', ':'))
    unpacker = k.HERE / 'native-input-unpack.cjs'
    secret['stringData'][unpacker.name] = unpacker.read_text()
    pod = job['spec']['template']['spec']
    main = pod['containers'][0]
    for row in main['env']:
        if row['name'] == 'TENANTS_FILE':
            row['value'] = '/roster/tenants.json'
    main['volumeMounts'].append({'name': 'roster', 'mountPath': '/roster', 'readOnly': True})
    pod['volumes'].append({'name': 'roster', 'emptyDir': {'sizeLimit': str(MAX_RAW_BYTES)}})
    # A separate, tokenless init phase reuses the explicitly selected exporter
    # envelope. Existing Pod peak accounting includes it before quota/fit.
    pod.setdefault('initContainers', []).append({
        'name': 'unpack-roster', 'image': c['pins']['appImage'], 'imagePullPolicy': 'IfNotPresent',
        'command': ['node', '/inputs/native-input-unpack.cjs', '/inputs', '/roster', str(c['tenants'])],
        'resources': copy.deepcopy(resources), 'securityContext': copy.deepcopy(main['securityContext']),
        'volumeMounts': [{'name': 'inputs', 'mountPath': '/inputs', 'readOnly': True},
                         {'name': 'roster', 'mountPath': '/roster'}]})
    receipt.update(inputUnpackerSha256=k.digest(unpacker), jobSha256=k.hashed(job))
    return job, secret, receipt
