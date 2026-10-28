#!/usr/bin/env node
'use strict';
// Attack and audit harness for the tenant-configuration call-path lab.
//
//   node harness.js --scratch DIR [--only A,B0,B1,C] [--out results.json]
//
// For each design it starts a fresh deployment (one Node process per role,
// started with setsid nohup, PIDs recorded), provisions three synthetic
// tenants, runs five measures, stops every process by its recorded PID, and
// then repeats the run once per CONTROL: the same deployment with one
// protection deliberately removed. A control "reports" when at least one of
// the checks it is expected to flip changes against the design's baseline.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execSync } = require('child_process');
const { PORTS, matrix, call } = require('./lib/net');
const c = require('./lib/crypto');
const P = require('./lib/policy');
const store = require('./lib/store');

const LAB = __dirname;
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const SCRATCH = arg('--scratch', process.env.LAB_SCRATCH);
const ONLY = (arg('--only', 'A,B0,B1,C')).split(',');
const OUT = arg('--out', path.join(LAB, 'results.json'));
if (!SCRATCH) { console.error('--scratch DIR is required (outside the git tree)'); process.exit(2); }
const gitTop = execSync('git rev-parse --show-toplevel', { cwd: LAB }).toString().trim();
if (path.resolve(SCRATCH).startsWith(gitTop + path.sep)) { console.error('scratch must be outside the git tree'); process.exit(2); }

const TENANTS = ['t1', 't2', 't3'];
const OWNER = { t1: 'owner-1', t2: 'owner-2', t3: 'owner-3' };
const ROLE_PORTS = {
  idp: ['idp'], dashboard: ['dashboard'], 'tenant-admin': ['ta_public', 'ta_internal'],
  'ns-admin': ['ns_admin'], orchestrator: ['orchestrator'], secrets: ['sec_public', 'sec_internal', 'sec_operator']
};
const isB = (d) => d === 'B0' || d === 'B1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let runSeq = 0;

// ---------------------------------------------------------------- processes
function portsFree () {
  const out = execSync('ss -ltnH').toString();
  return Object.values(PORTS).filter((p) => out.includes(':' + p + ' '));
}

async function startRun (design, breaks, opt) {
  const busy = portsFree();
  if (busy.length) throw new Error('ports busy before start: ' + busy.join(','));
  const label = breaks.length ? breaks.join('+') : (opt.revealPolicy === 'fresh' ? 'fresh' : 'baseline');
  const runDir = path.join(SCRATCH, 'runs', `${String(++runSeq).padStart(2, '0')}-${design}-${label}`);
  fs.mkdirSync(path.join(runDir, 'keys'), { recursive: true, mode: 0o700 });
  fs.mkdirSync(path.join(runDir, 'logs'), { recursive: true });
  // Throwaway keys, per run, in scratch only.
  const kp = crypto.generateKeyPairSync('ed25519');
  const wk = (n, v) => fs.writeFileSync(path.join(runDir, 'keys', n), v, { mode: 0o600 });
  wk('idp.key', kp.privateKey.export({ type: 'pkcs8', format: 'pem' }));
  wk('idp.pub', kp.publicKey.export({ type: 'spki', format: 'pem' }));
  wk('kek', crypto.randomBytes(32));
  wk('installwide.key', crypto.randomBytes(32));
  for (const s of ['svc-tenant-admin', 'svc-orchestrator', 'svc-dashboard', 'svc-operator']) wk(s, c.random(24));
  const users = {}; for (const t of TENANTS) users[OWNER[t]] = { password: c.random(12) };
  wk('users.json', JSON.stringify(users));
  fs.writeFileSync(path.join(runDir, 'run.json'), JSON.stringify({
    design, breaks, revealPolicy: opt.revealPolicy || 'session', freshSeconds: opt.freshSeconds || 2
  }));
  const roles = ['idp', 'secrets', 'tenant-admin', 'ns-admin', 'dashboard'].concat(isB(design) || design === 'C' ? ['orchestrator'] : []);
  const pids = {};
  for (const r of roles) {
    const cmd = `setsid nohup node ${path.join(LAB, 'roles', r + '.js')} ${runDir} > ${path.join(runDir, 'logs', r + '.log')} 2>&1 < /dev/null & echo $!`;
    pids[r] = Number(execSync(cmd, { shell: '/bin/bash' }).toString().trim());
  }
  fs.writeFileSync(path.join(runDir, 'pids.json'), JSON.stringify(pids));
  const run = { design, breaks, label, runDir, pids, roles, mx: matrix(design, breaks), users, opt };
  for (let i = 0; i < 50; i++) {
    try { await assertAlive(run); return run; } catch (e) { await sleep(100); }
  }
  await assertAlive(run); // throws with the reason
  return run;
}

