"""Fixed-purpose, private source equality for one owned retired provision actor.

The CLI accepts only a bound scope reference and observation challenge on stdin.
It emits identities, booleans and hashes. Raw API bytes never leave this process.
There is no caller-supplied resource, verb, argv, URL or output-file option.
"""
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time

import phase_fit as p

KIND = 'owned-provision-source-v1'
MAX_BYTES = 32 * 1024 * 1024  # The existing Kubernetes observer response bound.
FILES = ('phase_source_private.py', 'phase_fit.py', 'resource_budget.py')
SOURCE_CODES = {'K8S_PHASE_'+name for name in (
    'JOB_SOURCE_CHANGED','POD_SOURCE_CHANGED','SOURCE_METADATA_CHANGED','JOB_POLICY_CHANGED',
    'JOB_OWNERSHIP','JOB_NOT_COMPLETE','PROVISION_POD_ROSTER','POD_NOT_TERMINAL',
    'PROVISION_EXTRA_CONTAINER','CONTAINER_ROSTER','CONTAINER_NOT_TERMINAL',
    'TERMINAL_PROOF_CHANGED','JOB_RESOURCES_CHANGED','POD_RESOURCES_CHANGED',
    'POD_BUDGET_CHANGED','POD_SPEC_CHANGED','UNEXPECTED_ADMISSION_VOLUME','RECEIPT_CHANGED')}
ERROR_CODES=SOURCE_CODES|{'K8S_PHASE_PRIVATE_'+name for name in (
    'HELPER_UNAVAILABLE','TOOL_UNAVAILABLE','REFERENCE','PRIVATE_FILE','REFERENCE_CHANGED',
    'PREFLIGHT_CHANGED','SOURCE_CHANGED','NAMESPACE_CHANGED','TOOL_CHANGED','SCOPE','PROOF_REQUIRED',
    'SCOPE_CHANGED','DEADLINE_CHANGED','POD_ROSTER','FOREIGN_POD','POD_CHANGED','REQUEST','DEADLINE',
    'API_UNAVAILABLE','IDENTITY_CHANGED','PROOF_CHANGED','POST_IDENTITY_CHANGED','UNAVAILABLE')}


class Refused(RuntimeError):
    def __init__(self, code, verdict='FAIL'):
        super().__init__('K8S_PHASE_PRIVATE_'+code)
        self.verdict=verdict


def require(ok, code, verdict='FAIL'):
    if not ok:raise Refused(code,verdict)


