#!/usr/bin/env python3
"""Read-only M7 recorded-evidence gate. Never executes an application or emits a receipt."""
import argparse
import gzip
import io
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

# A queue gate must not create bytecode caches beside an imported contract.
sys.dont_write_bytecode = True

TIERS = ('unit', 'dom', 'dependency', 'core', 'harness', 'integration', 'stress', 'browser')
COMPONENTS = ('api', 'realtime', 'evaluator', 'postgres', 'vault-agent')
BASE_COMPONENTS = ('api', 'realtime', 'evaluator', 'postgres', 'vault')
SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
NAME = re.compile(r'[a-z][a-z0-9_-]{0,79}')
LIMIT = 16 * 1024 * 1024


def need(value, code):
    if not value:
        raise ValueError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'M7_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def decode(data):
    def finite_float(text):
        number = float(text)
        need(math.isfinite(number), 'M7_JSON_CONSTANT')
        return number
    return json.loads(data, object_pairs_hook=unique_object, parse_float=finite_float,
                      parse_constant=lambda _: need(False, 'M7_JSON_CONSTANT'))


def read_json(file):
    need(file.is_file() and not file.is_symlink() and file.stat().st_size <= LIMIT, 'M7_JSON_FILE')
    with file.open('rb') as stream:
        data = stream.read(LIMIT + 1)
    need(len(data) <= LIMIT, 'M7_JSON_FILE')
    return decode(data)


class Evidence:
    def __init__(self, root):
        self.root = root.resolve(strict=True)
        self.cache = {}
        self.total = 0
        self.allowed = {}

    def bytes(self, reference):
        need(isinstance(reference, dict) and set(reference) == {'path', 'sha256'}, 'M7_ARTIFACT_REFERENCE')
        name, digest = reference['path'], reference['sha256']
        need(isinstance(name, str) and isinstance(digest, str) and DIGEST.fullmatch(digest), 'M7_ARTIFACT_REFERENCE')
        need(self.allowed.get(name) == digest, 'M7_ARTIFACT_NOT_PINNED')
        relative = Path(name)
        need(not relative.is_absolute() and relative.parts and all(p not in ('.', '..') for p in relative.parts), 'M7_ARTIFACT_PATH')
        file = self.root
        for part in relative.parts:
            file /= part
            need(not file.is_symlink(), 'M7_ARTIFACT_SYMLINK')
        need(file.resolve(strict=True).is_relative_to(self.root) and file.is_file(), 'M7_ARTIFACT_PATH')
        if name not in self.cache:
            need(len(self.cache) < 256 and file.stat().st_size <= LIMIT, 'M7_ARTIFACT_BOUND')
            with file.open('rb') as stream:
                data = stream.read(LIMIT + 1)
            need(len(data) <= LIMIT, 'M7_ARTIFACT_BOUND')
            self.total += len(data)
            need(self.total <= 64 * 1024 * 1024, 'M7_ARTIFACT_BOUND')
            self.cache[name] = data
        data = self.cache[name]
        need(hashlib.sha256(data).hexdigest() == digest, 'M7_ARTIFACT_HASH')
        return data

    def json(self, reference):
        return decode(self.bytes(reference))


def identity(value):
    need(isinstance(value, dict) and set(value) == {'pair', 'imageId', 'instrument'}, 'M7_IDENTITY_SHAPE')
    pair = value['pair']
    need(isinstance(pair, dict) and set(pair) == {'core', 'deploy'} and
         all(isinstance(v, str) and SHA.fullmatch(v) for v in pair.values()), 'M7_SOURCE_IDENTITY')
    need(isinstance(value['imageId'], str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value['imageId']) and
         isinstance(value['instrument'], str) and DIGEST.fullmatch(value['instrument']), 'M7_IMAGE_INSTRUMENT_IDENTITY')


