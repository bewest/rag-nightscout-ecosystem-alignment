'use strict';
// OAuth helpers shared by the Hydra probes: per-tenant client, authorize URL, first hop, code flow.
const crypto = require('crypto');
const H = require('./harness');

const HY = `http://${H.env.HYDRA_HOST}:${H.env.LAB_PORT}`;

async function mkClient (origin, name, extra = {}) {
  const r = await H.hydraAdmin('POST', '/admin/clients', Object.assign({
    client_name: name, redirect_uris: [`${origin}/oauth/callback`], audience: [origin],
    grant_types: ['authorization_code', 'refresh_token'], response_types: ['code'],
    scope: 'openid offline', token_endpoint_auth_method: 'client_secret_post'
  }, extra));
  if (r.status !== 201) throw new Error(`client ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}

function authUrl (client, redirectOrigin, audience) {
  const q = new URLSearchParams({ client_id: client.client_id, response_type: 'code', scope: 'openid offline', state: crypto.randomBytes(12).toString('hex'), redirect_uri: `${redirectOrigin}/oauth/callback` });
  if (audience) q.set('audience', audience);
  return `${HY}/oauth2/auth?${q}`;
}

// first hop only, no cookies: does Hydra hand the request to the login app, or refuse it?
async function firstHop (url) {
  const u = new URL(url);
  const r = await H.req(H.env.HYDRA_HOST, 'GET', u.pathname + u.search);
  const loc = r.headers.location || '';
  return { status: r.status, toLogin: loc.includes('/ui/hydra/login'), locationHost: loc ? new URL(loc, HY).hostname : null, error: new URL(loc, HY).searchParams.get('error') || null };
}

async function codeFlow (page, client, origin) {
  await page.goto(authUrl(client, origin, origin));
  if (page.url().includes('/ui/login')) {
    await page.fill('input[name=identifier]', page.__who.email);
    await page.fill('input[name=password]', page.__who.password);
    await Promise.all([page.waitForURL(/\/oauth\/callback/), page.click('button[name=method][value=password]')]);
  } else {
    await page.waitForURL(/\/oauth\/callback/);
  }
  const cb = new URL(page.url());
  const code = cb.searchParams.get('code');
  const t = await fetch(`${H.env.HYDRA_PUBLIC}/oauth2/token`, {
    method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: `${origin}/oauth/callback`, client_id: client.client_id, client_secret: client.client_secret })
  });
  return { callbackHost: cb.hostname, status: t.status, body: await t.json() };
}

module.exports = { mkClient, authUrl, firstHop, codeFlow, HY };