def refusal(error):
    if isinstance(error,Refused) and str(error) in ERROR_CODES:
        return {'verdict':error.verdict,'code':str(error)}
    if isinstance(error,ValueError) and str(error) in SOURCE_CODES:
        return {'verdict':'FAIL','code':str(error)}
    return {'verdict':'UNMEASURED','code':'K8S_PHASE_PRIVATE_UNAVAILABLE'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity():
    here = Path(__file__).resolve().parent
    require(all((here/name).is_file() for name in FILES), 'HELPER_UNAVAILABLE','UNMEASURED')
    return {name: sha(here/name) for name in FILES}


def preflight(control):
    """Validate the fixed helper and existing tools before any fixture actor."""
    kubectl = Path(control['toolsDirectory'])/'kubectl'
    guard = Path(control['readonlyGuard'])
    require(kubectl.is_absolute() and kubectl.is_file() and guard.is_absolute() and guard.is_file(),
            'TOOL_UNAVAILABLE','UNMEASURED')
    return {'files': identity(), 'kubectl': {'path': str(kubectl), 'sha256': sha(kubectl)},
            'guard': {'path': str(guard), 'sha256': sha(guard)}}


def private_document(ref):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'REFERENCE')
    path = Path(ref['path'])
    require(path.is_absolute() and not path.is_symlink(), 'REFERENCE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        mode = os.fstat(fd)
        require(stat.S_ISREG(mode.st_mode) and mode.st_mode & 0o077 == 0 and mode.st_size <= MAX_BYTES,
                'PRIVATE_FILE')
        raw = os.read(fd, MAX_BYTES + 1)
    finally:os.close(fd)
    require(len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == ref['sha256'], 'REFERENCE_CHANGED')
    return json.loads(raw)


def write_scope(control, config, environment, runtime):
    """Bind existing controller custody, source and tool hashes, without a GET."""
    selected = control['resourcePhasePreflight']
    require(selected.get('privateSource') == preflight(control), 'PREFLIGHT_CHANGED')
    runtime = Path(runtime)
    case = Path(control['caseDirectory'])
    proof = private_document({'path': str(runtime/'provision-retirement.json'),
                              'sha256': sha(runtime/'provision-retirement.json')})
    job, = [o for o in p.objects(json.loads((case/'render.json').read_bytes())) if p.key(o) == p.PROVISION]
    require(proof['planSha256'] == p.digest(selected['plan']) and
            proof['sourceTemplateSha256'] == p.digest(job['spec']['template']), 'SOURCE_CHANGED')
    custody = json.loads((runtime/'custody.json').read_bytes())
    require(custody['namespaceUid'] == proof['namespaceUid'], 'NAMESPACE_CHANGED')
    require(config['kubectl'] == selected['privateSource']['kubectl']['path'] and
            config['readonlyGuard'] == selected['privateSource']['guard']['path'], 'TOOL_CHANGED')
    until = datetime.fromisoformat(json.loads((runtime/'deadlines.json').read_bytes())['workUntil']).timestamp()
    scope = {'version': 1, 'kind': KIND, 'context': environment['context'],
             'namespace': environment['namespace'], 'runId': environment['runId'],
             'namespaceUid': proof['namespaceUid'], 'expectedJob': job, 'retirement': proof,
             'planSha256': p.digest(selected['plan']), 'instrument': control['instrumentSha256'],
             'source': {'pair': {'core': environment['sourceCommit'], 'deploy': environment['imageDeployCommit']},
                        'bindingCommit': environment['bindingCommit'], 'appImage': environment['images']['app']},
             'tools': selected['privateSource'], 'workUntil': until}
    path = runtime/'provision-source-scope.private.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:json.dump(scope, out, sort_keys=True, allow_nan=False)
    return {'path': str(path), 'sha256': sha(path)}


def scope_check(scope):
    require(scope.get('version') == 1 and scope.get('kind') == KIND, 'SCOPE')
    require(re.fullmatch(r'ns-synth-[a-z0-9-]{1,54}', scope['namespace']) and
            re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', scope['runId']) and
            isinstance(scope['context'], str) and scope['context'] and not scope['context'].startswith('-'), 'SCOPE')
    expected = scope['expectedJob'];proof = scope['retirement']
    require(p.key(expected) == p.PROVISION and expected['metadata']['namespace'] == scope['namespace'] and
            expected['metadata']['labels']['nightscout.org/run-id'] == scope['runId'], 'SCOPE')
    require(proof['namespaceUid'] == scope['namespaceUid'] and proof['planSha256'] == scope['planSha256'] and
            proof['sourceTemplateSha256'] == p.digest(expected['spec']['template']) and
            re.fullmatch(r'provision-[a-z0-9-]+', proof['pod']['name']), 'SCOPE')
    tools = scope['tools'];binary = Path(tools['kubectl']['path'])
    require(binary.is_file() and Path(tools['guard']['path']).is_file(), 'TOOL_UNAVAILABLE','UNMEASURED')
    require(tools['files'] == identity() and binary.is_absolute() and binary.name == 'kubectl' and
            binary.is_file() and sha(binary) == tools['kubectl']['sha256'] and
            sha(tools['guard']['path']) == tools['guard']['sha256'], 'TOOL_CHANGED')


def binding(config, objects):
    phase = config.get(p.FIELD, {})
    require('privateSource' in phase, 'PROOF_REQUIRED','UNMEASURED')
    scope = private_document(phase['privateSource'])
    scope_check(scope)
    require(scope['context'] == config['context'] and scope['namespace'] == config['namespace'] and
            scope['runId'] == config['runId'] and scope['expectedJob'] == objects[p.PROVISION], 'SCOPE_CHANGED')
    require(scope['instrument'] == config['pins']['instrument'] and
            all(scope['source'][name] == config['pins'][name] for name in ('pair', 'bindingCommit', 'appImage')),
            'SOURCE_CHANGED')
    require(scope['tools']['kubectl']['path'] == config['kubectl'] and
            scope['tools']['guard']['path'] == config['readonlyGuard'] and
            scope['planSha256'] == p.digest(phase['plan']) and
            scope['retirement'] == p.reference(phase['retirement']), 'SCOPE_CHANGED')
    require(scope['workUntil'] == datetime.fromisoformat(config['deadlines']['workUntil'].replace('Z', '+00:00')).timestamp(),
            'DEADLINE_CHANGED')
    return scope


def actor_identity(obj):
    if obj is None:return None
    metadata = obj['metadata']
    result = {'name': metadata['name'], 'uid': metadata['uid'], 'resourceVersion': metadata['resourceVersion']}
    if obj.get('kind') == 'Pod' or 'containers' in obj.get('spec', {}):
        states = obj.get('status', {}).get('initContainerStatuses', []) + obj.get('status', {}).get('containerStatuses', [])
        result.update(nodeName=obj['spec'].get('nodeName'), phase=obj.get('status', {}).get('phase'),
                      controller=[{name:r.get(name) for name in ('kind','name','uid')}
                                  for r in metadata.get('ownerReferences',[]) if r.get('controller') is True],
                      resourcesSha256=p.digest({c['name']: c.get('resources', {}) for c in
                                                obj['spec'].get('initContainers', []) + obj['spec']['containers']}),
                      containers={c['name']: {name: c.get(name) for name in
                                             ('containerID', 'imageID', 'restartCount', 'ready')} for c in states})
    return result


def guarded_scope(config, namespace, job, pods, scope):
    require(namespace['metadata']['name'] == config['namespace'] and
            namespace['metadata'].get('labels', {}).get(config['ownerLabel']) == config['runId'] and
            not namespace['metadata'].get('deletionTimestamp'), 'NAMESPACE_CHANGED')
    require(job is not None and p.key(job) == p.PROVISION and
            job['metadata']['namespace'] == config['namespace'], 'JOB_CHANGED')
    owned = []
    roster = {}
    for pod in pods:
        m = pod['metadata']
        require(m['namespace'] == config['namespace'] and
                m.get('labels', {}).get(config['ownerLabel']) == config['runId'], 'FOREIGN_POD')
        require(m['name'] not in roster, 'POD_ROSTER')
        stable=actor_identity(pod)
        # Whole-namespace authority tracks roster, ownership, resources and
        # incarnations. Unrelated status refreshes do not change that authority.
        stable.pop('resourceVersion',None);stable.pop('phase',None)
        for state in stable['containers'].values():state.pop('ready',None)
        roster[m['name']] = stable
        if m.get('labels', {}).get('job-name') == 'provision' or any(r.get('kind') == 'Job' and
                (r.get('uid') == scope['retirement']['jobUid'] or r.get('name') == 'provision')
                for r in m.get('ownerReferences', [])):owned.append(pod)
    require(len(owned) <= 1, 'POD_ROSTER')
    pod = owned[0] if owned else None
    require(pod is None or (pod['metadata']['name'] == scope['retirement']['pod']['name'] and
                           pod['metadata']['uid'] == scope['retirement']['pod']['uid']), 'POD_CHANGED')
    return {'namespace': actor_identity(namespace), 'job': actor_identity(job), 'pod': actor_identity(pod)}, p.digest(roster)


def prove(request, get=None, clock=time):
    require(set(request) == {'version', 'scope', 'nonce', 'until', 'identity', 'rosterSha256'} and
            request['version'] == 1 and re.fullmatch(r'[a-f0-9]{64}', request['nonce']), 'REQUEST')
    scope = private_document(request['scope']);scope_check(scope)
    until = request['until']
    require(type(until) in (int, float) and clock.time() < until <= scope['workUntil'], 'DEADLINE','UNMEASURED')
    def left():
        remaining = until - clock.time();require(remaining > 0, 'DEADLINE','UNMEASURED');return remaining
    def query(kind, name, optional=False):
        left()
        # get is an inert test port. Actual subprocess argv is fixed here.
        if get is not None:value = get(kind, name, optional)
        else:
            argv = [scope['tools']['kubectl']['path'], '--context', scope['context'], '--namespace', scope['namespace'],
                    '--request-timeout='+str(min(20,left()))+'s', 'get', kind, name,
                    *(['--ignore-not-found'] if optional else []), '-o', 'json']
            result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=min(20, left()), check=False)
            require(result.returncode == 0 and isinstance(result.stdout, bytes) and len(result.stdout) <= MAX_BYTES,
                    'API_UNAVAILABLE','UNMEASURED')
            value = None if optional and not result.stdout.strip() else json.loads(result.stdout)
        left();return value
    previous = {k: v for k, v in scope['retirement'].items() if k != 'planSha256'}
    def sample():
        namespace = query('namespace', scope['namespace'])
        job = query('job', 'provision')
        pod = query('pod', scope['retirement']['pod']['name'], True)
        require(namespace is not None and namespace['metadata']['uid'] == scope['namespaceUid'] and
                namespace['metadata']['name'] == scope['namespace'] and
                namespace['metadata'].get('labels', {}).get('nightscout.org/run-id') == scope['runId'] and
                not namespace['metadata'].get('deletionTimestamp'), 'NAMESPACE_CHANGED')
        observed = {'namespace': actor_identity(namespace), 'job': actor_identity(job), 'pod': actor_identity(pod)}
        require(observed == request['identity'], 'IDENTITY_CHANGED')
        proof = p.terminal(scope['expectedJob'], job, [] if pod is None else [pod],
                           scope['namespaceUid'], scope['runId'], previous)
        return observed, proof
    first, proof = sample();last, again = sample()
    require(first == last and proof == again, 'IDENTITY_CHANGED');scope_check(scope);left()
    return {'version': 1, 'kind': KIND, 'verdict': 'PASS', 'matches': True,
            'nonce': request['nonce'], 'requestSha256': p.digest(request), 'scopeSha256': request['scope']['sha256'],
            'instrument': scope['instrument'], 'helperFiles': identity(), 'identity': first,
            'rosterSha256': request['rosterSha256'], 'terminalSha256': p.digest(proof),
            'sourceTemplateSha256': proof['sourceTemplateSha256'], 'podPresent': first['pod'] is not None}