// A dead server refuses exactly like a secure one, so every measured run
// starts and ends here.
async function assertAlive (run) {
  for (const r of run.roles) {
    const pid = run.pids[r];
    process.kill(pid, 0);
    const cmdline = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8');
    if (!cmdline.includes(path.join('roles', r + '.js'))) throw new Error(`pid ${pid} is not ${r}`);
    for (const p of ROLE_PORTS[r]) {
      const h = await call(run.mx, 'harness', p, 'GET', '/health');
      if (h.status !== 200 || h.body.pid !== pid || h.body.role !== r) throw new Error(`${r}:${p} health ${h.status}`);
    }
  }
}

async function stopRun (run) {
  for (const r of run.roles) { try { process.kill(run.pids[r], 'SIGTERM'); } catch (e) { /* already gone */ } }
  for (let i = 0; i < 50; i++) {
    const alive = run.roles.filter((r) => { try { process.kill(run.pids[r], 0); return true; } catch (e) { return false; } });
    if (!alive.length && !portsFree().length) return;
    await sleep(100);
  }
  throw new Error('processes did not stop: ' + JSON.stringify(run.pids));
}

// ---------------------------------------------------------------- helpers
const as = (run, zone, port, method, p, body, headers) => call(run.mx, zone, port, method, p, body, headers);
const svcKey = (run, n) => fs.readFileSync(path.join(run.runDir, 'keys', n)).toString();
const db = (run) => store.load(run.runDir);
function resetDisplay (run, t) {
  const s = db(run);
  s.owner[t].DISPLAY_UNITS = 'mg/dl';
  s.policy[t].DISPLAY_UNITS = P.defaultPolicy().DISPLAY_UNITS;
  store.save(run.runDir, s);
}

async function login (run, user) {
  const r = await as(run, 'internet', 'dashboard', 'POST', '/session/login', { user, password: run.users[user].password });
  if (r.status !== 200) throw new Error('login failed ' + user);
  return { session: r.body.session, lab: r.body._lab };
}

async function idpAssertion (run, user) {
  const r = await as(run, 'internet', 'idp', 'POST', '/login', { user, password: run.users[user].password });
  return r.body.assertion;
}

async function setup (run) {
  const op = run.design === 'A' ? null : run.design === 'B1' ? { authorization: 'Service ' + svcKey(run, 'svc-operator') } : {};
  for (const t of TENANTS) {
    const r = op === null
      ? await as(run, 'operator', 'ns_admin', 'POST', '/tenants', { slug: t, owner: OWNER[t] })
      : await as(run, 'operator', 'orchestrator', 'POST', '/operator/tenants', { slug: t, owner: OWNER[t] }, op);
    if (r.status !== 200) throw new Error(`provision ${t}: ${r.status} ${JSON.stringify(r.body)}`);
  }
  run.conn = {}; run.sessions = {};
  for (const t of TENANTS) {
    const { session } = await login(run, OWNER[t]);
    run.conn[t] = 'synthetic-connector-' + c.random(9);
    const r = await as(run, 'internet', 'dashboard', 'POST', '/secret', { session, tenant: t, kind: 'plugin:connect', value: run.conn[t] });
    if (r.status !== 200) throw new Error(`secret ${t}: ${r.status} ${JSON.stringify(r.body)}`);
    run.sessions[t] = session;
  }
  // Only owner-1 stays logged in, so the dashboard holds one live session.
  for (const t of ['t2', 't3']) await as(run, 'internet', 'dashboard', 'POST', '/session/logout', { session: run.sessions[t] });
}

// ---------------------------------------------------------------- attacker
// An attacker who controls a component acts from that component's zone and
// from the internet, with exactly the credentials the component holds.
class Attacker {
  constructor (run, zones, creds) {
    this.run = run; this.zones = zones.concat('internet');
    this.creds = Object.assign({ ownerTokens: [], assertions: [], serviceTokens: {}, signingKeys: {}, idpKey: null }, creds);
  }

  async req (port, method, p, body, headers) {
    const zone = this.zones.find((z) => (this.run.mx[z] || []).includes(port));
    if (!zone) return { status: 0, body: { error: 'blocked-by-matrix' } };
    return call(this.run.mx, zone, port, method, p, body, headers);
  }

  async prepare () {
    const tk = this.creds.serviceTokens.tenantAdmin;
    if (tk) {
      for (const t of TENANTS) {
        const r = await this.req('sec_internal', 'POST', `/t/${t}/consume`, { kind: 'jwt' }, { authorization: 'Service ' + tk });
        if (r.status === 200) this.creds.signingKeys[t] = Buffer.from(r.body.key, 'base64url');
      }
    }
  }

