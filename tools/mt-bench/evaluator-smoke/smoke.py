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
RUNNER = HERE.parent / 'm7-joined' / 'runner.py'
sys.path.insert(0, str(HERE))
import main_thread  # noqa: E402
import statement_phase  # noqa: E402

DEFAULT_DEPLOY = 'f57a8c335be9895c0ce4596d8a73275444b16541'  # nightscout-deploy; image inputs equal at 09f2223
K6_IMAGE = 'sha256:eeb0db19cd8d263aa57346cdbc7ea18e6fcfb2ba9497746a7ae82ceefc8c9fa5'  # grafana/k6:1.3.0
POSTGRES_IMAGE = 'sha256:21e7e1665c3dd2fdd80ebd9ce6d36fb160d6a4129683b315b6492a71d87bfda7'
BASELINE = HERE / 'baseline.json'
WORKLOAD = {'tenants': 16, 'load-seconds': 180, 'workload-scale': 24}


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout.strip()


def repo(env, default):
    return Path(os.environ.get(env) or ALIGNMENT / 'externals' / default)


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
    tag = f'ns-evaluator-smoke:{core[:12]}-{deploy[:12]}'
    image_id, lab = labels(tag)
    if image_id and lab.get('org.opencontainers.image.revision') == core and lab.get('org.nightscout.deploy.revision') == deploy:
        return tag, image_id, 'reused'
    sh(['git', '-C', str(deploy_repo), 'rev-parse', '--verify', deploy + '^{commit}'])
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


def config(core, deploy, core_repo, deploy_repo, project, workload):
    backend, edge = free_subnets()
    head = sh(['git', '-C', str(ALIGNMENT), 'rev-parse', 'HEAD'])
    return {
        'version': 1, 'tier': 'smoke', 'helperHead': head, 'k6Image': K6_IMAGE,
        'workSeconds': 2400, 'cleanupSeconds': 300,
        'prepare': {
            'core-repo': str(core_repo), 'core-commit': core, 'deploy-repo': str(deploy_repo), 'deploy-commit': deploy,
            'postgres-image': POSTGRES_IMAGE, 'tenants': workload['tenants'], 'replicas': 1,
            'warmup-seconds': 5, 'idle-seconds': 5, 'load-seconds': workload['load-seconds'],
            'setup-seconds': 180, 'drain-seconds': 180, 'accel': 1, 'hot-factor': 1, 'sampler-interval': 5,
            'probe-every-ms': 10000, 'sockets-per-tenant': 1, 'logical-polling-clients': 2,
            'workload-mix': 'realistic-v1', 'workload-scale': workload['workload-scale'],
            'primer-concurrency': 4, 'jwt-setup-concurrency': 4, 'fixture-project': project,
            'maximum-run-minutes': 40, 'backend-subnet': backend, 'edge-subnet': edge, 'quiet-load': os.cpu_count() or 1,
            'pgstream-topology': 'external-service-v1', 'completion-contract': 'evaluator-work-v2', 'static-workers': 1,
        },
    }


