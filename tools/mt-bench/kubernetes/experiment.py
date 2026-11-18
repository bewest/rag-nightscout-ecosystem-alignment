#!/usr/bin/env python3
"""Prepare a portable binding, bind a fresh allocation, or execute one bounded load."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import adapter as k
from auto_catalog import auto_catalog
import execute
import frozen
import matrix
from workloads import profile, reduce


def materialize(manifest, binding_repo, deploy_repo, out):
    selected = frozen.source(manifest)
    def git(repo, *args):
        return subprocess.check_output(['git', '-C', repo, *args])
    k.need(git(deploy_repo, 'rev-parse', 'HEAD').decode().strip() == selected['deployCommit']
           and not git(deploy_repo, 'status', '--porcelain', '--', 'bindings/compose'), 'IMAGE_DEPLOY_CHANGED')
    archive = git(binding_repo, 'archive', manifest['bindingCommit'], 'bindings/kubernetes')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(out, filter='data')
    package = out / 'bindings/kubernetes'
    asset = package / 'assets/source-contract.json'
    supported = k.document(asset)
    subprocess.run(['git', 'apply', '--directory=bindings/kubernetes', str(k.HERE / 'binding-input.patch')],
                   cwd=out, check=True)
    subprocess.run([sys.executable, package/'check/source-equivalence.py', '--capture',
                    '--compose', Path(deploy_repo).resolve()/'bindings/compose',
                    '--image', selected['localImageId']], check=True)
    measured = k.document(asset)
    for key in ('coreCommit', 'deployCommit', 'localImageId', 'producerBinarySha256'):
        k.need(measured[key] == selected[key], 'MEASURED_IMAGE_SOURCE_CHANGED')
    for key in ('commands', 'postgresIdentities', 'nativeCatalogueSha256'):
        k.need(measured[key] == supported[key], 'UNSUPPORTED_BINDING_CAPABILITY:' + key)
    # The package embeds deployment assets and a static role/provisioning protocol.
    # A changed deployment input needs a reviewed binding compatibility update.
    k.need(frozen.compatible_deployment_inputs(manifest, supported['sourceFilesSha256'],
                                               measured['sourceFilesSha256']),
           'UNSUPPORTED_BINDING_DEPLOYMENT_INPUT')
    frozen.install_bootstrap_helper(manifest, deploy_repo, package, measured)
    measured.update(selected)
    k.write(asset, measured)
    k.write(out/'binding.json', dict(bindingCommit=manifest['bindingCommit'],
            sourceContractSha256=k.digest(asset), patchSha256=k.digest(k.HERE/'binding-input.patch'),
            files={str(p.relative_to(package)):k.digest(p) for p in sorted(package.rglob('*')) if p.is_file()},
            sourceAcceptance=selected['sourceAcceptance'], capacityAcceptance='NOT_GRANTED'))
    return package


def workload(m):
    selected = frozen.source(m)
    p = m['profile']
    k.need('referencePins' not in p, 'DUPLICATE_SOURCE_SELECTION')
    return profile.validate(dict(p, referencePins=dict(core=selected['coreCommit'], deploy=selected['deployCommit'],
                                                      bindingCommit=m['bindingCommit'])))


def render_checks(instance):
    receipt = frozen.read_ref(instance['bindingReceipt'])
    package = Path(instance['bindingReceipt']['path']).parent / 'bindings/kubernetes'
    for name in ('check/invariants.js', 'assets/source-contract.json', 'assets/nginx.conf', 'assets/service-environment.js'):
        k.need(k.digest(package/name) == receipt['files'][name], 'BINDING_PACKAGE_CHANGED')
    check = """const fs=require('node:fs'),check=require(process.argv[1]);
      const read=path=>JSON.parse(fs.readFileSync(path));
      console.log(JSON.stringify(check.checks(check.manifests(read(process.argv[2])),read(process.argv[3]))));"""
    raw = subprocess.check_output(['node', '-e', check, package/'check/invariants.js',
                                   instance['render'], instance['inventory']], timeout=30)
    rows = json.loads(raw)
    k.need(bool(rows), 'RENDER_CHECKS_UNMEASURED')
    for row in rows:
        k.need(row['failures'] == [], 'UNSUPPORTED_RENDER:' + row['name'])
    return [row['name'] for row in rows]


def prepare(manifest_path, instance, out, *, await_primer=False):
    m = k.document(manifest_path)
    p = workload(m)
    config = k.document(instance['config'])
    inventory = k.document(instance['inventory'])
    render = k.document(instance['render'])
    delivery = frozen.read_ref(instance['delivery'])
    frozen.registry(delivery, inventory['images'], m)
    selected = frozen.source(m)
    pins = dict(pair=dict(core=selected['coreCommit'], deploy=selected['deployCommit']),
                bindingCommit=m['bindingCommit'], instrument=k.instrument()['sha256'],
                appImage=delivery['app'], appImageId=delivery['appImageId'],
                postgresImage=delivery['postgres'], postgresImageId=delivery['postgresImageId'],
                inventorySha256=k.digest(instance['inventory']), renderSha256=k.digest(instance['render']),
                candidate=inventory['candidateContract'])
    k.need(config.get('pins', pins) == pins, 'INSTANCE_PINS_CHANGED')
    tier = m.get('tier', 'discovery')
    k.need(config.get('tier', tier) == tier, 'INSTANCE_TIER_CHANGED')
    c = profile.bind(p, dict(config, pins=pins, tier=tier))
    objects = k.validate(c, inventory, render)
    frozen.check_bootstrap_render(m, objects.values())
    k.need(all(pins['candidate'].get(key) == selected.get(key) for key in
               ('runtimeBootstrapHelper', 'imageSourceAcceptance', 'sourceAcceptance')), 'BOOTSTRAP_HELPER_SCOPE')
    contract = objects['ConfigMap/provision-scripts']['data']['source-contract.json']
    frozen.rendered_contract(m, contract, instance['bindingReceipt'])
    k.need(pins['candidate']['sourceAcceptance'] == selected['sourceAcceptance'], 'CANDIDATE_IMAGE_STATUS')
    checks = render_checks(instance)
    k.need(c['roles'].get('evaluator') == dict(workload='StatefulSet/cohort', container='evaluator')
           and c['roles'].get('pgstream') == dict(workload='Deployment/pgstream', container='pgstream'),
           'UNSUPPORTED_ROLE_TOPOLOGY')
    k.need(c['storageMode'] == 'disposable', 'EXPERIMENT_STORAGE')
    if 'roleDocuments' in instance:
        docs = instance['roleDocuments']
        measured = k.completion_source(c, docs['evaluator'], docs['realtime'])
        k.need(c.get('completion', measured) == measured, 'COMPLETION_SOURCE_CHANGED')
        c['completion'] = measured
    if await_primer:
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
    selection = c['pins'].get('candidate', {})
    if 'runtimeBootstrapHelper' in selection:
        outcome.update({key: selection[key] for key in ('runtimeBootstrapHelper', 'imageSourceAcceptance', 'sourceAcceptance')})
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
                                                bootstrapHelper=k.active_baseline(d).get('bootstrapHelper'),
                                                namespaceUid=k.active_baseline(d)['namespace']['uid']))
        k.candidate.require(k, d, c)
        execute.authority(d, c)
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
                reduce.reduce_stage(d/'load', attempt/'observations')
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
    selection = config['pins'].get('candidate', {})
    keys = ('runtimeBootstrapHelper', 'imageSourceAcceptance', 'sourceAcceptance')
    if 'runtimeBootstrapHelper' in selection or 'runtimeBootstrapHelper' in pre:
        k.need('runtimeBootstrapHelper' in selection and selection.get('sourceAcceptance') == 'PENDING'
               and all(key in pre and pre[key] == selection.get(key) for key in keys),
               'PREFLIGHT_BOOTSTRAP_HELPER_CHANGED')


def failure(exc):
    code = str(exc)
    return dict(code=code if code == 'EVALUATOR_SCOPE_UNSAFE' or code.startswith(('K8S_', 'M7_')) else type(exc).__name__,
                verdict=getattr(exc, 'verdict', 'UNMEASURED'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    for name, fields in {'binding': ('manifest','binding_repo','deploy_repo','output'),
                         'describe': ('manifest',), 'prepare': ('manifest','instance','output'),
                         'run': ('packet','allocation','sha256')}.items():
        command = commands.add_parser(name)
        for field in fields:
            command.add_argument(field, type=str if field == 'sha256' else Path)
        if name == 'prepare':
            command.add_argument('--await-primer', action='store_true', help='bind DATA credentials after verified in-Pod priming')
        if name == 'run':
            command.add_argument('--matrix', type=Path)
    a = parser.parse_args()
    if a.action == 'binding':
        return str(materialize(k.document(a.manifest), a.binding_repo, a.deploy_repo, a.output.resolve()))
    if a.action == 'describe':
        return profile.describe(workload(k.document(a.manifest)))
    if a.action == 'prepare':
        return prepare(a.manifest, k.document(a.instance), a.output.resolve(), await_primer=a.await_primer)
    return run(a.packet, a.allocation, a.sha256, k.document(a.matrix) if a.matrix else None)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), indent=2))
    except (k.Refused, ValueError, OSError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps(failure(error)), file=sys.stderr)
        sys.exit(3)
