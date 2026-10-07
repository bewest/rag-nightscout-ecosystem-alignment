'use strict';
// Shared probe harness: start/stop lab-server with a break mode, Host-routed requests, Kratos and
// Hydra admin helpers, tenant fixtures, and a check recorder that writes results/<run>/<probe>.json.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { Pool } = require('pg');
const env = require('./env');

const ROOT = path.join(__dirname, '..');

function req (host, method, p, opts = {}) {
  return new Promise((resolve, reject) => {
    const body = opts.body == null ? null : (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body));
    const headers = Object.assign({ host: `${host}:${env.LAB_PORT}` }, opts.headers || {});
    if (body && !headers['content-type']) headers['content-type'] = 'application/json';
    const r = http.request({ host: '127.0.0.1', port: env.LAB_PORT, method, path: p, headers }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        let parsed = null;
        try { parsed = JSON.parse(data); } catch (e) { /* not json */ }
        resolve({ status: res.statusCode, headers: res.headers, body: parsed, text: data });
      });
    });
    r.on('error', reject);
    if (body) r.write(body);
    r.end();
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function startServer (breaks = '', label = 'server') {
  const logDir = path.join(ROOT, 'results', 'raw');
  fs.mkdirSync(logDir, { recursive: true });
  const out = fs.openSync(path.join(logDir, `${label}.log`), 'a');
  // detached: true makes Node call setsid(), so the server leads its own process group
  const child = spawn(process.execPath, [path.join(ROOT, 'lab-server.js')], {
    env: Object.assign({}, process.env, { NSJWT_BREAK: breaks }), stdio: ['ignore', out, out], detached: true
  });
  child.unref();
  for (let i = 0; i < 100; i++) {
    try {
      const h = await req(env.CONTROL_HOST, 'GET', '/health');
      if (h.status === 200 && h.body.breaks.join(',') === breaks.split(',').filter(Boolean).join(',')) {
        return { pid: child.pid, health: h.body, stop: () => stopServer(child) };
      }
    } catch (e) { /* not up yet */ }
    await sleep(100);
  }
  stopServer(child);
  throw new Error(`lab-server did not come up with breaks=${breaks}`);
}

async function stopServer (child) {
  try { process.kill(-child.pid, 'SIGTERM'); } catch (e) { /* gone */ }
  for (let i = 0; i < 50; i++) {
    try { await req(env.CONTROL_HOST, 'GET', '/health'); } catch (e) { return; }
    await sleep(100);
  }
  throw new Error('lab-server did not stop');
}

async function kratosAdmin (method, p, body) {
  const r = await fetch(`${env.KRATOS_ADMIN}${p}`, { method, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, body: await r.json().catch(() => null) };
}
async function hydraAdmin (method, p, body) {
  const r = await fetch(`${env.HYDRA_ADMIN}${p}`, { method, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, body: await r.json().catch(() => null) };
}

// Synthetic identities only: <label>-<random>@example.test, random password.
async function createIdentity (label) {
  const email = `${label}-${crypto.randomBytes(4).toString('hex')}@example.test`;
  const password = crypto.randomBytes(18).toString('base64url');
  const r = await kratosAdmin('POST', '/admin/identities', {
    schema_id: 'default', traits: { email },
    credentials: { password: { config: { password } } },
    verifiable_addresses: [{ value: email, verified: true, via: 'email', status: 'completed' }]
  });
  if (r.status !== 201) throw new Error(`createIdentity ${r.status} ${JSON.stringify(r.body)}`);
  return { id: r.body.id, email, password };
}

// Kratos native (API) login: what a mobile app does. Returns {status, token, subject}.
async function nativeLogin (who) {
  const f = await fetch(`${env.KRATOS_PUBLIC}/self-service/login/api`).then((r) => r.json());
  // ui.action carries Kratos's public base_url (the auth host); scripts reach Kratos directly
  const action = env.KRATOS_PUBLIC + new URL(f.ui.action).pathname + new URL(f.ui.action).search;
  const r = await fetch(action, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ method: 'password', identifier: who.email, password: who.password }) });
  const b = await r.json();
  return { status: r.status, token: b.session_token, subject: b.session && b.session.identity.id };
}

function db () { return new Pool({ connectionString: env.pgUrl('nsjwt'), max: 2 }); }
async function ensureSchema (pool) { await pool.query(require('./nsjwt').SCHEMA); }
async function tenant (pool, slug, clientId = null) {
  const r = await pool.query(`INSERT INTO tenants (slug, oauth_client_id) VALUES ($1, $2)
    ON CONFLICT (slug) DO UPDATE SET oauth_client_id = EXCLUDED.oauth_client_id RETURNING id, slug`, [slug, clientId]);
  return r.rows[0];
}
async function addMember (pool, t, subject) { await pool.query('INSERT INTO tenant_members (tenant_id, subject_id) VALUES ($1,$2) ON CONFLICT DO NOTHING', [t.id, subject]); }
async function removeMember (pool, t, subject) { await pool.query('DELETE FROM tenant_members WHERE tenant_id=$1 AND subject_id=$2', [t.id, subject]); }

function recorder (probe) {
  const run = process.env.RUN || new Date().toISOString().slice(0, 10);
  const checks = [];
  const meta = { probe, run, started: new Date().toISOString(), node: process.version };
  function check (id, desc, expect, got, pass) {
    const row = { id, desc, expect, got, pass: !!pass };
    checks.push(row);
    console.log(`${pass ? 'PASS' : 'FAIL'}  ${id}  ${desc}\n      expect: ${JSON.stringify(expect)}\n      got:    ${JSON.stringify(got)}`);
    return pass;
  }
  function note (k, v) { meta[k] = v; }
  function save () {
    const dir = path.join(ROOT, 'results', run);
    fs.mkdirSync(dir, { recursive: true });
    const failed = checks.filter((c) => !c.pass).length;
    const out = Object.assign({}, meta, { finished: new Date().toISOString(), total: checks.length, failed, checks });
    fs.writeFileSync(path.join(dir, `${probe}.json`), JSON.stringify(out, null, 2) + '\n');
    console.log(`\n${probe}: ${checks.length - failed}/${checks.length} checks as expected -> results/${run}/${probe}.json`);
    return failed;
  }
  return { check, note, save };
}

module.exports = { req, sleep, startServer, kratosAdmin, hydraAdmin, createIdentity, nativeLogin, db, ensureSchema, tenant, addMember, removeMember, recorder, env, ROOT };
