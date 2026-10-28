'use strict';
// ns-admin: the platform operator plane (D7). No credential; its protection
// is that only the operator zone (and, in B and C, an orchestrator) can reach
// it. It writes operator policy under the project floors (D22), creates and
// suspends tenants, and asks the secrets service to generate a signing key it
// never sees. It has no route that reveals a secret.
const { matrix, serve, call } = require('../lib/net');
const P = require('../lib/policy');
const { loadRun, load, save, audit } = require('../lib/store');

const run = loadRun(process.argv[2]);
const mx = matrix(run.design, run.breaks);
const opts = { noFloors: run.has('no-floors') };
const actor = () => ({ kind: 'operator-plane', id: null, verifiedBy: null });

serve('ns-admin', 'ns_admin', mx, [
  ['POST', /^\/tenants$/, async (req, m, b, ctx) => {
    const s = load(run.runDir);
    if (!/^[a-z0-9-]+$/.test(b.slug) || s.tenants[b.slug]) return [409, { error: 'slug' }];
    const policy = P.defaultPolicy();
    const bad = P.effectiveFloorViolations(P.effective(policy, {}));
    if (Object.keys(bad).length && !opts.noFloors) return [422, { error: 'floor', bad }];
    const pr = await call(mx, 'ns-admin', 'sec_operator', 'POST', `/t/${b.slug}/provision`, { kind: 'jwt' }, {}, ctx);
    if (pr.status !== 200) return [502, { error: 'provision', detail: pr.body }];
    s.tenants[b.slug] = { slug: b.slug, active: true, members: [b.owner] };
    s.policy[b.slug] = policy;
    s.owner[b.slug] = {};
    save(run.runDir, s);
    audit(run.runDir, 'ns-admin', { action: 'tenant-created', tenant: b.slug, actor: actor(), via: req.headers['x-lab-from'] });
    return [200, { ok: true }];
  }],
  ['POST', /^\/tenants\/([a-z0-9-]+)\/(suspend|activate)$/, async (req, m) => {
    const s = load(run.runDir);
    if (!s.tenants[m[1]]) return [404, { error: 'unknown-tenant' }];
    s.tenants[m[1]].active = m[2] === 'activate';
    save(run.runDir, s);
    audit(run.runDir, 'ns-admin', { action: m[2], tenant: m[1], actor: actor(), via: req.headers['x-lab-from'] });
    return [200, { ok: true }];
  }],
  ['PUT', /^\/tenants\/([a-z0-9-]+)\/policy\/([A-Z0-9_]+)$/, async (req, m, b) => {
    const s = load(run.runDir);
    if (!s.tenants[m[1]]) return [404, { error: 'unknown-tenant' }];
    const refused = P.checkPolicyWrite(m[2], b, opts);
    if (refused) {
      audit(run.runDir, 'ns-admin', { action: 'policy-write-refused', tenant: m[1], key: m[2], reason: refused, actor: actor(), via: req.headers['x-lab-from'] });
      return [422, { error: 'floor', reason: refused }];
    }
    s.policy[m[1]][m[2]] = b;
    save(run.runDir, s);
    audit(run.runDir, 'ns-admin', { action: 'policy-write', tenant: m[1], key: m[2], row: b, actor: actor(), via: req.headers['x-lab-from'] });
    return [200, { ok: true, effective: P.effective(s.policy[m[1]], s.owner[m[1]])[m[2]] }];
  }],
  ['GET', /^\/tenants\/([a-z0-9-]+)\/export$/, async (req, m) => {
    const s = load(run.runDir);
    if (!s.tenants[m[1]]) return [404, { error: 'unknown-tenant' }];
    return [200, { tenant: s.tenants[m[1]], policy: s.policy[m[1]], owner: s.owner[m[1]], effective: P.effective(s.policy[m[1]], s.owner[m[1]]) }];
  }]
]);