  assertionsFor (t) {
    const out = this.creds.assertions.slice();
    if (this.creds.idpKey) {
      const n = c.now();
      out.push(c.signEd({ iss: 'lab-idp', aud: 'nightscout-lab', sub: OWNER[t], auth_time: n, iat: n, exp: n + 600 }, this.creds.idpKey));
    }
    return out;
  }

  async tokensFor (t) {
    const out = [];
    for (const tok of this.creds.ownerTokens) {
      out.push(['held-token', tok]);
      out.push(['forged-claim', c.forgeClaim(tok, { tenant: t, sub: OWNER[t] })]);
    }
    if (this.creds.signingKeys[t]) {
      const n = c.now();
      out.push(['minted-with-harvested-key', c.signHS256({ sub: OWNER[t], tenant: t, scope: 'owner', auth_time: n, iat: n, exp: n + 900 }, this.creds.signingKeys[t])]);
    }
    for (const a of this.assertionsFor(t)) {
      const r = await this.req('ta_public', 'POST', `/t/${t}/token`, { assertion: a });
      if (r.status === 200) out.push(['token-exchange', r.body.token]);
    }
    return out;
  }

  // Each strategy: [name, async () => response]. Success is judged by the
  // caller against ground truth, not by the response alone.
  async strategies (t, action) {
    const S = [];
    const st = this.creds.serviceTokens;
    const svc = (k) => (st[k] ? { authorization: 'Service ' + st[k] } : {});
    if (action === 'operator') {
      const row = { default: 'mg/dl', mode: 'pinned', pin: 'mmol', constraint: {} };
      S.push(['ns-admin direct', () => this.req('ns_admin', 'PUT', `/tenants/${t}/policy/DISPLAY_UNITS`, row)]);
      for (const k of ['operator', 'dashboard', null]) {
        if (k && !st[k]) continue;
        S.push([`orchestrator operator route (${k || 'no'} token)`, () => this.req('orchestrator', 'POST', '/operator/policy', { tenant: t, key: 'DISPLAY_UNITS', row }, svc(k))]);
      }
      return S;
    }
    const body = { read: undefined, write: { value: 'mmol' }, reveal: { kind: 'plugin:connect' } }[action];
    for (const [via, tok] of await this.tokensFor(t)) {
      const h = { authorization: 'Bearer ' + tok };
      if (action === 'read') S.push([via, () => this.req('ta_public', 'GET', `/t/${t}/config`, undefined, h)]);
      if (action === 'write') S.push([via, () => this.req('ta_public', 'PUT', `/t/${t}/config/DISPLAY_UNITS`, body, h)]);
      if (action === 'reveal') S.push([via, () => this.req('sec_public', 'POST', `/t/${t}/reveal`, body, h)]);
    }
    for (const a of this.assertionsFor(t)) {
      S.push(['dashboard API with an assertion', async () => {
        const s = await this.req('dashboard', 'POST', '/session/assertion', { assertion: a });
        if (s.status !== 200) return s;
        const p = { read: '/read', write: '/edit', reveal: '/reveal' }[action];
        return this.req('dashboard', 'POST', p, Object.assign({ session: s.body.session, tenant: t, key: 'DISPLAY_UNITS' }, body));
      }]);
      for (const k of ['dashboard', null]) {
        if (k && !st[k]) continue;
        const p = { read: '/owner/read', write: '/owner/edit', reveal: '/owner/reveal' }[action];
        S.push([`orchestrator owner route (${k || 'no'} token)`, () => this.req('orchestrator', 'POST', p,
          Object.assign({ assertion: a, tenant: t, key: 'DISPLAY_UNITS' }, body), svc(k))]);
      }
    }
    for (const k of ['orchestrator', null]) {
      if (k && !st[k]) continue;
      const via = `internal API (${k || 'no'} token)`;
      if (action === 'read') S.push([via, () => this.req('ta_internal', 'GET', `/internal/t/${t}/config`, undefined, svc(k))]);
      if (action === 'write') S.push([via, () => this.req('ta_internal', 'PUT', `/internal/t/${t}/config/DISPLAY_UNITS`, { value: 'mmol', on_behalf_of: OWNER[t] }, svc(k))]);
      if (action === 'reveal') S.push([via, () => this.req('sec_internal', 'POST', `/internal/t/${t}/reveal`, { kind: 'plugin:connect', on_behalf_of: OWNER[t] }, svc(k))]);
    }
    if (action === 'read') S.push(['ns-admin export', () => this.req('ns_admin', 'GET', `/tenants/${t}/export`)]);
    if (action === 'reveal') S.push(['secrets operator port', () => this.req('sec_operator', 'POST', `/t/${t}/reveal`, body)]);
    return S;
  }

