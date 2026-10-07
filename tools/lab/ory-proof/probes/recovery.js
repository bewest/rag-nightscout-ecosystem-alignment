#!/usr/bin/env node
'use strict';
/*
 * probes/recovery.js - do recovery emails name a tenant, and can they name the wrong one?
 *
 * VARIANT=default            Kratos's built-in recovery_code template (compose.yaml as is)
 * VARIANT=recovery-template  variants/recovery-template.yaml: a template that renders
 *                            .TransientPayload.tenant and .RequestURL
 * U is a member of tenant-a only. Recovery is started for U three ways: on the auth host, through
 * tenant-b's /.ory/ proxy path, and (template variant) with transient_payload naming tenant-b.
 * Each email is fetched from the mail catcher; the probe records which tenant hosts it names.
 * Positive control: the first email must arrive and carry a code, or nothing below means anything.
 */
const H = require('../lib/harness');

const VARIANT = process.env.VARIANT || 'default';
const rec = H.recorder(`recovery-${VARIANT}`);

async function startRecovery (viaHost, prefix, email, transient) {
  const f = await H.req(viaHost, 'GET', `${prefix}/self-service/recovery/api`);
  if (f.status !== 200) return { status: f.status, body: f.body };
  const a = new URL(f.body.ui.action);
  const body = { method: 'code', email };
  if (transient) body.transient_payload = transient;
  const r = await H.req(H.env.AUTH_HOST, 'POST', a.pathname + a.search, { body });
  return { status: r.status, requestUrl: f.body.request_url, actionHost: a.hostname, state: r.body && r.body.state };
}

async function waitMail (to, n) {
  for (let i = 0; i < 60; i++) {
    const r = await fetch(`${H.env.MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`).then((x) => x.json());
    if ((r.messages || []).length >= n) {
      const msgs = [];
      for (const m of r.messages.slice(0, n).reverse()) msgs.push(await fetch(`${H.env.MAILPIT}/api/v1/message/${m.ID}`).then((x) => x.json()));
      return msgs;
    }
    await H.sleep(250);
  }
  return null;
}

const tenantsNamed = (s) => [...new Set((String(s).match(/[a-z0-9-]+\.user-content\.apex\.test/g) || []).concat(String(s).match(/tenant-[a-z]+/g) || []))];
const hostsNamed = (s) => [...new Set(String(s).match(/[a-z0-9.-]+\.apex\.test(:\d+)?/g) || [])];

async function main () {
  const U = await H.createIdentity('u');
  const pool = H.db();
  await H.ensureSchema(pool);
  const ta = await H.tenant(pool, 'tenant-a');
  await H.tenant(pool, 'tenant-b');
  await H.addMember(pool, ta, U.id);
  const srv = await H.startServer('', `recovery-${VARIANT}`);
  try {
    const s1 = await startRecovery(H.env.AUTH_HOST, '', U.email, VARIANT === 'recovery-template' ? { tenant: 'tenant-a' } : null);
    const s2 = await startRecovery(H.env.tenantHost('tenant-b'), '/.ory', U.email, null);
    const starts = [s1, s2];
    let s3 = null;
    if (VARIANT === 'recovery-template') { s3 = await startRecovery(H.env.AUTH_HOST, '', U.email, { tenant: 'tenant-b' }); starts.push(s3); }
    rec.note('starts', starts.map((s) => ({ status: s.status, requestUrlHost: s.requestUrl && new URL(s.requestUrl).host, actionHost: s.actionHost, state: s.state })));
    const mails = await waitMail(U.email, starts.length);
    rec.check('mail.arrives', 'positive control: one recovery email per started flow arrives, each with a code', starts.length, mails ? mails.length : 0, !!mails && mails.every((m) => /\b\d{6}\b/.test(m.Text)));
    if (!mails) throw new Error('no mail');
    const summary = mails.map((m, i) => ({ start: ['auth-host', 'tenant-b /.ory proxy', 'auth-host + transient tenant-b'][i], subject: m.Subject, tenantsNamed: tenantsNamed(m.Subject + '\n' + m.Text), hostsNamed: hostsNamed(m.Text) }));
    rec.note('emails', summary);
    // Read prediction (wrong, first run 2026-10-07): request_url would name base_url. Measured: it follows the request.
    rec.check('flow.request_url', "the request_url Kratos records for a flow started through tenant-b's proxy path names tenant-b (it follows the request's host, not base_url)", 'tenant-b.user-content.apex.test', s2.requestUrl && new URL(s2.requestUrl).hostname, s2.requestUrl && new URL(s2.requestUrl).hostname === 'tenant-b.user-content.apex.test');
    const direct = await fetch(`${H.env.KRATOS_PUBLIC}/self-service/recovery/api`, { headers: { 'x-forwarded-host': 'evil.test' } }).then((r) => r.json());
    rec.check('flow.request_url.unvalidated', 'direct to Kratos public with X-Forwarded-Host: evil.test, request_url names evil.test (no allow-list applies to it)', 'evil.test', new URL(direct.request_url).hostname, new URL(direct.request_url).hostname === 'evil.test');
    if (VARIANT === 'default') {
      rec.check('default.names-no-tenant', 'built-in template: the emails name no tenant at all, whichever host the flow started on', [[], []], summary.map((s) => s.tenantsNamed), summary.every((s) => s.tenantsNamed.length === 0));
    } else {
      rec.check('template.client-chosen', 'custom template rendering transient_payload: the tenant named is whatever the CALLER sent - tenant-b, where U is not a member',
        { first: ['tenant-a'], third: ['tenant-b'] }, { first: summary[0].tenantsNamed, third: summary[2].tenantsNamed },
        summary[0].tenantsNamed.includes('tenant-a') && summary[2].tenantsNamed.includes('tenant-b') && !summary[2].tenantsNamed.includes('tenant-a'));
      rec.check('template.request-url', "custom template rendering .RequestURL: the email for the flow started through tenant-b's proxy names tenant-b's host - chosen by whoever started the flow, for an identity that is not a member of tenant-b",
        ['tenant-b.user-content.apex.test:44480'], summary[1].hostsNamed, summary[1].hostsNamed.some((h) => h.startsWith('tenant-b.')));
    }
  } finally { await srv.stop(); await pool.end(); }
  process.exit(rec.save() ? 1 : 0);
}

main().catch((e) => { console.error(e); rec.note('error', String(e && e.stack || e)); rec.save(); process.exit(2); });
