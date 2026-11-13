"""Private read-only intake for the opt-in connection admission instrument.

This never grants a ticket, retires credit, starts a process, or certifies native
acceptance. The default joined adapter and its selector remain separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

KIND = 'm7-tagged-admission-observation-v1'
CORE = 'd0036890d0623ae79f14bfa71e7226c0fa122a29'
DEPLOY = 'd831c372b39ac19aff4271ecc5e2b1639d176448'


def need(value, code):
    if not value:
        raise ValueError('M7_TAGGED_' + code)


def sha(value):
    # connection-budget.js uses JSON.stringify in insertion order, not sorted
    # canonical JSON. Input must be parsed directly from the captured plan.
    def portable(item):
        if item is None or type(item) is bool: return True
        if type(item) is int: return abs(item) <= 9007199254740991
        if type(item) is str: return item.isascii()
        if type(item) is list: return all(portable(x) for x in item)
        if type(item) is dict: return all(type(k) is str and k.isascii() and not k.isdigit() and portable(v) for k,v in item.items())
        return False
    need(portable(value), 'PLAN_JSON_PARITY_DOMAIN')
    return hashlib.sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def hexid(value, length):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{' + str(length) + '}', value) is not None


def tag(incarnation, capability):
    return 'nscb:' + incarnation + ':' + hashlib.sha256(capability.encode()).hexdigest()[:16]


CONTROL = 'lifecycle-operator'
UUID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')

# Closed source/model interface for common control-recovery contract version 1.
CLASSES = ('lifecycle-operator', 'restore-commissioner', 'realtime-recovery')
IDENTIFIER = re.compile(r'[a-z][a-z0-9_]{0,62}')

def exact(value, keys):
    return type(value) is dict and set(value) == set(keys)

def integer(value, low, high):
    return type(value) is int and low <= value <= high

def principal3(value):
    need(exact(value, ('role','roleOid','database','databaseOid'))
         and all(type(value[k]) is str and IDENTIFIER.fullmatch(value[k]) for k in ('role','database'))
         and all(type(value[k]) is str and re.fullmatch(r'[1-9][0-9]{0,9}',value[k]) and int(value[k]) <= 4294967295 for k in ('roleOid','databaseOid')), 'COMMON_PRINCIPAL')

def common_custody(original, expected, service):
    need(exact(original, ('cid','startedAt','project','workingDirectory','service','imageId','source'))
         and hexid(original['cid'],64) and type(original['startedAt']) is str and 0 < len(original['startedAt']) <= 100
         and type(original['service']) is str and original['service'] == service
         and type(original['project']) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,62}',original['project'])
         and type(original['workingDirectory']) is str and original['workingDirectory'].startswith('/')
         and type(original['imageId']) is str and re.fullmatch(r'sha256:[a-f0-9]{64}',original['imageId'])
         and all(type(original[k]) is str and original[k] == expected[k] for k in ('imageId','project','workingDirectory'))
         and exact(original['source'], ('coreCommit','deployCommit')) and all(hexid(v,40) for v in original['source'].values()) and original['source'] == expected['source'], 'COMMON_CONTAINER_CUSTODY')

def common_leases(plan, ledger, expected=None):
    """Declared CBD contract. No dispatch, retirement or inferred cleanup."""
    need(type(plan.get('version')) is int and plan['version'] == 2
         and type(plan.get('lifecycleOperator')) is dict and type(plan['lifecycleOperator'].get('version')) is int
         and plan['lifecycleOperator']['version'] == 2, 'COMMON_PLAN_VERSION')
    need(exact(ledger, ('version','planSha256','resourceEpoch','slots','controlLeases'))
         and type(ledger['version']) is int and ledger['version'] == 3, 'COMMON_LEDGER_VERSION')
    need(hexid(plan.get('sha256'),64) and plan['sha256'] == sha({k:v for k,v in plan.items() if k != 'sha256'})
         and ledger['planSha256'] == plan['sha256'] and ledger['resourceEpoch'] == [plan['resource']['systemIdentifier'],plan['resource']['postmasterStartedAt']]
         and all(type(v) is str and v for v in ledger['resourceEpoch']), 'COMMON_PLAN_IDENTITY')
    if expected is not None:
        need(plan['source'] == expected['source'] and plan['sha256'] == expected['planSha256'], 'COMMON_EXPECTED_IDENTITY')
    recovery = plan.get('controlRecovery')
    need(exact(recovery, ('version','classes')) and type(recovery['version']) is int and recovery['version'] == 1
         and exact(recovery['classes'], CLASSES), 'COMMON_CLASSES')
    database = plan.get('workerDatabase')
    need(exact(database, ('database','databaseOid')) and type(database['database']) is str and IDENTIFIER.fullmatch(database['database'])
         and type(database['databaseOid']) is str and re.fullmatch(r'[1-9][0-9]{0,9}',database['databaseOid']) and int(database['databaseOid']) <= 4294967295, 'COMMON_DATABASE')
    need(type(plan['resource'].get('allowances')) is dict and type(plan['resource']['allowances'].get('controlRecovery')) is int
         and plan['resource']['allowances']['controlRecovery'] == 2, 'COMMON_ALLOWANCE')
    for name in CLASSES:
        entry = recovery['classes'][name]
        need(exact(entry, ('principal',)), 'COMMON_CLASS')
        principal3(entry['principal'])
        need(all(entry['principal'][k] == database[k] for k in database), 'COMMON_DATABASE')
    op = recovery['classes'][CONTROL]['principal']; ddl = recovery['classes']['restore-commissioner']['principal']
    need(op['role'] != ddl['role'] and op['roleOid'] != ddl['roleOid'], 'COMMON_COMMISSION_PRINCIPAL')
    slots = plan['slots'];need(type(slots) is list and len(slots) <= 10000, 'COMMON_SLOTS')
    names = [s.get('processInstanceId') for s in slots if type(s) is dict]
    need(len(names) == len(slots) and all(type(n) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,62}', n) and n not in CLASSES for n in names)
         and len(set(names)) == len(names) and exact(ledger['slots'], names), 'COMMON_SLOTS')
    ids, nonces, tags = set(), set(), set()
    def identity(row, required):
        inc, nonce = row.get('incarnation'), row.get('nonce')
        need(hexid(inc,32) and hexid(nonce,32) and inc != nonce and inc not in ids and nonce not in nonces, 'COMMON_INCARNATION')
        need(type(row.get('tags')) is list and all(type(t) is str for t in row['tags'])
             and len(row['tags']) == len(required) and set(row['tags']) == required and not tags.intersection(required), 'COMMON_TAGS')
        ids.add(inc);nonces.add(nonce);tags.update(required)
    total = 0
    for slot in slots:
        rows = ledger['slots'][slot['processInstanceId']]
        need(type(rows) is list, 'COMMON_WORKER_ROWS');total += len(rows)
        need(total <= 4096 and integer(slot.get('maximumOutstandingGenerations'),1,4096), 'COMMON_WORKER_BOUND')
        caps = slot.get('capabilities');need(type(caps) is dict and len(caps) > 0 and all(type(k) is str for k in caps), 'COMMON_CAPABILITIES')
        for row in rows:
            need(exact(row, ('incarnation','nonce','tags','container','state','retired')) and row['state'] in ('ISSUED','RETIRED')
                 and type(row['retired']) is bool and row['retired'] == (row['state'] == 'RETIRED'), 'COMMON_WORKER_ROW')
            need(hexid(row['incarnation'],32), 'COMMON_INCARNATION')
            identity(row, {tag(row['incarnation'],k) for k in caps})
            need(row['state'] != 'RETIRED' or row['container'] is not None, 'COMMON_WORKER_CONTAINER')
            if row['container'] is not None:common_custody(row['container'],expected or row['container'],slot['processInstanceId'])
        need(sum(r['state'] != 'RETIRED' for r in rows) <= slot['maximumOutstandingGenerations'], 'COMMON_WORKER_BOUND')
    rows = ledger['controlLeases'];need(type(rows) is list and len(rows) <= 4096, 'COMMON_HISTORY')
    for row in rows:
        need(exact(row, ('state','class','credits','incarnation','nonce','tags','intentSha256','planSha256','source','principal','container','stopped'))
             and type(row['class']) is str and row['class'] in CLASSES and type(row['state']) is str and row['state'] in ('ISSUED','BOUND','UNKNOWN','CLOSED')
             and type(row['credits']) is int and row['credits'] == 1 and hexid(row['intentSha256'],64), 'COMMON_ROW')
        need(hexid(row['incarnation'],32), 'COMMON_INCARNATION')
        identity(row, {tag(row['incarnation'],row['class'])})
        principal3(row['principal'])
        need(type(row['planSha256']) is str and row['planSha256'] == plan['sha256']
             and exact(row['source'], ('coreCommit','deployCommit')) and row['source'] == plan['source']
             and row['principal'] == recovery['classes'][row['class']]['principal'], 'COMMON_IDENTITY')
        need(row['state'] == 'UNKNOWN' or (row['container'] is None if row['state'] == 'ISSUED' else row['container'] is not None), 'COMMON_BINDING')
        if row['container'] is not None:
            common_custody(row['container'],expected or row['container'],row['class'])
        proof = row['stopped']
        need(proof is None or (row['state'] == 'UNKNOWN' and row['container'] is not None
             and exact(proof, ('container','resourceEpoch','noFutureDispatch')) and proof['container'] == row['container']
             and proof['resourceEpoch'] == ledger['resourceEpoch'] and proof['noFutureDispatch'] is True), 'COMMON_STOPPED')
    active = sum(r['state'] in ('ISSUED','BOUND') for r in rows)
    need(sum(r['state'] != 'CLOSED' for r in rows) <= 2 and active <= 1, 'COMMON_CAPACITY')
    need(not active or all(r['stopped'] is not None and r['class'] != 'restore-commissioner' for r in rows if r['state'] == 'UNKNOWN'), 'COMMON_PREDECESSOR')
    return rows


def envelope(expected, plan, raw):
    """Check declared envelope2 metadata; counts remain original evidence only."""
    need(type(raw) is dict and type(raw.get('version')) is int and raw['version'] == 2
         and raw.get('kind') in ('controlled-connection-observation','controlled-native-stored-counts')
         and raw.get('visibility') == 'PG_STAT_AUTHENTICATED_ONLY', 'COMMON_ENVELOPE')
    need(raw.get('source') == expected['source'] and raw.get('planSha256') == expected['planSha256']
         and raw.get('expected') == {k:expected[k] for k in ('source','project','workingDirectory','imageId')}, 'COMMON_ENVELOPE_IDENTITY')
    brackets = raw.get('hostMonotonic')
    need(exact(brackets, ('startedNs','finishedNs')) and all(type(v) is str and re.fullmatch(r'[0-9]{1,24}',v) for v in brackets.values())
         and int(brackets['finishedNs']) >= int(brackets['startedNs']), 'COMMON_ENVELOPE_BRACKETS')
    common_leases(plan,raw.get('ledger'),expected)
    return {k:raw[k] for k in ('resource','tags','occupancy')}


def control_leases(plan, ledger):
    """Exact proposed f098 v2 protocol. No migration or inferred zero credit."""
    if plan.get('version') == 2:
        return common_leases(plan, ledger)
    version = ledger.get('version')
    need(type(version) is int and version in (1, 2), 'LEDGER_VERSION')
    operator = plan.get('lifecycleOperator')
    if 'lifecycleOperator' not in plan:
        need(version == 1 and 'controlLeases' not in ledger, 'CONTROL_LEDGER_VERSION')
        return None
    need(version == 2 and isinstance(operator, dict) and set(operator) == {'version','principal','tenants','placement','files'}
         and type(operator['version']) is int and operator['version'] == 1, 'CONTROL_PLAN')
    tenants = operator['tenants']
    need(isinstance(tenants, list) and 0 < len(tenants) <= 10000 and all(isinstance(x,str) and UUID.fullmatch(x) and x != '00000000-0000-0000-0000-000000000000' for x in tenants)
         and len(set(tenants)) == len(tenants), 'CONTROL_TENANTS')
    principal = operator['principal']
    need(isinstance(principal, dict) and set(principal) == {'role','roleOid','database','databaseOid'}
         and all(isinstance(principal[k],str) and 0 < len(principal[k]) <= 63 and principal[k].isascii() for k in ('role','database'))
         and all(isinstance(principal[k],str) and re.fullmatch(r'[1-9][0-9]{0,9}',principal[k]) and int(principal[k]) <= 4294967295 for k in ('roleOid','databaseOid')), 'CONTROL_PRINCIPAL')
    files = operator['files']
    need(type(operator['placement']) is bool and isinstance(files,dict)
         and set(files) == {'env.json','config.json', *(['placement.json'] if operator['placement'] else [])}
         and all(hexid(v,64) for v in files.values()), 'CONTROL_FILES')
    need(type(plan['resource'].get('allowances',{}).get('controlRecovery')) is int
         and plan['resource']['allowances']['controlRecovery'] >= 1, 'CONTROL_ALLOWANCE')
    rows = ledger.get('controlLeases')
    need(isinstance(rows,list) and len(rows) <= 4096, 'CONTROL_HISTORY_BOUND')
    incarnations, nonces, all_tags = set(), set(), set()
    slots = {row['processInstanceId']:row for row in plan['slots']}
    for sid, generations in ledger['slots'].items():
        need(isinstance(generations,list), 'WORKER_LEDGER')
        for row in generations:
            inc, nonce = row.get('incarnation'),row.get('nonce')
            required = {tag(inc, name) for name in slots[sid]['capabilities']} if hexid(inc,32) else set()
            need(row.get('state') in ('ISSUED','RETIRED') and hexid(inc,32) and hexid(nonce,32)
                 and inc not in incarnations and nonce not in nonces and isinstance(row.get('tags'),list)
                 and len(row['tags']) == len(required) and set(row['tags']) == required, 'WORKER_LEDGER')
            incarnations.add(inc);nonces.add(nonce);all_tags.update(required)
    for row in rows:
        need(isinstance(row,dict) and row.get('state') in ('ISSUED','BOUND','UNKNOWN','CLOSED'), 'CONTROL_STATE')
        state = row['state']
        fields = {'state','credits','incarnation','nonce','tags','intent','intentSha256','planSha256','source','container'}
        need(set(row) == fields | ({'outcome'} if state in ('UNKNOWN','CLOSED') else set()), 'CONTROL_FIELDS')
        inc, nonce = row['incarnation'],row['nonce']
        need(hexid(inc,32) and hexid(nonce,32) and inc not in incarnations and nonce not in nonces, 'CONTROL_INCARNATION')
        name = tag(inc,CONTROL)
        need(row['tags'] == [name] and name not in all_tags, 'CONTROL_TAG')
        need(type(row['credits']) is int and row['credits'] == 1 and row['source'] == plan['source']
             and row['planSha256'] == plan['sha256'], 'CONTROL_IDENTITY')
        intent = row['intent']
        need(isinstance(intent,dict) and intent.get('command') in ('inspect','resume','clear-operations'), 'CONTROL_INTENT')
        need(set(intent) == {'version','command','tenant', *(['claimId'] if intent['command'] == 'resume' else [])}
             and type(intent['version']) is int and intent['version'] == 1 and intent['tenant'] in tenants
             and (intent['command'] != 'resume' or isinstance(intent['claimId'],str) and UUID.fullmatch(intent['claimId']))
             and row['intentSha256'] == sha(intent), 'CONTROL_INTENT')
        need((state == 'ISSUED' and row['container'] is None) or (state == 'UNKNOWN') or isinstance(row['container'],dict), 'CONTROL_CONTAINER')
        if state in ('UNKNOWN','CLOSED'):
            need(row['outcome'] == 'OUTCOME_UNCERTAIN' if state == 'UNKNOWN' else row['outcome'] in ('COMPLETED','REFUSED'), 'CONTROL_OUTCOME')
        incarnations.add(inc);nonces.add(nonce);all_tags.add(name)
    need(sum(row['state'] != 'CLOSED' for row in rows) <= 1, 'CONTROL_HELD_BOUND')
    return rows


def control_custody(row, expected):
    if 'class' in row:
        if row['container'] is not None:common_custody(row['container'],expected,row['class'])
        return
    original = row['container']
    if original is None:return
    need(isinstance(original,dict) and set(original) == {'cid','startedAt','project','workingDirectory','service','imageId','source'}
         and hexid(original['cid'],64) and isinstance(original['startedAt'],str) and 0 < len(original['startedAt']) <= 100
         and original['service'] == CONTROL and all(original[k] == expected[k] for k in ('source','imageId','project','workingDirectory')), 'CONTROL_CONTAINER_CUSTODY')


def control_observation(expected, rows, captures, mappings):
    need(isinstance(captures,list) and len(captures) <= (2 if any('class' in r for r in rows) else 1), 'CONTROL_PROCESS_BOUND')
    held = {row['incarnation']:row for row in rows if row['state'] != 'CLOSED'}
    seen = set();result = []
    for row in rows:control_custody(row,expected)
    for capture in captures:
        need(isinstance(capture,dict), 'CONTROL_PROCESS')
        inc = capture.get('incarnation')
        need(hexid(inc,32) and inc in held and inc not in seen and capture.get('processInstanceId') == held[inc].get('class',CONTROL), 'CONTROL_PROCESS_ROSTER');seen.add(inc)
        row = held[inc];original = row['container'];container = capture.get('container');inspection = capture.get('inspection')
        need(capture.get('health') is None, 'CONTROL_HEALTH_UNSUPPORTED')
        if original is None:
            need(container is None and inspection == 'UNBOUND', 'CONTROL_UNBOUND_CUSTODY')
        else:
            need(inspection in ('RUNNING','STOPPED','MISSING','UNKNOWN') and capture.get('inspectedCid') == original['cid'], 'CONTROL_INSPECTION_CUSTODY')
            if container is None:need(inspection in ('MISSING','UNKNOWN'), 'CONTROL_MISSING_CUSTODY')
            else:
                need(isinstance(container,dict) and all(container.get(k) == v for k,v in original.items()) and container.get('operatorIncarnation') == inc, 'CONTROL_PROCESS_CUSTODY')
                need((inspection == 'RUNNING' and container.get('running') is True) or (inspection == 'STOPPED' and container.get('running') is False), 'CONTROL_INSPECTION_STATE')
        actor = row.get('class',CONTROL)
        name = row['tags'][0];need(name not in mappings,'TAG_COLLISION')
        mappings[name] = {'actor':'control','processInstanceId':actor,'incarnation':inc,'capability':actor,'leaseState':row['state'],'creditsHeld':1,'originalApplicationNameStatus':'UNKNOWN'}
        result.append({'processInstanceId':actor,'incarnation':inc,'leaseState':row['state'],'intentSha256':row['intentSha256'],'declaredMaximumHeld':1,'inspection':inspection,'cleanup':'UNKNOWN','creditAuthority':'controller ledger; census never refunds'})
    need(seen == set(held), 'MISSING_CONTROL_PROCESS')
    return result

def observe(expected, plan, ledger, processes, census, controlProcesses=None):
    """Validate one already-captured observation, retaining private attribution.

    expected is a caller-pinned capture identity, never inferred from the
    observation. processes contains {health, container} for each held generation;
    container uses the deployment controller's normalized inspect contract.
    census is the source observer {resource, tags}; tags are source observer applicationName/count rows.
    Empty census says nothing about preauthentication or physical retirement.
    """
    need(expected.get('kind') == KIND, 'EXPLICIT_INSTRUMENT_REQUIRED')
    source = {'coreCommit': CORE, 'deployCommit': DEPLOY}
    need(expected.get('source') == plan.get('source') == source, 'SOURCE')
    need(type(expected.get('imageId')) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', expected['imageId']), 'IMAGE')
    need(type(expected.get('project')) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,62}', expected['project']), 'PROJECT')
    need(isinstance(expected.get('workingDirectory'), str) and expected['workingDirectory'].startswith('/'), 'DIRECTORY')
    body = {k: v for k, v in plan.items() if k != 'sha256'}
    need(plan.get('kind') == 'controlled-connection-budget-plan' and type(plan.get('version')) is int and plan['version'] in (1,2)
         and expected.get('planSha256') == plan.get('sha256') == sha(body), 'PLAN_IDENTITY')
    epoch = [plan['resource']['systemIdentifier'], plan['resource']['postmasterStartedAt']]
    need(ledger.get('planSha256') == plan['sha256'] and ledger.get('resourceEpoch') == epoch
         and [census['resource'].get('systemIdentifier'), census['resource'].get('postmasterStartedAt')] == epoch, 'EPOCH')
    resource = census['resource']
    need(resource.get('pgResourceId') == plan['resource']['pgResourceId']
         and resource.get('serverMaximum') == plan['resource']['serverMaximum']
         and resource.get('superuserReserved') == plan['resource']['reserved']['superuser']
         and resource.get('otherReserved') == plan['resource']['reserved']['other'], 'RESOURCE_SETTINGS')
    need(type(resource.get('unmanagedClients')) is int and resource['unmanagedClients'] >= 0, 'UNMANAGED_COUNT')
    controls = control_leases(plan, ledger)
    if plan['version'] == 2:common_leases(plan,ledger,expected)
    slots = {s['processInstanceId']: s for s in plan['slots']}
    need(len(slots) == len(plan['slots']) and set(slots) == set(ledger['slots']), 'ROSTER')
    if controls is None:need(controlProcesses is None or controlProcesses == [], 'UNPLANNED_CONTROL_PROCESSES')
    need(isinstance(processes, list) and len(processes) <= 10000, 'PROCESS_BOUND')
    held = {(sid, row['incarnation']): row for sid, generations in ledger['slots'].items()
            for row in generations if row['state'] != 'RETIRED'}
    need(len(held) == sum(row['state'] != 'RETIRED' for generations in ledger['slots'].values() for row in generations), 'GENERATION_DUPLICATE')
    seen = set()
    mappings = {}
    generations = []
    for capture in processes:
        health, container = capture.get('health'), capture['container']
        key = (capture['processInstanceId'], capture['incarnation'])
        need(key in held and key not in seen, 'GENERATION_ROSTER')
        seen.add(key)
        sid, incarnation = key
        row = held[key]
        need(hexid(incarnation, 32) and hexid(row['nonce'], 32), 'INCARNATION')
        if health is not None:
            need(health.get('source') == source and health.get('nonce') == row['nonce']
                 and health.get('planSha256') == plan['sha256'] and health.get('processInstanceId') == sid
                 and health.get('incarnation') == incarnation, 'HEALTH_IDENTITY')
        need(row.get('state') == 'ISSUED' and row.get('retired') is not True, 'HELD_STATE')
        original = row.get('container')
        inspection = capture.get('inspection')
        if original is None:
            need(container is None and inspection == 'UNBOUND' and health is None, 'UNBOUND_CUSTODY')
        else:
            need(hexid(original.get('cid'),64) and original.get('startedAt')
                 and original.get('source') == source and original.get('service') == sid
                 and all(original.get(k) == expected[k] for k in ('imageId','project','workingDirectory')), 'ORIGINAL_CONTAINER_CUSTODY')
            need(inspection in ('RUNNING', 'STOPPED', 'MISSING', 'UNKNOWN')
                 and capture.get('inspectedCid') == original['cid'], 'INSPECTION_CUSTODY')
            if container is None:
                need(inspection in ('MISSING', 'UNKNOWN') and health is None, 'MISSING_CUSTODY')
            else:
                for field in ('cid', 'startedAt', 'project', 'workingDirectory', 'service', 'imageId', 'source'):
                    need(container.get(field) == original.get(field), 'CONTAINER_IDENTITY')
                need(hexid(container.get('cid'), 64) and container.get('startedAt')
                     and container.get('project') == expected['project'] and container.get('workingDirectory') == expected['workingDirectory']
                     and container.get('service') == sid and container.get('imageId') == expected['imageId']
                     and container.get('source') == source, 'CONTAINER_CUSTODY')
                need((inspection == 'RUNNING' and container.get('running') is True)
                     or (inspection == 'STOPPED' and container.get('running') is False), 'INSPECTION_STATE')
        required = {tag(incarnation, name): name for name in slots[sid]['capabilities']}
        need(len(required) == len(slots[sid]['capabilities']) and set(row['tags']) == set(required)
             and len(row['tags']) == len(required), 'TAGS')
        if health is not None:
            need(set(health['tags']) == set(required) and len(health['tags']) == len(required), 'TAGS')
        names = health.get('applicationNames') if health is not None else {}
        need(isinstance(names, dict) and set(names) <= set(required), 'APPLICATION_MAP')
        for name, capability in required.items():
            need(name not in mappings, 'TAG_COLLISION')
            mappings[name] = {'processInstanceId': sid, 'incarnation': incarnation, 'capability': capability,
                              'originalApplicationNameStatus': 'UNKNOWN'}
        for name, original in names.items():
            need(original.get('capability') == required[name]
                 and (original.get('originalApplicationName') is None or isinstance(original.get('originalApplicationName'), str)), 'APPLICATION_MAP')
            mappings[name] = {'processInstanceId': sid, 'incarnation': incarnation, **original,
                              'originalApplicationNameStatus': 'OBSERVED_SAME_INCARNATION'}
        generations.append({'processInstanceId': sid, 'incarnation': incarnation,
                            'declaredMaximumHeld': slots[sid]['declaredMaximum'], 'inspection': inspection,
                            'unconfirmedCleanup': health.get('unconfirmedCleanup') if health else 'UNKNOWN',
                            'pendingConnects': health.get('pendingConnects') if health else 'UNKNOWN',
                            'creditAuthority': 'controller ledger; census never refunds'})
    need(seen == set(held), 'MISSING_HELD_GENERATION')
    if controls is not None:
        for mapping in mappings.values():mapping['actor'] = 'worker'
    control_rows = control_observation(expected,controls,controlProcesses,mappings) if controls is not None else None
    rows = census.get('tags')
    need(isinstance(rows, list) and len(rows) <= 10000, 'CENSUS_BOUND')
    seen_tags = set()
    attributed = []
    for row in rows:
        if plan['version'] == 2:need(exact(row,('applicationName','count')) and type(row['applicationName']) is str, 'COMMON_CENSUS_ROW')
        name = row.get('applicationName')
        need(name in mappings and name not in seen_tags, 'UNKNOWN_TAG_OR_MAPPING')
        need(type(row.get('count')) is int and 0 <= row['count'] <= 1000000, 'CENSUS_COUNT')
        seen_tags.add(name)
        attributed.append({'raw': row, 'attribution': mappings[name]})
    need(seen_tags == set(mappings), 'CENSUS_COVERAGE')
    result = {'kind': KIND, 'source': source, 'imageId': expected['imageId'], 'planSha256': plan['sha256'],
            'generations': generations, 'resource': resource, 'census': attributed,
            'preauthentication': 'UNKNOWN: absent from census is not retired',
            'nativeAcceptance': 'UNMEASURED', 'lifecycleAuthority': 'NONE',
            'originalNames': 'PRIVATE attribution only; raw census is unchanged'}
    if plan['version'] == 2:
        control_by_tag = {r['tags'][0]:r['class'] for r in controls if r['state'] != 'CLOSED'}
        physical = {'workers':sum(r['count'] for r in rows if r['applicationName'] not in control_by_tag),
                    'control':{c:sum(r['count'] for r in rows if control_by_tag.get(r['applicationName']) == c) for c in CLASSES}}
        occupancy = {'physical':physical,'heldControlCredits':len(control_rows),'activeControlExecutions':sum(r['state'] in ('ISSUED','BOUND') for r in controls)}
        raw = census.get('occupancy')
        need(exact(raw, ('physical','heldControlCredits','activeControlExecutions')) and exact(raw['physical'], ('workers','control'))
             and exact(raw['physical']['control'],CLASSES) and all(integer(x,0,1000000) for x in [raw['physical']['workers'],*raw['physical']['control'].values()])
             and integer(raw['heldControlCredits'],0,2) and integer(raw['activeControlExecutions'],0,1) and raw == occupancy, 'COMMON_OCCUPANCY')
        result.update(ledgerVersion=3,controls=control_rows,controlHistory={'total':len(controls),'closed':sum(r['state'] == 'CLOSED' for r in controls)},occupancy=occupancy,
                      heldCredits={'workers':sum(r['declaredMaximumHeld'] for r in generations),'control':len(control_rows)},
                      controlCreditAuthority='ledger state only; zero authenticated census never closes or refunds')
    elif controls is not None:
        need('occupancy' in census, 'CONTROL_OCCUPANCY_MISSING')
        control_names = {row['tags'][0] for row in controls if row['state'] != 'CLOSED'}
        occupancy = {'workers':sum(row['count'] for row in rows if row['applicationName'] not in control_names), 'control':sum(row['count'] for row in rows if row['applicationName'] in control_names)}
        if 'occupancy' in census:
            raw_occupancy=census['occupancy'];need(isinstance(raw_occupancy,dict) and set(raw_occupancy)=={'workers','control'} and all(type(x)is int and x>=0 for x in raw_occupancy.values()) and raw_occupancy == occupancy, 'OCCUPANCY_MISMATCH')
        result.update(ledgerVersion=2,controls=control_rows,controlHistory={'total':len(controls),'closed':sum(row['state'] == 'CLOSED' for row in controls)},occupancy=occupancy,heldCredits={'workers':sum(row['declaredMaximumHeld'] for row in generations),'control':len(control_rows)},occupancyWithinHeldCredits={'workers':occupancy['workers']<=sum(row['declaredMaximumHeld'] for row in generations),'control':occupancy['control']<=len(control_rows)},controlCreditAuthority='ledger state only; zero authenticated census never closes or refunds')
    return result


def observe_envelope(expected, plan, raw, processes, controlProcesses):
    """Shared attribution only, for declared observation2 or stored-count2.

    Stored clinical counts/selector/PG custody require their own existing oracle
    checks. Passing this function never certifies those payloads or native work.
    """
    census = envelope(expected, plan, raw)
    return observe(expected,plan,raw['ledger'],processes,census,controlProcesses)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    need(not args.capture.is_symlink(), 'INPUT_SYMLINK')
    need(args.capture.stat().st_size <= 16 * 1024 * 1024, 'INPUT_BOUND')
    need(args.capture.stat().st_mode & 0o077 == 0, 'PRIVATE_INPUT')
    value = json.loads(args.capture.read_text())
    result = observe(**value)
    # No overwrite: retain captured originals and a separate intake result.
    with open(args.output, 'x', opener=lambda path, flags: __import__('os').open(path, flags, 0o600)) as output:
        json.dump(result, output, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