  async attempt (t, action) {
    const run = this.run;
    const truth = {
      read: (r) => r.status === 200 && r.body && r.body.effective && 'DISPLAY_UNITS' in r.body.effective,
      write: () => db(run).owner[t].DISPLAY_UNITS === 'mmol',
      operator: () => { const row = db(run).policy[t].DISPLAY_UNITS; return row.mode === 'pinned' && row.pin === 'mmol'; },
      reveal: (r) => r.status === 200 && r.body && r.body.value === run.conn[t]
    }[action];
    const tried = [];
    for (const [via, fn] of await this.strategies(t, action)) {
      if (action === 'write' || action === 'operator') resetDisplay(run, t);
      const r = await fn();
      const ok = truth(r);
      if (action === 'write' || action === 'operator') resetDisplay(run, t);
      if (ok) return { ok: true, via };
      tried.push(`${via}: ${r.body && (r.body.reason || r.body.error) ? (r.body.reason || r.body.error) : r.status}`);
    }
    return { ok: false, tried };
  }
}

async function heldByDashboard (run) {
  const r = await as(run, 'harness', 'dashboard', 'GET', '/__lab/held');
  return { ownerTokens: r.body.ownerTokens, assertions: r.body.assertions, serviceTokens: r.body.serviceTokens };
}

// ---------------------------------------------------------------- measures
const checks = {}; // per run: key -> comparable value
const put = (k, v) => { checks[k] = v; };

async function m1BlastRadius (run) {
  const d = run.design;
  const out = {};
  const comps = {};
  comps.dashboard = new Attacker(run, ['dashboard'], await heldByDashboard(run));
  if (isB(d) || d === 'C') {
    comps.orchestrator = new Attacker(run, ['orchestrator'], { serviceTokens: d === 'B1' ? { orchestrator: svcKey(run, 'svc-orchestrator') } : {} });
  }
  // One tenant's owner credential: A and C hand out a per-tenant owner token;
  // B hands out nothing tenant-scoped, so the owner's assertion stands in.
  if (isB(d)) {
    comps['owner-1 credential'] = new Attacker(run, [], { assertions: [await idpAssertion(run, 'owner-1')] });
  } else {
    const a = await idpAssertion(run, 'owner-1');
    const r = await as(run, 'internet', 'ta_public', 'POST', '/t/t1/token', { assertion: a });
    comps['owner-1 credential'] = new Attacker(run, [], { ownerTokens: [r.body.token] });
  }
  // The secrets service's API caller: the non-human credential the secrets
  // service accepts for other people's secrets.
  comps['secrets API caller'] = isB(d)
    ? new Attacker(run, ['orchestrator'], { serviceTokens: d === 'B1' ? { orchestrator: svcKey(run, 'svc-orchestrator') } : {} })
    : new Attacker(run, ['tenant-admin'], { serviceTokens: { tenantAdmin: svcKey(run, 'svc-tenant-admin') } });
  comps['operator plane'] = new Attacker(run, ['ns-admin', 'operator'], { serviceTokens: d === 'B1' ? { operator: svcKey(run, 'svc-operator') } : {} });
  comps['identity provider'] = new Attacker(run, [], { idpKey: fs.readFileSync(path.join(run.runDir, 'keys', 'idp.key')) });

  for (const [name, att] of Object.entries(comps)) {
    await att.prepare();
    out[name] = {};
    for (const action of ['read', 'write', 'operator', 'reveal']) {
      const hit = []; const via = {}; const refused = {};
      for (const t of TENANTS) {
        const r = await att.attempt(t, action);
        if (r.ok) { hit.push(t); via[t] = r.via; } else refused[t] = r.tried;
      }
      out[name][action] = { tenants: hit, via, refused };
      put(`m1.${name}.${action}`, hit.join(',') || 'none');
    }
  }
  return out;
}

function lastAudit (run, pred) {
  const a = store.readAudit(run.runDir).filter(pred);
  return a[a.length - 1] || null;
}

function classify (entry, truth) {
  if (!entry) return 'no entry';
  const a = entry.actor || {};
  if (a.kind === 'human' && a.verifiedBy) return a.id === truth ? 'names the human, verified' : `names ${a.id}, verified`;
  if (a.kind === 'human') return a.id === truth ? 'names the human, unverified' : 'names a human the caller chose';
  if (a.kind === 'service') return a.onBehalfOf ? (a.onBehalfOf === truth ? 'names a service + the human it asserts' : 'names a service + a human the caller chose') : 'names a service only';
  if (a.kind === 'none') return a.onBehalfOf ? (a.onBehalfOf === truth ? 'names no identity; a human only as asserted' : 'names no identity + a human the caller chose') : 'names nothing';
  if (a.kind === 'operator-plane') return 'names the operator plane, no identity';
  return 'unknown';
}

