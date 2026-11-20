"""Read the run's candidate (image references, digests and labelled commits) and its selected options.

Run identity is the alignment commit, the image digests and the run configuration
(decision `brittle-check-removal`); no source, build or delivery receipt is read.
"""
import hashlib
import json
from pathlib import Path
import re
import primer_options
import population_ceiling

ACK_BUDGET = 'pgstreamNotifierAckTimeoutMs'
ACK_PACKAGE = ('scripts/producer_ack_publish.py', 'scripts/producer_wire.py')
PRIMER_STORAGE = 'primerStorage'
PRIMER_STORAGE_PACKAGE = 'scripts/primer_storage.py'
JOB_COMPLETE = 'provisionJobCompleteSeconds'


class Refused(ValueError):
    verdict = 'FAIL'


def require(ok, code):
    if not ok:
        raise Refused('K8S_EXPERIMENT_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_ref(ref):
    path = Path(ref['path'])
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'EVIDENCE_MISSING')
    raw = path.read_bytes()
    require(digest(raw) == ref['sha256'], 'EVIDENCE_CHANGED')
    return json.loads(raw)


CANDIDATE = ('app', 'appImageId', 'postgres', 'postgresImageId', 'coreCommit', 'deployCommit')


def candidate(manifest):
    value = manifest.get('candidate')
    require(isinstance(value, dict) and set(CANDIDATE) <= set(value)
            and all(re.fullmatch('[0-9a-f]{40}', value[k] or '') for k in ('coreCommit', 'deployCommit'))
            and all(re.fullmatch('sha256:[0-9a-f]{64}', value[k] or '') for k in ('appImageId', 'postgresImageId'))
            and all(isinstance(value[k], str) and re.search('@sha256:[0-9a-f]{64}$', value[k]) for k in ('app', 'postgres')),
            'CANDIDATE')
    return value


def source(manifest):
    require(manifest['version'] == 1 and manifest['kind'] == 'k8s-frozen-experiment', 'MANIFEST')
    selected = candidate(manifest)
    require(re.fullmatch('[0-9a-f]{40}', manifest.get('bindingCommit') or ''), 'SOURCE_ID')
    tier = manifest.get('tier', 'discovery')
    require(tier in ('smoke','discovery','acceptance'), 'TIER')
    # No receipt can label a source PASS; acceptance needs its own frozen record.
    status = 'PENDING'
    require(tier != 'acceptance', 'FROZEN_ACCEPTANCE_REQUIRED')
    chosen = dict(coreCommit=selected['coreCommit'], deployCommit=selected['deployCommit'],
                  localImageId=selected['appImageId'], sourceAcceptance=status)
    if ACK_BUDGET in manifest:
        budget = manifest[ACK_BUDGET]
        require(tier == 'discovery' and type(budget) is int and 0 < budget <= (2**63 - 1) // 1_000_000,
                'PGSTREAM_ACK_BUDGET')
        chosen[ACK_BUDGET] = budget
    if PRIMER_STORAGE in manifest:
        storage = manifest[PRIMER_STORAGE]
        require(tier == 'discovery' and isinstance(storage, dict) and set(storage)=={'stateMiB','secretCodec'}
                and type(storage['stateMiB']) is int and 0 < storage['stateMiB'] <= (2**53-1)//1048576
                and storage['secretCodec'] in ('raw-v1','gzip-v1'), 'PRIMER_STORAGE_SELECTION')
        chosen[PRIMER_STORAGE] = storage
    primer = primer_options.from_profile(manifest.get('profile',{}), require)
    population=population_ceiling.from_profile(manifest.get('profile',{}),require)
    if population is not None:
        require(tier=='discovery','POPULATION_DISCOVERY_ONLY')
        chosen[population_ceiling.FIELD]=population
    if primer is not None:
        require(tier == 'discovery', 'PRIMER_OPTIONS_DISCOVERY_ONLY')
        chosen[primer_options.FIELD] = primer
    startup = manifest.get('profile',{}).get('phases',{}).get('startupWindows',{}).get('kubernetes',{})
    if 'jobCompleteSeconds' in startup:
        seconds=startup['jobCompleteSeconds']
        require(type(seconds) is int and 1<=seconds<=(2**63-1)//1000000000,'STARTUP_JOB_COMPLETE_WINDOW')
        chosen[JOB_COMPLETE]=seconds
    return chosen


PROVENANCE = frozenset(('coreCommit', 'deployCommit', 'sourceAcceptance', 'imageSourceAcceptance'))


def contract(manifest, observed):
    chosen = source(manifest)
    # Run identity is the image digest plus the run configuration. Receipt
    # provenance (commits, receipt hashes, acceptance words) is recorded, not compared.
    require(all(observed.get(k) == v for k, v in chosen.items() if k not in PROVENANCE), 'CONTRACT_CONFIGURATION_CHANGED')
    require((ACK_BUDGET in observed) == (ACK_BUDGET in chosen), 'PGSTREAM_ACK_UNDECLARED')
    require((PRIMER_STORAGE in observed) == (PRIMER_STORAGE in chosen), 'PRIMER_STORAGE_UNDECLARED')
    require((JOB_COMPLETE in observed) == (JOB_COMPLETE in chosen),'STARTUP_JOB_COMPLETE_UNDECLARED')
    require((primer_options.FIELD in observed) == (primer_options.FIELD in chosen), 'PRIMER_OPTIONS_UNDECLARED')
    require(observed.get(population_ceiling.FIELD)==chosen.get(population_ceiling.FIELD),'POPULATION_CEILING_CHANGED')
    if population_ceiling.FIELD in chosen:
        require(observed.get(population_ceiling.PROTOCOL_FIELD)==population_ceiling.PROTOCOL,'POPULATION_SOURCE_UNSUPPORTED')
    if primer_options.PROTOCOL_FIELD in observed:
        require(observed[primer_options.PROTOCOL_FIELD] == primer_options.PROTOCOL and
                re.fullmatch('[a-f0-9]{64}', observed.get('sourceFilesSha256', {}).get('prime.js', '')),
                'PRIMER_OPTION_SOURCE_UNSUPPORTED')
    if primer_options.FIELD in chosen:
        primer_options.require_source(chosen[primer_options.FIELD], observed.get(primer_options.PROTOCOL_FIELD), require)
    require(re.fullmatch('[a-f0-9]{64}', observed['nativeCatalogueSha256']), 'CATALOGUE_ID')
    return chosen

