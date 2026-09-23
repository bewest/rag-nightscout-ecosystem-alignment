#!/usr/bin/env node
'use strict';
/*
 * subject-edit-keeps-fields-browser.js — register BF-47, branch
 * bf2/subject-edit-keeps-fields.
 *
 * An access entry (a "subject") or a role that is edited on the admin page is
 * saved back with PUT /api/v2/authorization/{subjects,roles}. The server
 * replaces the stored document with what the request carried. Whatever the
 * admin page did not fetch, it did not send, and the replace discarded it.
 *
 * This probe measures what survives, per path, by reading MongoDB directly
 * (never through the API under test):
 *
 *   admin  — a real browser opens /admin, edits the entry's roles (or a
 *            role's permissions) in the stock dialog and presses Save
 *   put    — CONTROL: a direct JSON PUT that carries notes and created_at
 *   omit   — a direct JSON PUT that changes roles and carries neither notes
 *            nor created_at (what a non-browser tool that only knows the
 *            fields it is changing sends)
 *   clear  — a direct JSON PUT that sends notes: '' — the operator clearing
 *            the notes on purpose; must still clear
 *
 * Every document is seeded through the API with notes and a fixed, old
 * created_at, so a created_at of "now" is distinguishable from the seeded one.
 *
 * MEASURED 2026-09-23, NODE_ENV=development, Node 20.20.0, mongo:7:
 *
 *   arm            origin/dev 74fc6619     bf2/auth-hardening 29e6430e   bf2/subject-edit-keeps-fields 7103f657
 *   -------------  ----------------------  ----------------------------  --------------------------------------
 *   subject/admin  notes -> ""             notes kept                    notes kept
 *                  created_at -> now       created_at -> now             created_at kept
 *                  accessToken on disk     (no token on disk)            (no token on disk)
 *   subject/put    both kept (control)     both kept (control)           both kept (control)
 *   subject/omit   notes gone, c_at now    notes gone, c_at now          both kept
 *   subject/clear  notes "", c_at now      notes "", c_at now            notes "", created_at kept
 *   role/admin     both kept               both kept                     both kept
 *   role/put       both kept (control)     both kept (control)           both kept (control)
 *   role/omit      notes gone, c_at now    notes gone, c_at now          both kept
 *   role/clear     notes "", c_at now      notes "", c_at now            notes "", created_at kept
 *
 * The role editor keeps both on every build because GET /roles serves whole
 * documents and the dialog sends them back; only the subject editor, whose
 * GET is pick()ed, loses created_at. created_at is never ABSENT after an edit:
 * save() overwrites a missing one with the time of the edit.
 *
 * Usage:
 *   node subject-edit-keeps-fields-browser.js --url http://127.0.0.1:PORT \
 *        --secret <API_SECRET> --mongo mongodb://127.0.0.1:27093/<db> \
 *        --ns <worktree whose node_modules has the mongodb driver> \
 *        [--expect base|fixed]
 *
 * --expect fixed  exits non-zero unless admin/omit keep both fields and
 *                 clear clears notes (the branch's claim).
 * --expect base   exits non-zero unless the admin arm LOSES created_at, i.e.
 *                 the base reproduces the defect (non-vacuity of the arm).
 * The put arm is an invariant: it must keep both on every build, or the
 * measurement is not attributable to the defect.
 *
 * Playwright: NSREVIEW_PLAYWRIGHT=<path to playwright-core>, system Chrome.
 * The server must run with NODE_ENV=development so the page is the
 * worktree's own bundle.
 */

const path = require('path');
const crypto = require('crypto');

const args = process.argv.slice(2);
const opt = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const URL_ = opt('--url'), SECRET = opt('--secret'), MONGO = opt('--mongo');
const NS = opt('--ns'), EXPECT = opt('--expect');
if (!URL_ || !SECRET || !MONGO || !NS) {
  console.error('need --url --secret --mongo --ns'); process.exit(2);
}
const PW = process.env.NSREVIEW_PLAYWRIGHT || 'playwright-core';
const { MongoClient, ObjectId } = require(require.resolve('mongodb', { paths: [NS] }));

