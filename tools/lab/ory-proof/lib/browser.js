'use strict';
// Chrome helpers shared by probes/cookie-edge.js and probes/cookie-handoff.js.
const crypto = require('crypto');
const { chromium } = require('playwright');
const env = require('./env');

const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const AUTH = env.ORIGIN(env.AUTH_HOST);

async function launch () {
  return chromium.launch({ executablePath: CHROME, headless: true, args: ['--host-resolver-rules=MAP *.apex.test 127.0.0.1'] });
}

// Every main-frame navigation request, in order; `redirect` marks a hop the browser followed
// from a 3xx without user action. Query strings are dropped (they carry codes and flow ids).
function navRecorder (page) {
  const chain = [];
  page.on('request', (r) => {
    if (r.isNavigationRequest() && r.frame() === page.mainFrame()) {
      const u = new URL(r.url());
      chain.push({ method: r.method(), url: `${u.host}${u.pathname}`, redirect: !!r.redirectedFrom() });
    }
  });
  return {
    chain,
    mark () { return chain.length; },
    since (i) {
      const c = chain.slice(i);
      return { navigations: c.length, redirects: c.filter((x) => x.redirect).length, chain: c };
    }
  };
}

// Load `start`; if the Kratos login form appears, submit who's password. Returns what the user saw.
async function visit (page, rec, start, who) {
  const i = rec.mark();
  await page.goto(start);
  await page.waitForLoadState('load');
  let passwordEntered = false;
  if (await page.locator('form#f input[name=identifier]').count()) {
    if (!who) return Object.assign({ passwordEntered, loginFormShown: true, finalUrl: page.url() }, rec.since(i));
    await page.fill('input[name=identifier]', who.email);
    await page.fill('input[name=password]', who.password);
    await Promise.all([page.waitForLoadState('load'), page.click('button[name=method][value=password]')]);
    await page.waitForLoadState('load');
    passwordEntered = true;
  }
  const app = await page.locator('#app').count() ? JSON.parse(await page.locator('#app').innerText()) : null;
  const u = new URL(page.url());
  return Object.assign({ passwordEntered, finalUrl: `${u.host}${u.pathname}`, app, body: app ? null : (await page.locator('body').innerText()).slice(0, 300) }, rec.since(i));
}

async function sameOriginFetch (page, origin, path, method = 'POST') {
  await page.goto(`${origin}/__health`);
  return page.evaluate(async ([p, m]) => { const r = await fetch(p, { method: m }); return { status: r.status, body: await r.json().catch(() => null) }; }, [path, method]);
}

async function crossOriginFetch (page, fromOrigin, targetUrl) {
  await page.goto(`${fromOrigin}/__health`);
  return page.evaluate(async (t) => {
    try { const r = await fetch(t, { method: 'POST', credentials: 'include' }); return { readable: true, status: r.status }; } catch (e) { return { readable: false, error: String(e) }; }
  }, targetUrl);
}

// A cross-origin form POST (a navigation: no CORS involved). Returns the status and body shown.
async function crossOriginForm (page, fromOrigin, targetUrl) {
  await page.goto(`${fromOrigin}/__health`);
  const resp = page.waitForResponse((r) => r.url() === targetUrl && r.request().method() === 'POST');
  await page.evaluate((t) => { const f = document.createElement('form'); f.method = 'POST'; f.action = t; document.body.appendChild(f); f.submit(); }, targetUrl);
  const r = await resp;
  await page.waitForLoadState('load');
  return { status: r.status(), body: await r.json().catch(() => null) };
}

async function kratosLogout (page) {
  await page.goto(`${AUTH}/ui/home`);
  const lo = await page.evaluate(async () => { const r = await fetch('/self-service/logout/browser', { headers: { accept: 'application/json' } }); return { status: r.status, body: await r.json().catch(() => null) }; });
  if (lo.status !== 200) return { status: lo.status };
  const r = await page.goto(lo.body.logout_url);
  await page.goto(`${AUTH}/ui/home`);
  const whoami = await page.locator('#whoami').getAttribute('data-status');
  return { status: lo.status, logoutNav: r && r.status(), whoamiAfter: whoami };
}

const digest = (v) => crypto.createHash('sha256').update(v).digest('hex').slice(0, 16);
const jarSummary = async (ctx) => (await ctx.cookies()).map((c) => ({ name: c.name.replace(/^csrf_token_.*/, 'csrf_token_*'), domain: c.domain, httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite }));

module.exports = { launch, navRecorder, visit, sameOriginFetch, crossOriginFetch, crossOriginForm, kratosLogout, digest, jarSummary, AUTH };
