#!/usr/bin/env python3
# Break-it controls for the admin-lifecycle lane: mutate, run, restore, rerun.
import json, os, re, subprocess, sys

W = os.environ['LANE_WORKTREE']  # externals/work/crm-admin-lifecycle-20261110
OUT = sys.argv[1]  # usage: LANE_WORKTREE=<worktree> controls-run.py controls.json
ENV = dict(os.environ, NODE_ENV='test', NS_ADMIN_LIFECYCLE_DOCKER_TEST='1', NS_TENANT_OWNERSHIP_DOCKER_TEST='1', NS_ADMIN_ROLE_DOCKER_TEST='1')
FIT = 'tests/admin-lifecycle-fit.integration.test.js'
STORE = 'tests/tenant-ownership-postgres.integration.test.js'

CONTROLS = [
  ('C0', 'census exemption removed (any non-participant refuses, as before the decision)',
   [('lib/server/serve/operation-cohort.js', "    if (actor.clinical === false) { exempt++; continue; }\n", '')], [FIT]),
  ('C1', 'plan grants ownership_operator SELECT on entries (one clinical table)',
   [('deploy/multitenant/config.js', "  sql.push(...require('../../lib/tenant-lifecycle/tenant-phase').phaseGrants({namespace:ns.control,role:r.ownership_operator}));\n",
     "  sql.push(...require('../../lib/tenant-lifecycle/tenant-phase').phaseGrants({namespace:ns.control,role:r.ownership_operator}));\n  grant('SELECT',table('entries','entries'),'ownership_operator');\n")],
   [FIT, 'tests/admin-role.test.js']),
  ('C2', 'exempt by role name instead of by grants',
   [('lib/server/serve/operation-cohort.js', "if (actor.clinical === false) {", "if (/_ownership_operator$/.test(actor.role)) {")], [FIT]),
  ('C1+C2', 'clinical grant in the plan AND name-based exemption',
   [('deploy/multitenant/config.js', "  sql.push(...require('../../lib/tenant-lifecycle/tenant-phase').phaseGrants({namespace:ns.control,role:r.ownership_operator}));\n",
     "  sql.push(...require('../../lib/tenant-lifecycle/tenant-phase').phaseGrants({namespace:ns.control,role:r.ownership_operator}));\n  grant('SELECT',table('entries','entries'),'ownership_operator');\n"),
    ('lib/server/serve/operation-cohort.js', "if (actor.clinical === false) {", "if (/_ownership_operator$/.test(actor.role)) {")], [FIT]),
  ('C3', 'ownership phase check removed (plan regardless of lifecycle)',
   [('lib/tenant-ownership/postgres.js', "lifecycle.active ? plan(operation, proposal, state) : { code: 'OWNERSHIP_TENANT_INACTIVE' }", "plan(operation, proposal, state)")], [STORE, FIT]),
  ('C3b', 'phase read without the shared window lock (hold: false)',
   [('lib/tenant-ownership/postgres.js', "tenant: actor.tenant, hold: true })", "tenant: actor.tenant, hold: false })")], [STORE, FIT]),
  ('C4a', 'plane rule no longer checks the consumer listener\'s port',
   [('lib/server/serve/listeners.js', "  if (consumer && overlaps(spec, consumer)) {", "  if (false && consumer && overlaps(spec, consumer)) {")], ['tests/serve-listeners.test.js', 'tests/admin-role.test.js']),
  ('C4b', 'same port allowed everywhere (overlaps always false)',
   [('lib/server/serve/listeners.js', "  if (a.port !== b.port || a.port === 0) return false;", "  return false;")], ['tests/serve-listeners.test.js', 'tests/admin-role.test.js']),
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
