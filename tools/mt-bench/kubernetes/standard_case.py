"""Materialize one standard discovery point using the selected deploy binding.

Run identity is the alignment commit, the candidate image references and digests,
and this run configuration (decision `brittle-check-removal`). There is no
delivery, source or build receipt and no captured binding: the binding is the
deploy checkout as selected, and the candidate images are run parameters.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import experiment
import fixture_copy
import frozen
import kube_adapter as k
import lifecycle_config as lc
import native_join


NAMESPACE_PREFIX = 'ns-synth-'
# DigitalOcean Kubernetes node-pool label: the pool selector for a multi-node layout.
POOL_LABEL = 'doks.digitalocean.com/node-pool'


def resolve_image(reference, inspect=None):
    """A digest-qualified image reference, its local image id and its labelled revisions."""
    k.need(isinstance(reference, str) and re.search('@sha256:[0-9a-f]{64}$', reference), 'STANDARD_IMAGE_DIGEST_REQUIRED')
    inspect = inspect or (lambda ref: json.loads(subprocess.check_output(['docker', 'image', 'inspect', ref], timeout=30))[0])
    spec = inspect(reference)
    labels = (spec.get('Config') or {}).get('Labels') or {}
    return {'reference': reference, 'imageId': spec['Id'],
            'core': labels.get('org.opencontainers.image.revision'), 'deploy': labels.get('org.nightscout.deploy.revision')}


def fixture_key(template_case, profile_path, *, app_image, postgres_image=None, core=None, binding_extra=None,
                seed='default', inspect=None):
    """The fixture key of the case `prepare` would materialize from the same inputs."""
    import fixture_catalog
    template_case = template_case.resolve()
    profile = k.document(profile_path)
    control = k.document(template_case/'lifecycle-input.json')
    inputs = k.document(template_case/'binding-inputs.json')
    if binding_extra:
        inputs.update(k.document(Path(binding_extra)))
    app = resolve_image(app_image, inspect)
    postgres = resolve_image(postgres_image or inputs['images']['postgres'], inspect)
    k.need(app['core'], 'FIXTURE_IMAGE_CORE_REVISION_REQUIRED')
    return fixture_catalog.key(
        tenants=profile['population']['provisionedTenants'], image=app['imageId'], postgres_image=postgres['imageId'],
        schema=fixture_catalog.schema((core or Path(control['coreRepository'])).resolve(), app['core']),
        transport=inputs.get('inputTransport', 'pgstream'), seed=seed, history=profile.get('history'),
        evaluator_slices=inputs.get('slices', {}).get('evaluator', 1))


def point_profiles(first, following):
    """Select workloads that can run against the same commissioned database and roles."""
    profiles = [first, *(k.document(path) for path in following)]
    if not following:
        return profiles
    seen = set()
    for profile in profiles:
        experiment.profile.validate(profile, require_pins=False)
        point = profile['workload'].get('pointId')
        k.need(isinstance(point, str) and len(point) <= 31 and k.NAME.fullmatch(point), 'WORKLOAD_POINT_ID')
        k.need(point not in seen, 'DUPLICATE_WORKLOAD_POINT')
        seen.add(point)
        k.need(profile['population']['provisionedTenants'] == first['population']['provisionedTenants']
               and profile['history'] == first['history'], 'WORKLOAD_POINT_FIXTURE_CHANGED')
        # The data primer and serving roles start once, before all traffic points.
        for field in ('primerOptions', 'producerStartup', 'startupWindows', 'cohortReadySeconds'):
            k.need(profile['phases'].get(field) == first['phases'].get(field), 'WORKLOAD_POINT_STARTUP_CHANGED')
        k.need(profile['population'].get('maxTenants') == first['population'].get('maxTenants'),
               'WORKLOAD_POINT_POPULATION_CEILING_CHANGED')
    return profiles


def prepare_points(case, profiles, instance):
    # The native Job includes the generated offer. Only its declaration varies per point.
    manifest = k.document(case/'intent.json')
    template = k.document(case/'native-run-template.json')
    preflight = k.document(case/'preflight.json')
    for profile in profiles:
        point = case/'points'/profile['workload']['pointId']
        point.mkdir(parents=True, mode=0o700)
        intent = dict(manifest, profile=profile)
        run = dict(template, workload=profile['workload'])
        k.write(point/'intent.json', intent)
        k.write(point/'native-run-template.json', run)
        k.write(point/'render.json', native_join.point_render(case, intent, run))
        source = dict(instance, config=str(point/'native-run-template.json'), render=str(point/'render.json'))
        experiment.prepare(point/'intent.json', source, point/'offline-final', await_primer=True)
        identity = dict(preflight['experiment'], experimentSha256=k.digest(point/'intent.json'),
                        renderSha256=k.digest(point/'render.json'))
        k.write(point/'preflight.json', dict(preflight, experiment=identity))


def keyed(action, template_case, binding, profile_path, output, *, seed='default', catalog=None,
          storage_class=None, snapshot_class=None, postgres_size=None, launch=None, **options):
    """Find the fixture by key. `reuse` restores it into the case at OUTPUT, building and registering
    it first on a miss (the seed case is OUTPUT-seed); `build` only builds and registers (case OUTPUT)."""
    import fixture_catalog
    k.need(action in ('reuse', 'build'), 'FIXTURE_ACTION')
    output = output.resolve()
    catalog = catalog or fixture_catalog.Catalog()
    key = fixture_key(template_case, profile_path, seed=seed, **{name: options.get(name) for name in
                      ('app_image', 'postgres_image', 'core', 'binding_extra', 'inspect')})
    following = options.get('next_points') or []
    if following:
        k.need(action == 'reuse', 'WORKLOAD_POINTS_REQUIRE_TRAFFIC_CASE')
        point_profiles(k.document(profile_path), following)
    hit = catalog.lookup(key, 'kubernetes')
    lookup = 'hit' if hit else 'miss'
    forward = None
    if not hit and key['transport'] == 'writer-driven':
        # Look at the seed manifest only when a ready record matches all workload and database inputs.
        candidates = []
        for entry in catalog.entries().values():
            record = entry['platforms'].get('kubernetes', {})
            if record.get('status') == 'ready' and fixture_copy.same_fixture_data(entry['key'], key):
                candidates.append((record['builtAt'], entry['key']))
        if candidates:
            repository = options.get('core') or Path(k.document(template_case/'lifecycle-input.json')['coreRepository'])
            target = resolve_image(options['app_image'], options.get('inspect'))['core']
            for _, source_key in sorted(candidates, key=lambda item: item[0], reverse=True):
                record = catalog.lookup(source_key, 'kubernetes')
                if not record:
                    continue
                manifest = fixture_copy.read_manifest(record['directory'])
                k.need(manifest.get('key') == source_key and manifest['fixtureId'] == record['identity']['fixtureId'],
                       'FIXTURE_CATALOG_MANIFEST_MISMATCH')
                if fixture_copy.can_migrate_forward(repository, manifest.get('coreCommit'), target):
                    hit, lookup = record, 'forward'
                    forward = {'sourceKey': source_key, 'seededFrom': manifest['coreCommit'], 'target': target}
                    break
    if not hit:
        seed_case = output if action == 'build' else output.with_name(output.name + '-seed')
        directory = catalog.reserve(key, 'kubernetes')
        try:
            chosen = fixture_copy.selection('seed', directory, storage_class, snapshot_class, postgres_size)
            # A seed has no load stage; the writer volume is reserved for the traffic case.
            seed_options = {key: value for key, value in options.items() if key not in ('writer_publication', 'next_points')}
            prepare(template_case, binding, profile_path, seed_case, fixture={**chosen, 'key': key}, **seed_options)
            (launch or _launch)(seed_case/'lifecycle-bound.json')
            manifest = fixture_copy.read_manifest(directory)
        except BaseException as error:
            catalog.failed(key, 'kubernetes', str(error) or type(error).__name__)
            raise
        hit = catalog.register(key, 'kubernetes', {
            'fixtureId': manifest['fixtureId'], 'volumeSnapshotContents': manifest['seedContents'],
            'providerSnapshots': manifest['handles'], 'seedCase': str(seed_case)})
    if action == 'build':
        return {'fixture': lookup, 'digest': hit['digest'], 'directory': hit['directory'], 'status': hit['status'],
                **({'forward': forward} if forward else {})}
    chosen = fixture_copy.selection('restore', hit['directory'])
    return prepare(template_case, binding, profile_path, output,
                   fixture={**chosen, 'key': key, 'digest': hit['digest'], 'lookup': lookup,
                            **({'forward': forward} if forward else {})}, **options)


def _launch(bound):
    """Run a seed case to completion; it stops after the capture and sends no traffic."""
    subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('experiment.py')), 'launch', str(bound)],
                   check=True, stdout=sys.stderr)


def prepare(template_case, binding, profile_path, output, *, app_image, postgres_image=None,
            namespace_prefix=NAMESPACE_PREFIX, core=None, taint=None, inspect=None, fixture=None, node_name=None, resources_file=None, binding_extra=None,
            node_pool=None, writer_publication=None, next_points=()):
    output = output.resolve()
    inputs = (template_case, binding)
    k.need(all(not output.is_relative_to(path.resolve()) for path in inputs),
           'STANDARD_OUTPUT_INSIDE_SOURCE')
    try:
        output.mkdir(parents=True,exist_ok=False,mode=0o700)
    except FileExistsError:
        raise k.Refused('K8S_STANDARD_CASE_EXISTS','UNMEASURED') from None
    try:
        return _materialize(template_case,binding,profile_path,output,core,taint,
                            app_image,postgres_image,namespace_prefix,inspect,fixture,node_name,resources_file,binding_extra,
                            node_pool,writer_publication,next_points)
    except Exception as error:
        failed = output.with_name(output.name+'.failed-'+str(time.time_ns()))
        output.rename(failed)
        report = experiment.failure(error)
        if not report['code'].startswith(('K8S_', 'M7_')):
            report.update(code='K8S_STANDARD_PREPARATION_FAILED', cause=type(error).__name__)
            if isinstance(error, FileNotFoundError):
                report['missing'] = str(error.filename)
            if isinstance(error, subprocess.CalledProcessError):
                report.update(program=Path(error.cmd[0]).name, returncode=error.returncode)
        report.update(stage='offline preparation', liveActors=0)
        k.write(failed/'prepare-error.json',report)
        raise k.Refused(report['code'], report['verdict']) from error


def _materialize(template_case, binding, profile_path, output, core, taint,
                 app_image, postgres_image, namespace_prefix, inspect, fixture=None, node_name=None, resources_file=None, binding_extra=None,
                 node_pool=None, writer_publication=None, next_points=()):
    template_case = template_case.resolve()
    binding = binding.resolve()
    output = output.resolve()
    run_id = output.name
    # The prefix is a run parameter; ownership and cleanup use the run-id label.
    namespace = namespace_prefix + run_id
    k.need(re.fullmatch(r'[a-z0-9][a-z0-9-]*[a-z0-9]', run_id) and k.NAME.fullmatch(namespace),
           'STANDARD_CASE_NAME')
    profile = k.document(profile_path)
    profiles = point_profiles(profile, next_points)
    for point in profiles:
        point['name'] = run_id
        point.pop('proposedEnvelope', None)
    control = k.document(template_case/'lifecycle-input.json')
    core = (core or Path(control['coreRepository'])).resolve()
    prior = k.document(template_case/'intent.json')
    run = k.document(template_case/'native-run-template.json')
    binding_inputs = k.document(template_case/'binding-inputs.json')
    env = k.document(template_case/'environment.json')
    storage = binding_inputs['storage']
    k.need(storage['mode'] in ('disposable', 'existing-claim'), 'STANDARD_CASE_STORAGE')
    if fixture:
        # Reuse selected: operator-approved claims replace disposable storage.
        binding_inputs['storage'] = storage = fixture_copy.storage(storage)
    run['storageMode'] = storage['mode']
    selection = run.pop('nativeLoad')
    selection.pop('writerPublication', None)  # A volume reservation belongs to one run namespace.
    if writer_publication is not None:
        selection['writerPublication'] = k.document(writer_publication)
    resources = k.document(binding/'bindings/kubernetes/lib/ns/typical-requests.json')
    selection.pop('nodeName', None)
    selection.pop('tolerations', None)
    selection['resources'] = {'requests': resources['k6']}
    selection['exporterResources'] = {'requests': resources['artifact-exporter']}
    selection['waiterResources'] = {'requests': resources['wait-for-jobs']}
    placement = {}
    if taint:
        key, equal, value = taint.partition('=')
        k.need(equal and key and value, 'STANDARD_RESERVED_WORKER_TAINT')
        placement = {'tolerations':[{'key':key,'value':value,'operator':'Equal','effect':'NoSchedule'}]}
        selection.update(placement)
    k.need(not (node_name and node_pool), 'STANDARD_NODE_NAME_OR_POOL')
    if node_name:
        # Pin every rendered workload and the native load Job to one named node (one case per node).
        k.need(k.NAME.fullmatch(node_name), 'STANDARD_NODE_NAME')
        placement = {**placement, 'nodeSelector': {'kubernetes.io/hostname': node_name}}
        selection['nodeName'] = node_name
    elif node_pool:
        # Multi-node layout: every workload and the load Job stay on one provider pool's nodes;
        # the scheduler places them across that pool (no per-node pin).
        k.need(k.NAME.fullmatch(node_pool), 'STANDARD_NODE_POOL')
        placement = {**placement, 'nodeSelector': {POOL_LABEL: node_pool}}
        selection['nodeSelector'] = {POOL_LABEL: node_pool}
    phases = profile['phases']
    traffic = profile['workload']
    for point in profiles:
        offer = point['workload']
        grace = max(v.get('gracefulStopSeconds', 30) for v in offer['driverPlan']['scenarios'].values())
        selection['deadlineSeconds'] = max(selection['deadlineSeconds'],
                                           offer.get('setupSeconds',310) + offer['loadSeconds'] + grace + 5)
    app = resolve_image(app_image, inspect)
    postgres = resolve_image(postgres_image or binding_inputs['images']['postgres'], inspect)
    candidate = {'app': app['reference'], 'appImageId': app['imageId'],
                 'postgres': postgres['reference'], 'postgresImageId': postgres['imageId'],
                 'coreCommit': app['core'], 'deployCommit': app['deploy']}
    alignment = k.instrument()['commit']
    binding_head = subprocess.check_output(['git','-C',binding,'rev-parse','HEAD'],text=True,timeout=15).strip()
    pins = {'core': app['core'], 'deploy': app['deploy'], 'bindingCommit': binding_head}
    for point in profiles:
        k.need(point.pop('referencePins', pins) == pins, 'SOURCE_PROFILE_MISMATCH')
    retired = ('nativeLoad', 'profile', 'sourceReceipt', 'buildReceipt', 'postgresImageId', 'candidate', 'alignmentCommit')
    intent = {key: value for key, value in prior.items() if key not in retired}
    intent.update(profile=profile, candidate=candidate, alignmentCommit=alignment, bindingCommit=binding_head)
    source = frozen.source(intent)
    # Carry forward only the platform setup allowance, independently of the selected load duration.
    setup_allowance = env['workDeadlineSeconds'] - prior['profile']['phases']['workSeconds']
    outer = sum(point['phases']['workSeconds'] for point in profiles) + setup_allowance
    tenants = profile['population']['provisionedTenants']
    images = {'app': candidate['app'], 'postgres': candidate['postgres']}
    binding_inputs.pop('resources', None)
    if resources_file:
        # One-change arm: explicit per-container requests/limits for named containers.
        binding_inputs['resources'] = k.document(Path(resources_file))
    binding_inputs.pop('applicationTopology', None)
    binding_inputs['primerConcurrency'] = phases.get('primerOptions', {}).get('concurrency', control['primerConcurrency'])
    binding_inputs.update(runId=run_id, namespace=namespace, tenantCount=tenants, images=images,
                          placement=placement, placementByWorkload={}, provisionDeadlineSeconds=outer,
                          sourceCommit=source['coreCommit'], imageDeployCommit=source['deployCommit'],
                          bindingIdentity=intent['bindingCommit'],resourceAccounting='requests-v1')
    connector_share = profile['population'].get('connectorShare')
    if connector_share:
        # vcpool connector tenants (connectors/connectors.py): the binding renders the role and the
        # connector-entry Job; execute.py enters and scores them around the load window.
        binding_inputs['vcpool'] = {'enabled': True, 'allowHosts': ['nightscout-upstream'], 'allowInsecureHttp': True}
    if binding_extra:
        # Extra binding inputs (e.g. roleEnv on a binding that supports it), merged last.
        binding_inputs.update(k.document(Path(binding_extra)))
    k.write(output/'binding-inputs.json',binding_inputs)
    bundled = Path(control['toolsDirectory'])/'jsonnet-0.21.0/jsonnet'
    jsonnet = str(bundled) if bundled.is_file() else shutil.which('jsonnet')
    k.need(jsonnet, 'STANDARD_JSONNET_REQUIRED')
    for name,suffix in [('render',''),('inventory','.inventory')]:
        data = subprocess.check_output([jsonnet,'-J',binding/'bindings/kubernetes/lib','--ext-code-file',
             'INPUT='+str(output/'binding-inputs.json'),'-e','(import "ns/nightscout.libsonnet").new(std.extVar("INPUT"))'+suffix],timeout=30)
        k.write(output/(name+'.json'),json.loads(data))
    rendered = k.document(output/'render.json')
    inventory = k.document(output/'inventory.json')
    stages = {name:[] for name in lc.STAGES}
    workload_stages = {'postgres':'stores', 'vault':'stores', 'provision':'provision',
                       'admin':'private-admin', 'primer':'primer',
                       # Suspended like the primer; execute.py unsuspends it after the roster is read.
                       'connector-entry':'primer'}
    for document in (run, intent):
        document.pop('applicationTopology', None)
        document['primerLocation'] = 'claim' if inventory['results']['primer'].get('claim') else 'pod'
    transport = inventory['inputTransport']
    k.need(transport == 'writer-driven', 'INPUT_TRANSPORT')
    run['roles'].pop('pgstream', None)
    for target in run['roles'].values():
        name = target['workload'].split('/', 1)[1]
        target['workload'] = inventory['workloads'][name]['kind'] + '/' + name
    for obj in k.manifests(rendered):
        stage = {'Namespace':'namespace','ClusterRoleBinding':'cluster-trust'}.get(obj['kind'],'foundation')
        if obj['kind'] in k.WORKLOADS:
            stage = workload_stages.get(obj['metadata']['name'], 'serving')
        stages[stage].append(obj)
    (output/'stages').mkdir()
    for stage,items in stages.items():
        k.write(output/'stages'/(stage+'.json'),{'apiVersion':'v1','kind':'List','items':items})
    if fixture:
        if 'key' in fixture:
            key = fixture['key']
            if fixture.get('forward'):
                forward = fixture['forward']
                k.need(forward['target'] == app['core'] and
                       fixture_copy.can_migrate_forward(core, forward['seededFrom'], app['core']), 'FIXTURE_FORWARD_ANCESTRY')
            k.need(key['tenants'] == tenants and key['transport'] == transport and
                   key.get('evaluatorSlices', 1) == (fixture_copy.evaluator_slices(inventory) if 'evaluatorSlices' in key else 1),
                   'FIXTURE_KEY_CASE_MISMATCH')
        library = binding/'bindings/kubernetes/lib'
        k.write(output/'stages/fixture-claims.json',
                fixture_copy.render(jsonnet,library,namespace,run_id,fixture,tenants,candidate['postgres'],
                                    fixture_copy.evaluator_slices(inventory), transport))
        if fixture['mode'] == 'seed':
            k.write(output/'stages/fixture-snapshots.json',
                    fixture_copy.snapshot_objects(jsonnet,library,namespace,run_id,fixture))

    k.write(output/'intent.json',intent)
    env.update(namespace=namespace,runId=run_id,images=images,tenantCount=tenants,sourceCommit=source['coreCommit'],
               imageDeployCommit=source['deployCommit'],provisionDeadlineSeconds=outer,workDeadlineSeconds=outer,
               cleanupDeadlineSeconds=outer+max(point['phases']['cleanupSeconds'] for point in profiles),resourceAccounting='requests-v1')
    k.write(output/'environment.json',env)
    now = datetime.now(timezone.utc)
    run['driver']['coreRepository'] = str(core)
    if connector_share:
        # A looping driver takes its ordinary prefix in host order (workload_runtime.ordinary_roster); the
        # connector group is then the host-order tail, so the two stay disjoint by tenant id.
        looping = profile['workload'].get('driverShape') in ('looping-v1', 'looping-v2')
        run['connectors'] = {'share': connector_share, 'ordinaryRosterTenants': profile['population']['ordinaryRosterTenants'],
                             'image': candidate['app'], 'order': 'host' if looping else 'roster',
                             # Upstream timing (connectors/upstream.cjs TIMINGS): aid-v1 unless the profile names a variant.
                             'timing': profile['population'].get('connectorTiming', 'aid-v1')}
    run.update(runId=run_id,namespace=namespace,tenants=tenants,workload=traffic,resourceAccounting='requests-v1',
               tenantsFile=str(output/'runtime/fixture/data-roster.private.json'), deadlines={kind:(now+timedelta(seconds=env[seconds])).isoformat().replace('+00:00','Z')
               for kind,seconds in [('workUntil','workDeadlineSeconds'),('cleanupUntil','cleanupDeadlineSeconds')]})
    k.write(output/'native-run-template.json', run)
    fixture_identity = {'mode':'fresh'} if fixture is None else {'mode':fixture['mode'], 'directory':str(fixture['directory'])}
    fixture_identity['history'] = profile['history']
    k.write(output/'preflight.json',{'offline':'PASS','commissioning':'PREFLIGHT_ONLY',
        'trialEnvelope':{'placementMode':'scheduler','resourceAccounting':'requests-v1'},'experiment':{'runId':run_id,
        'namespace':namespace,'renderSha256':k.digest(output/'render.json'),'experimentSha256':k.digest(output/'intent.json')},
        'identity':{'alignmentCommit':alignment,'bindingCommit':binding_head,'candidate':candidate,
                    'fixture':fixture_identity},
        'topology':{'inputTransport':transport, 'apiReplicas':inventory['workloads']['api']['replicas'],
                    'evaluatorSlices':inventory['slices']['evaluator'], 'realtimeSlices':inventory['slices']['realtime']}})
    selected_control = {key:control[key] for key in ('version','toolsDirectory','k6','readonlyGuard','pullSecretCommand') if key in control}
    selected_control.update(caseDirectory=str(output),bindingDirectory=str(binding),instrumentDirectory=str(k.ROOT),
                            schedulerPlacement=True,coreRepository=str(core),runTemplate=lc.ref(output/'native-run-template.json'),
                            candidate=candidate,alignmentCommit=alignment,nativeLimits=control['nativeLimits'],
                            primerConcurrency=phases.get('primerOptions',{}).get('concurrency',control['primerConcurrency']))
    if next_points:
        selected_control['loadPoints'] = [point['workload']['pointId'] for point in profiles]
    if fixture:
        selected_control['fixture'] = fixture
    k.write(output/'lifecycle-input.json',selected_control)
    native_join.prepare_case(output,selection)
    instance = {'config':str(output/'native-run-template.json'),'render':str(output/'render.json'),
                'inventory':str(output/'inventory.json'),'binding':str(binding)}
    if next_points:
        prepare_points(output, profiles, instance)
    else:
        experiment.prepare(output/'intent.json',instance,output/'offline-final',await_primer=True)
    result = experiment.launch(output/'lifecycle-input.json', True)
    preflight = k.document(output/'preflight.json')
    return {**result, 'identity':preflight['identity'], 'topology':preflight['topology']}