const SEEDED_AT = '2020-01-02T03:04:05.000Z';
const NOTE = 'seeded note, must survive';
const tag = crypto.randomBytes(3).toString('hex');
const H = { 'api-secret': crypto.createHash('sha1').update(SECRET).digest('hex'),
            'content-type': 'application/json' };

async function api (method, p, body) {
  const r = await fetch(URL_ + '/api/v2/authorization/' + p,
    { method, headers: H, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  if (!r.ok) throw new Error(method + ' ' + p + ' -> ' + r.status + ' ' + t.slice(0, 120));
  return t ? JSON.parse(t) : null;
}

async function seedSubject (name) {
  await api('POST', 'subjects', { name, roles: ['readable'], notes: NOTE, created_at: SEEDED_AT });
  return (await api('GET', 'subjects')).find(s => s.name === name);
}
async function seedRole (name) {
  await api('POST', 'roles', { name, permissions: ['api:entries:read'], notes: NOTE, created_at: SEEDED_AT });
  return (await api('GET', 'roles')).find(r => r.name === name);
}

async function adminEdit (token, kind, name) {
  const { chromium } = require(PW);
  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  try {
    const page = await (await browser.newContext()).newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e.message)));
    page.on('dialog', d => { errors.push('dialog: ' + d.message()); d.dismiss().catch(() => {}); });
    await page.goto(URL_ + '/admin?token=' + encodeURIComponent(token),
      { waitUntil: 'domcontentloaded', timeout: 120000 });
    const table = kind === 'subject' ? '#admin_subjects_table' : '#admin_roles_table';
    const icon = kind === 'subject' ? 'Edit this subject' : 'Edit this role';
    const row = page.locator(table + ' tr', { hasText: name });
    await row.first().waitFor({ timeout: 120000 });
    let putBody = null;
    page.on('request', rq => {
      if (rq.method() === 'PUT' && rq.url().includes('/authorization/')) putBody = rq.postData();
    });
    await row.first().locator('img[title="' + icon + '"]').click();
    if (kind === 'subject') {
      await page.locator('#edsub_roles').waitFor({ state: 'visible' });
      await page.fill('#edsub_roles', 'readable, careportal');
    } else {
      await page.locator('#edrole_permissions').waitFor({ state: 'visible' });
      await page.fill('#edrole_permissions', 'api:entries:read api:treatments:read');
    }
    const saved = page.waitForResponse(r => r.request().method() === 'PUT'
      && r.url().includes('/authorization/'), { timeout: 30000 });
    await page.locator('.ui-dialog:visible button', { hasText: 'Save' }).click();
    const resp = await saved;
    // the page reloads the list after a save; wait for the new value to show
    await page.locator(table + ' tr', { hasText: name })
      .filter({ hasText: kind === 'subject' ? 'careportal' : 'api:treatments:read' })
      .first().waitFor({ timeout: 30000 });
    return { status: resp.status(), putBody, errors };
  } finally {
    await browser.close();
  }
}

function survives (doc) {
  return {
    notes: doc && Object.prototype.hasOwnProperty.call(doc, 'notes')
      ? JSON.stringify(doc.notes) : '(absent)',
    created_at: doc && doc.created_at
      ? (doc.created_at === SEEDED_AT ? 'kept' : 'CHANGED to ' + doc.created_at) : '(absent)',
    edited: doc ? JSON.stringify(doc.roles || doc.permissions) : '(no doc)',
    tokenOnDisk: doc ? ['accessToken', 'accessTokenDigest', 'digest'].filter(f => f in doc).join(',') || '-' : '-',
  };
}

