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
CORE = '074eab44ee75b9175c951b6a8add3df3e9554af7'
DEPLOY = '479affb738e01e8f6fe1a476da63a0260ee08f50'


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


def observe(expected, plan, ledger, processes, census):
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
    need(re.fullmatch(r'sha256:[a-f0-9]{64}', expected.get('imageId', '')), 'IMAGE')
    need(re.fullmatch(r'[a-z][a-z0-9-]{0,62}', expected.get('project', '')), 'PROJECT')
    need(isinstance(expected.get('workingDirectory'), str) and expected['workingDirectory'].startswith('/'), 'DIRECTORY')
    body = {k: v for k, v in plan.items() if k != 'sha256'}
    need(plan.get('kind') == 'controlled-connection-budget-plan' and plan.get('version') == 1
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
    slots = {s['processInstanceId']: s for s in plan['slots']}
    need(len(slots) == len(plan['slots']) and set(slots) == set(ledger['slots']), 'ROSTER')
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
    rows = census.get('tags')
    need(isinstance(rows, list) and len(rows) <= 10000, 'CENSUS_BOUND')
    seen_tags = set()
    attributed = []
    for row in rows:
        name = row.get('applicationName')
        need(name in mappings and name not in seen_tags, 'UNKNOWN_TAG_OR_MAPPING')
        need(type(row.get('count')) is int and 0 <= row['count'] <= 1000000, 'CENSUS_COUNT')
        seen_tags.add(name)
        attributed.append({'raw': row, 'attribution': mappings[name]})
    need(seen_tags == set(mappings), 'CENSUS_COVERAGE')
    return {'kind': KIND, 'source': source, 'imageId': expected['imageId'], 'planSha256': plan['sha256'],
            'generations': generations, 'resource': resource, 'census': attributed,
            'preauthentication': 'UNKNOWN: absent from census is not retired',
            'nativeAcceptance': 'UNMEASURED', 'lifecycleAuthority': 'NONE',
            'originalNames': 'PRIVATE attribution only; raw census is unchanged'}


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
