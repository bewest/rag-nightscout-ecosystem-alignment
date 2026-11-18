"""Read the owner-selected receipt and verify the independent build and delivery evidence."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ACK_BUDGET = 'pgstreamNotifierAckTimeoutMs'
ACK_PACKAGE = ('scripts/producer_ack_publish.py', 'scripts/producer_wire.py')


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


def source(manifest):
    require(manifest['version'] == 1 and manifest['kind'] == 'k8s-frozen-experiment', 'MANIFEST')
    src = read_ref(manifest['sourceReceipt'])
    build_ref = manifest['buildReceipt']
    build = read_ref(build_ref)
    require(build.get('status') == 'BUILT_VERIFIED_LOCAL' and build.get('schemaVersion') == 1, 'BUILD_RECEIPT')
    pair = dict(core=build['coreCommit'], deploy=build['deployCommit'])
    require(all(re.fullmatch('[0-9a-f]{40}', x) for x in (*pair.values(), manifest['bindingCommit'])), 'SOURCE_ID')
    image = build['localImageId']
    producer = build['runtime']['binarySha256']
    require(re.fullmatch('sha256:[0-9a-f]{64}', image) and re.fullmatch('[0-9a-f]{64}', producer)
            and build['runtime']['producerHelpSucceeded'] is True and
            build['labels']['org.opencontainers.image.revision'] == pair['core'] and
            build['labels']['org.nightscout.deploy.revision'] == pair['deploy'], 'BUILD_IDENTITY')
    require(src.get('imageId') == image and src.get('capacityAcceptance') == 'NOT_GRANTED', 'SOURCE_IMAGE')
    if src.get('kind') == 'joined-acceptance' and src.get('status') == 'PASS':
        require(src['pair'] == pair and src['producer']['binarySha256'] == producer and
                src['producer']['bindingDeploy'] == pair['deploy'], 'SOURCE_PAIR')
        evidence = read_ref(dict(path=src['evidence'], sha256=src['evidenceSha256']))
        require(evidence['kind'] == 'source-acceptance-evidence-v1' and
                build_ref['sha256'] in evidence['files'].values(), 'SOURCE_BUILD_LINK')
        status = 'PASS'
    else:
        require((src.get('status'), src.get('sourceAcceptance')) in
                (('FROZEN_DIAGNOSTIC_ONLY', 'PENDING'), ('FROZEN_LOCAL_CANDIDATE', 'PENDING')), 'SOURCE_RECEIPT')
        selected = src.get('pair') or dict(core=src['coreCommit'], deploy=src['deployCommit'])
        require(selected == pair and src['imageReceiptSha256'] == build_ref['sha256'], 'SOURCE_PAIR')
        status = 'PENDING'
    tier = manifest.get('tier', 'discovery')
    require(tier in ('smoke','discovery','acceptance'), 'TIER')
    require(tier != 'acceptance' or status == 'PASS' and 'bootstrapHelper' not in manifest,
            'FROZEN_ACCEPTANCE_REQUIRED')
    chosen = dict(coreCommit=pair['core'], deployCommit=pair['deploy'], localImageId=image,
                producerBinarySha256=producer, diagnosticSha256=manifest['sourceReceipt']['sha256'],
                imageReceiptSha256=build_ref['sha256'], sourceAcceptance=status)
    if 'bootstrapHelper' in manifest:
        require(pair['deploy'] == BOOTSTRAP_BASE and manifest['bootstrapHelper'] == BOOTSTRAP_HELPER,
                'BOOTSTRAP_HELPER_UNSUPPORTED')
        chosen.update(imageSourceAcceptance=status, sourceAcceptance='PENDING',
                      runtimeBootstrapHelper={**BOOTSTRAP_HELPER, 'baseSha256': BOOTSTRAP_ORIGINAL,
                                              'sourcePath': BOOTSTRAP_PATH, 'mountPath': BOOTSTRAP_TARGET})
    if ACK_BUDGET in manifest:
        budget = manifest[ACK_BUDGET]
        require(tier == 'discovery' and type(budget) is int and 0 < budget <= (2**63 - 1) // 1_000_000,
                'PGSTREAM_ACK_BUDGET')
        chosen[ACK_BUDGET] = budget
    return chosen


def contract(manifest, observed):
    chosen = source(manifest)
    require(all(observed.get(k) == v for k, v in chosen.items()), 'CONTRACT_SOURCE_CHANGED')
    require(all((key in observed) == (key in chosen) for key in ('runtimeBootstrapHelper','imageSourceAcceptance')),
            'BOOTSTRAP_HELPER_UNDECLARED')
    require((ACK_BUDGET in observed) == (ACK_BUDGET in chosen), 'PGSTREAM_ACK_UNDECLARED')
    if 'bootstrapHelper' in manifest:
        require(observed.get('sourceFilesSha256', {}).get('bootstrap.js') == BOOTSTRAP_ORIGINAL, 'BOOTSTRAP_BASE_CHANGED')
    require(re.fullmatch('[a-f0-9]{64}', observed['nativeCatalogueSha256']), 'CATALOGUE_ID')
    return chosen


def registry(receipt, images, manifest):
    selected = source(manifest)
    require((receipt['sourceCommit'], receipt['imageDeployCommit'], receipt['appImageId']) ==
            (selected['coreCommit'], selected['deployCommit'], selected['localImageId']), 'DELIVERY_SOURCE')
    require(receipt['registryPlanChange'] is False and receipt['transferCostApproved'] is True,
            'DELIVERY_AUTHORITY')
    for name in ('app', 'postgres'):
        image = images[name]
        require(re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', image) and receipt[name] == image, 'REGISTRY_REFERENCE')
        # The digest covers the exact registry response bytes, including whitespace.
        obj = read_ref(dict(path=receipt['registryManifests'][name], sha256=image.split('@sha256:')[1]))
        require(obj.get('schemaVersion') == 2 and obj.get('mediaType') in
                ('application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json'),
                'REGISTRY_SINGLE_PLATFORM_MANIFEST_REQUIRED')
        expected = selected['localImageId'] if name == 'app' else manifest['postgresImageId']
        require(re.fullmatch('sha256:[a-f0-9]{64}', expected) and
                obj.get('config', {}).get('digest') == receipt[name+'ImageId'] == expected, 'REGISTRY_CONFIG_CHANGED')


def rendered_contract(manifest, raw, binding_ref):
    binding = read_ref(binding_ref)
    require(binding.get('bindingCommit') == manifest['bindingCommit'] and
            binding.get('sourceContractSha256') == digest(raw.encode()) ==
            binding['files']['assets/source-contract.json'], 'BINDING_CONTRACT_CHANGED')
    selected = contract(manifest, json.loads(raw))
    require(binding['files'].get('assets/bootstrap-helper.js') == selected.get('runtimeBootstrapHelper', {}).get('sha256'),
            'BOOTSTRAP_HELPER_PACKAGE_CHANGED')
    require(all((name in binding['files']) == (ACK_BUDGET in selected) for name in ACK_PACKAGE),
            'PGSTREAM_ACK_PACKAGE_CHANGED')
    return selected


# Only the independently controlled registry-client lifetime correction is supported.
BOOTSTRAP_PATH = 'bindings/compose/multitenant/bootstrap.js'
BOOTSTRAP_TARGET = '/opt/app/deploy/multitenant/bootstrap.js'
BOOTSTRAP_BASE = '49db85682482d5fa8b304a3a9ffaf3cb0980ec05'
BOOTSTRAP_ORIGINAL = '9b956ca77526358640c87d7ac8b2351ecd72c6b01921bad05fa28a4c22cc6a26'
BOOTSTRAP_HELPER = dict(deployCommit='c1961d23b917928c3fde6103e60d195ba280d315',
                        sha256='0955c71bde6936401888a634c8f9da3ac68c545dc397bba8b2045b135f3af2c3')
HELPER_MAP = 'bootstrap-diagnostic'
HELPER_ANNOTATIONS = {'nightscout.org/bootstrap-helper-commit': BOOTSTRAP_HELPER['deployCommit'],
                      'nightscout.org/bootstrap-helper-sha256': BOOTSTRAP_HELPER['sha256'],
                      'nightscout.org/instance-acceptance': 'PENDING'}



def compatible_deployment_inputs(manifest, expected, measured):
    if expected == measured:
        return True
    # The previously controlled registry-admin lifetime correction can be
    # embedded in the selected build. Every other binding asset stays exact.
    return ('bootstrapHelper' not in manifest and expected.get('bootstrap.js') == BOOTSTRAP_ORIGINAL
            and measured == {**expected, 'bootstrap.js': BOOTSTRAP_HELPER['sha256']})


def bootstrap_readback(selected, actual, created, namespace, run_id):
    helper = selected.get('runtimeBootstrapHelper')
    if helper is None:
        require(actual is None, 'BOOTSTRAP_HELPER_UNDECLARED')
        return {'mode': 'embedded-image', 'effectiveInstanceAcceptance': selected['sourceAcceptance']}
    require(actual is not None, 'BOOTSTRAP_HELPER_MISSING')
    metadata = actual.get('metadata', {})
    expected = [row['uid'] for row in created if row['kind'] == 'ConfigMap' and row['name'] == HELPER_MAP]
    data = actual.get('data', {})
    require(len(expected) == 1 and metadata.get('uid') == expected[0] and
            metadata.get('namespace') == namespace and metadata.get('labels', {}).get('nightscout.org/run-id') == run_id,
            'BOOTSTRAP_HELPER_OWNERSHIP')
    require(actual.get('immutable') is True and set(data) == {'bootstrap.js'} and
            not actual.get('binaryData') and isinstance(data['bootstrap.js'], str) and
            digest(data['bootstrap.js'].encode()) == helper['sha256'], 'BOOTSTRAP_HELPER_CHANGED')
    return {'mode': 'diagnostic-overlay', 'uid': expected[0], 'resourceVersion': metadata['resourceVersion'],
            'sha256': helper['sha256'], 'imageSourceAcceptance': selected['imageSourceAcceptance'],
            'effectiveInstanceAcceptance': selected['sourceAcceptance']}


def install_bootstrap_helper(manifest, deploy_repo, package, measured):
    if 'bootstrapHelper' not in manifest:
        return
    selected = source(manifest)
    revision = selected['runtimeBootstrapHelper']['deployCommit']
    def git(*args):
        return subprocess.check_output(['git', '-C', deploy_repo, *args], timeout=20)
    require(git('rev-parse', revision+'^').decode().strip() == selected['deployCommit'] and
            measured['sourceFilesSha256']['bootstrap.js'] == BOOTSTRAP_ORIGINAL and
            digest(git('show', selected['deployCommit']+':'+BOOTSTRAP_PATH)) == BOOTSTRAP_ORIGINAL,
            'BOOTSTRAP_BASE_CHANGED')
    corrected = git('show', revision+':'+BOOTSTRAP_PATH)
    require(digest(corrected) == selected['runtimeBootstrapHelper']['sha256'], 'BOOTSTRAP_HELPER_CHANGED')
    with (package/'assets/bootstrap-helper.js').open('xb') as output:
        output.write(corrected)


def check_bootstrap_render(manifest, objects):
    """Bind the mounted executable, its source, and its only consumer, including legacy absence."""
    objects = list(objects)
    enabled = 'bootstrapHelper' in manifest
    configs = [o for o in objects if o['kind'] == 'ConfigMap' and o['metadata']['name'] == HELPER_MAP]
    require(len(configs) == int(enabled), 'BOOTSTRAP_HELPER_CONFIGMAP')
    if enabled:
        selected = source(manifest)
        data = configs[0].get('data', {})
        require(configs[0].get('immutable') is True and set(data) == {'bootstrap.js'} and
                not configs[0].get('binaryData') and isinstance(data['bootstrap.js'], str) and
                digest(data['bootstrap.js'].encode()) == selected['runtimeBootstrapHelper']['sha256'],
                'BOOTSTRAP_HELPER_CHANGED')
    consumers, volumes = [], []
    for obj in objects:
        meta = obj['metadata']
        job = obj['kind'] == 'Job' and meta['name'] == 'provision'
        pod = obj.get('spec', {}).get('template', {})
        for metadata in (meta, pod.get('metadata', {}) if pod else None):
            if metadata is None:
                continue
            found = {k:v for k,v in metadata.get('annotations',{}).items() if k in HELPER_ANNOTATIONS}
            require(found == (HELPER_ANNOTATIONS if enabled and (job or obj in configs) else {}),
                    'BOOTSTRAP_HELPER_ANNOTATIONS')
        spec = pod.get('spec', {})
        for volume in spec.get('volumes', []):
            source_map = volume.get('configMap', {}).get('name')
            projected = any(row.get('configMap', {}).get('name') == HELPER_MAP
                            for row in volume.get('projected', {}).get('sources', []))
            if volume['name'] == HELPER_MAP or source_map == HELPER_MAP or projected:
                require(enabled and job and volume == {'name': HELPER_MAP, 'configMap': {
                    'name': HELPER_MAP, 'defaultMode':292}},
                    'BOOTSTRAP_HELPER_VOLUME')
                volumes.append(meta['name'])
        for section in ('containers','initContainers','ephemeralContainers'):
            for container in spec.get(section, []):
                for mount in container.get('volumeMounts', []):
                    target = Path(mount['mountPath'])
                    if mount.get('name') != HELPER_MAP and target not in (Path(BOOTSTRAP_TARGET), *Path(BOOTSTRAP_TARGET).parents):
                        continue
                    require(enabled and job and section == 'initContainers' and container['name'] == 'bootstrap' and
                            container.get('command') == ['node','deploy/multitenant/bootstrap.js'] and not container.get('args') and
                            container.get('workingDir','/opt/app') == '/opt/app' and
                            mount == dict(name=HELPER_MAP,subPath='bootstrap.js',mountPath=BOOTSTRAP_TARGET,readOnly=True),
                            'BOOTSTRAP_HELPER_MOUNT')
                    consumers.append(meta['name'])
    require(len(consumers) == len(volumes) == int(enabled), 'BOOTSTRAP_HELPER_CENSUS')
    if enabled:
        job = next(o for o in objects if o['kind'] == 'Job' and o['metadata']['name'] == 'provision')
        metadata = (configs[0]['metadata'], job['metadata'], job['spec']['template']['metadata'])
        owners = [m.get('labels', {}).get('nightscout.org/run-id') for m in metadata]
        require(metadata[0]['namespace'] == metadata[1]['namespace'] and owners[0] and owners[0] == owners[1] == owners[2],
                'BOOTSTRAP_HELPER_OWNERSHIP')