def attribution(value):
    need(isinstance(value, dict) and value and 'core' in value and
         set(value) <= {'core', 'deploy', 'baseline', 'instrument', 'imageId', 'credentialProfile', 'diagnostics'}, 'M7_ATTRIBUTION_SHAPE')
    for key, item in value.items():
        if key in ('core', 'deploy', 'baseline'):
            need(isinstance(item, str) and SHA.fullmatch(item), 'M7_ATTRIBUTION_SOURCE')
        elif key == 'instrument':
            need(isinstance(item, str) and DIGEST.fullmatch(item), 'M7_ATTRIBUTION_INSTRUMENT')
        elif key == 'imageId':
            need(isinstance(item, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', item), 'M7_ATTRIBUTION_IMAGE')
        elif key == 'diagnostics':
            need(item in ('ON', 'OFF'), 'M7_ATTRIBUTION_DIAGNOSTICS')
        else:
            need(isinstance(item, str) and NAME.fullmatch(item), 'M7_ATTRIBUTION_PROFILE')


def pointer(document, path):
    need(isinstance(path, str) and path.startswith('/') and len(path) <= 512, 'M7_ASSERTION_POINTER')
    value = document
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            need(re.fullmatch(r'0|[1-9][0-9]*', part) and int(part) < len(value), 'M7_ASSERTION_MISSING')
            value = value[int(part)]
        else:
            need(isinstance(value, dict) and part in value, 'M7_ASSERTION_MISSING')
            value = value[part]
    return value


def check_proof(specification, proof, evidence):
    need(isinstance(specification, dict) and set(specification) == {'attribution', 'assertions'}, 'M7_PROOF_SPEC')
    attribution(specification['attribution'])
    need(isinstance(proof, dict) and set(proof) == {'attribution', 'artifact'} and
         proof['attribution'] == specification['attribution'], 'M7_PROOF_ATTRIBUTION')
    assertions = specification['assertions']
    need(isinstance(assertions, dict) and 1 <= len(assertions) <= 256, 'M7_PROOF_ASSERTIONS')
    document = evidence.json(proof['artifact'])
    for path, expected in assertions.items():
        # JSON comparison is type-sensitive: True is not the numeric exit code 1.
        need(json.dumps(pointer(document, path), sort_keys=True) == json.dumps(expected, sort_keys=True), 'M7_PROOF_ASSERTION')


def counts(log):
    text = re.sub(r'\x1b\[[0-9;]*m', '', log.decode('utf8'))
    values = {'passing': [], 'pending': [], 'failing': []}
    for line in text.splitlines():
        match = re.match(r'^\s*(\d+) (passing|pending|failing)\b', line)
        if match:
            values[match[2]].append(int(match[1]))
    need(len(values['passing']) == 1 and all(len(v) <= 1 for v in values.values()), 'M7_TIER_EPILOGUE')
    return {key: value[0] if value else 0 for key, value in values.items()}


def pending_policy(specification, actual):
    need(isinstance(specification, dict) and set(specification) == {'count', 'reason'} and
         integer(specification['count']) and isinstance(specification['reason'], str) and
         (specification['count'] == 0 or specification['reason'].strip()), 'M7_PENDING_POLICY')
    need(type(actual) is int and actual == specification['count'], 'M7_PENDING_MISMATCH')


def check_acceptance(expected, receipt, evidence):
    need(type(expected.get('version')) is int and expected['version'] == 1 and expected.get('kind') == 'm7-joined-expectation', 'M7_EXPECTATION_SHAPE')
    identity(expected['identity'])
    need(type(receipt.get('version')) is int and receipt['version'] == 1 and receipt.get('kind') == 'joined-acceptance' and receipt.get('status') == 'PASS', 'M7_FULL_RECEIPT_REQUIRED')
    actual_identity = {field: receipt.get(field) for field in ('pair', 'imageId', 'instrument')}
    identity(actual_identity)
    need(actual_identity == expected['identity'], 'M7_RECEIPT_IDENTITY')
    need(receipt.get('evidenceSha256') == receipt['campaign']['sha256'], 'M7_ACCEPTANCE_EVIDENCE_HASH')
    pair = expected['identity']['pair']
    functional_pair=expected.get('functionalCampaignPair',pair)
    need(isinstance(functional_pair,dict) and set(functional_pair)=={'core','deploy'} and all(isinstance(v,str) and SHA.fullmatch(v) for v in functional_pair.values()),'M7_FUNCTIONAL_CAMPAIGN_PIN')
    need(functional_pair['core']==pair['core'],'M7_FUNCTIONAL_CORE_MISMATCH')
    campaign = evidence.json(receipt['campaign'])
    need(campaign.get('scope') == 'FROZEN_CORE_FUNCTIONAL_ACCEPTANCE_EXECUTION' and campaign.get('status') == 'passed' and
         campaign.get('errors') == [] and campaign.get('ownMongoCleanupVerified') is True and
         campaign.get('fixtureResiduals') == [] and campaign.get('fixtureVolumeResiduals') == [], 'M7_CAMPAIGN_INCOMPLETE')
    need(campaign.get('source', {}).get('coreCommit') == functional_pair['core'] and
         campaign.get('source', {}).get('deployCommit') == functional_pair['deploy'], 'M7_CAMPAIGN_SOURCE')
    commands = campaign.get('commands')
    need(isinstance(commands, list), 'M7_CAMPAIGN_COMMANDS')
    by_id = {}
    for command in commands:
        need(isinstance(command, dict) and isinstance(command.get('id'), str) and command['id'] not in by_id, 'M7_COMMAND_DUPLICATE')
        by_id[command['id']] = command
    need(set(expected['pending']) == set(TIERS) | {'corpus'}, 'M7_PENDING_POLICY')
    logs = receipt.get('tierLogs')
    need(isinstance(logs, dict) and set(logs) == set(TIERS), 'M7_REQUIRED_TIERS')
    campaign_directory = Path(receipt['campaign']['path']).parent
    for tier in TIERS:
        command = by_id.get(tier, {})
        need(command.get('status') == 'passed' and type(command.get('returnCode')) is int and command['returnCode'] == 0,
             'M7_TIER_NOT_PASSED')
        need(logs[tier]['path'] == str(campaign_directory / command.get('stdout', '')), 'M7_TIER_LOG_BINDING')
        result = counts(evidence.bytes(logs[tier]))
        need(result['passing'] > 0 and result['failing'] == 0, 'M7_TIER_RESULT')
        pending_policy(expected['pending'][tier], result['pending'])
    corpus_command = expected.get('corpusCommand')
    need(isinstance(corpus_command, str) and NAME.fullmatch(corpus_command), 'M7_CORPUS_COMMAND')
    command = by_id.get(corpus_command, {})
    need(command.get('status') == 'passed' and type(command.get('returnCode')) is int and command['returnCode'] == 0, 'M7_CORPUS_NOT_EXECUTED')
    corpus = evidence.json(receipt['corpus'])
    required = expected.get('corpusSuites')
    need(isinstance(required, list) and required and len(required) == len(set(required)) and
         all(isinstance(s, str) and re.fullmatch(r'tests/[A-Za-z0-9_.-]+\.test\.js', s) for s in required), 'M7_CORPUS_EXPECTATION')
    need(isinstance(corpus.get('suites'), list) and len(corpus['suites']) == len(required) and
         set(corpus['suites']) == set(required), 'M7_CORPUS_MISSING_SUITE')
    result = corpus.get('result', {})
    need(type(corpus.get('status')) is int and corpus['status'] == 0 and corpus.get('remaining') == [] and
         type(result.get('status')) is int and result['status'] == 0 and result.get('signal') is None and
         integer(result.get('passing'), 1) and type(result.get('failing')) is int and result['failing'] == 0, 'M7_CORPUS_INCOMPLETE')
    pending_policy(expected['pending']['corpus'], result.get('pending'))
    for category in ('criteria', 'controls'):
        specifications = expected.get(category)
        proofs = receipt.get(category)
        need(isinstance(specifications, dict) and specifications and isinstance(proofs, dict) and
             set(proofs) == set(specifications) and all(NAME.fullmatch(k) for k in specifications), 'M7_REQUIRED_PROOFS')
        for name, spec in specifications.items():
            if category == 'controls':
                need(isinstance(spec, dict) and set(spec) == {'baseline', 'broken', 'restored'} and
                     isinstance(proofs[name], dict) and set(proofs[name]) == set(spec), 'M7_CONTROL_PHASES')
                for phase in spec:
                    values = spec[phase].get('assertions', {}).values()
                    if phase == 'broken':
                        need(any((type(v) is int and v > 0) or v in ('RED', 'FAIL', 'failed') for v in values), 'M7_CONTROL_RED_REQUIRED')
                    else:
                        need(any((type(v) is int and v == 0) or v in ('GREEN', 'PASS', 'passed') for v in values), 'M7_CONTROL_GREEN_REQUIRED')
                    check_proof(spec[phase], proofs[name][phase], evidence)
            else:
                check_proof(spec, proofs[name], evidence)


def campaign_contract():
    file = Path(__file__).resolve().parents[2] / 'mt-bench/m7-joined/contract.py'
    spec = importlib.util.spec_from_file_location('m7_existing_campaign_contract', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def profile_selection(cell, expected):
    chosen=expected.get('profileSelection')
    need(isinstance(chosen,dict) and set(chosen)=={'version','settings','diagnostics','topology','sha256','evaluatorProgress'} and type(chosen['version']) is int and chosen['version']==2,'M7_PROFILE_SELECTION_PIN')
    need(chosen['evaluatorProgress']==progress_contract().POLICY,'M7_PROFILE_EVALUATOR_PROGRESS_PIN')
    digest=hashlib.sha256(json.dumps({k:v for k,v in chosen.items() if k!='sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    need(chosen['sha256']==digest,'M7_PROFILE_SELECTION_HASH')
    settings=chosen['settings']
    need(isinstance(settings,dict) and type(settings.get('schema')) is int and settings['schema']==1 and isinstance(settings.get('sha256'),str) and DIGEST.fullmatch(settings['sha256']) and settings.get('sourceCommit')==expected['identity']['pair']['core'] and isinstance(settings.get('sourceBlobs'),dict) and bool(settings['sourceBlobs']) and all(isinstance(k,str) and isinstance(v,str) and SHA.fullmatch(v) for k,v in settings['sourceBlobs'].items()),'M7_PROFILE_SETTINGS_PIN')
    diagnostics=chosen['diagnostics']
    need(isinstance(diagnostics,dict) and diagnostics.get('mode') in ('off','on') and integer(diagnostics.get('intervalMs'),1000) and diagnostics['intervalMs']<=60000 and diagnostics.get('environment')=={'NS_M7_DIAGNOSTICS':'1' if diagnostics['mode']=='on' else '0','NS_M7_DIAGNOSTICS_INTERVAL_MS':str(diagnostics['intervalMs'])},'M7_PROFILE_DIAGNOSTICS_PIN')
    topology=chosen['topology']
    need(isinstance(topology,dict) and topology.get('binding')=='registry-default' and topology.get('secretsBackend')=='vault-server' and topology.get('vaultAgentOverlay') is False and integer(topology.get('realtimeWorkers'),1) and integer(topology.get('evaluatorWorkers'),1),'M7_PROFILE_TOPOLOGY_PIN')
    need(cell.get('profileSelection')==chosen,'M7_PROFILE_SELECTION_MISMATCH')
    observed=cell.get('settingsFingerprintObservation',{})
    need(isinstance(observed,dict) and observed.get('verdict')=='PASS' and integer(observed.get('observations'),1) and type(observed.get('invalid')) is int and observed['invalid']==0 and type(observed.get('mismatch')) is int and observed['mismatch']==0,'M7_FINGERPRINT_UNMEASURED')


def progress_contract():
    file=Path(__file__).resolve().parents[2]/'mt-bench/m7-joined/evaluator_progress.py'
    spec=importlib.util.spec_from_file_location('m7_progress_contract',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def recovery_contract():
    directory=Path(__file__).resolve().parents[2]/'mt-bench/m7-joined'
    saved=sys.path[:]
    try:
        sys.path.insert(0,str(directory))
        spec=importlib.util.spec_from_file_location('m7_recovery_contract',directory/'evaluator_recovery.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    finally:sys.path[:]=saved


def progress_measurement(cell,expected,evidence):
    module=progress_contract()
    key=cell['profile']+':'+str(cell['tenants'])+':'+str(cell['replicas'])
    references=expected.get('evaluatorProgressArtifacts',{}).get(key)
    need(isinstance(references,dict) and set(references)=={'idle','load','recovery'},'M7_EVALUATOR_PROGRESS_ARTIFACTS')
    recorded=cell.get('evaluatorProgress',{})
    need(isinstance(recorded,dict) and set(recorded)=={'idle','load','recovery'},'M7_EVALUATOR_PROGRESS_REQUIRED')
    inventory=expected['capacityInventories'][cell['profile']+':'+str(cell['replicas'])]
    for phase in ('idle','load','recovery'):
        ref=references[phase];compressed=evidence.bytes(ref)
        need(ref['path'].endswith('.json.gz'),'M7_EVALUATOR_PROGRESS_ENCODING')
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:raw=stream.read(LIMIT+1)
        need(len(raw)<=LIMIT,'M7_EVALUATOR_PROGRESS_DECODE_BOUND')
        evidence.progress_decoded=getattr(evidence,'progress_decoded',0)+len(raw)
        need(evidence.progress_decoded<=64*1024*1024,'M7_EVALUATOR_PROGRESS_DECODE_BOUND')
        document=decode(raw)
        need(document.get('kind')==('evaluator-recovery-v2' if phase=='recovery' else 'evaluator-progress-phase-v2') and document.get('policy')==module.POLICY,'M7_EVALUATOR_PROGRESS_VERSION')
        need(document.get('attribution')=={'pair':cell['pair'],'imageId':cell['imageId'],'instrument':cell['instrument'],'profileSelection':cell['profileSelection']['sha256'],'tenants':cell['tenants'],'replicas':cell['replicas'],'profile':cell['profile'],'hostIdentity':cell['hostIdentity']},'M7_EVALUATOR_PROGRESS_IDENTITY')
        try:
            result=recovery_contract().verify(document,cell['tenants'],inventory['windows']['load']['evaluator']) if phase=='recovery' else module.verify(document,cell['tenants'],inventory['windows'][phase]['evaluator'],phase)
        except RuntimeError as error:raise ValueError(str(error)) from error
        need(recorded[phase]=={**result,'rawSha256':hashlib.sha256(raw).hexdigest(),'gzipSha256':ref['sha256']},'M7_EVALUATOR_PROGRESS_ASSESSMENT')


def cell_measurement(cell, expected, profile, host, evidence):
    for field, value in expected['identity'].items():
        need(cell.get(field) == value, 'M7_CAPACITY_IDENTITY')
    need(cell.get('hostIdentity') == host and isinstance(host, str) and DIGEST.fullmatch(host), 'M7_CAPACITY_HOST')
    need(cell.get('profile') == profile and cell.get('cadence') == campaign_contract().CADENCE[profile], 'M7_CAPACITY_PROFILE')
    need(type(cell.get('tenants')) is int and type(cell.get('replicas')) is int and
         cell['replicas'] in (1, 2, 4), 'M7_CAPACITY_CELL')
    profile_selection(cell,expected)
    correctness, oracle = cell.get('correctness'), cell.get('oracle', {})
    need(isinstance(correctness, list) and len(correctness) >= 2 and all(type(v) is bool for v in correctness) and
         oracle.get('verdict') in ('GREEN', 'RED') and integer(oracle.get('uncertain')) and
         correctness[0] == (oracle['verdict'] == 'GREEN') and correctness[1] == (oracle['uncertain'] == 0), 'M7_CAPACITY_ASSESSMENT')
    need(cell.get('verdict') == ('PASS' if all(correctness) else 'FAIL'), 'M7_CAPACITY_ASSESSMENT')
    inventory = expected.get('capacityInventories', {}).get(profile + ':' + str(cell['replicas']))
    need(isinstance(inventory, dict) and set(inventory) == {'httpShapes', 'windows'}, 'M7_CAPACITY_INVENTORY')
    shape_names = inventory['httpShapes']
    need(isinstance(shape_names, list) and len(shape_names) == 7 and len(set(shape_names)) == 7 and
         all(isinstance(name, str) and NAME.fullmatch(name) for name in shape_names), 'M7_HTTP_SHAPE_POLICY')
    measured = cell.get('measurements', {})
    shapes, windows = measured.get('httpShapes', {}), measured.get('windows', {})
    need(measured.get('complete') is True and isinstance(shapes, dict) and set(shapes) == set(shape_names), 'M7_HTTP_SHAPE_INVENTORY')
    need(isinstance(windows, dict) and set(windows) == {'idle-disabled', 'idle', 'load'} and
         isinstance(inventory['windows'], dict) and set(inventory['windows']) == set(windows), 'M7_CAPACITY_WINDOW_INVENTORY')
    for row in shapes.values():
        need(isinstance(row, dict) and integer(row.get('count'), 1) and all(
            type(row.get(key)) in (int, float) and math.isfinite(row[key]) and row[key] >= 0
            for key in ('p50', 'p95', 'p99')), 'M7_CAPACITY_NOT_MEASURED')
    progress_measurement(cell,expected,evidence)
    for phase, window in windows.items():
        groups = inventory['windows'][phase]
        need(isinstance(groups, dict) and set(BASE_COMPONENTS) <= set(groups) and set(groups) <= set(BASE_COMPONENTS) | {'vault-agent', 'other'} and all(
            isinstance(names, list) and names and len(set(names)) == len(names) and
            all(isinstance(name, str) and NAME.fullmatch(name) for name in names) for names in groups.values()), 'M7_ROLE_POLICY')
        need(len(groups['api']) == cell['replicas'] and set(groups.get('vault-agent', [])).isdisjoint(groups['vault']), 'M7_ROLE_POLICY')
        roles = window.get('roles', {})
        required_roles = {name for names in groups.values() for name in names}
        need(isinstance(roles, dict) and set(roles) == required_roles, 'M7_CAPACITY_ROLE_INVENTORY')
        seconds = 60 if phase == 'idle-disabled' else campaign_contract().CADENCE[profile][phase + 'Seconds']
        need(type(window.get('seconds')) in (int, float) and math.isfinite(window['seconds']) and window['seconds'] >= seconds, 'M7_CAPACITY_NOT_MEASURED')
        for row in roles.values():
            need(isinstance(row, dict) and row.get('counterReset') is False, 'M7_ROLE_METRIC')
            metrics = ('cpuUsecDelta', 'cpuCoresMean', 'cpuMsPerTenantMinute', 'anonBytesAfter', 'memoryCurrentBytesAfter', 'anonBytesPerTenant')
            if phase != 'idle-disabled':
                need(integer(row.get('sampleCount'), 1), 'M7_ROLE_METRIC')
                metrics += ('cpuPctMean', 'cpuPctMax', 'dockerMemoryBytesMax')
            need(all(type(row.get(key)) in (int, float) and math.isfinite(row[key]) and row[key] >= 0 for key in metrics), 'M7_ROLE_METRIC')
            # Producer retains docker top -eo pid,comm,rss, not a numeric RSS scalar.
            rss = row.get('processRssKiBAfter')
            need(isinstance(rss, str), 'M7_RSS_OBSERVATION')
            lines = rss.strip().splitlines()
            need(len(lines) >= 2 and lines[0].split() == ['PID', 'COMMAND', 'RSS'] and all(
                re.fullmatch(r'\s*[0-9]+\s+.+?\s+[0-9]+\s*', line) for line in lines[1:]), 'M7_RSS_OBSERVATION')


def check_ladder(expected, receipt, evidence, pilot=False):
    contract = campaign_contract()
    document = evidence.json(receipt['pilot' if pilot else 'capacity'])
    if pilot:
        replicas = expected.get('pilotReplicas')
        need(type(replicas) is int and replicas in contract.REPLICAS, 'M7_PILOT_REPLICA_PIN')
        need(document.get('kind') == 'm7-joined-remote-pilot' and isinstance(document.get('cells'), list) and
             len(document['cells']) == len(contract.PILOT_COUNTS) and
             {(r.get('tenants'), r.get('replicas')) for r in document['cells']} == {(n, replicas) for n in contract.PILOT_COUNTS}, 'M7_PILOT_MISSING_CELL')
    else:
        # Producer contract loads its fixed helper lazily. Keep resolution
        # scoped to this read-only invocation, without importing from a peer cwd.
        saved_path=sys.path[:]
        try:
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mt-bench/m7-joined'))
            contract.campaign_check(document)
        finally:sys.path[:]=saved_path
    for field, value in expected['identity'].items():
        need(document.get(field) == value, 'M7_CAPACITY_IDENTITY')
    need(document.get('profileSelection')==expected.get('profileSelection') and expected.get('profileSelection') is not None,'M7_PROFILE_SELECTION_MISMATCH')
    for cell in document['cells']:
        cell_measurement(cell, expected, 'remote-pilot' if pilot else 'capacity', document['hostIdentity'],evidence)
        need(cell['verdict'] == 'PASS', 'M7_CAPACITY_TARGET_NOT_PASSING')


def check_milestone(expected, receipt, evidence, api_scaling=False):
    specification = expected.get('capacityMilestone')
    need(isinstance(specification, dict) and set(specification) == {'tenants', 'replicas', 'profile', 'hostIdentity', 'comparisons'}, 'M7_MILESTONE_SPEC')
    contract = campaign_contract()
    target = (specification['tenants'], specification['replicas'])
    need(type(target[0]) is int and target[0] in contract.COUNTS and type(target[1]) is int and target[1] in contract.REPLICAS and
         specification['profile'] == 'capacity', 'M7_MILESTONE_TARGET')
    comparisons = specification['comparisons']
    need(isinstance(comparisons, list) and comparisons and len(comparisons) <= 128, 'M7_MILESTONE_COMPARISONS')
    required = []
    for row in comparisons:
        need(isinstance(row, dict) and set(row) == {'tenants', 'replicas'} and type(row['tenants']) is int and row['tenants'] in contract.COUNTS and
             type(row['replicas']) is int and row['replicas'] in contract.REPLICAS, 'M7_MILESTONE_COMPARISONS')
        required.append((row['tenants'], row['replicas']))
    need(len(set(required)) == len(required) and target in required, 'M7_MILESTONE_COMPARISONS')
    if api_scaling:
        need({(target[0], replicas) for replicas in contract.REPLICAS} <= set(required), 'M7_API_SCALING_COMPARISONS')
    references = receipt.get('milestoneCells')
    need(isinstance(references, list) and len(references) == len(required), 'M7_MILESTONE_MISSING_CELL')
    cells = {}
    for reference in references:
        cell = evidence.json(reference)
        cell_measurement(cell, expected, specification['profile'], specification['hostIdentity'],evidence)
        key = (cell['tenants'], cell['replicas'])
        need(key in required and key not in cells, 'M7_MILESTONE_CELL_SELECTION')
        cells[key] = cell
    need(set(cells) == set(required), 'M7_MILESTONE_MISSING_CELL')
    need(cells[target]['verdict'] == 'PASS', 'M7_CAPACITY_TARGET_NOT_PASSING')


def validate(expected, receipt, evidence, scope='acceptance'):
    need(scope in ('acceptance', 'pilot', 'capacity-milestone', 'api-scaling', 'full-ladder', 'scaling'), 'M7_SCOPE')
    need(isinstance(expected, dict) and isinstance(receipt, dict), 'M7_DOCUMENT_SHAPE')
    claims = receipt.get('claims')
    need(isinstance(claims, list) and len(set(claims)) == len(claims) and set(claims) <= {'acceptance', 'pilot', 'capacity-milestone', 'api-scaling', 'full-ladder', 'scaling'} and
         'acceptance' in claims and scope in claims and ('scaling' not in claims or 'api-scaling' in claims) and ('api-scaling' not in claims or 'capacity-milestone' in claims), 'M7_CLAIM_MISSING')
    need(isinstance(expected.get('artifacts'), dict) and 1 <= len(expected['artifacts']) <= 256 and
         all(isinstance(k, str) and isinstance(v, str) and DIGEST.fullmatch(v) for k, v in expected['artifacts'].items()), 'M7_EXPECTED_ARTIFACTS')
    evidence.allowed = expected['artifacts']
    check_acceptance(expected, receipt, evidence)
    if 'pilot' in claims:
        check_ladder(expected, receipt, evidence, pilot=True)
    if 'full-ladder' in claims:
        check_ladder(expected, receipt, evidence)
    if 'capacity-milestone' in claims:
        check_milestone(expected, receipt, evidence, api_scaling='api-scaling' in claims)
    if 'scaling' in claims:
        need(set(expected.get('scaling', {})) == set(COMPONENTS) and set(receipt.get('scaling', {})) == set(COMPONENTS), 'M7_SCALING_COMPONENTS')
        for component in COMPONENTS:
            specification = expected['scaling'][component]
            fields = {'proof', 'observations'} | ({'agentRoles'} if component == 'vault-agent' else set())
            need(isinstance(specification, dict) and set(specification) == fields, 'M7_SCALING_SPEC')
            check_proof(specification['proof'], receipt['scaling'][component], evidence)
            document = evidence.json(receipt['scaling'][component]['artifact'])
            observations = specification['observations']
            need(isinstance(observations, list) and 2 <= len(observations) <= 32, 'M7_SCALING_OBSERVATIONS')
            configurations = []
            for observation in observations:
                fields = {'configuration', 'samples', 'metrics'} | ({'roles'} if component == 'vault-agent' else set())
                need(isinstance(observation, dict) and set(observation) == fields, 'M7_SCALING_OBSERVATIONS')
                if component == 'vault-agent':
                    agent_roles = specification['agentRoles']
                    vault_roles = {name for inventory in expected.get('capacityInventories', {}).values() for group in inventory.get('windows', {}).values() for name in group.get('vault', [])}
                    need(isinstance(agent_roles, list) and agent_roles and len(set(agent_roles)) == len(agent_roles) and all(isinstance(name, str) and NAME.fullmatch(name) for name in agent_roles) and set(agent_roles).isdisjoint(vault_roles), 'M7_AGENT_ROLE_POLICY')
                    observed = pointer(document, observation['roles'])
                    need(isinstance(observed, dict) and set(agent_roles) <= set(observed), 'M7_AGENT_OVERLAY_UNMEASURED')
                    prefixes = tuple(observation['roles'] + '/' + name + '/' for name in agent_roles)
                    need(isinstance(observation['samples'], str) and observation['samples'].startswith(prefixes) and all(isinstance(selector, str) and selector.startswith(prefixes) for selector in observation['metrics']), 'M7_AGENT_METRIC_ATTRIBUTION')
                configuration = pointer(document, observation['configuration'])
                need((isinstance(configuration, str) and configuration.strip()) or
                     (type(configuration) in (int, float) and math.isfinite(configuration)), 'M7_SCALING_CONFIGURATION')
                configurations.append(json.dumps(configuration))
                need(integer(pointer(document, observation['samples']), 1), 'M7_SCALING_UNMEASURED')
                metrics = observation['metrics']
                need(isinstance(metrics, dict) and metrics, 'M7_SCALING_METRICS')
                for selector, units in metrics.items():
                    value = pointer(document, selector)
                    need(type(value) in (int, float) and math.isfinite(value) and isinstance(units, str) and units.strip(), 'M7_SCALING_UNMEASURED')
            need(len(set(configurations)) == len(configurations), 'M7_SCALING_DUPLICATE_CONFIGURATION')
        bindings = evidence.json(receipt['bindings'])
        need(bindings.get('complete') is True and isinstance(bindings.get('entries'), list), 'M7_BINDING_INVENTORY')
        need(bindings.get('pair') == expected['identity']['pair'], 'M7_BINDING_SOURCE')
        for row in bindings['entries']:
            need(isinstance(row, dict) and row.get('component') in COMPONENTS and isinstance(row.get('file'), str) and row['file'] and
                 integer(row.get('line'), 1) and isinstance(row.get('finding'), str) and row['finding'], 'M7_BINDING_FINDING')
    result = {'scope': scope, 'verifiedClaims': claims, 'kind': 'RECORDED_EVIDENCE_ONLY'}
    if 'capacity-milestone' in claims:
        result['capacityTarget'] = {key: expected['capacityMilestone'][key] for key in ('tenants', 'replicas', 'profile')}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path)
    parser.add_argument('--scope', choices=('acceptance', 'pilot', 'capacity-milestone', 'api-scaling', 'full-ladder', 'scaling'), default='acceptance')
    options = parser.parse_args()
    try:
        result = validate(read_json(options.expected), read_json(options.receipt), Evidence(options.evidence_root or options.receipt.parent), options.scope)
        print('PASS ' + json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, IndexError) as error:
        code = str(error)
        print('REFUSED ' + (code if re.fullmatch(r'M7_[A-Z0-9_]+', code) else 'M7_RECEIPT_INVALID'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
