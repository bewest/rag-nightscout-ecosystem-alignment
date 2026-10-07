#!/usr/bin/env node
'use strict';
/*
 * lab-server.js - the one browser-facing port (:44480), dispatched by Host:
 *   auth.apex.test             /ui/*  -> minimal self-service UI + Hydra login/consent app
 *                              else   -> Kratos public (reverse proxy)
 *   hydra.apex.test                   -> Hydra public (reverse proxy)
 *   <slug>.user-content.apex.test     -> nsjwt (lib/nsjwt.js); /.ory/* -> Kratos public (probe C)
 *   lab.control                       -> stats/event log for probes
 * Browsers reach it with Chromium --host-resolver-rules; scripts set the Host header.
 * NSJWT_BREAK is passed through to lib/nsjwt.js.
 */
const http = require('http');
const { Pool } = require('pg');
const env = require('./lib/env');
const nsjwt = require('./lib/nsjwt');

const AUTH = env.ORIGIN(env.AUTH_HOST);
const events = [];
const ev = (e) => { events.push(Object.assign({ t: Date.now() }, e)); if (events.length > 500) events.shift(); };

function proxy (req, res, target, stripPrefix) {
  const u = new URL(target);
  const path = stripPrefix ? req.url.slice(stripPrefix.length) || '/' : req.url;
  const headers = Object.assign({}, req.headers, { 'x-forwarded-host': req.headers.host, 'x-forwarded-proto': 'http' });
  const up = http.request({ host: u.hostname, port: u.port, method: req.method, path, headers }, (r) => {
    res.writeHead(r.statusCode, r.headers);
    r.pipe(res);
  });
  up.on('error', (e) => { res.writeHead(502); res.end(String(e)); });
  req.pipe(up);
}

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function renderFlow (kind, flow) {
  const nodes = (flow.ui && flow.ui.nodes) || [];
  const inputs = nodes.filter((n) => n.type === 'input').map((n) => {
    const a = n.attributes;
    if (a.type === 'submit') return `<button type="submit" name="${esc(a.name)}" value="${esc(a.value)}" data-group="${esc(n.group)}">${esc(a.name)}:${esc(a.value)}</button>`;
    return `<label>${esc(a.name)} <input name="${esc(a.name)}" type="${esc(a.type)}" value="${esc(a.value)}"></label>`;
  }).join('\n');
  const msgs = ((flow.ui && flow.ui.messages) || []).map((m) => `<li class="msg" data-id="${m.id}">${esc(m.text)}</li>`).join('');
  return `<!doctype html><title>${kind}</title><h1>${kind}</h1><ul>${msgs}</ul>
<form id="f" method="${esc(flow.ui.method)}" action="${esc(flow.ui.action)}">${inputs}</form>
<pre id="flow">${esc(JSON.stringify({ id: flow.id, return_to: flow.return_to, request_url: flow.request_url, action: flow.ui.action }))}</pre>`;
}

async function kratosGet (path, cookie) {
  const r = await fetch(`${env.KRATOS_PUBLIC}${path}`, { headers: cookie ? { cookie } : {} });
  return { status: r.status, body: await r.json().catch(() => null) };
}

async function hydraAdmin (method, path, body) {
  const r = await fetch(`${env.HYDRA_ADMIN}${path}`, { method, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, body: await r.json().catch(() => null) };
}

function html (res, status, body) { res.writeHead(status, { 'content-type': 'text/html; charset=utf-8' }); res.end(body); }
function json (res, status, body) { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); }
function redirect (res, to) { res.writeHead(303, { location: to }); res.end(); }