def reduce(run, empty_rules=False):
    run = Path(run)
    rules = [] if empty_rules else statement_phase.DEFAULT_RULES
    sql = statement_phase.reduce_point(run, rules)
    writes = sql['acceptedWrites']['total']
    samples = run.parent / (run.name + '-main-thread.jsonl')
    cpu = main_thread.reduce(samples, sql['windowNs'], writes) if samples.is_file() else {'status': 'UNMEASURED', 'reason': 'NO_SAMPLER_FILE'}
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
        'runnerSmokeVerdict': smoke.get('verdict', 'UNMEASURED'), 'runnerOracles': smoke.get('oracles'),
        'acceptedWrites': sql['acceptedWrites'], 'windowSeconds': sql['windowSeconds'], 'cycles': sql['cycles'],
        'statementsPerWrite': {'total': sql['total']['perWrite'],
                               'byRole': {k: v['perWrite'] for k, v in sql['roles'].items()},
                               'byPhase': {k: v['perWrite'] for k, v in sql['phases'].items()}},
        'executionMsPerWrite': {'total': sql['total']['msPerWrite'],
                                'byRole': {k: v['msPerWrite'] for k, v in sql['roles'].items()},
                                'byPhase': {k: v['msPerWrite'] for k, v in sql['phases'].items()}},
        'attributedShare': sql['attributedShare'],
        'mainThread': cpu,
        'shapes': sql['shapes'],
        'rules': 'empty (negative control)' if empty_rules else 'default',
        'scope': 'pg_stat_statements top-level calls of the four evaluator roles between the load bookends, '
                 'divided by HTTP-accepted writes plus stored probe writes; executor time, not CPU',
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
    pick = lambda s: {'statementsPerWrite': s['statementsPerWrite'], 'executionMsPerWrite': {'total': s['executionMsPerWrite']['total']},
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
    base = (comparison or {}).get('figures', {})
    def row(key, label):
        v = base.get(key, {})
        lines.append(f"| {label} | {v.get('observed', '')} | {v.get('baseline', '') if comparison else ''} |")
    for k, v in s['statementsPerWrite']['byRole'].items():
        lines.append(f"| role {k} | {v} | {base.get('statementsPerWrite.byRole.' + k, {}).get('baseline', '')} |")
    for k, v in s['statementsPerWrite']['byPhase'].items():
        lines.append(f"| phase {k} | {v} | {base.get('statementsPerWrite.byPhase.' + k, {}).get('baseline', '')} |")
    lines.append(f"| **total** | **{s['statementsPerWrite']['total']}** | {base.get('statementsPerWrite.total', {}).get('baseline', '')} |")
    m = s['mainThread']
    lines += ['', f"executor ms per write {s['executionMsPerWrite']['total']}; main thread: {m.get('status')} "
              f"{m.get('mainThreadMsPerWrite', '')} ms per write (busy share {m.get('mainThreadBusyShare', '')}, "
              f"whole process {m.get('processMsPerWrite', '')} ms per write); attributed share {s['attributedShare']}"]
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
        p.add_argument('--deploy-commit', default=DEFAULT_DEPLOY)
        p.add_argument('--scratch', help='private directory for build worktrees and logs (default: --out)')
        if name == 'run':
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
        tag, image_id, how = build(resolve(a.core, core_repo), a.deploy_commit, core_repo, deploy_repo, scratch)
        return print(json.dumps({'image': tag, 'imageId': image_id, 'origin': how}))
    # run
    require(bool(a.core) != bool(a.image), 'SMOKE_CORE_XOR_IMAGE')
    out = Path(a.out).resolve()
    require(not out.exists(), 'SMOKE_OUT_EXISTS')
    require(not str(out).startswith(str(ALIGNMENT.resolve())), 'SMOKE_OUT_INSIDE_CHECKOUT')
    busy()
    out.mkdir(parents=True, mode=0o700)
    t0 = time.monotonic()
    if a.core:
        tag, image_id, how = build(resolve(a.core, core_repo), a.deploy_commit, core_repo, deploy_repo, Path(a.scratch or out))
    else:
        tag = a.image
        image_id, _ = labels(tag)
        require(image_id is not None, 'SMOKE_IMAGE_MISSING')
        how = 'given'
    _, lab = labels(tag)
    core, deploy = lab.get('org.opencontainers.image.revision'), lab.get('org.nightscout.deploy.revision')
    require(bool(core and deploy and re.fullmatch(r'[0-9a-f]{40}', core) and re.fullmatch(r'[0-9a-f]{40}', deploy)), 'SMOKE_IMAGE_LABELS')
    project = a.project or f'evaluator-m-smoke-{core[:10]}'
    workload = {k: getattr(a, k.replace('-', '_')) for k in WORKLOAD}
    (out / 'workload.json').write_text(json.dumps(workload) + '\n')
    (out / 'image.json').write_text(json.dumps({'image': tag, 'imageId': image_id, 'origin': how, 'core': core, 'deploy': deploy}) + '\n')
    cfg = out / 'config.json'
    cfg.write_text(json.dumps(config(core, deploy, core_repo, deploy_repo, project, workload), indent=1) + '\n')
    run = out / 'run'
    sampler = main_thread.Sampler(project, out / 'run-main-thread.jsonl').start()
    code = None
    try:
        with (out / 'runner.log').open('w') as log:
            code = subprocess.run([sys.executable, str(RUNNER), 'run', str(cfg), str(run), '--candidate', tag],
                                  stdout=log, stderr=subprocess.STDOUT).returncode
    finally:
        sampler.stop()
    (out / 'elapsed.json').write_text(json.dumps({'seconds': round(time.monotonic() - t0, 1), 'runnerExit': code}) + '\n')
    finish(run, out, a.baseline, workload)
    if code:
        raise SystemExit(f'SMOKE_RUNNER_EXIT:{code} (see {out}/runner.log); figures above are from a failed run')


if __name__ == '__main__':
    main()
