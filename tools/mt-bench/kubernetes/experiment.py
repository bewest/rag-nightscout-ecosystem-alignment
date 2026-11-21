#!/usr/bin/env python3
"""Bind a fresh allocation, or execute one bounded load."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import kube_adapter as k
from auto_catalog import auto_catalog
import execute
import frozen
import edge_configuration
import matrix
import primer_options
import population_ceiling
import application_topology
from workloads import profile, reduce


def bind_primer_stall(package, manifest):
    phases = manifest.get('profile', {}).get('phases', {})
    startup = k.workload_inputs.startup_selection(phases, k.need)
    seconds = startup.get('kubernetes', {}).get('primerReadySeconds')
    if seconds is None:
        return
    lib = package/'lib/ns/nightscout.libsonnet'
    # Override the rendered init environment. Layout and comments in the
    # source Jsonnet library do not affect the selection.
    with lib.open('a') as wrapper:
        wrapper.write("""
+ {
  new(overrides)::
    local base = super.new(overrides);
    local actors = base.primer.job.spec.template.spec.initContainers;
    local stall = { name: 'NS_PRIMER_STALL_SECONDS', value: '%d' };
    base + { primer+: { job+: { spec+: { template+: { spec+: {
      initContainers: [if actor.name == 'primer' then actor + {
        env: [entry for entry in actor.env if entry.name != stall.name] + [stall],
      } else actor for actor in actors],
    } } } } } },
}
""" % seconds)


def bind_job_completion_wait(package, selected):
    if frozen.JOB_COMPLETE not in selected:
        return
    publisher=package/'scripts/secrets.sh'
    text=publisher.read_text()
    wait='k wait --for=condition=complete job/provision --timeout=30s >/dev/null'
    k.need(text.count(wait)==1,'PROVISION_JOB_COMPLETE_SEAM')
    publisher.write_text(text.replace(wait,wait.replace('30s',f"{selected[frozen.JOB_COMPLETE]}s")))


def workload(m):
    application_topology.selection(m, k.need)
    edge_configuration.selection(m.get('edge'),k.need)
    selected = frozen.source(m)
    p = m['profile']
    k.need('referencePins' not in p, 'DUPLICATE_SOURCE_SELECTION')
    return profile.validate(dict(p, referencePins=dict(core=selected['coreCommit'], deploy=selected['deployCommit'],
                                                      bindingCommit=m['bindingCommit'])))


def render_checks(instance):
    package = Path(instance['binding']) / 'bindings/kubernetes'
    check = """const fs=require('node:fs'),check=require(process.argv[1]);
      const read=path=>JSON.parse(fs.readFileSync(path));
      // Native declarations are an array; older binding flatteners omit arrays.
      const manifests=value=>Array.isArray(value)?value.flatMap(manifests):
        value&&typeof value==='object'?(value.kind==='List'?manifests(value.items):
          value.apiVersion&&value.kind?[value]:Object.values(value).flatMap(manifests)):[];
      const inventory=read(process.argv[3]);let all=manifests(read(process.argv[2]));
      // Only the opt-in test Job is outside the application's workload roster.
      // Its exact owned edge policy stays visible to the original binding's
      // private-plane checks, alongside every unchanged application policy.
      if(inventory.nativeLoad)all=all.filter(m=>!(m.kind==='Job'&&m.metadata.name==='k6'));
      console.log(JSON.stringify(check.checks(all,inventory)));"""
    raw = subprocess.check_output(['node', '-e', check, package/'check/invariants.js',
                                   instance['render'], instance['inventory']], timeout=30)
    rows = json.loads(raw)
    k.need(bool(rows), 'RENDER_CHECKS_UNMEASURED')
    for row in rows:
        k.need(row['failures'] == [], 'UNSUPPORTED_RENDER:' + row['name'])
    return [row['name'] for row in rows]


def prepare(manifest_path, instance, out, *, await_primer=False, existing_fixture=False):
    m = k.document(manifest_path)
    p = workload(m)
    k.need(m.get('primerLocation') or await_primer or primer_options.from_profile(p,k.need) is None,
           'PRIMER_OPTIONS_AWAIT_PRIMER_REQUIRED')
    config = k.document(instance['config'])
    inventory = k.document(instance['inventory'])
    k.need(m.get('nativeLoad') == config.get('nativeLoad') == inventory.get('nativeLoad'),
           'NATIVE_LOAD_SELECTION_CHANGED')
    config = dict(config, **application_topology.bind(m, config, inventory, k.need))
    render = k.document(instance['render'])
    population_ceiling.check_render(m,inventory,k.manifests(render),k.need)
    edge=edge_configuration.check(m,inventory,k.manifests(render),k.need)
    # The candidate's image digests are the run identity; Kubernetes pulls by digest.
    delivery = frozen.candidate(m)
    selected = frozen.source(m)
    pins = dict(pair=dict(core=selected['coreCommit'], deploy=selected['deployCommit']),
                bindingCommit=m['bindingCommit'], instrument=k.instrument()['sha256'],
                appImage=delivery['app'], appImageId=delivery['appImageId'],
                postgresImage=delivery['postgres'], postgresImageId=delivery['postgresImageId'],
                inventorySha256=k.digest(instance['inventory']), renderSha256=k.digest(instance['render']))
    k.need(config.get('pins', pins) == pins, 'INSTANCE_PINS_CHANGED')
    tier = m.get('tier', 'discovery')
    k.need(config.get('tier', tier) == tier, 'INSTANCE_TIER_CHANGED')
    c = profile.bind(p, dict(config, pins=pins, tier=tier))
    k.need('edgeConfiguration' not in config or config['edgeConfiguration']==edge,'EDGE_CONFIGURATION_CHANGED')
    if edge is not None:c['edgeConfiguration']=edge
    k.need('producerAckReadback' not in config and 'producerAckReadback' not in instance, 'PGSTREAM_ACK_READBACK_UNDECLARED')
    if c.get('nativeLoad') is not None:
        c['nativeLoadCustodyFile']=str(out.resolve()/'load/native-load.json')
    objects = k.validate(c, inventory, render)
    checks = render_checks(instance)
    k.need(c['storageMode'] in ('disposable', 'existing-claim'), 'EXPERIMENT_STORAGE')
    k.need('verificationProof' not in config, 'CANDIDATE_VERIFICATION_PROOF_SCOPE')
    if 'roleDocuments' in instance:
        docs = instance['roleDocuments']
        measured = k.completion_source(c, docs['evaluator'], docs['realtime'], **({'native_receipt':docs['nativeReceipt']} if 'nativeReceipt' in docs else {}))
        k.need(c.get('completion', measured) == measured, 'COMPLETION_SOURCE_CHANGED')
        c['completion'] = measured
    if existing_fixture:
        import fixture
        k.need(c.get('storageMode')=='existing-claim' and inventory['results']['primer'].get('claim'),
               'FIXTURE_CLAIM_REQUIRED')
        fixture.existing(c,inventory,objects,out.resolve().with_name(out.name+'-fixture'),
                         k.timestamp(c['deadlines']['workUntil']))
    if await_primer and c.get('primerLocation'):
        pass  # Offline preparation precedes the first fixture; live preparation receives its DATA roster.
    elif await_primer:
        c['primerOutput'] = str(out.resolve() / 'primer')
        c['tenantsFile'] = str(Path(c['primerOutput']) / 'tenants.json')
    else:
        k.need('primerOutput' not in c, 'PRIMER_INPUT')
        execute.roster(c)
        c['rosterSha256'] = k.digest(c['tenantsFile'])
    c['bindingChecks'] = checks
    c['experimentSha256'] = k.digest(manifest_path)
    # Use the existing preparer, including instrument and original render byte hashes.
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        bound = Path(scratch)/'bound.json'
        k.write(bound, c)
        k.prepare(bound, instance['inventory'], instance['render'], out)
    return {'packet': str(out), 'sourceAcceptance': selected['sourceAcceptance'], 'capacityAcceptance': 'NOT_GRANTED'}


def admitted_entries(d, c, objects, group):
    members = [(d, c, objects)]
    if group is not None:
        execute.matrix_plan(group)
        members = [k.load(path) for path in group['fixtures']]
        k.need(any(path == d for path, _, _ in members), 'MATRIX_ALLOCATION_ROSTER')
    entries = []
    for path, config, rendered in members:
        baseline = k.active_baseline(path)
        current = k.observe(config, rendered, k.Client(config), baseline)
        if config.get('nativeLoad') is not None:
            k.need(current.get('nativeLoadSuspended') is True and not current.get('testActors'),
                   'NATIVE_LOAD_EARLY_STARTED')
        matrix.identity(config, baseline, current)
        entries.append((path, config, rendered, current))
    return entries


def run(packet, grant_path, expected_digest, group=None):
    d, c, objects = k.load(packet)
    k.need('experimentSha256' in c, 'EXPERIMENT_PACKET_REQUIRED')
    # Claim the attempt exactly once, including failed admissions. Never overwrite its evidence.
    attempt = d / 'experiment'
    attempt.mkdir(mode=0o700, exist_ok=False)
    outcome = dict(verdict='UNMEASURED', tier=c.get('tier', 'discovery'),
                   capacityAcceptance='NOT_GRANTED', experimentSha256=c['experimentSha256'])
    try:
        k.need(not (d/'load').exists(), 'STAGE_OUTPUT_EXISTS')
        client = k.Client(c)
        entries = admitted_entries(d, c, objects, group)
        grant, usage = matrix.allocation(dict(allocation=str(grant_path), allocationSha256=expected_digest), entries)
        if group is None:
            k.need(grant.get('experimentSha256') == c['experimentSha256'], 'ALLOCATION_EXPERIMENT_CHANGED')
            pre = grant['preflight']
        else:
            pre = grant['experimentPreflights'][c['runId']]
        require_preflight(frozen.read_ref(pre), c)
        if 'primerOutput' in c:
            import primer
            primer.require_roster(d, c, k.active_baseline(d))
        else:
            k.need(k.digest(c['tenantsFile']) == c['rosterSha256'], 'EXPERIMENT_ROSTER_CHANGED')
        k.need(k.re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', c['baseUrl'])
               and 0 < execute.urlparse(c['baseUrl']).port <= 65535, 'LOOPBACK_FORWARD_REQUIRED')
        k.write(attempt/'allocation.json', dict(sha256=expected_digest, accounting=usage,
                                                namespaceUid=k.active_baseline(d)['namespace']['uid']))
        execute.authority(d, c)
        if c.get('history', profile.history.BASELINE) != profile.history.BASELINE:
            receipt = profile.history.run(c['history'], execute.roster(c), c['baseUrl'],
                        lambda query: k.sql(d, c, objects, query, client),
                        k.timestamp(c['deadlines']['workUntil']), profile.history.window(c['workload']),
                        verify_only=c.get('restoredHistory', False))
            k.write(attempt/'populated-history.json', receipt)
        outcome['load'] = execute.execute(d, c, objects, client, load=True)
        outcome['verdict'] = outcome['load']['verdict']
    except Exception as exc:
        outcome['firstFailure'] = failure(exc)
        outcome['verdict'] = getattr(exc, 'verdict', 'UNMEASURED')
        raise
    finally:
        k.write(attempt/'result.json', outcome)
        if (d/'load').is_dir():
            try:
                execute.native_resource_observation(d/'load',k.document(d/'load/driver.json'))
            except Exception as exc:
                k.write(attempt/'resource-observation-unavailable.json',failure(exc))
            try:
                measurements = reduce.reduce_stage(d/'load', attempt/'observations')
                outcome['observations'] = {key: measurements[key] for key in
                    ('http', 'issued', 'stored', 'clinical', 'selectedClinicalCoverage', 'delivered',
                     'evaluatorProgress', 'catchup', 'outcomeGate', 'componentCounters', 'stopEvidence',
                     'probeFailure', 'stageOutcome') if key in measurements}
                outcome['reduction'] = 'observations/reduction.json'
                k.write(attempt/'result.json', outcome)
            except Exception as exc:
                k.write(attempt/'reduction-failure.json', failure(exc))
        # The outer lifecycle indexes its case after it verifies absence.
        if d.name != 'packet' or d.parent.name != 'runtime':
            auto_catalog(d, k.write)
    return outcome


def require_preflight(pre, config):
    expected = {name:config[name] for name in ('runId', 'namespace', 'experimentSha256')}
    expected['renderSha256'] = config['pins']['renderSha256']
    k.need(pre.get('offline') == 'PASS' and pre.get('commissioning') == 'PREFLIGHT_ONLY', 'MATRIX_PREFLIGHT_REQUIRED')
    k.need(pre.get('experiment') == expected, 'PREFLIGHT_EXPERIMENT_CHANGED')


def failure(exc):
    code = str(exc)
    return dict(code=code if code == 'EVALUATOR_SCOPE_UNSAFE' or code.startswith(('K8S_', 'M7_')) else type(exc).__name__,
                verdict=getattr(exc, 'verdict', 'UNMEASURED'))


def launch(path, prepare_only):
    """Dispatch the existing lifecycle from the helper selected for this case."""
    from lifecycle_config import helper_directory
    config = k.document(path)
    directory = helper_directory(config)
    case = Path(config['caseDirectory'])
    command = [sys.executable, '-B']
    if 'inputs' in config:
        bound = path.resolve()
        if prepare_only:
            subprocess.run([*command, directory/'lifecycle_config.py', 'check', bound],
                           check=True, stdout=subprocess.DEVNULL)
    else:
        bound = case/'lifecycle-bound.json'
        subprocess.run([*command, directory/'lifecycle_config.py', 'capture', path.resolve(), bound],
                       check=True, stdout=subprocess.DEVNULL)
    if prepare_only:
        return {'configuration': str(bound), 'helper': str(directory), 'runtimeStarted': False}
    os.execv(sys.executable, [*command, directory/'lifecycle.py', bound])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    for name, fields in {'describe': ('manifest',), 'prepare': ('manifest','instance','output'),
                         'run': ('packet','allocation','sha256'), 'launch': ('config',)}.items():
        command = commands.add_parser(name)
        for field in fields:
            command.add_argument(field, type=str if field == 'sha256' else Path)
        if name == 'launch':
            command.add_argument('--prepare-only', action='store_true', help='capture or check the case without starting actors')
        if name == 'prepare':
            inputs = command.add_mutually_exclusive_group()
            inputs.add_argument('--await-primer', action='store_true', help='prepare the packet before commissioning')
            inputs.add_argument('--existing-fixture', action='store_true', help='read a commissioned, operator-owned fixture with existing claims')
        if name == 'run':
            command.add_argument('--matrix', type=Path)
    standard = commands.add_parser('standard', help='Prepare a fresh scheduler-placed discovery case offline')
    for field in ('template_case','binding','profile','output'):
        standard.add_argument(field, type=Path)
    standard.add_argument('--app-image', required=True, help='Candidate application image, REF@sha256:DIGEST')
    standard.add_argument('--postgres-image', help='PostgreSQL image, REF@sha256:DIGEST (defaults to the template)')
    standard.add_argument('--namespace-prefix', default='ns-synth-', help='Namespace name prefix; ownership is the run-id label')
    standard.add_argument('--core', type=Path, help='Core checkout for the driver (defaults to the template checkout)')
    standard.add_argument('--reserved-worker-taint', metavar='KEY=VALUE', help='Tolerate the reserved worker for this run')
    standard.add_argument('--node-name', help='Pin every workload and the load Job to this node (nodeSelector kubernetes.io/hostname)')
    standard.add_argument('--resources', type=Path, help='JSON per-container resources (requests/limits) for a one-change arm')
    standard.add_argument('--binding-input', type=Path, help='JSON object merged into the binding inputs last (for example roleEnv)')
    standard.add_argument('--fixture', choices=('reuse', 'build'),
                          help='find the CSI snapshot fixture by key (tenants, seed name, schema, images, transport, '
                               'history, evaluator K): reuse restores it into this case, building and registering it '
                               'first on a miss (live seed case OUTPUT-seed, no traffic); build only builds and '
                               'registers it (live, case OUTPUT) for later runs')
    standard.add_argument('--fixture-seed', default='default', metavar='NAME',
                          help='fixture seed name in the key; a new name forces an independent fixture')
    standard.add_argument('--fixture-catalog', type=Path, help='catalog file (default $NS_FIXTURE_CATALOG or the workspace catalog)')
    standard.add_argument('--storage-class', default='do-block-storage', help='StorageClass for seeded fixture claims')
    standard.add_argument('--snapshot-class', default='do-block-storage', help='VolumeSnapshotClass for a seed')
    standard.add_argument('--fixture-postgres-size', help='PostgreSQL claim size for a seed (default 4Gi: data plus about max_wal_size of WAL)')
    a = parser.parse_args()
    if a.action == 'standard':
        import standard_case
        options = dict(app_image=a.app_image, postgres_image=a.postgres_image, namespace_prefix=a.namespace_prefix,
                       core=a.core, taint=a.reserved_worker_taint, node_name=a.node_name,
                       resources_file=a.resources, binding_extra=a.binding_input)
        if a.fixture:
            import fixture_catalog
            return standard_case.keyed(a.fixture, a.template_case, a.binding, a.profile, a.output, seed=a.fixture_seed,
                                       catalog=fixture_catalog.Catalog(a.fixture_catalog), storage_class=a.storage_class,
                                       snapshot_class=a.snapshot_class, postgres_size=a.fixture_postgres_size, **options)
        return standard_case.prepare(a.template_case, a.binding, a.profile, a.output, **options)
    if a.action == 'launch':
        return launch(a.config, a.prepare_only)
    if a.action == 'describe':
        return profile.describe(workload(k.document(a.manifest)))
    if a.action == 'prepare':
        return prepare(a.manifest, k.document(a.instance), a.output.resolve(), await_primer=a.await_primer, existing_fixture=a.existing_fixture)
    return run(a.packet, a.allocation, a.sha256, k.document(a.matrix) if a.matrix else None)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), indent=2))
    except (k.Refused, ValueError, OSError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps(failure(error)), file=sys.stderr)
        sys.exit(3)
