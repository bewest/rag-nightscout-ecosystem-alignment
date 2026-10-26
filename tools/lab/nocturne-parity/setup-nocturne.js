// setup-nocturne.js — the credential and anonymous-access set-up on a fresh Nocturne database.
//
//   node setup-nocturne.js tenant <base> <tokenfile>
//     (Development server only) seeds one tenant with no sample data through Nocturne's dev-only
//     endpoint, signs in as its owner, and mints a direct grant with scope "*" through
//     POST /api/auth/direct-grants. The grant's plaintext token (noc_…) is the lab's full-access
//     credential: Nocturne also stores its SHA-1 (DirectGrantService.cs:175 at 89dcaf1dd), so a
//     Nightscout client configured with the token as its API secret authenticates with it.
//     The token is written to <tokenfile> (mode 600) and never printed.
//   node setup-nocturne.js public-read <base> <tokenfile>
//     gives the tenant's "Public" system member the read scopes Nocturne allows for it
//     (Scope.PublicShareScopes) and turns its 24-hour clamp off: the nearest analogue of
//     cgm-remote-monitor's AUTH_DEFAULT_ROLES=readable that Nocturne has. Read, not run: Nocturne
//     applies the Public member's permissions only to requests on a share-link host
//     (AuthenticationMiddleware.cs:225-227 at 89dcaf1dd, `context.IsShareAccess()`), so requests to
//     the apex are expected to be unchanged; the second probe run measures that.
//     Uses the token as a Bearer credential.
const fs = require('fs');
const [mode, base, tokenFile] = process.argv.slice(2);
async function call (method, path, {bearer, body} = {}) {
  const h = {};
  if (bearer) h.Authorization = 'Bearer ' + bearer;
  if (body !== undefined) h['Content-Type'] = 'application/json';
  const r = await fetch(base + path, {method, headers: h, body: body === undefined ? undefined : JSON.stringify(body)});
  const t = await r.text();
  let j; try { j = JSON.parse(t); } catch { j = undefined; }
  if (r.status >= 300) throw new Error(`${method} ${path} -> ${r.status} ${t.slice(0, 200)}`);
  return j;
}
(async () => {
  if (mode === 'tenant') {
    await call('POST', '/api/v4/dev-only/admin/seed-tenant', {body: {slug: 'npar', displayName: 'npar', ownerUsername: 'npar-owner', sampleData: false}});
    const login = await call('GET', '/api/v4/dev-only/auth/login?tenant=npar&format=json');
    const grant = await call('POST', '/api/auth/direct-grants', {bearer: login.accessToken, body: {label: 'npar-full', scopes: ['*']}});
    fs.writeFileSync(tokenFile, grant.token, {mode: 0o600});
    console.log(JSON.stringify({tenant: 'npar', grantScopes: grant.scopes}));
  } else if (mode === 'public-read') {
    const tok = fs.readFileSync(tokenFile, 'utf8').trim();
    const members = await call('GET', '/api/v4/member-invites/members', {bearer: tok});
    const pub = members.find(m => m.isSystemSubject && m.name === 'Public');
    if (!pub) throw new Error('no Public member');
    const perms = ['glucose.read', 'treatments.read', 'devices.read', 'heartrate.read', 'stepcount.read', 'food.read', 'reports.read', 'alerts.read'];
    await call('PUT', `/api/v4/member-invites/members/${pub.id}/permissions`, {bearer: tok, body: {directPermissions: perms}});
    await call('PUT', `/api/v4/member-invites/members/${pub.id}/limit-to-24-hours`, {bearer: tok, body: {limitTo24Hours: false}});
    const after = (await call('GET', '/api/v4/member-invites/members', {bearer: tok})).find(m => m.id === pub.id);
    console.log(JSON.stringify({publicDirectPermissions: after.directPermissions, limitTo24Hours: after.limitTo24Hours}));
  } else throw new Error('mode?');
})().catch(e => { console.error(e.message); process.exit(1); });