async function m2Audit (run) {
  const d = run.design;
  const out = {};
  // Owner edit through the dashboard.
  await as(run, 'internet', 'dashboard', 'POST', '/edit', { session: run.sessions.t1, tenant: 't1', key: 'DISPLAY_UNITS', value: 'mmol' });
  const e1 = lastAudit(run, (e) => e.action === 'owner-write' && e.tenant === 't1');
  out.ownerEdit = { actor: e1 && e1.actor, verdict: classify(e1, 'owner-1') };
  // Attacker edit. A, C: a stolen t1 owner token, with a spoofed name in the body.
  // B: the compromised orchestrator writing t2 and naming t2's owner.
  let e2;
  if (isB(d)) {
    const h = d === 'B1' ? { authorization: 'Service ' + svcKey(run, 'svc-orchestrator') } : {};
    await as(run, 'orchestrator', 'ta_internal', 'PUT', '/internal/t/t2/config/DISPLAY_UNITS', { value: 'mmol', on_behalf_of: 'owner-2' }, h);
    e2 = lastAudit(run, (e) => e.action === 'owner-write' && e.tenant === 't2');
    out.attackerEdit = { scenario: 'compromised orchestrator writes t2 naming owner-2', actor: e2 && e2.actor, verdict: classify(e2, 'attacker') };
  } else {
    const a = await idpAssertion(run, 'owner-1');
    const tok = (await as(run, 'internet', 'ta_public', 'POST', '/t/t1/token', { assertion: a })).body.token;
    await as(run, 'internet', 'ta_public', 'PUT', '/t/t1/config/DISPLAY_UNITS', { value: 'mg/dl', on_behalf_of: 'owner-9' }, { authorization: 'Bearer ' + tok });
    e2 = lastAudit(run, (e) => e.action === 'owner-write' && e.tenant === 't1');
    out.attackerEdit = { scenario: 'stolen t1 owner token, body claims owner-9', actor: e2 && e2.actor, verdict: classify(e2, 'owner-1') };
  }
  // Operator-plane edit (every design).
  await as(run, 'operator', 'ns_admin', 'PUT', '/tenants/t3/policy/DISPLAY_UNITS', { default: 'mg/dl', mode: 'pinned', pin: 'mmol', constraint: {} });
  const e3 = lastAudit(run, (e) => e.action === 'policy-write' && e.tenant === 't3');
  out.operatorEdit = { actor: e3 && e3.actor, verdict: classify(e3, 'operator') };
  put('m2.owner', out.ownerEdit.verdict);
  put('m2.attacker', out.attackerEdit.verdict);
  put('m2.operator', out.operatorEdit.verdict);
  return out;
}

const outcome = (r) => r.status === 200 ? 'accepted'
  : r.status === 0 ? 'unreachable (matrix)'
    : `refused ${r.status} ${(r.body && (r.body.reason || r.body.error)) || ''}`.trim();

