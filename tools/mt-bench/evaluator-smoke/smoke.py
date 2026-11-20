#!/usr/bin/env python3
"""Evaluator statement smoke: SQL statements and main-thread CPU per accepted write.

The "smoke" tier of decision capacity-test-tiers for the evaluator: a small Compose
multitenant deployment (default 16 tenants, K=1 evaluator, 180 s of realistic-v1
load at a fixed rate multiplier) through the m7-joined runner's smoke tier, then:

  statement_phase.py  evaluator statements per accepted write, by database role and phase
  main_thread.py      evaluator main-thread CPU per accepted write

and a comparison with a committed baseline. The comparison is a figure, never a
gate (decision performance-signals-not-gates); the runner's own smoke verdict
(stored counts, clinical witnesses, ownership, viewer bindings) stays strict.

  smoke.py build  --core REF [--deploy-commit SHA]       build or reuse the image
  smoke.py run    (--core REF | --image REF) --out DIR    build if needed, run, reduce, compare
  smoke.py reduce RUN_DIR [--baseline FILE] [--empty-rules]
  smoke.py compare SUMMARY.json BASELINE.json

Environment: NS_SMOKE_CORE_REPO (a cgm-remote-monitor checkout that holds REF;
default <alignment>/externals/cgm-remote-monitor-official) and NS_SMOKE_DEPLOY_REPO
(a nightscout-deploy checkout; default <alignment>/externals/nightscout-deploy).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALIGNMENT = HERE.parent.parent.parent
M7 = HERE.parent / 'm7-joined'
RUNNER = M7 / 'runner.py'
sys.path.insert(0, str(M7))
sys.path.insert(0, str(HERE))
import populated_history  # noqa: E402
from contract import DISCOVERY_MAX_API_REPLICAS, DISCOVERY_MAX_WORKERS  # noqa: E402
import main_thread  # noqa: E402
import statement_phase  # noqa: E402

DEFAULT_DEPLOY = 'f57a8c335be9895c0ce4596d8a73275444b16541'  # nightscout-deploy; image inputs equal at 09f2223
WRITER_DEPLOY = '086669a9a3bb8d32534e864f686f1d677aacfb57'
K6_IMAGE = 'sha256:eeb0db19cd8d263aa57346cdbc7ea18e6fcfb2ba9497746a7ae82ceefc8c9fa5'  # grafana/k6:1.3.0
POSTGRES_IMAGE = 'sha256:21e7e1665c3dd2fdd80ebd9ce6d36fb160d6a4129683b315b6492a71d87bfda7'
BASELINE = HERE / 'baseline.json'
WORKLOAD = {'tenants': 16, 'load-seconds': 180, 'workload-scale': 24.0}


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout.strip()


def repo(env, default):
    if os.environ.get(env):
        return Path(os.environ[env])
    local = ALIGNMENT / 'externals' / default
    if local.exists():
        return local
    common = sh(['git', '-C', str(ALIGNMENT), 'rev-parse', '--path-format=absolute', '--git-common-dir'])
    return Path(common).parent / 'externals' / default


def resolve(ref, root):
    """A commit, branch or a cgm-remote-monitor worktree path -> full commit."""
    if os.path.isdir(ref):
        require(sh(['git', '-C', ref, 'status', '--porcelain', '--untracked-files=no']) == '', 'SMOKE_CORE_WORKTREE_DIRTY')
        return sh(['git', '-C', ref, 'rev-parse', 'HEAD'])
    return sh(['git', '-C', str(root), 'rev-parse', '--verify', ref + '^{commit}'])


def require(ok, code):
    if not ok:
        raise SystemExit(code)


def labels(image):
    try:
        spec = json.loads(sh(['docker', 'image', 'inspect', image]))[0]
    except subprocess.CalledProcessError:
        return None, {}
    return spec['Id'], (spec.get('Config') or {}).get('Labels') or {}


def build(core, deploy, core_repo, deploy_repo, scratch):
    """Image from two commits, as deploy's tools/compose-overlay.sh + build.js do (overlay marker written here)."""
    deploy = sh(['git', '-C', str(deploy_repo), 'rev-parse', '--verify', deploy + '^{commit}'])
    tag = f'ns-evaluator-smoke:{core[:12]}-{deploy[:12]}'
    image_id, lab = labels(tag)
    if image_id and lab.get('org.opencontainers.image.revision') == core and lab.get('org.nightscout.deploy.revision') == deploy:
        return tag, image_id, 'reused'
    work = Path(scratch) / f'build-{core[:12]}'
    require(not work.exists(), 'SMOKE_BUILD_DIR_EXISTS')
    sh(['git', '-C', str(core_repo), 'worktree', 'add', '--detach', str(work), core])
    try:
        overlay = work / 'deploy' / 'multitenant'
        subprocess.run(['rm', '-rf', str(overlay)], check=True)
        overlay.mkdir(parents=True)
        tree = subprocess.run(['git', '-C', str(deploy_repo), 'archive', deploy + ':bindings/compose/multitenant'],
                              check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', str(overlay)], input=tree, check=True)
        (overlay / '.overlay.json').write_text(json.dumps({'version': 1, 'deployRepository': str(Path(deploy_repo).resolve()),
                                                           'deployCommit': deploy}) + '\n')
        log = Path(scratch) / f'build-{core[:12]}.log'
        with log.open('w') as out:
            subprocess.run(['node', 'build.js', '--image', tag], cwd=overlay, check=True, stdout=out, stderr=subprocess.STDOUT)
    finally:
        subprocess.run(['git', '-C', str(core_repo), 'worktree', 'remove', '--force', str(work)], check=False)
    image_id, lab = labels(tag)
    require(lab.get('org.opencontainers.image.revision') == core and lab.get('org.nightscout.deploy.revision') == deploy,
            'SMOKE_BUILT_LABELS')
    return tag, image_id, 'built'


def free_subnets():
    used = set()
    for net in sh(['docker', 'network', 'ls', '-q']).split():
        used |= set(sh(['docker', 'network', 'inspect', net, '--format', '{{range .IPAM.Config}}{{.Subnet}} {{end}}']).split())
    for third in range(20, 250):
        pair = (f'10.249.{third}.0/27', f'10.249.{third}.32/27')
        if not any(p.startswith(f'10.249.{third}.') for p in used):
            return pair
    raise SystemExit('SMOKE_NO_FREE_SUBNET')


def config(core, deploy, core_repo, deploy_repo, project, workload, *, transport='pgstream', replicas=None, workers=None):
    default_count = 2 if transport == 'writer-driven' else 1
    replicas = default_count if replicas is None else replicas
    workers = default_count if workers is None else workers
    backend, edge = free_subnets()
    head = sh(['git', '-C', str(ALIGNMENT), 'rev-parse', 'HEAD'])
    return {
        'version': 1, 'tier': 'smoke', 'helperHead': head, 'k6Image': K6_IMAGE,
        'workSeconds': 2400, 'cleanupSeconds': 300,
        **({'history': workload['history']} if 'history' in workload else {}),
        'prepare': {
            'core-repo': str(core_repo), 'core-commit': core, 'deploy-repo': str(deploy_repo), 'deploy-commit': deploy,
            'postgres-image': POSTGRES_IMAGE, 'tenants': workload['tenants'], 'replicas': replicas,
            'warmup-seconds': 5, 'idle-seconds': 5, 'load-seconds': workload['load-seconds'],
            'setup-seconds': 180, 'drain-seconds': 180, 'accel': 1, 'hot-factor': 1, 'sampler-interval': 5,
            'probe-every-ms': 10000, 'sockets-per-tenant': 1, 'logical-polling-clients': 2,
            'workload-mix': 'realistic-v1', 'workload-scale': workload['workload-scale'],
            'primer-concurrency': 4, 'jwt-setup-concurrency': 4, 'fixture-project': project,
            'maximum-run-minutes': 40, 'backend-subnet': backend, 'edge-subnet': edge, 'quiet-load': os.cpu_count() or 1,
            **({'input-transport': 'writer-driven'} if transport == 'writer-driven'
               else {'pgstream-topology': 'external-service-v1'}),
            'completion-contract': 'evaluator-work-v2', 'static-workers': workers,
        },
    }


def recorded_topology(run):
    # The runner retains the candidate-bound configuration. Older smoke packets used 1/1/1.
    source = run / 'config.json'
    options = json.loads(source.read_text())['prepare'] if source.is_file() else {}
    workers = options.get('static-workers', 1)
    return {'inputTransport': options.get('input-transport', 'pgstream'), 'apiReplicas': options.get('replicas', 1),
            'evaluatorSlices': workers, 'realtimeSlices': workers}


def reduce(run, empty_rules=False):
    run = Path(run)
    rules = [] if empty_rules else statement_phase.DEFAULT_RULES
    sql = statement_phase.reduce_point(run, rules)
    writes = sql['acceptedWrites']['total']
    topology = recorded_topology(run)
    slices = topology['evaluatorSlices']
    cpu = main_thread.reduce_services(run, slices, sql['windowNs'], writes)
    smoke = {}
    try:
        smoke = json.loads((run / 'smoke.json').read_text())
    except (OSError, ValueError):
        pass
    identity = {}
    try:
        identity = json.loads((run / 'candidate.json').read_text())
    except (OSError, ValueError):
        pass
    return {
        'version': 1, 'kind': 'evaluator-statement-smoke-v1',
        'candidate': {k: identity.get(k) for k in ('reference', 'imageId', 'core', 'deploy')},
        'topology': topology,
        'runnerSmokeVerdict': smoke.get('verdict', 'UNMEASURED'), 'runnerOracles': smoke.get('oracles'),
        'acceptedWrites': sql['acceptedWrites'], 'windowSeconds': sql['windowSeconds'], 'cycles': sql['cycles'],
        'statementsPerWrite': {'total': sql['total']['perWrite'],
                               'api': sql['api']['perWrite'],
                               'byRole': {k: v['perWrite'] for k, v in sql['roles'].items()},
                               'byPhase': {k: v['perWrite'] for k, v in sql['phases'].items()}},
        'executionMsPerWrite': {'total': sql['total']['msPerWrite'],
                                'api': sql['api']['msPerWrite'],
                                'byRole': {k: v['msPerWrite'] for k, v in sql['roles'].items()},
                                'byPhase': {k: v['msPerWrite'] for k, v in sql['phases'].items()}},
        'attributedShare': sql['attributedShare'],
        'mainThread': cpu,
        'shapes': sql['shapes'],
        'rules': 'empty (negative control)' if empty_rules else 'default',
        'scope': 'Totals and phases cover four evaluator roles. API figures cover nsdemo_api and nsdemo_lifetime_api '
                 'over the same window, including reads. Both use HTTP-accepted writes plus stored probe writes.',
    }


def compare(summary, baseline):
    """Figures only: observed, baseline, delta and ratio for each reported number."""
    def rows(a, b, prefix=''):
        out = {}
        for k in sorted(set(a) | set(b)):
            x, y = a.get(k), b.get(k)
            if isinstance(x, dict) or isinstance(y, dict):
                out.update(rows(x or {}, y or {}, prefix + k + '.'))
            elif isinstance(x, (int, float)) or isinstance(y, (int, float)):
                out[prefix + k] = {'observed': x, 'baseline': y,
                                   'delta': round(x - y, 3) if None not in (x, y) else None,
                                   'ratio': round(x / y, 3) if None not in (x, y) and y else None}
        return out
    def pick(s):
        times = s['executionMsPerWrite']
        return {'statementsPerWrite': s['statementsPerWrite'],
                'executionMsPerWrite': {key: times[key] for key in ('total', 'api') if key in times},
                'mainThreadMsPerWrite': s['mainThread'].get('mainThreadMsPerWrite')}
    return {'kind': 'evaluator-statement-smoke-comparison-v1', 'gate': False,
            'baselineCandidate': baseline.get('candidate'), 'observedCandidate': summary.get('candidate'),
            'workloadMatches': baseline.get('workload') == summary.get('workload'),
            'figures': rows(pick(summary), pick(baseline))}


def markdown(summary, comparison=None):
    s = summary
    lines = [f"core `{(s['candidate'].get('core') or '?')[:10]}` image `{(s['candidate'].get('imageId') or '?')[7:19]}`; "
             f"runner smoke verdict {s['runnerSmokeVerdict']}; accepted writes {s['acceptedWrites']['total']} "
             f"(http {s['acceptedWrites']['http']}, probe {s['acceptedWrites']['probeStored']}); window {s['windowSeconds']} s; "
             f"cycles {s['cycles']}", '',
             '| statements per accepted write | value | baseline |', '|---|---:|---:|']
    topology = s.get('topology')
    if topology:
        lines.insert(1, f"Input transport {topology['inputTransport']}, API replicas {topology['apiReplicas']}, "
                        f"evaluator slices {topology['evaluatorSlices']}, realtime slices {topology['realtimeSlices']}.")
    base = (comparison or {}).get('figures', {})
    def row(key, label):
        v = base.get(key, {})
        lines.append(f"| {label} | {v.get('observed', '')} | {v.get('baseline', '') if comparison else ''} |")
    for k, v in s['statementsPerWrite']['byRole'].items():
        lines.append(f"| role {k} | {v} | {base.get('statementsPerWrite.byRole.' + k, {}).get('baseline', '')} |")
    for k, v in s['statementsPerWrite']['byPhase'].items():
        lines.append(f"| phase {k} | {v} | {base.get('statementsPerWrite.byPhase.' + k, {}).get('baseline', '')} |")
    lines.append(f"| **evaluator total** | **{s['statementsPerWrite']['total']}** | {base.get('statementsPerWrite.total', {}).get('baseline', '')} |")
    lines.append(f"| API and API lifecycle roles | {s['statementsPerWrite']['api']} | {base.get('statementsPerWrite.api', {}).get('baseline', '')} |")
    m = s['mainThread']
    lines += ['', f"executor ms per write (evaluator / API) {s['executionMsPerWrite']['total']} / {s['executionMsPerWrite']['api']}; main thread: {m.get('status')} "
              f"{m.get('mainThreadMsPerWrite', '')} ms per write (busy share {m.get('mainThreadBusyShare', '')}, "
              f"whole process {m.get('processMsPerWrite', '')} ms per write); attributed share {s['attributedShare']}"]
    for service, value in m.get('byService', {}).items():
        lines.append(f"{service} main thread: {value['status']}, {value.get('mainThreadMsPerWrite', '—')} ms per accepted write.")
    if comparison:
        lines.append(f"comparison is a figure, not a gate; workload matches baseline: {comparison['workloadMatches']}")
    return '\n'.join(lines) + '\n'


def finish(run, out, baseline_path, workload, empty_rules=False):
    summary = reduce(run, empty_rules)
    summary['workload'] = workload
    comparison = None
    if baseline_path and Path(baseline_path).is_file():
        comparison = compare(summary, json.loads(Path(baseline_path).read_text()))
        (out / 'comparison.json').write_text(json.dumps(comparison, indent=1) + '\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    text = markdown(summary, comparison)
    (out / 'summary.md').write_text(text)
    print(text)
    return summary


def busy():
    load = os.getloadavg()[0]
    require(load <= (os.cpu_count() or 1), f'SMOKE_HOST_BUSY:load={load:.1f}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('build', 'run'):
        p = sub.add_parser(name)
        p.add_argument('--core', help='core commit, branch, or clean cgm-remote-monitor worktree path')
        p.add_argument('--deploy-commit', help='Deploy revision for an image built from --core')
        p.add_argument('--scratch', help='private directory for build worktrees and logs (default: --out)')
        if name == 'run':
            p.add_argument('--input-transport', choices=('pgstream', 'writer-driven'), default='pgstream')
            p.add_argument('--replicas', type=int, choices=range(1, DISCOVERY_MAX_API_REPLICAS + 1), help='API processes (writer-driven defaults to 2)')
            p.add_argument('--static-workers', type=int, choices=range(1, DISCOVERY_MAX_WORKERS + 1), help='Evaluator and realtime slices per role (writer-driven defaults to 2)')
            p.add_argument('--history-anchor-ms', type=int, help='Seed 72 SGVs per tenant ending at this shared five-minute UTC anchor')
            p.add_argument('--plan-only', action='store_true', help='Resolve and print the runner plan without starting a fixture')
            p.add_argument('--image', help='existing image reference with core/deploy revision labels')
            p.add_argument('--out', required=True, help='new private output directory (outside any checkout)')
            p.add_argument('--project', help='Compose project name (default evaluator-m-smoke-<core10>)')
            p.add_argument('--baseline', default=str(BASELINE))
            for k, v in WORKLOAD.items():
                p.add_argument('--' + k, type=type(v), default=v)
    r = sub.add_parser('reduce')
    r.add_argument('run')
    r.add_argument('--baseline', default=str(BASELINE))
    r.add_argument('--empty-rules', action='store_true', help='negative control: everything must be unattributed')
    c = sub.add_parser('compare')
    c.add_argument('summary')
    c.add_argument('baseline')
    a = ap.parse_args()
    core_repo, deploy_repo = repo('NS_SMOKE_CORE_REPO', 'cgm-remote-monitor-official'), repo('NS_SMOKE_DEPLOY_REPO', 'nightscout-deploy')
    if a.cmd == 'compare':
        return print(json.dumps(compare(json.loads(Path(a.summary).read_text()), json.loads(Path(a.baseline).read_text())), indent=1))
    if a.cmd == 'reduce':
        run = Path(a.run)
        out = Path(a.run).parent / ('reduce-empty-rules' if a.empty_rules else 'reduce')
        out.mkdir(exist_ok=True)
        workload = {}
        try:
            workload = json.loads((run.parent / 'workload.json').read_text())
        except (OSError, ValueError):
            pass
        return finish(run, out, None if a.empty_rules else a.baseline, workload, a.empty_rules) and None
    if a.cmd == 'build':
        require(a.core, 'SMOKE_CORE_REQUIRED')
        scratch = Path(a.scratch or '.').resolve()
        tag, image_id, how = build(resolve(a.core, core_repo), a.deploy_commit or DEFAULT_DEPLOY, core_repo, deploy_repo, scratch)
        return print(json.dumps({'image': tag, 'imageId': image_id, 'origin': how}))
    # run
    require(bool(a.core) != bool(a.image), 'SMOKE_CORE_XOR_IMAGE')
    out = Path(a.out).resolve()
    require(not out.exists(), 'SMOKE_OUT_EXISTS')
    require(not str(out).startswith(str(ALIGNMENT.resolve())), 'SMOKE_OUT_INSIDE_CHECKOUT')
    if not a.plan_only:
        busy()
    out.mkdir(parents=True, mode=0o700)
    t0 = time.monotonic()
    if a.core:
        deploy = a.deploy_commit or (WRITER_DEPLOY if a.input_transport == 'writer-driven' else DEFAULT_DEPLOY)
        tag, image_id, how = build(resolve(a.core, core_repo), deploy, core_repo, deploy_repo, Path(a.scratch or out))
    else:
        tag = a.image
        image_id, _ = labels(tag)
        require(image_id is not None, 'SMOKE_IMAGE_MISSING')
        how = 'given'
    _, lab = labels(tag)
    core, deploy = lab.get('org.opencontainers.image.revision'), lab.get('org.nightscout.deploy.revision')
    require(bool(core and deploy and re.fullmatch(r'[0-9a-f]{40}', core) and re.fullmatch(r'[0-9a-f]{40}', deploy)), 'SMOKE_IMAGE_LABELS')
    if a.image and a.deploy_commit:
        require(resolve(a.deploy_commit, deploy_repo) == deploy, 'SMOKE_IMAGE_DEPLOY_MISMATCH')
    project = a.project or f'evaluator-m-smoke-{core[:10]}'
    workload = {k: getattr(a, k.replace('-', '_')) for k in WORKLOAD}
    if a.history_anchor_ms is not None:
        workload['history'] = {'mode': populated_history.MODE, 'anchorUnixMs': a.history_anchor_ms}
        populated_history.validate(workload['history'])
    (out / 'workload.json').write_text(json.dumps(workload) + '\n')
    (out / 'image.json').write_text(json.dumps({'image': tag, 'imageId': image_id, 'origin': how, 'core': core, 'deploy': deploy}) + '\n')
    cfg = out / 'config.json'
    configuration = config(core, deploy, core_repo, deploy_repo, project, workload,
                           transport=a.input_transport, replicas=a.replicas, workers=a.static_workers)
    cfg.write_text(json.dumps(configuration, indent=1) + '\n')
    if a.plan_only:
        plan = sh([sys.executable, str(RUNNER), 'plan', str(cfg), '--candidate', tag])
        (out / 'plan.json').write_text(plan + '\n')
        return print(plan)
    run = out / 'run'
    samplers = []
    code = None
    try:
        for service, path in main_thread.sample_paths(run, configuration['prepare']['static-workers']).items():
            samplers.append(main_thread.Sampler(project, path, service=service).start())
        with (out / 'runner.log').open('w') as log:
            code = subprocess.run([sys.executable, str(RUNNER), 'run', str(cfg), str(run), '--candidate', tag],
                                  stdout=log, stderr=subprocess.STDOUT).returncode
    finally:
        for sampler in samplers:
            sampler.stop()
    (out / 'elapsed.json').write_text(json.dumps({'seconds': round(time.monotonic() - t0, 1), 'runnerExit': code}) + '\n')
    if code and not (run / 'fixture/load/after-pg-statements.tsv').is_file():
        raise SystemExit(f'SMOKE_RUNNER_EXIT:{code} (see {out}/runner.log)')
    finish(run, out, a.baseline, workload)
    if code:
        raise SystemExit(f'SMOKE_RUNNER_EXIT:{code} (see {out}/runner.log); figures above are from a failed run')


if __name__ == '__main__':
    main()