async function ui (req, res) {
  const url = new URL(req.url, AUTH);
  const p = url.pathname;
  const cookie = req.headers.cookie;
  const flowKind = /^\/ui\/(login|registration|recovery|verification|settings)$/.exec(p);
  if (flowKind) {
    const id = url.searchParams.get('flow');
    if (!id) return redirect(res, `${AUTH}/self-service/${flowKind[1]}/browser`);
    const f = await kratosGet(`/self-service/${flowKind[1]}/flows?id=${encodeURIComponent(id)}`, cookie);
    if (f.status !== 200) return html(res, f.status, `<pre id="err">${esc(JSON.stringify(f.body))}</pre>`);
    return html(res, 200, renderFlow(flowKind[1], f.body));
  }
  if (p === '/ui/error') {
    const f = await kratosGet(`/self-service/errors?id=${encodeURIComponent(url.searchParams.get('id') || '')}`);
    return html(res, 200, `<pre id="err">${esc(JSON.stringify(f.body))}</pre>`);
  }
  if (p === '/ui/home') {
    const s = await kratosGet('/sessions/whoami', cookie);
    return html(res, 200, `<pre id="whoami" data-status="${s.status}">${esc(JSON.stringify(s.status === 200 ? { id: s.body.identity.id } : s.body))}</pre>`);
  }
  if (p === '/ui/hydra/login') {
    const ch = url.searchParams.get('login_challenge');
    const lr = await hydraAdmin('GET', `/admin/oauth2/auth/requests/login?login_challenge=${encodeURIComponent(ch)}`);
    if (lr.status !== 200) return json(res, lr.status, lr.body);
    ev({ k: 'hydra-login', client_id: lr.body.client.client_id, skip: lr.body.skip, subject: lr.body.subject || null });
    let subject = lr.body.subject;
    if (!lr.body.skip) {
      const s = await kratosGet('/sessions/whoami', cookie);
      if (s.status !== 200) {
        return redirect(res, `${AUTH}/self-service/login/browser?return_to=${encodeURIComponent(`${AUTH}${req.url}`)}`);
      }
      subject = s.body.identity.id;
    }
    const acc = await hydraAdmin('PUT', `/admin/oauth2/auth/requests/login/accept?login_challenge=${encodeURIComponent(ch)}`, { subject, remember: true, remember_for: 3600 });
    return redirect(res, acc.body.redirect_to);
  }
  if (p === '/ui/hydra/consent') {
    const ch = url.searchParams.get('consent_challenge');
    const cr = await hydraAdmin('GET', `/admin/oauth2/auth/requests/consent?consent_challenge=${encodeURIComponent(ch)}`);
    if (cr.status !== 200) return json(res, cr.status, cr.body);
    ev({ k: 'hydra-consent', client_id: cr.body.client.client_id, skip: cr.body.skip, subject: cr.body.subject, requested_audience: cr.body.requested_access_token_audience });
    const acc = await hydraAdmin('PUT', `/admin/oauth2/auth/requests/consent/accept?consent_challenge=${encodeURIComponent(ch)}`, {
      grant_scope: cr.body.requested_scope, grant_access_token_audience: cr.body.requested_access_token_audience, remember: true, remember_for: 3600
    });
    return redirect(res, acc.body.redirect_to);
  }
  return html(res, 404, 'no ui route');
}

async function main () {
  const pool = new Pool({ connectionString: env.pgUrl('nsjwt'), max: 4 });
  const ns = nsjwt.create({ pool, env, breaks: process.env.NSJWT_BREAK });
  await ns.init();
  const rule = new RegExp(env.TENANT_HOST_RULE);

  const server = http.createServer((req, res) => {
    const host = String(req.headers.host || '').toLowerCase().replace(/:\d+$/, '');
    const go = async () => {
      if (host === env.CONTROL_HOST) {
        if (req.url === '/health') return json(res, 200, { ok: true, breaks: ns.breaks, pid: process.pid });
        if (req.url === '/events') return json(res, 200, { lab: events, nsjwt: ns.stats });
        if (req.url === '/reset') { events.length = 0; ns.stats.events.length = 0; return json(res, 200, { ok: true }); }
        return json(res, 404, {});
      }
      if (host === env.AUTH_HOST) return req.url.startsWith('/ui/') ? ui(req, res) : proxy(req, res, env.KRATOS_PUBLIC);
      if (host === env.HYDRA_HOST) return proxy(req, res, env.HYDRA_PUBLIC);
      if (rule.test(host) && req.url.startsWith('/.ory/')) return proxy(req, res, env.KRATOS_PUBLIC, '/.ory');
      return ns.handle(req, res);
    };
    go().catch((e) => { console.error(e); if (!res.headersSent) json(res, 500, { error: String(e) }); });
  });
  server.listen(env.LAB_PORT, '127.0.0.1', () => console.log(JSON.stringify({ listening: env.LAB_PORT, breaks: ns.breaks })));
}

main().catch((e) => { console.error(e); process.exit(1); });
