#!/usr/bin/env python3
"""Break-it controls for the admin-role ownership composition.

Each control applies one source mutation in the lane worktree, runs the named
tests, records the summary and first failure lines, restores the file with
`git checkout --`, reruns, and checks the tree is clean. Results: controls.json.
"""
import json, os, re, subprocess, sys

WT = sys.argv[1]
OUT = sys.argv[2]
MOCHA = ['node_modules/.bin/mocha', '--fail-zero', '--timeout', '90000', '--exit', '--require', './tests/hooks.js']
NATIVE = 'tests/admin-role-ownership.integration.test.js'
UNIT = 'tests/admin-role.test.js'
ENV = {**os.environ, 'NODE_ENV': 'test', 'NS_ADMIN_ROLE_DOCKER_TEST': '1'}

CONTROLS = [
  ('C1a', 'admin composition loses the ownership module', 'lib/server/serve/admin-preview.js',
   'const modules = [await ownershipModule(config.ownership, resources)];', 'const modules = [];', [NATIVE],
   "node -e \"require('./lib/server/serve/admin-preview').boot({maxBytes:1,timeoutMs:1,ownership:{}}).catch(e=>console.log('in-process boot:',e.code||'',e.message))\""),
  ('C1b', 'admin listener serves no ownership routes (role still listens)', 'lib/server/serve/admin-preview.js',
   'app: handler,', "app: (req, res) => { res.writeHead(404); res.end(); },", [NATIVE], None),
  ('C2a', 'deployment plan drops INSERT on the audit table', 'deploy/multitenant/config.js',
   "  grant('INSERT',table('authorization','tenant_subject_admin_audit'),'ownership_operator');\n", '', [NATIVE, UNIT], None),
  ('C3', 'deployment plan also grants DELETE on owner actors', 'deploy/multitenant/config.js',
   "  grant('SELECT',table('authorization','tenant_authorization_subjects'),'ownership_operator');\n",
   "  grant('SELECT',table('authorization','tenant_authorization_subjects'),'ownership_operator');\n  grant('DELETE',table('authorization','tenant_owner_actors'),'ownership_operator');\n", [NATIVE, UNIT], None),
  ('C4', 'admin identity readiness check removed', 'lib/server/serve/admin-preview.js',
   '  await identityReadiness(selected.connectionString);\n', '', [NATIVE], None),
  ('C5', 'admin composition widens the operator tenant list', 'lib/server/serve/admin-preview.js',
   'tenants: selected.tenants.slice() })', "tenants: [...selected.tenants, '22222222-2222-4222-8222-222222222222'] })", [NATIVE], None),
  ('C6', 'serve accepts admin inside a lifecycle operation cohort', 'lib/server/serve/index.js',
   "  if (options.operationConfig && names.includes('admin')) {", '  if (false) {', [UNIT], None),
  ('C7', 'the runtime-revoke test no longer revokes', NATIVE,
   '      await admin.query(`REVOKE INSERT ON ${audit} FROM "${IDENTITY}"`);\n', '', [NATIVE], None),
]

def run(files):
  p = subprocess.run(MOCHA + files, cwd=WT, env=ENV, capture_output=True, text=True)
  out = p.stdout + p.stderr
  summary = ' / '.join(re.findall(r'^\s+(\d+ (?:passing|failing|pending))', out, re.M))
  fails = re.findall(r'^\s+\d+\) .*$', out, re.M)
  detail = []
  tail = out.split(' failing', 1)[1] if ' failing' in out else ''
  m = re.search(r'\n\s+1\) .*?(?=\n\s+2\) |\Z)', tail, re.S)
  if m:
    detail = [l.strip() for l in m.group(0).splitlines() if l.strip() and not l.strip().startswith('at ')][:14]
  return {'exit': p.returncode, 'summary': summary, 'failing_titles': [f.strip() for f in fails][:12], 'first_failure': detail}

def containers():
  return subprocess.run(['docker', 'ps', '-a', '--filter', 'label=nightscout.test=admin-role-ownership', '--format', '{{.Names}}'],
                        capture_output=True, text=True).stdout.split()

results = []
for cid, desc, path, old, new, files, probe in CONTROLS:
  full = os.path.join(WT, path)
  src = open(full).read()
  assert src.count(old) == 1, (cid, 'mutation anchor not unique')
  open(full, 'w').write(src.replace(old, new))
  row = {'id': cid, 'description': desc, 'file': path, 'tests': files}
  try:
    row['mutated'] = run(files)
    if probe:
      row['probe'] = subprocess.run(probe, shell=True, cwd=WT, capture_output=True, text=True).stdout.strip()
  finally:
    subprocess.run(['git', 'checkout', '--', path], cwd=WT, check=True)
  row['restored'] = run(files)
  row['tree_clean'] = subprocess.run(['git', 'status', '--porcelain'], cwd=WT, capture_output=True, text=True).stdout == ''
  row['containers_left'] = containers()
  results.append(row)
  print(cid, 'mutated:', row['mutated']['summary'], '| restored:', row['restored']['summary'], '| clean:', row['tree_clean'], flush=True)
json.dump(results, open(OUT, 'w'), indent=2)