async function m3Policy (run) {
  const d = run.design;
  const out = {};
  const s1 = run.sessions.t1;
  const dash = (key, value, confirm) => as(run, 'internet', 'dashboard', 'POST', '/edit', { session: s1, tenant: 't1', key, value, confirm });
  // A crafted owner request that skips the dashboard's checks.
  let crafted;
  if (isB(d)) {
    const a = await idpAssertion(run, 'owner-1');
    const h = d === 'B1' ? { authorization: 'Service ' + svcKey(run, 'svc-dashboard') } : {};
    crafted = (key, value) => as(run, 'dashboard', 'orchestrator', 'POST', '/owner/edit', { assertion: a, tenant: 't1', key, value }, h);
  } else {
    const a = await idpAssertion(run, 'owner-1');
    const tok = (await as(run, 'internet', 'ta_public', 'POST', '/t/t1/token', { assertion: a })).body.token;
    crafted = (key, value) => as(run, 'internet', 'ta_public', 'PUT', `/t/t1/config/${key}`, { value }, { authorization: 'Bearer ' + tok });
  }
  const tries = [
    ['pinned key via dashboard (TRUST_PROXY=2)', () => dash('TRUST_PROXY', '2')],
    ['pinned key, crafted request skipping the dashboard (TRUST_PROXY=2)', () => crafted('TRUST_PROXY', '2')],
    ['floor: WRITE_VALIDATION=off, crafted', () => crafted('WRITE_VALIDATION', 'off')],
    ['floor: AUTH_DEFAULT_ROLES="readable careportal", crafted', () => crafted('AUTH_DEFAULT_ROLES', 'readable careportal')],
    ['floor: CONNECT_SOURCE_ENDPOINT to a link-local host, crafted', () => crafted('CONNECT_SOURCE_ENDPOINT', 'https://169.254.169.254/latest')],
    ['bounded: AUTH_DEFAULT_ROLES=status-only (floor-safe, outside the operator list), crafted', () => crafted('AUTH_DEFAULT_ROLES', 'status-only')],
    ['bounded: API3_AUTOPRUNE_ENTRIES=7 (below operator minimum 30)', () => dash('API3_AUTOPRUNE_ENTRIES', 7)],
    ['confirmation: API3_AUTOPRUNE_ENTRIES=90 without confirmation', () => dash('API3_AUTOPRUNE_ENTRIES', 90)],
    ['confirmation: API3_AUTOPRUNE_ENTRIES=90 with the phrase, after the export offer', () => dash('API3_AUTOPRUNE_ENTRIES', 90, 'DELETE ENTRIES OLDER THAN 90 DAYS')],
    ['open: DISPLAY_UNITS=mmol', () => dash('DISPLAY_UNITS', 'mmol')],
    ['tighten: WRITE_VALIDATION=reject', () => dash('WRITE_VALIDATION', 'reject')]
  ];
  // Operator-route attempts from the dashboard's network position.
  const pinRow = { default: '1', mode: 'pinned', pin: '3', constraint: {} };
  if (isB(d)) {
    const h = d === 'B1' ? { authorization: 'Service ' + svcKey(run, 'svc-dashboard') } : {};
    tries.push(['pinned key re-pinned from the dashboard via the orchestrator (TRUST_PROXY pin 3)', () => as(run, 'dashboard', 'orchestrator', 'POST', '/operator/policy', { tenant: 't1', key: 'TRUST_PROXY', row: pinRow }, h)]);
  } else {
    tries.push(['pinned key re-pinned from the dashboard (TRUST_PROXY pin 3)', async () => {
      const r = await as(run, 'dashboard', 'ns_admin', 'PUT', '/tenants/t1/policy/TRUST_PROXY', pinRow);
      if (r.status !== 0 || d !== 'C') return r;
      return as(run, 'dashboard', 'orchestrator', 'POST', '/operator/policy', { tenant: 't1', key: 'TRUST_PROXY', row: pinRow });
    }]);
  }
  // Floors against the operator plane itself.
  const opPin = (key, value) => as(run, 'operator', 'ns_admin', 'PUT', `/tenants/t2/policy/${key}`, { default: value, mode: 'pinned', pin: value, constraint: {} });
  tries.push(
    ['operator plane pins AUTH_DEFAULT_ROLES="readable careportal"', () => opPin('AUTH_DEFAULT_ROLES', 'readable careportal')],
    ['operator plane pins CONNECT_SOURCE_ENDPOINT to a link-local host', () => opPin('CONNECT_SOURCE_ENDPOINT', 'https://169.254.169.254/latest')],
    ['operator plane pins WRITE_VALIDATION=off', () => opPin('WRITE_VALIDATION', 'off')]
  );
  for (const [i, [name, fn]] of tries.entries()) {
    const r = await fn();
    out[name] = outcome(r);
    put(`m3.${String(i).padStart(2, '0')} ${name}`, out[name]);
  }
  return out;
}

async function m4CrossTenant (run) {
  const d = run.design;
  const out = {};
  if (isB(d)) {
    const r = await as(run, 'internet', 'dashboard', 'POST', '/edit', { session: run.sessions.t1, tenant: 't2', key: 'DISPLAY_UNITS', value: 'mmol' });
    out['owner-1 session edits t2 (via orchestrator)'] = outcome(r);
    put('m4.owner-1 edits t2', outcome(r));
    out.note = 'B has no tenant-scoped token: the refusal is the orchestrator\'s ownership (claim) check.';
    return out;
  }
  const a = await idpAssertion(run, 'owner-1');
  const tok = (await as(run, 'internet', 'ta_public', 'POST', '/t/t1/token', { assertion: a })).body.token;
  // t1's signing key: what signs t1's tokens in this run.
  const k1 = run.breaks.includes('install-wide-key')
    ? fs.readFileSync(path.join(run.runDir, 'keys', 'installwide.key'))
    : Buffer.from((await as(run, 'tenant-admin', 'sec_internal', 'POST', '/t/t1/consume', { kind: 'jwt' }, { authorization: 'Service ' + svcKey(run, 'svc-tenant-admin') })).body.key, 'base64url');
  const n = c.now();
  const rows = {
    'x1 t1 token replayed at t2': tok,
    'x2 forged claim (tenant t2, sub owner-2), t1 signature kept': c.forgeClaim(tok, { tenant: 't2', sub: 'owner-2' }),
    'x3 t2 token signed with t1\'s key': c.signHS256({ sub: 'owner-2', tenant: 't2', scope: 'owner', auth_time: n, iat: n, exp: n + 900 }, k1)
  };
  for (const [name, t] of Object.entries(rows)) {
    resetDisplay(run, 't2');
    const r = await as(run, 'internet', 'ta_public', 'PUT', '/t/t2/config/DISPLAY_UNITS', { value: 'mmol' }, { authorization: 'Bearer ' + t });
    const o = outcome(r);
    out[name] = o;
    put(`m4.${name}`, o);
    put(`m4.${name} is a signature failure`, o === 'refused 401 signature');
    resetDisplay(run, 't2');
  }
  return out;
}