(async () => {
  const mongo = await MongoClient.connect(MONGO);
  const db = mongo.db();
  const out = {};
  try {
    await api('POST', 'subjects', { name: 'bf47admin' + tag, roles: ['admin'] });
    const admin = (await api('GET', 'subjects')).find(s => s.name === 'bf47admin' + tag);

    // subjects
    const sAdmin = await seedSubject('bf47-admin-' + tag);
    const sPut = await seedSubject('bf47-put-' + tag);
    const sOmit = await seedSubject('bf47-omit-' + tag);
    const sClear = await seedSubject('bf47-clear-' + tag);
    const browser = await adminEdit(admin.accessToken, 'subject', sAdmin.name);
    out.subjectAdminPut = browser;
    await api('PUT', 'subjects', { _id: sPut._id, name: sPut.name, roles: ['readable', 'careportal'],
      notes: NOTE, created_at: SEEDED_AT });
    await api('PUT', 'subjects', { _id: sOmit._id, name: sOmit.name, roles: ['readable', 'careportal'] });
    await api('PUT', 'subjects', { _id: sClear._id, name: sClear.name, roles: ['readable', 'careportal'], notes: '' });
    const sc = db.collection('auth_subjects');
    for (const [arm, s] of [['admin', sAdmin], ['put', sPut], ['omit', sOmit], ['clear', sClear]]) {
      out['subject/' + arm] = survives(await sc.findOne({ _id: new ObjectId(s._id) }));
    }

    // roles
    const rAdmin = await seedRole('bf47-role-admin-' + tag);
    const rPut = await seedRole('bf47-role-put-' + tag);
    const rOmit = await seedRole('bf47-role-omit-' + tag);
    const rClear = await seedRole('bf47-role-clear-' + tag);
    out.roleAdminPut = await adminEdit(admin.accessToken, 'role', rAdmin.name);
    const perms = ['api:entries:read', 'api:treatments:read'];
    await api('PUT', 'roles', { _id: rPut._id, name: rPut.name, permissions: perms, notes: NOTE, created_at: SEEDED_AT });
    await api('PUT', 'roles', { _id: rOmit._id, name: rOmit.name, permissions: perms });
    await api('PUT', 'roles', { _id: rClear._id, name: rClear.name, permissions: perms, notes: '' });
    const rc = db.collection('auth_roles');
    for (const [arm, r] of [['admin', rAdmin], ['put', rPut], ['omit', rOmit], ['clear', rClear]]) {
      out['role/' + arm] = survives(await rc.findOne({ _id: new ObjectId(r._id) }));
    }
  } finally {
    await mongo.close();
  }

  const redact = s => s ? s.replace(/(accessToken=)[^&]*/g, '$1<redacted>') : s;
  console.log('subject admin-page PUT body:', redact(out.subjectAdminPut.putBody),
    out.subjectAdminPut.errors.length ? out.subjectAdminPut.errors : '');
  console.log('role    admin-page PUT body:', out.roleAdminPut.putBody,
    out.roleAdminPut.errors.length ? out.roleAdminPut.errors : '');
  const rows = Object.keys(out).filter(k => k.includes('/'));
  console.table(Object.fromEntries(rows.map(k => [k, out[k]])));

  const fails = [];
  const kept = r => r.notes === JSON.stringify(NOTE) && r.created_at === 'kept';
  for (const k of ['subject/put', 'role/put']) if (!kept(out[k])) fails.push(k + ' invariant broken');
  if (EXPECT === 'fixed') {
    for (const k of ['subject/admin', 'subject/omit', 'role/admin', 'role/omit']) if (!kept(out[k])) fails.push(k + ' lost a field');
    for (const k of ['subject/clear', 'role/clear']) {
      if (out[k].notes !== '""') fails.push(k + ' did not clear notes');
      if (out[k].created_at !== 'kept') fails.push(k + ' lost created_at');
    }
  } else if (EXPECT === 'base') {
    if (out['subject/admin'].created_at === 'kept') fails.push('subject/admin kept created_at on base: arm does not discriminate');
  }
  if (fails.length) { console.log('FAIL:\n  ' + fails.join('\n  ')); process.exit(1); }
  console.log(EXPECT ? 'PASS (' + EXPECT + ')' : 'measured');
})().catch(e => { console.error('probe failed:', e.stack || e.message); process.exit(2); });
