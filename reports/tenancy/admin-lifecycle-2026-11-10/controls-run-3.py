#!/usr/bin/env python3
# Break-it controls for the admin-lifecycle lane: mutate, run, restore, rerun.
import json, os, re, subprocess, sys

W = os.environ['LANE_WORKTREE']  # externals/work/crm-admin-lifecycle-20261110
OUT = sys.argv[1]
ENV = dict(os.environ, NODE_ENV='test', NS_ADMIN_LIFECYCLE_DOCKER_TEST='1', NS_TENANT_OWNERSHIP_DOCKER_TEST='1', NS_ADMIN_ROLE_DOCKER_TEST='1')
FIT = 'tests/admin-lifecycle-fit.integration.test.js'
STORE = 'tests/tenant-ownership-postgres.integration.test.js'

CONTROLS = [
  ('B1', 'driver drops ledgerNamespace', [('deploy/multitenant/restore.js', " ledgerNamespace: config.control.namespace,", "")], [FIT]),
  ('B2', 'operator retention grant removed', [('deploy/multitenant/config.js', "  grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until),UPDATE(phase,restored_at)',table('control','tenant_lifecycle_key_retention'),'operator');\n", "")], [FIT]),
  ('L1', 'grant without UPDATE(restored_at)', [('deploy/multitenant/config.js', "grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until),UPDATE(phase,restored_at)',", "grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until),UPDATE(phase)',")], [FIT]),
  ('L2', 'grant without SELECT(retain_until)', [('deploy/multitenant/config.js', "grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until),UPDATE(phase,restored_at)',", "grant('SELECT(request_id,tenant_id,phase,retained_at),UPDATE(phase,restored_at)',")], [FIT]),
  ('L3', 'grant without SELECT(tenant_id)', [('deploy/multitenant/config.js', "grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until),UPDATE(phase,restored_at)',", "grant('SELECT(request_id,phase,retained_at,retain_until),UPDATE(phase,restored_at)',")], [FIT]),
  ('L4', 'grant without any UPDATE', [('deploy/multitenant/config.js', "grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until),UPDATE(phase,restored_at)',", "grant('SELECT(request_id,tenant_id,phase,retained_at,retain_until)',")], [FIT]),
]

def mocha(files):
    p = subprocess.run(['timeout', '600', 'node_modules/.bin/mocha', '--fail-zero', '--timeout', '120000', '--exit', '--require', './tests/hooks.js', *files],
                       cwd=W, env=ENV, capture_output=True, text=True)
    out = p.stdout + p.stderr
    passing = re.search(r'(\d+) passing', out); failing = re.search(r'(\d+) failing', out)
    fails = re.findall(r'^\s+\d+\) .*\n(?:.*\n){0,1}\s+([A-Za-z]*Error[^\n]*|Error[^\n]*)', out, re.M)
    titles = re.findall(r'^\s+\d+\) (.+)$', out, re.M)
    return {'exit': p.returncode, 'passing': int(passing.group(1)) if passing else 0, 'failing': int(failing.group(1)) if failing else 0,
            'failures': titles[len(titles)//2:] if titles else [], 'symptoms': fails[:6], 'tail': out[-3000:]}

def containers():
    return subprocess.run(['docker', 'ps', '-aq', '--filter', 'label=nightscout.test=admin-lifecycle-fit', '--filter', 'label=nightscout.test=tenant-ownership'],
                          capture_output=True, text=True).stdout.split()

results = []
for cid, what, edits, files in CONTROLS:
    for path, old, new in edits:
        full = os.path.join(W, path); s = open(full).read()
        assert s.count(old) == 1, (cid, path, old)
        open(full, 'w').write(s.replace(old, new))
    mutated = mocha(files)
    subprocess.run(['git', 'checkout', '--', *sorted({e[0] for e in edits})], cwd=W, check=True)
    restored = mocha(files)
    clean = subprocess.run(['git', 'status', '--short'], cwd=W, capture_output=True, text=True).stdout.strip()
    row = {'id': cid, 'mutation': what, 'files': files, 'mutated': mutated, 'restored': {k: restored[k] for k in ('exit', 'passing', 'failing', 'failures')},
           'tree_clean': clean == '', 'containers_left': containers()}
    results.append(row)
    print(cid, 'mutated', mutated['passing'], '/', mutated['failing'], 'restored', restored['passing'], '/', restored['failing'], 'clean', clean == '', flush=True)
    for title in mutated['failures']: print('   FAIL', title, flush=True)
json.dump(results, open(OUT, 'w'), indent=1)