async function m5Effort (run) {
  const out = { edits: [] };
  const { session } = await login(run, 'owner-1');
  for (let i = 0; i < 3; i++) {
    const r = await as(run, 'internet', 'dashboard', 'POST', '/edit', { session, tenant: 't1', key: 'DISPLAY_UNITS', value: i % 2 ? 'mg/dl' : 'mmol' });
    out.edits.push({ status: r.status, dashboardCalls: r.body._lab.direct, totalCalls: r.body._lab.total, credentialsHandled: r.body.credentialsHandled });
  }
  const rv = await as(run, 'internet', 'dashboard', 'POST', '/reveal', { session, tenant: 't1', kind: 'plugin:connect' });
  out.reveal = { ok: rv.body.value === run.conn.t1, dashboardCalls: rv.body._lab.direct, totalCalls: rv.body._lab.total, ownerVisible: rv.status === 200 ? 'none' : rv.body.error };
  put('m5.first edit dashboard calls', out.edits[0].dashboardCalls);
  put('m5.later edit dashboard calls', out.edits[2].dashboardCalls);
  put('m5.later edit total calls', out.edits[2].totalCalls);
  put('m5.reveal owner-visible', out.reveal.ownerVisible);
  return out;
}

async function m5Fresh (run) {
  const { session } = await login(run, 'owner-1');
  await sleep((run.opt.freshSeconds + 1) * 1000);
  const r1 = await as(run, 'internet', 'dashboard', 'POST', '/reveal', { session, tenant: 't1', kind: 'plugin:connect' });
  const steps = [];
  let calls = r1.body._lab.direct;
  if (r1.status === 401 && r1.body.error === 'reauth-required') {
    steps.push('owner re-enters password');
    const ra = await as(run, 'internet', 'dashboard', 'POST', '/session/reauth', { session, password: run.users['owner-1'].password });
    calls += ra.body._lab.direct;
  }
  const r2 = await as(run, 'internet', 'dashboard', 'POST', '/reveal', { session, tenant: 't1', kind: 'plugin:connect' });
  calls += r2.body._lab.direct;
  const o = { firstAttempt: outcome(r1), ownerSteps: steps, revealed: r2.body.value === run.conn.t1, dashboardCallsTotal: calls };
  put('m5.fresh owner steps', steps.length);
  return o;
}

// ---------------------------------------------------------------- plan
// Controls: one protection removed per run, and the checks it must flip.
const CONTROLS = {
  A: [
    ['no-sig-verify', ['m1.dashboard.write', 'm1.owner-1 credential.write', 'm1.owner-1 credential.reveal', 'm4.x2 forged claim (tenant t2, sub owner-2), t1 signature kept']],
    ['install-wide-key', ['m4.x1 t1 token replayed at t2 is a signature failure', 'm4.x3 t2 token signed with t1\'s key']],
    ['actor-from-body', ['m2.attacker']],
    ['no-policy', ['m3.01 pinned key, crafted request skipping the dashboard (TRUST_PROXY=2)', 'm3.05 bounded: AUTH_DEFAULT_ROLES=status-only (floor-safe, outside the operator list), crafted']],
    ['no-floors', ['m3.02 floor: WRITE_VALIDATION=off, crafted', 'm3.12 operator plane pins AUTH_DEFAULT_ROLES="readable careportal"']],
    ['open-matrix', ['m1.dashboard.operator', 'm3.11 pinned key re-pinned from the dashboard (TRUST_PROXY pin 3)']],
    ['operator-reveal', ['m1.operator plane.reveal']],
    ['reveal-no-auth', ['m1.owner-1 credential.reveal']],
    ['no-token-cache', ['m5.later edit dashboard calls']],
    ['no-confirmation', ['m3.07 confirmation: API3_AUTOPRUNE_ENTRIES=90 without confirmation']]
  ],
  B0: [
    ['no-ownership-check', ['m1.dashboard.write', 'm1.owner-1 credential.write', 'm4.owner-1 edits t2']],
    ['no-policy', ['m3.01 pinned key, crafted request skipping the dashboard (TRUST_PROXY=2)']],
    ['no-floors', ['m3.02 floor: WRITE_VALIDATION=off, crafted', 'm3.12 operator plane pins AUTH_DEFAULT_ROLES="readable careportal"']],
    ['open-matrix', ['m1.dashboard.write', 'm1.dashboard.reveal']],
    ['operator-reveal', ['m1.operator plane.reveal']],
    ['no-confirmation', ['m3.07 confirmation: API3_AUTOPRUNE_ENTRIES=90 without confirmation']]
  ],
  B1: [
    ['b1-no-service-token', ['m1.dashboard.operator', 'm3.11 pinned key re-pinned from the dashboard via the orchestrator (TRUST_PROXY pin 3)']],
    ['no-ownership-check', ['m1.dashboard.write', 'm1.owner-1 credential.write', 'm4.owner-1 edits t2']],
    ['no-policy', ['m3.01 pinned key, crafted request skipping the dashboard (TRUST_PROXY=2)']],
    ['no-floors', ['m3.02 floor: WRITE_VALIDATION=off, crafted', 'm3.12 operator plane pins AUTH_DEFAULT_ROLES="readable careportal"']],
    ['open-matrix', ['m1.dashboard.operator']],
    ['operator-reveal', ['m1.operator plane.reveal']],
    ['no-confirmation', ['m3.07 confirmation: API3_AUTOPRUNE_ENTRIES=90 without confirmation']]
  ]
};
CONTROLS.C = CONTROLS.A; // C's owner path is A's; the same protections are removed

