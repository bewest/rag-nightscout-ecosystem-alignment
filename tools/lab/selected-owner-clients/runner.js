'use strict';
// Explicit selected-subject lab. Never imported by registered/default M4 gate.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawn, execFileSync } = require('node:child_process');
const { Lab, stableJSON } = require('../m4-client-binaries/lab');
const { CATALOGUE, measureRefusal, assertRefusal, compareAdmitted } = require('./contract');
const fixtures = require('../m4-client-binaries/clients/fixtures');
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const HEAD = '8713395992e07b4dd2cde61ee972e9a15c8ada8c';
class SelectedLab extends Lab {
  spawnServer (args, env, label) {
    assert.equal(label, 'preview');
    const child = spawn(process.execPath, [path.join(__dirname, 'server.js')], {
      cwd: this.opt.worktree, env: { ...env, SELECTED_OWNER_ARCHIVE: this.opt.worktree,
        SELECTED_OWNER_OPERATOR_PG: this.preview.adminURI, SELECTED_OWNER_LAB_MODE: this.opt.mode },
      stdio: ['ignore', 'pipe', 'pipe'] });
    const worker = { label, child, stdout: '', stderr: '', exit: null };
    child.stdout.on('data', b => { worker.stdout += b; });
    child.stderr.on('data', b => { worker.stderr += b; });
    worker.exited = new Promise(resolve => child.once('exit', (code, signal) => { worker.exit = { code, signal }; resolve(worker.exit); }));
    this.children.push(worker);
    return worker;
  }
  async snapshot () {
    const value = {};
    for (const tenant of [A, B]) for (const domain of this.preview.domainNames)
      value[tenant + ':' + domain] = (await this.preview.rows(domain, tenant)).map(stableJSON).sort();
    return value;
  }
  async subjectUpload (domain, phase) {
    const root = path.join(process.env.NS_M4_EXTERNALS, 'oref0');
    const file = path.join(this.state, phase + '-' + domain + '.json');
    const expected = fixtures[domain](this.base + (phase === 'tightened' ? 60000 : 0));
    fs.writeFileSync(file, JSON.stringify(expected));
    const mark = this.since('preview');
    const result = await this.runClient(root, { PATH: path.join(root, 'bin') + ':/usr/local/bin:/usr/bin:/bin' },
      ['bash', path.join(root, 'bin/ns-upload.sh'), this.urlFor('preview'), 'token=' + this.token('preview'), domain + '.json', file], 'subject oref0 ' + phase + ' ' + domain);
    const record = this.lastRecord('preview', mark, r => r.method === 'POST');
    assert.ok(record, 'actual pinned client must reach protected route');
    const rows = await this.preview.rows(domain);
    const contains = (a, e) => e && typeof e === 'object' ? Object.keys(e).every(k => contains(a?.[k], e[k])) : a === e;
    if (phase === 'admitted' || this.opt.mode === 'reference') {
      assert.equal(record.status, 200); assert.equal(result.status, 0);
      assert.ok(expected.every(e => rows.some(a => contains(a, e))), 'independent SQL oracle must contain expected synthetic client values');
    }
    const cell = await this.cell('preview', phase + ':' + domain, domain, record, { exit: result.status });
    return { record, cell };
  }
  async exercise () {
    await this.openPreview();
    for (const domain of this.preview.domainNames) assert.equal((await this.preview.rows(domain, B)).length, 0, 'tenant B starts empty');
    const admitted = {};
    for (const domain of ['entries', 'treatments', 'devicestatus']) admitted[domain] = (await this.subjectUpload(domain, 'admitted')).cell;
    for (const domain of this.preview.domainNames) assert.equal((await this.preview.rows(domain, B)).length, 0, 'admitted subject writes leave B empty');
    const before = await this.snapshot();
    await this.preview.admin.query('UPDATE preview_auth.tenant_owner_policy SET ceiling=$2 WHERE tenant_id=$1', [A, []]);
    const tightened = await this.subjectUpload('entries', 'tightened');
    const after = await this.snapshot();
    fs.writeFileSync(path.join(this.opt.out, 'tightening-oracle.json'), JSON.stringify({ before, after, status: tightened.record.status, ...measureRefusal(tightened.record, before, after) }, null, 2));
    if (this.opt.mode === 'selected') assertRefusal(tightened.record, before, after);
    else assert.notDeepEqual(after, before, 'unselected reference intentionally retains grant after ceiling change');
    // Pinned cgmsim cannot present a subject credential. Observe its real root
    // carrier as an unsupported selected principal; never translate credentials.
    const mark = this.since('preview'); const beforeRoot = await this.snapshot();
    const checkout = path.join(process.env.NS_M4_EXTERNALS, 'cgmsim-lib');
    const result = await this.runClient(checkout, { CGMSIM_LIB: checkout, NS_URL: this.urlFor('preview'), API_SECRET: this.rootSecret('preview') },
      ['node', path.join(__dirname, '../m4-client-binaries/clients/cgmsim-driver.js'), 'upload-entry'], 'cgmsim root principal boundary');
    const root = this.lastRecord('preview', mark, r => r.method === 'POST');
    assert.ok(root, 'actual cgmsim request must be observed');
    if (this.opt.mode === 'selected') {
      assert.equal(root.status, 503, 'read-derived existing unmapped principal error predicts 503; not a compatibility waiver');
      assert.deepEqual(await this.snapshot(), beforeRoot, 'selected root refusal has no stored effect');
    } else assert.equal(root.status, 200);
    return { versions: { postgres: this.preview.pgVersion, vault: this.preview.vaultVersion, node: process.version }, admitted, tightened: { status: tightened.record.status, cell: tightened.cell },
      cgmsimRoot: { status: root.status, exit: result.status }, checks: this.checks };
  }
}
async function run ({ worktree, out, control = false }) {
  assert.ok(process.env.NS_M4_EXTERNALS, 'explicit dedicated pinned-client root required');
  assert.ok(!fs.existsSync(out), 'fresh output required'); fs.mkdirSync(out, { mode: 0o700 });
  const pins = { oref0: 'd219baf9559d62a8bb0bd42014192a2d7c0839ef', 'cgmsim-lib': 'c09f9c039007a80a431baec6dbf852c52e3669db' };
  for (const [client, pin] of Object.entries(pins)) {
    const dir = path.join(process.env.NS_M4_EXTERNALS, client);
    assert.equal(execFileSync('git', ['-C', dir, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), pin);
    assert.equal(execFileSync('git', ['-C', dir, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' }).trim(), '');
  }
  const provenance = require('../m4-client-binaries/build-provenance')(path.join(process.env.NS_M4_EXTERNALS, 'cgmsim-lib'));
  assert.ok(provenance.ok); assert.equal(provenance.runtime_files, 94);
  if (control) {
    // Change archived scratch only. Selected bootstrap/root refusal stays active;
    // only the current ceiling intersection is ablated, so stale grants survive.
    const file = path.join(worktree, 'lib/subject-admin/owner-policy.js');
    const original = fs.readFileSync(file, 'utf8'); const target = 'project.has(permission) && ceiling.has(permission)';
    assert.equal(original.split(target).length, 2); fs.writeFileSync(file, original.replace(target, 'project.has(permission)'));
  }
  fs.cpSync(__dirname, path.join(out, 'instrument', 'selected-owner-clients'), { recursive: true });
  fs.cpSync(path.join(__dirname, '../m4-client-binaries'), path.join(out, 'instrument', 'm4-client-binaries'), { recursive: true });
  const capture = { head: HEAD, started: new Date().toISOString(), pins, control, provenance, catalogue: CATALOGUE, admittedClients: ['oref0'], rootBoundaryClients: ['cgmsim'], phases: {} };
  const base = Date.now();
  try {
    for (const mode of ['reference', 'selected']) {
      const dir = path.join(out, mode); fs.mkdirSync(dir);
      const lab = new SelectedLab({ worktree, out: dir, mode, clients: ['oref0', 'cgmsim'], pollCycles: 1 });
      fs.mkdirSync(lab.state); fs.mkdirSync(path.join(lab.state, 'bin'));
      const orefRoot = path.join(process.env.NS_M4_EXTERNALS, 'oref0');
      for (const [command, target] of Object.entries(require(path.join(orefRoot, 'package.json')).bin))
        fs.symlinkSync(path.resolve(orefRoot, target), path.join(lab.state, 'bin', command));
      lab.base = base; lab.head = HEAD;
      // canonical dockerArgs expects path.exists real node_modules; no cache writes.
      try { capture.phases[mode] = await lab.exercise(); }
      finally { capture.phases[mode] ||= {}; capture.phases[mode].cleanup = await lab.cleanup(); lab.log.end(); assert.ok(capture.phases[mode].cleanup.every(c => c.absent), 'owned containers absent'); }
    }
    compareAdmitted(capture.phases.reference.admitted, capture.phases.selected.admitted);
    capture.intentionalChanges = [{ phase: 'tightened', reason: 'selected current ceiling revokes existing subject grant on next operation',
      reference: capture.phases.reference.tightened.status, selected: capture.phases.selected.tightened.status },
    { phase: 'cgmsim-root', reason: 'root excluded; pinned cgmsim has no subject carrier; observed status requires separate compatibility disposition',
      reference: capture.phases.reference.cgmsimRoot.status, selected: capture.phases.selected.cgmsimRoot.status }];
    capture.ok = true;
  } catch (error) { capture.ok = false; capture.failure = error.message; }
  capture.finished = new Date().toISOString();
  fs.writeFileSync(path.join(out, 'selected-owner-run.json'), JSON.stringify(capture, null, 2));
  return capture;
}
module.exports = { SelectedLab, run, HEAD };