def observe(config, objects, observation, namespace, job, pods, client, remaining):
    scope = binding(config, objects)
    before, roster = guarded_scope(config, namespace, job, pods, scope)
    request = {'version': 1, 'scope': config[p.FIELD]['privateSource'], 'nonce': secrets.token_hex(32),
               'until': min(scope['workUntil'], time.time() + remaining()), 'identity': before, 'rosterSha256': roster}
    response = client.phase_source_proof(request)
    expected_keys = {'version', 'kind', 'verdict', 'matches', 'nonce', 'requestSha256', 'scopeSha256',
                     'instrument', 'helperFiles', 'identity', 'rosterSha256', 'terminalSha256',
                     'sourceTemplateSha256', 'podPresent'}
    old = {k: v for k, v in scope['retirement'].items() if k != 'planSha256'}
    require(isinstance(response, dict) and set(response) == expected_keys and response['version'] == 1 and
            response['kind'] == KIND and response['verdict'] == 'PASS' and response['matches'] is True and
            response['nonce'] == request['nonce'] and response['requestSha256'] == p.digest(request) and
            response['scopeSha256'] == config[p.FIELD]['privateSource']['sha256'] and
            response['instrument'] == scope['instrument'] and response['helperFiles'] == identity() and
            response['identity'] == before and response['rosterSha256'] == roster and
            response['terminalSha256'] == p.digest(old) and
            response['sourceTemplateSha256'] == old['sourceTemplateSha256'] and
            response['podPresent'] is (before['pod'] is not None), 'PROOF_CHANGED')
    after, post_roster = guarded_scope(config, client.get('namespace', config['namespace']),
                                      client.get('Job', 'provision'), client.get('pods')['items'], scope)
    remaining();require(after == before and post_roster == roster, 'POST_IDENTITY_CHANGED')
    require(binding(config,objects)==scope,'SCOPE_CHANGED');remaining()
    return {'contract': p.CONTRACT, 'jobUid': old['jobUid'], 'podUid': old['pod']['uid'],
            'retirement': 'VERIFIED', 'podPresent': response['podPresent'], 'planSha256': scope['planSha256'],
            'sourceEquality': 'VERIFIED_PRIVATE', 'proofSha256': p.digest(response),
            'scopeSha256': config[p.FIELD]['privateSource']['sha256']}


def main():
    try:
        require(len(sys.argv) == 1, 'REQUEST')
        raw = sys.stdin.buffer.read(MAX_BYTES + 1);require(len(raw) <= MAX_BYTES, 'REQUEST')
        answer = prove(json.loads(raw));code = 0
    except BaseException as error:
        answer=refusal(error);code = 3
    sys.stdout.write(json.dumps(answer, sort_keys=True) + '\n')
    return code


if __name__ == '__main__':sys.exit(main())