async function measured (design, breaks, opt, fn) {
  const run = await startRun(design, breaks, opt || {});
  try {
    await setup(run);
    await assertAlive(run);
    for (const k of Object.keys(checks)) delete checks[k];
    const result = await fn(run);
    await assertAlive(run);
    return { result, checks: Object.assign({}, checks), runDir: path.basename(run.runDir) };
  } finally {
    await stopRun(run);
  }
}

async function full (run) {
  return {
    m4: await m4CrossTenant(run),
    m3: await m3Policy(run),
    m2: await m2Audit(run),
    m1: await m1BlastRadius(run),
    m5: await m5Effort(run)
  };
}

(async () => {
  fs.mkdirSync(SCRATCH, { recursive: true });
  const results = {
    lab: 'tenant-config-callpath',
    generated: new Date().toISOString(),
    node: process.version,
    ports: PORTS,
    codeDefaultFloorViolations: P.effectiveFloorViolations(P.effective({}, {})),
    designs: {}
  };
  // CONTROL for the liveness assertion: kill one role by its recorded PID and
  // require assertAlive to fail. A check that never fails is not evidence.
  {
    console.log('== liveness control');
    const run = await startRun('A', [], {});
    process.kill(run.pids.secrets, 'SIGKILL');
    await sleep(200);
    let reported = false; let reason = null;
    try { await assertAlive(run); } catch (e) { reported = true; reason = e.code || e.message; }
    await stopRun(run);
    results.livenessControl = { killed: 'secrets', assertAliveFailed: reported, reason };
    console.log(`   reported=${reported} (${reason})`);
    if (!reported) throw new Error('liveness check is vacuous');
  }
  for (const d of ONLY) {
    console.log(`== ${d} baseline`);
    const base = await measured(d, [], {}, full);
    console.log(`== ${d} fresh re-authentication variant`);
    const fresh = await measured(d, [], { revealPolicy: 'fresh', freshSeconds: 2 }, m5Fresh);
    const controls = [];
    for (const [brk, expect] of CONTROLS[d]) {
      console.log(`== ${d} control ${brk}`);
      const r = await measured(d, [brk], {}, full);
      const changed = {};
      for (const k of new Set(Object.keys(base.checks).concat(Object.keys(r.checks)))) {
        if (JSON.stringify(base.checks[k]) !== JSON.stringify(r.checks[k])) changed[k] = { baseline: base.checks[k], control: r.checks[k] };
      }
      const missingKeys = expect.filter((k) => !(k in base.checks));
      const flipped = expect.filter((k) => k in changed);
      controls.push({ break: brk, expectedToFlip: expect, flipped, missingKeys, reported: flipped.length === expect.length && !missingKeys.length, changed });
      console.log(`   reported=${flipped.length === expect.length && !missingKeys.length} flipped=${flipped.length}/${expect.length}${missingKeys.length ? ' MISSING ' + missingKeys.join(' | ') : ''}`);
    }
    results.designs[d] = { baseline: base.result, checks: base.checks, freshVariant: fresh.result, controls };
  }
  fs.writeFileSync(OUT, JSON.stringify(results, null, 2) + '\n');
  console.log('wrote ' + OUT);
})().catch((e) => { console.error(e); process.exit(1); });
